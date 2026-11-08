#!/usr/bin/env python3
"""Build F004 Reading Arc Floor Lamp and export glb, blend, preview, metadata.

Run:
  blender -b --factory-startup --python build.py -- --outdir <dir>

Units are meters. Width is X, depth is Y, height is Z. Front faces -Y.
Origin is the bottom center of the footprint; the lamp sits on Z = 0.
"""

import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

INCH = 0.0254
WIDTH_IN = 18.0
DEPTH_IN = 18.0
HEIGHT_IN = 66.0
WIDTH = WIDTH_IN * INCH
DEPTH = DEPTH_IN * INCH
HEIGHT = HEIGHT_IN * INCH
HALF_W = WIDTH * 0.5
HALF_D = DEPTH * 0.5

# Stem sits slightly rearward so the compact arc can reach forward
# and still keep the shade inside the 18 in footprint.
Y_POLE = 0.064
Y_SHADE = -0.088
THETA_END = math.radians(74.0)
TUBE_R = 0.0086


def parse_outdir():
    outdir = os.path.dirname(os.path.abspath(__file__))
    if "--" in sys.argv:
        args = sys.argv[sys.argv.index("--") + 1 :]
        if "--outdir" in args:
            outdir = os.path.abspath(args[args.index("--outdir") + 1])
    os.makedirs(outdir, exist_ok=True)
    return outdir


def clear_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)
    for mat in list(bpy.data.materials):
        bpy.data.materials.remove(mat)


