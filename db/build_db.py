#!/usr/bin/env python3
"""Rebuild db/db.json from the spreadsheet, enrichment, catalog, and model files.

Reads db/source/objects.xlsx, db/source/enrichment.json, catalog/furniture.json,
each model's metadata.json and build.py, and every rooms/*/metadata.json on disk
or on a fetched origin branch. Principled BSDF base colors become swatch hex values.
Demo merchandising stays in enrichment.json so a rebuild does not drop it.

    python3 db/build_db.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_DIR = Path(__file__).resolve().parent
XLSX_PATH = DB_DIR / "source" / "objects.xlsx"
ENRICHMENT_PATH = DB_DIR / "source" / "enrichment.json"
OUT_PATH = DB_DIR / "db.json"
RAW_BASE = "https://raw.githubusercontent.com/wlamason/lovable-hackathon-2026/main"
STYLE_ORDER = [
    "modern",
    "coastal",
    "minimal",
    "scandinavian",
    "japandi",
    "industrial",
    "bohemian",
]
CATEGORY_ORDER = ["couch", "lamp", "table", "carpet", "tv", "plant"]
MATERIAL_CALLS = ("make_material", "new_material", "principled", "new_principled")

INCH_TO_M = 0.0254
SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
ASSET_NAMES = ("model.glb", "model.blend", "preview.png", "metadata.json")
ROLE_TAGS = {
    "Couch": ["seating"],
    "Lamp": ["lighting"],
    "Table": ["table"],
    "Carpet": ["rug"],
    "TV": ["screen"],
    "Plant": ["greenery"],
}

_trees: dict[str, set[str]] = {}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True)


def git_refs() -> list[str]:
    lines = git(
        "for-each-ref",
        "--format=%(refname:short)",
        "refs/remotes/origin",
    ).splitlines()
    return [line for line in lines if line and not line.endswith("/HEAD")]


def tree_paths(ref: str) -> set[str]:
    cached = _trees.get(ref)
    if cached is None:
        cached = set(git("ls-tree", "-r", "--name-only", ref).splitlines())
        _trees[ref] = cached
    return cached


def refs_with(rel: str) -> list[str]:
    return [ref for ref in git_refs() if rel in tree_paths(ref)]


def read_repo_text(rel: str) -> str:
    path = ROOT / rel
    if path.is_file():
        return path.read_text(encoding="utf-8")
    for ref in refs_with(rel):
        return git("show", f"{ref}:{rel}")
    raise FileNotFoundError(rel)


def short_ref(ref: str | None) -> str | None:
    if ref and ref.startswith("origin/"):
        return ref[len("origin/") :]
    return ref


def load_pull_requests() -> dict[str, dict]:
    try:
        raw = subprocess.check_output(
            [
                "gh",
                "pr",
                "list",
                "--state",
                "all",
                "--limit",
                "100",
                "--json",
                "number,state,headRefName,title",
            ],
            cwd=ROOT,
            text=True,
        )
        pulls = json.loads(raw)
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
        pulls = []
    return {pull["headRefName"]: pull for pull in pulls}


def r4(value: float) -> float:
    rounded = round(float(value), 4)
    return 0.0 if rounded == 0 else rounded


def vec3(value) -> list[float]:
    if isinstance(value, dict):
        return [r4(value["x"]), r4(value["y"]), r4(value["z"])]
    return [r4(value[0]), r4(value[1]), r4(value[2])]


def normalize_bbox(raw: dict | None) -> dict | None:
    if not raw or "min" not in raw or "max" not in raw:
        return None
    minimum = vec3(raw["min"])
    maximum = vec3(raw["max"])
    size_src = raw.get("size") if isinstance(raw.get("size"), dict) else raw
    if {"width", "depth", "height"} <= set(size_src):
        size = {
            "width": r4(size_src["width"]),
            "depth": r4(size_src["depth"]),
            "height": r4(size_src["height"]),
        }
    else:
        size = {
            "width": r4(maximum[0] - minimum[0]),
            "depth": r4(maximum[1] - minimum[1]),
            "height": r4(maximum[2] - minimum[2]),
        }
    return {"min": minimum, "max": maximum, "size": size}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")


def tag(text: str) -> str:
    return slug(text).replace("_", "-")


def as_number(value: str):
    number = float(value)
    if number.is_integer():
        return int(number)
    return number


def parse_catalog_sheet(path: Path) -> list[dict]:
    ns = {"m": SPREADSHEET_NS}
    with zipfile.ZipFile(path) as workbook:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in workbook.namelist():
            root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
            for entry in root.findall("m:si", ns):
                texts = [
                    node.text or ""
                    for node in entry.iter(f"{{{SPREADSHEET_NS}}}t")
                ]
                shared.append("".join(texts))

        book = ET.fromstring(workbook.read("xl/workbook.xml"))
        rels = ET.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
        targets = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}
        sheet_path = None
        for sheet in book.findall("m:sheets/m:sheet", ns):
            if sheet.attrib.get("name") == "Furniture Catalog":
                target = targets[sheet.attrib[f"{{{REL_NS}}}id"]]
                sheet_path = target if target.startswith("xl/") else f"xl/{target}"
                break
        if sheet_path is None:
            raise SystemExit("xlsx is missing the 'Furniture Catalog' sheet")

        root = ET.fromstring(workbook.read(sheet_path))
        rows: dict[int, dict[int, str]] = {}
        for cell in root.iter(f"{{{SPREADSHEET_NS}}}c"):
            ref = cell.attrib.get("r")
            if not ref:
                continue
            column = 0
            index = 0
            while index < len(ref) and ref[index].isalpha():
                column = column * 26 + (ord(ref[index].upper()) - 64)
                index += 1
            row_number = int(ref[index:])
            kind = cell.attrib.get("t")
            value_node = cell.find("m:v", ns)
            inline = cell.find("m:is", ns)
            if kind == "s" and value_node is not None and value_node.text is not None:
                value = shared[int(value_node.text)]
            elif kind == "inlineStr" and inline is not None:
                value = "".join(
                    node.text or ""
                    for node in inline.iter(f"{{{SPREADSHEET_NS}}}t")
                )
            elif value_node is not None and value_node.text is not None:
                value = value_node.text
            else:
                value = ""
            rows.setdefault(row_number, {})[column] = value

    header_row = rows[min(rows)]
    headers = [header_row[key] for key in sorted(header_row)]
    records = []
    for row_number in sorted(rows):
        if row_number == min(rows):
            continue
        values = rows[row_number]
        record = {}
        for column, header in enumerate(headers, start=1):
            record[header] = values.get(column, "")
        if record.get("Item ID"):
            records.append(record)
    return records


def discover_metadata(prefix: str) -> list[str]:
    """Every rooms/<id>/metadata.json or models/<category>/<id>/metadata.json on disk or any origin ref."""
    pattern = re.compile(rf"^{re.escape(prefix)}/[^/]+/metadata\.json$")
    if prefix == "models":
        pattern = re.compile(r"^models/[^/]+/[^/]+/metadata\.json$")
    found: set[str] = set()
    root = ROOT / prefix
    if root.is_dir():
        for path in root.glob("*/metadata.json" if prefix != "models" else "*/*/metadata.json"):
            rel = path.relative_to(ROOT).as_posix()
            if pattern.match(rel):
                found.add(rel)
    for ref in git_refs():
        for rel in tree_paths(ref):
            if pattern.match(rel):
                found.add(rel)
    return sorted(found)


def refresh_refs() -> None:
    """Pick up room branches that landed after this checkout. Failure leaves the current refs in place."""
    try:
        subprocess.run(
            ["git", "fetch", "origin", "--prune"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return
    _trees.clear()


def lin_to_srgb_channel(value: float) -> float:
    value = max(0.0, min(1.0, float(value)))
    if value <= 0.0031308:
        return 12.92 * value
    return 1.055 * (value ** (1.0 / 2.4)) - 0.055


def rgb_hex(rgb: tuple[float, float, float]) -> str:
    channels = [max(0, min(255, int(round(channel * 255)))) for channel in rgb]
    return "#" + "".join(f"{channel:02X}" for channel in channels)


def display_rgb(rgb: tuple[float, float, float], space: str) -> tuple[float, float, float]:
    if space == "linear":
        return tuple(lin_to_srgb_channel(channel) for channel in rgb)  # type: ignore[return-value]
    return tuple(max(0.0, min(1.0, float(channel))) for channel in rgb)  # type: ignore[return-value]


def load_enrichment() -> dict:
    if not ENRICHMENT_PATH.is_file():
        raise SystemExit(f"missing enrichment file: {ENRICHMENT_PATH}")
    data = json.loads(ENRICHMENT_PATH.read_text(encoding="utf-8"))
    data.setdefault("brands", [])
    data.setdefault("items", {})
    return data


def image_ref(rel: str) -> dict:
    return {"path": rel, "url": f"{RAW_BASE}/{rel}"}


def _split_args(blob: str) -> list[str]:
    args: list[str] = []
    buf: list[str] = []
    depth = 0
    quote = None
    for char in blob:
        if quote:
            buf.append(char)
            if char == quote:
                quote = None
            continue
        if char in ("'", '"'):
            quote = char
            buf.append(char)
            continue
        if char in "([{":
            depth += 1
            buf.append(char)
            continue
        if char in ")]}":
            depth -= 1
            buf.append(char)
            continue
        if char == "," and depth == 0:
            args.append("".join(buf).strip())
            buf = []
            continue
        buf.append(char)
    tail = "".join(buf).strip()
    if tail:
        args.append(tail)
    return args


def _parse_rgb_token(token: str, constants: dict[str, str]):
    token = token.strip()
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token) and token in constants:
        token = constants[token].strip()
    hex_match = re.fullmatch(r"['\"]?(#[0-9A-Fa-f]{6})['\"]?", token)
    if hex_match:
        text = hex_match.group(1)[1:]
        rgb = tuple(int(text[index : index + 2], 16) / 255 for index in (0, 2, 4))
        return rgb, "srgb"
    tuple_match = re.fullmatch(r"\(([^)]+)\)", re.sub(r"\s+", " ", token))
    if not tuple_match:
        return None
    numbers = []
    for part in tuple_match.group(1).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            numbers.append(float(part))
        except ValueError:
            return None
    if len(numbers) < 3:
        return None
    return tuple(numbers[:3]), None


def _helper_space(text: str, fn_name: str) -> str:
    match = re.search(rf"^def {fn_name}\(", text, re.M)
    if not match:
        return "linear"
    nxt = re.search(r"^def ", text[match.end() :], re.M)
    body = text[match.start() : match.end() + nxt.start()] if nxt else text[match.start() :]
    if "srgb_to_linear" in body or "linear_rgb" in body:
        return "srgb"
    return "linear"


def _module_constants(text: str) -> dict[str, str]:
    constants = {}
    pattern = re.compile(
        r"^([A-Z][A-Z0-9_]*)\s*=\s*(\([^)\n]+\)|\"#[0-9A-Fa-f]{6}\"|'#[0-9A-Fa-f]{6}')",
        re.M,
    )
    for match in pattern.finditer(text):
        constants[match.group(1)] = match.group(2)
    return constants


def _as_float(token: str | None) -> float | None:
    if token is None:
        return None
    try:
        return float(token.strip().rstrip(","))
    except ValueError:
        return None


def _keyword_map(args: list[str]) -> tuple[list[str], dict[str, str]]:
    positionals = []
    keywords = {}
    for arg in args:
        key_match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", arg, re.S)
        if key_match:
            keywords[key_match.group(1)] = key_match.group(2).strip()
        else:
            positionals.append(arg)
    return positionals, keywords


def _iter_calls(text: str):
    for name in MATERIAL_CALLS:
        token = name + "("
        start = 0
        while True:
            index = text.find(token, start)
            if index < 0:
                break
            if text[max(0, index - 4) : index] == "def ":
                start = index + len(token)
                continue
            depth = 0
            for cursor in range(index + len(name), len(text)):
                char = text[cursor]
                if char == "(":
                    depth += 1
                elif char == ")":
                    depth -= 1
                    if depth == 0:
                        yield name, text[index + len(token) : cursor]
                        start = cursor + 1
                        break
            else:
                break


def _material_role(name: str, metallic: float, emission: float) -> str:
    lowered = name.lower()
    if emission >= 1:
        return "light"
    if metallic >= 0.5:
        return "metal"
    if any(token in lowered for token in ("leaf", "vein", "petiole", "bark", "fruit", "olive")):
        return "foliage"
    if any(token in lowered for token in ("pot", "ceramic", "terracotta", "saucer", "soil", "slip")):
        return "planter"
    if any(token in lowered for token in ("fabric", "linen", "seat", "cushion", "pillow", "shade")):
        return "textile"
    if any(token in lowered for token in ("oak", "birch", "wood", "drift")):
        return "wood"
    if any(token in lowered for token in ("bezel", "screen", "slate")):
        return "surface"
    return "finish"


def _is_preview_material(name: str) -> bool:
    lowered = name.lower()
    if any(token in lowered for token in ("preview", "ground", "wall")):
        return True
    return lowered == "floor" or lowered.endswith("_floor") or lowered.endswith("floor")


def _material_record(name: str, rgb, space: str, roughness, metallic, emission, source: str) -> dict:
    authored = tuple(float(channel) for channel in rgb)
    shown = display_rgb(authored, space)
    record = {
        "name": name,
        "role": _material_role(name, metallic or 0.0, emission or 0.0),
        "color_space": space,
        "base_color_rgb": [round(channel, 4) for channel in authored],
        "hex": rgb_hex(shown),
        "roughness": None if roughness is None else round(roughness, 4),
        "metallic": round(metallic or 0.0, 4),
        "source": source,
    }
    if emission:
        record["emission_strength"] = round(emission, 4)
    return record


def extract_materials(text: str, source: str) -> list[dict]:
    constants = _module_constants(text)
    spaces = {name: _helper_space(text, name) for name in MATERIAL_CALLS}
    found: list[dict] = []
    seen: set[str] = set()

    def add(name: str, parsed, space: str, roughness, metallic, emission) -> None:
        if not name or name in seen or _is_preview_material(name):
            return
        if name in {"Key", "Fill", "Rim", "Bounce"}:
            return
        rgb, forced = parsed
        if any(channel < -0.001 or channel > 1.001 for channel in rgb):
            return
        if forced:
            space = forced
        seen.add(name)
        found.append(
            _material_record(name, rgb, space, roughness, metallic or 0.0, emission or 0.0, source)
        )

    for fn_name, blob in _iter_calls(text):
        positionals, keywords = _keyword_map(_split_args(blob))
        if len(positionals) < 2:
            continue
        name_match = re.fullmatch(r"['\"]([^'\"]+)['\"]", positionals[0].strip())
        if not name_match:
            continue
        parsed = _parse_rgb_token(positionals[1], constants)
        if parsed is None:
            continue
        roughness = _as_float(keywords.get("roughness") or keywords.get("rough"))
        if roughness is None and len(positionals) >= 3:
            roughness = _as_float(positionals[2])
        metallic = _as_float(keywords.get("metallic") or keywords.get("metal")) or 0.0
        emission = _as_float(keywords.get("emission_strength") or keywords.get("emit_strength")) or 0.0
        add(name_match.group(1), parsed, spaces.get(fn_name, "linear"), roughness, metallic, emission)

    spec_pattern = re.compile(
        r"\(\s*['\"]([^'\"]+)['\"]\s*,\s*(\([^)]+\)|['\"]#[0-9A-Fa-f]{6}['\"])\s*,\s*([0-9.]+)",
        re.S,
    )
    file_space = "srgb" if ("srgb_to_linear" in text or "linear_rgb(" in text) else "linear"
    for match in spec_pattern.finditer(text):
        parsed = _parse_rgb_token(match.group(2), constants)
        if parsed is None:
            continue
        add(match.group(1), parsed, file_space, _as_float(match.group(3)), 0.0, 0.0)

    leaf_match = re.search(r"^def leaf_color\(", text, re.M)
    if leaf_match:
        leaf_next = re.search(r"^def ", text[leaf_match.end() :], re.M)
        leaf_body = (
            text[leaf_match.start() : leaf_match.end() + leaf_next.start()]
            if leaf_next
            else text[leaf_match.start() :]
        )
        for label, key in (
            ("F015_LeafDark", "dark"),
            ("F015_LeafMid", "mid"),
            ("F015_LeafPale", "pale"),
            ("F015_LeafEdge", "yellow"),
        ):
            match = re.search(
                rf"\b{key}\s*=\s*\(([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\)",
                leaf_body,
            )
            if match:
                add(
                    label,
                    (tuple(float(match.group(i)) for i in (1, 2, 3)), None),
                    "linear",
                    None,
                    0.0,
                    0.0,
                )
        for record in found:
            if record["name"] == "F015_Leaf":
                record["vertex_colors"] = True
                record["note"] = "Principled Base Color is driven by vertex colors. F015_LeafMid is the blade body."

    for created in re.finditer(r"materials\.new\(\s*['\"]([^'\"]+)['\"]\s*\)", text):
        window = text[created.end() : created.end() + 700]
        next_new = re.search(r"materials\.new\(", window)
        if next_new:
            window = window[: next_new.start()]
        color_match = re.search(
            r"Base Color['\"]\s*,\s*\)\s*,\s*(\([^)]+\))",
            window,
        )
        if not color_match:
            continue
        parsed = _parse_rgb_token(color_match.group(1), constants)
        if parsed is None:
            continue
        rough_match = re.search(r"Roughness['\"]\s*,\s*\)\s*,\s*([0-9.]+)", window)
        metal_match = re.search(r"Metallic['\"]\s*,\s*\)\s*,\s*([0-9.]+)", window)
        emit_match = re.search(r"Emission Strength['\"]\s*,\s*\)\s*,\s*([0-9.]+)", window)
        add(
            created.group(1),
            parsed,
            "srgb" if "srgb_to_linear" in window else "linear",
            _as_float(rough_match.group(1)) if rough_match else None,
            _as_float(metal_match.group(1)) if metal_match else 0.0,
            _as_float(emit_match.group(1)) if emit_match else 0.0,
        )
    return found


def choose_primary_material(materials: list[dict], preferred: str | None) -> dict | None:
    if preferred:
        for record in materials:
            if record["name"] == preferred:
                return record
    best = None
    best_score = -10_000
    for record in materials:
        name = record["name"].lower()
        score = 0
        if any(token in name for token in ("fabric", "field", "seat", "oaktop", "leafmid", "birch")):
            score += 100
        if "leaf" in name and not any(token in name for token in ("vein", "pale", "deep", "edge", "dark")):
            score += 80
        if "linen" in name and "trim" not in name:
            score += 90
        if any(token in name for token in ("oak", "slate", "shade", "bezel", "brass")):
            score += 40
        if any(
            token in name
            for token in ("pot", "soil", "bark", "backing", "bulb", "led", "indicator", "plinth", "leg", "trim")
        ):
            score -= 30
        if record.get("emission_strength", 0) >= 1:
            score -= 40
        if record.get("vertex_colors"):
            score -= 50
        if score > best_score:
            best = record
            best_score = score
    return best or (materials[0] if materials else None)


def choose_feature_ref(common: set[str], hint: str | None) -> str | None:
    feature = sorted(ref for ref in common if ref != "origin/main")
    if hint:
        needle = hint.lower()
        for ref in feature:
            if needle in ref.lower():
                return ref
    for ref in feature:
        if "living-room" in ref:
            return ref
    return feature[0] if feature else None


def locate_assets(folder: str, hint: str | None, pulls: dict[str, dict]) -> dict:
    per_file: dict[str, list[str]] = {}
    missing: list[str] = []
    for name in ASSET_NAMES:
        rel = f"{folder}/{name}"
        refs = refs_with(rel)
        per_file[name] = refs
        if not refs:
            missing.append(rel)
    common: set[str] = set()
    if not missing:
        common = set.intersection(*(set(refs) for refs in per_file.values()))
    on_main = "origin/main" in common
    feature = choose_feature_ref(common, hint)
    branch = short_ref(feature)
    pull = pulls.get(branch) if branch else None
    state = pull["state"] if pull else None
    return {
        "folder": folder,
        "glb": f"{folder}/model.glb",
        "blend": f"{folder}/model.blend",
        "preview": f"{folder}/preview.png",
        "metadata": f"{folder}/metadata.json",
        "available": not missing,
        "missing": missing,
        "branch": branch,
        "pull_request": pull["number"] if pull else None,
        "pull_request_state": state,
        "on_default_branch": on_main,
        "only_open_pr": (not on_main) and state == "OPEN",
    }


def photo_credit(source_url: str) -> str:
    if "unsplash.com" in source_url:
        return "Unsplash"
    parts = source_url.split("/")
    return parts[2] if len(parts) > 2 else "Unknown"


def meters_from_inches(inches: dict) -> dict:
    return {
        "width": r4(float(inches["width"]) * INCH_TO_M),
        "depth": r4(float(inches["depth"]) * INCH_TO_M),
        "height": r4(float(inches["height"]) * INCH_TO_M),
    }


def same_dims(left: dict, right: dict) -> bool:
    return all(r4(left[key]) == r4(right[key]) for key in ("width", "depth", "height"))


def round_tree(value):
    if isinstance(value, dict):
        return {key: round_tree(item) for key, item in value.items()}
    if isinstance(value, list):
        return [round_tree(item) for item in value]
    if isinstance(value, float):
        return r4(value)
    return value


def source_block(located: dict, *, spreadsheet: bool) -> dict:
    block = {
        "branch": located["branch"],
        "pull_request": located["pull_request"],
        "pull_request_state": located["pull_request_state"],
        "on_default_branch": located["on_default_branch"],
        "only_open_pr": located["only_open_pr"],
    }
    if spreadsheet:
        block = {
            "spreadsheet": "db/source/objects.xlsx",
            "sheet": "Furniture Catalog",
            **block,
        }
    return block


def build() -> dict:
    if not XLSX_PATH.is_file():
        raise SystemExit(f"missing spreadsheet: {XLSX_PATH}")

    refresh_refs()
    pulls = load_pull_requests()
    enrichment = load_enrichment()
    brands_by_id = {brand["id"]: brand for brand in enrichment["brands"]}
    item_overrides = enrichment.get("items", {})
    catalog = json.loads(read_repo_text("catalog/furniture.json"))
    catalog_by_id = {item["id"]: item for item in catalog["items"]}
    sheet_rows = parse_catalog_sheet(XLSX_PATH)
    sheet_by_id = {row["Item ID"].strip(): row for row in sheet_rows}

    gaps: list[dict] = []
    warnings: list[str] = []

    room_records = []
    for rel in discover_metadata("rooms"):
        meta = json.loads(read_repo_text(rel))
        folder = str(Path(rel).parent.as_posix())
        located = locate_assets(folder, meta.get("id"), pulls)
        anchors = []
        for anchor_id, info in meta.get("empties", {}).items():
            anchor = {"id": anchor_id, "position_m": vec3(info["position_m"])}
            if "rotation_z_deg" in info:
                anchor["rotation_z_deg"] = info["rotation_z_deg"]
            if info.get("note"):
                anchor["note"] = info["note"]
            anchors.append(anchor)
        room_records.append(
            {
                "id": meta.get("id") or Path(folder).name,
                "name": meta.get("name") or Path(folder).name,
                "model": {
                    "glb": located["glb"],
                    "blend": located["blend"],
                    "preview": located["preview"],
                    "metadata": located["metadata"],
                    "folder": folder,
                    "available": located["available"],
                },
                "interior_m": round_tree(meta.get("interior_m")),
                "wall_thickness_m": r4(meta["wall_thickness_m"])
                if "wall_thickness_m" in meta
                else None,
                "anchors": anchors,
                "openings": round_tree(meta.get("openings")),
                "bbox_m": normalize_bbox(meta.get("bbox_m")),
                "origin": meta.get("origin"),
                "up_axis": meta.get("up_axis"),
                "source": source_block(located, spreadsheet=False),
                "_located": located,
            }
        )

    def room_for(label: str) -> dict | None:
        matches = [
            room
            for room in room_records
            if label.lower() in room["name"].lower()
            or label.lower().replace(" ", "_") in room["id"]
        ]
        return matches[0] if matches else None

    items = []
    seen: set[str] = set()
    ordered_ids = [row["Item ID"].strip() for row in sheet_rows]
    for item_id in list(catalog_by_id):
        if item_id not in sheet_by_id and item_id not in ordered_ids:
            ordered_ids.append(item_id)

    for item_id in ordered_ids:
        seen.add(item_id)
        row = sheet_by_id.get(item_id)
        catalog_item = catalog_by_id.get(item_id)
        if row is None:
            gaps.append(
                {
                    "id": item_id,
                    "kind": "missing_spreadsheet_row",
                    "detail": "Present in catalog/furniture.json and absent from the spreadsheet.",
                }
            )
            continue
        if catalog_item is None:
            gaps.append(
                {
                    "id": item_id,
                    "kind": "missing_catalog_row",
                    "detail": "Present in the spreadsheet and absent from catalog/furniture.json.",
                }
            )
            continue

        inches = {
            "width": as_number(row["Width (in)"]),
            "depth": as_number(row["Depth (in)"]),
            "height": as_number(row["Height (in)"]),
        }
        meters = meters_from_inches(inches)
        catalog_inches = catalog_item.get("dimensions_in") or {}
        if catalog_inches and not same_dims(inches, catalog_inches):
            warnings.append(
                f"{item_id} spreadsheet inches {inches} differ from catalog {catalog_inches}"
            )
        catalog_meters = catalog_item.get("dimensions_m") or {}
        if catalog_meters and not same_dims(meters, catalog_meters):
            warnings.append(
                f"{item_id} computed meters {meters} differ from catalog {catalog_meters}"
            )
        for field, sheet_key, catalog_key in (
            ("name", "Item", "name"),
            ("category", "Category", "category"),
            ("style", "Style", "style"),
            ("room", "Room", "room"),
        ):
            if str(row[sheet_key]).strip() != str(catalog_item.get(catalog_key, "")).strip():
                warnings.append(
                    f"{item_id} {field} spreadsheet {row[sheet_key]!r} catalog {catalog_item.get(catalog_key)!r}"
                )
        if int(as_number(row["Price (USD)"])) != int(catalog_item.get("price_usd")):
            warnings.append(
                f"{item_id} price spreadsheet {row['Price (USD)']!r} catalog {catalog_item.get('price_usd')!r}"
            )

        folder = catalog_item["path"].rstrip("/")
        located = locate_assets(folder, item_id, pulls)
        measured = None
        triangle_count = None
        if located["metadata"] and refs_with(located["metadata"]):
            meta = json.loads(read_repo_text(located["metadata"]))
            measured = normalize_bbox(meta.get("bounding_box_m"))
            triangle_count = meta.get("triangle_count")
            if meta.get("id") and meta["id"] != item_id:
                warnings.append(
                    f"{item_id} metadata id is {meta.get('id')}"
                )
        if not located["available"]:
            gaps.append(
                {
                    "id": item_id,
                    "kind": "missing_model_files",
                    "detail": "Catalog folder is missing files: " + ", ".join(located["missing"]),
                    "missing": located["missing"],
                }
            )
        elif not located["on_default_branch"]:
            where = (
                f"PR #{located['pull_request']} ({located['branch']})"
                if located["pull_request"]
                else located["branch"] or "no branch"
            )
            gaps.append(
                {
                    "id": item_id,
                    "kind": "not_on_default_branch",
                    "detail": f"Model files are on {where} and are not on origin/main.",
                    "only_open_pr": located["only_open_pr"],
                }
            )

        level = room_for(row["Room"].strip())
        tags = []
        for candidate in (
            tag(row["Category"]),
            tag(row["Style"]),
            tag(row["Room"]),
            *ROLE_TAGS.get(row["Category"].strip(), []),
        ):
            if candidate and candidate not in tags:
                tags.append(candidate)

        model = {
            "glb": located["glb"],
            "blend": located["blend"],
            "preview": located["preview"],
            "metadata": located["metadata"],
            "folder": folder,
            "available": located["available"],
        }
        if triangle_count is not None:
            model["triangle_count"] = triangle_count

        override = item_overrides.get(item_id, {})
        build_script = f"{folder}/build.py"
        materials: list[dict] = []
        try:
            materials = extract_materials(read_repo_text(build_script), build_script)
        except FileNotFoundError:
            gaps.append(
                {
                    "id": item_id,
                    "kind": "missing_build_script",
                    "detail": f"No {build_script} to read Principled BSDF colors from.",
                }
            )
        primary = choose_primary_material(materials, override.get("primary_material"))
        if override.get("primary_material") and (
            primary is None or primary["name"] != override["primary_material"]
        ):
            warnings.append(
                f"{item_id} primary_material {override['primary_material']} was not found in {build_script}"
            )
        if primary is None:
            color = None
            gaps.append(
                {
                    "id": item_id,
                    "kind": "missing_material_color",
                    "detail": "No product Principled BSDF color was parsed from the build script.",
                }
            )
        else:
            color = {
                "name": override.get("color_name") or primary["name"],
                "hex": primary["hex"],
                "material": primary["name"],
                "source": build_script,
            }

        brand_id = override.get("brand_id")
        if brand_id not in brands_by_id:
            gaps.append(
                {
                    "id": item_id,
                    "kind": "missing_brand",
                    "detail": f"enrichment brand_id {brand_id!r} is not in brands.",
                }
            )
        currency = override.get("currency") or "USD"
        slug_value = override.get("slug") or tag(row["Item"])
        featured = override.get("featured_rank", None)
        if featured is not None:
            featured = int(featured)

        items.append(
            {
                "id": item_id,
                "sku": override.get("sku") or f"{item_id}",
                "slug": slug_value,
                "name": row["Item"].strip(),
                "short_description": override.get("short_description")
                or f"{row['Item'].strip()} for the {row['Room'].strip()}.",
                "category": row["Category"].strip(),
                "category_id": slug(row["Category"]),
                "style": row["Style"].strip(),
                "style_id": slug(row["Style"]),
                "room": row["Room"].strip(),
                "room_id": level["id"] if level else None,
                "brand_id": brand_id,
                "price": {
                    "amount": int(as_number(row["Price (USD)"])),
                    "currency": currency,
                },
                "currency": currency,
                "in_stock": bool(override.get("in_stock", True)),
                "ships_in_days": int(override.get("ships_in_days", 7)),
                "sponsored": bool(override.get("sponsored", False)),
                "featured_rank": featured,
                "dimensions": {"inches": inches, "meters": meters},
                "color": color,
                "materials": materials,
                "photo": {
                    "url": row["Photo URL"].strip(),
                    "source_url": row["Photo Source"].strip(),
                    "credit": photo_credit(row["Photo Source"].strip()),
                },
                "images": {
                    "thumbnail": image_ref(located["preview"]),
                    "card": image_ref(located["preview"]),
                    "lifestyle": {
                        "url": row["Photo URL"].strip(),
                        "source_url": row["Photo Source"].strip(),
                        "credit": photo_credit(row["Photo Source"].strip()),
                        "shared_with": [],
                    },
                },
                "model": model,
                "measured_bbox_m": measured,
                "catalog_ref": {
                    "file": "catalog/furniture.json",
                    "id": item_id,
                    "path": folder,
                },
                "tags": tags,
                "source": source_block(located, spreadsheet=True),
            }
        )

    for item_id in catalog_by_id:
        if item_id not in seen:
            gaps.append(
                {
                    "id": item_id,
                    "kind": "missing_spreadsheet_row",
                    "detail": "Present in catalog/furniture.json and absent from the spreadsheet.",
                }
            )

    photos: dict[str, list[str]] = defaultdict(list)
    for item in items:
        photos[item["photo"]["url"]].append(item["id"])
    for item in items:
        siblings = [other for other in photos[item["photo"]["url"]] if other != item["id"]]
        item["images"]["lifestyle"]["shared_with"] = siblings
    data_gaps = [
        {
            "kind": "photo_credit",
            "detail": (
                "The spreadsheet stores a photo URL and an Unsplash source page, "
                "and does not name a photographer. photo.credit is the source site."
            ),
        }
    ]
    for url, ids in photos.items():
        if len(ids) > 1:
            data_gaps.append(
                {
                    "kind": "shared_photo",
                    "url": url,
                    "item_ids": ids,
                    "detail": "These items share one reference photo rather than a unique packshot.",
                }
            )
    data_gaps.extend(gaps)

    def grouped(key_name: str, id_name: str, order: list[str]) -> list[dict]:
        groups: dict[str, dict] = {}
        for item in items:
            group = groups.setdefault(
                item[id_name],
                {
                    "id": item[id_name],
                    "label": item[key_name],
                    "name": item[key_name],
                    "item_ids": [],
                },
            )
            group["item_ids"].append(item["id"])
        for group in groups.values():
            group["item_count"] = len(group["item_ids"])

        def sort_key(group: dict):
            return (order.index(group["id"]) if group["id"] in order else len(order), group["id"])

        return sorted(groups.values(), key=sort_key)

    for room in room_records:
        located = room.pop("_located")
        if not located["available"]:
            data_gaps.append(
                {
                    "id": room["id"],
                    "kind": "missing_room_files",
                    "detail": "Room folder is missing files: " + ", ".join(located["missing"]),
                }
            )
        room["catalog_room"] = next(
            (item["room"] for item in items if item["room_id"] == room["id"]),
            None,
        )
        room["label"] = room["name"]
        room["item_count"] = sum(1 for item in items if item["room_id"] == room["id"])
        room["images"] = {
            "thumbnail": image_ref(room["model"]["preview"]),
            "card": image_ref(room["model"]["preview"]),
        }

    for item_id in item_overrides:
        if item_id not in {item["id"] for item in items}:
            warnings.append(f"enrichment item {item_id} is not in the catalog")

    brand_records = []
    for brand in enrichment["brands"]:
        member_ids = [item["id"] for item in items if item.get("brand_id") == brand["id"]]
        brand_records.append(
            {
                "id": brand["id"],
                "name": brand["name"],
                "ships_from": brand.get("ships_from"),
                "blurb": brand.get("blurb"),
                "item_count": len(member_ids),
                "item_ids": member_ids,
            }
        )

    color_facets: dict[str, dict] = {}
    for item in items:
        if not item.get("color"):
            continue
        facet_key = f"{slug(item['color']['name'])}|{item['color']['hex']}"
        facet = color_facets.setdefault(
            facet_key,
            {
                "id": slug(item["color"]["name"]).replace("_", "-"),
                "label": item["color"]["name"],
                "name": item["color"]["name"],
                "hex": item["color"]["hex"],
                "item_ids": [],
            },
        )
        facet["item_ids"].append(item["id"])
    used_color_ids: set[str] = set()
    colors = []
    for facet in color_facets.values():
        facet["item_count"] = len(facet["item_ids"])
        base_id = facet["id"]
        if base_id in used_color_ids:
            facet["id"] = f"{base_id}-{facet['hex'][1:].lower()}"
        used_color_ids.add(facet["id"])
        colors.append(facet)

    if warnings:
        for warning in warnings:
            data_gaps.append({"kind": "consistency", "detail": warning})

    database = {
        "version": 2,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "demo_data": True,
        "demo_note": (
            "Brands, SKUs, short descriptions, stock, ship times, and sponsored ranks "
            "are fictional demo merchandising from db/source/enrichment.json. "
            "Colors, materials, preview images, prices, and dimensions come from the models and the spreadsheet."
        ),
        "units": {
            "linear": "meters",
            "display_dimensions": "inches",
            "currency": "USD",
            "inch_to_meter": INCH_TO_M,
        },
        "conventions": {
            "axis": catalog.get("axis"),
            "origin": catalog.get("origin"),
            "paths": "Repository-relative POSIX paths with no leading slash.",
            "ids": (
                "Item ids (F001) match the spreadsheet and catalog. "
                "category_id and style_id are lowercase slugs. "
                "room_id matches rooms[].id."
            ),
            "measured_bbox_m": (
                "Copied from metadata.json bounding_box_m and rounded to 4 decimal places (0.1 mm). "
                "min/max are axis-aligned around the floor-center origin."
            ),
            "photos": (
                "images.thumbnail and images.card are the model preview.png. "
                "images.lifestyle is the Unsplash photo. shared_with lists other item ids that use that same photo. "
                "photo is the same lifestyle image, kept for older readers."
            ),
            "colors": (
                "color.hex and materials[].hex are display sRGB. "
                "When build.py passes a color through srgb_to_linear or linear_rgb, the authored number is already sRGB. "
                "When it writes the Principled Base Color socket directly, the socket value is linear and the hex is the sRGB transfer of that value."
            ),
        },
        "sources": {
            "spreadsheet": "db/source/objects.xlsx",
            "sheet": "Furniture Catalog",
            "enrichment": "db/source/enrichment.json",
            "catalog": "catalog/furniture.json",
            "models": "models/<category>/<item_id>_<slug>/",
            "rooms": "rooms/<room_id>/",
        },
        "categories": grouped("category", "category_id", CATEGORY_ORDER),
        "styles": grouped("style", "style_id", STYLE_ORDER),
        "colors": colors,
        "brands": brand_records,
        "rooms": room_records,
        "items": items,
        "data_gaps": data_gaps,
    }
    return database


def validate(database: dict) -> list[str]:
    problems: list[str] = []
    required = [
        "id",
        "sku",
        "slug",
        "name",
        "short_description",
        "category",
        "style",
        "room",
        "brand_id",
        "price",
        "currency",
        "in_stock",
        "ships_in_days",
        "sponsored",
        "featured_rank",
        "dimensions",
        "color",
        "materials",
        "photo",
        "images",
        "model",
        "measured_bbox_m",
        "catalog_ref",
        "tags",
    ]
    item_ids = [item["id"] for item in database["items"]]
    if len(item_ids) != len(set(item_ids)):
        problems.append("duplicate item ids")
    for item in database["items"]:
        missing_keys = [key for key in required if key not in item]
        if missing_keys:
            problems.append(f"{item.get('id')} missing keys {missing_keys}")
        for label in ("glb", "blend", "preview", "metadata", "folder"):
            path = item["model"][label]
            if path.startswith("/") or "\\" in path:
                problems.append(f"{item['id']} path is not repo-relative: {path}")
        if item["model"]["available"]:
            if item["measured_bbox_m"] is None:
                problems.append(f"{item['id']} is available and has no measured bbox")
            branch = item["source"]["branch"]
            ref = f"origin/{branch}" if branch else None
            for label in ("glb", "blend", "preview", "metadata"):
                rel = item["model"][label]
                if ref and rel not in tree_paths(ref):
                    problems.append(f"{item['id']} {rel} missing on {ref}")
                if item["source"]["on_default_branch"] and rel not in tree_paths("origin/main"):
                    problems.append(f"{item['id']} {rel} missing on origin/main")
            size = item["measured_bbox_m"]["size"]
            for key in ("width", "depth", "height"):
                if size[key] <= 0:
                    problems.append(f"{item['id']} bbox size.{key} is {size[key]}")
        if item["price"]["currency"] != "USD" or item["currency"] != "USD":
            problems.append(f"{item['id']} currency is {item['price']['currency']}")
        brand_ids = {brand["id"] for brand in database["brands"]}
        if item["brand_id"] not in brand_ids:
            problems.append(f"{item['id']} brand_id {item['brand_id']} is missing")
        if not item["materials"]:
            problems.append(f"{item['id']} has no materials")
        if not item.get("color") or not re.fullmatch(r"#[0-9A-F]{6}", item["color"]["hex"]):
            problems.append(f"{item['id']} color hex is missing")
        for slot in ("thumbnail", "card"):
            image = item["images"][slot]
            if image["path"] != item["model"]["preview"]:
                problems.append(f"{item['id']} images.{slot} is not the model preview")
            expected = f"{RAW_BASE}/{image['path']}"
            if image["url"] != expected:
                problems.append(f"{item['id']} images.{slot}.url is {image['url']}")
        lifestyle = item["images"]["lifestyle"]
        if lifestyle["url"] != item["photo"]["url"]:
            problems.append(f"{item['id']} lifestyle url drifted from photo.url")
        if item["id"] in lifestyle["shared_with"]:
            problems.append(f"{item['id']} lists itself in shared_with")
        if not isinstance(item["sponsored"], bool):
            problems.append(f"{item['id']} sponsored is not a bool")
        if item["featured_rank"] is not None and not isinstance(item["featured_rank"], int):
            problems.append(f"{item['id']} featured_rank is not an int")
    ranks = {item["id"]: item["featured_rank"] for item in database["items"]}
    if ranks.get("F001") != 1 or not database["items"][item_ids.index("F001")]["sponsored"]:
        problems.append("F001 should be sponsored featured_rank 1")
    if ranks.get("F004") != 2 or not database["items"][item_ids.index("F004")]["sponsored"]:
        problems.append("F004 should be sponsored featured_rank 2")
    for item in database["items"]:
        if item["id"] not in {"F001", "F004"} and (item["sponsored"] or item["featured_rank"] is not None):
            problems.append(f"{item['id']} is sponsored without being F001 or F004")
    if not database.get("demo_data"):
        problems.append("demo_data is not true")
    if not 4 <= len(database["brands"]) <= 7:
        problems.append(f"expected 4-7 brands, found {len(database['brands'])}")
    for facet_name, key in (("styles", "label"), ("categories", "label"), ("colors", "label")):
        for facet in database[facet_name]:
            if "item_count" not in facet or facet["item_count"] != len(facet["item_ids"]):
                problems.append(f"{facet_name} {facet.get('id')} item_count mismatch")
            if key not in facet:
                problems.append(f"{facet_name} {facet.get('id')} missing {key}")
    for room in database["rooms"]:
        if "item_count" not in room or "label" not in room:
            problems.append(f"{room['id']} missing label or item_count")
    for room in database["rooms"]:
        if room["model"]["available"]:
            ref_name = room["source"]["branch"]
            ref = f"origin/{ref_name}" if ref_name else None
            for label in ("glb", "blend", "preview", "metadata"):
                rel = room["model"][label]
                if ref and rel not in tree_paths(ref):
                    problems.append(f"{room['id']} {rel} missing on {ref}")
                if room["source"]["on_default_branch"] and rel not in tree_paths("origin/main"):
                    problems.append(f"{room['id']} {rel} missing on origin/main")
            if not room["anchors"]:
                problems.append(f"{room['id']} has no anchors")
    return problems


def main() -> int:
    database = build()
    problems = validate(database)
    OUT_PATH.write_text(json.dumps(database, indent=2) + "\n", encoding="utf-8")
    # Round-trip the file the frontend will parse.
    json.loads(OUT_PATH.read_text(encoding="utf-8"))

    print(f"wrote {OUT_PATH.relative_to(ROOT)}")
    print(f"items {len(database['items'])}")
    print(f"categories {len(database['categories'])}")
    print(f"styles {len(database['styles'])}")
    print(f"rooms {len(database['rooms'])}")
    open_only = [
        item["id"] for item in database["items"] if item["source"]["only_open_pr"]
    ]
    print(f"only_open_pr {open_only or 'none'}")
    missing = [
        item["id"] for item in database["items"] if not item["model"]["available"]
    ]
    print(f"missing_models {missing or 'none'}")
    for item in database["items"]:
        bbox = item["measured_bbox_m"]
        size = bbox["size"] if bbox else None
        color = item.get("color") or {}
        print(
            f"  {item['id']} {color.get('name')} {color.get('hex')} "
            f"brand={item.get('brand_id')} mats={len(item.get('materials') or [])} "
            f"shared={item['images']['lifestyle']['shared_with']}"
        )
    for gap in database["data_gaps"]:
        print(f"gap {gap['kind']}: {gap.get('id', '')} {gap['detail']}")
    if problems:
        print("VALIDATION FAILED")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print("validation ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
