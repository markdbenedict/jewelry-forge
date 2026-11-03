"""multistone.ntop's input layout, importable inside nTop's Python Console (standard library and
nb_jewel only: nTop's Python has no yaml, trimesh or shapely - an `api build multistone` that imported
ntopjewel.multistone at the top failed there with "No module named 'yaml'", 2026-11-03)."""
from __future__ import annotations

from .nb_jewel import SLOT_NAMES

SLOTS = 5
SLOT_FIELDS = [("Seat Path", "path"), ("Prongs Path", "path"), ("Rail Offset", "mm"), ("Upper Rail Bottom", "mm"),
               ("Upper Rail Top", "mm"), ("Lower Rail Bottom", "mm"), ("Lower Rail Top", "mm"),
               ("Spin", "deg"), ("Pivot X", "mm"), ("Pivot Z", "mm"), ("Turn", "deg")]
COMMON = [("Clearance", "mm"), ("Head Blend", "mm"), ("Shank Blend", "mm")]


def slot_input(name: str, k: int) -> str:
    """The notebook input of slot k (0-based): `Seat Path`, `Seat Path 2` ..."""
    return name if k == 0 else f"{name} {k + 1}"


def specs() -> list[tuple[str, str]]:
    """Every notebook input but the output, in order (the catalog's order)."""
    shank_in = [(n, "path") for n in SLOT_NAMES] + [("Wrap Length", "mm"), ("Edge Round", "mm"),
                                                    ("Edge Round Inward", "mm"), ("Mesh Tolerance", "mm")]
    return shank_in + COMMON + [(slot_input(n, k), t) for k in range(SLOTS) for n, t in SLOT_FIELDS]


def input_order() -> list[str]:
    return [n for n, _ in specs()] + ["Output Path"]
