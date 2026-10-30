"""Phase 3 step 1: the shaped shank - the law, the bar and the sweep, the gate, the notebook."""
import math

import pytest

from ntopjewel import band, catalog, gate, geom, shank


def spec(**kw):
    kw.setdefault("width_bottom_mm", 2.2)
    kw.setdefault("thickness_bottom_mm", 1.2)
    b = kw.pop("band", None) or band.BandSpec(size=6, profile="court", width_mm=4.0, thickness_mm=1.6, mesh_tolerance_mm=0.05)
    return shank.ShankSpec(b, **kw)


def test_the_taper_law():
    s = spec()
    assert s.validate() == [] and s.tapered
    assert s.width_at(0) == 4.0 and s.thickness_at(0) == 1.6                       # the head keeps the full section
    assert s.width_at(60) == 4.0 and s.width_at(-60) == 4.0                        # and so do the shoulders, to taper_from_deg
    assert s.width_at(180) == 2.2 and s.thickness_at(180) == 1.2                    # the bottom
    assert 2.2 < s.width_at(120) < 4.0 and s.width_at(120) == s.width_at(240)       # symmetric, in between
    assert s.width_at(120) == pytest.approx((4.0 + 2.2) / 2)                        # the cosine ease is at half way at half way
    assert s.width_at(170) > s.width_at(180) and s.width_at(181) == pytest.approx(s.width_at(179))   # smooth at the bottom
    plain = shank.ShankSpec(s.band)
    assert not plain.tapered and plain.width_at(180) == 4.0 and plain.stem != s.stem
    assert spec(taper_from_deg=0).width_at(90) == pytest.approx((4.0 + 2.2) / 2)


def test_validation_covers_the_thin_end():
    assert spec(width_bottom_mm=5.0).validate()                                     # wider at the bottom: refused
    assert spec(thickness_bottom_mm=0.8).validate()                                 # under the band floor at 180°
    assert spec(taper_from_deg=175).validate()
    thin = spec(thickness_bottom_mm=1.0)                                            # 1.0 mm court: edge too thin for the 0.25 round
    assert any("180°" in p for p in thin.validate())
    assert spec(thickness_bottom_mm=1.0, band=band.BandSpec(size=6, profile="court", width_mm=4.0, thickness_mm=1.6,
                                                             edge_round_mm=0.15)).validate() == []


def test_bar_and_sweep_agree():
    """The bar wrapped (what nTop does) is the sweep (the independent model): same volume, same
    sections; a plain shank is the band (Pappus)."""
    import trimesh
    s = spec()
    ring = s.design_mesh()
    assert ring.is_watertight and ring.body_count == 1
    bar = s.bar_mesh()
    assert bar.is_watertight
    L = s.wrap_length_mm
    assert bar.bounds[0][1] < -L / 2 and bar.bounds[1][1] > L                      # a turn and a half plus the margins
    one = trimesh.intersections.slice_mesh_plane(bar, [0, 1, 0], [0, 0, 0], cap=True)
    one = trimesh.intersections.slice_mesh_plane(one, [0, -1, 0], [0, L, 0], cap=True)
    assert geom.remap_cylindrical(one, L).volume == pytest.approx(ring.volume, rel=1e-4)
    for t in (0, 90, 180, 270):
        w, th = shank.section_profile(ring, t)
        assert (w, th) == pytest.approx(s.section_extents(t), abs=0.01)
        assert w == pytest.approx(s.width_at(t), abs=0.02) and th == pytest.approx(s.thickness_at(t), abs=0.02)
    plain = shank.ShankSpec(s.band)
    assert plain.design_volume_mm3() == pytest.approx(plain.band.design_volume_mm3(), rel=0.002)
    assert ring.extents[0] == pytest.approx(2 * s.band.bore_radius_mm + 1.6 + 1.2, abs=0.01)   # thick at the head, thin at the bottom
    assert ring.extents[2] == pytest.approx(4.0, abs=0.01)


def test_design_shank_passes_its_gate(tmp_path):
    s = spec()
    m = s.design_mesh()
    m.export(tmp_path / "s.stl")
    rep = shank.check_shank(s, tmp_path / "s.stl", float(m.volume))
    assert rep.status == "passed", rep.text()
    assert {"section profile", "design volume", "inner diameter", "width"} <= {c.name for c in rep.checks}


def test_an_unwrapped_or_untapered_export_is_caught(tmp_path):
    s = spec()
    plain = shank.ShankSpec(s.band).design_mesh()                                   # the right band, no taper
    plain.export(tmp_path / "p.stl")
    rep = shank.check_shank(s, tmp_path / "p.stl", float(plain.volume))
    assert rep.status == "failed" and {"section profile", "design volume"} <= {c.name for c in rep.failures()}


