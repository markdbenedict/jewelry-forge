---
name: jewelry-design-rules
description: Design rules and reference numbers for rings, settings, pendants, bracelets, chains and castable resin printing / investment casting - ring sizing, minimum walls, prongs, bezels, clearances, metal weights, shrinkage, casting sprues and trees. Use whenever a jewelry dimension, tolerance or material figure is chosen or checked.
---

# Jewelry design rules (jewelry-forge)

Numbers are starting defaults from the Formlabs jewelry guidance used for the pear ring
and from bench practice; measured values replace them in `data/jewelry_tables.json` (one file for Python and
Blender; each entry is marked `default` or `calibrated`, with a dated `calibration_log`
entry). Quote the table, not memory.

## Ring sizing

- US size → inner diameter: `11.63 + 0.8128 × size` mm (US 5 = 15.69, 6 = 16.51, 7 = 17.32).
  ISO/EU = inner circumference in mm (ID = circ / π). UK letters step 0.4064 mm from
  A = 12.04 mm. `python -m ntopjewel sizes` prints the table.
- Size is applied to the **bore at the band's narrowest point** (the mid-plane of a
  comfort-fit band). Wide bands (> 6 mm) wear tight: add ¼ size for 6–8 mm, ½ size above.
- Print/cast allowance: unknown until calibrated. First printed band set: sizes 5, 6, 7
  with `--allowance 0`; measure on the mandrel; set the allowance from the difference.
  Cast rings typically come out ¼–½ size under the model; record the measured offset in
  `tables.CASTING["cast_ring_size_offset"]`.
- Band floors: thickness ≥ 1.0 mm (1.3 mm is a comfortable default), width ≥ 1.5 mm.

## Walls and features (castable resin print → investment cast)

| Feature | Floor | Note |
| --- | --- | --- |
| wall | 0.5 mm marginal, 0.75 mm good | below 0.5 prints but may not fill in casting |
| prong tip diameter | 0.8 mm | 0.9–1.2 mm typical |
| milgrain / bead | 0.5 mm | beads touching their neighbour by ≥ 30 % |
| engraving | ≥ 0.25 mm deep, ≥ 0.3 mm stroke | inside engraving 0.3 mm deep reads well |
| bezel wall | 0.5–0.8 mm | lip 0.3–0.5 mm above the stone girdle for burnishing |
| moving chain link clearance | ≥ 0.35 mm | printed assembled; fused links for casting as one |
| unsupported overhang detail | keep features > 0.3 mm | 50 µm pixel printers resolve ~0.1 mm but resin needs bulk |

## Settings

- Stone seat (bearing) at ~⅓ of prong height from the top; seat width ≈ 0.3–0.4 mm;
  culet clearance ≥ 0.5 mm above the finger.
- Prong count: 4 for ≤ 6 mm rounds, 6 above; 4 or 6 for ovals/pears with a V-prong at
  the point. Prong tips rounded (ball ≥ 0.9 mm) or flat; never knife edges.
- Bezel for a stone of outline O: wall = offset of O by 0.5–0.8 mm; seat depth = stone
  depth below the girdle + 0.2 mm; light windows leave ≥ 0.4 mm webs between cuts.
- Gem bodies: use the measured stone (calipers) when there is one; otherwise standard
  proportions (round brilliant depth ≈ 61 % of diameter; oval/pear depth ≈ 55–60 % of width).

## Pendants, bracelets, chains

- Bail inner diameter = chain diameter + 0.5 mm; bail wire ≥ 1.0 mm; centre of mass
  under the bail or the pendant tilts (the gate reports it when asked).
- Cuff: opening 25–30 mm for an average wrist; oval ratio ≈ 1.2:1; thickness ≥ 1.5 mm.
  Bangle inner circumference ≥ hand circumference over the knuckles.
- Links: wire 0.6–1.5 mm; cable link inner length ≈ 3 × wire; curb = oval link twisted
  45°–60°. Clasps, posts and springs are bought findings, not modelled.

## Weights and metals (g/cm³, approximate)

sterling 10.36 · fine silver 10.49 · 10k 11.6 · 14k yellow 13.1 · 14k white 12.6 ·
18k yellow 15.6 · 18k white 14.9 · platinum 950 20.7 · palladium 12.0 · bronze 8.8 ·
castable resin ≈ 1.15. Weight = volume (mm³) × density / 1000. `tables.weights_g(v)`.

## Casting (defaults to calibrate; see references/casting.md)

- Feed sprue 2.5–3.5 mm for rings, tapered toward the part, gated at the heaviest
  section, never on a show surface or a prong; neck blend 0.5–1.0 mm.
- Main sprue 6–10 mm; feeds at 45–60° upward; ≥ 6 mm between parts and to the flask
  wall; ≥ 12 mm investment above the top of the tree; heavy parts low.
- Linear shrink, model → cast: sterling ≈ 1.7 %, gold alloys ≈ 1.4 %, platinum ≈ 1.0 %,
  bronze ≈ 1.5 % (`tables.shrink_scale(metal)`). Applied as a uniform scale before meshing.

## Before any export

1. Gate floors set for the metal (`--wall-floor`), expected inner diameter and width given.
2. Deliverables named `<family>_<label>.stl` (e.g. `ring_band_US6.stl`), one file per size
   or variant, copied to `OneDrive\Documents\Jewelry\<project>`.
3. Report: dimensions, volume, weights per alloy, gate verdict, and anything below a floor.
