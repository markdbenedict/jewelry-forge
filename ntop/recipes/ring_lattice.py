"""Phase 3 step 8: `ring_lattice.ntop`, a band whose metal between a bore skin and the outer face is an open gyroid
lattice (2026-11-06).

    python -m ntopjewel api build ring_lattice        # nTop open (in the foreground), View > Python Console open
    python -m ntopjewel lattice                       # a lattice band through it: nTopCL + the lattice gate (out\\lattice)

The band is ring_band_profile's (cylinders, dome and comfort tori, the opening by the edge round). The lattice is nTop's
own `gyroid_implicit` (the surface, cubic cells of Cell Size) - whose field is not a distance (6 Nov), so only a thin seed
is thickened (`thicken_implicit`, Seed Thickness in field units), wrapped round the ring by Remap Cylindrical Body (Wrap
Length = a whole number of cells, so the pattern closes on itself), trimmed by the band inset by the growth inside the
zone, re-distanced (the mesh round trip at Seed Mesh Tolerance) and grown to the wall by Sheet Growth - which is the
opening of the trimmed sheet: its ends at the dome rounded, every lip where a sheet runs under the outer face at least
twice the growth (the marginal wall; the second run, 7 Nov, found lips of 0.26 before this) - and united with the band
less the zone, the bore skin and the rims (nb_lattice.body). Python holds the same geometry exactly
(ntopjewel.lattice.GyroidSpec, seeded_sheet_sdf), so the gate measures the built mesh against it point by point, and
flood-fills the voids from the outer face: a pocket that reaches no opening (trapped resin, trapped investment) fails
the part.
"""
from __future__ import annotations

from pathlib import Path

from ntopjewel import nb_jewel as nj
from ntopjewel import nb_lattice as nl

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
SPECS = nl.LATTICE_SPECS
INPUT_ORDER = nl.INPUT_ORDER

DEFAULTS = {
    "values": {},
    "input_order": INPUT_ORDER,
    "test_output": str(REPO / "out" / "api" / "ring_lattice_test.stl"),
    "save_to": str(REPO / "ntop" / "notebooks" / "ring_lattice.ntop"),
    "recipe_to": str(REPO / "ntop" / "recipes" / "ring_lattice.recipe.json"),
    "pause": False,
    "lazy_ok": True,          # nTopCL is the test: a 3 M-triangle lattice mesh may outlast the session's wait
    "fresh": True,
    "wait_s": 300,
    "volume_hint": "gyroid flat US 6 7 x 3.5, 3.5 mm cells, 0.6 sheets: the solid band's 1538 mm³ less a third (GyroidSpec.design_volume_mm3)",
}


def prepare(params: dict, work_dir: Path) -> dict:
    """Laptop side: the default lattice band's numbers."""
    from ntopjewel import band, lattice
    spec = lattice.GyroidSpec(band.BandSpec(size=6, profile="flat", width_mm=7.0, thickness_mm=3.5, mesh_tolerance_mm=0.1))
    v = spec.notebook_inputs("")
    v.pop("Output Path")
    params["values"] = {**v, **(params.get("values") or {})}
    return params


def build(notebook, params: dict | None = None) -> dict:
    """Entry point for `api build ring_lattice`."""
    return nj.standard_build(notebook, params, DEFAULTS, nl.body, "ring_lattice")
