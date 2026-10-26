# Recipe: `ring_band_profile.ntop` — the profiled band (Phase 1, step 1)

> **Superseded by `band_profile.py`** (Notebook API build script; run with
> `python -m ntopjewel api build band_profile`). Keep this page for the geometry
> explanation and as the GUI fallback if the Python Console is not available.

**Goal.** Give the hello band real cross-sections: a domed outside, a barrel ("comfort fit")
bore and rounded edges. One notebook covers flat, comfort-flat, court, D-shape and
half-round; Python picks the numbers per profile and the notebook only intersects,
subtracts and offsets. Time: 20–30 minutes, starting from `ring_band.ntop`.

**How the shape is made (so the blocks make sense).**

- Dome: intersect the flat band with a torus whose tube circle has radius
  ρ_d = (W²/4 + d²)/(2d) and sits at ring radius R_d = r_o − ρ_d. The circle touches the
  outer surface at the mid-plane and is `d` lower at the edges.
- Comfort bore: **intersect** with a torus with ρ_c = (W²/4 + c²)/(2c) at ring radius
  R_c = r_i + ρ_c. Its inner side touches the bore at the mid-plane and stands `c` further
  out at the edges, so the kept material has a barrel bore. (Subtracting this torus removes
  the band - its tube covers the whole section.)
- Edge round: Offset Body by −e, then by +e. Shrinking and regrowing an implicit rounds
  every edge with radius e and leaves the flat faces where they were.
- Python computes all six numbers (`python -m ntopjewel band --profile court --dry-run`
  prints them). For a flat outside it passes a torus that swallows the section, so the
  intersect removes nothing; for no bore relief, a torus centred on the bore that does the same.

The band is centred on the origin along Z (z = ±W/2), which Phase 2 needs for heads.

## 1. Start from the hello band

File → Open `ntop\notebooks\ring_band.ntop` → File → **Save As**
`ntop\notebooks\ring_band_profile.ntop`. Work in the copy.

## 2. Inputs

Keep `Outer Radius`, `Bore Radius`, `Mesh Tolerance`, `Output Path`. Remove `Width` from
the Inputs section and delete it, then add these scalar variables (type each value **with
`mm`**, rename, drag into Inputs). Test values are US 6, 4 mm wide, 1.3 mm thick, court:

| Input (exact name) | Test value | Meaning |
| --- | --- | --- |
| `Z Top` | `2 mm` | +W/2 |
| `Z Bottom` | `-2 mm` | −W/2 |
| `Dome Ring Radius` | `3.2371 mm` | R_d |
| `Dome Tube Radius` | `6.3163 mm` | ρ_d |
| `Comfort Ring Radius` | `15.3894 mm` | R_c |
| `Comfort Tube Radius` | `7.136 mm` | ρ_c |
| `Edge Round` | `0.25 mm` | +e |
| `Edge Round Inward` | `-0.25 mm` | −e |

Final Inputs order: Outer Radius, Bore Radius, Z Top, Z Bottom, Dome Ring Radius,
Dome Tube Radius, Comfort Ring Radius, Comfort Tube Radius, Edge Round, Edge Round
Inward, Mesh Tolerance, Output Path (12).

## 3. Geometry changes

1. **Centre the outer cylinder.** `Outer`: Point 1 = `0 mm, 0 mm,` *drop `Z Bottom`* ;
   Point 2 = `0 mm, 0 mm,` *drop `Z Top`*. (Same trick as before: a Point block with X `0 mm`,
   Y `0 mm` and the scalar chip in Z, then the Point block onto the cylinder's point row.
   Two Point blocks, one per end. The old Point block that held Width can be reused for
   the top.)
2. **Recentre the bore.** `Bore`: Point 1 = `0 mm, 0 mm, -10 mm`; Point 2 = `0 mm, 0 mm, 10 mm`.
3. **Dome torus** — add **Torus** (Create → Primitives). Center `0 mm, 0 mm, 0 mm`; Axis
   `0, 0, 1`; Radius = `Dome Ring Radius` chip; Torus radius = `Dome Tube Radius` chip.
   Rename `Dome Torus`.
4. **Comfort torus** — add another **Torus**. Center `0 mm, 0 mm, 0 mm`; Axis `0, 0, 1`;
   Radius = `Comfort Ring Radius`; Torus radius = `Comfort Tube Radius`. Rename `Comfort Torus`.
5. **Shaped** — add **Boolean Intersect** (Modeling → Booleans). Bodies = `Band` (the existing
   Boolean Subtract), `Dome Torus` and `Comfort Torus`. Blend Sharp. Rename `Shaped`.
   *Check:* the outside bulges and the bore is barrel-shaped; the band is 1.3 mm thick at the
   middle and about 0.69 mm at the edges (court).
6. (no step - kept so the numbering below matches the older copy)
7. **Edge round** — add **Offset Body** (Modeling → Operations). Body = `Shaped`, Distance =
   `Edge Round Inward` chip. Rename `Shrunk`. Add a second **Offset Body**: Body = `Shrunk`,
   Distance = `Edge Round` chip. Rename `Band Profile`. *Check:* all four edges are rounded;
   outer diameter still 19.107 mm at the middle.
8. **Rewire the tail.** `Mass Properties` body = `Band Profile`; `Mesh` body = `Band Profile`.
   Export Mesh and the Output (`Volume`) stay as they are.

If `Offset Body` grows instead of shrinks with the negative distance (edges stay sharp
after step 7), swap the two chips: nTop's sign convention is the only unknown here.

## 4. Save and verify

```powershell
python -m ntopjewel templates ntop\notebooks\ring_band_profile.ntop --catalog ring_band_profile
python -m ntopjewel band --size 6 --profile court --out out\band
```

Expected: `PASS`, inner Ø 16.507, outer Ø 19.107, width 4.000, wall p1 ≈ 0.69 mm (the
designed edge thickness; the gate's floor adapts to it), volume a little under 291 mm³,
triangle count well under a million.

Then the other four, which exercise the same notebook with different numbers:

```powershell
foreach ($p in "flat","comfort-flat","d-shape","half-round") { python -m ntopjewel band --size 6 --profile $p --out out\band }
```

`flat` is the one to watch: it passes a torus that should remove nothing, so its volume
must match the hello band (290.9 mm³) within the edge rounding.

## 5. If something does not line up

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Torus block refuses the Radius / Torus radius pair | a shallow dome on a wide band gives a ring radius ≤ 0 | the dry run warns about it; use `--dome` a little larger or a narrower band |
| `Domed` is empty or a thin ring | Intersect used the wrong torus, or the dome torus is centred off the origin | Center must be `0, 0, 0`; Radius chip is `Dome Ring Radius` |
| Band vanishes to a thin shell | comfort torus subtracted instead of intersected | step 5 is a Boolean Intersect with all three bodies |
| gate: width 20 or more | the bore cylinder went into the Intersect | step 4 uses `Band`, not `Bore` |
| gate: wall p1 far below 0.69 | edge round too big for the edge, or offsets reversed | `--dome`/`--comfort` smaller, or swap the offset chips |
| volume differs from nTop's by > 2 % | Mesh Tolerance too coarse for the rounded edges | try 0.05 mm once; expect ~4x the triangles |

## 6. Next

With five profiles passing, `ring-features` follows: engraving (Text to Implicit, wrapped
with Remap Cylindrical Body), milgrain (spheres on Equidistant Points on Curve), twist,
textures. Each is its own small recipe on top of this notebook.
