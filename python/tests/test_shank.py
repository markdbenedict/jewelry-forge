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
    assert {"section shape", "design volume", "inner diameter", "width"} <= {c.name for c in rep.checks}


def test_an_unwrapped_or_untapered_export_is_caught(tmp_path):
    s = spec()
    plain = shank.ShankSpec(s.band).design_mesh()                                   # the right band, no taper
    plain.export(tmp_path / "p.stl")
    rep = shank.check_shank(s, tmp_path / "p.stl", float(plain.volume))
    assert rep.status == "failed" and {"section shape", "design volume"} <= {c.name for c in rep.failures()}


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
    assert bad.status == "failed" and "section shape" in {c.name for c in bad.gate.failures()}


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
    assert nb.blocks[b["Shrunk"]]["wired"]["Body"][0] == b["Shank Bar"]                 # the opening on the bar ...
    assert nb.blocks[b["Shrunk"]]["wired"]["Distance"][0] == b["Edge Round Inward"]
    assert nb.blocks[b["Shrunk Body Mesh"]]["wired"]["Body"][0] == b["Shrunk"]          # ... re-distanced through a mesh
    assert nb.blocks[b["Shrunk Body Mesh"]]["wired"]["Tolerance"][0] == b["Mesh Tolerance"]
    assert nb.blocks[b["Shrunk Body"]]["wired"]["Mesh"][0] == b["Shrunk Body Mesh"]
    assert nb.blocks[b["Opened"]]["wired"]["Body"][0] == b["Shrunk Body"]
    assert nb.blocks[b["Opened"]]["wired"]["Distance"][0] == b["Edge Round"]
    assert nb.blocks[b["Shank"]]["wired"]["Body"][0] == b["Opened"]                     # ... then the wrap
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
    assert "section shape" in {c.name for c in shank.check_shank(s, tmp_path / "p.stl", float(plain.volume)).failures()}


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


# ---- step 1c: split shanks and ropes -------------------------------------------------------------
def test_the_split_law_and_its_limits():
    s = shank.ShankSpec(court(width=4.0), split_mm=1.6, split_span_deg=90)
    assert s.validate() == [] and s.split_at(0) == 1.6 and s.split_at(45) == pytest.approx(0.8) and s.split_at(90) == 0.0
    assert s.split_at(-45) == s.split_at(45) and s.split_at(180) == 0.0
    v = shank.ShankSpec(court(width=4.0), split_mm=1.6, split_span_deg=90, split_shape="chevron")
    assert v.split_at(45) == pytest.approx(0.8) and v.split_at(30) == pytest.approx(1.6 * 2 / 3)       # linear
    assert "split1.6" in s.stem and v.stem != s.stem
    assert shank.ShankSpec(court(width=3.0), split_mm=1.6).validate()                                # 0.7 mm halves: refused
    assert shank.ShankSpec(court(width=4.0), split_mm=1.6, strands=2).validate()                     # not with --double
    assert shank.ShankSpec(court(width=4.0), split_mm=1.6, split_span_deg=5).validate()
    assert shank.ShankSpec(court(width=4.0), split_mm=1.6, split_shape="wave").validate()
    ring = s.design_mesh()
    assert ring.is_watertight and ring.body_count == 1
    assert ring.volume < shank.ShankSpec(court(width=4.0)).design_mesh().volume                      # the slot takes metal out
    z0, z1, r0, r1 = s.section_bounds(0)
    b = s.band
    assert (z0, z1) == pytest.approx((-2.0, 2.0), abs=0.01)                                          # the outside is the band's ...
    assert (r0, r1) == pytest.approx((b.bore_radius_at(1.05), b.outer_radius_at(1.05)), abs=0.01)   # ... reached 0.8 + 0.25 off the mid-plane: the slot and its fillets
    assert s.section_bounds(180)[2:] == pytest.approx((b.bore_radius_mm, b.outer_radius_mm), abs=0.01)
    two = s.section_shape(0)
    assert len(two.geoms) == 2 and s.section_shape(180).geom_type == "Polygon"
    assert s.slot_half_at(0) == 0.8 and s.slot_half_at(89) > 0 == s.slot_half_at(90) and s.slot_half_at(271) > 0
    assert s.slot_half_at(85) == pytest.approx(0.2)                                                   # never narrower than the round end


