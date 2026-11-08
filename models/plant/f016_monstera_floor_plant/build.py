#!/usr/bin/env python3
"""Build F016 Monstera Floor Plant and export glTF, blend, preview, metadata.

Run:
  blender -b --factory-startup --python build.py -- --outdir <dir>

Units are meters. Fixed RNG seed keeps rebuilds deterministic.
"""

import json
import math
import os
import random
import struct
import sys
import traceback
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector

SEED = 16016

WIDTH_IN = 24.0
DEPTH_IN = 24.0
HEIGHT_IN = 48.0
INCH = 0.0254
WIDTH = WIDTH_IN * INCH
DEPTH = DEPTH_IN * INCH
HEIGHT = HEIGHT_IN * INCH

# Pot / soil anchors (meters). Foliage is fit to the target box after placement.
SOIL_Z = 0.308
POT_RIM_Z = 0.332

# Fenestrations in normalized blade space (half-width = 1, length = 1),
# sitting in the lobe centers of half_width_frac.
HOLE_SPECS = [
    (0.34, 0.15, 0.11, 0.026),
    (0.32, 0.37, 0.13, 0.032),
    (0.26, 0.58, 0.10, 0.026),
]

# az, tilt, petiole, leaf_len, width/length, pitch, normal_tilt, twist, emerge_r
# Azimuth 0 = +X, 90 = +Y (back), 270 = -Y (front). Angles in degrees.
LEAF_PLAN = [
    (265, 14, 0.40, 0.34, 0.92, 62, 34, 0, 0.020),
    (20, 8, 0.55, 0.38, 0.86, 70, 16, 4, 0.016),
    (150, 10, 0.50, 0.34, 0.88, 66, 18, -5, 0.018),
    (80, 11, 0.48, 0.32, 0.88, 64, 20, 6, 0.020),
    (325, 15, 0.38, 0.30, 0.90, 58, 30, -5, 0.022),
    (215, 16, 0.38, 0.30, 0.90, 56, 28, 6, 0.022),
    (0, 27, 0.185, 0.198, 0.94, 6, 18, 0, 0.024),
    (180, 27, 0.185, 0.198, 0.94, 8, 18, 0, 0.024),
    (90, 27, 0.185, 0.198, 0.94, 6, 18, 0, 0.024),
    (270, 27, 0.190, 0.202, 0.94, 8, 20, 0, 0.024),
    (48, 16, 0.34, 0.26, 0.88, 55, 20, 8, 0.020),
    (198, 17, 0.33, 0.25, 0.88, 54, 20, -7, 0.020),
    (305, 30, 0.14, 0.13, 0.80, 30, 22, 10, 0.016),
    (118, 28, 0.14, 0.12, 0.78, 32, 20, -8, 0.014),
]


def script_dir():
    return Path(__file__).resolve().parent


def parse_outdir():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []
    outdir = script_dir()
    if "--outdir" in argv:
        outdir = Path(argv[argv.index("--outdir") + 1]).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    return outdir


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = "METERS"
    return scene


def link_object(obj):
    bpy.context.scene.collection.objects.link(obj)
    return obj


def mesh_from_bmesh(name, bm):
    mesh = bpy.data.meshes.new(name + "_mesh")
    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    link_object(obj)
    return obj


def set_input(node, name, value):
    if name in node.inputs:
        node.inputs[name].default_value = value


