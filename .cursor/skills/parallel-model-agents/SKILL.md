---
name: parallel-model-agents
description: >-
  Fan out one cloud agent per furniture item or room so they do not edit the
  same files. Use when launching parallel 3D model work: brief template, folder
  ownership, pull request titles, bbox and preview checks, and the 15 minute timebox.
---

# Fan out one agent per object or room

On 8 Nov 2026 this repo was built by parallel cloud agents. Seventeen furniture agents, one living-room agent, two database agents, and five photo-room agents. The merges stayed clean because each agent owned one folder and nobody edited a shared file at the same time.

Use this when launching that kind of work. The worker skills are `blender-furniture-model` and `blender-room-model`. The database skill is `fake-db-for-frontend`. Do not send a database agent in the same wave as the model agents, and do not send two agents into `db/`.

## What to hand each agent

Start from `brief-template.md` in this folder. Fill the folder, the catalog row or the photo notes, and the PR title. Also point at the worker skill. The original briefs are the same rules: 15 minutes, bpy only, meters, Z up, front faces -Y, files listed by name, do not merge, do not push `main`.

The later room brief added three things the first furniture brief lacked. Keep them:

- Install `libegl1` with the other Blender libraries, or Eevee Next does not render.
- Embed `![name preview](preview.png)` in the README.
- In the PR body, embed the raw file URL on the branch:

```text
https://github.com/wlamason/lovable-hackathon-2026/blob/<branch>/<folder>/preview.png?raw=true
```

A relative image and a `cursor.com` artifact link both failed to show the preview on the GitHub PR page.

## Folder ownership

One agent, one directory.

| Work | Only this path |
| --- | --- |
| Furniture item | `models/<category>/<id>_<slug>/` |
| Room | `rooms/<slug>/` |
| Catalog index and root README | one agent, once (`catalog/furniture.json`, `README.md`, `rooms/living_room_generic/`) |
| Fake database | one agent, only `db/` |

Category directories (`models/couch/`, `models/plant/`) can receive new subfolders from different agents in the same hour. Git merges those as new files. Two agents must not choose the same `<id>_<slug>` or the same room slug.

Do not add a root `.gitignore` in the middle of a wave. There is still no root ignore file, because that would have been a shared edit. Tell every agent to delete `*.blend1` inside their own folder instead. F012, F013, and the living room each committed a Blender backup and needed a follow-up commit to remove it.

Furniture agents do not update `catalog/furniture.json`. The catalog agent publishes the path, and the furniture agent builds that folder. A model agent that also edits the catalog collides with every other model agent.

## Pull requests

Branch from `main`. The branches used on 8 Nov were `cursor/<slug>-<suffix>`. Any name other than `main` is fine if it is unique.

Titles that merged:

- `Add 3D model F009: Slim Side Table`
- `Add room: Glass wall garden room`
- `Add JSON fake DB for frontend` and `DB: add brands, colors, images, sponsored and facets for frontend`

The body needs the measured bbox, the triangle count, the rebuild command, and the raw preview URL. Do not merge. Do not push to `main`.

Item ids are not pull request numbers. This is the mixup from the day:

| Item | PR |
| --- | --- |
| F011 Soft Neutral Carpet | #1 |
| F005 Soft Glow Table Lamp | #2 |
| F012 48-Inch Smart TV | #3 |
| F010 Geometric Area Carpet | #4 |
| Living room, catalog, root README | #5 |
| F007 Oakline Round Coffee Table | #6 |
| F001 Cloudline 3-Seat Couch | #7 |
| F008 Slate Nesting Tables | #8 |
| F002 Harbor 2-Seat Loveseat | #9 |
| F006 Tripod Corner Lamp | #10 |
| F004 Reading Arc Floor Lamp | #11 |
| F003 Corner Modular Sectional | #12 |
| F014 Tall Fiddle Leaf Plant | #13 |
| F009 Slim Side Table | #14 |
| F013 65-Inch Smart TV | #15 |
| F015 Snake Plant | #16 |
| F017 Olive Tree in Pot | #17 |
| F016 Monstera Floor Plant | #18 |
| `db/db.json` first cut | #19 |
| Storefront facets | #20 |
| condo_open_kitchen | #21 |
| glass_garden_room | #22 |
| bright_loft | #23 |
| beamed_fireplace_living | #24 |
| studio_pass_through | #25 |

PR #26 (`DB: full room data for frontend`) was still open after the rooms merged, and it is the only agent that should be editing `db/` until it lands or closes. Do not launch a second database agent on top of it.

## Verification before the PR

Each agent runs its own script, then the shared checker:

```bash
/tmp/blender-4.2.3-linux-x64/blender -b --factory-startup \
  --python <folder>/build.py -- --outdir <folder>

python3 .cursor/skills/blender-furniture-model/validate_model.py <folder>
```

The script must print the bbox and the triangle count. The checker must print `PASS` and exit 0. Warnings on the already merged folders are listed in the worker skills. A new folder should have none.

Then confirm:

- `git status` shows files only under that one folder
- no `*.blend1`
- `README.md` contains `](preview.png)`
- the PR body URL uses the branch that was just pushed, not `main`, and the path matches the folder

`validate_model.py --all` is for someone looking at the whole tree after merges, not for an agent that is supposed to stay inside one folder. It does not modify files. On the tree after PR #25 it reported `23 passed, 0 failed`.

## Timebox

The briefs said under 15 minutes. Ship a mesh whose bbox matches and whose parts read at a glance. The olive tree at 28,740 triangles and the condo kitchen at 4,664 triangles were still inside the budgets. An agent that is out of time should stop adding leaves and export.

Wall clock for the furniture wave was about 17:41–18:04 UTC, with PR #5 (the room and catalog) in the middle of it. The photo rooms followed the database, 18:36–18:51 UTC. Overlap worked. Shared-file edits would not have.

## Done

- [ ] Every agent has a different folder, written in the brief
- [ ] The brief points at the worker skill and at `brief-template.md`
- [ ] Nobody in the wave edits `README.md`, `catalog/`, `db/`, or `.gitignore` except the one agent assigned that file
- [ ] Database work waits until model PRs have merged, and it does not overlap an open `db/` PR
- [ ] Each PR title matches the forms above, the body has bbox, triangle count, and the raw preview URL
- [ ] Each agent ran `validate_model.py` on its folder and reported `PASS`
- [ ] Nothing was merged and nothing was pushed to `main` by those agents
