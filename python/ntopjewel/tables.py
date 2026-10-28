"""Jewelry reference tables: ring sizes, metals, print/cast floors, casting defaults.

Ring sizes are geometric identities and live here. Every engineering number (densities,
shrinkage, wall floors, casting defaults, the sprue allowance) comes from ONE data file,
`data/jewelry_tables.json`, which Blender's `jewelry_kit.py` reads too, so the two sides can
never disagree again (2026-10-27: brass was 8.4 in Blender and 8.5 here). Each entry there
carries a `status` (default / calibrated / uncalibrated) and its source; a calibrated value is
changed in the JSON with a dated `calibration_log` entry, never in a notebook or a skill.
"""
from __future__ import annotations

import json
import math
import re
import string
from dataclasses import dataclass
from pathlib import Path

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


# --------------------------------------------------------------------------- the data file
TABLES_PATH = Path(__file__).resolve().parents[2] / "data" / "jewelry_tables.json"


def load_tables(path: Path | None = None) -> dict:
    """The shared engineering tables (see the module docstring). Raises if the file is missing:
    there is deliberately no second copy on the Python side."""
    p = Path(path) if path else TABLES_PATH
    if not p.exists():
        raise FileNotFoundError(f"engineering tables not found: {p} (the repo's data/jewelry_tables.json)")
    data = json.loads(p.read_text(encoding="utf-8"))
    if data.get("schema") != 1:
        raise ValueError(f"{p}: unknown tables schema {data.get('schema')!r}")
    return data


TABLES = load_tables()


# --------------------------------------------------------------------------- metals
@dataclass(frozen=True)
class Metal:
    key: str
    name: str
    density_g_cm3: float      # approximate; alloys vary by supplier
    linear_shrink_pct: float  # casting shrink default, model -> cast (to calibrate)
    min_wall_mm: float        # practical floor for a cast wall in this metal
    status: str = "default"   # default | calibrated | uncalibrated (data/jewelry_tables.json)
    source: str = ""


METALS: dict[str, Metal] = {
    key: Metal(key, m["name"], float(m["density_g_cm3"]), float(m["linear_shrink_pct"]), float(m["min_wall_mm"]),
               m.get("status", "default"), m.get("source", ""))
    for key, m in TABLES["metals"].items()
}
DEFAULT_WEIGHT_METALS = tuple(TABLES["default_weight_metals"])
STONE_DENSITY_G_CM3: dict[str, float] = {k: float(v["density_g_cm3"]) for k, v in TABLES["stones"].items()}
DEFAULT_STONE = TABLES["default_stone"]
CARAT_G = 0.2


def carats(volume_mm3: float, stone: str = DEFAULT_STONE) -> float:
    """Carat weight of a stone of this volume (1 ct = 0.2 g)."""
    return float(volume_mm3) * STONE_DENSITY_G_CM3[stone] / 1000.0 / CARAT_G
SPRUE_ALLOWANCE = float(TABLES["weight"]["sprue_allowance_fraction"]["value"])   # extra metal for sprue + button


def weight_g(volume_mm3: float, metal: str | Metal) -> float:
    m = METALS[metal] if isinstance(metal, str) else metal
    return float(volume_mm3) * m.density_g_cm3 / 1000.0


def weights_g(volume_mm3: float, metals=DEFAULT_WEIGHT_METALS) -> dict[str, float]:
    return {k: round(weight_g(volume_mm3, k), 2) for k in metals}


# --------------------------------------------------------------------------- floors
# Printing and casting floors (mm): wall_marginal (prints, may not fill in casting), wall_good
# (safe for cast sterling/gold), prong_tip_dia, bead_dia, engrave_depth, engrave_stroke,
# link_clearance (chain links printed assembled), band_min_thickness, band_min_width.
FLOORS: dict[str, float] = {k: float(v["mm"]) for k, v in TABLES["floors"].items()}
FLOOR_INFO: dict[str, dict] = {k: {"status": v.get("status", "default"), "source": v.get("source", "")}
                               for k, v in TABLES["floors"].items()}

# Casting defaults (to calibrate on the first two casts; see docs/plan.md). A range is a tuple.
CASTING: dict = {k: (tuple(v["value"]) if isinstance(v["value"], list) else v["value"])
                 for k, v in TABLES["casting"].items()}
CASTING_INFO: dict[str, dict] = {k: {"status": v.get("status", "default"), "source": v.get("source", "")}
                                 for k, v in TABLES["casting"].items()}


def uncalibrated() -> list[str]:
    """Entries still marked `uncalibrated` or `default` - what the first casts must measure."""
    out = [f"metal {k}: {m.status}" for k, m in METALS.items() if m.status != "calibrated"]
    out += [f"floor {k}: {v['status']}" for k, v in FLOOR_INFO.items() if v["status"] != "calibrated"]
    out += [f"casting {k}: {v['status']}" for k, v in CASTING_INFO.items() if v["status"] != "calibrated"]
    return out


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
