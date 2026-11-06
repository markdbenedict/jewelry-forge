"""Phase 3 step 7: `ring_frost.ntop`, a band with nTop's surface roughness on its outer face (2026-11-06).

    python -m ntopjewel api build ring_frost        # nTop open (in the foreground), View > Python Console open
    python -m ntopjewel texture --kind frost        # through it: nTopCL + the envelope gate (out\\texture)

The texture is nTop's `surface_roughness` toolkit block: simplex noise both ways, ±amplitude (0.1 -> ±0.085 measured),
frequency per metre (the spec's grain in mm is 1000 / frequency), over EVERY face - a satin / sandblasted frost. It adds
metal as well as cutting, so the mask is two-sided: the dents inside the zone cut from the band, the bumps inside it
united.

    Band Body (the profiled band, opened)
    Textured All Over = Surface Roughness(Band Body; Roughness frequency = Frequency, Roughess amplitude = Amplitude, Seed value = Seed)
    Dents = Band Body − Textured All Over                   (what the texture took off, on every face)
    Zone = Cylinder(Zone Z Bottom .. Zone Z Top, 40 mm) − Cylinder(same, Zone Inner Radius)
    Cut = Band Body − (Dents ∩ Zone); Bumps = Textured All Over − Band Body
    Textured = Cut ∪ (Bumps ∩ Zone)                         = the variable "Textured Band"
    -> Volume Integral (the Output) / Mesh from Implicit Body -> Export Mesh (Output Path)

The noise is nTop's, so Python gates the part by an envelope (ntopjewel.fieldtex.check_fieldtex), not against a
model of it. The body is nb_texture.product_body("frost"); the inputs nb_texture.product_specs("frost").
"""
from __future__ import annotations

from pathlib import Path

from ntopjewel import nb_jewel as nj
from ntopjewel import nb_texture as nt

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
KIND = "frost"
SPECS = nt.product_specs(KIND)
INPUT_ORDER = nt.product_input_order(KIND)

DEFAULTS = {
    "values": {},
    "input_order": INPUT_ORDER,
    "test_output": str(REPO / "out" / "api" / "ring_frost_test.stl"),
    "save_to": str(REPO / "ntop" / "notebooks" / "ring_frost.ntop"),
    "recipe_to": str(REPO / "ntop" / "recipes" / "ring_frost.recipe.json"),
    "pause": False,
    "lazy_ok": True,          # nTopCL is the test (the toolkit block's enums are set only by their defaults)
    "fresh": True,
    "wait_s": 120,
    "volume_hint": "frost US 6 court 4 x 1.6, grain 2 mm, ±0.08: about the plain band's 306 mm³ (the noise adds as much as it takes)",
}


def prepare(params: dict, work_dir: Path) -> dict:
    """Laptop side: the default frost band's numbers."""
    from ntopjewel import band, fieldtex
    spec = fieldtex.make_spec(KIND, band.BandSpec(size=6, profile="court", width_mm=4.0, thickness_mm=1.6, mesh_tolerance_mm=0.05))
    v = spec.notebook_inputs("")
    v.pop("Output Path")
    params["values"] = {**v, **(params.get("values") or {})}
    return params


def build(notebook, params: dict | None = None) -> dict:
    """Entry point for `api build ring_frost`."""
    return nj.standard_build(notebook, params, DEFAULTS, nt.product_body(KIND), "ring_frost")