def test_the_opening_and_what_it_takes_off_sharp_edges():
    """The notebook opens the wrapped body by the band's edge round: nothing on a plain band (its
    section is rounded that much already), a slot's four edges on a split, a bridge's on a double."""
    plain = shank.ShankSpec(court(width=4.0))
    assert plain.edge_round == 0.25 and plain.sharp_edge_round_mm3() == 0.0
    assert plain.notebook_inputs("B", "O")["Edge Round Inward"] == -0.25
    s = shank.ShankSpec(court(width=4.0), split_mm=1.6, split_span_deg=90)
    sharp = shank.ShankSpec(band.BandSpec(size=6, profile="court", width_mm=4.0, thickness_mm=1.5, edge_round_mm=0.0),
                            split_mm=1.6, split_span_deg=90)
    r_mid = s.band.bore_radius_mm + 0.75
    edges = 4 * math.radians(180) * r_mid                                                             # two walls x bore + outside, over 180°
    fillets = 0.25 ** 2 * (1 - math.pi / 4) * edges                                                  # a square corner: e² (1 - π/4) per mm
    plain, plain_sharp = shank.ShankSpec(court(width=4.0)), shank.ShankSpec(sharp.band)
    slot_fillets = (plain.design_volume_mm3() - s.design_volume_mm3()) - (plain_sharp.design_volume_mm3() - sharp.design_volume_mm3())
    assert 1.0 < slot_fillets / fillets < 1.45                                                        # the lofted halves carry them: 2.0 mm³ (the comfort relief and the
                                                                                                      # dome tilt the corners past 90°, so more than the square-corner figure)
    assert s.sharp_edge_round_mm3() < 0.3                                                             # so hardly a sharp edge is left to the notebook
    assert s.expected_volume_mm3() == pytest.approx(s.design_volume_mm3() - s.sharp_edge_round_mm3() - s.opening_overcut_mm3())
    assert 0.5 < s.opening_overcut_mm3() < 1.5 and plain.opening_overcut_mm3() < s.opening_overcut_mm3()   # the mesher's chamfer on every round (mesh tolerance 0.05 here)
    assert shank.ShankSpec(court(), rope=2).opening_overcut_mm3() == 0.0
    d = shank.ShankSpec(court(), strands=2, gap_mm=0.6, bridges_deg=(180.0, 100.0, -100.0))
    assert 0 < d.sharp_edge_round_mm3() < 1.0                                                         # the bridges' end faces
    assert d.bridge_spans()[0][1] > d.band.bore_radius_mm and d.bridge_spans()[0][2] < d.band.outer_radius_mm   # flush with the strands' edges
    rope = shank.ShankSpec(court(), rope=2)
    assert rope.edge_round == 0.0 and rope.notebook_inputs("B", "O")["Edge Round Inward"] == 0.0
    assert shank.ShankSpec(court(), strands=2, bridge_mm=0.5).validate()                             # 2 x 0.25 would open a 0.5 mm bridge away


def test_the_rope():
    r = shank.ShankSpec(court(), rope=2, rope_turns=10, rope_strand_mm=1.2)
    assert r.validate() == [] and r.rope_radius == 0.6 and r.rope_offset == pytest.approx(0.42)
    assert r.rope_centre_radius == pytest.approx(court().bore_radius_mm + 1.02)                        # the inner strand touches the bore
    c0, c1 = r.rope_centre(0, 0), r.rope_centre(0, 1)
    assert c0 == pytest.approx((r.rope_centre_radius + 0.42, 0.0)) and c1 == pytest.approx((r.rope_centre_radius - 0.42, 0.0), abs=1e-9)
    assert r.rope_centre(9, 0)[1] == pytest.approx(0.42 * math.sin(math.radians(90)))                 # a quarter twist 9° on, at 10 turns
    assert r.rope_stations == 360 and r.wrap_length_mm == pytest.approx(2 * math.pi * r.rope_centre_radius)
    assert r.stem.startswith("ring_shank_rope2x10_US6_d1.2_")
    ring = r.design_mesh()
    assert ring.is_watertight and ring.body_count == 1
    two = sum(r.rope_tube_ring(k).volume for k in range(2))
    assert 0.8 * two < ring.volume < two                                                              # overlapping strands
    assert r.overall_width_mm == pytest.approx(2.04) and r.outer_radius_mm == pytest.approx(r.rope_centre_radius + 1.02)
    three = shank.ShankSpec(court(), rope=3, rope_turns=8, rope_strand_mm=1.0, rope_offset_frac=0.7)
    assert three.validate() == [] and three.design_mesh().body_count == 1                             # staggered stations: no void at the seam
    assert shank.ShankSpec(court(), rope=4).validate()
    assert shank.ShankSpec(court(), rope=2, rope_strand_mm=0.6).validate()
    assert shank.ShankSpec(court(), rope=2, rope_offset_frac=1.2).validate()
    assert shank.ShankSpec(court(), rope=2, width_bottom_mm=2.0).validate()                           # a rope takes no taper


