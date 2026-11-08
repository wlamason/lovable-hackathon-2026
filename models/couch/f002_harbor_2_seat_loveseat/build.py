"""Build F002 Harbor 2-Seat Loveseat and export glTF, blend, preview, metadata.

Run:
  blender -b --factory-startup --python build.py -- --outdir <dir>
"""

import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

IN = 0.0254
SPEC_IN = {"width": 60.0, "depth": 35.0, "height": 34.0}
W = SPEC_IN["width"] * IN
D = SPEC_IN["depth"] * IN
H = SPEC_IN["height"] * IN


def parse_outdir():
    outdir = os.path.dirname(os.path.abspath(__file__))
    if "--" in sys.argv:
        args = sys.argv[sys.argv.index("--") + 1 :]
        if "--outdir" in args:
            outdir = os.path.abspath(args[args.index("--outdir") + 1])
    os.makedirs(outdir, exist_ok=True)
    return outdir


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = "METERS"


def make_material(name, color, roughness=0.72, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = (color[0], color[1], color[2], 1.0)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (color[0], color[1], color[2], 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return mat


def mesh_from_bm(name, bm, material, smooth=False):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for poly in me.polygons:
        poly.use_smooth = smooth
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    if material is not None:
        obj.data.materials.append(material)
    return obj


def _box_bm(x0, x1, y0, y1, z0, z1, bevel=0.0, segments=1):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x = x0 + (v.co.x + 0.5) * (x1 - x0)
        v.co.y = y0 + (v.co.y + 0.5) * (y1 - y0)
        v.co.z = z0 + (v.co.z + 0.5) * (z1 - z0)
    if bevel > 0:
        min_dim = min(x1 - x0, y1 - y0, z1 - z0)
        offset = min(bevel, min_dim * 0.32)
        bmesh.ops.bevel(
            bm,
            geom=list(bm.edges),
            offset=offset,
            offset_type="OFFSET",
            segments=segments,
            profile=0.5,
            affect="EDGES",
            clamp_overlap=True,
        )
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    return bm


def add_box(name, bounds, material, bevel=0.0, segments=1, smooth=False):
    x0, x1, y0, y1, z0, z1 = bounds
    bm = _box_bm(x0, x1, y0, y1, z0, z1, bevel=bevel, segments=segments)
    return mesh_from_bm(name, bm, material, smooth=smooth)


def add_tapered_leg(name, cx, cy, z0, z1, top, bot, material):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        size = bot if v.co.z < 0 else top
        v.co.x = cx + v.co.x * size
        v.co.y = cy + v.co.y * size
        v.co.z = z0 + (v.co.z + 0.5) * (z1 - z0)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    return mesh_from_bm(name, bm, material, smooth=False)


def lean_back(obj, pivot_y, pivot_z, degrees):
    """Rotate around X so the top moves toward +Y (the back of the sofa)."""
    theta = math.radians(-degrees)
    ca, sa = math.cos(theta), math.sin(theta)
    for v in obj.data.vertices:
        y = v.co.y - pivot_y
        z = v.co.z - pivot_z
        v.co.y = pivot_y + (y * ca - z * sa)
        v.co.z = pivot_z + (y * sa + z * ca)
    obj.data.update()


def yaw(obj, pivot_x, pivot_y, degrees):
    theta = math.radians(degrees)
    ca, sa = math.cos(theta), math.sin(theta)
    for v in obj.data.vertices:
        x = v.co.x - pivot_x
        y = v.co.y - pivot_y
        v.co.x = pivot_x + (x * ca - y * sa)
        v.co.y = pivot_y + (x * sa + y * ca)
    obj.data.update()


def build():
    linen = make_material("F002_Linen", (0.58, 0.49, 0.37), roughness=0.9)
    cushion = make_material("F002_Cushion", (0.70, 0.61, 0.47), roughness=0.86)
    shadow = make_material("F002_Shadow", (0.32, 0.26, 0.19), roughness=0.95)
    wood = make_material("F002_Driftwood", (0.36, 0.22, 0.11), roughness=0.5)
    navy = make_material("F002_Navy", (0.10, 0.18, 0.30), roughness=0.72)
    cream = make_material("F002_Cream", (0.78, 0.71, 0.58), roughness=0.84)
    seaglass = make_material("F002_SeaGlass", (0.28, 0.44, 0.43), roughness=0.8)

    parts = []
    arm_w = 5.5 * IN
    leg_h = 5.0 * IN
    leg_top = 2.45 * IN
    leg_bot = 1.55 * IN

    # Four tapered driftwood legs, inset under the corners.
    margin_x = 3.15 * IN
    cx = W / 2 - margin_x - leg_top / 2
    cy_front = -D / 2 + 3.5 * IN + leg_top / 2
    cy_back = D / 2 - 4.4 * IN - leg_top / 2
    for sx in (-1, 1):
        for sy, cy in ((-1, cy_front), (1, cy_back)):
            parts.append(
                add_tapered_leg(
                    f"leg_{sx}_{sy}",
                    sx * cx,
                    cy,
                    0.0,
                    leg_h + 0.004,
                    leg_top,
                    leg_bot,
                    wood,
                )
            )

    # Track arms run the full depth and set the width.
    for sx, name in ((-1, "arm_l"), (1, "arm_r")):
        outer = sx * W / 2
        inner = sx * (W / 2 - arm_w)
        x0, x1 = (inner, outer) if sx > 0 else (outer, inner)
        parts.append(
            add_box(
                name,
                (x0, x1, -D / 2, D / 2, leg_h, 24.0 * IN),
                linen,
                bevel=0.012,
                segments=1,
                smooth=True,
            )
        )

    inner_l = -W / 2 + arm_w
    inner_r = W / 2 - arm_w

    # Deck / front rail between the arms. Slightly darker so cushion gaps read.
    parts.append(
        add_box(
            "deck",
            (
                inner_l - 0.012,
                inner_r + 0.012,
                -D / 2 + 0.012,
                D / 2 - 0.02,
                leg_h,
                11.25 * IN,
            ),
            linen,
            bevel=0.006,
            segments=1,
            smooth=False,
        )
    )

    # Back frame rises above the arms to the overall height.
    parts.append(
        add_box(
            "back",
            (
                inner_l - 0.01,
                inner_r + 0.01,
                11.0 * IN,
                D / 2,
                11.0 * IN,
                H,
            ),
            linen,
            bevel=0.012,
            segments=1,
            smooth=True,
        )
    )

    # Two loose seat cushions.
    gap = 0.7 * IN
    side = 0.28 * IN
    seat_x0 = inner_l + side
    seat_x1 = inner_r - side
    mid = (seat_x0 + seat_x1) / 2
    seat_bounds_y = (-D / 2 + 0.006, 8.0 * IN)
    seat_z = (10.55 * IN, 18.5 * IN)
    for name, x0, x1 in (
        ("seat_l", seat_x0, mid - gap / 2),
        ("seat_r", mid + gap / 2, seat_x1),
    ):
        parts.append(
            add_box(
                name,
                (x0, x1, seat_bounds_y[0], seat_bounds_y[1], seat_z[0], seat_z[1]),
                cushion,
                bevel=0.02,
                segments=2,
                smooth=True,
            )
        )
    parts.append(
        add_box(
            "seat_gap",
            (
                mid - gap / 2 + 0.002,
                mid + gap / 2 - 0.002,
                seat_bounds_y[0] + 0.03,
                seat_bounds_y[1] - 0.02,
                seat_z[0] + 0.01,
                seat_z[1] - 0.018,
            ),
            shadow,
        )
    )

    # Two loose back cushions, leaned a few degrees into the back frame.
    bc_z0 = 16.0 * IN
    bc_z1 = 32.2 * IN
    bc_y0 = 5.6 * IN
    bc_y1 = 12.6 * IN
    bc_gap = 0.4 * IN
    for name, x0, x1 in (
        ("back_l", seat_x0 + 0.004, mid - bc_gap / 2),
        ("back_r", mid + bc_gap / 2, seat_x1 - 0.004),
    ):
        obj = add_box(
            name,
            (x0, x1, bc_y0, bc_y1, bc_z0, bc_z1),
            cushion,
            bevel=0.016,
            segments=2,
            smooth=True,
        )
        lean_back(obj, (bc_y0 + bc_y1) / 2, bc_z0, 8.0)
        parts.append(obj)
    parts.append(
        add_box(
            "back_gap",
            (
                mid - bc_gap / 2 + 0.002,
                mid + bc_gap / 2 - 0.002,
                bc_y0 + 0.02,
                bc_y1 - 0.01,
                bc_z0 + 0.02,
                bc_z1 - 0.02,
            ),
            shadow,
        )
    )
    # Lean the crevice with the cushions so it stays tucked between them.
    lean_back(parts[-1], (bc_y0 + bc_y1) / 2, bc_z0, 8.0)

    def throw_pillow(prefix, cx, width, depth, height, z0, y0, lean, yaw_deg, body_mat, bands):
        x0, x1 = cx - width / 2, cx + width / 2
        y1 = y0 + depth
        z1 = z0 + height
        pivot_y = (y0 + y1) / 2
        group = [
            add_box(
                prefix,
                (x0, x1, y0, y1, z0, z1),
                body_mat,
                bevel=0.014,
                segments=2,
                smooth=True,
            )
        ]
        band_h = height * 0.1
        for i, frac in enumerate(bands):
            cz = z0 + height * frac
            group.append(
                add_box(
                    f"{prefix}_band_{i}",
                    (
                        x0 + 0.014,
                        x1 - 0.014,
                        y0 - 0.007,
                        y0 + 0.005,
                        cz - band_h / 2,
                        cz + band_h / 2,
                    ),
                    navy,
                    bevel=0.0025,
                    segments=1,
                    smooth=True,
                )
            )
        for obj in group:
            lean_back(obj, pivot_y, z0, lean)
            yaw(obj, cx, pivot_y, yaw_deg)
        parts.extend(group)

    # Striped cream pillow on the left seat, sea-glass pillow on the right.
    left_cx = (seat_x0 + (mid - gap / 2)) / 2
    right_cx = ((mid + gap / 2) + seat_x1) / 2
    # Sit on the seat and lean against the back cushions, mostly in front of them.
    throw_pillow(
        "pillow_l",
        left_cx,
        14.0 * IN,
        5.0 * IN,
        10.0 * IN,
        17.85 * IN,
        0.35 * IN,
        13.0,
        -2.0,
        cream,
        (0.22, 0.5, 0.78),
    )
    throw_pillow(
        "pillow_r",
        right_cx,
        13.2 * IN,
        4.8 * IN,
        9.6 * IN,
        17.95 * IN,
        0.7 * IN,
        12.0,
        2.0,
        seaglass,
        (),
    )
    return parts


def join_parts(parts):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in parts:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = "F002"
    obj.data.name = "F002"
    return obj


def bounds_of(obj):
    xs = [v.co.x for v in obj.data.vertices]
    ys = [v.co.y for v in obj.data.vertices]
    zs = [v.co.z for v in obj.data.vertices]
    return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)


def recenter_and_fit(obj):
    """Origin at bottom-center of the footprint, then snap bbox to the spec."""
    minx, maxx, miny, maxy, minz, maxz = bounds_of(obj)
    cx = (minx + maxx) / 2
    cy = (miny + maxy) / 2
    for v in obj.data.vertices:
        v.co.x -= cx
        v.co.y -= cy
        v.co.z -= minz
    obj.data.update()
    obj.location = (0.0, 0.0, 0.0)
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)

    minx, maxx, miny, maxy, minz, maxz = bounds_of(obj)
    measured = (maxx - minx, maxy - miny, maxz - minz)
    print(
        "bbox before fit (m): width {:.4f} depth {:.4f} height {:.4f}".format(*measured)
    )
    obj.scale = (W / measured[0], D / measured[1], H / measured[2])
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    minx, maxx, miny, maxy, minz, maxz = bounds_of(obj)
    # Re-pin in case of tiny float drift from the scale.
    cx = (minx + maxx) / 2
    cy = (miny + maxy) / 2
    for v in obj.data.vertices:
        v.co.x -= cx
        v.co.y -= cy
        v.co.z -= minz
    obj.data.update()
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return bounds_of(obj)


