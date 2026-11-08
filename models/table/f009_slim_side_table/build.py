"""Build catalog item F009 Slim Side Table and export it.

Run:
    blender -b --factory-startup --python build.py -- --outdir <dir>

Units are meters. The table is 18 x 18 x 22 inches, origin at the floor
center, front facing -Y. Only bpy, bmesh, and mathutils are used.
"""

import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector


INCH = 0.0254
WIDTH = 18.0 * INCH
DEPTH = 18.0 * INCH
HEIGHT = 22.0 * INCH

# Tray top: shallow recessed deck inside a rounded rim, like the reference.
TOP_THICK = 0.022
RIM_W = 0.014
RIM_LIP = 0.011
CORNER_R = 0.020
CORNER_SEGMENTS = 5

# Slim tapered legs, slightly splayed, kept inside the top footprint.
LEG_HALF_TOP = 0.018
LEG_HALF_BOT = 0.011
LEG_INSET_TOP = 0.042
LEG_INSET_BOT = 0.026

TOLERANCE = 0.02


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


def new_material(name, color, roughness, coat=0.12):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.35
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = coat
    if "Coat Roughness" in bsdf.inputs:
        bsdf.inputs["Coat Roughness"].default_value = 0.28
    return mat


def _rounded_rect(bm, half_x, half_y, radius, segments, z):
    """CCW loop of a rounded rectangle, seen from above. Flat sides hit half_x/half_y."""
    radius = min(radius, half_x - 1e-4, half_y - 1e-4)
    corners = (
        (half_x - radius, -half_y + radius, -math.pi / 2.0, 0.0),
        (half_x - radius, half_y - radius, 0.0, math.pi / 2.0),
        (-half_x + radius, half_y - radius, math.pi / 2.0, math.pi),
        (-half_x + radius, -half_y + radius, math.pi, 3.0 * math.pi / 2.0),
    )
    verts = []
    for cx, cy, a0, a1 in corners:
        for i in range(segments):
            angle = a0 + (a1 - a0) * (i / segments)
            verts.append(
                bm.verts.new((cx + radius * math.cos(angle), cy + radius * math.sin(angle), z))
            )
    return verts


def _bridge(bm, lower, upper):
    count = len(lower)
    faces = []
    for i in range(count):
        j = (i + 1) % count
        faces.append(bm.faces.new((lower[i], lower[j], upper[j], upper[i])))
    return faces


def _fan(bm, loop, center, up=True):
    faces = []
    count = len(loop)
    for i in range(count):
        j = (i + 1) % count
        if up:
            faces.append(bm.faces.new((loop[i], loop[j], center)))
        else:
            faces.append(bm.faces.new((loop[i], center, loop[j])))
    return faces


def _build_tray(bm):
    """Rounded tray top: rim, recessed deck, and a flat underside."""
    half_x = WIDTH / 2.0
    half_y = DEPTH / 2.0
    z_top = HEIGHT
    z_deck = HEIGHT - RIM_LIP
    z_bot = HEIGHT - TOP_THICK
    inner_r = CORNER_R - RIM_W
    if inner_r <= 0.002:
        raise RuntimeError("rim is wider than the corner radius")

    outer_top = _rounded_rect(bm, half_x, half_y, CORNER_R, CORNER_SEGMENTS, z_top)
    inner_top = _rounded_rect(bm, half_x - RIM_W, half_y - RIM_W, inner_r, CORNER_SEGMENTS, z_top)
    inner_deck = _rounded_rect(bm, half_x - RIM_W, half_y - RIM_W, inner_r, CORNER_SEGMENTS, z_deck)
    outer_bot = _rounded_rect(bm, half_x, half_y, CORNER_R, CORNER_SEGMENTS, z_bot)

    _bridge(bm, outer_bot, outer_top)
    _bridge(bm, outer_top, inner_top)
    _bridge(bm, inner_top, inner_deck)
    deck_center = bm.verts.new((0.0, 0.0, z_deck))
    _fan(bm, inner_deck, deck_center, up=True)
    bot_center = bm.verts.new((0.0, 0.0, z_bot))
    _fan(bm, outer_bot, bot_center, up=False)


