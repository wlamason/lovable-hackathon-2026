---
name: blender-furniture-model
description: >-
  Build one catalog furniture item as a headless Blender model under
  models/<category>/<id>_<slug>/. Use when adding or rebuilding a couch, lamp,
  table, carpet, TV, or plant from catalog/furniture.json, with the repo's
  meter, Z-up, front-faces -Y conventions, glTF export, and bbox check.
---

# Build one catalog furniture model

Build a single item in its own folder. The models merged on 8 Nov 2026 (F001–F017) all followed this shape. A fresh agent can copy `template_build.py`, replace the mesh, and check the result with `validate_model.py`.

Stay inside the item folder. Do not edit the root README, `catalog/`, `db/`, `rooms/`, another item, or a shared ignore file. That is how parallel agents avoided merge conflicts.

Timebox about 15 minutes. Get the overall proportions right before adding detail.

## Dimensions come from the catalog

Read the item in `catalog/furniture.json`. Use `dimensions_in` and convert with `0.0254`. Do not retype rounded meters. `dimensions_m` in the catalog is already `inches * 0.0254`.

```text
width  = dimensions_in.width  * 0.0254    # X
depth  = dimensions_in.depth  * 0.0254    # Y
height = dimensions_in.height * 0.0254    # Z
```

The spreadsheet behind the catalog is `db/source/objects.xlsx`, sheet `Furniture Catalog`. During a fan-out, do not open that file and do not edit the catalog. Another agent owns both.

Folder name, matching `path` in the catalog:

```text
models/<category>/<id>_<slug>/
```

Category is lowercase (`couch`, `lamp`, `table`, `carpet`, `tv`, `plant`). The id is lowercase (`f009`). The slug is the item name in lowercase with punctuation collapsed to underscores (`slim_side_table`).

## Conventions

- Meters. One Blender unit is one meter. Set `scene.unit_settings.system = "METRIC"`, `scale_length = 1.0`, `length_unit = "METERS"`.
- Z up. Width along X, depth along Y, height along Z.
- The front faces -Y. A preview camera sits on the -Y side.
- Origin is the bottom center of the footprint. The object sits on the floor at Z=0 and is centered on X and Y. Apply location, rotation, and scale before export.
- The measured bounding box must match width × depth × height within 2% on each axis. Measure it in the script and abort if it does not.
- Low to mid poly. Stay under 30,000 triangles. The heaviest merged meshes are the olive tree (28,740) and the geometric carpet (24,334).
- Simple Principled BSDF colors. No image textures.
- One object named the item id (`F009`), or a parent of that name. Real sub-part proportions matter more than polygon count: seat height, arm width, leg thickness, cushion thickness, screen bezel, pot versus foliage.

## Blender on the VM

Blender is not in the repo. Use the official 4.2.3 LTS Linux tarball and leave it in `/tmp`:

```bash
sudo apt-get install -y libxi6 libxxf86vm1 libxfixes3 libxrender1 libgl1 libegl1 libxkbcommon0 libsm6
# https://download.blender.org/release/Blender4.2/blender-4.2.3-linux-x64.tar.xz
tar -C /tmp -xf blender-4.2.3-linux-x64.tar.xz
/tmp/blender-4.2.3-linux-x64/blender --version
```

`libegl1` is required. The original furniture brief omitted it. Eevee Next (`BLENDER_EEVEE_NEXT` in 4.2) fails without EGL and the script should fall back to Workbench, but the previews that look right were Eevee. A bare `curl` against `download.blender.org` can get a Cloudflare 403 HTML page instead of the tarball. If that happens, download the same `blender-4.2.3-linux-x64.tar.xz` another way. Do not commit Blender.

## Build

Copy the template into a new item folder, then replace `SPEC` and `build_product()`. Do not copy it onto an existing item.

```bash
mkdir -p models/table/f000_placeholder_box
cp .cursor/skills/blender-furniture-model/template_build.py \
  models/table/f000_placeholder_box/build.py
```

Run it headless. Blender eats arguments before `--`, so the script reads only what follows `--`.

