# Custom block library

One `.ntop` per custom block: a notebook with declared inputs and exactly one Output, built by
a script in `ntop/recipes/` (never by hand). Runner notebooks embed a block with
`embed_custom_block` (`NotebookHelper.embed_block`), so they carry a copy: after a block
changes, rebuild the notebooks that embed it (their build scripts do it in one run).

Every block has a **harness** in `ntop/notebooks/<block>_harness.ntop`, built by the same
script: it embeds the block, feeds it test inputs and measures what it returns (Volume
Integral, Mesh, Export), so nTopCL and the gate test the block on its own before any head
or ring uses it.

| Block | Inputs | Output | Script | Harness command |
| --- | --- | --- | --- | --- |
| `stone_seat.ntop` | Seat Path (text: the envelope STL from `gems.seat_envelope`), Clearance (mm) | Seat Cutter (implicit): stone + straight drop-in path, offset by the clearance | `ntop/recipes/stone_seat.py` | `python -m ntopjewel seat --shape round --length 6.5` |
| `prong_head.ntop` | Seat Cutter (implicit: wire `stone_seat`'s output in), Prong Count (int), Prong Spacing (deg), Prong Radius, Base X/Y/Z, Tip X/Y/Z, Upper/Lower Rail Z + Radius, Rail Tube Radius | Head (implicit): N prongs on two rails minus the cutter | `ntop/recipes/prong_head.py` | `python -m ntopjewel head --length 6.5 --prongs 6` |
| `outline_head.ntop` | Seat Cutter (implicit), Prongs Path (text: the rod STL Python writes), Rail Offset, Upper/Lower Rail Bottom + Top | Head (implicit): the rods ∪ two rails (the cutter offset ∩ a slab) minus the cutter - any outline | `ntop/recipes/outline_head.py` | `python -m ntopjewel head --shape pear --length 12.3 --width 8.9 --depth 4.6` |
| `bezel_head.ntop` | Seat Cutter (implicit), Windows Path (text: the light windows STL), Wall, Bezel Bottom, Bezel Top | Head (implicit): the cutter grown by the wall ∩ a slab, minus the cutter and the windows - any outline | `ntop/recipes/bezel_head.py` | `python -m ntopjewel head --bezel --length 6.5` |

Inside a block, a block output that feeds two inputs must go through a variable, or nTop refuses the block (2026-10-28). Blocks take other blocks' results as **implicit inputs** rather than embedding them. The harness (or a runner) embeds the blocks side by side and wires them. Every block build ends with a self-test: the saved block is embedded into a fresh notebook at once.

Point nTop's **My Blocks** folder here to find these blocks in the GUI as well.
