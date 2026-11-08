#!/usr/bin/env python3
"""Build catalog item F001 Cloudline 3-Seat Couch from scratch and export it.

Run:
  blender -b --factory-startup --python build.py -- --outdir <dir>

Default outdir is this script's folder. Uses only bpy, bmesh, and mathutils.
"""

import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector


IN = 0.0254

# Spec dimensions: 84 in wide x 36 in deep x 33 in tall.
WIDTH_IN = 84.0
DEPTH_IN = 36.0
HEIGHT_IN = 33.0
W = WIDTH_IN * IN
D = DEPTH_IN * IN
H = HEIGHT_IN * IN

# Real-world sub-part sizes (inches), converted below.
LEG_H = 3.25 * IN
LEG_SIZE = 2.15 * IN
LEG_INSET_X = 6.25 * IN
LEG_INSET_Y = 5.25 * IN
PLINTH_TOP = 12.0 * IN          # deck the cushions sit on
SEAT_TOP = 18.0 * IN           # standard seat height
ARM_W = 5.5 * IN
ARM_H = 24.0 * IN              # track-arm top, ~6 in above the seat
BACK_T = 4.75 * IN             # upholstered back shell thickness
SEAT_GAP = 0.7 * IN            # channel between the three cushions
SIDE_GAP = 0.4 * IN            # air between cushion and arm
BACK_CUSH_D = 9.0 * IN         # plush back, keeps the seat near 22 in
SEAT_FRONT_INSET = 1.4 * IN


def parse_outdir():
    outdir = os.path.dirname(os.path.abspath(__file__))
    argv = sys.argv
    if "--" in argv:
        args = argv[argv.index("--") + 1 :]
        if "--outdir" in args:
            idx = args.index("--outdir")
            if idx + 1 >= len(args):
                raise SystemExit("--outdir requires a directory")
            outdir = args[idx + 1]
    os.makedirs(outdir, exist_ok=True)
    return outdir


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = "METERS"


def make_material(name, color, roughness=0.86, metallic=0.0, sheen=0.18, specular=0.28):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (color[0], color[1], color[2], 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    spec_key = "Specular IOR Level" if "Specular IOR Level" in bsdf.inputs else "Specular"
    if spec_key in bsdf.inputs:
        bsdf.inputs[spec_key].default_value = specular
    if sheen and "Sheen Weight" in bsdf.inputs:
        bsdf.inputs["Sheen Weight"].default_value = sheen
        if "Sheen Roughness" in bsdf.inputs:
            bsdf.inputs["Sheen Roughness"].default_value = 0.55
    return mat


def apply_scale(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)


def shade_by_angle(obj, angle_deg=50.0):
    """Smooth the bevels and keep the structural corners crisp."""
    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.normal_update()
    limit = math.radians(angle_deg)
    sharp = set()
    for edge in bm.edges:
        if len(edge.link_faces) != 2:
            sharp.add(edge.index)
            continue
        ang = edge.link_faces[0].normal.angle(edge.link_faces[1].normal)
        if ang >= limit:
            sharp.add(edge.index)
            edge.smooth = False
        else:
            edge.smooth = True
    bm.to_mesh(mesh)
    bm.free()
    if "sharp_edge" not in mesh.attributes:
        mesh.attributes.new("sharp_edge", "BOOLEAN", "EDGE")
    attr = mesh.attributes["sharp_edge"].data
    for i, item in enumerate(attr):
        item.value = i in sharp
    for poly in mesh.polygons:
        poly.use_smooth = True
    mesh.update()


def add_box(name, center, size, material, bevel=0.01, segments=2, angle_deg=45.0):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=center)
    obj = bpy.context.active_object
    obj.name = name
    obj.dimensions = size
    apply_scale(obj)
    if bevel > 0:
        mod = obj.modifiers.new("Bevel", "BEVEL")
        mod.width = bevel
        mod.segments = segments
        mod.limit_method = "ANGLE"
        mod.angle_limit = math.radians(30.0)
        mod.harden_normals = True
        mod.use_clamp_overlap = True
        mod.miter_outer = "MITER_ARC"
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=mod.name)
    shade_by_angle(obj, angle_deg)
    if obj.data.materials:
        obj.data.materials[0] = material
    else:
        obj.data.materials.append(material)
    return obj


