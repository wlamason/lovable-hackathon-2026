# lovable-hackathon-2026

The work from 8 Nov 2026, and how to repeat it, is in [PROJECT.md](PROJECT.md).

Room designer. Catalog furniture and room levels share one coordinate system so a piece dropped into a room sits on the floor and faces the right way.

## Layout

```
models/<category>/<item_id>_<slug>/
rooms/<room_id>/
catalog/furniture.json
```

`catalog/furniture.json` is the web app index. It lists id, name, category, price, dimensions in inches and meters, style, room, and the folder path for every catalog item. Paths look like `models/couch/f001_cloudline_3_seat_couch`: category in lowercase, then the lowercase item id, an underscore, and the item name slug (lowercase, punctuation collapsed to underscores).

Each catalog folder contains:

| File | Role |
| --- | --- |
| `build.py` | Headless Blender script that builds the mesh from scratch |
| `model.glb` | glTF binary for the web viewer |
| `model.blend` | Source scene |
| `preview.png` | 512×512 render |
| `metadata.json` | Catalog fields plus the measured bounding box in meters |
| `README.md` | What the item is and how to rebuild it |

Room levels live under `rooms/`. `rooms/living_room_generic/` is an empty living room the furniture can be placed in. Its `metadata.json` records room dimensions, the measured bounding box, and empty-marker positions instead of catalog item fields.

## Catalog (F001–F017)

| ID | Item | Category | Size (W×D×H in) | Style | Folder |
| --- | --- | --- | --- | --- | --- |
| F001 | Cloudline 3-Seat Couch | Couch | 84 × 36 × 33 | Modern | `models/couch/f001_cloudline_3_seat_couch/` |
| F002 | Harbor 2-Seat Loveseat | Couch | 60 × 35 × 34 | Coastal | `models/couch/f002_harbor_2_seat_loveseat/` |
| F003 | Corner Modular Sectional | Couch | 104 × 72 × 34 | Modern | `models/couch/f003_corner_modular_sectional/` |
| F004 | Reading Arc Floor Lamp | Lamp | 18 × 18 × 66 | Modern | `models/lamp/f004_reading_arc_floor_lamp/` |
| F005 | Soft Glow Table Lamp | Lamp | 10 × 10 × 20 | Minimal | `models/lamp/f005_soft_glow_table_lamp/` |
| F006 | Tripod Corner Lamp | Lamp | 20 × 20 × 60 | Scandinavian | `models/lamp/f006_tripod_corner_lamp/` |
| F007 | Oakline Round Coffee Table | Table | 36 × 36 × 16 | Japandi | `models/table/f007_oakline_round_coffee_table/` |
| F008 | Slate Nesting Tables | Table | 32 × 32 × 18 | Industrial | `models/table/f008_slate_nesting_tables/` |
| F009 | Slim Side Table | Table | 18 × 18 × 22 | Minimal | `models/table/f009_slim_side_table/` |
| F010 | Geometric Area Carpet 8x10 | Carpet | 96 × 120 × 0.5 | Modern | `models/carpet/f010_geometric_area_carpet_8x10/` |
| F011 | Soft Neutral Carpet 5x7 | Carpet | 60 × 84 × 0.5 | Scandinavian | `models/carpet/f011_soft_neutral_carpet_5x7/` |
| F012 | 48-Inch Smart TV | TV | 43 × 3 × 26 | Modern | `models/tv/f012_48_inch_smart_tv/` |
| F013 | 65-Inch Smart TV | TV | 57 × 3 × 34 | Modern | `models/tv/f013_65_inch_smart_tv/` |
| F014 | Tall Fiddle Leaf Plant | Plant | 20 × 20 × 60 | Bohemian | `models/plant/f014_tall_fiddle_leaf_plant/` |
| F015 | Snake Plant | Plant | 12 × 12 × 32 | Minimal | `models/plant/f015_snake_plant/` |
| F016 | Monstera Floor Plant | Plant | 24 × 24 × 48 | Bohemian | `models/plant/f016_monstera_floor_plant/` |
| F017 | Olive Tree in Pot | Plant | 22 × 22 × 54 | Japandi | `models/plant/f017_olive_tree_in_pot/` |

Prices and meter conversions are in `catalog/furniture.json`. Every item above is a living-room piece.

## Shared conventions

- Units are meters. One Blender unit is one meter. Inches convert by × 0.0254.
- Z is up. Width runs along X, depth along Y, height along Z.
- The front of an object faces -Y.
- The origin is the bottom center of the footprint. The object sits on the floor at Z=0, centered on X and Y. Apply all transforms before export.
- Materials are simple Principled BSDF colors. No image textures.
- Room shells use the same axes. For `living_room_generic`, the origin is the interior floor center, the floor top is Z=0, and the walls stand just outside the interior footprint. Named meshes: Floor, Wall_N, Wall_S, Wall_E, Wall_W, Ceiling, Window, Door, plus a Baseboard. Ceiling is a separate object so a viewer can hide it. Empty markers (TV_wall, Sofa_spot, Rug_center, Coffee_spot) are suggested floor spots. Sofa_spot wants a 180° yaw so the sofa front faces the north TV wall.

Interior of the generic living room: 4.88 m along X, 6.10 m along Y, 2.74 m ceiling (about 16 ft × 20 ft × 9 ft). Wall thickness is 0.12 m. The window is on the east long wall. The doorway is 36 × 80 in on the south short wall.

## Rebuild any model

Install [Blender 4.2 LTS](https://www.blender.org/download/lts/4-2/) and run the folder's `build.py` headless. The script uses only bpy, bmesh, and mathutils. It clears the scene, builds the mesh, writes `metadata.json`, renders `preview.png`, exports `model.glb`, and saves `model.blend`. `--outdir` defaults to the script's own directory.

```bash
blender -b --factory-startup --python build.py -- --outdir <dir>
```

From the repo root:

```bash
blender -b --factory-startup --python rooms/living_room_generic/build.py -- --outdir rooms/living_room_generic
blender -b --factory-startup --python models/couch/f001_cloudline_3_seat_couch/build.py -- --outdir models/couch/f001_cloudline_3_seat_couch
```

The same command works for any other item folder.
