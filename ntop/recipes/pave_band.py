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

INPUT_ORDER = [*SLOT_NAMES, "Wrap Length", "Edge Round", "Edge Round Inward", "Mesh Tolerance",
               "Pave Seats Path", "Pave Beads Path", "Output Path"]


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


def _layer(h, name: str, path_var: str) -> str:
    imp = h.add(f"{name} Mesh", mask="import_mesh", must=nj.IMPORT_MESH)
    h.wire(path_var, imp, ["Path", "File Path", "File", "Filename"])
    body = h.add(f"{name}", mask="implicit_from_mesh", must=nj.IMPLICIT_FROM_MESH)
    h.wire(imp, body, ["Mesh"])
    return body


def _body(h, p, values, test_output):
    bar_paths = [nj.path_variable(h, name, nj.absolute(values[name], h, name)) for name in SLOT_NAMES]
    for name in ("Wrap Length", "Edge Round", "Edge Round Inward", "Mesh Tolerance"):
        h.real_var(name, float(values[name]), "mm")
    seats_var = nj.path_variable(h, "Pave Seats Path", nj.absolute(values["Pave Seats Path"], h, "Pave Seats Path"))
    beads_var = nj.path_variable(h, "Pave Beads Path", nj.absolute(values["Pave Beads Path"], h, "Pave Beads Path"))
    out_var = nj.path_variable(h, "Output Path", test_output)

    wrapped = nj.add_wrapped_shank(h, bar_paths, h.blocks["Wrap Length"], h.blocks["Edge Round Inward"], h.blocks["Edge Round"],
                                   h.blocks["Mesh Tolerance"])
    shank_body = h.wrap_var("Shank Body", wrapped)
    beads = _layer(h, "Pave Beads", beads_var)
    seats = _layer(h, "Pave Seats", seats_var)
    beaded = h.add("Beaded", mask="union", must=nj.UNION)
    h.to_list(shank_body, beaded, ["Bodies"])
    h.to_list(beads, beaded, ["Bodies"])
    ring = h.add("Ring", mask="subtract", must=nj.SUBTRACT)
    h.wire(beaded, ring, ["Primary Body", "Body"])
    h.to_list(seats, ring, ["Subtraction Bodies", "Bodies"])
    out = h.wrap_var("Ring Body", ring)
    integ, _mesh, export = nj.add_measure_mesh_export(h, out, out_var, h.blocks["Mesh Tolerance"])
    return integ, export


def build(notebook, params: dict | None = None) -> dict:
    """Entry point for `api build pave_band`; see the module docstring."""
    p = {**DEFAULTS, **(params or {})}
    if not (p.get("values") or {}):
        from ntopjewel.notebook_api import ConsoleError
        raise ConsoleError("no input values: run through `python -m ntopjewel api build pave_band` (prepare() computes them)")
    return nj.run_build(notebook, params, DEFAULTS, _body)
