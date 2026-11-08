"""Template for an empty room shell. Copy this file to rooms/<slug>/build.py.

    blender -b --factory-startup --python build.py -- --outdir <dir>

Edit SPEC (interior size, openings, anchors, colors), then add the photo-specific
parts in build_room(). Conventions match the rooms merged on 8 Nov 2026:
interior floor center at the origin, floor top at Z=0, walls outside the
footprint, furniture front is local -Y, anchor yaw is degrees about Z.
Only bpy, bmesh, and mathutils.
"""

import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

INCH = 0.0254
TRI_BUDGET = 50000

# A 16 x 20 x 9 ft shell, the same interior as living_room_generic.
# Replace the numbers from the reference photo. Not a 1:1 copy of the photo.
SPEC = {
    "id": "room_template",
    "name": "Room template",
    "description": "Empty rectangular shell. Replace this with what the reference photo shows.",
    "width_m": 4.88,
    "depth_m": 6.10,
    "height_m": 2.74,
    "wall_t": 0.12,
    "floor_srgb": (0.62, 0.48, 0.32),
    "wall_srgb": (0.86, 0.85, 0.82),
    "trim_srgb": (0.75, 0.73, 0.68),
    "glass_srgb": (0.75, 0.84, 0.88),
}


def srgb_to_linear(rgb):
    def channel(value):
        if value <= 0.04045:
            return value / 12.92
        return ((value + 0.055) / 1.055) ** 2.4

    return tuple(channel(value) for value in rgb)


def parse_outdir():
    out = Path(__file__).resolve().parent
    if "--" in sys.argv:
        args = sys.argv[sys.argv.index("--") + 1 :]
        if "--outdir" in args:
            out = Path(args[args.index("--outdir") + 1]).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    return out


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = "METERS"
    return scene


