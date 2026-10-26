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

## Open questions to settle on the first real run

- Whether a `core.var<file_path>` variable renamed with `rename_variable` becomes the
  notebook input "Output Path" and feeds `export_mesh`'s file input.
- Whether Boolean blocks and `implicit_to_mesh` build with their default Blend Type / Blend
  Radius / Min. feature size / Sharpen / Simplify when a script sets none of them.
- Whether a unit vector (`torus` Axis) is accepted without units (the script retries with mm).
- Whether a property of a built block (`Mass Properties.Volume`) can feed an empty
  variable created with `add_variable(name)` and then be the notebook Output.
- Whether `export_as_recipe(path, True)` writes a recipe we can diff in git.
- The shape of `list_block_properties()` answers (dicts with `name`? strings?) - the helper
  accepts either and logs what it saw.
- Whether `block_state` answers for variables (the helper tolerates a refusal).

## Findings

_(none yet — the first `api build band_profile` run fills this in)_

Template:

```
### YYYY-MM-DD — <one line>
- Call: `notebook.<method>(...)`
- Happened: <message / state>
- Expected: <what the doc says or what we needed>
- Repro: <the smallest script, or the line from out/api/<name>.driver.py>
- Workaround: <if any>
```
