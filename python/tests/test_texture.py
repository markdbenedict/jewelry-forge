"""Surface textures: a hammered band - strikes of one round hammer face in a seeded dart-throwing layout,
the independent model (the band less the strikes' spheres) and its gate."""
import math

import numpy as np
import pytest

from ntopjewel import band, tables, texture


def hammered(**kw):
    b = kw.pop("band", None) or band.BandSpec(size=6, profile="court", width_mm=4.0, thickness_mm=1.6, mesh_tolerance_mm=0.05)
    return texture.HammeredSpec(b, **kw)


def test_the_hammer_and_its_layout():
    s = hammered()
    assert s.validate() == []
    R = s.sphere_radius
    assert R == pytest.approx((0.8 ** 2 + 0.15 ** 2) / 0.3) and s.footprint_mm(0.15) == pytest.approx(1.6)
    u, z, d = s.layout()
    assert s.count == len(u) > 100
    L, sp = s.face_length, s.spacing * s.dimple_mm
    du = np.abs(u[:, None] - u[None, :])
    du = np.minimum(du, L - du)
    dist = np.hypot(du, z[:, None] - z[None, :]) + np.eye(len(u)) * 99
    assert dist.min() >= sp - 1e-9                                                       # spaced, round the seam too
    assert np.abs(z).max() <= s.z_limit + 1e-9
    assert d.min() >= tables.FLOORS["texture_depth"] - 1e-9 and d.max() <= s.depth_range[1] + 1e-9
    reach = np.abs(z) + np.array([s.footprint_mm(q) for q in d]) / 2
    assert reach.max() <= s.edge_reach + 1e-6                                              # no footprint into a rim
    assert (d < s.depth_range[0] - 1e-9).any()                                            # lighter strikes by the rims
    # the same seed, the same hammering; another seed, another
    assert np.array_equal(hammered().layout()[0], u) and not np.array_equal(hammered(seed=2).layout()[0][:5], u[:5])
    # every centre on its face point's normal, R - d out
    P, N, dd, C = s.strikes()
    assert np.allclose(np.linalg.norm(C - P, axis=1), R - dd) and np.allclose(np.linalg.norm(N, axis=1), 1.0)
    assert np.allclose(s.centres(), C)


def test_the_design_passes_its_gate_and_a_wrong_build_is_caught(tmp_path):
    s = hammered()
    m = s.design_mesh()
    assert m.is_watertight and m.body_count == 1
    plain = s.band_mesh()
    lost = plain.volume - m.volume
    assert 0.03 * plain.volume < lost < 0.08 * plain.volume                                # a few % of the metal
    m.export(tmp_path / "h.stl")
    rep = texture.check_texture(s, tmp_path / "h.stl", float(m.volume))
    assert rep.status == "passed", rep.text()
    assert {"strikes", "section shape", "design volume", "wall thickness"} <= {c.name for c in rep.checks}
    plain.export(tmp_path / "p.stl")                                                      # the texture left out
    assert {"strikes", "design volume", "section shape"} <= {c.name for c in texture.check_texture(s, tmp_path / "p.stl", float(plain.volume)).failures()}
    light = hammered(depth_mm=0.12)                                                        # struck too lightly (a wrong radius)
    light.design_mesh().export(tmp_path / "l.stl")
    failed = {c.name for c in texture.check_texture(s, tmp_path / "l.stl", float(light.design_mesh().volume)).failures()}
    assert "strikes" in failed


def test_what_a_hammering_refuses():
    assert "voxels" in hammered(band=band.BandSpec(size=6, width_mm=4.0, thickness_mm=1.6, mesh_tolerance_mm=0.1)).validate()[0]
    assert "polishes flat" in hammered(depth_mm=0.12).validate()[0]
    assert "hemisphere" in hammered(dimple_mm=0.8, depth_mm=0.45, depth_var=0.0).validate()[0]
    assert "0.5..1.5" in hammered(spacing=0.3).validate()[0]
    assert "no room" in hammered(band=band.BandSpec(size=6, width_mm=2.0, thickness_mm=1.6, mesh_tolerance_mm=0.05), rim_mm=0.4).validate()[0]
    wide = hammered(band=band.BandSpec(size=10, profile="comfort-flat", width_mm=8.0, thickness_mm=2.0, mesh_tolerance_mm=0.03))
    assert "M triangles" in wide.validate()[-1]
    assert tables.mesh_triangles_estimate(1184.9, 0.05) == pytest.approx(5.29e6, rel=0.01)  # the run it was calibrated on


