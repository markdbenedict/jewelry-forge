"""Phase 3 step 7: `ring_ribbed.ntop`, a band with nTop's triangle wave on its outer face (2026-11-06).

    python -m ntopjewel api build ring_ribbed        # nTop open (in the foreground), View > Python Console open
    python -m ntopjewel texture --kind ribbed        # through it: nTopCL + the envelope gate (out\\texture)

The texture is nTop's `triangle_wave_texture` toolkit block: the surface displaced OUTWARD along its normal by a
triangle wave of z (troughs on the surface, peaks about 3 x Wave height above it - measured 2026-11-06), so the band
is first offset in by the rib depth (Erosion, negative) and the ribs stand back up to the designed surface: ribs round
the ring, Rib Spacing apart, over EVERY face until the mask.

    Band Body (the profiled band, opened)
    Eroded = Offset(Band Body, Erosion)
    Textured All Over = Triangle Wave Texture(Eroded; Direction Z, Wave height, Wave spacing = Rib Spacing)
    Dents = Band Body − Textured All Over                   (what the texture took off, on every face)
    Zone = Cylinder(Zone Z Bottom .. Zone Z Top, 40 mm) − Cylinder(same, Zone Inner Radius)
    Textured = Band Body − (Dents ∩ Zone)                   = the variable "Textured Band"
    -> Volume Integral (the Output) / Mesh from Implicit Body -> Export Mesh (Output Path)

The noise is nTop's, so Python gates the part by an envelope (ntopjewel.fieldtex.check_fieldtex), not against a
model of it. The body is nb_texture.product_body("ribbed"); the inputs nb_texture.product_specs("ribbed").
"""
from __future__ import annotations

from pathlib import Path

from ntopjewel import nb_jewel as nj
from ntopjewel import nb_texture as nt

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
KIND = "ribbed"
SPECS = nt.product_specs(KIND)
INPUT_ORDER = nt.product_input_order(KIND)

DEFAULTS = {
    "values": {},
    "input_order": INPUT_ORDER,
    "test_output": str(REPO / "out" / "api" / "ring_ribbed_test.stl"),
    "save_to": str(REPO / "ntop" / "notebooks" / "ring_ribbed.ntop"),
    "recipe_to": str(REPO / "ntop" / "recipes" / "ring_ribbed.recipe.json"),
    "pause": False,
    "lazy_ok": True,          # nTopCL is the test (the toolkit block's enums are set only by their defaults)
    "fresh": True,
    "wait_s": 120,
    "volume_hint": "ribbed US 6 court 4 x 1.6, ribs 0.5 apart 0.2 deep: the plain band's 306 mm³ less about half the zone face x 0.2",
}


def prepare(params: dict, work_dir: Path) -> dict:
    """Laptop side: the default ribbed band's numbers."""
    from ntopjewel import band, fieldtex
    spec = fieldtex.make_spec(KIND, band.BandSpec(size=6, profile="court", width_mm=4.0, thickness_mm=1.6, mesh_tolerance_mm=0.05))
    v = spec.notebook_inputs("")
    v.pop("Output Path")
    params["values"] = {**v, **(params.get("values") or {})}
    return params


def build(notebook, params: dict | None = None) -> dict:
    """Entry point for `api build ring_ribbed`."""
    return nj.standard_build(notebook, params, DEFAULTS, nt.product_body(KIND), "ring_ribbed")
