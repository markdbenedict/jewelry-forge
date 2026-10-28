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

Point nTop's **My Blocks** folder here to find these blocks in the GUI as well.
