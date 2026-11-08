"""What passed and what failed, at a glance.

Every build command prints its full report and then ONE verdict line (`verdict`):

    ==> PASSED  ring_shank_court_US6_..._83cc6280
    ==> FAILED  ring_shank_court_US6_..._c813da63: section shape (0.058 mm vs 0.05 at 181°)
    ==> ERROR   shank: ntopcl failed: ...            (nothing was built, nothing was gated)

green / red / yellow when the console can show colour (NO_COLOR turns it off). And
`python -m ntopjewel runs` reads the report JSON every run leaves in out/ and prints one row
per run (`scan_runs`, `table`): today's runs by default, `--last N`, `--all`.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

GREEN, RED, YELLOW, BOLD, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[1m", "\033[0m"
FAMILIES = ("band", "ring", "shank", "seat", "head", "solitaire", "prep")
_vt_ready = False


def use_colour(stream=None) -> bool:
    """Colour only on a console that shows it: a TTY, NO_COLOR unset (Windows consoles get their
    escape-sequence mode switched on first)."""
    global _vt_ready
    stream = stream or sys.stdout
    if os.environ.get("NO_COLOR") or not getattr(stream, "isatty", lambda: False)():
        return False
    if os.name == "nt" and not _vt_ready:                     # pragma: no cover - the container is Linux
        os.system("")                                         # enables VT processing in conhost / Windows Terminal
        _vt_ready = True
    return True


def paint(text: str, colour: str, stream=None) -> str:
    return f"{BOLD}{colour}{text}{RESET}" if use_colour(stream) else text


def _failures(gate_report) -> list:
    if gate_report is None:
        return []
    return [c for c in getattr(gate_report, "checks", []) if getattr(c, "status", None) != "passed" and getattr(c, "hard", True)]


def _short(detail: str, limit: int = 70) -> str:
    """A check's detail cut to its numbers: up to the first ' - ' (the explanation) and `limit` characters."""
    import re
    d = detail.split(" - ")[0].strip()
    d = re.sub(r"^\d+ angles, outlines within (\S+ mm) of the design", r"off by \1", d)      # section shape: the number first
    return d if len(d) <= limit else d[:limit - 1] + "…"


def verdict(res, stream=None, prep=None) -> str:
    """The one line that says how a build went: PASSED / FAILED with the failing checks named - and, after a print
    preparation (`prep`, printprep.PrepResult), what it made or why it failed."""
    stem = Path(getattr(res, "stl", "") or "").stem or getattr(getattr(res, "spec", None), "stem", "?")
    status = str(getattr(res, "status", "failed")).lower()
    if status == "passed":
        if prep is not None and not prep.ok:
            return paint(f"==> FAILED  {stem}", RED, stream) + f": print prep ({_prep_failures(prep)})"
        line = paint(f"==> PASSED  {stem}", GREEN, stream) + (f"  (delivered to {res.delivered})" if getattr(res, "delivered", None) else "")
        if prep is not None:
            line += f"  print file: {prep.headline()}" + (f"; {prep.cautions()}" if prep.cautions() else "")
        return line
    fails = _failures(getattr(res, "gate", None))
    word = "INCOMPLETE" if status == "incomplete" else "FAILED"
    why = "; ".join(f"{c.name} ({_short(c.detail)})" for c in fails) or ("the nTop run failed" if not getattr(getattr(res, "run", None), "ok", True)
                                                                          else "see the report above")
    return paint(f"==> {word}  {stem}", RED if word == "FAILED" else YELLOW, stream) + f": {why}"


def _prep_failures(prep) -> str:
    return "; ".join(f"{c.name} ({_short(c.detail)})" for c in prep.checks if c.hard and c.status != "passed") or "see the report above"


def prep_verdict(prep, delivered=None, stream=None) -> str:
    """The verdict of a print preparation on its own (`--prep-stl`): PASSED when the supported file is one sound body
    standing on the plate with every contact on plain metal and every plain island held; what it could not support is
    said beside it."""
    stem = f"{prep.stem}.supported" + (f"_{prep.metal}" if prep.metal else "")
    if prep.ok:
        return (paint(f"==> PASSED  {stem}", GREEN, stream) + f"  ({prep.headline()}" + (f"; {prep.cautions()}" if prep.cautions() else "")
                + ")" + (f"  (delivered to {delivered})" if delivered else ""))
    return paint(f"==> FAILED  {stem}", RED, stream) + f": {_prep_failures(prep)}"


