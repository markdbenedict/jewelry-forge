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
    """The block notebook: Seat Path, Clearance -> Seat Cutter (implicit). Saved; the head blocks
    and the runners embed it."""
    h = nj.Helper(notebook)
    notebook.new_notebook()
    path_var = nj.path_variable(h, "Seat Path", nj.absolute(values["Seat Path"], h, "Seat Path"))
    clearance = h.real_var("Clearance", float(values["Clearance"]), "mm")
    body = h.import_body("Seat Body", path_var)
    cutter = h.offset("Seat Offset", body, clearance)                     # the envelope grown by the clearance
    return nj.save_block(notebook, h, cutter, [path_var, clearance], "Seat Cutter", p, self_test=False)


def _harness(h, p, values, test_output):
    seat_path = nj.path_variable(h, "Seat Path", nj.absolute(values["Seat Path"], h, "Seat Path"))
    clearance = h.real_var("Clearance", float(values["Clearance"]), "mm")
    tolerance = h.real_var("Mesh Tolerance", float(values["Mesh Tolerance"]), "mm")
    out_var = nj.path_variable(h, "Output Path", test_output)
    seat = h.add("Stone Seat", h.embed_block(p["block_to"]))
    h.wire(seat_path, seat, ["Seat Path"])
    h.wire(clearance, seat, ["Clearance"])
    cutter = h.wrap_var("Seat", seat)
    integ, _mesh, export = nj.add_measure_mesh_export(h, cutter, out_var, tolerance)
    return integ, export


def build(notebook, params: dict | None = None) -> dict:
    """Entry point for `api build stone_seat`: the block, then its harness."""
    return nj.block_build(notebook, params, DEFAULTS, "stone_seat", build_block, _harness, needs_seat=False)
