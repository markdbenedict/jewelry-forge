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
round head, with ledges and drop-in judged on the stone's outline. Pear: 5 prongs only (a V-prong
for the point is a later step). Oval, marquise, cushion, emerald: 4, 6 or 8 on rays from the centre.

## The solitaire (`solitaire.ntop`, `solitaire_outline.ntop`, `ntopjewel.solitaire`)

```powershell
python -m ntopjewel api build solitaire                                # once: ntop\notebooks\solitaire.ntop (embeds stone_seat + prong_head)
python -m ntopjewel solitaire --size 6 --length 6.5 --prongs 6        # court band, gothic arches, arch milgrain; out\solitaire
python -m ntopjewel solitaire --size 6 --dry-run                       # placement and cathedral numbers
python -m ntopjewel solitaire --size 6 --deliver --metal sterling      # PASSED -> Jewelry\Solitaires\<stem>\ + print-scaled STL
python -m ntopjewel api build solitaire_outline                        # once: the fancy-stone notebook (embeds stone_seat + outline_head)
python -m ntopjewel solitaire --size 4.5 --shape pear --length 12.3 --stone-width 8.9 --stone-depth 4.6 --material glass --engrave Makena
```

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
(x < -2), bore Ø, bore closed at the top (the culet/feet do not break into it), extents, stone
fits / ledges / drop-in measured in the head frame, **arch milgrain** (every designed bead's apex
found by a ray), volume vs nTop and vs the independent ring.
