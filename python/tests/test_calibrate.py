"""The calibration intake (calibrate, `python -m ntopjewel calibrate`): a round's measurement sheet read back as filled in,
each reading against the part as built, the resin's shrink and bloom fitted over the round, the density from the weights,
the tables updated with dated calibration_log entries (2026-11-09)."""
from __future__ import annotations

import datetime
import json
import random
from pathlib import Path

import pytest

from ntopjewel import calibrate, cli, tables, testprint

COURT_STEM = "ring_court_milgrain_groove_engraved_US4.5_w4_t1.3_16f7cb24"
HAMMER_STEM = "ring_texture_hammered_court_US4.5_w4_t1.6_d1.6x0.15_fd82f637"
TRUE_SHRINK, TRUE_BLOOM = 0.006, 0.03          # what the synthetic prints "did": 0.6 % shrink, 0.03 mm bloom


def _sheet(court_rows: dict, hammer_rows: dict, settings: dict | None = None, part_lines: bool = True, blank_answers: bool = False) -> str:
    """A round's sheet in testprint._sheet's format, the given rows filled in (the court band's feature answers given too,
    unless blank_answers)."""
    st = {"layer": "50", "exposure": "2.5", "bottom": "5", "bottom_s": "30", "as_is": "yes", "wash": "4", "cure": "15",
          "after": "2", "scale": "0.001", "calipers": "Mitutoyo digital"}
    st.update(settings or {})
    court, hammer = testprint.PARTS[0], testprint.PARTS[1]

    def table(part, rows):
        out = ["| Measure | 1 | 2 | 3 |", "| --- | --- | --- | --- |"]
        for label, _ in testprint.COMMON_ROWS + tuple(part.rows) + (testprint.WEIGHT_ROW,):
            cells = rows.get(label, ["", "", ""])
            cells = list(cells) + [""] * (3 - len(cells))
            out.append(f"| {label} | " + " | ".join(str(c) for c in cells) + " |")
        return out
    lines = ["# Test Print — measurements (US 4.5, 8 Nov 2026)", "", "Fill the blanks...", "", "## Print settings (once)", "",
             "- Printer / resin: Elegoo Mars 5 Ultra, Siraya Tech Royal Blue",
             f"- Layer height: {st['layer']} µm;  exposure: {st['exposure']} s;  bottom layers: {st['bottom']} at {st['bottom_s']} s",
             f"- Printed from the `.supported.stl` files as they are (no supports added, not rotated)? {st['as_is']}",
             f"- Wash: IPA {st['wash']} min;  cure: {st['cure']} min;  measured {st['after']} h after the cure",
             f"- Scale resolution: {st['scale']} g;  calipers: {st['calipers']}", "",
             f"## 1. {court.title}", ""]
    if part_lines:
        lines.append(f"Part: {COURT_STEM} (court)")
    lines += ["Design: bore Ø 15.288, width 4.000 (4.51 over the beads), thickness 1.300, outer Ø 17.89; 227.1 mm³ (0.26 g of resin).",
              "Printed: 11 supports (11 on polished faces), axis 37° to the plate, 1.5 mm apart.", ""]
    lines += table(court, court_rows)
    b = "____"
    lines += ["", "Features (yes / no, a few words):",
              f"- Beads: all present? {b if blank_answers else 'yes'}  Missing or merged in a quarter turn: {b if blank_answers else 'none'}  "
              f"Shape (round / blobby / flat): {b if blank_answers else 'round'}",
              "- Groove: continuous and crisp-edged? ____",
              f"- Supports: swelling where they met the part? {b if blank_answers else 'slight at two tips'}  Broke off clean at the tip? "
              f"{b if blank_answers else 'yes'}  Nubs sanded flush? {b if blank_answers else 'yes'}",
              f"- Anything sagged or missing where the preview marks it unsupported? {b if blank_answers else 'no'}", "", f"## 2. {hammer.title}", ""]
    if part_lines:
        lines.append(f"Part: {HAMMER_STEM} (hammered)")
    lines += ["Design: bore Ø 15.288, width 4.000, thickness 1.600, outer Ø 18.49; 271.7 mm³ (0.31 g of resin).",
              "Printed: 15 supports (15 on polished faces), lying flat (axis upright), 3 mm apart.", ""]
    lines += table(hammer, hammer_rows)
    lines += ["", "Features (yes / no, a few words):", "- Rims flat and clean? ____",
              "- Supports: swelling where they met the part? ____  Broke off clean at the tip? ____  Nubs sanded flush? ____",
              "- Anything sagged or missing where the preview marks it unsupported? ____", ""]
    return "\n".join(lines)