def make_material(name, srgb, roughness, metallic=0.0, alpha=1.0, transmission=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*srgb_to_linear(srgb), 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if "Alpha" in bsdf.inputs:
        bsdf.inputs["Alpha"].default_value = alpha
    if alpha < 1.0:
        mat.blend_method = "BLEND"
    for key in ("Transmission Weight", "Transmission"):
        if transmission and key in bsdf.inputs:
            bsdf.inputs[key].default_value = transmission
            break
    return mat


def add_box(bm, mn, mx, material_index):
    x0, y0, z0 = mn
    x1, y1, z1 = mx
    if x1 - x0 <= 1e-6 or y1 - y0 <= 1e-6 or z1 - z0 <= 1e-6:
        return
    verts = [
        bm.verts.new(corner)
        for corner in (
            (x0, y0, z0),
            (x1, y0, z0),
            (x1, y1, z0),
            (x0, y1, z0),
            (x0, y0, z1),
            (x1, y0, z1),
            (x1, y1, z1),
            (x0, y1, z1),
        )
    ]
    for indices in (
        (0, 1, 2, 3),
        (4, 7, 6, 5),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (3, 7, 4, 0),
    ):
        face = bm.faces.new([verts[index] for index in indices])
        face.material_index = material_index


def build_object(name, builder, materials):
    bm = bmesh.new()
    builder(bm)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    for mat in materials:
        obj.data.materials.append(mat)
    return obj


def add_empty(name, location, yaw_deg):
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_type = "PLAIN_AXES"
    obj.empty_display_size = 0.35
    obj.location = location
    # Leave the empty unrotated. The app applies rotation_z_deg from metadata.
    # Rotating the empty as well turns the furniture twice.
    obj["yaw_deg"] = yaw_deg
    obj["rotation_z_deg"] = yaw_deg
    bpy.context.collection.objects.link(obj)
    return obj


def world_bbox(objects):
    minimum = Vector((1e9, 1e9, 1e9))
    maximum = Vector((-1e9, -1e9, -1e9))
    for obj in objects:
        for corner in obj.bound_box:
            world = obj.matrix_world @ Vector(corner)
            minimum = Vector(tuple(min(minimum[i], world[i]) for i in range(3)))
            maximum = Vector(tuple(max(maximum[i], world[i]) for i in range(3)))
    return minimum, maximum


def triangle_count(objects):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    total = 0
    for obj in objects:
        if obj.type != "MESH":
            continue
        mesh = obj.evaluated_get(depsgraph).to_mesh()
        mesh.calc_loop_triangles()
        total += len(mesh.loop_triangles)
        obj.evaluated_get(depsgraph).to_mesh_clear()
    return total


def build_room():
    width = SPEC["width_m"]
    depth = SPEC["depth_m"]
    height = SPEC["height_m"]
    wall = SPEC["wall_t"]
    hx = width / 2
    hy = depth / 2
    floor_mat = make_material("FloorWood", SPEC["floor_srgb"], 0.55)
    wall_mat = make_material("WallPaint", SPEC["wall_srgb"], 0.7)
    trim_mat = make_material("Trim", SPEC["trim_srgb"], 0.45)
    glass_mat = make_material("Glass", SPEC["glass_srgb"], 0.08, alpha=0.35, transmission=0.6)

    door_w = 36 * INCH
    door_h = 80 * INCH
    door_cx = hx - 0.55 - door_w / 2
    window_w = 1.50
    window_h = 1.20
    window_sill = 0.90

    def floor(bm):
        add_box(bm, (-hx, -hy, -0.04), (hx, hy, 0.0), 0)

    def ceiling(bm):
        add_box(bm, (-hx, -hy, height), (hx, hy, height + 0.04), 0)

    def wall_n(bm):
        add_box(bm, (-hx - wall, hy, 0.0), (hx + wall, hy + wall, height), 0)

    def wall_s(bm):
        # Opening for the door. The wall stays outside the interior footprint.
        x0 = -hx - wall
        x1 = hx + wall
        y0 = -hy - wall
        y1 = -hy
        left = door_cx - door_w / 2
        right = door_cx + door_w / 2
        add_box(bm, (x0, y0, 0.0), (left, y1, height), 0)
        add_box(bm, (right, y0, 0.0), (x1, y1, height), 0)
        add_box(bm, (left, y0, door_h), (right, y1, height), 0)

    def wall_w(bm):
        add_box(bm, (-hx - wall, -hy, 0.0), (-hx, hy, height), 0)

    def wall_e(bm):
        y0 = -window_w / 2
        y1 = window_w / 2
        z0 = window_sill
        z1 = window_sill + window_h
        add_box(bm, (hx, -hy, 0.0), (hx + wall, y0, height), 0)
        add_box(bm, (hx, y1, 0.0), (hx + wall, hy, height), 0)
        add_box(bm, (hx, y0, 0.0), (hx + wall, y1, z0), 0)
        add_box(bm, (hx, y0, z1), (hx + wall, y1, height), 0)

    def door(bm):
        add_box(
            bm,
            (door_cx - door_w / 2 + 0.02, -hy - wall + 0.02, 0.0),
            (door_cx + door_w / 2 - 0.02, -hy - 0.02, door_h - 0.02),
            0,
        )

    def window(bm):
        add_box(
            bm,
            (hx + wall * 0.35, -window_w / 2, window_sill),
            (hx + wall * 0.65, window_w / 2, window_sill + window_h),
            0,
        )

    def baseboard(bm):
        h = 0.09
        t = 0.016
        add_box(bm, (-hx, hy - t, 0.0), (hx, hy, h), 0)
        add_box(bm, (-hx, -hy, 0.0), (hx, -hy + t, h), 0)
        add_box(bm, (-hx, -hy, 0.0), (-hx + t, hy, h), 0)
        add_box(bm, (hx - t, -hy, 0.0), (hx, hy, h), 0)

    objects = [
        build_object("Floor", floor, [floor_mat]),
        build_object("Ceiling", ceiling, [wall_mat]),
        build_object("Wall_N", wall_n, [wall_mat]),
        build_object("Wall_S", wall_s, [wall_mat]),
        build_object("Wall_W", wall_w, [wall_mat]),
        build_object("Wall_E", wall_e, [wall_mat]),
        build_object("Door", door, [trim_mat]),
        build_object("Window", window, [glass_mat]),
        build_object("Baseboard", baseboard, [trim_mat]),
    ]

    # yaw 0 keeps the furniture front on -Y. yaw 180 turns it toward +Y.
    anchors = [
        ("TV_wall", (0.0, hy - 0.15, 0.0), 0, "Floor anchor on the north wall."),
        ("Sofa_spot", (0.0, -1.0, 0.0), 180, "Yaw 180 so the sofa front faces the TV wall."),
        ("Rug_center", (0.0, -0.10, 0.0), 0, "Center of the seating rug."),
        ("Coffee_spot", (0.0, 0.20, 0.0), 0, "Coffee table between the sofa and the TV."),
        ("Plant_corner", (-hx + 0.35, hy - 0.35, 0.0), 45, "Northwest corner."),
    ]
    for name, location, yaw, _note in anchors:
        add_empty(name, location, yaw)

    meshes = [obj for obj in objects if obj.type == "MESH"]
    minimum, maximum = world_bbox(meshes)
    size = maximum - minimum
    tris = triangle_count(meshes)
    print(f"bbox m: {size.x:.4f} x {size.y:.4f} x {size.z:.4f}")
    print(f"triangles: {tris}")
    if tris > TRI_BUDGET:
        raise SystemExit(f"triangle count {tris} exceeds {TRI_BUDGET}")

    def r(value):
        return round(float(value), 4)

    empties = {}
    for name, location, yaw, note in anchors:
        empties[name] = {
            "position_m": [r(location[0]), r(location[1]), r(location[2])],
            "yaw_deg": yaw,
            "rotation_z_deg": yaw,
            "note": note,
        }
    meta = {
        "id": SPEC["id"],
        "name": SPEC["name"],
        "description": SPEC["description"],
        "units": "meters",
        "up_axis": "Z",
        "origin": "interior floor center (0, 0, 0); floor top is Z=0",
        "furniture_front": "local -Y; rotation_z_deg is the yaw to apply",
        "interior_m": {"width_x": width, "depth_y": depth, "height_z": height},
        "interior_ft": {
            "width_x": round(width / 0.3048, 2),
            "depth_y": round(depth / 0.3048, 2),
            "height_z": round(height / 0.3048, 2),
        },
        "ceiling_height_m": height,
        "wall_thickness_m": wall,
        "openings": {
            "door": {
                "object": "Door",
                "wall": "Wall_S",
                "width_in": 36,
                "height_in": 80,
                "width_m": round(door_w, 4),
                "height_m": round(door_h, 4),
            },
            "window": {
                "object": "Window",
                "wall": "Wall_E",
                "width_m": window_w,
                "height_m": window_h,
                "sill_z_m": window_sill,
            },
        },
        "free_floor": {
            "type": "rect",
            "x_min": r(-hx + 0.15),
            "x_max": r(hx - 0.15),
            "y_min": r(-hy + 0.9),
            "y_max": r(hy - 0.3),
            "note": "Seating floor. The south strip in front of the door is not free floor.",
        },
        "blocked": [
            {
                "name": "door_clearance",
                "note": "Keep about 0.9 m clear in front of the south door.",
                "rect_m": {"x_min": r(door_cx - door_w / 2), "x_max": r(door_cx + door_w / 2), "y_min": r(-hy), "y_max": r(-hy + 0.9)},
            }
        ],
        "bbox_m": {
            "min": [r(minimum.x), r(minimum.y), r(minimum.z)],
            "max": [r(maximum.x), r(maximum.y), r(maximum.z)],
            "size": [r(size.x), r(size.y), r(size.z)],
        },
        "empties": empties,
        "triangle_count": tris,
        "objects": [obj.name for obj in bpy.context.scene.objects if obj.type in {"MESH", "EMPTY"}],
    }
    return meta


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def render_preview(path):
    scene = bpy.context.scene
    scene.render.resolution_x = 1024
    scene.render.resolution_y = 640
    scene.render.resolution_percentage = 100
    scene.render.filepath = str(path)
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Standard"

    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.78, 0.82, 0.86, 1.0)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.45

    hy = SPEC["depth_m"] / 2
    camera_data = bpy.data.cameras.new("Camera")
    camera_data.lens = 28
    camera = bpy.data.objects.new("Camera", camera_data)
    # Just inside the south wall, matching a photo taken from that end of the room.
    camera.location = (0.4, -hy + 0.35, 1.45)
    bpy.context.collection.objects.link(camera)
    look_at(camera, (0.0, 0.4, 1.05))
    scene.camera = camera

    sun_data = bpy.data.lights.new("Sun", "SUN")
    sun_data.energy = 3.0
    sun = bpy.data.objects.new("Sun", sun_data)
    sun.rotation_euler = (math.radians(55), 0.0, math.radians(-40))
    bpy.context.collection.objects.link(sun)

    hidden = []
    for name in ("Ceiling", "Wall_S"):
        obj = bpy.data.objects[name]
        hidden.append(obj)
        obj.hide_render = True
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
        if hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
            scene.eevee.taa_render_samples = 16
        bpy.ops.render.render(write_still=True)
        print("RENDER engine BLENDER_EEVEE_NEXT")
    except Exception as exc:
        print("EEVEE failed:", exc)
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.display.shading.light = "STUDIO"
        scene.display.shading.color_type = "MATERIAL"
        bpy.ops.render.render(write_still=True)
        print("RENDER engine BLENDER_WORKBENCH")
    for obj in hidden:
        obj.hide_render = False


