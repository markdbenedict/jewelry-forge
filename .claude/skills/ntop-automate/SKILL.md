---
name: ntop-automate
description: Author nTop notebooks through the Notebook API (build scripts run in nTop's Python Console over SSH) and run them headlessly through nTopCL (nTop Automate) from this repo - build the input JSON from the catalog, run through ntopjewel, read the log and output JSON, diagnose failures. Use for any request that creates, changes, runs, sweeps or debugs an nTop notebook, or that asks what blocks or inputs a notebook has.
---

# nTop in jewelry-forge: author with the Notebook API, run with nTopCL

Two doors into nTop, both driven from Python, never by editing `.ntop` files:

| Door | What for | Entry |
| --- | --- | --- |
| **Notebook API** (Private Beta, nTop 6.3+) | authoring: add blocks, wire, declare inputs/output, save, export recipe | `python -m ntopjewel api build <recipe>` |
| **nTopCL** (nTop Automate) | running: inputs JSON in, log + output JSON + STL out | `python -m ntopjewel run|band ...` |

Never call `ntopcl` or `ssh` by hand for real work: `python -m ntopjewel ...` enforces the
JSON rules, resolves identifiers, checks build states and runs the mesh gate.

## Notebook API (from nTop's doc, Oct 2026, package v0.14 — not yet exercised on Mark's laptop)

- nTop exposes a Python console (**View > Python Console**, Ctrl+`) with one object,
  `notebook`. Only with the Private Beta (Early Access) permission on the licence; if the
  menu item is missing, that is the blocker, not our code.
- Over SSH it is `ssh -tt -i ~\.ssh\id_ntopcli -p 2222 localhost`, alive only while the
  console panel is open. Key auth only (`authorized_keys` ASCII, no BOM, owner-only).
  **One line per send**, scripts via `exec(open(r"...").read())`, **Ctrl+C to end, never
  `exit()`**. `ntopjewel.notebook_api.Console` wraps all of it; `Console.run_script` writes
  a driver + params JSON into `out/api/`, runs `build(notebook, params)` from the script and
  reads the result JSON back.
- A build script lives in `ntop/recipes/<name>.py`, imports only the standard library plus
  `ntopjewel.notebook_api` (stdlib-only, so it imports inside nTop's Python), and uses
  `NotebookHelper`: `add(label, *identifier_candidates, mask=, must=)`, `set`, `wire`,
  `to_list`, `real_var`, `wrap_var`, `property_var`, `declare_inputs`, `set_output`,
  `assert_ok`, `states`, `paused()`.
- Identifiers are snake_case plus the input type list, sometimes a version:
  `boolean_subtract<blend_enum,real_field,implicit,list<implicit>>`, `offset_implicit<implicit,real_field>`,
  `mass_properties_from_body<implicit,real_field,real>`, `implicit_to_mesh<implicit,real,real,bool,bool>[2.5.0]`,
  `export_mesh<file_path,mesh,unit_length_enum>`. nTop says they may change between
  releases, so scripts give `must` alternatives (`[["boolean_subtract", "implicit"], …]`);
  the helper matches case-insensitively with spaces as underscores, prefers a name match,
  then the unversioned definition, then the newest version, and records what it used. When
  a lookup misses, run `api build discover` (dumps all identifiers and the input names of
  the families we use) and put the real one in the script; never fix it in the GUI.
- Typed variables are blocks: `core.var<real>`, `core.var<text>`, `core.var<file_path>` …
  (input `Input`); `add_variable(name)` gives a `core.var_any<any>` with input `x`.
- Bad values fail at build time, not at call time: `block_state(id)["buildState"]` must be
  `e_OK`; `e_FAILED` carries `error`. `states()` checks every block the script made.
- Variables: `add_real_variable(name, value, "mm")` (the id is the name) are the notebook
  inputs after `move_block_to_input`; the Output is a variable fed from Mass Properties'
  Volume (`property_var`). A block output used twice goes through `add_variable(name, id)`.
- `new_notebook()` discards unsaved work; `save_notebook_as` and `export_as_recipe`
  overwrite silently. Scripts default to `fresh=True` and save into `ntop/notebooks/`;
  `--scratch` saves under `out/api/` for a trial.
- No SSH yet? `api build <recipe> --dry-run` writes the driver and prints the one line to
  paste into the GUI console; `api collect <recipe>` reads its result afterwards.
- Anything the API refuses, misreports or lacks goes in `ntop/ntop-beta-feedback.md` with
  the call, the message and what we expected (nTop's beta programme asks for exactly this).

## nTopCL

## Facts verified on nTop 6.3.3 (2026-10-25, Mark's laptop, cloud licence)

- `ntopcl -v 2 -j in.json -o out.json notebook.ntop` builds a notebook. `-t notebook.ntop`
  writes `input_template.json` and `output_template.json` into the working directory.
  `--logfile path` keeps the console log. `--version` prints the version.
- The log has one line per block: `15:57:33 [I]: Sphere_0 complete 0ms`. First lines are
  `Login successful`, `Notebook started`; last lines `nTop successfully built.` then
  `Logout successful`.
- **Success = exit code 0 AND no `[E]` line AND `nTop successfully built.` present.**
  A failed run still exits 0 (`[E]: ...` then `nTop exited with errors.`).
- **A notebook with no declared inputs must run without `-j`.** nTopCL rejects an input
  JSON whose `inputs` list is empty: `[E]: JSON file has no inputs`.
- Input JSON: `{"title", "description", "inputs": [{"name","type","value"[,"units"]}]}`.
  Types: `bool`, `scalar` (units), `integer`, `text`, `file_path`, `point` (units),
  `vector` (units, required for some), `enum` (integer id). A scalar may carry
  `"values": [..]` to sweep one parameter in a single run (one list per run).
- Output JSON: a list of `{name, type, value, components}`. An `implicit` output is a
  base64 blob. The scalar shape is tolerated in several forms by `ntopcl.scalar_value`;
  confirm it from the first real band run and simplify.
- One declared Output per notebook. Files leave through Export Mesh / Export 3MF blocks
  fed by a `file_path` (or `text`) input.

## Commands

```powershell
python -m ntopjewel doctor                                         # ntopcl found? version? notebooks? catalog?
python -m ntopjewel api check                                      # SSH to nTop's Python Console answers?
python -m ntopjewel api build band_profile [--scratch] [--param wait_s=600]   # author a notebook from ntop\recipes\band_profile.py
python -m ntopjewel api build band_profile --dry-run               # driver to paste into the GUI console; then api collect band_profile
python -m ntopjewel api line "print(notebook.list_available_blocks('boolean'))"   # discovery, one line
python -m ntopjewel templates ntop\notebooks\<nb>.ntop --catalog <name>   # -t, diff against catalog
python -m ntopjewel run <catalog> --set "Width=4" --set "Output Path=C:\...\x.stl"   # any notebook
python -m ntopjewel band --size 6 --width 4 --thickness 1.3 --out out\band          # band family
python -m ntopjewel gate <file.stl> --expect-inner 16.51 --expect-width 4           # mesh gate only
```

`ntopjewel.ntopcl.run(notebook, inputs, out_dir, tag=...)` is the programmatic entry;
it writes `<tag>.input.json`, `<tag>.output.json`, `<tag>.ntopcl.log` in `out_dir` and
raises `NtopclError` (with the parsed `RunResult` attached) on failure.

## Procedure for a new or changed notebook

1. Write or change the catalog entry first (`catalog/<name>.yaml` is the schema: types,
   units, ranges, defaults, docs); the build script's `INPUT_ORDER` must equal its input
   names (a test enforces this for the band).
2. Write or change the build script in `ntop/recipes/<name>.py`; run the offline tests
   (they exercise it against `python/tests/fake_notebook.py`).
3. `api build <name>` on the laptop; read the identifiers and states in the result and the
   saved `.recipe.json`. Fix misses in the script, rerun.
4. `templates` against the catalog entry until it says `catalog matches the notebook`.
5. Run once with test values; read `out/<tag>.ntopcl.log` and the output JSON.
6. Run the gate on every file the notebook wrote. Report the gate text, not a summary of it.
7. Record block timings from the log in the report when a run takes more than a minute.

## Diagnosing failures

| Log / symptom | Meaning | Do |
| --- | --- | --- |
| `[E]: JSON file has no inputs` | empty `inputs` list sent | run without `-j`, or declare inputs in the notebook |
| `[E]: <Block>: ...` then `nTop exited with errors.` | that block failed (bad input, disconnected port, enum id) | read the message; check units on scalar/vector inputs; `templates` to see what the notebook expects |
| run OK but no STL | Export block path not wired to the input, or folder missing | check Export Mesh's File input; the runner creates `out_dir` |
| `Expired local license` / login errors | licence | open the nTop GUI and sign in; cloud licence runs offline up to 10 days |
| `MSVCR100.dll` error | VC++ 2010 runtime missing | install Microsoft Visual C++ 2010 x64 redistributable |
| exit code non-zero, no `[E]` | crash or timeout | rerun with `--logfile`; try the notebook in the GUI |
| `api`: `SSH key not found` | no key yet | `ssh-keygen -t ed25519 -f ~\.ssh\id_ntopcli`, append the `.pub` to `~\.ssh\authorized_keys` (ASCII, no BOM) |
| `api`: `Permission denied (publickey)` | sshd rejects the key | `authorized_keys` has a BOM, wrong line, or is writable by others |
| `api`: `connection refused on localhost:2222` | no endpoint | nTop not running, or View > Python Console not open |
| `api`: `no block identifier for ...; near misses: [...]` | identifier changed / wrong guess | put the near miss into the script's candidates |
| `api`: `block X has no input like (...); it has [...]` | input name differs | add the listed name to the candidates |
| `api`: `blocks failed to build: {...}` | a value or wiring nTop rejects | read the `error` text; compare with the block's doc page; set units on reals/points |
| `api`: timed out | a slow build or a dialog in the GUI | look at the nTop window; raise `--timeout`; `--param wait_s=600` |

## Reading nTop documentation

The `ntop-docs` MCP server (`.mcp.json`) exposes `search_n_top` and a documentation
filesystem. Use it before guessing a block's inputs: search the block name, then read its
page. Block pages list exact input names and types.

## Rules

- Never edit an `.ntop` file by hand or by text/script; change it through the Notebook API
  (a build script), the GUI, or run-time inputs.
- A build script is the source of truth for a notebook; the exported `.recipe.json` is the
  reviewable diff; the `.ntop` is a build artefact that is still committed (nTopCL needs it).
- Close Blender and the browser before runs on the 32 GB laptop; trees may need the
  128 GB machine.
- Tests that call nTop are `pytest -m slow`; everything else must pass offline against the
  fake `ntopcl` in `python/tests/conftest.py`, which reproduces the real log format.
