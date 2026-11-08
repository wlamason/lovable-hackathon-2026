"""Modern condo open kitchen and living room.

Interior floor center is the world origin. Z is up. Floor top is Z=0.
Furniture front faces local -Y; anchor yaw is the Z rotation to apply.

Inspired by a bright NYC condo: cherry plank floor, white walls, a walnut
and white-gloss kitchen with a peninsula in the southeast corner, two
pendants, a tray ceiling and dropped beam, and a glass balcony door plus
window on the north wall.

Rebuild:
    blender -b --factory-startup --python build.py -- --outdir <dir>
"""

import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

# Interior 22.01 ft x 18.01 ft x 8.99 ft.
WIDTH_X = 6.71
DEPTH_Y = 5.49
HEIGHT_Z = 2.74
WALL_T = 0.12
FLOOR_T = 0.04
CEIL_T = 0.04

DOOR_W = 36 * 0.0254  # 0.9144
DOOR_H = 80 * 0.0254  # 2.032
DOOR_CX = -1.15

COUNTER_H = 36 * 0.0254  # 0.9144
COUNTER_D = 25 * 0.0254  # 0.635
TOP_T = 0.038
UPPER_Z0 = 54 * 0.0254  # 1.3716
UPPER_Z1 = 2.30
UPPER_D = 0.36
SOFFIT_Z = 2.42

BALC_X0 = -3.22
BALC_X1 = -1.70
WIN_X0 = -1.52
WIN_X1 = 1.05
WIN_SILL = 0.62
WIN_HEAD = 2.22
BALC_HEAD = 2.22

FRAME = 0.045

HX = WIDTH_X / 2
HY = DEPTH_Y / 2

# East run and peninsula. Peninsula overhangs to the west and north.
COUNTER_X0 = HX - COUNTER_D  # 2.720
COUNTER_Y0 = -HY + 0.012
COUNTER_Y1 = 0.15
RANGE_Y0 = -2.42
RANGE_Y1 = -1.68
FRIDGE_D = 0.76
FRIDGE_Y0 = 0.18
FRIDGE_Y1 = 0.18 + 0.914
FRIDGE_H = 1.82
FRIDGE_X0 = HX - FRIDGE_D

PEN_CAB_X0 = 1.25
PEN_TOP_X0 = 1.02
PEN_Y0 = -1.62
PEN_CAB_Y1 = -0.72
PEN_TOP_Y1 = -0.48

SINK_X0, SINK_X1 = 1.58, 2.18
SINK_Y0, SINK_Y1 = -1.30, -0.82

RAD_X0, RAD_X1 = -1.46, 0.98
RAD_DEPTH = 0.28


def outdir_from_args():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []
    out = os.path.dirname(os.path.abspath(__file__))
    if "--outdir" in argv:
        out = argv[argv.index("--outdir") + 1]
    os.makedirs(out, exist_ok=True)
    return out


def make_material(name, color, roughness=0.55, metallic=0.0, alpha=1.0, transmission=0.0, emission=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = (*color, alpha)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if "Alpha" in bsdf.inputs:
        bsdf.inputs["Alpha"].default_value = alpha
    for key in ("Transmission Weight", "Transmission"):
        if transmission and key in bsdf.inputs:
            bsdf.inputs[key].default_value = transmission
            break
    if emission:
        if "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = (*color, 1.0)
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = emission
    if alpha < 0.999 or transmission:
        if hasattr(mat, "blend_method"):
            try:
                mat.blend_method = "BLEND"
            except TypeError:
                pass
        if hasattr(mat, "surface_render_method"):
            try:
                mat.surface_render_method = "BLENDED"
            except TypeError:
                pass
        if hasattr(mat, "use_transparency_overlap"):
            mat.use_transparency_overlap = True
        mat.use_backface_culling = False
    return mat


def _fresh(bm):
    for vert in bm.verts:
        vert.tag = True
    return


def _assign_new(bm, existing, material_index):
    for face in bm.faces:
        if face not in existing:
            face.material_index = material_index


def add_box(bm, mn, mx, material_index):
    sx = mx[0] - mn[0]
    sy = mx[1] - mn[1]
    sz = mx[2] - mn[2]
    if sx <= 0 or sy <= 0 or sz <= 0:
        raise ValueError(f"degenerate box {mn} {mx}")
    _fresh(bm)
    existing = set(bm.faces)
    bmesh.ops.create_cube(bm, size=1.0)
    fresh = [vert for vert in bm.verts if not vert.tag]
    bmesh.ops.scale(bm, verts=fresh, vec=(sx, sy, sz))
    center = ((mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2, (mn[2] + mx[2]) / 2)
    bmesh.ops.translate(bm, verts=fresh, vec=center)
    _assign_new(bm, existing, material_index)


def add_cylinder(bm, radius, depth, location, material_index, segments=16):
    _fresh(bm)
    existing = set(bm.faces)
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        segments=segments,
        radius1=radius,
        radius2=radius,
        depth=depth,
    )
    fresh = [vert for vert in bm.verts if not vert.tag]
    bmesh.ops.translate(bm, verts=fresh, vec=location)
    _assign_new(bm, existing, material_index)


def add_cone(bm, radius_bottom, radius_top, depth, location, material_index, segments=16):
    _fresh(bm)
    existing = set(bm.faces)
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        segments=segments,
        radius1=radius_bottom,
        radius2=radius_top,
        depth=depth,
    )
    fresh = [vert for vert in bm.verts if not vert.tag]
    bmesh.ops.translate(bm, verts=fresh, vec=location)
    _assign_new(bm, existing, material_index)


