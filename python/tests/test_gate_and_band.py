import json
import math

import pytest
import trimesh

from ntopjewel import band, catalog, gate, ntopcl, runs, tables


def _band_mesh(r_in=8.255, r_out=9.555, width=4.0):
    return trimesh.creation.annulus(r_min=r_in, r_max=r_out, height=width, sections=720)


def test_gate_passes_a_clean_band(tmp_path):
    m = _band_mesh()
    p = tmp_path / "band.stl"
    m.export(p)
    rep = gate.check(p, expect_inner=16.51, expect_outer=19.11, expect_width=4.0,
                     expect_volume=gate.band_volume_mm3(16.51, 19.11, 4.0), wall_samples=600)
    assert rep.passed, rep.text()
    assert rep.axis == "z" and rep.shells == 1 and rep.watertight
    assert rep.inner_diameter_mm == pytest.approx(16.51, abs=0.01)
    assert rep.width_mm == pytest.approx(4.0, abs=1e-6)
    assert rep.thickness["median"] == pytest.approx(1.3, abs=0.05)       # radial wall of the band
    assert rep.weights_g["sterling"] == pytest.approx(tables.weight_g(rep.volume_mm3, "sterling"), abs=0.01)
    assert (tmp_path / "band.gate.json").exists()


def test_gate_fails_open_mesh_and_wrong_size(tmp_path):
    m = _band_mesh()
    m.faces = m.faces[:-50]          # knock a hole in it
    p = tmp_path / "broken.stl"
    m.export(p)
    rep = gate.check(p, expect_inner=17.0, wall_samples=0, write_report=False)
    names = {c.name: c.ok for c in rep.checks}
    assert not rep.passed and names["watertight"] is False and names["inner diameter"] is False


def test_gate_flags_thin_wall(tmp_path):
    m = _band_mesh(r_in=8.0, r_out=8.3)     # 0.3 mm wall
    p = tmp_path / "thin.stl"
    m.export(p)
    rep = gate.check(p, wall_samples=600, write_report=False)
    assert not rep.passed
    assert any(c.name == "wall thickness" and not c.ok for c in rep.checks)


def test_band_spec_math():
    s = band.BandSpec(size=6, width_mm=4, thickness_mm=1.3, profile="court")
    assert s.inner_diameter_mm == pytest.approx(16.5068)
    assert s.outer_radius_mm == pytest.approx(16.5068 / 2 + 1.3)
    assert s.label == "US6" and s.stem.startswith("ring_band_court_US6_w4_t1.3_") and len(s.spec_id) == 8
    assert band.BandSpec(size="L", system="UK").label == "UKL"
    assert band.BandSpec(size=6, thickness_mm=0.8).validate()
    # court on a 1.3 mm band: dome 0.325, comfort 0.286, edge 0.25
    assert s.dome == pytest.approx(0.325) and s.comfort == pytest.approx(0.286)
    assert s.edge_thickness_mm == pytest.approx(1.3 - 0.325 - 0.286)
    rd, td = s.dome_torus
    assert td == pytest.approx((4 + 0.325 ** 2) / (2 * 0.325))          # (W²/4 + d²) / 2d
    assert rd == pytest.approx(s.outer_radius_mm - td)
    rc, tc = s.comfort_torus
    assert rc == pytest.approx(s.bore_radius_mm + tc)
    ins = s.notebook_inputs("x")
    assert ins["Z Top"] == 2.0 and ins["Z Bottom"] == -2.0 and ins["Edge Round Inward"] == -0.25
    assert set(ins) == {"Outer Radius", "Bore Radius", "Z Top", "Z Bottom", "Dome Ring Radius", "Dome Tube Radius",
                        "Comfort Ring Radius", "Comfort Tube Radius", "Edge Round", "Edge Round Inward",
                        "Mesh Tolerance", "Output Path"}
    assert s.validate() == []


def test_profile_presets_and_limits():
    for name in band.PROFILES:
        assert band.BandSpec(size=6, profile=name).validate() == [], name
    flat = band.BandSpec(size=6, profile="flat")
    assert flat.dome == band.MIN_SAGITTA and flat.comfort == band.MIN_SAGITTA
    rd, td = flat.dome_torus                      # torus centred on the outer surface, swallowing the section
    assert rd == pytest.approx(flat.outer_radius_mm) and td > (1.3 ** 2 + 4) ** 0.5
    rc, tc = flat.comfort_torus                   # torus centred on the bore, swallowing the section
    assert rc == pytest.approx(flat.bore_radius_mm) and tc > (1.3 ** 2 + 4) ** 0.5
    assert flat.warnings() == []
    thin = band.BandSpec(size=6, thickness_mm=1.0, profile="half-round")      # edge would be 0.4 mm
    assert any("edge would be" in p for p in thin.validate())
    assert band.BandSpec(size=6, profile="court", edge_round_mm=0.6).validate()  # round too big for the edge
    with pytest.raises(ValueError, match="unknown profile"):
        band.BandSpec(size=6, profile="octagonal").dome
    wide = band.BandSpec(size=6, width_mm=8, thickness_mm=1.6, profile="court", dome_mm=0.3)
    assert wide.warnings() and "ring radius" in wide.warnings()[0]              # shallow dome, wide band


