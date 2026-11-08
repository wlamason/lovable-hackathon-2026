"""Build F013 65-Inch Smart TV and export glTF, blend, preview, and metadata.

Run:
  blender -b --factory-startup --python build.py -- --outdir <dir>

Units are meters. The panel is wall-mountable (no stand): 57 in wide,
3 in deep, 34 in tall. Origin is the bottom center of the footprint.
The front faces -Y. The glass uses a material named exactly "Screen".
"""

import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

INCH = 0.0254

# Catalog envelope. The 65 in figure is the 16:9 glass diagonal.
WIDTH_IN = 57.0
DEPTH_IN = 3.0
HEIGHT_IN = 34.0
DIAGONAL_IN = 65.0

W = WIDTH_IN * INCH
D = DEPTH_IN * INCH
H = HEIGHT_IN * INCH

_ASPECT_HYP = math.sqrt(16.0 ** 2 + 9.0 ** 2)
SCREEN_W = DIAGONAL_IN * INCH * 16.0 / _ASPECT_HYP
SCREEN_H = DIAGONAL_IN * INCH * 9.0 / _ASPECT_HYP
SIDE_BEZEL = (W - SCREEN_W) / 2.0
TOP_BEZEL = SIDE_BEZEL
BOTTOM_BEZEL = H - SCREEN_H - TOP_BEZEL

# Front lip depth of the glass recess. The rest of the 3 in is the panel body.
RECESS = 0.010
BEVEL = 0.0009


def parse_outdir():
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    outdir = os.path.dirname(os.path.abspath(__file__))
    if "--outdir" in argv:
        outdir = os.path.abspath(argv[argv.index("--outdir") + 1])
    os.makedirs(outdir, exist_ok=True)
    return outdir


def set_input(node, name, value):
    sock = node.inputs.get(name)
    if sock is not None:
        sock.default_value = value


def new_material(name, color, roughness, metallic=0.0, emission=None, emission_strength=0.0, coat=0.0, coat_roughness=0.1):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    set_input(bsdf, "Base Color", (*color, 1.0))
    set_input(bsdf, "Roughness", roughness)
    set_input(bsdf, "Metallic", metallic)
    set_input(bsdf, "Specular IOR Level", 0.5)
    set_input(bsdf, "Coat Weight", coat)
    set_input(bsdf, "Coat Roughness", coat_roughness)
    if emission is not None:
        set_input(bsdf, "Emission Color", (*emission, 1.0))
        set_input(bsdf, "Emission Strength", emission_strength)
    return mat


def link_object(name, mesh):
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


class VertCache:
    def __init__(self, bm):
        self.bm = bm
        self.verts = {}

    def __call__(self, x, y, z):
        key = (round(x, 6), round(y, 6), round(z, 6))
        vert = self.verts.get(key)
        if vert is None:
            vert = self.bm.verts.new(key)
            self.verts[key] = vert
        return vert

    def quad(self, a, b, c, d):
        self.bm.faces.new((self(*a), self(*b), self(*c), self(*d)))


