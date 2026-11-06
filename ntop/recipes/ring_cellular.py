"""Phase 3 step 7: `ring_cellular.ntop`, a band with nTop's cellular noise deboss on its outer face (2026-11-06).

    python -m ntopjewel api build ring_cellular        # nTop open (in the foreground), View > Python Console open
    python -m ntopjewel texture --kind cellular        # through it: nTopCL + the envelope gate (out\\texture)

The texture is nTop's `cellular_noise_deboss` toolkit block: soft dimples at the cells of a Worley noise, over EVERY
face. Its Frequency is a unitless real per metre, made in the notebook as a metre (1000 mm) over the Grain (mm); its
"Depth factor" is a length but not the depth - the dimples come out about 3.4 x factor x grain deep (measured once,
tables.cellular_noise_depth_per_factor_per_mm), so the spec sets the factor from the depth it wants.

    Band Body (the profiled band, opened)
    Noise Frequency = Thousand / Grain
    Textured All Over = Cellular Noise Deboss(Band Body; Frequency = Noise Frequency, Depth factor = Factor, Random seed = Seed;
                                             Distance and Return type at nTop's defaults)
    Dents = Band Body − Textured All Over                   (what the texture took off, on every face)
    Zone = Cylinder(Zone Z Bottom .. Zone Z Top, 40 mm) − Cylinder(same, Zone Inner Radius)
    Textured = Band Body − (Dents ∩ Zone)                   = the variable "Textured Band"
    -> Volume Integral (the Output) / Mesh from Implicit Body -> Export Mesh (Output Path)

The noise is nTop's, so Python gates the part by an envelope (ntopjewel.fieldtex.check_fieldtex), not against a
model of it. The body is nb_texture.product_body("cellular"); the inputs nb_texture.product_specs("cellular").
"""
from __future__ import annotations

from pathlib import Path

from ntopjewel import nb_jewel as nj
from ntopjewel import nb_texture as nt

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
KIND = "cellular"
SPECS = nt.product_specs(KIND)
INPUT_ORDER = nt.product_input_order(KIND)

DEFAULTS = {
    "values": {},
    "input_order": INPUT_ORDER,
    "test_output": str(REPO / "out" / "api" / "ring_cellular_test.stl"),
    "save_to": str(REPO / "ntop" / "notebooks" / "ring_cellular.ntop"),
    "recipe_to": str(REPO / "ntop" / "recipes" / "ring_cellular.recipe.json"),
    "pause": False,
    "lazy_ok": True,          # nTopCL is the test (the toolkit block's enums are set only by their defaults)
    "fresh": True,
    "wait_s": 120,
    "volume_hint": "cellular US 6 court 4 x 1.6, grain 2 mm, 0.08 deep: the plain band's 306 mm³ less a few",
}


def prepare(params: dict, work_dir: Path) -> dict:
    """Laptop side: the default cellular band's numbers."""
    from ntopjewel import band, fieldtex
    spec = fieldtex.make_spec(KIND, band.BandSpec(size=6, profile="court", width_mm=4.0, thickness_mm=1.6, mesh_tolerance_mm=0.05))
    v = spec.notebook_inputs("")
    v.pop("Output Path")
    params["values"] = {**v, **(params.get("values") or {})}
    return params


def build(notebook, params: dict | None = None) -> dict:
    """Entry point for `api build ring_cellular`."""
    return nj.standard_build(notebook, params, DEFAULTS, nt.product_body(KIND), "ring_cellular")
