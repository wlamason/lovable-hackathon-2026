"""Build F007 Oakline Round Coffee Table and export glTF, blend, preview, metadata.

Run:
    blender -b --factory-startup --python build.py -- --outdir <dir>

Default outdir is this script's folder. Units are meters (1 Blender unit = 1 m).
Width along X, depth along Y, height along Z. Front faces -Y.
Origin is the bottom center of the footprint.
"""

import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector


INCH = 0.0254

# Catalog dimensions.
WIDTH_IN = 36.0
DEPTH_IN = 36.0
HEIGHT_IN = 16.0
WIDTH_M = WIDTH_IN * INCH
DEPTH_M = DEPTH_IN * INCH
HEIGHT_M = HEIGHT_IN * INCH

# Pale oak, given as sRGB (Principled sockets store linear). Light enough
# for whitewashed Japandi oak, warm enough to read as wood under AgX.
TOP_SRGB = (0.83, 0.68, 0.49)
BASE_SRGB = (0.72, 0.56, 0.38)


def srgb_to_linear(rgb):
    def channel(u):
        if u <= 0.04045:
            return u / 12.92
        return ((u + 0.055) / 1.055) ** 2.4

    return tuple(channel(c) for c in rgb)


def parse_outdir():
    argv = sys.argv
    args = argv[argv.index("--") + 1 :] if "--" in argv else []
    outdir = Path(__file__).resolve().parent
    if "--outdir" in args:
        outdir = Path(args[args.index("--outdir") + 1]).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    return outdir


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = "METERS"
    return scene


def make_material(name, srgb, roughness, specular=0.32):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*srgb_to_linear(srgb), 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = 0.0
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = specular
    elif "Specular" in bsdf.inputs:
        bsdf.inputs["Specular"].default_value = specular
    return mat


def new_object(name, bm, material):
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.normal_update()
    top_face = max(bm.faces, key=lambda f: f.calc_center_median().z)
    if top_face.normal.z < 0.0:
        bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
        bm.normal_update()

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    mesh.validate(verbose=False)
    mesh.update()

    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    for poly in mesh.polygons:
        poly.use_smooth = True
    return obj


def dedupe(points, eps=1e-9):
    cleaned = []
    for point in points:
        if not cleaned:
            cleaned.append(point)
            continue
        pr, pz = cleaned[-1]
        if (point[0] - pr) ** 2 + (point[1] - pz) ** 2 > eps:
            cleaned.append(point)
    return cleaned


def slab_profile(radius, z_top, thickness, edge_radius, bottom_radius, n_edge, n_bottom):
    """(r, z) profile of a disc edge, top rim to bottom rim. Outermost r == radius."""
    z_bot = z_top - thickness
    if z_top - edge_radius <= z_bot + bottom_radius:
        raise RuntimeError("slab edge radii do not fit in the thickness")

    points = []
    cr = radius - edge_radius
    cz = z_top - edge_radius
    for i in range(n_edge + 1):
        angle = math.pi / 2.0 * (1.0 - i / n_edge)
        points.append((cr + edge_radius * math.cos(angle), cz + edge_radius * math.sin(angle)))

    points.append((radius, z_bot + bottom_radius))

    crb = radius - bottom_radius
    czb = z_bot + bottom_radius
    for i in range(1, n_bottom + 1):
        angle = -(math.pi / 2.0) * (i / n_bottom)
        points.append(
            (crb + bottom_radius * math.cos(angle), czb + bottom_radius * math.sin(angle))
        )
    return dedupe(points)


def add_revolved_disc(bm, profile, segments):
    rings = []
    for radius, z in profile:
        ring = []
        for i in range(segments):
            angle = 2.0 * math.pi * i / segments
            ring.append(bm.verts.new((radius * math.cos(angle), radius * math.sin(angle), z)))
        rings.append(ring)

    for upper, lower in zip(rings, rings[1:]):
        for i in range(segments):
            j = (i + 1) % segments
            bm.faces.new((upper[i], upper[j], lower[j], lower[i]))

    top_center = bm.verts.new((0.0, 0.0, profile[0][1]))
    bot_center = bm.verts.new((0.0, 0.0, profile[-1][1]))
    for i in range(segments):
        j = (i + 1) % segments
        bm.faces.new((top_center, rings[0][i], rings[0][j]))
        bm.faces.new((bot_center, rings[-1][j], rings[-1][i]))


