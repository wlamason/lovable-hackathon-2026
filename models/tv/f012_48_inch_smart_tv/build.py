"""Build catalog item F012, a wall-mounted 48-inch class smart TV.

Run:
    blender -b --factory-startup --python build.py -- --outdir <dir>

Units are meters. Width is X, depth is Y, height is Z. The screen faces -Y.
Origin is the bottom center of the footprint. No stand: the 3 in depth is the
panel itself so the bounding box matches the catalog envelope.
"""

import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

INCH = 0.0254

# Catalog envelope: 43 in wide x 3 in deep x 26 in tall.
WIDTH_IN = 43.0
DEPTH_IN = 3.0
HEIGHT_IN = 26.0
W = WIDTH_IN * INCH
D = DEPTH_IN * INCH
H = HEIGHT_IN * INCH

# Thin modern bezel. Bottom chin is only slightly taller than the sides.
BEZEL_SIDE = 0.40 * INCH
BEZEL_TOP = 0.36 * INCH
BEZEL_BOTTOM = 0.58 * INCH

# Slim front lip, with the electronics hump making up the rest of the 3 in depth.
SHELL_THICK = 0.46 * INCH
REAR_MARGIN_X = 0.85 * INCH
REAR_MARGIN_TOP = 0.95 * INCH
REAR_MARGIN_BOTTOM = 0.50 * INCH

SCREEN_INSET = 0.0014
SCREEN_GAP = 0.0006
SCREEN_THICK = 0.0032


def parse_outdir():
    outdir = os.path.dirname(os.path.abspath(__file__))
    if "--" in sys.argv:
        extra = sys.argv[sys.argv.index("--") + 1 :]
        i = 0
        while i < len(extra):
            if extra[i] == "--outdir" and i + 1 < len(extra):
                outdir = os.path.abspath(extra[i + 1])
                i += 2
            else:
                i += 1
    os.makedirs(outdir, exist_ok=True)
    return outdir


def reset_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in (bpy.data.meshes, bpy.data.materials, bpy.data.lights, bpy.data.cameras):
        for datablock in list(collection):
            if datablock.users == 0:
                collection.remove(datablock)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0


def set_input(node, name, value):
    if name in node.inputs:
        node.inputs[name].default_value = value


def make_material(name, color, roughness, metallic=0.0, specular=0.5, coat=0.0, coat_roughness=0.1, emission=None, emission_strength=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    set_input(bsdf, "Base Color", (*color, 1.0))
    set_input(bsdf, "Metallic", metallic)
    set_input(bsdf, "Roughness", roughness)
    set_input(bsdf, "Specular IOR Level", specular)
    set_input(bsdf, "Specular", specular)
    if coat:
        set_input(bsdf, "Coat Weight", coat)
        set_input(bsdf, "Coat Roughness", coat_roughness)
    if emission is not None:
        set_input(bsdf, "Emission Color", (*emission, 1.0))
        set_input(bsdf, "Emission Strength", emission_strength)
    return mat


def link_object(mesh, name, material):
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    mesh.materials.append(material)
    for poly in mesh.polygons:
        poly.material_index = 0
    return obj


def new_mesh_from_bmesh(name, bm):
    mesh = bpy.data.meshes.new(name)
    bm.normal_update()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return mesh


def make_frame(material):
    """Closed picture-frame shell. Front face is at y = -D/2."""
    y0 = -D / 2.0
    y1 = y0 + SHELL_THICK
    x0, x1 = -W / 2.0, W / 2.0
    z0, z1 = 0.0, H
    ix0, ix1 = x0 + BEZEL_SIDE, x1 - BEZEL_SIDE
    iz0, iz1 = z0 + BEZEL_BOTTOM, z1 - BEZEL_TOP

    verts = [
        (x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1),
        (ix0, y0, iz0), (ix1, y0, iz0), (ix1, y0, iz1), (ix0, y0, iz1),
        (x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1),
        (ix0, y1, iz0), (ix1, y1, iz0), (ix1, y1, iz1), (ix0, y1, iz1),
    ]
    faces = [
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
        (8, 12, 13, 9),
        (9, 13, 14, 10),
        (10, 14, 15, 11),
        (11, 15, 12, 8),
        (0, 8, 9, 1),
        (1, 9, 10, 2),
        (2, 10, 11, 3),
        (3, 11, 8, 0),
        (4, 5, 13, 12),
        (5, 6, 14, 13),
        (6, 7, 15, 14),
        (7, 4, 12, 15),
    ]
    bm = bmesh.new()
    bm_verts = [bm.verts.new(co) for co in verts]
    bm.verts.ensure_lookup_table()
    for face in faces:
        bm.faces.new([bm_verts[i] for i in face])
    mesh = new_mesh_from_bmesh("Bezel", bm)
    return link_object(mesh, "Bezel", material)


def make_box(name, bounds, material, bevel=0.0):
    x0, x1, y0, y1, z0, z1 = bounds
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for vert in bm.verts:
        vert.co.x = x0 + (vert.co.x + 0.5) * (x1 - x0)
        vert.co.y = y0 + (vert.co.y + 0.5) * (y1 - y0)
        vert.co.z = z0 + (vert.co.z + 0.5) * (z1 - z0)
    if bevel > 0.0:
        bmesh.ops.bevel(
            bm,
            geom=list(bm.edges),
            offset=bevel,
            segments=2,
            profile=0.5,
            affect="EDGES",
            clamp_overlap=True,
        )
    mesh = new_mesh_from_bmesh(name, bm)
    return link_object(mesh, name, material)


def make_rear(material):
    y_front = -D / 2.0
    y0 = y_front + SHELL_THICK - 0.003
    y1 = D / 2.0
    x0 = -W / 2.0 + REAR_MARGIN_X
    x1 = W / 2.0 - REAR_MARGIN_X
    z0 = REAR_MARGIN_BOTTOM
    z1 = H - REAR_MARGIN_TOP
    return make_box("Rear", (x0, x1, y0, y1, z0, z1), material, bevel=0.004)


def make_screen(material):
    y0 = -D / 2.0 + SCREEN_INSET
    y1 = y0 + SCREEN_THICK
    x0 = -W / 2.0 + BEZEL_SIDE + SCREEN_GAP
    x1 = W / 2.0 - BEZEL_SIDE - SCREEN_GAP
    z0 = BEZEL_BOTTOM + SCREEN_GAP
    z1 = H - BEZEL_TOP - SCREEN_GAP
    return make_box("Screen", (x0, x1, y0, y1, z0, z1), material, bevel=0.0004)


def make_led(material):
    """Tiny power indicator centered on the bottom chin, facing -Y."""
    radius = 0.0015
    depth = 0.0012
    y_front = -D / 2.0
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=16,
        radius=radius,
        depth=depth,
        location=(0.0, y_front - depth * 0.15, BEZEL_BOTTOM * 0.42),
        rotation=(math.radians(90.0), 0.0, 0.0),
    )
    obj = bpy.context.active_object
    obj.name = "PowerLED"
    mesh = obj.data
    mesh.name = "PowerLED"
    mesh.materials.append(material)
    return obj