def _printed(built: float, sign: int, n: int = 3, noise: float = 0.006, rng=None) -> list[str]:
    rng = rng or random.Random(7)
    return [f"{built * (1 - TRUE_SHRINK) + 2 * sign * TRUE_BLOOM + rng.gauss(0, noise):.3f}" for _ in range(n)]


def _round(tmp_path: Path, sheet: str, with_manifest: bool = True) -> tuple[Path, Path]:
    """A Jewelry folder with one round and (with_manifest) the court band's delivery holding a gate like the real one."""
    jewelry = tmp_path / "Jewelry"
    folder = jewelry / testprint.FOLDER / "2026-11-08 US4.5"
    folder.mkdir(parents=True)
    (folder / "measurements.md").write_text(sheet, encoding="utf-8")
    (folder / "README.md").write_text("| File | What |\n| --- | --- |\n"
                                      f"| `{COURT_STEM}.supported.stl` | court |\n| `{HAMMER_STEM}.supported.stl` | hammered |\n", encoding="utf-8")
    if with_manifest:
        d = jewelry / "Rings" / COURT_STEM
        d.mkdir(parents=True)
        (d / "manifest.json").write_text(json.dumps({
            "stem": COURT_STEM, "status": "passed", "features": {"milgrain": True},
            "gate": {"inner_diameter_mm": 15.2876, "outer_diameter_mm": 17.8706, "width_mm": 4.5057, "volume_mm3": 227.12, "area_mm2": 576.84},
            "prep": {"status": "passed", "supports": 17, "orientation": "17 supports (9 on polished faces, 8 in the bore), standing on edge (axis level)"}}),
            encoding="utf-8")
        (d / f"{COURT_STEM}.prep.json").write_text(json.dumps({
            "settings": {"support_spacing_mm": 3.0, "support_tip_mm": 0.25}, "unsupported": {"first_contact_mm": 0.04},
            "checks": [{"name": "layers held", "detail": "no layer hangs on more than 4.5 mm² per contact engaged under it (5 allowed)"}]}),
            encoding="utf-8")
    return jewelry, folder


def _filled(rng=None) -> tuple[dict, dict]:
    rng = rng or random.Random(3)
    court = {"Bore Ø, inside jaws (×3)": _printed(15.2876, -1, rng=rng), "Outer Ø over the beads (×3)": _printed(17.8706, +1, rng=rng),
             "Width over the beads (×2)": _printed(4.5057, +1, 2, rng=rng), "Width between the faces, beside a bead (×2)": _printed(4.0, +1, 2, rng=rng),
             "Weight (g)": ["0.256"]}
    hammer = {"Bore Ø, inside jaws (×3)": _printed(15.288, -1, rng=rng), "Mandrel size it stops at": ["4.25", "4.25", "4.25"],
              "Outer Ø across the rims (×3)": _printed(18.49, +1, rng=rng), "Width (×2)": _printed(4.0, +1, 2, rng=rng),
              "Weight (g)": ["0.306", "0.306"]}
    return court, hammer


