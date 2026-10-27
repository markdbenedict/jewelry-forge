# jewelry-forge

Parametric jewelry for resin printing and investment casting. nTop builds the geometry
headlessly (nTopCL), a Python package drives it and checks every export, Blender keeps the
organic sculpting and the silver product shot. Owner: Mark. Plan of record: `docs/plan.md`
(phases, gates, what exists, limitations, the next milestone, the real-check list); the
claude.ai doc "nTop Jewelry Skills — Development Plan" is its narrative companion.

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
  strokes, moving chain links ≥ 0.35 mm clearance. **Every engineering number - floors, metal
  densities, shrink, casting defaults, the sprue allowance - lives in
  `data/jewelry_tables.json`**, read by `ntopjewel.tables` and by `blender/jewelry_kit.py`
  (which carries an embedded copy a test keeps identical). Each entry says whether it is a
  `default` or `calibrated` (with a dated `calibration_log` entry); change numbers there,
  never in notebooks, skills or scripts.
- **One Output per notebook, and it is the volume** in mm³ - a Volume Integral of the
  constant 1 over the body (API-built notebooks; needs no density or unit), or Mass
  Properties' volume (GUI-built Phase 0). Files come out of Export Mesh / Export 3MF blocks
  fed by `file_path` inputs.

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
  `ntopcl` call: the runner enforces the JSON rules and runs the mesh gate. A run is headless
  and leaves only files (STL, log, report); **no notebook ever holds a particular ring**. To
  look at one in nTop, `ring ... --show` rebuilds the notebook with that ring's values in the
  open session (saved under `out\api\preview\`), or import the STL.
- **Run the mesh gate after every export** (`ntopjewel gate <file.stl> --expect ...`).
  Every check has a status - PASSED, FAILED or **INCOMPLETE** (it could not be measured: no
  rays came back, nTop reported no volume) - and a part's status is PASSED only when the
  nTop run succeeded and every hard check PASSED; INCOMPLETE is not a pass. The mandatory
  checks for a band or ring: watertight, winding, one shell, wall thickness, inner/outer Ø,
  width, volume (mesh vs nTop), **design volume (nTop vs the independent arithmetic in
  Python - the only check that catches a notebook building the wrong section)** and, when
  engraved, the pocket. The wall check casts rays only along radial/axial directions (letter
  walls and bead seams measure ribs and slivers, not walls), only between the bead rows, and
  not axially inside an engraving's span. Nothing is reported as finished until the status
  is PASSED.
- **Every variant and run has a distinct identity.** A stem is
  `ring_band_<profile>_<size>_w<width>_t<thickness>_<spec id>` (rings: `ring_<profile>_<features>_…`),
  the spec id being a hash of every number that defines the design, so two designs never share
  a file. Every run writes into a fresh `out\<family>\<stem>\<run id>\` directory and the
  export must have been written by that run (`runs.require_fresh`). The report JSON records
  the inputs, the notebook's sha256 and recipe, and the tool versions.
- Deliverables go to Mark's `OneDrive\Documents\Jewelry\<project>\<stem>\` only when the status
  is PASSED (`--deliver`; `runs.deliver` refuses anything else): the STL with the input JSON,
  the gate and build reports and `manifest.json`. `out/` is scratch and git-ignored.

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

## Notebook API rules (doc Oct 2026; console, SSH and discovery verified 2026-10-26 on nTop 6.3.3)

- The console is **View > Python Console** (Ctrl+`) inside nTop (present on Mark's licence).
  Everything is a method of `notebook` (`add_block`, `set_block_input`,
  `connect_block_property`, `append_to_list`, `add_real_variable`, `add_variable`,
  `move_block_to_input`, `set_block_as_output`, `block_state`, `save_notebook_as`,
  `export_as_recipe`, `paused_updates()` …).
- **Identifiers are snake_case + the input type list, sometimes a `[x.y.z]` version**:
  `boolean_subtract<blend_enum,real_field,implicit,list<implicit>>`,
  `boolean_intersect<blend_enum,real_field,list<implicit>>`, `offset_implicit<implicit,real_field>`,
  `mass_properties_from_body<implicit,real_field,real>`, `implicit_to_mesh<implicit,real,real,bool,bool>[2.5.0]`,
  `export_mesh<file_path,mesh,unit_length_enum>`, `torus<point,vector,real,real>` (Center, Axis,
  Radius, Torus Radius), `cylinder<point,point,real>`, `point<real,real,real>`,
  `remap_cylindrical_implicit<implicit,real>` (`Body`, `Y Mapping Length`), `twist<implicit,plane,real_field>`,
  `polar_array_implicit<implicit,real,integer,axis>` (`Body`, `Angular Spacing`, `Count`, `Axis`),
  `axis<point,vector>` (`Point`, `Vector`), `sphere<point,real>` (`Center Point`, `Radius`),
  `import_mesh<file_path,unit_length_enum>[1.1.0]` (`Path`), `implicit_from_mesh<mesh>` (`Mesh`),
  `core.var<integer>` for integer inputs. 6.3.3 lists 2273; `api build discover`
  dumps them with input names. **An unversioned identifier is version 1.0.0** - the original,
  usually deprecated definition (nTopCL: "Boolean Subtract version 1.0.0 is now deprecated …
  incorrect gradients when the Subtraction Bodies list contained a single body"); **take the
  highest `[x.y.z]`**: `boolean_subtract<…>[5.44.0]`, `boolean_intersect<…>[5.44.0]`,
  `mass_properties<implicit,real_field,real>[1.1.0]` (not `mass_properties_from_body`, 1.0.0).
- **Typed variables are blocks `core.var<real|text|file_path|implicit|…>`** with one input
  `Input`; bare `core.var` does not exist. `add_real_variable(name, v, "mm")` makes a
  `core.var<real>` whose id is the name; `add_variable(name)` makes `core.var_any<any>` with
  input `x`. `list_block_inputs` also lists the block's return value (`isReturnValue`).
- nTop's Python persists between runs, so the driver purges `ntopjewel*` from `sys.modules`
  before each run; without that an edited helper is not what runs.
- `set_block_input` cannot set a `file_path` parameter (6.3.3: "only real, vector, point,
  bool, integer and text"); a file input is a **`core.var<text>`** connected to the Export
  block's `Path`, which builds and which nTopCL types `text`.
- **Blocks build lazily.** A block nothing displays or consumes stays `e_DIRTY` forever and
  `block_state` cannot tell that from "queued"; the API has no build/evaluate call and
  `set_block_visibility` does not force one. What does make a measurement block build: a
  **typed consumer** - wrap it in a variable (`add_variable(name, block_id)`) and make that
  the Output (verified 2026-10-27: the volume integral built and returned 245.6 mm³ in the
  session). Still wait on the export block, and report a dirty measurement as a warning.
- Property names are lower case (`volume`, `mass`, `center of gravity`); match them
  case-insensitively. After `move_block_to_input(id)` the variable no longer answers
  `block_state` (its wires stay); the helper reports such ids as `input`.
- **A `real_field` input cannot be set at all** through `set_block_input` (`Density`, `Blend
  Radius`, `Distance`: 'has type "real_field", which cannot be set yet', with or without
  units). Feed it by **wiring a `core.var<real>`** into it (`add_real_variable` +
  `connect_block_property`), as the band does for the offsets.
- **Units are a per-notebook table.** A fresh notebook knows `mm` (its length unit) and
  nothing else: `add_real_variable(…, "kg/m3")` and `set_block_input_units` answer
  `"kg/m3" is not a unit this notebook knows`, although `get_block_input_units` spells the
  Density input exactly `kg/m3`. No API call registers a unit. `deg` IS known (angles work).
  So API-built notebooks use only mm and deg: volume = `volume_integral` of a unitless 1
  (inputs `Body`, `Integrand`), never Mass Properties.
- **What only nTopCL tells you about an API-built notebook** (a lazy block with no typed
  consumer never builds in the GUI session, so its input errors stay hidden): a required
  input with no default (`Input "Density" is incomplete`); a block added and never set
  (`Path_0`: `Input "Input" is incomplete`) - `h.remove()` it; an Output that is an untyped
  variable (`-t`: "Output of function not built") - make the Output typed (a variable
  wrapping the measurement block, or a `core.var<real>`). The runner's `templates` tolerates
  a missing output template; the first real run is the check.
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
| `.claude/skills/` | Skills: `ntop-automate`, `jewelry-design-rules`, `ring-band`, `ring-features` (more per phase) |
| `ntop/recipes/` | Build scripts (`<name>.py`, run through the Notebook API) + their exported `.recipe.json`; `*.md` are the GUI fallbacks |
| `ntop/blocks/` | Custom-block notebooks (`.ntop`), the library; nTop's My Blocks folder points here |
| `ntop/notebooks/` | Automate-ready runner notebooks, one per product family |
| `ntop/packages/` | `manifest.json` + README per block, nTop community-package layout |
| `ntop/ntop-beta-feedback.md` | What the Notebook API beta did and did not do for us, for nTop |
| `catalog/` | YAML schema of every runner notebook's inputs (types, units, ranges, defaults) |
| `data/jewelry_tables.json` | The one source of engineering numbers (metals, floors, casting, sprue allowance) with status and provenance, for Python and Blender |
| `docs/plan.md` | Plan of record: phases and gates, what exists, limitations, next milestone, real-check list |
| `python/ntopjewel/` | Runner, catalog validation, tables, mesh gate, run identity + delivery (`runs.py`), Notebook API client + `nb_jewel` build helpers, band/features specs, engraving meshes, CLI |
| `python/tests/` | pytest, offline: `fake_ntopcl.py` simulates nTop (builds the designed geometry, can be told to misbehave), `fake_notebook.py` the Notebook API; nTop runs would be marked `slow` |
| `python/constraints.txt` | The pinned, known-working dependency set (bootstrap and CI install with `-c`) |
| `.github/workflows/tests.yml` | The offline suite on every push and PR, Linux and Windows |
| `blender/` | `jewelry_kit.py`, `photo.py`, `forge_paths.py` (repo-relative paths, `JEWELRY_OUT`), the organic projects (pear rose ring; monstera band with its pure `leaf_design.py`) |
| `out/` | Scratch output, git-ignored: `out\<family>\<stem>\<run id>\` per run, `out\api\` for API builds, `out\blender\` for the Blender scripts |

## Commands

```powershell
# one-time
.\scripts\bootstrap.ps1          # venv, pip install -e python/ -c python/constraints.txt (pinned set), checks ntopcl, runs tests
.\scripts\setup-ntop-console.ps1 # SSH key for nTop's Python Console (Notebook API) + Documents\nTopScripts
# every day
.\.venv\Scripts\Activate.ps1
python -m ntopjewel doctor                      # finds ntopcl, nTop, Blender, printer folders
# authoring (nTop open with View > Python Console open)
python -m ntopjewel api check                                        # SSH to the console works?
python -m ntopjewel api build band_profile                           # writes ntop\notebooks\ring_band_profile.ntop
python -m ntopjewel api build ring_features --scratch                # Phase 1 step 2 notebook (prepare() writes the test engraving STL)
python -m ntopjewel api build band_profile --dry-run                 # driver to paste into the GUI console, then `api collect band_profile`
python -m ntopjewel api line "print(notebook.list_available_blocks('torus'))"
# running
python -m ntopjewel templates ntop\notebooks\ring_band_profile.ntop --catalog ring_band_profile
python -m ntopjewel band --size 6 --profile court --out out\band      # profiles: flat, comfort-flat, court, d-shape, half-round; files land in out\band\<stem>\<run id>\
python -m ntopjewel band --size 6 --profile court --dry-run           # the numbers the notebook will get
python -m ntopjewel ring --size 6 --profile court --milgrain --groove 0.25 --engrave "M+K 2026" --engrave-side inside --out out\ring   # --deliver copies a PASSED part + evidence to the Jewelry folder
python -m ntopjewel ring --size 4.5 --profile court --milgrain --groove 0.25 --engrave "Makena" --show   # that ring built in nTop's GUI session (out\api\preview), to look at
python -m ntopjewel gate out\band\<stem>\<run id>\<stem>.stl --expect-inner 16.51 --expect-width 4
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
- `ring-features` — milgrain, channel groove and wrapped engraving on a band (`ring` command).
- `blender-jewelry-render` (synced from claude.ai) — the silver product shot.
