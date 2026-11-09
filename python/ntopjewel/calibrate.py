"""The calibration intake (9 Nov 2026): a test-print round's filled-in measurement sheet read back and turned into the
tables' numbers.

Every reading on the sheet (`testprint._sheet`: a few readings per row, three columns) is set against the part AS
BUILT - the gate's measurement of the STL that was printed (the delivery's manifest), the design where the gate has no
figure - and all of a round's readings are fitted together to the printer's two numbers:

    measured = built x (1 - s) + 2 n delta

s the resin's shrink (a scale of the whole part), delta its BLOOM (every surface grows past the layer's outline by the
light that cures beyond it; n = +1 for a distance across metal - an outer diameter, a width, a height -, -1 across a
bore, whose walls grow inward). A bore reading and a reading across metal tell the two apart; without a bore reading
they cannot be, and nothing is written. A mandrel reading is a size: it becomes a bore diameter through the US formula
and weighs less than a caliper. Least squares gives s and delta with their uncertainty and a residual per reading; a
reading that stands out (a slipped caliper) is named and the fit repeated without it. The weights give the resin's
density, the printed volume being built x (1 - s)^3 plus the bloom over the surface.

What comes out: `calibration.md` and `calibration.json` in the round's folder (every reading, the fit, the answers
about supports and features as given), and - unless --dry-run, and only when the fit is sound - the tables
(`data/jewelry_tables.json`): settings.resin_shrink_pct and settings.print_bloom_mm calibrated, metals.resin's density
calibrated when the scale was fine enough, each with a dated calibration_log entry that keeps the previous value; and
an `evidence` entry per part printed, naming the support settings it printed with and what the sheet says of them
(swelling, clean breaks, sagging) - the print-prep defaults are not calibrated by one print, but every print bears on
them. The intake never touches a notebook, a skill or a script.
"""
from __future__ import annotations

import datetime
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import tables, testprint

BLANK = "____"
MANDREL_WEIGHT = 0.3             # a mandrel reads to a quarter size (0.2 mm): its reading counts this much of a caliper's
OUTLIER_MM = 0.05                # a reading this far off the fit (or 3 x the RMS, if more) is a slipped caliper: refit without it
MANDREL_DISAGREE_MM = 0.25       # a mandrel reading this far from the calipers' fit (more than a quarter size) is noted
RMS_SOUND_MM = 0.03              # a fit whose residuals exceed this is not written to the tables
SHRINK_SOUND_PCT = 3.0           # ... nor a shrink beyond this (castable resins shrink a per cent or two)
BLOOM_SOUND_MM = (-0.02, 0.15)   # ... nor a bloom outside this
DENSITY_SOUND_FRACTION = 0.05    # the scale's resolution must be within this of the part's weight for a density

# what a sheet row measures: the sign for the bloom (+1 across metal, -1 across a bore) and how the built value is found
MEASURES = {
    "bore": (-1, "the bore, inside jaws"),
    "mandrel": (-1, "the mandrel size it stops at (a bore diameter through the US formula)"),
    "outer": (+1, "the outer diameter"),
    "over_beads": (+1, "the width over the bead rows"),
    "width": (+1, "the band's width (at the head of a shaped shank)"),
    "width_bottom": (+1, "the band's width at the bottom of a shaped shank"),
    "height": (+1, "the overall height, the bottom of the band to the prong tips"),
    "weight": (0, "the weight"),
}


# ============================================================================ the sheet
@dataclass
class PartSheet:
    index: int
    title: str
    key: str | None              # testprint.PARTS key, when known
    stem: str | None
    design: dict                 # the Design: line's numbers
    printed: str                 # the Printed: line
    rows: dict                   # label -> [readings]  (only rows with a number)
    lines: list                  # the feature / support bullets as filled in
    unanswered: int              # bullets still holding a blank


@dataclass
class Sheet:
    path: Path
    size: str | None
    settings: dict               # the print settings as filled in (strings)
    parts: list                  # [PartSheet]


_NUM = re.compile(r"-?\d+(?:[.,]\d+)?")
_FRACTION = {"1/4": 0.25, "1/2": 0.5, "3/4": 0.75, "¼": 0.25, "½": 0.5, "¾": 0.75}