def test_cells_and_design_lines_are_read():
    assert calibrate.parse_number("15.27") == 15.27 and calibrate.parse_number("15,27 mm") == 15.27 and calibrate.parse_number("0.26g") == 0.26
    assert calibrate.parse_number("4 1/2") == 4.5 and calibrate.parse_number("4½") == 4.5 and calibrate.parse_number("½") == 0.5
    assert calibrate.parse_number("") is None and calibrate.parse_number("____") is None and calibrate.parse_number("yes") is None
    d = calibrate.parse_design("Design: bore Ø 15.288, width 4.000 (4.51 over the beads), thickness 1.300, outer Ø 17.89; 227.1 mm³ (0.26 g of resin).")
    assert d == {"bore": 15.288, "width": 4.0, "over_beads": 4.51, "thickness": 1.3, "outer": 17.89, "volume": 227.1, "resin_g": 0.26}
    d = calibrate.parse_design("Design: bore Ø 15.288; band 2.8 wide × 2 thick at the head, 2 × 1.5 at the bottom; 21.8 × 19.3 × 6.2 mm overall; 272.6 mm³ (0.31 g of resin).")
    assert d["width"] == 2.8 and d["width_bottom"] == 2.0 and d["thickness_bottom"] == 1.5 and d["extents"] == [21.8, 19.3, 6.2] and d["volume"] == 272.6
    assert calibrate.row_key("Bore Ø, inside jaws (×3)", "court") == "bore" and calibrate.row_key("Width (×2)", "hammered") == "width"
    assert calibrate.row_key("Band width at the bottom", None) == "width_bottom" and calibrate.row_key("Overall height, bottom of the band to the prong tips", None) == "height"
    assert calibrate.row_key("Outer Ø over the beads (×3)", None) == "outer" and calibrate.row_key("Something else", "court") is None


