"""The test-print round (testprint, `python -m ntopjewel testprint`): the set's command lines at the tables' size
and each part's own rules, `--prep-stl delivered`, and a round's folder written from the parts that came back -
the real preparation run on stand-in band meshes named for each design (2026-11-08)."""
from __future__ import annotations

import datetime
import json

import pytest

from ntopjewel import band, cli, geom, summary, tables, testprint


def test_the_set_is_built_at_the_tables_size_with_each_parts_own_rules():
    assert testprint.size() == "4.5" == f"{tables.SETTINGS['test_print_size']:g}"
    court, hammered, seraphine = (testprint.args_for(p) for p in testprint.PARTS)
    for a in (court, hammered, seraphine):
        assert a[a.index("--size") + 1] == "4.5" and "--prep" in a and "--deliver" in a
    assert court[court.index("--bore") + 1] == "allow"                     # 9 Nov: struts in the crown; it stands on its dome
    assert court[court.index("--support-spacing") + 1] == f"{tables.SETTINGS['test_print_court_spacing_mm']:g}" == "3"
    assert hammered[hammered.index("--support-spacing") + 1] == f"{tables.SETTINGS['test_print_hammered_spacing_mm']:g}" == "3"
    assert seraphine[seraphine.index("--support-spacing") + 1] == "2.2"
    again = testprint.args_for(testprint.PARTS[1], "6", metal="sterling", spacing=2.0, reprep=True)
    assert again[again.index("--prep-stl") + 1] == "delivered" and "--prep" not in again
    assert again[again.index("--support-spacing") + 1] == "2" and again[again.index("--metal") + 1] == "sterling"
    assert [p.key for p in testprint.select("seraphine, court")] == ["seraphine", "court"]
    with pytest.raises(ValueError, match="no test part bezel"):
        testprint.select("court,bezel")
    assert testprint.folder_for("J", None, datetime.date(2026, 11, 8)).as_posix() == "J/Test Print/2026-11-08 US4.5"


def test_dry_run_prints_the_three_commands_and_the_folder(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("JEWELRY_DELIVER", str(tmp_path / "Jewelry"))
    assert cli.main(["testprint", "--dry-run"]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert [l.split()[3] for l in out[:3]] == ["ring", "texture", "solitaire"] and '"M+K 2026"' in out[0]
    assert out[3].strip().startswith("->") and "Test Print" in out[3] and "US4.5" in out[3]
    assert cli.main(["testprint", "--parts", "lattice"]) == 2
    assert "no test part lattice" in capsys.readouterr().out


def _stand_in(args, tmp_path, capsys):
    """The design's spec and stem from its own command (refused for another file, it names the design), and the
    design's plain body - its band, or its shank for a solitaire - in a file of that name: the real preparation then
    runs with the design's own surface model, and the part can start on plain metal as the design does."""
    other = tmp_path / "other.stl"
    other.write_bytes(b"solid x\nendsolid x\n")
    rec = cli._run_part(args + ["--prep-stl", str(other)])
    assert rec["code"] == 2
    stem = capsys.readouterr().out.strip().splitlines()[-1].split("these arguments describe ")[1].split(" ")[0]
    spec = rec["spec"]
    assert spec.stem == stem
    stl = tmp_path / f"{stem}.stl"
    sh = getattr(spec, "shank_spec", None)
    (sh.design_mesh() if sh is not None else geom.band_mesh(spec.band.notebook_inputs(""))).export(str(stl))
    return stl


def test_a_round_writes_its_folder_from_the_parts_that_came_back(tmp_path, out_dir, monkeypatch, capsys):
    monkeypatch.setenv("JEWELRY_DELIVER", str(tmp_path / "Jewelry"))
    monkeypatch.setenv("JEWELRY_OUT", str(out_dir))
    seen = []

    def runner(args):                               # each part prepared from a stand-in, nothing built or delivered
        if args[0] == "texture":
            return {"code": 1, "res": None, "prep": None}                               # one that did not come back
        a = [x for x in args if x not in ("--prep", "--deliver")]
        stl = _stand_in(a, tmp_path, capsys)
        rec = cli._run_part(a + ["--prep-stl", str(stl)])
        seen.append((args, rec))
        return rec
    folder, done = testprint.run(None, testprint.PARTS, runner, tmp_path / "Jewelry", today=datetime.date(2026, 11, 8),
                                 say=lambda m: None)
    assert folder == tmp_path / "Jewelry" / "Test Print" / "2026-11-08 US4.5"
    assert [testprint.ok(rec) for _, rec in done] == [True, False, True]
    court, seraphine = seen[0][1], seen[1][1]
    assert court["prep"].settings["support_spacing_mm"] == pytest.approx(3.0)
    assert seraphine["prep"].settings["support_spacing_mm"] == pytest.approx(2.2)
    assert all(sp.cls in (0, 1) for sp in court["prep"].supports)                    # the bore allowed since 9 Nov
    names = sorted(p.name for p in folder.iterdir())
    for rec in (court, seraphine):
        assert rec["prep"].files["print file"].name in names and rec["prep"].files["preview"].name in names
    readme = (folder / "README.md").read_text(encoding="utf-8")
    assert readme.startswith("# Test Print — 8 Nov 2026, US 4.5") and "slice it as it is" in readme
    assert "bore Ø 15.288" in readme and "Not in this round" in readme and "hammered" in readme.split("Not in this round")[1]
    assert "sand their nubs flush" in readme and "within two layers of its lowest point" in readme
    sheet = (folder / "measurements.md").read_text(encoding="utf-8")
    assert "## 1. Court band" in sheet and "## 2. The Seraphine" in sheet and sheet.count("swelling where they met the part") == 2
    assert "Width over the beads" in sheet and "g of resin" in sheet and "2.2 mm apart" in sheet and "Bore nubs" in sheet
    line = summary.testprint_verdict("4.5", folder, done, testprint.ok)
    assert line.startswith("==> FAILED  test print US 4.5: hammered (exit 1") and "2 parts in" in line


def test_prep_stl_delivered_takes_the_designs_own_delivery(tmp_path, out_dir, monkeypatch, capsys):
    monkeypatch.setenv("JEWELRY_DELIVER", str(tmp_path / "Jewelry"))
    monkeypatch.setenv("JEWELRY_OUT", str(out_dir))
    spec = band.BandSpec(size=6, profile="court")
    assert cli.main(["band", "--size", "6", "--profile", "court", "--prep-stl", "delivered"]) == 2
    assert "no delivery of " + spec.stem in capsys.readouterr().out
    folder = tmp_path / "Jewelry" / "Bands" / spec.stem
    folder.mkdir(parents=True)
    geom.band_mesh(spec.notebook_inputs("")).export(str(folder / f"{spec.stem}.stl"))
    (folder / "manifest.json").write_text(json.dumps({"status": "passed", "stem": spec.stem}), encoding="utf-8")
    code = cli.main(["band", "--size", "6", "--profile", "court", "--prep-stl", "delivered", "--deliver", "--support-spacing", "2.5"])
    text = capsys.readouterr().out
    assert code == 0, text
    assert text.strip().splitlines()[-1].startswith(f"==> PASSED  {spec.stem}.supported") and f"delivered to {folder}" in text
    man = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert man["prep"]["status"] == "passed" and (folder / f"{spec.stem}.supported.stl").exists()
    doc = json.loads((folder / f"{spec.stem}.prep.json").read_text(encoding="utf-8"))
    assert doc["settings"]["support_spacing_mm"] == 2.5 and doc["part_volume_mm3"] > 0 and len(doc["part_extents_mm"]) == 3
