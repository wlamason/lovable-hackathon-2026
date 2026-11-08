"""Glass wall garden room.

A bright modern living room. The long north wall is floor-to-ceiling glass
with thin wood mullions and a low wood bench. Dark-framed sliding glass doors
fill the west wall from the northwest corner. East and south walls are solid
white, with a 36 x 80 in entry door on the south wall.

Interior floor center is the world origin. Z is up. Floor top is Z=0.
Furniture front faces local -Y, so an anchor's yaw is the Z rotation to apply
when a furniture model is placed there.

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

# Interior: 20 ft wide (X) x 16 ft deep (Y) x 9.5 ft high.
WIDTH_X = 6.10
DEPTH_Y = 4.88
HEIGHT_Z = 2.90
WALL_T = 0.12
FLOOR_T = 0.04
CEIL_T = 0.04

DOOR_W = 36 * 0.0254  # 0.9144 m
DOOR_H = 80 * 0.0254  # 2.032 m
DOOR_MARGIN_E = 0.42

# North window wall. Glazing sits on the bench, head at the ceiling.
BENCH_H = 0.40
BENCH_D = 0.50
FRAME = 0.052
MULL_V = 0.040
MULL_H = 0.040
RAIL_B = 0.048
RAIL_T = 0.056
MULL_Z = 1.36
N_BAYS = 4

# West sliding doors, from the north corner southward. Three ~1.22 m panels.
SLIDE_SOLID = 1.22  # solid white wall remaining at the south end of Wall_W
SLIDE_FRAME = 0.058
N_SLIDES = 3

BASE_H = 0.09
BASE_T = 0.016

HX = WIDTH_X / 2
HY = DEPTH_Y / 2
SLIDE_Y0 = -HY + SLIDE_SOLID

# Preview camera, inside near the south wall, wide view of the garden wall.
CAM_LOC = (0.35, -2.05, 1.38)
CAM_TARGET = (-0.15, 1.7, 1.16)
CAM_LENS = 22


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
    if "Specular IOR Level" in bsdf.inputs and alpha < 0.999:
        bsdf.inputs["Specular IOR Level"].default_value = 0.45
    for key in ("Transmission Weight", "Transmission"):
        if transmission and key in bsdf.inputs:
            bsdf.inputs[key].default_value = transmission
            break
    if alpha < 0.999:
        if hasattr(mat, "surface_render_method"):
            mat.surface_render_method = "BLENDED"
        if hasattr(mat, "blend_method"):
            mat.blend_method = "BLEND"
        if hasattr(mat, "use_backface_culling"):
            mat.use_backface_culling = False
        if hasattr(mat, "show_transparent_back"):
            mat.show_transparent_back = True
    return mat


def add_box(bm, mn, mx, material_index):
    sx = mx[0] - mn[0]
    sy = mx[1] - mn[1]
    sz = mx[2] - mn[2]
    if sx <= 1e-6 or sy <= 1e-6 or sz <= 1e-6:
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


def x_members(start, end, frame, mull, bays):
    """Vertical frame members and the open bays between them."""
    clear0 = start + frame
    clear1 = end - frame
    bay = (clear1 - clear0 - mull * (bays - 1)) / bays
    solids = [(start, start + frame), (end - frame, end)]
    opens = []
    x = clear0
    for i in range(bays):
        opens.append((x, x + bay))
        x += bay
        if i < bays - 1:
            solids.append((x, x + mull))
            x += mull
    return solids, opens


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = "METERS"

    plank_mat = make_material("Floor_GrayWash", (0.72, 0.68, 0.62), roughness=0.4)
    gap_mat = make_material("Floor_Gap", (0.48, 0.46, 0.43), roughness=0.65)
    wall_mat = make_material("Wall_White", (0.97, 0.97, 0.96), roughness=0.72)
    ceil_mat = make_material("Ceiling_White", (0.99, 0.99, 0.98), roughness=0.78)
    trim_mat = make_material("Trim_White", (0.96, 0.96, 0.95), roughness=0.5)
    wood_mat = make_material("Wood_Oak", (0.60, 0.42, 0.24), roughness=0.46)
    wood_top = make_material("Wood_Oak_Top", (0.67, 0.49, 0.30), roughness=0.4)
    metal_mat = make_material("Frame_Dark", (0.16, 0.17, 0.18), roughness=0.32, metallic=0.62)
    handle_mat = make_material("Handle_Metal", (0.55, 0.56, 0.57), roughness=0.25, metallic=0.9)
    door_mat = make_material("Door_White", (0.93, 0.92, 0.90), roughness=0.48)
    glass_mat = make_material(
        "Glass",
        (0.78, 0.88, 0.86),
        roughness=0.04,
        alpha=0.14,
        transmission=0.55,
    )
    ground_mat = make_material("Garden_Ground", (0.45, 0.54, 0.34), roughness=0.9)
    shrub_a = make_material("Garden_Shrub", (0.50, 0.60, 0.44), roughness=0.85)
    shrub_b = make_material("Garden_Olive", (0.40, 0.50, 0.36), roughness=0.88)
    shrub_c = make_material("Garden_Tree", (0.30, 0.42, 0.30), roughness=0.9)

    # Subfloor covers the exterior footprint. Planks run toward the window (along Y).
    floor_parts = [
        (
            (-(HX + WALL_T), -(HY + WALL_T), -FLOOR_T),
            (HX + WALL_T, HY + WALL_T, -0.006),
            gap_mat,
        )
    ]
    plank_w = 0.14
    gap = 0.0035
    x = -HX
    while x < HX - 0.002:
        x1 = min(x + plank_w, HX)
        floor_parts.append(((x, -HY, -0.008), (x1, HY, 0.0), plank_mat))
        x = x1 + gap
    build_object("Floor", floor_parts)

    wall_z0 = -0.002
    wall_z1 = HEIGHT_Z + 0.002

    # East wall owns both east corners. Solid white, TV side.
    build_object(
        "Wall_E",
        [((HX, -(HY + WALL_T), wall_z0), (HX + WALL_T, HY + WALL_T, wall_z1), wall_mat)],
    )

    # West wall is solid only south of the sliding doors. It owns the SW corner.
    build_object(
        "Wall_W",
        [((-(HX + WALL_T), -(HY + WALL_T), wall_z0), (-HX, SLIDE_Y0, wall_z1), wall_mat)],
    )

    door_x1 = HX - DOOR_MARGIN_E
    door_x0 = door_x1 - DOOR_W
    south_y0 = -(HY + WALL_T)
    south_y1 = -HY
    build_object(
        "Wall_S",
        [
            ((-HX, south_y0, wall_z0), (door_x0, south_y1, wall_z1), wall_mat),
            ((door_x1, south_y0, wall_z0), (HX, south_y1, wall_z1), wall_mat),
            ((door_x0, south_y0, DOOR_H), (door_x1, south_y1, wall_z1), wall_mat),
        ],
    )

    build_object(
        "Ceiling",
        [((-HX, -HY, HEIGHT_Z), (HX, HY, HEIGHT_Z + CEIL_T), ceil_mat)],
    )

    # North window wall: wood knee under the bench line, then a 4 x 2 pane grid.
    win_y0 = HY
    win_y1 = HY + WALL_T
    glass_y0 = HY + WALL_T / 2 - 0.005
    glass_y1 = HY + WALL_T / 2 + 0.005
    x_solids, x_opens = x_members(-HX, HX, FRAME, MULL_V, N_BAYS)
    z_solids = [
        (BENCH_H, BENCH_H + RAIL_B),
        (MULL_Z - MULL_H / 2, MULL_Z + MULL_H / 2),
        (HEIGHT_Z - RAIL_T, HEIGHT_Z),
    ]
    z_opens = [
        (BENCH_H + RAIL_B, MULL_Z - MULL_H / 2),
        (MULL_Z + MULL_H / 2, HEIGHT_Z - RAIL_T),
    ]
    # Members meet at their edges. Overlapping boxes z-fight, so rails stop at the jambs
    # and the mid rail stops at each vertical mullion.
    window_parts = [
        ((-HX, win_y0, wall_z0), (HX, win_y1, BENCH_H + 0.002), wood_mat),
    ]
    for xa, xb in (x_solids[0], x_solids[-1]):
        window_parts.append(((xa, win_y0, BENCH_H), (xb, win_y1, HEIGHT_Z), wood_mat))
    # Bottom rail projects into the room so it sits on the bench with no gap.
    window_parts.append(
        ((-HX + FRAME, win_y0 - 0.016, BENCH_H - 0.006), (HX - FRAME, win_y1, BENCH_H + RAIL_B), wood_mat)
    )
    window_parts.append(
        ((-HX + FRAME, win_y0, HEIGHT_Z - RAIL_T), (HX - FRAME, win_y1, HEIGHT_Z), wood_mat)
    )
    for xa, xb in x_solids[1:-1]:
        window_parts.append(
            ((xa, win_y0, BENCH_H + RAIL_B), (xb, win_y1, HEIGHT_Z - RAIL_T), wood_mat)
        )
    for xa, xb in x_opens:
        za, zb = z_solids[1]
        window_parts.append(((xa, win_y0, za), (xb, win_y1, zb), wood_mat))
    build_object("Window_N", window_parts)

    glass_parts = []
    for xa, xb in x_opens:
        for za, zb in z_opens:
            glass_parts.append(
                ((xa + 0.004, glass_y0, za + 0.004), (xb - 0.004, glass_y1, zb - 0.004), glass_mat)
            )
    glass = build_object("Window_N_Glass", glass_parts)
    if hasattr(glass, "visible_shadow"):
        glass.visible_shadow = False

    # Interior bench ledge along the window. Top sits flush with the bottom rail.
    lip = 0.012
    bench_x0 = -HX + 0.02
    bench_x1 = HX - 0.02
    bench_y0 = HY - BENCH_D
    build_object(
        "Bench",
        [
            ((bench_x0, bench_y0, -0.002), (bench_x1, HY, BENCH_H - 0.028), wood_mat),
            (
                (bench_x0 - lip, bench_y0 - lip, BENCH_H - 0.028),
                (bench_x1 + lip, HY, BENCH_H),
                wood_top,
            ),
        ],
    )

    # Dark-framed sliding doors on the west wall, meeting the window at the NW corner.
    slide_x0 = -(HX + WALL_T)
    slide_x1 = -HX
    glass_x0 = -(HX + WALL_T / 2) - 0.005
    glass_x1 = -(HX + WALL_T / 2) + 0.005
    y_solids, y_opens = x_members(SLIDE_Y0, HY, SLIDE_FRAME, SLIDE_FRAME, N_SLIDES)
    slide_parts = []
    for ya, yb in (y_solids[0], y_solids[-1]):
        slide_parts.append(((slide_x0, ya, wall_z0), (slide_x1, yb, HEIGHT_Z), metal_mat))
    for ya, yb in y_solids[1:-1]:
        slide_parts.append(
            ((slide_x0, ya, 0.02), (slide_x1, yb, HEIGHT_Z - SLIDE_FRAME), metal_mat)
        )
    for ya, yb in y_opens:
        slide_parts.append(
            ((slide_x0, ya, HEIGHT_Z - SLIDE_FRAME), (slide_x1, yb, HEIGHT_Z), metal_mat)
        )
        slide_parts.append(((slide_x0, ya, 0.0), (slide_x1, yb, 0.022), metal_mat))
    # Floor track steps 16 mm into the room, buried 2 mm into the planks.
    slide_parts.append(
        ((slide_x1 - 0.002, SLIDE_Y0, -0.002), (slide_x1 + 0.016, HY, 0.014), metal_mat)
    )
    # Corner post wrapping the northwest corner so the dark frame turns the corner.
    slide_parts.append(((slide_x0, HY, wall_z0), (slide_x1, HY + WALL_T, HEIGHT_Z), metal_mat))
    # Pull handle on the south panel, interior face.
    handle_y0 = y_opens[0][0] + 0.07
    slide_parts.append(
        ((slide_x1, handle_y0, 0.92), (slide_x1 + 0.018, handle_y0 + 0.025, 1.22), handle_mat)
    )
    build_object("Door_Sliding", slide_parts)

    slide_glass = []
    for ya, yb in y_opens:
        slide_glass.append(
            (
                (glass_x0, ya + 0.006, 0.022 + 0.006),
                (glass_x1, yb - 0.006, HEIGHT_Z - SLIDE_FRAME - 0.006),
                glass_mat,
            )
        )
    sliding_glass = build_object("Door_Sliding_Glass", slide_glass)
    if hasattr(sliding_glass, "visible_shadow"):
        sliding_glass.visible_shadow = False

    # Entry door on the south wall, toward the east.
    slab_t = 0.035
    gap_d = 0.008
    slab_y0 = south_y0 + 0.028
    slab_y1 = slab_y0 + slab_t
    casing_w = 0.07
    casing_t = 0.016
    bite = 0.004
    build_object(
        "Door",
        [
            ((door_x0 + gap_d, slab_y0, 0.008), (door_x1 - gap_d, slab_y1, DOOR_H - gap_d), door_mat),
            (
                (door_x0 + 0.10, slab_y1, 0.16),
                (door_x1 - 0.10, slab_y1 + 0.008, 0.95),
                door_mat,
            ),
            (
                (door_x0 + 0.10, slab_y1, 1.08),
                (door_x1 - 0.10, slab_y1 + 0.008, DOOR_H - 0.12),
                door_mat,
            ),
            ((door_x0 - casing_w, -HY - bite, -bite), (door_x0, -HY + casing_t, DOOR_H + casing_w), trim_mat),
            ((door_x1, -HY - bite, -bite), (door_x1 + casing_w, -HY + casing_t, DOOR_H + casing_w), trim_mat),
            ((door_x0, -HY - bite, DOOR_H), (door_x1, -HY + casing_t, DOOR_H + casing_w), trim_mat),
            (
                (door_x0 + 0.06, slab_y1, 0.98),
                (door_x0 + 0.09, slab_y1 + 0.02, 1.05),
                handle_mat,
            ),
            (
                (door_x0 + 0.07, slab_y1 + 0.006, 1.005),
                (door_x0 + 0.18, slab_y1 + 0.016, 1.022),
                handle_mat,
            ),
        ],
    )

    # Baseboard on solid wall faces only. The bench and the sliders take the other walls.
    base_parts = [
        ((HX - BASE_T, -HY + 0.002, -bite), (HX + bite, HY - 0.002, BASE_H), trim_mat),
        ((-HX - bite, -HY + 0.002, -bite), (-HX + BASE_T, SLIDE_Y0 - 0.008, BASE_H), trim_mat),
        ((-HX, -HY - bite, -bite), (door_x0 - casing_w - 0.004, -HY + BASE_T, BASE_H), trim_mat),
        ((door_x1 + casing_w + 0.004, -HY - bite, -bite), (HX, -HY + BASE_T, BASE_H), trim_mat),
    ]
    build_object("Baseboard", base_parts)

    # Flat ground plus two hedge bands outside the glass. Boxes stay cheap and read as planting.
    outer_x = HX + WALL_T
    outer_y = HY + WALL_T
    garden_parts = [
        ((-outer_x - 4.0, outer_y + 0.02, -0.06), (outer_x + 1.5, outer_y + 6.0, -0.01), ground_mat),
        ((-outer_x - 5.0, -HY, -0.06), (-outer_x - 0.02, outer_y + 0.02, -0.01), ground_mat),
        # Low shrub line just outside the window, filling the lower panes.
        ((-HX - 0.2, outer_y + 0.2, -0.01), (HX + 0.2, outer_y + 1.35, 0.85), shrub_a),
        # Taller foliage screen behind it, filling the upper panes.
        ((-HX - 1.2, outer_y + 1.7, -0.01), (HX + 1.2, outer_y + 2.6, 3.5), shrub_c),
        ((-outer_x - 1.8, -0.4, -0.01), (-outer_x - 0.3, 2.3, 1.1), shrub_b),
        ((-outer_x - 2.6, 0.6, -0.01), (-outer_x - 0.55, 2.6, 3.2), shrub_c),
    ]
    build_object("Garden", garden_parts)

    anchors = [
        (
            "Sofa_spot",
            (0.20, -0.90, 0.0),
            180,
            "Sofa facing the garden window. Yaw 180 degrees so its front (local -Y) points +Y.",
        ),
        (
            "TV_wall",
            (HX - 0.16, -0.20, 0.0),
            -90,
            "Floor anchor on the solid east wall. Yaw -90 degrees so the screen front faces west into the room. Raise Z to wall-mount.",
        ),
        (
            "Rug_center",
            (0.20, -0.05, 0.0),
            0,
            "Center of the seating rug between the sofa and the coffee table.",
        ),
        (
            "Coffee_spot",
            (0.20, 0.65, 0.0),
            0,
            "Coffee table in front of the sofa, toward the garden window.",
        ),
        (
            "Plant_corner",
            (HX - 0.55, HY - BENCH_D - 0.42, 0.0),
            180,
            "Floor plant at the east end of the window bench, against the white wall.",
        ),
        (
            "Lamp_corner",
            (-HX + 0.48, -HY + 0.48, 0.0),
            45,
            "Corner lamp in the solid southwest corner, clear of the sliding doors.",
        ),
        (
            "Side_table",
            (1.70, -0.90, 0.0),
            0,
            "Side table off the east end of the sofa.",
        ),
    ]
    for name, loc, yaw, _note in anchors:
        add_empty(name, loc, yaw)

    meshes = [obj for obj in scene.objects if obj.type == "MESH"]
    lo, hi = world_bbox(meshes)
    size = hi - lo
    tris = triangle_count(meshes)
    shell_names = {
        "Floor",
        "Wall_E",
        "Wall_W",
        "Wall_S",
        "Ceiling",
        "Window_N",
        "Window_N_Glass",
        "Door_Sliding",
        "Door_Sliding_Glass",
        "Door",
        "Bench",
        "Baseboard",
    }
    shell = [obj for obj in meshes if obj.name in shell_names]
    slo, shi = world_bbox(shell)
    print(f"BBOX min {tuple(round(v, 4) for v in lo)}")
    print(f"BBOX max {tuple(round(v, 4) for v in hi)}")
    print(f"BBOX size {tuple(round(v, 4) for v in size)}")
    print(f"SHELL min {tuple(round(v, 4) for v in slo)} max {tuple(round(v, 4) for v in shi)}")
    print(f"TRIANGLES {tris}")

    expected_lo = Vector((-(HX + WALL_T), -(HY + WALL_T), -FLOOR_T))
    expected_hi = Vector((HX + WALL_T, HY + WALL_T, HEIGHT_Z + CEIL_T))
    # Garden sits outside the shell. The track and bench stay inside the footprint,
    # except the dark corner post which ends on the outer north face.
    for i, label in enumerate("xyz"):
        if slo[i] < expected_lo[i] - 0.004 or shi[i] > expected_hi[i] + 0.004:
            raise SystemExit(
                f"shell bbox outside footprint on {label}: got {(slo[i], shi[i])} expected {(expected_lo[i], expected_hi[i])}"
            )
    if tris > 50000:
        raise SystemExit(f"triangle count {tris} is over 50000")

    def rnd(v):
        return [round(float(v[0]), 4), round(float(v[1]), 4), round(float(v[2]), 4)]

    slide_width = HY - SLIDE_Y0
    free_y1 = round(HY - BENCH_D, 4)
    meta = {
        "id": "glass_garden_room",
        "name": "Glass Wall Garden Room",
        "description": (
            "Bright modern living room. The long north wall is floor-to-ceiling glass "
            "with thin wood mullions in a four-by-two grid and a low wood bench along its base. "
            "Dark-framed sliding glass doors fill the west wall from the northwest corner. "
            "The east and south walls are solid white, with a 36 by 80 in entry door on the south wall. "
            "Gray-washed wood plank floor and a flat white ceiling. A simple garden plane sits outside the glass."
        ),
        "units": "meters",
        "up_axis": "Z",
        "origin": "interior floor center (0, 0, 0); floor top is Z=0",
        "interior_m": {"width_x": WIDTH_X, "depth_y": DEPTH_Y, "height_z": HEIGHT_Z},
        "interior_ft": {
            "width_x": round(WIDTH_X / 0.3048, 2),
            "depth_y": round(DEPTH_Y / 0.3048, 2),
            "height_z": round(HEIGHT_Z / 0.3048, 2),
        },
        "ceiling_height_m": HEIGHT_Z,
        "ceiling_height_ft": round(HEIGHT_Z / 0.3048, 2),
        "wall_thickness_m": WALL_T,
        "walls": {
            "Window_N": "+Y long wall, floor-to-ceiling wood-mullion glass with bench",
            "Door_Sliding": "-X wall from the northwest corner, dark-framed sliding glass doors",
            "Wall_W": "-X solid white wall south of the sliding doors",
            "Wall_E": "+X solid white wall",
            "Wall_S": "-Y solid white wall, entry door",
        },
        "openings": {
            "window_north": {
                "object": "Window_N",
                "wall": "Window_N",
                "width_m": WIDTH_X,
                "height_m": round(HEIGHT_Z - BENCH_H, 4),
                "sill_z_m": BENCH_H,
                "bays_x": N_BAYS,
                "bays_z": 2,
                "center_m": [0.0, round(HY + WALL_T / 2, 4), round((BENCH_H + HEIGHT_Z) / 2, 4)],
                "note": "Wood mullions. Bottom rail rests on the bench. Glass continues to the ceiling.",
            },
            "door_sliding": {
                "object": "Door_Sliding",
                "wall": "Wall_W",
                "width_m": round(slide_width, 4),
                "height_m": HEIGHT_Z,
                "sill_z_m": 0.0,
                "panels": N_SLIDES,
                "center_m": [
                    round(-(HX + WALL_T / 2), 4),
                    round((SLIDE_Y0 + HY) / 2, 4),
                    round(HEIGHT_Z / 2, 4),
                ],
                "note": "Three floor-to-ceiling dark-gray framed panels meeting the window wall at the northwest corner.",
            },
            "door": {
                "object": "Door",
                "wall": "Wall_S",
                "width_in": 36,
                "height_in": 80,
                "width_m": round(DOOR_W, 4),
                "height_m": round(DOOR_H, 4),
                "center_m": [
                    round((door_x0 + door_x1) / 2, 4),
                    round(-HY - WALL_T / 2, 4),
                    round(DOOR_H / 2, 4),
                ],
            },
        },
        "free_floor": {
            "type": "rect",
            "description": (
                "Interior floor where furniture can sit. Excludes the north window bench. "
                "The south entry door and the west sliders are in the walls and do not reduce the floor."
            ),
            "min_m": [-HX, -HY],
            "max_m": [HX, free_y1],
        },
        "bbox_m": {"min": rnd(lo), "max": rnd(hi), "size": rnd(size)},
        "shell_bbox_m": {"min": rnd(slo), "max": rnd(shi), "size": rnd(shi - slo)},
        "empties": {},
        "triangle_count": tris,
        "objects": [obj.name for obj in scene.objects if obj.type in {"MESH", "EMPTY"}],
    }
    for name, loc, yaw, note in anchors:
        meta["empties"][name] = {
            "position_m": [round(loc[0], 4), round(loc[1], 4), round(loc[2], 4)],
            "yaw_deg": yaw,
            "rotation_z_deg": yaw,
            "note": note,
        }
    return meta


def add_camera_and_sun():
    scene = bpy.context.scene
    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens = CAM_LENS
    cam_data.clip_start = 0.05
    cam_data.clip_end = 80
    cam = bpy.data.objects.new("Camera", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = CAM_LOC
    look_at(cam, Vector(CAM_TARGET))
    scene.camera = cam

    sun_data = bpy.data.lights.new("Sun", "SUN")
    sun_data.energy = 3.6
    sun_data.angle = math.radians(2.4)
    sun = bpy.data.objects.new("Sun", sun_data)
    bpy.context.collection.objects.link(sun)
    # Daylight from the garden, falling across the floor toward the camera.
    sun.rotation_euler = Vector((-0.25, -1.0, -0.95)).to_track_quat("-Z", "Y").to_euler()

    fill_data = bpy.data.lights.new("Fill", "AREA")
    fill_data.energy = 16
    fill_data.size = 5.0
    fill = bpy.data.objects.new("Fill", fill_data)
    bpy.context.collection.objects.link(fill)
    fill.location = (0.2, 0.4, 2.55)
    fill.rotation_euler = (0.0, 0.0, 0.0)

    bounce_data = bpy.data.lights.new("Bounce", "AREA")
    bounce_data.energy = 12
    bounce_data.size = 3.0
    bounce = bpy.data.objects.new("Bounce", bounce_data)
    bpy.context.collection.objects.link(bounce)
    bounce.location = (0.0, -1.4, 1.8)
    bounce.rotation_euler = (math.radians(90), 0.0, 0.0)

    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.86, 0.89, 0.90, 1.0)
    bg.inputs["Strength"].default_value = 0.55
    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look = "Medium High Contrast"
    scene.view_settings.exposure = 0.25


def render_preview(path):
    scene = bpy.context.scene
    scene.render.resolution_x = 1024
    scene.render.resolution_y = 640
    scene.render.resolution_percentage = 100
    scene.render.filepath = path
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    # South wall is behind the camera. Hide it so a wide lens cannot clip it.
    # Ceiling stays in the shot; it matches the flat white ceiling in the reference.
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