def test_a_filled_round_gives_back_the_shrink_the_bloom_and_the_density(tmp_path):
    court, hammer = _filled()
    jewelry, folder = _round(tmp_path, _sheet(court, hammer))
    cal = calibrate.calibrate(folder, today=datetime.date(2026, 11, 9))
    assert [p.sheet.stem for p in cal.parts] == [COURT_STEM, HAMMER_STEM] and cal.parts[0].delivery is not None and cal.parts[1].delivery is None
    assert cal.parts[0].built["bore"] == 15.2876 and cal.parts[0].built["over_beads"] == 4.5057 and cal.parts[0].built["width"] == 4.0   # the gate's, the design's
    assert cal.parts[1].built["bore"] == 15.288 and cal.parts[1].built["outer"] == 18.49                                                # the design line's
    f = cal.fit
    assert f.sound, f.why_unsound
    assert f.separable and f.shrink_pct == pytest.approx(100 * TRUE_SHRINK, abs=0.1) and f.bloom_mm == pytest.approx(TRUE_BLOOM, abs=0.006)
    assert f.rms_mm < 0.015 and not f.outliers and f.n == 21                 # 10 caliper readings on the court band, 8 + 3 mandrel on the hammered
    assert cal.sheet.settings["layer_um"] == "50" and cal.sheet.settings["as_is"] == "yes" and cal.sheet.settings["scale_g"] == "0.001"
    court_part = cal.parts[0]
    assert court_part.supports["swelling"] == "slight at two tips" and court_part.supports["sagged"] == "no"
    assert "3 mm apart" in court_part.supports["printed_with"] and "first contact 0.04" in court_part.supports["printed_with"]
    assert "4.5 mm² per tip" in court_part.supports["printed_with"]
    assert court_part.sheet.unanswered == 1 and cal.parts[1].sheet.unanswered == 3
    # the density: weight over the printed volume (built, shrunk, grown by the bloom), from the part with a gate volume and the one without
    assert cal.density is not None and cal.density_n == 2 and 1.0 < cal.density < 1.3
    text = cal.text()
    assert "shrink +0.61 %" in text or "shrink +0.60 %" in text or "shrink +0.59 %" in text
    assert "bloom +0.03" in text or "bloom +0.029" in text or "bloom +0.028" in text
    assert "under size: --allowance 0.15" in text and "resin density" in text
    assert cal.verdict().startswith("==> PASSED  calibrate 2026-11-08 US4.5") and "21 readings on 2 part(s)" in cal.verdict()
    # written to a copy of the tables
    tcopy = tmp_path / "tables.json"
    tcopy.write_text(tables.TABLES_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    applied = calibrate.apply(cal, tcopy)
    assert set(applied) == {"settings.resin_shrink_pct", "settings.print_bloom_mm", "metals.resin.density_g_cm3"}
    doc = json.loads(tcopy.read_text(encoding="utf-8"))
    assert doc["settings"]["resin_shrink_pct"]["status"] == "calibrated" and doc["settings"]["resin_shrink_pct"]["value"] == pytest.approx(0.6, abs=0.1)
    assert doc["settings"]["print_bloom_mm"]["status"] == "calibrated" and doc["settings"]["print_bloom_mm"]["value"] == pytest.approx(0.03, abs=0.006)
    assert doc["metals"]["resin"]["status"] == "calibrated" and doc["metals"]["resin"]["density_g_cm3"] == pytest.approx(cal.density, abs=0.001)
    log = doc["calibration_log"][-5:]
    assert [e["entry"] for e in log[:3]] == ["settings.resin_shrink_pct", "settings.print_bloom_mm", "metals.resin.density_g_cm3"]
    assert all(e["date"] == "2026-11-09" and e["status"] == "calibrated" for e in log[:3]) and log[0]["from"] == 0.0
    assert "50 µm layers" in log[0]["evidence"] and "2.5 s exposure" in log[0]["evidence"]
    assert [e["status"] for e in log[3:]] == ["evidence", "evidence"] and COURT_STEM in log[3]["evidence"] and "slight at two tips" in log[3]["evidence"]
    assert "Calibrated 2026-11-09" in doc["settings"]["print_bloom_mm"]["source"]
    md, js = calibrate.write_round(cal)
    assert md.exists() and json.loads(js.read_text(encoding="utf-8"))["fit"]["shrink_pct"] == pytest.approx(f.shrink_pct)
    assert tables.TABLES["settings"]["resin_shrink_pct"]["status"] == "uncalibrated"                       # the repo's own tables untouched


def test_stems_come_from_the_readme_when_the_sheet_has_no_part_lines(tmp_path):
    court, hammer = _filled()
    jewelry, folder = _round(tmp_path, _sheet(court, hammer, part_lines=False))
    cal = calibrate.calibrate(folder)
    assert [p.sheet.stem for p in cal.parts] == [COURT_STEM, HAMMER_STEM] and [p.sheet.key for p in cal.parts] == ["court", "hammered"]
    assert cal.parts[0].delivery is not None and cal.fit.sound


def test_a_slipped_caliper_is_dropped_and_named_and_a_mandrel_a_size_off_is_noted(tmp_path):
    court, hammer = _filled()
    court["Outer Ø over the beads (×3)"][1] = f"{float(court['Outer Ø over the beads (×3)'][1]) + 0.3:.3f}"   # one slip
    hammer["Mandrel size it stops at"] = ["3.5", "3.5", "3.5"]                                                  # a size too small
    jewelry, folder = _round(tmp_path, _sheet(court, hammer))
    cal = calibrate.calibrate(folder)
    assert cal.fit.sound and len(cal.fit.outliers) == 1 and "Outer Ø over the beads" in cal.fit.outliers[0]
    assert cal.fit.shrink_pct == pytest.approx(100 * TRUE_SHRINK, abs=0.1) and cal.fit.bloom_mm == pytest.approx(TRUE_BLOOM, abs=0.006)
    assert any(r.outlier for p in cal.parts for r in p.readings) and "dropped: part 1" in cal.text()
    assert cal.fit.notes and "mandrel" in cal.fit.notes[0]


def test_without_a_bore_reading_nothing_is_written_and_a_blank_sheet_is_an_error(tmp_path):
    court, hammer = _filled()
    for rows in (court, hammer):
        rows.pop("Bore Ø, inside jaws (×3)", None)
        rows.pop("Mandrel size it stops at", None)
    jewelry, folder = _round(tmp_path, _sheet(court, hammer))
    cal = calibrate.calibrate(folder)
    assert not cal.fit.separable and not cal.fit.sound and "no reading across a bore" in cal.fit.why_unsound[0]
    assert cal.verdict().startswith("==> FAILED  calibrate") and "cannot be told apart" in cal.verdict()
    tcopy = tmp_path / "tables.json"
    tcopy.write_text(tables.TABLES_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    applied = calibrate.apply(cal, tcopy)
    assert set(applied) == {"metals.resin.density_g_cm3"}                     # the weights still give a density
    doc = json.loads(tcopy.read_text(encoding="utf-8"))
    assert doc["settings"]["resin_shrink_pct"]["status"] == "uncalibrated" and doc["settings"]["print_bloom_mm"]["status"] == "uncalibrated"
    blank_jewelry, blank = _round(tmp_path / "blank", _sheet({}, {}), with_manifest=False)
    cal = calibrate.calibrate(blank)
    assert not cal.measured_parts and cal.verdict().startswith("==> ERROR") and "no readings" in cal.verdict()


def test_a_coarse_scale_gives_no_density(tmp_path):
    court, hammer = _filled()
    jewelry, folder = _round(tmp_path, _sheet(court, hammer, settings={"scale": "0.1"}))
    cal = calibrate.calibrate(folder)
    assert cal.fit.sound and cal.density is None and "too coarse" in (cal.density_note or "")
    assert all("too coarse" in (p.density_note or "") for p in cal.parts if p.weight_g is not None)


def test_the_cli_reads_the_newest_round_and_dry_run_leaves_the_tables(tmp_path, monkeypatch, capsys):
    court, hammer = _filled()
    jewelry, folder = _round(tmp_path, _sheet(court, hammer))
    older = jewelry / testprint.FOLDER / "2026-11-06 US6"
    older.mkdir()
    (older / "measurements.md").write_text("# old\n", encoding="utf-8")
    newer = jewelry / testprint.FOLDER / "2026-11-09 US4.5"                     # a later round, its sheet still blank
    newer.mkdir()
    (newer / "measurements.md").write_text(_sheet({}, {}), encoding="utf-8")
    monkeypatch.setenv("JEWELRY_DELIVER", str(jewelry))
    assert calibrate.newest_round(jewelry) == folder                              # the one being filled in
    (newer / "measurements.md").unlink()
    (folder / "measurements.md").write_text(_sheet({}, {}), encoding="utf-8")
    assert calibrate.newest_round(jewelry) == folder                              # none filled: the newest with a sheet
    (folder / "measurements.md").write_text(_sheet(court, hammer), encoding="utf-8")
    tcopy = tmp_path / "tables.json"
    tcopy.write_text(tables.TABLES_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    before = tcopy.read_text(encoding="utf-8")
    assert cli.main(["calibrate", "--dry-run", "--tables", str(tcopy)]) == 0
    out = capsys.readouterr().out
    assert out.strip().splitlines()[-1].startswith("==> PASSED  calibrate 2026-11-08 US4.5") and "dry run, nothing written" in out
    assert tcopy.read_text(encoding="utf-8") == before and (folder / "calibration.md").exists()
    assert cli.main(["calibrate", str(folder), "--tables", str(tcopy)]) == 0
    out = capsys.readouterr().out
    assert "3 table entries updated" in out and json.loads(tcopy.read_text(encoding="utf-8"))["settings"]["print_bloom_mm"]["status"] == "calibrated"
    assert cli.main(["calibrate", str(tmp_path / "nowhere")]) == 2
    assert "no measurement sheet" in capsys.readouterr().out


def _fill_workbook(path, court_rows, hammer_rows, settings=None, answers=None):
    """What Mark does in Excel: numbers into the yellow cells of the tables, words into the answers, values on the settings sheet."""
    from openpyxl import load_workbook
    wb = load_workbook(path)
    ws = wb["Print settings"]
    for i, (label, key) in enumerate(calibrate.SETTINGS_ROWS):
        if settings and key in settings:
            ws.cell(row=5 + i, column=2, value=settings[key])
    for name, rows in (("1 Court band", court_rows), ("2 Hammered band", hammer_rows)):
        w = wb[name]
        r = calibrate.TABLE_ROW
        while w.cell(row=r, column=1).value:
            label = str(w.cell(row=r, column=1).value)
            for j, v in enumerate(rows.get(label, [])):
                w.cell(row=r, column=2 + j, value=float(v))
            r += 1
        if answers and name in answers:
            r += 2                                                   # past the blank row and the Features header
            for a in answers[name]:
                if a is not None:
                    w.cell(row=r, column=2, value=a)
                r += 1
    wb.save(path)


def test_the_workbook_is_written_from_the_sheet_and_read_back_with_what_was_typed_in_it(tmp_path):
    jewelry, folder = _round(tmp_path, _sheet({}, {}, part_lines=False, blank_answers=True))   # a blank round, as testprint leaves it
    xlsx = calibrate.workbook_for_round(folder)
    assert xlsx == folder / "measurements.xlsx"
    from openpyxl import load_workbook
    wb = load_workbook(xlsx)
    assert wb.sheetnames == ["Print settings", "1 Court band", "2 Hammered band", calibrate.MD_SHEET] and wb[calibrate.MD_SHEET].sheet_state == "hidden"
    w = wb["1 Court band"]
    assert w["B1"].value == COURT_STEM and w["A7"].value == "Bore Ø, inside jaws (×3)" and w["E7"].value == 15.288    # the stem from the README
    assert w["A8"].value == "Mandrel size it stops at" and w["E8"].value == 4.5 and w["E14"].value == 0.26            # a size; the weight's resin g
    assert w["F7"].value.startswith("=IF(COUNT(B7:D7)") and w["G7"].value.startswith("=IF(OR(")
    labels = [w.cell(row=r, column=1).value for r in range(7, 15)]
    assert labels == [l for l, _ in testprint.COMMON_ROWS + tuple(testprint.PARTS[0].rows) + (testprint.WEIGHT_ROW,)]
    feats = [w.cell(row=r, column=1).value for r in range(17, 25)]
    assert feats[0] == "Beads: all present?" and feats[1] == "Missing or merged in a quarter turn:" and "Nubs sanded flush?" in feats
    assert len([f for f in feats if f]) == 8                                       # one row per blank: 3 + 1 + 3 + 1
    blank = calibrate.read_round(folder)
    assert not any(ps.rows for ps in blank.parts)                                  # the workbook holds nothing yet: the md is read
    court, hammer = _filled()
    _fill_workbook(xlsx, court, hammer, settings={"layer_um": 50, "exposure_s": "2.5", "as_is": "yes", "scale_g": 0.001},
                   answers={"1 Court band": ["yes", "none", "round", None, "slight at two tips", "yes", "yes", "no"]})
    sheet = calibrate.read_round(folder)
    assert sheet.path == xlsx and [ps.stem for ps in sheet.parts] == [COURT_STEM, HAMMER_STEM]
    assert sheet.settings["layer_um"] == "50" and sheet.settings["exposure_s"] == "2.5" and sheet.settings["scale_g"] == "0.001"
    assert sheet.parts[0].rows["Bore Ø, inside jaws (×3)"] == [float(x) for x in court["Bore Ø, inside jaws (×3)"]]
    assert sheet.parts[1].rows["Mandrel size it stops at"] == [4.25, 4.25, 4.25] and sheet.parts[1].rows["Weight (g)"] == [0.306, 0.306]
    assert sheet.parts[0].lines[0] == "Beads: all present? yes  Missing or merged in a quarter turn: none  Shape (round / blobby / flat): round"
    assert sheet.parts[0].lines[-2].endswith("Nubs sanded flush? yes") and sheet.parts[0].lines[-1].endswith("unsupported? no")
    assert sheet.parts[0].unanswered == 1 and sheet.parts[1].unanswered == 3
    cal = calibrate.calibrate(folder)
    assert cal.fit.sound and cal.fit.shrink_pct == pytest.approx(100 * TRUE_SHRINK, abs=0.1) and cal.parts[0].supports["swelling"] == "slight at two tips"
    assert cal.fit.bloom_mm == pytest.approx(TRUE_BLOOM, abs=0.006) and cal.density is not None


def test_the_cli_writes_a_workbook_for_a_round_and_testprint_writes_one_with_every_round(tmp_path, monkeypatch, capsys):
    jewelry, folder = _round(tmp_path, _sheet({}, {}), with_manifest=False)
    monkeypatch.setenv("JEWELRY_DELIVER", str(jewelry))
    assert cli.main(["calibrate", str(folder), "--workbook"]) == 0
    out = capsys.readouterr().out
    assert (folder / "measurements.xlsx").exists() and out.strip().splitlines()[-1].startswith("==> PASSED  workbook")
    assert "write_round" in dir(testprint) and "calibrate.workbook_for_round" in Path(testprint.__file__).read_text(encoding="utf-8")


def test_each_part_tab_carries_its_measurement_sketch(tmp_path):
    """Mark, 9 Nov: "terms like width are vague" - a picture per part of where each row is measured, in the sheet's words,
    on its tab and in the folder."""
    from openpyxl import load_workbook
    from ntopjewel import sketch
    jewelry, folder = _round(tmp_path, _sheet({}, {}, part_lines=False, blank_answers=True))
    xlsx = calibrate.workbook_for_round(folder)
    pngs = sorted(p.name for p in folder.glob("measure_*.png"))
    assert pngs == ["measure_court.png", "measure_hammered.png"]
    wb = load_workbook(xlsx)
    assert [len(wb[n]._images) for n in ("1 Court band", "2 Hammered band")] == [1, 1] and len(wb["Print settings"]._images) == 0
    assert "Where each row is measured" in str(wb["1 Court band"]["I4"].value)
    ser = calibrate.parse_design("bore Ø 15.288; band 2.8 wide × 2 thick at the head, 2 × 1.5 at the bottom; 21.8 × 19.3 × 6.2 mm overall; 272.6 mm³ (0.31 g of resin).")
    out = sketch.sketch("seraphine", ser, tmp_path / "s.png", "4.5")
    assert out.exists() and out.stat().st_size > 20000


def test_two_thickness_rows_give_the_cure_through_depth(tmp_path):
    """13 Nov 2026: the resin cures beyond each layer, so a ring printed on edge is thicker at its printed bottom than at
    its side; the difference is print_cure_through_mm, which the preparation then takes off every vat-facing surface."""
    court, hammer = _filled()
    court["Band thickness at the printed bottom, where it stood on its supports (×2)"] = ["1.52", "1.50"]
    court["Band thickness at the side, half way up as printed (×2)"] = ["1.31", "1.29"]
    jewelry, folder = _round(tmp_path, _sheet(court, hammer))
    cal = calibrate.calibrate(folder, today=datetime.date(2026, 11, 13))
    assert cal.cure_through == pytest.approx(0.21, abs=1e-6) and cal.fit.sound and cal.fit.n == 21      # the two rows are not in the fit
    assert "cure-through +0.210 mm" in cal.text()
    tcopy = tmp_path / "tables.json"
    tcopy.write_text(tables.TABLES_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    assert "settings.print_cure_through_mm" in calibrate.apply(cal, tcopy)
    doc = json.loads(tcopy.read_text(encoding="utf-8"))
    assert doc["settings"]["print_cure_through_mm"] == {**doc["settings"]["print_cure_through_mm"], "value": 0.21, "status": "calibrated"}
    assert tables.SETTINGS["print_cure_through_mm"] == 0.0 and tables.SETTINGS["support_min_spacing_mm"] == 1.5
    court["Band thickness at the printed bottom, where it stood on its supports (×2)"] = ["2.4"]          # a slip: not written
    j2, f2 = _round(tmp_path / "b", _sheet(court, hammer))
    cal = calibrate.calibrate(f2)
    assert "settings.print_cure_through_mm" not in calibrate.apply(cal, tcopy) and "not written" in cal.text()
