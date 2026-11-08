"""Build catalog item F006 Tripod Corner Lamp and export it.

Run:
  blender -b --factory-startup --python build.py -- --outdir <dir>

Units are meters (1 Blender unit = 1 m). Width is X, depth is Y, height is Z.
The front of the lamp (the single tripod leg) faces -Y. Origin is the bottom
center of the footprint, sitting on Z = 0.
"""

import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector

INCH = 0.0254
TARGET_W = 20.0 * INCH  # 0.508 m
TARGET_D = 20.0 * INCH
TARGET_H = 60.0 * INCH  # 1.524 m

# Drum shade: 16 in across, 9 in tall — a real floor-lamp proportion.
SHADE_R = 8.0 * INCH
SHADE_H = 9.0 * INCH
SHADE_TOP = TARGET_H
SHADE_BOT = TARGET_H - SHADE_H

HUB_R = 0.036
# About 1.9 in of pale-oak neck shows between the hub and the shade.
HUB_Z = SHADE_BOT - 0.048 - HUB_R


def parse_outdir():
    outdir = Path(__file__).resolve().parent
    argv = sys.argv
    if "--" in argv:
        args = argv[argv.index("--") + 1 :]
        if "--outdir" in args:
            outdir = Path(args[args.index("--outdir") + 1]).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    return outdir


def enable_gltf():
    import addon_utils

    addon_utils.enable("io_scene_gltf2", default_set=False, persistent=False)


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = "METERS"
    enable_gltf()
    return scene


def set_input(node, name, value):
    if name in node.inputs:
        node.inputs[name].default_value = value


def principled(name, color, rough=0.5, metal=0.0, spec=0.5, emit=None, emit_strength=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.use_backface_culling = False
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    set_input(bsdf, "Base Color", (color[0], color[1], color[2], 1.0))
    set_input(bsdf, "Roughness", rough)
    set_input(bsdf, "Metallic", metal)
    set_input(bsdf, "Specular IOR Level", spec)
    set_input(bsdf, "Specular", spec)
    if emit is not None and emit_strength > 0.0:
        emission = (emit[0], emit[1], emit[2], 1.0)
        set_input(bsdf, "Emission Color", emission)
        set_input(bsdf, "Emission", emission)
        set_input(bsdf, "Emission Strength", emit_strength)
    return mat


def link_mesh(name, mesh, mat):
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    if mat is not None:
        mesh.materials.append(mat)
    for poly in mesh.polygons:
        poly.use_smooth = True
    return obj


def mesh_from_bm(name, bm, mat):
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    return link_mesh(name, mesh, mat)


def probe_radius1_at_negative_z():
    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=8,
        radius1=0.4,
        radius2=0.1,
        depth=2.0,
    )
    neg = []
    pos = []
    for vert in bm.verts:
        radius = math.hypot(vert.co.x, vert.co.y)
        if radius < 0.05:
            continue
        if vert.co.z < -0.5:
            neg.append(radius)
        elif vert.co.z > 0.5:
            pos.append(radius)
    bm.free()
    neg_r = sum(neg) / len(neg)
    pos_r = sum(pos) / len(pos)
    return neg_r > pos_r


RADIUS1_AT_NEG_Z = None


