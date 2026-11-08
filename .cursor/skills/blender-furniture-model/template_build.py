"""Template for one catalog furniture item. Copy this file to the item folder as build.py.

    blender -b --factory-startup --python build.py -- --outdir <dir>

Edit SPEC, then replace build_product() with the real mesh. Units, the 2%
bbox check, the glTF export, the 512 preview, and metadata.json match the
furniture merged on 8 Nov 2026. Only bpy, bmesh, and mathutils.

The material helper is named srgb_to_linear on purpose. db/build_db.py treats
those authored numbers as display sRGB when it builds swatch hex values.
"""

import json
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

# Catalog row. dimensions_m are inches times 0.0254. price_usd is the catalog price.
SPEC = {
    "id": "F000",
    "name": "Placeholder Box",
    "category": "Table",
    "style": "Minimal",
    "room": "Living Room",
    "price_usd": 1,
    "width_in": 18.0,
    "depth_in": 18.0,
    "height_in": 22.0,
    # Authored display sRGB. Do not pre-convert these.
    "body_srgb": (0.83, 0.76, 0.64),
    "trim_srgb": (0.22, 0.20, 0.18),
}

INCH = 0.0254
TOLERANCE = 0.02
TRI_BUDGET = 30000


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


def make_material(name, srgb, roughness, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    # Socket values are linear. The name srgb_to_linear tells the DB the tuple above is sRGB.
    bsdf.inputs["Base Color"].default_value = (*srgb_to_linear(srgb), 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return mat


def add_box(bm, mn, mx, material_index):
    x0, y0, z0 = mn
    x1, y1, z1 = mx
    if x1 <= x0 or y1 <= y0 or z1 <= z0:
        raise ValueError(f"degenerate box {mn} {mx}")
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
    # Outward winding. The -Y face is the front.
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
    return verts


def build_product():
    """Replace this with the real object. Keep the mesh inside SPEC's box.

    Width is X, depth is Y, height is Z. The front faces -Y. The origin is the
    bottom center, so the finished vertices should span
    x [-width/2, width/2], y [-depth/2, depth/2], z [0, height].
    """
    width = SPEC["width_in"] * INCH
    depth = SPEC["depth_in"] * INCH
    height = SPEC["height_in"] * INCH
    body = make_material(f"{SPEC['id']}_Body", SPEC["body_srgb"], 0.55)
    trim = make_material(f"{SPEC['id']}_Trim", SPEC["trim_srgb"], 0.35)
    bm = bmesh.new()
    add_box(bm, (-width / 2, -depth / 2, 0.0), (width / 2, depth / 2, height * 0.16), 1)
    add_box(
        bm,
        (-width / 2, -depth / 2, height * 0.16),
        (width / 2, depth / 2, height),
        0,
    )
    mesh = bpy.data.meshes.new(SPEC["id"])
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(SPEC["id"], mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(body)
    obj.data.materials.append(trim)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return obj


def world_bounds(obj):
    minimum = Vector((1e9, 1e9, 1e9))
    maximum = Vector((-1e9, -1e9, -1e9))
    for corner in obj.bound_box:
        world = obj.matrix_world @ Vector(corner)
        minimum = Vector(tuple(min(minimum[i], world[i]) for i in range(3)))
        maximum = Vector(tuple(max(maximum[i], world[i]) for i in range(3)))
    return minimum, maximum


def triangle_count(obj):
    mesh = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
    mesh.calc_loop_triangles()
    count = len(mesh.loop_triangles)
    obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh_clear()
    return count


def check_dimensions(size):
    expected = (
        SPEC["width_in"] * INCH,
        SPEC["depth_in"] * INCH,
        SPEC["height_in"] * INCH,
    )
    for label, got, target in zip(("width", "depth", "height"), size, expected):
        error = abs(got - target) / target
        print(f"{label}: {got:.6f} m (nominal {target:.6f}, error {error:.4%})")
        if error > TOLERANCE:
            raise SystemExit(f"{label} is outside the {TOLERANCE:.0%} tolerance")


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def setup_preview(target):
    scene = bpy.context.scene
    scene.render.resolution_x = 512
    scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "Standard"
    world = bpy.data.worlds.new("PreviewWorld")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.72, 0.73, 0.74, 1.0)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.4

    floor_mesh = bpy.data.meshes.new("PreviewFloor")
    floor_bm = bmesh.new()
    add_box(floor_bm, (-1.2, -1.2, -0.02), (1.2, 1.2, -0.001), 0)
    floor_bm.to_mesh(floor_mesh)
    floor_bm.free()
    floor = bpy.data.objects.new("PreviewFloor", floor_mesh)
    bpy.context.collection.objects.link(floor)
    floor.data.materials.append(make_material("PreviewFloor", (0.45, 0.44, 0.42), 0.9))

    camera_data = bpy.data.cameras.new("PreviewCamera")
    camera_data.lens = 50
    camera = bpy.data.objects.new("PreviewCamera", camera_data)
    camera.location = (0.55, -0.85, 0.62)
    bpy.context.collection.objects.link(camera)
    look_at(camera, target)
    scene.camera = camera

    light_data = bpy.data.lights.new("Key", "AREA")
    light_data.energy = 40
    light_data.size = 1.2
    light = bpy.data.objects.new("Key", light_data)
    light.location = (0.8, -0.9, 1.3)
    bpy.context.collection.objects.link(light)
    look_at(light, target)

    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
        if hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
            scene.eevee.taa_render_samples = 16
        print("RENDER engine BLENDER_EEVEE_NEXT")
    except (TypeError, ValueError) as exc:
        print("EEVEE failed:", exc)
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.display.shading.light = "STUDIO"
        scene.display.shading.color_type = "MATERIAL"
        print("RENDER engine BLENDER_WORKBENCH")


def export_glb(obj, path):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.gltf(
        filepath=str(path),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_materials="EXPORT",
    )


def main():
    outdir = parse_outdir()
    reset_scene()
    obj = build_product()
    minimum, maximum = world_bounds(obj)
    size = maximum - minimum
    tris = triangle_count(obj)
    print(f"bbox m: {size.x:.4f} x {size.y:.4f} x {size.z:.4f}")
    print(f"triangles: {tris}")
    check_dimensions((size.x, size.y, size.z))
    if tris > TRI_BUDGET:
        raise SystemExit(f"triangle count {tris} exceeds {TRI_BUDGET}")

    width = SPEC["width_in"] * INCH
    depth = SPEC["depth_in"] * INCH
    height = SPEC["height_in"] * INCH
    metadata = {
        "id": SPEC["id"],
        "name": SPEC["name"],
        "category": SPEC["category"],
        "style": SPEC["style"],
        "room": SPEC["room"],
        "price_usd": SPEC["price_usd"],
        "dimensions_in": {
            "width": SPEC["width_in"],
            "depth": SPEC["depth_in"],
            "height": SPEC["height_in"],
        },
        "dimensions_m": {"width": width, "depth": depth, "height": height},
        "bounding_box_m": {
            "min": {"x": round(minimum.x, 4), "y": round(minimum.y, 4), "z": round(minimum.z, 4)},
            "max": {"x": round(maximum.x, 4), "y": round(maximum.y, 4), "z": round(maximum.z, 4)},
            "width": round(size.x, 4),
            "depth": round(size.y, 4),
            "height": round(size.z, 4),
        },
        "triangle_count": tris,
    }
    (outdir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    readme = (
        f"# {SPEC['id']} {SPEC['name']}\n\n"
        f"Replace this paragraph with what the object is and which catalog proportions it uses.\n\n"
        f"![{SPEC['name']} preview](preview.png)\n\n"
        "Rebuild from this folder:\n\n"
        "```bash\n"
        "blender -b --factory-startup --python build.py -- --outdir .\n"
        "```\n"
    )
    (outdir / "README.md").write_text(readme, encoding="utf-8")

    glb_path = outdir / "model.glb"
    export_glb(obj, glb_path)

    setup_preview((0.0, 0.0, height * 0.45))
    preview_path = outdir / "preview.png"
    bpy.context.scene.render.filepath = str(preview_path)
    bpy.ops.render.render(write_still=True)

    blend_path = outdir / "model.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    # A second save writes model.blend1 beside the scene. Never commit it.
    for backup in outdir.glob("*.blend1"):
        backup.unlink()
    print("WROTE", glb_path)
    print("WROTE", blend_path)
    print("WROTE", preview_path)
    print("WROTE", outdir / "metadata.json")


if __name__ == "__main__":
    main()