def build_object(name, parts, materials, curves=None):
    """parts: list of (min_xyz, max_xyz, material). curves: optional extra callbacks."""
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    index_of = {}

    def mid(mat):
        if mat.name not in index_of:
            index_of[mat.name] = len(index_of)
            mesh.materials.append(mat)
        return index_of[mat.name]

    for mn, mx, mat in parts:
        add_box(bm, mn, mx, mid(mat))
    if curves:
        for fn in curves:
            fn(bm, mid)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def box(x0, y0, z0, x1, y1, z1, mat):
    return ((x0, y0, z0), (x1, y1, z1), mat)


def add_empty(name, location, yaw_deg):
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_type = "ARROWS"
    obj.empty_display_size = 0.28
    obj.location = location
    obj.rotation_euler = (0.0, 0.0, math.radians(yaw_deg))
    bpy.context.collection.objects.link(obj)
    return obj


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def world_bbox(objects):
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for obj in objects:
        for corner in obj.bound_box:
            w = obj.matrix_world @ Vector(corner)
            lo = Vector((min(lo[i], w[i]) for i in range(3)))
            hi = Vector((max(hi[i], w[i]) for i in range(3)))
    return lo, hi


def triangle_count(objects):
    total = 0
    for obj in objects:
        mesh = obj.data
        mesh.calc_loop_triangles()
        total += len(mesh.loop_triangles)
    return total


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = "METERS"

    floor_mat = make_material("Floor_Cherry", (0.40, 0.15, 0.05), roughness=0.34)
    seam_mat = make_material("Floor_Seam", (0.24, 0.09, 0.03), roughness=0.46)
    wall_mat = make_material("Wall_Paint", (0.95, 0.95, 0.94), roughness=0.72)
    ceil_mat = make_material("Ceiling_Paint", (0.97, 0.97, 0.96), roughness=0.78)
    trim_mat = make_material("Trim_Paint", (0.97, 0.96, 0.95), roughness=0.5)
    door_mat = make_material("Door_Paint", (0.94, 0.94, 0.93), roughness=0.45)
    frame_mat = make_material("Window_Frame", (0.93, 0.93, 0.91), roughness=0.35)
    glass_mat = make_material(
        "Window_Glass",
        (0.70, 0.84, 0.92),
        roughness=0.05,
        alpha=0.28,
        transmission=0.85,
    )
    metal_mat = make_material("Stainless", (0.58, 0.59, 0.61), roughness=0.28, metallic=0.92)
    metal_dark = make_material("Steel_Dark", (0.18, 0.19, 0.20), roughness=0.35, metallic=0.7)
    walnut = make_material("Walnut", (0.34, 0.17, 0.07), roughness=0.42)
    white_gloss = make_material("White_Gloss", (0.93, 0.93, 0.91), roughness=0.12)
    quartz = make_material("Quartz", (0.94, 0.94, 0.92), roughness=0.16)
    backsplash_mat = make_material("Backsplash", (0.96, 0.96, 0.95), roughness=0.3)
    black_mat = make_material("Black_Glass", (0.06, 0.06, 0.065), roughness=0.18, metallic=0.15)
    lamp_mat = make_material("Lamp_White", (1.0, 0.98, 0.94), roughness=0.3, emission=4.0)
    bulb_mat = make_material("Bulb", (1.0, 0.96, 0.88), roughness=0.2, emission=12.0)

    wall_z0 = -0.002
    wall_z1 = HEIGHT_Z + 0.002
    bite = 0.004
    top_z0 = COUNTER_H - TOP_T
    top_z1 = COUNTER_H

    # Floor, top at Z=0, with plank seams on the interior.
    floor_parts = [
        box(-(HX + WALL_T), -(HY + WALL_T), -FLOOR_T, HX + WALL_T, HY + WALL_T, 0.0, floor_mat)
    ]
    plank_w = 0.15
    x = -HX + plank_w
    index = 0
    while x < HX - 0.02:
        floor_parts.append(box(x, -HY + 0.01, -0.001, x + 0.005, HY - 0.01, 0.0022, seam_mat))
        y = -HY + (0.35 if index % 2 == 0 else 1.05)
        while y < HY - 0.08:
            floor_parts.append(box(x - plank_w + 0.01, y, -0.001, x - 0.01, y + 0.005, 0.0022, seam_mat))
            y += 1.45
        x += plank_w
        index += 1
    build_object("Floor", floor_parts, [floor_mat, seam_mat])

    # North wall: balcony door (floor to head) and a wide window over a sill.
    north = [
        box(-HX, HY, wall_z0, BALC_X0, HY + WALL_T, wall_z1, wall_mat),
        box(BALC_X1, HY, wall_z0, WIN_X0, HY + WALL_T, wall_z1, wall_mat),
        box(WIN_X1, HY, wall_z0, HX, HY + WALL_T, wall_z1, wall_mat),
        box(BALC_X0, HY, BALC_HEAD, BALC_X1, HY + WALL_T, wall_z1, wall_mat),
        box(WIN_X0, HY, wall_z0, WIN_X1, HY + WALL_T, WIN_SILL, wall_mat),
        box(WIN_X0, HY, WIN_HEAD, WIN_X1, HY + WALL_T, wall_z1, wall_mat),
    ]
    build_object("Wall_N", north, [wall_mat])

    door_x0 = DOOR_CX - DOOR_W / 2
    door_x1 = DOOR_CX + DOOR_W / 2
    south_y0 = -(HY + WALL_T)
    south_y1 = -HY
    build_object(
        "Wall_S",
        [
            box(-HX, south_y0, wall_z0, door_x0, south_y1, wall_z1, wall_mat),
            box(door_x1, south_y0, wall_z0, HX, south_y1, wall_z1, wall_mat),
            box(door_x0, south_y0, DOOR_H, door_x1, south_y1, wall_z1, wall_mat),
        ],
        [wall_mat],
    )
    build_object(
        "Wall_W",
        [box(-(HX + WALL_T), -(HY + WALL_T), wall_z0, -HX, HY + WALL_T, wall_z1, wall_mat)],
        [wall_mat],
    )
    build_object(
        "Wall_E",
        [box(HX, -(HY + WALL_T), wall_z0, HX + WALL_T, HY + WALL_T, wall_z1, wall_mat)],
        [wall_mat],
    )

    build_object(
        "Ceiling",
        [box(-HX, -HY, HEIGHT_Z, HX, HY, HEIGHT_Z + CEIL_T, ceil_mat)],
        [ceil_mat],
    )

    # Dropped beam across the room, plus a tray frame over the kitchen.
    tray_x0 = 1.10
    tray_inner_x = 1.48
    tray_inner_y0 = -HY + 0.40
    beam_y0 = 1.02
    beam_y1 = 1.40
    soffit = [
        box(-HX, beam_y0, SOFFIT_Z, HX, beam_y1, HEIGHT_Z, ceil_mat),
        box(tray_x0, -HY, SOFFIT_Z, tray_inner_x, beam_y0, HEIGHT_Z, ceil_mat),
        box(tray_inner_x, -HY, SOFFIT_Z, HX, tray_inner_y0, HEIGHT_Z, ceil_mat),
        box(HX - 0.38, tray_inner_y0, SOFFIT_Z, HX, beam_y0, HEIGHT_Z, ceil_mat),
    ]
    build_object("Ceiling_Soffit", soffit, [ceil_mat])

    # Baseboard, broken for the entry, the balcony door, and the kitchen run.
    base_h = 0.089
    base_t = 0.016
    casing_w = 0.07
    base_parts = [
        box(-HX, HY - base_t, -bite, BALC_X0 - 0.01, HY + bite, base_h, trim_mat),
        box(BALC_X1 + 0.01, HY - base_t, -bite, HX, HY + bite, base_h, trim_mat),
        box(-HX, -HY - bite, -bite, door_x0 - casing_w, -HY + base_t, base_h, trim_mat),
        box(door_x1 + casing_w, -HY - bite, -bite, HX, -HY + base_t, base_h, trim_mat),
        box(-HX - bite, -HY + base_t, -bite, -HX + base_t, HY - base_t, base_h, trim_mat),
        box(HX - base_t, FRIDGE_Y1 + 0.02, -bite, HX + bite, HY - base_t, base_h, trim_mat),
    ]
    build_object("Baseboard", base_parts, [trim_mat])

    # Window on the north wall.
    glass_t = 0.01
    glass_y = HY + WALL_T / 2
    lip = 0.006
    mullion = 0.028
    win_parts = [
        box(WIN_X0 - lip, HY, WIN_SILL - lip, WIN_X1 + lip, HY + WALL_T, WIN_SILL + FRAME, frame_mat),
        box(WIN_X0 - lip, HY, WIN_HEAD - FRAME, WIN_X1 + lip, HY + WALL_T, WIN_HEAD + lip, frame_mat),
        box(WIN_X0 - lip, HY, WIN_SILL + FRAME, WIN_X0 + FRAME, HY + WALL_T, WIN_HEAD - FRAME, frame_mat),
        box(WIN_X1 - FRAME, HY, WIN_SILL + FRAME, WIN_X1 + lip, HY + WALL_T, WIN_HEAD - FRAME, frame_mat),
    ]
    pane = WIN_X1 - WIN_X0 - 2 * FRAME
    for i in range(1, 4):
        mx = WIN_X0 + FRAME + pane * i / 4
        win_parts.append(
            box(mx - mullion / 2, HY, WIN_SILL + FRAME, mx + mullion / 2, HY + WALL_T, WIN_HEAD - FRAME, frame_mat)
        )
    win_parts.append(
        box(WIN_X0 + FRAME, glass_y - glass_t / 2, WIN_SILL + FRAME, WIN_X1 - FRAME, glass_y + glass_t / 2, WIN_HEAD - FRAME, glass_mat)
    )
    # Interior sill.
    win_parts.append(box(WIN_X0 - 0.02, HY - 0.04, WIN_SILL - 0.02, WIN_X1 + 0.02, HY + lip, WIN_SILL + 0.012, frame_mat))
    build_object("Window_N", win_parts, [frame_mat, glass_mat])

    # Sliding balcony door.
    balc_parts = [
        box(BALC_X0 - lip, HY, 0.0, BALC_X1 + lip, HY + WALL_T, FRAME, frame_mat),
        box(BALC_X0 - lip, HY, BALC_HEAD - FRAME, BALC_X1 + lip, HY + WALL_T, BALC_HEAD + lip, frame_mat),
        box(BALC_X0 - lip, HY, FRAME, BALC_X0 + FRAME, HY + WALL_T, BALC_HEAD - FRAME, frame_mat),
        box(BALC_X1 - FRAME, HY, FRAME, BALC_X1 + lip, HY + WALL_T, BALC_HEAD - FRAME, frame_mat),
        box((BALC_X0 + BALC_X1) / 2 - mullion / 2, HY, FRAME, (BALC_X0 + BALC_X1) / 2 + mullion / 2, HY + WALL_T, BALC_HEAD - FRAME, frame_mat),
        box(BALC_X0 + FRAME, glass_y - glass_t / 2, FRAME, BALC_X1 - FRAME, glass_y + glass_t / 2, BALC_HEAD - FRAME, glass_mat),
        # Pull on the interior face, right leaf.
        box(BALC_X1 - 0.12, HY - 0.02, 1.00, BALC_X1 - 0.09, HY + 0.004, 1.18, metal_mat),
    ]
    build_object("Door_Balcony", balc_parts, [frame_mat, glass_mat, metal_mat])

    # White entry door on the south wall.
    slab_t = 0.035
    slab_y1 = south_y0 + 0.03 + slab_t
    slab_y0 = slab_y1 - slab_t
    gap = 0.008
    door_parts = [
        box(door_x0 + gap, slab_y0, 0.012, door_x1 - gap, slab_y1, DOOR_H - gap, door_mat),
        box(door_x0 - casing_w, -HY - bite, -bite, door_x0, -HY + 0.018, DOOR_H + casing_w, trim_mat),
        box(door_x1, -HY - bite, -bite, door_x1 + casing_w, -HY + 0.018, DOOR_H + casing_w, trim_mat),
        box(door_x0, -HY - bite, DOOR_H, door_x1, -HY + 0.018, DOOR_H + casing_w, trim_mat),
        box(door_x1 - 0.10, slab_y0 - 0.02, 0.98, door_x1 - 0.07, slab_y0, 1.05, metal_mat),
        box(door_x1 - 0.18, slab_y0 - 0.016, 1.005, door_x1 - 0.075, slab_y0 - 0.006, 1.02, metal_mat),
    ]
    build_object("Door", door_parts, [door_mat, trim_mat, metal_mat])

    # Low radiator / AC cover under the window.
    rad_y1 = HY - 0.02
    rad_y0 = rad_y1 - RAD_DEPTH
    rad_parts = [box(RAD_X0, rad_y0, 0.0, RAD_X1, rad_y1, 0.40, trim_mat)]
    slot_y0 = rad_y0 - 0.004
    for i in range(5):
        z0 = 0.08 + i * 0.055
        rad_parts.append(box(RAD_X0 + 0.06, slot_y0, z0, RAD_X1 - 0.06, rad_y0, z0 + 0.012, metal_dark))
    build_object("Radiator", rad_parts, [trim_mat, metal_dark])

    # Walnut base cabinets: east run (split by the range) and the peninsula.
    cab_z0 = 0.10
    cab_z1 = top_z0 + 0.002
    base_parts = [
        box(COUNTER_X0 + 0.012, COUNTER_Y0, cab_z0, HX - 0.004, RANGE_Y0 - 0.01, cab_z1, walnut),
        box(COUNTER_X0 + 0.012, RANGE_Y1 + 0.01, cab_z0, HX - 0.004, COUNTER_Y1, cab_z1, walnut),
        box(PEN_CAB_X0, PEN_Y0, cab_z0, COUNTER_X0 + 0.002, PEN_CAB_Y1, cab_z1, walnut),
    ]
    # White gloss doors on the peninsula's north (living) face.
    door_y0 = PEN_CAB_Y1 - 0.004
    door_y1 = PEN_CAB_Y1 + 0.014
    for x0, x1 in ((1.30, 1.74), (1.78, 2.22), (2.26, 2.68)):
        base_parts.append(box(x0, door_y0, 0.16, x1, door_y1, 0.84, white_gloss))
    # Stainless dishwasher on the south face of the peninsula.
    base_parts.append(box(2.20, PEN_Y0 - 0.016, 0.14, 2.68, PEN_Y0 + 0.002, 0.86, metal_mat))
    build_object("Kitchen_Base", base_parts, [walnut, white_gloss, metal_mat])

    # Quartz L top with a sink cutout in the peninsula.
    pen_top_x1 = COUNTER_X0 - 0.001
    counter_parts = [
        box(COUNTER_X0, COUNTER_Y0, top_z0, HX + 0.002, COUNTER_Y1, top_z1, quartz),
        box(PEN_TOP_X0, PEN_Y0, top_z0, SINK_X0, PEN_TOP_Y1, top_z1, quartz),
        box(SINK_X1, PEN_Y0, top_z0, pen_top_x1, PEN_TOP_Y1, top_z1, quartz),
        box(SINK_X0, PEN_Y0, top_z0, SINK_X1, SINK_Y0, top_z1, quartz),
        box(SINK_X0, SINK_Y1, top_z0, SINK_X1, PEN_TOP_Y1, top_z1, quartz),
    ]
    build_object("Kitchen_Counter", counter_parts, [quartz])

    basin_z = 0.78
    sink_parts = [
        box(SINK_X0 + 0.015, SINK_Y0 + 0.015, basin_z, SINK_X1 - 0.015, SINK_Y0 + 0.03, top_z0 + 0.004, metal_mat),
        box(SINK_X0 + 0.015, SINK_Y1 - 0.03, basin_z, SINK_X1 - 0.015, SINK_Y1 - 0.015, top_z0 + 0.004, metal_mat),
        box(SINK_X0 + 0.015, SINK_Y0 + 0.03, basin_z, SINK_X0 + 0.03, SINK_Y1 - 0.03, top_z0 + 0.004, metal_mat),
        box(SINK_X1 - 0.03, SINK_Y0 + 0.03, basin_z, SINK_X1 - 0.015, SINK_Y1 - 0.03, top_z0 + 0.004, metal_mat),
        box(SINK_X0 + 0.03, SINK_Y0 + 0.03, basin_z, SINK_X1 - 0.03, SINK_Y1 - 0.03, basin_z + 0.012, metal_mat),
        # Faucet on the north rim.
        box(1.84, SINK_Y1 - 0.02, top_z1, 1.96, SINK_Y1 + 0.05, 1.16, metal_mat),
        box(1.84, SINK_Y0 + 0.12, 1.12, 1.96, SINK_Y1 + 0.02, 1.16, metal_mat),
    ]
    build_object("Kitchen_Sink", sink_parts, [metal_mat])

    # Uppers: walnut carcass, white-gloss and walnut doors, open bay for the hood.
    upper_sections = [
        (-HY + 0.02, RANGE_Y0 - 0.02, walnut),
        (RANGE_Y1 + 0.04, -0.55, white_gloss),
        (-0.52, -0.02, white_gloss),
        (0.01, COUNTER_Y1, walnut),
    ]
    upper_parts = []
    face_x = HX - UPPER_D
    for y0, y1, door_mat in upper_sections:
        upper_parts.append(box(face_x, y0, UPPER_Z0, HX + 0.002, y1, UPPER_Z1, walnut))
        upper_parts.append(
            box(face_x - 0.014, y0 + 0.025, UPPER_Z0 + 0.025, face_x + 0.003, y1 - 0.025, UPPER_Z1 - 0.025, door_mat)
        )
    build_object("Kitchen_Uppers", upper_parts, [walnut, white_gloss])

    splash_parts = [
        box(HX - 0.018, COUNTER_Y0, top_z1, HX + 0.004, RANGE_Y0, UPPER_Z0, backsplash_mat),
        box(HX - 0.018, RANGE_Y1, top_z1, HX + 0.004, COUNTER_Y1, UPPER_Z0, backsplash_mat),
        box(HX - 0.012, RANGE_Y0, top_z1, HX + 0.004, RANGE_Y1, UPPER_Z0, metal_mat),
    ]
    build_object("Kitchen_Backsplash", splash_parts, [backsplash_mat, metal_mat])

    fridge_parts = [
        box(FRIDGE_X0, FRIDGE_Y0, 0.0, HX - 0.004, FRIDGE_Y1, FRIDGE_H, metal_mat),
        box(FRIDGE_X0 - 0.008, (FRIDGE_Y0 + FRIDGE_Y1) / 2 - 0.008, 0.62, FRIDGE_X0 + 0.002, (FRIDGE_Y0 + FRIDGE_Y1) / 2 + 0.008, FRIDGE_H - 0.04, metal_dark),
        box(FRIDGE_X0 - 0.008, FRIDGE_Y0 + 0.04, 0.58, FRIDGE_X0 + 0.002, FRIDGE_Y1 - 0.04, 0.60, metal_dark),
        box(FRIDGE_X0 - 0.02, FRIDGE_Y0 + 0.08, 1.05, FRIDGE_X0 - 0.004, FRIDGE_Y0 + 0.12, 1.45, metal_dark),
        box(FRIDGE_X0 - 0.02, FRIDGE_Y1 - 0.12, 1.05, FRIDGE_X0 - 0.004, FRIDGE_Y1 - 0.08, 1.45, metal_dark),
    ]
    build_object("Kitchen_Fridge", fridge_parts, [metal_mat, metal_dark])

    range_parts = [
        box(COUNTER_X0 + 0.02, RANGE_Y0, cab_z0, HX - 0.006, RANGE_Y1, cab_z1, metal_mat),
        box(COUNTER_X0 + 0.005, RANGE_Y0 + 0.08, 0.28, COUNTER_X0 + 0.02, RANGE_Y1 - 0.08, 0.72, black_mat),
        box(COUNTER_X0 - 0.012, RANGE_Y0 + 0.16, 0.62, COUNTER_X0 + 0.008, RANGE_Y1 - 0.16, 0.66, metal_dark),
        box(COUNTER_X0 + 0.05, RANGE_Y0 + 0.08, top_z1 - 0.002, HX - 0.05, RANGE_Y1 - 0.06, top_z1 + 0.012, black_mat),
    ]
    build_object("Kitchen_Range", range_parts, [metal_mat, black_mat, metal_dark])

    hood_parts = [
        box(HX - 0.52, RANGE_Y0 + 0.04, 1.58, HX + 0.002, RANGE_Y1 - 0.04, UPPER_Z1, metal_mat),
        box(HX - 0.50, RANGE_Y0 + 0.08, 1.52, HX - 0.46, RANGE_Y1 - 0.08, 1.58, metal_mat),
    ]
    build_object("Kitchen_Hood", hood_parts, [metal_mat])

    def pendant_curves(bm, mid):
        shade_depth = 0.20
        for px in (1.62, 2.22):
            loc_z = 1.78 + shade_depth / 2
            add_cone(bm, 0.09, 0.032, shade_depth, (px, -1.05, loc_z), mid(lamp_mat), segments=20)
            add_cylinder(bm, 0.006, HEIGHT_Z - (loc_z + shade_depth / 2), (px, -1.05, (HEIGHT_Z + loc_z + shade_depth / 2) / 2), mid(trim_mat), segments=8)
            add_cylinder(bm, 0.035, 0.012, (px, -1.05, HEIGHT_Z - 0.008), mid(trim_mat), segments=12)

    build_object("Kitchen_Pendants", [], [lamp_mat, trim_mat], curves=[pendant_curves])

    def light_curves(bm, mid):
        spots = ((2.15, -1.15), (2.15, -0.35), (2.55, -1.70), (-1.4, 0.3), (-0.4, -1.3), (0.3, 1.7))
        for lx, ly in spots:
            add_cylinder(bm, 0.055, 0.012, (lx, ly, HEIGHT_Z - 0.008), mid(trim_mat), segments=16)
            add_cylinder(bm, 0.032, 0.008, (lx, ly, HEIGHT_Z - 0.016), mid(bulb_mat), segments=12)

    build_object("Recessed_Lights", [], [trim_mat, bulb_mat], curves=[light_curves])

    anchors = [
        ("TV_wall", (-3.22, 0.20, 0.0), 90),
        ("Sofa_spot", (-0.85, 0.20, 0.0), -90),
        ("Rug_center", (-1.50, 0.20, 0.0), 90),
        ("Coffee_spot", (-2.15, 0.20, 0.0), 0),
        ("Plant_corner", (-2.85, 2.15, 0.0), 45),
        ("Lamp_corner", (-2.85, -2.15, 0.0), 135),
        ("Bar_spot", (1.85, -0.05, 0.0), 0),
    ]
    for name, loc, yaw in anchors:
        add_empty(name, loc, yaw)

    meshes = [obj for obj in scene.objects if obj.type == "MESH"]
    lo, hi = world_bbox(meshes)
    size = hi - lo
    tris = triangle_count(meshes)
    print(f"BBOX min {tuple(round(v, 4) for v in lo)}")
    print(f"BBOX max {tuple(round(v, 4) for v in hi)}")
    print(f"BBOX size {tuple(round(v, 4) for v in size)}")
    print(f"TRIANGLES {tris}")
    for obj in meshes:
        obj.data.calc_loop_triangles()
        print(f"  {obj.name} {len(obj.data.loop_triangles)}")

    def rnd(v):
        return [round(float(v[0]), 4), round(float(v[1]), 4), round(float(v[2]), 4)]

    def r3(x, y, z=0.0):
        return [round(x, 4), round(y, 4), round(z, 4)]

    free_poly = [
        [-HX, -HY],
        [COUNTER_X0, -HY],
        [COUNTER_X0, PEN_Y0],
        [PEN_TOP_X0, PEN_Y0],
        [PEN_TOP_X0, PEN_TOP_Y1],
        [COUNTER_X0, PEN_TOP_Y1],
        [COUNTER_X0, COUNTER_Y1],
        [FRIDGE_X0, COUNTER_Y1],
        [FRIDGE_X0, FRIDGE_Y1],
        [HX, FRIDGE_Y1],
        [HX, HY],
        [RAD_X1, HY],
        [RAD_X1, HY - 0.02 - RAD_DEPTH],
        [RAD_X0, HY - 0.02 - RAD_DEPTH],
        [RAD_X0, HY],
        [-HX, HY],
    ]

    meta = {
        "id": "condo_open_kitchen",
        "name": "Modern Condo Open Kitchen",
        "description": (
            "Open-plan condo living room with a walnut and white-gloss kitchen in the "
            "southeast corner. Cherry plank floor, white walls, quartz counters, a peninsula "
            "with a sink, stainless fridge and range, two pendants, a tray ceiling over the "
            "kitchen, a dropped beam, and a glass balcony door plus window on the north wall. "
            "The west side of the room is open for seating."
        ),
        "units": "meters",
        "up_axis": "Z",
        "origin": "interior floor center (0, 0, 0); floor top is Z=0",
        "furniture_front": "local -Y; anchor rotation_z_deg is the yaw to apply",
        "interior_m": {"width_x": WIDTH_X, "depth_y": DEPTH_Y, "height_z": HEIGHT_Z},
        "interior_ft": {
            "width_x": round(WIDTH_X / 0.3048, 2),
            "depth_y": round(DEPTH_Y / 0.3048, 2),
            "height_z": round(HEIGHT_Z / 0.3048, 2),
        },
        "ceiling_height_m": HEIGHT_Z,
        "ceiling_height_ft": round(HEIGHT_Z / 0.3048, 2),
        "soffit_bottom_m": SOFFIT_Z,
        "wall_thickness_m": WALL_T,
        "walls": {
            "Wall_N": "+Y wall, balcony door and window",
            "Wall_S": "-Y wall, entry door",
            "Wall_E": "+X wall, kitchen run",
            "Wall_W": "-X wall, TV side",
        },
        "openings": {
            "window": {
                "object": "Window_N",
                "wall": "Wall_N",
                "width_m": round(WIN_X1 - WIN_X0, 4),
                "height_m": round(WIN_HEAD - WIN_SILL, 4),
                "sill_z_m": WIN_SILL,
                "center_m": r3((WIN_X0 + WIN_X1) / 2, HY + WALL_T / 2, (WIN_SILL + WIN_HEAD) / 2),
            },
            "balcony_door": {
                "object": "Door_Balcony",
                "wall": "Wall_N",
                "width_m": round(BALC_X1 - BALC_X0, 4),
                "height_m": BALC_HEAD,
                "sill_z_m": 0.0,
                "center_m": r3((BALC_X0 + BALC_X1) / 2, HY + WALL_T / 2, BALC_HEAD / 2),
                "note": "Sliding glass door, no swing.",
            },
            "door": {
                "object": "Door",
                "wall": "Wall_S",
                "width_in": 36,
                "height_in": 80,
                "width_m": round(DOOR_W, 4),
                "height_m": round(DOOR_H, 4),
                "center_m": r3(DOOR_CX, -HY - WALL_T / 2, DOOR_H / 2),
            },
        },
        "bbox_m": {"min": rnd(lo), "max": rnd(hi), "size": rnd(size)},
        "free_floor": {
            "note": (
                "Open floor for furniture, excluding the east counter, peninsula "
                "(including the bar overhang), fridge, and the radiator under the window. "
                "Keep about 0.9 m clear in front of the south entry door. "
                "The rect is the primary seating zone inside that polygon."
            ),
            "rect_m": {
                "min_xy": [-3.20, -1.80],
                "max_xy": [0.85, 2.15],
            },
            "polygon_xy_m": [[round(p[0], 4), round(p[1], 4)] for p in free_poly],
        },
        "empties": {
            "TV_wall": {
                "position_m": r3(-3.22, 0.20),
                "rotation_z_deg": 90,
                "note": "Floor anchor on the west wall. Yaw 90 so a TV's front (local -Y) faces east into the room. Raise Z to mount the screen.",
            },
            "Sofa_spot": {
                "position_m": r3(-0.85, 0.20),
                "rotation_z_deg": -90,
                "note": "Floor anchor for a sofa. Yaw -90 so its front (local -Y) faces west toward TV_wall.",
            },
            "Rug_center": {
                "position_m": r3(-1.50, 0.20),
                "rotation_z_deg": 90,
                "note": "Center of the seating rug. Yaw 90 so the long side runs east-west under the sofa and coffee table.",
            },
            "Coffee_spot": {
                "position_m": r3(-2.15, 0.20),
                "rotation_z_deg": 0,
                "note": "Floor anchor for a coffee table between the sofa and the TV wall.",
            },
            "Plant_corner": {
                "position_m": r3(-2.85, 2.15),
                "rotation_z_deg": 45,
                "note": "Northwest corner beside the balcony glazing. Yaw 45 faces the plant into the room.",
            },
            "Lamp_corner": {
                "position_m": r3(-2.85, -2.15),
                "rotation_z_deg": 135,
                "note": "Southwest corner. Yaw 135 faces the lamp northeast toward the seating area.",
            },
            "Bar_spot": {
                "position_m": r3(1.85, -0.05),
                "rotation_z_deg": 0,
                "note": "North of the peninsula overhang, facing the counter (yaw 0). A second stool can sit about 0.55 m to the side on X.",
            },
        },
        "triangle_count": tris,
        "objects": [
            "Floor",
            "Wall_N",
            "Wall_S",
            "Wall_E",
            "Wall_W",
            "Ceiling",
            "Ceiling_Soffit",
            "Baseboard",
            "Window_N",
            "Door_Balcony",
            "Door",
            "Radiator",
            "Kitchen_Base",
            "Kitchen_Counter",
            "Kitchen_Sink",
            "Kitchen_Uppers",
            "Kitchen_Backsplash",
            "Kitchen_Fridge",
            "Kitchen_Range",
            "Kitchen_Hood",
            "Kitchen_Pendants",
            "Recessed_Lights",
            "TV_wall",
            "Sofa_spot",
            "Rug_center",
            "Coffee_spot",
            "Plant_corner",
            "Lamp_corner",
            "Bar_spot",
        ],
    }
    return meta