def make_material(name, color, roughness, metallic=0.0, emission=None, emission_strength=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.use_backface_culling = False
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.45
    if emission is not None:
        if "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = (*emission, 1.0)
            bsdf.inputs["Emission Strength"].default_value = emission_strength
        else:
            bsdf.inputs["Emission"].default_value = (*emission, 1.0)
    return mat


def new_vert(bm, co):
    return bm.verts.new(co)


def add_frustum(bm, cx, cy, z0, z1, r0, r1, segs, mat_idx, caps=True):
    """Z-axis frustum. Segment 0 lies on +X so the AABB hits the radius."""
    bottom = []
    top = []
    for i in range(segs):
        ang = 2.0 * math.pi * i / segs
        ca, sa = math.cos(ang), math.sin(ang)
        bottom.append(new_vert(bm, (cx + r0 * ca, cy + r0 * sa, z0)))
        top.append(new_vert(bm, (cx + r1 * ca, cy + r1 * sa, z1)))
    for i in range(segs):
        j = (i + 1) % segs
        face = bm.faces.new((bottom[i], bottom[j], top[j], top[i]))
        face.material_index = mat_idx
        face.smooth = True
    if caps and r0 > 0.0:
        center = new_vert(bm, (cx, cy, z0))
        for i in range(segs):
            j = (i + 1) % segs
            face = bm.faces.new((center, bottom[j], bottom[i]))
            face.material_index = mat_idx
            face.smooth = True
    if caps and r1 > 0.0:
        center = new_vert(bm, (cx, cy, z1))
        for i in range(segs):
            j = (i + 1) % segs
            face = bm.faces.new((center, top[i], top[j]))
            face.material_index = mat_idx
            face.smooth = True


def add_disc(bm, cx, cy, z, radius, segs, mat_idx):
    """Single-sided disc, normal +Z, plus a paper-thin underside so it is closed."""
    thickness = 0.0035
    add_frustum(bm, cx, cy, z, z + thickness, radius, radius, segs, mat_idx, caps=True)


def lathe_closed(bm, cx, cy, profile, segs, mat_idx):
    """Spin a closed (r, z) profile around a vertical axis at (cx, cy)."""
    rings = []
    for radius, z in profile:
        ring = []
        for i in range(segs):
            ang = 2.0 * math.pi * i / segs
            ring.append(
                new_vert(
                    bm,
                    (cx + radius * math.cos(ang), cy + radius * math.sin(ang), z),
                )
            )
        rings.append(ring)
    count = len(rings)
    for i in range(count):
        i2 = (i + 1) % count
        for j in range(segs):
            j2 = (j + 1) % segs
            face = bm.faces.new((rings[i][j], rings[i][j2], rings[i2][j2], rings[i2][j]))
            face.material_index = mat_idx
            face.smooth = True


def add_arc_tube(bm, y_pole, radius_arc, tube_r, theta_end, z_start, segs_len, segs_rad, mat_idx):
    """Circular arc in the YZ plane. theta = 0 is straight up; theta grows toward -Y."""
    rings = []
    thetas = [theta_end * i / segs_len for i in range(segs_len + 1)]
    center_y = y_pole - radius_arc
    for theta in thetas:
        cy = center_y + radius_arc * math.cos(theta)
        cz = z_start + radius_arc * math.sin(theta)
        radial = Vector((0.0, math.cos(theta), math.sin(theta)))
        side = Vector((1.0, 0.0, 0.0))
        ring = []
        for j in range(segs_rad):
            ang = 2.0 * math.pi * j / segs_rad
            offset = tube_r * (math.cos(ang) * radial + math.sin(ang) * side)
            ring.append(new_vert(bm, (offset.x, cy + offset.y, cz + offset.z)))
        rings.append(ring)
    for i in range(segs_len):
        for j in range(segs_rad):
            j2 = (j + 1) % segs_rad
            face = bm.faces.new((rings[i][j], rings[i][j2], rings[i + 1][j2], rings[i + 1][j]))
            face.material_index = mat_idx
            face.smooth = True
    for end, ring, theta in ((0, rings[0], thetas[0]), (1, rings[-1], thetas[-1])):
        cy = center_y + radius_arc * math.cos(theta)
        cz = z_start + radius_arc * math.sin(theta)
        center = new_vert(bm, (0.0, cy, cz))
        for j in range(segs_rad):
            j2 = (j + 1) % segs_rad
            if end == 0:
                face = bm.faces.new((center, ring[j], ring[j2]))
            else:
                face = bm.faces.new((center, ring[j2], ring[j]))
            face.material_index = mat_idx
            face.smooth = True


def arc_parameters():
    dy = Y_SHADE - Y_POLE
    radius_arc = dy / (math.cos(THETA_END) - 1.0)
    sin_t = math.sin(THETA_END)
    # Outermost tube vertex at the end of the arc lands on the target height.
    z_start = HEIGHT - (radius_arc + TUBE_R) * sin_t
    end_z = z_start + radius_arc * sin_t
    return radius_arc, z_start, end_z


def build_mesh():
    radius_arc, z_start, end_z = arc_parameters()
    shade_r = (Y_SHADE + HALF_D) - 0.006
    # Shallow saucer: the photo's flat disc, carried on a short arc.
    shade_top = end_z - 0.004
    shade_bottom = shade_top - 0.034
    inner_r = shade_r * 0.70

    bm = bmesh.new()
    metal = 0
    glow = 1

    # Weighted two-step round base. Outer radius is the 18 in footprint.
    add_frustum(bm, 0.0, 0.0, 0.0, 0.016, HALF_W, HALF_W, 96, metal, caps=True)
    add_frustum(bm, 0.0, 0.0, 0.016, 0.042, 0.206, 0.188, 80, metal, caps=True)
    # Stem boss, set back on the base.
    add_frustum(bm, 0.0, Y_POLE, 0.036, 0.072, 0.034, 0.020, 32, metal, caps=True)

    # Slim tapered stem, tangent into the arc (top radius matches the tube).
    add_frustum(bm, 0.0, Y_POLE, 0.058, z_start, 0.0155, TUBE_R, 28, metal, caps=True)

    add_arc_tube(bm, Y_POLE, radius_arc, TUBE_R, THETA_END, z_start, 40, 16, metal)

    # Short neck where the arc enters the shade.
    add_frustum(bm, 0.0, Y_SHADE, shade_top - 0.012, end_z, 0.012, 0.009, 20, metal, caps=True)

    # In-line rotary switch on the stem, at about hand height.
    switch_z = 1.05
    segs = 16
    knob_len = 0.022
    knob_r = 0.0065
    # Horizontal cylinder along +X, buried slightly in the stem.
    stem_r_at_switch = TUBE_R + (0.0155 - TUBE_R) * (z_start - switch_z) / (z_start - 0.058)
    x_inner = max(stem_r_at_switch * 0.45, 0.004)
    ring_a = []
    ring_b = []
    for i in range(segs):
        ang = 2.0 * math.pi * i / segs
        y = Y_POLE + knob_r * math.cos(ang)
        z = switch_z + knob_r * math.sin(ang)
        ring_a.append(new_vert(bm, (x_inner, y, z)))
        ring_b.append(new_vert(bm, (x_inner + knob_len, y, z)))
    for i in range(segs):
        j = (i + 1) % segs
        face = bm.faces.new((ring_a[i], ring_b[i], ring_b[j], ring_a[j]))
        face.material_index = metal
        face.smooth = True
    cap = new_vert(bm, (x_inner + knob_len, Y_POLE, switch_z))
    for i in range(segs):
        j = (i + 1) % segs
        face = bm.faces.new((cap, ring_b[j], ring_b[i]))
        face.material_index = metal
        face.smooth = True

    # Shallow disc shade (closed ring solid) with an open underside.
    lip = 0.0045
    profile = [
        (0.016, shade_top),
        (shade_r - lip, shade_top),
        (shade_r, shade_top - 0.006),
        (shade_r, shade_bottom + 0.008),
        (shade_r - 0.003, shade_bottom),
        (inner_r, shade_bottom),
        (inner_r, shade_bottom + 0.007),
        (0.016, shade_top - 0.007),
    ]
    lathe_closed(bm, 0.0, Y_SHADE, profile, 64, metal)

    # Warm diffuser panel set up inside the opening, like the reference glow.
    add_disc(bm, 0.0, Y_SHADE, shade_bottom + 0.004, inner_r - 0.008, 48, glow)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return bm, {
        "radius_arc": radius_arc,
        "z_start": z_start,
        "end_z": end_z,
        "shade_r": shade_r,
        "shade_top": shade_top,
        "shade_bottom": shade_bottom,
    }


def mesh_to_object(bm, materials):
    mesh = bpy.data.meshes.new("F004")
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new("F004", mesh)
    bpy.context.collection.objects.link(obj)
    for mat in materials:
        obj.data.materials.append(mat)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(48.0))
    except Exception as exc:
        print("shade_smooth_by_angle unavailable:", exc)
        bpy.ops.object.shade_smooth()
    for mod in list(obj.modifiers):
        bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return obj


