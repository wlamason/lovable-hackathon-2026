#!/usr/bin/env python3
"""Build catalog item F014, Tall Fiddle Leaf Plant, from scratch.

Headless:
  blender -b --factory-startup --python build.py -- --outdir <dir>

Units are meters (1 Blender unit = 1 m). Width is X, depth is Y, height is Z.
The front of the plant faces -Y. Origin is the bottom center of the footprint.
A fixed RNG seed keeps every rebuild identical. Only bpy, bmesh, and mathutils
are used.
"""

import json
import math
import random
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

SEED = 14014
INCH = 0.0254
TARGET_W = 20.0 * INCH
TARGET_D = 20.0 * INCH
TARGET_H = 60.0 * INCH
TOLERANCE = 0.02

# Material slots on the single F014 mesh.
MAT_POT = 0
MAT_CREAM = 1
MAT_SOIL = 2
MAT_BARK = 3
MAT_PETIOLE = 4
MAT_LEAF = 5
MAT_VEIN = 6
MAT_NEW = 7

# Fiddle-leaf silhouette, t from petiole (0) to drip tip (1), half-width factor.
LEAF_PROFILE = (
    (0.00, 0.05),
    (0.06, 0.12),
    (0.14, 0.34),
    (0.22, 0.52),
    (0.30, 0.46),
    (0.40, 0.30),  # waist
    (0.50, 0.42),
    (0.62, 0.78),
    (0.74, 1.00),  # broad violin top
    (0.84, 0.88),
    (0.92, 0.50),
    (0.97, 0.18),
    (1.00, 0.045),
)

# Columns across the blade. The center pair is the pale midrib.
LEAF_S = (-1.0, -0.52, -0.07, 0.07, 0.52, 1.0)
LEAF_T = (0.00, 0.07, 0.16, 0.28, 0.40, 0.52, 0.64, 0.76, 0.88, 0.95, 1.00)

# z, azimuths (0 = front / -Y), pitch from vertical, length, width/length, arch, kind.
TIERS = (
    (0.50, (45, 135, 225, 315), 52.0, 0.28, 0.70, 0.040, "mature"),
    (0.68, (0, 90, 180, 270), 42.0, 0.31, 0.72, 0.028, "mature"),
    (0.88, (45, 135, 225, 315), 32.0, 0.31, 0.70, 0.016, "mature"),
    (1.04, (0, 90, 180, 270), 22.0, 0.27, 0.64, 0.008, "mature"),
    (1.14, (20, 110, 200, 290), 15.0, 0.20, 0.56, 0.004, "young"),
    (1.155, (0,), 8.0, 0.34, 0.30, 0.000, "spear"),
)

SOIL_Z = 0.292
TRUNK_TOP = 1.15
TRUNK_BASE_R = 0.018
TRUNK_TOP_R = 0.009


def parse_outdir():
    outdir = Path(__file__).resolve().parent
    argv = sys.argv
    if "--" in argv:
        args = argv[argv.index("--") + 1 :]
        if "--outdir" in args:
            outdir = Path(args[args.index("--outdir") + 1]).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    return outdir


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    # Don't leave model.blend1 backups next to the deliverables.
    bpy.context.preferences.filepaths.save_version = 0
    return scene


