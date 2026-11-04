---
name: gem-library
description: Parametric stone bodies (round, oval, pear, marquise, cushion, emerald) for settings, seats and cutters, with volume and carat weight - the `gem` command and ntopjewel.gems - and the settings built from them, prong heads, bezels, the solitaire, multi-stone rings (`multistone`) and pavé bands (`pave`). Use for any request to model a stone, size a seat for one, estimate a stone's carat weight, or set stones in a ring.
---

# gem-library

**Status (2026-10-28).** Stones are exact meshes written by Python (`ntopjewel.gems.StoneSpec`),
checked offline; settings import them into nTop (Import Mesh -> Implicit from Mesh), the same
route the engraving uses. A 6.5 mm round comes out at 1.02 ct (trade table: 1.00).

```powershell
python -m ntopjewel gem --shape round --length 6.5                                  # ideal round, diamond
python -m ntopjewel gem --shape pear --length 12.3 --width 8.9 --depth 4.6 --material glass   # a calipered stone
python -m ntopjewel gem --shape emerald --length 8 --width 6 --dry-run              # numbers only
```

Writes `out\gems\<stem>.stl` and `<stem>.stone.json` (spec, crown/girdle/pavilion, volume,
carats, extents). Stem: `stone_<shape>_<L>x<W>x<depth>` with `p` for the decimal point.

## The body

Girdle outline (length along X, width along Y, centred), crown from the girdle top to a table
scaled from the outline (57 % round, 55 % pear/marquise, 60 % cushion, 65 % emerald), girdle band
(3 % of width, at least 0.1 mm, mid-plane at z = 0), pavilion to a culet point. Ideal heights
are crown 15 % and pavilion 43 % of the width; `--depth` scales both to a measured stone and
keeps the girdle. Pear: round end at +X, point at -X. Facets are not modelled: a setting
needs the envelope, not the facets.

Densities come from `data/jewelry_tables.json` (`stones`, all `default`): diamond 3.52,
moissanite 3.22, cz 5.80, corundum 4.00, beryl 2.72, quartz 2.65, glass 2.60. For a costume
stone, weigh it and add a calibrated entry.

## Seats (the `stone_seat` block)

```powershell
python -m ntopjewel seat --shape round --length 6.5                      # 0.05 mm clearance, 8 mm drop-in path
python -m ntopjewel seat --shape pear --length 12.3 --width 8.9 --depth 4.6 --clearance 0.08 --dry-run
```