@pytest.mark.parametrize("kind", ["split", "split-chevron-taper", "rope2", "rope3"])
def test_split_and_rope_designs_pass_their_gate_and_the_bar_agrees(kind, tmp_path):
    import trimesh
    s = {"split": shank.ShankSpec(court(width=4.0), split_mm=1.6, split_span_deg=90),
         "split-chevron-taper": shank.ShankSpec(court(width=4.0), width_bottom_mm=2.4, thickness_bottom_mm=1.2, split_mm=1.4,
                                                split_span_deg=70, split_shape="chevron"),
         "rope2": shank.ShankSpec(court(), rope=2, rope_turns=10, rope_strand_mm=1.2),
         "rope3": shank.ShankSpec(court(), rope=3, rope_turns=8, rope_strand_mm=1.0, rope_offset_frac=0.7)}[kind]
    assert s.validate() == []
    m = s.design_mesh()
    m.export(tmp_path / "s.stl")
    rep = shank.check_shank(s, tmp_path / "s.stl", s.expected_volume_mm3())
    assert rep.status == "passed", rep.text()
    bar = s.bar_mesh()
    assert bar.is_watertight and bar.body_count == 1
    L = s.wrap_length_mm
    one = trimesh.intersections.slice_mesh_plane(bar, [0, 1, 0], [0, -L / 730, 0], cap=True)
    one = trimesh.intersections.slice_mesh_plane(one, [0, -1, 0], [0, L - L / 730, 0], cap=True)
    assert geom.remap_cylindrical(one, L).volume == pytest.approx(m.volume, rel=3e-3)
    if not s.rope:
        plain = shank.ShankSpec(s.band).design_mesh()                                                 # the same band, no slot: caught
        plain.export(tmp_path / "p.stl")
        assert "design volume" in {c.name for c in shank.check_shank(s, tmp_path / "p.stl", float(plain.volume)).failures()}


@pytest.mark.parametrize("kind", ["split", "rope"])
def test_split_and_rope_end_to_end(kind, fake_ntopcl, tmp_path):
    nb = tmp_path / "ring_shank.ntop"
    nb.write_bytes(b"fake")
    s = (shank.ShankSpec(court(width=4.0), split_mm=1.6, split_span_deg=90) if kind == "split"
         else shank.ShankSpec(court(), rope=2, rope_turns=10, rope_strand_mm=1.2))
    res = shank.build(s, tmp_path / "out", notebook=nb)
    assert res.status == "passed", res.text()
    assert res.spec.notebook_inputs("B", "O")["Edge Round"] == (0.25 if kind == "split" else 0.0)


