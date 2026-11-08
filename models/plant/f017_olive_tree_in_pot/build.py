"""F017 Olive Tree in Pot — deterministic Blender builder.

Run:
  blender -b --factory-startup --python build.py -- --outdir <dir>
"""

import json
import math
import os
import random
import sys

import bmesh
import bpy
from mathutils import Quaternion, Vector

# Catalog size: 22 x 22 x 54 inches. Seed fixes every leaf placement.
SEED = 17017
INCH = 0.0254
TARGET_W = 22 * INCH
TARGET_D = 22 * INCH
TARGET_H = 54 * INCH

POT_SEGMENTS = 48
TRUNK_SIDES = 8
BRANCH_SIDES = 6


def srgb_to_linear(rgb):
    def chan(u):
        return u / 12.92 if u <= 0.04045 else ((u + 0.055) / 1.055) ** 2.4

    return tuple(chan(c) for c in rgb)


def parse_outdir():
    out = os.path.dirname(os.path.abspath(__file__))
    if "--" in sys.argv:
        args = sys.argv[sys.argv.index("--") + 1 :]
        if "--outdir" in args:
            out = os.path.abspath(args[args.index("--outdir") + 1])
    os.makedirs(out, exist_ok=True)
    return out


def make_material(name, srgb, roughness, specular=0.4):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = (*srgb_to_linear(srgb), 1.0)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*srgb_to_linear(srgb), 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = 0.0
    spec = bsdf.inputs.get("Specular IOR Level")
    if spec is not None:
        spec.default_value = specular
    return mat


def new_face(bm, verts, mat, expect):
    face = bm.faces.new(verts)
    normal = (verts[1].co - verts[0].co).cross(verts[2].co - verts[0].co)
    if normal.dot(expect) < 0:
        bm.faces.remove(face)
        face = bm.faces.new(list(reversed(verts)))
    face.material_index = mat
    face.smooth = True
    return face


def build_pot(bm, materials):
    """Handmade ceramic planter. Profile is (radius, height)."""
    mat_body, mat_rim = materials
    profile = [
        (0.000, 0.000),
        (0.098, 0.000),
        (0.108, 0.010),
        (0.114, 0.024),
        (0.100, 0.040),
        (0.112, 0.095),
        (0.128, 0.165),
        (0.138, 0.215),
        (0.130, 0.255),
        (0.136, 0.280),
        (0.150, 0.296),
        (0.158, 0.306),
        (0.140, 0.306),
        (0.132, 0.296),
        (0.124, 0.282),
        (0.118, 0.270),
    ]
    kinds = [
        "down",
        "outer",
        "outer",
        "outer",
        "outer",
        "outer",
        "outer",
        "outer",
        "outer",
        "outer",
        "outer",
        "up",
        "inner",
        "inner",
        "inner",
    ]
    segments = POT_SEGMENTS
    rings = []
    for radius, z in profile:
        if radius < 1e-8:
            rings.append([bm.verts.new((0.0, 0.0, z))])
            continue
        ring = []
        for s in range(segments):
            angle = 2.0 * math.pi * s / segments
            ring.append(
                bm.verts.new((radius * math.cos(angle), radius * math.sin(angle), z))
            )
        rings.append(ring)

    for i, kind in enumerate(kinds):
        mat = mat_rim if i >= 9 and kind != "inner" else mat_body
        ring_a = rings[i]
        ring_b = rings[i + 1]
        if len(ring_a) == 1:
            center = ring_a[0]
            expect = Vector((0.0, 0.0, -1.0 if kind == "down" else 1.0))
            for s in range(segments):
                new_face(
                    bm,
                    (center, ring_b[(s + 1) % segments], ring_b[s]),
                    mat,
                    expect,
                )
            continue
        for s in range(segments):
            vs = (
                ring_a[s],
                ring_a[(s + 1) % segments],
                ring_b[(s + 1) % segments],
                ring_b[s],
            )
            mid = sum((v.co for v in vs), Vector()) / 4.0
            if kind == "up":
                expect = Vector((0.0, 0.0, 1.0))
            elif kind == "down":
                expect = Vector((0.0, 0.0, -1.0))
            elif kind == "inner":
                expect = Vector((-mid.x, -mid.y, 0.0))
            else:
                expect = Vector((mid.x, mid.y, 0.2))
            new_face(bm, vs, mat, expect)


