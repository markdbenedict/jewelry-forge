# Runner notebooks

Automate-ready notebooks, one per product family. Each declares its inputs (names exactly
as in `catalog/<name>.yaml`), one Output (the volume: a Volume Integral of 1, or Mass Properties in the Phase 0 band), and writes
files through Export blocks fed by `file_path` inputs. Run them only through
`python -m ntopjewel ...`, which validates inputs, calls `ntopcl` and runs the gate.

**The `.ntop` files here are not in git** (since 2026-11-03: the solitaire notebooks reached 230 MB
each, past GitHub's 100 MB limit - nTop caches every bar's round-trip meshes in the file). They are
build products: `python -m ntopjewel api build <recipe>` regenerates each from `ntop/recipes/<recipe>.py`
and writes `<name>.build.json` beside it (catalog versions, sha256, commit), and **the stamp is what is
committed**. A fresh checkout runs the `api build`s listed in CLAUDE.md before any run; a run on a
notebook whose stamp is missing or older than the catalog's `rebuild_since` is refused naming the build.
The block library in `ntop/blocks/` (under 1 MB each) stays in git.

| Notebook | Catalog | Recipe |
| --- | --- | --- |
| `ring_band.ntop` | `catalog/ring_band.yaml` | `ntop/recipes/band-primitive.md` (Phase 0 flat band, gate passed 2026-10-25) |
| `ring_features.ntop` | `catalog/ring_features.yaml` | `ntop/recipes/ring_features.py` via `python -m ntopjewel api build ring_features` (Phase 1 step 2: milgrain, groove, engraving; API build, nTopCL runs and gate PASS verified 2026-10-27 on the scratch copy in `out\api\`; this file appears once `api build ring_features` without `--scratch` is run and committed) |
| `ring_band_profile.ntop` | `catalog/ring_band_profile.yaml` | `ntop/recipes/band_profile.py` via `python -m ntopjewel api build band_profile` (Phase 1 profiles; API-built, nTopCL run and gate passed 2026-10-27; `band-profile.md` is the GUI fallback) |
| `solitaire.ntop`, `solitaire_outline.ntop`, `solitaire_bezel.ntop` | `catalog/solitaire*.yaml` | `ntop/recipes/solitaire*.py` via `python -m ntopjewel api build solitaire` … (Phase 2: embedded seat and head on the shank; blended junctions since Phase 3 step 0; the shank the bars Python writes (Shank Path .. Shank Path 4, each opened and united in nTop since 2026-11-02, catalogs 0.8.1 / 0.4.1), plain, tapered, split (Slot Path through the arches) or knotted, since step 1d; carved by the artwork layers at Cut Path / Relief Path and united with the shoulder knots at Knot Path / Knot Path 2 before the arches and the head join it, since step 5 on 2026-11-03, catalogs 0.10.0 / 0.6.0) |
| `*_harness.ntop` | `catalog/*_harness.yaml` | `ntop/recipes/<block>.py` builds the library block in `ntop/blocks/` and its harness (the block embedded in a runner, for `seat` / `head`) |
| `ring_shank.ntop` | `catalog/ring_shank.yaml` (0.3.1) | `ntop/recipes/ring_shank.py` via `python -m ntopjewel api build ring_shank` (Phase 3 step 1: the bars Python writes - tapered, contoured, double, split, rope or Celtic knotwork; up to four, bodies that cross each other in different ones, each opened by the edge round (0 for a rope or a knot), united in nTop and wrapped with Remap Cylindrical Body; appears once Mark's build is committed) |
| `multistone.ntop` | `catalog/multistone.yaml` (0.1.0) | `ntop/recipes/multistone.py` via `python -m ntopjewel api build multistone` (Phase 3 step 2: the shank's bars, then five slots of stone_seat + outline_head, each spun, placed on +X and turned about the ring axis; heads united with the shank, blended, then every seat cut; embeds both blocks - rebuild after either changes) |
| `ring_artwork.ntop` | `catalog/ring_artwork.yaml` (0.1.0) | `ntop/recipes/ring_artwork.py` via `python -m ntopjewel api build ring_artwork` (Phase 3 step 5: the band as `ring_shank` builds it, the panel channels Python writes subtracted, the relief motifs united - `(shank − cuts) ∪ relief`) |
| `pave_band.ntop` | `catalog/pave_band.yaml` (0.1.0) | `ntop/recipes/pave_band.py` via `python -m ntopjewel api build pave_band` (Phase 3 step 2/3: the band as `ring_shank` builds it, then the beads Python writes united and the seats Python writes subtracted - `(shank ∪ beads) − seats`) |