def octagon_offsets(size, chamfer_frac):
    """CCW offsets in (tangent, radial) for a square with clipped corners."""
    half = size * 0.5
    cut = half * chamfer_frac
    return (
        (half, half - cut),
        (half - cut, half),
        (-(half - cut), half),
        (-half, half - cut),
        (-half, -(half - cut)),
        (-(half - cut), -half),
        (half - cut, -half),
        (half, -(half - cut)),
    )


def add_curved_leg(bm, angle, stations, chamfer_frac):
    """Tapered, gently splayed leg. stations: (z, center_radius, size), top to bottom."""
    radial = Vector((math.cos(angle), math.sin(angle), 0.0))
    tangent = Vector((-math.sin(angle), math.cos(angle), 0.0))
    rings = []
    for z, center_r, size in stations:
        center = radial * center_r + Vector((0.0, 0.0, z))
        ring = []
        for tx, ry in octagon_offsets(size, chamfer_frac):
            ring.append(bm.verts.new(center + tangent * tx + radial * ry))
        rings.append(ring)

    count = len(rings[0])
    for upper, lower in zip(rings, rings[1:]):
        for i in range(count):
            j = (i + 1) % count
            bm.faces.new((upper[i], lower[i], lower[j], upper[j]))

    bm.faces.new(rings[0])
    bm.faces.new(list(reversed(rings[-1])))


def sample_station(stations, z):
    ordered = sorted(stations, key=lambda item: item[0])
    if z <= ordered[0][0]:
        return ordered[0][1], ordered[0][2]
    if z >= ordered[-1][0]:
        return ordered[-1][1], ordered[-1][2]
    for left, right in zip(ordered, ordered[1:]):
        if left[0] <= z <= right[0]:
            span = right[0] - left[0]
            t = 0.0 if span == 0.0 else (z - left[0]) / span
            radius = left[1] + (right[1] - left[1]) * t
            size = left[2] + (right[2] - left[2]) * t
            return radius, size
    return ordered[-1][1], ordered[-1][2]


def leg_outer_radius(stations, chamfer_frac):
    """Largest distance from the origin of any leg corner."""
    farthest = 0.0
    for _z, center_r, size in stations:
        half = size * 0.5
        cut = half * chamfer_frac
        # Outer corners sit at radial = +half, tangent = ±(half - cut).
        corner = math.hypot(center_r + half, half - cut)
        farthest = max(farthest, corner)
    return farthest