def make_material(name, color, roughness, specular=0.4):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = (color[0], color[1], color[2], 1.0)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (color[0], color[1], color[2], 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = 0.0
    spec_name = "Specular IOR Level" if "Specular IOR Level" in bsdf.inputs else "Specular"
    if spec_name in bsdf.inputs:
        bsdf.inputs[spec_name].default_value = specular
    return mat


def create_materials():
    specs = (
        ("F014_Terracotta", (0.62, 0.28, 0.15), 0.68, 0.28),
        ("F014_CreamSlip", (0.80, 0.68, 0.48), 0.62, 0.30),
        ("F014_Soil", (0.11, 0.075, 0.04), 0.96, 0.15),
        ("F014_Bark", (0.28, 0.18, 0.10), 0.80, 0.22),
        ("F014_Petiole", (0.20, 0.26, 0.08), 0.55, 0.30),
        ("F014_Leaf", (0.035, 0.16, 0.045), 0.30, 0.46),
        ("F014_Vein", (0.18, 0.32, 0.10), 0.38, 0.32),
        ("F014_NewLeaf", (0.40, 0.50, 0.15), 0.36, 0.38),
    )
    return [make_material(*spec) for spec in specs]


def profile_width(t):
    for i in range(len(LEAF_PROFILE) - 1):
        t0, w0 = LEAF_PROFILE[i]
        t1, w1 = LEAF_PROFILE[i + 1]
        if t <= t1 or i == len(LEAF_PROFILE) - 2:
            u = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            u = max(0.0, min(1.0, u))
            return w0 + (w1 - w0) * u
    return LEAF_PROFILE[-1][1]


def add_revolution(bm, profile, segments):
    """Revolve a (z, r) profile around Z. Closed when both ends sit on the axis."""
    cols = []
    for z, r in profile:
        if r < 1e-8:
            cols.append([bm.verts.new((0.0, 0.0, z))])
            continue
        ring = []
        for i in range(segments):
            angle = 2.0 * math.pi * i / segments
            ring.append(bm.verts.new((r * math.cos(angle), r * math.sin(angle), z)))
        cols.append(ring)

    faces = []
    for i in range(len(cols) - 1):
        a = cols[i]
        b = cols[i + 1]
        if len(a) == 1 and len(b) == 1:
            continue
        if len(a) == 1:
            center = a[0]
            for j in range(segments):
                faces.append(bm.faces.new((center, b[j], b[(j + 1) % segments])))
        elif len(b) == 1:
            center = b[0]
            for j in range(segments):
                faces.append(bm.faces.new((a[(j + 1) % segments], a[j], center)))
        else:
            for j in range(segments):
                j2 = (j + 1) % segments
                faces.append(bm.faces.new((a[j], a[j2], b[j2], b[j])))
    return faces


def trunk_radius(t):
    """t is 0 at the soil line and 1 at the crown. Includes a root flare."""
    t = max(0.0, min(1.0, t))
    flare = 1.0 + 0.65 * max(0.0, 1.0 - t * 8.0) ** 2
    return (TRUNK_BASE_R * (1.0 - t) + TRUNK_TOP_R * t) * flare


def trunk_axis(z):
    """Gentle deterministic lean so the stem is not a perfect cylinder."""
    span = TRUNK_TOP - SOIL_Z
    t = max(0.0, min(1.0, (z - SOIL_Z) / span))
    x = 0.004 * math.sin(math.pi * t)
    y = 0.003 * math.sin(2.0 * math.pi * t)
    return Vector((x, y, z)), t


def leaf_frame(azimuth_deg, pitch_deg):
    azimuth = math.radians(azimuth_deg)
    pitch = math.radians(pitch_deg)
    outward = Vector((math.sin(azimuth), -math.cos(azimuth), 0.0))
    up = Vector((0.0, 0.0, 1.0))
    direction = (outward * math.sin(pitch) + up * math.cos(pitch)).normalized()
    right = up.cross(outward)
    if right.length < 1e-6:
        right = Vector((1.0, 0.0, 0.0))
    else:
        right.normalize()
    normal = right.cross(direction)
    if normal.length < 1e-6:
        normal = up
    else:
        normal.normalize()
    if normal.z < 0.0:
        normal.negate()
    return outward, direction, right, normal


def add_face(bm, verts, material):
    face = bm.faces.new(verts)
    face.material_index = material
    face.smooth = True
    return face


def build_leaf(bm, z_attach, azimuth_deg, pitch_deg, length, width_ratio, arch, kind, rng):
    azimuth_deg = azimuth_deg + rng.uniform(-2.2, 2.2)
    pitch_deg = max(4.0, pitch_deg + rng.uniform(-1.4, 1.4))
    length *= rng.uniform(0.985, 1.015)
    twist = math.radians(rng.uniform(-8.0, 8.0))
    wave_phase = rng.uniform(0.0, math.tau)
    cup_scale = rng.uniform(0.9, 1.1)

    outward, direction, right, normal = leaf_frame(azimuth_deg, pitch_deg)
    # Small twist so neighboring blades don't sit in one plane.
    cos_t = math.cos(twist)
    sin_t = math.sin(twist)
    right = (right * cos_t + normal * sin_t).normalized()
    normal = right.cross(direction).normalized()
    if normal.z < 0.0:
        normal.negate()

    axis, t_param = trunk_axis(z_attach)
    radius = trunk_radius(t_param)
    petiole = 0.028 if kind == "spear" else 0.05
    origin = axis + outward * (radius * 0.82)
    blade_origin = origin + direction * petiole

    add_cylinder(bm, origin, blade_origin, 0.0042, 0.0034, 6, MAT_PETIOLE)

    width = length * width_ratio
    if kind == "spear":
        cup = 0.055 * cup_scale
        material = MAT_NEW
        vein = MAT_NEW
    elif kind == "young":
        cup = 0.016 * cup_scale
        material = MAT_NEW
        vein = MAT_VEIN
    else:
        cup = 0.014 * cup_scale * (length / 0.30)
        material = MAT_LEAF
        vein = MAT_VEIN

    rows_top = []
    rows_bot = []
    half_thick = 0.0008
    for t in LEAF_T:
        half_w = profile_width(t) * width * 0.5
        top_row = []
        bot_row = []
        along = t * length
        droop = up_vector() * (arch * (t ** 1.45))
        for s in LEAF_S:
            across = s * half_w
            vault = math.sin(math.pi * t) * (1.0 - s * s)
            offset = normal * (cup * vault)
            if abs(s) > 0.9:
                offset += normal * (0.005 * math.sin(t * math.pi * 3.2 + wave_phase))
            # Shallow top groove along the midrib.
            if abs(s) < 0.16:
                offset -= normal * (0.0035 * math.sin(math.pi * t))
            center = blade_origin + right * across + direction * along + offset - droop
            top_row.append(bm.verts.new(center + normal * half_thick))
            bot_row.append(bm.verts.new(center - normal * half_thick))
        rows_top.append(top_row)
        rows_bot.append(bot_row)

    n_rows = len(rows_top)
    n_cols = len(LEAF_S)
    for i in range(n_rows - 1):
        for j in range(n_cols - 1):
            slot = vein if j == 2 else material
            add_face(
                bm,
                (
                    rows_top[i][j],
                    rows_top[i][j + 1],
                    rows_top[i + 1][j + 1],
                    rows_top[i + 1][j],
                ),
                slot,
            )
            add_face(
                bm,
                (
                    rows_bot[i][j],
                    rows_bot[i + 1][j],
                    rows_bot[i + 1][j + 1],
                    rows_bot[i][j + 1],
                ),
                material,
            )

    def side(chain_a, chain_b, material_index):
        for i in range(n_rows - 1):
            add_face(
                bm,
                (chain_a[i], chain_b[i], chain_b[i + 1], chain_a[i + 1]),
                material_index,
            )

    side([row[0] for row in rows_top], [row[0] for row in rows_bot], material)
    side([row[-1] for row in rows_bot], [row[-1] for row in rows_top], material)
    for j in range(n_cols - 1):
        add_face(
            bm,
            (rows_top[0][j], rows_top[0][j + 1], rows_bot[0][j + 1], rows_bot[0][j]),
            material,
        )
        add_face(
            bm,
            (
                rows_top[-1][j],
                rows_bot[-1][j],
                rows_bot[-1][j + 1],
                rows_top[-1][j + 1],
            ),
            material,
        )


def up_vector():
    return Vector((0.0, 0.0, 1.0))


def add_cylinder(bm, p0, p1, r0, r1, segments, material):
    axis = p1 - p0
    length = axis.length
    if length < 1e-6:
        return
    direction = axis / length
    quat = Vector((0.0, 0.0, 1.0)).rotation_difference(direction)
    rot = quat.to_matrix()
    rings = []
    for t, radius in ((0.0, r0), (1.0, r1)):
        ring = []
        for i in range(segments):
            angle = 2.0 * math.pi * i / segments
            local = Vector((radius * math.cos(angle), radius * math.sin(angle), t * length))
            ring.append(bm.verts.new(p0 + rot @ local))
        rings.append(ring)
    for i in range(segments):
        j = (i + 1) % segments
        add_face(bm, (rings[0][i], rings[0][j], rings[1][j], rings[1][i]), material)
    return rings


def build_trunk(bm):
    steps = 22
    segments = 12
    rings = []
    z0 = SOIL_Z - 0.012
    for s in range(steps):
        tlin = s / (steps - 1)
        z = z0 + (TRUNK_TOP - z0) * tlin
        center, t_param = trunk_axis(z)
        radius = trunk_radius(t_param if z >= SOIL_Z else 0.0)
        ring = []
        for i in range(segments):
            angle = 2.0 * math.pi * i / segments
            wobble = 1.0 + 0.035 * math.sin(3.0 * angle + tlin * 11.0)
            offset = Vector((math.cos(angle), math.sin(angle), 0.0)) * (radius * wobble)
            ring.append(bm.verts.new(center + offset))
        rings.append(ring)
    for s in range(steps - 1):
        for i in range(segments):
            j = (i + 1) % segments
            add_face(
                bm,
                (rings[s][i], rings[s][j], rings[s + 1][j], rings[s + 1][i]),
                MAT_BARK,
            )
    # Caps so the tube is closed where it meets soil and the apical leaf.
    for ring, up in ((rings[0], False), (rings[-1], True)):
        center = sum((v.co for v in ring), Vector()) / len(ring)
        hub = bm.verts.new(center)
        for i in range(segments):
            j = (i + 1) % segments
            if up:
                add_face(bm, (hub, ring[i], ring[j]), MAT_BARK)
            else:
                add_face(bm, (hub, ring[j], ring[i]), MAT_BARK)


def build_scars(bm):
    for index, z in enumerate((0.34, 0.395, 0.45)):
        azimuth = math.radians(25.0 + index * 137.507764)
        outward = Vector((math.sin(azimuth), -math.cos(azimuth), 0.0))
        center, t_param = trunk_axis(z)
        radius = trunk_radius(t_param)
        pos = center + outward * (radius * 0.96)
        normal = outward
        tangent = up_vector().cross(normal).normalized()
        bitangent = normal.cross(tangent).normalized()
        hub = bm.verts.new(pos + normal * 0.0016)
        ring = []
        segments = 8
        for i in range(segments):
            angle = 2.0 * math.pi * i / segments
            point = (
                pos
                + normal * 0.0016
                + tangent * (math.cos(angle) * 0.0075)
                + bitangent * (math.sin(angle) * 0.0055)
            )
            ring.append(bm.verts.new(point))
        for i in range(segments):
            add_face(bm, (hub, ring[i], ring[(i + 1) % segments]), MAT_BARK)


def build_pot_and_saucer(bm):
    segments = 40
    saucer = (
        (0.012, 0.000),
        (0.012, 0.116),
        (0.018, 0.136),
        (0.030, 0.152),
        (0.020, 0.158),
        (0.006, 0.150),
        (0.000, 0.142),
        (0.000, 0.000),
    )
    # Foot bottoms out on the saucer floor so the planter sits, it does not hover.
    pot = (
        (0.020, 0.000),
        (0.018, 0.078),
        (0.030, 0.094),
        (0.090, 0.102),
        (0.170, 0.110),
        (0.235, 0.104),
        (0.275, 0.114),
        (0.302, 0.126),
        (0.314, 0.138),
        (0.306, 0.144),
        (0.290, 0.136),
        (0.255, 0.126),
        (0.185, 0.136),
        (0.105, 0.126),
        (0.055, 0.112),
        (0.028, 0.104),
        (0.014, 0.112),
        (0.011, 0.096),
        (0.010, 0.000),
    )
    saucer_faces = add_revolution(bm, saucer, segments)
    pot_faces = add_revolution(bm, pot, segments)
    bm.normal_update()
    bmesh.ops.recalc_face_normals(bm, faces=saucer_faces)
    bmesh.ops.recalc_face_normals(bm, faces=pot_faces)
    bm.normal_update()

    for face in saucer_faces:
        face.material_index = MAT_POT
        face.smooth = True
    for face in pot_faces:
        center = face.calc_center_median()
        radial = Vector((center.x, center.y, 0.0))
        outer = radial.length > 1e-5 and face.normal.dot(radial.normalized()) > 0.45
        if outer and 0.248 < center.z < 0.286:
            face.material_index = MAT_CREAM
        else:
            face.material_index = MAT_POT
        face.smooth = True

    # Handmade wobble, small enough to keep the planter round.
    for vert in {v for face in pot_faces for v in face.verts}:
        radial = math.hypot(vert.co.x, vert.co.y)
        if radial < 0.02:
            continue
        wave = 0.0016 * math.sin(3.0 * math.atan2(vert.co.y, vert.co.x) + vert.co.z * 16.0)
        scale = (radial + wave) / radial
        vert.co.x *= scale
        vert.co.y *= scale

    # Soil surface, slightly domed, sitting inside the rim.
    soil_r = 0.108
    hub = bm.verts.new((0.0, 0.0, SOIL_Z + 0.008))
    ring = []
    for i in range(segments):
        angle = 2.0 * math.pi * i / segments
        ring.append(
            bm.verts.new((soil_r * math.cos(angle), soil_r * math.sin(angle), SOIL_Z))
        )
    for i in range(segments):
        add_face(bm, (hub, ring[i], ring[(i + 1) % segments]), MAT_SOIL)


def build_model():
    rng = random.Random(SEED)
    bm = bmesh.new()
    build_pot_and_saucer(bm)
    build_trunk(bm)
    build_scars(bm)
    for z, azimuths, pitch, length, ratio, arch, kind in TIERS:
        for azimuth in azimuths:
            build_leaf(bm, z, azimuth, pitch, length, ratio, arch, kind, rng)

    mesh = bpy.data.meshes.new("F014")
    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    mesh.validate(clean_customdata=False)
    mesh.update()

    obj = bpy.data.objects.new("F014", mesh)
    bpy.context.scene.collection.objects.link(obj)
    for mat in create_materials():
        obj.data.materials.append(mat)
    return obj


def mesh_bounds(mesh):
    xs = [v.co.x for v in mesh.vertices]
    ys = [v.co.y for v in mesh.vertices]
    zs = [v.co.z for v in mesh.vertices]
    return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)