def test_inputs_match_the_catalog_and_identity():
    s = spec()
    v = s.notebook_inputs("B", "O")
    assert list(v) == list(catalog.load("ring_shank").inputs)
    assert v["Wrap Length"] == pytest.approx(2 * math.pi * (s.band.bore_radius_mm + 0.8), abs=1e-3)
    assert spec(taper_from_deg=45).stem != s.stem and spec(stations=72).stem != s.stem
    assert s.stem.startswith("ring_shank_court_US6_w4-2.2_t1.6-1.2_")


def test_shank_end_to_end_and_an_unwrapped_notebook_is_caught(fake_ntopcl, tmp_path, monkeypatch):
    nb = tmp_path / "ring_shank.ntop"
    nb.write_bytes(b"fake")
    monkeypatch.setenv("JEWELRY_DELIVER", str(tmp_path / "Jewelry"))
    res = shank.build(spec(), tmp_path / "out", notebook=nb, deliver=True, cast_metal="sterling")
    assert res.status == "passed", res.text()
    assert res.delivered and (res.delivered.parent / f"{res.spec.stem}.bar.stl").exists()
    monkeypatch.setenv("FAKE_NTOPCL_SHAPE", "nowrap")
    bad = shank.build(spec(), tmp_path / "out", notebook=nb)
    assert bad.status == "failed" and "section profile" in {c.name for c in bad.gate.failures()}


