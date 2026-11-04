"""Phase 2 step 4: the `bezel_head` library block and its harness.

    python -m ntopjewel api build stone_seat            # first, if ntop/blocks/stone_seat.ntop is not there
    python -m ntopjewel api build bezel_head            # nTop open, View > Python Console open

1. Block `ntop/blocks/bezel_head.ntop` (Seat Cutter is an implicit INPUT, as the prong heads'):
       cup      Offset Body (Seat Cutter, Wall) ∩ a slab (Box from Corners, z Bezel Bottom .. Bezel
                Top), the intersection blended by Blend Radius (rim and lip edges rounded): above the
                girdle a straight wall round the outline with a lip to burnish over the crown, below
                it a cup on the pavilion
       windows  Import Mesh (Windows Path: the light windows Python writes, heads.BezelSpec)
                -> Implicit from Mesh
       seat     cup − Seat Cutter − windows
       Output   Head (implicit)
2. Harness `ntop/notebooks/bezel_head_harness.ntop`: Seat Path + Clearance (an embedded stone_seat)
   and Windows Path + Wall + Bezel Bottom + Bezel Top (an embedded bezel_head) + Mesh Tolerance +
   Output Path, measured. Run by `python -m ntopjewel head --bezel ...` (heads.build_bezel), gated
   for fit, seat, drop-in, the wall ring and volume.
"""
from __future__ import annotations

from pathlib import Path

from ntopjewel import nb_jewel as nj

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
TEST_ENVELOPE = REPO / "out" / "api" / "bezel_head_test_envelope.stl"
TEST_WINDOWS = REPO / "out" / "api" / "bezel_head_test_windows.stl"

GEOMETRY_SPECS = [("Windows Path", "path"), ("Wall", "mm"), ("Bezel Bottom", "mm"), ("Bezel Top", "mm"), ("Blend Radius", "mm")]
SEAT_SPECS = [("Seat Path", "path"), ("Clearance", "mm")]
BLOCK_SPECS = SEAT_SPECS + GEOMETRY_SPECS
INPUT_ORDER = [n for n, _ in BLOCK_SPECS] + ["Mesh Tolerance", "Output Path"]
CUTTER_INPUT = "Seat Cutter"
SLAB_HALF_WIDTH = 40.0          # the slab's x/y half extent (any stone fits)


def _spec():
    from ntopjewel import gems, heads
    return heads.BezelSpec(gems.StoneSpec("round", 6.5))


DEFAULTS = {
    "values": {},
    "input_order": INPUT_ORDER,
    "test_output": str(REPO / "out" / "api" / "bezel_head_test.stl"),
    "seat_block": str(REPO / "ntop" / "blocks" / "stone_seat.ntop"),
    "block_to": str(REPO / "ntop" / "blocks" / "bezel_head.ntop"),
    "block_recipe_to": str(REPO / "ntop" / "recipes" / "bezel_head.block.recipe.json"),
    "save_to": str(REPO / "ntop" / "notebooks" / "bezel_head_harness.ntop"),
    "recipe_to": str(REPO / "ntop" / "recipes" / "bezel_head_harness.recipe.json"),
    "pause": False,
    "lazy_ok": True,
    "fresh": True,
    "wait_s": 240,
    "volume_hint": "bezel, 6.5 mm round, 6 windows: 34.0 mm³ (heads.BezelSpec.design_mesh)",
}


def prepare(params: dict, work_dir: Path) -> dict:
    """Laptop side: the test envelope and prong meshes, and every input value."""
    spec = _spec()
    TEST_ENVELOPE.parent.mkdir(parents=True, exist_ok=True)
    spec.seat.envelope().export(str(TEST_ENVELOPE))
    spec.windows_mesh().export(str(TEST_WINDOWS))
    v = spec.notebook_inputs(str(TEST_ENVELOPE), str(TEST_WINDOWS), "")
    v.pop("Output Path")
    params["values"] = {**v, **(params.get("values") or {})}
    return params


def _block_body(notebook, values: dict):
    """Fresh notebook -> (helper, bezel body, input ids in order)."""
    h = nj.Helper(notebook)
    notebook.new_notebook()
    cutter = nj.implicit_input(h, CUTTER_INPUT)
    ids = nj.add_typed_inputs(h, GEOMETRY_SPECS, values)
    grown = h.offset("Bezel Grown", cutter, ids["Wall"])                            # the cutter + the wall
    lo = nj.point_block(h, "Bezel Low Corner", z_var=ids["Bezel Bottom"], x=-SLAB_HALF_WIDTH, y=-SLAB_HALF_WIDTH)
    hi = nj.point_block(h, "Bezel High Corner", z_var=ids["Bezel Top"], x=SLAB_HALF_WIDTH, y=SLAB_HALF_WIDTH)
    slab = h.add("Bezel Slab", mask="box_from_corners", must=nj.BOX_FROM_CORNERS)
    corners = [i["name"] for i in h.inputs(slab) if "point" in str(i.get("type", ""))]
    h.wire(lo, slab, [corners[0]])
    h.wire(hi, slab, [corners[1]])
    cup = h.intersect("Bezel Cup", [grown, slab], blend=ids["Blend Radius"])        # the rim and the lip's edge rounded
    windows = h.import_body("Windows", ids["Windows Path"])
    head = h.subtract("Seated", cup, [cutter, windows])
    return h, head, [cutter] + [ids[n] for n, _ in GEOMETRY_SPECS]


def build_block(notebook, p: dict, values: dict) -> dict:
    h, head, order = _block_body(notebook, values)
    return nj.save_block(notebook, h, head, order, "Head", p)


_harness = nj.seat_head_harness("Bezel Head", SEAT_SPECS, GEOMETRY_SPECS, CUTTER_INPUT)


def build(notebook, params: dict | None = None) -> dict:
    """Entry point for `api build bezel_head`: the block, then its harness."""
    return nj.block_build(notebook, params, DEFAULTS, "bezel_head", build_block, _harness)
