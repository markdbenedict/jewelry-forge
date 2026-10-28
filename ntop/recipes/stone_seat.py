"""Phase 2 step 2: the first library block, `stone_seat`, and the harness that tests it.

    python -m ntopjewel api build stone_seat            # nTop open, View > Python Console open
    python -m ntopjewel api build stone_seat --scratch  # both files into out/api/ instead

1. Block `ntop/blocks/stone_seat.ntop` (a notebook with inputs and one Output = a custom block):
       inputs  Seat Path (text: the seat envelope STL Python writes - the stone plus its
               straight drop-in path, gems.seat_envelope), Clearance (mm)
       body    Import Mesh -> Implicit from Mesh -> Offset Body by Clearance
       Output  Seat Cutter (implicit): what a head subtracts so the stone drops in from above
2. Harness `ntop/notebooks/stone_seat_harness.ntop`: embeds the block (outside paused updates -
   nTop refuses an embed while paused), feeds it its own inputs, and measures the cutter like
   every runner: Volume Integral of 1 (Output "Volume"), Mesh, Export Mesh. nTopCL runs the
   harness (`python -m ntopjewel seat ...`) and the gate checks the cutter against Steiner's
   exact offset volume and the stone's extents + clearance.

The harness carries an embedded copy of the block: rebuild both (this script) after changing it.
"""
from __future__ import annotations

from pathlib import Path

from ntopjewel import nb_jewel as nj
from ntopjewel.notebook_api import ConsoleError, NotebookHelper

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
TEST_ENVELOPE = REPO / "out" / "api" / "stone_seat_test_envelope.stl"

BLOCK_INPUTS = ["Seat Path", "Clearance"]
TEST_VALUES = {"Seat Path": str(TEST_ENVELOPE), "Clearance": 0.05, "Mesh Tolerance": 0.05}
INPUT_ORDER = ["Seat Path", "Clearance", "Mesh Tolerance", "Output Path"]
DEFAULTS = {
    "values": TEST_VALUES,
    "input_order": INPUT_ORDER,
    "test_output": str(REPO / "out" / "api" / "stone_seat_test.stl"),
    "block_to": str(REPO / "ntop" / "blocks" / "stone_seat.ntop"),
    "block_recipe_to": str(REPO / "ntop" / "recipes" / "stone_seat.block.recipe.json"),
    "save_to": str(REPO / "ntop" / "notebooks" / "stone_seat_harness.ntop"),
    "recipe_to": str(REPO / "ntop" / "recipes" / "stone_seat_harness.recipe.json"),
    "pause": False,                     # the harness embeds the block: no paused updates
    "fresh": True,
    "wait_s": 180,
    "volume_hint": "6.5 mm round, 0.05 mm clearance, drop 8 mm: 311.85 mm³ (gems.SeatSpec.design_volume_mm3)",
}


def prepare(params: dict, work_dir: Path) -> dict:
    """Laptop side: write the test seat envelope (6.5 mm round) the block and harness read."""
    from ntopjewel import gems
    spec = gems.SeatSpec(gems.StoneSpec("round", 6.5))
    TEST_ENVELOPE.parent.mkdir(parents=True, exist_ok=True)
    spec.envelope().export(str(TEST_ENVELOPE))
    params.setdefault("values", {})["Seat Path"] = str(TEST_ENVELOPE)
    return params


def build_block(notebook, p: dict, values: dict) -> dict:
    """The block notebook: Seat Path, Clearance -> Seat Cutter (implicit). Saved, not embedded."""
    h = NotebookHelper(notebook)
    notebook.new_notebook()
    path_var = nj.path_variable(h, "Seat Path", nj.absolute(values["Seat Path"], h, "Seat Path"))
    clearance = h.real_var("Clearance", float(values["Clearance"]), "mm")
    imp = h.add("Seat Mesh", mask="import_mesh", must=nj.IMPORT_MESH)
    h.wire(path_var, imp, ["Path", "File Path", "File", "Filename"])
    body = h.add("Seat Body", mask="implicit_from_mesh", must=nj.IMPLICIT_FROM_MESH)
    h.wire(imp, body, ["Mesh"])
    cutter = h.add("Seat Offset", mask="offset", must=nj.OFFSET)
    h.wire(body, cutter, ["Body"])
    h.wire(clearance, cutter, ["Distance", "Offset"])
    out = h.wrap_var("Seat Cutter", cutter)          # core.var<implicit>: what a head subtracts
    h.declare_inputs([path_var, clearance])
    h.set_output(out)
    warnings = nj.settle(h, cutter, "the block's Output")
    Path(p["block_to"]).parent.mkdir(parents=True, exist_ok=True)
    notebook.save_notebook_as(p["block_to"])
    try:
        notebook.export_as_recipe(p["block_recipe_to"], True)
    except Exception as e:
        h.log.append(f"export_as_recipe (block) failed: {e}")
    if not Path(p["block_to"]).exists():
        raise ConsoleError(f"the block was not saved to {p['block_to']}")
    return {"saved": p["block_to"], "recipe": p["block_recipe_to"], "identifiers": h.identifiers, "warnings": warnings,
            "blocks": h.blocks, "states": h.states(0), "log": h.log}


def _harness(h, p, values, test_output):
    seat_path = nj.path_variable(h, "Seat Path", nj.absolute(values["Seat Path"], h, "Seat Path"))
    clearance = h.real_var("Clearance", float(values["Clearance"]), "mm")
    tolerance = h.real_var("Mesh Tolerance", float(values["Mesh Tolerance"]), "mm")
    out_var = nj.path_variable(h, "Output Path", test_output)
    ident = h.embed_block(p["block_to"])
    seat = h.add("Stone Seat", ident)
    h.wire(seat_path, seat, ["Seat Path"])
    h.wire(clearance, seat, ["Clearance"])
    cutter = h.wrap_var("Seat", seat)
    integ, _mesh, export = nj.add_measure_mesh_export(h, cutter, out_var, tolerance)
    return integ, export


def build(notebook, params: dict | None = None) -> dict:
    """Entry point for `api build stone_seat`: the block, then its harness."""
    params = dict(params or {})
    if "save_to" in params and "block_to" not in params:          # --scratch: keep the block beside it
        params["block_to"] = str(Path(params["save_to"]).parent / "stone_seat.ntop")
        params.setdefault("block_recipe_to", str(Path(params["save_to"]).parent / "stone_seat.block.recipe.json"))
    p = {**DEFAULTS, **params}
    values = {**DEFAULTS["values"], **(p.get("values") or {})}
    p["block_to"] = nj.absolute(p["block_to"])
    p["block_recipe_to"] = nj.absolute(p["block_recipe_to"])
    block = build_block(notebook, p, values)
    harness = nj.run_build(notebook, p, DEFAULTS, _harness)
    harness["block"] = block
    return harness