def test_cli_dry_run(capsys):
    from ntopjewel import cli
    assert cli.main(["shank", "--size", "6", "--thickness", "1.6", "--width-bottom", "2.2", "--thickness-bottom", "1.2", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "ring_shank_court_US6_w4-2.2_t1.6-1.2_" in out and "180°: width 2.200" in out and "Wrap Length" in out
    assert cli.main(["shank", "--size", "6", "--width-bottom", "6", "--dry-run"]) == 1


def test_recipe_builds_on_the_fake_notebook(tmp_path):
    from .fake_notebook import FakeNotebook
    from .test_notebook_api import load_recipe
    mod = load_recipe("ring_shank")
    params = mod.prepare({}, tmp_path)
    params.update({"save_to": str(tmp_path / "s.ntop"), "recipe_to": str(tmp_path / "s.json"), "test_output": str(tmp_path / "s.stl")})
    nb = FakeNotebook()
    res = mod.build(nb, params)
    b = res["blocks"]
    assert nb.inputs == mod.INPUT_ORDER and res["warnings"] == []
    assert nb.blocks[b["Shank"]]["wired"]["Body"][0] == b["Shank Bar"]
    assert nb.blocks[b["Shank"]]["wired"]["Y Mapping Length"][0] == b["Wrap Length"]


# ---- step 1b: the centreline and double bands ----------------------------------------------------
def court(width=3.0, thickness=1.5):
    return band.BandSpec(size=6, profile="court", width_mm=width, thickness_mm=thickness, mesh_tolerance_mm=0.05)


def test_the_centreline_laws():
    c = shank.ShankSpec(court(), dip_mm=1.5, dip_span_deg=70)
    assert c.validate() == [] and c.z_offset(0) == 1.5 and c.z_offset(70) == 0.0 and c.z_offset(180) == 0.0
    assert c.z_offset(35) == pytest.approx(0.75) and c.z_offset(-35) == c.z_offset(35)                 # a cosine bump, symmetric
    assert abs(c.z_offset(69) - c.z_offset(70)) < 0.005                                               # tangent at the span's end
    v = shank.ShankSpec(court(), dip_mm=2.0, dip_span_deg=60, dip_shape="chevron")
    assert v.z_offset(0) == 2.0 and v.z_offset(30) == pytest.approx(1.0) and v.z_offset(60) == 0.0     # a V
    assert v.section_bounds(0)[:2] == pytest.approx((0.5, 3.5), abs=0.01)                             # the 3 mm band centred 2 mm up
    assert v.overall_width_mm == pytest.approx(5.0, abs=0.01) and c.overall_width_mm == pytest.approx(4.5, abs=0.01)
    assert shank.ShankSpec(court()).overall_width_mm == pytest.approx(3.0, abs=0.01)
    assert v.stem != c.stem and "chevron2" in v.stem and "contour1.5" in c.stem
    assert shank.ShankSpec(court(), dip_mm=1.0, dip_shape="wave").validate()
    assert shank.ShankSpec(court(), dip_mm=12.0).validate()


def test_double_bands_and_bridges():
    d = shank.ShankSpec(court(), strands=2, gap_mm=0.6, bridges_deg=(180.0, 100.0, -100.0))
    assert d.validate() == [] and d.strand_centres == [-1.8, 1.8]
    assert d.section_bounds(0) == pytest.approx((-3.3, 3.3, court().bore_radius_mm, court().outer_radius_mm), abs=0.01)
    assert len(d.bridge_spans()) == 3 and d.bridge_spans()[0][3] < 0 < d.bridge_spans()[0][4]          # the bridge spans the gap
    ring = d.design_mesh()
    assert ring.is_watertight and ring.body_count == 1
    two = [shank.ShankSpec(court(), strands=2, gap_mm=0.6, bridges_deg=(180.0,)).strand_ring(k).volume for k in range(2)]
    assert ring.volume > sum(two)                                                                     # the bridges add metal
    assert ring.extents[2] == pytest.approx(6.6, abs=0.01)
    assert shank.ShankSpec(court(), strands=2, bridges_deg=()).validate()                             # two rings, no bridge: refused
    assert shank.ShankSpec(court(), strands=2, gap_mm=-0.5).validate()
    assert shank.ShankSpec(court(), strands=3).validate()
    w = shank.ShankSpec(court(), dip_mm=1.2, dip_span_deg=80, strands=2, gap_mm=0.4, mirror=True, bridges_deg=(180.0,))
    assert w.validate() == [] and w.z_offset(0, 0) == pytest.approx(-0.5) and w.z_offset(0, 1) == pytest.approx(0.5)   # a wishbone: the strands meet at the head
    assert w.design_mesh().is_watertight and w.design_mesh().body_count == 1
    assert shank.ShankSpec(court(), dip_mm=2.0, strands=2, gap_mm=0.4, mirror=True).validate()        # they would cross


@pytest.mark.parametrize("kind", ["chevron", "double", "wishbone"])
def test_shaped_designs_pass_their_gate_and_the_bar_agrees(kind, tmp_path):
    import trimesh
    s = {"chevron": shank.ShankSpec(court(), dip_mm=2.0, dip_span_deg=60, dip_shape="chevron"),
         "double": shank.ShankSpec(court(), width_bottom_mm=2.0, thickness_bottom_mm=1.2, strands=2, gap_mm=0.5, bridges_deg=(180.0, 90.0, 270.0)),
         "wishbone": shank.ShankSpec(court(), dip_mm=1.2, dip_span_deg=80, strands=2, gap_mm=0.4, mirror=True, bridges_deg=(180.0,))}[kind]
    m = s.design_mesh()
    m.export(tmp_path / "s.stl")
    rep = shank.check_shank(s, tmp_path / "s.stl", float(m.volume))
    assert rep.status == "passed", rep.text()
    bar = s.bar_mesh()
    assert bar.is_watertight
    L = s.wrap_length_mm
    one = trimesh.intersections.slice_mesh_plane(bar, [0, 1, 0], [0, -L / 730, 0], cap=True)
    one = trimesh.intersections.slice_mesh_plane(one, [0, -1, 0], [0, L - L / 730, 0], cap=True)
    assert geom.remap_cylindrical(one, L).volume == pytest.approx(m.volume, rel=2e-3)
    plain = shank.ShankSpec(s.band).design_mesh()                                                     # the same band, unshaped: caught
    plain.export(tmp_path / "p.stl")
    assert "section profile" in {c.name for c in shank.check_shank(s, tmp_path / "p.stl", float(plain.volume)).failures()}


def test_double_chevron_end_to_end(fake_ntopcl, tmp_path):
    nb = tmp_path / "ring_shank.ntop"
    nb.write_bytes(b"fake")
    s = shank.ShankSpec(court(), dip_mm=2.0, dip_span_deg=60, dip_shape="chevron", strands=2, gap_mm=0.6, bridges_deg=(180.0, 100.0, -100.0))
    res = shank.build(s, tmp_path / "out", notebook=nb)
    assert res.status == "passed", res.text()


def test_cli_shape_flags(capsys):
    from ntopjewel import cli
    assert cli.main(["shank", "--size", "6", "--width", "3", "--thickness", "1.5", "--dip", "2", "--dip-shape", "chevron",
                     "--double", "--gap", "0.6", "--bridges", "180,100,-100", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "chevron2_x2_" in out and "bridged at 180°, 100°, -100°" in out
    assert "  0°: width 3.000  thickness 1.500  centre z +0.200 / +3.800" in out            # the dip at the head
    assert "180°: width 3.000  thickness 1.500  centre z -1.800 / +1.800" in out            # none at the bottom
