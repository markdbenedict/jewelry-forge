"""Phase 2: the `outline_head` library block (prongs on any outline; pear first) and its harness.

    python -m ntopjewel api build stone_seat            # first, if ntop/blocks/stone_seat.ntop is not there
    python -m ntopjewel api build outline_head          # nTop open, View > Python Console open

1. Block `ntop/blocks/outline_head.ntop` (Seat Cutter is an implicit INPUT, as prong_head's):
       prongs   Import Mesh (Prongs Path: the rods Python writes, ntopjewel.heads.OutlineHeadSpec)
                -> Implicit from Mesh
       rails    per rail: Offset Body (Seat Cutter, Rail Offset) ∩ a slab (Box from Corners,
                z Rail Bottom .. Rail Top), the intersection blended (edges rounded): a gallery
                following the pavilion, whatever the outline; prongs ∪ rails blended too (Blend Radius)
       seat     (prongs ∪ rails) − Seat Cutter
       Output   Head (implicit)
2. Harness `ntop/notebooks/outline_head_harness.ntop`: Seat Path + Clearance (an embedded
   stone_seat) and Prongs Path + the rail numbers (an embedded outline_head, the seat's output as
   its cutter) + Mesh Tolerance + Output Path, measured. Run by `python -m ntopjewel head --shape
   pear ...` (ntopjewel.heads.build_outline_head), gated for fit, ledges, drop-in and volume.
"""
from __future__ import annotations

from pathlib import Path

from ntopjewel import nb_jewel as nj

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
TEST_ENVELOPE = REPO / "out" / "api" / "outline_head_test_envelope.stl"
TEST_PRONGS = REPO / "out" / "api" / "outline_head_test_prongs.stl"

GEOMETRY_SPECS = [("Prongs Path", "path"), ("Rail Offset", "mm"), ("Upper Rail Bottom", "mm"), ("Upper Rail Top", "mm"),
                  ("Lower Rail Bottom", "mm"), ("Lower Rail Top", "mm"), ("Blend Radius", "mm")]
SEAT_SPECS = [("Seat Path", "path"), ("Clearance", "mm")]
BLOCK_SPECS = SEAT_SPECS + GEOMETRY_SPECS
INPUT_ORDER = [n for n, _ in BLOCK_SPECS] + ["Mesh Tolerance", "Output Path"]
CUTTER_INPUT = "Seat Cutter"
SLAB_HALF_WIDTH = 40.0          # the rail slabs' x/y half extent (any stone fits)


def _spec():
    from ntopjewel import gems, heads
    return heads.OutlineHeadSpec(gems.StoneSpec("pear", 12.3, 8.9, 4.6, material="glass"))


DEFAULTS = {
    "values": {},
    "input_order": INPUT_ORDER,
    "test_output": str(REPO / "out" / "api" / "outline_head_test.stl"),
    "seat_block": str(REPO / "ntop" / "blocks" / "stone_seat.ntop"),
    "block_to": str(REPO / "ntop" / "blocks" / "outline_head.ntop"),
    "block_recipe_to": str(REPO / "ntop" / "recipes" / "outline_head.block.recipe.json"),
    "save_to": str(REPO / "ntop" / "notebooks" / "outline_head_harness.ntop"),
    "recipe_to": str(REPO / "ntop" / "recipes" / "outline_head_harness.recipe.json"),
    "pause": False,
    "lazy_ok": True,
    "fresh": True,
    "wait_s": 240,
    "volume_hint": "5-prong head (1 V), 12.3 x 8.9 pear: ~99 mm³ unblended + the blend (heads.outline_design_mesh, blend_volume_mm3)",
}


def prepare(params: dict, work_dir: Path) -> dict:
    """Laptop side: the test envelope and prong meshes, and every input value."""
    spec = _spec()
    TEST_ENVELOPE.parent.mkdir(parents=True, exist_ok=True)
    spec.seat.envelope().export(str(TEST_ENVELOPE))
    spec.prongs_mesh().export(str(TEST_PRONGS))
    v = spec.notebook_inputs(str(TEST_ENVELOPE), str(TEST_PRONGS), "")
    v.pop("Output Path")
    params["values"] = {**v, **(params.get("values") or {})}
    return params


def _block_body(notebook, values: dict):
    """Fresh notebook -> (helper, head body, input ids in order)."""
    h = nj.Helper(notebook)
    notebook.new_notebook()
    cutter = nj.implicit_input(h, CUTTER_INPUT)
    ids = nj.add_typed_inputs(h, GEOMETRY_SPECS, values)
    prongs = h.import_body("Prongs", ids["Prongs Path"])
    parts = [prongs]
    for rail in ("Upper", "Lower"):
        grown = h.offset(f"{rail} Rail Grown", cutter, ids["Rail Offset"])          # the cutter grown: the rail follows the pavilion
        lo = nj.point_block(h, f"{rail} Rail Low Corner", z_var=ids[f"{rail} Rail Bottom"], x=-SLAB_HALF_WIDTH, y=-SLAB_HALF_WIDTH)
        hi = nj.point_block(h, f"{rail} Rail High Corner", z_var=ids[f"{rail} Rail Top"], x=SLAB_HALF_WIDTH, y=SLAB_HALF_WIDTH)
        slab = h.add(f"{rail} Rail Slab", mask="box_from_corners", must=nj.BOX_FROM_CORNERS)
        corners = [i["name"] for i in h.inputs(slab) if "point" in str(i.get("type", ""))]
        h.wire(lo, slab, [corners[0]])
        h.wire(hi, slab, [corners[1]])
        parts.append(h.intersect(f"{rail} Rail", [grown, slab], blend=ids["Blend Radius"]))    # the slab's edges rounded
    basket = h.union("Basket", parts, blend=ids["Blend Radius"])                    # prongs melt into the rails
    head = h.subtract("Seated", basket, [cutter])
    return h, head, [cutter] + [ids[n] for n, _ in GEOMETRY_SPECS]


def build_block(notebook, p: dict, values: dict) -> dict:
    h, head, order = _block_body(notebook, values)
    return nj.save_block(notebook, h, head, order, "Head", p)


_harness = nj.seat_head_harness("Outline Head", SEAT_SPECS, GEOMETRY_SPECS, CUTTER_INPUT)


def build(notebook, params: dict | None = None) -> dict:
    """Entry point for `api build outline_head`: the block, then its harness."""
    return nj.block_build(notebook, params, DEFAULTS, "outline_head", build_block, _harness)