def add_taper(name, p0, p1, r0, r1, mat, segments=28, clip_floor=False):
    """Cone from p0 (radius r0) to p1 (radius r1). Optional floor clip at Z=0."""
    global RADIUS1_AT_NEG_Z
    if RADIUS1_AT_NEG_Z is None:
        RADIUS1_AT_NEG_Z = probe_radius1_at_negative_z()

    p0 = Vector(p0)
    p1 = Vector(p1)
    direction = p1 - p0
    length = direction.length
    if length < 1e-8:
        raise ValueError("zero-length part %s" % name)
    direction = direction / length

    if clip_floor:
        extra = max(r0, r1) * 3.0 + 0.03
        start = p0 - direction * extra
    else:
        start = p0
    depth = (p1 - start).length
    mid = (start + p1) * 0.5

    radius_bottom = r0 if RADIUS1_AT_NEG_Z else r1
    radius_top = r1 if RADIUS1_AT_NEG_Z else r0

    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=segments,
        radius1=radius_bottom,
        radius2=radius_top,
        depth=depth,
    )
    rot = Vector((0.0, 0.0, 1.0)).rotation_difference(direction).to_matrix().to_4x4()
    bmesh.ops.transform(bm, verts=list(bm.verts), matrix=Matrix.Translation(mid) @ rot)

    if clip_floor:
        geom = list(bm.verts) + list(bm.edges) + list(bm.faces)
        bmesh.ops.bisect_plane(
            bm,
            geom=geom,
            plane_co=Vector((0.0, 0.0, 0.0)),
            plane_no=Vector((0.0, 0.0, 1.0)),
            clear_inner=True,
            clear_outer=False,
        )
        zs = [vert.co.z for vert in bm.verts]
        if not zs or max(zs) < 0.02:
            bm.free()
            raise RuntimeError("floor clip removed %s" % name)
        boundary = [edge for edge in bm.edges if edge.is_boundary]
        if boundary:
            try:
                bmesh.ops.holes_fill(bm, edges=boundary, sides=0)
            except TypeError:
                bmesh.ops.holes_fill(bm, edges=boundary)

    return mesh_from_bm(name, bm, mat)


def add_sphere(name, loc, radius, mat, u=32, v=16):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(
        bm,
        u_segments=u,
        v_segments=v,
        radius=radius,
        matrix=Matrix.Translation(Vector(loc)),
    )
    return mesh_from_bm(name, bm, mat)


def add_hoop(name, z, radius, height, thickness, mat, segments=64):
    """Square-section ring, centered at z, closed and watertight."""
    bm = bmesh.new()
    outer_r = radius + thickness * 0.5
    inner_r = radius - thickness * 0.5
    z0 = z - height * 0.5
    z1 = z + height * 0.5

    def ring(zz, r):
        verts = []
        for i in range(segments):
            ang = 2.0 * math.pi * i / segments
            verts.append(bm.verts.new((r * math.cos(ang), r * math.sin(ang), zz)))
        return verts

    outer_bot = ring(z0, outer_r)
    outer_top = ring(z1, outer_r)
    inner_top = ring(z1, inner_r)
    inner_bot = ring(z0, inner_r)

    def bridge(ring_a, ring_b):
        for i in range(segments):
            j = (i + 1) % segments
            bm.faces.new((ring_a[i], ring_a[j], ring_b[j], ring_b[i]))

    bridge(outer_bot, outer_top)
    bridge(outer_top, inner_top)
    bridge(inner_top, inner_bot)
    bridge(inner_bot, outer_bot)
    return mesh_from_bm(name, bm, mat)


def add_plane(name, z, size, mat):
    bm = bmesh.new()
    half = size * 0.5
    verts = [
        bm.verts.new((-half, -half, z)),
        bm.verts.new((half, -half, z)),
        bm.verts.new((half, half, z)),
        bm.verts.new((-half, half, z)),
    ]
    bm.faces.new(verts)
    return mesh_from_bm(name, bm, mat)


def tight_bbox(obj):
    matrix = obj.matrix_world
    xs, ys, zs = [], [], []
    for vert in obj.data.vertices:
        point = matrix @ vert.co
        xs.append(point.x)
        ys.append(point.y)
        zs.append(point.z)
    return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)


def bbox_of(objects):
    boxes = [tight_bbox(obj) for obj in objects if obj.type == "MESH" and len(obj.data.vertices)]
    return (
        min(box[0] for box in boxes),
        max(box[1] for box in boxes),
        min(box[2] for box in boxes),
        max(box[3] for box in boxes),
        min(box[4] for box in boxes),
        max(box[5] for box in boxes),
    )


def select_only(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def apply_location_scale(obj):
    select_only(obj)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)


def join_objects(objects, name):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.join()
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name
    return obj


