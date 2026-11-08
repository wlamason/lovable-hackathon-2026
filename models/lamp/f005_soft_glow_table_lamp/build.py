#!/usr/bin/env python3
"""Build catalog item F005 Soft Glow Table Lamp and export it.

Run:
  blender -b --factory-startup --python build.py -- --outdir <dir>

Default outdir is this script's folder. Uses only bpy, bmesh, and mathutils.
"""

import json
import math
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector

INCH = 0.0254
WIDTH_IN = 10.0
DEPTH_IN = 10.0
HEIGHT_IN = 20.0
TARGET = (WIDTH_IN * INCH, DEPTH_IN * INCH, HEIGHT_IN * INCH)  # 0.254, 0.254, 0.508

# Shade is the widest and tallest part. Peaks land on the +/- X and +/- Y axes.
SHADE_R = TARGET[0] * 0.5
SHADE_H = 5.15 * INCH
SHADE_TOP = TARGET[2]
SHADE_BOTTOM = SHADE_TOP - SHADE_H
N_FLUTES = 12
SEGS_PER_FLUTE = 8
N_AROUND = N_FLUTES * SEGS_PER_FLUTE
SHELL = 0.0028

# (z fraction from rim up to crown, radius fraction of SHADE_R)
SHADE_PROFILE = [
    (0.00, 0.875),
    (0.045, 0.945),
    (0.11, 0.985),
    (0.19, 1.000),
    (0.30, 0.978),
    (0.42, 0.915),
    (0.54, 0.820),
    (0.66, 0.690),
    (0.77, 0.530),
    (0.86, 0.360),
    (0.93, 0.210),
    (0.975, 0.090),
]


def parse_outdir():
    outdir = Path(__file__).resolve().parent
    if "--" in sys.argv:
        args = sys.argv[sys.argv.index("--") + 1 :]
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


def new_mesh(name):
    mesh = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj, mesh


def finish_mesh(obj, mesh, bm):
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    for poly in mesh.polygons:
        poly.use_smooth = True
    obj.location = (0.0, 0.0, 0.0)
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)


def flute_factors(theta, z_frac):
    """Return (radial scale, downward hem offset). Peaks stay at scale 1."""
    c = math.cos(N_FLUTES * theta)
    # Broader lobes than a pure sine, closer to a pressed-glass mushroom shade.
    c = math.copysign(abs(c) ** 0.65, c)
    fade = (1.0 - z_frac) ** 0.55
    amp = 0.062 * fade
    scale = 1.0 - amp * (1.0 - c)
    hem = max(0.0, 1.0 - z_frac / 0.22)
    z_off = -0.004 * hem * (1.0 - c) * 0.5
    return scale, z_off


def build_shade():
    obj, mesh = new_mesh("Shade")
    bm = bmesh.new()
    outer_rings = []
    inner_rings = []

    for z_frac, r_frac in SHADE_PROFILE:
        outer = []
        inner = []
        z_base = SHADE_BOTTOM + z_frac * SHADE_H
        for j in range(N_AROUND):
            theta = 2.0 * math.pi * j / N_AROUND
            scale, z_off = flute_factors(theta, z_frac)
            r = SHADE_R * r_frac * scale
            z = z_base + z_off
            outer.append(bm.verts.new((r * math.cos(theta), r * math.sin(theta), z)))
            ri = max(r - SHELL, 0.0015)
            inner.append(
                bm.verts.new((ri * math.cos(theta), ri * math.sin(theta), z - SHELL * 0.45))
            )
        outer_rings.append(outer)
        inner_rings.append(inner)

    def bridge(rings, flip):
        for i in range(len(rings) - 1):
            a = rings[i]
            b = rings[i + 1]
            for j in range(N_AROUND):
                j2 = (j + 1) % N_AROUND
                if flip:
                    bm.faces.new((a[j], b[j], b[j2], a[j2]))
                else:
                    bm.faces.new((a[j], a[j2], b[j2], b[j]))

    bridge(outer_rings, flip=False)
    bridge(inner_rings, flip=True)

    # Scalloped lip between the outer and inner rims.
    lip_o = outer_rings[0]
    lip_i = inner_rings[0]
    for j in range(N_AROUND):
        j2 = (j + 1) % N_AROUND
        bm.faces.new((lip_o[j], lip_i[j], lip_i[j2], lip_o[j2]))

    # Crown: outer pole is the exact top of the bounding box.
    outer_pole = bm.verts.new((0.0, 0.0, SHADE_TOP))
    inner_pole = bm.verts.new((0.0, 0.0, SHADE_TOP - SHELL))
    top_o = outer_rings[-1]
    top_i = inner_rings[-1]
    for j in range(N_AROUND):
        j2 = (j + 1) % N_AROUND
        bm.faces.new((top_o[j], outer_pole, top_o[j2]))
        bm.faces.new((top_i[j2], inner_pole, top_i[j]))

    finish_mesh(obj, mesh, bm)
    return obj


