"""Beamed living room with a corner fireplace.

Interior floor center is the world origin. Z is up. The floor top is Z=0.
Looking from the south (-Y) toward the north wall matches the reference photo:

- West wall (-X): glass French doors, toward the near (south) end.
- North wall (+Y): white entry door, then a three-section picture window.
- Northeast corner: angled tile fireplace with a raised hearth.
- East wall (+X): solid wall. The TV anchor sits south of the hearth.
- Four dark beams run east-west (along X) under a white ceiling.

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

FT = 0.3048
IN = 0.0254

# 18 ft wide (X, the far wall) by 21 ft deep (Y) by 8.5 ft tall.
WIDTH_X = 18 * FT
DEPTH_Y = 21 * FT
HEIGHT_Z = 8.5 * FT
WALL_T = 0.12
FLOOR_T = 0.04
CEIL_T = 0.04

DOOR_W = 36 * IN
DOOR_H = 80 * IN

BASE_H = 3.5 * IN
BASE_T = 0.016
CASING = 0.065
CASING_T = 0.016

HX = WIDTH_X / 2
HY = DEPTH_Y / 2
INV = math.sqrt(0.5)

# North wall, west to east: margin, entry door, gap, picture window, gap, fireplace.
ENTRY_X0 = -HX + 0.48
ENTRY_X1 = ENTRY_X0 + DOOR_W
WIN_W = 2.05
WIN_X0 = ENTRY_X1 + 0.42
WIN_X1 = WIN_X0 + WIN_W
WIN_SILL = 0.78
WIN_HEAD = 2.22
WIN_FRAME = 0.052
WIN_MULLION = 0.04

# Fireplace leg along each wall. The angled face meets the north wall just past the window.
FACE_X = WIN_X1 + 0.18
FP_A = HX - FACE_X
P_N = (FACE_X, HY)
P_E = (HX, HY - FP_A)
CORNER = (HX, HY)
HEARTH_D = 0.64
HEARTH_H = 0.102
FP_TOP = 2.18
OFF = HEARTH_D * INV
Q1 = (P_N[0] - OFF, P_N[1] - OFF)
Q2 = (P_E[0] - OFF, P_E[1] - OFF)

# French pair on the west wall, in the near half so a south camera sees them on the left.
FRENCH_W = 64 * IN
FRENCH_Y0 = -HY + 1.35
FRENCH_Y1 = FRENCH_Y0 + FRENCH_W
FRENCH_OPEN = 80.0  # degrees each leaf swings into the room

# Beams along X. Beam_1 is the northernmost.
BEAM_W = 0.18
BEAM_H = 0.22
BEAM_MARGIN_N = 0.92
BEAM_MARGIN_S = 1.45
BEAM_SPAN = DEPTH_Y - BEAM_MARGIN_N - BEAM_MARGIN_S
BEAM_YS = [HY - BEAM_MARGIN_N - i * (BEAM_SPAN / 3) for i in range(4)]

# Family seating faces the east wall, with the fireplace ahead and to the right.
SOFA_X = -0.40
SOFA_Y = 0.32
SOFA_YAW = 90.0
TV_X = HX - 0.15
TV_Y = SOFA_Y
TV_YAW = -90.0
COFFEE_X = 0.90
COFFEE_Y = SOFA_Y
RUG_X = 0.22
RUG_Y = SOFA_Y
PLANT_X = -2.46
PLANT_Y = 2.48
PLANT_YAW = 45.0
LAMP_X = -2.32
LAMP_Y = -2.85
LAMP_YAW = 135.0
SIDE_X = SOFA_X
SIDE_Y = 1.70

# Raised tile the fireplace sits on. Not free floor.
HEARTH_POLY = [Q1, Q2, P_E, CORNER, P_N]
# Interior floor minus that platform.
FREE_POLY = [
    (-HX, -HY),
    (HX, -HY),
    P_E,
    Q2,
    Q1,
    P_N,
    (-HX, HY),
]


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


def make_material(name, color, roughness=0.55, metallic=0.0, alpha=1.0, transmission=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = (*color, alpha)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if "Alpha" in bsdf.inputs:
        bsdf.inputs["Alpha"].default_value = alpha
    if "Specular IOR Level" in bsdf.inputs and alpha == 1.0 and metallic == 0.0:
        bsdf.inputs["Specular IOR Level"].default_value = 0.28
    for key in ("Transmission Weight", "Transmission"):
        if transmission and key in bsdf.inputs:
            bsdf.inputs[key].default_value = transmission
            break
    if alpha < 0.999 or transmission:
        if hasattr(mat, "blend_method"):
            mat.blend_method = "BLEND"
        if hasattr(mat, "surface_render_method"):
            mat.surface_render_method = "BLENDED"
        if hasattr(mat, "use_transparency_overlap"):
            mat.use_transparency_overlap = True
        mat.use_backface_culling = False
    return mat


def add_box(bm, mn, mx, material_index):
    sx = mx[0] - mn[0]
    sy = mx[1] - mn[1]
    sz = mx[2] - mn[2]
    if sx <= 0 or sy <= 0 or sz <= 0:
        raise ValueError(f"degenerate box {mn} {mx}")
    for vert in bm.verts:
        vert.tag = True
    existing = set(bm.faces)
    bmesh.ops.create_cube(bm, size=1.0)
    fresh = [vert for vert in bm.verts if not vert.tag]
    bmesh.ops.scale(bm, verts=fresh, vec=(sx, sy, sz))
    center = ((mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2, (mn[2] + mx[2]) / 2)
    bmesh.ops.translate(bm, verts=fresh, vec=center)
    for face in bm.faces:
        if face not in existing:
            face.material_index = material_index


def add_oriented_box(bm, center, axis_u, axis_v, size_u, size_v, size_w, material_index):
    """Axis-aligned cube remapped so local X/Y/Z follow axis_u, axis_v, and their cross."""
    u = Vector(axis_u).normalized()
    v = Vector(axis_v)
    v = (v - u * v.dot(u)).normalized()
    w = u.cross(v)
    for vert in bm.verts:
        vert.tag = True
    existing = set(bm.faces)
    bmesh.ops.create_cube(bm, size=1.0)
    fresh = [vert for vert in bm.verts if not vert.tag]
    origin = Vector(center)
    for vert in fresh:
        co = vert.co.copy()
        vert.co = origin + u * (size_u * co.x) + v * (size_v * co.y) + w * (size_w * co.z)
    for face in bm.faces:
        if face not in existing:
            face.material_index = material_index


def add_prism(bm, loop, z0, z1, material_index):
    """Vertical prism. loop is CCW when viewed from above."""
    bot = [bm.verts.new((p[0], p[1], z0)) for p in loop]
    top = [bm.verts.new((p[0], p[1], z1)) for p in loop]
    top_face = bm.faces.new(top)
    top_face.material_index = material_index
    bot_face = bm.faces.new(list(reversed(bot)))
    bot_face.material_index = material_index
    n = len(loop)
    for i in range(n):
        j = (i + 1) % n
        side = bm.faces.new((bot[i], bot[j], top[j], top[i]))
        side.material_index = material_index


def build_object(name, parts, location=(0.0, 0.0, 0.0), rotation_z=0.0):
    """parts: list of (min_xyz, max_xyz, material) in the object's local space."""
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    index_of = {}
    for mn, mx, mat in parts:
        if mat.name not in index_of:
            index_of[mat.name] = len(index_of)
            mesh.materials.append(mat)
        add_box(bm, mn, mx, index_of[mat.name])
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = location
    obj.rotation_euler = (0.0, 0.0, rotation_z)
    bpy.context.collection.objects.link(obj)
    return obj