def edge_split(obj, angle_deg=48.0):
    select_only(obj)
    bpy.ops.object.shade_smooth()
    mod = obj.modifiers.new("EdgeSplit", "EDGE_SPLIT")
    mod.split_angle = math.radians(angle_deg)
    mod.use_edge_angle = True
    bpy.ops.object.modifier_apply(modifier=mod.name)


def tri_count(obj):
    obj.data.calc_loop_triangles()
    return len(obj.data.loop_triangles)


def build_materials():
    # Honey oak, dark enough to stay wooden under studio lighting.
    wood = principled("F006_Oak", (0.48, 0.30, 0.15), rough=0.46, metal=0.0, spec=0.32)
    brass = principled("F006_Brass", (0.78, 0.54, 0.24), rough=0.28, metal=1.0, spec=0.55)
    shade = principled(
        "F006_Linen",
        (0.80, 0.70, 0.54),
        rough=0.82,
        metal=0.0,
        spec=0.16,
        emit=(1.0, 0.72, 0.40),
        emit_strength=0.45,
    )
    trim = principled("F006_LinenTrim", (0.55, 0.42, 0.28), rough=0.72, metal=0.0, spec=0.2)
    glow = principled(
        "F006_Bulb",
        (1.0, 0.86, 0.62),
        rough=0.35,
        metal=0.0,
        spec=0.3,
        emit=(1.0, 0.68, 0.32),
        emit_strength=4.5,
    )
    return wood, brass, shade, trim, glow


def build_base(wood, brass):
    """Tripod legs and brass ferrules. One leg forward (-Y), two into the corner."""
    hub = Vector((0.0, 0.0, HUB_Z))
    # Axis points on the floor, inset so the ferrule ellipse lands near the target box.
    feet = [
        Vector((0.0, -0.236, 0.0)),
        Vector((-0.236, 0.236, 0.0)),
        Vector((0.236, 0.236, 0.0)),
    ]
    parts = []
    for index, foot in enumerate(feet):
        top = hub + (foot - hub).normalized() * 0.012
        axis = (top - foot).normalized()
        wood_bottom = foot + axis * 0.020
        parts.append(
            add_taper(
                "leg_%d" % index,
                wood_bottom,
                top,
                0.0165,
                0.011,
                wood,
                segments=28,
                clip_floor=False,
            )
        )
        parts.append(
            add_taper(
                "ferrule_%d" % index,
                foot - axis * 0.03,
                foot + axis * 0.034,
                0.019,
                0.019,
                brass,
                segments=24,
                clip_floor=True,
            )
        )
        # Bolt head where the leg enters the hub.
        outward = (foot - hub).normalized()
        parts.append(
            add_taper(
                "bolt_%d" % index,
                hub + outward * (HUB_R * 0.55),
                hub + outward * (HUB_R + 0.007),
                0.0065,
                0.0065,
                brass,
                segments=12,
            )
        )
    return parts


def fit_base(parts):
    base = join_objects(parts, "F006_base")
    bpy.context.view_layer.update()
    minx, maxx, miny, maxy, minz, maxz = tight_bbox(base)
    base.location = (-(minx + maxx) * 0.5, -(miny + maxy) * 0.5, -minz)
    apply_location_scale(base)
    bpy.context.view_layer.update()
    minx, maxx, miny, maxy, minz, maxz = tight_bbox(base)
    width = maxx - minx
    depth = maxy - miny
    base.scale = (TARGET_W / width, TARGET_D / depth, 1.0)
    apply_location_scale(base)
    bpy.context.view_layer.update()
    box = tight_bbox(base)
    print(
        "base bbox after fit: "
        "x [%.4f %.4f] y [%.4f %.4f] z [%.4f %.4f]"
        % box
    )
    return base


