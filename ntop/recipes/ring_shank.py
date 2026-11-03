"""Build `ring_shank.ntop` through nTop's Notebook API: a shaped shank from the bars Python writes -
Phase 3, step 1 (ntopjewel.shank).

    Shank Path .. Shank Path 4 (text)  -> Import Mesh -> Implicit from Mesh, each
                       -> each: Offset Body (Edge Round Inward, -e) -> Mesh -> Implicit from Mesh -> Offset Body
                          (Edge Round, +e): the opening (nj.add_opening) that rounds every edge a cut left sharp
                          (a split's slot, a bridge's ends); the band's own edges are rounded that much in the
                          section already. On the bar, where the field is exact - and on each bar apart, since a
                          union's field erodes into its overlaps (a 0.05 mm groove along a split's seam, 2026-11-02)
                       -> Boolean Union of the four opened bars (Shank Bars): bodies that cross each other - a
                          split's halves, a double band's bridges, a rope's, plait's or trinity knot's strands -
                          come in separate bars and are united HERE, as implicits (a mesh union left faces
                          micrometres apart along its seams, which the import read as self-intersecting,
                          2026-11-02); an unused slot imports the smallest bar again, which changes nothing
                       -> Remap Cylindrical Body (Y mapping length = Wrap Length)   the bar wrapped round Z
                       -> Shank Body -> Volume Integral of 1 (Output "Volume"), Mesh (Mesh Tolerance),
                          Export Mesh (Output Path)

A bar is the ring unrolled: X radial, Y along the ring (Y = Wrap Length is one turn, angle 0 at
Y = 0), Z axial, one cross-section every few degrees (the band profile at that angle's width and
thickness), running a turn and a half plus a margin so the seam lies inside material whichever
way nTop reads the angle (a body that does not run the whole way round appears at its angle and
a turn on). X -> r and Z -> z are exact under the map, so the section at every angle is the one
`ShankSpec` designed there; the gate measures that (`shank.check_shank`).

Run:  python -m ntopjewel api build ring_shank      (nTop open, View > Python Console open)
      python -m ntopjewel templates ntop\\notebooks\\ring_shank.ntop --catalog ring_shank
      python -m ntopjewel shank --size 6 --profile court --thickness 1.6 --width-bottom 2.2 --thickness-bottom 1.2
"""
from __future__ import annotations

from pathlib import Path

from ntopjewel import nb_jewel as nj
from ntopjewel.nb_jewel import SLOT_NAMES

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
TEST_DIR = REPO / "out" / "api"
TEST_STEM = "ring_shank_test"                                     # prepare() writes ring_shank_test.bar.stl

INPUT_ORDER = [*SLOT_NAMES, "Wrap Length", "Edge Round", "Edge Round Inward", "Mesh Tolerance", "Output Path"]


def _spec():
    from ntopjewel import band, shank
    return shank.ShankSpec(band.BandSpec(size=6, profile="court", width_mm=4.0, thickness_mm=1.6, mesh_tolerance_mm=0.1),
                           width_bottom_mm=2.2, thickness_bottom_mm=1.2)


DEFAULTS = {
    "values": {**{name: str(TEST_DIR / f"{TEST_STEM}.bar.stl") for name in SLOT_NAMES},
               "Wrap Length": 56.884, "Edge Round": 0.25, "Edge Round Inward": -0.25, "Mesh Tolerance": 0.1},
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
    """Laptop side: write the test bars the notebook imports (the tapered shank: one bar and the
    same file in the other slots), and every input value."""
    from ntopjewel import shank
    spec = _spec()
    TEST_DIR.mkdir(parents=True, exist_ok=True)
    v = spec.notebook_inputs(shank.write_bars(spec, TEST_DIR, TEST_STEM))
    v.pop("Output Path")
    params["values"] = {**v, **(params.get("values") or {})}
    return params


def _body(h, p, values, test_output):
    bar_paths = [nj.path_variable(h, name, nj.absolute(values[name], h, name)) for name in SLOT_NAMES]
    for name in ("Wrap Length", "Edge Round", "Edge Round Inward", "Mesh Tolerance"):
        h.real_var(name, float(values[name]), "mm")
    out_var = nj.path_variable(h, "Output Path", test_output)

    wrapped = nj.add_wrapped_shank(h, bar_paths, h.blocks["Wrap Length"], h.blocks["Edge Round Inward"], h.blocks["Edge Round"],
                                   h.blocks["Mesh Tolerance"])
    ring = h.wrap_var("Shank Body", wrapped)
    integ, _mesh, export = nj.add_measure_mesh_export(h, ring, out_var, h.blocks["Mesh Tolerance"])
    return integ, export


def build(notebook, params: dict | None = None) -> dict:
    """Entry point for `api build ring_shank`; see the module docstring."""
    return nj.run_build(notebook, params, DEFAULTS, _body)
