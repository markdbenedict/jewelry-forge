"""Phase 2 step 3: the `prong_head` library block and its harness.

    python -m ntopjewel api build stone_seat             # first, if ntop/blocks/stone_seat.ntop is not there
    python -m ntopjewel api build prong_head             # nTop open, View > Python Console open

1. Block `ntop/blocks/prong_head.ntop` (Seat Cutter is an implicit INPUT; no block inside):
       one prong   Cylinder Base -> Tip (Prong Radius) ∪ a sphere on each end
       prongs      Polar Array of it about +Z: Prong Count copies, Prong Spacing (deg) apart
       basket      ∪ two tori about Z: Upper Rail (Z, Radius), Lower Rail (Z, Radius), Rail Tube Radius,
                   the union blended by Blend Radius (prongs melt into the rails)
       seat        − Seat Cutter (the stone_seat block's output, wired in): trims the prongs back to the girdle line
                   above the girdle (the stone drops in) and leaves a ledge in each below it
       Output      Head (implicit)
2. Harness `ntop/notebooks/prong_head_harness.ntop`: Seat Path + Clearance (to an embedded
   stone_seat) and the 14 head numbers (to an embedded prong_head, with the seat's output as its
   cutter) + Mesh Tolerance + Output Path, measured (Volume Integral, Mesh, Export Mesh). Run by
   `python -m ntopjewel head ...` (ntopjewel.heads.build_head), gated for fit, ledges, drop-in
   and volume against the independent trimesh/manifold head.

Every number comes from ntopjewel.heads.HeadSpec; the notebook has no arithmetic. Both notebooks
carry embedded copies of the blocks they use: rebuild them (this script) after a block changes.
"""
from __future__ import annotations

from pathlib import Path

from ntopjewel import nb_jewel as nj

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
TEST_ENVELOPE = REPO / "out" / "api" / "prong_head_test_envelope.stl"

# the block's numeric inputs; its first input is the seat cutter (implicit), wired in by whoever uses it
GEOMETRY_SPECS = [("Prong Count", "int"), ("Prong Spacing", "deg"),
                  ("Prong Radius", "mm"), ("Base X", "mm"), ("Base Y", "mm"), ("Base Z", "mm"),
                  ("Tip X", "mm"), ("Tip Y", "mm"), ("Tip Z", "mm"), ("Upper Rail Z", "mm"), ("Upper Rail Radius", "mm"),
                  ("Lower Rail Z", "mm"), ("Lower Rail Radius", "mm"), ("Rail Tube Radius", "mm"), ("Blend Radius", "mm")]
SEAT_SPECS = [("Seat Path", "path"), ("Clearance", "mm")]           # the harness's, for the stone_seat block
BLOCK_SPECS = SEAT_SPECS + GEOMETRY_SPECS                           # = the harness inputs before Mesh Tolerance
INPUT_ORDER = [n for n, _ in BLOCK_SPECS] + ["Mesh Tolerance", "Output Path"]
CUTTER_INPUT = "Seat Cutter"


def _test_values() -> dict:
    """6-prong head for a 6.5 mm round (ntopjewel.heads.HeadSpec defaults)."""
    from ntopjewel import gems, heads
    spec = heads.HeadSpec(gems.StoneSpec("round", 6.5), prongs=6)
    v = spec.notebook_inputs(str(TEST_ENVELOPE), "")
    v.pop("Output Path")
    return v


DEFAULTS = {
    "values": {},                       # filled by prepare() (laptop side) - nTop's Python has no trimesh
    "input_order": INPUT_ORDER,
    "test_output": str(REPO / "out" / "api" / "prong_head_test.stl"),
    "seat_block": str(REPO / "ntop" / "blocks" / "stone_seat.ntop"),
    "block_to": str(REPO / "ntop" / "blocks" / "prong_head.ntop"),
    "block_recipe_to": str(REPO / "ntop" / "recipes" / "prong_head.block.recipe.json"),
    "save_to": str(REPO / "ntop" / "notebooks" / "prong_head_harness.ntop"),
    "recipe_to": str(REPO / "ntop" / "recipes" / "prong_head_harness.recipe.json"),
    "pause": False,                     # embeds: no paused updates
    "lazy_ok": True,                    # the GUI may leave the head unbuilt; `head` under nTopCL is the test
    "fresh": True,
    "wait_s": 240,
    "volume_hint": "6-prong head, 6.5 mm round: 38.6 mm³ unblended + ~1.3 mm³ of blend (heads.design_mesh, blend_volume_mm3)",
}


def prepare(params: dict, work_dir: Path) -> dict:
    """Laptop side: the test seat envelope and every input value (heads.HeadSpec)."""
    from ntopjewel import gems, heads
    spec = heads.HeadSpec(gems.StoneSpec("round", 6.5), prongs=6)
    TEST_ENVELOPE.parent.mkdir(parents=True, exist_ok=True)
    spec.seat.envelope().export(str(TEST_ENVELOPE))
    params["values"] = {**_test_values(), **(params.get("values") or {})}
    return params


def _head_body(notebook, values: dict):
    """Fresh notebook -> (helper, head body, input ids in order)."""
    h = nj.Helper(notebook)
    notebook.new_notebook()
    cutter = nj.implicit_input(h, CUTTER_INPUT)
    ids = nj.add_typed_inputs(h, GEOMETRY_SPECS, values)
    # a block output used twice goes through a variable - in a custom block this is not optional:
    # a block notebook that fed one Point to both the rod and a sphere was refused (bisected 2026-10-28)
    base = h.wrap_var("Base Point", nj.point_from_vars(h, "Base", ids["Base X"], ids["Base Y"], ids["Base Z"]))
    tip = h.wrap_var("Tip Point", nj.point_from_vars(h, "Tip", ids["Tip X"], ids["Tip Y"], ids["Tip Z"]))
    radius = ids["Prong Radius"]
    rod = h.cylinder("Prong Rod", base, tip, radius)
    prong = h.union("Prong", [rod, h.sphere("Prong Foot", base, radius), h.sphere("Prong Tip", tip, radius)])
    prongs = h.polar_array("Prongs", prong, ids["Prong Spacing"], ids["Prong Count"], nj.z_axis(h))
    rails = [h.torus(rail, ids[f"{rail} Radius"], ids["Rail Tube Radius"],
                     centre=nj.point_block(h, f"{rail} Centre", z_var=ids[f"{rail} Z"]))
             for rail in ("Upper Rail", "Lower Rail")]
    basket = h.union("Basket", [prongs, *rails], blend=ids["Blend Radius"])        # prongs melt into the rails
    head = h.subtract("Seated", basket, [cutter])
    return h, head, [cutter] + [ids[n] for n, _ in GEOMETRY_SPECS]


def build_block(notebook, p: dict, values: dict) -> dict:
    """The head block: Seat Cutter (implicit input) + 14 numbers -> Head. It holds no other block;
    a bezel can reuse the same seat cutter."""
    h, head, order = _head_body(notebook, values)
    return nj.save_block(notebook, h, head, order, "Head", p)


_harness = nj.seat_head_harness("Prong Head", SEAT_SPECS, GEOMETRY_SPECS, CUTTER_INPUT)


def build(notebook, params: dict | None = None) -> dict:
    """Entry point for `api build prong_head`: the block, then its harness."""
    return nj.block_build(notebook, params, DEFAULTS, "prong_head", build_block, _harness)
