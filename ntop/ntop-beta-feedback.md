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
- `list_available_blocks()` returned a list in which no identifier contains the text
  `boolean subtract` (our guess at the Boolean Subtract identifier was wrong, or the unmasked
  list is partial). `api build discover` records what it actually offers.

## Open questions to settle on the first real run

- Exact identifiers for: point, cylinder (point/point/radius), torus, boolean subtract /
  intersect, offset body, mass properties, mesh from implicit body, export mesh — recorded
  automatically in `out/api/band_profile.result.json` → `identifiers`.
- Whether `add_block("core.var")` + `set_block_input(id, "Input", "<text>")` makes a text
  variable, or whether a Text block wrapped in `add_variable` is needed (the script tries
  both; the result's `log` says which worked).
- Whether a property of a built block (`Mass Properties.Volume`) can feed an empty
  variable created with `add_variable(name)` and then be the notebook Output.
- Whether `export_as_recipe(path, True)` writes a recipe we can diff in git.
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