def test_profile_notebook_inputs_match_catalog():
    cat = catalog.load("ring_band_profile")
    inputs = cat.build_inputs(band.BandSpec(size=6).notebook_inputs("C:\\o\\b.stl"))
    assert len(inputs) == 12 and all(e["name"] in cat.inputs for e in inputs)


def test_band_end_to_end_with_fake_ntopcl(fake_ntopcl, profile_notebook, tmp_path, monkeypatch):
    """The simulated nTop builds the designed court section: every hard check passes, including
    the design-volume cross-check, and the run leaves its evidence in a fresh run directory."""
    monkeypatch.setenv("JEWELRY_OUT", str(tmp_path / "out"))
    spec = band.BandSpec(size=6, width_mm=4.0, thickness_mm=1.3, profile="court")
    res = band.build(spec, tmp_path / "out" / "band", notebook=profile_notebook)
    assert res.status == gate.PASSED and res.ok, res.text()
    assert res.stl.name == f"{spec.stem}.stl" and res.stl.exists()
    assert res.run_dir == tmp_path / "out" / "band" / spec.stem / res.run_id and res.stl.parent == res.run_dir
    assert res.ntop_volume_mm3 == pytest.approx(spec.design_volume_mm3(), rel=0.01)       # the section, not an annulus
    assert res.gate.inner_diameter_mm == pytest.approx(spec.inner_diameter_mm, abs=0.02)
    checks = {c.name: c for c in res.gate.checks}
    assert checks["design volume"].ok and checks["volume"].ok and checks["wall thickness"].ok
    report = json.loads((res.run_dir / f"{spec.stem}.report.json").read_text(encoding="utf-8"))
    assert report["status"] == "passed" and report["spec_id"] == spec.spec_id and report["notebook"]["sha256"]
    assert report["environment"]["ntopjewel"] and report["environment"]["ntopcl"] == "6.3.3"
    assert "mm^3" in res.run.summary()
    assert math.isclose(res.run.log.total_block_ms, 6)


def test_band_delivery_carries_its_evidence(fake_ntopcl, profile_notebook, tmp_path, monkeypatch):
    monkeypatch.setenv("JEWELRY_DELIVER", str(tmp_path / "Jewelry"))
    spec = band.BandSpec(size=7, profile="flat")
    res = band.build(spec, tmp_path / "o", notebook=profile_notebook, deliver=True, deliver_project="Bands")
    folder = tmp_path / "Jewelry" / "Bands" / spec.stem
    assert res.delivered == folder / f"{spec.stem}.stl" and res.delivered.exists()
    names = {p.name for p in folder.iterdir()}
    assert {f"{spec.stem}.input.json", f"{spec.stem}.gate.json", f"{spec.stem}.report.json", "manifest.json"} <= names
    man = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert man["status"] == "passed" and man["sha256"] and man["notebook"]["sha256"] and man["delivered_at"]
    assert man["design"]["profile"] == "flat" and man["inputs"]["Bore Radius"] == spec.notebook_inputs("")["Bore Radius"]


def test_wrong_profile_is_rejected_not_delivered(fake_ntopcl, profile_notebook, tmp_path, monkeypatch):
    """A notebook that ignores the tori builds a flat annulus for a court spec: every dimension
    check passes and nTop's own volume agrees with its mesh - only the design-volume
    cross-check can catch it, so it is a hard FAIL and nothing is delivered."""
    monkeypatch.setenv("JEWELRY_DELIVER", str(tmp_path / "Jewelry"))
    monkeypatch.setenv("FAKE_NTOPCL_SHAPE", "annulus")
    spec = band.BandSpec(size=6, profile="court")
    res = band.build(spec, tmp_path / "o", notebook=profile_notebook, deliver=True)
    assert res.status == gate.FAILED and not res.ok and res.delivered is None
    checks = {c.name: c for c in res.gate.checks}
    assert checks["inner diameter"].ok and checks["outer diameter"].ok and checks["width"].ok and checks["volume"].ok
    assert not checks["design volume"].ok and "+1" in checks["design volume"].detail      # ~ +19 %
    assert not (tmp_path / "Jewelry").exists() and any("not delivered" in n for n in res.notes)
    assert "FAIL" in res.text() and "status: FAILED" in res.text()