def make_material(name, color, roughness, specular=0.35, coat=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = (color[0], color[1], color[2], 1.0)
    mat.use_backface_culling = False
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    set_input(bsdf, "Base Color", (color[0], color[1], color[2], 1.0))
    set_input(bsdf, "Roughness", roughness)
    set_input(bsdf, "Metallic", 0.0)
    set_input(bsdf, "Specular IOR Level", specular)
    set_input(bsdf, "Coat Weight", coat)
    if coat:
        set_input(bsdf, "Coat Roughness", 0.28)
    return mat


def make_materials():
    return {
        "pot": make_material("F016_Terracotta", (0.68, 0.34, 0.20), 0.78, 0.28),
        "saucer": make_material("F016_Saucer", (0.55, 0.26, 0.15), 0.84, 0.22),
        "cream": make_material("F016_CreamBand", (0.86, 0.76, 0.58), 0.62, 0.32),
        "dark": make_material("F016_DarkBand", (0.22, 0.09, 0.06), 0.55, 0.30),
        "soil": make_material("F016_Soil", (0.11, 0.07, 0.045), 0.95, 0.08),
        "petiole": make_material("F016_Petiole", (0.30, 0.46, 0.16), 0.50, 0.32),
        "leaf_deep": make_material("F016_LeafDeep", (0.045, 0.24, 0.08), 0.36, 0.42, coat=0.12),
        "leaf_mid": make_material("F016_LeafMid", (0.07, 0.32, 0.10), 0.34, 0.44, coat=0.14),
        "leaf_light": make_material("F016_LeafLight", (0.12, 0.40, 0.12), 0.36, 0.40, coat=0.10),
    }


def assign_mat(obj, mat, smooth):
    obj.data.materials.append(mat)
    for poly in obj.data.polygons:
        poly.use_smooth = smooth
        poly.material_index = 0


def fix_outer_normals(bm):
    """Flip the shell if the outermost side faces point inward."""
    bm.normal_update()
    best_r = 0.0
    centers = []
    for face in bm.faces:
        center = face.calc_center_median()
        radius = math.hypot(center.x, center.y)
        centers.append((radius, face, center))
        best_r = max(best_r, radius)
    if best_r < 1e-6:
        return
    score = 0
    count = 0
    for radius, face, center in centers:
        if radius < best_r * 0.9:
            continue
        if abs(face.normal.z) > 0.7:
            continue
        radial = Vector((center.x, center.y))
        count += 1
        score += 1 if face.normal.xy.dot(radial) > 0 else -1
    if count and score < 0:
        bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
        bm.normal_update()


def revolve(name, profile, segments, mat, smooth=True):
    bm = bmesh.new()
    rings = []
    for radius, z in profile:
        if radius < 1e-7:
            rings.append([bm.verts.new((0.0, 0.0, z))])
            continue
        ring = []
        for i in range(segments):
            angle = 2.0 * math.pi * i / segments
            ring.append(
                bm.verts.new((radius * math.cos(angle), radius * math.sin(angle), z))
            )
        rings.append(ring)
    for i in range(len(profile) - 1):
        lower = rings[i]
        upper = rings[i + 1]
        if len(lower) == 1 and len(upper) == 1:
            continue
        if len(lower) == 1:
            center = lower[0]
            for j in range(segments):
                j2 = (j + 1) % segments
                bm.faces.new((center, upper[j2], upper[j]))
        elif len(upper) == 1:
            center = upper[0]
            for j in range(segments):
                j2 = (j + 1) % segments
                bm.faces.new((lower[j], lower[j2], center))
        else:
            for j in range(segments):
                j2 = (j + 1) % segments
                bm.faces.new((lower[j], lower[j2], upper[j2], upper[j]))
    fix_outer_normals(bm)
    obj = mesh_from_bmesh(name, bm)
    assign_mat(obj, mat, smooth)
    return obj


def make_band(name, r_out, r_in, z0, z1, segments, mat):
    profile = [
        (r_in, z0),
        (r_out, z0),
        (r_out, z1),
        (r_in, z1),
        (r_in, z0),
    ]
    return revolve(name, profile, segments, mat, smooth=True)


def build_pot(mats):
    saucer = [
        (0.000, 0.000),
        (0.150, 0.000),
        (0.158, 0.006),
        (0.158, 0.018),
        (0.148, 0.026),
        (0.136, 0.016),
        (0.090, 0.012),
        (0.000, 0.012),
    ]
    pot = [
        (0.000, 0.016),
        (0.074, 0.016),
        (0.080, 0.026),
        (0.092, 0.060),
        (0.106, 0.115),
        (0.118, 0.178),
        (0.112, 0.232),
        (0.122, 0.278),
        (0.134, 0.308),
        (0.144, 0.324),
        (0.148, POT_RIM_Z),
        (0.132, POT_RIM_Z),
        (0.126, 0.320),
        (0.116, 0.306),
        (0.108, 0.240),
        (0.098, 0.130),
        (0.088, 0.055),
        (0.078, 0.038),
        (0.000, 0.038),
    ]
    parts = [
        revolve("saucer", saucer, 56, mats["saucer"]),
        revolve("pot", pot, 56, mats["pot"]),
        make_band("band_cream", 0.124, 0.102, 0.152, 0.202, 56, mats["cream"]),
        make_band("band_dark_lo", 0.127, 0.104, 0.146, 0.158, 56, mats["dark"]),
        make_band("band_dark_hi", 0.125, 0.104, 0.196, 0.210, 56, mats["dark"]),
    ]

    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        segments=40,
        radius1=0.108,
        radius2=0.108,
        depth=0.016,
    )
    for vert in bm.verts:
        vert.co.z += SOIL_Z
        if vert.co.z >= SOIL_Z - 0.001:
            radial = math.hypot(vert.co.x, vert.co.y) / 0.108
            vert.co.z += 0.010 * (1.0 - radial * radial)
            vert.co.z += 0.003 * math.sin(vert.co.x * 48.0 + vert.co.y * 36.0)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    soil = mesh_from_bmesh("soil", bm)
    assign_mat(soil, mats["soil"], smooth=True)
    parts.append(soil)
    return parts


