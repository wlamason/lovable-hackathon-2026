"""Build catalog item F011 Soft Neutral Carpet 5x7 and export it.

Run:
    blender -b --factory-startup --python build.py -- --outdir <dir>

Units are meters. The rug sits on Z=0, centered on X/Y, front facing -Y.
"""

import argparse
import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector


INCH = 0.0254

WIDTH_IN = 60.0
DEPTH_IN = 84.0
HEIGHT_IN = 0.5
# Classic flat border, wide enough to read on a 5x7 rug.
BORDER_IN = 4.0
# Subtle rolled edge. Kept well under half the pile thickness.
BEVEL_M = 0.0032
BEVEL_SEGMENTS = 4

WIDTH_M = WIDTH_IN * INCH
DEPTH_M = DEPTH_IN * INCH
HEIGHT_M = HEIGHT_IN * INCH
BORDER_M = BORDER_IN * INCH

ITEM_ID = "F011"
ITEM_NAME = "Soft Neutral Carpet 5x7"


def srgb_to_linear(rgb):
    def channel(u):
        if u <= 0.04045:
            return u / 12.92
        return ((u + 0.055) / 1.055) ** 2.4

    return tuple(channel(c) for c in rgb)


def parse_args():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []
    parser = argparse.ArgumentParser(description="Build F011 Soft Neutral Carpet 5x7")
    parser.add_argument(
        "--outdir",
        default=os.path.dirname(os.path.abspath(__file__)),
        help="Directory for model.glb, model.blend, preview.png, and metadata.json",
    )
    return parser.parse_args(argv)


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = "METERS"


def make_material(name, base_srgb, roughness, sheen=0.35):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    color = srgb_to_linear(base_srgb) + (1.0,)
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.22
    elif "Specular" in bsdf.inputs:
        bsdf.inputs["Specular"].default_value = 0.22
    if "Sheen Weight" in bsdf.inputs:
        bsdf.inputs["Sheen Weight"].default_value = sheen
    elif "Sheen" in bsdf.inputs:
        bsdf.inputs["Sheen"].default_value = sheen
    if "Sheen Roughness" in bsdf.inputs:
        bsdf.inputs["Sheen Roughness"].default_value = 0.65
    return mat


def build_rug_mesh():
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for vert in bm.verts:
        vert.co.x *= WIDTH_M
        vert.co.y *= DEPTH_M
        vert.co.z = (vert.co.z + 0.5) * HEIGHT_M

    bm.normal_update()
    bm.faces.ensure_lookup_table()
    top = [face for face in bm.faces if face.normal.z > 0.99]
    if len(top) != 1:
        raise RuntimeError("expected a single top face before inset, got %d" % len(top))

    bmesh.ops.inset_region(
        bm,
        faces=top,
        thickness=BORDER_M,
        depth=0.0,
        use_even_offset=True,
    )

    bm.normal_update()
    bm.edges.ensure_lookup_table()
    sharp = [
        edge
        for edge in bm.edges
        if len(edge.link_faces) == 2 and edge.calc_face_angle(0.0) > math.radians(30.0)
    ]
    bmesh.ops.bevel(
        bm,
        geom=sharp,
        offset=BEVEL_M,
        offset_type="OFFSET",
        segments=BEVEL_SEGMENTS,
        profile=0.55,
        affect="EDGES",
        clamp_overlap=True,
    )

    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.normal_update()

    inner_hx = (WIDTH_M * 0.5) - BORDER_M
    inner_hy = (DEPTH_M * 0.5) - BORDER_M
    for face in bm.faces:
        center = face.calc_center_median()
        normal = face.normal
        if normal.z < -0.5 and center.z < HEIGHT_M * 0.4:
            face.material_index = 2
        elif (
            normal.z > 0.85
            and abs(center.x) < inner_hx - 0.001
            and abs(center.y) < inner_hy - 0.001
            and center.z > HEIGHT_M * 0.5
        ):
            face.material_index = 0
        else:
            face.material_index = 1
        face.smooth = True

    mesh = bpy.data.meshes.new(ITEM_ID)
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(make_material("F011_Field", (0.910, 0.863, 0.796), 0.93, 0.45))
    mesh.materials.append(make_material("F011_Border", (0.710, 0.655, 0.580), 0.94, 0.35))
    mesh.materials.append(make_material("F011_Backing", (0.545, 0.490, 0.420), 0.97, 0.05))
    return mesh


