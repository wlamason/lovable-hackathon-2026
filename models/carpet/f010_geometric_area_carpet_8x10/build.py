#!/usr/bin/env python3
"""Build catalog item F010 Geometric Area Carpet 8x10.

Headless:
    blender -b --factory-startup --python build.py -- --outdir <dir>

Default outdir is this script's folder. Uses only bpy/bmesh/mathutils.
"""

import math
import os
import sys

import addon_utils
import bmesh
import bpy
from mathutils import Vector

INCH = 0.0254
WIDTH_IN = 96.0
DEPTH_IN = 120.0
HEIGHT_IN = 0.5
WIDTH = WIDTH_IN * INCH
DEPTH = DEPTH_IN * INCH
HEIGHT = HEIGHT_IN * INCH

# One cell per inch so the diamond lattice lands on the grid.
COLS = 96
ROWS = 120
BORDER_CELLS = 3  # 3 in charcoal binding
ACCENT_CELLS = 1  # 1 in brass pinstripe inside the binding
BEVEL = 0.006  # slight plan inset of the top perimeter (meters)
BEVEL_Z = 0.62  # top perimeter sits a bit below the pile surface

DIAMONDS_X = 4
DIAMONDS_Y = 5

# Material slot order. Face indices point into this list.
MAT_FIELD = 0
MAT_BORDER = 1
MAT_ACCENT = 2
MAT_OUTLINE = 3
MAT_TEAL_CORE = 4
MAT_TEAL_MID = 5
MAT_RUST_CORE = 6
MAT_RUST_MID = 7
MAT_BACKING = 8


def srgb_to_linear(c):
    def channel(u):
        if u <= 0.04045:
            return u / 12.92
        return ((u + 0.055) / 1.055) ** 2.4

    return tuple(channel(x) for x in c)


def script_dir():
    return os.path.dirname(os.path.abspath(__file__))


def parse_outdir():
    out = script_dir()
    if "--" in sys.argv:
        args = sys.argv[sys.argv.index("--") + 1 :]
        if "--outdir" in args:
            out = args[args.index("--outdir") + 1]
    return os.path.abspath(out)


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = "METERS"


def enable_gltf():
    addon_utils.enable("io_scene_gltf2", default_set=False, persistent=False)


def make_material(name, srgb, roughness):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = (*srgb_to_linear(srgb), 1.0)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*srgb_to_linear(srgb), 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.22
    if "Metallic" in bsdf.inputs:
        bsdf.inputs["Metallic"].default_value = 0.0
    return mat


def build_materials():
    specs = [
        ("F010_Field", (0.902, 0.878, 0.831), 0.92),
        ("F010_Border", (0.165, 0.161, 0.149), 0.88),
        ("F010_Accent", (0.690, 0.537, 0.345), 0.84),
        ("F010_Outline", (0.204, 0.196, 0.180), 0.90),
        ("F010_TealCore", (0.110, 0.298, 0.290), 0.90),
        ("F010_TealMid", (0.478, 0.620, 0.588), 0.90),
        ("F010_RustCore", (0.549, 0.243, 0.184), 0.90),
        ("F010_RustMid", (0.769, 0.541, 0.416), 0.90),
        ("F010_Backing", (0.227, 0.204, 0.173), 0.95),
    ]
    return [make_material(n, c, r) for n, c, r in specs]


def face_material(i, j):
    """Material index for the top quad whose lower-left cell is (i, j)."""
    dist = min(i, j, COLS - 1 - i, ROWS - 1 - j)
    if dist < BORDER_CELLS:
        return MAT_BORDER
    if dist < BORDER_CELLS + ACCENT_CELLS:
        return MAT_ACCENT

    inset = BORDER_CELLS + ACCENT_CELLS
    ii = i - inset
    jj = j - inset
    inner_cols = COLS - 2 * inset
    inner_rows = ROWS - 2 * inset
    u = (ii + 0.5) / inner_cols
    v = (jj + 0.5) / inner_rows
    cell_x = min(int(u * DIAMONDS_X), DIAMONDS_X - 1)
    cell_y = min(int(v * DIAMONDS_Y), DIAMONDS_Y - 1)
    fx = (u * DIAMONDS_X) % 1.0
    fy = (v * DIAMONDS_Y) % 1.0
    manh = abs(fx - 0.5) + abs(fy - 0.5)
    even = ((cell_x + cell_y) % 2) == 0
    if manh < 0.20:
        return MAT_TEAL_CORE if even else MAT_RUST_CORE
    if manh < 0.38:
        return MAT_TEAL_MID if even else MAT_RUST_MID
    if manh < 0.48:
        return MAT_OUTLINE
    return MAT_FIELD


def grid_xy(i, j, inset):
    x = -WIDTH / 2.0 + (i / COLS) * WIDTH
    y = -DEPTH / 2.0 + (j / ROWS) * DEPTH
    if inset:
        if i == 0:
            x += BEVEL
        elif i == COLS:
            x -= BEVEL
        if j == 0:
            y += BEVEL
        elif j == ROWS:
            y -= BEVEL
    return x, y


