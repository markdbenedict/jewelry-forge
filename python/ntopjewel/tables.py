"""Jewelry reference tables: ring sizes, metals, print/cast floors, casting defaults.

Every number here is either a geometric identity (ring sizes) or a *default to calibrate*
(walls, shrinkage). Calibrated values are changed here, with a dated note, never in a
notebook or a skill.
"""
from __future__ import annotations

import math
import re
import string
from dataclasses import dataclass

# --------------------------------------------------------------------------- ring sizes
US_SIZE_INTERCEPT_MM = 11.63     # inner diameter of US size 0
US_SIZE_STEP_MM = 0.8128         # per whole US size (1/2 size = 0.4064 mm)
UK_A_INNER_DIAMETER_MM = 12.04   # UK/AU letter A; half of a US step per letter
UK_STEP_MM = 0.4064


def us_size_to_inner_diameter_mm(size: float) -> float:
    """US/Canada ring size -> inner diameter in mm (quarter sizes allowed)."""
    return US_SIZE_INTERCEPT_MM + US_SIZE_STEP_MM * float(size)


def inner_diameter_mm_to_us_size(d: float) -> float:
    return (float(d) - US_SIZE_INTERCEPT_MM) / US_SIZE_STEP_MM


def iso_circumference_to_inner_diameter_mm(circumference_mm: float) -> float:
    """ISO 8653 / EU / 'French' sizes are the inner circumference in mm."""
    return float(circumference_mm) / math.pi


def inner_diameter_mm_to_iso_circumference(d: float) -> float:
    return float(d) * math.pi


def uk_size_to_inner_diameter_mm(letter: str) -> float:
    """UK/Australian letter sizes A..Z, with '1/2' suffix allowed ('L 1/2' or 'L.5').

    Approximation: letters step by half a US size from A = 12.04 mm. Good to ~0.05 mm.
    """
    s = letter.strip().upper().replace(" ", "")
    m = re.fullmatch(r"([A-Z])(1/2|\.5|HALF)?", s)
    if not m:
        raise ValueError(f"UK size must be a letter A..Z with optional 1/2, got {letter!r}")
    idx = string.ascii_uppercase.index(m.group(1))
    half = 0.5 if m.group(2) else 0.0
    return UK_A_INNER_DIAMETER_MM + UK_STEP_MM * (idx + half)


def inner_diameter_mm(size: float | str, system: str = "US") -> float:
    """Inner diameter for a size in any supported system: US, UK, ISO (EU circumference), MM."""
    system = system.upper()
    if system in ("US", "USA", "CA"):
        return us_size_to_inner_diameter_mm(float(size))
    if system in ("UK", "AU", "AUS"):
        return uk_size_to_inner_diameter_mm(str(size))
    if system in ("ISO", "EU", "FR", "CIRC"):
        return iso_circumference_to_inner_diameter_mm(float(size))
    if system in ("MM", "ID"):
        return float(size)
    raise ValueError(f"unknown ring size system {system!r}")


def size_label(size: float | str, system: str = "US") -> str:
    """File-name friendly label: US6, US6.5, UKL, ISO52, ID16.5."""
    system = system.upper()
    if system in ("US", "USA", "CA"):
        f = float(size)
        return "US" + (f"{int(f)}" if f.is_integer() else f"{f:g}")
    if system in ("UK", "AU", "AUS"):
        return "UK" + str(size).replace(" ", "").replace("1/2", "half")
    if system in ("ISO", "EU", "FR", "CIRC"):
        return f"ISO{float(size):g}"
    return f"ID{float(size):g}"


# --------------------------------------------------------------------------- metals
@dataclass(frozen=True)
class Metal:
    key: str
    name: str
    density_g_cm3: float      # approximate; alloys vary by supplier
    linear_shrink_pct: float  # casting shrink default, model -> cast (to calibrate)
    min_wall_mm: float        # practical floor for a cast wall in this metal


