import math

import pytest
import trimesh

from ntopjewel import band, gate, tables


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
    s = band.BandSpec(size=6, width_mm=4, thickness_mm=1.3)
    assert s.inner_diameter_mm == pytest.approx(16.5068)
    assert s.outer_radius_mm == pytest.approx(16.5068 / 2 + 1.3)
    assert s.label == "US6"
    assert band.BandSpec(size="L", system="UK").label == "UKL"
    assert band.BandSpec(size=6, thickness_mm=0.8).validate()


def test_band_end_to_end_with_fake_ntopcl(fake_ntopcl, band_notebook, tmp_path, monkeypatch):
    monkeypatch.setenv("JEWELRY_OUT", str(tmp_path / "out"))
    spec = band.BandSpec(size=6, width_mm=4.0, thickness_mm=1.3)
    res = band.build(spec, tmp_path / "out" / "band", notebook=band_notebook)
    assert res.ok, res.text()
    assert res.stl.name == "ring_band_US6.stl" and res.stl.exists()
    assert res.ntop_volume_mm3 == pytest.approx(res.analytic_volume_mm3)
    assert res.gate.inner_diameter_mm == pytest.approx(spec.inner_diameter_mm, abs=0.02)
    assert (tmp_path / "out" / "band" / "ring_band_US6.report.json").exists()
    assert "nTop volume" in res.text()
    assert math.isclose(res.run.log.total_block_ms, 6)


def test_band_delivery(fake_ntopcl, band_notebook, tmp_path, monkeypatch):
    monkeypatch.setenv("JEWELRY_DELIVER", str(tmp_path / "Jewelry"))
    res = band.build(band.BandSpec(size=7), tmp_path / "o", notebook=band_notebook, deliver=True, deliver_project="Bands")
    assert res.delivered == tmp_path / "Jewelry" / "Bands" / "ring_band_US7.stl"
    assert res.delivered.exists()
