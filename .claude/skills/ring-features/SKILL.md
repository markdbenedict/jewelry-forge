---
name: ring-features
description: Add milgrain beads, a channel groove and a wrapped engraving (inside or outside) to a profiled ring band with nTop through ntopjewel - the `ring` command, ring_features.ntop, the engraving STL that Python writes, the gate expectations with features on - and artwork in relief (leaf rows, vine scrolls, volutes) in sunk panels on a band's faces (`artwork`, ring_artwork.ntop). Use for any request to engrave or decorate a band, add milgrain, a groove, leaves or scrollwork, or to run or debug ring_features / ring_artwork.
---

# ring-features

**Status.** 2026-10-27: API build clean (55 blocks `e_OK`); nTopCL runs clean (4 s, 38
blocks); **gate PASS** on the engraved + beaded + grooved court ring at US6 and US4.5 (volume
within 0.2 % of design, engraving pocket found) once the thickness rays were confined to the
band between the bead rows and to radial/axial directions. Until the notebook is in
`ntop/notebooks/`, run with `--notebook out\api\ring_features.ntop`.

## Make rings

```powershell
python -m ntopjewel ring --size 6 --profile court --milgrain --out out\ring
python -m ntopjewel ring --size 6 --profile court --groove 0.25 --groove-width 0.6
python -m ntopjewel ring --size 6 --profile court --engrave "M+K 2026" --engrave-side inside --engrave-depth 0.3
python -m ntopjewel ring --size 7 --profile d-shape --milgrain --groove 0.2 --engrave "forever" --deliver --project "Rings"
python -m ntopjewel ring --size 6 --milgrain --groove 0.25 --engrave "M+K 2026" --dry-run     # numbers, no nTop
python -m ntopjewel ring --size 4.5 --profile court --milgrain --groove 0.25 --engrave "Makena" --show   # look at it in nTop
```

Band options are the same as `band` (`--profile`, `--width`, `--thickness`, `--dome`, `--comfort`,
`--edge-round`, `--allowance`, `--tolerance`, `--system`). Output: a fresh run directory
`out\ring\<stem>\<run id>\` with `<stem>.stl`, `<stem>.engraving.stl`, the input JSON, the
nTopCL log, `<stem>.gate.json` and `<stem>.report.json`, where the stem is
`ring_<profile>_<features>_<label>_w<width>_t<thickness>_<spec id>` (the spec id hashes every
input and the engraving text/side/depth, so no two designs share a file). `--deliver` copies
a **PASSED** part with that evidence and a `manifest.json` to
`OneDrive\Documents\Jewelry\Rings\<stem>\`; FAILED or INCOMPLETE parts are never delivered.

**Seeing a ring in nTop.** A `ring` run is headless: nTopCL reads the notebook, takes the
inputs from JSON and writes the STL; no notebook ever holds a particular ring. `--show`
builds the notebook again, through the Notebook API in nTop's open session (nTop open, View >
Python Console open), with *this* ring's 23 values instead of the test values: nTop's canvas
fills with the blocks, the viewport is left showing the finished ring only (`display_only`
hides the rest), the notebook is saved as `out\api\preview\<stem>.ntop` with its mesh and
`<stem>.preview.json`, and the mesh the session exported is gated. It replaces whatever
notebook nTop has open (unsaved GUI changes are lost) and runs no nTopCL. The repo's
`ring_features.ntop` is untouched. The STL from a normal run opens in Windows 3D Viewer or
through an Import Mesh block, which is quicker when only the mesh matters.

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
  length` = 2π x the MEAN surface radius over the text's height, so glyphs are distorted least on a curved face) and subtracts it. Reading direction is mirrored for the
  inside. Checks: depth ≥ 0.25, thinnest stroke ≥ 0.3 mm at the chosen height, ≥ 0.5 mm wall
  left at the text's edge, text shorter than 90 % of the circumference. The cut is `depth`
  deep at the text's top and bottom and a little deeper mid-height on a curved face.
- `design volume` is a hard gate check: nTop's volume against the design volume (band +
  exposed bead volume − the groove circle cut from the section itself (exact on any profile) −
  the exact pocket ∫∫ |R_floor² − r(z)²| / 2R_wrap over the glyphs, deeper mid-height on a curved face), ±3 % with features, ±2 % plain;
  INCOMPLETE when nTop reports no volume. The simulated nTop in the tests builds this exact
  geometry (section, beads, groove, cut text) and passes it; told to build a flat annulus
  instead, it fails here and only here (+17 %).