def test_cli_texture(capsys, tmp_path):
    from ntopjewel import cli
    assert cli.main(["texture", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "ring_texture_hammered_court_US6_w4_t1.6_d1.6x0.15_" in out and "strikes of a 2.21 mm hammer face" in out and "M triangles" in out
    assert cli.main(["texture", "--tolerance", "0.1", "--dry-run"]) == 1
    assert "--tolerance 0.06 or finer" in capsys.readouterr().out
    assert cli.main(["texture", "--write-design", "--out", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "not an nTop build" in out
    assert len(list(tmp_path.rglob("*.design.stl"))) == 1 and len(list(tmp_path.rglob("*.centres.csv"))) == 1
    csv = np.loadtxt(next(tmp_path.rglob("*.centres.csv")), delimiter=",")
    assert csv.shape == (hammered().count, 3)
    assert cli.main(["texture", "--out", str(tmp_path)]) == 2                              # no notebook built here: refused


def test_recipe_builds_on_the_fake_api(tmp_path):
    """ring_texture.ntop from nTop's own blocks: Import Points -> one Sphere on the list -> Union, less from the band."""
    from ntopjewel import catalog
    from .fake_notebook import FakeNotebook
    from .test_notebook_api import load_recipe
    mod = load_recipe("ring_texture")
    params = mod.prepare({}, tmp_path)
    params.update({"save_to": str(tmp_path / "t.ntop"), "recipe_to": str(tmp_path / "t.json"), "test_output": str(tmp_path / "t.stl")})
    nb = FakeNotebook()
    res = mod.build(nb, params)
    assert nb.inputs == mod.INPUT_ORDER == list(catalog.load("ring_texture").inputs)
    assert nb.lint() == [] and res["warnings"] == []
    assert res["identifiers"]["Strike Centres"].startswith("import_points") and res["identifiers"]["Strikes Units"] == "core.var<unit_length_enum>"
    assert params["values"]["Strike Radius"] == pytest.approx(hammered().sphere_radius, abs=1e-6)


def test_hammered_end_to_end_and_a_wrong_notebook_is_caught(fake_ntopcl, tmp_path, out_dir, monkeypatch):
    nb = tmp_path / "ring_texture.ntop"
    nb.write_bytes(b"fake")
    s = hammered()
    res = texture.build(s, out_dir, notebook=nb)
    assert res.status == "passed", res.text()
    assert res.ntop_volume_mm3 == pytest.approx(s.design_volume_mm3(), rel=2e-3)
    csv = np.loadtxt(next(res.run_dir.glob("*.centres.csv")), delimiter=",")
    assert csv.shape == (s.count, 3)
    for fault, lost in (("nostrikes", "strikes"), ("light", "strikes")):
        monkeypatch.setenv("FAKE_NTOPCL_SHAPE", fault)
        bad = texture.build(s, out_dir, notebook=nb)
        assert bad.status == "failed" and lost in {c.name for c in bad.gate.failures()}, bad.text()


def test_the_unit_reaches_ntopcl_as_its_measured_id():
    from ntopjewel import catalog
    s = hammered()
    entries = {e["name"]: e for e in catalog.load("ring_texture").build_inputs(s.notebook_inputs("c.csv", "o.stl"))}
    assert entries["Strikes Units"] == {"name": "Strikes Units", "type": "enum", "value": 1}            # 1 = mm (points_probe)
    assert entries["Strike Radius"]["value"] == pytest.approx(s.sphere_radius, abs=1e-6)


# ---- a hammered shank (ring_shank 0.4.0's Strikes) -------------------------------------------------------
def court(**kw):
    return band.BandSpec(size=6, profile="court", width_mm=4.0, thickness_mm=1.6, mesh_tolerance_mm=0.05, **kw)


def test_the_plain_band_layout_is_the_one_real_ntop_passed():
    """The hammer and its faces were factored out of HammeredSpec after its first real run (2026-11-05): the
    layout must be draw for draw the same, or that run's evidence no longer describes the design."""
    s = hammered()
    assert s.spec_id == "0c808bd0" and s.count == 150
    assert s.centres()[0] == pytest.approx([-11.78746, -0.87716, 1.25161], abs=2e-5)       # the first line of that run's centres file


def test_a_tapered_shank_is_hammered_where_its_face_is(tmp_path):
    from ntopjewel import shank
    s = shank.ShankSpec(court(), width_bottom_mm=2.6, thickness_bottom_mm=1.4, hammer=texture.Hammer())
    assert s.validate() == [] and s.warnings() == [] and "_hammered1.6x0.15_" in s.stem
    u, z, d = s.strike_layout()
    f = s.hammer_face()
    h = s.hammer
    for uu, zz, dd in zip(u, z, d):                                  # every footprint inside its stretch, short of the rims
        t = np.degrees(uu / f.radius)
        a, b = [iv for iv in f.intervals(t) if iv[0] <= zz <= iv[1]][0]
        assert min(zz - a, b - zz) - h.footprint_mm(dd) / 2 >= h.rim(s.band.edge_round) - 0.02
    bottom = [zz for uu, zz in zip(u, z) if abs(np.degrees(uu / f.radius) - 180) < 20]
    assert bottom and max(abs(q) for q in bottom) < 0.4                 # one row where the shank is narrowest
    m = s.struck_mesh()
    assert m.is_watertight and m.body_count == 1 and m.volume < s.design_mesh().volume - 5
    m.export(tmp_path / "s.stl")
    rep = shank.check_shank(s, tmp_path / "s.stl", s.expected_volume_mm3())
    assert rep.status == "passed", rep.text()
    assert "strikes" in {c.name for c in rep.checks}


def test_a_split_shank_warns_where_its_halves_are_too_narrow():
    from ntopjewel import shank
    s = shank.ShankSpec(court(), split_mm=1.6, split_span_deg=100, hammer=texture.Hammer())
    assert s.validate() == [] and any("stays polished" in w for w in s.warnings())
    small = shank.ShankSpec(court(), split_mm=1.6, split_span_deg=100, hammer=texture.Hammer(dimple_mm=1.0, depth_mm=0.14, rim_mm=0.12))
    assert small.validate() == [] and not any("stays polished" in w for w in small.warnings()) and small.strike_count > 300


def test_what_a_hammered_shank_refuses():
    from ntopjewel import shank
    assert "not a rope or a knot" in shank.ShankSpec(court(), rope=2, hammer=texture.Hammer()).validate()[0]
    assert "voxels" in shank.ShankSpec(band.BandSpec(size=6, width_mm=4.0, thickness_mm=1.6), hammer=texture.Hammer()).validate()[0]
    assert "polishes flat" in shank.ShankSpec(court(), hammer=texture.Hammer(depth_mm=0.12)).validate()[0]
    plain = shank.ShankSpec(court(), width_bottom_mm=2.6, thickness_bottom_mm=1.4)
    assert "hammer" not in plain.design() and "_hammered" not in plain.stem               # earlier designs keep their ids
    assert plain.strike_inputs("x.csv") == {"Strikes Path": "x.csv", "Strike Radius": 1.0, "Strikes Units": "mm"}


def test_hammered_shank_end_to_end_and_a_wrong_notebook_is_caught(fake_ntopcl, tmp_path, out_dir, monkeypatch):
    from ntopjewel import shank
    nb = tmp_path / "ring_shank.ntop"
    nb.write_bytes(b"fake")
    s = shank.ShankSpec(court(), width_bottom_mm=2.6, thickness_bottom_mm=1.4, hammer=texture.Hammer())
    res = shank.build(s, out_dir, notebook=nb)
    assert res.status == "passed", res.text()
    assert np.loadtxt(next(res.run_dir.glob("*.strikes.csv")), delimiter=",").shape == (s.strike_count, 3)
    monkeypatch.setenv("FAKE_NTOPCL_SHAPE", "nostrikes")
    bad = shank.build(s, out_dir, notebook=nb)
    assert bad.status == "failed" and "strikes" in {c.name for c in bad.gate.failures()}, bad.text()
    monkeypatch.delenv("FAKE_NTOPCL_SHAPE")
    plain = shank.build(shank.ShankSpec(court(), width_bottom_mm=2.6, thickness_bottom_mm=1.4), out_dir, notebook=nb)
    assert plain.status == "passed"                                                          # the far point cuts nothing
    assert np.loadtxt(next(plain.run_dir.glob("*.strikes.csv")), delimiter=",").tolist() == list(texture.FAR_STRIKE)


def test_ring_shank_recipe_takes_the_strikes(tmp_path, fake_open_bar):
    from ntopjewel import catalog
    from .fake_notebook import FakeNotebook
    from .test_notebook_api import load_recipe
    mod = load_recipe("ring_shank")
    params = mod.prepare({}, tmp_path)
    params.update({"save_to": str(tmp_path / "s.ntop"), "recipe_to": str(tmp_path / "s.json"), "test_output": str(tmp_path / "s.stl"),
                   "open_bar_block": str(fake_open_bar)})
    nb = FakeNotebook()
    res = mod.build(nb, params)
    assert nb.inputs == mod.INPUT_ORDER == list(catalog.load("ring_shank").inputs) and nb.lint() == [] and res["warnings"] == []
    assert res["identifiers"]["Strike Centres"].startswith("import_points")


# ---- a hammered solitaire: the shank struck before the arches and the head join it -----------------------------------
def hammered_solitaire(**kw):
    from ntopjewel import gems, heads, solitaire
    kw.setdefault("shank_blend_mm", 0.0)                       # as test_solitaire.spec: the simulated blend is square-cornered
    kw.setdefault("hammer", texture.Hammer())
    return solitaire.SolitaireSpec(band.BandSpec(size=6, profile="court", mesh_tolerance_mm=0.05),
                                   heads.HeadSpec(gems.StoneSpec("round", 6.5), prongs=6), **kw)


def test_a_hammered_solitaire_keeps_its_strikes_off_the_head_and_the_arches():
    import json
    from ntopjewel import runs, solitaire
    s = hammered_solitaire(text="M+K")
    assert s.validate() == []
    sh = s.shank_spec
    assert sh.hammer.clear_deg == s.head_clear_deg() == s.shoulder_deg + solitaire.WEDGE_EXTRA_DEG + solitaire.PANEL_WEDGE_CLEAR_DEG
    P = sh.strikes()[0]
    th = np.degrees(np.abs(np.arctan2(P[:, 1], P[:, 0])))                               # from the top (+X), either way
    assert sh.strike_count > 50 and th.min() > sh.hammer.clear_deg
    assert "_hammered1.6x0.15_" in s.stem
    v = s.notebook_inputs("")
    assert v["Strike Radius"] == pytest.approx(sh.hammer.sphere_radius, abs=1e-6) and v["Strikes Units"] == "mm"
    plain = hammered_solitaire(hammer=None)                                             # an unhammered ring keeps its identity
    assert "hammer" not in json.dumps(plain.design()) and plain.notebook_inputs("")["Strike Radius"] == 1.0
    assert runs.spec_id(plain.design()) != runs.spec_id(s.design())
    flat = hammered_solitaire(cathedral=False)                                          # plain shoulders: past the head's reach
    assert flat.shank_spec.hammer.clear_deg == flat.head_clear_deg() < s.head_clear_deg()
    # the design: the shank struck, the rest as before
    assert s.carved_shank_mesh().volume < plain.carved_shank_mesh().volume - 0.5 * sh.strike_count * 0.1


def test_what_a_hammered_solitaire_refuses():
    from ntopjewel import artwork, shank
    b = band.BandSpec(size=6, profile="court", mesh_tolerance_mm=0.05)
    assert "not its shank" in hammered_solitaire(hammer=None, shank=shank.ShankSpec(b, hammer=texture.Hammer())).validate()[0]
    assert "shoulder knots" in hammered_solitaire(cathedral=False, shoulder_knot="trinity").validate()[0]
    assert "artwork" in hammered_solitaire(cathedral=False, panels=artwork.seraphine_panels(outer="scroll", sides="none")).validate()[0]
    assert "outside engraving" in hammered_solitaire(text="M+K", engrave_side="outside").validate()[0]
    deep = hammered_solitaire(text="M+K", engrave_depth_mm=0.5).validate()
    assert deep and "under the engraving" in deep[0]
    assert "trinity" in hammered_solitaire(shank=shank.ShankSpec(b, split_mm=1.6, split_span_deg=100, knot="trinity")).validate()[0]


def test_hammered_solitaire_end_to_end_and_a_lost_hammering_is_caught(fake_ntopcl, tmp_path, out_dir, monkeypatch):
    from ntopjewel import solitaire
    nb = tmp_path / "solitaire.ntop"
    nb.write_bytes(b"fake")
    s = hammered_solitaire()
    res = solitaire.build(s, out_dir, notebook=nb)
    assert res.status == "passed", res.text()
    assert "strikes" in {c.name for c in res.gate.checks}
    assert np.loadtxt(next(res.run_dir.glob("*.strikes.csv")), delimiter=",").shape == (s.shank_spec.strike_count, 3)
    monkeypatch.setenv("FAKE_NTOPCL_SHAPE", "nostrikes")
    bad = solitaire.build(s, out_dir, notebook=nb)
    assert bad.status == "failed" and "strikes" in {c.name for c in bad.gate.failures()}, bad.text()
