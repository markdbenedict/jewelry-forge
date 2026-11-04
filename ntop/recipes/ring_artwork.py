"""Build `ring_artwork.ntop` through nTop's Notebook API: a band with artwork in relief in sunk panels on
its faces - Phase 3 step 5 (ntopjewel.artwork; the Seraphine Celtic ring's leaf rows and vine scroll).

    Shank Path .. Shank Path 4  -> the band exactly as ring_shank.ntop builds it (nj.add_wrapped_shank: each bar
                                   imported, opened by the edge round on its own, united, wrapped round Z) = Shank Body
    Cut Path                    -> Import Mesh -> Implicit from Mesh: every panel's channel (a box the channel's width
                                   from its floor out past the face, over the panel's arc; disjoint bodies)
    Relief Path                 -> Import Mesh -> Implicit from Mesh: the motifs (one body per leaf or scroll, each
                                   plugged into the channel floor; disjoint)
    Ring                        = (Shank Body − cuts) ∪ relief: the band is opened first, so the channel edges stay
                                   crisp and the relief is never rounded
                               -> Volume Integral of 1 (Output "Volume"), Mesh (Mesh Tolerance), Export Mesh

Python lays the motifs out in each panel's own frame, builds them in the bar frame and wraps them
(artwork.ArtworkSpec); the notebook has no arithmetic.

Run:  python -m ntopjewel api build ring_artwork      (nTop open, View > Python Console open, in the foreground)
      python -m ntopjewel artwork --size 6 --sides leaves --outer vine
"""
from __future__ import annotations

from pathlib import Path

from ntopjewel import nb_jewel as nj
from ntopjewel.nb_jewel import SLOT_NAMES

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
TEST_DIR = REPO / "out" / "api"
TEST_STEM = "ring_artwork_test"

SPECS = nj.SHANK_SPECS + [("Cut Path", "path"), ("Relief Path", "path")]
INPUT_ORDER = nj.input_order(SPECS)


def _spec():
    from ntopjewel import artwork, band, shank
    b = band.BandSpec(size=6, width_mm=2.8, thickness_mm=2.0, profile="flat", mesh_tolerance_mm=0.05)
    return artwork.ArtworkSpec(shank.ShankSpec(b), artwork.seraphine_panels(25.0, 60.0))


DEFAULTS = {
    "values": {},
    "input_order": INPUT_ORDER,
    "test_output": str(REPO / "out" / "api" / "ring_artwork_test.stl"),
    "save_to": str(REPO / "ntop" / "notebooks" / "ring_artwork.ntop"),
    "recipe_to": str(REPO / "ntop" / "recipes" / "ring_artwork.recipe.json"),
    "pause": False,                     # embeds the open_bar block: no paused updates
    "fresh": True,
    "wait_s": 300,
    "show": ["Ring Body"],
    "volume_hint": "US6 flat 2.8 x 2.0 band, leaf rows on both sides and a vine outside from 25° to 60°: see `artwork --dry-run`",
}


def prepare(params: dict, work_dir: Path) -> dict:
    """Laptop side: the test band's bars, cutters and relief, and every input value."""
    from ntopjewel import shank
    spec = _spec()
    TEST_DIR.mkdir(parents=True, exist_ok=True)
    bars = shank.write_bars(spec.shank, TEST_DIR, TEST_STEM)
    cut, relief = spec.write_layers(TEST_DIR, TEST_STEM)
    v = spec.notebook_inputs(bars, cut, relief)
    v.pop("Output Path")
    params["values"] = {**v, **(params.get("values") or {})}
    return params


def _body(h, p, values, test_output):
    ids = nj.add_typed_inputs(h, SPECS, values)
    out_var = nj.path_variable(h, "Output Path", test_output)
    with h.section("Shank"):
        shank_body = h.wrap_var("Shank Body", nj.add_wrapped_shank(h, [ids[n] for n in SLOT_NAMES], ids["Wrap Length"],
                                                                   ids["Edge Round Inward"], ids["Edge Round"], ids["Mesh Tolerance"],
                                                                   opener=h.embed_block(p["open_bar_block"])))
    with h.section("Artwork"):
        cuts = h.import_body("Panel Cuts", ids["Cut Path"])
        relief = h.import_body("Relief", ids["Relief Path"])
        carved = h.subtract("Carved", shank_body, [cuts], comment="The panel channels, cut from the opened band: their edges stay crisp.")
        ring = h.union("Ring", [carved, relief], comment="The motifs standing in the channels, never rounded.")
    with h.section("Result"):
        out = h.wrap_var("Ring Body", ring)
        integ, _mesh, export = nj.add_measure_mesh_export(h, out, out_var, ids["Mesh Tolerance"])
    return integ, export


def build(notebook, params: dict | None = None) -> dict:
    """Entry point for `api build ring_artwork`; see the module docstring."""
    return nj.standard_build(notebook, params, DEFAULTS, _body, "ring_artwork", blocks=("open_bar_block",))
