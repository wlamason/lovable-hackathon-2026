#!/usr/bin/env python3
"""Check a furniture item or room folder against the repo's export conventions.

Pure Python. Reads model.glb (Y-up glTF, the Blender export_yup result) and
metadata.json. Does not import bpy and does not modify the folder.

    python3 .cursor/skills/blender-furniture-model/validate_model.py <folder> [<folder> ...]
    python3 .cursor/skills/blender-furniture-model/validate_model.py --all

Exit 0 when every folder passes the hard checks. Warnings (a missing
rotation_z_deg, a README without an embedded preview, an unexpected PNG
size) are printed and do not fail the run.
"""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

INCH = 0.0254
FURNITURE_TRI_BUDGET = 30_000
ROOM_TRI_BUDGET = 50_000
CATALOG_TOLERANCE = 0.02
REQUIRED_FILES = (
    "build.py",
    "model.glb",
    "model.blend",
    "preview.png",
    "metadata.json",
    "README.md",
)
REQUIRED_ANCHORS = ("Sofa_spot", "TV_wall", "Rug_center", "Coffee_spot")
FURNITURE_META_KEYS = (
    "id",
    "name",
    "category",
    "style",
    "room",
    "price_usd",
    "dimensions_in",
    "dimensions_m",
    "bounding_box_m",
)
ROOM_META_KEYS = ("id", "name", "interior_m", "bbox_m", "empties")

COMPONENT = {
    5120: ("b", 1),
    5121: ("B", 1),
    5122: ("h", 2),
    5123: ("H", 2),
    5125: ("I", 4),
    5126: ("f", 4),
}
ACCESSOR_WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "catalog" / "furniture.json").is_file():
            return parent
    return Path.cwd()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def vec3(value) -> tuple[float, float, float]:
    if isinstance(value, dict):
        return (float(value["x"]), float(value["y"]), float(value["z"]))
    return (float(value[0]), float(value[1]), float(value[2]))


def size_of(raw: dict | None) -> tuple[float, float, float] | None:
    if not isinstance(raw, dict):
        return None
    size = raw.get("size")
    if isinstance(size, dict) and {"width", "depth", "height"} <= set(size):
        return (float(size["width"]), float(size["depth"]), float(size["height"]))
    if {"width", "depth", "height"} <= set(raw):
        return (float(raw["width"]), float(raw["depth"]), float(raw["height"]))
    if isinstance(size, (list, tuple)) and len(size) == 3:
        return (float(size[0]), float(size[1]), float(size[2]))
    if "min" in raw and "max" in raw:
        minimum, maximum = vec3(raw["min"]), vec3(raw["max"])
        return tuple(maximum[i] - minimum[i] for i in range(3))  # type: ignore[return-value]
    return None


def png_size(path: Path) -> tuple[int, int] | None:
    data = path.read_bytes()[:24]
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    return struct.unpack_from(">II", data, 16)