def build_soil(bm, mat):
    segments = 40
    rings_n = 3
    radius = 0.122
    base_z = 0.268
    rows = []
    for i in range(rings_n + 1):
        t = i / rings_n
        r = radius * t
        z = base_z + 0.016 * (1.0 - t * t)
        if i == 0:
            rows.append([bm.verts.new((0.0, 0.0, z))])
            continue
        ring = []
        for s in range(segments):
            angle = 2.0 * math.pi * s / segments
            ring.append(bm.verts.new((r * math.cos(angle), r * math.sin(angle), z)))
        rows.append(ring)
    for i in range(rings_n):
        if len(rows[i]) == 1:
            center = rows[i][0]
            for s in range(segments):
                new_face(
                    bm,
                    (center, rows[i + 1][s], rows[i + 1][(s + 1) % segments]),
                    mat,
                    Vector((0.0, 0.0, 1.0)),
                )
            continue
        for s in range(segments):
            new_face(
                bm,
                (
                    rows[i][s],
                    rows[i][(s + 1) % segments],
                    rows[i + 1][(s + 1) % segments],
                    rows[i + 1][s],
                ),
                mat,
                Vector((0.0, 0.0, 1.0)),
            )


def catmull(p0, p1, p2, p3, t):
    t2 = t * t
    t3 = t2 * t
    return 0.5 * (
        (2.0 * p1)
        + (-p0 + p2) * t
        + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2
        + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t3
    )


def sample_curve(points, per_seg):
    padded = [points[0]] + list(points) + [points[-1]]
    out = []
    for i in range(1, len(padded) - 2):
        for s in range(per_seg):
            out.append(catmull(padded[i - 1], padded[i], padded[i + 1], padded[i + 2], s / per_seg))
    out.append(points[-1])
    return out


def parallel_frames(points):
    tangents = []
    for i, point in enumerate(points):
        if i == 0:
            tangent = points[1] - points[0]
        elif i == len(points) - 1:
            tangent = points[-1] - points[-2]
        else:
            tangent = points[i + 1] - points[i - 1]
        if tangent.length < 1e-8:
            tangent = Vector((0.0, 0.0, 1.0))
        tangents.append(tangent.normalized())

    reference = Vector((0.0, 1.0, 0.0))
    if abs(tangents[0].dot(reference)) > 0.9:
        reference = Vector((1.0, 0.0, 0.0))
    normal = (reference - tangents[0] * reference.dot(tangents[0])).normalized()
    normals = [normal]
    for i in range(1, len(points)):
        axis = tangents[i - 1].cross(tangents[i])
        if axis.length < 1e-6:
            carried = normals[-1] - tangents[i] * normals[-1].dot(tangents[i])
            if carried.length < 1e-6:
                carried = Vector((1.0, 0.0, 0.0))
            normals.append(carried.normalized())
            continue
        angle = math.acos(max(-1.0, min(1.0, tangents[i - 1].dot(tangents[i]))))
        rotated = Quaternion(axis.normalized(), angle) @ normals[-1]
        carried = rotated - tangents[i] * rotated.dot(tangents[i])
        normals.append(carried.normalized())
    binormals = [tangents[i].cross(normals[i]).normalized() for i in range(len(points))]
    return tangents, normals, binormals


def add_tube(bm, points, radii, sides, mat, cap=True):
    tangents, normals, binormals = parallel_frames(points)
    rings = []
    for i, center in enumerate(points):
        ring = []
        radius = radii[i]
        rx = radius * (1.0 + 0.07 * math.sin(i * 0.85))
        ry = radius * (0.88 + 0.06 * math.sin(i * 1.27 + 0.6))
        for s in range(sides):
            angle = 2.0 * math.pi * s / sides
            bulge = 1.0 + 0.05 * math.sin(s * 3.0 + i * 0.65)
            co = (
                center
                + normals[i] * math.cos(angle) * rx * bulge
                + binormals[i] * math.sin(angle) * ry * bulge
            )
            ring.append(bm.verts.new(co))
        rings.append(ring)
    for i in range(len(rings) - 1):
        for s in range(sides):
            new_face(
                bm,
                (
                    rings[i][s],
                    rings[i][(s + 1) % sides],
                    rings[i + 1][(s + 1) % sides],
                    rings[i + 1][s],
                ),
                mat,
                normals[i],
            )
    if cap:
        for end, sign in ((0, -1.0), (len(rings) - 1, 1.0)):
            center = bm.verts.new(points[end])
            expect = tangents[end] * sign
            ring = rings[end]
            order = range(sides) if sign > 0 else range(sides - 1, -1, -1)
            seq = list(order)
            for s in range(sides):
                new_face(
                    bm,
                    (center, ring[seq[s]], ring[seq[(s + 1) % sides]]),
                    mat,
                    expect,
                )