def test_cli_split_and_rope_flags(capsys):
    from ntopjewel import cli
    assert cli.main(["shank", "--size", "6", "--width", "4", "--thickness", "1.5", "--split", "1.6", "--split-span", "90", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "_split1.6_" in out and "  0°: width 4.000  thickness 1.500  centre z +0.000  split 1.600" in out
    assert cli.main(["shank", "--size", "6", "--rope", "2", "--rope-turns", "10", "--rope-strand", "1.2", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "ring_shank_rope2x10_US6_d1.2_" in out and "Edge Round: 0.0" in out
    assert cli.main(["shank", "--size", "6", "--width", "3", "--split", "1.6", "--dry-run"]) == 1


# ---- step 1e: Celtic knotwork ---------------------------------------------------------------------
def test_the_interlace_rule():
    """Crossings found once each, over and under solved to alternate along every strand with one
    strand over at every crossing, the radial law ±1 at the crossings and 0 midway; a diagram that
    cannot alternate is refused."""
    import numpy as np
    from ntopjewel import knotwork as kw
    L = 55.0
    for n, R in ((2, 1), (2, 4), (3, 4), (4, 3)):
        st = kw.plait_strands(n, R, 1.4, L, 72 * R)
        xs = kw.crossings(st)
        lace = kw.interlace(st, xs)
        assert lace.problems == [] and len(xs) == R * n * (n - 1)                                 # every pair crosses 2R times
        assert all(lace.count(k) == 2 * R * (n - 1) for k in range(n))
        for c in xs:
            a, b = lace.params[c.i].index(c.s_i), lace.params[c.j].index(c.s_j)
            assert lace.over[c.i][a] != lace.over[c.j][b]                                        # one over, one under
        for k in range(n):
            ov = lace.over[k]
            assert all(ov[q] != ov[q + 1] for q in range(len(ov) - 1)) and ov[0] != ov[-1]        # alternating round the loop
            cs = np.array(lace.params[k])
            assert np.allclose(np.abs(lace.depth(k, cs)), 1.0)
            assert np.allclose(lace.depth(k, (cs[:-1] + cs[1:]) / 2), 0.0, atol=1e-12)
            assert np.abs(lace.depth(k, np.linspace(0, st[k].length, 500))).max() <= 1.0 + 1e-12
    assert kw.plait_crossing_angle_deg(1.4, 4, L) == pytest.approx(65.2, abs=0.1)
    assert kw.pair_openings(kw.plait_strands(3, 4, 1.4, L, 288))[(0, 1)] == pytest.approx(math.sqrt(3) * 1.4, abs=0.01)
    # an open strand that crosses a closed one once leaves it with an odd count: no alternation
    closed = kw.plait_strands(1, 1, 1.0, L, 72)[0]
    straight = kw.Strand(np.array([[5.0, 0.0], [35.0, 0.0]]), closed=False)
    lace = kw.interlace([closed, straight])
    assert len(lace.crossings) == 1 and lace.problems and "odd" in lace.problems[0]
    assert lace.depth(1, np.array([0.0, 30.0])).tolist() == [0.0, 0.0]                           # an open strand's ends at mid-depth
    # a strand running along another is one touch, not a crossing storm
    assert len(kw.crossings([straight, kw.Strand(np.array([[10.0, 0.0], [20.0, 0.0]]), closed=False)])) == 1


def knot(**kw):
    b = kw.pop("band", None) or band.BandSpec(size=6, profile="court", width_mm=4.0, thickness_mm=1.6, mesh_tolerance_mm=0.1)
    kw.setdefault("knot", "plait")
    return shank.ShankSpec(b, **kw)


def test_the_plait():
    from ntopjewel import knotwork as kw
    s = knot(knot_strands=3, knot_repeats=4, knot_strand_mm=1.2)
    assert s.validate() == [] and s.warnings() == []
    b = s.band
    assert s.knot_thickness == pytest.approx(0.85) and s.knot_rise == pytest.approx(0.375)       # two strands fused 0.1 make 1.6
    assert s.knot_mid_radius == pytest.approx(b.bore_radius_mm + 0.8) and s.knot_amplitude == pytest.approx(1.4)
    assert s.knot_points == 288 and s.edge_round == 0.0 and s.opening_chamfer_mm == 0.0
    assert s.stem.startswith("ring_shank_plait3x4_US6_w1.2t0.85_")
    v = s.notebook_inputs("B", "O")
    assert v["Edge Round"] == 0.0 and v["Edge Round Inward"] == 0.0 and v["Wrap Length"] == pytest.approx(2 * math.pi * (b.bore_radius_mm + 0.8), abs=1e-3)
    lace = s.knot_layout()
    assert lace.problems == [] and len(lace.crossings) == 24
    ring = s.design_mesh()
    assert ring.is_watertight and ring.body_count == 1
    import numpy as np
    r = np.hypot(ring.vertices[:, 0], ring.vertices[:, 1])
    assert r.min() == pytest.approx(b.bore_radius_mm, abs=1e-3)                                   # an under strand's inner face on the bore
    assert r.max() == pytest.approx(b.outer_radius_mm, abs=3e-3)                                  # an over strand's outer face at the band's outside
    assert ring.bounds[1][2] - ring.bounds[0][2] == pytest.approx(4.0, abs=1e-3) and s.overall_width_mm == 4.0
    assert s.outer_radius_mm == b.outer_radius_mm and s.wall_floor() == 0.5
    assert s.design()["knot"] == "plait" and s.design()["knot_fuse"] == kw.KNOT_FUSE_MM
    wire = knot(knot_strands=4, knot_repeats=3, knot_profile="round")
    assert wire.validate() == [] and wire.knot_width == pytest.approx(0.85) and wire.stem.startswith("ring_shank_plait4x3_US6_d0.85_")
    assert knot(knot_strands=2, knot_repeats=1).validate() == [] and knot(knot_strands=2, knot_repeats=1).warnings() == []
    # refusals
    assert "2..4" in knot(knot_strands=5).validate()[0]
    assert "whole number" in knot(knot_repeats=0).validate()[0]
    assert "0.75" in knot(band=band.BandSpec(size=6, width_mm=4.0, thickness_mm=1.3)).validate()[0]        # a 0.7 mm strand
    assert "part by only" in knot(band=band.BandSpec(size=6, width_mm=3.0, thickness_mm=1.6), knot_strands=4).validate()[0]
    assert "do not weave" in knot(band=band.BandSpec(size=6, width_mm=4.0, thickness_mm=1.6), knot_strand_mm=2.2).validate()[0]
    assert "no taper" in knot(width_bottom_mm=2.0).validate()[0]
    assert knot(knot="celtic").validate()


@pytest.mark.parametrize("kind", ["plait2", "plait3", "plait4-wire"])
def test_plait_designs_pass_their_gate_and_the_bar_agrees(kind, tmp_path):
    import trimesh
    s = {"plait2": knot(knot_strands=2, knot_repeats=4, knot_strand_mm=1.2),
         "plait3": knot(knot_strands=3, knot_repeats=4, knot_strand_mm=1.2),
         "plait4-wire": knot(knot_strands=4, knot_repeats=3, knot_profile="round")}[kind]
    assert s.validate() == []
    m = s.design_mesh()
    m.export(tmp_path / "s.stl")
    rep = shank.check_shank(s, tmp_path / "s.stl", s.expected_volume_mm3())
    assert rep.status == "passed", rep.text()
    shape = next(c for c in rep.checks if c.name == "section shape")
    assert "within 0.0" in shape.detail                                                             # ring sweep vs the bar wrapped: hundredths
    bar = s.bar_mesh()
    assert bar.is_watertight and bar.body_count == 1
    assert bar.bounds[0][0] == pytest.approx(s.band.bore_radius_mm, abs=1e-3) and bar.bounds[1][0] == pytest.approx(s.band.outer_radius_mm, abs=1e-3)
    L = s.wrap_length_mm
    one = trimesh.intersections.slice_mesh_plane(bar, [0, 1, 0], [0, -L / 730, 0], cap=True)
    one = trimesh.intersections.slice_mesh_plane(one, [0, -1, 0], [0, L - L / 730, 0], cap=True)
    assert geom.remap_cylindrical(one, L).volume == pytest.approx(m.volume, rel=1e-3)
    if kind == "plait3":
        plain = shank.ShankSpec(s.band).design_mesh()                                                # the band itself in place of the weave: caught
        plain.export(tmp_path / "p.stl")
        failed = {c.name for c in shank.check_shank(s, tmp_path / "p.stl", float(plain.volume)).failures()}
        assert "design volume" in failed and "section shape" in failed


def test_plait_end_to_end(fake_ntopcl, tmp_path):
    nb = tmp_path / "ring_shank.ntop"
    nb.write_bytes(b"fake")
    s = knot(knot_strands=3, knot_repeats=4, knot_strand_mm=1.2)
    res = shank.build(s, tmp_path / "out", notebook=nb)
    assert res.status == "passed", res.text()
    assert (res.run_dir / f"{s.stem}.bar.stl").exists()
    import json
    report = json.loads((res.run_dir / f"{s.stem}.report.json").read_text())
    assert report["design"]["knot_strands"] == 3 and report["shank"]["knot"] == "plait"


def test_cli_plait_flags(capsys):
    from ntopjewel import cli
    assert cli.main(["shank", "--size", "6", "--width", "4", "--thickness", "1.6", "--knot", "plait", "--knot-strands", "3",
                     "--knot-repeats", "4", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "ring_shank_plait3x4_US6_w1.2t0.85_" in out and "24 crossings, 16 on each strand" in out and "Edge Round: 0.0" in out
    assert cli.main(["shank", "--size", "6", "--width", "4", "--thickness", "1.3", "--knot", "plait", "--dry-run"]) == 1
    assert "at least 0.75 mm" in capsys.readouterr().out
    assert cli.main(["shank", "--size", "6", "--width", "4", "--thickness", "1.6", "--knot", "plait", "--knot-profile", "round",
                     "--knot-strands", "4", "--knot-repeats", "3", "--dry-run"]) == 0
    assert "round wires 0.85 mm" in capsys.readouterr().out


def trinity(**kw):
    b = kw.pop("band", None) or band.BandSpec(size=6, profile="court", width_mm=4.0, thickness_mm=1.6, mesh_tolerance_mm=0.1)
    kw.setdefault("split_mm", 1.6)
    kw.setdefault("split_span_deg", 100.0)
    kw.setdefault("knot", "trinity")
    kw.setdefault("knot_strand_mm", 0.9)
    kw.setdefault("knot_mm", 5.6)
    return shank.ShankSpec(b, **kw)


def test_the_trefoil_and_the_sweep_pieces():
    """The opened trefoil: three self-crossings at radius R, alternating; a sweep in two pieces that
    share a ring and its cap unites to one clean body."""
    import numpy as np
    import trimesh
    from ntopjewel import knotwork as kw
    st = kw.trefoil_motif((20.0, 0.0), 1.6, ((26.0, 1.3), (26.0, -1.3)), towards_tail=1.0)
    xs = kw.crossings([st])
    assert len(xs) == 3 and all(c.self_crossing for c in xs)
    assert all(math.hypot(c.y - 20.0, c.z) == pytest.approx(1.6, abs=0.02) for c in xs)             # on the circle of radius R
    assert all(70 < c.angle_deg < 80 for c in xs)                                                    # 2 atan(1.5 x 0.5) = 74°
    lace = kw.interlace([st], xs)
    assert lace.problems == [] and lace.over[0] == [True, False, True, False, True, False]
    assert lace.depth(0, np.array([0.0, st.length]), law="mid").tolist() == [0.0, 0.0]               # the ends at mid-depth
    assert lace.bore_law_problems(widths=[1.2]) == []
    assert np.abs(lace.depth(0, np.linspace(0, st.length, 300), law="bore", widths=[0.9])).max() == pytest.approx(1.0)
    assert kw.interlace([kw.Strand(np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 1.0], [0.0, 1.0], [0.0, 0.5], [12.0, 0.5]]), closed=False)]).problems == []
    prof = kw.ribbon_profile(0.9, 1.1, 0.25)
    inset = kw.offset_profile(prof, 0.05)
    assert np.abs(inset).max() == pytest.approx(np.abs(prof).max() - 0.05, abs=1e-4)
    # a path, swept in two pieces sharing ring k and its cap triangles: one body, no needle faces
    path = np.column_stack([np.linspace(0, 10, 41), np.zeros(41), np.sin(np.linspace(0, 3, 41))])
    rings, _ = kw.sweep_rings(path, profile=prof, closed=False, up=(0.0, 0.0, 1.0))
    cap = kw.cap_triangles(prof)
    a = kw.mesh_from_rings(rings[:21], end_cap=cap)
    b = kw.mesh_from_rings(rings[20:], start_cap=cap)
    whole = kw.mesh_from_rings(rings)
    u = trimesh.boolean.union([a, b], engine="manifold")
    assert u.is_watertight and u.body_count == 1 and u.volume == pytest.approx(whole.volume, rel=1e-6)
    assert (u.area_faces < 1e-7).sum() == 0 and u.edges_unique_length.min() > 1e-3


def test_the_trinity_shank(tmp_path):
    import numpy as np
    import trimesh
    from ntopjewel import knotwork as kw
    s = trinity()
    assert s.validate() == [] and s.trinity and s.split_mm == 1.6
    lay = s.trinity_layout()
    assert lay["R"] == pytest.approx((2.8 - shank.KNOT_LOBE_MARGIN_MM - 0.45) / (math.sin(math.radians(60)) * 1.5), abs=1e-6)
    assert lay["y_pad"] == pytest.approx(30.0 / s.deg_per_mm) and lay["y_c"] == pytest.approx(lay["y_pad"] - shank.KNOT_NOSE_JOIN_MM + lay["R"])
    assert lay["theta_1"] == pytest.approx((lay["y_c"] + 0.5 * lay["R"] + 3.0) * s.deg_per_mm)
    assert s.trinity_thickness == pytest.approx(1.12) and s.trinity_ribbon == 0.9 and s.trinity_width == 5.6
    assert s.edge_round == 0.0 and s.opening_chamfer_mm == 0.0 and s.notebook_inputs("B", "O")["Edge Round"] == 0.0
    assert "_split1.6_trinity5.6_" in s.stem and s.stem.startswith("ring_shank_court_US6_")
    for side, lace in zip((1, -1), s.trinity_laces()):
        assert len(lace.crossings) == 3 and lace.problems == []
    flat, solid = s.trinity_bend_radii()
    assert flat >= 0.45 + 0.1 and solid >= 0.56 + 0.1
    m = s.design_mesh()
    assert m.is_watertight and m.body_count == 1
    r = np.hypot(m.vertices[:, 0], m.vertices[:, 1])
    assert r.min() == pytest.approx(s.band.bore_radius_mm, abs=2e-3)                                 # the halves and the band under the head
    assert r.max() == pytest.approx(s.band.bore_radius_mm + shank.KNOT_LIFT_MM + 2 * 1.12 - kw.KNOT_FUSE_MM, abs=0.02)   # a pass over
    assert 5.6 - 2 * shank.KNOT_LOBE_MARGIN_MM <= s.overall_width_mm <= 5.6 + 0.1                    # the lobes (their ribbon tilts as it rises)
    m.export(tmp_path / "t.stl")
    assert trimesh.load(tmp_path / "t.stl").is_watertight                                            # survives float32
    rep = shank.check_shank(s, tmp_path / "t.stl", s.expected_volume_mm3())
    assert rep.status == "passed", rep.text()
    bar = s.bar_mesh()
    bar.export(tmp_path / "bar.stl")
    back = shank.wrap_bar(trimesh.load(tmp_path / "bar.stl"), s.wrap_length_mm)
    assert back.is_watertight and back.volume == pytest.approx(m.volume, rel=1e-3)
    plain = shank.ShankSpec(s.band, split_mm=1.6, split_span_deg=100.0).design_mesh()               # the split without its knots: caught
    plain.export(tmp_path / "p.stl")
    failed = {c.name for c in shank.check_shank(s, tmp_path / "p.stl", float(plain.volume)).failures()}
    assert "design volume" in failed and ("section shape" in failed or "width" in failed)
    # refusals
    assert "--split" in trinity(split_mm=0.0).validate()[0]
    assert "centre closes" in trinity(knot_mm=4.4).validate()[0]
    assert "at most" in trinity(knot_thickness_mm=1.5).validate()[0]
    assert "wider than a half" in trinity(knot_strand_mm=1.4).validate()[0]
    assert "slot has closed" in trinity(split_span_deg=60.0).validate()[0]
    assert "no dip" in trinity(dip_mm=1.0).validate()[0]
    assert trinity(knot="celtic").validate()


def test_trinity_end_to_end(fake_ntopcl, tmp_path):
    nb = tmp_path / "ring_shank.ntop"
    nb.write_bytes(b"fake")
    s = trinity(knot_pad_deg=25.0, knot_mm=5.2, knot_strand_mm=0.8)
    res = shank.build(s, tmp_path / "out", notebook=nb)
    assert res.status == "passed", res.text()


def test_cli_trinity_flags(capsys):
    from ntopjewel import cli
    assert cli.main(["shank", "--size", "6", "--width", "4", "--thickness", "1.6", "--split", "1.6", "--split-span", "100",
                     "--knot", "trinity", "--knot-width", "5.6", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "_split1.6_trinity5.6_" in out and "trinity knots on the shoulders" in out and "ribbon 0.9 wide x 1.12 thick" in out
    assert cli.main(["shank", "--size", "6", "--knot", "trinity", "--dry-run"]) == 1
    assert "--split" in capsys.readouterr().out