def parse_number(cell: str) -> float | None:
    """A reading from a table cell: '15.27', '15,27 mm', '4 1/2', '4½'; None for a blank or words."""
    s = cell.strip().replace("mm", "").replace("g", "").strip()
    if not s or BLANK in s:
        return None
    for frac, v in _FRACTION.items():
        if s.endswith(frac):
            head = s[: -len(frac)].strip()
            m = _NUM.fullmatch(head) if head else None
            if head == "":
                return v
            if m:
                return float(head.replace(",", ".")) + v
    m = _NUM.search(s)
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", "."))
    except ValueError:
        return None


def parse_design(line: str) -> dict:
    """The numbers testprint._design_line wrote: bore, width, thickness, outer, over_beads, width_bottom, thickness_bottom,
    extents, volume, resin_g (whichever the line has)."""
    d = {}
    for key, pat in (("bore", r"bore Ø\s*([\d.]+)"), ("over_beads", r"\(([\d.]+) over the beads\)"),
                     ("thickness", r"thickness\s*([\d.]+)"), ("outer", r"outer Ø\s*([\d.]+)"),
                     ("volume", r"([\d.]+)\s*mm³"), ("resin_g", r"\(([\d.]+) g of resin\)")):
        m = re.search(pat, line)
        if m:
            d[key] = float(m.group(1))
    m = re.search(r"band ([\d.]+) wide × ([\d.]+) thick at the head, ([\d.]+) × ([\d.]+) at the bottom", line)
    if m:
        d["width"], d["thickness"], d["width_bottom"], d["thickness_bottom"] = (float(x) for x in m.groups())
    else:
        m = re.search(r"width\s*([\d.]+)", line)
        if m:
            d["width"] = float(m.group(1))
    m = re.search(r"([\d.]+) × ([\d.]+) × ([\d.]+) mm overall", line)
    if m:
        d["extents"] = [float(x) for x in m.groups()]
    return d


def _settings(lines: list[str]) -> dict:
    """The print settings bullets as filled in: whatever stands where a blank was (None where the blank still is)."""
    text = "\n".join(lines)
    out = {}
    pats = {"printer": r"Printer / resin:\s*(.+)", "layer_um": r"Layer height:\s*(\S+)\s*µm", "exposure_s": r"exposure:\s*(\S+)\s*s",
            "bottom_layers": r"bottom layers:\s*(\S+)\s*at", "bottom_s": r"bottom layers:\s*\S+\s*at\s*(\S+)\s*s",
            "as_is": r"not rotated\)\?\s*(.+)", "wash_min": r"IPA\s*(\S+)\s*min", "cure_min": r"cure:\s*(\S+)\s*min",
            "after_cure_h": r"measured\s*(\S+)\s*h after", "scale_g": r"Scale resolution:\s*(\S+)\s*g", "calipers": r"calipers:\s*(.+)"}
    for k, pat in pats.items():
        m = re.search(pat, text)
        v = m.group(1).strip() if m else None
        out[k] = None if (v is None or BLANK in v or v == "") else v
    return out


