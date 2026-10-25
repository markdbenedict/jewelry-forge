---
name: ring-band
description: Build plain ring bands with nTop through ntopjewel - size (US/UK/ISO/mm), width, thickness, export STL, run the mesh gate and deliver to the Jewelry folder. Phase 0 flat band now; profiles (D, court, comfort fit), engraving and textures arrive in Phase 1. Use for any request to make, resize or batch band rings.
---

# ring-band

**Status:** Phase 0. `ntop/notebooks/ring_band.ntop` (flat band = outer cylinder minus
bore) built from `ntop/recipes/band-primitive.md`. If `python -m ntopjewel doctor` lists
no notebook, the recipe has not been built yet: ask Mark to build it; do not improvise a
notebook.

## Make bands

```powershell
python -m ntopjewel band --size 6 --width 4 --thickness 1.3 --out out\band
python -m ntopjewel band --size 6.5 --system US --allowance 0.05
python -m ntopjewel band --size L --system UK
python -m ntopjewel band --size 52 --system ISO --deliver --project "Bands"
python -m ntopjewel band --size 6 --dry-run      # just the millimetres, no nTop run
```

For a set, loop sizes in PowerShell (`foreach ($s in 5,6,7) { python -m ntopjewel band --size $s ... }`);
one STL per size is what the print-prep software wants.

What Python decides: inner diameter from `tables.inner_diameter_mm(size, system)`
(+ allowance), bore radius, outer radius = bore + thickness, file name
`ring_band_<label>.stl`, gate expectations (inner Ø and width ± 0.05 mm, volume ± 2 %
against nTop's Mass Properties, wall ≥ 0.5 mm floor).

What the notebook decides: nothing but geometry construction. Inputs are `Outer Radius`,
`Bore Radius`, `Width`, `Mesh Tolerance`, `Output Path` (see `catalog/ring_band.yaml`).

## Report back

Paste the gate text (PASS/FAIL, inner Ø, outer Ø, width, volume, weights, each check),
the nTop volume, and where the STL went. A FAIL is reported as a FAIL with the failing
check named; do not deliver a failing file.

## Defaults and floors

Width 4 mm, thickness 1.3 mm, mesh tolerance 0.01 mm. Thickness floor 1.0 mm, width
floor 1.5 mm (`tables.FLOORS`). Wide bands (> 6 mm) get +¼ size; see
`jewelry-design-rules`.

## Phase 1 (next)

`Band from profile` custom block: Revolve Profile of flat / D / court / half-round /
knife-edge sections; comfort-fit bore and domed outside via torus intersect/subtract
(`tables.torus_for_sagitta`); then `ring-features` (engraving with Text to Implicit,
grooves, milgrain, twist, textures via Remap Cylindrical Body).