# Narrow splits cut into a plump heart outline: (position, width, depth).
LEAF_SLITS = (
    (0.27, 0.038, 0.70),
    (0.46, 0.036, 0.66),
    (0.64, 0.034, 0.62),
    (0.80, 0.030, 0.46),
)


def _raw_half_width(y):
    if y <= 0.001 or y >= 0.999:
        return 0.0
    env = math.sin(math.pi * y) ** 0.48
    env += 0.30 * math.exp(-0.5 * ((y - 0.15) / 0.09) ** 2)
    cut = 0.0
    for center, sigma, depth in LEAF_SLITS:
        cut = max(cut, depth * math.exp(-0.5 * ((y - center) / sigma) ** 2))
    return max(0.0, env * (1.0 - cut))


def _smooth_half_width(y):
    weights = ((-0.016, 0.10), (-0.008, 0.22), (0.0, 0.36), (0.008, 0.22), (0.016, 0.10))
    total = 0.0
    for offset, weight in weights:
        total += weight * _raw_half_width(min(0.999, max(0.001, y + offset)))
    return total


_HALF_PEAK = max(_smooth_half_width(i / 400.0) for i in range(1, 400))


def half_width_frac(y):
    """Split heart silhouette, 0 at the petiole and the tip, 1 at the widest lobe."""
    if y <= 0.0 or y >= 1.0:
        return 0.0
    return _smooth_half_width(y) / _HALF_PEAK


def blade_points(length, width, samples=64):
    """Simple (non-self-intersecting) lobed outline, right side then left."""
    half = width * 0.5
    right = []
    for i in range(samples):
        y_frac = i / (samples - 1)
        right.append((half_width_frac(y_frac) * half, y_frac * length))
    left = [(-x, y) for x, y in reversed(right[1:-1])]
    return right + left


def point_in_poly(x, y, poly):
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) + 1e-12) + xi
        ):
            inside = not inside
        j = i
    return inside


def ellipse_inside(poly, cx, cy, rx, ry, margin):
    if rx <= margin or ry <= margin:
        return False
    for k in range(12):
        angle = 2.0 * math.pi * k / 12.0
        x = cx + math.cos(angle) * rx
        y = cy + math.sin(angle) * ry
        if not point_in_poly(x, y, poly):
            return False
    # Keep a rim of leaf between the hole and the silhouette.
    for k in range(12):
        angle = 2.0 * math.pi * k / 12.0
        x = cx + math.cos(angle) * (rx + margin)
        y = cy + math.sin(angle) * (ry + margin)
        if not point_in_poly(x, y, poly):
            return False
    return True


