"""Bright loft with tall windows.

Interior floor center is the world origin. Z is up. Floor top is Z=0.
Furniture whose origin is the bottom center of its footprint sits on the floor.
A furniture model's front faces local -Y, so an anchor yaw is the Z rotation
to apply when placing that model.

West long wall: two tall black grid windows in deep reveals.
East long wall: a jog that steps into the room and leaves a northeast alcove.
South short wall: a 36 by 80 in doorway (behind the preview camera).

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

# Overall interior bounding box: 19 ft x 25 ft x 10.5 ft.
WIDTH_X = 19.0 * FT
DEPTH_Y = 25.0 * FT
HEIGHT_Z = 10.5 * FT
WALL_T = 0.12
# West wall is thicker so the black frames sit in a deep white reveal.
WALL_T_W = 0.34
FLOOR_T = 0.04
CEIL_T = 0.04

# Northeast alcove: 4 ft clear east-west, 10 ft along Y.
ALC_CLEAR = 4.0 * FT
ALC_LEN = 10.0 * FT

DOOR_W = 36 * 0.0254
DOOR_H = 80 * 0.0254

WIN_W = 3.25 * FT
WIN_H = 8.2 * FT
WIN_SILL = 1.5 * FT
WIN_SOUTH_MARGIN = 3.25 * FT
WIN_GAP = 3.5 * FT

REVEAL = 0.15
FRAME_D = 0.05
FRAME = 0.055
MUNTIN = 0.028
LIP = 0.014
BURY = 0.008

BASE_H = 0.07
BASE_T = 0.015
BITE = 0.004

PITCH = 0.132
PLANK_GAP = 0.0035

HX = WIDTH_X / 2.0
HY = DEPTH_Y / 2.0
# Interior face of the wall that juts into the room.
JOG_X = HX - WALL_T - ALC_CLEAR
# Interior face of the alcove's south return (alcove is north of this).
JOG_Y = HY - ALC_LEN
SEAT_X = (-HX + JOG_X) / 2.0

WIN1_Y0 = -HY + WIN_SOUTH_MARGIN
WIN1_Y1 = WIN1_Y0 + WIN_W
WIN2_Y0 = WIN1_Y1 + WIN_GAP
WIN2_Y1 = WIN2_Y0 + WIN_W
WIN_Z0 = WIN_SILL
WIN_Z1 = WIN_SILL + WIN_H

# Door on the south wall, east of the seating axis, clear of the jog.
DOOR_CX = 0.25


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


def make_material(name, color, roughness=0.55, metallic=0.0, alpha=1.0, transmission=0.0, blend=False):
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
    if blend:
        if hasattr(mat, "blend_method"):
            mat.blend_method = "BLEND"
        if hasattr(mat, "surface_render_method"):
            mat.surface_render_method = "BLENDED"
        try:
            mat.use_backface_culling = False
        except Exception:
            pass
        if hasattr(mat, "show_transparent_back"):
            mat.show_transparent_back = True
    return mat


def add_box(bm, mn, mx, material_index):
    sx = mx[0] - mn[0]
    sy = mx[1] - mn[1]
    sz = mx[2] - mn[2]
    if sx <= 1e-5 or sy <= 1e-5 or sz <= 1e-5:
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


def build_object(name, parts):
    """parts: list of (min_xyz, max_xyz, material)."""
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    index_of = {}
    for mn, mx, mat in parts:
        if mx[0] - mn[0] <= 1e-5 or mx[1] - mn[1] <= 1e-5 or mx[2] - mn[2] <= 1e-5:
            continue
        if mat.name not in index_of:
            index_of[mat.name] = len(index_of)
            mesh.materials.append(mat)
        add_box(bm, mn, mx, index_of[mat.name])
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    for poly in mesh.polygons:
        poly.use_smooth = False
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def add_empty(name, location, yaw_deg):
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_type = "PLAIN_AXES"
    obj.empty_display_size = 0.35
    obj.location = location
    # Yaw lives in metadata. The empty stays unrotated, matching living_room_generic,
    # so a viewer does not apply the yaw twice.
    obj["yaw_deg"] = yaw_deg
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


def append_planks(parts, woods, x0, x1, y0, y1, z0, z1, x_ref):
    i = math.floor((x0 - x_ref) / PITCH + 1e-6)
    guard = 0
    while guard < 400:
        guard += 1
        x = x_ref + i * PITCH
        if x >= x1 - 0.002:
            break
        xa = max(x, x0)
        xb = min(x + PITCH - PLANK_GAP, x1)
        if xb - xa > 0.02:
            parts.append(((xa, y0, z0), (xb, y1, z1), woods[i % len(woods)]))
        i += 1


def build_west_wall(wall_mat, x_ext, x_int, fx0, fx1, z0, z1):
    """Thick west wall with two openings. Frame-zone faces are buried in the frame."""
    parts = []
    y_min = -(HY + WALL_T)
    y_max = HY + WALL_T
    windows = ((WIN1_Y0, WIN1_Y1), (WIN2_Y0, WIN2_Y1))
    inset = LIP - BURY

    def solid_band(ya, yb, inset0, inset1):
        slices = (
            (x_ext, fx0 + BURY, 0.0),
            (fx0, fx1, 1.0),
            (fx1 - BURY, x_int, 0.0),
        )
        for xa, xb, use in slices:
            y0 = ya + (inset0 if use else 0.0)
            y1 = yb - (inset1 if use else 0.0)
            parts.append(((xa, y0, z0), (xb, y1, z1), wall_mat))

    solid_band(y_min, windows[0][0], 0.0, inset)
    solid_band(windows[0][1], windows[1][0], inset, inset)
    solid_band(windows[1][1], y_max, inset, 0.0)

    for y0, y1 in windows:
        slices = (
            (x_ext, fx0 + BURY, 0.0),
            (fx0, fx1, inset),
            (fx1 - BURY, x_int, 0.0),
        )
        for xa, xb, pull in slices:
            parts.append(((xa, y0 - BURY, z0), (xb, y1 + BURY, WIN_Z0 - pull), wall_mat))
            parts.append(((xa, y0 - BURY, WIN_Z1 + pull), (xb, y1 + BURY, z1), wall_mat))
    return parts


def window_parts(y0, y1, fx0, fx1, x_int, frame_mat, wall_mat):
    zs, zh = WIN_Z0, WIN_Z1
    parts = [
        ((fx0, y0 - LIP, zs - LIP), (fx1, y1 + LIP, zs + FRAME), frame_mat),
        ((fx0, y0 - LIP, zh - FRAME), (fx1, y1 + LIP, zh + LIP), frame_mat),
        ((fx0, y0 - LIP, zs - LIP), (fx1, y0 + FRAME, zh + LIP), frame_mat),
        ((fx0, y1 - FRAME, zs - LIP), (fx1, y1 + LIP, zh + LIP), frame_mat),
    ]
    iy0 = y0 + FRAME
    iy1 = y1 - FRAME
    iz0 = zs + FRAME
    iz1 = zh - FRAME
    cols, rows = 3, 4
    pane_w = (iy1 - iy0 - (cols - 1) * MUNTIN) / cols
    pane_h = (iz1 - iz0 - (rows - 1) * MUNTIN) / rows
    if pane_w <= 0 or pane_h <= 0:
        raise SystemExit(f"window pane degenerate {pane_w} {pane_h}")
    for c in range(1, cols):
        cy = iy0 + c * pane_w + (c - 1) * MUNTIN
        parts.append(((fx0, cy - 0.001, iz0 - 0.002), (fx1, cy + MUNTIN + 0.001, iz1 + 0.002), frame_mat))
    for r in range(1, rows):
        cz = iz0 + r * pane_h + (r - 1) * MUNTIN
        parts.append(((fx0, iy0 - 0.002, cz - 0.001), (fx1, iy1 + 0.002, cz + MUNTIN + 0.001), frame_mat))
    # White interior stool, proud of the reveal.
    parts.append(
        ((fx1 - 0.012, y0 - 0.012, zs - 0.008), (x_int + 0.028, y1 + 0.012, zs + 0.012), wall_mat)
    )
    return parts


def glass_parts(y0, y1, fx0):
    return [
        (
            (fx0 - 0.008, y0 + FRAME, WIN_Z0 + FRAME),
            (fx0 + 0.002, y1 - FRAME, WIN_Z1 - FRAME),
            None,
        )
    ]


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = "METERS"

    woods = [
        make_material("Floor_Wood_A", (0.73, 0.50, 0.25), roughness=0.38),
        make_material("Floor_Wood_B", (0.64, 0.42, 0.20), roughness=0.44),
        make_material("Floor_Wood_C", (0.69, 0.46, 0.22), roughness=0.36),
        make_material("Floor_Wood_D", (0.57, 0.36, 0.17), roughness=0.48),
        make_material("Floor_Wood_E", (0.78, 0.55, 0.28), roughness=0.34),
    ]
    gap_mat = make_material("Floor_Gap", (0.28, 0.18, 0.10), roughness=0.7)
    wall_mat = make_material("Wall_Paint", (0.94, 0.935, 0.925), roughness=0.86)
    ceil_mat = make_material("Ceiling_Paint", (0.99, 0.99, 0.985), roughness=0.82)
    casing_mat = make_material("Door_Casing", (0.97, 0.97, 0.965), roughness=0.55)
    door_mat = make_material("Door_Paint", (0.91, 0.90, 0.87), roughness=0.5)
    frame_mat = make_material("Window_Frame", (0.012, 0.012, 0.013), roughness=0.32)
    base_mat = make_material("Baseboard_Black", (0.015, 0.015, 0.016), roughness=0.48)
    glass_mat = make_material(
        "Window_Glass",
        (0.74, 0.86, 0.93),
        roughness=0.05,
        alpha=0.35,
        transmission=0.9,
        blend=True,
    )
    metal_mat = make_material("Door_Metal", (0.08, 0.08, 0.09), roughness=0.28, metallic=0.85)

    z0 = -0.002
    z1 = HEIGHT_Z + 0.002
    x_int = -HX
    x_ext = -(HX + WALL_T_W)
    fx1 = x_int - REVEAL
    fx0 = fx1 - FRAME_D
    if fx0 <= x_ext + 0.02:
        raise SystemExit(f"window frame does not fit in the west wall: {fx0} {x_ext}")

    # Floor: dark seam base under a honey-oak strip floor. Tops of the planks are Z=0.
    floor_parts = [
        (
            (-(HX + WALL_T_W), -(HY + WALL_T), -FLOOR_T),
            (JOG_X + WALL_T, HY + WALL_T, -0.004),
            gap_mat,
        ),
        (
            (JOG_X + WALL_T, JOG_Y - WALL_T, -FLOOR_T),
            (HX + WALL_T, HY + WALL_T, -0.004),
            gap_mat,
        ),
    ]
    append_planks(floor_parts, woods, -HX + 0.001, JOG_X - 0.001, -HY + 0.001, HY - 0.001, -0.004, 0.0, -HX)
    # The jog wall stops at the alcove, so the opening in front of it is floor too.
    append_planks(
        floor_parts,
        woods,
        JOG_X + 0.001,
        JOG_X + WALL_T - 0.001,
        JOG_Y + 0.001,
        HY - 0.001,
        -0.004,
        0.0,
        -HX,
    )
    append_planks(
        floor_parts,
        woods,
        JOG_X + WALL_T + 0.001,
        HX - 0.001,
        JOG_Y + 0.001,
        HY - 0.001,
        -0.004,
        0.0,
        -HX,
    )
    build_object("Floor", floor_parts)

    build_object("Wall_W", build_west_wall(wall_mat, x_ext, x_int, fx0, fx1, z0, z1))

    build_object(
        "Wall_N",
        [((-HX - 0.006, HY, z0), (HX + 0.006, HY + WALL_T, z1), wall_mat)],
    )
    door_x0 = DOOR_CX - DOOR_W / 2.0
    door_x1 = DOOR_CX + DOOR_W / 2.0
    if door_x0 <= -HX + 0.2 or door_x1 >= JOG_X - 0.35:
        raise SystemExit(f"door does not fit the south wall: {door_x0} {door_x1}")
    south_y0 = -(HY + WALL_T)
    south_y1 = -HY
    build_object(
        "Wall_S",
        [
            ((-HX - 0.006, south_y0, z0), (door_x0, south_y1, z1), wall_mat),
            ((door_x1, south_y0, z0), (JOG_X + 0.006, south_y1, z1), wall_mat),
            ((door_x0, south_y0, DOOR_H), (door_x1, south_y1, z1), wall_mat),
        ],
    )
    build_object(
        "Wall_Jog",
        [((JOG_X, south_y0, z0), (JOG_X + WALL_T, JOG_Y, z1), wall_mat)],
    )
    build_object(
        "Wall_Return",
        [((JOG_X + WALL_T - 0.006, JOG_Y - WALL_T, z0), (HX + WALL_T, JOG_Y, z1), wall_mat)],
    )
    build_object(
        "Wall_E",
        [((HX, JOG_Y - 0.006, z0), (HX + WALL_T, HY + WALL_T, z1), wall_mat)],
    )

    build_object(
        "Ceiling",
        [
            ((-HX - 0.003, -HY - 0.003, HEIGHT_Z), (JOG_X + 0.006, HY + 0.003, HEIGHT_Z + CEIL_T), ceil_mat),
            (
                # Starts at the jog's interior face so the alcove mouth is not an open slot.
                (JOG_X - 0.002, JOG_Y - 0.006, HEIGHT_Z),
                (HX + 0.003, HY + 0.003, HEIGHT_Z + CEIL_T),
                ceil_mat,
            ),
        ],
    )

    casing = 0.07
    base_parts = [
        ((-HX - BITE, -HY, -0.001), (-HX + BASE_T, HY, BASE_H), base_mat),
        ((-HX + BASE_T, HY - BASE_T, -0.001), (HX, HY + BITE, BASE_H), base_mat),
        ((-HX + BASE_T, -HY - BITE, -0.001), (door_x0 - casing - 0.001, -HY + BASE_T, BASE_H), base_mat),
        ((door_x1 + casing + 0.001, -HY - BITE, -0.001), (JOG_X - BASE_T, -HY + BASE_T, BASE_H), base_mat),
        ((JOG_X - BASE_T, -HY + BASE_T, -0.001), (JOG_X + BITE, JOG_Y, BASE_H), base_mat),
        ((JOG_X, JOG_Y - BITE, -0.001), (JOG_X + WALL_T, JOG_Y + BASE_T, BASE_H), base_mat),
        ((JOG_X + WALL_T, JOG_Y - BITE, -0.001), (HX - BASE_T, JOG_Y + BASE_T, BASE_H), base_mat),
        ((HX - BASE_T, JOG_Y + BASE_T, -0.001), (HX + BITE, HY - BASE_T, BASE_H), base_mat),
    ]
    build_object("Baseboard", base_parts)

    for name, y0, y1 in (("Window_Near", WIN1_Y0, WIN1_Y1), ("Window_Far", WIN2_Y0, WIN2_Y1)):
        build_object(name, window_parts(y0, y1, fx0, fx1, x_int, frame_mat, wall_mat))
        gparts = [((mn[0], mn[1], mn[2]), mx, glass_mat) for mn, mx, _ in glass_parts(y0, y1, fx0)]
        glass = build_object(name + "_Glass", gparts)
        if hasattr(glass, "visible_shadow"):
            glass.visible_shadow = False

    slab_t = 0.035
    gap = 0.008
    slab_y0 = south_y0 + 0.03
    slab_y1 = slab_y0 + slab_t
    slab_x0 = door_x0 + gap
    slab_x1 = door_x1 - gap
    slab_z1 = DOOR_H - gap
    casing_t = 0.016
    build_object(
        "Door",
        [
            ((slab_x0, slab_y0, 0.012), (slab_x1, slab_y1, slab_z1), door_mat),
            ((slab_x0 + 0.08, slab_y1, 0.16), (slab_x1 - 0.08, slab_y1 + 0.008, 0.92), door_mat),
            ((slab_x0 + 0.08, slab_y1, 1.06), (slab_x1 - 0.08, slab_y1 + 0.008, slab_z1 - 0.08), door_mat),
            ((door_x0 - casing, -HY - BITE, -BITE), (door_x0, -HY + casing_t, DOOR_H + casing), casing_mat),
            ((door_x1, -HY - BITE, -BITE), (door_x1 + casing, -HY + casing_t, DOOR_H + casing), casing_mat),
            ((door_x0, -HY - BITE, DOOR_H), (door_x1, -HY + casing_t, DOOR_H + casing), casing_mat),
            ((slab_x1 - 0.07, slab_y1, 0.98), (slab_x1 - 0.04, slab_y1 + 0.02, 1.04), metal_mat),
            ((slab_x1 - 0.15, slab_y1 + 0.006, 1.005), (slab_x1 - 0.055, slab_y1 + 0.016, 1.02), metal_mat),
        ],
    )

    anchors = anchor_specs()
    for name, spec in anchors.items():
        add_empty(name, spec["position_m"], spec["yaw_deg"])

    meshes = [obj for obj in scene.objects if obj.type == "MESH"]
    lo, hi = world_bbox(meshes)
    size = hi - lo
    tris = triangle_count(meshes)
    print(f"BBOX min {tuple(round(v, 4) for v in lo)}")
    print(f"BBOX max {tuple(round(v, 4) for v in hi)}")
    print(f"BBOX size {tuple(round(v, 4) for v in size)}")
    print(f"TRIANGLES {tris}")

    expected_lo = Vector((-(HX + WALL_T_W), -(HY + WALL_T), -FLOOR_T))
    expected_hi = Vector((HX + WALL_T, HY + WALL_T, HEIGHT_Z + CEIL_T))
    for i in range(3):
        if abs(lo[i] - expected_lo[i]) > 0.004 or abs(hi[i] - expected_hi[i]) > 0.004:
            raise SystemExit(
                f"bbox mismatch axis {i}: got {(lo[i], hi[i])} expected {(expected_lo[i], expected_hi[i])}"
            )

    def rnd(v):
        return [round(float(v[0]), 4), round(float(v[1]), 4), round(float(v[2]), 4)]

    def win_opening(obj_name, y0, y1):
        return {
            "object": obj_name,
            "glass": obj_name + "_Glass",
            "wall": "Wall_W",
            "width_m": round(WIN_W, 4),
            "height_m": round(WIN_H, 4),
            "sill_z_m": round(WIN_SILL, 4),
            "grid": "3 columns x 4 rows",
            "reveal_depth_m": REVEAL,
            "center_m": [
                round(-HX - WALL_T_W / 2.0, 4),
                round((y0 + y1) / 2.0, 4),
                round(WIN_SILL + WIN_H / 2.0, 4),
            ],
        }

    # Walkable outline. The 0.12 m jog wall is not floor, so the alcove
    # starts at the east face of that wall.
    polygon = [
        [round(-HX, 4), round(-HY, 4)],
        [round(JOG_X, 4), round(-HY, 4)],
        [round(JOG_X, 4), round(JOG_Y, 4)],
        [round(JOG_X + WALL_T, 4), round(JOG_Y, 4)],
        [round(HX, 4), round(JOG_Y, 4)],
        [round(HX, 4), round(HY, 4)],
        [round(-HX, 4), round(HY, 4)],
    ]

    meta = {
        "id": "bright_loft",
        "name": "Bright loft with tall windows",
        "description": (
            "Spacious empty loft with a honey oak strip floor, white walls, thin black "
            "baseboards, and a flat white ceiling. Two tall black-framed grid windows sit "
            "in deep reveals on the west long wall. The east wall jogs into the room along "
            "its south run and opens into a northeast alcove. A 36 by 80 inch door is on "
            "the south wall."
        ),
        "units": "meters",
        "up_axis": "Z",
        "origin": "interior floor center (0, 0, 0); floor top is Z=0",
        "interior_m": {
            "width_x": round(WIDTH_X, 4),
            "depth_y": round(DEPTH_Y, 4),
            "height_z": round(HEIGHT_Z, 4),
        },
        "interior_ft": {"width_x": 19.0, "depth_y": 25.0, "height_z": 10.5},
        "ceiling_height_m": round(HEIGHT_Z, 4),
        "ceiling_height_ft": 10.5,
        "wall_thickness_m": WALL_T,
        "window_wall_thickness_m": WALL_T_W,
        "main_bay_m": {
            "width_x": round(JOG_X + HX, 4),
            "depth_y": round(DEPTH_Y, 4),
            "note": "Rectangle west of the jog, before the alcove is added.",
        },
        "walls": {
            "Wall_N": "+Y short wall, blank TV wall",
            "Wall_S": "-Y short wall, doorway",
            "Wall_E": "+X alcove outer wall",
            "Wall_W": "-X long wall, two tall windows",
            "Wall_Jog": "east wall jog, interior face at X=JOG_X, from the south wall to the alcove",
            "Wall_Return": "south side of the northeast alcove",
        },
        "jog": {
            "clear_depth_m": round(ALC_CLEAR, 4),
            "clear_depth_ft": 4.0,
            "length_along_y_m": round(HY - JOG_Y, 4),
            "length_along_y_ft": 10.0,
            "interior_corner_m": [round(JOG_X, 4), round(JOG_Y, 4)],
            "note": (
                "The east wall steps west into the room from the south wall up to the "
                "return, leaving a 4 ft by 10 ft alcove in the northeast."
            ),
        },
        "openings": {
            "windows": [
                win_opening("Window_Near", WIN1_Y0, WIN1_Y1),
                win_opening("Window_Far", WIN2_Y0, WIN2_Y1),
            ],
            "door": {
                "object": "Door",
                "wall": "Wall_S",
                "width_in": 36,
                "height_in": 80,
                "width_m": round(DOOR_W, 4),
                "height_m": round(DOOR_H, 4),
                "center_m": [
                    round((door_x0 + door_x1) / 2.0, 4),
                    round(-HY - WALL_T / 2.0, 4),
                    round(DOOR_H / 2.0, 4),
                ],
            },
        },
        "bbox_m": {"min": rnd(lo), "max": rnd(hi), "size": rnd(size)},
        "free_floor": {
            "polygon_m": polygon,
            "note": (
                "Walkable floor at Z=0. Vertices in order around the interior footprint. "
                "X is east, Y is north. The jog wall (thickness 0.12 m east of JOG_X, "
                "south of JOG_Y) is not floor. Primary seating fits in the main bay, "
                "clear of the south door."
            ),
            "seating_rect_m": {
                "min": [round(-HX + 0.5, 4), round(-HY + 1.05, 4)],
                "max": [round(JOG_X - 0.45, 4), round(HY - 0.4, 4)],
            },
        },
        "empties": anchors,
        "triangle_count": tris,
        "objects": [
            "Floor",
            "Wall_N",
            "Wall_S",
            "Wall_E",
            "Wall_W",
            "Wall_Jog",
            "Wall_Return",
            "Ceiling",
            "Window_Near",
            "Window_Near_Glass",
            "Window_Far",
            "Window_Far_Glass",
            "Door",
            "Baseboard",
            "TV_wall",
            "Sofa_spot",
            "Rug_center",
            "Coffee_spot",
            "Plant_corner",
            "Lamp_corner",
            "Alcove_spot",
        ],
    }
    return meta


def anchor_specs():
    """Yaw is degrees about Z. Furniture front is local -Y."""
    plant = [-HX + 0.62, HY - 0.62, 0.0]
    lamp = [-HX + 0.55, -HY + 0.58, 0.0]
    alcove = [(JOG_X + WALL_T + HX) / 2.0, (JOG_Y + HY) / 2.0, 0.0]
    specs = {
        "TV_wall": {
            "position_m": [round(SEAT_X, 4), round(HY - 0.28, 4), 0.0],
            "yaw_deg": 0,
            "rotation_z_deg": 0,
            "note": "Floor anchor on the blank north wall, centered in the main bay. Yaw 0 so a TV's front (local -Y) faces into the room. Raise Z to wall-mount the screen.",
        },
        "Sofa_spot": {
            "position_m": [round(SEAT_X, 4), -0.70, 0.0],
            "yaw_deg": 180,
            "rotation_z_deg": 180,
            "note": "Floor anchor for a sofa in the main bay. Yaw 180 so its front (local -Y) faces TV_wall.",
        },
        "Rug_center": {
            "position_m": [round(SEAT_X, 4), 0.10, 0.0],
            "yaw_deg": 0,
            "rotation_z_deg": 0,
            "note": "Center of the seating rug between the sofa and the coffee table. Yaw 0 lays an 8x10 carpet with its long side along Y.",
        },
        "Coffee_spot": {
            "position_m": [round(SEAT_X, 4), 0.85, 0.0],
            "yaw_deg": 0,
            "rotation_z_deg": 0,
            "note": "Floor anchor for a coffee table between the sofa and the north wall. Yaw 0.",
        },
        "Plant_corner": {
            "position_m": [round(plant[0], 4), round(plant[1], 4), 0.0],
            "yaw_deg": 0,
            "rotation_z_deg": 0,
            "note": "Northwest corner, beside the blank wall and clear of the far window. Yaw 0.",
        },
        "Lamp_corner": {
            "position_m": [round(lamp[0], 4), round(lamp[1], 4), 0.0],
            "yaw_deg": 0,
            "rotation_z_deg": 0,
            "note": "Southwest corner for a floor lamp, west of the door. Yaw 0.",
        },
        "Alcove_spot": {
            "position_m": [round(alcove[0], 4), round(alcove[1], 4), 0.0],
            "yaw_deg": -90,
            "rotation_z_deg": -90,
            "note": "Center of the northeast alcove. Yaw -90 so a chair or lamp front (local -Y) faces west into the main room.",
        },
    }
    return specs


def add_camera_and_sun():
    scene = bpy.context.scene
    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens = 16
    cam_data.sensor_width = 36
    cam_data.clip_start = 0.05
    cam_data.clip_end = 40
    cam = bpy.data.objects.new("Camera", cam_data)
    bpy.context.collection.objects.link(cam)
    # Inside the south end of the main bay, looking north toward the blank wall.
    # Windows fall on the left, the jog on the right, matching the reference photo.
    cam.location = (1.22, -3.48, 1.46)
    look_at(cam, Vector((-1.85, 0.75, 1.42)))
    scene.camera = cam

    sun_data = bpy.data.lights.new("Sun", "SUN")
    sun_data.energy = 5.5
    sun_data.angle = math.radians(1.4)
    sun_data.color = (1.0, 0.96, 0.88)
    sun = bpy.data.objects.new("Sun", sun_data)
    bpy.context.collection.objects.link(sun)
    # Low enough that light through the west windows still reaches the north wall.
    elev = math.radians(22)
    az = math.radians(68)
    direction = Vector(
        (
            math.cos(elev) * math.cos(az),
            math.cos(elev) * math.sin(az),
            -math.sin(elev),
        )
    )
    sun.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

    fill_data = bpy.data.lights.new("Fill", "AREA")
    fill_data.energy = 18
    fill_data.size = 6.0
    fill_data.color = (1.0, 0.98, 0.95)
    fill = bpy.data.objects.new("Fill", fill_data)
    bpy.context.collection.objects.link(fill)
    fill.location = (SEAT_X, 0.4, 2.85)
    fill.rotation_euler = (0.0, 0.0, 0.0)

    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.96, 0.97, 1.0, 1.0)
    bg.inputs["Strength"].default_value = 1.15
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.exposure = -0.12

    ee = getattr(scene, "eevee", None)
    if ee is not None:
        interesting = [a for a in dir(ee) if "shadow" in a.lower() or "taa" in a.lower() or "sample" in a.lower()]
        print("EEVEE ATTRS", interesting)
        for attr, val in (
            ("taa_render_samples", 48),
            ("use_shadows", True),
            ("use_shadow_high_bitdepth", True),
            ("use_raytracing", True),
        ):
            if hasattr(ee, attr):
                try:
                    setattr(ee, attr, val)
                except Exception as exc:
                    print("eevee skip", attr, exc)
        for attr in ("shadow_cascade_size", "shadow_cube_size"):
            if hasattr(ee, attr):
                try:
                    setattr(ee, attr, "4096")
                    print("set", attr)
                except Exception as exc:
                    print("eevee skip", attr, exc)


def render_preview(path):
    scene = bpy.context.scene
    scene.render.resolution_x = 1024
    scene.render.resolution_y = 640
    scene.render.resolution_percentage = 100
    scene.render.filepath = path
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    # South wall is behind this camera. Keep the ceiling so the tall room reads.
    hidden = []
    for name in ("Wall_S", "Door"):
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
        scene.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in [i.identifier for i in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_WORKBENCH"
        try:
            bpy.ops.render.render(write_still=True)
            print("RENDER engine", scene.render.engine)
        except Exception as exc2:
            print("fallback failed:", exc2)
            scene.render.engine = "BLENDER_WORKBENCH"
            scene.display.shading.light = "STUDIO"
            scene.display.shading.color_type = "MATERIAL"
            scene.display.shading.show_shadows = True
            bpy.ops.render.render(write_still=True)
            print("RENDER engine BLENDER_WORKBENCH")
    for obj in hidden:
        obj.hide_render = False


def export_assets(out, meta):
    import addon_utils

    addon_utils.enable("io_scene_gltf2", default_set=False, persistent=False)

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