def apply_transform(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)


def bevel_object(obj, width, segments=2):
    apply_transform(obj)
    mod = obj.modifiers.new("Bevel", "BEVEL")
    mod.width = width
    mod.segments = segments
    mod.limit_method = "ANGLE"
    mod.angle_limit = math.radians(40.0)
    mod.harden_normals = True
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=mod.name)


def join_objects(objects, name):
    for obj in objects:
        apply_transform(obj)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.join()
    joined = bpy.context.active_object
    joined.name = name
    joined.data.name = name
    return joined


def fit_bottom_center(obj, target_w, target_d, target_h):
    """Scale so the world bbox matches the catalog size, origin at bottom center."""
    mesh = obj.data
    xs = [v.co.x for v in mesh.vertices]
    ys = [v.co.y for v in mesh.vertices]
    zs = [v.co.z for v in mesh.vertices]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    minz, maxz = min(zs), max(zs)
    cx = (minx + maxx) * 0.5
    cy = (miny + maxy) * 0.5
    sx = target_w / (maxx - minx)
    sy = target_d / (maxy - miny)
    sz = target_h / (maxz - minz)
    for vert in mesh.vertices:
        vert.co.x = (vert.co.x - cx) * sx
        vert.co.y = (vert.co.y - cy) * sy
        vert.co.z = (vert.co.z - minz) * sz
    mesh.update()


def measured_bbox(obj):
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    xs = [c.x for c in corners]
    ys = [c.y for c in corners]
    zs = [c.z for c in corners]
    return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)


def triangle_count(obj):
    mesh = obj.data
    mesh.calc_loop_triangles()
    return len(mesh.loop_triangles)


def shade(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(45.0))
    except Exception:
        bpy.ops.object.shade_smooth()
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")


