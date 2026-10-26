# jewelry-forge

Parametric jewelry for resin printing and investment casting. nTop builds the geometry
headlessly (nTopCL), a Python package drives it and checks every export, Blender keeps the
organic sculpting and the silver product shot. Owner: Mark. Plan of record:
"nTop Jewelry Skills — Development Plan" (claude.ai doc).

## Conventions that must never drift

- **Units:** 1 unit = 1 mm everywhere (nTop notebooks, Blender scenes, Python, STL).
  Angles in degrees. Volumes in mm³, weights in grams.
- **Ring axis:** in nTop notebooks the ring axis is **Z** (band lies flat on XY; the Phase 0
  band spans z = 0 … Width, profile blocks from Phase 1 centre on the origin). In Blender scenes the ring axis is **Y** (ring stands upright on the
  floor); `blender/photo.py` assumes this. The mesh gate detects the axis from the mesh.
- **Ring sizing:** US size → inner diameter `11.63 + 0.8128 × size` mm. Other systems
  convert through `ntopjewel.tables`. Sizes are never typed into a notebook; Python
  computes radii and passes millimetres.
- **Minimum walls (resin print + casting):** 0.5 mm marginal, 0.75 mm good. Prong tips
  ≥ 0.8 mm diameter, milgrain beads ≥ 0.5 mm, engraving ≥ 0.25 mm deep with ≥ 0.3 mm
  strokes, moving chain links ≥ 0.35 mm clearance. Floors live in `ntopjewel/tables.py`;
  change them there, not in notebooks or skills.
- **One Output per notebook, and it is the volume** (Mass Properties, mm³). Files come out
  of Export Mesh / Export 3MF blocks fed by `file_path` inputs.

## How work gets done

- Custom blocks are authored by Mark in the nTop GUI from a written recipe in
  `ntop/recipes/`. Claude cannot see the nTop canvas; Claude writes the recipe, then
  drives and verifies the block through `ntopcl`. If a block needs a third GUI sitting,
  split it into two simpler blocks.
- **Never edit an `.ntop` file by hand or by script.** Change behaviour through inputs
  (JSON) or through a recipe revision Mark applies in the GUI.
- Every nTop run goes through `ntopjewel` (`python -m ntopjewel ...`), never a bare
  `ntopcl` call: the runner enforces the JSON rules and runs the mesh gate.
- **Run the mesh gate after every export** (`ntopjewel gate <file.stl> --expect ...`).
  Nothing is reported as finished until the gate passes.
- Deliverables (STL/3MF for printing) are copied to Mark's `OneDrive\Documents\Jewelry\<project>`
  folder, one file per size/variant; `out/` is scratch and git-ignored.

## nTopCL rules (verified 2026-10-25 on nTop 6.3.3, cloud licence, Mark's laptop)

- Invocation: `ntopcl -v 2 -j in.json -o out.json notebook.ntop` (`--logfile path` to keep
  the log; `-t notebook.ntop` writes `input_template.json` / `output_template.json`).
- A notebook with **no inputs** must be run **without `-j`**; nTopCL rejects an input JSON
  whose `inputs` list is empty (`[E]: JSON file has no inputs`).
- **Success = all three:** exit code 0, no `[E]` line in the log, and the line
  `nTop successfully built.` present. nTopCL can exit 0 after a failed block.
- Per-block timing lines look like `15:57:33 [I]: Sphere_0 complete 0ms`; the runner
  parses them into the report.
- Input types (Automate docs): `bool`, `scalar` (+ `units`), `integer`, `text`, `file_path`,
  `point`, `vector` (+ `units`, required for some vectors), `enum` (integer id). A scalar may
  carry `values: [..]` to sweep one parameter in a single run. **nTop's own `-t` template
  spells a scalar `real` and an export path `text`** (seen 2026-10-25); the runner copies
  the template's spelling, so never hand-write type names.
- Output JSON is a list of `{name, type, value, components}`; an `implicit` output comes
  back as base64; a `real` output is `{"val": <SI number>, "units": {"length": 3}, "isFinite": true}`
  (metres, kilograms); `ntopcl.scalar_value` converts to mm / g.
- **Mesh from Implicit Body `Tolerance` = 2 × voxel size**, triangle count ∝ 1/tolerance².
  Default 0.1 mm (50 µm voxels). 0.01 mm produced a 57 M-triangle, 2.7 GB band STL.

## Repo map

| Path | What |
| --- | --- |
| `.claude/skills/` | Skills: `ntop-automate`, `jewelry-design-rules`, `ring-band` (more per phase) |
| `ntop/recipes/` | GUI build recipes for custom blocks and runner notebooks |
| `ntop/blocks/` | Custom-block notebooks (`.ntop`), the library; nTop's My Blocks folder points here |
| `ntop/notebooks/` | Automate-ready runner notebooks, one per product family |
| `ntop/packages/` | `manifest.json` + README per block, nTop community-package layout |
| `catalog/` | YAML schema of every runner notebook's inputs (types, units, ranges, defaults) |
| `python/ntopjewel/` | Runner, catalog validation, tables, mesh gate, CLI |
| `python/tests/` | pytest; offline by default, nTop runs are marked `slow` |
| `blender/` | `jewelry_kit.py`, `photo.py` and the organic projects (pear rose ring, monstera band) |
| `out/` | Scratch output, git-ignored |

## Commands

```powershell
# one-time
.\scripts\bootstrap.ps1          # venv, pip install -e python/, checks ntopcl, runs tests
# every day
.\.venv\Scripts\Activate.ps1
python -m ntopjewel doctor                      # finds ntopcl, nTop, Blender, printer folders
python -m ntopjewel templates ntop\notebooks\ring_band.ntop
python -m ntopjewel band --size 6 --width 4 --thickness 1.3 --out out\band
python -m ntopjewel gate out\band\ring_band_US6.stl --expect-inner 16.51 --expect-width 4
pytest python\tests -q                          # offline tests
pytest python\tests -q -m slow                  # tests that run nTop
```

## Machines

- Main laptop (Windows, RTX 5070 Ti 16 GB, 32 GB RAM, ~21 GB in use day to day): nTop 6.3.3,
  Blender 5.2.2, Claude Code. Close Blender and the browser before large runs.
- Second laptop (128 GB RAM, not portable): candidate build server for casting trees if a
  run exceeds 32 GB. nTop cloud licence allows one named user on up to three devices.
- `ntopcl.exe` default path: `C:\Program Files\nTopology\nTopology\ntopcl.exe`
  (override with the `NTOPCL` environment variable).

## Skills to reach for

- `ntop-automate` — anything that runs a notebook, builds input JSON or reads a log.
- `jewelry-design-rules` — sizes, walls, prongs, bezels, chains, casting numbers.
- `ring-band` — the band family (Phase 0 hello band, profiles from Phase 1).
- `blender-jewelry-render` (synced from claude.ai) — the silver product shot.
