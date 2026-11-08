# Brief to paste

Fill the blanks. One agent, one folder. Point the agent at `.cursor/skills/blender-furniture-model/SKILL.md` or `.cursor/skills/blender-room-model/SKILL.md` and at this file.

```text
Timebox: under 15 minutes. Proportions first, then detail.

Repo: lovable-hackathon-2026. Other agents are writing other folders at the same time.
Touch only <FOLDER>. Do not edit the root README, .gitignore, catalog/, db/, models/ outside your folder, rooms/ outside your folder, or any lockfile.

Read:
- .cursor/skills/blender-furniture-model/SKILL.md   (furniture)
  or .cursor/skills/blender-room-model/SKILL.md    (room)
- catalog/furniture.json row <ID>                  (furniture only)
- rooms/living_room_generic/build.py               (rooms only)

<FOLDER>: <models/<category>/<id>_<slug>  or  rooms/<slug>>

Catalog row (furniture): <id, name, category, style, price, width x depth x height inches>

Reference (rooms): <what the photo shows, in a few sentences. Not a 1:1 copy.>

Deliver, inside the folder only:
- build.py  (bpy, bmesh, mathutils only)
- model.glb, model.blend, preview.png, metadata.json, README.md

Run:
  blender -b --factory-startup --python <FOLDER>/build.py -- --outdir <FOLDER>
Then:
  python3 .cursor/skills/blender-furniture-model/validate_model.py <FOLDER>

Conventions: meters, Z up, furniture front faces -Y, origin at the bottom center.
Rooms: interior floor center at (0,0,0), floor top Z=0, walls outside the footprint.
Bbox within 2% of the catalog size. Furniture under 30k triangles, rooms under 50k.
Principled BSDF only. Name srgb_to_linear if you author sRGB colors.
Write rotation_z_deg and yaw_deg on every room anchor. Do not rotate the empty as well.
Embed ![name preview](preview.png) in the README.
Delete any *.blend1 before commit. Do not commit Blender.

Git: branch from main, push the branch, open a PR against main titled
  "Add 3D model <ID>: <Name>"    or    "Add room: <Name>"
PR body must include the measured bbox, the triangle count, and
  ![preview](https://github.com/wlamason/lovable-hackathon-2026/blob/<branch>/<FOLDER>/preview.png?raw=true)
Do not merge. Do not push to main.

Report: PR link, measured bbox, triangle count, validator result, anything that failed.
```
