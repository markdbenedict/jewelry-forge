"""The unfaceted stones and the square step cut (Phase 3 step 4): an asscher, a cabochon and a pearl
on a post - their bodies, the heads that hold them (the outline_head block, a different prong and rail
layout each) and the rings they ride in."""
import math

import pytest

from ntopjewel import band, gems, heads, multistone, solitaire, tables
from .pseudo_blend import Blended


def asscher():
    return gems.StoneSpec("asscher", 7.0)


def cabochon():
    return gems.StoneSpec("cabochon", 10.0, 8.0)


def pearl():
    return gems.StoneSpec("pearl", 8.0)


# ---- bodies ----------------------------------------------------------------------------------------
def test_asscher_is_a_square_step_cut_with_cut_corners():
    s = asscher()
    assert s.validate() == [] and s.width == 7.0 and s.faceted
    m = s.mesh()
    assert m.is_watertight and m.extents[0] == pytest.approx(7.0, abs=1e-3) and m.extents[1] == pytest.approx(7.0, abs=1e-3)
    from shapely.geometry import Polygon
    o = Polygon(s.outline())
    corner = gems.ASSCHER_CORNER_FRAC * s.width
    assert o.area == pytest.approx(49.0 - 2 * corner ** 2, rel=1e-3)                     # four triangles of corner²/2 off the square
    assert s.depth > gems.StoneSpec("emerald", 7.0, 7.0).depth                          # the asscher's deep pavilion


def test_cabochon_is_a_flat_base_a_girdle_band_and_an_elliptic_dome():
    s = cabochon()
    assert s.validate() == [] and not s.faceted
    m = s.mesh()
    assert m.is_watertight
    dome, pav = s.heights
    assert pav == 0.0 and dome == pytest.approx(gems.CABOCHON_DOME_FRAC * 8.0)
    a, b = 5.0, 4.0                                                                   # a prism to the girdle + half an ellipsoid
    want = math.pi * a * b * s.girdle + 2.0 / 3.0 * math.pi * a * b * dome
    assert m.volume == pytest.approx(want, rel=0.01)
    assert gems.StoneSpec("cabochon", 10.0, 8.0, dome_frac=0.8).validate()               # a dome over 0.6 x the width


def test_pearl_is_a_sphere_half_drilled_from_below():
    s = pearl()
    assert s.validate() == [] and s.material == "pearl" and s.girdle == 0.0
    m = s.mesh()
    assert m.is_watertight
    d, depth = s.drill
    want = 4.0 / 3.0 * math.pi * 4.0 ** 3 - math.pi * (d / 2) ** 2 * depth             # the drill's cap end is flat
    assert m.volume == pytest.approx(want, rel=0.005)
    assert m.contains([[0.0, 0.0, -4.0 + depth / 2]]).tolist() == [False]               # the drill is open
    assert gems.StoneSpec("pearl", 8.0, drill_mm=3.0).validate()                         # wider than a third of the pearl
    assert gems.StoneSpec("pearl", 8.0, material="diamond").material == "diamond"        # said is said


def test_the_seat_keeps_a_pearls_drill_open_so_the_post_survives_its_cut():
    from ntopjewel import geom
    s = pearl()
    env = gems.seat_envelope(s)
    r, top = geom.drill_of(env)
    assert r == pytest.approx(0.5, abs=0.01) and top == pytest.approx(-4.0 + 4.8, abs=0.01)
    grown = geom.offset_convex(env, 0.05)
    assert grown.contains([[0.0, 0.0, -1.0]]).tolist() == [False]                       # the drill, narrowed by the clearance
    assert grown.contains([[0.0, 0.7, -1.0]]).tolist() == [True]


# ---- heads -----------------------------------------------------------------------------------------
HEADS = {"asscher": lambda: heads.OutlineHeadSpec(asscher()),
         "cabochon": lambda: heads.OutlineHeadSpec(cabochon()),
         "pearl": lambda: heads.OutlineHeadSpec(pearl()),
         "pearl-cup-and-post": lambda: heads.OutlineHeadSpec(pearl(), prongs=0)}