```bash
/tmp/blender-4.2.3-linux-x64/blender -b --factory-startup \
  --python models/table/f000_placeholder_box/build.py \
  -- --outdir models/table/f000_placeholder_box
```

The template, and every merged `build.py`, also calls `bpy.ops.wm.read_factory_settings(use_empty=True)` so a leftover scene cannot leak in.

The untouched template is an 18 × 18 × 22 in box (the F009 size) with 24 triangles. A real item prints its own count. F009's merged mesh is 272. Expected lines from the template:

```text
bbox m: 0.4572 x 0.4572 x 0.5588
triangles: 24
width: 0.457200 m (nominal 0.457200, error 0.0000%)
RENDER engine BLENDER_EEVEE_NEXT
WROTE models/table/f000_placeholder_box/model.glb
WROTE models/table/f000_placeholder_box/model.blend
WROTE models/table/f000_placeholder_box/preview.png
WROTE models/table/f000_placeholder_box/metadata.json
```

Abort when any axis is over 2% or the triangle count is over 30,000. Delete the placeholder folder when you are done looking. It is not a catalog item.

What the script does, in the order that worked:

1. Clear the scene and set metric units.
2. Build the mesh with `bpy`, `bmesh`, and `mathutils` only. No addons and no external assets.
3. Apply transforms. Name the object the item id.
4. Print the world bbox and the triangle count (`mesh.calc_loop_triangles()`). Raise `SystemExit` when the 2% check or the triangle budget fails.
5. Write `metadata.json` from the measured bbox, not from the nominal size alone.
6. Export `model.glb` with the product selected. `use_selection=True`, `export_format="GLB"`, `export_apply=True`, `export_yup=True`, `export_materials="EXPORT"`. Y-up is for the web viewer. Blender itself stays Z-up.
7. Add a preview camera, lights, and a floor named `PreviewFloor`. Render 512×512 PNG. Try `BLENDER_EEVEE_NEXT`, then `BLENDER_EEVEE`, then `BLENDER_WORKBENCH`. The template tries Eevee Next and then Workbench.
8. Save `model.blend`. Delete any `model.blend1` the save leaves behind.

Keep the preview floor, camera, and lights out of the glTF selection. Several blends contain that studio because the `.blend` is saved after the preview rig is added. That is acceptable. The glb must not contain it.

Plants that scatter leaves should set a fixed seed (`14014` for F014, `15015` for F015, `16016` for F016, `17017` for F017) so a rebuild matches.

## Materials and swatch hex

Author colors as display sRGB and pass them through a function named `srgb_to_linear` before assigning the Principled Base Color. The socket stores linear. `db/build_db.py` looks for that function name (or `linear_rgb`). When it finds it, the hex swatch is the sRGB you typed. Oakline's top `(0.83, 0.68, 0.49)` becomes `#D4AD7D`. Slate authored the same way is `#3A434A`.

If you write the tuple straight into the socket, the DB treats the number as linear and gamma-encodes it. Cloudline fabric then displays as `#BFB5A8` and the satin-black lamp as `#1D1D1E`, which are lighter than the linear numbers in the script. Pick one approach and name the helper so the hex matches the color you meant.

Name product materials with the item id, for example `F001_Fabric` or `F007_OakTop`. The enrichment file points `primary_material` at that name. Do not name a product material `Floor`, `Wall`, `Ground`, or anything with `preview` in it. The DB drops those as studio materials.

The snake plant is the exception. Its leaf shader is driven by vertex colors, and the swatch is the mid green `#427752` (`F015_LeafMid`), not the Principled socket.

## metadata.json

```json
{
  "id": "F009",
  "name": "Slim Side Table",
  "category": "Table",
  "style": "Minimal",
  "room": "Living Room",
  "price_usd": 99,
  "dimensions_in": {"width": 18, "depth": 18, "height": 22},
  "dimensions_m": {"width": 0.4572, "depth": 0.4572, "height": 0.5588},
  "bounding_box_m": {
    "min": {"x": -0.2286, "y": -0.2286, "z": 0.0},
    "max": {"x": 0.2286, "y": 0.2286, "z": 0.5588},
    "width": 0.4572,
    "depth": 0.4572,
    "height": 0.5588
  },
  "triangle_count": 272
}
```

