"""The `open_bar` library block: one bar of a shank, imported and opened by the edge round - and
the harness that tests it (2026-11-04).

    python -m ntopjewel api build open_bar             # nTop open, View > Python Console open
    python -m ntopjewel api build open_bar --scratch   # both files into out/api/ instead

1. Block `ntop/blocks/open_bar.ntop`:
       inputs  Bar Path (text: a bar STL Python writes, ntopjewel.shank.write_bars - X radial, Y along
               the ring, Z axial), Edge Round Inward (mm, -e), Edge Round (mm, +e), Mesh Tolerance (mm)
       body    Import Mesh -> Implicit from Mesh (Bar) -> the opening: Offset Body (-e, Bar Eroded) ->
               Mesh from Implicit Body (Mesh Tolerance) -> Implicit from Mesh (Bar Re-distanced) ->
               Offset Body (+e, Opened)
       Output  Opened Bar (implicit)
   Every runner with a shank (ring_shank, pave_band, ring_artwork, the solitaires, multistone)
   embeds it once and places one instance per bar slot: six blocks per bar become one, and the
   rule it carries - open each bar on its own, re-distanced between the offsets, unite afterwards
   (CLAUDE.md, nTopCL rules) - lives in one place.
2. Harness `ntop/notebooks/open_bar_harness.ntop`: the block embedded and fed its own inputs, the
   opened bar measured like every runner (Volume Integral of 1, Mesh, Export Mesh).

Runners carry an embedded copy of the block: rebuild them after changing it.
"""
from __future__ import annotations

from pathlib import Path

from ntopjewel import nb_jewel as nj

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
TEST_DIR = REPO / "out" / "api"
TEST_STEM = "open_bar_test"                                     # prepare() writes open_bar_test.bar.stl

SPECS = nj.OPEN_BAR_SPECS                                       # Bar Path, Edge Round Inward, Edge Round, Mesh Tolerance
INPUT_ORDER = nj.input_order(SPECS)

DEFAULTS = {
    "values": {},                       # filled by prepare() (laptop side) - nTop's Python has no trimesh
    "input_order": INPUT_ORDER,
    "test_output": str(REPO / "out" / "api" / "open_bar_test.stl"),
    "block_to": str(REPO / "ntop" / "blocks" / "open_bar.ntop"),
    "block_recipe_to": str(REPO / "ntop" / "recipes" / "open_bar.block.recipe.json"),
    "save_to": str(REPO / "ntop" / "notebooks" / "open_bar_harness.ntop"),
    "recipe_to": str(REPO / "ntop" / "recipes" / "open_bar_harness.recipe.json"),
    "pause": False,                     # the harness embeds the block: no paused updates
    "lazy_ok": True,                    # the GUI may leave the opening unbuilt; nTopCL builds it in every shank run
    "fresh": True,
    "wait_s": 180,
    "volume_hint": "the tapered court US6 bar (ring_shank's test bar) opened by 0.25 mm: a little under its 242 mm³",
}


def _spec():
    from ntopjewel import band, shank
    return shank.ShankSpec(band.BandSpec(size=6, profile="court", width_mm=4.0, thickness_mm=1.6, mesh_tolerance_mm=0.1),
                           width_bottom_mm=2.2, thickness_bottom_mm=1.2)


def prepare(params: dict, work_dir: Path) -> dict:
    """Laptop side: ring_shank's tapered test bar and the opening's numbers (ShankSpec)."""
    from ntopjewel import shank
    spec = _spec()
    TEST_DIR.mkdir(parents=True, exist_ok=True)
    v = spec.notebook_inputs(shank.write_bars(spec, TEST_DIR, TEST_STEM))
    params["values"] = {"Bar Path": v[nj.SLOT_NAMES[0]], "Edge Round Inward": v["Edge Round Inward"],
                        "Edge Round": v["Edge Round"], "Mesh Tolerance": v["Mesh Tolerance"], **(params.get("values") or {})}
    return params


def build_block(notebook, p: dict, values: dict) -> dict:
    h = nj.Helper(notebook)
    notebook.new_notebook()
    ids = nj.add_typed_inputs(h, SPECS, values)
    opened = nj.open_bar_body(h, ids)
    return nj.save_block(notebook, h, opened, [ids[n] for n, _ in SPECS], "Opened Bar", p)


def _harness(h, p, values, test_output):
    ids = nj.add_typed_inputs(h, SPECS, values)
    out_var = nj.path_variable(h, "Output Path", test_output)
    bar = h.add("Opened Bar", h.embed_block(p["block_to"]))
    for name, _ in SPECS:
        h.wire(ids[name], bar, [name])
    body = h.wrap_var("Result", bar)
    integ, _mesh, export = nj.add_measure_mesh_export(h, body, out_var, ids["Mesh Tolerance"])
    return integ, export


def build(notebook, params: dict | None = None) -> dict:
    """Entry point for `api build open_bar`: the block, then its harness."""
    return nj.block_build(notebook, params, DEFAULTS, "open_bar", build_block, _harness, needs_seat=False)