def build_table():
    top_mat = make_material("F007_OakTop", TOP_SRGB, roughness=0.46, specular=0.36)
    base_mat = make_material("F007_OakBase", BASE_SRGB, roughness=0.55, specular=0.32)

    top_thickness = 1.125 * INCH
    top_z = HEIGHT_M
    top_radius = WIDTH_M * 0.5
    edge_r = 0.28 * INCH
    bottom_ease = 0.09 * INCH

    bm = bmesh.new()
    profile = slab_profile(
        top_radius, top_z, top_thickness, edge_r, bottom_ease, n_edge=5, n_bottom=2
    )
    add_revolved_disc(bm, profile, segments=80)
    top = new_object("F007_top", bm, top_mat)

    # Leg centerline, inches then converted. Gentle outward curve, thicker under the top.
    # z is height of each cross-section station.
    underside = top_z - top_thickness
    leg_top_z = underside + 0.12 * INCH
    chamfer = 0.20
    stations_in = (
        (leg_top_z / INCH, 11.35, 1.90),
        (9.25, 11.95, 1.74),
        (4.50, 12.58, 1.60),
        (0.0, 13.20, 1.46),
    )
    stations = tuple((z * INCH, r * INCH, s * INCH) for z, r, s in stations_in)

    outer = leg_outer_radius(stations, chamfer)
    if outer >= top_radius - 0.01:
        raise RuntimeError(
            f"legs extend too far ({outer:.4f} m) for the {top_radius:.4f} m top"
        )

    # Lower shelf meets the inner face of each leg with a short buried overlap.
    shelf_thickness = 0.78 * INCH
    shelf_bottom = 3.55 * INCH
    shelf_mid = shelf_bottom + shelf_thickness * 0.5
    center_r, leg_size = sample_station(stations, shelf_mid)
    inner_face = center_r - leg_size * 0.5
    overlap = 0.58 * leg_size
    shelf_radius = inner_face + overlap
    # Keep the shelf edge inside the leg center so it cannot poke out the sides.
    shelf_radius = min(shelf_radius, center_r - 0.04 * INCH)

    for z_check in (shelf_bottom, shelf_bottom + shelf_thickness):
        cr, sz = sample_station(stations, z_check)
        if shelf_radius < (cr - sz * 0.5) - 0.002:
            raise RuntimeError("lower shelf does not meet the legs")

    parts = [top]
    # Gaps face the front (-Y) and the back: legs on the diagonals.
    for index in range(4):
        angle = math.pi / 4.0 + index * (math.pi / 2.0)
        bm = bmesh.new()
        add_curved_leg(bm, angle, stations, chamfer)
        parts.append(new_object(f"F007_leg_{index}", bm, base_mat))

    bm = bmesh.new()
    shelf_profile = slab_profile(
        shelf_radius,
        shelf_bottom + shelf_thickness,
        shelf_thickness,
        edge_radius=0.10 * INCH,
        bottom_radius=0.06 * INCH,
        n_edge=3,
        n_bottom=2,
    )
    add_revolved_disc(bm, shelf_profile, segments=64)
    parts.append(new_object("F007_shelf", bm, base_mat))
    return parts


def join_parts(parts):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in parts:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = "F007"
    obj.data.name = "F007"
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.context.scene.cursor.location = (0.0, 0.0, 0.0)
    bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
    return obj


def measured_bbox(obj):
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    xs = [p.x for p in points]
    ys = [p.y for p in points]
    zs = [p.z for p in points]
    min_v = Vector((min(xs), min(ys), min(zs)))
    max_v = Vector((max(xs), max(ys), max(zs)))
    return min_v, max_v


def triangle_count(obj):
    mesh = obj.data
    mesh.calc_loop_triangles()
    return len(mesh.loop_triangles)


def assert_proportions(min_v, max_v):
    size = max_v - min_v
    targets = (WIDTH_M, DEPTH_M, HEIGHT_M)
    names = ("width", "depth", "height")
    for measured, target, name in zip(size, targets, names):
        err = abs(measured - target) / target
        print(f"{name}: {measured:.6f} m  target {target:.6f} m  error {err * 100:.3f}%")
        if err > 0.02:
            raise SystemExit(f"{name} is outside the 2% tolerance")
    if abs(min_v.z) > 0.002:
        raise SystemExit(f"model does not sit on Z=0 (min z = {min_v.z:.6f})")
    if abs((min_v.x + max_v.x) * 0.5) > 0.002 or abs((min_v.y + max_v.y) * 0.5) > 0.002:
        raise SystemExit("footprint is not centered on the origin")
    return size


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
        export_cameras=False,
        export_lights=False,
    )


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_area_light(name, location, energy, size, color, target):
    light = bpy.data.lights.new(name, "AREA")
    light.energy = energy
    light.size = size
    light.color = color
    obj = bpy.data.objects.new(name, light)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    look_at(obj, target)
    return obj