def fit_to_catalog(mesh):
    minx, maxx, miny, maxy, minz, maxz = mesh_bounds(mesh)
    pre = (maxx - minx, maxy - miny, maxz - minz)
    print(
        "PRE-FIT bbox m: "
        f"width={pre[0]:.4f} depth={pre[1]:.4f} height={pre[2]:.4f}"
    )
    cx = (minx + maxx) * 0.5
    cy = (miny + maxy) * 0.5
    sx = TARGET_W / (maxx - minx)
    sy = TARGET_D / (maxy - miny)
    sz = TARGET_H / (maxz - minz)
    print(f"FIT scale: sx={sx:.4f} sy={sy:.4f} sz={sz:.4f}")
    for vert in mesh.vertices:
        vert.co.x = (vert.co.x - cx) * sx
        vert.co.y = (vert.co.y - cy) * sy
        vert.co.z = (vert.co.z - minz) * sz
    mesh.update()
    return sx, sy, sz


def triangle_count(mesh):
    mesh.calc_loop_triangles()
    return len(mesh.loop_triangles)


def assert_catalog_size(bounds):
    minx, maxx, miny, maxy, minz, maxz = bounds
    size = (maxx - minx, maxy - miny, maxz - minz)
    targets = (TARGET_W, TARGET_D, TARGET_H)
    labels = ("width", "depth", "height")
    print(
        "BBOX m: "
        f"min=({minx:.4f}, {miny:.4f}, {minz:.4f}) "
        f"max=({maxx:.4f}, {maxy:.4f}, {maxz:.4f}) "
        f"size=({size[0]:.4f}, {size[1]:.4f}, {size[2]:.4f})"
    )
    for label, measured, target in zip(labels, size, targets):
        error = abs(measured - target) / target
        print(f"  {label}: measured={measured:.4f} target={target:.4f} error={error:.3%}")
        if error > TOLERANCE:
            raise SystemExit(f"{label} is outside the {TOLERANCE:.0%} tolerance")
    if abs(minz) > 1e-4:
        raise SystemExit(f"model does not sit on Z=0 (min z={minz})")
    if abs((minx + maxx) * 0.5) > 1e-4 or abs((miny + maxy) * 0.5) > 1e-4:
        raise SystemExit("footprint is not centered on X/Y")
    return size