def build_panel():
    """Watertight panel: thin front bezel, recessed glass bay, flat back."""
    y_front = -D / 2.0
    y_recess = y_front + RECESS
    y_back = D / 2.0

    x_l, x_r = -W / 2.0, W / 2.0
    z_b, z_t = 0.0, H
    x_il, x_ir = -SCREEN_W / 2.0, SCREEN_W / 2.0
    z_is = BOTTOM_BEZEL
    z_it = BOTTOM_BEZEL + SCREEN_H

    # Shallow status pocket in the chin so the LED sits behind the front plane.
    pocket_w = 0.036
    pocket_h = 0.008
    cz = BOTTOM_BEZEL * 0.46
    x_pl, x_pr = -pocket_w / 2.0, pocket_w / 2.0
    z_pb, z_pt = cz - pocket_h / 2.0, cz + pocket_h / 2.0
    y_pocket = y_front + 0.0018

    mesh = bpy.data.meshes.new("Panel")
    bm = bmesh.new()
    v = VertCache(bm)

    # Front bezel, with a rectangular pocket in the chin.
    v.quad((x_l, y_front, z_b), (x_r, y_front, z_b), (x_r, y_front, z_pb), (x_l, y_front, z_pb))
    v.quad((x_l, y_front, z_pb), (x_pl, y_front, z_pb), (x_pl, y_front, z_pt), (x_l, y_front, z_pt))
    v.quad((x_pr, y_front, z_pb), (x_r, y_front, z_pb), (x_r, y_front, z_pt), (x_pr, y_front, z_pt))
    v.quad((x_l, y_front, z_pt), (x_r, y_front, z_pt), (x_r, y_front, z_is), (x_l, y_front, z_is))
    v.quad((x_l, y_front, z_is), (x_il, y_front, z_is), (x_il, y_front, z_it), (x_l, y_front, z_it))
    v.quad((x_ir, y_front, z_is), (x_r, y_front, z_is), (x_r, y_front, z_it), (x_ir, y_front, z_it))
    v.quad((x_l, y_front, z_it), (x_r, y_front, z_it), (x_r, y_front, z_t), (x_l, y_front, z_t))

    # Pocket walls and floor (floor sits just behind the outer face).
    v.quad((x_pl, y_front, z_pb), (x_pr, y_front, z_pb), (x_pr, y_pocket, z_pb), (x_pl, y_pocket, z_pb))
    v.quad((x_pr, y_front, z_pt), (x_pl, y_front, z_pt), (x_pl, y_pocket, z_pt), (x_pr, y_pocket, z_pt))
    v.quad((x_pl, y_front, z_pt), (x_pl, y_front, z_pb), (x_pl, y_pocket, z_pb), (x_pl, y_pocket, z_pt))
    v.quad((x_pr, y_front, z_pb), (x_pr, y_front, z_pt), (x_pr, y_pocket, z_pt), (x_pr, y_pocket, z_pb))
    v.quad((x_pl, y_pocket, z_pb), (x_pr, y_pocket, z_pb), (x_pr, y_pocket, z_pt), (x_pl, y_pocket, z_pt))

    # Glass recess.
    v.quad((x_il, y_front, z_is), (x_ir, y_front, z_is), (x_ir, y_recess, z_is), (x_il, y_recess, z_is))
    v.quad((x_ir, y_front, z_it), (x_il, y_front, z_it), (x_il, y_recess, z_it), (x_ir, y_recess, z_it))
    v.quad((x_il, y_front, z_it), (x_il, y_front, z_is), (x_il, y_recess, z_is), (x_il, y_recess, z_it))
    v.quad((x_ir, y_front, z_is), (x_ir, y_front, z_it), (x_ir, y_recess, z_it), (x_ir, y_recess, z_is))
    v.quad((x_il, y_recess, z_is), (x_ir, y_recess, z_is), (x_ir, y_recess, z_it), (x_il, y_recess, z_it))

    # Outer shell and flat wall-mount back.
    v.quad((x_l, y_front, z_b), (x_l, y_back, z_b), (x_r, y_back, z_b), (x_r, y_front, z_b))
    v.quad((x_l, y_front, z_t), (x_r, y_front, z_t), (x_r, y_back, z_t), (x_l, y_back, z_t))
    v.quad((x_l, y_front, z_b), (x_l, y_front, z_t), (x_l, y_back, z_t), (x_l, y_back, z_b))
    v.quad((x_r, y_front, z_t), (x_r, y_front, z_b), (x_r, y_back, z_b), (x_r, y_back, z_t))
    v.quad((x_l, y_back, z_b), (x_l, y_back, z_t), (x_r, y_back, z_t), (x_r, y_back, z_b))

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()

    obj = link_object("Panel", mesh)
    bevel = obj.modifiers.new("Bevel", "BEVEL")
    bevel.width = BEVEL
    bevel.segments = 2
    bevel.limit_method = "ANGLE"
    bevel.angle_limit = math.radians(40.0)
    bevel.harden_normals = True
    bevel.miter_outer = "MITER_ARC"
    return obj, (x_il, x_ir, z_is, z_it, y_front, y_recess, y_pocket, cz)