def perimeter(cols, rows):
    pts = []
    for i in range(cols + 1):
        pts.append((i, 0))
    for j in range(1, rows + 1):
        pts.append((cols, j))
    for i in range(cols - 1, -1, -1):
        pts.append((i, rows))
    for j in range(rows - 1, 0, -1):
        pts.append((0, j))
    return pts


def build_mesh(materials):
    bm = bmesh.new()
    top = {}
    for j in range(ROWS + 1):
        for i in range(COLS + 1):
            x, y = grid_xy(i, j, inset=True)
            on_rim = i == 0 or i == COLS or j == 0 or j == ROWS
            z = HEIGHT * BEVEL_Z if on_rim else HEIGHT
            top[(i, j)] = bm.verts.new((x, y, z))

    for j in range(ROWS):
        for i in range(COLS):
            verts = [top[(i, j)], top[(i + 1, j)], top[(i + 1, j + 1)], top[(i, j + 1)]]
            face = bm.faces.new(verts)
            face.material_index = face_material(i, j)
            face.smooth = True

    loop = perimeter(COLS, ROWS)
    bot = {}
    for i, j in loop:
        x, y = grid_xy(i, j, inset=False)
        bot[(i, j)] = bm.verts.new((x, y, 0.0))

    for k in range(len(loop)):
        a = loop[k]
        b = loop[(k + 1) % len(loop)]
        face = bm.faces.new([top[a], bot[a], bot[b], top[b]])
        face.material_index = MAT_BORDER
        face.smooth = True

    bottom = bm.faces.new([bot[ij] for ij in reversed(loop)])
    bottom.material_index = MAT_BACKING
    bottom.smooth = True

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for edge in bm.edges:
        angle = edge.calc_face_angle(0.0)
        edge.smooth = angle < math.radians(35.0)

    mesh = bpy.data.meshes.new("F010")
    for mat in materials:
        mesh.materials.append(mat)
    bm.to_mesh(mesh)
    bm.free()
    mesh.validate(verbose=False)
    mesh.update()

    obj = bpy.data.objects.new("F010", mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    obj["item_id"] = "F010"
    return obj


def world_bbox(obj):
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    xs = [v.x for v in corners]
    ys = [v.y for v in corners]
    zs = [v.z for v in corners]
    return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)


def triangle_count(obj):
    mesh = obj.data
    mesh.calc_loop_triangles()
    return len(mesh.loop_triangles)


def assert_dimensions(obj):
    min_x, max_x, min_y, max_y, min_z, max_z = world_bbox(obj)
    size = (max_x - min_x, max_y - min_y, max_z - min_z)
    targets = (WIDTH, DEPTH, HEIGHT)
    labels = ("width", "depth", "height")
    print(
        "F010 bbox m: width={:.6f} depth={:.6f} height={:.6f} "
        "min=({:.6f},{:.6f},{:.6f}) max=({:.6f},{:.6f},{:.6f}) tris={}".format(
            size[0],
            size[1],
            size[2],
            min_x,
            min_y,
            min_z,
            max_x,
            max_y,
            max_z,
            triangle_count(obj),
        )
    )
    for label, measured, target in zip(labels, size, targets):
        err = abs(measured - target) / target
        if err > 0.02:
            raise SystemExit(
                f"{label} {measured:.6f} m is {err:.2%} off target {target:.6f} m"
            )
    if abs(min_z) > 1e-5:
        raise SystemExit(f"origin Z not on the floor: min_z={min_z}")
    if abs((min_x + max_x) / 2.0) > 1e-4 or abs((min_y + max_y) / 2.0) > 1e-4:
        raise SystemExit("footprint is not centered on the origin")
    return size, (min_x, min_y, min_z), (max_x, max_y, max_z)


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_preview_rig():
    scene = bpy.context.scene

    world = bpy.data.worlds.new("F010_World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (*srgb_to_linear((0.78, 0.78, 0.77)), 1.0)
    bg.inputs["Strength"].default_value = 0.85

    sun_data = bpy.data.lights.new("F010_Key", "SUN")
    sun_data.energy = 3.5
    sun_data.angle = math.radians(8.0)
    sun = bpy.data.objects.new("F010_Key", sun_data)
    scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(52.0), math.radians(-8.0), math.radians(28.0))

    fill_data = bpy.data.lights.new("F010_Fill", "AREA")
    fill_data.energy = 250.0
    fill_data.shape = "DISK"
    fill_data.size = 2.5
    fill = bpy.data.objects.new("F010_Fill", fill_data)
    scene.collection.objects.link(fill)
    fill.location = (-1.6, -1.2, 2.4)
    look_at(fill, (0.0, 0.0, 0.0))

    cam_data = bpy.data.cameras.new("F010_Camera")
    cam_data.lens = 46.0
    cam_data.clip_start = 0.01
    cam_data.clip_end = 100.0
    cam = bpy.data.objects.new("F010_Camera", cam_data)
    scene.collection.objects.link(cam)
    cam.location = (2.15, -2.85, 2.35)
    look_at(cam, (0.0, 0.05, 0.0))
    scene.camera = cam

    bpy.ops.mesh.primitive_plane_add(size=14.0, location=(0.0, 0.0, -0.004))
    ground = bpy.context.active_object
    ground.name = "PreviewGround"
    gmat = make_material("PreviewGround", (0.62, 0.62, 0.61), 0.95)
    ground.data.materials.append(gmat)
    return ground