def fit_hole(poly, cx, cy, rx, ry):
    margin = min(rx, ry) * 0.35
    for _ in range(8):
        if ellipse_inside(poly, cx, cy, rx, ry, margin):
            return rx, ry
        rx *= 0.82
        ry *= 0.82
        margin *= 0.82
    return None


def holes_for_leaf(length, width, outline):
    if length < 0.22:
        specs = []
    elif length < 0.30:
        specs = HOLE_SPECS[:2]
    else:
        specs = HOLE_SPECS
    holes = []
    for x_frac, y_frac, rx_frac, ry_frac in specs:
        rx = rx_frac * width * 0.5
        ry = ry_frac * length
        for sign in (1.0, -1.0):
            cx = sign * x_frac * width * 0.5
            cy = y_frac * length
            fitted = fit_hole(outline, cx, cy, rx, ry)
            if fitted is None:
                continue
            holes.append((cx, cy, fitted[0], fitted[1]))
    return holes


def ellipse_points(cx, cy, rx, ry, segments=12):
    # Clockwise so the spline cuts a hole out of a counter-clockwise outline.
    points = []
    for i in range(segments):
        angle = -2.0 * math.pi * i / segments
        points.append((cx + math.cos(angle) * rx, cy + math.sin(angle) * ry))
    return points


def apply_modifiers(obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    new_mesh = bpy.data.meshes.new_from_object(evaluated, depsgraph=depsgraph)
    old = obj.data
    obj.modifiers.clear()
    obj.data = new_mesh
    if old.users == 0:
        bpy.data.meshes.remove(old)
    obj.data.update()


def curl_leaf(obj, length, amount):
    half_w = max(max(abs(v.co.x) for v in obj.data.vertices), 1e-6)
    for vert in obj.data.vertices:
        along = max(0.0, vert.co.y / max(length, 1e-6))
        across = abs(vert.co.x) / half_w
        vert.co.z += -amount * along * along
        vert.co.z += -amount * 0.42 * across * across
    obj.data.update()


def add_poly_spline(curve, points):
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for point, (x, y) in zip(spline.points, points):
        point.co = (x, y, 0.0, 1.0)
    spline.use_cyclic_u = True
    return spline


def convert_to_mesh(obj):
    for other in bpy.context.view_layer.objects:
        other.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.convert(target="MESH")


def make_leaf(name, length, width, thickness, curl, with_holes, mat):
    outline_xy = blade_points(length, width)
    curve = bpy.data.curves.new(name + "_cu", "CURVE")
    curve.dimensions = "2D"
    curve.fill_mode = "BOTH"
    curve.resolution_u = 1
    add_poly_spline(curve, outline_xy)
    hole_count = 0
    if with_holes:
        for cx, cy, rx, ry in holes_for_leaf(length, width, outline_xy):
            add_poly_spline(curve, ellipse_points(cx, cy, rx, ry, segments=10))
            hole_count += 1
    print(f"{name} holes {hole_count}", flush=True)
    obj = bpy.data.objects.new(name, curve)
    link_object(obj)
    curve.materials.append(mat)
    convert_to_mesh(obj)
    if len(obj.data.polygons) < 1:
        raise RuntimeError(f"{name} curve fill produced no faces")
    solid = obj.modifiers.new("Solid", "SOLIDIFY")
    solid.thickness = thickness
    solid.offset = 0.0
    apply_modifiers(obj)
    if obj.data.materials.get(mat.name) is None and len(obj.data.materials) == 0:
        obj.data.materials.append(mat)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    curl_leaf(obj, length, curl)
    return obj


def make_taper(name, length, r_bot, r_top, segments, mat, smooth):
    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        segments=segments,
        radius1=r_bot,
        radius2=r_top,
        depth=length,
    )
    for vert in bm.verts:
        vert.co.z += length * 0.5
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    obj = mesh_from_bmesh(name, bm)
    assign_mat(obj, mat, smooth)
    return obj


def make_sphere(name, radius, mat):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=8, v_segments=6, radius=radius)
    obj = mesh_from_bmesh(name, bm)
    assign_mat(obj, mat, smooth=True)
    return obj


