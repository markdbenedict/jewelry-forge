# nTop Notebook API — private beta feedback log

What the API did and did not do for jewelry-forge, in the form nTop's beta programme asks
for (one entry per finding: nTop version, package version, the call, what happened, what
we expected, a minimal reproduction). Mark decides what to send; nothing here is sent
automatically.

Environment: nTop 6.3.3 (cloud licence), Notebook API package v0.14 (doc dated Oct 2026),
Windows 11 laptops, Python per nTop's bundled console.

## Verified 2026-10-26 (Mark's laptop)

- View > Python Console is present and works; the SSH endpoint on localhost:2222 answers with
  the key from `scripts/setup-ntop-console.ps1`; `python -m ntopjewel api check` connected.
- A fresh notebook's section id was `section_2`, not `section_0`: ids are not 0-based; never
  assume them.
- `list_available_blocks()` returns 2273 identifiers on 6.3.3, snake_case with the input type
  list and sometimes a `[x.y.z]` version (`boolean_subtract<blend_enum,real_field,implicit,list<implicit>>`,
  also `[5.44.0]` and `[1.1.0]` variants). The doc's `sphere<point,real>` example is the only
  hint at this form; a list of the current identifiers per block page would save every beta
  user the discovery run. Masked and unmasked queries agree (nothing hidden).
- `add_block("core.var")` → `No block with the identifier "core.var" is available`; typed
  variables are `core.var<real>`, `core.var<text>`, `core.var<file_path>`, … (input `Input`).
  `add_real_variable` returns funcId `core.var<real>` with the name as id; `add_variable(name)`
  returns `core.var_any<any>` with input `x`.
- `list_block_inputs` includes the block's return value (`isReturnValue: true`, named like
  the block id, e.g. `Implicit Body_0: implicit`).
- The console's Python keeps imported modules between runs (`sys.modules`), so a script that
  imports a helper package sees stale code after the package changes unless it purges the
  module first. Expected: documented, or a "fresh interpreter per script" option.

- Second real build (2026-10-26 evening): all geometry blocks, `implicit_to_mesh[2.5.0]` and
  `export_mesh` built `e_OK` with their defaults (Blend Type/Radius, Min. feature size, Sharpen,
  Simplify untouched); a `torus` Axis vector is accepted without units; `rename_variable` works
  on a `core.var<text>` added with `add_block`; a `core.var<text>` connects to `export_mesh`'s
  `file_path` input (named `Path`); `add_variable(name, block_id)` wraps a block and both the
  variable and the wrapped block report `e_OK`; `block_state` answers for variables.

## Open questions

- Whether a property of a built block (`Mass Properties.Volume`) feeds an `add_variable`
  variable and can be the notebook Output (next run).
- Whether `export_as_recipe(path, True)` writes a recipe we can diff in git.
- The shape of `list_block_properties()` answers (dicts with `name`? strings?) - the helper
  accepts either and logs what it saw.
- Whether the API has any call that builds a lazy block (see finding 2); the next run logs
  `dir(notebook)`.

## Findings

### 2026-10-26 — `set_block_input` cannot set a `file_path` parameter
- Call: `notebook.add_block("core.var<file_path>")` then `notebook.set_block_input(id, "Input", r"C:\...\x.stl")`
- Happened: `Parameter "Input" of block "Path_0" has type "file_path", which cannot be set yet;
  only "real", "vector", "point", "bool", "integer" and "text" parameters can.`
- Expected: a file path is the natural input of every Export block; scripts that author
  Automate notebooks need it.
- Workaround: a `core.var<text>` holding the path connects to `export_mesh`'s `Path` input and
  builds; nTopCL's template then types the input `text`, which it accepts.

### 2026-10-26 — a block nothing consumes never builds (`e_DIRTY` for 300 s)
- Call: `mass_properties_from_body` wired from the final body, nothing downstream; polled
  `block_state(id)` for 300 s → `e_DIRTY` throughout, while the mesher and export (which
  consume the same body) went `e_OK`.
- Expected: either documented ("blocks build on demand; use X to force a build / the Output
  is evaluated when ...") or a `build_block(id)` / `evaluate(id)` call. `block_state` reports
  `e_DIRTY` the same way for "queued behind a long build" and "will never build", which makes a
  script wait for nothing.
- Workaround: wire the block's property into the Output variable first, then poll; treat a
  remaining `e_DIRTY` as "verify with nTopCL".

Template:

```
### YYYY-MM-DD — <one line>
- Call: `notebook.<method>(...)`
- Happened: <message / state>
- Expected: <what the doc says or what we needed>
- Repro: <the smallest script, or the line from out/api/<name>.driver.py>
- Workaround: <if any>
```