def setup_preview(scene):
    look = Vector((0.0, 0.0, 0.15))
    direction = Vector((0.70, -1.05, 0.46))
    direction.normalize()
    cam_data = bpy.data.cameras.new("PreviewCamera")
    cam_data.lens = 50
    cam_data.clip_start = 0.01
    cam_data.clip_end = 50
    cam = bpy.data.objects.new("PreviewCamera", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = look + direction * 2.15
    look_at(cam, look)
    scene.camera = cam

    world = bpy.data.worlds.new("PreviewWorld")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.68, 0.66, 0.63, 1.0)
    bg.inputs["Strength"].default_value = 0.55

    target = (0.0, 0.0, 0.16)
    # Keep the key modest so the flat oak top does not blow out to white.
    add_area_light("Key", (1.05, -1.25, 1.15), 70, 1.6, (1.0, 0.95, 0.88), target)
    add_area_light("Fill", (-1.20, -0.45, 0.70), 22, 1.8, (0.88, 0.92, 1.0), target)
    add_area_light("Rim", (-0.40, 1.30, 0.85), 28, 1.1, (1.0, 0.96, 0.90), target)
    add_area_light("Bounce", (0.0, -0.15, -0.20), 8, 1.4, (1.0, 0.94, 0.86), target)

    bpy.ops.mesh.primitive_plane_add(size=6.0, location=(0.0, 0.0, -0.002))
    floor = bpy.context.active_object
    floor.name = "PreviewFloor"
    floor_mat = make_material("PreviewFloor", (0.80, 0.78, 0.75), roughness=0.92, specular=0.12)
    floor.data.materials.append(floor_mat)

    scene.render.resolution_x = 512
    scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = 0.0


def configure_engine(scene):
    # Eevee Next needs a GPU context that this VM often does not have.
    # Cycles CPU is reliable and still quick at 512px.
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 64
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
    if hasattr(scene.cycles, "use_adaptive_sampling"):
        scene.cycles.use_adaptive_sampling = True
    print("render engine: CYCLES CPU")


def write_metadata(path, min_v, max_v, size):
    def rnd(value):
        return round(float(value), 6)

    payload = {
        "id": "F007",
        "name": "Oakline Round Coffee Table",
        "category": "Table",
        "style": "Japandi",
        "room": "Living Room",
        "price_usd": 219,
        "dimensions_in": {
            "width": WIDTH_IN,
            "depth": DEPTH_IN,
            "height": HEIGHT_IN,
        },
        "dimensions_m": {
            "width": rnd(WIDTH_M),
            "depth": rnd(DEPTH_M),
            "height": rnd(HEIGHT_M),
        },
        "bounding_box_m": {
            "min": {"x": rnd(min_v.x), "y": rnd(min_v.y), "z": rnd(min_v.z)},
            "max": {"x": rnd(max_v.x), "y": rnd(max_v.y), "z": rnd(max_v.z)},
            "width": rnd(size.x),
            "depth": rnd(size.y),
            "height": rnd(size.z),
        },
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main():
    outdir = parse_outdir()
    scene = reset_scene()
    parts = build_table()
    table = join_parts(parts)
    min_v, max_v = measured_bbox(table)
    size = assert_proportions(min_v, max_v)
    tris = triangle_count(table)
    print(f"triangles: {tris}")
    print(f"bbox min: ({min_v.x:.6f}, {min_v.y:.6f}, {min_v.z:.6f})")
    print(f"bbox max: ({max_v.x:.6f}, {max_v.y:.6f}, {max_v.z:.6f})")
    if tris > 30000:
        raise SystemExit(f"triangle count {tris} exceeds 30000")

    glb_path = outdir / "model.glb"
    export_glb(table, glb_path)
    print(f"exported {glb_path}")

    blend_path = outdir / "model.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), compress=True)
    print(f"saved {blend_path}")

    metadata_path = outdir / "metadata.json"
    write_metadata(metadata_path, min_v, max_v, size)
    print(f"wrote {metadata_path}")

    setup_preview(scene)
    configure_engine(scene)
    preview_path = outdir / "preview.png"
    scene.render.filepath = str(preview_path)
    bpy.ops.render.render(write_still=True)
    print(f"rendered {preview_path}")


if __name__ == "__main__":
    main()
