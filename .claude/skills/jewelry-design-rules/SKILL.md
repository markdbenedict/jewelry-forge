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
- Print/cast allowance: a printed dimension moves two ways - the resin's shrink (`settings.resin_shrink_pct`, a scale
  of everything) and its bloom (`settings.print_bloom_mm`: every surface grows past the layer's outline, so outer
  dimensions come out larger and bores smaller by twice it). Both come from a test-print round's sheet through
  `python -m ntopjewel calibrate` (a reading across a bore and one across metal tell them apart); until then they are
  `uncalibrated`. A bore is compensated by `--allowance` (the intake's report names the figure for the round's size:
  bore × shrink + 2 × bloom). Cast rings typically come out ¼–½ size under the model; record the measured offset in
  `tables.CASTING["cast_ring_size_offset"]` (Phase 5).
- Band floors: thickness ≥ 1.0 mm (1.3 mm is a comfortable default), width ≥ 1.5 mm.

## Walls and features (castable resin print → investment cast)

| Feature | Floor | Note |
| --- | --- | --- |
| wall | 0.5 mm marginal, 0.75 mm good | below 0.5 prints but may not fill in casting |
| prong tip diameter | 0.8 mm | 0.9–1.2 mm typical |
| milgrain / bead | 0.5 mm | beads touching their neighbour by ≥ 30 % |
| engraving | ≥ 0.25 mm deep, ≥ 0.3 mm stroke | inside engraving 0.3 mm deep reads well |
| raised line in relief (a leaf row's stem) | ≥ 0.15 mm wide (`floors.relief_line`, default) | three to five printer pixels; it lies on a surface the investment fills, unlike a free wall |
| bezel wall | 0.5–0.8 mm | lip 0.3–0.5 mm above the stone girdle for burnishing |
| moving chain link clearance | ≥ 0.35 mm | printed assembled; fused links for casting as one |
| unsupported overhang detail | keep features > 0.3 mm | 50 µm pixel printers resolve ~0.1 mm but resin needs bulk |
| lattice sheet or strut | ≥ 0.6 mm (`floors.lattice_member`, default) | a gyroid sheet is continuous and well supported: between the marginal and the good wall |
| lattice pore (the sphere that passes through the void) | ≥ 1.0 mm (`floors.lattice_pore`, default) | the investment between the sheets; see below |

**Lattices are exposed, never buried.** A lattice closed inside a skin traps uncured resin (and cups on the FEP);
in the casting its negative space IS investment, which must survive the burnout and the pour and then come out
again. An open lattice can do both the way filigree does: its investment is one continuous network anchored to the
block through the open face, not a free-standing core, and after the quench water goes in at one opening and out at
another. So every void must reach the outside (the `lattice` gate flood-fills the built mesh from the outer face and
fails any pocket that does not), the channels must be wide enough for the investment to hold and to wash out
(`lattice_pore`), the sheets thick enough to print and fill (`lattice_member`), and a solid bore skin (`settings.
lattice_skin_mm`, 0.8) and solid rims (the good wall) carry the ring. At these floors a gyroid needs a cell of about
3.5 mm (0.6 mm sheets leave a 1.04 mm pore), so a lattice band is a chunky one (≥ 3.3 mm thick) and saves about a
third of the metal. A sheet that runs nearly parallel under the outer face, cut by it, leaves a thin lip (0.26 mm on
the second real run): the lattice is grown from a seed trimmed by the band inset by the growth, so the growth is the
opening - every sheet end at the outer face is rounded by half the marginal wall and no lip is thinner than the
marginal wall (0.5). All of it defaults until the first lattice print and cast.

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

## Printing: orientation and supports (`--prep`, `printprep.py`)

The printer gets a file already oriented and supported - Mark slices it as it is and adds nothing. Every number is a
`default` in the tables' settings until the test prints set it:

| Setting | Default | What it is |
| --- | --- | --- |
| `print_layer_mm` | 0.05 | the slicer's layer; the preparation slices at it for islands and suction cups |
| `print_overhang_deg` | 45 | a down-facing surface flatter than this (from level) needs a support; any island does |
| `print_start_gap_mm` | 0.1 | the first contact within this of the part's lowest point (two layers): until it, nothing but the film holds the part |
| `support_hold_area_mm2` | 5 | a layer needs a contact at or under its height per this much area; more go under the lowest layers where the spacing left fewer |
| `support_tip_mm` | 0.25 | the contact's diameter, the breakaway neck at the surface (light tips swell less where they meet the part) |
| `support_contact_depth_mm` | 0.1 | how far the tip reaches in (more on a slope, so the whole tip is in) |
| `support_tip_length_mm` / `support_column_mm` | 1.0 / 0.8 | the cone to the column; a long column thickens to 1/15 of its length (≤ 1.6) |
| `support_spacing_mm` | 1.5 | contacts along an overhang; one holds the overhang within ¾ of it (`--support-spacing` for one run; the test prints' court band 3.0, hammered band 3.0 and Seraphine 2.2 - about half the contacts, Mark 8 Nov: denser would swell) |
| `support_lift_mm` / `raft_thickness_mm` | 5.0 / 0.8 | the part's lowest point above the raft; the raft, chamfered for the scraper |
| `support_clearance_mm` | 0.3 | columns kept this far off the part |
| `support_keepoff_mm` | 0.5 | no contact nearer a feature than this |

- **Contacts on plain metal only**: polished faces (dome, side faces, rims) and the bore - never on beads, engraving,
  texture, lattice, relief panels, knots, prongs, seats, arches. The classes come from the design (the plain section
  and the family's zones), not from the mesh. `--bore avoid` keeps the bore clear too (a calibration ring read on the
  mandrel); then its overhangs count as unsupportable.
- **The part starts on its supports.** Until its first contact, nothing but the film holds a part: a feature that
  leads the first contact cures onto the film, the part grows from it there, and every later layer stays with the film
  while the supports print alone. The 8 Nov 2026 court band did exactly that - leaning 53°, its bottom bead row (no
  contact on a bead) led by twelve layers; "the ring itself stuck to the film, not the supports". So an orientation
  whose first contact comes later than `print_start_gap_mm` after the part's lowest point is shunned by the search and
  refused if forced (a layer or two of a feature on the film comes away with the tips; a stack of them is the part's
  foot). A band with milgrain on both edges can start only on its dome, standing on edge - and then its bore's crown
  needs struts, so the bore cannot be kept clear (`--bore avoid` leaves the crown to print unsupported).
- **Every layer is held.** The contacts engaged under a layer are all that hold it off the film: one per
  `support_hold_area_mm2` of its area at least, added under the lowest layers (half the spacing, then a quarter) where
  the spacing left fewer. The hammered band's rim printed on 4.7 mm² per tip (15 tips, flat); a ring standing on edge at
  3 mm spacing would have hung 24 mm² of its first half millimetre on the one tip at its lowest point.
- **Orientation**: after those, whatever leaves the fewest feature islands (a piece of a layer touching nothing printed
  before it - it prints on the film, not on the part, and the feature comes out short) and the least feature overhang
  no contact covers, then the fewest contacts, then no suction cups (resin walled in by a layer and sealed below - a
  knot's lobe, a bezel cup facing the film), small layers, low height. Milgrain on both edges always leaves some bead
  islands; a hammered or textured band prints flat on a side face; a solitaire stands head up, the bore held from the
  raft past the shank's bottom or by struts on the bore's floor.
- Report and warnings name what is left unsupported in the ring's own angles (θ from the head, r, z), so the test
  prints can be read against them.

## Before any export

1. Gate floors set for the metal (`--wall-floor`), expected inner diameter and width given.
2. Deliverables named `<family>_<label>.stl` (e.g. `ring_band_US6.stl`), one file per size
   or variant, copied to `OneDrive\Documents\Jewelry\<project>`.
3. Report: dimensions, volume, weights per alloy, gate verdict, and anything below a floor.
