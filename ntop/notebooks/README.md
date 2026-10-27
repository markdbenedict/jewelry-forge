# Runner notebooks

Automate-ready notebooks, one per product family. Each declares its inputs (names exactly
as in `catalog/<name>.yaml`), one Output (the volume: a Volume Integral of 1, or Mass Properties in the Phase 0 band), and writes
files through Export blocks fed by `file_path` inputs. Run them only through
`python -m ntopjewel ...`, which validates inputs, calls `ntopcl` and runs the gate.

| Notebook | Catalog | Recipe |
| --- | --- | --- |
| `ring_band.ntop` | `catalog/ring_band.yaml` | `ntop/recipes/band-primitive.md` (Phase 0 flat band, gate passed 2026-10-25) |
| `ring_features.ntop` | `catalog/ring_features.yaml` | `ntop/recipes/ring_features.py` via `python -m ntopjewel api build ring_features` (Phase 1 step 2: milgrain, groove, engraving; pending first real build) |
| `ring_band_profile.ntop` | `catalog/ring_band_profile.yaml` | `ntop/recipes/band_profile.py` via `python -m ntopjewel api build band_profile` (Phase 1 profiles; API-built, nTopCL run and gate passed 2026-10-27; `band-profile.md` is the GUI fallback) |
