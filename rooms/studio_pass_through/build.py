"""Studio with a pass-through kitchen.

Long narrow rental studio. Origin is the center of the full interior footprint
(living room plus the kitchen/entry service zone). Z is up. Floor top is Z=0.
Furniture front faces local -Y; anchor yaw is the Z rotation to apply.

    living room, 12 ft x 18.5 ft, window wall at -Y
    |------------------------------|
    |                              |
    |         open floor           |   +X east blank wall
    |                              |
    |---------|------|-------------|  Y_SPLIT
    | kitchen | hall | bifold      |
    | nook    | door | closet      |   service zone, 6 ft
    |---------|------|-------------|

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

# Overall shell is the 12 x 18.5 ft living floor plus a 6 ft service zone.
WIDTH_FT = 12.0
LIVING_FT = 18.5
SERVICE_FT = 6.0
HEIGHT_FT = 8.5

WIDTH_X = WIDTH_FT * FT
LIVING_D = LIVING_FT * FT
SERVICE_D = SERVICE_FT * FT
TOTAL_Y = LIVING_D + SERVICE_D
HEIGHT_Z = HEIGHT_FT * FT
WALL_T = 0.12
FLOOR_T = 0.04
CEIL_T = 0.04

HX = WIDTH_X / 2
HY = TOTAL_Y / 2
Y_S = -HY
Y_N = HY
Y_SPLIT = Y_S + LIVING_D

# Far-end program, inches from the west interior face. 66+5+38+35 = 144.
KIT_IN = 66.0
PIER_IN = 5.0
HALL_IN = 38.0
CLOSET_IN = 35.0

DOOR_W = 36 * IN
DOOR_H = 80 * IN
COUNTER_H = 36 * IN
COUNTER_D = 25 * IN
BAR_H = 36.5 * IN
CAP_T = 1.25 * IN
SOFFIT_DROP = 15 * IN

BASE_H = 3.5 * IN
BASE_T = 0.016
BITE = 0.004

WIN_W = 9.0 * FT
WIN_SILL = 30 * IN
WIN_HEAD = 86 * IN


def xin(inches_from_west):
    return -HX + inches_from_west * IN


X_K0 = xin(0.0)
X_K1 = xin(KIT_IN)
X_P0 = X_K1
X_P1 = xin(KIT_IN + PIER_IN)
X_H0 = X_P1
X_C0 = xin(KIT_IN + PIER_IN + HALL_IN)
X_C1 = HX

# Back-wall appliance run inside the 66 in kitchen: 12 in cabinet, 24 in range, 30 in fridge.
X_CAB1 = xin(12.0)
X_RNG0 = xin(12.0)
X_RNG1 = xin(36.0)
X_FR0 = xin(36.0)
X_FR1 = xin(66.0)


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


def make_material(
    name,
    color,
    roughness=0.55,
    metallic=0.0,
    alpha=1.0,
    transmission=0.0,
    emission=0.0,
):
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
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = emission
        if "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = (*color, 1.0)
    if alpha < 0.999 or transmission:
        if hasattr(mat, "blend_method"):
            mat.blend_method = "BLEND"
        if hasattr(mat, "surface_render_method"):
            mat.surface_render_method = "BLENDED"
        if hasattr(mat, "use_transparency_overlap"):
            mat.use_transparency_overlap = True
    return mat


def add_box(bm, mn, mx, material_index):
    sx = mx[0] - mn[0]
    sy = mx[1] - mn[1]
    sz = mx[2] - mn[2]
    if sx <= 1e-6 or sy <= 1e-6 or sz <= 1e-6:
        raise ValueError(f"degenerate box {tuple(round(v, 4) for v in mn)} {tuple(round(v, 4) for v in mx)}")
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
    """parts: list of (min_xyz, max_xyz, material). Min/max corners are sorted."""
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    index_of = {}
    for a, b, mat in parts:
        mn = tuple(min(a[i], b[i]) for i in range(3))
        mx = tuple(max(a[i], b[i]) for i in range(3))
        if mat.name not in index_of:
            index_of[mat.name] = len(index_of)
            mesh.materials.append(mat)
        add_box(bm, mn, mx, index_of[mat.name])
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def box(parts, a, b, mat):
    parts.append((a, b, mat))


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


def build_dome(name, xy, radius, trim_mat, glow_mat):
    """Flush ceiling dome. Object origin sits on the ceiling underside."""
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    mesh.materials.append(trim_mat)
    mesh.materials.append(glow_mat)

    existing = set(bm.faces)
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=24,
        radius1=radius,
        radius2=radius,
        depth=0.016,
    )
    ring_faces = [face for face in bm.faces if face not in existing]
    ring_verts = [vert for vert in bm.verts]
    bmesh.ops.translate(bm, verts=ring_verts, vec=(0.0, 0.0, -0.006))
    for face in ring_faces:
        face.material_index = 0

    existing = set(bm.faces)
    bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=radius * 0.78)
    dome_faces = [face for face in bm.faces if face not in existing]
    dome_verts = []
    seen = set()
    for face in dome_faces:
        for vert in face.verts:
            if vert not in seen:
                seen.add(vert)
                dome_verts.append(vert)
    for vert in dome_verts:
        vert.co.z *= 0.22
        vert.co.z -= radius * 0.22
    for face in dome_faces:
        face.material_index = 1

    bm.to_mesh(mesh)
    bm.free()
    for poly in mesh.polygons:
        poly.use_smooth = True
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = (xy[0], xy[1], HEIGHT_Z)
    bpy.context.collection.objects.link(obj)
    return obj


def add_south_louver_door(parts, x0, x1, y0, y1, z0, z1, mat):
    stile = 0.04
    rail_b = 0.07
    rail_t = 0.05
    box(parts, (x0, y0, z0), (x0 + stile, y1, z1), mat)
    box(parts, (x1 - stile, y0, z0), (x1, y1, z1), mat)
    box(parts, (x0, y0, z0), (x1, y1, z0 + rail_b), mat)
    box(parts, (x0, y0, z1 - rail_t), (x1, y1, z1), mat)
    z = z0 + rail_b + 0.012
    z_top = z1 - rail_t - 0.008
    guard = 0
    while z + 0.014 <= z_top and guard < 40:
        box(
            parts,
            (x0 + stile + 0.006, y0 + 0.005, z),
            (x1 - stile - 0.006, y1 - 0.005, z + 0.014),
            mat,
        )
        z += 0.072
        guard += 1


def base_y_face(parts, x0, x1, y_face, into_positive_y, mat):
    """Baseboard on a wall face whose normal points along Y."""
    if into_positive_y:
        y0, y1 = y_face - BITE, y_face + BASE_T
    else:
        y0, y1 = y_face - BASE_T, y_face + BITE
    box(parts, (x0, y0, -0.002), (x1, y1, BASE_H), mat)


def base_x_face(parts, y0, y1, x_face, into_positive_x, mat):
    if into_positive_x:
        x0, x1 = x_face - BITE, x_face + BASE_T
    else:
        x0, x1 = x_face - BASE_T, x_face + BITE
    box(parts, (x0, y0, -0.002), (x1, y1, BASE_H), mat)


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = "METERS"

    floor_mat = make_material("Floor_Wood", (0.80, 0.58, 0.32), roughness=0.38)
    wall_mat = make_material("Wall_Paint", (0.965, 0.965, 0.96), roughness=0.7)
    ceil_mat = make_material("Ceiling_Paint", (0.97, 0.97, 0.96), roughness=0.8)
    trim_mat = make_material("Trim_Paint", (0.97, 0.97, 0.96), roughness=0.48)
    door_mat = make_material("Door_Paint", (0.95, 0.95, 0.94), roughness=0.42)
    frame_mat = make_material("Window_Frame", (0.96, 0.96, 0.95), roughness=0.38)
    glass_mat = make_material(
        "Window_Glass",
        (0.68, 0.82, 0.90),
        roughness=0.05,
        alpha=0.28,
        transmission=0.92,
    )
    steel_mat = make_material("Stainless", (0.62, 0.63, 0.65), roughness=0.22, metallic=0.88)
    granite_mat = make_material("Granite", (0.58, 0.55, 0.51), roughness=0.32)
    cab_mat = make_material("Cabinet_Gray", (0.50, 0.52, 0.54), roughness=0.46)
    cab_door_mat = make_material("Cabinet_Door", (0.40, 0.42, 0.44), roughness=0.4)
    fridge_mat = make_material("Fridge_White", (0.91, 0.91, 0.92), roughness=0.24, metallic=0.08)
    cook_mat = make_material("Cooktop", (0.05, 0.05, 0.055), roughness=0.1, metallic=0.4)
    toe_mat = make_material("Toe_Kick", (0.16, 0.16, 0.15), roughness=0.7)
    glow_mat = make_material("Dome_Glow", (1.0, 0.95, 0.84), roughness=0.25, emission=1.6)
    dark_mat = make_material("Dark_Inset", (0.08, 0.08, 0.09), roughness=0.35)
    backdrop_mat = make_material("Backdrop_Sky", (0.74, 0.83, 0.91), roughness=0.9, emission=1.3)

    wall_z0 = -0.002
    wall_z1 = HEIGHT_Z + 0.002
    soffit_z = HEIGHT_Z - SOFFIT_DROP

    # --- Shell ---
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

    build_object(
        "Wall_W",
        [((-(HX + WALL_T), -(HY + WALL_T), wall_z0), (-HX, HY + WALL_T, wall_z1), wall_mat)],
    )
    build_object(
        "Wall_E",
        [((HX, -(HY + WALL_T), wall_z0), (HX + WALL_T, HY + WALL_T, wall_z1), wall_mat)],
    )

    win_x0 = -WIN_W / 2
    win_x1 = WIN_W / 2
    south_y0 = Y_S - WALL_T
    south_y1 = Y_S
    build_object(
        "Wall_S",
        [
            ((-HX, south_y0, wall_z0), (win_x0, south_y1, wall_z1), wall_mat),
            ((win_x1, south_y0, wall_z0), (HX, south_y1, wall_z1), wall_mat),
            ((win_x0, south_y0, wall_z0), (win_x1, south_y1, WIN_SILL), wall_mat),
            ((win_x0, south_y0, WIN_HEAD), (win_x1, south_y1, wall_z1), wall_mat),
        ],
    )

    door_cx = (X_H0 + X_C0) / 2
    door_x0 = door_cx - DOOR_W / 2
    door_x1 = door_cx + DOOR_W / 2
    if not (X_H0 + 0.012 < door_x0 and door_x1 < X_C0 - 0.012):
        raise SystemExit(f"entry door does not fit the hall: {(door_x0, door_x1)} hall {(X_H0, X_C0)}")

    north_y0 = Y_N
    north_y1 = Y_N + WALL_T
    build_object(
        "Wall_N",
        [
            ((-HX, north_y0, wall_z0), (door_x0, north_y1, wall_z1), wall_mat),
            ((door_x1, north_y0, wall_z0), (HX, north_y1, wall_z1), wall_mat),
            ((door_x0, north_y0, DOOR_H), (door_x1, north_y1, wall_z1), wall_mat),
        ],
    )

    build_object(
        "Ceiling",
        [((-HX, Y_S, HEIGHT_Z), (HX, Y_N, HEIGHT_Z + CEIL_T), ceil_mat)],
    )

    # Pier between the kitchen opening and the hall, full height.
    build_object(
        "Wall_Pier",
        [((X_P0, Y_SPLIT, wall_z0), (X_P1, Y_N + 0.002, wall_z1), wall_mat)],
    )

    # Closet occupies the northeast corner. Its west wall is the hall's east side.
    closet_jamb = 0.06
    build_object(
        "Closet",
        [
            ((X_C0, Y_SPLIT, wall_z0), (X_C0 + closet_jamb, Y_N + 0.002, wall_z1), wall_mat),
            # Header above the bifolds, south face flush with the living-room side.
            (
                (X_C0 + closet_jamb, Y_SPLIT, DOOR_H),
                (X_C1 + 0.002, Y_SPLIT + 0.08, wall_z1),
                wall_mat,
            ),
            # Shelf inside, so the louver gaps have something to catch.
            (
                (X_C0 + closet_jamb + 0.02, Y_SPLIT + 0.25, 1.35),
                (X_C1 - 0.02, Y_N - 0.08, 1.37),
                trim_mat,
            ),
        ],
    )

    # Half wall and granite breakfast ledge. Opening runs up to the soffit.
    half_y0 = Y_SPLIT
    half_y1 = Y_SPLIT + 0.11
    build_object(
        "Halfwall",
        [((X_K0, half_y0, wall_z0), (X_K1 + 0.002, half_y1, BAR_H - CAP_T), wall_mat)],
    )
    build_object(
        "Kitchen_Ledge",
        [
            (
                (X_K0, half_y0 - 0.045, BAR_H - CAP_T),
                (X_K1, half_y1 + 0.015, BAR_H),
                granite_mat,
            )
        ],
    )
    build_object(
        "Ceiling_Soffit",
        [
            (
                (X_K0 - 0.002, Y_SPLIT - 0.02, soffit_z),
                (X_P1, Y_SPLIT + 0.42, wall_z1),
                wall_mat,
            )
        ],
    )

    # --- Window wall (near end, south) ---
    frame = 0.045
    glass_t = 0.008
    glass_y = south_y0 + WALL_T / 2
    lip = 0.004
    mullion = 0.03
    span = (win_x1 - win_x0 - 2 * frame) / 3
    m1 = win_x0 + frame + span
    m2 = m1 + span
    window_parts = [
        ((win_x0, south_y0, WIN_SILL), (win_x1, south_y1, WIN_SILL + frame), frame_mat),
        ((win_x0, south_y0, WIN_HEAD - frame), (win_x1, south_y1, WIN_HEAD), frame_mat),
        ((win_x0, south_y0, WIN_SILL), (win_x0 + frame, south_y1, WIN_HEAD), frame_mat),
        ((win_x1 - frame, south_y0, WIN_SILL), (win_x1, south_y1, WIN_HEAD), frame_mat),
        ((m1 - mullion / 2, south_y0, WIN_SILL + frame), (m1 + mullion / 2, south_y1, WIN_HEAD - frame), frame_mat),
        ((m2 - mullion / 2, south_y0, WIN_SILL + frame), (m2 + mullion / 2, south_y1, WIN_HEAD - frame), frame_mat),
        (
            (win_x0 + frame, glass_y - glass_t / 2, WIN_SILL + frame),
            (win_x1 - frame, glass_y + glass_t / 2, WIN_HEAD - frame),
            glass_mat,
        ),
        # Interior stool and casing.
        ((win_x0 - 0.02, Y_S - lip, WIN_SILL - 0.02), (win_x1 + 0.02, Y_S + 0.035, WIN_SILL + 0.012), frame_mat),
        ((win_x0 - 0.015, Y_S - lip, WIN_SILL), (win_x0, Y_S + 0.012, WIN_HEAD + 0.015), frame_mat),
        ((win_x1, Y_S - lip, WIN_SILL), (win_x1 + 0.015, Y_S + 0.012, WIN_HEAD + 0.015), frame_mat),
        ((win_x0, Y_S - lip, WIN_HEAD), (win_x1, Y_S + 0.012, WIN_HEAD + 0.015), frame_mat),
    ]
    build_object("Window_S", window_parts)

    # Bright exterior so the glass reads as a window in the render. Not exported.
    build_object(
        "Render_Backdrop",
        [((-4.0, south_y0 - 0.25, 0.15), (4.0, south_y0 - 0.22, 4.2), backdrop_mat)],
    )

    # --- Entry door, interior (hall) face toward -Y ---
    slab_t = 0.035
    gap = 0.008
    slab_y1 = north_y0 + 0.02
    slab_y0 = slab_y1 - slab_t
    slab_x0 = door_x0 + gap
    slab_x1 = door_x1 - gap
    slab_z1 = DOOR_H - gap
    casing = 0.018
    door_parts = [
        ((slab_x0, slab_y0, 0.012), (slab_x1, slab_y1, slab_z1), door_mat),
        ((slab_x0 + 0.08, slab_y0 - 0.008, 0.12), (slab_x1 - 0.08, slab_y0, 0.95), door_mat),
        ((slab_x0 + 0.08, slab_y0 - 0.008, 1.08), (slab_x1 - 0.08, slab_y0, slab_z1 - 0.08), door_mat),
        ((door_x0 - casing, north_y0 - casing, -BITE), (door_x0, north_y0 + 0.008, DOOR_H + casing), trim_mat),
        ((door_x1, north_y0 - casing, -BITE), (door_x1 + casing, north_y0 + 0.008, DOOR_H + casing), trim_mat),
        ((door_x0 - casing, north_y0 - casing, DOOR_H), (door_x1 + casing, north_y0 + 0.008, DOOR_H + casing), trim_mat),
        # Lever and deadbolt on the hall side, east stile.
        ((slab_x1 - 0.07, slab_y0 - 0.02, 0.98), (slab_x1 - 0.04, slab_y0, 1.05), steel_mat),
        ((slab_x1 - 0.16, slab_y0 - 0.016, 1.0), (slab_x1 - 0.05, slab_y0 - 0.006, 1.018), steel_mat),
        ((slab_x1 - 0.065, slab_y0 - 0.012, 1.42), (slab_x1 - 0.04, slab_y0, 1.47), steel_mat),
        ((slab_cx_peephole := (slab_x0 + slab_x1) / 2 - 0.012, slab_y0 - 0.01, 1.52), (slab_cx_peephole + 0.024, slab_y0, 1.545), dark_mat),
    ]
    build_object("Door_Entry", door_parts)

    # --- Louvered bifolds, facing the living room (-Y) ---
    door_y0 = Y_SPLIT + 0.02
    door_y1 = door_y0 + 0.03
    open_x0 = X_C0 + closet_jamb + 0.008
    open_x1 = X_C1 - 0.012
    mid = (open_x0 + open_x1) / 2
    gap_d = 0.008
    closet_parts = []
    add_south_louver_door(closet_parts, open_x0, mid - gap_d / 2, door_y0, door_y1, 0.012, DOOR_H - 0.008, door_mat)
    add_south_louver_door(closet_parts, mid + gap_d / 2, open_x1, door_y0, door_y1, 0.012, DOOR_H - 0.008, door_mat)
    # Knobs where the two panels meet.
    box(closet_parts, (mid - 0.03, door_y0 - 0.012, 0.98), (mid - 0.012, door_y0, 1.0), steel_mat)
    box(closet_parts, (mid + 0.012, door_y0 - 0.012, 0.98), (mid + 0.03, door_y0, 1.0), steel_mat)
    build_object("Closet_Doors", closet_parts)

    # --- Kitchen nook ---
    # 12 in gray base on the left, 24 in range, 30 in fridge, all on the north wall.
    cab_x0 = X_K0 + 0.012
    cab_x1 = X_CAB1 - 0.008
    cab_y1 = Y_N - 0.004
    cab_y0 = cab_y1 - (COUNTER_D - 0.04)
    kitchen_cab = []
    box(kitchen_cab, (cab_x0, cab_y0, 0.0), (cab_x1, cab_y1, 0.09), toe_mat)
    box(kitchen_cab, (cab_x0, cab_y0, 0.09), (cab_x1, cab_y1, COUNTER_H - CAP_T), cab_mat)
    # Two drawer fronts on the aisle face.
    drawer_h = (COUNTER_H - CAP_T - 0.12) / 2
    for i in range(2):
        z0 = 0.11 + i * (drawer_h + 0.008)
        box(
            kitchen_cab,
            (cab_x0 + 0.012, cab_y0 - 0.008, z0),
            (cab_x1 - 0.012, cab_y0, z0 + drawer_h - 0.004),
            cab_door_mat,
        )
        box(
            kitchen_cab,
            (cab_x0 + 0.05, cab_y0 - 0.02, z0 + drawer_h * 0.45),
            (cab_x1 - 0.05, cab_y0 - 0.008, z0 + drawer_h * 0.45 + 0.012),
            steel_mat,
        )
    # Upper on the back wall, left of the microwave, bottom at 54 in.
    upper_z0 = 54 * IN
    upper_z1 = 84 * IN
    box(kitchen_cab, (cab_x0, Y_N - 0.33, upper_z0), (cab_x1, Y_N - 0.004, upper_z1), cab_mat)
    box(
        kitchen_cab,
        (cab_x0 + 0.012, Y_N - 0.33 - 0.008, upper_z0 + 0.02),
        (cab_x1 - 0.012, Y_N - 0.33, upper_z1 - 0.02),
        cab_door_mat,
    )
    box(
        kitchen_cab,
        ((cab_x0 + cab_x1) / 2 - 0.04, Y_N - 0.33 - 0.02, (upper_z0 + upper_z1) / 2),
        ((cab_x0 + cab_x1) / 2 + 0.04, Y_N - 0.33 - 0.008, (upper_z0 + upper_z1) / 2 + 0.012),
        steel_mat,
    )
    # Longer upper on the west wall, seen through the left side of the pass-through.
    west_upper_y0 = Y_SPLIT + 0.28
    west_upper_y1 = west_upper_y0 + 28 * IN
    box(
        kitchen_cab,
        (X_K0 - 0.002, west_upper_y0, upper_z0),
        (X_K0 + 12 * IN, west_upper_y1, upper_z1),
        cab_mat,
    )
    box(
        kitchen_cab,
        (X_K0 + 12 * IN, west_upper_y0 + 0.02, upper_z0 + 0.02),
        (X_K0 + 12 * IN + 0.008, west_upper_y1 - 0.02, upper_z1 - 0.02),
        cab_door_mat,
    )
    build_object("Kitchen_Cabinet", kitchen_cab)

    counter_parts = [
        (
            (cab_x0 - 0.004, cab_y0 - 0.025, COUNTER_H - CAP_T),
            (cab_x1 + 0.004, cab_y1, COUNTER_H),
            granite_mat,
        ),
        # Short backsplash behind the cabinet.
        ((cab_x0, Y_N - 0.012, COUNTER_H), (cab_x1, Y_N, COUNTER_H + 0.10), granite_mat),
    ]
    build_object("Kitchen_Counter", counter_parts)

    rng_x0 = X_RNG0 + 0.008
    rng_x1 = X_RNG1 - 0.008
    rng_y1 = Y_N - 0.004
    rng_y0 = rng_y1 - COUNTER_D
    range_parts = [
        ((rng_x0, rng_y0, 0.0), (rng_x1, rng_y1, COUNTER_H - 0.02), steel_mat),
        # Oven door.
        ((rng_x0 + 0.02, rng_y0 - 0.01, 0.08), (rng_x1 - 0.02, rng_y0, COUNTER_H - 0.14), steel_mat),
        ((rng_x0 + 0.06, rng_y0 - 0.016, 0.28), (rng_x1 - 0.06, rng_y0 - 0.01, COUNTER_H - 0.28), dark_mat),
        ((rng_x0 + 0.08, rng_y0 - 0.028, COUNTER_H - 0.22), (rng_x1 - 0.08, rng_y0 - 0.012, COUNTER_H - 0.19), steel_mat),
        # Cooktop flush with the neighboring counter.
        ((rng_x0 + 0.01, rng_y0 + 0.02, COUNTER_H - 0.018), (rng_x1 - 0.01, rng_y1 - 0.04, COUNTER_H + 0.004), cook_mat),
        ((rng_x0, rng_y1 - 0.045, COUNTER_H - 0.01), (rng_x1, rng_y1, COUNTER_H + 0.012), steel_mat),
        ((rng_x0 + 0.01, rng_y1 - 0.02, COUNTER_H), (rng_x1 - 0.01, rng_y1, COUNTER_H + 0.10), steel_mat),
    ]
    # Four burners.
    bw, bd = 0.07, 0.05
    for bx in (rng_x0 + 0.08, rng_x1 - 0.08 - bw):
        for by in (rng_y0 + 0.08, rng_y1 - 0.14 - bd):
            box(range_parts, (bx, by, COUNTER_H + 0.004), (bx + bw, by + bd, COUNTER_H + 0.008), dark_mat)
    build_object("Kitchen_Range", range_parts)

    micro_z0 = 54 * IN
    micro_z1 = micro_z0 + 15 * IN
    micro_y1 = Y_N - 0.004
    micro_y0 = micro_y1 - 14 * IN
    micro_parts = [
        ((rng_x0, micro_y0, micro_z0), (rng_x1, micro_y1, micro_z1), steel_mat),
        ((rng_x0 + 0.025, micro_y0 - 0.008, micro_z0 + 0.04), (rng_x1 - 0.07, micro_y0, micro_z1 - 0.025), dark_mat),
        ((rng_x1 - 0.055, micro_y0 - 0.02, micro_z0 + 0.08), (rng_x1 - 0.03, micro_y0 - 0.008, micro_z1 - 0.08), steel_mat),
    ]
    build_object("Kitchen_Microwave", micro_parts)

    fr_x0 = X_FR0 + 0.012
    fr_x1 = X_FR1 - 0.01
    fr_y1 = Y_N - 0.004
    fr_y0 = fr_y1 - 30 * IN
    fr_z1 = 67 * IN
    split_z = fr_z1 * 0.68
    fridge_parts = [
        ((fr_x0, fr_y0, 0.0), (fr_x1, fr_y1, fr_z1), fridge_mat),
        ((fr_x0 + 0.02, fr_y0 - 0.008, split_z - 0.008), (fr_x1 - 0.02, fr_y0, split_z + 0.008), dark_mat),
        # Vertical handles on the west edge of each door.
        ((fr_x0 + 0.03, fr_y0 - 0.02, split_z + 0.08), (fr_x0 + 0.05, fr_y0 - 0.008, fr_z1 - 0.1), steel_mat),
        ((fr_x0 + 0.03, fr_y0 - 0.02, 0.18), (fr_x0 + 0.05, fr_y0 - 0.008, split_z - 0.1), steel_mat),
    ]
    build_object("Kitchen_Fridge", fridge_parts)

    # --- Baseboard ---
    trim_parts = []
    base_y_face(trim_parts, -HX, HX, Y_S, True, trim_mat)
    base_x_face(trim_parts, Y_S + BASE_T, Y_SPLIT - 0.002, -HX, True, trim_mat)
    base_x_face(trim_parts, half_y1 + 0.002, Y_N - BASE_T, -HX, True, trim_mat)
    base_x_face(trim_parts, Y_S + BASE_T, Y_SPLIT - 0.002, HX, False, trim_mat)
    # North wall beside the entry door, hall side only. Kitchen base is hidden by appliances.
    base_y_face(trim_parts, X_H0 + 0.002, door_x0 - casing - 0.004, Y_N, False, trim_mat)
    base_y_face(trim_parts, door_x1 + casing + 0.004, X_C0 - 0.002, Y_N, False, trim_mat)
    # Half wall, both faces, and the pier faces that meet open floor.
    base_y_face(trim_parts, X_K0, X_K1, half_y0, False, trim_mat)
    base_y_face(trim_parts, X_K0 + BASE_T, X_K1, half_y1, True, trim_mat)
    base_y_face(trim_parts, X_P0, X_P1, Y_SPLIT, False, trim_mat)
    base_x_face(trim_parts, Y_SPLIT + BASE_T, Y_N - BASE_T, X_P1, True, trim_mat)
    base_x_face(trim_parts, half_y1, Y_N - BASE_T, X_P0, False, trim_mat)
    # Hall side of the closet wall, stopped clear of the bifold swing.
    base_x_face(trim_parts, Y_SPLIT + BASE_T, Y_N - BASE_T, X_C0, False, trim_mat)
    build_object("Baseboard", trim_parts)

    # Outlets on the long east living wall, plus a switch inside the hall.
    outlets = []
    for oy in (Y_SPLIT - 1.15, Y_SPLIT - 1.55):
        box(outlets, (HX - 0.012, oy - 0.034, 0.30), (HX + 0.002, oy + 0.034, 0.42), trim_mat)
        box(outlets, (HX - 0.018, oy - 0.012, 0.345), (HX - 0.012, oy + 0.012, 0.375), dark_mat)
    box(outlets, (X_P1 - 0.002, Y_SPLIT + 0.06, 1.12), (X_P1 + 0.008, Y_SPLIT + 0.13, 1.24), trim_mat)
    build_object("Outlets", outlets)

    # Dome lights. The hall one matches the listing photo; the living room gets one too.
    build_dome("Light_Dome_Hall", ((X_H0 + X_C0) / 2, Y_SPLIT + SERVICE_D * 0.42), 0.18, trim_mat, glow_mat)
    y_liv = (Y_S + Y_SPLIT) / 2
    build_dome("Light_Dome_Living", (0.05, y_liv + 1.05), 0.19, trim_mat, glow_mat)

    # Anchors. Yaw is degrees about Z. Furniture front is local -Y.
    # yaw 90 faces +X, yaw 180 faces +Y, yaw 270 faces -X.
    sofa_x = -HX + 0.08 + (36 * IN) / 2
    anchors = [
        (
            "Sofa_spot",
            (sofa_x, y_liv, 0.0),
            90,
            "Against the west wall for a sofa about 36 in deep. Yaw 90 so the front faces the east TV wall.",
        ),
        (
            "TV_wall",
            (HX - 0.10, y_liv, 0.0),
            270,
            "Floor anchor on the blank east wall. Yaw 270 so the screen faces -X into the room. Raise Z to wall-mount.",
        ),
        (
            "Rug_center",
            (-0.10, y_liv, 0.0),
            0,
            "Center of an area rug between the sofa and the TV. Yaw 0 keeps an 8x10 rug's long side along the room.",
        ),
        (
            "Coffee_spot",
            (0.20, y_liv, 0.0),
            0,
            "Coffee table between the sofa and the TV.",
        ),
        (
            "Plant_corner",
            (-HX + 0.42, Y_S + 0.48, 0.0),
            0,
            "Southwest corner, beside the window wall.",
        ),
        (
            "Lamp_corner",
            (HX - 0.42, Y_S + 0.50, 0.0),
            0,
            "Southeast corner, beside the window and clear of the TV.",
        ),
        (
            "Bar_spot",
            ((X_K0 + X_K1) / 2, Y_SPLIT - 0.48, 0.0),
            180,
            "Stool or small table in front of the granite pass-through. Yaw 180 faces the kitchen.",
        ),
    ]
    for name, loc, yaw, _note in anchors:
        add_empty(name, loc, yaw)

    bpy.context.view_layer.update()
    meshes = [
        obj
        for obj in scene.objects
        if obj.type == "MESH" and not obj.name.startswith("Render_")
    ]
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
        if abs(lo[i] - expected_lo[i]) > 0.004 or abs(hi[i] - expected_hi[i]) > 0.004:
            raise SystemExit(
                f"bbox mismatch axis {i}: got {(round(lo[i], 4), round(hi[i], 4))} "
                f"expected {(round(expected_lo[i], 4), round(expected_hi[i], 4))}"
            )
    if tris > 50000:
        raise SystemExit(f"triangle count {tris} exceeds 50000")

    def rnd(v):
        return [round(float(v[0]), 4), round(float(v[1]), 4), round(float(v[2]), 4)]

    def r(v):
        return round(float(v), 4)

    open_w = open_x1 - open_x0
    meta = {
        "id": "studio_pass_through",
        "name": "Studio with Pass-Through Kitchen",
        "description": (
            "Long narrow rental studio with a light oak floor, white walls, and an 8.5 ft flat ceiling. "
            "The open living floor is 12 by 18.5 ft. At the far end a half-wall pass-through opens to a "
            "compact kitchen nook (gray cabinets, granite ledge, white fridge, stainless range and microwave). "
            "Beside it a short hall leads to the entry door, with a louvered bifold closet facing the living room. "
            "The near wall is a wide window wall."
        ),
        "units": "meters",
        "up_axis": "Z",
        "origin": "interior floor center (0, 0, 0); floor top is Z=0",
        "interior_m": {
            "width_x": r(WIDTH_X),
            "depth_y": r(TOTAL_Y),
            "height_z": r(HEIGHT_Z),
            "living_depth_y": r(LIVING_D),
            "service_depth_y": r(SERVICE_D),
        },
        "interior_ft": {
            "width_x": WIDTH_FT,
            "depth_y": LIVING_FT + SERVICE_FT,
            "height_z": HEIGHT_FT,
            "living_depth_y": LIVING_FT,
            "service_depth_y": SERVICE_FT,
        },
        "ceiling_height_m": r(HEIGHT_Z),
        "ceiling_height_ft": HEIGHT_FT,
        "wall_thickness_m": WALL_T,
        "walls": {
            "Wall_N": "+Y end wall, entry door in the hall",
            "Wall_S": "-Y window wall",
            "Wall_E": "+X long wall",
            "Wall_W": "-X long wall",
            "Wall_Pier": "full-height pier between the kitchen pass-through and the hall",
            "Halfwall": "36.5 in pony wall under the kitchen pass-through",
        },
        "openings": {
            "window": {
                "object": "Window_S",
                "wall": "Wall_S",
                "width_m": r(WIN_W),
                "height_m": r(WIN_HEAD - WIN_SILL),
                "sill_z_m": r(WIN_SILL),
                "head_z_m": r(WIN_HEAD),
                "center_m": [0.0, r(Y_S - WALL_T / 2), r((WIN_SILL + WIN_HEAD) / 2)],
            },
            "door": {
                "object": "Door_Entry",
                "wall": "Wall_N",
                "width_in": 36,
                "height_in": 80,
                "width_m": r(DOOR_W),
                "height_m": r(DOOR_H),
                "center_m": [r(door_cx), r(Y_N + WALL_T / 2), r(DOOR_H / 2)],
            },
            "closet": {
                "object": "Closet_Doors",
                "wall": "south face of the closet, facing the living room",
                "width_m": r(open_w),
                "height_m": r(DOOR_H),
                "center_m": [r((open_x0 + open_x1) / 2), r(Y_SPLIT + 0.03), r(DOOR_H / 2)],
            },
            "pass_through": {
                "object": "Halfwall",
                "width_m": r(X_K1 - X_K0),
                "sill_z_m": r(BAR_H),
                "head_z_m": r(soffit_z),
                "height_m": r(soffit_z - BAR_H),
                "center_m": [r((X_K0 + X_K1) / 2), r(Y_SPLIT + 0.05), r((BAR_H + soffit_z) / 2)],
            },
        },
        "free_floor": {
            "type": "rect",
            "x_min": r(-HX),
            "x_max": r(HX),
            "y_min": r(Y_S),
            "y_max": r(Y_SPLIT),
            "note": (
                "Open living floor south of the pass-through, hall, and closet. "
                "Keep the hallway threshold clear: x from the pier to the closet "
                f"({r(X_H0)} to {r(X_C0)}), y within 0.85 m of Y={r(Y_SPLIT)}. "
                "The kitchen nook and entry hall are not furnishing floor."
            ),
        },
        "bbox_m": {"min": rnd(lo), "max": rnd(hi), "size": rnd(size)},
        "empties": {},
        "triangle_count": tris,
        "objects": [],
    }
    for name, loc, yaw, note in anchors:
        meta["empties"][name] = {
            "position_m": [r(loc[0]), r(loc[1]), r(loc[2])],
            "yaw_deg": yaw,
            "note": note,
        }
    meta["objects"] = [
        obj.name
        for obj in scene.objects
        if obj.type in {"MESH", "EMPTY"} and not obj.name.startswith("Render_")
    ]
    meta["objects"].sort()
    return meta


def add_camera_and_sun():
    scene = bpy.context.scene
    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens = 24
    cam_data.clip_start = 0.05
    cam_data.clip_end = 40
    cam = bpy.data.objects.new("Camera", cam_data)
    bpy.context.collection.objects.link(cam)
    # Interior camera near the window wall, left of center, looking toward the kitchen and hall.
    cam.location = (-0.42, Y_S + 0.70, 1.55)
    look_at(cam, Vector((0.02, Y_N - 0.45, 1.16)))
    scene.camera = cam

    sun_data = bpy.data.lights.new("Sun", "SUN")
    sun_data.energy = 1.8
    sun_data.color = (1.0, 0.97, 0.92)
    sun_data.angle = math.radians(6)
    sun = bpy.data.objects.new("Sun", sun_data)
    bpy.context.collection.objects.link(sun)
    sun.location = (0.4, Y_S - 1.5, 6.5)
    look_at(sun, Vector((0.2, 0.5, 1.0)))

    def area(name, loc, energy, size, rot):
        data = bpy.data.lights.new(name, "AREA")
        data.energy = energy
        data.shape = "RECTANGLE"
        data.size = size[0]
        data.size_y = size[1]
        obj = bpy.data.objects.new(name, data)
        bpy.context.collection.objects.link(obj)
        obj.location = loc
        obj.rotation_euler = rot
        return obj

    # Daylight just inside the south window, aimed north (+Y). Area lights emit along -Z.
    win = area("Window_Light", (0.0, Y_S + 0.2, (WIN_SILL + WIN_HEAD) / 2), 70, (2.6, 1.25), (math.radians(90), 0.0, 0.0))
    win.data.color = (1.0, 0.97, 0.92)
    area("Fill", (0.0, (Y_S + Y_SPLIT) / 2, HEIGHT_Z - 0.15), 10, (3.2, 3.2), (0.0, 0.0, 0.0))
    # Small upward light, inset from the walls so it brightens the ceiling without a shadow stripe.
    area("Ceiling_Fill", (0.0, (Y_S + Y_SPLIT) / 2, HEIGHT_Z - 0.45), 10, (1.6, 2.4), (math.pi, 0.0, 0.0))
    area("Kitchen_Fill", ((X_K0 + X_K1) / 2, (Y_SPLIT + Y_N) / 2, HEIGHT_Z - 0.25), 8, (1.1, 1.1), (0.0, 0.0, 0.0))
    area("Hall_Fill", ((X_H0 + X_C0) / 2, (Y_SPLIT + Y_N) / 2, HEIGHT_Z - 0.2), 6, (0.7, 1.1), (0.0, 0.0, 0.0))

    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.92, 0.94, 0.96, 1.0)
    bg.inputs["Strength"].default_value = 0.45
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.exposure = 0.12


def render_preview(path):
    scene = bpy.context.scene
    scene.render.resolution_x = 1024
    scene.render.resolution_y = 640
    scene.render.resolution_percentage = 100
    scene.render.filepath = path
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    # Near window wall stays in the glb. It sits behind this camera, so the shot matches the listing photo.
    hidden = []
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
        keep = obj.type in {"MESH", "EMPTY"} and not obj.name.startswith("Render_")
        obj.select_set(keep)
    bpy.ops.export_scene.gltf(
        filepath=glb,
        export_format="GLB",
        use_selection=True,
        export_apply=False,
        export_yup=True,
        export_materials="EXPORT",
        export_cameras=False,
        export_lights=False,
    )
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
        fh.write("\n")
    bpy.context.preferences.filepaths.save_version = 0
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