def _add_leg(bm, x_sign, y_sign):
    """Axis-aligned tapered leg. Centers shift outward toward the floor so the sides stay planar."""
    cx0 = x_sign * (WIDTH / 2.0 - LEG_INSET_BOT)
    cy0 = y_sign * (DEPTH / 2.0 - LEG_INSET_BOT)
    cx1 = x_sign * (WIDTH / 2.0 - LEG_INSET_TOP)
    cy1 = y_sign * (DEPTH / 2.0 - LEG_INSET_TOP)
    z1 = HEIGHT - TOP_THICK + 0.002

    def ring(cx, cy, half, z):
        return [
            bm.verts.new((cx - half, cy - half, z)),
            bm.verts.new((cx + half, cy - half, z)),
            bm.verts.new((cx + half, cy + half, z)),
            bm.verts.new((cx - half, cy + half, z)),
        ]

    bottom = ring(cx0, cy0, LEG_HALF_BOT, 0.0)
    top = ring(cx1, cy1, LEG_HALF_TOP, z1)
    bm.faces.new((bottom[0], bottom[3], bottom[2], bottom[1]))
    bm.faces.new((top[0], top[1], top[2], top[3]))
    vertical = []
    for i in range(4):
        j = (i + 1) % 4
        bm.faces.new((bottom[i], bottom[j], top[j], top[i]))
        edge = bm.edges.get((bottom[i], top[i]))
        if edge is not None:
            vertical.append(edge)
    bmesh.ops.bevel(
        bm,
        geom=vertical,
        offset=0.0012,
        segments=1,
        profile=0.5,
        affect="EDGES",
        clamp_overlap=True,
    )





def build_table():
    bm = bmesh.new()
    _build_tray(bm)
    for x_sign in (-1.0, 1.0):
        for y_sign in (-1.0, 1.0):
            _add_leg(bm, x_sign, y_sign)

    bm.normal_update()
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.edges.ensure_lookup_table()
    open_edges = [edge for edge in bm.edges if not edge.is_manifold]
    if open_edges:
        raise RuntimeError(f"mesh is not manifold ({len(open_edges)} edges)")

    # Every triangle of the recessed deck sits on one plane. Leg tops are lower.
    deck_z = HEIGHT - RIM_LIP
    deck_faces = {
        face
        for face in bm.faces
        if face.normal.z > 0.9 and abs(face.calc_center_median().z - deck_z) < 0.001
    }
    if len(deck_faces) < 4:
        raise RuntimeError(f"expected a recessed deck, found {len(deck_faces)} faces")
    for face in bm.faces:
        face.material_index = 1 if face in deck_faces else 0

    mesh = bpy.data.meshes.new("F009")
    bm.to_mesh(mesh)
    bm.free()
    mesh.validate(clean_customdata=False)

    obj = bpy.data.objects.new("F009", mesh)
    bpy.context.scene.collection.objects.link(obj)
    frame = new_material("F009_Birch", (0.66, 0.52, 0.36), 0.48, coat=0.08)
    deck_mat = new_material("F009_BirchDeck", (0.55, 0.42, 0.28), 0.55, coat=0.04)
    obj.data.materials.append(frame)
    obj.data.materials.append(deck_mat)

    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(45))
    # Keep the rounded top corners smooth. Flat-shade the deck, rim, and the
    # long leg faces so a triangulated quad does not pick up a shading crease.
    for poly in obj.data.polygons:
        if abs(poly.normal.z) > 0.95 or poly.area > 0.004:
            poly.use_smooth = False
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    obj.select_set(False)
    return obj


def world_bounds(objects):
    xs, ys, zs = [], [], []
    for obj in objects:
        for corner in obj.bound_box:
            point = obj.matrix_world @ Vector(corner)
            xs.append(point.x)
            ys.append(point.y)
            zs.append(point.z)
    return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)


def bounds_dict(bounds):
    min_x, max_x, min_y, max_y, min_z, max_z = bounds

    def r(value):
        value = round(float(value), 6)
        return 0.0 if value == 0.0 else value

    return {
        "min": {"x": r(min_x), "y": r(min_y), "z": r(min_z)},
        "max": {"x": r(max_x), "y": r(max_y), "z": r(max_z)},
        "width": r(max_x - min_x),
        "depth": r(max_y - min_y),
        "height": r(max_z - min_z),
    }


