# Casting notes (reference for the casting-prep skill, Phase 4)

Two workflows, both to be supported:

1. **Print parts individually with a short printed sprue stub, wax-weld onto a wax tree.**
   The default. Needs only "sprue attach": a cylinder (2.5–3.5 mm for rings) on a picked
   point and direction, blended into the part (Boolean Union, blend radius 0.5–1.0 mm),
   8–12 mm long, with a slight taper widening toward the tree.
2. **Print the whole tree in castable resin.** For small runs of identical rings. Needs the
   tree builder (main sprue 6–10 mm, button, tiers of parts at 45–60°, spacing ≥ 6 mm,
   flask fit with ≥ 6 mm to the wall and ≥ 12 mm investment above) and a check against
   the printer's build volume as well as the flask.

Per-metal defaults live in `data/jewelry_tables.json` (read as `tables.METALS`, `tables.CASTING`; each entry carries its status and source). The first
two casts are experiments: measure finished ring size vs. model, weight vs. the report,
and note where metal failed to fill; update the tables with a dated note.

Checks the casting report will carry: volume, surface area, weight per alloy including
sprues and button, thinnest wall (ray-cast map), thin-flash risk (< 0.5 mm regions),
suggested sprue point (centroid of the thickest region).
