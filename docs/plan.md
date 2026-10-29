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
| 2 — custom-block library | `ntop/blocks/`: band profile, bead row, groove, engraving wrap as reusable blocks; My Blocks pointed at the repo; gem bodies (round, oval, pear, cushion, emerald, marquise); prong and bezel heads; ring assembly | a solitaire (6.5 mm round, 6-prong) in sizes 5–7 passes the gate, prints with every prong intact | started 28 Oct: custom blocks proven through the API (`custom_block_probe`: save -> `embed_custom_block` -> `add_block`, builds); `NotebookHelper.embed_block`; stone bodies for all six shapes (`gem`, exact meshes, 6.5 mm round = 1.02 ct) |
| 3 — pendants, bracelets, chains | bezel/disc/tag pendants with bail, cuffs and bangles, chain links with ≥ 0.35 mm clearance | a text pendant hangs level; a 10-link cable segment prints with every link free | not started |
| 4 — casting prep | sprues, trees, shrink scaling, weight and metal estimates, flask layout | a tree of Phase 1–2 parts cast in one pour; `cast_ring_size_offset` and the shrink factors calibrated | not started |
| 5 — hardening | sweeps (`values: [...]`), batch delivery, second-laptop build server, skills polished | the full suite plus the real checks below pass on both laptops | continuous |

## Current limitations

- Shrink: `--deliver --metal` writes the print file scaled for casting + resin shrink, but the
  metal shrink figures are defaults and the resin's is an uncalibrated 0 %: the first print and
  cast set them (Phase 1 gate).

- No part has been printed or cast yet: every wall floor, density, shrink figure and the
  `cast_ring_size_offset` in `data/jewelry_tables.json` is a **default**, not a calibration.
- `ring_features.ntop` lives in `out\api\` (scratch) until `api build ring_features` saves it
  into `ntop\notebooks\` and it is committed; `ring` runs need `--notebook out\api\ring_features.ntop`
  until then.
- The Notebook API cannot register units, set `file_path` or `real_field` parameters, or force a
  lazy block to build; the build scripts route round all of these (see `CLAUDE.md`). nTopCL is
  the only check for a block that never built in the GUI session.
- The thickness check is statistical (4000 rays, p1 against the floor) and excludes bead rows and
  letter ribs by rule, not by understanding the geometry; a thin feature in an excluded zone is
  not measured. The design-volume cross-check catches a wrong section, not a locally thin one.
- The simulated nTop proves the pipeline's logic, not nTop's behaviour: Import Mesh's unit
  handling, blend radii and voxel effects are only seen in real runs.
- Blender scripts run only on the laptops (bpy); the offline suite imports them with stubs.
- nTop runs on the main laptop only (32 GB); casting trees may need the 128 GB machine.

## Phase 2 order of work

1. Stone bodies - done (Python meshes, `gem`).
2. *(done 28 Oct: built, round and pear seats PASSED under nTopCL)* The first library block, `ntop/blocks/stone_seat.ntop`: stone mesh path in, the stone
   implicit plus its seat cutter (the stone, a clearance offset and a straight drop-in path
   above the girdle) out; built by a script, embedded and measured by a harness notebook that
   nTopCL runs, so the block has a gate of its own.
3. *(done 28 Oct: built, embedded, PASSED under nTopCL)* `prong_head`: N prongs on an open two-rail basket, seat cut by `stone_seat` (drop-in above the girdle, a ledge under it), >= 0.8 mm of prong left above the girdle; gate: stone fits, ledges, drop-in clear, volume vs an independent trimesh/manifold head. Round stones (torus rails); fancy outlines need outline rails.
4. `bezel`: wall 0.5-0.8 mm round the outline, lip, light windows.
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
   engraving inputs). Later: a V-prong for the pear's point, outline heads for the other shapes in rings.
6. Gate: 6.5 mm round 6-prong solitaire, sizes 5-7, PASSED and printed.

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
| Headless run + gate | `python -m ntopjewel band …` / `ring …` | `status: PASSED`, design volume within tolerance |
| Visual | `python -m ntopjewel ring … --show`; eyes on the ring in nTop | beads, groove, text where designed |
| Blender | `blender -b -P blender\monstera\test_ring.py -- 6`; the product shot (skill `blender-jewelry-render`) | check_model report and renders written under `out\blender\` |
| Physical | print, measure, cast, weigh (above) | the Phase 1 gate |

`pytest python\tests -q -m slow` is reserved for tests that call the real nTopCL; none exist yet
(the first will wrap the headless run above once a printer and resin are chosen).