def assert_front_and_size(obj):
    minx, maxx, miny, maxy, minz, maxz = measured_bbox(obj)
    width = maxx - minx
    depth = maxy - miny
    height = maxz - minz
    print(f"Measured bbox m: {width:.6f} x {depth:.6f} x {height:.6f}")
    print(f"Target bbox m:   {W:.6f} x {D:.6f} x {H:.6f}")
    print(f"Origin check min: ({minx:.6f}, {miny:.6f}, {minz:.6f})")
    for label, actual, target in (("width", width, W), ("depth", depth, D), ("height", height, H)):
        error = abs(actual - target) / target
        if error > 0.02:
            raise RuntimeError(f"{label} error {error:.3%} exceeds 2%")
    if abs(minz) > 1e-5 or abs((minx + maxx) * 0.5) > 1e-5 or abs((miny + maxy) * 0.5) > 1e-5:
        raise RuntimeError("origin is not the bottom center of the bounding box")
    # Front faces -Y: a polygon on the front of the screen should point toward -Y.
    front_normals = [p.normal.y for p in obj.data.polygons if p.center.y < miny + 0.004]
    if not front_normals or min(front_normals) > -0.5:
        raise RuntimeError("front of the panel does not face -Y")
    names = [slot.name for slot in obj.data.materials]
    if "Screen" not in names:
        raise RuntimeError(f"Screen material missing, have {names}")
    tris = triangle_count(obj)
    print(f"Triangles: {tris}")
    print(f"Materials: {names}")
    return {
        "width": width,
        "depth": depth,
        "height": height,
        "min": [minx, miny, minz],
        "max": [maxx, maxy, maxz],
        "triangles": tris,
    }


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def setup_preview(target):
    scene = bpy.context.scene
    world = scene.world
    if world is None:
        world = bpy.data.worlds.new("World")
        scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background:
        background.inputs["Color"].default_value = (0.62, 0.63, 0.65, 1.0)
        background.inputs["Strength"].default_value = 0.45

    cam_data = bpy.data.cameras.new("Camera")
    cam = bpy.data.objects.new("Camera", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam_data.lens = 50
    # Far enough to show the whole panel, angled so the thin side and rear step read.
    yaw = math.radians(34.0)
    dist = 2.45
    cam.location = (math.sin(yaw) * dist, -math.cos(yaw) * dist, H * 0.62)
    look_at(cam, target)

    def area(name, location, energy, size):
        light_data = bpy.data.lights.new(name, "AREA")
        light_data.energy = energy
        light_data.size = size
        light_data.shape = "RECTANGLE"
        light_data.size_y = size * 0.7
        light = bpy.data.objects.new(name, light_data)
        scene.collection.objects.link(light)
        light.location = location
        look_at(light, target)
        return light

    # Large soft key so the glossy screen gets a smooth highlight, not a hard band.
    area("Key", (-0.7, -1.6, 1.35), 220.0, 2.2)
    area("Fill", (1.2, -1.4, 0.4), 70.0, 1.8)
    area("Rim", (0.35, 1.0, 0.85), 110.0, 0.7)

    engines = {item.identifier for item in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
    for candidate in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        if candidate in engines:
            scene.render.engine = candidate
            break
    else:
        scene.render.engine = "BLENDER_WORKBENCH"
    print(f"Render engine: {scene.render.engine}")
    if hasattr(scene, "eevee"):
        eevee = scene.eevee
        if hasattr(eevee, "taa_render_samples"):
            eevee.taa_render_samples = 32
        if hasattr(eevee, "use_raytracing"):
            eevee.use_raytracing = False
    scene.render.resolution_x = 512
    scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False


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
        export_yup=True,
        export_cameras=False,
        export_lights=False,
    )


def write_metadata(path, bbox):
    payload = {
        "id": "F012",
        "name": "48-Inch Smart TV",
        "category": "TV",
        "style": "Modern",
        "room": "Living Room",
        "price_usd": 399,
        "dimensions_in": {
            "width": WIDTH_IN,
            "depth": DEPTH_IN,
            "height": HEIGHT_IN,
        },
        "dimensions_m": {
            "width": round(W, 6),
            "depth": round(D, 6),
            "height": round(H, 6),
        },
        "bounding_box_m": {
            "width": round(bbox["width"], 6),
            "depth": round(bbox["depth"], 6),
            "height": round(bbox["height"], 6),
            "min": [round(v, 6) for v in bbox["min"]],
            "max": [round(v, 6) for v in bbox["max"]],
        },
        "triangle_count": bbox["triangles"],
        "screen_material": "Screen",
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def build():
    reset_scene()
    bezel_mat = make_material("Bezel", (0.012, 0.012, 0.013), roughness=0.42, specular=0.35)
    rear_mat = make_material("Rear", (0.028, 0.028, 0.030), roughness=0.58, specular=0.28)
    # Dark glossy panel. Named Screen so the web app can swap it.
    screen_mat = make_material(
        "Screen",
        (0.020, 0.023, 0.030),
        roughness=0.04,
        specular=0.5,
        coat=0.55,
        coat_roughness=0.04,
    )
    led_mat = make_material(
        "PowerLED",
        (0.85, 0.90, 0.95),
        roughness=0.25,
        emission=(0.65, 0.85, 1.0),
        emission_strength=4.0,
    )

    frame = make_frame(bezel_mat)
    bevel_object(frame, width=0.0016, segments=2)
    rear = make_rear(rear_mat)
    screen = make_screen(screen_mat)
    led = make_led(led_mat)

    tv = join_objects([frame, rear, screen, led], "F012")
    shade(tv)
    fit_bottom_center(tv, W, D, H)
    bpy.ops.object.select_all(action="DESELECT")
    tv.select_set(True)
    bpy.context.view_layer.objects.active = tv
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bbox = assert_front_and_size(tv)
    return tv, bbox


def main():
    outdir = parse_outdir()
    tv, bbox = build()
    target = (0.0, 0.0, H * 0.42)
    setup_preview(target)
    preview_path = os.path.join(outdir, "preview.png")
    bpy.context.scene.render.filepath = preview_path
    bpy.ops.render.render(write_still=True)
    export_glb(tv, os.path.join(outdir, "model.glb"))
    blend_path = os.path.join(outdir, "model.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    write_metadata(os.path.join(outdir, "metadata.json"), bbox)
    print(f"Wrote {outdir}")


if __name__ == "__main__":
    main()