The cutter a head subtracts: the stone plus its girdle outline carried straight up (the
drop-in path), offset by the clearance. Python writes the envelope (convex hull of stone +
lifted outline); the block imports it and offsets it in nTop. Gate: closed, one shell, nTop
volume vs mesh, **design volume vs Steiner's exact offset volume** (V + S c + M c² + 4/3 π c³ -
exact for convex bodies, and every stone here is convex), extents = stone + 2 x clearance.
Defaults (`settings` in `data/jewelry_tables.json`): clearance 0.05 mm, drop 8 mm. Files in
`out\seat\<stem>\<run id>\`.

## Prong heads (the `prong_head` block, `ntopjewel.heads`)

```powershell
python -m ntopjewel head --length 6.5 --prongs 6                 # the solitaire head
python -m ntopjewel head --length 6.5 --prongs 4 --dry-run       # numbers only
```

N straight prongs from feet below the culet to tips above the girdle, on two torus rails
(open basket underneath), minus the `stone_seat` cutter: above the girdle the prongs stop at
the girdle line + clearance (the stone drops in; the setter bends the tips), below it each
prong keeps a 0.3 mm ledge the girdle sits on. Default prong diameter leaves >= 0.8 mm above
the girdle (1.2 mm for a 6.5 mm round). Gate: closed, one shell, **stone fits** (head ∩
stone ≈ 0), **seat ledges** (N prongs reach under the girdle), **drop-in clear** (none inside
the girdle line above it), volume vs an independent trimesh/manifold build of the same
numbers. v1: round stones only.

## Outline heads: pear and other fancy stones (the `outline_head` block, `heads.OutlineHeadSpec`)

```powershell
python -m ntopjewel head --shape pear --length 12.3 --width 8.9 --depth 4.6 --material glass   # 5 prongs: the point + 4 on the round end
python -m ntopjewel head --shape pear --length 12.3 --width 8.9 --depth 4.6 --dry-run
```

Any shape other than round goes to `outline_head` (a round one with `--outline`). Prongs sit on the
girdle outline; each rod hugs the pavilion (offset prong radius - ledge, so the seat cut leaves a
groove the stone rests in) and rises straight from the girdle. Python writes the rods as one STL
(Prongs Path, like the stone and the engraving); nTop makes the rails: the seat cutter offset by
Rail Offset, cut to two slabs, so they follow any outline and pass through every prong. Gate as the
round head, with ledges and drop-in judged on the stone's outline. Pear: the point gets a V-prong plus four round prongs on the round end. Marquise: a V at each
point plus 4 side prongs. `--no-v-prong` puts a round prong on the point instead. The V is a
chevron wall (>= 0.8 mm) hugging the outline about 1.5-1.8 mm back from the point, from 0.6 mm
under the girdle to just above the tips, carried down the pavilion by a rod; the seat cut leaves
the point a ledge inside it. Oval, cushion, emerald: 4, 6 or 8 on rays from the centre.

## Bezels (the `bezel_head` block, `heads.BezelSpec`)

```powershell
python -m ntopjewel head --bezel --length 6.5                                   # a 6.5 mm round in a bezel
python -m ntopjewel head --bezel --shape pear --length 12.3 --width 8.9 --depth 4.6 --wall 0.7 --lip 0.4
python -m ntopjewel solitaire --bezel --size 6 --length 6.5                      # solitaire_bezel.ntop
```

The seat cutter grown by the wall (default `bezel_wall_mm` 0.65 in the tables; 0.5-0.8 burnishes),
cut from the cup's edge to `bezel_lip_mm` (0.5) above the girdle, minus the cutter: a straight
wall above the girdle, a cup on the pavilion below. Light windows (`--windows`, default 6 where
the cup has room, else a closed cup) under a solid `bezel_bearing_mm` band. Any of the six shapes.
Gate: fit, seated, drop-in, the wall a closed ring at least the wall floor thick, volume.

## The solitaire (`solitaire.ntop`, `solitaire_outline.ntop`, `solitaire_bezel.ntop`, `ntopjewel.solitaire`)

```powershell
python -m ntopjewel api build solitaire                                # once: ntop\notebooks\solitaire.ntop (embeds stone_seat + prong_head)
python -m ntopjewel solitaire --size 6 --length 6.5 --prongs 6        # court band, gothic arches, arch milgrain; out\solitaire
python -m ntopjewel solitaire --size 6 --dry-run                       # placement and cathedral numbers
python -m ntopjewel solitaire --size 6 --deliver --metal sterling      # PASSED -> Jewelry\Solitaires\<stem>\ + print-scaled STL
python -m ntopjewel api build solitaire_outline                        # once: the fancy-stone notebook (embeds stone_seat + outline_head)
python -m ntopjewel solitaire --size 4.5 --shape pear --length 12.3 --stone-width 8.9 --stone-depth 4.6 --material glass --engrave Makena
python -m ntopjewel solitaire --size 6 --length 6.5 --width-bottom 2.4 --thickness-bottom 1.2   # on a tapered shank (Phase 3 step 1d)
python -m ntopjewel solitaire --size 6 --length 6.5 --split 1.6 --split-span 80                # a split shank: the slot runs under the head, through the arches
python -m ntopjewel solitaire --size 6 --shape marquise --length 10 --stone-width 5 --split 1.6 --split-span 100 --knot trinity   # ring 01: trinity knots on the shoulders
python -m ntopjewel solitaire --profile flat --width 2.8 --thickness 2 --prongs 4 --no-arches --sides leaves --outer scroll   # the Seraphine: artwork panels under the head
python -m ntopjewel solitaire --profile flat --width 2.8 --thickness 2 --prongs 4 --no-arches --sides leaves --outer scroll --shoulder-knot trinity   # ... and a trinity knot on each shoulder
```

The shank is always the bars Python writes (`ntopjewel.shank.ShankSpec`, as the `shank` command:
`<stem>.bar.stl`, `.bar2.stl` ... in the run directory, the smallest repeated in unused slots; `Shank Path` .. `Shank Path 4` / `Wrap Length` inputs, catalogs 0.9 / 0.5): each
Import Mesh → Implicit from Mesh → opened by the edge round, then united → Remap Cylindrical =
Band Body → carved by the artwork layers at `Cut Path` / `Relief Path` (`nj.add_carved`: (Band Body −
Panel Cuts) ∪ Relief = Carved Band; no-op specks without artwork) → the arches, opened on their own,
united with it. Ring 01 (the marquise on the
trinity shank) built PASSED in nTop on 2 Nov; its 7 "shells" were the mesher's zero-volume
bubbles where the rails' feet kiss the band's dome, which the gate now reports apart. Bodies that cross each other (a
split's halves, a knot's strands) come in separate bars and nTop unites them (`ring-band`). Plain by default; `--width-bottom`,
`--thickness-bottom`, `--taper-from` (≥ the arches' wedge + 3°, i.e. 50° at the default
shoulder) taper it towards the bottom of the finger (stem `..._w4-2.4_t1.3-1.2_...`). `--split`
splits it (`--split-span`, `--split-shape` as the `shank` command): the halves carry the slot
and its fillets in the bar, and the arches are cut by the same slot swept in the ring frame
(`<stem>.slot.stl`, the `Slot Path` input; a speck far outside the ring when there is no split)
before their own opening rounds the cut; the head must bridge the slot (its lowest metal
reaches `head_foot_half_span` either side of the centre - 2.07 mm for the round head's lower
rail - so the slot may be at most that less 0.3 mm, twice), and the bore check runs beside the
slot. `--knot trinity` on a split shank (reference ring 01; `ring-band` has the knot itself)
replaces the arches: the band runs either side of the head out to a nose between the knot's
lobes - as far as the head reaches along the ring plus 0.5 mm (`SolitaireSpec.knot_pad_deg_needed`,
set on the `ShankSpec` unless `--knot-pad` asked for more) - and the arches and their milgrain
are off: the notebook keeps no conditional, so the arch inputs become one stub buried in the
band under the head - both arch centres on the same point of the +X axis at mid-thickness, so the
arches' intersection is a whole cylinder of 0.7 mm or less (`buried_stub_radius`: 0.1 inside the
bore and the outer face; `arch_inputs`: Z Top/Bottom ±0.5, a 2 mm dome tube, a 10° wedge, the cut
inside the bore; catalogs 0.7.1 / 0.3.1 widened their ranges for it, no rebuild), which the
opening chain erodes by the edge round, meshes and dilates, and which changes nothing. (Two stubs
4° apart met in a 0.11 mm lens that a 0.1 mm erosion emptied before the mesh round trip -
2026-11-03, the flat band under the Seraphine head; the knot shank's edge round of 0 had hidden
it; `validate` refuses a band too thin to bury the stub past its round.) The independent model
builds the stub as a thin unopened wall. Slot Path is a speck (the band under the head is
whole), Edge Round 0 (the knot shank's rounds are all in its bar), the gate's section angles
skip the knots, and the design volume takes no slot-edge term. Contoured, double, rope and
plait shanks under a head are refused for now (the arches and the head placement assume a band
centred on the mid-plane).

A non-round `--shape` runs `solitaire_outline.ntop`. `--engrave TEXT` cuts it inside the shank
(`--engrave-side outside` for the outside), centred opposite the head, 0.3 mm deep, letter height
to fit the band (`--engrave-height`, `--engrave-depth`); the gate's `engraving` check finds the
pocket. The text is part of the spec id but not the stem.

**Artwork under the head** (`ring-features` has the panels themselves): `--sides` / `--outer` (a motif, or
`none`, the default), `--start` / `--end`, `--channel`, `--rail`, `--relief`, `--leaf`, `--leaf-pitch`,
`--stroke`, `--no-vein` as the `artwork` command - `SolitaireSpec.panels` and the artwork numbers,
`SolitaireSpec.artwork` the `ArtworkSpec` over the shank. The band is carved before anything joins it
(the channel edges stay crisp, the relief is never rounded), so each panel's head end is held back
(`panel_start_min_deg`): past the arches' wedge + 1° (inside it the arch fills the band's faces from
mid-wall outward), or with **`--no-arches`** (plain shoulders: the head stands on the band, milgrain
off, the arch inputs the buried stubs as for a knot shank) just past the head's reach along the ring
(the placed head or its seat cutter, whichever reaches further) + the shank blend + 0.5 mm - 21.6° for
the 6.5 mm round 4-prong on the 2.8 x 2.0 flat band, so the Seraphine's panels from 25° are not
moved. A panel ending inside that is refused, as is an outside engraving with an outer panel, and the
artwork's own rules apply (a court band's domed outer face refuses the relief: flat bands). The gate
adds `channel floors` / `relief` / `rails`, keeps the channel zones out of the wall sample, compares
the section shape inside the panels against the carved band's core (`artwork.gate_section` within
`artwork.section_clip`: below the channel floors - a relief edge on the section plane read as the
relief's height, 2026-11-03) and uses the carved band as the independent shank (`carved_shank_mesh`,
design volume and blend estimate alike). The `bore` check measures outside the head's zone
(`head_zone_deg`: its reach along the ring + 5°) and `bore under the head` within it, allowing
`BLEND_BORE_BULGE` (0.2) x the shank blend on the radius: nTop's smooth union bulges the bore where
the head's lowest metal runs within the blend of it (36 µm with the lower rail 0.2 mm above the flat
band's bore; a court band's comfort relief keeps its rail away). `blend_bore_note` says so in the
run's notes and names the `--finger-clear` that would clear it (0.75 on the Seraphine).
Stem `..._art_<id>`; `<stem>.cut.stl` / `.relief.stl` in the run directory, delivered with the part.

**Shoulder knots** (`--shoulder-knot trinity`; `ntopjewel.ornament.KnotOrnament`): a closed Celtic trinity
knot standing on the band's outer face on each shoulder, between the head and the panels, as the
Seraphine's - the trefoil φ = 2t, ρ = R (1 + c cos 3t) about a point on the band's mid-line, one lobe
pointing down the shank, the weave solved by `knotwork.interlace` and the ribbon lying on the face
(its underside 0.1 inside it) under the bore law, lifting by thickness − fuse only to pass over itself
(ramp 1.0 mm: a shorter one bent the sweep tighter than the ribbon's half-thickness and folded it).
`--knot-width` (default the band's + 1.2: the lobes overhang the band, as ring 01's), `--strand-width`
(ribbon 0.7), `--knot-thickness` (0.5), `--knot-at` (its centre from the top; default just past the
head, `KNOT_HEAD_CLEAR_DEG` beyond `head_clear_deg`). Each knot is cut into two pieces between its
third/fourth and sixth/first passes, so each holds one pass of every crossing; both knots' first pieces
go in `<stem>.knot.stl`, the seconds in `<stem>.knot2.stl` (`Knot Path` / `Knot Path 2`, catalogs
0.10.0 / 0.6.0: pieces that cross each other never share a mesh), each read back and refused if it
crosses itself; nTop unites them with the carved band (`nj.add_carved`'s union) after its opening - the
ribbon's rounds are its own. Buried specks when there are no knots. Plain shoulders only (`--no-arches`),
a flat outer face, a plain band; the panels are held back `PANEL_KNOT_CLEAR_DEG` past the knots'
span. `validate` wants three open lobes at least 0.3 mm wide and the bore law to come down before the
next under pass. Gate: `knot ribbon` / `knot surround` probes (a grid over the knot's footprint and the
band beside it, cast on the built ring and the design alike), the section check sits the knots' span
out, the wall sample skips it. Stem `..._art_knot_<id>`.

**Shoulder knots** (`--shoulder-knot trinity`; `ntopjewel.ornament.KnotOrnament`): a closed Celtic trinity
knot standing on the band's outer face on each shoulder, between the head and the panels, as the
Seraphine's - the trefoil φ = 2t, ρ = R (1 + c cos 3t) about a point on the band's mid-line, one lobe
pointing down the shank, the weave solved by `knotwork.interlace` and the ribbon lying on the face
(its underside 0.1 inside it) under the bore law, lifting by thickness − fuse only to pass over itself
(ramp 1.0 mm: a shorter one bent the sweep tighter than the ribbon's half-thickness and folded it).
`--knot-width` (default the band's + 1.2: the lobes overhang the band, as ring 01's), `--strand-width`
(ribbon 0.7), `--knot-thickness` (0.5), `--knot-at` (its centre from the top; default just past the
head, `KNOT_HEAD_CLEAR_DEG` beyond `head_clear_deg`). Each knot is cut into two pieces between its
third/fourth and sixth/first passes, so each holds one pass of every crossing; both knots' first pieces
go in `<stem>.knot.stl`, the seconds in `<stem>.knot2.stl` (`Knot Path` / `Knot Path 2`, catalogs
0.10.0 / 0.6.0: pieces that cross each other never share a mesh), each read back and refused if it
crosses itself; nTop unites them with the carved band (`nj.add_carved`'s union) after its opening - the
ribbon's rounds are its own. Buried specks when there are no knots. Plain shoulders only (`--no-arches`),
a flat outer face, a plain band; the panels are held back `PANEL_KNOT_CLEAR_DEG` past the knots'
span. `validate` wants three open lobes at least 0.3 mm wide and the bore law to come down before the
next under pass. Gate: `knot ribbon` / `knot surround` probes (a grid over the knot's footprint and the
band beside it, cast on the built ring and the design alike), the section check sits the knots' span
out, the wall sample skips it. Stem `..._art_knot_<id>`.

Band options are the `band` ones (`--width` is the band's; the stone's are `--stone-width`,
`--stone-depth`). `--finger-clear` (default 0.6 mm, never under the wall floor) is the metal
between the bore and the culet; `--shoulder` (default 45°) is where the arch leaves the band
(tangentially: the arch is the band's section swept round a circle tangent there, through a crest
0.6 mm under the girdle). Milgrain runs along both edges of both arches, from the tangent point
to just short of the head: `--no-milgrain`, `--bead-radius` (0.3), `--bead-pitch` (2.2 radii).
The head is the `prong_head` block turned a quarter about +Y so its axis points out along +X;
the seat cutter goes through the shank as well. Gate: closed, one shell, walls on the band
(x < -2, the shank's floor), bore Ø, bore closed at the top (the culet/feet do not break into
it), extents, stone fits / ledges / drop-in measured in the head frame, **arch milgrain** (every
designed bead's apex found by a ray), **section shape** on the plain part of the shank (the
gate's 12 angles less the arches' wedge about the head and the engraving's span opposite it,
against `ShankSpec.gate_section`: a shank built plain where a taper was designed fails here),
volume vs nTop and vs the independent ring (design + blend − the chamfer nTop's opening puts on
the shank's rounds).

## Multi-stone rings (`multistone.ntop`, `ntopjewel.multistone`, Phase 3 step 2)

```powershell
python -m ntopjewel multistone --size 6 --length 6.5 --side-shape round --side-length 4                 # a round three-stone
python -m ntopjewel multistone --size 6 --shape cushion --length 7 --stone-width 6 --side-shape pear --side-length 6 --side-width 4   # ring 05
python -m ntopjewel multistone --size 6 --length 6 --side-shape round --side-length 3 --side-pairs 2      # five in a row
python -m ntopjewel multistone ... --width-bottom 2 --thickness-bottom 1.4 --dry-run                    # on a tapered shank; numbers only
```

A centre stone and `--side-pairs` side stones each side, every one in an **outline head** (the
`outline_head` block - prongs on its outline, rails following its pavilion; round stones too, 4/6/8
prongs; a pear 5 with its V; a marquise a V at each end). Band defaults: court 2.6 x 1.8, Mesh
Tolerance 0.05. Each head is placed as the solitaire's (the quarter-turn about a pivot ∥ +Y onto
+X) after a **spin** about its own axis (sides ±90°: their length runs along the band, a pear's or
marquise's point at the centre; `--centre-spin 90` turns the centre's length along the band) and
before a **turn** about the ring axis to its angle. Every culet stands at least `--finger-clear`
above the bore; a small side stone whose two rails need more room under it than that leaves stands
higher, until its lowest metal is 0.2 mm above the bore (`MultiStoneSpec._seating`).

**The side angles are solved**: for each side stone the smallest turn (bisection to 0.0001°, plus
0.01°) at which its girdle is `--side-gap` (0.3 mm) clear of its neighbour's and neither stone's
seat cutter - drop-in path included - takes metal from the other's head. Prongs may touch and fuse
(nTop's blended union); a seat may not cut a neighbour's prong. Usually the prongs bind, not the
gap: `describe()` prints the girdle gaps it got.

The notebook has five slots (`Seat Path`, `Prongs Path`, the five rail numbers, `Spin`, `Pivot X`,
`Pivot Z`, `Turn`; slot k > 1 suffixed " k"); a three-stone ring repeats the centre in slots 4 and
5 (the same head in the same place unites to nothing new). One `Clearance`, `Head Blend` and `Shank
Blend` for all. Ring = ((shank ∪ placed heads), blended) − placed seats. The shank is the bars
(plain or tapered; no rope, knot, double band or split yet; the heads must stay inside the taper's
full section).

Gate (`multistone.check_multistone`): the shank's walls and section shape away from the heads
(beyond their reach + 8°), bore, `bore closed under the stones`, extents against the design, and
for each stone in its own frame `stones fit`, `seat ledges` (every prong under its girdle) and
`drop-in clear`; the design volume with every head's blend estimate and the heads-into-shank
junction. A notebook whose side slots never got their own values fails `seat ledges` and the
design volume. Stem `ring_multi_<n>_<centre>_<side>_<size>_<spec id>`; runs in `out\multistone\`.

## Pavé bands (`pave_band.ntop`, `ntopjewel.pave`, Phase 3 step 2/3)

```powershell
python -m ntopjewel pave --size 6 --stone 1.3 --span 180                     # one row over the top half
python -m ntopjewel pave --size 6 --stone 1.3 --rows 2 --span 120            # two staggered rows (nested)
python -m ntopjewel pave --size 6 --stone 1.3 --rows 2 --layout aligned --eternity   # a grid all round
python -m ntopjewel pave --size 6 --rows 3 --span 90 --dry-run               # the layout, the band, the inputs
```

Rows of round stones (`--stone` 0.8-3 mm, `--rows` 1-4, `--layout staggered|aligned`, `--span`
degrees centred on the top or `--eternity`) set in the band's surface. Each stone sits in a seat cut
along the surface normal: its envelope (crown and girdle carried straight up, the drop-in path)
grown by the seat clearance, the table `pave_table_below_mm` below the surface, a light hole
(`pave_hole_frac` x the stone) drilled on through to the bore. Beads (`pave_bead_frac` x the stone,
at least the 0.5 mm floor) stand in the gaps `pave_bead_gap_mm` outside the openings they border:
from every pair of neighbouring stones the two points at that holding distance from both, points
closer than a bead's diameter merged (a staggered triangle's three meet at its centre), beads off
the band's top or holding no real stone dropped; every stone needs `pave_min_beads`. **The pitch is
solved on the real 3-D geometry**: neighbours' normals converge towards the axis, so their girdles'
lower edges come closest - the pitch along a row and the spacing across rows are bisected until
those edges stand `pave_stone_gap_mm` apart (a full eternity widens the pitch to divide 360°).

The band is `ring_shank`'s (plain, or tapered with the pavé inside the full section; no rope,
knot, double band, split or dip yet). With no `--width` / `--thickness` the band is sized to the
layout (`pave.band_for`: the outer rows' openings plus a 0.5 mm wall to the edge, rounded up to
0.1 mm; the seat plus the light hole's shoulder plus 0.75 mm, at least 1.6 mm), comfort-flat
(a flat top), at `pave_mesh_tolerance_mm` 0.05 (the webs between seats are 0.1 mm).

Python writes `<stem>.seats.stl` (every cutter, disjoint) and `<stem>.beads.stl` (every sphere,
disjoint) beside the bars; the notebook builds `(shank ∪ beads) − seats`, the seats cut after the
beads so every drop-in path is clear (a bead in a tight interstice comes out trimmed by the
openings, as on the bench); neither layer is opened by the edge round.

Gate (`pave.check_pave`): the band's checks (bore, width, outer Ø over the beads, walls with seat
and bead faces left out - the floor under the stones is measured from the bore, the outer rows'
walls to the band's edge - the section shape through the pavé against the design's within the mesh
tolerance, design volume = band ∪ beads − seats less the band's opening corrections) and the pavé's:
`stones fit` (ring ∩ every stone), `light holes open`, `seats` (every floor at its depth),
`drop-in clear`, `beads` (every apex where designed) and `stones held` (each stone's standing
beads >= `pave_min_beads`) - rays cast identically on the built ring and on the design, so the
imported facets are the same on both. A notebook that loses the beads fails `beads` and `stones
held` (the volume barely moves); one that never cuts the seats fails five checks.

Stem: `ring_pave_<profile>_<size>_w<W>t<T>_<rows>[s|a]x<stone>_<span>deg|eternity_<spec id>`;
runs land in `out\pave\`, `--deliver` in `Jewelry\Pave\`.

## Blends (every head and solitaire notebook)

Metal-to-metal junctions are blended in nTop (prongs into rails, rail and bezel edges, the head into
the shank) by `blend_radius_mm` from the tables (0.3; `--blend` for the head's own, `--shank-blend` for
the join; 0 = sharp; at most 1 mm and never wider than the feature joined). The seat and the engraving
are cut after the blended join, so the stone's clearance survives. The independent model is unblended:
the gate expects the design plus `blend_volume_factor` x r² x the exposed junction length (calibrated
2026-10-30 on nTop 6.3.3: 0.32; an intersection's rounded edges count against) and says so in the
design-volume line; a blended intersection may shrink the extents by the blend radius (the pear's
rails: 0.23 mm). Beads stop 0.8 x the shank blend clear of the head. Offline, the simulated nTop
blends too (`tests/pseudo_blend.py`).
