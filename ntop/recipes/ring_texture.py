"""Phase 3 step 7: `ring_texture.ntop`, a hammered band, through nTop's Notebook API (2026-11-05).

    python -m ntopjewel api build ring_texture        # nTop open (in the foreground), View > Python Console open
    python -m ntopjewel texture                       # a hammered band through it: nTopCL + the gate (out\\texture)

The band is ring_band_profile's (cylinders, dome and comfort tori, the opening by the edge round). The strikes
are nTop's own: Import Points reads Python's centres (`HammeredSpec.write_centres`, comma-separated x,y,z in
mm), ONE Sphere takes the whole list on its Center Point and makes a sphere per point, a Boolean Union joins
them - measured by points_probe (2026-11-05: 4.7346 mm³ against Python's 4.734). Their union is the distance
to the nearest centre less the hammer's radius, so no mesh of the dimples goes to nTop.

    Band Body (the profiled band, opened)
    Strike Centres (Import Points: Strikes Path, Units = Strikes Units) -> Strikes (Sphere, Strike Radius)
      -> Strikes United (Boolean Union) = the variable "Strikes Body"
    Struck Band = Band Body - Strikes Body (sharp: a ridge between two strikes is a crease, as hammering leaves it)
      = the variable "Struck Band" (measured AND meshed: a block output used twice loses a wire)
    -> Volume Integral (the Output) / Mesh from Implicit Body -> Export Mesh (Output Path)

Strikes Units is a notebook input because the API can neither set nor read an enum, and Import Points' Units
has no default; nTopCL sets it (1 = mm, measured). The strikes are subtracted after the opening, so their
ridges stay sharp - the design is (band opened) less the spheres, which is what `HammeredSpec.design_mesh` models.
"""
from __future__ import annotations

from pathlib import Path

from ntopjewel import nb_jewel as nj

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
CENTRES = REPO / "out" / "api" / "ring_texture_test_centres.csv"
STRIKE_SPECS = [("Strikes Path", "path"), ("Strike Radius", "mm")]
INPUT_ORDER = list(nj.BAND_INPUTS) + [n for n, _ in STRIKE_SPECS] + ["Strikes Units", "Output Path"]

DEFAULTS = {
    "values": {},
    "input_order": INPUT_ORDER,
    "test_output": str(REPO / "out" / "api" / "ring_texture_test.stl"),
    "save_to": str(REPO / "ntop" / "notebooks" / "ring_texture.ntop"),
    "recipe_to": str(REPO / "ntop" / "recipes" / "ring_texture.recipe.json"),
    "pause": False,
    "lazy_ok": True,          # nTopCL is the test: Import Points' Units is set only at run time
    "fresh": True,
    "wait_s": 120,
    "volume_hint": "hammered US 6 court 4 x 1.6: about 292 mm³ (HammeredSpec.design_volume_mm3; the plain band 306)",
}


def prepare(params: dict, work_dir: Path) -> dict:
    """Laptop side: the default hammered band's numbers and its strike centres."""
    from ntopjewel import band, texture
    spec = texture.HammeredSpec(band.BandSpec(size=6, profile="court", width_mm=4.0, thickness_mm=1.6, mesh_tolerance_mm=0.05))
    CENTRES.parent.mkdir(parents=True, exist_ok=True)
    spec.write_centres(CENTRES)
    v = spec.notebook_inputs(str(CENTRES), "")
    v.pop("Output Path")
    v.pop("Strikes Units")
    params["values"] = {**v, **(params.get("values") or {})}
    return params


def _body(h, p, values, test_output):
    nj.add_band_inputs(h, values)
    ids = nj.add_typed_inputs(h, STRIKE_SPECS, values)
    out_var = nj.path_variable(h, "Output Path", test_output)
    with h.section("Band"):
        band = nj.add_profiled_band(h)
    with h.section("Strikes"):
        pts = h.add("Strike Centres", "import_points<file_path,unit_length_enum>", mask="import_points", must=[["import_points"]])
        h.wire(ids["Strikes Path"], pts, [h.input_of_type(pts, "file_path")])
        nj.enum_input(h, "Strikes Units", "unit_length_enum", pts, "Units")
        h.comment(pts, "Python's strike centres (x,y,z in mm, ring frame); Units is the notebook input Strikes Units (1 = mm).")
        balls = h.add("Strikes", nj.SPHERE, mask="sphere", must=[["sphere<point,real>"], ["sphere", "point", "real"]])
        h.wire(pts, balls, nj.CENTRE)
        h.wire(ids["Strike Radius"], balls, ["Radius"])
        h.comment(balls, "One Sphere on the whole list: nTop makes one per point (measured, points_probe) - the hammer's face at every strike.")
        united = h.add("Strikes United", mask="union", must=nj.UNION)
        h.wire(balls, united, nj.BODIES)
        strikes = h.wrap_var("Strikes Body", united)
    with h.section("Struck"):
        struck = h.subtract("Struck", band, [strikes],
                            comment="The strikes cut after the opening: the ridges between them stay crisp, as a hammer leaves them.")
        body = h.wrap_var("Struck Band", struck)
        integ, _mesh, export = nj.add_measure_mesh_export(h, body, out_var, h.blocks["Mesh Tolerance"])
    return integ, export


def build(notebook, params: dict | None = None) -> dict:
    """Entry point for `api build ring_texture`."""
    return nj.standard_build(notebook, params, DEFAULTS, _body, "ring_texture")
