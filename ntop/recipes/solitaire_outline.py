"""`ntop/notebooks/solitaire_outline.ntop` - a PEAR (or other fancy outline) in an outline_head on a
profiled band, gothic cathedral arches with milgrain, optional engraving. The body is
ntopjewel.nb_solitaire (shared with solitaire.py, the round-stone notebook).

    python -m ntopjewel api build stone_seat ; python -m ntopjewel api build outline_head    # the blocks, first
    python -m ntopjewel api build solitaire_outline                                         # nTop open, Python Console open
    python -m ntopjewel solitaire --size 4.5 --shape pear --length 12.3 --stone-width 8.9 --stone-depth 4.6 --engrave Makena

It embeds copies of both blocks: rebuild it after either block changes.
"""
from __future__ import annotations

from pathlib import Path

from ntopjewel import nb_solitaire as ns

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
KIND = "outline"
SPECS = ns.specs(KIND)
INPUT_ORDER = ns.input_order(KIND)


def _spec():
    from ntopjewel import band, gems, heads, solitaire
    return solitaire.SolitaireSpec(band.BandSpec(size=4.5, profile="court", mesh_tolerance_mm=0.05),
                                   heads.OutlineHeadSpec(gems.StoneSpec("pear", 12.3, 8.9, 4.6, material="glass")),
                                   text="Makena")


DEFAULTS = {
    "values": {},                       # prepare() (laptop side) computes them
    "input_order": INPUT_ORDER,
    "test_output": str(REPO / "out" / "api" / "solitaire_outline_test.stl"),
    "seat_block": str(REPO / "ntop" / "blocks" / "stone_seat.ntop"),
    "head_block": str(REPO / "ntop" / "blocks" / "outline_head.ntop"),
    "save_to": str(REPO / "ntop" / "notebooks" / "solitaire_outline.ntop"),
    "recipe_to": str(REPO / "ntop" / "recipes" / "solitaire_outline.recipe.json"),
    "pause": False,                     # embeds blocks: no paused updates
    "show": ["Ring", "Ring Body"],      # the GUI shows the finished ring only
    "lazy_ok": True,                    # nTopCL (`solitaire` command) is the test
    "fresh": True,
    "wait_s": 240,
    "volume_hint": "US4.5 court, 12.3 x 8.9 pear, 5 prongs, arch milgrain, Makena inside: 324.5 mm³ (solitaire.design_mesh)",
}


def prepare(params: dict, work_dir: Path) -> dict:
    return ns.prepare(_spec(), params, REPO / "out" / "api", "solitaire_outline")


def build(notebook, params: dict | None = None) -> dict:
    return ns.build(notebook, params or {}, DEFAULTS, KIND)
