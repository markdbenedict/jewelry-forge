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
from ntopjewel.notebook_api import ConsoleError, NotebookHelper

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
    h = NotebookHelper(notebook)
    notebook.new_notebook()
    cut = notebook.add_block("core.var<implicit>")
    cutter = cut["id"] if cut["id"] == CUTTER_INPUT else notebook.rename_variable(cut["id"], CUTTER_INPUT)["id"]
    h.blocks[CUTTER_INPUT] = cutter
    h.identifiers[CUTTER_INPUT] = "core.var<implicit>"
    ids = nj.add_typed_inputs(h, GEOMETRY_SPECS, values)

    imp = h.add("Prongs Mesh", mask="import_mesh", must=nj.IMPORT_MESH)
    h.wire(ids["Prongs Path"], imp, ["Path", "File Path", "File", "Filename"])
    prongs = h.add("Prongs", mask="implicit_from_mesh", must=nj.IMPLICIT_FROM_MESH)
    h.wire(imp, prongs, ["Mesh"])
    parts = [prongs]
    for rail in ("Upper", "Lower"):
        grown = h.add(f"{rail} Rail Grown", mask="offset", must=nj.OFFSET)
        h.wire(cutter, grown, ["Body"])
        h.wire(ids["Rail Offset"], grown, ["Distance", "Offset"])
        lo = nj.point_block(h, f"{rail} Rail Low Corner", z_var=ids[f"{rail} Rail Bottom"], x=-SLAB_HALF_WIDTH, y=-SLAB_HALF_WIDTH)
        hi = nj.point_block(h, f"{rail} Rail High Corner", z_var=ids[f"{rail} Rail Top"], x=SLAB_HALF_WIDTH, y=SLAB_HALF_WIDTH)
        slab = h.add(f"{rail} Rail Slab", mask="box_from_corners", must=nj.BOX_FROM_CORNERS)
        corners = [i["name"] for i in h.inputs(slab) if "point" in str(i.get("type", ""))]
        h.wire(lo, slab, [corners[0]])
        h.wire(hi, slab, [corners[1]])
        r = h.add(f"{rail} Rail", mask="intersect", must=nj.INTERSECT)
        h.to_list(grown, r, ["Bodies"])
        h.to_list(slab, r, ["Bodies"])
        nj.wire_blend(h, r, ids["Blend Radius"])                 # the slab's edges rounded
        parts.append(r)
    basket = h.add("Basket", mask="union", must=nj.UNION)
    for part in parts:
        h.to_list(part, basket, ["Bodies"])
    nj.wire_blend(h, basket, ids["Blend Radius"])                # prongs melt into the rails
    head = h.add("Seated", mask="subtract", must=nj.SUBTRACT)
    h.wire(basket, head, ["Primary Body", "Body"])
    h.to_list(cutter, head, ["Subtraction Bodies", "Bodies"])
    return h, head, [cutter] + [ids[n] for n, _ in GEOMETRY_SPECS]


def build_block(notebook, p: dict, values: dict) -> dict:
    h, head, order = _block_body(notebook, values)
    out = h.wrap_var("Head", head)
    h.declare_inputs(order)
    h.set_output(out)
    warnings = nj.settle(h, head, "the block's Output")
    Path(p["block_to"]).parent.mkdir(parents=True, exist_ok=True)
    notebook.save_notebook_as(p["block_to"])
    try:
        notebook.export_as_recipe(p["block_recipe_to"], True)
    except Exception as e:
        h.log.append(f"export_as_recipe (block) failed: {e}")
    if not Path(p["block_to"]).exists():
        raise ConsoleError(f"the block was not saved to {p['block_to']}")
    self_test = embed_self_test(notebook, p["block_to"])
    return {"saved": p["block_to"], "recipe": p["block_recipe_to"], "identifiers": h.identifiers, "warnings": warnings,
            "self_test": self_test, "blocks": h.blocks, "states": h.states(0), "log": h.log}


def embed_self_test(notebook, block_path: str) -> dict:
    notebook.new_notebook()
    try:
        notebook.embed_custom_block(block_path)
    except Exception as e:
        raise ConsoleError(f"nTop refuses the saved block as a custom block: {e}") from e
    blocks = [b for b in notebook.list_custom_blocks() if b.get("name") == Path(block_path).stem]
    if not blocks:
        raise ConsoleError(f"embedded {block_path} but list_custom_blocks() does not name it")
    return {"accepted": True, "id": blocks[0]["id"]}


def _harness(h, p, values, test_output):
    ids = nj.add_typed_inputs(h, BLOCK_SPECS + [("Mesh Tolerance", "mm")], values)
    out_var = nj.path_variable(h, "Output Path", test_output)
    seat = h.add("Stone Seat", h.embed_block(p["seat_block"]))
    for name, _ in SEAT_SPECS:
        h.wire(ids[name], seat, [name])
    head = h.add("Outline Head", h.embed_block(p["block_to"]))
    h.wire(seat, head, [CUTTER_INPUT])
    for name, _ in GEOMETRY_SPECS:
        h.wire(ids[name], head, [name])
    body = h.wrap_var("Result", head)
    integ, _mesh, export = nj.add_measure_mesh_export(h, body, out_var, ids["Mesh Tolerance"])
    return integ, export


def build(notebook, params: dict | None = None) -> dict:
    """Entry point for `api build outline_head`: the block, then its harness."""
    params = dict(params or {})
    if "save_to" in params and "block_to" not in params:          # --scratch
        params["block_to"] = str(Path(params["save_to"]).parent / "outline_head.ntop")
        params.setdefault("block_recipe_to", str(Path(params["save_to"]).parent / "outline_head.block.recipe.json"))
    p = {**DEFAULTS, **params}
    values = {**DEFAULTS["values"], **(p.get("values") or {})}
    if not values:
        raise ConsoleError("no input values: run through `python -m ntopjewel api build outline_head` (prepare() computes them)")
    for key in ("block_to", "block_recipe_to", "seat_block"):
        p[key] = nj.absolute(p[key])
    if not Path(p["seat_block"]).exists():
        raise ConsoleError(f"{p['seat_block']} is missing: run `python -m ntopjewel api build stone_seat` first")
    p["values"] = values
    block = build_block(notebook, p, values)
    res = nj.run_build(notebook, p, {**DEFAULTS, "values": values}, _harness)
    res["block"] = block
    res["warnings"] = block.get("warnings", []) + res.get("warnings", [])
    return res