def build_upper(wood, brass, shade, trim, glow):
    parts = []
    parts.append(add_sphere("hub", (0.0, 0.0, HUB_Z), HUB_R, wood, u=32, v=16))
    parts.append(
        add_hoop(
            "hub_band",
            HUB_Z,
            radius=HUB_R + 0.001,
            height=0.009,
            thickness=0.007,
            mat=brass,
            segments=40,
        )
    )
    # Turned oak neck from inside the hub up into the shade.
    parts.append(
        add_taper(
            "neck",
            (0.0, 0.0, HUB_Z - 0.01),
            (0.0, 0.0, SHADE_BOT + 0.012),
            0.013,
            0.011,
            wood,
            segments=24,
        )
    )
    # Brass gallery / socket under the drum.
    parts.append(
        add_taper(
            "socket",
            (0.0, 0.0, SHADE_BOT - 0.014),
            (0.0, 0.0, SHADE_BOT + 0.020),
            0.020,
            0.023,
            brass,
            segments=28,
        )
    )
    parts.append(add_sphere("bulb", (0.0, 0.0, SHADE_BOT + 0.055), 0.020, glow, u=24, v=12))

    shade_mid = (SHADE_TOP + SHADE_BOT) * 0.5
    parts.append(
        add_hoop(
            "shade",
            shade_mid,
            radius=SHADE_R,
            height=SHADE_H - 0.012,
            thickness=0.004,
            mat=shade,
            segments=72,
        )
    )
    trim_h = 0.012
    trim_t = 0.010
    parts.append(
        add_hoop(
            "shade_trim_top",
            SHADE_TOP - trim_h * 0.5,
            radius=SHADE_R + 0.001,
            height=trim_h,
            thickness=trim_t,
            mat=trim,
            segments=72,
        )
    )
    parts.append(
        add_hoop(
            "shade_trim_bot",
            SHADE_BOT + trim_h * 0.5,
            radius=SHADE_R + 0.001,
            height=trim_h,
            thickness=trim_t,
            mat=trim,
            segments=72,
        )
    )
    # Warm diffuser inside the drum. The lower cap sits in the bottom opening
    # so the shade reads as lit from a three-quarter view.
    parts.append(
        add_taper(
            "diffuser",
            (0.0, 0.0, SHADE_BOT + 0.016),
            (0.0, 0.0, SHADE_TOP - 0.022),
            SHADE_R - 0.016,
            SHADE_R - 0.016,
            glow,
            segments=48,
        )
    )
    for index, deg in enumerate((-90.0, 30.0, 150.0)):
        ang = math.radians(deg)
        inner = (
            math.cos(ang) * 0.024,
            math.sin(ang) * 0.024,
            SHADE_BOT + 0.012,
        )
        outer = (
            math.cos(ang) * (SHADE_R - 0.012),
            math.sin(ang) * (SHADE_R - 0.012),
            SHADE_BOT + 0.008,
        )
        parts.append(
            add_taper("spider_%d" % index, inner, outer, 0.0022, 0.0022, brass, segments=8)
        )
    return parts


def build_lamp():
    wood, brass, shade, trim, glow = build_materials()
    base_parts = build_base(wood, brass)
    base = fit_base(base_parts)
    upper = build_upper(wood, brass, shade, trim, glow)
    lamp = join_objects([base] + upper, "F006")
    edge_split(lamp, angle_deg=50.0)
    bpy.context.scene.cursor.location = (0.0, 0.0, 0.0)
    select_only(lamp)
    bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
    bpy.context.view_layer.update()
    return lamp


def dimensions(box):
    minx, maxx, miny, maxy, minz, maxz = box
    return maxx - minx, maxy - miny, maxz - minz