def build_screen(opening):
    x_il, x_ir, z_is, z_it, y_front, y_recess, _y_pocket, _cz = opening
    pad = 0.0016
    mesh = bpy.data.meshes.new("Screen")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(mesh)
    bm.free()
    obj = link_object("Screen", mesh)
    obj.location = (0.0, (y_front + 0.004 + y_recess - 0.001) / 2.0, (z_is + z_it) / 2.0)
    obj.scale = (x_ir - x_il - 2 * pad, (y_recess - 0.001) - (y_front + 0.004), z_it - z_is - 2 * pad)
    return obj


def build_indicator(opening):
    _x_il, _x_ir, _z_is, _z_it, y_front, _y_recess, y_pocket, cz = opening
    mesh = bpy.data.meshes.new("Indicator")
    bm = bmesh.new()
    radius = 0.0032
    depth = 0.0014
    segments = 24
    cy = y_pocket - 0.00035
    ring_front = []
    ring_back = []
    for i in range(segments):
        ang = 2.0 * math.pi * i / segments
        x = radius * math.cos(ang)
        z = cz + radius * math.sin(ang)
        ring_front.append(bm.verts.new((x, cy - depth / 2.0, z)))
        ring_back.append(bm.verts.new((x, cy + depth / 2.0, z)))
    for i in range(segments):
        j = (i + 1) % segments
        bm.faces.new((ring_front[i], ring_front[j], ring_back[j], ring_back[i]))
    bm.faces.new(list(reversed(ring_front)))
    bm.faces.new(ring_back)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    return link_object("Indicator", mesh)


def apply_modifiers(obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    baked = bpy.data.meshes.new_from_object(evaluated)
    old = obj.data
    obj.modifiers.clear()
    obj.data = baked
    if old.users == 0:
        bpy.data.meshes.remove(old)


def apply_transforms(obj):
    # matrix_world is cached; compose from the properties so a stale depsgraph
    # cannot leave a unit cube in the preview scene.
    obj.data.transform(obj.matrix_basis.copy())
    obj.location = (0.0, 0.0, 0.0)
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)
    bpy.context.view_layer.update()


def shade_smooth(obj, angle_deg=50.0):
    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.normal_update()
    limit = math.radians(angle_deg)
    for edge in bm.edges:
        if len(edge.link_faces) == 2 and edge.calc_face_angle(0.0) > limit:
            edge.smooth = False
        else:
            edge.smooth = True
    for face in bm.faces:
        face.smooth = True
    bm.to_mesh(mesh)
    bm.free()


def world_bounds(objects):
    xs, ys, zs = [], [], []
    for obj in objects:
        if obj.type != "MESH":
            continue
        for vert in obj.data.vertices:
            world = obj.matrix_world @ vert.co
            xs.append(world.x)
            ys.append(world.y)
            zs.append(world.z)
    return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))


def triangle_count(objects):
    total = 0
    for obj in objects:
        if obj.type != "MESH":
            continue
        obj.data.calc_loop_triangles()
        total += len(obj.data.loop_triangles)
    return total


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def project_ndc(scene, cam, points):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    projection = cam.calc_matrix_camera(
        depsgraph,
        x=scene.render.resolution_x,
        y=scene.render.resolution_y,
        scale_x=scene.render.pixel_aspect_x,
        scale_y=scene.render.pixel_aspect_y,
    )
    modelview = cam.matrix_world.inverted()
    ndc = []
    for point in points:
        clip = projection @ modelview @ Vector((point.x, point.y, point.z, 1.0))
        ndc.append((clip.x / clip.w, clip.y / clip.w, clip.w))
    return ndc


def frame_camera(cam, target, objects):
    """Pull the camera back along a front three-quarter view until the panel fits."""
    scene = bpy.context.scene
    offset = Vector((1.25, -1.95, 0.26))
    direction = offset.normalized()
    corners = []
    for obj in objects:
        if obj.type != "MESH":
            continue
        for corner in obj.bound_box:
            corners.append(obj.matrix_world @ Vector(corner))
    distance = 3.3
    span = 99.0
    for _ in range(10):
        cam.location = Vector(target) + direction * distance
        look_at(cam, target)
        bpy.context.view_layer.update()
        ndc = project_ndc(scene, cam, corners)
        span = max(max(abs(x), abs(y)) for x, y, w in ndc if w > 0)
        print(f"CAMERA dist={distance:.2f} span={span:.3f}")
        if abs(span - 0.80) < 0.035:
            break
        distance *= span / 0.80
    if span > 0.92:
        raise SystemExit(f"preview camera failed to frame the TV (span={span:.3f})")


