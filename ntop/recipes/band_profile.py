"""Build `ring_band_profile.ntop` through nTop's Notebook API (Private Beta, nTop 6.3+).

What it builds (see band-profile.md for the geometry and ntopjewel.band for the numbers):

    inputs (12 real/text variables, in catalog order)
    Outer / Bore cylinders  ->  Boolean Subtract (Band)  ->  Boolean Intersect with Dome Torus
    and Comfort Torus (Shaped)  ->  Offset Body (−e) -> Offset Body (+e) = Band Body
    -> Volume Integral of the constant 1 over the body (variable "Volume" = the notebook Output)
    -> Mesh from Implicit Body -> Export Mesh (file = Output Path)

Why a volume integral and not Mass Properties: Mass Properties needs a Density in kg/m3, and a
fresh notebook's unit table knows only mm ("kg/m3" is not a unit this notebook knows, 2026-10-27);
∫ 1 dV needs no unit anywhere.

How to run it
  * From Claude Code on the laptop (nTop open, View > Python Console open):
        python -m ntopjewel api build band_profile            # --scratch to save under out\\api first
  * Without SSH: `python -m ntopjewel api build band_profile --dry-run` prints one
    exec(open(r"...band_profile.driver.py").read()) line to paste into the GUI console;
    then `python -m ntopjewel api collect band_profile` reads the result.

Verified 2026-10-27 on nTop 6.3.3: 16 blocks e_OK, nTopCL run clean, gate PASS for all five
profiles. The shared geometry lives in ntopjewel.nb_jewel (stdlib only) so ring_features.py
builds the same band.
"""
from __future__ import annotations

from pathlib import Path

from ntopjewel import nb_jewel as nj

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]

# Court profile, US 6, 4 mm wide, 1.3 mm thick: `python -m ntopjewel band --size 6 --profile court --dry-run`
TEST_VALUES = {
    "Outer Radius": 9.5534,
    "Bore Radius": 8.2534,
    "Z Top": 2.0,
    "Z Bottom": -2.0,
    "Dome Ring Radius": 3.2371,
    "Dome Tube Radius": 6.3163,
    "Comfort Ring Radius": 15.3894,
    "Comfort Tube Radius": 7.136,
    "Edge Round": 0.25,
    "Edge Round Inward": -0.25,
    "Mesh Tolerance": 0.1,
}
INPUT_ORDER = list(TEST_VALUES) + ["Output Path"]
assert list(TEST_VALUES) == nj.BAND_INPUTS

DEFAULTS = {
    "values": TEST_VALUES,
    "input_order": INPUT_ORDER,
    "test_output": str(REPO / "out" / "api" / "ring_band_profile_test.stl"),
    "save_to": str(REPO / "ntop" / "notebooks" / "ring_band_profile.ntop"),
    "recipe_to": str(REPO / "ntop" / "recipes" / "ring_band_profile.recipe.json"),
    "pause": True,            # batch the edits with paused_updates()
    "fresh": True,            # start from new_notebook()
    "wait_s": 120,
    "volume_hint": "about 244 mm³ for the court test values (BandSpec.design_volume_mm3)",
}


def _body(h, p, values, test_output):
    nj.add_band_inputs(h, values)
    out_var = nj.path_variable(h, "Output Path", test_output)
    body = nj.add_profiled_band(h)
    integ, _mesh, export = nj.add_measure_mesh_export(h, body, out_var, h.blocks["Mesh Tolerance"])
    return integ, export


def build(notebook, params: dict | None = None) -> dict:
    """Entry point for `api build band_profile`; see the module docstring."""
    return nj.run_build(notebook, params, DEFAULTS, _body)
