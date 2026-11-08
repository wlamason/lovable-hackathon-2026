"""Build catalog item F015 Snake Plant and export glTF, blend, preview, metadata.

Run:
    blender -b --factory-startup --python build.py -- --outdir <dir>

Default outdir is this script's folder. Uses only bpy, bmesh, and mathutils.
Randomness is driven by a fixed seed so rebuilds match.
"""

import json
import math
import random
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

SEED = 15015
INCH = 0.0254
WIDTH_IN, DEPTH_IN, HEIGHT_IN = 12.0, 12.0, 32.0
WIDTH = WIDTH_IN * INCH
DEPTH = DEPTH_IN * INCH
HEIGHT = HEIGHT_IN * INCH

# Pot and soil, meters. Foliage fills the remaining height and the 12 in footprint.
POT_TOP_Z = 0.180
SOIL_CENTER_Z = 0.156
LEAF_BASE_Z = 0.140


def parse_outdir():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []
    outdir = Path(__file__).resolve().parent
    for i, arg in enumerate(argv):
        if arg == "--outdir" and i + 1 < len(argv):
            outdir = Path(argv[i + 1]).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    return outdir


def clamp(value, low, high):
    return max(low, min(high, value))


def smoothstep(edge0, edge1, value):
    if edge1 == edge0:
        return 0.0
    t = clamp((value - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def lerp(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(len(a)))


def vnorm(vec, fallback):
    if vec.length < 1e-8:
        return fallback.copy()
    return vec.normalized()


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes, bpy.data.materials, bpy.data.lights, bpy.data.cameras):
        for block in list(datablocks):
            if block.users == 0:
                datablocks.remove(block)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0


def set_input(node, names, value):
    for name in names:
        if name in node.inputs:
            node.inputs[name].default_value = value
            return


def new_principled(name, color, roughness, specular, coat=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.use_backface_culling = False
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (320, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (40, 0)
    set_input(bsdf, ("Base Color",), (*color, 1.0))
    set_input(bsdf, ("Roughness",), roughness)
    set_input(bsdf, ("Metallic",), 0.0)
    set_input(bsdf, ("Specular IOR Level", "Specular"), specular)
    set_input(bsdf, ("Coat Weight",), coat)
    if coat:
        set_input(bsdf, ("Coat Roughness",), 0.35)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    mat.diffuse_color = (*color, 1.0)
    return mat, bsdf


def attach_vertex_color(mat, bsdf):
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    try:
        color_node = nodes.new("ShaderNodeVertexColor")
    except RuntimeError:
        color_node = nodes.new("ShaderNodeColorAttribute")
    color_node.location = (-220, 40)
    color_node.layer_name = "Col"
    links.new(color_node.outputs["Color"], bsdf.inputs["Base Color"])


def make_materials():
    pot, _ = new_principled("F015_Ceramic", (0.86, 0.82, 0.75), 0.58, 0.28, coat=0.04)
    soil, soil_bsdf = new_principled("F015_Soil", (0.18, 0.13, 0.08), 0.94, 0.12)
    leaf, leaf_bsdf = new_principled("F015_Leaf", (0.07, 0.22, 0.10), 0.40, 0.42, coat=0.14)
    attach_vertex_color(soil, soil_bsdf)
    attach_vertex_color(leaf, leaf_bsdf)
    return {"pot": pot, "soil": soil, "leaf": leaf}


def mesh_object(name, bm, material, colors=None):
    mesh = bpy.data.meshes.new(name)
    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    mesh.materials.append(material)
    if colors is not None:
        attr = mesh.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="POINT")
        for index, color in enumerate(colors):
            attr.data[index].color = color
        mesh.color_attributes.active_color_index = 0
        if hasattr(mesh.color_attributes, "render_color_index"):
            # render_color_index follows the active color once it is assigned
            mesh.color_attributes.active_color_index = mesh.color_attributes.find("Col")
    return obj


def shade(obj, angle=None):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    if angle is None:
        bpy.ops.object.shade_smooth()
        return
    try:
        bpy.ops.object.shade_auto_smooth(angle=angle)
    except (AttributeError, TypeError, RuntimeError):
        bpy.ops.object.shade_smooth()


def revolved(name, profile, material, segments, colors_fn=None):
    bm = bmesh.new()
    rings = []
    color_for_vert = []
    for radius, z in profile:
        ring = []
        if radius <= 1e-8:
            vert = bm.verts.new((0.0, 0.0, z))
            ring = [vert]
            if colors_fn:
                color_for_vert.append((vert, colors_fn(0.0, 0.0, z)))
        else:
            for i in range(segments):
                angle = math.tau * i / segments
                x = radius * math.cos(angle)
                y = radius * math.sin(angle)
                vert = bm.verts.new((x, y, z))
                ring.append(vert)
                if colors_fn:
                    color_for_vert.append((vert, colors_fn(x, y, z)))
        rings.append(ring)

    for j in range(len(profile) - 1):
        r0 = profile[j][0]
        r1 = profile[j + 1][0]
        ring0 = rings[j]
        ring1 = rings[j + 1]
        if r0 <= 1e-8 and r1 <= 1e-8:
            continue
        if r0 <= 1e-8:
            pole = ring0[0]
            for i in range(segments):
                face = bm.faces.new((pole, ring1[i], ring1[(i + 1) % segments]))
                face.smooth = True
            continue
        if r1 <= 1e-8:
            pole = ring1[0]
            for i in range(segments):
                face = bm.faces.new((ring0[i], pole, ring0[(i + 1) % segments]))
                face.smooth = True
            continue
        for i in range(segments):
            i2 = (i + 1) % segments
            face = bm.faces.new((ring0[i], ring0[i2], ring1[i2], ring1[i]))
            face.smooth = True

    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.verts.index_update()
    colors = None
    if colors_fn:
        colors = [(1.0, 1.0, 1.0, 1.0)] * len(bm.verts)
        for vert, color in color_for_vert:
            colors[vert.index] = color
    return mesh_object(name, bm, material, colors)


def pot_profile():
    # Closed ceramic shell: flat foot, soft taper, rolled lip, hollow interior.
    return [
        (0.000, 0.000),
        (0.064, 0.000),
        (0.072, 0.005),
        (0.074, 0.016),
        (0.078, 0.048),
        (0.084, 0.100),
        (0.090, 0.148),
        (0.094, 0.162),
        (0.100, 0.170),
        (0.102, 0.176),
        (0.098, 0.180),
        (0.090, 0.180),
        (0.084, 0.176),
        (0.080, 0.168),
        (0.078, 0.156),
        (0.076, 0.142),
        (0.074, 0.128),
        (0.000, 0.128),
    ]


def soil_color(x, y, z):
    n = 0.5 + 0.5 * math.sin(x * 150.0 + y * 80.0) * math.sin(y * 130.0 - x * 50.0)
    fleck = 0.5 + 0.5 * math.sin(x * 420.0 - y * 360.0 + z * 40.0)
    dark = (0.11, 0.075, 0.045)
    mid = (0.22, 0.15, 0.09)
    color = lerp(dark, mid, clamp(0.35 + 0.5 * n + 0.15 * fleck, 0.0, 1.0))
    return (*color, 1.0)


def build_pot(material):
    return revolved("F015_Pot", pot_profile(), material, segments=48)


def build_soil(material):
    # Slightly domed soil disc tucked under the rim.
    profile = [
        (0.000, SOIL_CENTER_Z),
        (0.028, 0.154),
        (0.055, 0.150),
        (0.074, 0.147),
        (0.081, 0.146),
    ]
    obj = revolved("F015_Soil", profile, material, segments=40, colors_fn=soil_color)
    # Surface of revolution may face downward; the dome's outer normals should point up.
    mesh = obj.data
    mesh.calc_loop_triangles()
    # Average polygon normal via a temporary bmesh would be heavier; flip if the
    # highest vertex's nearby faces point down by checking a known top face later.
    return obj


def ensure_soil_faces_up(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    bm.normal_update()
    if not bm.faces:
        bm.free()
        return
    average_z = sum(face.normal.z for face in bm.faces) / len(bm.faces)
    if average_z < 0.0:
        bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
        bm.normal_update()
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def leaf_width_factor(t):
    if t < 0.10:
        return 0.30 + 0.70 * (t / 0.10)
    if t < 0.68:
        return 1.0 - 0.05 * ((t - 0.32) / 0.36) ** 2
    u = (t - 0.68) / 0.32
    return max(0.05, (1.0 - u) ** 1.30)


def leaf_color(z, u, t, phase, side, hue):
    chevron = (0.5 - abs(u - 0.5)) * 0.010
    zz = z + chevron
    wave = (
        0.52 * math.sin(zz * 54.0 + phase)
        + 0.30 * math.sin(zz * 121.0 + phase * 1.6 + 0.4)
        + 0.18 * math.sin(zz * 22.0 + phase * 0.35)
    )
    light = clamp((wave - 0.28) / 0.72, 0.0, 1.0) ** 1.45
    dark = (0.028, 0.105, 0.052)
    mid = (0.055, 0.185, 0.085)
    pale = (0.40, 0.48, 0.28)
    color = lerp(lerp(dark, mid, 0.65), pale, light)
    sheath = 1.0 - smoothstep(0.0, 0.16, t)
    color = lerp(color, (0.025, 0.09, 0.045), sheath * 0.50)
    rib = math.exp(-((u - 0.5) ** 2) / 0.010)
    color = lerp(color, (color[0] * 0.72, color[1] * 0.80, color[2] * 0.68), rib * 0.40)
    edge = abs(u - 0.5) * 2.0
    margin = smoothstep(0.64, 0.94, edge)
    margin *= smoothstep(0.05, 0.16, t) * (1.0 - 0.35 * smoothstep(0.90, 1.0, t))
    yellow = (0.64, 0.52, 0.10)
    color = lerp(color, yellow, margin * 0.90)
    if side == "back":
        color = tuple(channel * 0.88 for channel in color)
    # Tiny per-leaf shift so the clump is not one flat green.
    color = (
        clamp(color[0] * (1.0 + hue * 0.25), 0.0, 1.0),
        clamp(color[1] * (1.0 + hue), 0.0, 1.0),
        clamp(color[2] * (1.0 - hue * 0.20), 0.0, 1.0),
    )
    return (*color, 1.0)


def leaf_specs(rng):
    # yaw degrees (0 = lean toward +X, -90 = front / -Y), lean, length, width, twist.
    base = [
        (8.0, 2.2, 0.675, 0.040, 2.0),
        (-16.0, 3.4, 0.600, 0.046, -4.0),
        (22.0, 4.0, 0.545, 0.034, 5.0),
        (158.0, 4.2, 0.500, 0.032, -3.0),
        (0.0, 13.0, 0.640, 0.058, 6.0),
        (90.0, 13.0, 0.640, 0.055, -5.0),
        (180.0, 13.0, 0.640, 0.057, 4.0),
        (-90.0, 13.2, 0.655, 0.062, -6.0),
        (42.0, 10.0, 0.505, 0.044, 7.0),
        (136.0, 10.0, 0.485, 0.042, -4.0),
        (-136.0, 9.6, 0.485, 0.042, 3.0),
        (-42.0, 10.0, 0.510, 0.045, -6.0),
        (-64.0, 8.4, 0.440, 0.036, 2.5),
        (72.0, 8.0, 0.425, 0.034, -2.5),
    ]
    specs = []
    for yaw, lean, length, width, twist in base:
        specs.append(
            {
                "yaw": math.radians(yaw + rng.uniform(-1.4, 1.4)),
                "lean": math.radians(max(1.2, lean + rng.uniform(-0.35, 0.35))),
                "length": length * rng.uniform(0.985, 1.015),
                "width": width * rng.uniform(0.97, 1.03),
                "thickness": rng.uniform(0.010, 0.0125),
                "twist": math.radians(twist + rng.uniform(-1.5, 1.5)),
                "base_r": 0.004 + 0.020 * clamp(lean / 13.0, 0.0, 1.0) + rng.uniform(-0.0015, 0.0015),
                "base_z": LEAF_BASE_Z + rng.uniform(-0.004, 0.003),
                "side": rng.uniform(-0.008, 0.008),
                "phase": rng.uniform(0.0, math.tau),
                "hue": rng.uniform(-0.06, 0.06),
            }
        )
    return specs


def centerline(spec, t):
    lean = spec["lean"] * (0.48 + 0.52 * t)
    dist = spec["length"] * t
    radial = Vector((math.cos(spec["yaw"]), math.sin(spec["yaw"]), 0.0))
    tangential = Vector((-math.sin(spec["yaw"]), math.cos(spec["yaw"]), 0.0))
    base = Vector(
        (
            radial.x * spec["base_r"],
            radial.y * spec["base_r"],
            spec["base_z"],
        )
    )
    return (
        base
        + radial * (math.sin(lean) * dist)
        + tangential * (spec["side"] * math.sin(math.pi * t))
        + Vector((0.0, 0.0, math.cos(lean) * dist))
    )


def leaf_frame(spec, t):
    eps = 0.012
    p0 = centerline(spec, max(0.0, t - eps))
    p1 = centerline(spec, min(1.0, t + eps))
    tangent = vnorm(p1 - p0, Vector((0.0, 0.0, 1.0)))
    radial = Vector((math.cos(spec["yaw"]), math.sin(spec["yaw"]), 0.0))
    bitangent = tangent.cross(radial)
    if bitangent.length < 1e-6:
        bitangent = Vector((-math.sin(spec["yaw"]), math.cos(spec["yaw"]), 0.0))
    bitangent.normalize()
    normal = bitangent.cross(tangent)
    normal = vnorm(normal, radial)
    if normal.dot(radial) < 0.0:
        normal.negate()
        bitangent.negate()
    return centerline(spec, t), bitangent, normal


def add_leaf(bm, spec, color_for_vert):
    segments = 20
    across = 8
    stations = []
    for i in range(segments):
        t = i / segments
        center, bitangent, normal = leaf_frame(spec, t)
        width = spec["width"] * leaf_width_factor(t)
        thick = spec["thickness"] * (1.0 - 0.55 * smoothstep(0.75, 1.0, t))
        twist = spec["twist"] * (t ** 1.05)
        ct, st = math.cos(twist), math.sin(twist)
        samples = []
        us = [j / (across - 1) for j in range(across)]
        for u in us:
            samples.append((u, "front"))
        for u in reversed(us[1:-1]):
            samples.append((u, "back"))
        ring = []
        for u, side in samples:
            s = math.sin(math.pi * u) ** 0.72
            if side == "front":
                local_y = 0.20 * thick * s
            else:
                local_y = -0.80 * thick * s
            local_x = (u - 0.5) * width
            xr = local_x * ct - local_y * st
            yr = local_x * st + local_y * ct
            vert = bm.verts.new(center + bitangent * xr + normal * yr)
            ring.append(vert)
            color_for_vert.append((vert, leaf_color(vert.co.z, u, t, spec["phase"], side, spec["hue"])))
        stations.append(ring)

    loop_count = len(stations[0])
    for i in range(len(stations) - 1):
        for k in range(loop_count):
            k2 = (k + 1) % loop_count
            face = bm.faces.new(
                (
                    stations[i][k],
                    stations[i][k2],
                    stations[i + 1][k2],
                    stations[i + 1][k],
                )
            )
            face.smooth = True

    tip_center, _, _ = leaf_frame(spec, 1.0)
    tip = bm.verts.new(tip_center)
    color_for_vert.append((tip, leaf_color(tip.co.z, 0.5, 1.0, spec["phase"], "front", spec["hue"])))
    last = stations[-1]
    for k in range(loop_count):
        face = bm.faces.new((last[k], last[(k + 1) % loop_count], tip))
        face.smooth = True

    base_center = centerline(spec, 0.0)
    base = bm.verts.new(base_center)
    color_for_vert.append((base, leaf_color(base.co.z, 0.5, 0.0, spec["phase"], "front", spec["hue"])))
    first = stations[0]
    for k in range(loop_count):
        face = bm.faces.new((first[(k + 1) % loop_count], first[k], base))
        face.smooth = True


def build_leaves(material, rng):
    bm = bmesh.new()
    color_for_vert = []
    for spec in leaf_specs(rng):
        add_leaf(bm, spec, color_for_vert)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.verts.index_update()
    colors = [(0.05, 0.2, 0.08, 1.0)] * len(bm.verts)
    for vert, color in color_for_vert:
        colors[vert.index] = color
    return mesh_object("F015_Leaves", bm, material, colors)


def vertex_bounds(objects):
    min_x = min_y = min_z = 1e9
    max_x = max_y = max_z = -1e9
    for obj in objects:
        for vert in obj.data.vertices:
            x, y, z = vert.co
            min_x = min(min_x, x)
            max_x = max(max_x, x)
            min_y = min(min_y, y)
            max_y = max(max_y, y)
            min_z = min(min_z, z)
            max_z = max(max_z, z)
    return min_x, max_x, min_y, max_y, min_z, max_z


def fit_to_catalog(leaves, anchors):
    """Scale foliage so the full plant bbox matches the catalog size.

    The pot stays circular. Leaf vertices are mapped so the combined
    footprint is the target width and depth and the tallest tip hits the
    target height, with the pot bottom kept on Z = 0.
    """
    min_x, max_x, min_y, max_y, min_z, max_z = vertex_bounds([leaves])
    center_x = (min_x + max_x) * 0.5
    center_y = (min_y + max_y) * 0.5
    span_x = max(max_x - min_x, 1e-6)
    span_y = max(max_y - min_y, 1e-6)
    # Height is measured from the floor, not from the buried leaf bases.
    anchor_z = min(vert.co.z for obj in anchors for vert in obj.data.vertices)
    scale_z = (HEIGHT - anchor_z) / max(max_z - anchor_z, 1e-6)
    scale_x = WIDTH / span_x
    scale_y = DEPTH / span_y
    for vert in leaves.data.vertices:
        vert.co.x = (vert.co.x - center_x) * scale_x
        vert.co.y = (vert.co.y - center_y) * scale_y
        vert.co.z = anchor_z + (vert.co.z - anchor_z) * scale_z
    leaves.data.update()

    min_x, max_x, min_y, max_y, min_z, max_z = vertex_bounds([leaves, *anchors])
    shift_x = -0.5 * (min_x + max_x)
    shift_y = -0.5 * (min_y + max_y)
    shift_z = -min_z
    for obj in (leaves, *anchors):
        for vert in obj.data.vertices:
            vert.co.x += shift_x
            vert.co.y += shift_y
            vert.co.z += shift_z
        obj.data.update()
    print(
        f"fit scales xyz=({scale_x:.4f}, {scale_y:.4f}, {scale_z:.4f}) "
        f"shift=({shift_x:.4f}, {shift_y:.4f}, {shift_z:.4f})"
    )


def triangle_count(objects):
    total = 0
    for obj in objects:
        obj.data.calc_loop_triangles()
        total += len(obj.data.loop_triangles)
    return total


def measure(objects):
    bpy.context.view_layer.update()
    min_x, max_x, min_y, max_y, min_z, max_z = vertex_bounds(objects)
    size = (max_x - min_x, max_y - min_y, max_z - min_z)
    print(
        "F015 bbox m: "
        f"min=({min_x:.4f}, {min_y:.4f}, {min_z:.4f}) "
        f"max=({max_x:.4f}, {max_y:.4f}, {max_z:.4f}) "
        f"size=({size[0]:.4f}, {size[1]:.4f}, {size[2]:.4f}) "
        f"target=({WIDTH:.4f}, {DEPTH:.4f}, {HEIGHT:.4f})"
    )
    errors = (
        abs(size[0] - WIDTH) / WIDTH,
        abs(size[1] - DEPTH) / DEPTH,
        abs(size[2] - HEIGHT) / HEIGHT,
    )
    center = (abs(min_x + max_x), abs(min_y + max_y), abs(min_z))
    if max(errors) > 0.02 or max(center) > 0.005:
        raise SystemExit(
            f"Bounding box is outside tolerance: errors={errors} center_offset={center}"
        )
    return (min_x, min_y, min_z), (max_x, max_y, max_z), size


def parent_hierarchy(*objects):
    root = bpy.data.objects.new("F015", None)
    root.empty_display_type = "PLAIN_AXES"
    root.empty_display_size = 0.12
    bpy.context.scene.collection.objects.link(root)
    for obj in objects:
        obj.parent = root
        obj.matrix_parent_inverse = root.matrix_world.inverted()
    return root


def apply_transforms(objects):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)


def export_glb(root, path):
    bpy.ops.object.select_all(action="DESELECT")
    root.select_set(True)
    for child in root.children:
        child.select_set(True)
    bpy.context.view_layer.objects.active = root
    bpy.ops.export_scene.gltf(
        filepath=str(path),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_materials="EXPORT",
        export_vertex_color="MATERIAL",
        export_cameras=False,
        export_lights=False,
        export_animations=False,
    )


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_area(name, location, energy, size, target):
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.size = size
    data.shape = "DISK"
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    look_at(obj, target)
    return obj


def setup_studio(scene):
    world = scene.world
    if world is None:
        world = bpy.data.worlds.new("World")
        scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background is None:
        background = world.node_tree.nodes.new("ShaderNodeBackground")
        world.node_tree.links.new(
            background.outputs["Background"],
            world.node_tree.nodes["World Output"].inputs["Surface"],
        )
    background.inputs[0].default_value = (0.46, 0.48, 0.47, 1.0)
    background.inputs[1].default_value = 0.40

    target = (0.0, 0.0, HEIGHT * 0.46)
    add_area("Key", (-0.95, -1.55, 1.65), 55.0, 1.25, target)
    add_area("Fill", (1.40, -0.95, 0.85), 18.0, 1.60, target)
    add_area("Rim", (0.20, 1.20, 1.30), 26.0, 0.75, target)

    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens = 50
    cam_data.sensor_fit = "VERTICAL"
    cam_data.clip_start = 0.01
    cam = bpy.data.objects.new("Camera", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    # Square frame with a little air around the full 12 x 12 x 32 in silhouette.
    yaw = math.radians(28.0)
    pitch = math.radians(11.0)
    distance = 2.25
    cam.location = (
        target[0] + math.sin(yaw) * math.cos(pitch) * distance,
        target[1] - math.cos(yaw) * math.cos(pitch) * distance,
        target[2] + math.sin(pitch) * distance,
    )
    look_at(cam, target)
    return cam


def add_ground():
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=4.0)
    for vert in bm.verts:
        vert.co.z = -0.001
    mesh = bpy.data.meshes.new("PREVIEW_Ground")
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new("PREVIEW_Ground", mesh)
    bpy.context.scene.collection.objects.link(obj)
    mat, _ = new_principled("PREVIEW_Ground", (0.46, 0.48, 0.47), 0.86, 0.15)
    mesh.materials.append(mat)
    return obj


def configure_render(scene, path):
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 512
    scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    scene.render.filepath = str(path)
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    eevee = scene.eevee
    for attr, value in (
        ("taa_render_samples", 48),
        ("taa_samples", 16),
        ("use_raytracing", False),
    ):
        if hasattr(eevee, attr):
            setattr(eevee, attr, value)


def write_metadata(path, bounds_min, bounds_max, size, triangles):
    payload = {
        "id": "F015",
        "name": "Snake Plant",
        "category": "Plant",
        "style": "Minimal",
        "room": "Living Room",
        "price_usd": 39,
        "dimensions_in": {"width": WIDTH_IN, "depth": DEPTH_IN, "height": HEIGHT_IN},
        "dimensions_m": {
            "width": round(WIDTH, 4),
            "depth": round(DEPTH, 4),
            "height": round(HEIGHT, 4),
        },
        "bounding_box_m": {
            "min": {"x": round(bounds_min[0], 6), "y": round(bounds_min[1], 6), "z": round(bounds_min[2], 6)},
            "max": {"x": round(bounds_max[0], 6), "y": round(bounds_max[1], 6), "z": round(bounds_max[2], 6)},
            "width": round(size[0], 6),
            "depth": round(size[1], 6),
            "height": round(size[2], 6),
        },
        "triangle_count": triangles,
        "seed": SEED,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main():
    outdir = parse_outdir()
    random.seed(SEED)
    clear_scene()
    rng = random.Random(SEED)
    materials = make_materials()
    pot = build_pot(materials["pot"])
    soil = build_soil(materials["soil"])
    ensure_soil_faces_up(soil)
    leaves = build_leaves(materials["leaf"], rng)
    fit_to_catalog(leaves, (pot, soil))
    shade(pot, angle=math.radians(35))
    shade(soil, angle=math.radians(60))
    shade(leaves, angle=math.radians(50))
    apply_transforms([pot, soil, leaves])
    bounds_min, bounds_max, size = measure([pot, soil, leaves])
    triangles = triangle_count([pot, soil, leaves])
    print(f"F015 triangles: {triangles}")
    root = parent_hierarchy(pot, soil, leaves)
    write_metadata(outdir / "metadata.json", bounds_min, bounds_max, size, triangles)

    scene = bpy.context.scene
    setup_studio(scene)
    export_glb(root, outdir / "model.glb")
    ground = add_ground()
    configure_render(scene, outdir / "preview.png")
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(ground, do_unlink=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(outdir / "model.blend"))
    backup = outdir / "model.blend1"
    if backup.exists():
        backup.unlink()
    print(f"Wrote exports in {outdir}")


if __name__ == "__main__":
    main()
