---
name: blender-room-model
description: >-
  Build one room shell from reference photos under rooms/<slug>/ with headless
  Blender. Use when adding a living-room level: floor center at the origin,
  walls outside the footprint, furniture anchors with yaw, a preview that hides
  the camera-side wall, and a PR body that embeds the raw preview URL.
---

# Build one room from reference photos

Build an empty shell a furniture model can sit in. Read `rooms/living_room_generic/build.py`, its `metadata.json`, and the root `README.md` first. The five photo rooms (`condo_open_kitchen`, `glass_garden_room`, `bright_loft`, `beamed_fireplace_living`, `studio_pass_through`) are the later pattern: same axes, plus a free-floor record, more anchors, a 1024×640 preview, and an embedded README image.

Only create files in `rooms/<slug>/`. Do not edit the root README, `db/`, `catalog/`, `models/`, or any other room.

Timebox about 15 minutes. The room should be clearly reminiscent of the photo, not a measured replica.

## Conventions

- Meters, Z up. Interior floor center is `(0, 0, 0)`. The floor top is Z=0, so a furniture model whose origin is its bottom center sits on the floor.
- Width is X, depth is Y, height is Z. Walls stand outside the interior footprint. Interior walls are about 0.12 m thick. A window wall can be thicker when the frame sits in a reveal (`bright_loft` uses 0.34 m). Exterior set dressing, such as the garden plane in `glass_garden_room`, may extend the mesh bbox far past the interior. Record the interior in `interior_m`. Record the mesh in `bbox_m`.
- Floor thickness hangs below Z=0 (the generic room uses 0.04 m, so the mesh min Z is `-0.04`). Do not sink the walkable surface.
- Furniture front faces local -Y. An anchor's yaw is the Z rotation, in degrees, applied to that furniture model. Positive yaw is right-handed. A point on the front, local `(0, -1)`, lands at:

  | Yaw | Front faces |
  | --- | --- |
  | 0 | -Y |
  | 90 | +X |
  | 180 | +Y |
  | 270 or -90 | -X |

  `living_room_generic` puts the TV on the north wall (+Y) and sets `Sofa_spot` to 180 so the sofa front faces it. `studio_pass_through` puts the sofa on the west wall at yaw 90 (front toward +X) and the TV on the east wall at yaw 270 (screen toward -X).

- Write both `yaw_deg` and `rotation_z_deg` with the same number. `db/build_db.py` copies only `rotation_z_deg`. `studio_pass_through` stored `yaw_deg` alone, so a database rebuild drops those yaws. `bright_loft` stores both and leaves the empty unrotated.
- Do not rotate the empty and also expect the app to apply the metadata yaw. That turns the furniture twice. `living_room_generic` and `bright_loft` leave the empty's Euler at zero. The template does the same and stores the yaw on a custom property plus in `metadata.json`.
- Separate objects with stable names: `Floor`, `Wall_N`, `Wall_S`, `Wall_E`, `Wall_W` (or `Wall_*`), `Ceiling`, `Window_*`, `Door_*`, `Baseboard`, and `Kitchen_*` when the photo has a kitchen. The viewer hides ceiling and walls by name.
- Principled BSDF only. No image textures. Floor wood matches the photo. Glass is slightly transparent (`alpha` about 0.35 and a transmission input).
- Under 50,000 triangles. The heaviest merged room is `condo_open_kitchen` at 4,664.
- Real sizes unless the photo clearly says otherwise: doors about 36 × 80 in, counters 36 in high and 25 in deep, upper-cabinet bottoms near 54 in, ceilings 8.5–10 ft. `bright_loft` is 10.5 ft because the photo is a tall loft.

Required anchors: `Sofa_spot`, `TV_wall`, `Rug_center`, `Coffee_spot`, plus one to three that fit the photo (`Plant_corner`, `Lamp_corner`, `Side_table`, `Alcove_spot`, `Bar_spot`). Positions are meters on the floor (Z=0).

