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

- Third build (2026-10-27 morning, `status: ok`): `add_variable("Volume")` +
  `connect_block_property(mass, "volume", "Volume", "x")` + `set_block_as_output("Volume")`
  all accepted; the notebook saved and `export_as_recipe(path, True)` wrote the recipe.
  `list_block_properties` on `mass_properties_from_body` returns lower-case names:
  `['center of gravity', 'mass', 'principal frame', 'principal moments', 'volume']`. After
  `move_block_to_input(id)` the variable no longer answers `block_state(id)` ("No block with
  the id ... exists in the notebook") although the wires from it stay intact. The notebook's
  methods on 6.3.3 / v0.14: PauseMode, add_block, add_floating_comment, add_point_variable,
  add_real_variable, add_section, add_variable, add_vector_variable, append_to_list,
  block_state, clear_block_input, close_current_open_custom_block, collapse_section,
  connect_block_property, current_open_custom_block, delete_block, delete_variable,
  embed_custom_block, expand_section, export_as_recipe, get_block_comment, get_block_input,
  get_block_input_meta, get_block_input_units, get_block_output_meta, get_block_visibility,
  get_floating_comment, import_recipe, list_available_blocks, list_block_inputs,
  list_block_properties, list_blocks, list_custom_blocks, list_sections, list_variables,
  move_block, move_block_to_body, move_block_to_input, new_notebook, open_custom_block,
  open_notebook, pause_updates, paused_updates, rename_variable, resume_updates,
  save_notebook, save_notebook_as, set_block_as_output, set_block_comment, set_block_input,
  set_block_input_units, set_block_visibility, update_floating_comment, updates_paused.

- Fourth build (2026-10-27 07:00, `status: ok`, then nTopCL clean): `volume_integral<implicit,
  real_field,real>` fed the body and a unitless `core.var<real>` = 1 builds in the session
  (245.60 mm³) once it is wrapped in a variable that is the notebook Output - a typed consumer
  makes a lazy block build; `ntopcl -t` then writes the output template; the run reports
  `Volume` as a `real` in m³ and the mesh gate passes (mesh volume within 0.14 % of nTop).
  Blocks `[5.44.0]` / `implicit_to_mesh[2.5.0]` run without deprecation warnings.

- Fifth build (2026-10-27 16:00, `ring_features`, `status: ok`, 55 blocks e_OK): `deg` is a
  known unit in a fresh notebook (`add_real_variable(..., "deg")` accepted); `core.var<integer>`
  + `set_block_input(id, "Input", 87)` makes an integer input; `polar_array_implicit`
  (`Angular Spacing`, `Count`, `Axis`), `axis<point,vector>` (`Point`, `Vector`),
  `sphere<point,real>` (`Center Point`), `import_mesh[1.1.0]` (`Path`, fed by a text variable),
  `implicit_from_mesh<mesh>` (`Mesh`), `remap_cylindrical_implicit` (`Y Mapping Length`) and
  `volume_integral` (`Body`, `Integrand`) all build on their defaults.

- Sixth build (2026-10-28, `custom_block_probe`): the custom-block methods carry good docstrings
  (they read like this file's wish list: "no dialog", "replaces that copy rather than adding a
  second"). A notebook with an input and an Output saved by `save_notebook_as` embeds with
  `embed_custom_block(path)`; `list_custom_blocks()` → `[{'name': 'probe_block', 'id':
  'user_func_ff2e1992_..._<real>', 'bufferId': 2}]`; `add_block(that id)` gives an instance with the
  block's `Radius` input, settable and `e_OK`. `embed_custom_block` raises while `paused_updates()`
  is held. `open_custom_block` takes the display name (`probe_block`), not the instance id.
  `add_variable(name, sphere_id)` makes a `core.var<sphere>`, i.e. the variable takes the wrapped
  block's own type. Nice to have: the uuid in `user_func_<uuid>` documented as stable per block
  file (or not), and a way to create a block from inside a notebook without a save/embed round trip.

## Open questions

- None blocking. Nice to have: a documented way to register a unit in a notebook, and a
  `required`/`has_default` flag per input in `list_block_inputs`.

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
  script wait for nothing. The API has no build/evaluate method (see the method list above);
  `set_block_visibility(id, True)` on the Mass Properties block did not make it build either,
  and neither did making its property the notebook Output or calling `get_block_output_meta`
  on the Output variable (value `None`).
- Workaround: wire the block's property into the Output variable first, then poll; treat a
  remaining `e_DIRTY` as "verify with nTopCL".

### 2026-10-27 — an unversioned identifier is the deprecated 1.0.0 definition
- Call: `add_block("boolean_subtract<blend_enum,real_field,implicit,list<implicit>>")` (the
  identifier without a `[version]`), likewise `boolean_intersect<…>` and
  `mass_properties_from_body<…>`.
- Happened: the notebook builds, but nTopCL warns `Boolean Subtract version 1.0.0 is now
  deprecated due to incorrect gradients in certain cases when the Subtraction Bodies list
  input contained a single body`, `Version 1.0.0 of Boolean Intersect is deprecated …`,
  `Version 1.0.0 of Mass Properties from Body is deprecated due to an issue that caused
  unstable output …`. The current blocks are `…[5.44.0]` and `mass_properties<…>[1.1.0]`.
- Expected: the doc's identifier convention should say that the bare identifier is the
  original version and that scripts must pick the newest `[x.y.z]` (or offer a "current"
  alias / a `list_available_blocks(current_only=True)`); `add_block` could warn like nTopCL.
- Workaround: sort candidates by version, treating an unversioned identifier as 1.0.0.

### 2026-10-27 — a `real_field` parameter cannot be set by `set_block_input`
- Call: `set_block_input("Mass properties_0", "Density", 1000.0)` and with `kg/m^3` / `g/cm^3` / `g/mm^3`.
- Happened: without units `Parameter "Density" of block "Mass properties_0" has type
  "real_field", which cannot be set yet; only "real", "vector", "point", "bool", "integer" and
  "text" parameters can.`; with units `… carries no unit, so its value cannot be given in kg/m^3.`
- Expected: real_field inputs are everywhere (Blend Radius, Offset Distance, Density); a
  constant should be settable like a real, with units. The two messages also contradict each
  other (one says it carries no unit, the other that it cannot be set yet).
- Workaround: a `core.var<real>` with units wired into the input builds fine.

### 2026-10-27 — a fresh notebook's unit table knows only `mm`; no way to add a unit
- Call: `add_real_variable("Density", 1000.0, "kg/m3")` and `set_block_input_units(id, "Input",
  "kg/m3")`, also `kg/m^3`, `kg/m³`, `g/cm^3`, `g/cm³`, `g/mm^3`, `g/mm³`, `g/cc`; meanwhile
  `get_block_input_units("Mass properties_0", "Density")` → `'kg/m3'`.
- Happened: every spelling, including nTop's own `kg/m3`: `"kg/m3" is not a unit this notebook
  knows.` A unitless variable wired into Density then fails the build with `'Density' requires
  units of mass/length^3, but received no units.`
- Expected: units the GUI parses in any field (`kg/m3`) should be accepted by the API, or a
  call to register a unit in the notebook, or `add_real_variable` could accept the unit as the
  GUI does and add it to the table.
- Workaround: avoid non-length units in API-built notebooks. For the volume, a
  `volume_integral<implicit,real_field,real>` of the constant 1 (a unitless variable) instead
  of Mass Properties + Density.

### 2026-10-27 — required inputs without defaults are invisible until nTopCL
- Call: `add_block("mass_properties_from_body<implicit,real_field,real>")`, wire `Body`, leave
  `Density` alone; the block stays `e_DIRTY` in the GUI (lazy), the notebook saves fine.
- Happened: `ntopcl` fails: `Mass properties_0: Input "Density" is incomplete`, then
  `Fatal error: Volume: Output block is unbuilt`. Same for a `core.var<file_path>` left unset:
  `Path_0: Input "Input" is incomplete`.
- Expected: `list_block_inputs` could flag inputs that have no default (`required: true`), or
  `block_state` could report `e_INCOMPLETE` without a build.
- Workaround: set every input nTopCL has ever flagged; delete blocks the script could not set.

### 2026-10-27 — `ntopcl -t` cannot template an Output that was never built
- Call: Output = `add_variable("Volume")` fed by `connect_block_property(mass, "volume", …)`;
  saved without a GUI build; `ntopcl -t notebook.ntop`.
- Happened: `[E]: Error generating output template : Output of function not built`; the input
  template is still written.
- Expected: the template to come from the Output's declared type, or the doc to say the
  notebook must be built once before `-t`.
- Workaround: a typed `core.var<real>` Output; the runner treats the missing output template
  as a note and checks the type on the first run.

Template:

```
### YYYY-MM-DD — <one line>
- Call: `notebook.<method>(...)`
- Happened: <message / state>
- Expected: <what the doc says or what we needed>
- Repro: <the smallest script, or the line from out/api/<name>.driver.py>
- Workaround: <if any>
```