@pytest.mark.parametrize("name", list(HEADS))
def test_design_head_passes_its_gate(name, tmp_path):
    s = HEADS[name]()
    assert s.validate() == []
    m = heads.outline_design_mesh(s, ops=Blended())
    m.export(tmp_path / "h.stl")
    rep = heads.check_outline_head(s, tmp_path / "h.stl", float(m.volume))
    assert rep.status == "passed", rep.text()
    names = {c.name for c in rep.checks}
    if name == "asscher":
        assert "seat ledges" in names
    elif name == "cabochon":
        assert {"prongs", "seat floor"} <= names
    else:
        assert {"cup", "post"} <= names and ("prongs" in names) == (s.count > 0)


def test_kinds_and_layouts():
    cab, prl = HEADS["cabochon"](), HEADS["pearl"]()
    assert HEADS["asscher"]().kind == "faceted" and cab.kind == "cabochon" and prl.kind == "pearl"
    assert cab.count == 4 and prl.count == 4 and HEADS["pearl-cup-and-post"]().count == 0
    for foot, knee, tip in cab.prong_axes():                                            # upright beside the girdle band
        assert foot[0] == pytest.approx(knee[0]) and knee[0] == pytest.approx(tip[0])
    pr, z0, z1 = prl.post
    assert pr == pytest.approx(0.5) and z1 == pytest.approx(-4.0 + 4.8)
    assert heads.OutlineHeadSpec(pearl(), cup_frac=0.6).validate()                       # a cup past 40 % hides the pearl
    assert heads.OutlineHeadSpec(gems.StoneSpec("pearl", 8.0, drill_mm=0.5)).validate()  # a post under the wall floor


@pytest.mark.parametrize("name,fault,lost", [("asscher", "noseat", "stone fits"), ("cabochon", "noprongs", "prongs"),
                                             ("pearl", "noprongs", "post")])
def test_head_end_to_end_and_a_lost_part_is_caught(name, fault, lost, fake_ntopcl, tmp_path, monkeypatch):
    nb = tmp_path / "outline_head_harness.ntop"
    nb.write_bytes(b"fake")
    s = HEADS[name]()
    res = heads.build_outline_head(s, tmp_path / "out", notebook=nb)
    assert res.status == "passed", res.text()
    monkeypatch.setenv("FAKE_NTOPCL_SHAPE", fault)
    bad = heads.build_outline_head(s, tmp_path / "out", notebook=nb)
    assert bad.status == "failed" and lost in {c.name for c in bad.gate.failures()}, bad.text()


# ---- rings -----------------------------------------------------------------------------------------
def ring(stone, **kw):
    """A low-set cabochon or pearl has no room for cathedral arches (the CLI leaves them off)."""
    return solitaire.SolitaireSpec(band.BandSpec(size=6, profile="court", mesh_tolerance_mm=0.05),
                                   heads.OutlineHeadSpec(stone, **kw), cathedral=stone.faceted)


@pytest.mark.parametrize("stone", [asscher, cabochon, pearl])
def test_solitaire_end_to_end(stone, fake_ntopcl, tmp_path, out_dir):
    nb = tmp_path / "solitaire_outline.ntop"
    nb.write_bytes(b"fake")
    s = ring(stone())
    assert s.validate() == []
    res = solitaire.build(s, out_dir, notebook=nb)
    assert res.status == "passed", res.text()
    names = {c.name for c in res.gate.checks}
    assert ("seat ledges" in names) == (stone is asscher)


def test_multistone_pearl_between_asschers_end_to_end(fake_ntopcl, tmp_path, out_dir):
    nb = tmp_path / "multistone.ntop"
    nb.write_bytes(b"fake")
    b = band.BandSpec(size=6, profile="comfort-flat", width_mm=2.6, thickness_mm=1.8, mesh_tolerance_mm=0.05)
    spec = multistone.MultiStoneSpec(b, heads.OutlineHeadSpec(gems.StoneSpec("pearl", 7.0), mesh_tolerance_mm=0.05),
                                     heads.OutlineHeadSpec(gems.StoneSpec("asscher", 4.0), mesh_tolerance_mm=0.05),
                                     centre_spin_deg=0.0)
    assert spec.validate() == []
    res = multistone.build(spec, out_dir, notebook=nb)
    assert res.status == "passed", res.text()
    names = {c.name for c in res.gate.checks}
    assert {"seat ledges", "cup", "post"} <= names