`free_floor` is the polygon or rect where furniture can go. Cut counters, peninsulas, a raised hearth, and the hall threshold out of it. `condo_open_kitchen` and `beamed_fireplace_living` use a polygon. `studio_pass_through` uses a rect plus a note. The template records both a `free_floor` rect and a `blocked` list. The generic room omitted `free_floor`; photo rooms should not.

## Blender

Same install as the furniture skill. `libegl1` is listed here because the room brief added it after Eevee Next failed without EGL.

```bash
sudo apt-get install -y libxi6 libxxf86vm1 libxfixes3 libxrender1 libgl1 libegl1 libxkbcommon0 libsm6
# https://download.blender.org/release/Blender4.2/blender-4.2.3-linux-x64.tar.xz
tar -C /tmp -xf blender-4.2.3-linux-x64.tar.xz
```

A bare `curl` to `download.blender.org` can receive a Cloudflare 403 challenge page instead of the tarball. Download the same `blender-4.2.3-linux-x64.tar.xz` another way if that happens. Do not commit Blender.

## Build

```bash
mkdir -p rooms/room_template
cp .cursor/skills/blender-room-model/template_build.py rooms/room_template/build.py
```

Edit `SPEC` and `build_room()` so the shell matches the photo: floor tone, window wall, door wall, jogs, beams, kitchen, fireplace. Do not copy the template onto a room that already exists. Then:

```bash
/tmp/blender-4.2.3-linux-x64/blender -b --factory-startup \
  --python rooms/room_template/build.py \
  -- --outdir rooms/room_template
```

Expected lines for the untouched template, which is a 16 × 20 × 9 ft rectangle:

```text
bbox m: 5.1200 x 6.3400 x 2.8200
triangles: 204
RENDER engine BLENDER_EEVEE_NEXT
WROTE rooms/room_template/model.glb
WROTE rooms/room_template/model.blend
WROTE rooms/room_template/preview.png
WROTE rooms/room_template/metadata.json
```

A photo room prints its own bbox and triangle count. `living_room_generic` itself is 372 triangles and bbox `5.12 × 6.34 × 2.82` m. The template's 204 triangles are the box shell before photo detail. Delete `rooms/room_template/` after a dry run. It is not one of the six rooms.

Order that kept the glb complete:

1. `read_factory_settings(use_empty=True)` and metric units.
2. Build named meshes and empties.
3. Measure mesh bbox (skip empties) and triangle count. Abort above 50,000 triangles.
4. Write `metadata.json` with interior size, openings, `free_floor`, anchors, and the measured bbox.
5. Render the preview. Hide the ceiling and the wall nearest the camera. The generic room hides `Ceiling` and `Wall_W`. Photo rooms hide the camera-side wall (`Wall_S` when the camera is at the south end).
6. Set `hide_render` back to false before export. The hidden wall stays in the glb.
7. Export glTF of meshes and empties only (`export_cameras=False`, `export_lights=False`, `export_yup=True`, `export_apply=True`).
8. Save `model.blend` and delete any `*.blend1`.

Preview is about 1024×640, from an interior camera near the reference photo's viewpoint. The generic room was rendered at 512×512 before that size was fixed. New rooms use 1024×640. Try `BLENDER_EEVEE_NEXT`, then Workbench.

Point the camera at the feature the photo is about (the garden wall, the fireplace, the pass-through), not at a blank corner. The template camera sits just inside the south wall and looks north, which is why it hides `Wall_S`.

## metadata.json

Minimum fields the merged rooms and the checker share:

- `id`, `name`, `description`
- `units`, `up_axis`, `origin`
- `interior_m` with `width_x`, `depth_y`, `height_z`, and `interior_ft` for the same box
- `ceiling_height_m`, `wall_thickness_m`
- `openings` keyed by window, door, and any pass-through, each with `position` via `center_m` and a width and height
- `empties` keyed by anchor name. Each value has `position_m`, `yaw_deg`, `rotation_z_deg`, and a `note`
- `free_floor` as a `rect` (`x_min`, `x_max`, `y_min`, `y_max`) or a `polygon_m` of `[x, y]` vertices, plus a note that says what was excluded
- `blocked` for hearth, counters, and door clearance when those are easier to list than to polygon-cut
- `bbox_m` with `min`, `max`, and `size` arrays in meters
- `triangle_count`
- `objects` listing mesh and empty names