def triangle_count(obj):
    obj.data.calc_loop_triangles()
    return len(obj.data.loop_triangles)


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def render_preview(path):
    scene = bpy.context.scene
    world = bpy.data.worlds.new("PreviewWorld")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.78, 0.76, 0.72, 1.0)
    bg.inputs[1].default_value = 0.35

    floor_mat = make_material("PreviewFloor", (0.42, 0.40, 0.37), roughness=0.95)
    floor = add_box(
        "preview_floor",
        (-3.0, 3.0, -3.0, 3.0, -0.02, -0.004),
        floor_mat,
    )

    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens = 42
    cam_data.clip_start = 0.05
    cam = bpy.data.objects.new("Camera", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = (1.55, -2.15, 0.95)
    look_at(cam, (0.0, 0.0, 0.34))
    scene.camera = cam

    sun_data = bpy.data.lights.new("Key", "SUN")
    sun_data.energy = 1.15
    sun_data.color = (1.0, 0.96, 0.88)
    sun_data.angle = math.radians(8)
    sun = bpy.data.objects.new("Key", sun_data)
    bpy.context.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(50), math.radians(6), math.radians(-38))

    fill_data = bpy.data.lights.new("Fill", "AREA")
    fill_data.energy = 28
    fill_data.size = 2.4
    fill = bpy.data.objects.new("Fill", fill_data)
    bpy.context.collection.objects.link(fill)
    fill.location = (-1.3, -1.35, 0.85)
    look_at(fill, (0.0, 0.0, 0.35))

    rim_data = bpy.data.lights.new("Rim", "AREA")
    rim_data.energy = 18
    rim_data.size = 1.4
    rim = bpy.data.objects.new("Rim", rim_data)
    bpy.context.collection.objects.link(rim)
    rim.location = (-0.5, 1.45, 1.1)
    look_at(rim, (0.0, 0.0, 0.4))

    scene.render.resolution_x = 512
    scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = path
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.exposure = 0.0

    errors = []
    for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_WORKBENCH"):
        scene.render.engine = engine
        if engine == "BLENDER_EEVEE_NEXT":
            scene.eevee.taa_render_samples = 24
        else:
            scene.display.shading.light = "STUDIO"
            scene.display.shading.color_type = "MATERIAL"
            scene.display.render_aa = "8"
        try:
            bpy.ops.render.render(write_still=True)
            print(f"preview rendered with {engine}")
            break
        except Exception as exc:  # noqa: BLE001 — fall back to the next engine
            errors.append(f"{engine}: {exc}")
    else:
        raise RuntimeError("preview render failed: " + " | ".join(errors))

    # Preview helpers stay out of the source scene.
    bpy.data.objects.remove(floor, do_unlink=True)
    bpy.data.objects.remove(cam, do_unlink=True)
    bpy.data.objects.remove(sun, do_unlink=True)
    bpy.data.objects.remove(fill, do_unlink=True)
    bpy.data.objects.remove(rim, do_unlink=True)


