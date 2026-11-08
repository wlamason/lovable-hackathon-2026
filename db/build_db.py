#!/usr/bin/env python3
"""Rebuild db/db.json from the furniture spreadsheet, catalog, and model metadata.

Reads db/source/objects.xlsx (sheet "Furniture Catalog"), catalog/furniture.json,
each item's metadata.json, and rooms/*/metadata.json. Model files are resolved
against git refs (origin/main and the model branches) so a path that exists only
on an open pull request is still recorded and flagged.

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
OUT_PATH = DB_DIR / "db.json"

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
    found: set[str] = set()
    root = ROOT / prefix
    if root.is_dir():
        for path in root.glob("*/metadata.json"):
            found.add(path.relative_to(ROOT).as_posix())
    for ref in git_refs():
        for rel in tree_paths(ref):
            if rel.startswith(f"{prefix}/") and rel.endswith("/metadata.json"):
                parts = rel.split("/")
                if len(parts) == 3:
                    found.add(rel)
    return sorted(found)


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

    pulls = load_pull_requests()
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

        items.append(
            {
                "id": item_id,
                "name": row["Item"].strip(),
                "category": row["Category"].strip(),
                "category_id": slug(row["Category"]),
                "style": row["Style"].strip(),
                "style_id": slug(row["Style"]),
                "room": row["Room"].strip(),
                "room_id": level["id"] if level else None,
                "price": {
                    "amount": int(as_number(row["Price (USD)"])),
                    "currency": "USD",
                },
                "dimensions": {"inches": inches, "meters": meters},
                "photo": {
                    "url": row["Photo URL"].strip(),
                    "source_url": row["Photo Source"].strip(),
                    "credit": photo_credit(row["Photo Source"].strip()),
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

    def grouped(key_name: str, id_name: str) -> list[dict]:
        groups: dict[str, dict] = {}
        for item in items:
            group = groups.setdefault(
                item[id_name],
                {"id": item[id_name], "name": item[key_name], "item_ids": []},
            )
            group["item_ids"].append(item["id"])
        return list(groups.values())

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

    database = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
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
                "photo.url is the display image. photo.source_url is the upstream page. "
                "photo.credit is the source site when the spreadsheet has no photographer."
            ),
        },
        "sources": {
            "spreadsheet": "db/source/objects.xlsx",
            "sheet": "Furniture Catalog",
            "catalog": "catalog/furniture.json",
            "models": "models/<category>/<item_id>_<slug>/",
            "rooms": "rooms/<room_id>/",
        },
        "categories": grouped("category", "category_id"),
        "styles": grouped("style", "style_id"),
        "rooms": room_records,
        "items": items,
        "data_gaps": data_gaps,
    }
    return database


def validate(database: dict) -> list[str]:
    problems: list[str] = []
    required = [
        "id",
        "name",
        "category",
        "style",
        "room",
        "price",
        "dimensions",
        "photo",
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
        if item["price"]["currency"] != "USD":
            problems.append(f"{item['id']} currency is {item['price']['currency']}")
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
        print(
            f"  {item['id']} pr={item['source']['pull_request']} "
            f"branch={item['source']['branch']} "
            f"on_main={item['source']['on_default_branch']} "
            f"bbox={size} folder={item['model']['folder']}"
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
