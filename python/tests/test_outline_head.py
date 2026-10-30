"""The outline head (pear first): prongs on the outline, rails following the pavilion."""
import numpy as np
import pytest

from ntopjewel import gems, heads
from .pseudo_blend import Blended


def pear():
    return gems.StoneSpec("pear", 12.3, 8.9, 4.6, material="glass")


def test_pear_prongs_sit_on_the_outline_and_lie_on_the_offset_pavilion():
    s = heads.OutlineHeadSpec(pear())
    assert s.validate() == [] and s.count == 5
    pts = s.outline_points()
    assert pts[0][0][0] == pytest.approx(-6.15, abs=0.01)                       # the point prong
    assert sorted(round(float(q[1]), 2) for q, _ in pts[1:]) == sorted(-round(float(q[1]), 2) for q, _ in pts[1:])  # mirror pairs
    for (foot, knee, tip), (q, m) in zip(s.prong_axes(), pts):
        N, Q, C = s._pavilion_normal(q, m)
        # every point of the lower rod is the prong offset off the pavilion plane through that generator
        for p in (foot, knee):
            assert float(np.dot(p - C, N)) == pytest.approx(s.offset, abs=1e-9)
        assert tip[2] == pytest.approx(s.z_tip) and tip[0] == pytest.approx(knee[0])
    r = s.rails()
    assert r["upper"][1] <= -s.stone.girdle / 2 - 0.3 and r["lower"][1] <= r["upper"][0] - 0.3


def test_floor_raises_the_feet_and_lower_rail():
    free = heads.OutlineHeadSpec(pear())
    floored = heads.OutlineHeadSpec(pear(), floor_z=free.z_culet + 0.4)
    assert floored.lowest_z() >= floored.floor_z - 1e-9 > free.lowest_z()
    assert floored.validate() == []


def test_design_head_passes_its_gate(tmp_path):
    s = heads.OutlineHeadSpec(pear())
    m = heads.outline_design_mesh(s, ops=Blended())        # as nTop builds it
    m.export(tmp_path / "h.stl")
    rep = heads.check_outline_head(s, tmp_path / "h.stl", float(m.volume))
    assert rep.status == "passed", rep.text()


@pytest.mark.parametrize("shape,L,W", [("oval", 8.0, 6.0), ("marquise", 10.0, 5.0), ("cushion", 7.0, 7.0), ("emerald", 8.0, 6.0)])
def test_other_outlines_put_every_prong_on_its_own_ray(shape, L, W):
    """2026-10-29: prongs at 225° and 315° all landed on one outline point (the angle difference was
    not wrapped), so 4-prong heads had 3 prongs; the pear's angles never crossed 180° and passed."""
    import math
    s = heads.OutlineHeadSpec(gems.StoneSpec(shape, L, W))
    assert s.validate() == []
    pts = s.outline_points()
    assert len({(round(float(q[0]), 3), round(float(q[1]), 3)) for q, _ in pts}) == s.count
    rays = [q for (q, _), kind in zip(pts, s.point_kinds()) if kind == "round"]
    assert len(rays) == 4
    for k, q in enumerate(rays):
        want = math.radians(45.0 + 90.0 * k)
        got = math.atan2(q[1], q[0])
        assert abs((got - want + math.pi) % (2 * math.pi) - math.pi) < math.radians(1.0)


@pytest.mark.parametrize("shape,L,W", [("oval", 8.0, 6.0), ("emerald", 8.0, 6.0)])
def test_four_prong_heads_pass_their_gate(shape, L, W, tmp_path):
    s = heads.OutlineHeadSpec(gems.StoneSpec(shape, L, W))
    m = heads.outline_design_mesh(s, ops=Blended())
    m.export(tmp_path / "h.stl")
    rep = heads.check_outline_head(s, tmp_path / "h.stl", float(m.volume))
    assert rep.status == "passed", rep.text()