def test_cli_dry_runs(capsys):
    from ntopjewel import cli
    assert cli.main(["gem", "--shape", "pearl", "--length", "8", "--drill", "1.2", "--dry-run"]) == 0
    assert "half-drilled Ø 1.2 mm" in capsys.readouterr().out and "ct pearl"
    assert cli.main(["head", "--shape", "cabochon", "--length", "10", "--width", "8", "--cab-dome", "0.4", "--dry-run"]) == 0
    assert "upright" in capsys.readouterr().out
    assert cli.main(["head", "--shape", "pearl", "--length", "8", "--prongs", "0", "--cup", "0.25", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "no claws" in out and "25% of the pearl" in out
    assert cli.main(["solitaire", "--shape", "asscher", "--length", "6", "--dry-run"]) == 0
    assert "Prongs Path" in capsys.readouterr().out


def test_earlier_designs_keep_their_ids():
    """The dome, drill and cup knobs enter a design only when they define it (2026-11-05: adding them
    moved every stone's spec id, the Seraphine's pinned one among them)."""
    assert set(gems.StoneSpec("round", 6.5).design()) == {"shape", "length_mm", "width_mm", "depth_mm", "table_frac", "girdle_mm", "material"}
    assert "drill_mm" in gems.StoneSpec("pearl", 8.0, drill_mm=1.2).design()
    assert "cup_frac" not in heads.OutlineHeadSpec(gems.StoneSpec("pear", 12.3, 8.9, 4.6, material="glass")).design()
    assert "cup_frac" in heads.OutlineHeadSpec(pearl()).design()
    assert heads.OutlineHeadSpec(gems.StoneSpec("pear", 12.3, 8.9, 4.6), mesh_tolerance_mm=0.05).stem \
        == "head_5prong_pear_12p3x8p9x4p60_38a88504"                                   # `head --shape pear ...` before these stones


# ---- what the first real runs found (2026-11-05) -----------------------------------------------------
def test_low_set_stones_have_one_rail_and_rails_never_meet():
    """A pearl's cup was given as both rails; nTop's Basket is one blended union of the prongs and both
    rails, and the smooth minimum of a body with itself swelled the cup 0.08 mm all over (+9.6 %)."""
    for s in (HEADS["cabochon"](), HEADS["pearl"](), HEADS["pearl-cup-and-post"](),
              heads.OutlineHeadSpec(gems.StoneSpec("cabochon", 5.0, 4.0))):          # a collar too thin: the plate alone
        r = s.rails()
        assert r["lower"] == heads.EMPTY_RAIL and s.validate() == [], s.stem
        assert s.lowest_z() > heads.EMPTY_RAIL[1] + 5
    twin = {"upper": (-4.9, -2.4), "lower": (-4.9, -2.4)}
    assert heads.rail_overlap_problems(twin, 0.3)
    assert heads.rail_overlap_problems({"upper": (-1.0, -0.5), "lower": (-1.5, -1.0)}, 0.3)       # meeting on a plane
    assert not heads.rail_overlap_problems({"upper": (-1.0, -0.5), "lower": (-1.8, -1.3)}, 0.3)   # the faceted heads' 0.3 gap
    assert not heads.rail_overlap_problems(twin, 0.0)                                            # sharp: no swell


def test_twin_rails_swell_in_the_simulated_ntop_and_the_gate_sees_it(tmp_path):
    s = HEADS["pearl"]()
    v = s.notebook_inputs("")
    twin = dict(v, **{"Lower Rail Bottom": v["Upper Rail Bottom"], "Lower Rail Top": v["Upper Rail Top"]})
    m = heads.outline_head_mesh(twin, s.seat.envelope(), s.prongs_mesh(), ops=Blended())
    m.export(tmp_path / "h.stl")
    rep = heads.check_outline_head(s, tmp_path / "h.stl", float(m.volume))
    assert "design volume" in {c.name for c in rep.failures()}


def test_the_solitaire_allows_the_rails_rounded_corner_on_both_sides():
    """The asscher solitaire came out 6.63 mm along the finger against 7.06 designed: its steep pavilion
    makes the rail's top corner acute, and the blend took 0.215 mm off each side (the allowance was one
    blend, 0.4 mm, for both sides). The multistone gate already allowed two of rail_corner_shrink."""
    h = heads.OutlineHeadSpec(gems.StoneSpec("asscher", 6.0))
    assert 0.1 + 2 * h.rail_corner_shrink() > 0.43
    assert HEADS["cabochon"]().rail_corner_shrink() == pytest.approx(0.3)                        # a vertical face: a square corner
