# Recipes

A recipe is how a notebook or custom block gets built. Since the Notebook API (nTop 6.3+
Private Beta) the primary form is a **build script**: `<name>.py` with
`build(notebook, params) -> dict`, run inside nTop's Python Console by
`python -m ntopjewel api build <name>`. It adds the blocks, wires them, declares the inputs
and the Output, saves the `.ntop` into `ntop/notebooks/` (or `ntop/blocks/`) and exports
`<name>.recipe.json` next to itself — that JSON is the reviewable record of what was built.

The `*.md` files are the older GUI procedures. They stay as the fallback when a script
cannot run (no beta permission, no console) and as the human-readable explanation of the
geometry; the script wins when the two disagree.

| Recipe | Produces | Phase | Status |
| --- | --- | --- | --- |
| `band-primitive.md` | `ntop/notebooks/ring_band.ntop` (flat band, hello band) | 0 | built by Mark in the GUI 2026-10-25; gate passed |
| `band_profile.py` | `ntop/notebooks/ring_band_profile.ntop` (dome, comfort bore, rounded edges) | 1 | real identifiers; geometry = band ∩ dome torus ∩ comfort torus (the first real build subtracted the comfort torus and left a 0 mm shell - fixed); real build in progress |
| `band-profile.md` | same notebook, GUI route | 1 | superseded by `band_profile.py`; fallback only |
| `discover.py` | nothing saved: digest of this nTop's block identifiers, input names and variable behaviour (`out/api/discover.result.json`) | — | run first on a new nTop build or when an identifier lookup fails |

Rules:

- The catalog entry (`catalog/<name>.yaml`) is written first; the script's `INPUT_ORDER`
  equals its input names (tested).
- Identifiers and input names are candidates, resolved at run time by `NotebookHelper`;
  the result's `identifiers` map and the exported recipe show what was used. A miss is
  fixed in the script, not in the GUI.
- Every script runs against `python/tests/fake_notebook.py` in the offline tests before it
  runs against nTop.
- One block per recipe where possible; a block that needs more than two sittings is split.
- Scripts import only the standard library and `ntopjewel.notebook_api` (which is
  stdlib-only), because they execute inside nTop's own Python.

Running by hand, if SSH is not set up yet: `python -m ntopjewel api build <name> --dry-run`
prints the one `exec(open(r"...driver.py").read())` line to paste into View > Python
Console; `python -m ntopjewel api collect <name>` then reads the result.