def build_bmesh_object(name, builder, materials):
    mesh = bpy.data.meshes.new(name)
    for mat in materials:
        mesh.materials.append(mat)
    bm = bmesh.new()
    builder(bm)
    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def add_empty(name, location, yaw_deg):
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_type = "PLAIN_AXES"
    obj.empty_display_size = 0.35
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


def point_in_poly(x, y, poly):
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i][0], poly[i][1]
        xj, yj = poly[j][0], poly[j][1]
        if (yi > y) != (yj > y):
            xint = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < xint:
                inside = not inside
        j = i
    return inside


def rnd3(v):
    return [round(float(v[0]), 4), round(float(v[1]), 4), round(float(v[2]), 4)]


def rnd2(poly):
    return [[round(float(p[0]), 4), round(float(p[1]), 4)] for p in poly]


def french_leaf_parts(leaf_w, leaf_h, thick, frame_mat, glass_mat, metal_mat):
    stile = 0.07
    rail_bot = 0.12
    rail_top = 0.078
    muntin = 0.028
    rows = 5
    cols = 2
    parts = []
    x0, x1 = 0.0, thick
    parts.append(((x0, 0.0, 0.0), (x1, stile, leaf_h), frame_mat))
    parts.append(((x0, leaf_w - stile, 0.0), (x1, leaf_w, leaf_h), frame_mat))
    parts.append(((x0, stile, 0.0), (x1, leaf_w - stile, rail_bot), frame_mat))
    parts.append(((x0, stile, leaf_h - rail_top), (x1, leaf_w - stile, leaf_h), frame_mat))
    inner_h = leaf_h - rail_bot - rail_top
    inner_w = leaf_w - 2 * stile
    glass_h = (inner_h - (rows - 1) * muntin) / rows
    glass_w = (inner_w - (cols - 1) * muntin) / cols
    muntin_y = stile + glass_w
    parts.append(((x0, muntin_y, rail_bot), (x1, muntin_y + muntin, leaf_h - rail_top), frame_mat))
    z = rail_bot + glass_h
    for _ in range(rows - 1):
        parts.append(((x0, stile, z), (x1, leaf_w - stile, z + muntin), frame_mat))
        z += muntin + glass_h
    z = rail_bot
    gx0 = x0 + thick * 0.38
    gx1 = x1 - thick * 0.38
    for _r in range(rows):
        y = stile
        for _c in range(cols):
            parts.append(((gx0, y + 0.001, z + 0.001), (gx1, y + glass_w - 0.001, z + glass_h - 0.001), glass_mat))
            y += glass_w + muntin
        z += glass_h + muntin
    # Lever on the latch stile.
    parts.append(((thick, leaf_w - stile - 0.01, 0.96), (thick + 0.018, leaf_w - stile + 0.045, 1.04), metal_mat))
    parts.append(((thick + 0.004, leaf_w - stile + 0.01, 0.985), (thick + 0.014, leaf_w - stile + 0.12, 1.015), metal_mat))
    for hz in (0.22, 0.98, 1.72):
        parts.append(((-0.004, -0.006, hz), (thick * 0.55, 0.028, hz + 0.10), metal_mat))
    return parts


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = "METERS"

    floor_mat = make_material("Floor_Cherry", (0.55, 0.26, 0.11), roughness=0.5)
    wall_mat = make_material("Wall_Cream", (0.94, 0.92, 0.87), roughness=0.72)
    ceil_mat = make_material("Ceiling_White", (0.97, 0.97, 0.96), roughness=0.78)
    beam_mat = make_material("Beam_Wood", (0.20, 0.10, 0.045), roughness=0.55)
    base_mat = make_material("Baseboard_Wood", (0.45, 0.27, 0.14), roughness=0.48)
    trim_mat = make_material("Trim_White", (0.96, 0.96, 0.94), roughness=0.45)
    door_mat = make_material("Door_White", (0.95, 0.95, 0.93), roughness=0.42)
    frame_mat = make_material("Window_Frame", (0.96, 0.96, 0.95), roughness=0.38)
    glass_mat = make_material(
        "Glass",
        (0.78, 0.88, 0.90),
        roughness=0.06,
        alpha=0.28,
        transmission=0.85,
    )
    metal_mat = make_material("Brass", (0.74, 0.55, 0.24), roughness=0.32, metallic=0.85)
    tile_mat = make_material("Tile_Gray", (0.76, 0.74, 0.70), roughness=0.5)
    hearth_mat = make_material("Hearth_Tile", (0.84, 0.81, 0.76), roughness=0.46)
    grout_mat = make_material("Tile_Grout", (0.52, 0.50, 0.47), roughness=0.75)
    fire_mat = make_material("Firebox_Black", (0.012, 0.012, 0.014), roughness=0.32, metallic=0.25)
    fire_glass = make_material("Firebox_Glass", (0.03, 0.035, 0.04), roughness=0.12, metallic=0.55)
    rug_mat = make_material("Rug_Field", (0.40, 0.36, 0.32), roughness=0.85)
    rug_border = make_material("Rug_Border", (0.22, 0.17, 0.13), roughness=0.8)

    # Floor slab, top face at Z=0, covering the exterior footprint.
    build_object(
        "Floor",
        [
            (
                (-(HX + WALL_T), -(HY + WALL_T), -FLOOR_T),
                (HX + WALL_T, HY + WALL_T, 0.0),
                floor_mat,
            )
        ],
    )

    wall_z0 = -0.002
    wall_z1 = HEIGHT_Z + 0.002
    bite = 0.004

    # North wall owns neither corner post. Hole for the entry door and the picture window.
    build_object(
        "Wall_N",
        [
            ((-HX, HY, wall_z0), (ENTRY_X0, HY + WALL_T, wall_z1), wall_mat),
            ((ENTRY_X1, HY, wall_z0), (WIN_X0, HY + WALL_T, wall_z1), wall_mat),
            ((WIN_X1, HY, wall_z0), (HX, HY + WALL_T, wall_z1), wall_mat),
            ((WIN_X0, HY, wall_z0), (WIN_X1, HY + WALL_T, WIN_SILL), wall_mat),
            ((WIN_X0, HY, WIN_HEAD), (WIN_X1, HY + WALL_T, wall_z1), wall_mat),
            ((ENTRY_X0, HY, DOOR_H), (ENTRY_X1, HY + WALL_T, wall_z1), wall_mat),
        ],
    )
    build_object(
        "Wall_S",
        [((-HX, -(HY + WALL_T), wall_z0), (HX, -HY, wall_z1), wall_mat)],
    )
    # West wall owns both corner posts and has the French-door opening.
    build_object(
        "Wall_W",
        [
            ((-(HX + WALL_T), -(HY + WALL_T), wall_z0), (-HX, FRENCH_Y0, wall_z1), wall_mat),
            ((-(HX + WALL_T), FRENCH_Y1, wall_z0), (-HX, HY + WALL_T, wall_z1), wall_mat),
            ((-(HX + WALL_T), FRENCH_Y0, DOOR_H), (-HX, FRENCH_Y1, wall_z1), wall_mat),
        ],
    )
    build_object(
        "Wall_E",
        [((HX, -(HY + WALL_T), wall_z0), (HX + WALL_T, HY + WALL_T, wall_z1), wall_mat)],
    )
    build_object(
        "Ceiling",
        [((-HX, -HY, HEIGHT_Z), (HX, HY, HEIGHT_Z + CEIL_T), ceil_mat)],
    )

    beam_z0 = HEIGHT_Z - BEAM_H
    beam_z1 = HEIGHT_Z + 0.004
    beam_x0 = -HX - 0.01
    beam_x1 = HX + 0.01
    for index, y in enumerate(BEAM_YS, start=1):
        build_object(
            f"Beam_{index}",
            [((beam_x0, y - BEAM_W / 2, beam_z0), (beam_x1, y + BEAM_W / 2, beam_z1), beam_mat)],
        )

    # Wood baseboard on the interior faces. Broken for doors, and stopped at the fireplace.
    base_parts = [
        ((-HX + BASE_T, HY - BASE_T, -bite), (ENTRY_X0 - CASING, HY + bite, BASE_H), base_mat),
        ((ENTRY_X1 + CASING, HY - BASE_T, -bite), (P_N[0] - 0.01, HY + bite, BASE_H), base_mat),
        ((-HX + BASE_T, -HY - bite, -bite), (HX - BASE_T, -HY + BASE_T, BASE_H), base_mat),
        ((-HX - bite, -HY + BASE_T, -bite), (-HX + BASE_T, FRENCH_Y0 - CASING, BASE_H), base_mat),
        ((-HX - bite, FRENCH_Y1 + CASING, -bite), (-HX + BASE_T, HY - BASE_T, BASE_H), base_mat),
        ((HX - BASE_T, -HY + BASE_T, -bite), (HX + bite, P_E[1] - 0.01, BASE_H), base_mat),
    ]
    build_object("Baseboard", base_parts)

    # Entry door, closed, seen from inside the room. Six raised panels.
    slab_t = 0.038
    slab_x0 = ENTRY_X0 + 0.008
    slab_x1 = ENTRY_X1 - 0.008
    slab_y_int = HY - 0.006
    slab_y_ext = slab_y_int + slab_t
    slab_z0 = 0.01
    slab_z1 = DOOR_H - 0.01
    door_parts = [
        ((slab_x0, slab_y_int, slab_z0), (slab_x1, slab_y_ext, slab_z1), door_mat),
        ((ENTRY_X0 - CASING, HY - CASING_T, -bite), (ENTRY_X0, HY + bite, DOOR_H + CASING), trim_mat),
        ((ENTRY_X1, HY - CASING_T, -bite), (ENTRY_X1 + CASING, HY + bite, DOOR_H + CASING), trim_mat),
        ((ENTRY_X0, HY - CASING_T, DOOR_H), (ENTRY_X1, HY + bite, DOOR_H + CASING), trim_mat),
    ]
    margin = 0.105
    gap_m = 0.062
    col_w = (slab_x1 - slab_x0 - 2 * margin - gap_m) / 2
    cols = (slab_x0 + margin, slab_x0 + margin + col_w + gap_m)
    rows = ((0.14, 0.78), (0.88, 1.38), (1.48, 1.90))
    for x_left in cols:
        for z0p, z1p in rows:
            door_parts.append(
                (
                    (x_left, slab_y_int - 0.009, z0p),
                    (x_left + col_w, slab_y_int + 0.001, z1p),
                    door_mat,
                )
            )
    # Lever on the east stile, interior side.
    door_parts.append(
        ((slab_x1 - 0.10, slab_y_int - 0.02, 0.96), (slab_x1 - 0.055, slab_y_int - 0.004, 1.05), metal_mat)
    )
    door_parts.append(
        ((slab_x1 - 0.16, slab_y_int - 0.016, 0.99), (slab_x1 - 0.07, slab_y_int - 0.008, 1.02), metal_mat)
    )
    build_object("Door_Entry", door_parts)

    # Fixed French-door casing on the interior of the west opening. Leaves are separate objects.
    build_object(
        "Door_French_Frame",
        [
            ((-HX - bite, FRENCH_Y0 - CASING, -bite), (-HX + CASING_T, FRENCH_Y0, DOOR_H + CASING), trim_mat),
            ((-HX - bite, FRENCH_Y1, -bite), (-HX + CASING_T, FRENCH_Y1 + CASING, DOOR_H + CASING), trim_mat),
            ((-HX - bite, FRENCH_Y0, DOOR_H), (-HX + CASING_T, FRENCH_Y1, DOOR_H + CASING), trim_mat),
        ],
    )
    leaf_w = FRENCH_W / 2 - 0.016
    leaf_h = DOOR_H - 0.028
    leaf_t = 0.038
    leaf_parts = french_leaf_parts(leaf_w, leaf_h, leaf_t, door_mat, glass_mat, metal_mat)
    build_object(
        "Door_French_S",
        leaf_parts,
        location=(-HX + 0.014, FRENCH_Y0 + 0.012, 0.012),
        rotation_z=math.radians(-FRENCH_OPEN),
    )
    build_object(
        "Door_French_N",
        leaf_parts,
        location=(-HX + 0.014, FRENCH_Y1 - 0.012, 0.012),
        rotation_z=math.radians(-(180.0 - FRENCH_OPEN)),
    )

    # Three-section picture window in the north wall.
    win_parts = [
        ((WIN_X0, HY, WIN_SILL), (WIN_X1, HY + WALL_T, WIN_SILL + WIN_FRAME), frame_mat),
        ((WIN_X0, HY, WIN_HEAD - WIN_FRAME), (WIN_X1, HY + WALL_T, WIN_HEAD), frame_mat),
        ((WIN_X0, HY, WIN_SILL + WIN_FRAME), (WIN_X0 + WIN_FRAME, HY + WALL_T, WIN_HEAD - WIN_FRAME), frame_mat),
        ((WIN_X1 - WIN_FRAME, HY, WIN_SILL + WIN_FRAME), (WIN_X1, HY + WALL_T, WIN_HEAD - WIN_FRAME), frame_mat),
    ]
    inner_x0 = WIN_X0 + WIN_FRAME
    inner_x1 = WIN_X1 - WIN_FRAME
    pane_w = (inner_x1 - inner_x0 - 2 * WIN_MULLION) / 3
    glass_t = 0.008
    glass_y = HY + WALL_T / 2
    x = inner_x0
    for i in range(3):
        win_parts.append(
            (
                (x, glass_y - glass_t / 2, WIN_SILL + WIN_FRAME),
                (x + pane_w, glass_y + glass_t / 2, WIN_HEAD - WIN_FRAME),
                glass_mat,
            )
        )
        x += pane_w
        if i < 2:
            win_parts.append(((x, HY, WIN_SILL + WIN_FRAME), (x + WIN_MULLION, HY + WALL_T, WIN_HEAD - WIN_FRAME), frame_mat))
            x += WIN_MULLION
    # Interior stool and casing.
    win_parts.append(
        (
            (WIN_X0 - 0.012, HY - 0.048, WIN_SILL - 0.02),
            (WIN_X1 + 0.012, HY + bite, WIN_SILL + 0.014),
            frame_mat,
        )
    )
    win_parts.append(((WIN_X0 - CASING, HY - CASING_T, WIN_SILL - 0.02), (WIN_X0, HY + bite, WIN_HEAD + CASING), trim_mat))
    win_parts.append(((WIN_X1, HY - CASING_T, WIN_SILL - 0.02), (WIN_X1 + CASING, HY + bite, WIN_HEAD + CASING), trim_mat))
    win_parts.append(((WIN_X0, HY - CASING_T, WIN_HEAD), (WIN_X1, HY + bite, WIN_HEAD + CASING), trim_mat))
    build_object("Window", win_parts)

    # Corner fireplace. The surround is the triangle against the two walls.
    # The hearth quad is tucked a couple of centimeters into that mass so the
    # shared edge does not z-fight, and the whole raised platform is excluded
    # from the free floor.
    def build_fireplace(bm):
        add_prism(bm, [P_N, P_E, CORNER], 0.0, FP_TOP, 0)
        face_len = FP_A * math.sqrt(2.0)
        u_axis = Vector((INV, -INV, 0.0))
        n_axis = Vector((-INV, -INV, 0.0))
        origin = Vector((P_N[0], P_N[1], 0.0))
        tile = 0.28
        grout_h = FP_TOP - HEARTH_H
        s = tile
        while s < face_len - 0.04:
            center = origin + u_axis * s + Vector((0.0, 0.0, (FP_TOP + HEARTH_H) / 2)) + n_axis * 0.004
            add_oriented_box(bm, center, u_axis, n_axis, 0.008, 0.006, grout_h, 1)
            s += tile
        z = HEARTH_H + tile
        while z < FP_TOP - 0.04:
            center = origin + u_axis * (face_len / 2) + Vector((0.0, 0.0, z)) + n_axis * 0.004
            add_oriented_box(bm, center, u_axis, n_axis, face_len, 0.006, 0.008, 1)
            z += tile

    build_bmesh_object("Fireplace", build_fireplace, [tile_mat, grout_mat])

    tuck = 0.02
    p_n_h = (P_N[0] + tuck * INV, P_N[1] + tuck * INV)
    p_e_h = (P_E[0] + tuck * INV, P_E[1] + tuck * INV)

    def build_hearth(bm):
        add_prism(bm, [p_n_h, Q1, Q2, p_e_h], 0.0, HEARTH_H, 0)

    build_bmesh_object("Fireplace_Hearth", build_hearth, [hearth_mat])

    def build_firebox(bm):
        face_len = FP_A * math.sqrt(2.0)
        u_axis = Vector((INV, -INV, 0.0))
        n_axis = Vector((-INV, -INV, 0.0))
        mid = Vector((P_N[0], P_N[1], 0.0)) + u_axis * (face_len / 2)
        outer_w, outer_h = 0.98, 0.64
        inner_w, inner_h = 0.78, 0.44
        z_mid = 0.70
        frame_n = 0.024
        glass_n = 0.012
        center = mid + n_axis * frame_n + Vector((0.0, 0.0, z_mid))
        side = (outer_w - inner_w) / 2
        band = (outer_h - inner_h) / 2
        add_oriented_box(
            bm,
            center + u_axis * (-(inner_w / 2 + side / 2)),
            u_axis,
            n_axis,
            side,
            0.028,
            outer_h,
            0,
        )
        add_oriented_box(
            bm,
            center + u_axis * (inner_w / 2 + side / 2),
            u_axis,
            n_axis,
            side,
            0.028,
            outer_h,
            0,
        )
        add_oriented_box(
            bm,
            center + Vector((0.0, 0.0, inner_h / 2 + band / 2)),
            u_axis,
            n_axis,
            inner_w,
            0.028,
            band,
            0,
        )
        add_oriented_box(
            bm,
            center + Vector((0.0, 0.0, -(inner_h / 2 + band / 2))),
            u_axis,
            n_axis,
            inner_w,
            0.028,
            band,
            0,
        )
        glass_center = mid + n_axis * glass_n + Vector((0.0, 0.0, z_mid))
        add_oriented_box(bm, glass_center, u_axis, n_axis, inner_w - 0.02, 0.012, inner_h - 0.02, 1)
        bar = mid + n_axis * 0.034 + Vector((0.0, 0.0, z_mid + 0.02))
        add_oriented_box(bm, bar, u_axis, n_axis, 0.62, 0.012, 0.018, 2)

    build_bmesh_object("Fireplace_Firebox", build_firebox, [fire_mat, fire_glass, metal_mat])

    # Small rug just inside the entry door.
    rug_cx = (ENTRY_X0 + ENTRY_X1) / 2
    rug_cy = HY - 0.34
    rug_w, rug_d = 0.78, 0.46
    build_object(
        "Entry_Rug",
        [
            (
                (rug_cx - rug_w / 2, rug_cy - rug_d / 2, 0.001),
                (rug_cx + rug_w / 2, rug_cy + rug_d / 2, 0.008),
                rug_border,
            ),
            (
                (rug_cx - rug_w / 2 + 0.045, rug_cy - rug_d / 2 + 0.045, 0.008),
                (rug_cx + rug_w / 2 - 0.045, rug_cy + rug_d / 2 - 0.045, 0.014),
                rug_mat,
            ),
        ],
    )

    anchors = [
        ("TV_wall", (TV_X, TV_Y, 0.0), TV_YAW),
        ("Sofa_spot", (SOFA_X, SOFA_Y, 0.0), SOFA_YAW),
        ("Rug_center", (RUG_X, RUG_Y, 0.0), 0.0),
        ("Coffee_spot", (COFFEE_X, COFFEE_Y, 0.0), 0.0),
        ("Plant_corner", (PLANT_X, PLANT_Y, 0.0), PLANT_YAW),
        ("Lamp_corner", (LAMP_X, LAMP_Y, 0.0), LAMP_YAW),
        ("Side_table", (SIDE_X, SIDE_Y, 0.0), 0.0),
    ]
    for name, loc, yaw in anchors:
        add_empty(name, loc, yaw)
        if not point_in_poly(loc[0], loc[1], FREE_POLY):
            raise SystemExit(f"anchor {name} at {loc} is outside the free floor")
        if point_in_poly(loc[0], loc[1], HEARTH_POLY):
            raise SystemExit(f"anchor {name} at {loc} sits on the hearth")
    if not point_in_poly(0.0, 0.0, FREE_POLY):
        raise SystemExit("room center is outside the free floor polygon")
    if point_in_poly(HX - 0.08, HY - 0.08, FREE_POLY):
        raise SystemExit("fireplace corner was not excluded from the free floor")
    if not point_in_poly(HX - 0.08, HY - 0.08, HEARTH_POLY):
        raise SystemExit("fireplace corner is not inside the hearth polygon")

    bpy.context.view_layer.update()
    meshes = [obj for obj in scene.objects if obj.type == "MESH"]
    lo, hi = world_bbox(meshes)
    size = hi - lo
    tris = triangle_count(meshes)
    print(f"BBOX min {tuple(round(v, 4) for v in lo)}")
    print(f"BBOX max {tuple(round(v, 4) for v in hi)}")
    print(f"BBOX size {tuple(round(v, 4) for v in size)}")
    print(f"TRIANGLES {tris}")

    expected_lo = Vector((-(HX + WALL_T), -(HY + WALL_T), -FLOOR_T))
    expected_hi = Vector((HX + WALL_T, HY + WALL_T, HEIGHT_Z + CEIL_T))
    for i in range(3):
        if lo[i] < expected_lo[i] - 0.004 or hi[i] > expected_hi[i] + 0.004:
            raise SystemExit(
                f"bbox exceeds shell axis {i}: got {(lo[i], hi[i])} shell {(expected_lo[i], expected_hi[i])}"
            )
    if tris > 50000:
        raise SystemExit(f"triangle count {tris} is above 50000")

    def anchor_meta(name, loc, yaw, note):
        return {
            "position_m": rnd3(loc),
            "rotation_z_deg": yaw,
            "note": note,
        }

    meta = {
        "id": "beamed_fireplace_living",
        "name": "Beamed Living Room with Fireplace",
        "description": (
            "Suburban family living room with a medium cherry floor, cream walls, "
            "wood baseboards, and a white ceiling crossed by four exposed dark wood beams. "
            "A white entry door and a three-section picture window share the north wall, "
            "glass French doors open on the west wall, and a light-gray tile fireplace "
            "angles across the northeast corner on a raised hearth."
        ),
        "units": "meters",
        "up_axis": "Z",
        "origin": "interior floor center (0, 0, 0); floor top is Z=0",
        "anchor_convention": (
            "Position is the floor center of a furniture footprint. "
            "Yaw is degrees about Z applied to a model whose front faces local -Y."
        ),
        "interior_m": {"width_x": round(WIDTH_X, 4), "depth_y": round(DEPTH_Y, 4), "height_z": round(HEIGHT_Z, 4)},
        "interior_ft": {"width_x": 18.0, "depth_y": 21.0, "height_z": 8.5},
        "ceiling_height_m": round(HEIGHT_Z, 4),
        "ceiling_height_ft": 8.5,
        "wall_thickness_m": WALL_T,
        "walls": {
            "Wall_N": "+Y far wall, entry door and picture window",
            "Wall_S": "-Y near wall",
            "Wall_E": "+X wall, solid, beside the fireplace",
            "Wall_W": "-X wall, French doors",
        },
        "openings": [
            {
                "name": "entry_door",
                "kind": "door",
                "object": "Door_Entry",
                "wall": "Wall_N",
                "width_m": round(DOOR_W, 4),
                "height_m": round(DOOR_H, 4),
                "width_in": 36,
                "height_in": 80,
                "position_m": rnd3(((ENTRY_X0 + ENTRY_X1) / 2, HY + WALL_T / 2, DOOR_H / 2)),
                "size_m": [round(DOOR_W, 4), round(WALL_T, 4), round(DOOR_H, 4)],
            },
            {
                "name": "french_doors",
                "kind": "door",
                "object": "Door_French_S",
                "wall": "Wall_W",
                "width_m": round(FRENCH_W, 4),
                "height_m": round(DOOR_H, 4),
                "width_in": 64,
                "height_in": 80,
                "leaves": 2,
                "open_degrees": FRENCH_OPEN,
                "position_m": rnd3((-HX - WALL_T / 2, (FRENCH_Y0 + FRENCH_Y1) / 2, DOOR_H / 2)),
                "size_m": [round(WALL_T, 4), round(FRENCH_W, 4), round(DOOR_H, 4)],
            },
            {
                "name": "picture_window",
                "kind": "window",
                "object": "Window",
                "wall": "Wall_N",
                "sections": 3,
                "width_m": round(WIN_W, 4),
                "height_m": round(WIN_HEAD - WIN_SILL, 4),
                "sill_z_m": WIN_SILL,
                "head_z_m": WIN_HEAD,
                "position_m": rnd3(((WIN_X0 + WIN_X1) / 2, HY + WALL_T / 2, (WIN_SILL + WIN_HEAD) / 2)),
                "size_m": [round(WIN_W, 4), round(WALL_T, 4), round(WIN_HEAD - WIN_SILL, 4)],
            },
        ],
        "fireplace": {
            "object": "Fireplace",
            "hearth_object": "Fireplace_Hearth",
            "corner": "northeast",
            "face": "45 degrees across the corner",
            "surround_top_z_m": FP_TOP,
            "hearth_height_m": HEARTH_H,
            "hearth_polygon_m": rnd2(HEARTH_POLY),
        },
        "beams": [
            {"object": f"Beam_{i}", "axis": "X", "center_y_m": round(y, 4), "width_m": BEAM_W, "drop_m": BEAM_H}
            for i, y in enumerate(BEAM_YS, start=1)
        ],
        "free_floor": {
            "units": "meters",
            "note": (
                "Furniture may sit inside this polygon. The raised hearth, including the floor "
                "under the corner fireplace, is not free floor."
            ),
            "polygon_m": rnd2(FREE_POLY),
            "excluded": [
                {
                    "name": "hearth",
                    "reason": "Raised tile hearth and the floor under the corner fireplace. Not free floor.",
                    "polygon_m": rnd2(HEARTH_POLY),
                    "height_m": HEARTH_H,
                }
            ],
        },
        "bbox_m": {"min": rnd3(lo), "max": rnd3(hi), "size": rnd3(size)},
        "empties": {
            "TV_wall": anchor_meta(
                "TV_wall",
                (TV_X, TV_Y, 0.0),
                TV_YAW,
                "East wall, south of the hearth. Yaw -90 so the screen (local -Y) faces the sofa. The fireplace is to the TV's north.",
            ),
            "Sofa_spot": anchor_meta(
                "Sofa_spot",
                (SOFA_X, SOFA_Y, 0.0),
                SOFA_YAW,
                "Faces the east-wall TV (yaw 90, front toward +X). The corner fireplace is ahead and to the right.",
            ),
            "Rug_center": anchor_meta(
                "Rug_center",
                (RUG_X, RUG_Y, 0.0),
                0.0,
                "Seating rug. Yaw 0 keeps a 10 ft local-Y carpet running with the sofa.",
            ),
            "Coffee_spot": anchor_meta(
                "Coffee_spot",
                (COFFEE_X, COFFEE_Y, 0.0),
                0.0,
                "Coffee table between the sofa and the TV, clear of the hearth.",
            ),
            "Plant_corner": anchor_meta(
                "Plant_corner",
                (PLANT_X, PLANT_Y, 0.0),
                PLANT_YAW,
                "Northwest corner, beside the entry door. Yaw 45 faces the plant into the room.",
            ),
            "Lamp_corner": anchor_meta(
                "Lamp_corner",
                (LAMP_X, LAMP_Y, 0.0),
                LAMP_YAW,
                "Southwest corner. Yaw 135 faces a floor lamp toward the seating and the fireplace.",
            ),
            "Side_table": anchor_meta(
                "Side_table",
                (SIDE_X, SIDE_Y, 0.0),
                0.0,
                "North end of the sofa, on the way toward the fireplace.",
            ),
        },
        "triangle_count": tris,
        "objects": [
            "Floor",
            "Wall_N",
            "Wall_S",
            "Wall_W",
            "Wall_E",
            "Ceiling",
            "Beam_1",
            "Beam_2",
            "Beam_3",
            "Beam_4",
            "Baseboard",
            "Door_Entry",
            "Door_French_Frame",
            "Door_French_S",
            "Door_French_N",
            "Window",
            "Fireplace",
            "Fireplace_Hearth",
            "Fireplace_Firebox",
            "Entry_Rug",
            "TV_wall",
            "Sofa_spot",
            "Rug_center",
            "Coffee_spot",
            "Plant_corner",
            "Lamp_corner",
            "Side_table",
        ],
    }
    return meta


