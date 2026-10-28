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
