---
name: fake-db-for-frontend
description: >-
  Regenerate db/db.json for the room-designer frontend from the spreadsheet,
  catalog, and model metadata. Use when changing furniture records, swatches,
  brands, sponsored ranks, or room anchors, including the xlsx parser, sRGB
  hex rule, shared photos, and URL checks.
---

# Rebuild the fake furniture database

`db/db.json` is the document the frontend fetches. `db/build_db.py` rebuilds it. Do not hand-edit `db.json`. Change `db/source/enrichment.json` or a model, then run the script.

This skill describes the merged script (schema version 2, PRs #19 and #20). If `db/db.json` has a `"version"` other than `2`, or if `db/README.md` disagrees with this file, follow the README and the script. An open PR titled `DB: full room data for frontend` (#26) already edits `db/` to add the photo rooms. Do not open a second pull request that touches `db/` while that one is open.

The model and room skills are `blender-furniture-model` and `blender-room-model`. This skill does not build meshes.

## Command

From the repo root:

```bash
python3 db/build_db.py
```

No extra packages. The script uses the stdlib only (`zipfile`, `xml.etree`, `json`, `subprocess`). It calls `git fetch origin` and `gh pr list`. Both need the usual credentials. A failed fetch keeps the refs already on disk. A failed `gh` call leaves pull-request numbers null and still writes the file.

The run that produced the merged file (`generated_at` `2026-11-08T18:34:52Z`) printed this shape:

```text
wrote db/db.json
items 17
categories 6
styles 7
rooms 1
only_open_pr none
missing_models none
  F001 Oatmeal #BFB5A8 brand=cloudline-home mats=5 shared=['F002', 'F011']
  F007 Pale oak #D4AD7D brand=oakline-studio mats=2 shared=['F003', 'F009', 'F010']
  ...
gap photo_credit:  The spreadsheet stores a photo URL and an Unsplash source page, ...
gap shared_photo: F001, F002, F011 These items share one reference photo...
validation ok
```

`rooms 1` is because that run happened before the five photo rooms merged. The script discovers every `rooms/*/metadata.json` on disk and on any fetched origin branch. A later run on current `main` would list six rooms, still at schema version 2, unless PR #26 has replaced the script.

Exit 0 and the line `validation ok` are the success signal. The script writes `db/db.json` before it returns, including when validation fails and the exit code is 1. Do not commit a file whose run did not print `validation ok`.

`only_open_pr none` and `missing_models none` mean every item's `model.glb`, `model.blend`, `preview.png`, and `metadata.json` are on `origin/main`.

## What the script reads

| Input | Role |
| --- | --- |
| `db/source/objects.xlsx`, sheet `Furniture Catalog` | Id, name, category, style, room, price, inches, Unsplash photo |
| `db/source/enrichment.json` | Fictional merchandising that a rebuild must not wipe |
| `catalog/furniture.json` | Folder path and the axis conventions |
| `models/<category>/<id>_<slug>/metadata.json` | Measured bbox and, when present, `triangle_count` |
| `models/.../build.py` | Principled BSDF colors |
| `rooms/<id>/metadata.json` | Interior size, openings, anchors |

Item ids come from the spreadsheet, then any catalog id the sheet missed. Spreadsheet columns:

`Item ID`, `Item`, `Category`, `Style`, `Room`, `Price (USD)`, `Width (in)`, `Depth (in)`, `Height (in)`, `Photo URL`, `Photo Source`.

Meters are `inches * 0.0254`, rounded to 4 decimal places. The script warns when those numbers, the names, or the prices disagree with `catalog/furniture.json`.

## xlsx, without openpyxl

The workbook is a zip of SpreadsheetML. `parse_catalog_sheet` does not import openpyxl, because the VM was not assumed to have it.

- Shared strings live in `xl/sharedStrings.xml`. A string can be split across several `t` nodes inside one `si`. Join all of them. Reading only the first `t` truncates the name or the URL.
- The sheet must be named exactly `Furniture Catalog`. The relationship `Target` in `xl/_rels/workbook.xml.rels` is sometimes `worksheets/sheet1.xml` and sometimes `xl/worksheets/sheet1.xml`. Prefix `xl/` only when it is missing.
- Cell type `s` is an index into the shared strings. `inlineStr` is the text under `is`. Anything else with a `v` node is a raw number, still a string until `as_number`.
- The first row is the header. Later rows join to that header by column number. A row with an empty `Item ID` is skipped.

## Enrichment, facets, and demo flags

`db/source/enrichment.json` is hand-edited. The script merges it on top of the measured data. Edit this file to change brands, SKUs, short descriptions, `in_stock`, `ships_in_days`, sponsored ranks, `color_name`, and `primary_material`. Do not put hex values here. Hex is computed from `build.py`.

`demo_data` is `true`. `demo_note` says brands, SKUs, stock, ship times, and sponsored ranks are fictional. Prices, dimensions, preview paths, and colors are not.

Sponsored rows the validator insists on: F001 is `featured_rank` 1, F004 is `featured_rank` 2, both `sponsored: true`. Every other item is `sponsored: false` and `featured_rank: null`.

Brands on the merged file: Cloudline Home, Harbor House, Lumen Works, Oakline Studio, Loom & Field, Northglass, Verdure. SKUs look like `CLH-F001`.

Facets are `categories`, `styles`, `colors`, `rooms`, and `brands`. Each has `id`, a label, `item_count`, and `item_ids`. `item_count` must equal the length of `item_ids`. Style order is Modern, Coastal, Minimal, Scandinavian, Japandi, Industrial, Bohemian. Category order is Couch, Lamp, Table, Carpet, TV, Plant. Color ids come from the swatch name. Two colors that slug to the same id get the hex appended (`black` versus `black-1d1d1e` did not happen; satin black and the TV black have different names).

`room_id` on an item is the room whose name contains the spreadsheet room label. Every catalog item is `Living Room`, so they all point at `living_room_generic`. The photo rooms are shells, not extra catalog rooms.

## Colors: linear versus sRGB

`color.hex` is display sRGB of the albedo, `#RRGGBB` uppercase.

- If `build.py` passes the tuple through `srgb_to_linear` or `linear_rgb`, the authored number is already sRGB. Oakline's top `(0.83, 0.68, 0.49)` is `#D4AD7D`. Slate authored the same way is `#3A434A`.
- If the script writes the tuple straight into the Principled Base Color socket, the socket value is linear. The hex is the sRGB transfer of that linear value (`lin_to_srgb_channel`: the standard 2.4 curve, with the 0.0031308 cutoff). Cloudline fabric displays as `#BFB5A8`. Satin black displays as `#1D1D1E`.
- A `#RRGGBB` literal in the script is sRGB.
- The snake plant replaces Base Color with vertex colors. The swatch is the mid-leaf green `#427752` (`F015_LeafMid`), which the script special-cases by reading `leaf_color()`.

Naming a helper `srgb_to_linear` in a file that actually stores linear numbers makes the swatch too dark, because the DB will skip the transfer. The checker looks at the helper's body, not at a comment.

`primary_material` in the enrichment file selects which parsed material becomes `color`. The name has to match a material the parser found (`F001_Fabric`, `F007_OakTop`, `SatinBlack`). Materials whose names look like `preview`, `ground`, `wall`, or `floor` are dropped. So are lights named Key, Fill, Rim, and Bounce.

## Images and shared photos

`images.thumbnail` and `images.card` are the model `preview.png`:

```text
path: models/couch/f001_cloudline_3_seat_couch/preview.png
url:  https://raw.githubusercontent.com/wlamason/lovable-hackathon-2026/main/<path>
```

`images.lifestyle` is the Unsplash URL from the sheet, plus `shared_with`, the other item ids that use that same photo. `photo` repeats the lifestyle image for older readers. Product cards must use `images.card`. The lifestyle URL is a room photo, not a packshot.

The sheet does not name a photographer, so `credit` is `Unsplash`. These groups share one photo:

- F001, F002, F011
- F003, F007, F009, F010
- F004, F006
- F005, F008
- F012, F013
- F014, F017
- F015, F016

`shared_with` must not contain the item's own id.

## URL and asset checks

`validate` fails the process when any of these break:

- A required item key is missing, including `color`, `materials`, `images`, `measured_bbox_m`, `brand_id`
- A path is absolute or contains a backslash
- An available item's glb, blend, preview, or metadata is absent from `origin/<branch>` or, when `on_default_branch` is set, from `origin/main`
- A bbox size is not positive
- `color.hex` is not `#` plus six uppercase hex digits
- `images.card.url` or `images.thumbnail.url` is not `https://raw.githubusercontent.com/wlamason/lovable-hackathon-2026/main/` plus the repo-relative path
- The lifestyle URL disagrees with `photo.url`
- F001 / F004 sponsored ranks are wrong, or another item is sponsored
- `demo_data` is not true
- A facet `item_count` disagrees with `item_ids`
- An available room has no anchors, or its files are missing on the branch it was found on

`source.only_open_pr` is true only when the four model files are missing from `origin/main` and the pull request is still `OPEN`. After the merge, re-run the script. Leaving the flag true means the run happened before `git fetch` saw the merge, or the branch name did not match `gh pr list`.

`measured_bbox_m` is normalized to `{min, max, size}` with `min` and `max` as length-3 arrays. The furniture files use either `{x, y, z}` or arrays. Both are accepted. F006, F007, and F009 have no `triangle_count`, so `model.triangle_count` is omitted for them.

Room anchors are copied from `empties`. The position is always copied. `rotation_z_deg` is copied when present. `yaw_deg` alone is ignored. That is why studio anchors need `rotation_z_deg` before a rebuild will publish their yaw.

## Done

- [ ] Read `db/README.md` and the `"version"` field. If they are no longer version 2, follow them instead of this skill
- [ ] No other open PR is already editing `db/`
- [ ] Merchandising changes are in `db/source/enrichment.json`, not typed into `db.json`
- [ ] New model colors are parsed from `build.py`. sRGB inputs go through a function named `srgb_to_linear`
- [ ] `python3 db/build_db.py` from the repo root prints `validation ok` and exits 0
- [ ] `only_open_pr` is `none` and `missing_models` is `none` once the model PRs are on `main`
- [ ] Card image URLs are `https://raw.githubusercontent.com/wlamason/lovable-hackathon-2026/main/` plus a repo-relative `preview.png`
- [ ] Shared Unsplash groups are unchanged unless the spreadsheet changed, and cards still use `images.card`
- [ ] The commit stays inside `db/`
