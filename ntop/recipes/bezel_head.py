"""Phase 2 step 4: the `bezel_head` library block and its harness.

    python -m ntopjewel api build stone_seat            # first, if ntop/blocks/stone_seat.ntop is not there
    python -m ntopjewel api build bezel_head            # nTop open, View > Python Console open

1. Block `ntop/blocks/bezel_head.ntop` (Seat Cutter is an implicit INPUT, as the prong heads'):
       cup      Offset Body (Seat Cutter, Wall) ∩ a slab (Box from Corners, z Bezel Bottom .. Bezel
                Top): above the girdle a straight wall round the outline with a lip to burnish over
                the crown, below it a cup on the pavilion
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
from ntopjewel.notebook_api import ConsoleError, NotebookHelper

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
TEST_ENVELOPE = REPO / "out" / "api" / "bezel_head_test_envelope.stl"
TEST_WINDOWS = REPO / "out" / "api" / "bezel_head_test_windows.stl"

GEOMETRY_SPECS = [("Windows Path", "path"), ("Wall", "mm"), ("Bezel Bottom", "mm"), ("Bezel Top", "mm")]
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
    h = NotebookHelper(notebook)
    notebook.new_notebook()
    cut = notebook.add_block("core.var<implicit>")
    cutter = cut["id"] if cut["id"] == CUTTER_INPUT else notebook.rename_variable(cut["id"], CUTTER_INPUT)["id"]
    h.blocks[CUTTER_INPUT] = cutter
    h.identifiers[CUTTER_INPUT] = "core.var<implicit>"
    ids = nj.add_typed_inputs(h, GEOMETRY_SPECS, values)

    grown = h.add("Bezel Grown", mask="offset", must=nj.OFFSET)          # the cutter + the wall
    h.wire(cutter, grown, ["Body"])
    h.wire(ids["Wall"], grown, ["Distance", "Offset"])
    lo = nj.point_block(h, "Bezel Low Corner", z_var=ids["Bezel Bottom"], x=-SLAB_HALF_WIDTH, y=-SLAB_HALF_WIDTH)
    hi = nj.point_block(h, "Bezel High Corner", z_var=ids["Bezel Top"], x=SLAB_HALF_WIDTH, y=SLAB_HALF_WIDTH)
    slab = h.add("Bezel Slab", mask="box_from_corners", must=nj.BOX_FROM_CORNERS)
    corners = [i["name"] for i in h.inputs(slab) if "point" in str(i.get("type", ""))]
    h.wire(lo, slab, [corners[0]])
    h.wire(hi, slab, [corners[1]])
    cup = h.add("Bezel Cup", mask="intersect", must=nj.INTERSECT)
    h.to_list(grown, cup, ["Bodies"])
    h.to_list(slab, cup, ["Bodies"])
    imp = h.add("Windows Mesh", mask="import_mesh", must=nj.IMPORT_MESH)
    h.wire(ids["Windows Path"], imp, ["Path", "File Path", "File", "Filename"])
    windows = h.add("Windows", mask="implicit_from_mesh", must=nj.IMPLICIT_FROM_MESH)
    h.wire(imp, windows, ["Mesh"])
    head = h.add("Seated", mask="subtract", must=nj.SUBTRACT)
    h.wire(cup, head, ["Primary Body", "Body"])
    h.to_list(cutter, head, ["Subtraction Bodies", "Bodies"])
    h.to_list(windows, head, ["Subtraction Bodies", "Bodies"])
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
    head = h.add("Bezel Head", h.embed_block(p["block_to"]))
    h.wire(seat, head, [CUTTER_INPUT])
    for name, _ in GEOMETRY_SPECS:
        h.wire(ids[name], head, [name])
    body = h.wrap_var("Result", head)
    integ, _mesh, export = nj.add_measure_mesh_export(h, body, out_var, ids["Mesh Tolerance"])
    return integ, export


def build(notebook, params: dict | None = None) -> dict:
    """Entry point for `api build bezel_head`: the block, then its harness."""
    params = dict(params or {})
    if "save_to" in params and "block_to" not in params:          # --scratch
        params["block_to"] = str(Path(params["save_to"]).parent / "bezel_head.ntop")
        params.setdefault("block_recipe_to", str(Path(params["save_to"]).parent / "bezel_head.block.recipe.json"))
    p = {**DEFAULTS, **params}
    values = {**DEFAULTS["values"], **(p.get("values") or {})}
    if not values:
        raise ConsoleError("no input values: run through `python -m ntopjewel api build bezel_head` (prepare() computes them)")
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