def triangle_count(obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    mesh.calc_loop_triangles()
    count = len(mesh.loop_triangles)
    evaluated.to_mesh_clear()
    return count


def check_dimensions(size):
    nominal = (WIDTH, DEPTH, HEIGHT)
    labels = ("width", "depth", "height")
    for label, got, expect in zip(labels, size, nominal):
        err = abs(got - expect) / expect
        print(f"{label}: {got:.6f} m (nominal {expect:.6f}, error {err:.4%})")
        if err > TOLERANCE:
            raise SystemExit(f"{label} is outside the {TOLERANCE:.0%} tolerance")


def export_glb(obj, path):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.gltf(
        filepath=str(path),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_texcoords=False,
        export_normals=True,
        export_materials="EXPORT",
        export_yup=True,
    )


def verify_imported_glb(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported = [obj for obj in bpy.data.objects if obj not in before and obj.type == "MESH"]
    if not imported:
        raise RuntimeError("glTF import produced no mesh")
    bounds = world_bounds(imported)
    for obj in list(bpy.data.objects):
        if obj not in before:
            mesh = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if isinstance(mesh, bpy.types.Mesh) and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
    return bounds


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
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Base Contrast"
    scene.view_settings.exposure = -0.4

    world = bpy.data.worlds.new("PreviewWorld")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.63, 0.64, 0.66, 1.0)
    bg.inputs["Strength"].default_value = 0.35

    preview = bpy.data.collections.new("Preview")
    scene.collection.children.link(preview)

    floor_mesh = bpy.data.meshes.new("PreviewFloor")
    floor_bm = bmesh.new()
    bmesh.ops.create_grid(floor_bm, x_segments=1, y_segments=1, size=1.4)
    floor_bm.to_mesh(floor_mesh)
    floor_bm.free()
    floor = bpy.data.objects.new("PreviewFloor", floor_mesh)
    floor.location = (0.0, 0.0, -0.001)
    preview.objects.link(floor)
    floor_mat = new_material("PreviewFloor", (0.42, 0.41, 0.40), 0.9, coat=0.0)
    floor.data.materials.append(floor_mat)

    cam_data = bpy.data.cameras.new("PreviewCamera")
    cam_data.lens = 50
    cam = bpy.data.objects.new("PreviewCamera", cam_data)
    cam.location = (0.52, -0.64, 0.78)
    preview.objects.link(cam)
    look_at(cam, target)
    scene.camera = cam

    def add_light(name, kind, location, energy, size=0.35, rotation=None):
        light_data = bpy.data.lights.new(name, kind)
        light_data.energy = energy
        if kind == "AREA":
            light_data.size = size
        if kind == "SUN":
            light_data.angle = math.radians(6)
        light = bpy.data.objects.new(name, light_data)
        light.location = location
        if rotation is not None:
            light.rotation_euler = rotation
        else:
            look_at(light, target)
        preview.objects.link(light)
        return light

    add_light("Key", "AREA", (0.55, -0.40, 1.05), 28, size=0.55)
    add_light("Fill", "AREA", (-0.75, -0.30, 0.6), 10, size=0.7)
    add_light("Rim", "AREA", (0.05, 0.7, 0.75), 6, size=0.35)
    add_light(
        "Sun",
        "SUN",
        (0.0, 0.0, 2.0),
        1.1,
        rotation=(math.radians(52), math.radians(6), math.radians(28)),
    )

    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
        if hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
            scene.eevee.taa_render_samples = 24
    except (TypeError, ValueError):
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.display.shading.light = "STUDIO"
        scene.display.shading.color_type = "MATERIAL"


def main():
    outdir = parse_outdir()
    reset_scene()
    table = build_table()

    bounds = world_bounds([table])
    measured = bounds_dict(bounds)
    size = (measured["width"], measured["depth"], measured["height"])
    tris = triangle_count(table)
    print(
        f"F009 bbox m: {measured['width']:.6f} x {measured['depth']:.6f} x {measured['height']:.6f}"
    )
    print(f"triangles: {tris}")
    check_dimensions(size)
    if tris > 30000:
        raise SystemExit(f"triangle count {tris} exceeds 30000")

    glb_path = outdir / "model.glb"
    export_glb(table, glb_path)
    imported = bounds_dict(verify_imported_glb(glb_path))
    print(
        "imported glb bbox m: "
        f"{imported['width']:.6f} x {imported['depth']:.6f} x {imported['height']:.6f}"
    )
    check_dimensions((imported["width"], imported["depth"], imported["height"]))

    metadata = {
        "id": "F009",
        "name": "Slim Side Table",
        "category": "Table",
        "style": "Minimal",
        "room": "Living Room",
        "price_usd": 99,
        "dimensions_in": {"width": 18, "depth": 18, "height": 22},
        "dimensions_m": {"width": WIDTH, "depth": DEPTH, "height": HEIGHT},
        "bounding_box_m": imported,
    }
    (outdir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")

    setup_preview((0.0, 0.0, HEIGHT * 0.42))
    preview_path = outdir / "preview.png"
    bpy.context.scene.render.filepath = str(preview_path)
    bpy.ops.render.render(write_still=True)

    blend_path = outdir / "model.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    print(f"wrote {glb_path}")
    print(f"wrote {blend_path}")
    print(f"wrote {preview_path}")


if __name__ == "__main__":
    main()
