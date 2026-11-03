# jewelry-forge — development plan (plan of record)

This file is the plan of record; the claude.ai doc "nTop Jewelry Skills — Development Plan"
is its narrative companion (background on nTop, the skill architecture, sources) and is
updated from here, not the other way round. Dates are evenings-and-weekends pace from
27 October 2026; the order matters more than the dates.

## What exists today (2026-10-27)

| Capability | State | Evidence |
| --- | --- | --- |
| Headless nTop runs through `ntopjewel` (input JSON from the catalog, log + output parsing, success = exit 0 + no `[E]` + "nTop successfully built") | done | Phase 0 band 25 Oct; every run since |
| Mesh gate: watertight, winding, shells, wall thickness by ray casting (radial/axial rays, between bead rows, no letter ribs), inner/outer Ø, width, volume vs nTop, **design volume vs independent arithmetic**, engraving pocket area; statuses PASSED / FAILED / INCOMPLETE | done | `python/ntopjewel/gate.py`, `band.py`, `features.py` |
| Notebook authoring through the Notebook API (SSH to nTop's Python Console, build scripts in `ntop/recipes/`, identifiers resolved at run time, every block's build state checked) | done | `ring_band_profile.ntop` (16 blocks) and `ring_features.ntop` (55 blocks) built from scripts, no GUI work |
| Profiled bands: flat, comfort-flat, court, d-shape, half-round; sizes US/UK/ISO/mm | done, gate PASS for all five profiles | 27 Oct |
| Features: milgrain beads, channel groove, wrapped engraving inside or outside (text meshed in Python, Remap Cylindrical in nTop) | done, gate PASS at US6 and US4.5 (volume within 0.2 % of design, pocket found) | 27 Oct |
| `ring --show`: the same ring rebuilt in nTop's open session to look at | done | 27 Oct |
| Every run in a fresh directory with a distinct stem (`…_w4_t1.3_<spec id>`); delivery = STL + inputs + gate/build report + manifest (notebook sha256, recipe, versions), only when PASSED | done | `python/ntopjewel/runs.py` |
| One engineering-tables file for Python and Blender (`data/jewelry_tables.json`, with status default / calibrated) | done | `tables.py`, `blender/jewelry_kit.py` |
| Simulated nTop for the offline suite that builds the designed geometry (section revolve, beads, groove, engraving) and can be told to misbehave | done | `python/tests/fake_ntopcl.py`; 80 offline tests |
| Blender: parametric band, print/cast checker, silver product shot, monstera leaf band, pear setting | done (pre-nTop work) | `blender/` |

## Phases and gates