def main():
    outdir = parse_outdir()
    reset_scene()
    meta = build_room()
    (outdir / "metadata.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    readme = (
        f"# {SPEC['name']}\n\n"
        f"{SPEC['description']}\n\n"
        "The interior floor center is the origin and the floor top is Z=0. "
        "Walls stand outside that footprint. Furniture front faces local -Y.\n\n"
        f"![{SPEC['name']} preview](preview.png)\n\n"
        "Rebuild from this folder:\n\n"
        "```bash\n"
        "blender -b --factory-startup --python build.py -- --outdir .\n"
        "```\n"
    )
    (outdir / "README.md").write_text(readme, encoding="utf-8")

    preview = outdir / "preview.png"
    render_preview(preview)

    for obj in bpy.context.view_layer.objects:
        obj.select_set(obj.type in {"MESH", "EMPTY"})
    bpy.ops.export_scene.gltf(
        filepath=str(outdir / "model.glb"),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_materials="EXPORT",
        export_cameras=False,
        export_lights=False,
    )
    blend_path = outdir / "model.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    for backup in outdir.glob("*.blend1"):
        backup.unlink()
    print("WROTE", outdir / "model.glb")
    print("WROTE", blend_path)
    print("WROTE", preview)
    print("WROTE", outdir / "metadata.json")


if __name__ == "__main__":
    main()
