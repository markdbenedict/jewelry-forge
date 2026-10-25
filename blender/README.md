# Blender side

Blender 5.2 keeps the organic work and the product shot. Everything here runs inside
Blender (bpy), either through the Blender connector in claude.ai or headless with
`blender -b file.blend -P script.py`. Scenes use millimetres (`scale_length = 0.001`)
with the ring axis along **Y** (ring standing upright).

| File | What |
| --- | --- |
| `jewelry_kit.py` | mm workspace, preview material, parametric band (Geometry Nodes), `check_model()` print/cast checker |
| `photo.py` | the silver product shot: material, sweep, softboxes, macro camera, render settings (`setup(scene, rings)`) |
| `monstera/` | monstera-leaf band (`monstera_ring.py`: `build(size, ...)`, variety, STL export) and its test/gallery scripts |
| `pear/` | pear costume-gem play ring: bezel cup with light windows, roses and leaves (`rose_ring.build(size)`) |

The `.blend` files and STLs live in `OneDrive\Documents\Jewelry\<project>`, not here.
Blender meshes enter nTop through **Implicit Body from Mesh** for sprues, trees and weight.