def add_area(name, location, target, energy, size, color=(1.0, 1.0, 1.0)):
    light = bpy.data.lights.new(name, "AREA")
    light.energy = energy
    light.size = size
    light.color = color
    obj = bpy.data.objects.new(name, light)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    look_at(obj, target)
    return obj


def render_preview(outdir, target, product_meshes):
    scene = bpy.context.scene
    scene.render.resolution_x = 512
    scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.filepath = os.path.join(outdir, "preview.png")
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0

    world = bpy.data.worlds.new("Studio")
    scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.84, 0.85, 0.87, 1.0)
    background.inputs["Strength"].default_value = 0.55

    # Neutral wall just behind the panel so the shot reads as wall-mounted.
    wall_mesh = bpy.data.meshes.new("PreviewWall")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(wall_mesh)
    bm.free()
    wall = link_object("PreviewWall", wall_mesh)
    wall.location = (0.0, D / 2.0 + 0.08, H * 0.48)
    wall.scale = (6.0, 0.02, 4.0)
    apply_transforms(wall)
    wall_mat = new_material("PreviewWall", (0.80, 0.81, 0.83), 0.92, metallic=0.0)
    wall.data.materials.append(wall_mat)

    camera_data = bpy.data.cameras.new("Camera")
    camera_data.lens = 48
    camera_data.clip_start = 0.01
    camera_data.clip_end = 50
    camera = bpy.data.objects.new("Camera", camera_data)
    bpy.context.scene.collection.objects.link(camera)
    scene.camera = camera
    frame_camera(camera, target, product_meshes)

    # Side key so the glass keeps a small highlight instead of a full-frame blast.
    add_area("Key", (1.55, -0.55, 1.55), target, 90, 0.35, (1.0, 0.98, 0.95))
    add_area("Fill", (0.0, -2.6, 0.55), target, 28, 2.4, (0.92, 0.95, 1.0))
    add_area("Rim", (-1.2, 0.35, 1.3), target, 70, 0.4, (1.0, 0.98, 0.95))

    def snap():
        bpy.ops.render.render(write_still=True)

    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
        scene.eevee.taa_render_samples = 48
        if hasattr(scene.eevee, "use_raytracing"):
            scene.eevee.use_raytracing = False
        snap()
        engine = "BLENDER_EEVEE_NEXT"
    except Exception as exc:
        print("Eevee preview failed, falling back to Workbench:", exc)
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.display.shading.light = "STUDIO"
        scene.display.shading.color_type = "MATERIAL"
        snap()
        engine = "BLENDER_WORKBENCH"
    print("PREVIEW_ENGINE", engine)

    # Drop studio-only objects so the blend and glTF are the product.
    for extra in (wall, camera):
        data = extra.data
        bpy.data.objects.remove(extra, do_unlink=True)
        if data is not None and data.users == 0:
            if isinstance(data, bpy.types.Mesh):
                bpy.data.meshes.remove(data)
            elif isinstance(data, bpy.types.Camera):
                bpy.data.cameras.remove(data)
    for obj in list(bpy.data.objects):
        if obj.type == "LIGHT":
            data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if data.users == 0:
                bpy.data.lights.remove(data)
    bpy.data.materials.remove(wall_mat)