def add_camera_and_sun():
    scene = bpy.context.scene
    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens = 16
    cam_data.clip_start = 0.05
    cam_data.clip_end = 40
    cam = bpy.data.objects.new("Camera", cam_data)
    bpy.context.collection.objects.link(cam)
    # Wide interior view: balcony door and window on the left, kitchen on the right.
    cam.location = (-2.35, -2.30, 1.52)
    look_at(cam, Vector((-0.15, 0.45, 1.02)))
    scene.camera = cam

    sun_data = bpy.data.lights.new("Sun", "SUN")
    sun_data.energy = 1.8
    sun_data.color = (1.0, 0.95, 0.88)
    sun_data.angle = math.radians(6)
    sun = bpy.data.objects.new("Sun", sun_data)
    bpy.context.collection.objects.link(sun)
    # Rays travel toward -Y (in from the north glazing) and downward.
    sun.rotation_euler = (math.radians(-58), math.radians(18), math.radians(8))

    fill_data = bpy.data.lights.new("Fill", "AREA")
    fill_data.energy = 28
    fill_data.size = 4.5
    fill_data.color = (1.0, 0.97, 0.93)
    fill = bpy.data.objects.new("Fill", fill_data)
    bpy.context.collection.objects.link(fill)
    fill.location = (-0.4, -0.2, 2.55)
    fill.rotation_euler = (0.0, 0.0, 0.0)

    window_data = bpy.data.lights.new("WindowFill", "AREA")
    window_data.energy = 45
    window_data.size = 3.2
    window_data.color = (0.92, 0.95, 1.0)
    window_light = bpy.data.objects.new("WindowFill", window_data)
    bpy.context.collection.objects.link(window_light)
    window_light.location = (-0.6, 2.2, 1.7)
    look_at(window_light, Vector((-0.4, 0.0, 0.8)))

    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.70, 0.80, 0.90, 1.0)
    bg.inputs["Strength"].default_value = 0.45
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.exposure = 0.0