def taper_leg(obj, factor=0.72):
    mesh = obj.data
    zmin = min(v.co.z for v in mesh.vertices)
    for vert in mesh.vertices:
        if abs(vert.co.z - zmin) < 1e-5:
            vert.co.x *= factor
            vert.co.y *= factor
    mesh.update()


def shear_top_back(obj, amount):
    """Lean the top of a cushion toward +Y (into the back)."""
    mesh = obj.data
    zs = [v.co.z for v in mesh.vertices]
    z0, z1 = min(zs), max(zs)
    span = max(z1 - z0, 1e-8)
    for vert in mesh.vertices:
        t = (vert.co.z - z0) / span
        vert.co.y += amount * t
    mesh.update()


def world_bounds(obj):
    bpy.context.view_layer.update()
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    minv = Vector(
        (
            min(c.x for c in corners),
            min(c.y for c in corners),
            min(c.z for c in corners),
        )
    )
    maxv = Vector(
        (
            max(c.x for c in corners),
            max(c.y for c in corners),
            max(c.z for c in corners),
        )
    )
    return minv, maxv, maxv - minv


def recenter_bottom_center(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    minv, maxv, _size = world_bounds(obj)
    shift = Vector((-(minv.x + maxv.x) * 0.5, -(minv.y + maxv.y) * 0.5, -minv.z))
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.translate(bm, verts=bm.verts, vec=shift)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    obj.location = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()


def fit_to_target(obj, target):
    """Lock the outer box to the catalog size. Construction is already on target;
    this only corrects bevel/float drift and refuses a large proportion change.
    """
    _minv, _maxv, size = world_bounds(obj)
    scale = Vector((target[0] / size.x, target[1] / size.y, target[2] / size.z))
    for axis, value in zip("xyz", scale):
        drift = abs(value - 1.0)
        if drift > 0.02:
            raise SystemExit(
                f"refusing to scale {axis} by {value:.4f}; model proportions are off"
            )
        print(f"fit scale {axis} = {value:.6f}")
    obj.scale = scale
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.context.view_layer.update()


def triangle_count(obj):
    mesh = obj.data
    mesh.calc_loop_triangles()
    return len(mesh.loop_triangles)


def build_sofa():
    # Warm oatmeal linen. Values are the shaded cloth color, not a highlight.
    fabric = make_material("F001_Fabric", (0.52, 0.46, 0.39), roughness=0.92, sheen=0.08)
    cushion = make_material(
        "F001_Cushion", (0.64, 0.57, 0.48), roughness=0.9, sheen=0.1
    )
    leg_mat = make_material(
        "F001_Leg",
        (0.09, 0.075, 0.06),
        roughness=0.42,
        metallic=0.15,
        sheen=0.0,
        specular=0.45,
    )
    pillow_slate = make_material(
        "F001_Pillow_Slate", (0.30, 0.38, 0.46), roughness=0.88, sheen=0.08
    )
    pillow_cream = make_material(
        "F001_Pillow_Cream", (0.66, 0.55, 0.42), roughness=0.9, sheen=0.08
    )

    parts = []

    plinth_h = PLINTH_TOP - LEG_H
    parts.append(
        add_box(
            "plinth",
            (0.0, 0.0, LEG_H + plinth_h * 0.5),
            (W, D, plinth_h),
            fabric,
            bevel=0.008,
            segments=2,
            angle_deg=42.0,
        )
    )

    back_h = H - PLINTH_TOP
    parts.append(
        add_box(
            "back_shell",
            (0.0, D * 0.5 - BACK_T * 0.5, PLINTH_TOP + back_h * 0.5),
            (W, BACK_T, back_h),
            fabric,
            bevel=0.01,
            segments=2,
            angle_deg=42.0,
        )
    )

    arm_depth = D - BACK_T
    arm_h = ARM_H - PLINTH_TOP
    arm_center_y = -D * 0.5 + arm_depth * 0.5
    arm_center_z = PLINTH_TOP + arm_h * 0.5
    for side, name in ((-1.0, "arm_left"), (1.0, "arm_right")):
        parts.append(
            add_box(
                name,
                (side * (W * 0.5 - ARM_W * 0.5), arm_center_y, arm_center_z),
                (ARM_W, arm_depth, arm_h),
                fabric,
                bevel=0.012,
                segments=2,
                angle_deg=42.0,
            )
        )

    # Legs: short, slightly tapered, inset under the plinth. Tops tuck into the deck.
    leg_h = LEG_H + 0.012
    x_leg = W * 0.5 - LEG_INSET_X
    y_leg = D * 0.5 - LEG_INSET_Y
    for ix, sx in enumerate((-1.0, 1.0)):
        for iy, sy in enumerate((-1.0, 1.0)):
            leg = add_box(
                f"leg_{ix}{iy}",
                (sx * x_leg, sy * y_leg, leg_h * 0.5 - 0.006),
                (LEG_SIZE, LEG_SIZE, leg_h),
                leg_mat,
                bevel=0.0,
            )
            # Taper after the box exists. Bottom sits on Z=0 (center is leg_h/2 - 0.006,
            # half-height is leg_h/2, so min z = -0.006 + wait):
            # center z = leg_h/2 - 0.006, half = leg_h/2, min z = -0.006.
            # Shift is wrong. Recalculate: we want min z = 0.
            # Set location so bottom is 0: center = leg_h/2, bottom = 0, top = leg_h.
            # I passed center leg_h/2 - 0.006 which puts bottom at -0.006. Fix below.
            taper_leg(leg, 0.70)
            parts.append(leg)

    # Correct leg bottoms to Z=0 and sink the top 12 mm into the plinth.
    for part in parts:
        if not part.name.startswith("leg_"):
            continue
        mesh = part.data
        zmin = min(v.co.z for v in mesh.vertices)
        # world z == local z because the object origin is at the center and location.z is center.
        # Move the object up so the tapered bottom lands on the floor.
        part.location.z += -((part.location.z + zmin))
        # After moving, top is at leg_h. Plinth starts at LEG_H and leg_h = LEG_H+0.012,
        # so the top embeds 12 mm. Good.
        bpy.context.view_layer.update()

    inner_left = -W * 0.5 + ARM_W + SIDE_GAP
    inner_right = W * 0.5 - ARM_W - SIDE_GAP
    cushion_w = (inner_right - inner_left - 2.0 * SEAT_GAP) / 3.0
    seat_t = SEAT_TOP - PLINTH_TOP
    # Back cushions tuck slightly into the shell and lean back.
    bc_rear = D * 0.5 - BACK_T + 0.018
    bc_front = bc_rear - BACK_CUSH_D
    seat_front = -D * 0.5 + SEAT_FRONT_INSET
    seat_rear = bc_front + 0.04
    seat_d = seat_rear - seat_front
    seat_center_y = (seat_front + seat_rear) * 0.5
    bc_bottom = SEAT_TOP - 0.07
    bc_top = H - 0.006
    bc_h = bc_top - bc_bottom
    bc_center_y = (bc_front + bc_rear) * 0.5
    bc_center_z = (bc_bottom + bc_top) * 0.5

    print(
        f"seat depth {seat_d / IN:.2f} in, cushion width {cushion_w / IN:.2f} in, "
        f"back cushion {bc_h / IN:.2f} in tall"
    )

    for i in range(3):
        cx = inner_left + cushion_w * 0.5 + i * (cushion_w + SEAT_GAP)
        seat = add_box(
            f"seat_{i}",
            (cx, seat_center_y, PLINTH_TOP + seat_t * 0.5 + 0.001),
            (cushion_w, seat_d, seat_t),
            cushion,
            bevel=0.032,
            segments=3,
            angle_deg=58.0,
        )
        parts.append(seat)
        back = add_box(
            f"back_{i}",
            (cx, bc_center_y, bc_center_z),
            (cushion_w, BACK_CUSH_D, bc_h),
            cushion,
            bevel=0.034,
            segments=3,
            angle_deg=58.0,
        )
        shear_top_back(back, 0.035)
        parts.append(back)

    # Corner throw pillows, leaning into the arms and the back. Sized so the
    # rotated bounds stay inside the catalog box (the frame defines the bbox).
    pillows = [
        (
            "pillow_left",
            inner_left + 0.24,
            seat_rear - 0.20,
            SEAT_TOP + 0.13,
            pillow_slate,
            (-28.0, 8.0, 18.0),
            (0.46, 0.14, 0.30),
        ),
        (
            "pillow_right",
            inner_right - 0.26,
            seat_rear - 0.18,
            SEAT_TOP + 0.14,
            pillow_cream,
            (-24.0, -6.0, -14.0),
            (0.42, 0.13, 0.28),
        ),
    ]
    for name, px, py, pz, mat, rot, size in pillows:
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(px, py, pz))
        pillow = bpy.context.active_object
        pillow.name = name
        pillow.dimensions = size
        pillow.rotation_euler = tuple(math.radians(a) for a in rot)
        apply_scale(pillow)
        mod = pillow.modifiers.new("Bevel", "BEVEL")
        mod.width = 0.028
        mod.segments = 3
        mod.limit_method = "ANGLE"
        mod.angle_limit = math.radians(30.0)
        mod.harden_normals = True
        mod.use_clamp_overlap = True
        bpy.ops.object.modifier_apply(modifier="Bevel")
        shade_by_angle(pillow, 60.0)
        pillow.data.materials.append(mat)
        parts.append(pillow)

    # Join into one mesh named for the catalog id.
    bpy.ops.object.select_all(action="DESELECT")
    for part in parts:
        part.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    sofa = bpy.context.active_object
    sofa.name = "F001"
    sofa.data.name = "F001"
    recenter_bottom_center(sofa)

    minv, maxv, size = world_bounds(sofa)
    print(
        f"pre-fit bbox m: {size.x:.4f} x {size.y:.4f} x {size.z:.4f} "
        f"min {tuple(round(v, 4) for v in minv)}"
    )
    fit_to_target(sofa, (W, D, H))
    return sofa


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def setup_studio(sofa):
    scene = bpy.context.scene
    world = bpy.data.worlds.new("Studio")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.72, 0.73, 0.74, 1.0)
    bg.inputs["Strength"].default_value = 0.35

    floor_mat = make_material(
        "PreviewFloor", (0.45, 0.45, 0.46), roughness=0.95, sheen=0.0, specular=0.08
    )
    bpy.ops.mesh.primitive_plane_add(size=8.0, location=(0.0, 0.0, -0.002))
    floor = bpy.context.active_object
    floor.name = "PreviewFloor"
    floor.data.materials.append(floor_mat)

    def add_light(name, kind, location, energy, size=1.0, color=(1.0, 1.0, 1.0)):
        data = bpy.data.lights.new(name, kind)
        data.energy = energy
        data.color = color
        if kind == "AREA":
            data.size = size
            data.shape = "SQUARE"
        if kind == "SUN":
            data.angle = math.radians(6.0)
        obj = bpy.data.objects.new(name, data)
        scene.collection.objects.link(obj)
        obj.location = location
        return obj

    key = add_light(
        "Key", "AREA", (1.6, -2.3, 2.0), 110, size=2.4, color=(1.0, 0.96, 0.90)
    )
    look_at(key, (0.0, 0.0, 0.35))
    fill = add_light(
        "Fill", "AREA", (-1.8, -1.3, 1.2), 36, size=2.6, color=(0.86, 0.90, 1.0)
    )
    look_at(fill, (0.0, 0.0, 0.32))
    rim = add_light(
        "Rim", "AREA", (-0.4, 1.7, 1.5), 22, size=1.8, color=(1.0, 0.95, 0.88)
    )
    look_at(rim, (0.0, 0.0, 0.4))

    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens = 48
    cam_data.clip_start = 0.05
    cam_data.clip_end = 40.0
    cam = bpy.data.objects.new("Camera", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    # Front three-quarter view. Front of the sofa is -Y.
    cam.location = (1.48, -1.72, 0.78)
    look_at(cam, (0.0, 0.0, 0.30))

    engine = "BLENDER_WORKBENCH"
    for candidate in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = candidate
            engine = candidate
            break
        except TypeError:
            continue
    scene.render.engine = engine
    scene.render.resolution_x = 512
    scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    if hasattr(scene, "eevee"):
        if hasattr(scene.eevee, "taa_render_samples"):
            scene.eevee.taa_render_samples = 32
        if hasattr(scene.eevee, "use_shadows"):
            scene.eevee.use_shadows = True
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    print(f"render engine: {scene.render.engine}")
    return floor


def export_all(sofa, outdir, bounds):
    minv, maxv, size = bounds
    glb_path = os.path.join(outdir, "model.glb")
    blend_path = os.path.join(outdir, "model.blend")
    preview_path = os.path.join(outdir, "preview.png")
    meta_path = os.path.join(outdir, "metadata.json")

    import addon_utils

    addon_utils.enable("io_scene_gltf2")

    bpy.ops.object.select_all(action="DESELECT")
    sofa.select_set(True)
    bpy.context.view_layer.objects.active = sofa
    bpy.ops.export_scene.gltf(
        filepath=glb_path,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_materials="EXPORT",
        export_normals=True,
        export_texcoords=True,
        export_animations=False,
    )

    scene = bpy.context.scene
    scene.render.filepath = preview_path
    bpy.ops.render.render(write_still=True)

    bpy.ops.wm.save_as_mainfile(filepath=blend_path)

    tris = triangle_count(sofa)
    metadata = {
        "id": "F001",
        "name": "Cloudline 3-Seat Couch",
        "category": "Couch",
        "style": "Modern",
        "room": "Living Room",
        "price_usd": 899,
        "dimensions_in": {
            "width": WIDTH_IN,
            "depth": DEPTH_IN,
            "height": HEIGHT_IN,
        },
        "dimensions_m": {
            "width": round(W, 6),
            "depth": round(D, 6),
            "height": round(H, 6),
        },
        "bounding_box_m": {
            "width": round(size.x, 6),
            "depth": round(size.y, 6),
            "height": round(size.z, 6),
            "min": [round(minv.x, 6), round(minv.y, 6), round(minv.z, 6)],
            "max": [round(maxv.x, 6), round(maxv.y, 6), round(maxv.z, 6)],
        },
        "triangle_count": tris,
    }
    with open(meta_path, "w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)
        handle.write("\n")

    print("EXPORT", glb_path)
    print("BOUNDS_M", round(size.x, 6), round(size.y, 6), round(size.z, 6))
    print("TRIANGLES", tris)
    for label, actual, target in (
        ("width", size.x, W),
        ("depth", size.y, D),
        ("height", size.z, H),
    ):
        err = abs(actual - target) / target
        if err > 0.02:
            raise SystemExit(f"{label} error {err * 100:.2f}% exceeds 2%")
    if abs(minv.z) > 1e-4 or abs(minv.x + maxv.x) > 1e-3 or abs(minv.y + maxv.y) > 1e-3:
        raise SystemExit(f"origin is not bottom-center: min {minv} max {maxv}")


def main():
    outdir = parse_outdir()
    clear_scene()
    sofa = build_sofa()
    bounds = world_bounds(sofa)
    setup_studio(sofa)
    export_all(sofa, outdir, bounds)


if __name__ == "__main__":
    main()
