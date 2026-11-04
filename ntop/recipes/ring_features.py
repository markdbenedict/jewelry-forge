"""Build `ring_features.ntop` through nTop's Notebook API: the profiled band plus milgrain,
a channel groove and a wrapped engraving - Phase 1, step 2.

    the 11 band inputs (see band_profile.py)  ->  Band Body
    + Milgrain : two spheres (z = ±Bead Z at radius Bead Ring Radius) -> union -> Polar Array
                 (Bead Count copies, Bead Spacing apart, about +Z) -> union with the band
    - Groove   : a torus (ring radius, tube radius, centre z) subtracted
    - Engraving: Import Mesh (Engraving Path) -> Implicit from Mesh -> Remap Cylindrical Body
                 (Y mapping length = Engraving Wrap Length) -> subtracted
    -> Ring Body -> Volume Integral of 1 (Output "Volume"), Mesh, Export Mesh (Output Path)

One notebook, no conditionals: a feature is switched off by its numbers (a tiny bead inside
the band, a groove torus 10 mm outside the ring, a speck of an engraving mesh far from it).
`ntopjewel.features.RingSpec` works those numbers out; `ntopjewel.engrave` writes the STL the
Engraving Path points at (the test build gets a dummy one from `prepare()`).

Run:  python -m ntopjewel api build ring_features --scratch     (then templates / ring --notebook)
"""
from __future__ import annotations

from pathlib import Path

from ntopjewel import nb_jewel as nj

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]

# court US6 band + milgrain (87 beads of r 0.3 on both edges) + a 0.6 x 0.25 mm channel groove
# + an inside engraving placeholder: `python -m ntopjewel ring --size 6 --profile court --milgrain --groove --dry-run`
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
    "Bead Radius": 0.3,
    "Bead Ring Radius": 9.1834,
    "Bead Z": 1.955,
    "Bead Z Minus": -1.955,
    "Bead Spacing": 4.1379,          # degrees = 360 / Bead Count
    "Bead Count": 87,
    "Groove Ring Radius": 9.6034,    # outer radius + tube - depth: the tube cuts `depth` into the surface
    "Groove Tube Radius": 0.3,
    "Groove Z": 0.0,
    "Engraving Path": str(REPO / "out" / "api" / "ring_features_test_engraving.stl"),
    "Engraving Wrap Length": 51.8577,   # 2π x bore radius: undistorted on the inside
}
FEATURE_REALS = ["Bead Radius", "Bead Ring Radius", "Bead Z", "Bead Z Minus",
                 "Groove Ring Radius", "Groove Tube Radius", "Groove Z", "Engraving Wrap Length"]
INPUT_ORDER = list(TEST_VALUES) + ["Output Path"]
assert INPUT_ORDER[:11] == nj.BAND_INPUTS

DEFAULTS = {
    "values": TEST_VALUES,
    "input_order": INPUT_ORDER,
    "test_output": str(REPO / "out" / "api" / "ring_features_test.stl"),
    "save_to": str(REPO / "ntop" / "notebooks" / "ring_features.ntop"),
    "recipe_to": str(REPO / "ntop" / "recipes" / "ring_features.recipe.json"),
    "pause": True,
    "fresh": True,
    "wait_s": 180,
    "volume_hint": "court US6 band (244 mm³) + 87 x 2 beads - a 0.6 x 0.25 mm groove: about 249 mm³ "
                   "(RingSpec.design_volume_mm3)",
}


def prepare(params: dict, work_dir: Path) -> dict:
    """Laptop side, before the script is sent to nTop: write the test engraving STL the
    notebook will import (a no-op speck unless `--param text=...`). Needs trimesh, so it
    never runs inside nTop."""
    from ntopjewel import engrave
    p = {**DEFAULTS, **params}
    values = {**TEST_VALUES, **(p.get("values") or {})}
    path = Path(values["Engraving Path"])
    text = params.get("text")
    info = engrave.write_engraving(path, text, height_mm=1.6, depth_mm=0.3, radius_mm=values["Bore Radius"], side="inside")
    params.setdefault("values", {})["Engraving Path"] = str(path)
    params["values"]["Engraving Wrap Length"] = round(info["wrap_length_mm"], 4)
    return params


def _body(h, p, values, test_output):
    nj.add_band_inputs(h, values)
    for name in FEATURE_REALS:
        h.real_var(name, float(values[name]), "mm")
    nj.angle_variable(h, "Bead Spacing", float(values["Bead Spacing"]))
    nj.integer_variable(h, "Bead Count", int(values["Bead Count"]))
    engr_path = nj.path_variable(h, "Engraving Path", str(values["Engraving Path"]))
    out_var = nj.path_variable(h, "Output Path", test_output)
    v = h.blocks
    with h.section("Band"):
        band = nj.add_profiled_band(h)
    with h.section("Milgrain"):                                  # a bead on each edge, arrayed round the axis
        beads = []
        for label, zvar in (("Bead+", "Bead Z"), ("Bead-", "Bead Z Minus")):
            pt = nj.point_block(h, f"{label} P", x_var=v["Bead Ring Radius"], z_var=v[zvar])
            beads.append(h.sphere(label, pt, v["Bead Radius"]))
        pair = h.union("Bead Pair", beads)
        milgrain = h.polar_array("Milgrain", pair, v["Bead Spacing"], v["Bead Count"], nj.z_axis(h))
        beaded = h.union("Beaded", [band, milgrain])
    with h.section("Groove"):                                    # a torus subtracted
        gp = nj.point_block(h, "Groove P", z_var=v["Groove Z"])
        gt = h.torus("Groove Torus", v["Groove Ring Radius"], v["Groove Tube Radius"], centre=gp)
        grooved = h.subtract("Grooved", beaded, [gt])
    with h.section("Engraving"):                                 # imported mesh -> implicit -> wrapped round the ring -> subtracted
        text = h.import_body("Engraving Body", engr_path)
        wrapped = h.remap_cylindrical("Engraving Wrapped", text, v["Engraving Wrap Length"])
        engraved = h.subtract("Engraved", grooved, [wrapped], comment="The text wrapped round the ring and cut in, last.")
    with h.section("Result"):
        ring = h.wrap_var("Ring Body", engraved)
        integ, _mesh, export = nj.add_measure_mesh_export(h, ring, out_var, v["Mesh Tolerance"])
    return integ, export


def build(notebook, params: dict | None = None) -> dict:
    """Entry point for `api build ring_features`; see the module docstring."""
    return nj.run_build(notebook, params, DEFAULTS, _body)
