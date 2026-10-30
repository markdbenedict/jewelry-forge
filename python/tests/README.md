# Tests

Offline by default: no nTop, no Blender, no licence. `pytest python\tests -q` on the laptop,
and GitHub Actions runs the same suite on Linux and Windows for every push.

| File | Stands in for | What it proves |
| --- | --- | --- |
| `fake_ntopcl.py` | `ntopcl.exe` | the runner's JSON/log/output rules against the real 6.3.3 formats; and, because it **builds the geometry the notebook would build** (section revolve, bead spheres, groove torus, the engraving cut from the STL Python wrote - trimesh + manifold3d), the gate and the design-volume and engraving checks face the real shape. `FAKE_NTOPCL_SHAPE=annulus` / `noseat` / `nobeads` / `noengrave` / `noblend`, `FAKE_NTOPCL_EXPORT=0`, `FAKE_NTOPCL_VOLUME=none` make it misbehave the way a wrong notebook would, so the rejections are tested, not assumed |
| `pseudo_blend.py` | nTop's blended Boolean Union / Intersect | the fake's heads and solitaires carry the tables' blend volume as geometry: convex fill pieces along every junction loop (cut off along an intersection's edges), so the gate's design-volume check faces blended meshes; square-cornered, not nTop's smooth bump |
| `fake_notebook.py` | nTop's `notebook` object (Notebook API) | identifier resolution, wiring, inputs/Output, lazy blocks, unit table, the 6.3.3 refusals verbatim |
| stubs in `test_blender_scripts.py` | `bpy`, `bmesh`, `mathutils` | the Blender modules import, read the shared tables, and `leaf_design` is pure and reproducible |

Rejection cases that must stay red when the code regresses: wrong profile (passes every
dimension, fails `design volume`), missing nTop volume (INCOMPLETE, not delivered), no export
with an older export nearby (error), unmeasured wall (INCOMPLETE), two variants sharing a name.

What the suite cannot establish - nTop's own behaviour, a GUI build, a render, a print - is the
real-check list in `docs/plan.md`. Tests that call the real nTopCL would be marked `slow`
(`pytest -m slow`); there are none yet.
