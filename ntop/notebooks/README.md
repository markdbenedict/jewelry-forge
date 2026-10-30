# Runner notebooks

Automate-ready notebooks, one per product family. Each declares its inputs (names exactly
as in `catalog/<name>.yaml`), one Output (the volume: a Volume Integral of 1, or Mass Properties in the Phase 0 band), and writes
files through Export blocks fed by `file_path` inputs. Run them only through
`python -m ntopjewel ...`, which validates inputs, calls `ntopcl` and runs the gate.

| Notebook | Catalog | Recipe |
| --- | --- | --- |
| `ring_band.ntop` | `catalog/ring_band.yaml` | `ntop/recipes/band-primitive.md` (Phase 0 flat band, gate passed 2026-10-25) |
| `ring_features.ntop` | `catalog/ring_features.yaml` | `ntop/recipes/ring_features.py` via `python -m ntopjewel api build ring_features` (Phase 1 step 2: milgrain, groove, engraving; API build, nTopCL runs and gate PASS verified 2026-10-27 on the scratch copy in `out\api\`; this file appears once `api build ring_features` without `--scratch` is run and committed) |
| `ring_band_profile.ntop` | `catalog/ring_band_profile.yaml` | `ntop/recipes/band_profile.py` via `python -m ntopjewel api build band_profile` (Phase 1 profiles; API-built, nTopCL run and gate passed 2026-10-27; `band-profile.md` is the GUI fallback) |
| `solitaire.ntop`, `solitaire_outline.ntop`, `solitaire_bezel.ntop` | `catalog/solitaire*.yaml` | `ntop/recipes/solitaire*.py` via `python -m ntopjewel api build solitaire` … (Phase 2: band + embedded seat and head; blended junctions since Phase 3 step 0) |
| `*_harness.ntop` | `catalog/*_harness.yaml` | `ntop/recipes/<block>.py` builds the library block in `ntop/blocks/` and its harness (the block embedded in a runner, for `seat` / `head`) |
| `ring_shank.ntop` | `catalog/ring_shank.yaml` (0.2.0) | `ntop/recipes/ring_shank.py` via `python -m ntopjewel api build ring_shank` (Phase 3 step 1: the bar Python writes, wrapped with Remap Cylindrical Body, then opened by the edge round; appears once Mark's build is committed) |
