"""Build `ring_shank.ntop` through nTop's Notebook API: a shaped shank from the bar Python writes -
Phase 3, step 1 (ntopjewel.shank).

    Shank Path (text)  -> Import Mesh -> Implicit from Mesh
                       -> Remap Cylindrical Body (Y mapping length = Wrap Length)   the bar wrapped round Z
                       -> Shank Body -> Volume Integral of 1 (Output "Volume"), Mesh (Mesh Tolerance),
                          Export Mesh (Output Path)

The bar is the ring unrolled: X radial, Y along the ring (Y = Wrap Length is one turn, angle 0 at
Y = 0), Z axial, one cross-section every few degrees (the band profile at that angle's width and
thickness), running a turn and a half plus a margin so the seam lies inside material whichever
way nTop reads the angle. X -> r and Z -> z are exact under the map, so the section at every
angle is the one `ShankSpec` designed there; the gate measures that (`shank.check_shank`).

Run:  python -m ntopjewel api build ring_shank      (nTop open, View > Python Console open)
      python -m ntopjewel templates ntop\\notebooks\\ring_shank.ntop --catalog ring_shank
      python -m ntopjewel shank --size 6 --profile court --thickness 1.6 --width-bottom 2.2 --thickness-bottom 1.2
"""
from __future__ import annotations

from pathlib import Path

from ntopjewel import nb_jewel as nj

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
TEST_BAR = REPO / "out" / "api" / "ring_shank_test_bar.stl"

INPUT_ORDER = ["Shank Path", "Wrap Length", "Mesh Tolerance", "Output Path"]


def _spec():
    from ntopjewel import band, shank
    return shank.ShankSpec(band.BandSpec(size=6, profile="court", width_mm=4.0, thickness_mm=1.6, mesh_tolerance_mm=0.1),
                           width_bottom_mm=2.2, thickness_bottom_mm=1.2)


DEFAULTS = {
    "values": {"Shank Path": str(TEST_BAR), "Wrap Length": 56.884, "Mesh Tolerance": 0.1},
    "input_order": INPUT_ORDER,
    "test_output": str(REPO / "out" / "api" / "ring_shank_test.stl"),
    "save_to": str(REPO / "ntop" / "notebooks" / "ring_shank.ntop"),
    "recipe_to": str(REPO / "ntop" / "recipes" / "ring_shank.recipe.json"),
    "pause": True,
    "fresh": True,
    "wait_s": 180,
    "show": ["Shank", "Shank Body"],
    "volume_hint": "court US6, 4 x 1.6 mm at the head tapering to 2.2 x 1.2 mm: about 242 mm³ (ShankSpec.design_volume_mm3)",
}


def prepare(params: dict, work_dir: Path) -> dict:
    """Laptop side: write the test bar the notebook imports, and every input value."""
    spec = _spec()
    TEST_BAR.parent.mkdir(parents=True, exist_ok=True)
    spec.bar_mesh().export(str(TEST_BAR))
    v = spec.notebook_inputs(str(TEST_BAR))
    v.pop("Output Path")
    params["values"] = {**v, **(params.get("values") or {})}
    return params


def _body(h, p, values, test_output):
    bar_path = nj.path_variable(h, "Shank Path", nj.absolute(values["Shank Path"], h, "Shank Path"))
    h.real_var("Wrap Length", float(values["Wrap Length"]), "mm")
    h.real_var("Mesh Tolerance", float(values["Mesh Tolerance"]), "mm")
    out_var = nj.path_variable(h, "Output Path", test_output)

    imp = h.add("Shank Mesh", mask="import_mesh", must=nj.IMPORT_MESH)
    h.wire(bar_path, imp, ["Path", "File Path", "File", "Filename"])
    body = h.add("Shank Bar", mask="implicit_from_mesh", must=nj.IMPLICIT_FROM_MESH)
    h.wire(imp, body, ["Mesh"])
    wrapped = h.add("Shank", mask="remap_cylindrical", must=nj.REMAP_CYLINDRICAL)
    h.wire(body, wrapped, ["Body"])
    h.wire(h.blocks["Wrap Length"], wrapped, ["Y mapping length", "Y Mapping Length", "Mapping Length", "Length"])

    ring = h.wrap_var("Shank Body", wrapped)
    integ, _mesh, export = nj.add_measure_mesh_export(h, ring, out_var, h.blocks["Mesh Tolerance"])
    return integ, export


def build(notebook, params: dict | None = None) -> dict:
    """Entry point for `api build ring_shank`; see the module docstring."""
    return nj.run_build(notebook, params, DEFAULTS, _body)