def main():
    outdir = parse_outdir()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0

    if BOTTOM_BEZEL <= 0.01 or SIDE_BEZEL <= 0.0:
        raise SystemExit(
            f"Bezel math failed: side={SIDE_BEZEL:.4f} bottom={BOTTOM_BEZEL:.4f}"
        )

    bezel = new_material("Bezel", (0.008, 0.008, 0.009), 0.48, metallic=0.04)
    screen_mat = new_material(
        "Screen",
        (0.012, 0.016, 0.024),
        0.22,
        metallic=0.0,
        emission=(0.012, 0.018, 0.030),
        emission_strength=0.9,
        coat=0.35,
        coat_roughness=0.18,
    )
    indicator_mat = new_material(
        "Indicator",
        (0.75, 0.88, 1.0),
        0.2,
        emission=(0.65, 0.86, 1.0),
        emission_strength=18.0,
    )

    panel, opening = build_panel()
    screen = build_screen(opening)
    indicator = build_indicator(opening)

    panel.data.materials.append(bezel)
    screen.data.materials.append(screen_mat)
    indicator.data.materials.append(indicator_mat)

    apply_modifiers(panel)
    for obj in (panel, screen, indicator):
        apply_transforms(obj)
        shade_smooth(obj)
        obj.data.name = obj.name

    root = bpy.data.objects.new("F013", None)
    root.empty_display_type = "PLAIN_AXES"
    root.empty_display_size = 0.15
    scene.collection.objects.link(root)
    for obj in (panel, screen, indicator):
        obj.parent = root
        obj.matrix_parent_inverse = root.matrix_world.inverted()

    meshes = [panel, screen, indicator]
    xmin, xmax, ymin, ymax, zmin, zmax = world_bounds(meshes)
    measured = (xmax - xmin, ymax - ymin, zmax - zmin)
    targets = (W, D, H)
    names = ("width", "depth", "height")
    print(
        "BBOX_M min=({:.6f}, {:.6f}, {:.6f}) max=({:.6f}, {:.6f}, {:.6f})".format(
            xmin, ymin, zmin, xmax, ymax, zmax
        )
    )
    print(
        "SIZE_M width={:.6f} depth={:.6f} height={:.6f}".format(*measured)
    )
    print(
        "TARGET_M width={:.6f} depth={:.6f} height={:.6f}".format(*targets)
    )
    for name, got, target in zip(names, measured, targets):
        err = abs(got - target) / target
        print(f"ERR_{name} {err * 100:.4f}%")
        if err > 0.02:
            raise SystemExit(f"{name} bbox {got:.6f} m is {err * 100:.2f}% off {target:.6f} m")
    if abs(xmin + xmax) > 1e-5 or abs(ymin + ymax) > 1e-5 or abs(zmin) > 1e-5:
        raise SystemExit("origin is not the bottom center of the footprint")

    tris = triangle_count(meshes)
    print("TRIANGLES", tris)
    if tris > 30000:
        raise SystemExit(f"triangle count {tris} exceeds 30000")
    if bpy.data.materials.get("Screen") is None:
        raise SystemExit("Screen material missing")

    def r6(value):
        return round(float(value), 6)

    metadata = {
        "id": "F013",
        "name": "65-Inch Smart TV",
        "category": "TV",
        "style": "Modern",
        "room": "Living Room",
        "price_usd": 699,
        "dimensions_in": {"width": WIDTH_IN, "depth": DEPTH_IN, "height": HEIGHT_IN},
        "dimensions_m": {"width": r6(W), "depth": r6(D), "height": r6(H)},
        "bounding_box_m": {
            "min": [r6(xmin), r6(ymin), r6(zmin)],
            "max": [r6(xmax), r6(ymax), r6(zmax)],
            "width": r6(measured[0]),
            "depth": r6(measured[1]),
            "height": r6(measured[2]),
        },
        "triangle_count": tris,
        "screen_diagonal_in": DIAGONAL_IN,
        "materials": ["Bezel", "Screen", "Indicator"],
    }
    with open(os.path.join(outdir, "metadata.json"), "w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)
        handle.write("\n")

    render_preview(outdir, (0.0, 0.0, H * 0.48), meshes)

    bpy.ops.export_scene.gltf(
        filepath=os.path.join(outdir, "model.glb"),
        export_format="GLB",
        use_selection=False,
        export_apply=True,
        export_yup=True,
    )
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(outdir, "model.blend"))
    print("WROTE", outdir)


if __name__ == "__main__":
    main()