## README and the pull request

The README embeds the preview with a relative path so GitHub renders it in the folder:

```markdown
![Glass wall garden room preview](preview.png)
```

Also say which photo it is reminiscent of, the interior size, where the anchors face, and:

```bash
blender -b --factory-startup --python build.py -- --outdir .
```

The PR description uses an absolute raw URL on the pushed branch. A relative path does not render in the PR body. Confirm the branch segment before you publish.

```markdown
![preview](https://github.com/wlamason/lovable-hackathon-2026/blob/<your-branch>/rooms/<slug>/preview.png?raw=true)
```

Title the PR `Add room: <short name>`. Do not merge it and do not push to `main`.

## Check

The furniture skill's script handles rooms too. It selects the room checks when `metadata.json` has `interior_m` or `empties`.

```bash
python3 .cursor/skills/blender-furniture-model/validate_model.py rooms/glass_garden_room
```

```text
PASS rooms/glass_garden_room (room)
  triangles 1272  bbox_m 12.8400 x 11.1200 x 3.5600  min (-8.1700, -2.5600, -0.0600)
1 passed, 0 failed, 1 checked
```

That bbox is larger than the 6.10 × 4.88 × 2.90 m interior because the garden plane is in the mesh. The checker compares the glb to `bbox_m`, not to `interior_m`.

`rooms/living_room_generic` still passes and warns: three anchors have no yaw, `free_floor` is absent, the preview is 512×512, and the README does not embed the image. Those warnings are the historical file. A new photo room should not print them. `studio_pass_through` warns because its anchors set `yaw_deg` and not `rotation_z_deg`.

Hard failures: missing file, a Blender backup, glb size disagreeing with `bbox_m`, more than 50,000 triangles, a missing required anchor, or `yaw_deg` and `rotation_z_deg` set to different numbers.

## Pitfalls that actually came up

- Hiding the camera wall for the still and forgetting to unhide it removes that wall from the glb. Unhide, then export.
- Putting the yaw only on the empty's rotation, or only in `yaw_deg`, loses it in the database. Write `rotation_z_deg`.
- `download.blender.org` plus the missing `libegl1` package. Install the library list above before the first render.
- The second save creates `model.blend1`. Delete it. The living room backup had to be removed after the first commit.
- Photo rooms share no files. Two agents writing the same `rooms/<slug>/` will conflict. One slug per agent.
- A kitchen, hearth, or hall that is left inside `free_floor` will get a sofa on top of it. Cut it out and say so in the note.

## Done

- [ ] Files exist only under `rooms/<slug>/`: `build.py`, `model.glb`, `model.blend`, `preview.png`, `metadata.json`, `README.md`
- [ ] Interior floor center is the origin, floor top is Z=0, walls are outside the footprint
- [ ] Anchors include `Sofa_spot`, `TV_wall`, `Rug_center`, and `Coffee_spot`, each with `position_m`, `yaw_deg`, and `rotation_z_deg`
- [ ] Empties are unrotated. `free_floor` excludes counters, hearth, and door clearance
- [ ] Preview is about 1024×640, the camera-side wall is hidden only in that render, and the wall is still in `model.glb`
- [ ] README embeds `![name preview](preview.png)` and states the reference photo and the rebuild command
- [ ] Triangle count is under 50,000
- [ ] `python3 .cursor/skills/blender-furniture-model/validate_model.py rooms/<slug>` prints `PASS` and exits 0
- [ ] PR body embeds `https://github.com/wlamason/lovable-hackathon-2026/blob/<branch>/rooms/<slug>/preview.png?raw=true`
- [ ] The PR is not merged and `main` was not pushed