def lathe(bm, profile, n=72):
    """Spin a (radius, z) profile around Z. Profile may start/end on the axis."""
    rings = []
    for r, z in profile:
        if r <= 1e-8:
            rings.append(("pole", bm.verts.new((0.0, 0.0, z))))
        else:
            ring = []
            for j in range(n):
                theta = 2.0 * math.pi * j / n
                ring.append(bm.verts.new((r * math.cos(theta), r * math.sin(theta), z)))
            rings.append(("ring", ring))

    for (ta, a), (tb, b) in zip(rings, rings[1:]):
        if ta == "ring" and tb == "ring":
            for j in range(n):
                j2 = (j + 1) % n
                bm.faces.new((a[j], a[j2], b[j2], b[j]))
        elif ta == "pole" and tb == "ring":
            for j in range(n):
                j2 = (j + 1) % n
                bm.faces.new((a, b[j], b[j2]))
        elif ta == "ring" and tb == "pole":
            for j in range(n):
                j2 = (j + 1) % n
                bm.faces.new((a[j2], a[j], b))
        else:
            raise RuntimeError("degenerate lathe segment")


def build_brass():
    """Disc foot, slender stem, and socket cup. All stay inside the shade radius."""
    obj, mesh = new_mesh("Brass")
    bm = bmesh.new()
    # 4.0 in foot, 0.46 in stem, socket hidden up inside the shade.
    foot_r = 2.0 * INCH
    stem_r = 0.23 * INCH
    lathe(
        bm,
        [
            (0.000, 0.000),
            (foot_r * 0.92, 0.000),
            (foot_r, 0.0014),
            (foot_r, 0.0052),
            (foot_r * 0.90, 0.0082),
            (0.55 * INCH, 0.0082),
            (0.38 * INCH, 0.0115),
            (stem_r, 0.020),
            (stem_r, 0.405),
            (0.34 * INCH, 0.414),
            (0.48 * INCH, 0.422),
            (0.48 * INCH, 0.446),
            (0.30 * INCH, 0.454),
            (stem_r * 0.7, 0.460),
            (0.000, 0.460),
        ],
        n=48,
    )
    finish_mesh(obj, mesh, bm)
    return obj


def build_bulb():
    obj, mesh = new_mesh("Bulb")
    bm = bmesh.new()
    result = bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=16, radius=0.62 * INCH)
    bmesh.ops.translate(bm, verts=result["verts"], vec=(0.0, 0.0, 0.436))
    finish_mesh(obj, mesh, bm)
    return obj


def bsdf(mat):
    mat.use_nodes = True
    node = mat.node_tree.nodes.get("Principled BSDF")
    if node is None:
        node = mat.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
    return node


def set_input(node, names, value):
    for name in names:
        sock = node.inputs.get(name)
        if sock is not None:
            sock.default_value = value
            return
    raise KeyError("none of %s on Principled BSDF" % (names,))