def export_assets(obj, outdir, measured):
    def r(value):
        return round(float(value), 6)

    minx, maxx, miny, maxy, minz, maxz = [r(v) for v in measured]
    width, depth, height = r(maxx - minx), r(maxy - miny), r(maxz - minz)
    for label, got, target in (
        ("width", width, W),
        ("depth", depth, D),
        ("height", height, H),
    ):
        err = abs(got - target) / target
        print(f"{label}: {got:.6f} m (target {target:.6f}, error {err:.4%})")
        if err > 0.02:
            raise SystemExit(f"{label} outside 2% tolerance")

    tris = triangle_count(obj)
    print(f"triangles: {tris}")
    if tris > 30000:
        raise SystemExit(f"triangle count {tris} exceeds 30000")

    glb_path = os.path.join(outdir, "model.glb")
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.gltf(
        filepath=glb_path,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
    )

    meta = {
        "id": "F002",
        "name": "Harbor 2-Seat Loveseat",
        "category": "Couch",
        "style": "Coastal",
        "room": "Living Room",
        "price_usd": 649,
        "dimensions_in": SPEC_IN,
        "dimensions_m": {"width": r(W), "depth": r(D), "height": r(H)},
        "bounding_box_m": {
            "width": width,
            "depth": depth,
            "height": height,
            "min": [minx, miny, minz],
            "max": [maxx, maxy, maxz],
        },
        "triangle_count": tris,
    }
    with open(os.path.join(outdir, "metadata.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
        fh.write("\n")

    blend_path = os.path.join(outdir, "model.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    render_preview(os.path.join(outdir, "preview.png"))
    # Source scene is the model alone; preview lights are removed inside render.
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print("wrote", glb_path)
    return meta


def main():
    outdir = parse_outdir()
    reset_scene()
    parts = build()
    obj = join_parts(parts)
    measured = recenter_and_fit(obj)
    export_assets(obj, outdir, measured)


if __name__ == "__main__":
    main()
