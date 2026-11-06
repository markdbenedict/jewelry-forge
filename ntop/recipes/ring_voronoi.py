"""Phase 3 step 7: `ring_voronoi.ntop`, a band with nTop's voronoi deboss on its outer face (2026-11-06).

    python -m ntopjewel api build ring_voronoi        # nTop open (in the foreground), View > Python Console open
    python -m ntopjewel texture --kind voronoi        # a voronoi band through it: nTopCL + the envelope gate (out\\texture)

The band is ring_band_profile's (cylinders, dome and comfort tori, the opening by the edge round). The texture is
nTop's own `voronoi_deboss` toolkit block (nb_texture.add_voronoi_deboss): the walls of a 3-D voronoi tessellation
of the body carved as half-round grooves - Thickness wide and half as deep (measured 6 Nov) - over EVERY face. So:

    Band Body (the profiled band, opened)
    Grooved = Voronoi Deboss(Band Body; Feature size, Voronoi cell count, Relaxation iterations, Thickness = Groove,
                             Blend radius, Spatial weighting)
    Dents = Band Body − Grooved                             (what the texture took off, on every face)
    Zone = Cylinder(Zone Z Bottom .. Zone Z Top, 40 mm) − Cylinder(same, Zone Inner Radius)
                                                            (between the rims, from just under the dome outwards)
    Textured = Band Body − (Dents ∩ Zone)                   = the variable "Textured Band": the outer face grooved,
                                                            the bore, the sides and the rims as designed
    -> Volume Integral (the Output) / Mesh from Implicit Body -> Export Mesh (Output Path)

The cells are nTop's (no seed input), so Python gates the part by an envelope (ntopjewel.fieldtex.check_fieldtex),
not against a model of the grooves.
"""
from __future__ import annotations

from pathlib import Path

from ntopjewel import nb_jewel as nj
from ntopjewel import nb_texture as nt

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
SPECS = nt.VORONOI_SPECS
INPUT_ORDER = list(nj.BAND_INPUTS) + [n for n, _ in SPECS] + ["Output Path"]

DEFAULTS = {
    "values": {},
    "input_order": INPUT_ORDER,
    "test_output": str(REPO / "out" / "api" / "ring_voronoi_test.stl"),
    "save_to": str(REPO / "ntop" / "notebooks" / "ring_voronoi.ntop"),
    "recipe_to": str(REPO / "ntop" / "recipes" / "ring_voronoi.recipe.json"),
    "pause": False,
    "lazy_ok": True,          # nTopCL is the test (the toolkit block's Blend type enum is set only by its default)
    "fresh": True,
    "wait_s": 120,
    "volume_hint": "voronoi US 6 court 4 x 1.6, 200 cells, 0.2 grooves: the plain band's 306 mm³ less a few (VoronoiSpec.max_removal_mm3)",
}


def prepare(params: dict, work_dir: Path) -> dict:
    """Laptop side: the default voronoi band's numbers."""
    from ntopjewel import band, fieldtex
    spec = fieldtex.VoronoiSpec(band.BandSpec(size=6, profile="court", width_mm=4.0, thickness_mm=1.6, mesh_tolerance_mm=0.05))
    v = spec.notebook_inputs("")
    v.pop("Output Path")
    params["values"] = {**v, **(params.get("values") or {})}
    return params


def _body(h, p, values, test_output):
    nj.add_band_inputs(h, values)
    ids = nj.add_typed_inputs(h, SPECS, values)
    out_var = nj.path_variable(h, "Output Path", test_output)
    with h.section("Band"):
        band = nj.add_profiled_band(h)
    with h.section("Voronoi"):
        grooved = nt.add_voronoi_deboss(h, band, ids)
    with h.section("Mask"):
        body = nt.add_outer_face_mask(h, band, grooved, ids)
    with h.section("Textured"):
        integ, _mesh, export = nj.add_measure_mesh_export(h, body, out_var, h.blocks["Mesh Tolerance"])
    return integ, export


def build(notebook, params: dict | None = None) -> dict:
    """Entry point for `api build ring_voronoi`."""
    return nj.standard_build(notebook, params, DEFAULTS, _body, "ring_voronoi")
