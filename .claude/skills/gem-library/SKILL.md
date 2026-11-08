---
name: gem-library
description: Parametric stone bodies (round, oval, pear, marquise, cushion, emerald, asscher, cabochon, pearl) for settings, seats and cutters, with volume and carat weight - the `gem` command and ntopjewel.gems - and the settings built from them, prong heads, bezels, the solitaire, multi-stone rings (`multistone`) and pavé bands (`pave`). Use for any request to model a stone, size a seat for one, estimate a stone's carat weight, or set stones in a ring.
---

# gem-library

**Status (2026-10-28).** Stones are exact meshes written by Python (`ntopjewel.gems.StoneSpec`),
checked offline; settings import them into nTop (Import Mesh -> Implicit from Mesh), the same
route the engraving uses. A 6.5 mm round comes out at 1.02 ct (trade table: 1.00).

```powershell
python -m ntopjewel gem --shape round --length 6.5                                  # ideal round, diamond
python -m ntopjewel gem --shape pear --length 12.3 --width 8.9 --depth 4.6 --material glass   # a calipered stone
python -m ntopjewel gem --shape emerald --length 8 --width 6 --dry-run              # numbers only
python -m ntopjewel gem --shape asscher --length 7                                   # a square step cut (--width ignored)
python -m ntopjewel gem --shape cabochon --length 10 --width 8 --cab-dome 0.4        # flat base, girdle band, elliptic dome
python -m ntopjewel gem --shape pearl --length 8 --drill 1.0 --drill-depth 0.6       # half-drilled from below for a post; material pearl
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

**Asscher** (2026-11-05): the emerald's cut-corner outline on a square (corners cut 25 % of the
width), table 62 %, a deep step-cut pavilion (crown 15 %, pavilion 47 % of the width). A faceted
stone: everything round and fancy shapes do applies; on point in a multistone with `--centre-spin 45`.

**Cabochon**: an elliptical outline, a flat base at the girdle band's underside (z = -g/2), a girdle
band (8 % of the width, at least 0.3 mm: the bezel or claws hold it there), an elliptic dome of
`--cab-dome` x the width (default 0.35; 0.1..0.6). No pavilion: heights (dome, 0).

**Pearl**: a sphere of diameter `--length` with its equator as the girdle line (girdle 0), half-drilled
from below for a post: `--drill` Ø (default 1.0 mm; 0.5 mm to a third of the pearl), `--drill-depth`
x the diameter up (default 0.6; 30-80 %). Material defaults to `pearl` (nacre, SG 2.71) for a pearl and
to the tables' default stone for everything else. The seat keeps the drill open: `geom.offset_convex`
offsets the hull and subtracts the drill narrowed by the clearance (`geom.drill_of` finds it), as
nTop's exact offset of the drilled envelope does, so the post survives the seat cut.

Densities come from `data/jewelry_tables.json` (`stones`, all `default`): diamond 3.52,
moissanite 3.22, cz 5.80, corundum 4.00, beryl 2.72, quartz 2.65, glass 2.60, pearl 2.71. For a
costume stone, weigh it and add a calibrated entry.

## Seats (the `stone_seat` block)

```powershell
python -m ntopjewel seat --shape round --length 6.5                      # 0.05 mm clearance, 8 mm drop-in path
python -m ntopjewel seat --shape pear --length 12.3 --width 8.9 --depth 4.6 --clearance 0.08 --dry-run
```

The cutter a head subtracts: the stone plus its girdle outline carried straight up (the
drop-in path), offset by the clearance. Python writes the envelope (convex hull of stone +
lifted outline); the block imports it and offsets it in nTop. Gate: closed, one shell, nTop
volume vs mesh, **design volume vs Steiner's exact offset volume** (V + S c + M c² + 4/3 π c³ -
exact for convex bodies; a pearl's drilled envelope is measured by `geom.offset_convex` instead), extents = stone + 2 x clearance.
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
the point a ledge inside it. Oval, cushion, emerald, asscher: 4, 6 or 8 on rays from the centre.

The unfaceted stones ride the same block (same inputs, no rebuild) with another prong and rail layout
(`OutlineHeadSpec.kind`: faceted | cabochon | pearl):

```powershell
python -m ntopjewel head --shape cabochon --length 10 --width 8                  # 4 upright claws, a plate under the base, a collar round the band
python -m ntopjewel head --shape pearl --length 8                                # a cup, a post up the drill and 4 claws following the sphere
python -m ntopjewel head --shape pearl --length 8 --prongs 0 --cup 0.25          # cup and post alone (the pearl is glued on the post)
```

- **Cabochon**: claws straight up beside the girdle band from the plate to a tip over the dome
  (girdle/2 + max(0.8, 0.35 x the dome)), bent over by the setter; ONE rail, a slab from under the
  plate below the base to the top of the collar round the girdle band (the plate alone when the band
  is too thin for a collar of the wall floor). 4, 6 or 8 claws. Upper Rail Top may rise above 0
  (catalogs 0.2.1 / 0.7.1, a range widened: no rebuild).
- **Pearl**: ONE rail, the cup: the seat grown by Rail Offset from below the pearl to `--cup`
  x its diameter up (default 0.2; 0.1..0.4); a post (the drill less the clearance, at least the wall
  floor) from the cup floor up the drill, in the prongs mesh; 0, 3, 4 or 6 claws following the sphere
  from the cup and bending in above the equator.
- Gate: the faceted heads' seat ledges are replaced by hold checks (`heads.hold_checks`): **prongs**
  (metal at every claw's knee just above the girdle), cabochon **seat floor** (the plate under >= 90 % of
  the base), pearl **cup** (>= 90 % of a ring halfway up the cup) and **post** (>= 80 % of the drill
  filled at its mid-height). Fit, drop-in (a pearl's drill exempt), one shell and volume as before. The
  simulated nTop's `noprongs` fault (the prongs mesh lost) is what the claws and post checks catch.
- **One rail, never two that meet.** The block's Basket is ONE blended union of the prongs and both rails,
  and two rails that overlap or meet swell it (the smooth minimum of a body with itself stands about a quarter
  of the blend outside it): the first real pearl head, its cup given as both rails, came out 0.08 mm thicker
  all over, +9.6 % design volume (2026-11-05). A one-rail head sends the other slab to `heads.EMPTY_RAIL`
  (z -15 .. -14.9, below everything: an empty rail); `heads.rail_overlap_problems` refuses rails that
  overlap or meet, and the simulated nTop swells them as nTop does, so the gate catches it offline.

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

## Partial bezels (the `partial_bezel_head` block, `ntopjewel.partial_bezel`)

```powershell
python -m ntopjewel api build partial_bezel_head                 # once: ntop\blocks\partial_bezel_head.ntop + its harness
python -m ntopjewel head --partial-bezel --shape pear --length 10 --width 7 --depth 4.5          # two walls on the flanks, a hood over the point
python -m ntopjewel head --partial-bezel --shape oval --length 8 --width 6                       # an east-west half bezel (no point: no hood)
python -m ntopjewel head --partial-bezel --shape pear ... --wall-from 0.2 --wall-to 0.6 --hood-reach 1.8 --lip 0.8
```

A bezel kept on two mirrored wall stretches along the stone's flanks, a hood over each point (pear: one,
marquise: two; `--no-hood` none), a full cup under the girdle carrying the stone all round (the bearing). Any
outline: a round, oval, cushion, emerald or asscher gets an east-west half bezel (walls 0.30..0.70). The walls are
**fractions of the half outline from the -X end** (a pear's point) - a pear's flanks are not circular sectors -
turned into angles about the outline's centroid for nTop (`PartialBezelSpec.span`, `.angles()`); a pear's default
runs from just past its hood (reach + 0.6 mm) to 0.70, a marquise's between its hoods. Inherits the bezel's wall
(0.65), lip (0.5), clearance and blend.

**Built in nTop from primitives, every number from Python** (no mesh but the seat envelope): grown = Offset Body
(Seat Cutter, Wall); mask = a SHARP union of the cup slab (Box from Corners, Bezel Bottom .. Cup Top), the +y wall's
sector (a y >= 0 box turned by Wall To Angle ∩ a y <= 0 box turned by Wall From Angle, about the vertical through Wall
Centre X; Bezel Bottom .. Bezel Top) and its Mirror Body across y = 0, and a vertical Cylinder per hood (Hood X / Hood 2
X, Hood Reach, up to Hood Top; an unused hood at x 60, cutting nothing); head = (grown ∩ mask, ONE blended
intersection: the rim, the wall ends and the hood rounded) − Seat Cutter. No blended union: the pieces overlap, and a
smooth union of bodies meeting on a face swells them (the pearl's cup).

Gate (`check_partial_bezel`, and `partial_bezel_checks` on the finished ring in the head's frame): fit, seated,
drop-in, and probes of the design's intent, not the builder - **walls** (5 stations per side at the girdle and half
way up the lip, the wall where it should be), **open** (no metal above the cup over the stretches without a wall),
**hoods**, **point clear** (metal ∩ stone within 1 mm of each point: the aggregate fit check can hide a small point
collision), **bearing** (the cup under the girdle at 12 stations). The simulated nTop's faults `noside` (a wall never
mirrored), `nohood` and `fullbezel` (the mask's walls lost) fail `walls`, `hoods` and `open`.

**The ring** (`solitaire_partial_bezel.ntop`, `solitaire --partial-bezel`): placed as the bezel (the cup carried down
into the band to the floor), no arches by default. The reference photo's look - the pear low between broad domed
shoulders - is a broad thick top section on a tapered shank:

```powershell
python -m ntopjewel api build solitaire_partial_bezel
python -m ntopjewel solitaire --partial-bezel --shape pear --length 10 --stone-width 7 --stone-depth 4.5 --profile half-round --width 9.5 --thickness 3.3 --width-bottom 2.8 --thickness-bottom 1.7 --lip 0.8 --tolerance 0.06
```

The 10 x 7 x 4.5 pear is an illustrative fixture, not the photo's stone (unmeasured); about 11 g in sterling. Mesh Tolerance
0.06 for it: the broad band has ~40 % more surface than our other rings, and at 0.05 the real run made 5.29 M
triangles (264 MB), past the gate's 5 M `mesh density` limit (triangles ∝ 1/tolerance²: 0.06 gives ~3.7 M; its 0.03 mm
voxel still resolves the 0.65 mm walls and 0.3 mm blends).

**The print file**: add `--prep` to any build (or `--prep-stl <the STL>` / `--prep-stl delivered` with the arguments it was built with) for `<stem>.supported.stl` - oriented, supported on polished faces and the bore only, on a raft, one body to slice as it is (`--bore avoid`, `--orient`, `--metal`; see `jewelry-design-rules`, "Printing").

## The solitaire (`solitaire.ntop`, `solitaire_outline.ntop`, `solitaire_bezel.ntop`, `ntopjewel.solitaire`)

```powershell
python -m ntopjewel api build solitaire                                # once: ntop\notebooks\solitaire.ntop (embeds stone_seat + prong_head)
python -m ntopjewel solitaire --size 6 --length 6.5 --prongs 6        # court band, gothic arches, arch milgrain; out\solitaire
python -m ntopjewel solitaire --size 6 --dry-run                       # placement and cathedral numbers
python -m ntopjewel solitaire --size 6 --deliver --metal sterling      # PASSED -> Jewelry\Solitaires\<stem>\ + print-scaled STL
python -m ntopjewel api build solitaire_outline                        # once: the fancy-stone notebook (embeds stone_seat + outline_head)
python -m ntopjewel solitaire --size 4.5 --shape pear --length 12.3 --stone-width 8.9 --stone-depth 4.6 --material glass --engrave Makena
python -m ntopjewel solitaire --size 6 --shape asscher --length 6                              # an asscher on four claws (solitaire_outline)
python -m ntopjewel solitaire --size 6 --shape pearl --length 8 --prongs 0                      # a pearl on a post in a cup, low on the band
python -m ntopjewel solitaire --size 6 --shape cabochon --length 10 --stone-width 8             # a cabochon on a plate, four claws over the dome
python -m ntopjewel solitaire --size 6 --length 6.5 --width-bottom 2.4 --thickness-bottom 1.2   # on a tapered shank (Phase 3 step 1d)
python -m ntopjewel solitaire --size 6 --length 6.5 --split 1.6 --split-span 80                # a split shank: the slot runs under the head, through the arches
python -m ntopjewel solitaire --size 6 --shape marquise --length 10 --stone-width 5 --split 1.6 --split-span 100 --knot trinity   # ring 01: trinity knots on the shoulders
python -m ntopjewel solitaire --size 6 --length 6.5 --split 1.6 --split-span 120 --knot twist   # rings 06 / 07: the halves cross on each shoulder
python -m ntopjewel solitaire --profile flat --width 2.8 --thickness 2 --prongs 4 --no-arches --sides leaves --outer scroll   # artwork panels under the head, plain shoulders
python -m ntopjewel solitaire --profile flat --width 2.8 --thickness 2 --prongs 4 --no-arches --sides scroll-leaves --outer scroll --shoulder-knot trinity   # the Seraphine: a trinity knot tucked under the head on each shoulder, a volute then leaves (tips to the head) on the sides, the scroll outside
python -m ntopjewel solitaire --size 6 --length 6.5 --hammered        # a hammered band under the head: struck before the arches and the head join it, none within their reach (ring-features skill: textures)
```

A cabochon or a pearl (`SolitaireSpec.unfaceted`) is placed by the head's lowest metal, not a culet: the plate
or cup's underside stands 0.2 mm above the bore at the default `--finger-clear` (0.6; more raises it), so the
stone sits low on the band and there is no room for cathedral arches - the CLI leaves them off for these
stones and the spec refuses them. The gate uses the hold checks (prongs, seat floor / cup, post) in place of the
seat ledges.

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
slot. `--knot twist` (rings 06 / 07; `ring-band` has the twist) sits the head on the whole band the same way:
the pad reaches past the head by 0.5 mm plus the eye's round end (split/2), the arches are off, the head need not
bridge a slot. `--knot trinity` on a split shank (reference ring 01; `ring-band` has the knot itself)
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

**Pavé round a multi-stone ring** (`multistone --pave 1.3 [--pave-rows N --pave-layout --pave-from DEG --pave-material]`;
`MultiStoneSpec.pave_stone_mm` ...): the `pave.PaveSpec` over the same shank, centred on the bottom (`centre_deg`
180), its first girdle edge `PAVE_HEAD_CLEAR_MM` (0.4) + the shank blend past the side heads' metal at the band's
surface (`head_face_reach_deg`, not the prongs' splay above) unless `--pave-from` says where. multistone.ntop 0.2.0
takes `Pave Beads Path` / `Pave Seats Path`: the beads united with the shank before the heads (sharp), the seats cut
with the heads' after the blended join - as pave_band.ntop; no pavé = a speck buried in the band and one far outside.
`validate` refuses a taper under it, an arc too short for a row, and pavé seats that cut a side head. The gate adds
the pavé's own checks (`pavé stones fit / light holes open / seats / drop-in clear / beads / stones held`), drops wall
rays on the pavé's seats and beads, and compares the section through the pavé with the design's. **Not on a court
band**: its dome falls away where the seat openings sit and leaves 0.2 mm lips at any width (p1 0.19-0.24); a
comfort-flat band keeps 0.5-0.6. Stones of different materials: `--material` (the centre; a ruby is `sapphire`,
corundum) and `--side-material`. Stem `ring_multi_3_<centre>_<side>_pave1x1p3_<size>_<id>`.

**Artwork under the head** (`ring-features` has the panels themselves): `--sides` / `--outer` (a motif, or
`none`, the default), `--start` / `--end`, `--channel`, `--rail`, `--relief`, `--leaf`, `--leaf-pitch`,
`--stroke`, `--no-vein`, `--leaf-tip head|shank` (default head: the reference ring's leaves point at the
head; `scroll-leaves` puts a volute at the head end of a leaf row, as its side faces), `--leaf-tilt` and
`--leaf-stem` (the leaves turned ±DEG in turn on a serpentine stem FRAC of the relief high, `ring-features`)
as the `artwork` command - `SolitaireSpec.panels` and the artwork numbers,
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
knot standing on the band's outer face on each shoulder, tucked under the head as the Seraphine's - the
trefoil φ = 2t, ρ = R (1 + c cos 3t) about a point on the band's mid-line, its lone lobe pointing at the
head (`--knot-point head|shank`; the other two spread across the band below it), the weave solved by
`knotwork.interlace` and the ribbon lying on the face (its underside 0.1 inside it) under the bore law,
lifting by thickness − fuse only to pass over itself (ramp 1.0 mm: a shorter one bent the sweep tighter
than the ribbon's half-thickness and folded it). `--knot-width` (default the band's + `OVERHANG_MM` 0.8,
lobe edge to lobe edge: about 1.3 x the band, as the reference ring's), `--strand-width` (ribbon 0.6; 0.7
closed the lobes to 0.22 mm at that width), `--knot-thickness` (0.5), `--knot-at` (its centre from the
top; default the span begins at `knot_clear_deg`: the head's and the seat cutter's reach along the ring
**at the band's face**, between the face and the knot's top - `head_face_reach_mm`, less than the full
reach since the prong tips splay above - plus `KNOT_HEAD_CLEAR_MM` 0.2, so the shank blend melts the
apex into the head's base: 16.8°-36.3° on the Seraphine). Each knot is cut into two pieces between its
third/fourth and sixth/first passes, so each holds one pass of every crossing; both knots' first pieces
go in `<stem>.knot.stl`, the seconds in `<stem>.knot2.stl` (`Knot Path` / `Knot Path 2`, catalogs
0.10.0 / 0.6.0: pieces that cross each other never share a mesh), each read back and refused if it
crosses itself; nTop unites them with the carved band (`nj.add_carved`'s union) after its opening - the
ribbon's rounds are its own. Buried specks when there are no knots. Plain shoulders only (`--no-arches`),
a flat outer face, a plain band. The panels: an outer-face panel is held back `PANEL_KNOT_CLEAR_DEG`
past the knots' span (37.3° on the Seraphine); the side-face panels run on under the knots' overhang
from `head_clear_deg` (25° there), as the reference ring's leaf rows do (`panel_start_min_deg(face)`).
`validate` wants three open lobes at least 0.3 mm wide and the bore law to come down before the next
under pass. A tapered shank may carry the knots when its full section runs `KNOT_TAPER_CLEAR_DEG` (2°)
past their span (and past the panels, `ring-features`): on plain shoulders the taper may not begin under
the head either (`head_clear_deg`); split, contoured and double shanks still wait. Gate: `knot ribbon` / `knot surround` probes (a grid over the knot's footprint and the band
beside it, cast on the built ring and the design alike; the surround from `knot_face_from_mm` on - the
head's reach at the face + the shank blend - because the smooth union lays a 0.25 mm fillet round the
head's foot there, which the knot's apex is meant to melt into; the detail names where the worst probe
lies), the section check sits the knots' span out, the wall sample skips it. Stem `..._art_knot_<id>`.
Built PASSED in nTop 2026-11-03 (one shell + 1 speck, 310/310 ribbon probes, volume −0.10 %) in the
first placement; the photo comparison then moved the knot under the head and turned it - values only,
no rebuild - and that run (2026-11-04) built in one shell with every ribbon and panel probe in place,
failing only on the four surround probes inside the head's fillet.

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
python -m ntopjewel multistone --profile comfort-flat --width 2.6 --thickness 1.8 --length 4 --prongs 4 --row 4 --shared-prongs --gallery   # ring 02
python -m ntopjewel multistone --profile comfort-flat --width 2.6 --thickness 1.8 --shape cushion --length 7 --stone-width 6 --side-shape pear --side-length 6 --side-width 4 --gallery   # ring 05 on a gallery
python -m ntopjewel multistone --profile comfort-flat --width 2.6 --thickness 1.8 --length 4 --prongs 4 --row 4 --shared-prongs --gallery --width-bottom 2 --thickness-bottom 1.4 --engrave "M+K 2026"   # ring 02 as photographed: tapered, engraved inside
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

**Stones in a row** (`--row N`, 2..5): N stones of the centre's kind, symmetric about the top - one
at the top for an odd N, the first pair straddling it for an even N (ring 02's four) - each the
smallest angle on that clears its neighbour, all spun as the centre (role "row").

**Shared prongs** (`--shared-prongs`, `ntopjewel.gallery.Post`): where neighbours face each other,
each one's prong facing the other on each side of the band (one per side: 4-prong heads; a V-prong is
never shared) becomes one straight radial **post** between them, solved (least squares) so that at each
girdle's underside its axis stands `rho - ledge` outside both outlines - it overlaps each stone by
the ledge, like any prong. Its foot stands just inside the band's face (`outer_radius_at`), or in the
rails past the band's edge; its radius starts at the heads' and grows until what both drop-in paths
leave of the tip holds the prong-tip floor. With shared prongs the angles are solved against the
neighbours' rails, not their (now shared) prongs, and every stone gets its own prongs file (an inner
stone of a row keeps none: a speck buried in the band under it). Ring 02: 6 posts, 2 + 0 + 0 + 2 own
prongs, ten prongs for four stones.

**The gallery bridge** (`--gallery`): one rail each side of the band through the heads' upper rails,
its section at each stone the rail where the radial plane through that stone cuts it, straight between
(a structured loft, `gallery.loft_around_axis`: rounded-rectangle stations every 0.5°, no mesh
boolean). The bridge and the posts go to nTop as two layers in the ring frame (`Gallery Path`, `Shared
Prongs Path`, multistone 0.3.0; specks buried in the band without), united with the heads (sharp: the
bridge's section is each head's rail where they meet), and that body melts into the shank by the
blended union - the posts' feet get their fillet - and every seat is cut after.

Gate (`multistone.check_multistone`): the shank's walls and section shape away from the heads
(beyond their reach + 8°), bore, `bore closed under the stones`, extents against the design, and
for each stone in its own frame `stones fit`, `seat ledges` (every prong under its girdle) and
`drop-in clear`; the design volume with every head's blend estimate and the heads-into-shank
junction. A notebook whose side slots never got their own values fails `seat ledges` and the
design volume. With shared prongs `seat ledges` counts each stone's own prongs and the posts beside it,
and `shared prong tips` measures what both seats left of each post above the girdles (inscribed circle
≥ the tip floor less the mesh tolerance); with a gallery, `gallery` probes each bridge rail where the
design shows it outermost. A lost posts layer fails both, a lost bridge `gallery`. Stem
`ring_multi_<n>_<centre>_<side>[_row][_shared][_gallery]_<size>_<spec id>`; runs in `out\multistone\`.

**Engraving** (`--engrave TEXT [--engrave-side inside|outside --engrave-height --engrave-depth]`, multistone.ntop
0.4.0: `Engraving Path` / `Engraving Wrap Length`; rings 02 and 05): the solitaire's text, centred opposite the
centre stone - Python writes it unwrapped, the notebook wraps it, turns it 180° under the finger and cuts it with the
seats after the blended join (the solitaire's own `Engraving` section, `nb_solitaire.engraving`). The letters are
sized on the band *under the text*: on a tapered shank the bottom section (`ShankSpec.engraving_band`: its width sizes
the letters, its thickness the wall left under them; the solitaire now does the same). Refused: text with pavé (the
pavé is centred on the bottom and its light holes open on the bore), text reaching within 10° of the heads, and the
engraving helper's own floors (strokes ≥ 0.3 mm, wall left ≥ the floor) - on a taper the refusal names the bottom
section and what would widen it (a court band tapered to 2 mm leaves too little width for 0.3 mm strokes; comfort-flat
2 x 1.4 takes 1 mm letters). Gate: `engraving` (the pocket opposite the centre; a notebook that never cut the text
fails it alone), wall rays radial only and no section-shape angle through the text. The text is in the spec id only
when there is one (earlier designs keep their ids).

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