def measure(obj):
    xs = [v.co.x for v in obj.data.vertices]
    ys = [v.co.y for v in obj.data.vertices]
    zs = [v.co.z for v in obj.data.vertices]
    obj.data.calc_loop_triangles()
    size = (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
    return {
        "min": {"x": min(xs), "y": min(ys), "z": min(zs)},
        "max": {"x": max(xs), "y": max(ys), "z": max(zs)},
        "size": {"width": size[0], "depth": size[1], "height": size[2]},
        "triangles": len(obj.data.loop_triangles),
    }


def assert_dimensions(box):
    size = box["size"]
    targets = (WIDTH, DEPTH, HEIGHT)
    names = ("width", "depth", "height")
    measured = (size["width"], size["depth"], size["height"])
    print(
        "BBOX min",
        tuple(round(box["min"][k], 5) for k in ("x", "y", "z")),
        "max",
        tuple(round(box["max"][k], 5) for k in ("x", "y", "z")),
    )
    print(
        "SIZE m",
        tuple(round(v, 5) for v in measured),
        "target",
        tuple(round(v, 5) for v in targets),
        "tris",
        box["triangles"],
    )
    for name, got, want in zip(names, measured, targets):
        err = abs(got - want) / want
        if err > 0.02:
            raise SystemExit(f"{name} {got:.4f} m is {err:.2%} off target {want:.4f} m")
    if abs(box["min"]["z"]) > 1e-4:
        raise SystemExit(f"base is not on the floor: min z = {box['min']['z']}")
    if abs((box["min"]["x"] + box["max"]["x"]) * 0.5) > 0.01:
        raise SystemExit("footprint is not centered on X")
    if abs((box["min"]["y"] + box["max"]["y"]) * 0.5) > 0.01:
        raise SystemExit("footprint is not centered on Y")


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_light(name, kind, location, energy, color, target=None, size=0.6):
    data = bpy.data.lights.new(name, kind)
    data.energy = energy
    data.color = color
    if kind == "AREA":
        data.size = size
        data.shape = "SQUARE"
    if kind == "POINT":
        data.use_shadow = False
        data.shadow_soft_size = 0.05
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    if target is not None:
        look_at(obj, target)
    return obj


def setup_preview(scene, info):
    world = scene.world
    if world is None:
        world = bpy.data.worlds.new("World")
        scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.70, 0.71, 0.73, 1.0)
        bg.inputs["Strength"].default_value = 0.42

    bpy.ops.mesh.primitive_plane_add(size=8.0, location=(0.0, 0.0, -0.001))
    floor = bpy.context.active_object
    floor.name = "PreviewFloor"
    floor_mat = make_material("Floor", (0.55, 0.54, 0.52), 0.92, metallic=0.0)
    floor.data.materials.append(floor_mat)

    # Orthographic three-quarter view so the full 66 in height and the arc both fit.
    target = (0.0, -0.02, 0.74)
    cam_data = bpy.data.cameras.new("Camera")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = 2.15
    cam_data.clip_start = 0.01
    cam_data.clip_end = 50.0
    cam = bpy.data.objects.new("Camera", cam_data)
    bpy.context.collection.objects.link(cam)
    # High enough to show the base disc, still low enough to catch the shade glow.
    cam.location = (1.65, -1.95, 1.42)
    look_at(cam, target)
    scene.camera = cam

    lamp_target = (0.0, -0.02, 1.05)
    add_light("Key", "AREA", (1.6, -2.2, 2.4), 140, (1.0, 0.96, 0.90), lamp_target, size=2.2)
    add_light("Fill", "AREA", (-2.0, -1.4, 1.4), 70, (0.80, 0.86, 1.0), lamp_target, size=2.2)
    add_light("Rim", "AREA", (-1.2, 2.2, 2.0), 260, (1.0, 0.95, 0.88), (0.0, 0.0, 1.2), size=1.4)
    glow_z = info["shade_bottom"] - 0.05
    add_light(
        "ShadeGlow",
        "POINT",
        (0.0, Y_SHADE, glow_z),
        18,
        (1.0, 0.70, 0.40),
    )

    scene.render.resolution_x = 512
    scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    scene.view_settings.exposure = 0.0


