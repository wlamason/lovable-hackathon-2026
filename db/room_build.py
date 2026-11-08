"""Normalize rooms/*/ into the frontend room records.

Imported by build_db.py. Source geometry, materials, and README prose come from
the room folder. Style tags, starter layouts, and a few blocked rectangles come
from db/source/rooms_enrichment.json and are flagged inferred or demo.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_BASE = "https://raw.githubusercontent.com/wlamason/lovable-hackathon-2026/main"
BLOB_BASE = "https://github.com/wlamason/lovable-hackathon-2026/blob/main"
METERS_PER_FOOT = 0.3048

ROOM_TYPE_LABELS = {
    "living": "Living room",
    "open-plan-kitchen": "Open-plan kitchen",
    "loft": "Loft",
    "studio": "Studio",
    "garden": "Garden room",
}
SIZE_LABELS = {"small": "Small", "medium": "Medium", "large": "Large"}
LIGHT_LABELS = {"bright": "Bright", "medium": "Medium", "soft": "Soft"}
STYLE_LABELS = {
    "modern": "Modern",
    "coastal": "Coastal",
    "minimal": "Minimal",
    "scandinavian": "Scandinavian",
    "japandi": "Japandi",
    "industrial": "Industrial",
    "bohemian": "Bohemian",
}

# Anchor name -> catalog categories, optional id allow-list, note.
ANCHOR_SUGGESTIONS = {
    "Sofa_spot": {"categories": ["Couch"], "note": "Sofas whose footprint fits the free floor."},
    "TV_wall": {"categories": ["TV"], "note": "Screens. Raise Z off the floor anchor to wall-mount."},
    "Rug_center": {"categories": ["Carpet"], "note": "Rugs whose width and depth fit the free floor."},
    "Coffee_spot": {"categories": ["Table"], "ids": ["F007", "F008"], "note": "Coffee and nesting tables."},
    "Plant_corner": {"categories": ["Plant"], "note": "Floor plants."},
    "Lamp_corner": {"categories": ["Lamp"], "ids": ["F004", "F006"], "note": "Floor lamps, not the table lamp."},
    "Side_table": {"categories": ["Table", "Lamp"], "ids": ["F009", "F008", "F005"], "note": "Side table or the table lamp."},
    "Bar_spot": {"categories": [], "ids": [], "note": "The catalog has no bar stool. Leave this anchor empty."},
    "Alcove_spot": {
        "categories": ["Lamp", "Plant", "Table"],
        "ids": ["F005", "F015", "F009"],
        "note": "A small lamp, plant, or side table for the alcove.",
    },
}

FEATURE_LABELS = {
    "window": "Window",
    "door": "Door",
    "sliding_door": "Sliding door",
    "french_door": "French doors",
    "closet": "Closet",
    "pass_through": "Kitchen pass-through",
    "fireplace": "Fireplace",
    "beam": "Exposed beams",
    "kitchen": "Kitchen",
    "peninsula": "Peninsula",
    "alcove": "Alcove",
    "radiator": "Radiator",
    "pendant": "Pendants",
    "tray_ceiling": "Tray ceiling",
    "soffit": "Soffit",
    "bench": "Window bench",
}


def r4(value: float) -> float:
    rounded = round(float(value), 4)
    return 0.0 if rounded == 0 else rounded


def lin_to_srgb_channel(value: float) -> float:
    value = max(0.0, min(1.0, float(value)))
    if value <= 0.0031308:
        return 12.92 * value
    return 1.055 * (value ** (1.0 / 2.4)) - 0.055


def rgb_hex(rgb) -> str:
    shown = tuple(lin_to_srgb_channel(channel) for channel in rgb)
    channels = [max(0, min(255, int(round(channel * 255)))) for channel in shown]
    return "#" + "".join(f"{channel:02X}" for channel in channels)


def file_ref(rel: str) -> dict:
    path = ROOT / rel
    exists = path.is_file()
    return {
        "path": rel,
        "raw_url": f"{RAW_BASE}/{rel}",
        "blob_url": f"{BLOB_BASE}/{rel}",
        "bytes": path.stat().st_size if exists else None,
        "exists": exists,
    }


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


def _as_float(token: str | None) -> float | None:
    if token is None:
        return None
    try:
        return float(token.strip().rstrip(","))
    except ValueError:
        return None


def _parse_rgb(token: str):
    match = re.fullmatch(r"\(([^)]+)\)", re.sub(r"\s+", " ", token.strip()))
    if not match:
        return None
    numbers = []
    for part in match.group(1).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            numbers.append(float(part))
        except ValueError:
            return None
    if len(numbers) < 3:
        return None
    return tuple(numbers[:3])


def _iter_make_material(text: str):
    token = "make_material("
    start = 0
    while True:
        index = text.find(token, start)
        if index < 0:
            return
        if text[max(0, index - 4) : index] == "def ":
            start = index + len(token)
            continue
        depth = 0
        for cursor in range(index + len("make_material"), len(text)):
            char = text[cursor]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    yield text[index + len(token) : cursor]
                    start = cursor + 1
                    break
        else:
            return


def material_role(name: str) -> str:
    lowered = name.lower()
    if lowered.startswith("floor") or "floor_" in lowered:
        return "floor"
    if "ceiling" in lowered:
        return "ceiling"
    if lowered.startswith("wall") or lowered.startswith("adjacent_wall"):
        return "wall"
    if "glass" in lowered:
        return "glass"
    if any(
        token in lowered
        for token in ("beam", "hearth", "tile", "walnut", "quartz", "granite", "cabinet", "brass", "wood", "baseboard")
    ):
        return "accent"
    return "finish"


def extract_room_materials(text: str, source: str) -> list[dict]:
    found = []
    seen = set()
    for blob in _iter_make_material(text):
        positionals, keywords = _keyword_map(_split_args(blob))
        if len(positionals) < 2:
            continue
        name_match = re.fullmatch(r"['\"]([^'\"]+)['\"]", positionals[0].strip())
        if not name_match or name_match.group(1) in seen:
            continue
        rgb = _parse_rgb(positionals[1])
        if rgb is None or any(channel < -0.001 or channel > 1.001 for channel in rgb):
            continue
        seen.add(name_match.group(1))
        roughness = _as_float(keywords.get("roughness"))
        if roughness is None and len(positionals) >= 3:
            roughness = _as_float(positionals[2])
        metallic = _as_float(keywords.get("metallic")) or 0.0
        alpha = _as_float(keywords.get("alpha"))
        transmission = _as_float(keywords.get("transmission")) or 0.0
        emission = _as_float(keywords.get("emission")) or 0.0
        record = {
            "name": name_match.group(1),
            "role": material_role(name_match.group(1)),
            "hex": rgb_hex(rgb),
            "base_color_rgb": [r4(channel) for channel in rgb],
            "color_space": "linear",
            "roughness": None if roughness is None else r4(roughness),
            "metallic": r4(metallic),
            "source": source,
        }
        if alpha is not None:
            record["alpha"] = r4(alpha)
        if transmission:
            record["transmission"] = r4(transmission)
        if emission:
            record["emission_strength"] = r4(emission)
        found.append(record)
    return found


def palette_from(materials: list[dict]) -> dict:
    def first(role: str):
        for material in materials:
            if material["role"] == role:
                return {
                    "name": material["name"],
                    "hex": material["hex"],
                    "material": material["name"],
                }
        return None

    accents = [
        {"name": material["name"], "hex": material["hex"], "role": material["role"]}
        for material in materials
        if material["role"] in {"accent", "glass"}
    ]
    return {
        "floor": first("floor"),
        "wall": first("wall"),
        "ceiling": first("ceiling"),
        "accents": accents,
    }


def preview_hides(text: str) -> list[str]:
    start = text.find("def render_preview")
    if start < 0:
        return []
    nxt = text.find("\ndef ", start + 1)
    body = text[start:nxt if nxt > 0 else None]
    match = re.search(r"for name in \((.*?)\):", body, re.S)
    if not match:
        return []
    return re.findall(r"['\"]([^'\"]+)['\"]", match.group(1))


def preview_pixels(text: str) -> dict | None:
    start = text.find("def render_preview")
    if start < 0:
        return None
    nxt = text.find("\ndef ", start + 1)
    body = text[start:nxt if nxt > 0 else None]
    width = re.search(r"resolution_x\s*=\s*(\d+)", body)
    height = re.search(r"resolution_y\s*=\s*(\d+)", body)
    if not width or not height:
        return None
    return {"width": int(width.group(1)), "height": int(height.group(1))}


def readme_prose(text: str) -> str:
    lines = []
    fence = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        if stripped.startswith("![") or stripped.startswith("## Rebuild") or stripped == "Rebuild from this folder:":
            continue
        if stripped.startswith("Rebuild from this folder"):
            break
        lines.append(line)
    prose = "\n".join(lines).strip()
    prose = re.sub(r"^# .+\n+", "", prose).strip()
    return prose


def first_sentence(text: str) -> str:
    flat = re.sub(r"\s+", " ", text).strip()
    match = re.match(r"(.+?\.)(?:\s|$)", flat)
    return match.group(1) if match else flat


def inspired_sentences(text: str) -> list[str]:
    flat = re.sub(r"\s+", " ", text)
    return [chunk.strip() for chunk in re.findall(r"Inspired by[^.]*\.", flat)]


def shoelace(points: list[list[float]]) -> float:
    if len(points) < 3:
        return 0.0
    area = 0.0
    for index, (x_pos, y_pos) in enumerate(points):
        x_next, y_next = points[(index + 1) % len(points)]
        area += x_pos * y_next - x_next * y_pos
    return abs(area) / 2.0


def rect_from_points(points: list[list[float]]) -> dict:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return {
        "min": [r4(min(xs)), r4(min(ys))],
        "max": [r4(max(xs)), r4(max(ys))],
        "width_m": r4(max(xs) - min(xs)),
        "depth_m": r4(max(ys) - min(ys)),
    }


def _pair(value) -> list[float] | None:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return [float(value[0]), float(value[1])]
    return None


def normalize_free_floor(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    polygon = raw.get("polygon_xy_m") or raw.get("polygon_m")
    rect = None
    if isinstance(raw.get("rect_m"), dict):
        rect_raw = raw["rect_m"]
        min_xy = _pair(rect_raw.get("min_xy") or rect_raw.get("min"))
        max_xy = _pair(rect_raw.get("max_xy") or rect_raw.get("max"))
        if min_xy and max_xy:
            rect = rect_from_points([min_xy, max_xy])
    if _pair(raw.get("min_m")) and _pair(raw.get("max_m")):
        rect = rect_from_points([_pair(raw["min_m"]), _pair(raw["max_m"])])
    if {"x_min", "x_max", "y_min", "y_max"} <= set(raw):
        rect = rect_from_points(
            [[raw["x_min"], raw["y_min"]], [raw["x_max"], raw["y_max"]]]
        )
    seating = None
    if isinstance(raw.get("seating_rect_m"), dict):
        seat = raw["seating_rect_m"]
        if _pair(seat.get("min")) and _pair(seat.get("max")):
            seating = rect_from_points([_pair(seat["min"]), _pair(seat["max"])])
    points = None
    if isinstance(polygon, list) and polygon and isinstance(polygon[0], list):
        points = [[r4(point[0]), r4(point[1])] for point in polygon if len(point) >= 2]
    if points is None and rect:
        min_xy, max_xy = rect["min"], rect["max"]
        points = [
            [min_xy[0], min_xy[1]],
            [max_xy[0], min_xy[1]],
            [max_xy[0], max_xy[1]],
            [min_xy[0], max_xy[1]],
        ]
    area = shoelace(points) if points else 0.0
    return {
        "rect_m": rect,
        "seating_rect_m": seating,
        "polygon_xy_m": points,
        "bounds_m": rect_from_points(points) if points else rect,
        "area_m2": r4(area),
        "area_ft2": r4(area / (METERS_PER_FOOT ** 2)),
        "note": raw.get("note") or raw.get("description"),
        "source": "metadata.free_floor",
    }


def blocked_from_metadata(meta: dict) -> list[dict]:
    blocked = []
    free = meta.get("free_floor") if isinstance(meta.get("free_floor"), dict) else {}
    for entry in free.get("excluded") or []:
        polygon = entry.get("polygon_m") or entry.get("polygon_xy_m")
        points = [[r4(point[0]), r4(point[1])] for point in polygon] if polygon else None
        blocked.append(
            {
                "id": entry.get("name") or "excluded",
                "label": entry.get("name") or "Excluded floor",
                "reason": entry.get("reason"),
                "polygon_xy_m": points,
                "height_m": entry.get("height_m"),
                "inferred": False,
                "source": "metadata.free_floor.excluded",
            }
        )
    hearth = meta.get("fireplace") if isinstance(meta.get("fireplace"), dict) else None
    if hearth and hearth.get("hearth_polygon_m"):
        already = any(item["id"] == "hearth" for item in blocked)
        if not already:
            points = [[r4(point[0]), r4(point[1])] for point in hearth["hearth_polygon_m"]]
            blocked.append(
                {
                    "id": "hearth",
                    "label": "Fireplace hearth",
                    "reason": "Raised hearth polygon from metadata.fireplace.",
                    "polygon_xy_m": points,
                    "height_m": hearth.get("hearth_height_m"),
                    "inferred": False,
                    "source": "metadata.fireplace.hearth_polygon_m",
                }
            )
    return blocked


def _size_of(entry: dict) -> dict:
    width = entry.get("width_m")
    height = entry.get("height_m")
    size = {"width_m": width, "height_m": height, "depth_m": None}
    if isinstance(entry.get("size_m"), list) and len(entry["size_m"]) >= 3:
        size = {
            "width_m": r4(entry["size_m"][0]),
            "depth_m": r4(entry["size_m"][1]),
            "height_m": r4(entry["size_m"][2]),
        }
    return {key: (None if value is None else r4(value) if isinstance(value, float) else value) for key, value in size.items()}


def feature_type(key: str, entry: dict) -> str:
    kind = f"{key} {entry.get('kind') or ''}".lower()
    if "french" in kind:
        return "french_door"
    if "sliding" in kind or "balcony" in kind:
        return "sliding_door"
    if "closet" in kind:
        return "closet"
    if "pass" in kind:
        return "pass_through"
    if "window" in kind:
        return "window"
    if "door" in kind:
        return "door"
    return kind.replace(" ", "_")


def iter_openings(openings):
    if isinstance(openings, list):
        for entry in openings:
            if isinstance(entry, dict):
                yield entry.get("name") or entry.get("kind") or "opening", entry
        return
    if not isinstance(openings, dict):
        return
    for key, entry in openings.items():
        if isinstance(entry, list):
            for index, item in enumerate(entry, start=1):
                if isinstance(item, dict):
                    suffix = f"_{index}" if len(entry) > 1 else ""
                    yield f"{key}{suffix}", item
        elif isinstance(entry, dict):
            yield key, entry


def features_from(meta: dict) -> list[dict]:
    features = []
    seen = set()

    def add(feature_id: str, feature_type_id: str, **extra):
        if feature_id in seen:
            return
        seen.add(feature_id)
        record = {
            "id": feature_id,
            "type": feature_type_id,
            "label": extra.pop("label", FEATURE_LABELS.get(feature_type_id, feature_type_id.replace("_", " ").title())),
            "wall": extra.pop("wall", None),
            "position_m": extra.pop("position_m", None),
            "size_m": extra.pop("size_m", None),
            "source": extra.pop("source", "metadata"),
        }
        record.update(extra)
        features.append(record)

    for key, entry in iter_openings(meta.get("openings")):
        kind = feature_type(str(key), entry)
        position = entry.get("position_m") or entry.get("center_m")
        add(
            str(key),
            kind,
            wall=entry.get("wall"),
            position_m=[r4(value) for value in position] if isinstance(position, list) else None,
            size_m=_size_of(entry),
            object=entry.get("object"),
            note=entry.get("note"),
            sill_z_m=entry.get("sill_z_m"),
            source="metadata.openings",
        )
    if isinstance(meta.get("fireplace"), dict):
        hearth = meta["fireplace"]
        add(
            "fireplace",
            "fireplace",
            wall=hearth.get("corner"),
            note=hearth.get("face"),
            size_m={"surround_top_z_m": hearth.get("surround_top_z_m"), "hearth_height_m": hearth.get("hearth_height_m")},
            source="metadata.fireplace",
        )
    beams = meta.get("beams") or []
    if beams:
        add(
            "beams",
            "beam",
            label=f"{len(beams)} exposed beams",
            members=beams,
            source="metadata.beams",
        )
    objects = [str(name) for name in meta.get("objects") or []]
    description = str(meta.get("description") or "").lower()
    if any(name.lower().startswith("kitchen") for name in objects):
        add("kitchen", "kitchen", source="metadata.objects")
    if "peninsula" in description:
        add("peninsula", "peninsula", source="metadata.description")
    if meta.get("jog") or "Alcove_spot" in (meta.get("empties") or {}):
        add("alcove", "alcove", note=(meta.get("jog") or {}).get("note"), source="metadata.jog")
    if any(name.lower() == "radiator" for name in objects):
        add("radiator", "radiator", wall="Wall_N", source="metadata.objects")
    if any("pendant" in name.lower() for name in objects):
        add("pendants", "pendant", source="metadata.objects")
    if meta.get("soffit_bottom_m") is not None or any(name == "Ceiling_Soffit" for name in objects):
        kind = "tray_ceiling" if "tray" in description else "soffit"
        add(
            kind,
            kind,
            label="Tray ceiling" if kind == "tray_ceiling" else "Soffit",
            size_m={"soffit_bottom_m": meta.get("soffit_bottom_m")},
            source="metadata",
        )
    if any(name == "Bench" for name in objects):
        add("bench", "bench", wall="Window_N", source="metadata.objects")
    if any(name.lower().startswith("closet") for name in objects):
        add("closet", "closet", source="metadata.objects")
    return features


def walls_from(meta: dict, features: list[dict], hidden: list[str]) -> list[dict]:
    raw = meta.get("walls") or {}
    if not isinstance(raw, dict):
        return []
    walls = []
    for wall_id, label in raw.items():
        cardinal = wall_id.rsplit("_", 1)[-1] if "_" in wall_id else None
        if cardinal not in {"N", "E", "S", "W"}:
            cardinal = None
        opening_types = {"window", "door", "sliding_door", "french_door", "closet", "pass_through"}
        openings = [
            feature["id"]
            for feature in features
            if feature.get("wall") == wall_id and feature["type"] in opening_types
        ]
        walls.append(
            {
                "id": wall_id,
                "cardinal": cardinal,
                "label": label,
                "openings": openings,
                "hidden_in_preview": wall_id in hidden,
            }
        )
    return walls


def size_class(area_m2: float) -> str:
    # Furnishing area: free floor when the metadata has one, otherwise the interior.
    if area_m2 < 24:
        return "small"
    if area_m2 < 30:
        return "medium"
    return "large"


def dimensions_block(meta: dict) -> dict:
    interior = meta.get("interior_m") or {}
    feet = meta.get("interior_ft") or {}
    width_m = float(interior.get("width_x") or 0)
    depth_m = float(interior.get("depth_y") or 0)
    height_m = float(interior.get("height_z") or meta.get("ceiling_height_m") or 0)
    width_ft = float(feet.get("width_x") or (width_m / METERS_PER_FOOT))
    depth_ft = float(feet.get("depth_y") or (depth_m / METERS_PER_FOOT))
    height_ft = float(feet.get("height_z") or feet.get("ceiling") or (height_m / METERS_PER_FOOT))
    return {
        "meters": {"width": r4(width_m), "depth": r4(depth_m), "height": r4(height_m)},
        "feet": {"width": r4(width_ft), "depth": r4(depth_ft), "height": r4(height_ft)},
        "inches": {
            "width": r4(width_ft * 12),
            "depth": r4(depth_ft * 12),
            "height": r4(height_ft * 12),
        },
    }


def bounds_block(raw) -> dict | None:
    if not isinstance(raw, dict) or "min" not in raw or "max" not in raw:
        return None
    minimum = [r4(value) for value in raw["min"]]
    maximum = [r4(value) for value in raw["max"]]
    if isinstance(raw.get("size"), list) and len(raw["size"]) >= 3:
        size = [r4(value) for value in raw["size"][:3]]
    else:
        size = [r4(maximum[index] - minimum[index]) for index in range(3)]
    return {"min": minimum, "max": maximum, "size": size}


def shell_room(meta: dict, folder: str, located: dict, build_text: str, readme: str, extra: dict) -> dict:
    room_id = meta.get("id") or Path(folder).name
    name = meta.get("name") or room_id
    prose = readme_prose(readme) if readme else (meta.get("description") or "")
    long_description = extra.get("long_description") or prose or meta.get("description") or ""
    short_description = extra.get("short_description") or meta.get("description") or first_sentence(long_description)
    description_from_enrichment = bool(extra.get("short_description") or extra.get("long_description"))
    dims = dimensions_block(meta)
    area_m2 = r4(dims["meters"]["width"] * dims["meters"]["depth"])
    free = normalize_free_floor(meta.get("free_floor"))
    materials = extract_room_materials(build_text, f"{folder}/build.py")
    hidden = preview_hides(build_text)
    features = features_from(meta)
    files = {
        "glb": file_ref(located["glb"]),
        "blend": file_ref(located["blend"]),
        "build_py": file_ref(f"{folder}/build.py"),
        "readme": file_ref(f"{folder}/README.md"),
        "metadata": file_ref(located["metadata"]),
        "preview": file_ref(located["preview"]),
    }
    inspiration = []
    for sentence in inspired_sentences(readme or ""):
        inspiration.append(
            {
                "description": sentence,
                "url": None,
                "known": False,
                "inferred": False,
                "source": "readme",
            }
        )
    for entry in extra.get("inspiration") or []:
        inspiration.append(
            {
                "description": entry.get("description"),
                "url": entry.get("url"),
                "known": bool(entry.get("known", False)),
                "inferred": bool(entry.get("inferred", True)),
                "source": "rooms_enrichment",
            }
        )
    style_ids = list(extra.get("style_ids") or [])
    room_type = extra.get("room_type") or "living"
    light = extra.get("light_level") or "medium"
    size = size_class(free["area_m2"] if free and free["area_m2"] else area_m2)
    objects = [str(item) for item in meta.get("objects") or []]
    has_kitchen = any(item.lower().startswith("kitchen") for item in objects)
    has_fireplace = "fireplace" in meta or any("fireplace" in item.lower() for item in objects)
    has_outdoor = any(feature["type"] in {"window", "sliding_door", "french_door"} for feature in features)
    preview = located["preview"]
    pixels = preview_pixels(build_text)
    return {
        "id": room_id,
        "slug": room_id.replace("_", "-"),
        "name": name,
        "display_name": extra.get("display_name") or name,
        "label": extra.get("display_name") or name,
        "short_description": short_description,
        "long_description": long_description,
        "description_source": {
            "short": "rooms_enrichment" if extra.get("short_description") else "readme_or_metadata",
            "long": "rooms_enrichment" if extra.get("long_description") else "readme",
            "demo": description_from_enrichment,
        },
        "sort_order": int(extra.get("sort_order") or 0),
        "catalog_room": extra.get("catalog_room"),
        "dimensions": dims,
        "floor_area": {
            "m2": area_m2,
            "ft2": r4(area_m2 / (METERS_PER_FOOT ** 2)),
            "basis": "interior width x depth",
        },
        "interior_m": {
            "width_x": dims["meters"]["width"],
            "depth_y": dims["meters"]["depth"],
            "height_z": dims["meters"]["height"],
        },
        "wall_thickness_m": None if meta.get("wall_thickness_m") is None else r4(meta["wall_thickness_m"]),
        "shell_bounds_m": bounds_block(meta.get("shell_bbox_m") or meta.get("bbox_m")),
        "bounds_m": bounds_block(meta.get("bbox_m")),
        "bbox_m": bounds_block(meta.get("bbox_m")),
        "conventions": {
            "units": meta.get("units") or "meters",
            "up_axis": meta.get("up_axis") or "Z",
            "origin": meta.get("origin"),
            "furniture_front": "-Y",
            "yaw_axis": "Z",
            "yaw_units": "degrees",
            "yaw_meaning": (
                "Right-handed rotation about Z applied to a model whose front is local -Y. "
                "Positive yaw turns the model from +X toward +Y. "
                "180 degrees turns the front from -Y to +Y."
            ),
            "meters_per_foot": METERS_PER_FOOT,
        },
        "origin": meta.get("origin"),
        "up_axis": meta.get("up_axis") or "Z",
        "model": {
            "glb": located["glb"],
            "blend": located["blend"],
            "preview": located["preview"],
            "metadata": located["metadata"],
            "build_py": f"{folder}/build.py",
            "readme": f"{folder}/README.md",
            "folder": folder,
            "available": located["available"] and all(record["exists"] for record in files.values()),
        },
        "files": files,
        "triangle_count": meta.get("triangle_count"),
        "images": {
            "thumbnail": image_ref(preview),
            "card": image_ref(preview),
            "hero": image_ref(preview),
            "preview_px": pixels,
            "inspiration": inspiration,
        },
        "preview_hides": hidden,
        "anchors": [],
        "free_floor": free,
        "blocked": blocked_from_metadata(meta),
        "features": features,
        "walls": walls_from(meta, features, hidden),
        "openings": meta.get("openings"),
        "materials": materials,
        "palette": palette_from(materials),
        "tags": {
            "room_type": {
                "id": room_type,
                "label": ROOM_TYPE_LABELS.get(room_type, room_type),
                "inferred": True,
                "source": "rooms_enrichment",
            },
            "style_ids": style_ids,
            "styles": [
                {"id": style_id, "label": STYLE_LABELS.get(style_id, style_id), "inferred": True}
                for style_id in style_ids
            ],
            "vibe": list(extra.get("vibe") or []),
            "light_level": {
                "id": light,
                "label": LIGHT_LABELS.get(light, light),
                "inferred": True,
                "source": "rooms_enrichment",
            },
            "size_class": {
                "id": size,
                "label": SIZE_LABELS[size],
                "inferred": False,
                "source": "free_floor area, else interior floor area",
                "thresholds_m2": {"small": "< 24", "medium": "24 to 30", "large": ">= 30"},
            },
            "has_kitchen": has_kitchen,
            "has_fireplace": has_fireplace,
            "has_outdoor_view": has_outdoor,
            "has_beams": bool(meta.get("beams")),
        },
        "readme_markdown": readme or "",
        "source_metadata": meta,
        "_extra": extra,
        "_located": located,
    }


def _anchor_yaw(info: dict):
    if "rotation_z_deg" in info:
        return info["rotation_z_deg"]
    if "yaw_deg" in info:
        return info["yaw_deg"]
    return 0


def attach_anchors_and_fit(room: dict, items: list[dict]) -> None:
    meta = room.pop("source_metadata")
    # Keep the metadata on the record. pop only to read empties, then put it back.
    room["source_metadata"] = meta
    extra = room.pop("_extra")
    suggestions_extra = extra.get("anchor_notes") or {}
    anchors = []
    ceiling = room["dimensions"]["meters"]["height"] or 0
    free = room.get("free_floor") or {}
    span = free.get("rect_m") or free.get("bounds_m") or {}
    span_w = span.get("width_m") or room["dimensions"]["meters"]["width"]
    span_d = span.get("depth_m") or room["dimensions"]["meters"]["depth"]
    free_area = free.get("area_m2") or room["floor_area"]["m2"]
    fit_rows = []
    fitting_ids = set()
    for item in items:
        meters = item["dimensions"]["meters"]
        footprint = r4(float(meters["width"]) * float(meters["depth"]))
        sides = sorted((float(meters["width"]), float(meters["depth"])))
        spans = sorted((span_w, span_d))
        fits_span = sides[0] <= spans[0] + 0.02 and sides[1] <= spans[1] + 0.02
        fits_area = footprint <= free_area + 0.001
        fits_height = float(meters["height"]) <= ceiling + 0.02
        fits = bool(fits_span and fits_area and fits_height)
        if fits:
            fitting_ids.add(item["id"])
        fit_rows.append(
            {
                "id": item["id"],
                "name": item["name"],
                "category": item["category"],
                "footprint_m": {"width": meters["width"], "depth": meters["depth"], "height": meters["height"]},
                "footprint_m2": footprint,
                "free_area_m2": free_area,
                "fits_area": fits_area,
                "fits_span": fits_span,
                "fits_height": fits_height,
                "fits": fits,
            }
        )
    for anchor_id, info in (meta.get("empties") or {}).items():
        yaw = float(_anchor_yaw(info))
        suggestion = ANCHOR_SUGGESTIONS.get(anchor_id, {"categories": [], "note": info.get("note")})
        allowed = suggestion.get("ids")
        categories = list(suggestion.get("categories") or [])
        compatible = []
        for item in items:
            if categories and item["category"] not in categories:
                continue
            if allowed is not None and item["id"] not in allowed:
                continue
            if item["id"] not in fitting_ids and anchor_id != "TV_wall":
                continue
            if anchor_id == "TV_wall" and item["category"] != "TV":
                continue
            compatible.append(item["id"])
        note = suggestions_extra.get(anchor_id) or suggestion.get("note") or info.get("note")
        anchors.append(
            {
                "id": anchor_id,
                "name": anchor_id,
                "position_m": [r4(value) for value in info["position_m"]],
                "yaw_deg": r4(yaw),
                "yaw_rad": round(math.radians(yaw), 6),
                "rotation_z_deg": r4(yaw),
                "description": info.get("note"),
                "intended_use": note,
                "suggested_categories": categories,
                "compatible_item_ids": compatible,
            }
        )
    blocked = list(room.get("blocked") or [])
    for entry in extra.get("blocked") or []:
        points = [[r4(point[0]), r4(point[1])] for point in entry.get("polygon_xy_m") or []]
        blocked.append(
            {
                "id": entry.get("id"),
                "label": entry.get("label"),
                "reason": entry.get("reason"),
                "polygon_xy_m": points,
                "height_m": entry.get("height_m"),
                "inferred": bool(entry.get("inferred", True)),
                "source": "rooms_enrichment",
            }
        )
    placements = []
    for anchor_id, item_id in (extra.get("starter_layout") or {}).items():
        fit = next((row for row in fit_rows if row["id"] == item_id), None)
        placements.append(
            {
                "anchor_id": anchor_id,
                "item_id": item_id,
                "fits": bool(fit and fit["fits"]),
            }
        )
    room["anchors"] = anchors
    room["blocked"] = blocked
    room["fit"] = {
        "free_area_m2": free_area,
        "span_m": {"width": span_w, "depth": span_d},
        "items": fit_rows,
        "starter_layout": {
            "demo": True,
            "inferred": True,
            "source": "rooms_enrichment",
            "note": "Demo arrangement for the frontend. Not stored on the room file.",
            "placements": placements,
        },
    }


def load_room_enrichment(path: Path) -> dict:
    if not path.is_file():
        return {"rooms": {}}
    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("rooms", {})
    return data


def room_facets(rooms: list[dict]) -> dict:
    def bucket(records: dict, facet_id: str, label: str, room_id: str):
        facet = records.setdefault(
            facet_id,
            {"id": facet_id, "label": label, "item_count": 0, "room_ids": []},
        )
        facet["room_ids"].append(room_id)

    types: dict[str, dict] = {}
    sizes: dict[str, dict] = {}
    features: dict[str, dict] = {}
    styles: dict[str, dict] = {}
    for room in rooms:
        tags = room["tags"]
        bucket(types, tags["room_type"]["id"], tags["room_type"]["label"], room["id"])
        bucket(sizes, tags["size_class"]["id"], tags["size_class"]["label"], room["id"])
        for style in tags["styles"]:
            bucket(styles, style["id"], style["label"], room["id"])
        seen_types = set()
        for feature in room["features"]:
            if feature["type"] in seen_types:
                continue
            seen_types.add(feature["type"])
            bucket(features, feature["type"], FEATURE_LABELS.get(feature["type"], feature["label"]), room["id"])
    for group in (types, sizes, features, styles):
        for facet in group.values():
            facet["item_count"] = len(facet["room_ids"])
    size_order = ["small", "medium", "large"]
    return {
        "room_types": list(types.values()),
        "size_classes": sorted(sizes.values(), key=lambda facet: size_order.index(facet["id"]) if facet["id"] in size_order else 9),
        "room_features": list(features.values()),
        "room_styles": [styles[style_id] for style_id in STYLE_LABELS if style_id in styles],
    }
