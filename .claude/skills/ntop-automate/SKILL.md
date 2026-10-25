---
name: ntop-automate
description: Run nTop notebooks headlessly through nTopCL (nTop Automate) from this repo - build the input JSON from the catalog, run through ntopjewel, read the log and output JSON, diagnose failures. Use for any request that runs, sweeps or debugs an nTop notebook, or that asks what inputs a notebook takes.
---

# nTop Automate (nTopCL) in jewelry-forge

nTop runs headlessly as `ntopcl.exe`; Python drives it. Never call `ntopcl` by hand for
real work: `python -m ntopjewel ...` enforces the JSON rules and runs the mesh gate.

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
python -m ntopjewel templates ntop\notebooks\<nb>.ntop --catalog <name>   # -t, diff against catalog
python -m ntopjewel run <catalog> --set "Width=4" --set "Output Path=C:\...\x.stl"   # any notebook
python -m ntopjewel band --size 6 --width 4 --thickness 1.3 --out out\band          # band family
python -m ntopjewel gate <file.stl> --expect-inner 16.51 --expect-width 4           # mesh gate only
```

`ntopjewel.ntopcl.run(notebook, inputs, out_dir, tag=...)` is the programmatic entry;
it writes `<tag>.input.json`, `<tag>.output.json`, `<tag>.ntopcl.log` in `out_dir` and
raises `NtopclError` (with the parsed `RunResult` attached) on failure.

## Procedure for a new or changed notebook

1. `templates` against its catalog entry; fix names in the GUI until it says
   `catalog matches the notebook`. The catalog (`catalog/<name>.yaml`) is the schema:
   types, units, ranges, defaults, docs. Add or change inputs there first.
2. Run once with test values; read `out/<tag>.ntopcl.log` and the output JSON.
3. Run the gate on every file the notebook wrote. Report the gate text, not a summary of it.
4. Record block timings from the log in the report when a run takes more than a minute.

## Diagnosing failures

| Log / symptom | Meaning | Do |
| --- | --- | --- |
| `[E]: JSON file has no inputs` | empty `inputs` list sent | run without `-j`, or declare inputs in the notebook |
| `[E]: <Block>: ...` then `nTop exited with errors.` | that block failed (bad input, disconnected port, enum id) | read the message; check units on scalar/vector inputs; `templates` to see what the notebook expects |
| run OK but no STL | Export block path not wired to the input, or folder missing | check Export Mesh's File input; the runner creates `out_dir` |
| `Expired local license` / login errors | licence | open the nTop GUI and sign in; cloud licence runs offline up to 10 days |
| `MSVCR100.dll` error | VC++ 2010 runtime missing | install Microsoft Visual C++ 2010 x64 redistributable |
| exit code non-zero, no `[E]` | crash or timeout | rerun with `--logfile`; try the notebook in the GUI |

## Reading nTop documentation

The `ntop-docs` MCP server (`.mcp.json`) exposes `search_n_top` and a documentation
filesystem. Use it before guessing a block's inputs: search the block name, then read its
page. Block pages list exact input names and types.

## Rules

- Never edit an `.ntop` file by hand or script; change inputs or ask Mark to apply a recipe.
- Close Blender and the browser before runs on the 32 GB laptop; trees may need the
  128 GB machine.
- Tests that call nTop are `pytest -m slow`; everything else must pass offline against the
  fake `ntopcl` in `python/tests/conftest.py`, which reproduces the real log format.