def align_z(direction):
    z_axis = direction.normalized()
    helper = Vector((0.0, 1.0, 0.0)) if abs(z_axis.z) > 0.95 else Vector((0.0, 0.0, 1.0))
    x_axis = helper.cross(z_axis).normalized()
    y_axis = z_axis.cross(x_axis).normalized()
    return Matrix(
        (
            (x_axis.x, y_axis.x, z_axis.x, 0.0),
            (x_axis.y, y_axis.y, z_axis.y, 0.0),
            (x_axis.z, y_axis.z, z_axis.z, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        )
    )


def leaf_matrix(origin, tip_dir, outward, normal_tilt, twist):
    """Local +Y runs base-to-tip. Local +Z is the face normal, kept perpendicular to the tip."""
    outward = outward.normalized()
    tip = tip_dir.normalized()
    desired = (
        Vector((0.0, 0.0, 1.0)) * math.cos(normal_tilt) + outward * math.sin(normal_tilt)
    ).normalized()
    normal = desired - tip * desired.dot(tip)
    if normal.length < 1e-6:
        normal = Vector((0.0, 0.0, 1.0)).cross(tip)
        if normal.length < 1e-6:
            normal = Vector((1.0, 0.0, 0.0)).cross(tip)
    normal.normalize()
    if abs(twist) > 1e-6:
        normal = (Matrix.Rotation(twist, 4, tip) @ normal).normalized()
    axis_x = tip.cross(normal).normalized()
    normal = axis_x.cross(tip).normalized()
    return Matrix(
        (
            (axis_x.x, tip.x, normal.x, origin.x),
            (axis_x.y, tip.y, normal.y, origin.y),
            (axis_x.z, tip.z, normal.z, origin.z),
            (0.0, 0.0, 0.0, 1.0),
        )
    )


def leaf_material(mats, length, index):
    if length < 0.18:
        return mats["leaf_light"]
    if index % 3 == 0:
        return mats["leaf_deep"]
    if index % 3 == 1:
        return mats["leaf_mid"]
    return mats["leaf_deep"] if length > 0.33 else mats["leaf_mid"]


def build_foliage(mats, rng):
    parts = []
    for index, spec in enumerate(LEAF_PLAN):
        az_deg, tilt_deg, pet_len, leaf_len, width_ratio, pitch_deg, normal_deg, twist_deg, emerge_r = spec
        az_deg += rng.uniform(-3.0, 3.0)
        tilt_deg += rng.uniform(-1.5, 1.5)
        pet_len *= 1.0 + rng.uniform(-0.03, 0.03)
        leaf_len *= 1.0 + rng.uniform(-0.03, 0.03)
        pitch_deg += rng.uniform(-2.0, 2.0)
        normal_deg += rng.uniform(-2.0, 2.0)
        twist_deg += rng.uniform(-4.0, 4.0)
        emerge_r *= 1.0 + rng.uniform(-0.08, 0.08)

        azimuth = math.radians(az_deg)
        outward = Vector((math.cos(azimuth), math.sin(azimuth), 0.0))
        tilt = math.radians(tilt_deg)
        pet_dir = (
            outward * math.sin(tilt) + Vector((0.0, 0.0, 1.0)) * math.cos(tilt)
        ).normalized()
        emerge = outward * emerge_r + Vector((0.0, 0.0, SOIL_Z - 0.012))
        origin = emerge + pet_dir * pet_len

        pitch = math.radians(pitch_deg)
        tip_dir = (
            outward * math.cos(pitch) + Vector((0.0, 0.0, 1.0)) * math.sin(pitch)
        ).normalized()

        width = leaf_len * width_ratio
        thickness = max(0.0018, leaf_len * 0.0065)
        curl = leaf_len * 0.055
        mat = leaf_material(mats, leaf_len, index)
        leaf = make_leaf(
            f"leaf_{index:02d}",
            leaf_len,
            width,
            thickness,
            curl,
            with_holes=leaf_len >= 0.17,
            mat=mat,
        )
        leaf.matrix_world = leaf_matrix(
            origin,
            tip_dir,
            outward,
            math.radians(normal_deg),
            math.radians(twist_deg),
        )

        r_bot = 0.0045 + leaf_len * 0.014
        r_top = r_bot * 0.58
        embed = 0.014
        petiole = make_taper(
            f"petiole_{index:02d}",
            pet_len + embed,
            r_bot,
            r_top,
            8,
            mats["petiole"],
            smooth=True,
        )
        petiole.matrix_world = align_z(pet_dir)
        petiole.matrix_world.translation = emerge

        knuckle = make_sphere(
            f"knuckle_{index:02d}",
            0.007 + leaf_len * 0.012,
            mats["petiole"],
        )
        knuckle.matrix_world.translation = origin - pet_dir * 0.004

        parts.extend((leaf, petiole, knuckle))
    return parts


def bake(obj):
    obj.data.transform(obj.matrix_world.copy())
    obj.matrix_world = Matrix.Identity(4)
    obj.data.update()


def world_bounds(objs):
    xs, ys, zs = [], [], []
    for obj in objs:
        for vert in obj.data.vertices:
            xs.append(vert.co.x)
            ys.append(vert.co.y)
            zs.append(vert.co.z)
    return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)