def build_wood(bm, mat):
    controls = [
        Vector((0.000, 0.000, 0.240)),
        Vector((0.008, -0.010, 0.330)),
        Vector((0.014, -0.020, 0.430)),
        Vector((0.006, -0.012, 0.530)),
        Vector((-0.006, -0.004, 0.630)),
    ]
    radius_controls = [0.022, 0.016, 0.0135, 0.011, 0.0085]
    spine = sample_curve(controls, 3)
    radii = sample_curve(radius_controls, 3)
    # Knots where an olive trunk thickens.
    for index in (4, 11, 18):
        if index < len(radii):
            radii[index] *= 1.18
    add_tube(bm, spine, radii, TRUNK_SIDES, mat, cap=True)

    branches = [
        (0.50, Vector((-0.12, 0.02, 0.78)), 0.0090, 0.0026, 0.05),
        (0.52, Vector((0.125, -0.03, 0.84)), 0.0085, 0.0024, 0.055),
        (0.47, Vector((0.02, -0.135, 0.74)), 0.0080, 0.0022, 0.04),
        (0.56, Vector((-0.03, 0.12, 0.82)), 0.0072, 0.0020, 0.035),
        (0.60, Vector((0.03, -0.02, 1.08)), 0.0070, 0.0018, 0.02),
    ]
    for start_z, end, r0, r1, lift in branches:
        origin = min(spine, key=lambda p: abs(p.z - start_z))
        mid = (origin + end) * 0.5
        mid.z += lift
        outward = end - origin
        if outward.length > 1e-6:
            mid += outward.normalized() * 0.02
        bezier = []
        steps = 5
        for s in range(steps):
            t = s / (steps - 1)
            bezier.append(
                (1 - t) ** 2 * origin + 2 * (1 - t) * t * mid + t ** 2 * end
            )
        curve = sample_curve(bezier, 2)
        br = [r0 * (1 - i / (len(curve) - 1)) + r1 * (i / (len(curve) - 1)) for i in range(len(curve))]
        add_tube(bm, curve, br, BRANCH_SIDES, mat, cap=True)


def unit_icosphere(subdiv):
    src = bmesh.new()
    bmesh.ops.create_icosphere(src, subdivisions=subdiv, radius=1.0)
    src.verts.ensure_lookup_table()
    src.faces.ensure_lookup_table()
    verts = [v.co.copy() for v in src.verts]
    faces = [tuple(v.index for v in face.verts) for face in src.faces]
    src.free()
    return verts, faces


def add_ellipsoid(bm, ico_verts, ico_faces, center, scale, rotation, mat):
    spawned = []
    for co in ico_verts:
        point = Vector((co.x * scale.x, co.y * scale.y, co.z * scale.z))
        spawned.append(bm.verts.new(rotation @ point + center))
    for face in ico_faces:
        poly = bm.faces.new(tuple(spawned[i] for i in face))
        poly.material_index = mat
        poly.smooth = True


def leaf_material(leaf_mats):
    shade = random.random()
    if shade < 0.34:
        return leaf_mats[0]
    if shade < 0.72:
        return leaf_mats[1]
    if shade < 0.90:
        return leaf_mats[2]
    return leaf_mats[3]