| Phase | Builds | Gate (held in the hand, not a screenshot) | State |
| --- | --- | --- | --- |
| 0 — environment + hello band | `ring_band.ntop`, runner, gate | a band built headless from JSON passes the gate | passed 25 Oct |
| 1 — rings | profiled bands; milgrain, groove, engraving; Notebook API authoring | **one printed and cast band** (any profile) measured on the mandrel and weighed | steps 1 and 2 verified 27 Oct, `ring_features.ntop` committed; print + cast waits for the kit (printer/resin being bought) |
| 2 — custom-block library | `ntop/blocks/`: stone seat, prong heads (round, outline, V-prongs), bezel; gem bodies (round, oval, pear, cushion, emerald, marquise); the solitaire assembly (cathedral arches, milgrain, engraving) | a solitaire (6.5 mm round, 6-prong) in sizes 5–7 passes the gate, prints with every prong intact | software half PASSED 29 Oct (round US 5-7, every fancy shape, pear and marquise with V-prongs, bezels offline); the print is what remains (band profile / bead / groove / wrap as library blocks deferred to Phase 3 step 1) |
| 3 — ring styles | the twelve reference rings in `docs/reference/rings/`: blended junctions; shank shaping (taper, contours, split and twisted, knotwork); multi-stone placement and galleries; pavé and accents; pearl, cabochon and asscher bodies; artwork on the band; organic motifs | each capability proven on one reference ring (gated); a three-stone ring and a pavé-shoulder ring printed with every seat open | started 30 Oct: step 0 (blends) built and PASSED in nTop, factor calibrated; step 1a (tapered shank, `ring_shank.ntop`), 1b (contour/chevron centrelines, double bands), 1c (split and rope shanks) and 1d (the solitaire on a tapered or split shank) PASSED in nTop (30 Oct - 1 Nov); the edge-round opening found never to have built, fixed in every notebook and calibrated (31 Oct: band 0.00 %, solitaire −0.08 %); 1e Celtic knotwork written (1 Nov): the plait band and ring 01's trinity-knot shank and solitaire; the trinity's real runs failed on a self-intersecting bar (1-2 Nov), traced to the mesh union's micrometre seams - every shank now goes to nTop as up to four bars that nTop unites (2 Nov); with that the trinity shank, the trinity solitaire and the plait built in one shell (gate tuned for the mesher's zero-volume bubbles and the knots' crease fill); the split's seam groove then moved the opening before the union (four notebooks to rebuild again), real check pending; step 2/3 (`multistone.ntop`, `pave_band.ntop`: the three-stone rings incl. the ruby demo, the pavé band) and step 5 (`ring_artwork.ntop`: the Seraphine's leaf rows and vine) PASSED in nTop 3 Nov; the same panels carved under a solitaire's head (the three solitaire notebooks, `--no-arches` plain shoulders, the `scroll` motif) written 3 Nov, real check pending |
| 4 — pendants, bracelets, chains | bezel/disc/tag pendants with bail, cuffs and bangles, chain links with ≥ 0.35 mm clearance | a text pendant hangs level; a 10-link cable segment prints with every link free | not started |
| 5 — casting prep | sprues, trees, shrink scaling, weight and metal estimates, flask layout | a tree of Phase 1–3 parts cast in one pour; `cast_ring_size_offset` and the shrink factors calibrated | not started |
| 6 — hardening | sweeps (`values: [...]`), batch delivery, second-laptop build server, skills polished | the full suite plus the real checks below pass on both laptops | continuous |

## Current limitations

- Shrink: `--deliver --metal` writes the print file scaled for casting + resin shrink, but the
  metal shrink figures are defaults and the resin's is an uncalibrated 0 %: the first print and
  cast set them (Phase 1 gate).

- No part has been printed or cast yet: every wall floor, density, shrink figure and the
  `cast_ring_size_offset` in `data/jewelry_tables.json` is a **default**, not a calibration.
- The Notebook API cannot register units, set `file_path` or `real_field` parameters, or force a
  lazy block to build; the build scripts route round all of these (see `CLAUDE.md`). nTopCL is
  the only check for a block that never built in the GUI session.
- The thickness check is statistical (4000 rays, p1 against the floor) and excludes bead rows and
  letter ribs by rule, not by understanding the geometry; a thin feature in an excluded zone is
  not measured. The design-volume cross-check catches a wrong section, not a locally thin one.
- The simulated nTop proves the pipeline's logic, not nTop's behaviour: Import Mesh's unit
  handling and voxel effects are only seen in real runs; its blends carry nTop's calibrated
  volume but not nTop's shape (square-cornered fill pieces, not a smooth bump); it does not run
  the opening, so a design whose fillets are not in Python's geometry (a bridge's ends) is only
  rounded for real. The opening in nTop was a no-op until 30 Oct (see Phase 3 step 1). It unites
  the shank's bars as meshes (in the ring frame) where nTop unites implicits: a mesh union is
  what the real nTop could not import (2 Nov), so the simulation cannot show that failure.
- A mesh boolean's result never goes to nTop as a bar: its seams hold faces micrometres apart
  that float32 STL and Import Mesh turn into self-intersections (Phase 3 step 1e). Bodies that
  cross each other travel in separate bars (up to four) and nTop unites them; a design needing
  more than four mutually crossing bodies has no notebook yet.
- Blender scripts run only on the laptops (bpy); the offline suite imports them with stubs.
- nTop runs on the main laptop only (32 GB); casting trees may need the 128 GB machine.

## Phase 2 order of work

1. Stone bodies - done (Python meshes, `gem`).
2. *(done 28 Oct: built, round and pear seats PASSED under nTopCL)* The first library block, `ntop/blocks/stone_seat.ntop`: stone mesh path in, the stone
   implicit plus its seat cutter (the stone, a clearance offset and a straight drop-in path
   above the girdle) out; built by a script, embedded and measured by a harness notebook that
   nTopCL runs, so the block has a gate of its own.
3. *(done 28 Oct: built, embedded, PASSED under nTopCL)* `prong_head`: N prongs on an open two-rail basket, seat cut by `stone_seat` (drop-in above the girdle, a ledge under it), >= 0.8 mm of prong left above the girdle; gate: stone fits, ledges, drop-in clear, volume vs an independent trimesh/manifold head. Round stones (torus rails); fancy outlines need outline rails.
4. *(written 29 Oct, offline green; first real build pending)* `bezel_head` (`ntop/recipes/bezel_head.py`): the seat
   cutter offset by the wall (`bezel_wall_mm` 0.65) ∩ a slab from the cup's edge to `bezel_lip_mm` (0.5) above the girdle,
   minus the cutter: a straight wall above the girdle to burnish over the crown, a cup on the pavilion below it, any
   outline. Light windows (6 stadium slots under a `bezel_bearing_mm` 0.55 band; none where the cup has no room) are a
   Python STL (Windows Path), subtracted. Gate: fit, seated, drop-in, `bezel wall` (the section half way up the lip
   shrunk by half the wall floor is still one closed ring), volume. `solitaire_bezel.ntop`: the solitaire body with the
   bezel; on a ring the cup runs down into the band (the floor 0.2 mm above the bore). Offline: round 6.5, Makena pear
   US 4.5 and 10x5 marquise bezel rings PASSED. The check that counts pieces in a section now keeps holes (a bezel
   ring's outer boundary alone covered the stone's opening).