def snap_to_target(objs):
    minx, maxx, miny, maxy, minz, maxz = world_bounds(objs)
    span_x = maxx - minx
    span_y = maxy - miny
    span_z = maxz - minz
    cx = (minx + maxx) * 0.5
    cy = (miny + maxy) * 0.5
    sx = WIDTH / span_x
    sy = DEPTH / span_y
    sz = HEIGHT / span_z
    print(
        f"PRE_BBOX_M width={span_x:.4f} depth={span_y:.4f} height={span_z:.4f} "
        f"center=({cx:.4f},{cy:.4f}) minz={minz:.4f}"
    )
    print(f"SNAP_SCALE x={sx:.4f} y={sy:.4f} z={sz:.4f}")
    for obj in objs:
        for vert in obj.data.vertices:
            x, y, z = vert.co
            vert.co = Vector(((x - cx) * sx, (y - cy) * sy, (z - minz) * sz))
        obj.data.update()


def join_parts(objs):
    for obj in bpy.context.view_layer.objects:
        obj.select_set(False)
    for obj in objs:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    plant = objs[0]
    plant.name = "F016"
    plant.data.name = "F016"
    return plant


def triangle_count(obj):
    obj.data.calc_loop_triangles()
    return len(obj.data.loop_triangles)


def bounds_dict(obj):
    minx, maxx, miny, maxy, minz, maxz = world_bounds([obj])
    return {
        "min": [minx, miny, minz],
        "max": [maxx, maxy, maxz],
        "width": maxx - minx,
        "depth": maxy - miny,
        "height": maxz - minz,
    }


def assert_close(measured, target, label):
    error = abs(measured - target) / target
    if error > 0.02:
        raise RuntimeError(
            f"{label} {measured:.4f} m is {error * 100:.2f}% off target {target:.4f} m"
        )