def make_materials():
    brass = bpy.data.materials.new("Brass")
    b = bsdf(brass)
    set_input(b, ("Base Color",), (0.66, 0.50, 0.26, 1.0))
    set_input(b, ("Metallic",), 1.0)
    set_input(b, ("Roughness",), 0.30)
    set_input(b, ("Specular IOR Level", "Specular"), 0.5)

    shade = bpy.data.materials.new("SoftShade")
    s = bsdf(shade)
    set_input(s, ("Base Color",), (0.96, 0.94, 0.90, 1.0))
    set_input(s, ("Metallic",), 0.0)
    set_input(s, ("Roughness",), 0.28)
    set_input(s, ("Transmission Weight", "Transmission"), 0.22)
    set_input(s, ("IOR",), 1.45)
    set_input(s, ("Emission Color", "Emission"), (1.0, 0.90, 0.74, 1.0))
    set_input(s, ("Emission Strength",), 0.45)

    bulb = bpy.data.materials.new("Bulb")
    u = bsdf(bulb)
    set_input(u, ("Base Color",), (1.0, 0.86, 0.62, 1.0))
    set_input(u, ("Roughness",), 0.15)
    set_input(u, ("Emission Color", "Emission"), (1.0, 0.82, 0.48, 1.0))
    set_input(u, ("Emission Strength",), 6.0)
    return brass, shade, bulb


def assign(obj, mat):
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)


def join_parts(parts):
    for obj in bpy.context.view_layer.objects:
        obj.select_set(False)
    for obj in parts:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = "F005_Soft_Glow_Table_Lamp"
    obj.data.name = "F005_Soft_Glow_Table_Lamp"
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return obj


def world_bbox(obj):
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    xs = [c.x for c in corners]
    ys = [c.y for c in corners]
    zs = [c.z for c in corners]
    mn = (min(xs), min(ys), min(zs))
    mx = (max(xs), max(ys), max(zs))
    return mn, mx


def triangle_count(obj):
    mesh = obj.data
    mesh.calc_loop_triangles()
    return len(mesh.loop_triangles)