def read_sheet(path: Path) -> Sheet:
    """The measurement sheet of a round, as filled in."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    m = re.search(r"\(US ([\d.]+),", text)
    size = m.group(1) if m else None
    parts: list[PartSheet] = []
    settings: dict = {}
    section = None
    cur: dict | None = None
    titles = {p.title: p.key for p in testprint.PARTS}
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("## "):
            if cur is not None:
                parts.append(_part(cur, titles))
            cur = None
            head = line[3:].strip()
            if head.lower().startswith("print settings"):
                section = "settings"
                settings_lines: list[str] = []
            else:
                mm = re.match(r"(\d+)\.\s+(.*)", head)
                section = "part"
                cur = {"index": int(mm.group(1)) if mm else len(parts) + 1, "title": (mm.group(2) if mm else head).strip(),
                       "stem": None, "key": None, "design": {}, "printed": "", "rows": {}, "lines": []}
            continue
        if section == "settings":
            settings_lines.append(line)
            settings = _settings(settings_lines)
        elif section == "part" and cur is not None:
            if line.startswith("Part:"):
                mm = re.match(r"Part:\s*(\S+)(?:\s*\((\w+)\))?", line)
                if mm:
                    cur["stem"], cur["key"] = mm.group(1), mm.group(2)
            elif line.startswith("Design:"):
                cur["design"] = parse_design(line)
            elif line.startswith("Printed:"):
                cur["printed"] = line[len("Printed:"):].strip().rstrip(".")
            elif line.startswith("|") and not line.startswith("| ---") and not line.startswith("| Measure"):
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if cells:
                    vals = [v for v in (parse_number(c) for c in cells[1:]) if v is not None]
                    if vals:
                        cur["rows"][cells[0]] = vals
            elif line.startswith("- "):
                cur["lines"].append(line[2:].strip())
    if cur is not None:
        parts.append(_part(cur, titles))
    return Sheet(path, size, settings, parts)


def _part(cur: dict, titles: dict) -> PartSheet:
    key = cur["key"] or titles.get(cur["title"])
    unanswered = sum(1 for l in cur["lines"] if BLANK in l)
    return PartSheet(cur["index"], cur["title"], key, cur["stem"], cur["design"], cur["printed"], cur["rows"], cur["lines"], unanswered)


def stems_from_readme(folder: Path) -> list[str]:
    """The parts' stems in the order the round's README lists them (sheets before 9 Nov carry no Part: line)."""
    readme = Path(folder) / "README.md"
    if not readme.exists():
        return []
    out = []
    for line in readme.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*`([^`]+)\.supported(?:_\w+)?\.stl`", line)
        if m:
            out.append(m.group(1))
    return out


def row_key(label: str, part_key: str | None) -> str | None:
    """What a row of the sheet measures, from its label (the labels testprint writes; the common rows for every part)."""
    rows = dict(testprint.COMMON_ROWS + (testprint.WEIGHT_ROW,))
    for p in testprint.PARTS:
        if part_key is None or p.key == part_key:
            rows.update(dict(p.rows))
    if label in rows:
        return rows[label]
    low = label.lower()
    if "mandrel" in low:
        return "mandrel"
    if "bore" in low:
        return "bore"
    if "weight" in low:
        return "weight"
    if "outer" in low:
        return "outer"
    if "over the beads" in low:
        return "over_beads"
    if "height" in low:
        return "height"
    if "bottom" in low:
        return "width_bottom"
    if "width" in low:
        return "width"
    return None


# ============================================================================ the parts as built
def find_delivery(deliver_dir: Path, stem: str) -> Path | None:
    """The design's delivered folder (<Jewelry>/<project>/<stem>), whichever project it went to."""
    for man in Path(deliver_dir).glob(f"*/{stem}/manifest.json"):
        return man.parent
    return None


def built_values(design: dict, manifest: dict | None) -> dict:
    """What each measure should read if the print were exact: the gate's measurements of the STL that was printed, the
    design's numbers where the gate has none. Also volume, area, milgrain."""
    g = (manifest or {}).get("gate") or {}
    feats = (manifest or {}).get("features") or {}
    milgrain = bool(feats.get("milgrain"))
    b: dict = {}
    if g.get("inner_diameter_mm"):
        b["bore"] = float(g["inner_diameter_mm"])
    elif "bore" in design:
        b["bore"] = design["bore"]
    if "bore" in b:
        b["mandrel"] = b["bore"]
    if g.get("outer_diameter_mm"):
        b["outer"] = float(g["outer_diameter_mm"])
    elif "outer" in design:
        b["outer"] = design["outer"]
    if milgrain and g.get("width_mm"):
        b["over_beads"] = float(g["width_mm"])
    elif "over_beads" in design:
        b["over_beads"] = design["over_beads"]
    if "width" in design:
        b["width"] = design["width"]
    elif g.get("width_mm") and not milgrain:
        b["width"] = float(g["width_mm"])
    if "width_bottom" in design:
        b["width_bottom"] = design["width_bottom"]
    if design.get("extents"):
        b["height"] = design["extents"][0]
    elif g.get("extents_mm"):
        b["height"] = float(g["extents_mm"][0])
    if g.get("volume_mm3"):
        b["volume"] = float(g["volume_mm3"])
    elif "volume" in design:
        b["volume"] = design["volume"]
    if g.get("area_mm2"):
        b["area"] = float(g["area_mm2"])
    b["milgrain"] = milgrain
    return b


# ============================================================================ the fit
@dataclass
class Reading:
    part: int
    stem: str | None
    key: str
    label: str
    measured: float              # one reading, in mm (a mandrel size already a diameter)
    built: float
    sign: int
    weight: float = 1.0
    residual: float = math.nan
    outlier: bool = False


@dataclass
class Fit:
    shrink_pct: float | None = None
    shrink_pct_sd: float | None = None
    bloom_mm: float | None = None
    bloom_mm_sd: float | None = None
    rms_mm: float | None = None
    n: int = 0
    separable: bool = False
    outliers: list = field(default_factory=list)
    why_unsound: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    @property
    def sound(self) -> bool:
        return not self.why_unsound