METALS: dict[str, Metal] = {
    "resin":       Metal("resin", "castable resin (print)", 1.15, 0.0, 0.5),
    "sterling":    Metal("sterling", "sterling silver 925", 10.36, 1.7, 0.6),
    "fine_silver": Metal("fine_silver", "fine silver 999", 10.49, 1.7, 0.6),
    "10k_yellow":  Metal("10k_yellow", "10k yellow gold", 11.6, 1.4, 0.5),
    "14k_yellow":  Metal("14k_yellow", "14k yellow gold", 13.1, 1.4, 0.5),
    "14k_white":   Metal("14k_white", "14k white gold", 12.6, 1.4, 0.5),
    "18k_yellow":  Metal("18k_yellow", "18k yellow gold", 15.6, 1.4, 0.5),
    "18k_white":   Metal("18k_white", "18k white gold", 14.9, 1.4, 0.5),
    "platinum":    Metal("platinum", "platinum 950", 20.7, 1.0, 0.5),
    "palladium":   Metal("palladium", "palladium 950", 12.0, 1.2, 0.5),
    "bronze":      Metal("bronze", "jewelers bronze", 8.8, 1.5, 0.7),
    "brass":       Metal("brass", "brass", 8.5, 1.5, 0.7),
}
DEFAULT_WEIGHT_METALS = ("sterling", "14k_yellow", "18k_yellow", "platinum")


def weight_g(volume_mm3: float, metal: str | Metal) -> float:
    m = METALS[metal] if isinstance(metal, str) else metal
    return float(volume_mm3) * m.density_g_cm3 / 1000.0


def weights_g(volume_mm3: float, metals=DEFAULT_WEIGHT_METALS) -> dict[str, float]:
    return {k: round(weight_g(volume_mm3, k), 2) for k in metals}


# --------------------------------------------------------------------------- floors
# Printing and casting floors (mm). Source: Formlabs jewelry guidance used for the pear
# ring, plus bench practice. Replace with measured values; keep the dated note.
FLOORS = {
    "wall_marginal": 0.50,   # prints, may not fill in casting
    "wall_good": 0.75,       # safe wall for cast sterling/gold
    "prong_tip_dia": 0.80,
    "bead_dia": 0.50,        # milgrain / bead-set beads
    "engrave_depth": 0.25,
    "engrave_stroke": 0.30,
    "link_clearance": 0.35,  # moving chain links printed assembled
    "band_min_thickness": 1.0,
    "band_min_width": 1.5,
}

# Casting defaults (to calibrate on the first two casts; see the development plan).
CASTING = {
    "ring_sprue_dia_mm": (2.5, 3.5),
    "main_sprue_dia_mm": (6.0, 10.0),
    "feed_angle_deg": (45.0, 60.0),
    "part_spacing_mm": 6.0,
    "flask_wall_clearance_mm": 6.0,
    "investment_above_top_mm": 12.0,
    "neck_blend_mm": (0.5, 1.0),
    "cast_ring_size_offset": 0.0,   # measured: cast size - model size (fill in after cast #1)
}


# --------------------------------------------------------------------------- geometry
def torus_for_sagitta(chord_mm: float, sagitta_mm: float) -> tuple[float, float]:
    """Tube radius r and the offset of its centre for a circular arc with the given chord
    and sagitta (depth at mid-chord). Used for comfort-fit bores and domed outer profiles:

      band of width W, dome d  -> intersect with a torus of tube radius r_d = (W²/4 + d²)/(2d)
                                  and major radius R_out - r_d + d ... see band.py
    Returns (r, r - sagitta).
    """
    if sagitta_mm <= 0:
        raise ValueError("sagitta must be > 0")
    r = (chord_mm ** 2 / 4.0 + sagitta_mm ** 2) / (2.0 * sagitta_mm)
    return r, r - sagitta_mm


def shrink_scale(metal: str | Metal, extra_pct: float = 0.0) -> float:
    """Linear scale factor to apply to a model so the cast comes out at size."""
    m = METALS[metal] if isinstance(metal, str) else metal
    return 1.0 + (m.linear_shrink_pct + extra_pct) / 100.0
