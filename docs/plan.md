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
| 3 — ring styles | the twelve reference rings in `docs/reference/rings/`: blended junctions; shank shaping (taper, contours, split and twisted, knotwork); multi-stone placement and galleries; pavé and accents; pearl, cabochon and asscher bodies; artwork on the band; organic motifs | each capability proven on one reference ring (gated); a three-stone ring and a pavé-shoulder ring printed with every seat open | started 30 Oct: step 0 (blends) built and PASSED in nTop, factor calibrated; step 1a (tapered shank, `ring_shank.ntop`), 1b (contour/chevron centrelines, double bands), 1c (split and rope shanks) and 1d (the solitaire on a tapered or split shank) PASSED in nTop (30 Oct - 1 Nov); the edge-round opening found never to have built, fixed in every notebook and calibrated (31 Oct: band 0.00 %, solitaire −0.08 %); 1e Celtic knotwork written (1 Nov): the plait band and ring 01's trinity-knot shank and solitaire; the trinity's real runs failed on a self-intersecting bar (1-2 Nov), traced to the mesh union's micrometre seams - every shank now goes to nTop as up to four bars that nTop unites (2 Nov); with that the trinity shank, the trinity solitaire and the plait built in one shell (gate tuned for the mesher's zero-volume bubbles and the knots' crease fill); the split's seam groove then moved the opening before the union (four notebooks to rebuild again), real check pending; step 2/3 (`multistone.ntop`, `pave_band.ntop`: the three-stone rings incl. the ruby demo, the pavé band) and step 5 (`ring_artwork.ntop`: the Seraphine's leaf rows and vine) PASSED in nTop 3 Nov; the same panels carved under a solitaire's head (the three solitaire notebooks, `--no-arches` plain shoulders, the `scroll` motif) PASSED in nTop 3 Nov 22:30, and with trinity knots tucked under the head on the shoulders 23:31 (`solitaire.ntop`; the outline and bezel notebooks still to rebuild); the Seraphine then tuned against the photos (4 Nov: knot apex at the head, volute + leaves on the sides) |
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
   *Twisted split (5 Nov, rings 06 / 07): `--knot twist` on a split shank - the halves cross over each other on
   each shoulder. Built as the split it is: each half is ONE loft the whole way round (half k from the crossing
   zones round the bottom, the other half under the head, the strand between), so the shank is the split's two
   bars and nTop's notebooks are unchanged (no rebuild). In a zone of `--twist-length` (8 mm) the strand's
   section morphs from its half into the mirror-image half by a half cosine (outlines started below their own
   centre, so the morph is point for point), its centre following, its width stretched by the slope it runs
   across the ring at; both strands thin to `--knot-thickness` (0.7 T) where they cross, the upper half lifted
   onto the lower (fused 0.1) over the length their footprints overlap, easing back by a cosine to the zone's
   ends. The slot becomes two eyes per shoulder: closed under the head (a round end split/2 deep, the pad sized
   from the head by the solitaire), split_mm where the strands leave it and where they become the halves, the
   split's law from there to the span. No opening (the lofts carry the rounds); the gate reads the design
   inside the zones. Refused: a zone too short for the over strand to come down (ramp >= 1 mm, rise radius >=
   t/2 + 0.1), the slot closed before the zone ends, a taper starting inside it. Offline PASSED: the shank
   (4 x 1.6 court, 1.6 split: crossings at 56°, lift 1.02) and a round six-prong solitaire on it. *Real
   check:* `shank --size 6 --width 4 --thickness 1.6 --split 1.6 --split-span 110 --knot twist`, then
   `solitaire --size 6 --length 6.5 --split 1.6 --split-span 120 --knot twist`. **Real check 5 Nov: both
   PASSED.** Pavé along one strand (ring 07) is the next piece.*
2. **Multi-stone placement and galleries.** *(3 Nov: the multi-stone ring written and gated offline -
   `multistone`, `multistone.ntop`, `ntopjewel.multistone`: a centre and 1-2 side pairs, every stone in an
   outline head (round included), spun (a pear's point at the centre), placed as the solitaire's and
   turned about the ring axis; each side angle bisected to the smallest at which no seat cuts a
   neighbour's head and the girdles stand `--side-gap` apart; five slots, unused ones repeat the centre.
   Gated per stone in its own frame. *Real check:* `api build multistone`, then the round three-stone and
   ring 05's cushion + pears - PASSED, and a look in the GUI at where the prongs between stones meet.
   Not yet: the gallery bridge under the heads, shared prongs (ring 02), engraving.)*
   *(4 Nov evening: the gallery bridge and shared prongs written and gated offline - `--row N` (ring 02's
   four rounds, none at the top), `--shared-prongs` (each facing pair of prongs one solved post between the
   girdles, sized for the tip floor under both seats; ring 02: 10 prongs for 4 stones), `--gallery` (a lofted
   rail each side of the band through the heads' upper rails; ring 05's cushion and pears); multistone.ntop
   0.3.0 unites `Gallery Path` / `Shared Prongs Path` with the heads before their blended join with the shank. New gate checks `shared prong
   tips` and `gallery`. *Real check pending:* `api build multistone`, then ring 02 and ring 05 with
   `--gallery`, and the ruby ring again (unchanged design, new notebook). Engraving on a multi-stone ring
   still to come.)*
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
   *Inside engraving on multi-stone rings (5 Nov): rings 02 and 05 carry text inside. `multistone --engrave` (and
   `--engrave-side / -height / -depth`) - multistone.ntop 0.4.0 takes Engraving Path / Engraving Wrap Length and cuts the
   text with the seats after the blended join, the solitaire's engraving section reused; the letters sized on the band
   under the text (`ShankSpec.engraving_band`: a taper's bottom - the solitaire likewise); refused with pavé or within
   10° of the heads; gate `engraving` (an uncut text fails it alone). Offline PASSED: ring 02 tapered and engraved,
   ring 05 engraved. **Real check PASSED 5 Nov 10:10-10:16** after `api build multistone`: ring 02 tapered with
   `--engrave "M+K 2026"` (1 mm letters; 12.3 mm² of pocket for 3.2 mm² of text, design volume +0.75 %, every check)
   and ring 05 with `--engrave Always` (1.5 mm letters; 8.3 mm² for 3.1 mm², −0.63 %). Still to do by eye: the
   letters in the GUI or the print - 1 mm text is near the resin's limit.*
4. **New stone bodies.** Pearl (sphere on a post in a cup), cabochon (dome on a flat base), asscher
   (emerald outline with a corner-cut ratio); their seats.
   *(5 Nov: written and gated offline. `gems`: `asscher` (the emerald's cut-corner outline on a square, 25 %
   corners, table 62 %, a deep step-cut pavilion), `cabochon` (flat base, girdle band, elliptic dome, `--cab-dome`),
   `pearl` (a sphere half-drilled from below, `--drill` / `--drill-depth`; material `pearl`, SG 2.71 default, by
   default for a pearl). All ride the outline_head block with no notebook change: the cabochon on four upright
   claws, a plate under its base and a collar round its girdle band; the pearl in a cup (`--cup`) on a post up
   the drill (the seat keeps the drill open, `geom.offset_convex`) with 0/3/4/6 claws. The faceted heads' seat
   ledges give way to hold checks for these (claws at the knee, seat floor, cup, post; the fake's `noprongs`
   fault is caught). A solitaire places a cabochon or pearl by its plate / cup (0.2 mm above the bore at the
   default clearance) and has no room for arches under it (refused; the CLI leaves them off). Catalogs
   outline_head_harness 0.2.1 / solitaire_outline 0.7.1 only widen Upper Rail Top's range for the collar - no
   rebuild. Offline PASSED: the three heads, the three solitaires, a pearl between two asschers (multistone).
   *First real runs (5 Nov 07:00): the asscher and cabochon heads, the cabochon and pearl-on-post solitaires
   PASSED; the 4-claw pearl head FAILED design volume (+9.6 %): its cup was given as both rails, and the
   block's one blended union of prongs and rails swelled the twin 0.08 mm all over (the 0-claw solitaire carried
   the same 6.6 mm³, inside its tolerance). Now one rail and an empty one (`heads.EMPTY_RAIL`; the cabochon's
   plate and collar one slab too), rails that overlap or meet refused, and the simulated nTop swells them as nTop
   does. The asscher solitaire FAILED extents along the finger (6.63 vs 7.06): the rail's acute top corner on the
   steep pavilion rounded back 0.215 a side, past the solitaire's one-blend allowance; it now allows two of
   `rail_corner_shrink`, as multistone does. Re-run: `head --shape pearl --length 8` and the three solitaires.)*
   *Pavé round a multi-stone ring (4 Nov): Mark's marquise ruby between two cushion diamonds with diamond pavé
   round the rest, in gold - multistone.ntop 0.2.0 takes Pave Beads / Seats Path (rebuild), the pavé centred on
   the bottom and clear of the side heads; offline PASSED on comfort-flat 2.6 x 1.8 (a court band's dome left
   0.2 mm lips beside the seats). Real check pending: `api build multistone`, then the ruby command.*
   *Partial bezels (5 Nov, from Mark's open-pear photo and the attached development plan, taken on a lean path):
   `partial_bezel_head` (block + harness) and `solitaire_partial_bezel.ntop`, `head / solitaire --partial-bezel`. Two
   mirrored walls on the flanks (fractions of the outline from the point, turned into angles for nTop), a hood over each
   point, a full cup under the girdle; any outline (an east-west half bezel on the others). **Built in nTop from
   primitives** - grown cutter ∩ a sharp mask (cup box, two turned half-boxes and their Mirror Body, hood cylinders), one
   blended intersection, seat cut last; Python supplies numbers only. Gate probes: walls, open stretches, hoods, point
   clear, bearing; faults noside / nohood / fullbezel caught. Offline PASSED: pear, marquise and oval heads, the
   reference ring (10 x 7 pear, half-round 9.5 x 3.3 tapering to 2.8 x 1.7, lip 0.8). *Real check:* `api build
   partial_bezel_head`, `head --partial-bezel --shape pear --length 10 --width 7 --depth 4.5`, `api build
   solitaire_partial_bezel`, then the reference ring command (CLAUDE.md). **Real check 5 Nov 11:46-11:54:** the head
   PASSED every check (nTop 50.33 vs design 49.85 mm³, +0.96 %; walls 20/20, open 22/22, hood, point clear, bearing
   12/12) - the first notebook built from nTop's own primitives (turned half-boxes, Mirror Body, cylinders) for a head.
   The ring passed every geometric check (design volume +0.04 %, section shape 0.010 mm, all the probes) but FAILED
   `mesh density`: 5.29 M triangles at Mesh Tolerance 0.05 (the broad band's surface); its command now carries
   `--tolerance 0.06` (~3.7 M). **Re-run at 0.06, 5 Nov: PASSED.** Physical setting validation stays with the Phase 1/5 print-and-cast
   milestones (a setter's judgement, the plan's PB-07).*
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
   First attempt (14:02): nTopCL still working after an hour, killed by the runner's timeout, no log
   (the runner now streams it). The suspect by elimination - the artwork layers are the band run's -
   was the arch stub buried under the head with `--no-arches`: two cylinders 4° apart whose
   intersection on this band was a 0.11 mm lens, which the flat band's 0.1 mm erosion all but emptied
   before the mesh round trip (the knot ring's edge round of 0 had hidden it); now one stub sized to
   the band. **Second attempt (17:17): nTopCL 51 s, one shell, no self-intersection warning, volume
   −0.09 %, all 3,364 panel probes in place** - and two gate failures of the gate's own making: the
   section at 91° (a leaf edge on the section plane; the check now compares the band's core inside a
   panel) and the bore under the head (the shank blend's 36 µm bulge where the lower rail runs 0.2 mm
   above a flat band's bore; now measured apart with the blend's allowance). **Third run (22:30):
   PASSED** - the Seraphine's construction built and gated in nTop: leaf rows on both side faces, a
   scroll on the outer face, a 4-prong round standing on the flat 2.8 x 2.0 band. `solitaire_outline`
   and `solitaire_bezel` still want their `api build` (catalogs 0.5.0) before a fancy or bezel
   solitaire runs again.
   **Knots on the shoulders (3 Nov, late):** `ntopjewel.ornament.KnotOrnament` - a closed trinity knot woven
   in two pieces on the band's outer face, wider than the band, placed just past the head, the panels
   held back past it; Knot Path / Knot Path 2 on the three solitaire notebooks (catalogs 0.10.0 / 0.6.0,
   rebuild), two probe checks. **Built PASSED in nTop 3 Nov 23:31** (`solitaire.ntop` rebuilt; one shell
   + 1 speck, every ribbon and surround probe in place, volume −0.10 %); rendered. **The photo
   comparison (4 Nov):** the reference knot sits against the head with its apex pointing at it, about
   1.3 x the band wide; a volute stands at the base of the head on each side face above a leaf row
   whose tips point at the head; the outer scroll starts after the knot. So: the knot's lone lobe
   points at the head (`--knot-point`), the knot tucks under it (`knot_clear_deg` from the head's reach
   at the band's face, + 0.2 mm: 16.8°-36.3°), width band + 0.8, ribbon 0.6; `scroll-leaves` (a volute
   then leaves) and `--leaf-tip head` (the default); the side panels run on under the knots' overhang
   from 25°, only the outer panel waits for the knot (37.3°). Values only, no rebuild. *Real check (4 Nov 05:14):* nTopCL 50 s, one shell + 6 specks, every
   panel and ribbon probe in place, volume −0.09 %, section within 0.011 mm - and `knot surround`
   102/106: the four probes between the head and the knot read the smooth union's 0.25 mm fillet round
   the upper rail's foot, which the knot's apex is placed to melt into; the surround window now begins
   past the head's reach + the shank blend (`knot_face_from_mm`), and every probe check names where its
   worst probe lies. **Re-run 05:47: PASSED** (`solitaire --profile flat --width 2.8 --thickness 2
   --prongs 4 --no-arches --sides scroll-leaves --outer scroll --shoulder-knot trinity`; surround 48/48) -
   the knotted Seraphine is a gated part. Rendered from the nTop STL as a turntable movie with an emerald
   (`out\blender\seraphine\seraphine_emerald_turntable.blend` / `.mp4`: the ring and stone copies under a
   `Turntable` empty spinning one turn in 144 frames at 24 fps, Principled glass IOR 1.577 with volume
   absorption for the green, the sweep at 0.3 roughness, H.264 from Blender's FFmpeg output - note Blender
   5.2 wants `image_settings.media_type = "VIDEO"` before `file_format = "FFMPEG"`; ~8.5 s a frame on the
   5070 Ti at 1080p / 128 samples). Mark's next ask (4 Nov 05:55): the leaf rows with each leaf turned ±7.5°
   in turn and a serpentine vine half the leaf's height connecting them - `--leaf-tilt 7.5 --leaf-stem 0.5`
   (`motif_leaves`: the stem through every base, one united relief body per panel copy since pieces of two
   heights can neither cross nor share a face in a layer; the relief probes keep off the step). *First real
   run (07:10): nTop built the united relief in one shell* - and failed `relief 374/376` on the **outer**
   face: the vein-shortening meant for the narrowed row leaves had reached the outer vine's small leaves,
   whose 0.09 mm slits had never fitted before and which the mesher cannot resolve (0.102). Fixed by
   restoring the vine's veins exactly (the two PASSED Seraphine designs' relief volume, bodies and ids are
   now pinned by a test), keeping the relief probes off every vein slit, and probing a stem along its own
   centreline; `--stem-width` (Mark: half the thickness, 0.15; a new `relief_line` floor 0.15 mm in the
   tables, default). *Real check (07:40): PASSED* with `--leaf-tilt 7.5 --leaf-stem 0.5 --stem-width 0.15`. Then
   (07:44) **the band tapered below the scrollwork**: the artwork and the shoulder knots accept a tapered
   shank whose full section runs past them (`TAPER_CLEAR_DEG` 1° past the last panel, `KNOT_TAPER_CLEAR_DEG`
   2° past the knots, and not under the head on plain shoulders), `--taper-from` defaulting to just past
   the panels; the panels and knots are built on the full section as before, only the bar changes.
   Offline PASSED (the tapered knotted Seraphine through `check_solitaire` on the blended design mesh);
   *real check pending:* `... --width-bottom 2 --thickness-bottom 1.5`. **Still missing for the Seraphine:** double-claw prong tips
   and the heart-shaped gallery (6).)* Scroll and floral relief panels,
   leaf borders, vein engraving: the medallion's 2-D artwork pipeline plus the engraving wrap, raised or cut.
6. **Organic motifs.** Leaves, vines, scrolls, the crescent moon: parametric silhouettes bent onto the
   shank where they are simple; Blender sculpts imported as meshes where they are not.
7. **Surface textures** *(5 Nov: started, Mark's call - nTop's field modelling where it is hardest to replace:
   textures driven by fields, then lattice hollowing, thickness fields, casting trees)*. First: **hammered on a plain
   band** - `texture`, `ntopjewel.texture.HammeredSpec`. One round hammer face (`sphere_radius` from the nominal
   strike's footprint and depth) pressed in along the face's normal at seeded dart-throwing centres, periodic round
   the ring, spaced half a dimple (so no point is unstruck), each strike's depth varied ±25 %, lighter towards the
   polished rims so its footprint ends there, never under the new floor `texture_depth` (0.1 mm, default). The union
   of equal spheres is the distance to the nearest centre less one radius, so **nTop can build it as one field from
   the centres alone** (`write_centres`) - no mesh of the dimples goes to nTop. Independent model: the band nTop builds
   less the spheres (manifold3d, tidied like the knots: three strikes meeting near a point left slivers float32 STL
   could not hold). Gate (`check_texture`): band checks, section shape against the design's own sections (the whole
   Mesh Tolerance: a ridge is a crease the mesher rounds), design volume (US6 4 x 1.6 court: 150 strikes take 4.4 %
   of the metal, so a missing texture fails), and a probe down every strike's normal. **Mesh density** is the
   texture's constraint: the lightest strike must span 3 voxels (Mesh Tolerance 0.05 for a 0.1 mm strike) and
   `tables.mesh_triangles_estimate` (new setting `mesh_triangles_per_voxel_area` 2.79 - 2.78 with the hammered band's point - calibrated on the partial-bezel
   ring's 5.29 M at 0.05) refuses a design past 5 M before anything runs (the default: ~2.5 M). Offline: the design
   passes its gate; a plain band and a too-light hammering are caught. *Next:* the discovery run (`api build discover`,
   its new field / noise / cell / point keywords) shows which blocks nTop has for points and point-distance fields;
   then the `ring_texture` notebook, its catalog, the simulated nTop's branch and the real check. Until then
   `texture --dry-run` / `--write-design` (Python's model, not an nTop build). *Discovery, 5 Nov:* nTop has
   `import_points<file_path,unit_length_enum>` but no block that places a body at every point of a list; it also
   has its own `cellular_noise_deboss` / `voronoi_deboss` (dents from nTop's own random points - a texture
   Python could gate by bounds only). *points_probe, 5 Nov (four rounds to get there):* the API can neither set
   nor read an enum and Import Points' Units has no default, so the unit is a notebook input nTopCL sets (id 1 =
   mm, 2 = cm, measured); a block output used twice keeps one wire in a runner too; and **one Sphere on the
   imported list makes a sphere per point** (4.7346 mm³ against Python's 4.734). So **`ring_texture.ntop`**:
   the profiled band (opened) less the union of nTop's spheres at Python's centres (Strikes Path CSV, Strike
   Radius, Strikes Units = 1). `texture` now runs it through nTopCL and the gate; offline PASSED, and a
   notebook that skips the strikes or strikes 3 % light fails `strikes`. **Real check PASSED (5 Nov):** `api build
   ring_texture`, then `texture` (US 6 court 4 x 1.6, Mesh Tolerance 0.05): 150/150 strikes within 0.028 mm of the
   design's depth, section shape 0.007 mm, design volume -0.13 % (nTop 292.07 mm³ against 292.46), 2.44 M
   triangles in 20 s - the second point of `mesh_triangles_per_voxel_area` (2.77; the setting now 2.78, the mean
   of two). Rendered (`out\blender\hammered\hammered_band.png`; `blender/photo.py` now gives an STL import,
   which has no material slot, the silver - it had rendered matte white).
   **Any ring hammered (5 Nov):** the layout moved onto a face (`texture.Hammer`, `strike_layout` over `BandFace`
   - draw for draw the band's first layout, pinned to the real run's centres - or `ShankFace`, any profiled
   shank's outer face tabulated from its sections every 1°), so a **shank** takes `hammer=` (`shank --hammered`;
   tapered, split, dipped, double; refused on a rope or a knot): `ring_shank.ntop` 0.4.0 gains the Strikes section
   (`nj.add_strikes`, shared with ring_texture) after the wrap; a face too narrow for a strike stays polished and
   warns where (a split's 1.2 mm halves take `--dimple 1.0 --depth 0.14 --rim 0.12`). A **solitaire** takes
   `hammer=` (`solitaire --hammered`): the carved band struck before the arches and the head join it, no strike
   within `head_clear_deg` (the arches' wedge + 1°, or on plain shoulders the head's reach + the shank blend +
   0.5 mm) plus half a footprint; refused with artwork panels, shoulder knots, a knot shank or an outside
   engraving, and when the deepest strike and the letters leave less than `wall_good` under an inside one. All four
   solitaire notebooks gain the Strikes section (solitaire 0.12.0, outline 0.8.0, bezel 0.8.0, partial bezel 0.2.0;
   rebuild them). pave_band, ring_artwork and multistone refuse a hammered shank (no Strikes section yet). Offline:
   PASSED, a notebook that skips the strikes fails `strikes`. **Real check, 6 Nov: the hammered solitaire PASSED**
   (`api build solitaire` 0.12.0, then `solitaire --size 6 --length 6.5 --hammered`): 106/106 strikes within
   0.045 mm of the design's depth, section shape 0.007 mm, design volume -0.15 % (nTop 277.72 mm³), 32/32 arch
   beads, stone fit, seat and bore checks as before; 2.81 M triangles. `api build ring_shank` 0.4.0 failed: with
   the Strikes section its export cannot build in the session (Import Points' Units is set only by nTopCL) and the
   recipe, unlike ring_texture's and the solitaires', waited for it - `lazy_ok` added, and a test now holds every
   recipe carrying the strikes to it. **Real check PASSED (6 Nov):** `api build ring_shank` 0.4.0, then the tapered
   hammered shank (`shank --size 6 --width 4 --thickness 1.6 --width-bottom 2.6 --thickness-bottom 1.4 --tolerance
   0.05 --hammered`): 124/124 strikes within 0.045 mm, section shape 0.010 mm, design volume -0.11 %, one shell,
   2.20 M triangles.
   **Field textures, nTop's own (6 Nov, Mark: "strongly embrace a number of textures from nTop").** nTop's toolkits
   carry texture blocks that take any implicit body: simplex and cellular noise debosses, surface roughness, voronoi
   deboss and emboss, the triangle wave (and, for Python-designed patterns, field math down to an expression field,
   `evaluate_imp_expression`, and `remap_cylindrical_field` to wrap a field round the ring). Their randomness is nTop's,
   so Python cannot rebuild them point for point; what a gate can hold them to is an **envelope** - no metal outside
   the band, no pit deeper than asked, the bore and the rims untouched, the face covered, the walls, the volume within
   the range the depth allows. Before building on them, a **probe** (`texture_probe.ntop`, `texture-probe`): each
   block on its own copy of the plain US 6 court 4 x 1.6 band (Mesh Tolerance 0.05), one nTopCL run, one STL each,
   and Python measures every vertex and triangle against the designed section (`ntopjewel.texture_probe`: signed
   distance, grouped by the nearest face - outer, bore, sides, edges - deepest / highest, the share of each face
   touched, the outer face's feature size round the ring, the volume taken). What it must answer: what the "Depth
   factor" / "Frequency" / unnamed inputs mean in millimetres (input names are matched by keyword at build time and
   every match logged: only cellular noise's and the triangle wave's names are known), whether the enums nTopCL
   cannot be given have defaults it accepts, and whether a block textures the bore and rims too (then the products
   mask it to the outer face). First build (6 Nov, 0.1.0): roughness and the triangle wave built; simplex and
   cellular noise refused a unitless "Depth factor" ("Operand A (no units) and Operand B (units of length) do not
   match") and the voronois a unitless "Spatial weighting" ("requires units of length") - both take millimetres; the
   build log gave every block's real input names (`nb_texture` lists them), so 0.2.0 matches each to its own
   variable (voronoi cell count, relaxation iterations, an integer frequency, the voronois' wall thickness).
   **Probe measured (6 Nov, 0.2.0; one nTopCL run, 60 s, every STL written - nTopCL exits non-zero after a "Logout
   failed" warning, so the probe now stands on the log and the STLs):** every block textures the WHOLE surface - bore,
   sides and rounded edges as much as the outer face - so a product must mask it (texture the band, then intersect
   / unite with the plain band outside the outer face's zone: the hammer's rim and clear logic again). What each
   does at the probe's numbers (Depth 0.1, Seed 1, Cell Size 1, 200 cells, 3 relaxations, wave 0.5):
   *simplex noise deboss* (Frequency 10, Depth factor 0.1 mm): a long-wave dent of at most 0.014 mm, 14 % of the
   face touched, feature 9 mm - too gentle and too coarse at these numbers (its Frequency is an integer per body?);
   *cellular noise deboss* (Frequency 1.0, Depth factor 0.1 mm): took 0.158 mm off EVERYWHERE, 100 % touched, no
   pattern (feature 10 mm) - at frequency 1 the cell is the whole ring: an offset, not a texture (its volume -27 %);
   *surface roughness* (frequency 10, amplitude 0.1): ±0.015 mm, 35 % touched, long-wave - a matte, not a visible
   texture, at these numbers; *voronoi deboss* (200 cells, wall 0.15, weighting 1 mm): dents to 0.077 mm, 22 % of the
   face, feature 0.15 mm (the wall between cells is what the autocorrelation sees), volume -1.6 %: the one block that
   made a jewellery texture first time (nTop's Depth input is not what it says: 0.1 asked, 0.077 built, the dents
   shallower towards the cell walls); *voronoi emboss*: the mirror, +0.098 on the faces but +0.28 mm on the side faces
   and +0.20 on the edges (the raised cells overhang the rims: a mask is not optional); *triangle wave* (height 0.1,
   spacing 0.5, direction Z): added 0.30 mm everywhere, 100 % touched, feature 0.05 (= the mesh), volume +32 %: the
   wave stands outside the body (height is peak-to-peak 3x what was asked, or the wave is added not carved) - to be
   read in the GUI before it is used. **Seen, not just measured (6 Nov):** the probe's STLs drawn as depth maps of
   each face (`texture-probe` now writes `texture_probe_<case>.png`: the outer face and the bore unrolled, a side
   face, coloured by the signed distance to the design). The **voronoi deboss carves the cell WALLS**: half-round
   grooves along the edges of a 3-D voronoi tessellation of the body - Thickness wide, half as deep (0.15 -> 0.077)
   - leaving the cells flat: a cracked-earth / mosaic net, cells 2-3 mm across on the face; the emboss is the same
   net raised (a wire net). The **triangle wave displaces the surface outward along its normal** by a triangle
   wave of (direction · position): troughs ON the design, peaks 3 x the "height" above it, period = the spacing,
   the side faces displaced too - ribs round the ring; a product would start from a band eroded by the peak. The
   noises' frequencies read as **per metre** (nTop's SI inside): at 1 the cellular cell was the whole ring.
   **First product, `ring_voronoi.ntop` (6 Nov):** the band, nTop's voronoi deboss on it, the dents (band − grooved)
   kept inside a zone - a hollow cylinder between the rims (Zone Z Top / Bottom, as the band's own Z Top / Bottom)
   from just under the dome outwards (Zone Inner Radius) - and cut from the band: the outer face grooved, the
   bore, sides and rims as designed, the grooves stopping at the rims in a clean line (`nb_texture.add_voronoi_deboss`
   + `add_outer_face_mask`, the same mask for any deboss). `texture --kind voronoi --groove 0.2 --cells 200`
   (`ntopjewel.fieldtex.VoronoiSpec`: the groove's width is nTop's Thickness, its depth half of it; rim = edge round
   + 0.1; refused under the `texture_depth` floor, past 1 mm, with too little wall under a groove at the zone's edge,
   under 3 voxels, past 5 M triangles). **The gate is an envelope** (`check_fieldtex`): the band checks (the cells are
   flat on the designed surface, so the outer Ø is the plain band's); `texture envelope` - every built vertex inside
   the zone between +0.04 and −(depth + 0.04) of the design (no metal added, no groove deeper than designed);
   `untouched outside the zone` - the bore, the sides and the rims within 0.04 of the design (the mask held);
   `texture coverage` - the grooves' share of the zone's face 3-60 % and the flat cells they enclose counted on a
   raster (≥ 4; a plain band has one); `design volume` - nTop's volume in [plain − zone face x depth, plain]. The
   simulated nTop grooves a seeded 2-D net with half-round cutters (faults: `notexture`, `unmasked`, `deep` - each
   caught). Offline PASSED (30 cells on the face, 13 % grooved, 0.100 deep). *Real checks pending:* `api build
   ring_voronoi`, then `texture --kind voronoi --thickness 1.6 --tolerance 0.05`; and the probe's round two
   (`api build texture_probe` 0.3.0 - the noises at 500 per metre - then `texture-probe`, with the depth maps).

## Notebook readability (2026-11-04)

Mark's ask: the notebooks simpler and readable by a person, without restructuring the codebase. Done:
(1) every runner notebook is laid out as an outline - named sections in build order (`Shank`, `Artwork`,
`Arches`, `Head`, `Milgrain`, `Engraving`, `Ring` / `Result`; multistone `Head 1` .. `Head 5`), all but the
last collapsed, comments on the junctions that need a reason (the opening, seats cut after the blended
join, the beads on the opened band), labels that say what a block is (`Bar 2 Opened`, `Head 3 On Ring`);
(2) the recipes are written in `nj.Helper` verbs, declare their inputs as `SPECS` and share
`nj.standard_build` / `nj.block_build` / `nj.save_block` / `nj.seat_head_harness` (prong_head's stage
bisection, a one-off diagnosis from 28 Oct, is gone); (3) `api build` names the tracked files it wrote
(`commit    : git add ...`) so the recipe JSON goes into git with the stamp it was built with. Checked
offline: every recipe built on the fake before and after gives the same blocks, wiring, list order,
inputs and Output in all 17 notebooks (geometry unchanged, so no `rebuild_since` bump). *Real check
pending:* rebuild all 13 recipes; the `sections` line, or a `layout` note with the real signatures of
`add_section` / `move_block` / `set_block_comment` if 6.3.3 refuses them; commit the files it names.
*Real check (12:40):* all 13 built; `add_section` and the comments worked, `move_block` refused a section id
(6.3.3 moves a block next to another block), so the sections switched off after their first variable -
fixed (variables go next to a block already in the section).

Then (13:04) items 4-6: (4) each multistone slot one placement - Combine Transforms of spin, quarter-turn
and turn - for the head and its seat (97 -> 62 blocks), the list order measured in nTop by
`transform_probe` (`ntop/api_facts.json`) since nTop's docs do not state it; (5) the gothic arch its +y
half ∩ the half's mirror, the -y bead rows the +y rows' mirror (Mirror Body across y = 0): four inputs
gone, solitaire 0.11.0 / outline and bezel 0.7.0, the model's arch and bead volumes identical to the µm;
(6) the `open_bar` library block - one bar imported and opened by the edge round - one instance per bar
slot in every shank runner (ring_shank 29 -> 9 blocks, pave_band / ring_artwork 35 -> 15, the solitaires
95 -> 63). *Real check pending:* `api build transform_probe` (both facts settled, file written), `api build
open_bar`, then the seven shank runners; a solitaire and the ruby multistone re-run PASSED.
*Real check (14:37): PASSED* - the probe measured list order and a correct mirror, every build and both
check runs passed, and the solitaire and multistone notebooks measure the same volumes as before
(287.96 / 278.07 mm³). The sections still switched off at the first wrapping variable: `move_block`
moves only next to a top-level block. Now real variables are made in their section and wrapping
variables stay at the top level (layout only; rebuild a runner to see its sections).

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
