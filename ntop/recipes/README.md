# Recipes

A recipe is the written build procedure for a custom block or a runner notebook: block
list, wiring, exact input names, units, defaults and the checks that prove it works.
Claude writes recipes; Mark builds them in the nTop GUI; Claude verifies the result
through `ntopcl` and the mesh gate.

| Recipe | Produces | Phase |
| --- | --- | --- |
| `band-primitive.md` | `ntop/notebooks/ring_band.ntop` (flat band, hello band) | 0 |

Rules: one block per recipe where possible; every notebook input named exactly as in
`catalog/`; a block that needs a third GUI sitting is split into two simpler blocks.