def look_at(obj, target):
    direction = (target - obj.location).normalized()
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_preview(scene, plant):
    world = scene.world
    if world is None:
        world = bpy.data.worlds.new("World")
        scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background:
        background.inputs["Color"].default_value = (0.86, 0.83, 0.78, 1.0)
        background.inputs["Strength"].default_value = 0.35

    ground_bm = bmesh.new()
    bmesh.ops.create_grid(ground_bm, x_segments=1, y_segments=1, size=3.0)
    for vert in ground_bm.verts:
        vert.co.z = -0.002
    ground = mesh_from_bmesh("PREVIEW_GROUND", ground_bm)
    ground_mat = make_material("PreviewFloor", (0.76, 0.70, 0.62), 0.95, 0.1)
    assign_mat(ground, ground_mat, smooth=True)

    target = Vector((0.0, 0.0, HEIGHT * 0.46))
    camera_data = bpy.data.cameras.new("PreviewCamera")
    camera_data.lens = 65.0
    camera_data.sensor_width = 36.0
    camera_data.clip_start = 0.05
    camera_data.clip_end = 40.0
    camera = bpy.data.objects.new("PreviewCamera", camera_data)
    link_object(camera)
    scene.camera = camera
    direction = Vector((0.42, -1.02, 0.78))
    half_fov = math.atan((camera_data.sensor_width * 0.5) / camera_data.lens)
    projected = max(HEIGHT * 0.98, WIDTH * 0.85 + DEPTH * 0.62)
    distance = (projected * 0.5 * 1.38) / math.tan(half_fov)
    camera.location = target + direction.normalized() * distance
    look_at(camera, target)

    sun_data = bpy.data.lights.new("KeySun", "SUN")
    sun_data.energy = 3.4
    sun_data.angle = math.radians(2.5)
    sun_data.color = (1.0, 0.95, 0.86)
    sun = bpy.data.objects.new("KeySun", sun_data)
    link_object(sun)
    sun.location = (1.8, -1.6, 2.6)
    look_at(sun, Vector((0.0, 0.0, HEIGHT * 0.55)))

    fill_data = bpy.data.lights.new("Fill", "AREA")
    fill_data.energy = 180.0
    fill_data.size = 2.2
    fill_data.color = (0.85, 0.90, 1.0)
    fill = bpy.data.objects.new("Fill", fill_data)
    link_object(fill)
    fill.location = (-1.4, -1.1, 1.0)
    look_at(fill, target)

    rim_data = bpy.data.lights.new("Rim", "AREA")
    rim_data.energy = 90.0
    rim_data.size = 1.4
    rim_data.color = (1.0, 0.94, 0.84)
    rim = bpy.data.objects.new("Rim", rim_data)
    link_object(rim)
    rim.location = (-0.3, 1.5, 1.7)
    look_at(rim, Vector((0.0, 0.0, HEIGHT * 0.7)))

    scene.render.resolution_x = 512
    scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    try:
        scene.view_settings.view_transform = "AgX"
    except TypeError:
        pass
    scene.view_settings.exposure = -0.05
    return camera


def render_preview(scene, filepath):
    scene.render.filepath = str(filepath)
    engines = [e.identifier for e in scene.render.bl_rna.properties["engine"].enum_items]
    print("ENGINES", engines)
    order = []
    for name in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "BLENDER_WORKBENCH", "CYCLES"):
        if name in engines:
            order.append(name)
    errors = []
    for engine in order:
        scene.render.engine = engine
        if engine == "CYCLES":
            scene.cycles.device = "CPU"
            scene.cycles.samples = 48
            try:
                scene.cycles.use_denoising = True
            except Exception:
                scene.cycles.use_denoising = False
        if engine == "BLENDER_WORKBENCH":
            scene.display.shading.light = "STUDIO"
            scene.display.shading.color_type = "MATERIAL"
        if hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
            scene.eevee.taa_render_samples = 16
        if hasattr(scene, "eevee") and hasattr(scene.eevee, "use_raytracing"):
            scene.eevee.use_raytracing = False
        try:
            bpy.ops.render.render(write_still=True)
            print("RENDER_OK", engine)
            return engine
        except Exception as exc:
            errors.append(f"{engine}: {exc}")
            print("RENDER_FAIL", engine, exc)
    raise RuntimeError("preview render failed: " + " | ".join(errors))


def export_glb(plant, filepath):
    import addon_utils

    addon_utils.enable("io_scene_gltf2")
    for obj in bpy.context.view_layer.objects:
        obj.select_set(False)
    plant.select_set(True)
    bpy.context.view_layer.objects.active = plant
    bpy.ops.export_scene.gltf(
        filepath=str(filepath),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_materials="EXPORT",
    )


def glb_bounds(path):
    data = Path(path).read_bytes()
    if data[:4] != b"glTF":
        raise RuntimeError("exported file is not glTF binary")
    offset = 12
    length, chunk_type = struct.unpack_from("<II", data, offset)
    if chunk_type != 0x4E4F534A:
        raise RuntimeError("glTF JSON chunk missing")
    payload = json.loads(data[offset + 8 : offset + 8 + length])
    mins = [math.inf, math.inf, math.inf]
    maxs = [-math.inf, -math.inf, -math.inf]
    for mesh in payload.get("meshes", []):
        for prim in mesh.get("primitives", []):
            accessor = payload["accessors"][prim["attributes"]["POSITION"]]
            for axis in range(3):
                mins[axis] = min(mins[axis], accessor["min"][axis])
                maxs[axis] = max(maxs[axis], accessor["max"][axis])
    return mins, maxs, payload