def assert_spec(box):
    width, depth, height = dimensions(box)
    minx, maxx, miny, maxy, minz, maxz = box
    print(
        "F006 bbox m: width=%.6f depth=%.6f height=%.6f min=(%.6f %.6f %.6f) max=(%.6f %.6f %.6f)"
        % (width, depth, height, minx, miny, minz, maxx, maxy, maxz)
    )
    checks = {
        "width": abs(width - TARGET_W) / TARGET_W,
        "depth": abs(depth - TARGET_D) / TARGET_D,
        "height": abs(height - TARGET_H) / TARGET_H,
    }
    for axis, error in checks.items():
        print("  %s error %.4f%%" % (axis, error * 100.0))
        if error > 0.02:
            raise SystemExit("bounding box %s is outside 2%% of the spec" % axis)
    if abs(minz) > 0.002:
        raise SystemExit("model does not sit on Z=0 (minz=%s)" % minz)
    if abs((minx + maxx) * 0.5) > 0.002 or abs((miny + maxy) * 0.5) > 0.002:
        raise SystemExit("footprint is not centered on the origin")


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def frame_camera(scene, cam, corners):
    from bpy_extras.object_utils import world_to_camera_view

    center = sum(corners, Vector((0.0, 0.0, 0.0))) / len(corners)
    direction = (cam.location - center)
    if direction.length < 1e-6:
        direction = Vector((1.0, -1.0, 0.3))
    direction = direction.normalized()

    def fits(distance):
        cam.location = center + direction * distance
        look_at(cam, center)
        bpy.context.view_layer.update()
        for corner in corners:
            point = world_to_camera_view(scene, cam, corner)
            if point.z < 0.0:
                return False
            if not (0.07 <= point.x <= 0.93 and 0.06 <= point.y <= 0.94):
                return False
        return True

    lo, hi = 0.4, 8.0
    if not fits(hi):
        hi = 14.0
    for _ in range(22):
        mid = (lo + hi) * 0.5
        if fits(mid):
            hi = mid
        else:
            lo = mid
    cam.location = center + direction * hi
    look_at(cam, center)
    bpy.context.view_layer.update()