- Gate with features: the wall-thickness rays sample only |z| ≤ bead z − bead radius − 0.05
  (beads are solid bumps; a ray grazing one measures a chord, which failed the first run at
  p1 0.448 mm) and only along radial or axial directions (a ray off a letter's side wall runs
  through the 0.3 mm rib between strokes - a ridge on solid metal, not a wall - and read p1
  0.28 mm on the second run) and, inside the text's span, only radially (a letter's top or
  bottom wall measures the rib to the next stroke); the outer Ø expectation takes the groove
  into account; the `engraving` check samples the surface and measures the area 0.08..depth+0.08 mm
  below the engraved face within the text's height and angle: found when it is at least half
  the text's own area (floor + walls come to ~2.5 x on a real ring), and the same band of
  radii elsewhere must be empty.

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

The gate text with its `status:` line (PASSED / FAILED / INCOMPLETE), the engraving note
(length, thinnest stroke) and where the run directory and any delivery are. A FAIL is a
FAIL and INCOMPLETE is not a pass; neither is delivered.


## Artwork in relief (`artwork`, `ring_artwork.ntop`, `ntopjewel.artwork`, Phase 3 step 5)

```powershell
python -m ntopjewel artwork --size 6 --sides leaves --outer vine                 # leaf rows on the sides, a vine outside (flat 2.8 x 2.0 band)
python -m ntopjewel artwork --size 6 --sides scroll-leaves --outer scroll         # the Seraphine's faces: a volute then leaves (tips to the head) on the sides, the scroll outside
python -m ntopjewel artwork --size 6 --sides scroll-leaves --outer scroll --leaf-tilt 7.5 --leaf-stem 0.5   # ... the leaves turned ±7.5° in turn on a serpentine stem half their height
python -m ntopjewel artwork --size 6 --sides leaves --outer none --end 100       # leaf rows on the side faces only
python -m ntopjewel artwork --size 6 --sides plain --outer volute --start 20 --end 60 --dry-run
python -m ntopjewel solitaire --profile flat --width 2.8 --thickness 2 --prongs 4 --no-arches --sides scroll-leaves --outer scroll   # the same panels under a head (gem-library)
```