def scatter_clumps(
    bm, ico_verts, ico_faces, leaf_mats, center, radii, count, z_min,
    shell_min, shell_max, size_min, size_max, placed,
):
    """Overlapping flattened clumps. A tight outer shell keeps the crown solid."""
    golden = math.pi * (3.0 - math.sqrt(5.0))
    for i in range(count):
        y = 1.0 - 2.0 * ((i + 0.5) / count)
        ring = math.sqrt(max(0.0, 1.0 - y * y))
        theta = golden * i
        shell = random.uniform(shell_min, shell_max)
        shell *= 0.96 + 0.04 * math.sin(theta * 3.0 + y * 2.2)
        pos = center + Vector(
            (
                math.cos(theta) * ring * radii.x * shell,
                math.sin(theta) * ring * radii.y * shell,
                y * radii.z * shell - 0.03 * ring * ring,
            )
        )
        if pos.z < z_min or (math.hypot(pos.x, pos.y) < 0.045 and pos.z < center.z - 0.05):
            continue
        outward = pos - center
        if outward.length < 1e-6:
            outward = Vector((0.0, 0.0, 1.0))
        outward.normalize()
        base = random.uniform(size_min, size_max)
        scale = Vector((base * random.uniform(0.85, 1.05), base * 0.72, base * 0.46))
        rotation = outward.to_track_quat("Z", "Y")
        rotation = Quaternion(outward, random.uniform(0.0, math.pi)) @ rotation
        add_ellipsoid(bm, ico_verts, ico_faces, pos, scale, rotation, leaf_material(leaf_mats))
        placed.append(pos.copy())


def build_canopy(bm, leaf_mats, fruit_mat):
    """Rounded crown of clustered silvery-green clumps. Fully determined by SEED."""
    random.seed(SEED)
    placed = []
    ico_verts, ico_faces = unit_icosphere(0)
    crown = Vector((0.0, -0.008, 0.985))
    # Radii sit just inside the 22 in canopy so the clumps themselves reach the box.
    radii = Vector((0.274, 0.272, 0.352))
    scatter_clumps(
        bm, ico_verts, ico_faces, leaf_mats, crown, radii,
        1040, 0.60, 0.90, 1.0, 0.022, 0.036, placed,
    )
    scatter_clumps(
        bm, ico_verts, ico_faces, leaf_mats, crown, radii,
        280, 0.64, 0.32, 0.78, 0.026, 0.044, placed,
    )
    print("clumps", len(placed))

    fruit_verts, fruit_faces = unit_icosphere(1)
    random.seed(SEED + 19)
    fruits = 0
    for leaf_pos in placed:
        if fruits >= 16:
            break
        if random.random() > 0.03:
            continue
        delta = leaf_pos - crown
        fruit_pos = leaf_pos + (delta.normalized() * 0.012 if delta.length > 1e-6 else Vector())
        if fruit_pos.z < 0.75 or fruit_pos.z > 1.22:
            continue
        if math.hypot(fruit_pos.x, fruit_pos.y) < 0.06:
            continue
        radius = random.uniform(0.0075, 0.011)
        spin = Quaternion(Vector((0.2, 0.1, 1.0)).normalized(), random.uniform(0.0, math.pi))
        add_ellipsoid(
            bm,
            fruit_verts,
            fruit_faces,
            fruit_pos,
            Vector((radius * 0.8, radius, radius * 0.8)),
            spin,
            fruit_mat,
        )
        fruits += 1
    print("olives", fruits)


def fit_tree(mesh, pot_end):
    """Scale trunk and foliage onto the catalog box. The pot is left as modeled."""
    tree = list(mesh.vertices[pot_end:])
    xs = [v.co.x for v in tree]
    ys = [v.co.y for v in tree]
    zs = [v.co.z for v in tree]
    print(
        "pre-fit tree extent m: %.4f x %.4f x %.4f (z %.4f..%.4f)"
        % (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs), min(zs), max(zs))
    )

    def match_axis(index, half_target):
        vals = [v.co[index] for v in tree]
        shift = -0.5 * (min(vals) + max(vals))
        for v in tree:
            v.co[index] += shift
        peak = max(abs(v.co[index]) for v in tree)
        scale = half_target / peak
        for v in tree:
            v.co[index] *= scale
        return scale

    sx = match_axis(0, TARGET_W * 0.5)
    sy = match_axis(1, TARGET_D * 0.5)
    peak_z = max(v.co.z for v in tree)
    sz = TARGET_H / peak_z
    for v in tree:
        v.co.z *= sz

    xs = [v.co.x for v in mesh.vertices]
    ys = [v.co.y for v in mesh.vertices]
    zs = [v.co.z for v in mesh.vertices]
    dx = -0.5 * (min(xs) + max(xs))
    dy = -0.5 * (min(ys) + max(ys))
    dz = -min(zs)
    for v in mesh.vertices:
        v.co.x += dx
        v.co.y += dy
        v.co.z += dz
    mesh.update()
    print("tree fit scales %.4f %.4f %.4f  translate %.4f %.4f %.4f" % (sx, sy, sz, dx, dy, dz))
    return sx, sy, sz