def _solve(rs: list[Reading], separable: bool):
    w = np.array([r.weight for r in rs])
    b = np.array([r.built for r in rs])
    n = np.array([r.sign for r in rs], float)
    y = np.array([r.measured for r in rs]) - b
    A = np.column_stack([-b, 2.0 * n]) if separable else (-b)[:, None]
    Aw, yw = A * w[:, None], y * w
    x, *_ = np.linalg.lstsq(Aw, yw, rcond=None)
    res = y - A @ x
    dof = max(len(rs) - A.shape[1], 1)
    sigma2 = float(np.sum((res * w) ** 2) / dof)
    try:
        cov = sigma2 * np.linalg.inv(Aw.T @ Aw)
        sd = np.sqrt(np.maximum(np.diag(cov), 0.0))
    except np.linalg.LinAlgError:
        sd = np.full(A.shape[1], math.nan)
    fine = res[w >= 1.0] if np.any(w >= 1.0) else res                   # the calipers' scatter; a mandrel reads coarser
    return x, sd, res, math.sqrt(float(np.mean(fine ** 2)))


def fit_round(readings: list[Reading]) -> Fit:
    """Shrink and bloom from every reading of the round, the outliers dropped once."""
    f = Fit()
    rs = [r for r in readings if r.sign != 0]
    if len(rs) < 3:
        f.why_unsound.append(f"only {len(rs)} dimensional reading(s): three at least, across a bore and across metal")
        f.n = len(rs)
        return f
    signs = {r.sign for r in rs}
    f.separable = len(signs) == 2
    if not f.separable:
        f.why_unsound.append(("no reading across a bore" if -1 not in signs else "no reading across metal")
                             + ": the shrink and the bloom cannot be told apart")
    x, sd, res, rms = _solve(rs, f.separable)
    for r, e in zip(rs, res):
        r.residual = float(e)
    limit = max(OUTLIER_MM, 3.0 * rms)
    out = [r for r in rs if r.weight >= 1.0 and abs(r.residual) > limit]   # a mandrel's quarter sizes are not slips
    if out and len(rs) - len(out) >= 3:
        for r in out:
            r.outlier = True
            f.outliers.append(f"part {r.part} {r.label} {r.measured:.3f} mm ({r.residual:+.3f} off the fit)")
        kept = [r for r in rs if not r.outlier]
        x, sd, res, rms = _solve(kept, f.separable)
        for r, e in zip(kept, res):
            r.residual = float(e)
        rs = kept
    f.n = len(rs)
    f.shrink_pct, f.shrink_pct_sd = 100.0 * float(x[0]), 100.0 * float(sd[0])
    if f.separable:
        f.bloom_mm, f.bloom_mm_sd = float(x[1]), float(sd[1])
    f.rms_mm = rms
    for r in rs:
        if r.weight < 1.0 and abs(r.residual) > MANDREL_DISAGREE_MM:
            f.notes.append(f"part {r.part}: the mandrel reads {r.measured:.2f} mm where the calipers' fit says "
                           f"{r.measured - r.residual:.2f} ({r.residual:+.2f})")
    if rms > RMS_SOUND_MM:
        f.why_unsound.append(f"the readings scatter {rms:.3f} mm about the fit ({RMS_SOUND_MM:g} allowed)")
    if abs(f.shrink_pct) > SHRINK_SOUND_PCT:
        f.why_unsound.append(f"a shrink of {f.shrink_pct:.2f} % is not a resin's ({SHRINK_SOUND_PCT:g} % at most)")
    if f.bloom_mm is not None and not BLOOM_SOUND_MM[0] <= f.bloom_mm <= BLOOM_SOUND_MM[1]:
        f.why_unsound.append(f"a bloom of {f.bloom_mm:.3f} mm is outside {BLOOM_SOUND_MM[0]:g}..{BLOOM_SOUND_MM[1]:g}")
    return f


# ============================================================================ the round
@dataclass
class PartResult:
    sheet: PartSheet
    delivery: Path | None
    built: dict
    readings: list
    weight_g: float | None
    density: float | None
    density_note: str | None
    supports: dict                 # what the part printed with (manifest prep + prep.json) and what the sheet says


