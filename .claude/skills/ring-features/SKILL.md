---
name: ring-features
description: Add milgrain beads, a channel groove and a wrapped engraving (inside or outside) to a profiled ring band with nTop through ntopjewel - the `ring` command, ring_features.ntop, the engraving STL that Python writes, the gate expectations with features on. Use for any request to engrave a band, add milgrain or a groove, or to run or debug ring_features.
---

# ring-features

**Status.** First real `api build ring_features` 2026-10-27 16:00: 55 blocks `e_OK`, volume
250.3 mm³ in the session (design 249). nTopCL run and gate next; until the notebook is in
`ntop/notebooks/`, run with `--notebook out\api\ring_features.ntop`.

## Make rings

```powershell
python -m ntopjewel ring --size 6 --profile court --milgrain --out out\ring
python -m ntopjewel ring --size 6 --profile court --groove 0.25 --groove-width 0.6
python -m ntopjewel ring --size 6 --profile court --engrave "M+K 2026" --engrave-side inside --engrave-depth 0.3
python -m ntopjewel ring --size 7 --profile d-shape --milgrain --groove 0.2 --engrave "forever" --deliver --project "Rings"
python -m ntopjewel ring --size 6 --milgrain --groove 0.25 --engrave "M+K 2026" --dry-run     # numbers, no nTop
```

Band options are the same as `band` (`--profile`, `--width`, `--thickness`, `--dome`, `--comfort`,
`--edge-round`, `--allowance`, `--tolerance`, `--system`). Output: `out\ring\ring_<profile>_<features>_<label>.stl`
plus `<stem>.engraving.stl`, `<stem>.report.json`, the nTopCL log; `--deliver` copies a passing
STL to `OneDrive\Documents\Jewelry\Rings`.

## How the features work (ntopjewel.features.RingSpec)

- One notebook, no switches: a feature that is off is sent as geometry that cannot change
  the band - a 0.05 mm bead inside the wall, a groove torus 10 mm outside the ring, an
  engraving "speck" 6 mm outside it.
- **Milgrain**: a sphere on each edge corner (centre 0.15 radii inside both faces, ~55 %
  exposed), unioned, Polar Array about +Z with `Bead Count` = round(2π r / (2.2 ρ)) copies and
  `Bead Spacing` = 360/count degrees. Bead radius floor 0.25 mm (`FLOORS["bead_dia"]`). The
  beads widen the ring: the gate expects width = 2 (z + ρ) and outer Ø = max(band, beads).
- **Groove**: a torus subtracted; ring radius = outer radius at the groove's z + tube − depth,
  tube = width/2. Checks: ≥ 0.5 mm of wall under it, clear of the edge round.
- **Engraving**: Python writes the text as a solid (matplotlib DejaVu Sans Bold → shapely →
  trimesh), extruded radially across the surface it cuts; the notebook imports it, wraps it
  with Remap Cylindrical Body (X radial, Y around the circumference, Z axial; `Y mapping
  length` = 2π x the surface radius) and subtracts it. Reading direction is mirrored for the
  inside. Checks: depth ≥ 0.25, thinnest stroke ≥ 0.3 mm at the chosen height, ≥ 0.5 mm wall
  left at the text's edge, text shorter than 90 % of the circumference. The cut is `depth`
  deep at the text's top and bottom and a little deeper mid-height on a curved face.
- The report's last note compares nTop's volume with the design volume (band + exposed bead
  volume − groove − text area x depth); ±3 % with features, ±2 % plain.

## Inputs (catalog/ring_features.yaml, 23)

The 11 band inputs, then Bead Radius / Bead Ring Radius / Bead Z / Bead Z Minus (mm), Bead
Spacing (deg), Bead Count (integer), Groove Ring Radius / Groove Tube Radius / Groove Z (mm),
Engraving Path (text), Engraving Wrap Length (mm), Output Path (text). `Bead Z Minus` exists
because the API cannot negate a variable.

## Authoring and verification

`python -m ntopjewel api build ring_features --scratch` (nTop open, console open). Its
`prepare()` writes the test engraving STL first (`--param text=HI` for real text). Then
`templates out\api\ring_features.ntop --catalog ring_features`, then a `ring ... --notebook
out\api\ring_features.ntop` run and its gate. Verified on the first real build: `deg` is a
known unit, Polar Array takes `Angular Spacing` / `Count` / `Axis`, Axis takes `Point` /
`Vector`, Volume Integral takes `Body` / `Integrand`, Remap takes `Y Mapping Length`. Still to
confirm with nTopCL: Import Mesh's default length unit (the gate's volume and the engraving
note catch a wrong unit).

## Report back

The gate text, the engraving note (length, thinnest stroke) and the design-volume note, plus
where the STL went. A FAIL is a FAIL; never deliver one.