def world_bounds(obj):
    xs, ys, zs = [], [], []
    for corner in obj.bound_box:
        world = obj.matrix_world @ Vector(corner)
        xs.append(world.x)
        ys.append(world.y)
        zs.append(world.z)
    return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)


def fit_to_target(obj):
    """Scale about the footprint center so the box matches the spec exactly."""
    minx, maxx, miny, maxy, minz, maxz = world_bounds(obj)
    dims = Vector((maxx - minx, maxy - miny, maxz - minz))
    target = Vector((WIDTH_M, DEPTH_M, HEIGHT_M))
    if min(dims) <= 0:
        raise RuntimeError("degenerate rug bounds %s" % (dims,))
    scale = Vector((target.x / dims.x, target.y / dims.y, target.z / dims.z))
    obj.scale = scale
    bpy.context.view_layer.update()

    minx, maxx, miny, maxy, minz, maxz = world_bounds(obj)
    center = Vector(((minx + maxx) * 0.5, (miny + maxy) * 0.5, minz))
    obj.location -= center
    bpy.context.view_layer.update()

    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.context.view_layer.update()


def triangle_count(obj):
    obj.data.calc_loop_triangles()
    return len(obj.data.loop_triangles)


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def setup_preview(scene, rug):
    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes["Background"]
    background.inputs["Color"].default_value = (0.93, 0.91, 0.88, 1.0)
    background.inputs["Strength"].default_value = 0.55

    floor_mesh = bpy.data.meshes.new("PREVIEW_Floor")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=2.2)
    bm.to_mesh(floor_mesh)
    bm.free()
    floor = bpy.data.objects.new("PREVIEW_Floor", floor_mesh)
    scene.collection.objects.link(floor)
    floor.location = (0.0, 0.0, -0.001)
    floor_mat = make_material("PREVIEW_Floor", (0.82, 0.80, 0.77), 0.85, 0.0)
    floor.data.materials.append(floor_mat)

    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens = 42
    cam = bpy.data.objects.new("Camera", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.location = (1.05, -1.62, 1.22)
    look_at(cam, Vector((0.0, 0.05, 0.0)))

    def add_area(name, location, energy, size, color):
        light_data = bpy.data.lights.new(name, "AREA")
        light_data.energy = energy
        light_data.size = size
        light_data.color = color
        light = bpy.data.objects.new(name, light_data)
        scene.collection.objects.link(light)
        light.location = location
        look_at(light, Vector((0.0, 0.0, 0.0)))
        return light

    add_area("Key", (1.15, -1.35, 1.85), 280.0, 1.6, (1.0, 0.97, 0.93))
    add_area("Fill", (-1.45, -0.85, 1.15), 90.0, 2.2, (0.90, 0.93, 1.0))
    add_area("Rim", (-0.35, 1.55, 0.85), 55.0, 1.3, (1.0, 0.96, 0.90))

    scene.render.resolution_x = 512
    scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"

    engine = "BLENDER_WORKBENCH"
    for candidate in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = candidate
            engine = candidate
            break
        except TypeError:
            continue
    if engine.startswith("BLENDER_EEVEE"):
        if hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
            scene.eevee.taa_render_samples = 32
    else:
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.display.shading.light = "STUDIO"
        scene.display.shading.color_type = "MATERIAL"
    print("RENDER_ENGINE", scene.render.engine)
    return engine


def render_preview(scene, path, engine):
    scene.render.filepath = path
    try:
        bpy.ops.render.render(write_still=True)
    except Exception as exc:
        print("RENDER_FALLBACK", exc)
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.display.shading.light = "STUDIO"
        scene.display.shading.color_type = "MATERIAL"
        bpy.ops.render.render(write_still=True)
        engine = "BLENDER_WORKBENCH"
    if not os.path.isfile(path):
        raise RuntimeError("preview was not written")
    return engine


def export_glb(obj, path):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_materials="EXPORT",
    )