@dataclass
class Calibration:
    folder: Path
    sheet: Sheet
    parts: list
    fit: Fit
    density: float | None
    density_n: int
    density_note: str | None
    date: datetime.date
    applied: dict = field(default_factory=dict)      # entry -> (from, to) once written to the tables
    notes: list = field(default_factory=list)

    @property
    def measured_parts(self) -> list:
        return [p for p in self.parts if p.readings or p.weight_g is not None]

    def to_dict(self) -> dict:
        return {"folder": str(self.folder), "sheet": str(self.sheet.path), "date": self.date.isoformat(), "size": self.sheet.size,
                "settings": self.sheet.settings,
                "fit": {"shrink_pct": self.fit.shrink_pct, "shrink_pct_sd": self.fit.shrink_pct_sd, "bloom_mm": self.fit.bloom_mm,
                        "bloom_mm_sd": self.fit.bloom_mm_sd, "rms_mm": self.fit.rms_mm, "readings": self.fit.n,
                        "separable": self.fit.separable, "outliers": self.fit.outliers, "unsound": self.fit.why_unsound},
                "density_g_cm3": self.density, "density_parts": self.density_n, "density_note": self.density_note,
                "parts": [{"index": p.sheet.index, "title": p.sheet.title, "key": p.sheet.key, "stem": p.sheet.stem,
                           "delivery": str(p.delivery) if p.delivery else None, "built": p.built,
                           "readings": [{"label": r.label, "measures": r.key, "measured_mm": r.measured, "built_mm": r.built,
                                         "residual_mm": (None if math.isnan(r.residual) else round(r.residual, 4)),
                                         "outlier": r.outlier} for r in p.readings],
                           "weight_g": p.weight_g, "density_g_cm3": p.density, "density_note": p.density_note,
                           "supports": p.supports, "answers": p.sheet.lines, "unanswered": p.sheet.unanswered}
                          for p in self.parts],
                "applied": {k: {"from": v[0], "to": v[1]} for k, v in self.applied.items()}, "notes": self.notes}

    def text(self) -> str:
        """The report for the console and calibration.md."""
        f = self.fit
        lines = [f"Calibration intake: {self.folder.name} (US {self.sheet.size or '?'}), read {self.date:%d %b %Y}"]
        st = self.sheet.settings
        words = {"layer_um": "{} µm layers", "exposure_s": "{} s exposure", "bottom_layers": "{} bottom layers", "bottom_s": "at {} s",
                 "as_is": "printed as is: {}", "wash_min": "IPA {} min", "cure_min": "cure {} min", "after_cure_h": "measured {} h after",
                 "scale_g": "scale to {} g", "calipers": "calipers {}"}
        given = [words[k].format(v) for k, v in st.items() if v and k in words]
        lines.append("  print settings: " + (", ".join(given) if given else "none filled in"))
        for p in self.parts:
            tag = f"  part {p.sheet.index} ({p.sheet.key or p.sheet.title[:30]}, {p.sheet.stem or 'no stem'})"
            if not p.readings and p.weight_g is None:
                lines.append(tag + ": not measured")
                continue
            lines.append(tag + (": as built from the gate" if p.delivery else ": as built from the design line (no delivery found)"))
            by_label: dict = {}
            for r in p.readings:
                by_label.setdefault(r.label, []).append(r)
            for label, rs in by_label.items():
                vals = ", ".join(f"{r.measured:.3f}" for r in rs)
                mean = float(np.mean([r.measured for r in rs]))
                flags = " [outlier]" if any(r.outlier for r in rs) else ""
                lines.append(f"    {label}: {vals} -> mean {mean:.3f} vs built {rs[0].built:.3f} ({mean - rs[0].built:+.3f}){flags}")
            if p.weight_g is not None:
                lines.append(f"    weight {p.weight_g:.3f} g" + (f" -> {p.density:.3f} g/cm³" if p.density else "")
                             + (f" ({p.density_note})" if p.density_note else ""))
            if p.supports.get("printed_with"):
                lines.append(f"    supports: {p.supports['printed_with']}")
            for k in ("swelling", "clean_break", "nubs", "sagged"):
                if p.supports.get(k):
                    lines.append(f"      {k.replace('_', ' ')}: {p.supports[k]}")
            if p.sheet.unanswered:
                lines.append(f"    {p.sheet.unanswered} question(s) still blank")
        if f.shrink_pct is not None:
            s = f"  fit over {f.n} readings: shrink {f.shrink_pct:+.2f} % ± {f.shrink_pct_sd:.2f}"
            if f.bloom_mm is not None:
                s += f", bloom {f.bloom_mm:+.4f} mm ± {f.bloom_mm_sd:.4f}"
            s += f", residuals {f.rms_mm:.3f} mm rms"
            lines.append(s)
            if f.bloom_mm is not None and self.sheet.size:
                bore = tables.us_size_to_inner_diameter_mm(float(self.sheet.size))
                under = bore * f.shrink_pct / 100.0 + 2.0 * f.bloom_mm
                lines.append(f"  a US {self.sheet.size} bore ({bore:.2f} mm) prints {abs(under):.3f} mm {'under' if under > 0 else 'over'} size: "
                             f"--allowance {under:.2f} would compensate it")
        for o in f.outliers:
            lines.append(f"  dropped: {o}")
        for n_ in f.notes:
            lines.append(f"  note: {n_}")
        for w in f.why_unsound:
            lines.append(f"  not written: {w}")
        if self.density is not None:
            lines.append(f"  resin density {self.density:.3f} g/cm³ from {self.density_n} part(s)" + (f" ({self.density_note})" if self.density_note else ""))
        elif self.density_note:
            lines.append(f"  resin density: {self.density_note}")
        for k, (a, b) in self.applied.items():
            lines.append(f"  tables: {k} {a} -> {b}")
        lines += [f"  note: {n}" for n in self.notes]
        return "\n".join(lines)

    def verdict(self, stream=None, dry_run: bool = False) -> str:
        from . import summary
        f = self.fit
        n = len(self.measured_parts)
        if not n:
            return summary.paint(f"==> ERROR   calibrate {self.folder.name}", summary.YELLOW, stream) + ": no readings on the sheet yet"
        if f.sound and f.shrink_pct is not None:
            bits = [f"shrink {f.shrink_pct:+.2f} %", f"bloom {f.bloom_mm:+.3f} mm", f"{f.n} readings on {n} part(s)"]
            if self.density is not None:
                bits.append(f"density {self.density:.3f}")
            tail = "dry run, nothing written" if dry_run else (f"{len(self.applied)} table entr{'y' if len(self.applied) == 1 else 'ies'} updated"
                                                              if self.applied else "tables unchanged")
            return summary.paint(f"==> PASSED  calibrate {self.folder.name}", summary.GREEN, stream) + f"  ({', '.join(bits)}; {tail})"
        why = "; ".join(f.why_unsound) or "no fit"
        return summary.paint(f"==> FAILED  calibrate {self.folder.name}", summary.RED, stream) + f": {why}"