def testprint_verdict(size, folder, done, ok, stream=None) -> str:
    """The verdict of a test-print round: PASSED when every part built, passed its gate and was prepared; else the
    parts that did not, and why (their own verdicts above say more)."""
    bad = [(p, rec) for p, rec in done if not ok(rec)]
    if not bad:
        return paint(f"==> PASSED  test print US {size}", GREEN, stream) + f"  ({len(done)} parts in {folder})"
    why = []
    for p, rec in bad:
        res, prep = rec.get("res"), rec.get("prep")
        if res is not None and not res.ok:
            why.append(f"{p.key} (" + ("; ".join(c.name for c in _failures(getattr(res, "gate", None))) or "the build failed") + ")")
        elif prep is not None and not prep.ok:
            why.append(f"{p.key} (print prep: {_prep_failures(prep)})")
        else:
            why.append(f"{p.key} (exit {rec.get('code')}: nothing came back)")
    good = len(done) - len(bad)
    return (paint(f"==> FAILED  test print US {size}", RED, stream) + ": " + "; ".join(why)
            + (f"  ({good} part{'s' if good != 1 else ''} in {folder})" if good else ""))


def error_line(what: str, err, stream=None) -> str:
    """The verdict when nothing was built: the command stopped before or inside nTop."""
    return paint(f"==> ERROR   {what}", YELLOW, stream) + f": {str(err).splitlines()[0] if str(err) else type(err).__name__}"


@dataclass
class RunRow:
    when: datetime
    family: str
    stem: str
    status: str
    failures: list[str]
    run_dir: Path


def scan_runs(out_dir: Path, since: datetime | None = None, last: int | None = None) -> list[RunRow]:
    """Every run under out/<family>/<stem>/<run id>/ that left a report, oldest first: since a
    time, or the `last` N, or all."""
    rows = []
    for fam in FAMILIES:
        for rep in Path(out_dir, fam).glob("*/*/*.prep.json" if fam == "prep" else "*/*/*.report.json"):
            run_dir = rep.parent
            try:
                when = datetime.strptime(run_dir.name[:15], "%Y%m%d-%H%M%S")
                doc = json.loads(rep.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            g = doc.get("gate") or {"checks": doc.get("checks", [])}
            fails = [f"{c['name']} ({_short(c.get('detail', ''), 48)})" for c in g.get("checks", [])
                     if c.get("status", "passed" if c.get("ok") else "failed") != "passed" and c.get("hard", True)]
            rows.append(RunRow(when, fam, doc.get("stem", run_dir.parent.name), str(doc.get("status", "?")).lower(), fails, run_dir))
    rows.sort(key=lambda r: r.when)
    if since is not None:
        rows = [r for r in rows if r.when >= since]
    if last is not None:
        rows = rows[-last:]
    return rows


def _design(stem: str, width: int = 46) -> str:
    """A stem without its family prefix and spec id, cut to `width`: what the run was."""
    s = stem
    for prefix in ("ring_shank_", "solitaire_", "ring_band_", "ring_", "head_", "seat_"):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    s = s.rsplit("_", 1)[0] if len(s.rsplit("_", 1)) == 2 and len(s.rsplit("_", 1)[1]) == 8 else s
    return s if len(s) <= width else s[:width - 1] + "…"


def table(rows: list[RunRow], stream=None) -> str:
    """One line per run: time, family, design, status and - for a failure - the failing checks."""
    if not rows:
        return "no runs found"
    lines = [f"{'when':<11} {'family':<9} {'design':<46} status"]
    for r in rows:
        status = {"passed": paint("PASSED", GREEN, stream), "failed": paint("FAILED", RED, stream)}.get(r.status, paint(r.status.upper(), YELLOW, stream))
        line = f"{r.when:%m-%d %H:%M} {r.family:<9} {_design(r.stem):<46} {status}"
        if r.failures:
            line += "  " + "; ".join(r.failures)
        lines.append(line)
    n_pass = sum(r.status == "passed" for r in rows)
    lines.append(f"{len(rows)} runs: {n_pass} passed, {len(rows) - n_pass} not")
    return "\n".join(lines)
