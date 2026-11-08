# Furniture database

`db/db.json` is the document the room designer loads for prices, photos, dimensions, and 3D paths. It joins the Furniture Catalog spreadsheet with `catalog/furniture.json` and the measured bounds in each model's `metadata.json`.

Regenerate it from the repo root after catalog or model metadata changes:

```bash
python3 db/build_db.py
```

The script reads `db/source/objects.xlsx` (sheet `Furniture Catalog`), `catalog/furniture.json`, `rooms/*/metadata.json`, and `models/*/*/metadata.json`. It checks `model.glb`, `model.blend`, `preview.png`, and `metadata.json` on `origin/main` and on the model branches. `source.only_open_pr` is true when those files exist only on an open pull request.

## Schema

Top-level fields:

| Field | Meaning |
| --- | --- |
| `version` | Schema version. Currently `1`. |
| `generated_at` | UTC timestamp of the last build. |
| `units` | Meters for 3D, inches for display, USD for price. `inch_to_meter` is `0.0254`. |
| `conventions` | Axis, origin, path, and bbox rules shared with the catalog. Width is X, depth is Y, height is Z, up is Z, front is -Y. Origin is the bottom center of the footprint on the floor. |
| `categories` | `{id, name, item_ids}`. `id` is a lowercase slug (`couch`, `lamp`, `table`, `carpet`, `tv`, `plant`). |
| `styles` | Same shape (`modern`, `coastal`, `minimal`, `scandinavian`, `japandi`, `industrial`, `bohemian`). |
| `rooms` | Placeable levels. Includes `model.glb` and `anchors`. |
| `items` | One record per catalog id `F001`–`F017`. |
| `data_gaps` | Photo and asset issues the build noticed. |

Each item:

| Field | Meaning |
| --- | --- |
| `id`, `name` | Stable catalog id and display name. |
| `category`, `style`, `room` | Labels from the spreadsheet. |
| `category_id`, `style_id`, `room_id` | Slugs. `room_id` matches `rooms[].id`. |
| `price` | `{amount, currency}`. Currency is `USD`. |
| `dimensions` | `{inches, meters}`, each `{width, depth, height}`. |
| `photo` | `{url, source_url, credit}`. `url` is the image to show. `credit` is the source site. |
| `model` | `{glb, blend, preview, metadata, folder, available, triangle_count}`. Paths are repo-relative. |
| `measured_bbox_m` | `{min, max, size}` in meters from that model's `metadata.json`, rounded to 4 decimal places. |
| `catalog_ref` | `{file, id, path}` pointing at `catalog/furniture.json`. |
| `tags` | Category, style, room, and a role tag such as `seating` or `lighting`. |
| `source` | Spreadsheet plus the model branch, pull request number, and whether the files are on `main`. |

`rooms[].anchors` are floor points in meters. `Sofa_spot` includes `rotation_z_deg` so a model's front (local -Y) faces the TV wall.

## Frontend

The React app can fetch the file if the dev server exposes the repo root:

```javascript
const db = await fetch("/db/db.json").then((res) => {
  if (!res.ok) throw new Error(`db.json ${res.status}`);
  return res.json();
});

const sofa = db.items.find((item) => item.id === "F001");
const room = db.rooms.find((entry) => entry.id === sofa.room_id);
const spot = room.anchors.find((anchor) => anchor.id === "Sofa_spot");

// sofa.price.amount, sofa.photo.url, sofa.dimensions.inches
// load sofa.model.glb (models/couch/f001_cloudline_3_seat_couch/model.glb)
// position at spot.position_m and yaw spot.rotation_z_deg
```

Vite and other bundlers can import it when the module graph includes JSON:

```javascript
import db from "../db/db.json";

const monstera = db.items.find((item) => item.id === "F016");
// monstera.model.glb === "models/plant/f016_monstera_floor_plant/model.glb"
// monstera.measured_bbox_m.size === { width: 0.6096, depth: 0.6096, height: 1.2192 }
```

Copy `db.json` into `public/db/` if the app only serves that folder, and keep the same `/db/db.json` URL.
