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
  strokes, a raised line in relief ≥ 0.15 mm wide, moving chain links ≥ 0.35 mm clearance. **Every engineering number - floors, metal
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
  checks for a band or ring: watertight, winding, one shell (the mesher's zero-volume bubbles
  counted apart, see the nTopCL rules), wall thickness, inner/outer Ø,
  width, volume (mesh vs nTop), **design volume (nTop vs the independent arithmetic in
  Python - the check that catches a notebook building the wrong section)**, **section shape
  (the built outline against the designed section at 12 angles: an edge left sharp, a missing
  strand, a wrong wrap; the whole mesh tolerance through a trinity knot, whose step creases the
  mesher fills by a voxel per round trip)** and, when engraved, the pocket. The wall check casts rays only along radial/axial directions (letter
  walls and bead seams measure ribs and slivers, not walls), only between the bead rows, and
  not axially inside an engraving's span, and drops a ray that leaves through a face at a grazing angle (a sharp edge's corner, not a wall); fewer than 1000 usable rays is INCOMPLETE (p1 of a
  few hundred rays is not a measurement). The ring axis is the one whose centre line passes
  through the bore (a band wider than its diameter keeps its axis). Nothing is reported as
  finished until the status is PASSED.
- **Every command ends with one verdict line** (`summary.verdict`): `==> PASSED <stem>`, `==> FAILED
  <stem>: <failing checks>`, or `==> ERROR <what>: <why>` when nothing was built; green / red /
  yellow on a console that shows colour. `python -m ntopjewel runs` tabulates every run's report
  in `out\` - read that, not the scroll-back, after a batch.
- **A notebook must be at least as new as its catalog says** (`rebuild_since` in the catalog,
  `runs.require_built`): `api build` writes `ntop\notebooks\<name>.build.json` (the catalog
  versions it was built for, the notebook's sha256) and a run of a catalog's own notebook is
  refused, naming the `api build` to run, when the stamp is missing or older than
  `rebuild_since`. Bump `rebuild_since` with every notebook-body change, inputs changed or not
  (2026-11-02: a notebook a commit behind ran and one design failed for it). **Commit the stamp;
  the notebook itself is not in git** (`ntop/notebooks/*.ntop` ignored since 2026-11-03: the
  solitaire notebooks reached 230 MB, past GitHub's 100 MB limit; a fresh checkout runs the
  `api build`s). The block library `ntop/blocks/*.ntop` (small) is tracked.
- **Every variant and run has a distinct identity.** A stem is
  `ring_band_<profile>_<size>_w<width>_t<thickness>_<spec id>` (rings: `ring_<profile>_<features>_…`),
  the spec id being a hash of every number that defines the design, so two designs never share
  a file. Every run writes into a fresh `out\<family>\<stem>\<run id>\` directory and the
  export must have been written by that run (`runs.require_fresh`). The report JSON records
  the inputs, the notebook's sha256 and recipe, and the tool versions.
- **A stem appears twice in every run file's path** (`out\<family>\<stem>\<run id>\<stem>.print_sterling.stl`),
  and a solitaire's is up to 90 characters, so a deep `--out` passes Windows' MAX_PATH (260) and a build
  dies mid-way with FileNotFoundError (2026-11-03, pytest's temp dir). `runs.fresh_run_dir` refuses such a
  run before making anything (`RunPathError`, an `==> ERROR`) unless the LongPathsEnabled policy is on
  (`doctor` shows it; whether nTopCL honours it is unverified); tests use the `out_dir` fixture, which
  stays short on Windows.
- Deliverables go to Mark's `OneDrive\Documents\Jewelry\<project>\<stem>\` only when the status
  is PASSED (`--deliver`; `runs.deliver` refuses anything else): the STL with the input JSON,
  the gate and build reports and `manifest.json`. `out/` is scratch and git-ignored.
- **Shrink is a scale, allowance is fit.** Casting and resin shrink are isotropic (width,
  thickness and seats shrink too), so they are never folded into `allowance_mm`. Every part is
  designed and gated at its finished size; `--deliver --metal sterling` adds
  `<stem>.print_sterling.stl`, the design scaled about the origin by `tables.print_scale`
  (metal + resin shrink), with the factor and the calibration state of both figures in the
  manifest. `allowance_mm` stays the mandrel/comfort adjustment.

## nTopCL rules (verified 2026-10-25 on nTop 6.3.3, cloud licence, Mark's laptop)

- Invocation: `ntopcl -v 2 -j in.json -o out.json notebook.ntop` (`-t notebook.ntop` writes
  `input_template.json` / `output_template.json`). **`--logfile path` is not accepted** (exit code 1
  at once, 2026-11-03): the runner keeps the log from stdout.
- A notebook with **no inputs** must be run **without `-j`**; nTopCL rejects an input JSON
  whose `inputs` list is empty (`[E]: JSON file has no inputs`).
- **Success = all three:** exit code 0, no `[E]` line in the log, and the line
  `nTop successfully built.` present. nTopCL can exit 0 after a failed block.
- Per-block timing lines look like `15:57:33 [I]: Sphere_0 complete 0ms`; the runner
  parses them into the report. `ntopcl.run` streams nTopCL's stdout into `<tag>.ntopcl.log` as it
  goes (`Get-Content -Wait -Tail 3` it during a long run; nTopCL's stdout is block-buffered, so
  the file can lag by a few KB), kills nTopCL after `NTOPCL_TIMEOUT_S` (3600) naming the last block
  that completed (`==> ERROR`), and kills it on Ctrl+C (the child has no console window;
  2026-11-03: a solitaire run killed after an hour had left no log at all).
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
- **Import Mesh's `[W] Mesh_0: Duplicate and/or very close vertices have been merged` is routine**
  (an STL is a triangle soup); `[W] Mesh_0: Output Mesh is self-intersecting` is the one that
  matters, and Implicit Body from such a mesh built the trinity shank in five shells (2026-11-01/02).
  The cause: a mesh union (manifold3d) of bodies that cross each other leaves faces micrometres
  apart along its seams (sub-µm at seam corners), which float32 STL (±2 µm at y ≈ 60) and the
  import turn into intersections - no cleaning fixes that (`geom.clean` merges coplanar facets into
  mm-long triangles, which a vertex-wise unwrap turns into self-intersections; the edge collapse
  helps nothing). **So no bar carries a mesh union**: bodies that cross each other go to nTop in
  separate bars (`ShankSpec.bar_meshes`, `Shank Path` .. `Shank Path 4`; an unused slot imports the
  smallest bar again - a speck in its place vanished under the opening's erosion and nothing
  downstream built, 2026-11-02) and nTop's Boolean Union joins the implicits; pieces that continue
  each other overlap by a 0.1 mm plug, never share a face. The simulated nTop unites the wrapped
  bars in the ring frame (`shank.bars_from_inputs`). Verified 2026-11-02: the trinity shank, the
  trinity solitaire and the plait all built in one shell.
- **Open each bar on its own, then unite** (`nj.add_wrapped_shank`, one `open_bar` block per bar): a Boolean Union's field is the
  minimum of its bodies' fields, so inside an overlap it measures to a body's buried face, and the
  opening's erosion cut a 0.05 mm groove along a split's seam all round the bottom (2026-11-02,
  the halves' overlap wedge). Same rule as the arches: open apart, unite afterwards. **And bodies
  that overlap must overlap by more than the edge round**: the opening rounds the edge where a
  body's cut face meets the surface, starting the edge round back from the cut, so a 0.1 mm
  overlap under a 0.25 mm round still left the halves' quarter-rounds meeting in a 0.055 mm groove
  (2026-11-03, opened per bar; `ShankSpec.split_overlap_mm` = edge round + mesh tolerance).
- **A mesh Python wraps for nTop must be clean before and after the wrap**: never refine a mesh in 3-D
  with trimesh's `subdivide_to_size` (a triangle soup with T-junctions, which the cylindrical wrap bends
  into piercings: nTop read the artwork cutters as self-intersecting and left 0.013 mm needles on the
  faces, 2026-11-03), and never warp a cap triangulated by earcut (its slivers fold under the chord sag
  c²/8r: 96 crossing pairs in the leaves). Build structured meshes instead: boxes lofted station by
  station (`artwork.prism_along_y`, `swept_slit`), outlines densified in 2-D and capped by the constrained
  Delaunay in `artwork.quality_triangulate` (`radial_prism`, `axial_prism`). Every layer is read back
  from its STL and refused if `geom.intersecting_faces` finds a pair (`ArtworkSpec.write_layers`).
- **Mesh from Implicit Body leaves 12-face bubbles of no volume where two surfaces kiss** (a
  ribbon's rounded corner passing another's at a fused crossing, a rail's foot on the band's dome
  inside the blend): 2 on the plait, 7 on the trinity solitaire (2026-11-02). The gate counts a
  closed component under `gate.SPECK_VOLUME_MM3` (1e-6 mm³, a 10 µm cube) as a degenerate speck,
  reported beside the shell count, not as a shell; a 0.05 mm bead adrift (5e-4 mm³) still counts.

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
- **A build script runs in nTop's own Python, which has none of this package's dependencies** (no
  yaml, numpy, trimesh, shapely): at module level a recipe imports only `nb_jewel`, `notebook_api` and
  the console-safe `nb_*` modules; anything heavier goes inside `prepare()` (laptop side). 2026-11-03:
  `api build multistone` failed in nTop with "No module named 'yaml'"; `tests/test_console_safe.py`
  now imports every recipe (and builds the newer ones) in a Python where those packages are blocked.
- nTop's Python persists between runs, so the driver purges `ntopjewel*` from `sys.modules`
  before each run; without that an edited helper is not what runs.
- `set_block_input` cannot set a `file_path` parameter (6.3.3: "only real, vector, point,
  bool, integer and text"); a file input is a **`core.var<text>`** connected to the Export
  block's `Path`, which builds and which nTopCL types `text` (`nj.path_variable` makes the text
  variable directly; it no longer probes `core.var<file_path>` first, which printed a fallback
  per path on every build).
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
- **Custom blocks work through the API** (verified 2026-10-28, `custom_block_probe`): a notebook
  saved with inputs (`move_block_to_input`) and one Output IS a custom block. In a user notebook,
  `embed_custom_block(path)` reads it in (no dialog; again for the same path replaces the copy;
  **refused while `paused_updates()` is held**), `list_custom_blocks()` then gives
  `{name, id, bufferId}` where `name` is the file stem and `id` the identifier
  `user_func_<uuid><input types>` that `add_block` takes; the instance's inputs keep the block's
  input names. Resolve the identifier by name from `list_custom_blocks()`, never hard-code it.
  `open_custom_block(name)` takes the display name, not an instance id. The Output's type is the
  variable's (`core.var<sphere>` for a sphere): wrap a block's body as `core.var<implicit>` when
  consumers expect an implicit. Library blocks live in `ntop/blocks/<name>.ntop`; runners embed them. **A block takes
  another block's result as an implicit input (`core.var<implicit>`, declared as an input) instead of embedding it**:
  that keeps each block small and lets a bezel reuse the seat. (The refusals that led here came from a
  shared block output, not from nesting - see the variable rule below.) Combinations
  in a block notebook may stay `e_DIRTY` in the GUI (`nj.settle` saves anyway; nTopCL is the test), and every
  block build ends by embedding the saved block in a fresh notebook (self-test).
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
- **nTop runs its Python at a crawl unless its window has the focus** (2026-11-03: four builds
  took all night in the background - one API call every 20 minutes - then all four finished in
  eight minutes when Mark switched to nTop). Keep nTop in the foreground while `api build` runs.
  A build script runs inside nTop's Python and outlives the client's timeout, so a timed-out
  build keeps going in there and later builds queue behind it; `api build` refuses to start
  unless the console answers within 45 s. A build that finished after its client gave up is
  collected and stamped with `api collect <recipe>` (its result.json says whether every block
  built and the notebook was saved).
- SSH: `ssh -tt -i ~\.ssh\id_ntopcli -p 2222 localhost` while the console panel is open.
  Key-based only; `authorized_keys` written as ASCII (no BOM), owner-only. **One line per
  send**; a script is run as `exec(open(r"...driver.py").read())`; **Ctrl+C ends the
  session, never `exit()`**. `ntopjewel.notebook_api.Console` does all of this.
- `add_block` returns `{name, id, funcId}`; use the returned id, never the display name. **Never label a
  block with a name already used** (an input variable's especially): `NotebookHelper.add` refuses it, since
  the later block takes the name over and `finish` then makes it the notebook input (2026-11-03: rotation
  blocks "Spin 2" / "Turn 2" shadowed slot 2's inputs).
  **A block output used twice goes through a variable** (`h.wrap_var`) - in a custom block this is
  not style but validity: a block notebook in which one Point fed both a cylinder and a sphere was
  refused by `embed_custom_block` ("Not a valid custom block"; bisected 2026-10-28). Variables may
  feed any number of inputs. Variables are notebook inputs once
  `move_block_to_input` is called; one `set_block_as_output`.
- **Recipes are written in `nj.Helper` verbs** (2026-11-04): `h.union / intersect / subtract / offset /
  import_body / mesh / remap_cylindrical / rotation / transform / cylinder / torus / sphere / polar_array`,
  one call per block, each wiring its inputs by nTop's names; a recipe declares its inputs as `SPECS`
  (`nj.add_typed_inputs`) and ends in `nj.standard_build` (runners) or `nj.block_build` + `nj.save_block`
  (library blocks; `nj.seat_head_harness` for a head's harness). Labels say what a block is (`Bar 2 Opened`,
  `Head 3 On Ring`, `Band Eroded` / `Band Re-distanced`). **A runner notebook reads as an outline**: blocks go
  into named sections (`with h.section("Shank"):`), `h.comment` notes why a junction is where it is (the
  opening, seats cut after the blended join), and `finish` collapses every section but the last. Block
  notebooks get no sections (nothing untried in a custom block). Sections and comments are layout only,
  and every call is guarded (a refusal is logged and the build carries on without them). 6.3.3's real
  signatures (logged 2026-11-04): `add_section(section_name, before_section_id='') -> dict`, `add_block(ident,
  section_id)`, `set_block_comment(block_id, block_comment)`, `collapse_section(section_id='')`, and
  **`move_block(block_id, targetBlockId, placeBefore=False)` moves a block NEXT TO a top-level block** - a
  section id there is 'No block with the id "section_3"', a block inside a section 'is not a top level block'.
  So `add_block(ident, section_id)` and `add_real_variable(name, value, units, section_id)` put blocks and
  real variables in a section, and a wrapping variable (`add_variable(name, block_id)`, no section) stays
  at the notebook's top level (`Helper.place` notes it once).
- **Shank bars are opened by the `open_bar` library block** (2026-11-04, `ntop/blocks/open_bar.ntop`: Bar
  Path, Edge Round Inward, Edge Round, Mesh Tolerance -> Opened Bar; import, -e, re-distance, +e inside):
  every runner with a shank embeds it once and places one per bar slot (`add_wrapped_shank(..., opener=)`),
  six blocks per bar become one. Rebuild the runners after changing it (`api build open_bar` first).
- **Combine Transforms' list order is measured, not assumed**: nTop's block page does not say which end of
  the list applies first, and multistone's heads land by it (measured 2026-11-04: **list order**, the first
  applied first; Mirror Body correct). `api build transform_probe` measures it (and
  that Mirror Body across a Plane - Origin, X axis, Y axis - lands where it should) in the session and writes
  `ntop/api_facts.json` (committed); `Helper.combine(label, [first, second, ...])` lays the list out to match
  and refuses, naming the probe, without the file. Each multistone slot is one placement (spin, quarter-turn,
  turn) for the head and its seat.
- **A symmetric body is a half and its mirror** (`Helper.mirror`, `nb_solitaire.mirror_plane`: the plane y = 0):
  the gothic arch is its +y half ∩ the half's mirror, the -y bead rows the +y rows' mirror - so the "Minus"
  inputs are gone (solitaire 0.11.0). The independent model builds the same (arch and bead volumes identical
  to the µm before and after, 2026-11-04). The knots are not mirrored in nTop: Python writes them.
- **Blends**: Boolean Union / Intersect take `Blend Radius` (a `real_field`: wire a `core.var<real>`,
  `nj.wire_blend`); the Blend Type enum stays at nTop's default. A smooth union fills every corner two
  surfaces make within its radius, so **the seat and the engraving are subtracted after the blended
  join**, never before. The independent model is unblended; the gate expects design + `blend_volume_factor`
  x r² x exposed junction length (calibrated 2026-10-30: 0.32; a blended intersection's edges count
  against), and a blended intersection may shrink a part's extents by the blend radius. The builders in
  `heads` / `solitaire` take a `geom.Booleans` (sharp by default); the simulated nTop passes
  `tests/pseudo_blend.Blended`, which lays the blend's volume along the junctions as geometry.
  **Never give a blended union two bodies that overlap or meet on a face**: its smooth minimum of a body with
  itself stands about a quarter of the radius outside it (the outline head's Basket unites the prongs and both
  rails in one blended union; a pearl's cup given as both rails came out 0.08 mm thick all over, +9.6 %,
  2026-11-05). A one-rail head sends the other slab to `heads.EMPTY_RAIL`. **And a blended intersection rounds
  an acute edge back further than one radius**: a rail following a steep pavilion lost 0.215 mm a side along the
  finger (the asscher solitaire), so the extents allowance is two of `OutlineHeadSpec.rail_corner_shrink`.
- **Offset Body adds a constant to the field; it does not re-distance.** Two offsets back to
  back (-e then +e, the opening that rounds every convex edge) cancel exactly - five band
  profiles matched their UNopened sections to 0.05 % (2026-10-30): no edge round was ever built
  before that date. `nj.add_opening` re-distances between them with a mesh round trip (Mesh from
  Implicit Body at the notebook's tolerance -> Implicit Body from Mesh); every band, solitaire
  and shank notebook now carries it. The re-distance mesh chamfers the eroded body's sharp
  corners by about a voxel (half the Mesh Tolerance), so the round comes out fuller than e: the
  models emulate it (`geom.open_polygon`, `tables.opening_chamfer_mm`, calibrated 2026-10-31:
  the court band then matches to 0.00 %). **Open each body on its own and unite afterwards**:
  opening the union of the band and its arches grew a 0.07 mm layer over the arch feet, where
  the arch dome lies on the band's dome. The gate's **section shape** check (the built outline
  at 12 angles against the designed 2-D section, Hausdorff within 0.03 mm or half the mesh
  tolerance) is what catches an edge left sharp; a design-volume tolerance did not. Inside an
  artwork panel it compares only the band's core below the channel floors (`section_clip`): a
  relief edge lying on the section plane read as the relief's whole height (0.243 mm at 91° on the
  Seraphine solitaire, every built point within 0.008 of the design, 2026-11-03); the panel probes
  cover the relief. **A smooth union bulges a surface that another body's metal approaches within
  the blend radius**: the solitaire's lower rail 0.2 mm above a flat band's bore pushed the bore
  36 µm inward under the head (2026-11-03; a court band's comfort relief had kept its rail away),
  so the solitaire's `bore` check measures outside the head's zone and `bore under the head` allows
  `BLEND_BORE_BULGE` x the shank blend, with a note naming the `--finger-clear` that would clear it.
  **And it lays a fillet round the head's foot on the band's face**, reaching about the blend radius past
  the head's metal: 0.25 mm high where the upper rail's rounded flank overhangs the face (2026-11-04, the
  Seraphine's first knotted run: 4 `knot surround` probes read it). The knot's apex stands at the fillet's
  toe by design (`KNOT_HEAD_CLEAR_MM`), so the surround probes begin past `knot_face_from_mm` (the head's
  reach at the face + the shank blend); every probe check's detail now names where its worst probe lies.
- Bad inputs fail at **build** time: check `block_state(id)["buildState"]` is `e_OK`
  (`e_FAILED` carries `error`); do not trust a call that returned without raising.
- `new_notebook()` discards the open notebook; `save_notebook_as` / `export_as_recipe`
  overwrite silently. Build scripts default to a fresh notebook and save into the repo.
- Scripts run unsandboxed with Mark's privileges on a local-only endpoint; nothing of
  Mark's work goes anywhere but his disk. Beta findings go in `ntop/ntop-beta-feedback.md`.

## Repo map

| Path | What |
| --- | --- |
| `.claude/skills/` | Skills: `ntop-automate`, `jewelry-design-rules`, `ring-band`, `ring-features`, `gem-library` (more per phase) |
| `ntop/recipes/` | Build scripts (`<name>.py`, run through the Notebook API) + their exported `.recipe.json`; `*.md` are the GUI fallbacks |
| `ntop/blocks/` | Custom-block notebooks (`.ntop`), the library; nTop's My Blocks folder points here |
| `ntop/notebooks/` | Automate-ready runner notebooks, one per product family |
| `ntop/packages/` | `manifest.json` + README per block, nTop community-package layout |
| `ntop/api_facts.json` | What `transform_probe` measured in nTop (Combine Transforms' order, Mirror Body); the recipes read it |
| `ntop/ntop-beta-feedback.md` | What the Notebook API beta did and did not do for us, for nTop |
| `catalog/` | YAML schema of every runner notebook's inputs (types, units, ranges, defaults) |
| `data/jewelry_tables.json` | The one source of engineering numbers (metals, floors, casting, sprue allowance) with status and provenance, for Python and Blender |
| `docs/plan.md` | Plan of record: phases and gates, what exists, limitations, next milestone, real-check list |
| `python/ntopjewel/` | Runner, catalog validation, tables, mesh gate, run identity + delivery (`runs.py`), Notebook API client + `nb_jewel` build helpers (incl. the generic block `harness`), band/features specs, engraving meshes, stones and seats (`gems.py`: the faceted shapes incl. the asscher, a cabochon, a half-drilled pearl), prong heads incl. outline heads for fancy stones and bezels (`heads.py`), partial bezels - two walls and a hood over each point, built in nTop from primitives (`partial_bezel.py`), pavé layouts, seats and beads (`pave.py`), multi-stone rings (`multistone.py`: heads spun, placed and turned, side angles solved), artwork on the band (`artwork.py`: 2-D motifs in relief in sunk panels on any face, built in the bar frame and wrapped; under a solitaire's head too), knot ornaments standing on a band (`ornament.py`: a closed trinity knot woven in two pieces on the outer face, wider than the band - the Seraphine's shoulders), the solitaire assembly (`solitaire.py`, notebook body `nb_solitaire.py`; its shank a bar from `shank.py`, carved by the artwork before the arches and the head join it), shaped shanks (`shank.py`: the ring unrolled as a bar for nTop to wrap), Celtic knotwork (`knotwork.py`: strands interlaced in the ring's surface - crossings incl. self-crossings, the alternating over/under, the radial laws, the trefoil motif, ribbon sweeps that share rings and caps), surface textures (`texture.py`: a hammered band - seeded strikes of one hammer face, gated against the band less the spheres), shared independent geometry (`geom.py`), CLI |
| `python/tests/` | pytest, offline: `fake_ntopcl.py` simulates nTop (builds the designed geometry with `pseudo_blend.py`'s blended booleans, can be told to misbehave), `fake_notebook.py` the Notebook API; nTop runs would be marked `slow` |
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
python -m ntopjewel api build stone_seat                             # library block ntop\blocks\stone_seat.ntop + its harness ntop\notebooks\stone_seat_harness.ntop
python -m ntopjewel api build prong_head                             # ntop\blocks\prong_head.ntop (seat cutter as an input) + ntop\notebooks\prong_head_harness.ntop (embeds stone_seat + prong_head)
python -m ntopjewel api build solitaire                              # ntop\notebooks\solitaire.ntop: band (carved by the artwork layers) + embedded seat and head, gothic arches + arch milgrain
python -m ntopjewel api build outline_head                           # ntop\blocks\outline_head.ntop (prongs on any outline, rails following the pavilion) + its harness
python -m ntopjewel api build solitaire_outline                      # ntop\notebooks\solitaire_outline.ntop: the solitaire with the outline head (pear ...)
python -m ntopjewel api build bezel_head                             # ntop\blocks\bezel_head.ntop (wall + cup round any outline, light windows) + its harness
python -m ntopjewel api build solitaire_bezel                        # ntop\notebooks\solitaire_bezel.ntop: the solitaire with the bezel
python -m ntopjewel api build partial_bezel_head                     # ntop\blocks\partial_bezel_head.ntop (two walls on the flanks, a hood over each point; nTop primitives) + its harness
python -m ntopjewel api build solitaire_partial_bezel                # ntop\notebooks\solitaire_partial_bezel.ntop: the solitaire with the partial bezel
python -m ntopjewel api build transform_probe                        # measures Combine Transforms' list order + Mirror Body in the session -> ntop\api_facts.json (commit it)
python -m ntopjewel api build open_bar                               # ntop\blocks\open_bar.ntop (one bar imported + opened by the edge round) + its harness; every shank runner embeds it
python -m ntopjewel api build ring_shank                             # ntop\notebooks\ring_shank.ntop: a shaped shank from the bars Python writes, united in nTop (prepare() writes the test bar)
python -m ntopjewel api build pave_band                              # ntop\notebooks\pave_band.ntop: the shank + the seats and beads Python writes, (shank ∪ beads) − seats
python -m ntopjewel api build multistone                             # ntop\notebooks\multistone.ntop: five outline-head slots spun, placed and turned round the shank (embeds stone_seat + outline_head), pavé beads and seats round the rest
python -m ntopjewel api build ring_artwork                           # ntop\notebooks\ring_artwork.ntop: the shank − the panel channels Python writes ∪ the relief motifs
python -m ntopjewel api build band_profile --dry-run                 # driver to paste into the GUI console, then `api collect band_profile`
python -m ntopjewel api line "print(notebook.list_available_blocks('torus'))"
# running
python -m ntopjewel templates ntop\notebooks\ring_band_profile.ntop --catalog ring_band_profile
python -m ntopjewel band --size 6 --profile court --out out\band      # profiles: flat, comfort-flat, court, d-shape, half-round; files land in out\band\<stem>\<run id>\
python -m ntopjewel band --size 6 --profile court --dry-run           # the numbers the notebook will get
python -m ntopjewel shank --size 6 --profile court --thickness 1.6 --width-bottom 2.2 --thickness-bottom 1.2   # a tapered shank: the ring unrolled as a bar, wrapped by nTop (out\shank)
python -m ntopjewel shank --size 6 --width 3 --thickness 1.5 --dip 2 --dip-shape chevron --double --gap 0.6 --bridges 180,100,-100   # a double chevron band (contour | chevron dips, --mirror for a wishbone)
python -m ntopjewel shank --size 6 --width 4 --thickness 1.5 --split 1.6 --split-span 90       # a split shank: the slot opens at the head, closes towards the bottom
python -m ntopjewel shank --size 6 --rope 2 --rope-turns 10 --rope-strand 1.2                   # a rope band: two round strands twisted round the ring (3 for a three-strand rope)
python -m ntopjewel shank --size 6 --width 4 --thickness 1.6 --knot plait --knot-strands 3 --knot-repeats 4   # a Celtic plait: 2..4 ribbons (or --knot-profile round wires) interlaced round the ring
python -m ntopjewel shank --size 6 --width 4 --thickness 1.6 --split 1.6 --split-span 100 --knot trinity      # trinity knots woven from a split shank's halves on each shoulder (ring 01)
python -m ntopjewel shank --size 6 --width 4 --thickness 1.6 --split 1.6 --split-span 110 --knot twist        # the halves cross over each other on each shoulder (rings 06, 07; --twist-length 8)
python -m ntopjewel ring --size 6 --profile court --milgrain --groove 0.25 --engrave "M+K 2026" --engrave-side inside --out out\ring   # --deliver copies a PASSED part + evidence to the Jewelry folder
python -m ntopjewel ring --size 4.5 --profile court --milgrain --groove 0.25 --engrave "Makena" --show   # that ring built in nTop's GUI session (out\api\preview), to look at
python -m ntopjewel gem --shape pear --length 12.3 --width 8.9 --depth 4.6 --material glass   # stone body STL + carats (out\gems)
python -m ntopjewel gem --shape pearl --length 8                     # also asscher, cabochon (--cab-dome); a pearl half-drilled for a post (--drill, --drill-depth), nacre by default
python -m ntopjewel head --shape pearl --length 8 --prongs 0 --cup 0.25   # a pearl in a cup on a post (outline_head; cabochon: claws over the dome on a plate)
python -m ntopjewel seat --shape round --length 6.5                   # the stone_seat block's cutter through its harness (nTopCL + gate; out\seat)
python -m ntopjewel head --length 6.5 --prongs 6                      # the prong_head block through its harness: fit, ledges, drop-in, volume (out\head)
python -m ntopjewel solitaire --size 6 --length 6.5 --prongs 6        # the Phase 2 ring: head on a court band, gothic arches with milgrain, gated (out\solitaire)
python -m ntopjewel solitaire --size 4.5 --shape pear --length 12.3 --stone-width 8.9 --stone-depth 4.6 --material glass --engrave Makena   # pear, text inside the shank
python -m ntopjewel solitaire --bezel --size 6 --length 6.5            # any stone in a bezel (head --bezel for the head alone)
python -m ntopjewel solitaire --size 6 --shape pearl --length 8 --prongs 0   # a pearl or a cabochon sits low on the band: placed by its plate / cup, no arches
python -m ntopjewel solitaire --partial-bezel --shape pear --length 10 --stone-width 7 --stone-depth 4.5 --profile half-round --width 9.5 --thickness 3.3 --width-bottom 2.8 --thickness-bottom 1.7 --lip 0.8 --tolerance 0.06   # the open pear (reference photo, 5 Nov): two walls on the flanks, a hood over the point, low between broad shoulders (head --partial-bezel for the head; any outline: an east-west half bezel)
python -m ntopjewel solitaire --size 6 --length 6.5 --blend 0 --shank-blend 0   # sharp junctions (default: the tables' blend_radius_mm on both)
python -m ntopjewel solitaire --size 6 --length 6.5 --width-bottom 2.4 --thickness-bottom 1.2   # on a tapered shank: every solitaire's shank is bars (Shank Path .. 4), plain unless shaped
python -m ntopjewel solitaire --size 6 --length 6.5 --split 1.6 --split-span 80                # a split shank: the slot under the head, through the arches (Slot Path)
python -m ntopjewel solitaire --size 6 --shape marquise --length 10 --stone-width 5 --split 1.6 --split-span 100 --knot trinity   # ring 01: the knots take the arches' place
python -m ntopjewel solitaire --size 6 --length 6.5 --split 1.6 --split-span 120 --knot twist    # a twisted split under the head (rings 06 / 07): the head on the whole band, an eye, the crossing
python -m ntopjewel solitaire --profile flat --width 2.8 --thickness 2 --prongs 4 --no-arches --sides leaves --outer scroll   # the Seraphine: artwork panels carved into the band under the head, plain shoulders
python -m ntopjewel solitaire --profile flat --width 2.8 --thickness 2 --prongs 4 --no-arches --sides scroll-leaves --outer scroll --shoulder-knot trinity   # ... the Seraphine proper: a trinity knot tucked under the head on each shoulder (apex at the head, 1.3 x the band), a volute then leaves (tips to the head) on the sides, the scroll outside past the knot
python -m ntopjewel solitaire --profile flat --width 2.8 --thickness 2 --prongs 4 --no-arches --sides scroll-leaves --outer scroll --shoulder-knot trinity --leaf-tilt 7.5 --leaf-stem 0.5 --stem-width 0.15 --width-bottom 2 --thickness-bottom 1.5   # ... leaves turned in turn on a slender stem, the band tapered below the scrollwork (taper from 121°, past the panels)
python -m ntopjewel pave --size 6 --stone 1.3 --rows 2 --span 120     # a pavé band: rows of stones in seats with light holes, held by beads (out\pave; --eternity, --layout aligned)
python -m ntopjewel multistone --shape cushion --length 7 --stone-width 6 --side-shape pear --side-length 6 --side-width 4   # ring 05: a centre + side stones, pears pointing in (out\multistone; --side-pairs 2 for five)
python -m ntopjewel multistone --profile comfort-flat --width 2.6 --thickness 1.8 --shape marquise --length 10 --stone-width 5 --material sapphire --side-shape cushion --side-length 4.5 --side-width 4.5 --side-material diamond --pave 1.3   # a marquise ruby (corundum) between cushion diamonds, diamond pavé round the rest of the ring (multistone 0.2.0: Pave Beads / Seats Path)
python -m ntopjewel multistone --profile comfort-flat --width 2.6 --thickness 1.8 --length 4 --prongs 4 --row 4 --shared-prongs --gallery   # ring 02: four rounds in a row (none at the top), the prongs between neighbours shared as posts, a gallery bridge each side (multistone 0.3.0: Gallery Path / Shared Prongs Path)
python -m ntopjewel multistone --profile comfort-flat --width 2.6 --thickness 1.8 --length 4 --prongs 4 --row 4 --shared-prongs --gallery --width-bottom 2 --thickness-bottom 1.4 --engrave "M+K 2026"   # ... ring 02 as photographed: tapered, engraved inside opposite the centre (multistone 0.4.0: Engraving Path; the letters sized at the taper's bottom)
python -m ntopjewel artwork --size 6 --sides leaves --outer vine     # artwork in relief in sunk panels: leaf rows on the side faces (tips to the head; --leaf-tip shank; scroll-leaves: a volute first), a vine (scroll: with a volute at the head end) outside, 25°-120° from the top (out\artwork)
python -m ntopjewel artwork --size 6 --sides scroll-leaves --outer scroll --leaf-tilt 7.5 --leaf-stem 0.5 --stem-width 0.15   # the leaves turned ±7.5° in turn, threaded on a serpentine stem half their height and 0.15 wide (one united relief body per panel; floor relief_line)
python -m ntopjewel artwork --size 6 --sides scroll-leaves --outer scroll --width-bottom 2 --thickness-bottom 1.5   # ... on a band tapered below the scrollwork (the ease begins just past the panels unless --taper-from says later)
python -m ntopjewel texture --dry-run                # a hammered band (150 strikes of one round hammer face, seeded; Mesh Tolerance 0.05); --write-design writes Python's model + strike centres (no notebook yet)
python -m ntopjewel gate out\band\<stem>\<run id>\<stem>.stl --expect-inner 16.51 --expect-width 4
python -m ntopjewel runs                        # one line per run today: PASSED / FAILED and the failing checks (--since 16:00, --last 5, --all)
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
- `ring-band` — the band family (Phase 0 hello band, profiles from Phase 1, shaped shanks from Phase 3).
- `ring-features` — milgrain, channel groove and wrapped engraving on a band (`ring` command); artwork in relief in sunk panels on its faces (`artwork`); surface textures (`texture`: hammered).
- `gem-library` — stone bodies, seats, prong heads, the solitaire, multi-stone rings and pavé (`gem`, `seat`, `head`, `solitaire`, `multistone`, `pave`).
- `blender-jewelry-render` (synced from claude.ai) — the silver product shot.