def render_preview(scene, path):
    scene.render.filepath = path
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
        scene.eevee.taa_render_samples = 32
        if hasattr(scene.eevee, "use_raytracing"):
            scene.eevee.use_raytracing = False
    except Exception as exc:
        print("Eevee setup failed, using Workbench:", exc)
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.display.shading.light = "STUDIO"
        scene.display.shading.color_type = "MATERIAL"
    bpy.ops.render.render(write_still=True)
    print("Rendered", path, "engine", scene.render.engine)


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
    print("Exported", path)


def _round_vec(values):
    return {key: round(float(values[key]), 6) for key in values}


def write_metadata(path, box):
    payload = {
        "id": "F004",
        "name": "Reading Arc Floor Lamp",
        "category": "Lamp",
        "style": "Modern",
        "room": "Living Room",
        "price_usd": 119,
        "dimensions_in": {"width": WIDTH_IN, "depth": DEPTH_IN, "height": HEIGHT_IN},
        "dimensions_m": {"width": round(WIDTH, 6), "depth": round(DEPTH, 6), "height": round(HEIGHT, 6)},
        "bounding_box_m": {
            "min": _round_vec(box["min"]),
            "max": _round_vec(box["max"]),
            "size": _round_vec(box["size"]),
        },
        "triangle_count": box["triangles"],
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    print("Wrote", path)


def main():
    outdir = parse_outdir()
    clear_scene()
    metal = make_material(
        "SatinBlack",
        (0.012, 0.012, 0.013),
        roughness=0.52,
        metallic=0.18,
    )
    glow = make_material(
        "WarmDiffuser",
        (1.0, 0.84, 0.62),
        roughness=0.4,
        metallic=0.0,
        emission=(1.0, 0.72, 0.38),
        emission_strength=8.0,
    )
    bm, info = build_mesh()
    obj = mesh_to_object(bm, [metal, glow])
    box = measure(obj)
    assert_dimensions(box)
    print(
        "Arc radius {:.3f} m, stem top z {:.3f}, shade r {:.3f}".format(
            info["radius_arc"], info["z_start"], info["shade_r"]
        )
    )

    scene = bpy.context.scene
    setup_preview(scene, info)
    blend_path = os.path.join(outdir, "model.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print("Saved", blend_path)

    export_glb(obj, os.path.join(outdir, "model.glb"))
    render_preview(scene, os.path.join(outdir, "preview.png"))
    write_metadata(os.path.join(outdir, "metadata.json"), box)
    # Save again so the blend keeps the camera that produced the preview.
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)


if __name__ == "__main__":
    main()