def measured_bbox(mesh):
    xs = [v.co.x for v in mesh.vertices]
    ys = [v.co.y for v in mesh.vertices]
    zs = [v.co.z for v in mesh.vertices]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    minz, maxz = min(zs), max(zs)
    return {
        "min": [minx, miny, minz],
        "max": [maxx, maxy, maxz],
        "width": maxx - minx,
        "depth": maxy - miny,
        "height": maxz - minz,
    }


def triangle_count(mesh):
    mesh.calc_loop_triangles()
    return len(mesh.loop_triangles)


def aim_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_light(name, kind, location, target, energy, color, size=1.0):
    light = bpy.data.lights.new(name, kind)
    light.energy = energy
    light.color = color
    if kind == "AREA":
        light.size = size
    if kind == "SUN":
        light.angle = math.radians(14)
    obj = bpy.data.objects.new(name, light)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = Vector(location)
    aim_at(obj, target)
    return obj


def setup_preview(scene, out_png):
    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes["Background"]
    background.inputs["Color"].default_value = (*srgb_to_linear((0.91, 0.88, 0.83)), 1.0)
    background.inputs["Strength"].default_value = 0.32

    floor_mat = make_material("PreviewFloor", (0.80, 0.76, 0.70), 0.92, 0.2)
    bpy.ops.mesh.primitive_plane_add(size=6.0, location=(0.0, 0.0, -0.002))
    floor = bpy.context.active_object
    floor.name = "PREVIEW_FLOOR"
    floor.data.materials.append(floor_mat)

    target = (0.0, 0.0, 0.62)
    add_light("PREVIEW_SUN", "SUN", (1.6, -1.8, 2.6), target, 1.8, (1.0, 0.96, 0.90))
    add_light("PREVIEW_KEY", "AREA", (1.15, -1.45, 1.55), target, 120, (1.0, 0.95, 0.88), 1.6)
    add_light("PREVIEW_FILL", "AREA", (-1.4, -0.9, 0.85), target, 36, (0.85, 0.90, 1.0), 1.8)
    add_light("PREVIEW_RIM", "AREA", (-0.5, 1.5, 1.45), target, 70, (1.0, 0.97, 0.92), 0.8)

    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens = 58
    cam_data.sensor_fit = "VERTICAL"
    cam_data.clip_start = 0.05
    cam_data.clip_end = 40.0
    cam = bpy.data.objects.new("Camera", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    view = Vector((0.78, -1.12, 0.22)).normalized()
    # Fit a sphere around the tree into the vertical field of view.
    radius = 0.86
    half_angle = cam_data.angle * 0.5
    distance = radius / math.sin(half_angle) * 1.02
    cam.location = Vector(target) + view * distance
    aim_at(cam, target)

    scene.render.resolution_x = 512
    scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    scene.render.filepath = out_png
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.exposure = 0.0

    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
        scene.eevee.taa_render_samples = 24
        if hasattr(scene.eevee, "use_raytracing"):
            scene.eevee.use_raytracing = False
        print("render engine: BLENDER_EEVEE_NEXT")
    except Exception as exc:  # noqa: BLE001
        print("eevee unavailable:", exc)
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.display.shading.light = "STUDIO"
        scene.display.shading.color_type = "MATERIAL"
        scene.display.shading.show_shadows = True
        print("render engine: BLENDER_WORKBENCH")


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = "METERS"
    return scene


def main():
    outdir = parse_outdir()
    scene = clear_scene()

    mats = {
        "pot": make_material("Pot", (0.77, 0.69, 0.58), 0.78, 0.35),
        "rim": make_material("PotRim", (0.84, 0.77, 0.68), 0.58, 0.42),
        "soil": make_material("Soil", (0.23, 0.18, 0.13), 0.98, 0.15),
        "bark": make_material("Bark", (0.40, 0.34, 0.28), 0.90, 0.22),
        "leaf_silver": make_material("LeafSilver", (0.63, 0.68, 0.48), 0.58, 0.30),
        "leaf_mid": make_material("LeafOlive", (0.46, 0.54, 0.33), 0.56, 0.28),
        "leaf_deep": make_material("LeafDeep", (0.31, 0.38, 0.23), 0.62, 0.25),
        "leaf_pale": make_material("LeafPale", (0.72, 0.75, 0.58), 0.52, 0.32),
        "fruit": make_material("OliveFruit", (0.16, 0.18, 0.09), 0.38, 0.45),
    }
    ordered = [
        mats["pot"],
        mats["rim"],
        mats["soil"],
        mats["bark"],
        mats["leaf_silver"],
        mats["leaf_mid"],
        mats["leaf_deep"],
        mats["leaf_pale"],
        mats["fruit"],
    ]
    index = {mat: i for i, mat in enumerate(ordered)}

    bm = bmesh.new()
    build_pot(bm, (index[mats["pot"]], index[mats["rim"]]))
    build_soil(bm, index[mats["soil"]])
    bm.verts.ensure_lookup_table()
    pot_end = len(bm.verts)
    build_wood(bm, index[mats["bark"]])
    build_canopy(
        bm,
        [
            index[mats["leaf_silver"]],
            index[mats["leaf_mid"]],
            index[mats["leaf_deep"]],
            index[mats["leaf_pale"]],
        ],
        index[mats["fruit"]],
    )
    bm.normal_update()

    mesh = bpy.data.meshes.new("F017")
    bm.to_mesh(mesh)
    bm.free()
    for mat in ordered:
        mesh.materials.append(mat)
    mesh.update()

    print("polygons", len(mesh.polygons), "pot verts", pot_end)
    fit_tree(mesh, pot_end)
    bbox = measured_bbox(mesh)
    tris = triangle_count(mesh)
    print(
        "bbox m: width %.4f  depth %.4f  height %.4f  triangles %d"
        % (bbox["width"], bbox["depth"], bbox["height"], tris)
    )
    for axis, got, target in (
        ("width", bbox["width"], TARGET_W),
        ("depth", bbox["depth"], TARGET_D),
        ("height", bbox["height"], TARGET_H),
    ):
        err = abs(got - target) / target
        print("  %s error %.3f%%" % (axis, err * 100))
        if err > 0.02:
            raise SystemExit("bounding box outside 2% tolerance on %s" % axis)

    obj = bpy.data.objects.new("F017", mesh)
    scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    glb_path = os.path.join(outdir, "model.glb")
    bpy.ops.export_scene.gltf(
        filepath=glb_path,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
    )
    print("exported", glb_path)

    metadata = {
        "id": "F017",
        "name": "Olive Tree in Pot",
        "category": "Plant",
        "style": "Japandi",
        "room": "Living Room",
        "price_usd": 129,
        "dimensions_in": {"width": 22, "depth": 22, "height": 54},
        "dimensions_m": {
            "width": round(TARGET_W, 6),
            "depth": round(TARGET_D, 6),
            "height": round(TARGET_H, 6),
        },
        "bounding_box_m": {
            "min": [round(v, 6) for v in bbox["min"]],
            "max": [round(v, 6) for v in bbox["max"]],
            "width": round(bbox["width"], 6),
            "depth": round(bbox["depth"], 6),
            "height": round(bbox["height"], 6),
        },
        "triangle_count": tris,
        "seed": SEED,
    }
    meta_path = os.path.join(outdir, "metadata.json")
    with open(meta_path, "w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)
        handle.write("\n")
    print("wrote", meta_path)

    preview_path = os.path.join(outdir, "preview.png")
    setup_preview(scene, preview_path)
    bpy.ops.render.render(write_still=True)
    print("rendered", preview_path)

    # Source scene is the asset only.
    for extra in list(bpy.data.objects):
        if extra.name != "F017":
            bpy.data.objects.remove(extra, do_unlink=True)
    blend_path = os.path.join(outdir, "model.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path, compress=True)
    print("saved", blend_path)


if __name__ == "__main__":
    main()