def test_outline_head_end_to_end_and_an_uncut_seat_is_caught(fake_ntopcl, tmp_path, monkeypatch):
    nb = tmp_path / "outline_head_harness.ntop"
    nb.write_bytes(b"fake")
    s = heads.OutlineHeadSpec(pear())
    res = heads.build_outline_head(s, tmp_path / "out", notebook=nb)
    assert res.status == "passed", res.text()
    assert (res.stl.parent / f"{s.stem}.prongs.stl").exists()
    monkeypatch.setenv("FAKE_NTOPCL_SHAPE", "noseat")
    bad = heads.build_outline_head(s, tmp_path / "out", notebook=nb)
    assert bad.status == "failed" and "stone fits" in {c.name for c in bad.gate.failures()}


def test_cli_head_pear_dry_run(capsys):
    from ntopjewel import cli
    assert cli.main(["head", "--shape", "pear", "--length", "12.3", "--width", "8.9", "--depth", "4.6", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "5 prongs" in out and "Prongs Path" in out and "Rail Offset" in out


def test_outline_head_recipe_builds_a_block_and_its_harness(tmp_path):
    from .fake_notebook import FakeNotebook
    from .test_notebook_api import load_recipe
    env = tmp_path / "env.stl"
    gems.SeatSpec(pear()).envelope().export(str(env))
    load_recipe("stone_seat").build(FakeNotebook(), {"save_to": str(tmp_path / "sh.ntop"), "recipe_to": str(tmp_path / "sh.json"),
                                                     "test_output": str(tmp_path / "s.stl"), "values": {"Seat Path": str(env)}})
    mod = load_recipe("outline_head")
    params = mod.prepare({}, tmp_path)
    params.update({"save_to": str(tmp_path / "oh.ntop"), "recipe_to": str(tmp_path / "oh.json"), "test_output": str(tmp_path / "h.stl"),
                   "seat_block": str(tmp_path / "stone_seat.ntop")})
    nb = FakeNotebook()
    res = mod.build(nb, params)
    assert res["block"]["self_test"]["accepted"]
    ids = res["block"]["identifiers"]
    assert ids["Upper Rail Slab"].startswith("box_from_corners") and ids["Prongs"].startswith("implicit_from_mesh")
    assert nb.inputs == mod.INPUT_ORDER and res["warnings"] == []


def test_v_prongs_on_the_points():
    """A pear's point and both of a marquise's get a V (on by default); --no-v-prong gives round ones."""
    p = heads.OutlineHeadSpec(pear())
    assert p.point_kinds() == ["v", "round", "round", "round", "round"] and p.count == 5
    m = heads.OutlineHeadSpec(gems.StoneSpec("marquise", 10.0, 5.0))
    assert m.point_kinds().count("v") == 2 and m.count == 6 and m.validate() == []
    assert m.v_thickness - m.clearance >= heads.PRONG_TIP_FLOOR - 0.05                 # the V's wall after the seat cut
    off = heads.OutlineHeadSpec(gems.StoneSpec("marquise", 10.0, 5.0), v_prongs=False)
    assert off.point_kinds().count("v") == 0 and off.count == 4 and off.stem != m.stem
    assert heads.OutlineHeadSpec(gems.StoneSpec("oval", 8.0, 6.0)).point_kinds().count("v") == 0
    assert heads.OutlineHeadSpec(gems.StoneSpec("oval", 8.0, 6.0), v_prongs=True).validate()   # no points to cover


def test_v_prong_wraps_the_point_and_the_head_still_seats(tmp_path):
    """The V covers the point (metal ahead of it, past the clearance) and leaves it its ledge and drop-in."""
    import numpy as np
    s = heads.OutlineHeadSpec(gems.StoneSpec("marquise", 10.0, 5.0))
    m = heads.outline_design_mesh(s, ops=Blended())
    m.export(tmp_path / "h.stl")
    rep = heads.check_outline_head(s, tmp_path / "h.stl", float(m.volume))
    assert rep.status == "passed", rep.text()
    # a ray along the axis at the girdle, from beyond each point back towards the stone, meets metal first
    for sx in (1.0, -1.0):
        origin = np.array([[sx * 8.0, 0.0, 0.0]])
        locs, _, _ = m.ray.intersects_location(origin, np.array([[-sx, 0.0, 0.0]]), multiple_hits=False)
        assert len(locs) and abs(locs[0][0]) > s.stone.length / 2 + s.clearance