def _support_answers(lines: list[str]) -> dict:
    out: dict = {}
    for l in lines:
        m = re.search(r"swelling where they met the part\?\s*(.*?)\s{2,}Broke off clean at the tip\?\s*(.*?)\s{2,}Nubs sanded flush\?\s*(.*)$", l)
        if m:
            for k, v in zip(("swelling", "clean_break", "nubs"), m.groups()):
                out[k] = None if BLANK in v or not v.strip() else v.strip()
        m = re.search(r"marks it unsupported\?\s*(.*)$", l)
        if m:
            v = m.group(1).strip()
            out["sagged"] = None if BLANK in v or not v else v
    return out


def _printed_with(delivery: Path | None, stem: str | None) -> str | None:
    """What the part printed with, from its delivery: the prep's headline and spacing, the first contact, the hold."""
    if delivery is None or not stem:
        return None
    try:
        man = json.loads((delivery / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    prep = man.get("prep") or {}
    bits = [prep.get("orientation") or ""]
    pj = delivery / f"{stem}.prep.json"
    if pj.exists():
        try:
            doc = json.loads(pj.read_text(encoding="utf-8"))
            s = doc.get("settings") or {}
            if s.get("support_spacing_mm"):
                bits.append(f"{s['support_spacing_mm']:g} mm apart")
            if s.get("support_tip_mm"):
                bits.append(f"{s['support_tip_mm']:g} mm tips")
            un = doc.get("unsupported") or {}
            if un.get("first_contact_mm") is not None:
                bits.append(f"first contact {un['first_contact_mm']:.2f} mm up")
            for ch in doc.get("checks") or []:
                if ch.get("name") == "layers held":
                    m = re.search(r"more than ([\d.]+) mm²", ch.get("detail", ""))
                    if m:
                        bits.append(f"{m.group(1)} mm² per tip at most")
        except (OSError, ValueError):
            pass
    return ", ".join(b for b in bits if b) or None


def calibrate(folder: Path, deliver_dir: Path | None = None, today: datetime.date | None = None) -> Calibration:
    """Read the round's sheet, set every reading against the part as built, fit the round. Writes nothing."""
    folder = Path(folder)
    today = today or datetime.date.today()
    deliver_dir = Path(deliver_dir) if deliver_dir else folder.parent.parent
    sheet = read_sheet(folder / "measurements.md")
    readme_stems = stems_from_readme(folder)
    parts: list[PartResult] = []
    readings: list[Reading] = []
    for i, ps in enumerate(sheet.parts):
        if ps.stem is None and i < len(readme_stems):
            ps.stem = readme_stems[i]
        delivery = find_delivery(deliver_dir, ps.stem) if ps.stem else None
        manifest = None
        if delivery is not None:
            try:
                manifest = json.loads((delivery / "manifest.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                manifest = None
        built = built_values(ps.design, manifest)
        rs: list[Reading] = []
        weight = None
        for label, vals in ps.rows.items():
            key = row_key(label, ps.key)
            if key is None:
                continue
            if key == "weight":
                weight = float(np.mean(vals))
                continue
            if key not in built:
                continue
            sign = MEASURES[key][0]
            for v in vals:
                measured = tables.us_size_to_inner_diameter_mm(v) if key == "mandrel" else v
                rs.append(Reading(ps.index, ps.stem, key, label, float(measured), float(built[key]), sign,
                                  MANDREL_WEIGHT if key == "mandrel" else 1.0))
        readings += rs
        sup = _support_answers(ps.lines)
        sup["printed_with"] = _printed_with(delivery, ps.stem)
        parts.append(PartResult(ps, delivery, built, rs, weight, None, None, sup))
    fit = fit_round(readings)
    # the resin's density, the printed volume being the built one shrunk and grown by the bloom
    s = (fit.shrink_pct or 0.0) / 100.0 if fit.sound else 0.0        # an unsound fit's shrink is not applied to the volume
    delta = (fit.bloom_mm or 0.0) if fit.sound else 0.0
    scale_g = parse_number(sheet.settings.get("scale_g") or "") if sheet.settings.get("scale_g") else None
    dens, note_all = [], None
    for p in parts:
        if p.weight_g is None or not p.built.get("volume"):
            if p.weight_g is not None:
                p.density_note = "no built volume"
            continue
        v = p.built["volume"] * (1.0 - s) ** 3 + (p.built.get("area") or 0.0) * delta
        p.density = p.weight_g / v * 1000.0
        if scale_g is not None and scale_g > DENSITY_SOUND_FRACTION * p.weight_g:
            p.density_note = f"the scale's {scale_g:g} g is {100 * scale_g / p.weight_g:.0f} % of the part: too coarse"
        else:
            dens.append(p.density)
    density = float(np.mean(dens)) if dens else None
    if density is None and any(p.weight_g is not None for p in parts):
        note_all = "no density to trust" + (": the scale is too coarse for parts this light" if scale_g else "")
    elif density is not None and scale_g is None:
        note_all = "the scale's resolution was not given: taken as fine enough"
    return Calibration(folder, sheet, parts, fit, density, len(dens), note_all, today)


# ============================================================================ the tables
def apply(cal: Calibration, tables_path: Path | None = None) -> dict:
    """Write what the round established into the tables: shrink and bloom (when the fit is sound), the resin's density
    (when a scale fine enough weighed a part), and an evidence entry per part printed. Returns {entry: (from, to)}."""
    path = Path(tables_path) if tables_path else tables.TABLES_PATH
    doc = json.loads(path.read_text(encoding="utf-8"))
    log = doc.setdefault("calibration_log", [])
    date = cal.date.isoformat()
    applied: dict = {}
    where = f"{cal.folder.name} ({len(cal.measured_parts)} part(s) measured, {cal.fit.n} readings)"
    f = cal.fit
    if f.sound and f.shrink_pct is not None and f.bloom_mm is not None:
        for key, value, text in (("resin_shrink_pct", round(f.shrink_pct, 2),
                                  f"shrink {f.shrink_pct:+.2f} % ± {f.shrink_pct_sd:.2f}"),
                                 ("print_bloom_mm", round(f.bloom_mm, 4), f"bloom {f.bloom_mm:+.4f} mm ± {f.bloom_mm_sd:.4f}")):
            entry = doc["settings"].setdefault(key, {"value": 0.0, "status": "uncalibrated", "source": ""})
            before = entry.get("value")
            entry["value"] = value
            entry["status"] = "calibrated"
            if "calibration_log" not in (entry.get("source") or ""):
                entry["source"] = (entry.get("source") or "").rstrip(". ") + f". Calibrated {date}: see calibration_log"
            log.append({"date": date, "entry": f"settings.{key}", "from": before, "to": value, "status": "calibrated",
                        "evidence": f"{where}: {text}, fitted with the other over every reading (residuals {f.rms_mm:.3f} mm rms"
                                    + (f"; dropped {', '.join(f.outliers)}" if f.outliers else "") + "). "
                                    + _settings_text(cal.sheet.settings)})
            applied[f"settings.{key}"] = (before, value)
    if cal.density is not None:
        m = doc["metals"]["resin"]
        before = m.get("density_g_cm3")
        value = round(cal.density, 3)
        m["density_g_cm3"] = value
        m["status"] = "calibrated"
        if "calibration_log" not in (m.get("source") or ""):
            m["source"] = (m.get("source") or "").rstrip(". ") + f". Calibrated {date}: see calibration_log"
        parts = "; ".join(f"part {p.sheet.index} {p.weight_g:.3f} g over {p.built['volume']:.1f} mm³ -> {p.density:.3f}"
                          for p in cal.parts if p.density is not None and p.density_note is None)
        log.append({"date": date, "entry": "metals.resin.density_g_cm3", "from": before, "to": value, "status": "calibrated",
                    "evidence": f"{where}: {parts}; the printed volume taken as built x (1 - shrink)^3 + bloom over the surface. "
                                + _settings_text(cal.sheet.settings)})
        applied["metals.resin.density_g_cm3"] = (before, value)
    for p in cal.measured_parts:
        sup = p.supports
        said = ", ".join(f"{k.replace('_', ' ')}: {sup[k]}" for k in ("swelling", "clean_break", "nubs", "sagged") if sup.get(k))
        log.append({"date": date, "entry": "settings.print_* and support_* (evidence)", "from": None, "to": None, "status": "evidence",
                    "evidence": f"{p.sheet.stem or p.sheet.title}: printed with {sup.get('printed_with') or p.sheet.printed}"
                                + (f"; the sheet says {said}" if said else "; nothing said of the supports")
                                + (f"; readings {len(p.readings)}" if p.readings else "")})
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    cal.applied = applied
    return applied


def _settings_text(st: dict) -> str:
    bits = []
    if st.get("printer"):
        bits.append(st["printer"])
    if st.get("layer_um"):
        bits.append(f"{st['layer_um']} µm layers")
    if st.get("exposure_s"):
        bits.append(f"{st['exposure_s']} s exposure")
    if st.get("wash_min"):
        bits.append(f"IPA {st['wash_min']} min")
    if st.get("cure_min"):
        bits.append(f"cure {st['cure_min']} min")
    if st.get("after_cure_h"):
        bits.append(f"measured {st['after_cure_h']} h after")
    if st.get("as_is"):
        bits.append(f"printed as is: {st['as_is']}")
    return ("Settings: " + ", ".join(bits) + ".") if bits else "Settings not given on the sheet."


def write_round(cal: Calibration) -> tuple[Path, Path]:
    """calibration.md and calibration.json in the round's folder."""
    md = cal.folder / "calibration.md"
    js = cal.folder / "calibration.json"
    body = [f"# Calibration — {cal.folder.name}", "", "```", cal.text(), "```", "",
            "The model: measured = built × (1 − shrink) + 2 × bloom × (+1 across metal, −1 across a bore); the fit is over every "
            "reading of the round, a mandrel reading counted as a bore diameter at a third of a caliper's weight.", ""]
    md.write_text("\n".join(body), encoding="utf-8")
    js.write_text(json.dumps(cal.to_dict(), indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return md, js


def newest_round(deliver_dir: Path) -> Path | None:
    """The latest round folder (ISO dates sort) whose sheet holds a reading - the one being filled in - else the latest
    with a sheet at all."""
    root = Path(deliver_dir) / testprint.FOLDER
    if not root.exists():
        return None
    with_sheet = [d for d in sorted((p for p in root.iterdir() if p.is_dir()), reverse=True) if (d / "measurements.md").exists()]
    for d in with_sheet:
        try:
            if any(ps.rows for ps in read_sheet(d / "measurements.md").parts):
                return d
        except (OSError, ValueError):
            continue
    return with_sheet[0] if with_sheet else None