5. `solitaire.ntop` (`ntop/recipes/solitaire.py`): court band + embedded `stone_seat` + `prong_head`,
   head turned a quarter about +Y onto the band top, culet 0.6 mm above the bore.
   - *28 Oct, first real build:* PASSED at US 5-7 with a circular-segment shoulder that barely read as a
     cathedral. Mark's review: milgrain on the arch only, and a more graceful arch-to-band transition.
     `gate.json` was found written before the family checks (fixed: `gate.save`).
   - *v2 (written 28 Oct, offline green; real build pending):* **gothic tangent arches**. Each shoulder
     is the band's own section swept round a circle tangent to the band at ±45° and through a crest
     0.6 mm under the girdle; at the tangent ray the arch's section is the band's, so the band flows into
     the arch. Arches are cut to a ±47° wedge (two corner boxes turned about Z) and stop at mid-wall,
     united with the band before its edge-round offsets (one rounding over both). **Arch milgrain**: four
     rows (both edges, both arches) of 0.3 mm beads at 2.2 radii, polar-arrayed about the arch centres,
     from the tangent point to 0.2 mm short of the head's envelope (8 per row at US6).
   - Gate adds `arch milgrain` (a ray at each designed bead must meet its apex; missing beads change the
     volume ~1 %, inside the design-volume tolerance). Design volumes: US6 286.6 mm³.
   - Unchecked until the real build: `box_from_corners` input names (resolved by type), the wedge turn's
     sign (right-handed, as the head's turn proved), and whether nTop's offset over band ∪ arch matches
     the independent model (design volume and the bead check will say).
   - *v2 built 28 Oct:* PASSED at US 5 and 6 under nTopCL (32/32 beads, design volume +0.5 %).
5b. *(done 28 Oct: outline_head + solitaire_outline built; the Makena ring PASSED under nTopCL first time - 325.7 mm³ vs 324.5 designed (+0.35 %), 28/28 beads, engraving pocket found, bore 15.288 exact)* **Fancy stones and engraving.** `outline_head` block
   (`ntop/recipes/outline_head.py`): prongs on the girdle outline (pear: the point + four on the round end),
   each rod lying on the pavilion offset by prong radius - ledge (a cone's normal is constant along a
   generator), upright from the girdle; Python writes the rods as one STL (Prongs Path); the rails are the
   seat cutter offset by Rail Offset ∩ a slab, so they follow any outline and meet every prong. Gate:
   fit, ledges and drop-in judged on the outline (`heads.outline_count`). `solitaire_outline.ntop` = the
   solitaire body (now `ntopjewel.nb_solitaire`, shared with `solitaire.ntop`) with the outline head; on
   a ring the head's floor is 0.2 mm above the bore (feet and lower rail move up the pavilion); arch beads
   stop by distance to the real head and seat meshes. **Engraving** in both solitaire notebooks: the
   ring_features pipeline, the wrapped text turned 180° to sit opposite the head; gate `engraving` (pocket
   found) and the wall check skips the text's axial ribs. First ring: US 4.5 court, 12.3 x 8.9 x 4.6 pear
   (glass), 5 prongs, "Makena" inside: 324.5 mm³ designed. `solitaire.ntop` must be rebuilt (new
   engraving inputs). 29 Oct: the first offline ring gate of the other four shapes found every 4-prong head
   had 3 prongs (prong angles past 180° were not wrapped; fixed, regression test); oval 8x6, marquise 10x5,
   cushion 7, emerald 8x6 PASSED under nTopCL on 29 Oct, as heads and as US 6 solitaires (nTop within
   0.2 % of the design for the heads, 0.6 % for the rings). `solitaire.ntop` (round) still needs `api build
   solitaire` for the engraving inputs; the round US 5-7 re-runs follow.
   - *V-prongs (done 29 Oct: the Makena pear US 4.5 and a 10x5 marquise US 6 PASSED under nTopCL, +0.37 % / +0.45 %):* a stone's point (the pear's, both of the
     marquise's) gets a V: the outline grown by the V wall (prong radius, >= 0.8 mm) within max(1.5, 0.2 W) of
     the point, 0.6 mm under the girdle to just above the tips, on a support rod down the pavilion. Part of the
     prongs STL, so no block or notebook rebuild. Marquise default = 2 V + 4 side prongs. `--no-v-prong` restores
     the round prong. The pear and marquise designs (and stems) change. The marquise's 4 prongs left both
   points bare.
6. Gate: 6.5 mm round 6-prong solitaire, sizes 5-7, PASSED and printed. *PASSED 29 Oct under nTopCL (US 5 / 6 / 7:
   +0.51 / +0.58 / +0.48 % vs design, every check green, engraving inputs in place); printing it with every prong
   intact is what remains.*

## Phase 3 order of work — ring styles

The reference set is `docs/reference/rings/` (README: what each ring needs). Mark's call (30 Oct):
explore the ring space fully before pendants, bracelets and chains; blends first.

0. *(built 30 Oct: all six notebooks rebuilt; blended round head, round ring and bezel ring PASSED
   first time; the pear ring failed only the gate's extents check, which was the gate's fault - a
   blended intersection rounds the rails' outermost edges away, so extents may now shrink by the
   head's blend radius; `blend_volume_factor` calibrated 0.17 → 0.32 on those four runs)*
   **Blended booleans.** nTop's Boolean Union /
   Intersect `Blend Radius` (a `real_field`: wired from a mm variable, the Blend Type enum left at its
   default) on every metal-to-metal junction: `prong_head` prongs ∪ rails; `outline_head` rails ∩ slab
   (edges rounded) and prongs ∪ rails; `bezel_head` cup ∩ slab (rim and lip rounded); the solitaires'
   head ∪ shank. **The seat and the engraving are cut after the blended join**: a smooth union fills
   every corner two surfaces make within its radius, the seat's corners included (0.05 mm clearance).
   Default `blend_radius_mm` 0.3 (tables); `--blend`, `--shank-blend`; 0 = sharp. The independent model
   stays unblended and bounds what the blend adds: `blend_volume_factor` x r² x the junction length
   (`geom.junction_length`, from manifold3d's face origins; a union's junction counts where it is
   exposed - not buried in the shank, not inside the seat cut - and an intersection's edges count
   against); the design-volume check expects design + that estimate (the factor is calibrated:
   0.32 r² per mm reproduces the head and the bezel ring exactly and over-predicts the prong rings
   by < 0.3 % of their volume). Arch beads keep 0.8 x the shank blend clear of the head. The
   simulated nTop blends too (`tests/pseudo_blend.py`: square-cornered fill pieces along every
   junction loop, cut off along an intersection's edges, carrying the tables' volume), so the
   offline suite gates blended meshes; the one place its fill is cruder than nTop's is a foot of
   the round head meeting the hollow under the arches, where it stands 0.05 mm into the bore
   (nTop's did not: the US6 run passed the bore check), so the round-ring tests keep that one
   join sharp. *Next real check:* measure the min vertex radius under the head in the blended
   US6 STL to see what nTop's fill does there.
1. **Shank shaping.** *(1a and the rope PASSED in nTop 30 Oct; 1b and the split rebuilt, real run
   pending)* Every shaped shank
   is made one way: Python writes the ring **unrolled as a bar** (X radial, Y along the ring, Z
   axial; a cross-section every 2.5°), nTop imports it and wraps it round Z with Remap Cylindrical
   Body (`ring_shank.ntop`; r, z and the angle are exact under that map, as the engraving showed),
   the independent model sweeps the same sections round the axis directly, and the gate measures
   the built section against the design at twelve angles. 1a **tapered section** (`shank`:
   `ShankSpec`, width and thickness at the bottom, the taper's start angle, a cosine ease; the
   thin end validated as a band; walls gated against the thinnest station). 1b *(written 30 Oct,
   offline green)* **centrelines**: the band's centre leaves the mid-plane near the head - a
   cosine `contour` bump or a `chevron` V (`--dip`, `--dip-span`) - and **double bands**
   (`--double`: two strands of the band stacked with a gap, nested or mirrored into a wishbone,
   joined by full-thickness bridges at chosen angles); strands and bridges are united by nTop
   (each strand a bar of its own, the bridges another, since 2 Nov - see 1e) and, independently,
   in the ring frame; the gate's section check compares z and r bounds per angle. Same notebook. 1c *(30 Oct)* **split and rope shanks**: `--split` cuts a slot that
   opens at the head and closes towards the bottom (contour or chevron, round ends, each half at
   least 1 mm); the halves are lofted the whole way round from the 2-D opened sections, so the
   slot's fillets are in the bar (they overlap where the slot is closed, each drawn a wedge inside
   the other so no faces coincide; the model is that union, each half its own bar for nTop to
   unite since 2 Nov). `--rope` makes the band two or three round strands twisted a whole number
   of turns round the ring (tubes round helices in a fixed-up frame, the innermost just touching
   the bore, overlapping into one solid - a bar each). The notebook
   **opens the bar by the band's edge round** before the wrap (`Edge Round Inward` / `Edge Round`;
   catalog 0.2.0) for whatever a union left sharp (a bridge's ends), and the gate's expected volume
   takes off e²(tan(δ/2) − δ/2) per mm of every convex edge turning more than 30° in the design
   mesh. **Real runs 30 Oct:** the tapered shank PASSED (sections within 0.004 mm, volume +0.00 %),
   the 2 x 10 rope PASSED (−0.02 %); the split failed its section check at the head - the model
   had ignored the slot's effect on the bore and dome extents (fixed) - and its slot edges came
   back **sharp**, which exposed the finding below. Next: 1d **the solitaire on a shaped shank**
   (its shank a bar too: the arches and beads move into the bar frame or stay in nTop); Celtic
   knotwork last. The band profile, bead row, groove and engraving wrap become library blocks on
   the way.

   **The opening never built (found 30 Oct).** nTop's Offset Body adds a constant to the field,
   so the two offsets every band notebook ran since Phase 1 (−e, +e) cancelled: all five real
   profiles match their *unopened* sections to 0.05 % (court 4 x 1.3: 245.60 mm³ vs 245.55
   unopened, 243.99 opened), every solitaire sits +0.4..0.6 % above its design by the same
   1.5 mm³, and every part built so far has sharp band edges. It passed because the design-volume
   tolerance was 2 %. Fixed by re-distancing between the offsets (`nj.add_opening`: Mesh from
   Implicit → Implicit from Mesh; in `add_profiled_band` and `ring_shank`), the band's
   design-volume tolerance is 0.5 %, the Pappus model is exact on the section polygon, and the
   gate gained a **section shape** check (the built outline at 12 angles against the designed 2-D
   section, Hausdorff within 0.03 mm or half the mesh tolerance: the real court band reads 0.049
   against its opened section and 0.020 against the unopened one; a wrapped shank 0.004; a rope
   0.034 at its strands' crease, which nTop's mesher rounds by a voxel). The blend factor stands
   (it was calibrated on blended-minus-unblended nTop volumes). **Rebuilt and run 31 Oct:** the
   court band's edges are rounded (shape 0.019; volume 243.06 against 243.99 for the exact
   opening: the re-distance mesh chamfers the eroded corners by about a voxel, so the round is
   fuller than e - modelled as `opening_chamfer_voxels` = 1.0, calibrated, after which the band
   matches to 0.00 % and the split to +0.3 %); the split PASSED with rounded slot edges (shape
   0.031); the solitaire's band edges are rounded too (0.009 at the bottom), but opening the
   band *united with the arches* grew a 0.07 mm layer over the arch feet, where the arch dome lies
   on the band's dome (+1.1 mm³; the re-distance mesh of two near-coincident surfaces) - the
   arches are now opened on their own and united afterwards - rebuilt and run 31 Oct: the US6
   round PASSED at −0.08 % of its design + blend (287.72 vs 287.95 mm³). Every part now has the
   edges the design says it has. 1d *(written 1 Nov, offline green, real build pending)* **the
   solitaire on a shaped shank**: every solitaire's shank is now the bar Python writes
   (`SolitaireSpec.shank`, a `ShankSpec`; plain by default), imported, opened and wrapped in the
   notebook exactly as `ring_shank` does, the arches opened apart and united; `--width-bottom`,
   `--thickness-bottom`, `--taper-from` taper it (the taper must start outside the arches' wedge);
   the gate adds the section-shape check on the plain arc (clear of the arches and the engraving)
   and takes the shank's chamfer off the expectation. `--split` gives the **split-shank
   solitaire** (reference rings 01, 06): the halves carry the slot in the bar, the arches are cut
   by the same slot swept in the ring frame (`Slot Path`, a speck when there is none) before
   their opening, the head must bridge the slot (its foot's reach across the band, 2.07 mm either
   side for the round head's lower rail), and the bore check runs beside the slot. Contoured,
   double and rope shanks under a head are refused until the head placement and the arches
   follow them. Catalogs 0.7 / 0.3 (Shank Path, Wrap Length, Slot Path in; the five
   primitive-band inputs out). **Real check 1 Nov: all three PASSED** (the plain round from a
   bar, the tapered and the split solitaire). 1e *(written 1 Nov, offline green, real run
   pending)* **Celtic knotwork** (`knotwork.py`): strands interlaced in the ring's developed
   surface, with the one rule every Celtic knot obeys - at each crossing one strand over, one
   under, alternating along every strand (the over/under of each strand's first crossing solved
   so every crossing is consistent; a diagram that cannot alternate is refused). The interlace is
   a radial law: a strand sits at mid-depth between crossings and rises or sinks by h at each
   (a cosine from crossing to crossing), the over strand's inner face 0.1 mm inside the under
   strand's outer face so they fuse into one casting; strands are ribbons (rounded rectangle,
   `ribbon_profile`) or round wires swept along their centrelines (`sweep_along`; the rope's
   `tube_along` is now a round case of it), in the bar frame for nTop and the ring frame for the
   model. First pattern, the **plait band** (`shank --knot plait --knot-strands 2..4
   --knot-repeats R [--strand-width w] [--knot-profile round]`): n sinusoids phased 2π/n, the
   band's width and thickness its envelope (strand thickness (T + 0.1)/2, two stacked at a
   crossing make T; bore and outer Ø exact). Gated as a rope is (sections off the bar wrapped,
   e = 0, walls at 0.8 t); the three designs (2 and 3 ribbons, 4 wires) pass offline, the bar
   wrapped matches the ring-frame model to 0.01 % and 0.013 mm. Second, the **trinity knot**
   (reference ring 01): a triquetra woven from a split shank's two halves on each shoulder -
   the trefoil curve (three lobes, three self-crossings at radius R) with its down-shank lobe
   opened and led out as the halves by cubic tails that narrow the half's section into the
   knot's ribbon (0.9 x 0.7 T), the other two lobes flanking the band under the head, which
   ends in a nose that enters the knot's head-side crossing. `shank --split ... --knot trinity
   [--knot-width --knot-thickness --knot-ratio --knot-tail --knot-pad]` builds it as a band;
   `solitaire --split ... --knot trinity` puts a head on it: the arches and milgrain give way to
   the knots (the arch inputs become stubs buried in the band under the head - no notebook
   change, catalogs 0.7.1 / 0.3.1 only widen ranges), the band under the head is sized from the
   head's reach along the ring, the gate skips the knots' angles. What it took (all 1 Nov): the
   full-lift "bore" law bent the ribbon tighter than its thickness; a sweep that passes over
   itself is no manifold (two pieces sharing one ring and cap); overlaps drawn a hair apart left
   needle faces at every junction (bodies now meet in one identical face); a strand station in a
   loft's cap plane, and a pad station at the wrap's cut angle, broke the STL round trip
   (stations kept off those planes; the fake's weld merges within 0.01 µm). **Real runs 1-2 Nov
   FAILED** (the trinity shank twice, the trinity solitaire once): nTop called the bar
   self-intersecting and built it in 5 / 161 shells (volume still within 0.1 %). Collapsing the
   union's micron edges (`geom.collapse_short_edges`) changed nothing, and the "very close
   vertices merged" warning turned out routine (an STL is a triangle soup). The cause, found with
   an exact triangle-pair test on the bar: a **mesh union of bodies that cross each other leaves
   faces micrometres apart along its seams** (16 pairs, 0-10 µm apart, at the strands' crossings
   and where they enter the pad's noses, the ring-frame union itself; manifold3d's seam corners
   are that small), which float32 STL (±2 µm at y ≈ 60) and the import turn into
   intersections; `geom.clean` cannot help (it merges coplanar facets into mm-long triangles,
   which the vertex-wise unwrap turned into 3858 intersecting pairs on the slot's faces). **So no
   bar carries a mesh union any more** (2 Nov): bodies that cross each other go to nTop in
   separate bars - `ShankSpec.bar_meshes`, up to four (`Shank Path` .. `Shank Path 4`, catalogs
   ring_shank 0.3 / solitaire 0.8 / 0.4; an unused slot imports a speck inside the first bar) -
   and nTop's Boolean Union joins the implicits before the opening and the wrap. A split's
   halves one each; a double band's strands one each and its bridges another; a rope's or a
   plait's strands one each; the trinity's lower half with the strands' first pieces, its upper
   half with their second and the pad on its own, each piece running a 0.1 mm plug (its section
   drawn in 4 %) into the half and the piece that continue it, so the union sees overlaps and
   never a shared face. Each of the three trinity bars has no intersecting triangle pair as
   written (float32), its shells 0.54 mm apart; the simulated nTop (which unites the wrapped bars
   in the ring frame, `bars_from_inputs`) rebuilds the design to 0.00 %, one shell. **Real runs
   2 Nov, four notebooks rebuilt: no self-intersection anywhere.** The trinity shank built in one
   shell, volume −0.07 %, sections within 0.025 mm outside the knots and 0.057 inside them (a
   pass over another makes a step crease the mesher fills by a voxel at each of its two round
   trips: the knot angles now take the whole mesh tolerance, `ShankSpec.section_tolerance`);
   the trinity solitaire (ring 01) built right in every check but the shell count: 7 "shells"
   that are 12-face bubbles of no volume where two surfaces kiss (the strands' rounded corners
   passing each other, the rails' feet on the band's dome inside the blend), the plait 2 - the
   gate now counts a closed component under 1e-6 mm³ as a degenerate speck beside the shells, not
   as one (`gate.SPECK_VOLUME_MM3`); with those two gate changes Mark's STLs re-gate PASSED. The
   plain split shank through the new union failed its section by 0.058 at the bottom: a 0.05 mm
   groove along the halves' seam on both the bore and the outside, because the opening eroded the
   *union's* field, which inside the overlap wedge measures to a half's buried face. **Each bar is
   now opened on its own and the opened bars united** (catalogs .1: same inputs, rebuild the four
   notebooks again). **Rerun
   17:00, 2 Nov: trinity shank, ring-01 solitaire and plait PASSED; the split shank failed the
   same 0.058** - its `ring_shank.ntop` was the 14:52 build, a commit behind (pulled, not rebuilt).
   Nothing could tell: the inputs had not changed. So `api build` now stamps every notebook it
   saves (`<name>.build.json`: catalog versions, sha256), catalogs carry `rebuild_since`, and a run
   on an older notebook is refused naming the rebuild (`runs.require_built`); every command ends
   in one verdict line and `ntopjewel runs` tabulates the day's runs. **The 20:00 rebuilds then
   all timed out:** the unused slots' speck, eroded by the 0.25 mm edge round, was empty, nTop's
   Mesh block failed on it (`Bounding box for this Implicit Body is empty`) and the chain never
   built. An unused slot now imports the smallest real bar again. **3 Nov, 07:18: the four
   notebooks built and stamped (nTop needs the focus to run its Python at speed); the split shank
   through the per-bar opening still read 0.056 at the bottom** - the crown 0.055 mm low along the
   seam at every closed angle. Not the union's field this time but the halves' overlap: the
   opening rounds the edge where a half's cut face meets the crown by the edge round, which
   begins 0.25 mm back from the cut, and the halves overlapped only 0.1 mm, so the two
   quarter-rounds met in a groove (r = 9.603 + sqrt(0.25² − 0.15²) = 9.803 vs 9.853 designed;
   built 9.798). Each half is now lofted edge round + mesh tolerance past the centreline
   (`ShankSpec.split_overlap_mm`, 0.35 mm), and a 2-D emulation of the per-bar opening in the
   tests reads the groove at 0.1 and nothing at 0.35. *Real check:* `shank --split 1.6
   --split-span 100` (a Python-side change: no rebuild) - bottom sections within ~0.01 mm. Then
   step 2.
2. **Multi-stone placement and galleries.** *(3 Nov: the multi-stone ring written and gated offline -
   `multistone`, `multistone.ntop`, `ntopjewel.multistone`: a centre and 1-2 side pairs, every stone in an
   outline head (round included), spun (a pear's point at the centre), placed as the solitaire's and
   turned about the ring axis; each side angle bisected to the smallest at which no seat cuts a
   neighbour's head and the girdles stand `--side-gap` apart; five slots, unused ones repeat the centre.
   Gated per stone in its own frame. *Real check:* `api build multistone`, then the round three-stone and
   ring 05's cushion + pears - PASSED, and a look in the GUI at where the prongs between stones meet.
   Not yet: the gallery bridge under the heads, shared prongs (ring 02), engraving.)*
   N heads at (angle, tilt) along the band from the head
   library, a gallery bridge underneath, shared prongs for stones in a row; gate: every stone fits,
   seats and drops in, stone-to-stone clearance.
3. **Pavé and accents.** *(3 Nov: the pavé band written and gated offline - `pave`, `pave_band.ntop`,
   `ntopjewel.pave`: rows (1-4, staggered or aligned) of round stones over any span or all round, each
   in a seat cut along the surface normal with a light hole to the bore, held by beads standing just
   outside the openings; the pitch solved on the girdles' 3-D edges (neighbours' normals converge);
   Python writes the seats and the beads as one mesh each, the notebook builds (shank ∪ beads) − seats;
   the gate probes every hole, seat floor, drop-in path and bead with rays cast on the built ring and
   the design alike. *Real check:* `api build pave_band`, then `pave --rows 1 --span 180` and
   `pave --rows 2 --span 120` - PASSED, and a look at the beads in the GUI at Mesh Tolerance 0.05.)*
   Rows of 1–1.5 mm rounds along a path with seats and beads, graduated sizes,
   small polygon bezels (kite, hexagon); spacing and bead rules into the tables.
4. **New stone bodies.** Pearl (sphere on a post in a cup), cabochon (dome on a flat base), asscher
   (emerald outline with a corner-cut ratio); their seats.
5. **Artwork on the band.** *(3 Nov: started, from the Seraphine Celtic ring Mark photographed -
   leaf rows in channels on both side faces, a vine scroll in a channel on the outer face, 25°-120°
   from the top, Celtic knots on the shoulders, scroll volutes under a 4-prong head with double claws
   and a heart-shaped gallery. `artwork`, `ring_artwork.ntop`, `ntopjewel.artwork`: panels (a sunk
   channel on the outer or a side face over an arc, rails along its edges) with a 2-D motif in relief
   on the floor - `leaves`, `vine`, `volute`, `plain` - built in the bar frame and wrapped; Python
   writes the cutters and the relief, the notebook builds (shank − cuts) ∪ relief; the gate probes
   every panel's floor, relief and rails on a grid. **First real run (11:16): every panel probe passed
   and the volume matched to 0.03 %, but 4 needle shells stood on the side faces - nTop read the cutter
   layer as self-intersecting (3-D subdivision's T-junctions bent by the wrap; earcut's sliver caps fold
   too). Layers are now structured lofts and constrained-Delaunay prisms, and refused at write time if
   they cross themselves.** *Real check:* `artwork --sides leaves --outer vine` again (no rebuild) -
   PASSED (13:00), one shell, +0.04 % volume, every probe. **Under the head (3 Nov, afternoon):** the three
   solitaire notebooks take `Cut Path` / `Relief Path` after `Slot Path` (catalogs 0.9.0 / 0.5.0, rebuild)
   and carve the opened band (`nj.add_carved`) before the arches, the milgrain and the blended head join
   it; `SolitaireSpec.panels` + the artwork numbers, each panel's head end held back past the arches'
   wedge or, with `--no-arches` (plain shoulders, the head standing on the band - the Seraphine's), just
   clear of the head's reach + the shank blend; a `scroll` motif (the vine with a full volute at its head
   end, the reference ring's scrolls at the base of the head); side channels measured from the band's edge
   thickness and a domed outer face refused under relief; the no-op relief a speck buried in the band
   (an outside speck came out of a union as a second shell). The gate carries the three probe checks
   under the head. *Real check:* `api build solitaire` (and `solitaire_outline`, `solitaire_bezel`), then
   `solitaire --profile flat --width 2.8 --thickness 2 --prongs 4 --no-arches --sides leaves --outer scroll`
   - and the plain `solitaire --size 6` again, whose band now passes through the carve with specks.
   **Still missing for the Seraphine:** the knots standing on a continuous band beside the head (ours are
   woven from a split), double-claw prongs and the heart gallery (6).)* Scroll and floral relief panels,
   leaf borders, vein engraving: the medallion's 2-D artwork pipeline plus the engraving wrap, raised or cut.
6. **Organic motifs.** Leaves, vines, scrolls, the crescent moon: parametric silhouettes bent onto the
   shank where they are simple; Blender sculpts imported as meshes where they are not.

## Next acceptance milestone — the Phase 1 gate

1. `python -m ntopjewel api build ring_features`; commit `ntop\notebooks\ring_features.ntop`
   and `ntop\recipes\ring_features.recipe.json`.
2. Choose the band to print (profile, size, with or without features); `python -m ntopjewel ring … --deliver`
   produces `OneDrive\Documents\Jewelry\Rings\<stem>\` with the STL, inputs, reports and manifest.
3. Print it; measure the inner diameter on the mandrel; set `allowance_mm` (and, if the
   printer under-sizes bores consistently, a calibrated `print_bore_offset` entry in the tables).
4. Cast it; weigh it; record the cast size offset and the measured density in
   `data/jewelry_tables.json` with a dated `calibration_log` entry and `status: calibrated`.
5. The gate passes when the cast band sits on the mandrel at the designed size (±0.1 mm) and
   weighs within 5 % of the gate's prediction.

## Verification: what is simulated and what must be real

The offline suite (`pytest python\tests -q`, also run by GitHub Actions on Linux and Windows for
every push) covers: the catalog and input JSON rules; log and output parsing; the Notebook API
client against a fake notebook with realistic identifiers; the mesh gate on real meshes; the
whole band/ring path against the simulated nTop, including the rejections (wrong profile,
missing volume, no export, stale export, conflicting names); the Blender modules with stubbed
`bpy`. It cannot establish anything about nTop itself or a render. The real checks, run on the
laptop whenever a notebook, a build script or the gate changes:

| Check | Command | Pass means |
| --- | --- | --- |
| GUI build | `python -m ntopjewel api build <recipe>` (nTop open, console open) | every block `e_OK`, notebook saved, recipe exported |
| Template | `python -m ntopjewel templates ntop\notebooks\<nb>.ntop --catalog <name>` | "catalog matches the notebook" |
| Headless run + gate | `python -m ntopjewel band …` / `ring …` / `shank …` | `status: PASSED`, design volume within tolerance, section shape within 0.03 mm (an edge left sharp fails here, 30 Oct) |
| Visual | `python -m ntopjewel ring … --show`; eyes on the ring in nTop | beads, groove, text where designed |
| Blender | `blender -b -P blender\monstera\test_ring.py -- 6`; the product shot (skill `blender-jewelry-render`) | check_model report and renders written under `out\blender\` |
| Physical | print, measure, cast, weigh (above) | the Phase 1 gate |

`pytest python\tests -q -m slow` is reserved for tests that call the real nTopCL; none exist yet
(the first will wrap the headless run above once a printer and resin are chosen).
