---
name: gem-library
description: Parametric stone bodies (round, oval, pear, marquise, cushion, emerald) for settings, seats and cutters, with volume and carat weight - the `gem` command and ntopjewel.gems. Use for any request to model a stone, size a seat for one, or estimate a stone's carat weight from its dimensions.
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
```

The shank is always the bar Python writes (`ntopjewel.shank.ShankSpec`, as the `shank` command:
`<stem>.bar.stl` in the run directory; `Shank Path` / `Wrap Length` inputs, catalogs 0.7 / 0.3):
Import Mesh → Implicit from Mesh → opened by the edge round → Remap Cylindrical = Band Body; the
arches are opened on their own and united with it. Plain by default; `--width-bottom`,
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
are off: the notebook keeps no conditional, so the arch inputs become two 0.7 mm stubs buried
in the band 4° either side of the head (`arch_inputs`: Z Top/Bottom ±0.5, a 2 mm dome tube, a
10° wedge, the cut inside the bore; catalogs 0.7.1 / 0.3.1 widened their ranges for them, no
rebuild), which the opening chain can mesh and which change nothing; the independent model
builds the same stub with a 0.1 mm wall. Slot Path is a speck (the band under the head is
whole), Edge Round 0 (the knot shank's rounds are all in its bar), the gate's section angles
skip the knots, and the design volume takes no slot-edge term. Contoured, double, rope and
plait shanks under a head are refused for now (the arches and the head placement assume a band
centred on the mid-plane).

A non-round `--shape` runs `solitaire_outline.ntop`. `--engrave TEXT` cuts it inside the shank
(`--engrave-side outside` for the outside), centred opposite the head, 0.3 mm deep, letter height
to fit the band (`--engrave-height`, `--engrave-depth`); the gate's `engraving` check finds the
pocket. The text is part of the spec id but not the stem.

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
