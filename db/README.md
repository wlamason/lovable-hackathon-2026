# Furniture database

`db/db.json` is the document the room designer loads. Version 3 adds a full record for every room shell. Item fields from version 2 are unchanged.

Regenerate it from the repo root:

```bash
python3 db/build_db.py
```

The script fetches `origin`, then reads:

- `db/source/objects.xlsx` (sheet `Furniture Catalog`) for price, dimensions, style, and the Unsplash photo
- `db/source/enrichment.json` for demo merchandising that is not in the spreadsheet
- `catalog/furniture.json` for model folders
- `models/<category>/<item_id>_<slug>/metadata.json` for the measured bbox
- `models/.../build.py` for Principled BSDF base colors
- every `rooms/<room_id>/metadata.json`, plus that folder's `build.py` and `README.md`
- `db/source/rooms_enrichment.json` for room tags and demo starter layouts

`demo_data` is `true`. Brands, SKUs, short descriptions, `in_stock`, `ships_in_days`, and sponsored ranks are fictional and live in `enrichment.json`. Room style ids, vibe, light level, and starter layouts are inferred or demo data in `rooms_enrichment.json`. Colors, preview paths, prices, dimensions, and room geometry come from the repo files.

## Schema

Top level: `version` (3), `generated_at`, `demo_data`, `demo_note`, `units`, `conventions`, `categories`, `styles`, `colors`, `brands`, `room_types`, `size_classes`, `room_features`, `room_styles`, `rooms`, `items`, `data_gaps`.

`categories`, `styles`, and `colors` have `id`, `label`, `item_count`, and `item_ids`. `styles` also has `room_ids` and `room_count`. Room facets (`room_types`, `size_classes`, `room_features`, `room_styles`) use the same shape, and their `item_count` counts rooms. Style order is Modern, Coastal, Minimal, Scandinavian, Japandi, Industrial, Bohemian.

## Rooms

Each `rooms[]` entry keeps the version 2 keys (`id`, `name`, `label`, `model`, `interior_m`, `anchors`, `openings`, `bbox_m`, `images.thumbnail`, `images.card`, `item_count`, `catalog_room`) and adds the fields below. `item_count` is still the number of catalog items whose spreadsheet room maps to this shell. Every item in the current catalog maps to `living_room_generic`.

| Field | Meaning |
| --- | --- |
| `slug`, `display_name`, `sort_order` | URL slug, label, and list order. |
| `short_description`, `long_description` | First sentence and the README prose. `description_source` says where they came from. |
| `dimensions` | Interior width, depth, and height in `meters`, `feet`, and `inches`. |
| `floor_area` | Interior width times depth, in `m2` and `ft2`. |
| `shell_bounds_m`, `bounds_m` | Shell box, and the full glTF box when the file includes a garden or yard. `{min, max, size}`. |
| `conventions` | Meters, up axis Z, origin, furniture front `-Y`, and yaw about Z in degrees. |
| `files` | `glb`, `blend`, `build_py`, `readme`, `metadata`, `preview`. Each has `path`, `raw_url`, `blob_url`, `bytes`, and `exists`. |
| `triangle_count` | From `metadata.json`. |
| `images.thumbnail`, `images.card`, `images.hero` | All three point at `preview.png` with `{path, url}`. |
| `images.inspiration` | Reference-photo notes from the README. `url` is null when no file is named. `inferred` is true when the note was written for the DB. |
| `images.preview_px` | Preview render size from `build.py`. |
| `preview_hides` | Object names the preview camera hides. |
| `anchors` | `id`, `name`, `position_m` `[x,y,z]`, `yaw_deg`, `yaw_rad`, `rotation_z_deg`, `description`, `intended_use`, `suggested_categories`, `compatible_item_ids`. |
| `free_floor` | `rect_m`, `polygon_xy_m`, `bounds_m`, `area_m2`, `area_ft2`, `note`. Null when the metadata has no free-floor polygon. |
| `blocked` | Hearth, bench, and hall polygons. `inferred` is false when the polygon is copied from metadata. |
| `features` | Windows, doors, sliders, French doors, fireplace, beams, kitchen, peninsula, alcove, closet, radiator, pendants, tray ceiling, soffit, bench. Each has `type`, `wall`, `position_m`, and `size_m` when the file has them. |
| `walls` | One entry per metadata wall: `id`, `cardinal`, `label`, `openings`, `hidden_in_preview`. |
| `materials`, `palette` | Principled BSDF colors from the room `build.py`. `palette.floor`, `palette.wall`, `palette.ceiling`, and `palette.accents` carry display-sRGB `hex` values. Socket colors are linear in these scripts, so the hex is the sRGB transfer. |
| `tags` | `room_type`, `style_ids`, `styles`, `vibe`, `light_level`, `size_class` (`small` under 24 m², `medium` under 30, `large` from 30, using free-floor area when it exists), `has_kitchen`, `has_fireplace`, `has_outdoor_view`, `has_beams`. Style, vibe, light, and room type are flagged `inferred`. |
| `fit.items` | Every catalog item: footprint against the free floor, with `fits_area`, `fits_span`, `fits_height`, and `fits`. |
| `fit.starter_layout` | Demo anchor-to-item map. `demo` and `inferred` are true. |
| `readme_markdown`, `source_metadata` | The README text and the metadata JSON, so nothing in the source files is dropped. |

