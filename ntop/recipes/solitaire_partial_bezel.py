"""`ntop/notebooks/solitaire_partial_bezel.ntop` - a stone in a partial_bezel_head (two walls on its flanks, a hood over
each point) on the shank Python writes as a bar (plain or tapered: the reference ring's broad shank tapering
down), arches optional (the reference has none), optional engraving. The body is ntopjewel.nb_solitaire (shared
with the other solitaire notebooks).

    python -m ntopjewel api build stone_seat ; python -m ntopjewel api build partial_bezel_head   # the blocks, first
    python -m ntopjewel api build solitaire_partial_bezel                                        # nTop open, Python Console open
    python -m ntopjewel solitaire --partial-bezel --shape pear --length 10 --stone-width 7 --stone-depth 4.5 --no-arches ...

It embeds copies of both blocks: rebuild it after either block changes.
"""
from __future__ import annotations

from pathlib import Path

from ntopjewel import nb_solitaire as ns

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
KIND = "partial"
SPECS = ns.specs(KIND)
INPUT_ORDER = ns.input_order(KIND)


def _spec():
    from ntopjewel import band, gems, partial_bezel, solitaire
    return solitaire.SolitaireSpec(band.BandSpec(size=6, profile="court", mesh_tolerance_mm=0.05),
                                   partial_bezel.PartialBezelSpec(gems.StoneSpec("pear", 10.0, 7.0, 4.5)), cathedral=False)


DEFAULTS = {
    "values": {},                       # prepare() (laptop side) computes them
    "input_order": INPUT_ORDER,
    "test_output": str(REPO / "out" / "api" / "solitaire_partial_bezel_test.stl"),
    "seat_block": str(REPO / "ntop" / "blocks" / "stone_seat.ntop"),
    "head_block": str(REPO / "ntop" / "blocks" / "partial_bezel_head.ntop"),
    "save_to": str(REPO / "ntop" / "notebooks" / "solitaire_partial_bezel.ntop"),
    "recipe_to": str(REPO / "ntop" / "recipes" / "solitaire_partial_bezel.recipe.json"),
    "pause": False,                     # embeds blocks: no paused updates
    "show": ["Ring", "Ring Body"],      # the GUI shows the finished ring only
    "lazy_ok": True,                    # nTopCL (`solitaire` command) is the test
    "fresh": True,
    "wait_s": 240,
    "volume_hint": "US6 court, 10 x 7 pear in a partial bezel, no arches: see `solitaire --partial-bezel --dry-run`",
}


def prepare(params: dict, work_dir: Path) -> dict:
    return ns.prepare(_spec(), params, REPO / "out" / "api", "solitaire_partial_bezel")


def build(notebook, params: dict | None = None) -> dict:
    return ns.build(notebook, params or {}, DEFAULTS, KIND)
