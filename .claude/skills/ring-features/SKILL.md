---
name: ring-features
description: Add milgrain beads, a channel groove and a wrapped engraving (inside or outside) to a profiled ring band with nTop through ntopjewel - the `ring` command, ring_features.ntop, the engraving STL that Python writes, the gate expectations with features on - and artwork in relief (leaf rows, vine scrolls, volutes) in sunk panels on a band's faces (`artwork`, ring_artwork.ntop), surface textures (hammered and nTop's own: `texture`), and open lattice bands (a gyroid between a bore skin and the rims: `lattice`, ring_lattice.ntop). Use for any request to engrave, texture, lattice or decorate a band, add milgrain, a groove, leaves, scrollwork, a hammered finish or a gyroid, or to run or debug ring_features / ring_artwork / ring_lattice.
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
python -m ntopjewel artwork --size 6 --sides scroll-leaves --outer scroll --leaf-tilt 7.5 --leaf-stem 0.5 --stem-width 0.15   # ... the leaves turned ±7.5° in turn on a serpentine stem half their height, 0.15 wide
python -m ntopjewel artwork --size 6 --sides scroll-leaves --outer scroll --width-bottom 2 --thickness-bottom 1.5         # the band tapered below the scrollwork: full section past the panels, a cosine ease to the bottom
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
serpentine stem `--stem-width` wide (default the stroke; floor `relief_line` 0.15 mm in the tables - a raised
line three to five printer pixels wide, lying on a surface the investment fills) standing FRAC of the relief
(≥ 0.1 mm) threaded through the row - v = A sin(π
(u − u_base0) / pitch), through every base, swinging `STEM_SWING` (0.65) of the free half-width out between
them, the sign of its slope at a base the sign of that leaf's tilt, so the leaf grows on from it; on
`scroll-leaves` it starts PLUG_MM inside the volute's far edge with a half-swing lead-in. The leaves come out
narrower for it (the tilted tip must stay inside the channel; 0.62 of the free width with a stem, so it shows
beside them) and a narrowed leaf's vein stops where the tip is still 0.12 wider than the slit (`leaf_vein(length,
width)`). Pieces of two heights cannot share a layer as separate bodies (they would cross or share a face),
so `relief_bodies` unites a panel copy's leaves and stem pieces into **one body** with manifold (the stem's
bottom at half the plug, so no bottoms are coplanar; the seams are square); `write_layers` still reads the
layer back and refuses any crossing. The gate's relief probes keep `PROBE_MARGIN_MM` off the step where a
stem meets a leaf (the mesher's blur of a 0.125 step) **and off every vein slit** (a 0.09-0.2 mm slit 0.12
deep is below what the mesher resolves: 0.102 on the outer vine's leaves the one day they carried veins,
2026-11-04), and probe a stem along its own centreline every 0.125 mm where it shows between the leaves
(the grid's margin leaves nothing on a 0.15 mm line). None of the three numbers enters the spec id when 0,
so the straight rows keep their stems - and `test_the_built_seraphine_designs_keep_their_geometry` pins the
two PASSED Seraphine designs' relief volume, body count and id: the outer vine's leaves carry no veins
(`leaf_vein`'s plain rule never fits their clipped tips; only a narrowed row leaf takes the `short_tip`
rule), and a change that gives them some changes a built design. A side face is the band's **edge thickness** (the mid-plane thickness less the
dome and the comfort fit) less two rails, centred between the bore's and the dome's edges; on a domed
(court) outer face the relief would stand proud where the face falls away at the channel's edge, so
`validate` refuses it (a flat band, a deeper channel or a lower relief). A `plain` panel's relief file
holds a 0.2 mm cube **buried in the band** opposite the head (`buried_speck`), so the notebook's union
has a body and the ring is unchanged - never a speck outside the ring, which a union leaves as a second shell.
**A tapered band** (`--width-bottom`, `--thickness-bottom`, `--taper-from`; the `shank` taper, `ring-band`)
carries artwork as long as the full section runs past the last panel: `validate` wants `taper_from_deg` ≥
the last panel's end + `TAPER_CLEAR_DEG` (1°; the cosine ease has zero slope there), and the CLI's
`--taper-from` defaults to exactly that with panels (`artwork.taper_start_deg`), 60° without. The panels'
cutters and relief are built on the full section as ever; only the bar changes (stem `..._w2.8-2_t2-1.5_...`).
Split, contoured, double, rope and knot shanks still wait.

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

## Surface textures (`texture`, `ntopjewel.texture`, Phase 3 step 7)

```powershell
python -m ntopjewel texture --dry-run                                  # hammered US6 court 4 x 1.6: 150 strikes, ~2.5 M triangles at 0.05
python -m ntopjewel texture --dimple 2 --depth 0.18 --seed 7 --dry-run  # bigger, deeper strikes; another seed, another hammering
python -m ntopjewel texture --write-design                             # Python's model (STL + strike centres CSV) to look at - NOT an nTop build
python -m ntopjewel api build ring_texture                             # the notebook (nTop open, Python Console open)
python -m ntopjewel texture                                            # through ring_texture.ntop: nTopCL + the gate (out\texture; --deliver)
```

Hammered: one round hammer face (radius from `--dimple` x `--depth`, the nominal strike) pressed in along the
face's normal at seeded dart-throwing centres round the face (periodic round the ring), `--spacing` 0.5 dimples
apart (no point unstruck), each strike's depth varied `--depth-var` (±25 %), lighter towards the polished rims
(`--rim`, default edge round + 0.1) so a footprint ends there, never under the `texture_depth` floor (0.1 mm).
The union of equal spheres is the distance to the nearest centre less one radius: nTop builds it as one field from
the centres. The texture defaults the band to 1.6 thick and Mesh Tolerance 0.05: the lightest strike must span 3
voxels, and `tables.mesh_triangles_estimate` refuses a design past 5 M triangles. Gate (`check_texture`): band
checks, section shape against the design's sections (whole Mesh Tolerance), design volume, a probe down every
strike's normal. Notebook `ring_texture.ntop` (5 Nov): the profiled band (opened) less nTop's own spheres - Import
Points reads the centres CSV (`Strikes Path`), ONE Sphere on the whole list makes one per point (measured,
`points_probe`), a Boolean Union joins them; `Strikes Units` is a notebook input (the API cannot set an enum,
Import Points has no default unit; 1 = mm). The strikes are cut after the opening, so their ridges stay crisp.
Real check PASSED 5 Nov (150/150 strikes, section 0.007 mm, volume -0.13 %, 2.44 M triangles).

Any ring (5 Nov): the strikes are laid out on a face (`texture.Hammer` + `strike_layout` over `BandFace` or a shank's
`ShankFace`, tabulated from its sections), so `shank --hammered` strikes any profiled shank (tapered, split, dipped,
double; ring_shank.ntop 0.4.0) and `solitaire --hammered` the solitaire's band before the arches and the head join it,
no strike within `head_clear_deg` of the top. The same flags (`--dimple --depth --depth-var --spacing --rim --seed`).
A face too narrow for a strike (a split's halves, a taper's bottom) stays polished and the run warns where and what
fits. Refused: a rope or a knot shank; on a solitaire, artwork panels, shoulder knots, an outside engraving, or an
inside one with less than `wall_good` left under the deepest strike and the letters; pave / multistone / artwork
runners (no Strikes section yet).

```powershell
python -m ntopjewel shank --size 6 --width 4 --thickness 1.6 --width-bottom 2.6 --thickness-bottom 1.4 --tolerance 0.05 --hammered
python -m ntopjewel shank --size 6 --width 4 --thickness 1.6 --split 1.6 --split-span 90 --tolerance 0.05 --hammered --dimple 1.0 --depth 0.14 --rim 0.12
python -m ntopjewel solitaire --size 6 --length 6.5 --hammered        # rebuild the solitaire notebooks first (solitaire 0.12.0 ...)
```

nTop's own textures (6 Nov, started): its toolkit blocks - simplex / cellular noise deboss, surface roughness, voronoi
deboss / emboss, triangle wave - are probed before anything is built on them: `api build texture_probe`, then
`texture-probe` (one STL per texture on the plain US6 court 4 x 1.6 band, each measured against the designed section:
depth and height per face, how much of the outer face, bore, sides and edges each touches, feature size, volume taken;
`texture_probe.json` / `.txt` in `out\texture_probe\<run id>\`; `--set Depth=0.15` etc. for other numbers,
`--measure DIR` to re-measure, and a depth map of each face per texture, `texture_probe_<case>.png`). Their noise is
nTop's, so their gate is an envelope, not a design to match. Measured 6 Nov: every block textures every face (a product
masks it to the outer face); the voronoi deboss carves the cell walls as half-round grooves (Thickness wide, half as
deep) - the first product; the triangle wave displaces the surface outward (peaks 3 x the height); the noises'
frequencies are per metre.

```powershell
python -m ntopjewel texture --kind voronoi --thickness 1.6 --tolerance 0.05 --dry-run        # nTop's voronoi deboss: 200 cells, 0.2 mm grooves (0.1 deep) on the outer face
python -m ntopjewel texture --kind voronoi --thickness 1.6 --tolerance 0.05 --groove 0.3 --cells 300 --rim 0.5
python -m ntopjewel api build ring_voronoi                                                   # the notebook (nTop open, Python Console open)
python -m ntopjewel texture --kind voronoi --thickness 1.6 --tolerance 0.05                  # through ring_voronoi.ntop: nTopCL + the envelope gate (out\texture)
```

Voronoi (`ntopjewel.fieldtex.VoronoiSpec`, `ring_voronoi.ntop`): the band, nTop's `voronoi_deboss` toolkit block on it
(Feature size = --cell-size, Voronoi cell count = --cells, Relaxation iterations, Thickness = --groove, Blend radius,
Spatial weighting), the dents (band − grooved) kept inside a zone between the rims and from just under the dome outwards,
cut from the band: the outer face grooved, the bore / sides / rims as designed, the grooves ending at the rims in a clean
line. The gate holds the part to an envelope: inside the zone nothing above the design and nothing deeper than the groove;
outside it nothing moved; the grooves cover 3-60 % of the face and enclose at least 4 flat cells (counted on a raster);
nTop's volume between the plain band and the band less the zone's face sunk by the depth. The report says what came out
(deepest, share, cells and their size, volume taken). Refused: grooves under 2 x `texture_depth` (0.2 wide) or over 1 mm,
too little wall under a groove at the zone's edge, under 3 voxels, past 5 M triangles.

The other kinds (`fieldtex.NoiseSpec`, `RibbedSpec`; `ring_<kind>.ntop`, the same mask and envelope):

```powershell
python -m ntopjewel texture --kind frost --thickness 1.6 --tolerance 0.05 --grain 2 --depth 0.1 --seed 1   # surface roughness: a ±0.1 frost, 2 mm grain
python -m ntopjewel texture --kind pitted --thickness 1.6 --tolerance 0.05 --grain 1.5 --depth 0.1       # simplex deboss: the same noise cut in only
python -m ntopjewel texture --kind cellular --thickness 1.6 --tolerance 0.05 --grain 2 --depth 0.15      # cellular deboss: soft dimples at the cells, --depth the deepest
python -m ntopjewel texture --kind ribbed --thickness 1.6 --tolerance 0.05 --rib 0.5 --depth 0.2         # the triangle wave: ribs round the ring, 0.5 apart, 0.2 deep
```

`--grain` is the noise's period in mm (nTop's frequency is per metre: 1000 / grain); `--depth` the amplitude (the frost
rises as much as it cuts; the gate's outer-Ø expectation grows by it); `--seed` nTop's. The cellular block's "Depth
factor" is not a depth - the dimples come out about 3.4 x factor x grain deep (tables, one measurement), so the spec sets
the factor from `--depth`. The ribbed band is eroded by the rib depth first (the wave only stands outward, peaks 3 x its
height input) and the ribs come back up to the design. Coverage the gate asks for: frost ≥ 30 %, pitted ≥ 10 %, cellular
and ribbed ≥ 50 %. Refused: amplitude under `texture_depth` or over 0.5, a grain under 8 voxels or over twice the band's
width, ribs under 6 voxels apart.
All five PASSED in real nTop on 6 Nov at the numbers above (frost ±0.084 for 0.1 asked, pitted 0.082, cellular 0.100,
ribbed 0.190 for 0.2, voronoi 0.102 for 0.1; the mask held to 0.005 mm on every one; 21-25 s a run).

## Lattice bands (`lattice`, `ring_lattice.ntop`, `ntopjewel.lattice`, Phase 3 step 8)

```powershell
python -m ntopjewel lattice --dry-run                                           # flat US6 7 x 3.5: 3.5 mm gyroid cells, 0.6 sheets, 0.8 skin, 0.75 rims
python -m ntopjewel lattice --width 6 --thickness 3.3 --cell 3.5 --member 0.6 --dry-run
python -m ntopjewel lattice --write-design                                      # Python's own mesh of it (manifold3d's level set; half a minute) - NOT an nTop build
python -m ntopjewel api build ring_lattice                                      # the notebook (nTop open, Python Console open)
python -m ntopjewel lattice                                                     # through ring_lattice.ntop: nTopCL + the lattice gate (out\lattice; --deliver)
```

An exposed gyroid, never a buried infill (the design rules say why: the resin and the investment both have to get out).
The profiled band keeps a solid bore skin (`--skin`, tables `lattice_skin_mm` 0.8) and solid rims (`--rim`, the good
wall); between them, from the skin's top to the outer face, the metal is nTop's gyroid sheet. `gyroid_implicit`
(`--cell`, cubic cells in the bar frame) gives the surface, but its field is the gyroid function scaled by cell / 2π, not
a distance (measured 6 Nov: Thicken 0.6 came out 0.45, varying with the gradient), so the notebook thickens only a thin
seed (two voxels, in field units x `api_facts` gyroid_field_gradient 1.6), wraps it round the ring by Remap Cylindrical
with a mapping length of a whole number of cells (`GyroidSpec.cells_around`, so the pattern closes on itself), trims it
to the band inside the zone (grown into the skin and the rims past the growth and the round, so the union overlaps
instead of meeting on a face), re-distances it by the mesh round trip and grows it to `--member` by an Offset (exact on
a distance field), trims it again, opens it by 0.1 mm (feather edges thinner than 0.2 go, the sheet ends come back
rounded) and unites it with the band less the zone. `lattice_sheet_correction_mm` (tables settings) is what the round
trips take off the sheet, measured by the second run.

Python holds the same geometry exactly (`lattice.GyroidSpec`: the gyroid's formula, its distance by two Newton steps -
the first-order g / |∇g| alone thins a 0.6 sheet to 0.54 -, the wrap, the opening at the dome), so the gate is not an
envelope: **lattice match** (the built mesh's inside / outside at 20 000 points in the zone against the model, ≥ 98 %;
when it fails, the report names the best of the mirrored and shifted gyroids - nTop's convention, to record in
`GYROID_VARIANT`), **sheet thickness** (rays through the sheets, off their ends: p1 against the member floor, the median
against the wall asked), **pore width** (rays across the voids to the next sheet, p5 within 85 % of the unit cell's own),
**open voids** (the built mesh voxelised by scanline rays at 0.1 mm and flood-filled from the outer face: a pocket of
void that reaches no opening fails the part), **design volume** (nTop's integral against the model's grid integration,
±2 %), the mask (bore, sides, rims as designed), the band checks (the generic wall rays kept off the sheet ends). The
result says what the lattice saves (sterling, against the solid band). Refused: a member under `lattice_member`, a cell
whose pore (`unit_cell_stats`, the sphere that passes) is under `lattice_pore`, a zone under half a cell deep, a skin
under the good wall, a design whose metal is not one piece or whose voids do not all reach the face (the same flood
fill on the model), a sheet under 6 voxels.

The first real run (6 Nov, flat 7 x 3.5, 16 s): one shell, the match 98.7 % (nTop's gyroid standard and unshifted,
Thicken symmetric, the wrap ours), the pore 1.07, every void open, the mask held - and the sheet 0.450 for 0.6, which
is where the seed pipeline (0.2.0) comes from. The gate learnt two rules from it: flakes with no thickness where the
sheets lean on the skin are the mesher's (counted apart, like the specks), and a void pocket is only one above 0.03 mm³
(slivers at the grid's size are reported, not failed). The second run's one number: the sheet's median against the
wall asked, into `lattice_sheet_correction_mm`.