def test_missing_measurement_is_incomplete_not_delivered(fake_ntopcl, profile_notebook, tmp_path, monkeypatch):
    """No nTop volume -> the design cannot be cross-checked -> INCOMPLETE, which is not a pass."""
    monkeypatch.setenv("JEWELRY_DELIVER", str(tmp_path / "Jewelry"))
    monkeypatch.setenv("FAKE_NTOPCL_VOLUME", "none")
    res = band.build(band.BandSpec(size=6, profile="court"), tmp_path / "o", notebook=profile_notebook, deliver=True)
    assert res.status == gate.INCOMPLETE and not res.ok and res.delivered is None
    dv = [c for c in res.gate.checks if c.name == "design volume"][0]
    assert dv.status == gate.INCOMPLETE and not dv.ok and "no volume" in dv.detail
    assert "INCOMPLETE" in res.text() and "[INC ]" in res.gate.text()
    assert not (tmp_path / "Jewelry").exists()


def test_unmeasured_wall_is_incomplete(tmp_path):
    """The thickness check that cannot run is INCOMPLETE (hard), no longer an advisory pass."""
    import trimesh
    m = trimesh.creation.annulus(r_min=8.0, r_max=9.3, height=4.0, sections=180)
    stl = tmp_path / "ring.stl"
    m.export(stl)
    rep = gate.check(stl, expect_inner=16.0, wall_samples=0)
    wall = [c for c in rep.checks if c.name == "wall thickness"][0]
    assert wall.status == gate.INCOMPLETE and wall.hard and not wall.ok
    assert rep.status == gate.INCOMPLETE and not rep.passed and rep.incomplete
    assert gate.check(stl, expect_inner=16.0).passed                        # measured: passes


def test_stale_export_never_passes_for_a_new_run(fake_ntopcl, profile_notebook, tmp_path, monkeypatch):
    """Run 1 exports; run 2's notebook writes nothing. Run 2 must fail even though run 1's STL
    sits in the sibling run directory with the same name."""
    spec = band.BandSpec(size=6, profile="court")
    first = band.build(spec, tmp_path / "o", notebook=profile_notebook)
    assert first.ok and first.stl.exists()
    monkeypatch.setenv("FAKE_NTOPCL_EXPORT", "0")
    with pytest.raises(ntopcl.NtopclError, match="was not written"):
        band.build(spec, tmp_path / "o", notebook=profile_notebook)
    runs_ = sorted(p for p in (tmp_path / "o" / spec.stem).iterdir() if p.is_dir())
    assert len(runs_) == 2 and first.stl.exists() and not (runs_[-1] / f"{spec.stem}.stl").exists()
    # and a file that predates the run is refused even at the expected path
    old = tmp_path / "old.stl"
    old.write_bytes(b"x")
    import os, time
    os.utime(old, (time.time() - 60, time.time() - 60))
    with pytest.raises(FileNotFoundError, match="predates"):
        runs.require_fresh(old, time.time())


def test_variants_never_share_a_name():
    base = band.BandSpec(size=6, profile="court")
    others = [band.BandSpec(size=6, profile="court", width_mm=5.0), band.BandSpec(size=6, profile="court", thickness_mm=1.5),
              band.BandSpec(size=6, profile="court", dome_mm=0.5), band.BandSpec(size=6, profile="court", edge_round_mm=0.15),
              band.BandSpec(size=6, profile="court", allowance_mm=0.1), band.BandSpec(size=6, profile="d-shape"),
              band.BandSpec(size=6.5, profile="court")]
    stems = {s.stem for s in [base, *others]}
    assert len(stems) == len(others) + 1
    assert base.stem == band.BandSpec(size=6, profile="court").stem            # stable for the same design
    assert base.stem.startswith("ring_band_court_US6_w4_t1.3_") and others[0].stem.startswith("ring_band_court_US6_w5_t1.3_")


def test_profile_booleans_give_the_designed_section():
    """Sample band ∩ dome ∩ comfort on an (r, z) grid: full thickness at the mid-plane, the designed
    edge thickness at the edges, and a flat profile untouched. (The first API build subtracted the
    comfort torus and produced a 0 mm shell - this is the guard against that.)"""
    import numpy as np
    r = np.linspace(0, 14, 5601)
    for name, mid, edge in (("court", 1.3, 1.3 - 0.325 - 0.286), ("flat", 1.3, 1.3)):
        s = band.BandSpec(size=6, profile=name)
        def thickness(zq):
            row = s.section_mask(r, zq)
            return r[row].max() - r[row].min() if row.any() else 0.0
        assert thickness(0.0) == pytest.approx(mid, abs=0.01), name
        assert thickness(1.999) == pytest.approx(edge, abs=0.02), name
        assert thickness(2.5) == 0.0                                   # nothing outside the band width
        assert 0 < thickness(1.0) <= mid + 1e-9
        # the section is one solid run of material at every height, never a split or a sliver
        for zq in (0.0, 0.5, 1.0, 1.5, 1.9):
            row = s.section_mask(r, zq)
            idx = np.flatnonzero(row)
            assert idx[-1] - idx[0] + 1 == len(idx), (name, zq)
            assert thickness(zq) >= edge - 0.02, (name, zq)
