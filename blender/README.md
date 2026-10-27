# Blender side

Blender 5.2 keeps the organic work and the product shot. Everything here runs inside
Blender (bpy), either through the Blender connector in claude.ai or headless with
`blender -b file.blend -P script.py`. Scenes use millimetres (`scale_length = 0.001`)
with the ring axis along **Y** (ring standing upright).

| File | What |
| --- | --- |
| `jewelry_kit.py` | mm workspace, preview material, parametric band (Geometry Nodes), `check_model()` print/cast checker |
| `photo.py` | the silver product shot: material, sweep, softboxes, macro camera, render settings (`setup(scene, rings)`) |
| `forge_paths.py` | pure Python: the repo root, `out_dir()` (`JEWELRY_OUT`, else `<repo>\out`) and the `sys.path` setup the scripts share |
| `monstera/` | monstera-leaf band: `leaf_design.py` (the 2-D leaf, pure numpy), `monstera_ring.py` (`build(size, ...)`, STL export), `gallery.py` (twelve leaves on a sheet, no Blender needed) and the `test_*.py` / `compare_top.py` render scripts |
| `pear/` | pear costume-gem play ring: bezel cup with light windows, roses and leaves (`rose_ring.build(size)`) |

Wall floors, metal densities and the sprue allowance in `jewelry_kit.py` come from
`data\jewelry_tables.json` (the file `ntopjewel.tables` reads): `JEWELRY_FORGE_ROOT` names another
checkout, a text block called `jewelry_tables.json` inside the `.blend` works away from the repo, and
an embedded copy (kept equal by `python\tests\test_blender_scripts.py`) is the last resort;
`jewelry_kit.TABLES_SOURCE` says which one was used.

The scripts find their modules from their own location, so they run from any checkout:
`blender -b -P blender\monstera\test_ring.py -- 5 6 7`, then `... test_photo.py -- 64 50` and
`... compare_top.py`; `python blender\monstera\gallery.py [--out folder]` needs no Blender.
Output goes to `%JEWELRY_OUT%\blender\monstera`, else `<repo>\out\blender\monstera`.
The `.blend` files and STLs live in `OneDrive\Documents\Jewelry\<project>`, not here.
Blender meshes enter nTop through **Implicit Body from Mesh** for sprues, trees and weight.
