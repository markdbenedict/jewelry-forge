import math

import pytest
import trimesh

from ntopjewel import band, catalog, gate, tables


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
    assert s.label == "US6" and s.stem == "ring_band_court_US6"
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
    monkeypatch.setenv("JEWELRY_OUT", str(tmp_path / "out"))
    spec = band.BandSpec(size=6, width_mm=4.0, thickness_mm=1.3, profile="court")
    res = band.build(spec, tmp_path / "out" / "band", notebook=profile_notebook)
    assert res.ok, res.text()
    assert res.stl.name == "ring_band_court_US6.stl" and res.stl.exists()
    assert res.ntop_volume_mm3 == pytest.approx(
        gate.band_volume_mm3(spec.inner_diameter_mm, 2 * spec.outer_radius_mm, 4.0), rel=1e-6)
    assert res.gate.inner_diameter_mm == pytest.approx(spec.inner_diameter_mm, abs=0.02)
    assert (tmp_path / "out" / "band" / "ring_band_court_US6.report.json").exists()
    assert "mm^3" in res.run.summary()
    assert math.isclose(res.run.log.total_block_ms, 6)


def test_band_delivery(fake_ntopcl, profile_notebook, tmp_path, monkeypatch):
    monkeypatch.setenv("JEWELRY_DELIVER", str(tmp_path / "Jewelry"))
    res = band.build(band.BandSpec(size=7, profile="flat"), tmp_path / "o", notebook=profile_notebook,
                     deliver=True, deliver_project="Bands")
    assert res.delivered == tmp_path / "Jewelry" / "Bands" / "ring_band_flat_US7.stl"
    assert res.delivered.exists()


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
