"""Phase 2 gate notebook: `ntop/notebooks/solitaire.ntop` - a ROUND stone in a prong_head on a profiled
band, gothic cathedral arches with milgrain, optional engraving. The body is ntopjewel.nb_solitaire
(shared with solitaire_outline.py, the fancy-shape notebook).

    python -m ntopjewel api build stone_seat ; python -m ntopjewel api build prong_head   # the blocks, first
    python -m ntopjewel api build solitaire                                              # nTop open, Python Console open
    python -m ntopjewel solitaire --size 6 --length 6.5 --prongs 6                      # then run and gate a ring

It embeds copies of both blocks: rebuild it after either block changes.
"""
from __future__ import annotations

from pathlib import Path

from ntopjewel import nb_solitaire as ns

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
KIND = "round"
SPECS = ns.specs(KIND)
INPUT_ORDER = ns.input_order(KIND)


def _spec():
    from ntopjewel import band, gems, heads, solitaire
    return solitaire.SolitaireSpec(band.BandSpec(size=6, profile="court", mesh_tolerance_mm=0.05),
                                   heads.HeadSpec(gems.StoneSpec("round", 6.5), prongs=6))


DEFAULTS = {
    "values": {},                       # prepare() (laptop side) computes them
    "input_order": INPUT_ORDER,
    "test_output": str(REPO / "out" / "api" / "solitaire_test.stl"),
    "seat_block": str(REPO / "ntop" / "blocks" / "stone_seat.ntop"),
    "head_block": str(REPO / "ntop" / "blocks" / "prong_head.ntop"),
    "save_to": str(REPO / "ntop" / "notebooks" / "solitaire.ntop"),
    "recipe_to": str(REPO / "ntop" / "recipes" / "solitaire.recipe.json"),
    "pause": False,                     # embeds blocks: no paused updates
    "show": ["Ring", "Ring Body"],      # the GUI shows the finished ring only
    "lazy_ok": True,                    # nTopCL (`solitaire` command) is the test
    "fresh": True,
    "wait_s": 240,
    "volume_hint": "US6 court, 6.5 mm round, 6 prongs, arch milgrain: 287 mm³ (solitaire.design_mesh)",
}


def prepare(params: dict, work_dir: Path) -> dict:
    return ns.prepare(_spec(), params, REPO / "out" / "api", "solitaire")


def build(notebook, params: dict | None = None) -> dict:
    return ns.build(notebook, params or {}, DEFAULTS, KIND)
