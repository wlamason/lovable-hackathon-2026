"""Build catalog item F003, Corner Modular Sectional.

Run:
  blender -b --factory-startup --python build.py -- --outdir <dir>

Units are meters (1 Blender unit = 1 m). Width is X, depth is Y, height is Z.
The front of the sectional faces -Y. Origin is the bottom center of the footprint.
The 104 in run lies along X; the 72 in chaise return lies along Y (left / -X side).
"""

import json
import os
import sys

import bmesh
import bpy
from mathutils import Vector

IN = 0.0254

# Nominal catalog size.
W_IN, D_IN, H_IN = 104.0, 72.0, 34.0
TARGET_W = W_IN * IN
TARGET_D = D_IN * IN
TARGET_H = H_IN * IN

# Proportions (inches).
CHAISE_W_IN = 40.0
SOFA_D_IN = 38.0
ARM_W_IN = 6.0
ARM_H_IN = 24.0
BACK_T_IN = 6.0
RAIL_T_IN = 2.5
PLINTH_H_IN = 2.5
DECK_IN = 12.0
SEAT_IN = 18.0
PAD_IN = 0.5
GAP_IN = 0.55
BC_T_IN = 5.75
BC_TOP_IN = 33.35
BC_BOTTOM_DROP_IN = 1.15
PLINTH_INSET_IN = 1.15


def parse_outdir():
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    outdir = os.path.dirname(os.path.abspath(__file__))
    if "--outdir" in argv:
        outdir = os.path.abspath(argv[argv.index("--outdir") + 1])
    os.makedirs(outdir, exist_ok=True)
    return outdir


def srgb_to_linear(rgb):
    def f(u):
        if u <= 0.04045:
            return u / 12.92
        return ((u + 0.055) / 1.055) ** 2.4

    return (f(rgb[0]), f(rgb[1]), f(rgb[2]), 1.0)


def make_material(name, srgb, roughness, sheen=0.0, specular=0.28):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = srgb_to_linear(srgb)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        return mat
    bsdf.inputs["Base Color"].default_value = srgb_to_linear(srgb)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = 0.0
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = specular
    if "Sheen Weight" in bsdf.inputs and sheen:
        bsdf.inputs["Sheen Weight"].default_value = sheen
    if "Sheen Roughness" in bsdf.inputs and sheen:
        bsdf.inputs["Sheen Roughness"].default_value = 0.6
    return mat


def add_prism(name, pts, z0, z1, mat):
    """Extrude a CCW plan polygon from z0 to z1."""
    mesh = bpy.data.meshes.new(name + "_mesh")
    bm = bmesh.new()
    n = len(pts)
    bottom = [bm.verts.new((x, y, z0)) for x, y in pts]
    top = [bm.verts.new((x, y, z1)) for x, y in pts]
    bm.faces.new(list(reversed(bottom)))
    bm.faces.new(top)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((bottom[i], bottom[j], top[j], top[i]))
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    for face in bm.faces:
        face.smooth = False
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    mesh.materials.append(mat)
    return obj


def add_box(name, x0, x1, y0, y1, z0, z1, mat, bevel=0.0, smooth=False, lean=0.0):
    """Axis-aligned box. `lean` shifts the top face toward +Y (back)."""
    if not (x1 > x0 and y1 > y0 and z1 > z0):
        raise RuntimeError("degenerate box %s" % name)
    mesh = bpy.data.meshes.new(name + "_mesh")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x = x0 + (v.co.x + 0.5) * (x1 - x0)
        v.co.y = y0 + (v.co.y + 0.5) * (y1 - y0)
        v.co.z = z0 + (v.co.z + 0.5) * (z1 - z0)
        if lean and v.co.z > (z0 + z1) * 0.5:
            v.co.y += lean
    if bevel > 0.0:
        min_dim = min(x1 - x0, y1 - y0, z1 - z0)
        offset = min(bevel, min_dim * 0.28)
        if offset > 1e-5:
            bmesh.ops.bevel(
                bm,
                geom=list(bm.edges),
                offset=offset,
                segments=2,
                profile=0.55,
                affect="EDGES",
            )
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    for face in bm.faces:
        face.smooth = smooth
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    mesh.materials.append(mat)
    return obj


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def world_aabb(obj):
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    xs = [c.x for c in corners]
    ys = [c.y for c in corners]
    zs = [c.z for c in corners]
    return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)


def triangle_count(obj):
    mesh = obj.data
    mesh.calc_loop_triangles()
    return len(mesh.loop_triangles)