def _identity() -> list[float]:
    return [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


def _mul(a: list[float], b: list[float]) -> list[float]:
    out = [0.0] * 16
    for col in range(4):
        for row in range(4):
            out[col * 4 + row] = sum(a[k * 4 + row] * b[col * 4 + k] for k in range(4))
    return out


def _trs(translation, rotation, scale) -> list[float]:
    tx, ty, tz = translation
    x, y, z, w = rotation
    sx, sy, sz = scale
    r00 = 1 - 2 * (y * y + z * z)
    r01 = 2 * (x * y - z * w)
    r02 = 2 * (x * z + y * w)
    r10 = 2 * (x * y + z * w)
    r11 = 1 - 2 * (x * x + z * z)
    r12 = 2 * (y * z - x * w)
    r20 = 2 * (x * z - y * w)
    r21 = 2 * (y * z + x * w)
    r22 = 1 - 2 * (x * x + y * y)
    return [
        r00 * sx, r10 * sx, r20 * sx, 0.0,
        r01 * sy, r11 * sy, r21 * sy, 0.0,
        r02 * sz, r12 * sz, r22 * sz, 0.0,
        tx, ty, tz, 1.0,
    ]


def _transform(matrix: list[float], x: float, y: float, z: float) -> tuple[float, float, float]:
    return (
        matrix[0] * x + matrix[4] * y + matrix[8] * z + matrix[12],
        matrix[1] * x + matrix[5] * y + matrix[9] * z + matrix[13],
        matrix[2] * x + matrix[6] * y + matrix[10] * z + matrix[14],
    )


def _gltf_to_blender(x: float, y: float, z: float) -> tuple[float, float, float]:
    # export_yup=True maps Blender (x, y, z) to glTF (x, z, -y).
    return (x, -z, y)


def _read_accessor(gltf: dict, blob: bytes, index: int):
    accessor = gltf["accessors"][index]
    if accessor.get("sparse"):
        raise ValueError(f"sparse accessor {index} is not supported")
    view = gltf["bufferViews"][accessor["bufferView"]]
    if view.get("buffer", 0) != 0:
        raise ValueError("only the GLB binary chunk is supported")
    fmt, width = COMPONENT[accessor["componentType"]]
    components = ACCESSOR_WIDTH[accessor["type"]]
    stride = view.get("byteStride") or width * components
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    count = accessor["count"]
    values = []
    for item in range(count):
        offset = start + item * stride
        values.append(struct.unpack_from("<" + fmt * components, blob, offset))
    return values


def measure_glb(path: Path) -> dict:
    data = path.read_bytes()
    magic, version, length = struct.unpack_from("<III", data, 0)
    if magic != 0x46546C67:
        raise ValueError(f"{path} is not a GLB")
    if version != 2:
        raise ValueError(f"{path} is glTF version {version}, expected 2")
    offset = 12
    gltf = None
    blob = b""
    while offset + 8 <= length:
        chunk_length, chunk_type = struct.unpack_from("<II", data, offset)
        chunk = data[offset + 8 : offset + 8 + chunk_length]
        if chunk_type == 0x4E4F534A:
            gltf = json.loads(chunk)
        elif chunk_type == 0x004E4942:
            blob = chunk
        offset += 8 + chunk_length
    if gltf is None:
        raise ValueError(f"{path} has no JSON chunk")

    nodes = gltf.get("nodes", [])
    worlds: dict[int, list[float]] = {}

    def visit(index: int, parent: list[float]) -> None:
        node = nodes[index]
        if "matrix" in node:
            local = [float(v) for v in node["matrix"]]
        else:
            local = _trs(
                node.get("translation", (0.0, 0.0, 0.0)),
                node.get("rotation", (0.0, 0.0, 0.0, 1.0)),
                node.get("scale", (1.0, 1.0, 1.0)),
            )
        world = _mul(parent, local)
        worlds[index] = world
        for child in node.get("children", []):
            visit(child, world)

    scene = gltf.get("scenes", [{}])[gltf.get("scene", 0)]
    for root in scene.get("nodes", []):
        visit(root, _identity())

    minimum = [1e9, 1e9, 1e9]
    maximum = [-1e9, -1e9, -1e9]
    triangles = 0
    mesh_names: list[str] = []
    saw_position = False
    for index, node in enumerate(nodes):
        mesh_index = node.get("mesh")
        if mesh_index is None:
            continue
        mesh = gltf["meshes"][mesh_index]
        mesh_names.append(node.get("name") or mesh.get("name") or f"mesh_{mesh_index}")
        world = worlds.get(index, _identity())
        for primitive in mesh.get("primitives", []):
            mode = primitive.get("mode", 4)
            if "POSITION" not in primitive.get("attributes", {}):
                continue
            positions = _read_accessor(gltf, blob, primitive["attributes"]["POSITION"])
            saw_position = True
            for position in positions:
                point = _transform(world, *position[:3])
                blender = _gltf_to_blender(*point)
                for axis in range(3):
                    minimum[axis] = min(minimum[axis], blender[axis])
                    maximum[axis] = max(maximum[axis], blender[axis])
            if mode != 4:
                raise ValueError(f"primitive mode {mode} is not TRIANGLES")
            if "indices" in primitive:
                triangles += len(_read_accessor(gltf, blob, primitive["indices"])) // 3
            else:
                triangles += len(positions) // 3
    if not saw_position:
        raise ValueError(f"{path} has no mesh positions")
    size = tuple(maximum[axis] - minimum[axis] for axis in range(3))
    return {
        "min": tuple(minimum),
        "max": tuple(maximum),
        "size": size,
        "triangles": triangles,
        "meshes": mesh_names,
    }


def preview_embedded(text: str) -> bool:
    """True when the README includes a Markdown image, not just the filename in prose."""
    return "](preview.png)" in text or "](./preview.png)" in text


def relative_error(got: float, expected: float) -> float:
    if abs(expected) < 1e-9:
        return abs(got - expected)
    return abs(got - expected) / abs(expected)


def within(got: float, expected: float, tolerance: float, absolute: float = 0.0005) -> bool:
    return abs(got - expected) <= max(absolute, abs(expected) * tolerance)


class Report:
    def __init__(self, folder: Path):
        self.folder = folder
        self.failures: list[str] = []
        self.warnings: list[str] = []

    def fail(self, message: str) -> None:
        self.failures.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def check_files(folder: Path, report: Report) -> None:
    for name in REQUIRED_FILES:
        path = folder / name
        if not path.is_file() or path.stat().st_size == 0:
            report.fail(f"missing or empty {name}")
    backups = sorted(folder.glob("*.blend1")) + sorted(folder.glob("*.blend2"))
    for backup in backups:
        report.fail(f"Blender backup left in the folder: {backup.name}")


def check_furniture(folder: Path, meta: dict, measured: dict, report: Report) -> None:
    for key in FURNITURE_META_KEYS:
        if key not in meta:
            report.fail(f"metadata.json missing {key}")
    dims = meta.get("dimensions_m") or {}
    if not {"width", "depth", "height"} <= set(dims):
        report.fail("dimensions_m needs width, depth, height")
        return
    expected = (float(dims["width"]), float(dims["depth"]), float(dims["height"]))
    got = measured["size"]
    labels = ("width", "depth", "height")
    for label, actual, target in zip(labels, got, expected):
        error = relative_error(actual, target)
        if error > CATALOG_TOLERANCE:
            report.fail(
                f"{label} {actual:.4f} m is {error:.2%} off catalog {target:.4f} m "
                f"(limit {CATALOG_TOLERANCE:.0%})"
            )
    recorded = size_of(meta.get("bounding_box_m"))
    if recorded is None:
        report.fail("bounding_box_m has no size")
    else:
        for label, actual, target in zip(labels, got, recorded):
            if not within(actual, target, 0.01):
                report.fail(
                    f"glb {label} {actual:.4f} m does not match metadata bounding_box_m {target:.4f} m"
                )
    minimum = measured["min"]
    center_x = (measured["min"][0] + measured["max"][0]) * 0.5
    center_y = (measured["min"][1] + measured["max"][1]) * 0.5
    for label, actual, span in (
        ("origin x", center_x, expected[0]),
        ("origin y", center_y, expected[1]),
        ("origin z", minimum[2], expected[2]),
    ):
        limit = max(0.002, CATALOG_TOLERANCE * span)
        if abs(actual) > limit:
            report.fail(f"{label} is {actual:.4f} m; bottom center should sit on the floor at 0")
    if measured["triangles"] > FURNITURE_TRI_BUDGET:
        report.fail(f"{measured['triangles']} triangles exceeds {FURNITURE_TRI_BUDGET}")
    recorded_tris = meta.get("triangle_count")
    if recorded_tris is None:
        report.warn("metadata.json has no triangle_count (several early items omitted it)")
    elif int(recorded_tris) != measured["triangles"]:
        report.fail(
            f"metadata triangle_count {recorded_tris} != glb {measured['triangles']}"
        )
    preview = png_size(folder / "preview.png")
    if preview is None:
        report.fail("preview.png is not a PNG")
    elif preview != (512, 512):
        report.warn(f"preview.png is {preview[0]}x{preview[1]}; furniture previews are 512x512")
    readme = (folder / "README.md").read_text(encoding="utf-8") if (folder / "README.md").is_file() else ""
    if not preview_embedded(readme):
        report.warn("README.md does not embed preview.png as an image")


def check_room(folder: Path, meta: dict, measured: dict, report: Report) -> None:
    for key in ROOM_META_KEYS:
        if key not in meta:
            report.fail(f"metadata.json missing {key}")
    interior = meta.get("interior_m") or {}
    for key in ("width_x", "depth_y", "height_z"):
        if key not in interior:
            report.fail(f"interior_m missing {key}")
    recorded = size_of(meta.get("bbox_m"))
    if recorded is None:
        report.fail("bbox_m has no size")
    else:
        for label, actual, target in zip(("x", "y", "z"), measured["size"], recorded):
            if not within(actual, float(target), 0.02, absolute=0.01):
                report.fail(
                    f"glb size {label} {actual:.4f} m does not match metadata bbox_m {float(target):.4f} m"
                )
    if measured["triangles"] > ROOM_TRI_BUDGET:
        report.fail(f"{measured['triangles']} triangles exceeds {ROOM_TRI_BUDGET}")
    recorded_tris = meta.get("triangle_count")
    if recorded_tris is None:
        report.warn("metadata.json has no triangle_count")
    elif int(recorded_tris) != measured["triangles"]:
        report.fail(
            f"metadata triangle_count {recorded_tris} != glb {measured['triangles']}"
        )
    empties = meta.get("empties") or {}
    if not isinstance(empties, dict):
        report.fail("empties must be an object keyed by anchor name")
        empties = {}
    for name in REQUIRED_ANCHORS:
        if name not in empties:
            report.fail(f"missing anchor {name}")
    for name, info in empties.items():
        if not isinstance(info, dict) or "position_m" not in info:
            report.fail(f"anchor {name} has no position_m")
            continue
        try:
            position = vec3(info["position_m"])
        except (KeyError, TypeError, ValueError):
            report.fail(f"anchor {name} position_m is not a 3-vector")
            continue
        if abs(position[2]) > 0.05:
            report.warn(f"anchor {name} Z is {position[2]:.3f}; floor anchors are Z=0")
        has_yaw = "yaw_deg" in info
        has_rotation = "rotation_z_deg" in info
        if not has_yaw and not has_rotation:
            report.warn(f"anchor {name} has no yaw_deg or rotation_z_deg")
        elif has_yaw and not has_rotation:
            report.warn(
                f"anchor {name} sets yaw_deg but not rotation_z_deg; "
                "db/build_db.py only copies rotation_z_deg"
            )
        elif has_yaw and has_rotation and abs(float(info["yaw_deg"]) - float(info["rotation_z_deg"])) > 0.1:
            report.fail(f"anchor {name} yaw_deg and rotation_z_deg disagree")
    if "free_floor" not in meta:
        report.warn("metadata.json has no free_floor; photo rooms record where furniture can sit")
    preview = png_size(folder / "preview.png")
    if preview is None:
        report.fail("preview.png is not a PNG")
    elif preview[0] < 900 or preview[1] < 480:
        report.warn(
            f"preview.png is {preview[0]}x{preview[1]}; photo-room previews are about 1024x640"
        )
    readme = (folder / "README.md").read_text(encoding="utf-8") if (folder / "README.md").is_file() else ""
    if not preview_embedded(readme):
        report.warn("README.md does not embed preview.png as an image")
    if "blender -b" not in readme:
        report.warn("README.md does not include the headless blender command")


def check_folder(folder: Path) -> Report:
    folder = folder.resolve()
    report = Report(folder)
    check_files(folder, report)
    meta_path = folder / "metadata.json"
    glb_path = folder / "model.glb"
    if not meta_path.is_file() or not glb_path.is_file():
        return report
    try:
        meta = load_json(meta_path)
    except json.JSONDecodeError as exc:
        report.fail(f"metadata.json is not JSON: {exc}")
        return report
    try:
        measured = measure_glb(glb_path)
    except (ValueError, KeyError, struct.error) as exc:
        report.fail(f"could not measure model.glb: {exc}")
        return report
    kind = "room" if "interior_m" in meta or "empties" in meta else "furniture"
    if kind == "room":
        check_room(folder, meta, measured, report)
    else:
        check_furniture(folder, meta, measured, report)
    report.measured = measured  # type: ignore[attr-defined]
    report.kind = kind  # type: ignore[attr-defined]
    return report


def discover(root: Path) -> list[Path]:
    folders = []
    models = root / "models"
    if models.is_dir():
        folders.extend(sorted(path.parent for path in models.glob("*/*/model.glb")))
    rooms = root / "rooms"
    if rooms.is_dir():
        folders.extend(sorted(path.parent for path in rooms.glob("*/model.glb")))
    return folders


def print_report(report: Report) -> None:
    measured = getattr(report, "measured", None)
    kind = getattr(report, "kind", "?")
    try:
        shown = report.folder.relative_to(repo_root())
    except ValueError:
        shown = report.folder
    status = "PASS" if not report.failures else "FAIL"
    print(f"{status} {shown} ({kind})")
    if measured:
        size = measured["size"]
        minimum = measured["min"]
        print(
            f"  triangles {measured['triangles']}"
            f"  bbox_m {size[0]:.4f} x {size[1]:.4f} x {size[2]:.4f}"
            f"  min ({minimum[0]:.4f}, {minimum[1]:.4f}, {minimum[2]:.4f})"
        )
    for message in report.failures:
        print(f"  FAIL {message}")
    for message in report.warnings:
        print(f"  WARN {message}")


def main(argv: list[str]) -> int:
    root = repo_root()
    args = argv[1:]
    if not args or args == ["--all"]:
        folders = discover(root)
    else:
        folders = []
        for arg in args:
            if arg == "--all":
                folders.extend(discover(root))
            else:
                folders.append(Path(arg))
    if not folders:
        print("no model folders found", file=sys.stderr)
        return 1
    failed = 0
    for folder in folders:
        if not folder.is_dir():
            print(f"FAIL {folder}")
            print("  FAIL folder does not exist")
            failed += 1
            continue
        report = check_folder(folder)
        print_report(report)
        if report.failures:
            failed += 1
    print(f"{len(folders) - failed} passed, {failed} failed, {len(folders)} checked")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