def add_camera_lights_and_set():
    scene = bpy.context.scene
    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens = 16
    cam_data.sensor_width = 36
    cam_data.clip_start = 0.05
    cam_data.clip_end = 80
    cam = bpy.data.objects.new("Camera", cam_data)
    bpy.context.collection.objects.link(cam)
    # Just outside the south wall (hidden in the preview) so the shot takes in
    # the French doors, all four beams, the far wall, and the corner fireplace.
    cam.location = (-0.20, -3.90, 1.22)
    look_at(cam, Vector((-0.05, 0.55, 1.32)))
    scene.camera = cam

    sun_data = bpy.data.lights.new("Sun", "SUN")
    sun_data.energy = 2.2
    sun_data.angle = math.radians(18)
    sun_data.color = (1.0, 0.96, 0.90)
    sun = bpy.data.objects.new("Sun", sun_data)
    bpy.context.collection.objects.link(sun)
    sun.rotation_euler = Vector((-0.35, -0.55, -1.1)).to_track_quat("-Z", "Y").to_euler()

    fill_data = bpy.data.lights.new("Fill", "AREA")
    fill_data.energy = 28
    fill_data.size = 8.0
    fill_data.color = (1.0, 0.97, 0.93)
    fill = bpy.data.objects.new("Fill", fill_data)
    bpy.context.collection.objects.link(fill)
    fill.location = (0.0, -0.4, 2.40)
    fill.rotation_euler = (0.0, 0.0, 0.0)

    win_data = bpy.data.lights.new("WindowLight", "AREA")
    win_data.energy = 35
    win_data.size = 1.8
    win_data.color = (0.92, 0.96, 1.0)
    win = bpy.data.objects.new("WindowLight", win_data)
    bpy.context.collection.objects.link(win)
    win.location = ((WIN_X0 + WIN_X1) / 2, HY - 0.35, (WIN_SILL + WIN_HEAD) / 2)
    look_at(win, Vector((win.location.x, win.location.y - 2.0, win.location.z - 0.4)))

    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.70, 0.80, 0.88, 1.0)
    bg.inputs["Strength"].default_value = 0.55
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.exposure = -0.05

    # Render-only set dressing so the glass reads as a view outside. Not exported.
    green = make_material("Foliage", (0.22, 0.40, 0.18), roughness=0.8)
    green_dark = make_material("Foliage_Dark", (0.12, 0.28, 0.12), roughness=0.8)
    yard = make_material("Yard", (0.34, 0.42, 0.22), roughness=0.9)
    adj_wall = make_material("Adjacent_Wall", (0.93, 0.91, 0.86), roughness=0.75)
    adj_floor = make_material("Adjacent_Floor", (0.55, 0.32, 0.16), roughness=0.45)
    build_object(
        "_Render_Yard",
        [((-2.0, HY + WALL_T + 0.05, -0.02), (4.2, HY + 3.2, 0.0), yard)],
    )
    shrubs = [
        ((-0.4, HY + 0.55, 0.0), (0.35, HY + 1.05, 1.7), green),
        ((0.45, HY + 0.7, 0.0), (1.35, HY + 1.35, 2.5), green_dark),
        ((1.4, HY + 0.5, 0.0), (2.15, HY + 1.0, 1.9), green),
        ((-1.3, HY + 0.8, 0.0), (-0.55, HY + 1.4, 2.2), green_dark),
    ]
    build_object("_Render_Trees", shrubs)
    build_object(
        "_Render_Adjacent",
        [
            ((-(HX + 2.4), FRENCH_Y0 - 0.4, -0.02), (-(HX + WALL_T) - 0.02, FRENCH_Y1 + 0.6, 0.0), adj_floor),
            ((-(HX + 2.4), FRENCH_Y0 - 0.4, 0.0), (-(HX + 2.15), FRENCH_Y1 + 0.6, HEIGHT_Z), adj_wall),
        ],
    )


def render_preview(path):
    scene = bpy.context.scene
    scene.render.resolution_x = 1024
    scene.render.resolution_y = 640
    scene.render.resolution_percentage = 100
    scene.render.filepath = path
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    hidden = []
    for name in ("Wall_S",):
        obj = bpy.data.objects.get(name)
        if obj is not None:
            hidden.append(obj)
            obj.hide_render = True
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
        if hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
            scene.eevee.taa_render_samples = 48
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
        keep = obj.type in {"MESH", "EMPTY"} and not obj.name.startswith("_")
        obj.select_set(keep)
    floor = bpy.data.objects.get("Floor")
    if floor is not None:
        bpy.context.view_layer.objects.active = floor
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
    add_camera_lights_and_set()
    export_assets(out, meta)


if __name__ == "__main__":
    main()