def export_glb(obj, path):
    import addon_utils

    addon_utils.enable("io_scene_gltf2", default_set=True, persistent=False)
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
        export_texcoords=False,
        export_normals=True,
        export_cameras=False,
        export_lights=False,
    )
    print(f"Exported {path}")


def look_at(obj, target):
    direction = target - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_preview_stage(scene, bounds):
    minx, maxx, miny, maxy, minz, maxz = bounds
    center = Vector(((minx + maxx) * 0.5, (miny + maxy) * 0.5, (minz + maxz) * 0.46))

    world = bpy.data.worlds.new("F014_World")
    scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes["Background"]
    background.inputs[0].default_value = (0.78, 0.75, 0.70, 1.0)
    background.inputs[1].default_value = 0.35

    sun_data = bpy.data.lights.new("F014_Key", "SUN")
    sun_data.energy = 3.2
    sun_data.color = (1.0, 0.96, 0.90)
    sun_data.angle = math.radians(8.0)
    sun = bpy.data.objects.new("F014_Key", sun_data)
    scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(52.0), math.radians(6.0), math.radians(-38.0))

    fill_data = bpy.data.lights.new("F014_Fill", "AREA")
    fill_data.energy = 90.0
    fill_data.size = 2.4
    fill_data.color = (0.85, 0.90, 1.0)
    fill = bpy.data.objects.new("F014_Fill", fill_data)
    scene.collection.objects.link(fill)
    fill.location = (-1.1, -0.7, 1.3)
    look_at(fill, center)

    floor_mat = make_material("F014_Floor", (0.40, 0.28, 0.17), 0.86, 0.18)
    floor_mesh = bpy.data.meshes.new("F014_Floor")
    floor_bm = bmesh.new()
    bmesh.ops.create_grid(floor_bm, x_segments=1, y_segments=1, size=2.4)
    floor_bm.to_mesh(floor_mesh)
    floor_bm.free()
    floor = bpy.data.objects.new("F014_Floor", floor_mesh)
    floor.location = (0.0, 0.0, -0.002)
    floor.data.materials.append(floor_mat)
    scene.collection.objects.link(floor)

    cam_data = bpy.data.cameras.new("F014_Camera")
    cam_data.lens = 58
    cam_data.sensor_fit = "VERTICAL"
    cam_data.clip_start = 0.05
    cam_data.clip_end = 40.0
    cam = bpy.data.objects.new("F014_Camera", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam

    view = Vector((0.62, -1.05, 0.30)).normalized()
    fov = cam_data.angle
    dist = (TARGET_H * 0.62) / math.tan(fov * 0.5)
    cam.location = center + view * dist
    look_at(cam, center)
    bpy.context.view_layer.update()

    # Pull the camera back until every bbox corner sits inside the frame.
    corners = [
        Vector((x, y, z))
        for x in (minx, maxx)
        for y in (miny, maxy)
        for z in (minz, maxz)
    ]
    for _ in range(8):
        bpy.context.view_layer.update()
        inv = cam.matrix_world.inverted()
        tan_half = math.tan(cam_data.angle * 0.5)
        fits = True
        for corner in corners:
            local = inv @ corner
            depth = -local.z
            if depth < 0.05 or abs(local.x) > depth * tan_half * 0.92:
                fits = False
            if depth < 0.05 or abs(local.y) > depth * tan_half * 0.90:
                fits = False
        if fits:
            break
        dist *= 1.08
        cam.location = center + view * dist
        look_at(cam, center)


def configure_eevee(scene):
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    eevee = scene.eevee
    if hasattr(eevee, "taa_render_samples"):
        eevee.taa_render_samples = 32
    if hasattr(eevee, "use_raytracing"):
        eevee.use_raytracing = False


def configure_workbench(scene):
    scene.render.engine = "BLENDER_WORKBENCH"
    shading = scene.display.shading
    shading.light = "STUDIO"
    shading.color_type = "MATERIAL"
    shading.show_shadows = True
    shading.show_cavity = False


def render_preview(scene, path):
    scene.render.resolution_x = 512
    scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.filepath = str(path)
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0
    try:
        configure_eevee(scene)
        bpy.ops.render.render(write_still=True)
        print("Rendered preview with EEVEE")
    except Exception as exc:
        print(f"EEVEE render failed ({exc}); falling back to Workbench")
        configure_workbench(scene)
        bpy.ops.render.render(write_still=True)
        print("Rendered preview with Workbench")


def write_metadata(path, bounds, tris):
    minx, maxx, miny, maxy, minz, maxz = bounds
    width, depth, height = maxx - minx, maxy - miny, maxz - minz

    def r(value):
        return round(float(value), 6)

    meta = {
        "id": "F014",
        "name": "Tall Fiddle Leaf Plant",
        "category": "Plant",
        "style": "Bohemian",
        "room": "Living Room",
        "price_usd": 89,
        "dimensions_in": {"width": 20, "depth": 20, "height": 60},
        "dimensions_m": {
            "width": r(TARGET_W),
            "depth": r(TARGET_D),
            "height": r(TARGET_H),
        },
        "bounding_box_m": {
            "min": {"x": r(minx), "y": r(miny), "z": r(minz)},
            "max": {"x": r(maxx), "y": r(maxy), "z": r(maxz)},
            "width": r(width),
            "depth": r(depth),
            "height": r(height),
        },
        "triangle_count": tris,
        "seed": SEED,
    }
    path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {path}")


def main():
    outdir = parse_outdir()
    scene = reset_scene()
    obj = build_model()
    fit_to_catalog(obj.data)
    bounds = mesh_bounds(obj.data)
    size = assert_catalog_size(bounds)
    tris = triangle_count(obj.data)
    print(f"TRIANGLES: {tris}")
    if tris > 30000:
        raise SystemExit(f"triangle count {tris} is above the 30k web budget")

    export_glb(obj, outdir / "model.glb")
    blend_path = outdir / "model.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    print(f"Saved {blend_path}")

    add_preview_stage(scene, bounds)
    render_preview(scene, outdir / "preview.png")
    # Keep the blend as the plant plus the preview camera/lights used above.
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    write_metadata(outdir / "metadata.json", bounds, tris)
    print(
        "DONE F014 "
        f"{size[0]:.4f} x {size[1]:.4f} x {size[2]:.4f} m, {tris} tris"
    )


if __name__ == "__main__":
    main()
