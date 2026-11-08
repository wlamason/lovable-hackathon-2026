# Furniture database

`db/db.json` is the document the room designer loads. Version 2 adds the storefront fields the site was filling in by hand: card images, brands, color swatches, sponsored ranks, and filter counts.

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
- every `rooms/<room_id>/metadata.json` on disk or on any fetched branch

`demo_data` is `true`. Brands, SKUs, short descriptions, `in_stock`, `ships_in_days`, and sponsored ranks are fictional and live in `enrichment.json` so a rebuild keeps them. Colors, preview paths, prices, and dimensions are measured from the models and the spreadsheet. Swatch names are labels in the enrichment file; the hex values are not.

## Schema

Top level: `version`, `generated_at`, `demo_data`, `demo_note`, `units`, `conventions`, `categories`, `styles`, `colors`, `brands`, `rooms`, `items`, `data_gaps`.

`categories`, `styles`, `colors`, and `rooms` each have `id`, `label`, `item_count`, and `item_ids`. Style order is Modern, Coastal, Minimal, Scandinavian, Japandi, Industrial, Bohemian.

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
