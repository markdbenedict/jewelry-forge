# jewelry-forge

Parametric jewelry for resin printing and investment casting. nTop builds the geometry
headlessly (nTopCL), a Python package drives it and checks every export, Blender keeps the
organic sculpting and the silver product shot. Owner: Mark. Plan of record:
"nTop Jewelry Skills — Development Plan" (claude.ai doc).

## Conventions that must never drift

- **Units:** 1 unit = 1 mm everywhere (nTop notebooks, Blender scenes, Python, STL).
  Angles in degrees. Volumes in mm³, weights in grams.
- **Ring axis:** in nTop notebooks the ring axis is **Z**, band centred on the origin (z = ±W/2;
  only the Phase 0 hello band spans z = 0 … W). In Blender scenes the ring axis is **Y** (ring stands upright on the
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

- Notebooks and custom blocks are **authored through nTop's Notebook API** (Private Beta,
  nTop 6.3+, package v0.14): a build script `ntop/recipes/<name>.py` with
  `build(notebook, params)` runs inside nTop's Python Console. `python -m ntopjewel api build
  <name>` sends it over SSH (localhost:2222, key `~/.ssh/id_ntopcli`), saves the `.ntop`,
  exports the JSON recipe next to the script and reports every block's build state and the
  identifiers it resolved. Claude cannot see the nTop canvas; the GUI is for Mark to review
  the result and for the few things the API cannot do. The `*.md` recipes are the fallback
  when a script cannot run (no beta permission, no console).
- **Never edit an `.ntop` file by hand or by text/script.** The file is nTop's. Change it
  through the API (`notebook.*` calls in a build script), through the GUI, or through
  inputs (JSON) at run time.
- Block identifiers (`cylinder<point,point,real>`) and input names are resolved at run time
  (`list_available_blocks`, `list_block_inputs`) and recorded in the build result. A guess
  that failed is fixed in the script's candidate list, never patched in the GUI.
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

## Notebook API rules (from nTop's doc, Oct 2026; not yet exercised on Mark's laptop)

- The console is **View > Python Console** (Ctrl+`) inside nTop; it exists only with the
  Private Beta (Early Access) licence permission. Everything is a method of `notebook`
  (`add_block`, `set_block_input`, `connect_block_property`, `append_to_list`,
  `add_real_variable`, `add_variable`, `move_block_to_input`, `set_block_as_output`,
  `block_state`, `save_notebook_as`, `export_as_recipe`, `paused_updates()` …).
- SSH: `ssh -tt -i ~\.ssh\id_ntopcli -p 2222 localhost` while the console panel is open.
  Key-based only; `authorized_keys` written as ASCII (no BOM), owner-only. **One line per
  send**; a script is run as `exec(open(r"...driver.py").read())`; **Ctrl+C ends the
  session, never `exit()`**. `ntopjewel.notebook_api.Console` does all of this.
- `add_block` returns `{name, id, funcId}`; use the returned id, never the display name.
  A block output used twice goes through a variable. Variables are notebook inputs once
  `move_block_to_input` is called; one `set_block_as_output`.
- Bad inputs fail at **build** time: check `block_state(id)["buildState"]` is `e_OK`
  (`e_FAILED` carries `error`); do not trust a call that returned without raising.
- `new_notebook()` discards the open notebook; `save_notebook_as` / `export_as_recipe`
  overwrite silently. Build scripts default to a fresh notebook and save into the repo.
- Scripts run unsandboxed with Mark's privileges on a local-only endpoint; nothing of
  Mark's work goes anywhere but his disk. Beta findings go in `ntop/ntop-beta-feedback.md`.

## Repo map

| Path | What |
| --- | --- |
| `.claude/skills/` | Skills: `ntop-automate`, `jewelry-design-rules`, `ring-band` (more per phase) |
| `ntop/recipes/` | Build scripts (`<name>.py`, run through the Notebook API) + their exported `.recipe.json`; `*.md` are the GUI fallbacks |
| `ntop/blocks/` | Custom-block notebooks (`.ntop`), the library; nTop's My Blocks folder points here |
| `ntop/notebooks/` | Automate-ready runner notebooks, one per product family |
| `ntop/packages/` | `manifest.json` + README per block, nTop community-package layout |
| `ntop/ntop-beta-feedback.md` | What the Notebook API beta did and did not do for us, for nTop |
| `catalog/` | YAML schema of every runner notebook's inputs (types, units, ranges, defaults) |
| `python/ntopjewel/` | Runner, catalog validation, tables, mesh gate, Notebook API client, CLI |
| `python/tests/` | pytest; offline by default, nTop runs are marked `slow` |
| `blender/` | `jewelry_kit.py`, `photo.py` and the organic projects (pear rose ring, monstera band) |
| `out/` | Scratch output, git-ignored |

## Commands

```powershell
# one-time
.\scripts\bootstrap.ps1          # venv, pip install -e python/, checks ntopcl, runs tests
.\scripts\setup-ntop-console.ps1 # SSH key for nTop's Python Console (Notebook API) + Documents\nTopScripts
# every day
.\.venv\Scripts\Activate.ps1
python -m ntopjewel doctor                      # finds ntopcl, nTop, Blender, printer folders
# authoring (nTop open with View > Python Console open)
python -m ntopjewel api check                                        # SSH to the console works?
python -m ntopjewel api build band_profile                           # writes ntop\notebooks\ring_band_profile.ntop
python -m ntopjewel api build band_profile --dry-run                 # driver to paste into the GUI console, then `api collect band_profile`
python -m ntopjewel api line "print(notebook.list_available_blocks('torus'))"
# running
python -m ntopjewel templates ntop\notebooks\ring_band_profile.ntop --catalog ring_band_profile
python -m ntopjewel band --size 6 --profile court --out out\band      # profiles: flat, comfort-flat, court, d-shape, half-round
python -m ntopjewel band --size 6 --profile court --dry-run           # the numbers the notebook will get
python -m ntopjewel gate out\band\ring_band_court_US6.stl --expect-inner 16.51 --expect-width 4
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
- Notebook API on both laptops: SSH key `~\.ssh\id_ntopcli` (override `NTOP_SSH_KEY`), own
  console scripts in `Documents\nTopScripts\` (create before starting nTop); driver files
  the CLI writes live in `out\api\`.

## Skills to reach for

- `ntop-automate` — anything that runs a notebook, builds input JSON, reads a log, or
  authors a notebook through the Notebook API.
- `jewelry-design-rules` — sizes, walls, prongs, bezels, chains, casting numbers.
- `ring-band` — the band family (Phase 0 hello band, profiles from Phase 1).
- `blender-jewelry-render` (synced from claude.ai) — the silver product shot.