`min` and `max` may be `{x, y, z}` objects or length-3 arrays. F006 uses arrays. Include `triangle_count`. F006, F007, and F009 omitted it, so `db.json` stored `null` for those three.

## README

One short paragraph: what it is, the inch size, and the rebuild command. Also embed the preview so the picture shows up when someone opens the folder on GitHub. Most furniture READMEs only mention the filename in a sentence, which does not render the image.

```markdown
![Slim Side Table preview](preview.png)
```

And the rebuild command:

```bash
blender -b --factory-startup --python build.py -- --outdir .
```

## Check

`validate_model.py` reads the glTF (Y-up) back into Blender space and compares it with the catalog size. It does not launch Blender.

```bash
python3 .cursor/skills/blender-furniture-model/validate_model.py \
  models/table/f009_slim_side_table
```

A historical folder still passes, with warnings for the gaps left on 8 Nov:

```text
PASS models/table/f009_slim_side_table (furniture)
  triangles 272  bbox_m 0.4572 x 0.4572 x 0.5588  min (-0.2286, -0.2286, -0.0000)
  WARN metadata.json has no triangle_count (several early items omitted it)
  WARN README.md does not embed preview.png as an image
1 passed, 0 failed, 1 checked
```

A new item should print `PASS` and no `WARN`. Exit 0 means the hard checks passed. `--all` walks every `models/*/*/model.glb` and `rooms/*/model.glb`.

Hard failures: missing file, a `*.blend1` backup, bbox more than 2% off `dimensions_m`, glb size disagreeing with `bounding_box_m`, origin not on the floor at the footprint center, more than 30,000 triangles, `triangle_count` present but different from the glb.

## Pitfalls that actually came up

- Item id is not the pull request number. F011 is PR #1. F001 is PR #7. PR #5 is the living room, catalog, and root README, so the furniture PRs are #1–#4 and #6–#18.
- Do not commit `model.blend1`. Blender writes it beside `model.blend` on a later save. F012, F013, and the living room all had a backup removed in a follow-up commit. There is no root `.gitignore` because nobody was allowed to edit shared files during the fan-out. Delete the backup inside the item folder.
- Preview images in the PR body only render from a raw GitHub URL. Relative paths do not (F017). `cursor.com` artifact links stay blank unless a dashboard setting is on (F007, F008, F010, F012, F014, F015). Use `https://github.com/wlamason/lovable-hackathon-2026/blob/<branch>/models/<category>/<id>_<slug>/preview.png?raw=true`.
- Lifestyle photos in the spreadsheet are shared across items. The model `preview.png` is the product image. Do not bake the Unsplash photo onto the mesh.
- TVs are the panel only, 3 inches deep, no stand. The glass is a separate material named `Screen`.
- Carpets are thin (0.5 in). A 2% error on that axis is a fraction of a millimeter, so build the slab to the nominal thickness instead of scaling a thick mesh down.

## Done

- [ ] Files exist only under `models/<category>/<id>_<slug>/`: `build.py`, `model.glb`, `model.blend`, `preview.png`, `metadata.json`, `README.md`
- [ ] No `*.blend1`, no Blender install, no edits outside the folder
- [ ] Script uses only `bpy`, `bmesh`, and `mathutils`, and runs with `blender -b --factory-startup --python build.py -- --outdir .`
- [ ] Bbox matches the catalog within 2%, origin at the bottom center, front toward -Y
- [ ] Triangle count is under 30,000 and recorded in `metadata.json`
- [ ] Materials are Principled BSDF colors. sRGB inputs go through `srgb_to_linear`
- [ ] `preview.png` is 512×512 and embedded in `README.md`
- [ ] `python3 .cursor/skills/blender-furniture-model/validate_model.py <folder>` prints `PASS` and exits 0
- [ ] Pull request title is `Add 3D model F00N: Name`, the body has the raw preview URL, and the PR is not merged
