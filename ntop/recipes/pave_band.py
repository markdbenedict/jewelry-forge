"""Build `pave_band.ntop` through nTop's Notebook API: a band set with pavé - Phase 3 step 2/3
(ntopjewel.pave).

    Shank Path .. Shank Path 4  -> the band exactly as ring_shank.ntop builds it (nj.add_wrapped_shank:
                                   each bar imported, opened by the edge round on its own, the bars
                                   united, wrapped round Z by Remap Cylindrical (Wrap Length)) = Shank Body
    Pave Beads Path             -> Import Mesh -> Implicit from Mesh (every bead, a sphere standing on the
                                   band's surface in the gaps between the stones; disjoint)
    Pave Seats Path             -> Import Mesh -> Implicit from Mesh (every stone's seat: its envelope
                                   grown by the clearance with the drop-in path above, the light hole on
                                   through to the bore; disjoint)
    Ring                        = (Shank Body ∪ beads) − seats. The seats are cut AFTER the beads go on, so
                                   every drop-in path is clear and a bead in a tight interstice is trimmed
                                   by the openings, as on the bench; neither layer is opened (the edge round
                                   would melt a 0.5 mm bead and round the seats' rims)
                               -> Volume Integral of 1 (Output "Volume"), Mesh (Mesh Tolerance), Export Mesh

Python lays the stones out on the real surface (pave.PaveSpec: the pitch along and across the rows
solved on the girdles' 3-D edges) and writes both layers; the notebook has no arithmetic.

Run:  python -m ntopjewel api build pave_band      (nTop open, View > Python Console open, in the foreground)
      python -m ntopjewel pave --size 6 --stone 1.3 --rows 2 --span 180
"""
from __future__ import annotations

from pathlib import Path

from ntopjewel import nb_jewel as nj
from ntopjewel.nb_jewel import SLOT_NAMES

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
TEST_DIR = REPO / "out" / "api"
TEST_STEM = "pave_band_test"

SPECS = nj.SHANK_SPECS + [("Pave Seats Path", "path"), ("Pave Beads Path", "path")]
INPUT_ORDER = nj.input_order(SPECS)


def _spec():
    from ntopjewel import pave, shank
    b = pave.band_for(1.3, 1, "staggered", 6)
    return pave.PaveSpec(shank.ShankSpec(b), stone_mm=1.3, rows=1, span_deg=60.0)


DEFAULTS = {
    "values": {},
    "input_order": INPUT_ORDER,
    "test_output": str(REPO / "out" / "api" / "pave_band_test.stl"),
    "save_to": str(REPO / "ntop" / "notebooks" / "pave_band.ntop"),
    "recipe_to": str(REPO / "ntop" / "recipes" / "pave_band.recipe.json"),
    "pause": True,
    "fresh": True,
    "wait_s": 300,
    "show": ["Ring Body"],
    "volume_hint": "US6 comfort-flat 2.5 x 1.6 band, one row of 1.3 mm stones over 60° (7 stones, 16 beads): see `pave --dry-run`",
}


def prepare(params: dict, work_dir: Path) -> dict:
    """Laptop side: the test band's bars, seats and beads, and every input value."""
    from ntopjewel import shank
    spec = _spec()
    TEST_DIR.mkdir(parents=True, exist_ok=True)
    bars = shank.write_bars(spec.shank, TEST_DIR, TEST_STEM)
    seats, beads = spec.write_layer(TEST_DIR, TEST_STEM)
    v = spec.notebook_inputs(bars, seats, beads)
    v.pop("Output Path")
    params["values"] = {**v, **(params.get("values") or {})}
    return params


def _body(h, p, values, test_output):
    ids = nj.add_typed_inputs(h, SPECS, values)
    out_var = nj.path_variable(h, "Output Path", test_output)
    with h.section("Shank"):
        shank_body = h.wrap_var("Shank Body", nj.add_wrapped_shank(h, [ids[n] for n in SLOT_NAMES], ids["Wrap Length"],
                                                                   ids["Edge Round Inward"], ids["Edge Round"], ids["Mesh Tolerance"]))
    with h.section("Pavé"):
        beads = h.import_body("Pave Beads", ids["Pave Beads Path"])
        seats = h.import_body("Pave Seats", ids["Pave Seats Path"])
        beaded = h.union("Beaded", [shank_body, beads], comment="The beads stand on the opened band (not rounded: the opening would melt them).")
        ring = h.subtract("Ring", beaded, [seats], comment=(
            "The seats are cut AFTER the beads go on: every drop-in path is clear, a bead in a tight gap is trimmed by "
            "the openings, as on the bench."))
    with h.section("Result"):
        out = h.wrap_var("Ring Body", ring)
        integ, _mesh, export = nj.add_measure_mesh_export(h, out, out_var, ids["Mesh Tolerance"])
    return integ, export


def build(notebook, params: dict | None = None) -> dict:
    """Entry point for `api build pave_band`; see the module docstring."""
    return nj.standard_build(notebook, params, DEFAULTS, _body, "pave_band")