```javascript
const loft = db.rooms.find((room) => room.id === "bright_loft");
loft.display_name;                 // "Bright Loft"
loft.dimensions.feet;              // {width: 19, depth: 25, height: 10.5}
loft.images.hero.url;              // raw.githubusercontent.com preview.png
loft.files.glb.blob_url;           // github.com blob URL
loft.palette.floor.hex;
loft.anchors.find((anchor) => anchor.id === "Sofa_spot").compatible_item_ids;
loft.fit.starter_layout.placements; // demo: [{anchor_id: "Sofa_spot", item_id: "F003", fits: true}, ...]
db.room_types;                      // {id, label, item_count, room_ids}
db.size_classes;
```

`brands` has `id`, `name`, `ships_from`, `blurb`, `item_count`, and `item_ids`. Cloudline Home and Lumen Works match the names the site already uses.

Each item:

| Field | Meaning |
| --- | --- |
| `id`, `sku`, `slug`, `name`, `short_description` | Stable id plus demo storefront copy. `sku` looks like `CLH-F001`. |
| `category`, `style`, `room` | Spreadsheet labels. `category_id`, `style_id`, and `room_id` are the facet ids. |
| `brand_id` | Key into `brands`. |
| `price` | `{amount, currency}`. `currency` is also copied onto the item (`USD`). |
| `in_stock`, `ships_in_days` | Demo availability. |
| `sponsored`, `featured_rank` | `F001` is rank 1 and `F004` is rank 2. Every other item is `false` / `null`. |
| `dimensions` | `{inches, meters}`, each `{width, depth, height}`. |
| `color` | `{name, hex, material, source}`. `hex` is the display swatch for the primary material. |
| `materials` | Principled BSDF entries from `build.py`: `name`, `role`, `hex`, `base_color_rgb`, `roughness`, `metallic`. |
| `images.thumbnail`, `images.card` | The model `preview.png` as a repo-relative `path` and a `url` on `raw.githubusercontent.com/.../main/`. |
| `images.lifestyle` | Unsplash `url`, `source_url`, `credit`, and `shared_with` (other item ids using that photo). |
| `photo` | The same lifestyle image, kept so older readers still resolve. |
| `model` | `{glb, blend, preview, metadata, folder, available}`. |
| `measured_bbox_m` | `{min, max, size}` in meters. |
| `catalog_ref`, `tags`, `source` | Catalog pointer, filter tags, and which branch the files were checked on. |

Use `images.card` on product cards. Use `images.lifestyle` only when a shared room photo is acceptable; `shared_with` is empty when the photo is unique.

`color.hex` is display sRGB. If `build.py` converts with `srgb_to_linear` or `linear_rgb`, the hex is the authored sRGB color. If it writes the Base Color socket directly, the socket value is linear and the hex is that value encoded with the sRGB transfer, which is the albedo the shader displays.

## Frontend

```javascript
const db = await fetch("/db/db.json").then((res) => {
  if (!res.ok) throw new Error(`db.json ${res.status}`);
  return res.json();
});

const styles = db.styles; // {id, label, item_count}
const brand = db.brands.find((entry) => entry.id === "lumen-works");
const sofa = db.items.find((item) => item.id === "F001");

sofa.images.card.url;       // raw GitHub preview.png
sofa.images.card.path;      // models/couch/f001_cloudline_3_seat_couch/preview.png
sofa.images.lifestyle.shared_with; // ["F002", "F011"]
sofa.color;                  // {name: "Oatmeal", hex: "#BFB5A8", ...}
sofa.sponsored;              // true
sofa.featured_rank;          // 1
sofa.price;                  // {amount: 899, currency: "USD"}
sofa.sku;                    // "CLH-F001"
sofa.in_stock;
sofa.ships_in_days;

const room = db.rooms.find((entry) => entry.id === sofa.room_id);
const spot = room.anchors.find((anchor) => anchor.id === "Sofa_spot");
// load sofa.model.glb, place it at spot.position_m, yaw spot.rotation_z_deg
```

```javascript
import db from "../db/db.json";
```

Copy `db.json` into `public/db/` if the app only serves that folder. The fetch URL stays `/db/db.json`.