def measure_imported_glb(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=path)
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError("glb import produced no mesh")
    xs, ys, zs = [], [], []
    tris = 0
    for obj in meshes:
        bpy.context.view_layer.update()
        minx, maxx, miny, maxy, minz, maxz = world_bounds(obj)
        xs.extend((minx, maxx))
        ys.extend((miny, maxy))
        zs.extend((minz, maxz))
        obj.data.calc_loop_triangles()
        tris += len(obj.data.loop_triangles)
    return {
        "width": max(xs) - min(xs),
        "depth": max(ys) - min(ys),
        "height": max(zs) - min(zs),
        "min": [min(xs), min(ys), min(zs)],
        "max": [max(xs), max(ys), max(zs)],
        "triangles": tris,
    }


def main():
    args = parse_args()
    outdir = os.path.abspath(args.outdir)
    os.makedirs(outdir, exist_ok=True)

    clear_scene()
    scene = bpy.context.scene

    mesh = build_rug_mesh()
    rug = bpy.data.objects.new(ITEM_ID, mesh)
    scene.collection.objects.link(rug)
    bpy.context.view_layer.objects.active = rug
    rug.select_set(True)
    fit_to_target(rug)

    minx, maxx, miny, maxy, minz, maxz = world_bounds(rug)
    measured = {
        "width": maxx - minx,
        "depth": maxy - miny,
        "height": maxz - minz,
    }
    tris = triangle_count(rug)
    print("BBOX_M", measured)
    print("BBOX_ORIGIN_MIN", [minx, miny, minz])
    print("TRIANGLES", tris)

    targets = {"width": WIDTH_M, "depth": DEPTH_M, "height": HEIGHT_M}
    for axis, target in targets.items():
        error = abs(measured[axis] - target) / target
        if error > 0.02:
            raise RuntimeError("%s error %.4f exceeds 2%%" % (axis, error))
    if abs(minz) > 1e-5 or abs((minx + maxx) * 0.5) > 1e-5 or abs((miny + maxy) * 0.5) > 1e-5:
        raise RuntimeError("origin is not at the bottom center of the footprint")

    metadata = {
        "id": ITEM_ID,
        "name": ITEM_NAME,
        "category": "Carpet",
        "style": "Scandinavian",
        "room": "Living Room",
        "price_usd": 159,
        "dimensions_in": {"width": WIDTH_IN, "depth": DEPTH_IN, "height": HEIGHT_IN},
        "dimensions_m": {"width": WIDTH_M, "depth": DEPTH_M, "height": HEIGHT_M},
        "bounding_box_m": {
            "width": measured["width"],
            "depth": measured["depth"],
            "height": measured["height"],
            "min": [minx, miny, minz],
            "max": [maxx, maxy, maxz],
        },
        "triangle_count": tris,
    }

    engine = setup_preview(scene, rug)
    preview_path = os.path.join(outdir, "preview.png")
    render_preview(scene, preview_path, engine)

    glb_path = os.path.join(outdir, "model.glb")
    export_glb(rug, glb_path)

    blend_path = os.path.join(outdir, "model.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)

    imported = measure_imported_glb(glb_path)
    print("GLB_BBOX_M", {k: imported[k] for k in ("width", "depth", "height")})
    print("GLB_TRIANGLES", imported["triangles"])
    for axis in ("width", "depth", "height"):
        error = abs(imported[axis] - targets[axis]) / targets[axis]
        if error > 0.02:
            raise RuntimeError("exported %s error %.4f exceeds 2%%" % (axis, error))

    metadata["bounding_box_m"] = {
        "width": imported["width"],
        "depth": imported["depth"],
        "height": imported["height"],
        "min": imported["min"],
        "max": imported["max"],
    }
    metadata["triangle_count"] = imported["triangles"]
    metadata_path = os.path.join(outdir, "metadata.json")
    with open(metadata_path, "w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)
        handle.write("\n")

    print("WROTE", glb_path)
    print("WROTE", blend_path)
    print("WROTE", preview_path)
    print("WROTE", metadata_path)


if __name__ == "__main__":
    main()