def join_parts(parts, name):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in parts:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    with bpy.context.temp_override(active_object=parts[0], selected_objects=parts):
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = name
    obj.data.name = name + "_mesh"
    return obj


def setup_preview(scene, sofa):
    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.90, 0.90, 0.91, 1.0)
        bg.inputs["Strength"].default_value = 0.7

    sun_data = bpy.data.lights.new("Key", "SUN")
    sun_data.energy = 3.2
    sun_data.angle = 0.12
    sun = bpy.data.objects.new("Key", sun_data)
    bpy.context.collection.objects.link(sun)
    sun.rotation_euler = (0.95, 0.05, -0.55)

    def area(name, energy, size, location, target):
        data = bpy.data.lights.new(name, "AREA")
        data.energy = energy
        data.size = size
        data.shape = "SQUARE"
        obj = bpy.data.objects.new(name, data)
        bpy.context.collection.objects.link(obj)
        obj.location = Vector(location)
        look_at(obj, target)
        return obj

    center = (0.0, -0.05, 0.35)
    area("Fill", 180.0, 2.4, (1.7, -1.6, 1.5), center)
    area("Rim", 90.0, 1.6, (-1.8, 1.3, 1.4), center)

    floor_mat = make_material("PreviewFloor", (0.74, 0.72, 0.69), 0.95, specular=0.15)
    add_box(
        "PreviewFloor",
        -3.4,
        3.4,
        -3.4,
        3.4,
        -0.04,
        -0.004,
        floor_mat,
    )

    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens = 40
    cam_data.clip_start = 0.05
    cam_data.clip_end = 40.0
    cam = bpy.data.objects.new("Camera", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = Vector((-1.25, -2.85, 1.78))
    look_at(cam, (0.02, -0.02, 0.30))
    scene.camera = cam

    scene.render.resolution_x = 512
    scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    try:
        scene.view_settings.view_transform = "Standard"
    except Exception:
        pass
    scene.view_settings.exposure = 0.35

    engine = "BLENDER_WORKBENCH"
    for candidate in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = candidate
            engine = candidate
            break
        except Exception as exc:
            print("engine unavailable", candidate, exc)
    if engine.startswith("BLENDER_EEVEE"):
        eevee = scene.eevee
        if hasattr(eevee, "taa_render_samples"):
            eevee.taa_render_samples = 24
        if hasattr(eevee, "use_gtao"):
            eevee.use_gtao = True
        if hasattr(eevee, "gtao_distance"):
            eevee.gtao_distance = 0.4
    else:
        scene.render.engine = "BLENDER_WORKBENCH"
        shading = scene.display.shading
        shading.light = "STUDIO"
        shading.color_type = "MATERIAL"
    print("render engine", scene.render.engine)
    # sofa is already the subject; reference it so lint/tools see the arg used
    sofa.hide_render = False


def render_preview(scene, filepath):
    scene.render.filepath = filepath
    try:
        bpy.ops.render.render(write_still=True)
        print("rendered", filepath, "with", scene.render.engine)
        return
    except Exception as exc:
        print("primary render failed:", exc)
    scene.render.engine = "BLENDER_WORKBENCH"
    shading = scene.display.shading
    shading.light = "STUDIO"
    shading.color_type = "MATERIAL"
    try:
        bpy.ops.render.render(write_still=True)
        print("rendered", filepath, "with WORKBENCH")
        return
    except Exception as exc:
        print("workbench render failed:", exc)
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 16
    scene.cycles.use_denoising = False
    bpy.ops.render.render(write_still=True)
    print("rendered", filepath, "with CYCLES")


def main():
    outdir = parse_outdir()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0

    x0, x1 = -TARGET_W / 2.0, TARGET_W / 2.0
    y0, y1 = -TARGET_D / 2.0, TARGET_D / 2.0

    chaise_w = CHAISE_W_IN * IN
    sofa_d = SOFA_D_IN * IN
    arm_w = ARM_W_IN * IN
    arm_h = ARM_H_IN * IN
    back_t = BACK_T_IN * IN
    rail_t = RAIL_T_IN * IN
    plinth_h = PLINTH_H_IN * IN
    deck = DECK_IN * IN
    seat = SEAT_IN * IN
    pad = PAD_IN * IN
    gap = GAP_IN * IN
    bc_t = BC_T_IN * IN
    bc_top = BC_TOP_IN * IN
    bc_drop = BC_BOTTOM_DROP_IN * IN
    inset = PLINTH_INSET_IN * IN
    x_seam = x0 + chaise_w  # joint between chaise module and the two-seat run

    mat_frame = make_material("F003_Frame", (0.145, 0.145, 0.155), 0.91, sheen=0.14, specular=0.2)
    mat_seat = make_material("F003_Seat", (0.22, 0.22, 0.23), 0.76, sheen=0.32, specular=0.28)
    mat_back = make_material("F003_BackCushion", (0.185, 0.185, 0.195), 0.80, sheen=0.26, specular=0.26)
    mat_plinth = make_material("F003_Plinth", (0.04, 0.04, 0.045), 0.5, specular=0.35)
    mat_pillow_a = make_material("F003_PillowOatmeal", (0.62, 0.56, 0.48), 0.86, sheen=0.16)
    mat_pillow_b = make_material("F003_PillowStone", (0.46, 0.45, 0.43), 0.86, sheen=0.16)

    parts = []

    def box(name, bounds, mat, bevel=0.0, smooth=False, lean=0.0):
        parts.append(add_box(name, *bounds, mat, bevel=bevel, smooth=smooth, lean=lean))

    # Recessed plinth, inset so the upholstered body reads as floating.
    box(
        "plinth_rear",
        (x0 + inset, x1 - inset, y1 - sofa_d + inset, y1 - inset, 0.0, plinth_h),
        mat_plinth,
    )
    box(
        "plinth_chaise",
        (x0 + inset, x_seam - inset, y0 + inset, y1 - sofa_d + inset + 0.002, 0.0, plinth_h),
        mat_plinth,
    )

    # Outer frame. Pieces meet on shared planes (no coplanar overlap).
    box(
        "back",
        (x0, x1, y1 - back_t, y1, plinth_h, TARGET_H),
        mat_frame,
    )
    box(
        "arm_right",
        (x1 - arm_w, x1, y1 - sofa_d, y1 - back_t, plinth_h, arm_h),
        mat_frame,
    )
    # One L-shaped track arm so the chaise's outer front corner has no panel seam.
    parts.append(
        add_prism(
            "arm_chaise",
            [
                (x0, y0),
                (x_seam, y0),
                (x_seam, y0 + arm_w),
                (x0 + arm_w, y0 + arm_w),
                (x0 + arm_w, y1 - back_t),
                (x0, y1 - back_t),
            ],
            plinth_h,
            arm_h,
            mat_frame,
        )
    )
    box(
        "rail_sofa_front",
        (x_seam, x1 - arm_w, y1 - sofa_d, y1 - sofa_d + rail_t, plinth_h, deck),
        mat_frame,
    )
    box(
        "rail_chaise_inner",
        (x_seam - rail_t, x_seam, y0 + arm_w - 0.002, y1 - sofa_d, plinth_h, deck),
        mat_frame,
    )

    # Deck fills the well. A 2 mm bite into the frame hides coplanar interior faces.
    box(
        "deck_rear",
        (
            x0 + arm_w - 0.002,
            x1 - arm_w + 0.002,
            y1 - sofa_d + rail_t - 0.002,
            y1 - back_t + 0.002,
            plinth_h,
            deck,
        ),
        mat_frame,
    )
    box(
        "deck_chaise",
        (
            x0 + arm_w - 0.002,
            x_seam - rail_t,
            y0 + arm_w - 0.002,
            y1 - sofa_d + rail_t + 0.001,
            plinth_h,
            deck,
        ),
        mat_frame,
    )

    cushion_bevel = 0.014
    # Chaise lounge cushion (footrest end of the return).
    box(
        "cushion_chaise",
        (
            x0 + arm_w + pad,
            x_seam - rail_t - pad,
            y0 + arm_w + pad,
            y1 - sofa_d - gap * 0.5,
            deck,
            seat,
        ),
        mat_seat,
        bevel=cushion_bevel,
        smooth=True,
    )
    # Corner seat, where the return meets the long run.
    corner_x1 = x_seam - gap * 0.5
    box(
        "cushion_corner",
        (
            x0 + arm_w + pad,
            corner_x1,
            y1 - sofa_d + gap * 0.5,
            y1 - back_t - 0.004,
            deck,
            seat,
        ),
        mat_seat,
        bevel=cushion_bevel,
        smooth=True,
    )
    seat_x0 = x_seam + gap * 0.5
    seat_x1 = x1 - arm_w - pad
    seat_y0 = y1 - sofa_d + rail_t + pad
    seat_y1 = y1 - back_t - 0.004
    span = seat_x1 - seat_x0
    seat_w = (span - gap) * 0.5
    for index, sx0 in enumerate((seat_x0, seat_x0 + seat_w + gap)):
        box(
            "cushion_seat_%d" % index,
            (sx0, sx0 + seat_w, seat_y0, seat_y1, deck, seat),
            mat_seat,
            bevel=cushion_bevel,
            smooth=True,
        )

    # Loose back cushions, tucked slightly into the back frame and leaning back.
    bc_y0 = y1 - back_t - bc_t
    bc_y1 = y1 - back_t + 0.01
    bc_z0 = seat - bc_drop
    lean = 0.038
    back_spans = (
        (x0 + arm_w + pad, corner_x1),
        (seat_x0, seat_x0 + seat_w),
        (seat_x0 + seat_w + gap, seat_x0 + 2 * seat_w + gap),
    )
    for index, (bx0, bx1) in enumerate(back_spans):
        box(
            "back_cushion_%d" % index,
            (bx0, bx1, bc_y0, bc_y1, bc_z0, bc_top),
            mat_back,
            bevel=0.012,
            smooth=True,
            lean=lean,
        )

    # Two throw pillows on the long run and one at the corner, inside the shell.
    pillow_d = 0.12
    pillow_h = 0.22
    pillow_mats = (mat_pillow_a, mat_pillow_b, mat_pillow_a)
    for index, (bx0, bx1) in enumerate(back_spans):
        pw = min(0.36, (bx1 - bx0) * 0.72)
        cx = (bx0 + bx1) * 0.5
        py1 = bc_y0 + 0.02
        py0 = py1 - pillow_d
        box(
            "pillow_%d" % index,
            (cx - pw * 0.5, cx + pw * 0.5, py0, py1, seat + 0.004, seat + 0.004 + pillow_h),
            pillow_mats[index],
            bevel=0.012,
            smooth=True,
            lean=0.03,
        )

    sofa = join_parts(parts, "F003")
    bpy.ops.object.select_all(action="DESELECT")
    sofa.select_set(True)
    bpy.context.view_layer.objects.active = sofa
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    minx, maxx, miny, maxy, minz, maxz = world_aabb(sofa)
    measured = {
        "width": maxx - minx,
        "depth": maxy - miny,
        "height": maxz - minz,
        "min": [minx, miny, minz],
        "max": [maxx, maxy, maxz],
    }
    tris = triangle_count(sofa)
    print("F003 bbox m", measured)
    print("F003 triangles", tris)

    def rel_err(actual, target):
        return abs(actual - target) / target

    errors = {
        "width": rel_err(measured["width"], TARGET_W),
        "depth": rel_err(measured["depth"], TARGET_D),
        "height": rel_err(measured["height"], TARGET_H),
    }
    print("F003 relative error", errors)
    for axis, err in errors.items():
        if err > 0.02:
            raise RuntimeError("bbox %s off by %.3f%%" % (axis, err * 100.0))
    if minz < -1e-4 or abs((minx + maxx) * 0.5) > 1e-3 or abs((miny + maxy) * 0.5) > 1e-3:
        raise RuntimeError("origin is not at bottom center: %s" % measured)
    if tris > 30000:
        raise RuntimeError("triangle count %d exceeds 30000" % tris)

    glb_path = os.path.join(outdir, "model.glb")
    sofa.select_set(True)
    bpy.ops.export_scene.gltf(
        filepath=glb_path,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_materials="EXPORT",
        export_yup=True,
    )
    print("exported", glb_path)

    metadata = {
        "id": "F003",
        "name": "Corner Modular Sectional",
        "category": "Couch",
        "style": "Modern",
        "room": "Living Room",
        "price_usd": 1299,
        "dimensions_in": {"width": W_IN, "depth": D_IN, "height": H_IN},
        "dimensions_m": {
            "width": round(TARGET_W, 6),
            "depth": round(TARGET_D, 6),
            "height": round(TARGET_H, 6),
        },
        "bounding_box_m": {
            "width": round(measured["width"], 6),
            "depth": round(measured["depth"], 6),
            "height": round(measured["height"], 6),
            "min": [round(v, 6) for v in measured["min"]],
            "max": [round(v, 6) for v in measured["max"]],
        },
        "triangle_count": tris,
    }
    meta_path = os.path.join(outdir, "metadata.json")
    with open(meta_path, "w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)
        handle.write("\n")
    print("wrote", meta_path)

    setup_preview(scene, sofa)
    preview_path = os.path.join(outdir, "preview.png")
    render_preview(scene, preview_path)

    blend_path = os.path.join(outdir, "model.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print("saved", blend_path)


if __name__ == "__main__":
    main()
