"""F008 Slate Nesting Tables.

Industrial living-room set: three slate tops on black metal frames, arranged
nested (smaller tables pulled forward under the larger ones). The nested set
fills 32 x 32 x 18 inches. Width is X, depth is Y, height is Z, front faces -Y,
origin at the bottom center of the footprint.

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

INCH = 0.0254

# Spec bounding box for the nested set.
SPEC_IN = (32.0, 32.0, 18.0)  # width, depth, height
TARGET = tuple(v * INCH for v in SPEC_IN)

# Each table: width, depth, height in inches. Tops are staggered in depth so
# every slab is visible, while the union stays inside the 32 x 32 footprint.
# Distances "from front" are along +Y from the front face of the bounding box.
TABLES = (
    # name, width, depth, height, from_front, top_t, leg, apron_h, overhang
    ("large", 32.0, 20.0, 18.0, 12.0, 0.70, 0.75, 0.80, 0.65),
    ("medium", 23.0, 16.0, 15.5, 6.0, 0.60, 0.625, 0.65, 0.55),
    ("small", 15.5, 13.5, 13.25, 0.0, 0.55, 0.50, 0.55, 0.45),
)


def parse_outdir():
    outdir = os.path.dirname(os.path.abspath(__file__))
    if "--" in sys.argv:
        args = sys.argv[sys.argv.index("--") + 1 :]
        if "--outdir" in args:
            idx = args.index("--outdir")
            if idx + 1 < len(args):
                outdir = os.path.abspath(args[idx + 1])
    os.makedirs(outdir, exist_ok=True)
    return outdir


def srgb_to_linear(c):
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def linear_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    rgb = tuple(int(hex_color[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    return tuple(srgb_to_linear(c) for c in rgb)


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (
        bpy.data.meshes,
        bpy.data.materials,
        bpy.data.lights,
        bpy.data.cameras,
    ):
        for block in list(datablocks):
            datablocks.remove(block)


def make_material(name, hex_color, metallic, roughness):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    color = linear_rgb(hex_color) + (1.0,)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.28 if metallic < 0.5 else 0.5
    # Viewport / Workbench color matches the shader base color.
    mat.diffuse_color = color
    mat.metallic = metallic
    mat.roughness = roughness
    return mat


def _mesh_from_bmesh(name, bm, mat):
    mesh = bpy.data.meshes.new(name + "_mesh")
    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    mesh.materials.append(mat)
    return obj


def create_box(name, center, size, mat, bevel=0.0):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    extent = max(v.co.x for v in bm.verts) - min(v.co.x for v in bm.verts)
    if extent <= 0:
        raise RuntimeError("create_cube returned an empty mesh")
    scale = (size[0] / extent, size[1] / extent, size[2] / extent)
    bmesh.ops.scale(bm, vec=scale, verts=bm.verts)
    if bevel > 0:
        bmesh.ops.bevel(
            bm,
            geom=list(bm.edges),
            offset=bevel,
            offset_type="OFFSET",
            segments=2 if bevel >= 0.001 else 1,
            profile=0.5,
            affect="EDGES",
            clamp_overlap=True,
        )
    bmesh.ops.translate(bm, vec=Vector(center), verts=bm.verts)
    return _mesh_from_bmesh(name, bm, mat)


def create_cylinder(name, center, radius, depth, mat, vertices=16):
    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=vertices,
        radius1=radius,
        radius2=radius,
        depth=depth,
    )
    bmesh.ops.translate(bm, vec=Vector(center), verts=bm.verts)
    return _mesh_from_bmesh(name, bm, mat)


def build_table(spec, slate, metal):
    name, width_in, depth_in, height_in, from_front_in, top_t_in, leg_in, apron_h_in, overhang_in = spec
    width = width_in * INCH
    depth = depth_in * INCH
    height = height_in * INCH
    top_t = top_t_in * INCH
    leg = leg_in * INCH
    apron_h = apron_h_in * INCH
    overhang = overhang_in * INCH
    apron_t = leg * 0.82

    # Footprint center. Front of the bbox is Y = -TARGET_D/2.
    center_x = 0.0
    front_y = -TARGET[1] / 2.0 + from_front_in * INCH
    center_y = front_y + depth / 2.0

    parts = []
    top_center_z = height - top_t / 2.0
    parts.append(
        create_box(
            f"{name}_top",
            (center_x, center_y, top_center_z),
            (width, depth, top_t),
            slate,
            bevel=0.0016,
        )
    )

    inset = overhang + leg / 2.0
    leg_dx = width / 2.0 - inset
    leg_dy = depth / 2.0 - inset
    glide_h = 0.004
    leg_h = height - top_t - glide_h
    leg_z = glide_h + leg_h / 2.0
    apron_z = height - top_t - apron_h / 2.0
    span_x = width - 2.0 * overhang - 2.0 * leg
    span_y = depth - 2.0 * overhang - 2.0 * leg

    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            x = center_x + sx * leg_dx
            y = center_y + sy * leg_dy
            parts.append(
                create_cylinder(
                    f"{name}_glide",
                    (x, y, glide_h / 2.0),
                    radius=leg * 0.62,
                    depth=glide_h,
                    mat=metal,
                )
            )
            parts.append(
                create_box(
                    f"{name}_leg",
                    (x, y, leg_z),
                    (leg, leg, leg_h),
                    metal,
                    bevel=min(0.0008, leg * 0.08),
                )
            )

    # Apron rails sit on the leg centerlines, just under the top.
    for sy in (-1.0, 1.0):
        parts.append(
            create_box(
                f"{name}_apron",
                (center_x, center_y + sy * leg_dy, apron_z),
                (span_x, apron_t, apron_h),
                metal,
                bevel=0.0005,
            )
        )
    for sx in (-1.0, 1.0):
        parts.append(
            create_box(
                f"{name}_apron",
                (center_x + sx * leg_dx, center_y, apron_z),
                (apron_t, span_y, apron_h),
                metal,
                bevel=0.0005,
            )
        )

    # Low back rail (does not block the table nested in front).
    rail_h = leg * 0.72
    rail_z = 0.028 + rail_h / 2.0
    parts.append(
        create_box(
            f"{name}_back_rail",
            (center_x, center_y + leg_dy, rail_z),
            (span_x, apron_t, rail_h),
            metal,
            bevel=0.0004,
        )
    )
    return parts


def assert_nesting_clearance():
    """Fail fast if a smaller top cannot physically slide under the next one."""
    parsed = []
    for spec in TABLES:
        name, w, d, h, front, top_t, leg, apron_h, overhang = spec
        parsed.append(
            {
                "name": name,
                "w": w,
                "d": d,
                "h": h,
                "front": front,
                "back": front + d,
                "top_t": top_t,
                "leg": leg,
                "apron_bottom": h - top_t - apron_h,
                "inner_half_w": w / 2.0 - overhang - leg,
            }
        )
    # Overall footprint uses the large table's width and the staggered depth.
    large, medium, small = parsed
    if abs(large["w"] - SPEC_IN[0]) > 1e-6:
        raise SystemExit("large table width must define the spec width")
    if abs(small["front"]) > 1e-6:
        raise SystemExit("small table must sit on the front of the bounding box")
    if abs(large["back"] - SPEC_IN[1]) > 1e-6:
        raise SystemExit("large table must sit on the back of the bounding box")
    for outer, inner in ((large, medium), (medium, small)):
        if inner["h"] >= outer["apron_bottom"] - 0.35:
            raise SystemExit(f"{inner['name']} is too tall to nest under {outer['name']}")
        if inner["w"] / 2.0 >= outer["inner_half_w"] - 0.4:
            raise SystemExit(f"{inner['name']} is too wide to pass between {outer['name']} legs")
        if inner["back"] <= outer["front"] + 2.0:
            raise SystemExit(f"{inner['name']} does not tuck under {outer['name']}")


def join_objects(objs, name):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objs:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name
    return obj


def world_bounds(obj):
    xs, ys, zs = [], [], []
    for corner in obj.bound_box:
        world = obj.matrix_world @ Vector(corner)
        xs.append(world.x)
        ys.append(world.y)
        zs.append(world.z)
    return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)


def apply_transforms(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)


def fit_bbox(obj, target):
    """Scale to the spec size and plant the origin on the bottom center."""
    apply_transforms(obj)
    bpy.context.view_layer.update()
    minx, maxx, miny, maxy, minz, maxz = world_bounds(obj)
    size = (maxx - minx, maxy - miny, maxz - minz)
    print(
        "bbox before fit (m): "
        f"W={size[0]:.6f} D={size[1]:.6f} H={size[2]:.6f}"
    )
    obj.scale = (target[0] / size[0], target[1] / size[1], target[2] / size[2])
    apply_transforms(obj)
    bpy.context.view_layer.update()
    minx, maxx, miny, maxy, minz, maxz = world_bounds(obj)
    obj.location = Vector((-(minx + maxx) / 2.0, -(miny + maxy) / 2.0, -minz))
    apply_transforms(obj)
    bpy.context.view_layer.update()
    # Origin is world zero; geometry now spans the centered footprint at Z=0.
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.context.scene.cursor.location = (0.0, 0.0, 0.0)
    bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
    return world_bounds(obj)


def shade_smooth(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(40))
    except Exception as exc:
        print("shade_smooth_by_angle unavailable:", exc)
        bpy.ops.object.shade_smooth()


def triangle_count(obj):
    obj.data.calc_loop_triangles()
    return len(obj.data.loop_triangles)


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def setup_preview(subject):
    scene = bpy.context.scene
    world = scene.world
    if world is None:
        world = bpy.data.worlds.new("World")
        scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = linear_rgb("#C8CCD0") + (1.0,)
    bg.inputs["Strength"].default_value = 0.35

    floor_mat = make_material("PreviewFloor", "#C5C8CC", metallic=0.0, roughness=0.85)
    floor = create_box(
        "PreviewFloor",
        (0.0, 0.0, -0.004),
        (6.0, 6.0, 0.004),
        floor_mat,
        bevel=0.0,
    )
    floor.hide_render = False

    # Front is -Y. Three-quarter view from the front-right.
    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens = 48
    cam_data.clip_start = 0.01
    cam_data.clip_end = 40
    cam = bpy.data.objects.new("Camera", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = (1.05, -1.28, 0.78)
    look_at(cam, (0.0, -0.02, 0.16))
    scene.camera = cam

    def add_area(name, location, energy, size, hex_color):
        light_data = bpy.data.lights.new(name, type="AREA")
        light_data.energy = energy
        light_data.size = size
        light_data.color = linear_rgb(hex_color)
        light = bpy.data.objects.new(name, light_data)
        bpy.context.scene.collection.objects.link(light)
        light.location = location
        look_at(light, (0.0, 0.0, 0.18))
        return light

    add_area("Key", (1.25, -1.15, 1.15), 55, 1.6, "#FFF6EC")
    add_area("Fill", (-1.25, -0.85, 0.7), 18, 1.8, "#E4ECF8")
    add_area("Rim", (-0.35, 1.15, 0.85), 14, 1.2, "#FFFFFF")

    sun_data = bpy.data.lights.new("Sun", type="SUN")
    sun_data.energy = 1.15
    sun_data.angle = math.radians(6)
    sun_data.color = linear_rgb("#FFF8F0")
    sun = bpy.data.objects.new("Sun", sun_data)
    bpy.context.scene.collection.objects.link(sun)
    sun.location = (0.8, -0.6, 2.0)
    look_at(sun, (0.0, 0.0, 0.1))

    scene.render.resolution_x = 512
    scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = 0.0
    return floor


def render_preview(scene, path):
    scene.render.filepath = path
    engine_items = {item.identifier for item in scene.render.bl_rna.properties["engine"].enum_items}
    print("render engines:", sorted(engine_items))
    for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "BLENDER_WORKBENCH"):
        if engine not in engine_items:
            continue
        scene.render.engine = engine
        if engine == "BLENDER_EEVEE_NEXT":
            eevee = scene.eevee
            if hasattr(eevee, "taa_render_samples"):
                eevee.taa_render_samples = 64
            if hasattr(eevee, "use_raytracing"):
                eevee.use_raytracing = False
        elif engine == "BLENDER_EEVEE":
            if hasattr(scene.eevee, "taa_render_samples"):
                scene.eevee.taa_render_samples = 24
        else:
            shading = scene.display.shading
            shading.light = "STUDIO"
            shading.color_type = "MATERIAL"
            shading.show_shadows = True
        try:
            bpy.ops.render.render(write_still=True)
            print("preview rendered with", engine)
            return engine
        except Exception as exc:
            print("render failed on", engine, exc)
    raise SystemExit("preview render failed")


def export_glb(obj, path):
    addon_utils = __import__("addon_utils")
    addon_utils.enable("io_scene_gltf2")
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_materials="EXPORT",
        export_cameras=False,
        export_lights=False,
    )


def write_metadata(path, bounds, tris):
    minx, maxx, miny, maxy, minz, maxz = bounds
    measured = {
        "width": maxx - minx,
        "depth": maxy - miny,
        "height": maxz - minz,
        "min": [minx, miny, minz],
        "max": [maxx, maxy, maxz],
    }
    payload = {
        "id": "F008",
        "name": "Slate Nesting Tables",
        "category": "Table",
        "style": "Industrial",
        "room": "Living Room",
        "price_usd": 189,
        "dimensions_in": {"width": SPEC_IN[0], "depth": SPEC_IN[1], "height": SPEC_IN[2]},
        "dimensions_m": {"width": TARGET[0], "depth": TARGET[1], "height": TARGET[2]},
        "bounding_box_m": measured,
        "triangle_count": tris,
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    print("measured bbox m:", measured)
    print("triangles:", tris)
    for axis, measured_v, target_v in (
        ("width", measured["width"], TARGET[0]),
        ("depth", measured["depth"], TARGET[1]),
        ("height", measured["height"], TARGET[2]),
    ):
        err = abs(measured_v - target_v) / target_v
        print(f"  {axis} error {err * 100:.4f}%")
        if err > 0.02:
            raise SystemExit(f"{axis} is outside the 2% tolerance")
    if abs(minz) > 1e-4 or abs((minx + maxx) / 2) > 1e-4 or abs((miny + maxy) / 2) > 1e-4:
        raise SystemExit("origin is not at the bottom center of the footprint")


def main():
    outdir = parse_outdir()
    assert_nesting_clearance()
    clear_scene()

    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = "METERS"

    # Honed slate is a dark cool gray; keep roughness high so the tops
    # do not blow out to white under the studio lights.
    slate = make_material("Slate", "#3A434A", metallic=0.0, roughness=0.72)
    metal = make_material("Black Metal", "#141518", metallic=1.0, roughness=0.38)

    parts = []
    for spec in TABLES:
        parts.extend(build_table(spec, slate, metal))

    table = join_objects(parts, "F008")
    shade_smooth(table)
    bounds = fit_bbox(table, TARGET)
    tris = triangle_count(table)
    print(
        "bbox after fit (m): "
        f"min=({bounds[0]:.6f}, {bounds[2]:.6f}, {bounds[4]:.6f}) "
        f"max=({bounds[1]:.6f}, {bounds[3]:.6f}, {bounds[5]:.6f})"
    )

    setup_preview(table)
    glb_path = os.path.join(outdir, "model.glb")
    export_glb(table, glb_path)
    write_metadata(os.path.join(outdir, "metadata.json"), bounds, tris)
    render_preview(scene, os.path.join(outdir, "preview.png"))
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(outdir, "model.blend"))
    print("wrote", outdir)


if __name__ == "__main__":
    main()