A **panel** is a channel `--channel` deep cut into one face of the band - the outer face or a side
face - from `--start` to `--end` degrees from the top (mirrored on the other side of the ring), leaving
a rail `--rail` wide along each edge, with a **motif** standing `--relief` high on the channel floor
and so `channel − relief` below the face, protected by the rails. Motifs are 2-D shapely polygons in
the panel's own frame (u along the ring from the head end, v across the channel): `leaves` (a row of
teardrop leaves, tips toward the head by default - the reference ring's - or away (`--leaf-tip head|shank`),
each with a shallow vein groove, VEIN_WIDTH_MM x VEIN_DEPTH_MM), `scroll-leaves` (a volute the channel's
width at the head end, then the leaf row from `2R + stroke + 0.3` on - the Seraphine's side faces, a volute
at the base of the head above each leaf row), `vine` (a gentle S-curve spine with a leaf at each crest and a hook at each end, one
polygon, clipped to the channel), `scroll` (the vine with a full volute the channel's width at its head
end - the Seraphine's scrolls at the base of the head - the spine running on from the volute's outer
turn), `volute` (a spiral scroll), `plain` (the channel alone). A new motif is one function returning
`[{"poly", "veins"}]` (and `"h_frac"`, the body's height as a fraction of the relief, when not the full height).
**A leaf row on a stem** (`--leaf-tilt DEG`, `--leaf-stem FRAC`; `motif_leaves(tilt_deg, stem, stem_from)`):
each leaf turned about the centre of its base, alternately + and − along the row (at most ±15°), and a
serpentine stem `--stroke` wide standing FRAC of the relief (≥ 0.1 mm) threaded through the row - v = A sin(π
(u − u_base0) / pitch), through every base, swinging `STEM_SWING` (0.65) of the free half-width out between
them, the sign of its slope at a base the sign of that leaf's tilt, so the leaf grows on from it; on
`scroll-leaves` it starts PLUG_MM inside the volute's far edge with a half-swing lead-in. The leaves come out
narrower for it (the tilted tip must stay inside the channel; 0.62 of the free width with a stem, so it shows
beside them) and a narrowed leaf's vein stops where the tip is still 0.12 wider than the slit (`leaf_vein(length,
width)`). Pieces of two heights cannot share a layer as separate bodies (they would cross or share a face),
so `relief_bodies` unites a panel copy's leaves and stem pieces into **one body** with manifold (the stem's
bottom at half the plug, so no bottoms are coplanar; the seams are square); `write_layers` still reads the
layer back and refuses any crossing. The gate's relief probes keep `PROBE_MARGIN_MM` off the step where a
stem meets a leaf (the mesher's blur of a 0.125 step). Neither number enters the spec id when 0, so the
straight rows keep their stems. A side face is the band's **edge thickness** (the mid-plane thickness less the
dome and the comfort fit) less two rails, centred between the bore's and the dome's edges; on a domed
(court) outer face the relief would stand proud where the face falls away at the channel's edge, so
`validate` refuses it (a flat band, a deeper channel or a lower relief). A `plain` panel's relief file
holds a 0.2 mm cube **buried in the band** opposite the head (`buried_speck`), so the notebook's union
has a body and the ring is unchanged - never a speck outside the ring, which a union leaves as a second shell.

Geometry: the cutters are boxes lofted station by station along the ring and wrapped vertex-wise
(geom.remap_cylindrical, what nTop's Remap Cylindrical does); a relief body's outline is densified in
2-D, capped by a constrained Delaunay triangulation (`quality_triangulate`: boundary + an interior grid,
every boundary edge recovered by edge flips, no slivers) and swept - radially on the outer face
(`radial_prism`, every vertex wrapped), straight along the axis on a side face after the outline itself
is wrapped (`axial_prism`, exact); a vein is a rectangle swept along its segment (`swept_slit`). Never
a 3-D subdivision or an earcut cap under the wrap: T-junctions pierce and slivers fold (the first real
run, 2026-11-03). `write_layers` reads each layer back and refuses one that crosses itself. A side-face
motif is stretched along the ring in proportion to the radius (±10 % over a 2 mm thick band).
Python writes `<stem>.cut.stl` (one body per panel copy) and `<stem>.relief.stl` (one body per leaf
or scroll, each plugged `PLUG_MM` into the floor); the notebook builds `(shank − cuts) ∪ relief` -
the band is opened by its edge round first, so the channel edges stay crisp and the relief is never
rounded. **Cutters must not touch**: an outer channel as deep as the side rails are wide meets the
side channels' walls along an edge, which the STL round trip turns into a non-manifold seam
(`validate` refuses it). Rails are lips on a solid band, not walls: at least `RAIL_MIN_MM` (0.3)
wide, and the wall sampler skips every panelled face's channel zone (a ray through a rail into the
channel read 0.35 mm). Mesh Tolerance 0.05.

Gate (`artwork.check_artwork`): the band's checks with the panels' zones out of the wall sample and
the section shape through the panels against the design's **core** (`section_clip`: below the channel
floors - a relief edge lying on a section plane read as the relief's whole height on the Seraphine
solitaire, 2026-11-03; the probes see to the relief), the design volume, and three probe checks
cast identically on the built ring and the design - `channel floors`, `relief`, `rails` - on a 0.25 mm
grid over every panel (points within 0.12 mm of a motif's edge skipped). A notebook that never cut
the channels fails floors and volume; one that lost the relief fails `relief`.

**Under a solitaire's head** (gem-library: `solitaire --sides/--outer/--start/--end ...`, the same flags):
the three solitaire notebooks take `Cut Path` / `Relief Path` after `Slot Path` and carve the opened band
(`nj.add_carved`: (Band Body − Panel Cuts) ∪ Relief = Carved Band) BEFORE the arches, the milgrain and the
blended head join it and the seat and engraving are cut. `SolitaireSpec.panels` + the artwork numbers;
every panel's head end is held back (`panel_start_min_deg`): past the arches' wedge + 1° (they fill the
band's faces from mid-wall outward inside it), or with `--no-arches` (plain shoulders, the head standing
on the band as the Seraphine's does; milgrain off) just past the head's reach along the ring + the shank
blend + 0.5 mm. Without artwork the two inputs get no-op specks (`write_artwork`). The gate adds the three
probe checks, keeps the channel zones out of the wall sample and compares the section shape inside the
panels against the carved band. The simulated nTop carves from the same files (`carved_shank_from_inputs`;
`FAKE_NTOPCL_SHAPE=nocut|norelief` to lose a layer).

Not yet: panels on a tapered, split or knotted shank; the Seraphine's knots standing on a continuous
band beside the head, its double-claw prongs and heart gallery (plan step 5/6).