def assert_proportions(mn, mx):
    size = (mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2])
    print("measured_bbox_min", tuple(round(v, 6) for v in mn))
    print("measured_bbox_max", tuple(round(v, 6) for v in mx))
    print("measured_size_m", tuple(round(v, 6) for v in size))
    labels = ("width", "depth", "height")
    for label, got, want in zip(labels, size, TARGET):
        err = abs(got - want) / want
        print("%s error %.4f%%" % (label, err * 100.0))
        if err > 0.02:
            raise SystemExit("bbox %s off by %.2f%%" % (label, err * 100.0))
    if abs(mn[2]) > 1e-4:
        raise SystemExit("model does not sit on Z=0 (min z = %s)" % mn[2])
    if abs(mn[0] + mx[0]) > 1e-4 or abs(mn[1] + mx[1]) > 1e-4:
        raise SystemExit("footprint is not centered on the origin")
    return size


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_preview_rig(target):
    scene = bpy.context.scene
    world = bpy.data.worlds.new("PreviewWorld")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.62, 0.61, 0.59, 1.0)
    bg.inputs[1].default_value = 0.7

    floor_mesh = bpy.data.meshes.new("Floor")
    floor = bpy.data.objects.new("Floor", floor_mesh)
    scene.collection.objects.link(floor)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.9)
    bm.to_mesh(floor_mesh)
    bm.free()
    floor.location = (0.0, 0.0, -0.0008)
    mat = bpy.data.materials.new("Floor")
    node = bsdf(mat)
    set_input(node, ("Base Color",), (0.55, 0.50, 0.45, 1.0))
    set_input(node, ("Roughness",), 0.85)
    assign(floor, mat)

    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens = 55
    cam = bpy.data.objects.new("Camera", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    # Front of the lamp faces -Y; show a three-quarter view from the front-left.
    # Far enough back that the full 20 in height sits inside the square frame.
    cam.location = (-0.58, -1.02, 0.56)
    look_at(cam, (0.0, 0.0, 0.25))

    key_data = bpy.data.lights.new("Key", "AREA")
    key_data.energy = 45
    key_data.size = 0.45
    key_data.color = (1.0, 0.96, 0.90)
    key = bpy.data.objects.new("Key", key_data)
    scene.collection.objects.link(key)
    key.location = (-0.45, -0.55, 0.70)
    look_at(key, (0.0, 0.0, 0.25))

    fill_data = bpy.data.lights.new("Fill", "AREA")
    fill_data.energy = 18
    fill_data.size = 0.6
    fill_data.color = (0.85, 0.90, 1.0)
    fill = bpy.data.objects.new("Fill", fill_data)
    scene.collection.objects.link(fill)
    fill.location = (0.55, -0.25, 0.40)
    look_at(fill, (0.0, 0.0, 0.22))

    # Warm practical so the shade reads as glowing in the still.
    glow_data = bpy.data.lights.new("Glow", "POINT")
    glow_data.energy = 4
    glow_data.color = (1.0, 0.82, 0.55)
    glow = bpy.data.objects.new("Glow", glow_data)
    scene.collection.objects.link(glow)
    glow.location = (0.0, 0.0, 0.44)

    scene.render.resolution_x = 512
    scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    engine = "BLENDER_EEVEE_NEXT"
    try:
        scene.render.engine = engine
    except TypeError:
        engine = "BLENDER_WORKBENCH"
        scene.render.engine = engine
    if engine.startswith("BLENDER_EEVEE"):
        eevee = scene.eevee
        if hasattr(eevee, "taa_render_samples"):
            eevee.taa_render_samples = 24
        if hasattr(eevee, "use_bloom"):
            eevee.use_bloom = True
    print("render_engine", scene.render.engine)


def render_preview(path):
    scene = bpy.context.scene
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def export_glb(obj, path):
    for other in bpy.context.view_layer.objects:
        other.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.gltf(
        filepath=str(path),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_materials="EXPORT",
    )


def write_metadata(path, mn, mx, size, tris):
    payload = {
        "id": "F005",
        "name": "Soft Glow Table Lamp",
        "category": "Lamp",
        "style": "Minimal",
        "room": "Living Room",
        "price_usd": 69,
        "dimensions_in": {"width": WIDTH_IN, "depth": DEPTH_IN, "height": HEIGHT_IN},
        "dimensions_m": {"width": TARGET[0], "depth": TARGET[1], "height": TARGET[2]},
        "bounding_box_m": {
            "min": {"x": round(mn[0], 6), "y": round(mn[1], 6), "z": round(mn[2], 6)},
            "max": {"x": round(mx[0], 6), "y": round(mx[1], 6), "z": round(mx[2], 6)},
            "size": {
                "width": round(size[0], 6),
                "depth": round(size[1], 6),
                "height": round(size[2], 6),
            },
        },
        "triangle_count": tris,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")


def main():
    outdir = parse_outdir()
    reset_scene()
    brass_mat, shade_mat, bulb_mat = make_materials()
    shade = build_shade()
    brass = build_brass()
    bulb = build_bulb()
    assign(shade, shade_mat)
    assign(brass, brass_mat)
    assign(bulb, bulb_mat)
    lamp = join_parts([shade, brass, bulb])
    mn, mx = world_bbox(lamp)
    size = assert_proportions(mn, mx)
    tris = triangle_count(lamp)
    print("triangle_count", tris)

    add_preview_rig((0.0, 0.0, 0.25))
    render_preview(outdir / "preview.png")
    export_glb(lamp, outdir / "model.glb")
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(outdir / "model.blend"))
    write_metadata(outdir / "metadata.json", mn, mx, size, tris)
    print("wrote", outdir)


if __name__ == "__main__":
    main()