def render_preview(path):
    scene = bpy.context.scene
    scene.render.resolution_x = 1024
    scene.render.resolution_y = 640
    scene.render.resolution_percentage = 100
    scene.render.filepath = path
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    # South wall is behind the interior camera. Ceiling stays so the tray reads.
    hidden = []
    for name in ("Wall_S",):
        obj = bpy.data.objects.get(name)
        if obj:
            hidden.append(obj)
            obj.hide_render = True
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
        if hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
            scene.eevee.taa_render_samples = 24
        bpy.ops.render.render(write_still=True)
        print("RENDER engine BLENDER_EEVEE_NEXT")
    except Exception as exc:
        print("EEVEE failed:", exc)
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.display.shading.light = "STUDIO"
        scene.display.shading.color_type = "MATERIAL"
        scene.display.shading.show_shadows = True
        bpy.ops.render.render(write_still=True)
        print("RENDER engine BLENDER_WORKBENCH")
    for obj in hidden:
        obj.hide_render = False


def export_assets(out, meta):
    glb = os.path.join(out, "model.glb")
    blend = os.path.join(out, "model.blend")
    preview = os.path.join(out, "preview.png")
    meta_path = os.path.join(out, "metadata.json")

    render_preview(preview)

    for obj in bpy.context.view_layer.objects:
        obj.select_set(obj.type in {"MESH", "EMPTY"})
    bpy.ops.export_scene.gltf(
        filepath=glb,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_materials="EXPORT",
        export_cameras=False,
        export_lights=False,
    )
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
        fh.write("\n")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    print("WROTE", glb)
    print("WROTE", blend)
    print("WROTE", preview)
    print("WROTE", meta_path)


def main():
    out = outdir_from_args()
    meta = build()
    add_camera_and_sun()
    export_assets(out, meta)


if __name__ == "__main__":
    main()