def setup_preview(scene, lamp):
    world = scene.world
    if world is None:
        world = bpy.data.worlds.new("World")
        scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background is None:
        background = world.node_tree.nodes.new("ShaderNodeBackground")
        output = world.node_tree.nodes.get("World Output")
        world.node_tree.links.new(background.outputs["Background"], output.inputs["Surface"])
    background.inputs["Color"].default_value = (0.58, 0.59, 0.61, 1.0)
    background.inputs["Strength"].default_value = 0.28

    floor_mat = principled("F006_PreviewFloor", (0.46, 0.45, 0.44), rough=0.92, spec=0.12)
    floor = add_plane("PreviewFloor", -0.0008, 6.0, floor_mat)

    target = bpy.data.objects.new("PreviewTarget", None)
    target.location = (0.0, 0.0, 0.70)
    scene.collection.objects.link(target)

    def area(name, loc, energy, size, color):
        data = bpy.data.lights.new(name, "AREA")
        data.energy = energy
        data.size = size
        data.color = color
        obj = bpy.data.objects.new(name, data)
        scene.collection.objects.link(obj)
        obj.location = loc
        constraint = obj.constraints.new("TRACK_TO")
        constraint.target = target
        constraint.track_axis = "TRACK_NEGATIVE_Z"
        constraint.up_axis = "UP_Y"
        return obj

    area("Key", (1.15, -1.85, 1.85), 110.0, 1.25, (1.0, 0.95, 0.88))
    area("Fill", (-1.45, -1.15, 0.95), 36.0, 1.6, (0.88, 0.92, 1.0))
    area("Rim", (0.15, 1.55, 1.55), 64.0, 0.85, (1.0, 0.92, 0.80))

    bulb = bpy.data.lights.new("BulbLight", "POINT")
    bulb.energy = 6.0
    bulb.color = (1.0, 0.78, 0.5)
    bulb.shadow_soft_size = 0.05
    bulb_obj = bpy.data.objects.new("BulbLight", bulb)
    bulb_obj.location = (0.0, 0.0, SHADE_BOT + 0.08)
    scene.collection.objects.link(bulb_obj)

    cam_data = bpy.data.cameras.new("PreviewCam")
    cam_data.lens = 85
    cam_data.clip_start = 0.01
    cam_data.clip_end = 50.0
    cam = bpy.data.objects.new("PreviewCam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    # Front-three-quarter, a little below the shade, so the forward leg and
    # the lit drum opening both read. A longer lens keeps the 16 in shade
    # from looming over the 20 in footprint.
    center = Vector((0.0, 0.0, TARGET_H * 0.46))
    cam.location = center + Vector((0.58, -1.62, -0.06))
    box = tight_bbox(lamp)
    corners = [
        Vector((x, y, z))
        for x in (box[0], box[1])
        for y in (box[2], box[3])
        for z in (box[4], box[5])
    ]
    frame_camera(scene, cam, corners)
    return floor


def render_preview(scene, path):
    scene.render.resolution_x = 512
    scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    scene.render.filepath = str(path)
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False

    def try_engine(engine, prep=None):
        scene.render.engine = engine
        if prep:
            prep()
        result = bpy.ops.render.render(write_still=True)
        ok = result == {"FINISHED"} and path.exists() and path.stat().st_size > 0
        print("render engine %s -> %s" % (engine, result))
        return ok

    def prep_eevee():
        eevee = scene.eevee
        if hasattr(eevee, "taa_render_samples"):
            eevee.taa_render_samples = 32
        if hasattr(eevee, "use_raytracing"):
            eevee.use_raytracing = False

    if try_engine("BLENDER_EEVEE_NEXT", prep_eevee):
        return "BLENDER_EEVEE_NEXT"
    print("Eevee failed, falling back to Workbench")
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    if try_engine("BLENDER_WORKBENCH"):
        return "BLENDER_WORKBENCH"
    print("Workbench failed, falling back to Cycles")
    scene.cycles.samples = 32
    scene.cycles.use_denoising = False
    if try_engine("CYCLES"):
        return "CYCLES"
    raise SystemExit("preview render failed")


def export_glb(path, lamp):
    select_only(lamp)
    bpy.ops.export_scene.gltf(
        filepath=str(path),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
    )


def measure_imported(path, original):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported = [obj for obj in bpy.data.objects if obj not in before and obj.type == "MESH"]
    if not imported:
        raise SystemExit("reimport of model.glb produced no mesh")
    bpy.context.view_layer.update()
    box = bbox_of(imported)
    for obj in list(bpy.data.objects):
        if obj is not original:
            bpy.data.objects.remove(obj, do_unlink=True)
    return box


def write_metadata(path, box):
    minx, maxx, miny, maxy, minz, maxz = box
    width, depth, height = dimensions(box)

    def r(value):
        return round(float(value), 6)

    payload = {
        "id": "F006",
        "name": "Tripod Corner Lamp",
        "category": "Lamp",
        "style": "Scandinavian",
        "room": "Living Room",
        "price_usd": 149,
        "dimensions_in": {"width": 20, "depth": 20, "height": 60},
        "dimensions_m": {
            "width": r(TARGET_W),
            "depth": r(TARGET_D),
            "height": r(TARGET_H),
        },
        "bounding_box_m": {
            "width": r(width),
            "depth": r(depth),
            "height": r(height),
            "min": [r(minx), r(miny), r(minz)],
            "max": [r(maxx), r(maxy), r(maxz)],
        },
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return payload


def main():
    outdir = parse_outdir()
    scene = reset_scene()
    lamp = build_lamp()
    box = tight_bbox(lamp)
    assert_spec(box)
    triangles = tri_count(lamp)
    print("F006 triangles: %d" % triangles)
    if triangles > 30000:
        raise SystemExit("triangle count %d exceeds 30000" % triangles)

    preview = outdir / "preview.png"
    setup_preview(scene, lamp)
    engine = render_preview(scene, preview)
    print("preview written with %s" % engine)

    for obj in list(bpy.data.objects):
        if obj.name != "F006":
            bpy.data.objects.remove(obj, do_unlink=True)
    lamp = bpy.data.objects["F006"]

    glb = outdir / "model.glb"
    export_glb(glb, lamp)
    imported_box = measure_imported(glb, lamp)
    print(
        "imported glb bbox m: width=%.6f depth=%.6f height=%.6f"
        % dimensions(imported_box)
    )
    assert_spec(imported_box)

    lamp = bpy.data.objects["F006"]
    meta = write_metadata(outdir / "metadata.json", imported_box)
    blend = outdir / "model.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    print("wrote %s" % glb)
    print("wrote %s" % blend)
    print("wrote %s" % preview)
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