def render_preview(path):
    scene = bpy.context.scene
    scene.render.resolution_x = 512
    scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.filepath = path
    scene.render.film_transparent = False

    engines = ["BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "BLENDER_WORKBENCH", "CYCLES"]
    last_error = None
    for engine in engines:
        try:
            scene.render.engine = engine
        except TypeError as exc:
            last_error = exc
            continue
        if engine == "CYCLES":
            scene.cycles.device = "CPU"
            scene.cycles.samples = 32
            scene.cycles.use_denoising = False
        if engine == "BLENDER_WORKBENCH":
            shading = scene.display.shading
            shading.light = "STUDIO"
            shading.color_type = "MATERIAL"
            shading.background_type = "WORLD"
        if "EEVEE" in engine:
            eevee = getattr(scene, "eevee", None)
            if eevee is not None and hasattr(eevee, "taa_render_samples"):
                eevee.taa_render_samples = 16
        try:
            bpy.ops.render.render(write_still=True)
            print(f"preview rendered with {engine}")
            return engine
        except Exception as exc:  # noqa: BLE001 — try the next headless engine
            last_error = exc
            print(f"render engine {engine} failed: {exc}")
    raise SystemExit(f"all render engines failed: {last_error}")


def export_glb(obj, path):
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
    )


def measure_imported(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    imported = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    if not imported:
        raise SystemExit("glTF reimport produced no mesh")
    mins = [math.inf, math.inf, math.inf]
    maxs = [-math.inf, -math.inf, -math.inf]
    tris = 0
    for obj in imported:
        for corner in obj.bound_box:
            world = obj.matrix_world @ Vector(corner)
            for axis in range(3):
                mins[axis] = min(mins[axis], world[axis])
                maxs[axis] = max(maxs[axis], world[axis])
        obj.data.calc_loop_triangles()
        tris += len(obj.data.loop_triangles)
    size = tuple(maxs[i] - mins[i] for i in range(3))
    for obj in imported:
        bpy.data.objects.remove(obj, do_unlink=True)
    return size, tuple(mins), tuple(maxs), tris


def write_metadata(path, size, mins, maxs, tris):
    import json

    payload = {
        "id": "F010",
        "name": "Geometric Area Carpet 8x10",
        "category": "Carpet",
        "style": "Modern",
        "room": "Living Room",
        "price_usd": 249,
        "dimensions_in": {"width": WIDTH_IN, "depth": DEPTH_IN, "height": HEIGHT_IN},
        "dimensions_m": {
            "width": round(WIDTH, 6),
            "depth": round(DEPTH, 6),
            "height": round(HEIGHT, 6),
        },
        "bounding_box_m": {
            "width": round(size[0], 6),
            "depth": round(size[1], 6),
            "height": round(size[2], 6),
            "min": [round(v, 6) for v in mins],
            "max": [round(v, 6) for v in maxs],
        },
        "triangle_count": tris,
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    print("wrote", path)


def main():
    outdir = parse_outdir()
    os.makedirs(outdir, exist_ok=True)
    reset_scene()
    enable_gltf()

    materials = build_materials()
    rug = build_mesh(materials)
    size, mins, maxs = assert_dimensions(rug)
    tris = triangle_count(rug)
    print(f"built F010 triangles={tris}")

    add_preview_rig()
    preview = os.path.join(outdir, "preview.png")
    render_preview(preview)

    blend_path = os.path.join(outdir, "model.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print("wrote", blend_path)

    glb_path = os.path.join(outdir, "model.glb")
    export_glb(rug, glb_path)
    print("wrote", glb_path)

    gsize, gmins, gmaxs, gtris = measure_imported(glb_path)
    print(
        "F010 exported bbox m: width={:.6f} depth={:.6f} height={:.6f} tris={}".format(
            gsize[0], gsize[1], gsize[2], gtris
        )
    )
    targets = (WIDTH, DEPTH, HEIGHT)
    for label, measured, target in zip(("width", "depth", "height"), gsize, targets):
        err = abs(measured - target) / target
        if err > 0.02:
            raise SystemExit(f"exported {label} out of tolerance: {measured} vs {target}")

    write_metadata(os.path.join(outdir, "metadata.json"), gsize, gmins, gmaxs, gtris)
    # Keep the source scene free of the reimported copy.
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)


if __name__ == "__main__":
    main()
