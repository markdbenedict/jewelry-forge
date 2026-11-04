"""The one-line verdicts, the `runs` table, and the guard against running a notebook older than its catalog."""
import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from ntopjewel import band, catalog, cli, config, gate, runs, shank, summary


def tapered():
    return shank.ShankSpec(band.BandSpec(size=6, profile="court", width_mm=4.0, thickness_mm=1.6, mesh_tolerance_mm=0.1),
                           width_bottom_mm=2.2, thickness_bottom_mm=1.2)


class _Res:
    def __init__(self, status, checks, stl="out/x/ring_shank_abc_12345678.stl"):
        self.status, self.stl, self.delivered = status, Path(stl), None
        self.gate = gate.GateReport(path=str(stl), checks=checks)


def test_verdict_names_the_failing_hard_checks_only(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    ok = _Res("passed", [gate.Check("shells", True, "1 (expected 1)")])
    assert summary.verdict(ok) == "==> PASSED  ring_shank_abc_12345678"
    bad = _Res("failed", [gate.Check("shells", True, "1"),
                          gate.Check("mesh density", False, "9,000,000 triangles", hard=False),          # soft: not a cause
                          gate.Check("section shape", False, "12 angles, outlines within 0.058 mm of the design (tolerance 0.05); "
                                     "worst at 181° - the built section is not the designed one")])
    line = summary.verdict(bad)
    assert line.startswith("==> FAILED  ring_shank_abc_12345678: section shape (off by 0.058 mm (tolerance 0.05); worst at 181°)")
    assert "mesh density" not in line and "the built section" not in line
    assert summary.error_line("shank", ValueError("no build stamp\nmore")) == "==> ERROR   shank: no build stamp"


def test_runs_table_reads_the_reports(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("NO_COLOR", "1")
    for fam, stem, run_id, status, checks in (
            ("shank", "ring_shank_court_US6_split1.6_c813da63", "20261102-165709", "failed",
             [{"name": "section shape", "ok": False, "status": "failed", "hard": True,
               "detail": "12 angles, outlines within 0.058 mm of the design (tolerance 0.05); worst at 181° - why"}]),
            ("solitaire", "solitaire_court_US6_trinity5.2_marquise_dec54e1d", "20261102-165808", "passed", []),
            ("shank", "ring_shank_plait3x4_US6_968eb59b", "20261101-141300", "failed", [])):
        d = tmp_path / fam / stem / run_id
        d.mkdir(parents=True)
        (d / f"{stem}.report.json").write_text(json.dumps({"stem": stem, "status": status, "gate": {"checks": checks}}))
    rows = summary.scan_runs(tmp_path)
    assert [r.when.strftime("%d %H:%M") for r in rows] == ["01 14:13", "02 16:57", "02 16:58"]       # oldest first
    text = summary.table(rows)
    assert "court_US6_split1.6 " in text and "c813da63" not in text                                   # the spec id dropped
    assert "FAILED  section shape (off by 0.058 mm" in text and text.endswith("3 runs: 1 passed, 2 not")
    assert cli.main(["runs", "--out", str(tmp_path), "--since", "2026-11-02 16:58"]) == 0
    assert "1 runs: 1 passed, 0 not" in capsys.readouterr().out
    assert cli.main(["runs", "--out", str(tmp_path), "--last", "2"]) == 0
    assert "2 runs: 1 passed, 1 not" in capsys.readouterr().out


def test_a_notebook_older_than_its_catalog_is_refused(tmp_path, monkeypatch):
    """2026-11-02: the split shank ran on a notebook built before the per-bar opening and failed for it;
    nothing in the inputs had changed, so nothing else could notice."""
    monkeypatch.setattr(config, "notebooks_dir", lambda: tmp_path)
    nb = tmp_path / "ring_shank.ntop"
    nb.write_bytes(b"built at 14:52")
    cat = catalog.load("ring_shank")
    assert cat.notebook == nb and cat.rebuild_since >= "0.3.1"
    with pytest.raises(ValueError, match="no build stamp.*api build ring_shank"):
        runs.require_built(cat, nb)
    runs.build_stamp_path(nb).write_text(json.dumps({"sha256": runs.sha256(nb), "catalogs": {"ring_shank": "0.3.0"}}))
    with pytest.raises(ValueError, match=re.escape(f"built for ring_shank 0.3.0; the catalog is {cat.version} and its notebook "
                                                  f"changed in {cat.rebuild_since}")):
        runs.require_built(cat, nb)
    stamp = runs.write_build_stamp(nb, {"ring_shank": cat.version})            # what `api build` does after saving
    assert stamp["catalogs"] == {"ring_shank": cat.version} and runs.require_built(cat, nb) == []
    nb.write_bytes(b"edited in the GUI")
    assert "changed since its build stamp" in runs.require_built(cat, nb)[0]
    assert runs.require_built(replace(cat, rebuild_since=None), tmp_path / "other.ntop") == []      # a catalog without the rule
    assert runs._recipe_for(Path("stone_seat_harness.ntop")) == "stone_seat" and runs._recipe_for(Path("ring_band_profile.ntop")) == "band_profile"


def test_the_runner_refuses_before_nTop_runs(fake_ntopcl, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "notebooks_dir", lambda: tmp_path)
    monkeypatch.setenv("NO_COLOR", "1")
    nb = tmp_path / "ring_shank.ntop"
    nb.write_bytes(b"fake")
    s = tapered()
    with pytest.raises(ValueError, match="api build ring_shank"):
        shank.build(s, tmp_path / "out")                                       # the catalog's own notebook: checked
    assert not (tmp_path / "out").exists() or not any((tmp_path / "out").rglob("*.stl"))
    assert cli.main(["shank", "--size", "6", "--thickness", "1.6", "--width-bottom", "2.2", "--thickness-bottom", "1.2",
                     "--out", str(tmp_path / "out")]) == 2
    assert capsys.readouterr().out.strip().splitlines()[-1].startswith("==> ERROR   shank: ring_shank.ntop has no build stamp")
    runs.write_build_stamp(nb, {"ring_shank": catalog.load("ring_shank").version})
    res = shank.build(s, tmp_path / "out")
    assert res.status == "passed", res.text()
    assert summary.verdict(res).startswith("==> PASSED  " + s.stem)


def test_a_run_whose_paths_would_pass_max_path_is_refused_before_anything_is_made(tmp_path):
    """2026-11-03: two solitaire end-to-end tests failed on the laptop with FileNotFoundError from
    the middle of a build - pytest's temp dir plus a 90-character stem twice passed Windows'
    MAX_PATH. The runner now says so up front, naming the length and the way out."""
    stem = "solitaire_court_US6_w4-4_t1.6-1.6_split1.6_trinity5.6_6prong_marquise_10x5x3p05_25341b97"
    with pytest.raises(runs.RunPathError, match="use a shorter --out, or enable long paths"):
        runs.fresh_run_dir(tmp_path / "out", stem, max_path=len(str(tmp_path)) + 2 * len(stem))
    assert not (tmp_path / "out").exists()
    d, _ = runs.fresh_run_dir(tmp_path / "out", stem, max_path=None)      # no limit: the usual directory
    assert d.is_dir() and d.parent.name == stem
    assert runs.path_limit() in (None, runs.WINDOWS_MAX_PATH)
