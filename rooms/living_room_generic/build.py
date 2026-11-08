"""Generic living room level.

Interior floor center is the world origin. Z is up. Furniture whose origin is
the bottom center of its footprint sits on the floor at Z=0.

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

# Interior: 16 ft x 20 ft x 9 ft, stated in meters.
WIDTH_X = 4.88
DEPTH_Y = 6.10
HEIGHT_Z = 2.74
WALL_T = 0.12
FLOOR_T = 0.04
CEIL_T = 0.04

DOOR_W = 36 * 0.0254  # 0.9144 m
DOOR_H = 80 * 0.0254  # 2.032 m
# Door sits on the south (short) wall, toward the east side.
DOOR_MARGIN_E = 0.55

WINDOW_W = 1.50  # along Y, centered on the east (long) wall
WINDOW_H = 1.20
WINDOW_SILL = 0.90
FRAME = 0.05

BASE_H = 0.089
BASE_T = 0.016

HX = WIDTH_X / 2
HY = DEPTH_Y / 2


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
    for key in ("Transmission Weight", "Transmission"):
        if transmission and key in bsdf.inputs:
            bsdf.inputs[key].default_value = transmission
            break
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


def build_object(name, parts, materials):
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


def add_empty(name, location):
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_type = "PLAIN_AXES"
    obj.empty_display_size = 0.3
    obj.location = location
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

    floor_mat = make_material("Floor_Wood", (0.66, 0.48, 0.30), roughness=0.48)
    wall_mat = make_material("Wall_Paint", (0.93, 0.91, 0.87), roughness=0.7)
    ceil_mat = make_material("Ceiling_Paint", (0.97, 0.97, 0.96), roughness=0.75)
    trim_mat = make_material("Trim_Paint", (0.97, 0.96, 0.94), roughness=0.55)
    door_mat = make_material("Door_Paint", (0.86, 0.82, 0.74), roughness=0.48)
    frame_mat = make_material("Window_Frame", (0.95, 0.95, 0.93), roughness=0.4)
    glass_mat = make_material(
        "Window_Glass",
        (0.72, 0.84, 0.90),
        roughness=0.08,
        alpha=0.35,
        transmission=0.9,
    )
    metal_mat = make_material("Door_Metal", (0.45, 0.46, 0.48), roughness=0.28, metallic=0.85)

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
        [floor_mat],
    )

    # Walls embed 2 mm into the floor and ceiling so faces do not sit on the same plane.
    wall_z0 = -0.002
    wall_z1 = HEIGHT_Z + 0.002
    # North short wall, solid. East/west walls own the corner posts.
    build_object(
        "Wall_N",
        [((-HX, HY, wall_z0), (HX, HY + WALL_T, wall_z1), wall_mat)],
        [wall_mat],
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
        [wall_mat],
    )

    # West long wall, full exterior depth including both corners.
    build_object(
        "Wall_W",
        [((-(HX + WALL_T), -(HY + WALL_T), wall_z0), (-HX, HY + WALL_T, wall_z1), wall_mat)],
        [wall_mat],
    )

    win_y0 = -WINDOW_W / 2
    win_y1 = WINDOW_W / 2
    win_z0 = WINDOW_SILL
    win_z1 = WINDOW_SILL + WINDOW_H
    east_x0 = HX
    east_x1 = HX + WALL_T
    build_object(
        "Wall_E",
        [
            ((east_x0, -(HY + WALL_T), wall_z0), (east_x1, win_y0, wall_z1), wall_mat),
            ((east_x0, win_y1, wall_z0), (east_x1, HY + WALL_T, wall_z1), wall_mat),
            ((east_x0, win_y0, wall_z0), (east_x1, win_y1, win_z0), wall_mat),
            ((east_x0, win_y0, win_z1), (east_x1, win_y1, wall_z1), wall_mat),
        ],
        [wall_mat],
    )

    # Ceiling is its own object so a viewer can hide it.
    build_object(
        "Ceiling",
        [((-HX, -HY, HEIGHT_Z), (HX, HY, HEIGHT_Z + CEIL_T), ceil_mat)],
        [ceil_mat],
    )

    # Baseboard along the interior faces, broken for the doorway and its casing.
    casing_w = 0.07
    # Trim bites 4 mm into the walls so it does not z-fight the paint.
    bite = 0.004
    base_parts = [
        ((-HX, HY - BASE_T, -bite), (HX, HY + bite, BASE_H), trim_mat),
        ((-HX, -HY - bite, -bite), (door_x0 - casing_w - 0.001, -HY + BASE_T, BASE_H), trim_mat),
        ((door_x1 + casing_w + 0.001, -HY - bite, -bite), (HX, -HY + BASE_T, BASE_H), trim_mat),
        ((-HX - bite, -HY + BASE_T + 0.001, -bite), (-HX + BASE_T, HY - BASE_T - 0.001, BASE_H), trim_mat),
        ((HX - BASE_T, -HY + BASE_T + 0.001, -bite), (HX + bite, HY - BASE_T - 0.001, BASE_H), trim_mat),
    ]
    build_object("Baseboard", base_parts, [trim_mat])

    # Window: frame and glass occupy the rough opening; sill projects into the room.
    glass_t = 0.008
    glass_x = east_x0 + WALL_T / 2
    mullion = 0.025
    lip = 0.004
    window_parts = [
        ((east_x0, win_y0 - lip, win_z0 - lip), (east_x1, win_y1 + lip, win_z0 + FRAME), frame_mat),
        ((east_x0, win_y0 - lip, win_z1 - FRAME), (east_x1, win_y1 + lip, win_z1 + lip), frame_mat),
        ((east_x0, win_y0 - lip, win_z0 + FRAME), (east_x1, win_y0 + FRAME, win_z1 - FRAME), frame_mat),
        ((east_x0, win_y1 - FRAME, win_z0 + FRAME), (east_x1, win_y1 + lip, win_z1 - FRAME), frame_mat),
        (
            (east_x0, -mullion / 2, win_z0 + FRAME),
            (east_x1, mullion / 2, win_z1 - FRAME),
            frame_mat,
        ),
        (
            (glass_x - glass_t / 2, win_y0 + FRAME, win_z0 + FRAME),
            (glass_x + glass_t / 2, win_y1 - FRAME, win_z1 - FRAME),
            glass_mat,
        ),
        (
            (east_x0 - 0.035, win_y0 - 0.02, win_z0 - 0.02),
            (east_x0 + lip, win_y1 + 0.02, win_z0 + 0.012),
            frame_mat,
        ),
    ]
    build_object("Window", window_parts, [frame_mat, glass_mat])

    # Door slab set in the opening, interior casing, and a lever handle.
    slab_t = 0.035
    gap = 0.008
    slab_y0 = south_y0 + 0.025
    slab_y1 = slab_y0 + slab_t
    slab_x0 = door_x0 + gap
    slab_x1 = door_x1 - gap
    slab_z1 = DOOR_H - gap
    casing_t = 0.015
    door_parts = [
        ((slab_x0, slab_y0, 0.01), (slab_x1, slab_y1, slab_z1), door_mat),
        # Two raised panels on the interior face of the slab.
        (
            (slab_x0 + 0.09, slab_y1, 0.14),
            (slab_x1 - 0.09, slab_y1 + 0.008, 0.92),
            door_mat,
        ),
        (
            (slab_x0 + 0.09, slab_y1, 1.05),
            (slab_x1 - 0.09, slab_y1 + 0.008, slab_z1 - 0.09),
            door_mat,
        ),
        ((door_x0 - casing_w, -HY - bite, -bite), (door_x0, -HY + casing_t, DOOR_H + casing_w), trim_mat),
        ((door_x1, -HY - bite, -bite), (door_x1 + casing_w, -HY + casing_t, DOOR_H + casing_w), trim_mat),
        ((door_x0, -HY - bite, DOOR_H), (door_x1, -HY + casing_t, DOOR_H + casing_w), trim_mat),
        # Lever on the west stile, interior side.
        (
            (slab_x0 + 0.04, slab_y1, 0.98),
            (slab_x0 + 0.07, slab_y1 + 0.02, 1.04),
            metal_mat,
        ),
        (
            (slab_x0 + 0.055, slab_y1 + 0.006, 1.005),
            (slab_x0 + 0.15, slab_y1 + 0.016, 1.02),
            metal_mat,
        ),
    ]
    build_object("Door", door_parts, [door_mat, trim_mat, metal_mat])

    # Floor anchors. Sofa_spot assumes a 180 degree yaw so the front faces the TV wall.
    empties = {
        "TV_wall": (0.0, HY - 0.15, 0.0),
        "Sofa_spot": (0.0, -1.00, 0.0),
        "Rug_center": (0.0, -0.10, 0.0),
        "Coffee_spot": (0.0, 0.20, 0.0),
    }
    for name, loc in empties.items():
        add_empty(name, loc)

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
        if abs(lo[i] - expected_lo[i]) > 0.002 or abs(hi[i] - expected_hi[i]) > 0.002:
            raise SystemExit(
                f"bbox mismatch axis {i}: got {(lo[i], hi[i])} expected {(expected_lo[i], expected_hi[i])}"
            )

    def rnd(v):
        return [round(float(v[0]), 4), round(float(v[1]), 4), round(float(v[2]), 4)]

    meta = {
        "id": "living_room_generic",
        "name": "Generic Living Room",
        "units": "meters",
        "up_axis": "Z",
        "origin": "interior floor center (0, 0, 0); floor top is Z=0",
        "interior_m": {"width_x": WIDTH_X, "depth_y": DEPTH_Y, "height_z": HEIGHT_Z},
        "interior_ft": {
            "width_x": round(WIDTH_X / 0.3048, 2),
            "depth_y": round(DEPTH_Y / 0.3048, 2),
            "height_z": round(HEIGHT_Z / 0.3048, 2),
        },
        "wall_thickness_m": WALL_T,
        "walls": {
            "Wall_N": "+Y short wall",
            "Wall_S": "-Y short wall, doorway",
            "Wall_E": "+X long wall, window",
            "Wall_W": "-X long wall",
        },
        "openings": {
            "window": {
                "object": "Window",
                "wall": "Wall_E",
                "width_m": WINDOW_W,
                "height_m": WINDOW_H,
                "sill_z_m": WINDOW_SILL,
                "center_m": [round(HX + WALL_T / 2, 4), 0.0, round(WINDOW_SILL + WINDOW_H / 2, 4)],
            },
            "door": {
                "object": "Door",
                "wall": "Wall_S",
                "width_in": 36,
                "height_in": 80,
                "width_m": round(DOOR_W, 4),
                "height_m": round(DOOR_H, 4),
                "center_m": [round((door_x0 + door_x1) / 2, 4), round(-HY - WALL_T / 2, 4), round(DOOR_H / 2, 4)],
            },
        },
        "bbox_m": {"min": rnd(lo), "max": rnd(hi), "size": rnd(size)},
        "empties": {
            "TV_wall": {
                "position_m": [0.0, round(HY - 0.15, 4), 0.0],
                "note": "Floor anchor centered on the north wall. A floor-origin TV or console sits here; raise Z to mount the screen.",
            },
            "Sofa_spot": {
                "position_m": [0.0, -1.0, 0.0],
                "rotation_z_deg": 180,
                "note": "Floor anchor for a sofa. Yaw 180 degrees so its front (local -Y) faces TV_wall.",
            },
            "Rug_center": {
                "position_m": [0.0, -0.1, 0.0],
                "note": "Center of the seating rug, between the sofa and the coffee table.",
            },
            "Coffee_spot": {
                "position_m": [0.0, 0.2, 0.0],
                "note": "Floor anchor for a coffee table between the sofa and the TV wall.",
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
            "Window",
            "Door",
            "Baseboard",
            "TV_wall",
            "Sofa_spot",
            "Rug_center",
            "Coffee_spot",
        ],
    }
    return meta, door_x0, door_x1


def add_camera_and_sun():
    scene = bpy.context.scene
    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens = 32
    cam_data.clip_start = 0.05
    cam_data.clip_end = 80
    cam = bpy.data.objects.new("Camera", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = (-5.2, -4.6, 3.3)
    look_at(cam, Vector((0.5, 0.2, 0.85)))
    scene.camera = cam

    sun_data = bpy.data.lights.new("Sun", "SUN")
    sun_data.energy = 1.6
    sun_data.angle = math.radians(8)
    sun = bpy.data.objects.new("Sun", sun_data)
    bpy.context.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(52), math.radians(-8), math.radians(-55))

    fill_data = bpy.data.lights.new("Fill", "AREA")
    fill_data.energy = 18
    fill_data.size = 4.0
    fill = bpy.data.objects.new("Fill", fill_data)
    bpy.context.collection.objects.link(fill)
    fill.location = (0.0, -0.4, 2.45)
    fill.rotation_euler = (0.0, 0.0, 0.0)

    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.78, 0.82, 0.86, 1.0)
    bg.inputs["Strength"].default_value = 0.35
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.exposure = -0.15


def render_preview(path):
    scene = bpy.context.scene
    scene.render.resolution_x = 512
    scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    scene.render.filepath = path
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    hidden = []
    for name in ("Ceiling", "Wall_W"):
        obj = bpy.data.objects[name]
        hidden.append(obj)
        obj.hide_render = True
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
        if hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
            scene.eevee.taa_render_samples = 32
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
    meta, _, _ = build()
    add_camera_and_sun()
    export_assets(out, meta)


if __name__ == "__main__":
    main()