def write_metadata(path, box, tris):
    payload = {
        "id": "F016",
        "name": "Monstera Floor Plant",
        "category": "Plant",
        "style": "Bohemian",
        "room": "Living Room",
        "price_usd": 79,
        "dimensions_in": {"width": WIDTH_IN, "depth": DEPTH_IN, "height": HEIGHT_IN},
        "dimensions_m": {
            "width": round(WIDTH, 6),
            "depth": round(DEPTH, 6),
            "height": round(HEIGHT, 6),
        },
        "bounding_box_m": {
            "min": [round(v, 6) for v in box["min"]],
            "max": [round(v, 6) for v in box["max"]],
            "width": round(box["width"], 6),
            "depth": round(box["depth"], 6),
            "height": round(box["height"], 6),
        },
        "triangle_count": tris,
        "seed": SEED,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")


def main():
    outdir = parse_outdir()
    print(f"SEED {SEED}")
    print(f"TARGET_M width={WIDTH:.4f} depth={DEPTH:.4f} height={HEIGHT:.4f}")
    rng = random.Random(SEED)
    scene = reset_scene()
    mats = make_materials()
    parts = []
    parts.extend(build_pot(mats))
    parts.extend(build_foliage(mats, rng))
    bpy.context.view_layer.update()
    for part in parts:
        bake(part)
    snap_to_target(parts)
    plant = join_parts(parts)
    box = bounds_dict(plant)
    tris = triangle_count(plant)
    print(
        f"BBOX_M width={box['width']:.4f} depth={box['depth']:.4f} "
        f"height={box['height']:.4f}"
    )
    print(f"BBOX_MIN {box['min']}")
    print(f"BBOX_MAX {box['max']}")
    print(f"TRIS {tris}")
    assert_close(box["width"], WIDTH, "width")
    assert_close(box["depth"], DEPTH, "depth")
    assert_close(box["height"], HEIGHT, "height")
    if abs(box["min"][2]) > 1e-5:
        raise RuntimeError("model does not sit on Z=0")
    if abs((box["min"][0] + box["max"][0]) * 0.5) > 1e-4:
        raise RuntimeError("model is not centered on X")
    if abs((box["min"][1] + box["max"][1]) * 0.5) > 1e-4:
        raise RuntimeError("model is not centered on Y")
    if tris > 30000:
        raise RuntimeError(f"triangle count {tris} exceeds 30000")
    if tris < 100:
        raise RuntimeError("mesh is unexpectedly empty")

    write_metadata(outdir / "metadata.json", box, tris)
    add_preview(scene, plant)
    preview_path = outdir / "preview.png"
    render_preview(scene, preview_path)
    blend_path = outdir / "model.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    glb_path = outdir / "model.glb"
    export_glb(plant, glb_path)
    mins, maxs, payload = glb_bounds(glb_path)
    print(f"GLB_MIN {mins}")
    print(f"GLB_MAX {maxs}")
    # glTF is Y-up: Blender (x, y, z) -> (x, z, -y). Sizes must match.
    glb_width = maxs[0] - mins[0]
    glb_height = maxs[1] - mins[1]
    glb_depth = maxs[2] - mins[2]
    print(f"GLB_SIZE width={glb_width:.4f} depth={glb_depth:.4f} height={glb_height:.4f}")
    assert_close(glb_width, WIDTH, "glb width")
    assert_close(glb_depth, DEPTH, "glb depth")
    assert_close(glb_height, HEIGHT, "glb height")
    names = [node.get("name", "") for node in payload.get("nodes", [])]
    print("GLB_NODES", names)
    if not any("F016" in name for name in names):
        raise RuntimeError(f"exported nodes missing F016: {names}")
    print("EXPORT_OK", outdir)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
