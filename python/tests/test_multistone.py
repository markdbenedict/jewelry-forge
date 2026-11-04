"""Multi-stone rings (Phase 3 step 2): the side stones' angles solved against their neighbours, the
pear's point turned to the centre, the notebook's five slots, and the ring end to end on the
simulated nTop - including the gate catching a notebook whose side slots never got their own values."""
import math

import numpy as np
import pytest

from ntopjewel import band, catalog, gems, heads, multistone as ms


def ring_band():
    return band.BandSpec(size=6, width_mm=2.6, thickness_mm=1.8, profile="court", mesh_tolerance_mm=0.05)


def three(centre=("round", 6.5, None), side=("round", 4.0, None), **kw):
    return ms.MultiStoneSpec(ring_band(), heads.OutlineHeadSpec(gems.StoneSpec(centre[0], centre[1], centre[2])),
                             heads.OutlineHeadSpec(gems.StoneSpec(side[0], side[1], side[2])), **kw)


def test_the_side_angle_is_the_smallest_that_clears_the_centre():
    s = three()
    assert s.validate() == []
    stones = s.stones()
    assert [p.role for p in stones] == ["centre", "side", "side"]
    t = stones[1].theta_deg
    assert t > 0 and stones[2].theta_deg == -t
    centre = (s.centre, 0.0, 0.0)
    assert s._clear(centre, (s.side, t, s.side_spin(t)))
    assert not s._clear(centre, (s.side, t - 0.5, s.side_spin(t - 0.5)))      # half a degree closer: a seat cuts a prong, or the girdles crowd
    # the smaller stone sits lower, its culet still clear of the bore
    assert s.girdle_radius(s.side) < s.girdle_radius(s.centre)
    assert s.girdle_gap(0, 1) >= s.side_gap_mm                                     # here the prongs, not the gap, set the angle
    wider = three(side_gap_mm=s.girdle_gap(0, 1) + 0.5)
    assert wider.stones()[1].theta_deg > t and wider.girdle_gap(0, 1) == pytest.approx(wider.side_gap_mm, abs=0.02)


def test_a_pear_side_stone_points_at_the_centre():
    s = three(centre=("cushion", 7.0, 6.0), side=("pear", 6.0, 4.0))
    assert s.validate() == []
    for p in s.stones()[1:]:
        m = s.matrix(p.head, p.theta_deg, p.spin_deg)
        xy = p.head.stone.outline()
        tip = xy[np.argmin(xy[:, 0])]                                              # the pear's point is at -X in its frame
        tip_ring = m @ np.array([tip[0], tip[1], 0.0, 1.0])
        centre_ring = m @ np.array([0.0, 0.0, 0.0, 1.0])
        a_tip, a_c = (math.degrees(math.atan2(v[1], v[0])) for v in (tip_ring, centre_ring))
        assert abs(a_tip) < abs(a_c)                                               # nearer the top than the stone's own centre


def test_five_stones_and_the_slot_limit():
    five = three(side=("round", 3.0, None), side_pairs=2)
    assert five.validate() == [] and five.stone_count == 5
    th = sorted(p.theta_deg for p in five.stones())
    assert th[0] < th[1] < 0 < th[3] < th[4]
    seven = three(side=("round", 2.5, None), side_pairs=3)
    assert any("head slots" in x for x in seven.validate())
    mixed = ms.MultiStoneSpec(ring_band(), heads.OutlineHeadSpec(gems.StoneSpec("round", 6.5)),
                              heads.OutlineHeadSpec(gems.StoneSpec("round", 4.0), clearance_mm=0.1))
    assert any("one seat clearance" in x for x in mixed.validate())


def test_unused_slots_repeat_the_centre_and_every_catalog_input_is_given():
    s = three()
    files = [(f"env{i}", f"prongs{i}") for i in range(s.stone_count)]
    v = s.notebook_inputs("bar.stl", files, "out.stl", pave_paths=("beads.stl", "seats.stl"))
    cat = catalog.load("multistone")
    assert set(v) == set(cat.inputs) and list(cat.inputs) == ms.input_order()
    for name, _ in ms.SLOT_FIELDS:
        assert v[ms.slot_input(name, 3)] == v[ms.slot_input(name, 4)] == v[name]          # slots 4 and 5: the centre again
    assert v["Turn 2"] == -v["Turn 3"] and v["Spin 2"] == -v["Spin 3"] == 90.0


def test_recipe_builds_on_the_fake_notebook(tmp_path):
    from .fake_notebook import FakeNotebook
    from .test_notebook_api import load_recipe
    env = tmp_path / "env.stl"
    gems.SeatSpec(gems.StoneSpec("round", 6.5)).envelope().export(str(env))          # the two blocks, built by the fake first
    load_recipe("stone_seat").build(FakeNotebook(), {"save_to": str(tmp_path / "sh.ntop"), "recipe_to": str(tmp_path / "sh.json"),
                                                     "test_output": str(tmp_path / "s.stl"), "values": {"Seat Path": str(env)}})
    oh = load_recipe("outline_head")
    pp = oh.prepare({}, tmp_path)
    pp.update({"save_to": str(tmp_path / "oh.ntop"), "recipe_to": str(tmp_path / "oh.json"), "test_output": str(tmp_path / "h.stl"),
               "seat_block": str(tmp_path / "stone_seat.ntop")})
    oh.build(FakeNotebook(), pp)
    mod = load_recipe("multistone")
    params = mod.prepare({}, tmp_path)
    params.update({"save_to": str(tmp_path / "m.ntop"), "recipe_to": str(tmp_path / "m.json"), "test_output": str(tmp_path / "m.stl"),
                   "seat_block": str(tmp_path / "stone_seat.ntop"), "head_block": str(tmp_path / "outline_head.ntop")})
    nb = FakeNotebook()
    res = mod.build(nb, params)
    b = res["blocks"]
    assert nb.inputs == mod.INPUT_ORDER and res["warnings"] == []
    for k in range(1, ms.SLOTS + 1):
        tag = f" {k}"
        sfx = "" if k == 1 else f" {k}"
        assert nb.blocks[b[f"Stone Seat{tag}"]]["wired"]["Seat Path"][0] == b[f"Seat Path{sfx}"]
        assert nb.blocks[b[f"Outline Head{tag}"]]["wired"]["Seat Cutter"][0] == b[f"Seat Local{tag}"]
        assert nb.blocks[b[f"Outline Head{tag}"]]["wired"]["Prongs Path"][0] == b[f"Prongs Path{sfx}"]
        # spin, then the quarter-turn onto +X, then the turn about the ring axis: ONE combined transform for the head and its seat
        assert nb.blocks[b[f"Head {k} Moves"]]["lists"]["Transforms"] == [b[f"Head {k} Spin"], b[f"Head {k} Quarter Turn"], b[f"Head {k} Turn"]]
        assert nb.variables[b[f"Head {k} Placement"]]["wraps"] == b[f"Head {k} Moves"]
        for what, start in (("Head", f"Outline Head{tag}"), ("Seat", f"Seat Local{tag}")):
            moved = nb.blocks[b[f"{what} {k} On Ring"]]
            assert moved["wired"]["Transformation"][0] == b[f"Head {k} Placement"] and moved["wired"]["Object"][0] == b[start]
    assert nb.blocks[b["Heads"]]["lists"]["Bodies"] == [b[f"Head {k} On Ring"] for k in range(1, ms.SLOTS + 1)]
    assert nb.blocks[b["Beaded Shank"]]["lists"]["Bodies"] == [b["Shank Body"], b["Pave Beads"]]   # the pavé's beads join the shank ...
    assert nb.blocks[b["Joined"]]["lists"]["Bodies"] == [b["Beaded Shank"], b["Heads"]]
    assert nb.blocks[b["Joined"]]["wired"]["Blend Radius"][0] == b["Shank Blend"]        # ... the heads melt into it ...
    assert nb.blocks[b["Ring"]]["wired"]["Primary Body"][0] == b["Joined"]               # ... THEN every seat is cut, the pavé's last
    assert nb.blocks[b["Ring"]]["lists"]["Subtraction Bodies"] == [b[f"Seat {k} On Ring"] for k in range(1, ms.SLOTS + 1)] + [b["Pave Seats"]]
    assert nb.blocks[b["Pave Beads Mesh"]]["wired"]["Path"][0] == b["Pave Beads Path"]


def _build(out_dir, tmp_path, spec):
    nb = tmp_path / "multistone.ntop"
    nb.write_bytes(b"fake")
    return ms.build(spec, out_dir, notebook=nb)


def test_three_stone_end_to_end(fake_ntopcl, tmp_path, out_dir):
    res = _build(out_dir, tmp_path, three())
    assert res.ok, res.text()
    names = {c.name for c in res.gate.checks}
    assert {"stones fit", "seat ledges", "drop-in clear", "bore closed under the stones", "design volume", "section shape"} <= names


def test_the_gate_catches_side_slots_left_on_the_centre(fake_ntopcl, tmp_path, out_dir, monkeypatch):
    monkeypatch.setenv("FAKE_NTOPCL_SHAPE", "noside")
    res = _build(out_dir, tmp_path, three())
    failed = {c.name for c in res.gate.checks if not c.ok}
    assert not res.ok and {"seat ledges", "design volume"} <= failed


def test_cli_multistone_dry_run(capsys):
    from ntopjewel import cli
    assert cli.main(["multistone", "--shape", "cushion", "--length", "7", "--stone-width", "6", "--side-shape", "pear",
                     "--side-length", "6", "--side-width", "4", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "point inward" in out and "Turn 2" in out and "Prongs Path 5" in out


def test_the_extents_allowance_follows_the_rails_acute_corner():
    """2026-11-03: the real round three-stone came out 7.10 mm along the finger against the sharp
    design's 7.55 - the centre's upper rail, leaning out with the pavilion, has an acute top corner
    that the blend rounds back 0.225 mm a side; the square-corner allowance (tolerance + one blend)
    was 0.40 in all."""
    h = heads.OutlineHeadSpec(gems.StoneSpec("round", 6.5))
    per_side = ms.rail_corner_shrink(h)
    assert 0.225 < per_side < 0.7 and per_side > h.blend * (2 ** 0.5 - 1)
    assert ms.rail_corner_shrink(heads.OutlineHeadSpec(gems.StoneSpec("round", 6.5), blend_mm=0.0)) == 0.0


def test_stones_sized_by_weight_and_pears_pointing_out():
    """The ruby demo (2026-11-03): a 1.5 ct cushion, two 0.5 ct pears with their points away from it."""
    c = gems.StoneSpec.for_carats("cushion", 1.5, material="sapphire")
    p = gems.StoneSpec.for_carats("pear", 0.5, material="sapphire")
    assert c.carats() == pytest.approx(1.5, abs=0.005) and p.carats() == pytest.approx(0.5, abs=0.005)
    assert c.length / c.width == pytest.approx(gems.RATIO["cushion"], abs=0.01)
    s = ms.MultiStoneSpec(ring_band(), heads.OutlineHeadSpec(c), heads.OutlineHeadSpec(p), side_point="out")
    assert s.validate() == []
    for q in s.stones()[1:]:
        m = s.matrix(q.head, q.theta_deg, q.spin_deg)
        xy = q.head.stone.outline()
        tip = m @ np.array([*xy[np.argmin(xy[:, 0])], 0.0, 1.0])
        mid = m @ np.array([0.0, 0.0, 0.0, 1.0])
        assert abs(math.atan2(tip[1], tip[0])) > abs(math.atan2(mid[1], mid[0]))          # the point further from the top
    inward = ms.MultiStoneSpec(ring_band(), heads.OutlineHeadSpec(c), heads.OutlineHeadSpec(p))
    assert "side_point" not in inward.design() and s.spec_id != inward.spec_id
    # every prong reaches under its girdle, counted prong by prong (pieces fuse with the centre's metal)
    d = s.design_mesh()
    q = s.stones()[1]
    local = d.copy()
    local.apply_transform(np.linalg.inv(s.matrix(q.head, q.theta_deg, q.spin_deg)))
    under, _ = heads.seat_regions(q.head.stone, q.head.clearance)
    g = q.head.stone.girdle
    assert ms.prong_ledges(local, s.placed_head(q.head), -g / 2 - 0.3, under) == 5
    assert heads.outline_count(local, -g / 2 - 0.3, under) < 5                              # the piece count misses one



def ruby():
    """Mark's ring (2026-11-04): a marquise ruby (corundum: 'sapphire' in the tables) between two cushion
    diamonds, diamond pavé round the rest of the ring."""
    b = band.BandSpec(size=6, width_mm=2.6, thickness_mm=1.8, profile="comfort-flat", mesh_tolerance_mm=0.05)   # a court band's dome
    return ms.MultiStoneSpec(b, heads.OutlineHeadSpec(gems.StoneSpec("marquise", 10.0, 5.0, material="sapphire")),   # left 0.2 mm lips
                             heads.OutlineHeadSpec(gems.StoneSpec("cushion", 4.5, 4.5, material="diamond")), pave_stone_mm=1.3)


def test_pave_round_a_three_stone_ring(fake_ntopcl, tmp_path, out_dir, monkeypatch):
    """Pavé centred on the bottom, its first stones clear of the side heads, the beads before the heads
    and the seats after, the pavé's gate checks on top of the three-stone ones; a lost seats layer caught."""
    s = ruby()
    assert s.validate() == [], s.validate()
    pv = s.pave
    assert pv.centre_deg == 180.0 and pv.stone_count >= 20
    assert pv.reach_from_top_deg > s.head_face_reach_deg() + 2.0                  # the pavé starts past the heads' metal
    assert "_pave1x1p3_" in s.stem and s.design()["pave"]["pave_stone"] == 1.3
    assert s.design() != ruby().__class__(s.band, s.centre, s.side).design()      # the pavé is in the identity ...
    plain = three()
    assert "pave" not in plain.design()                                           # ... and the rings without keep theirs
    beads, seats = plain.pave_layers()
    assert beads.volume < 0.01 and seats.volume < 0.01                            # no pavé: the no-op specks
    res = _build(out_dir, tmp_path, s)
    assert res.ok, res.text()
    names = {c.name for c in res.gate.checks}
    assert {"pavé stones fit", "pavé seats", "pavé light holes open", "pavé beads", "pavé stones held", "stones fit"} <= names
    assert abs(s.carats() - (0.87 + 2 * 0.40 + pv.carats())) < 0.05
    monkeypatch.setenv("FAKE_NTOPCL_SHAPE", "nopave")
    bad = _build(out_dir, tmp_path, s)
    assert not bad.ok and "pavé seats" in {c.name for c in bad.gate.checks if not c.ok}
    from ntopjewel import cli
    assert cli.main(["multistone", "--profile", "comfort-flat", "--width", "2.6", "--thickness", "1.8", "--shape", "marquise", "--length", "10",
                     "--stone-width", "5", "--material", "sapphire", "--side-shape", "cushion", "--side-length", "4.5",
                     "--side-width", "4.5", "--side-material", "diamond", "--pave", "1.3", "--dry-run"]) == 0
    late = ms.MultiStoneSpec(s.band, s.centre, s.side, pave_stone_mm=1.3, pave_from_deg=30.0)
    assert any("cut" in x and "side heads" in x for x in late.validate())          # a pavé started inside the side heads


def test_the_combined_placement_follows_the_measured_order(tmp_path, monkeypatch):
    """Combine Transforms' list order is measured in nTop (transform_probe -> api_facts.json): when
    nTop applies the list last-first, the moves are laid out reversed so spin -> quarter-turn -> turn
    still happen in that order; with nothing measured the build refuses, naming the probe."""
    import json
    from ntopjewel import nb_jewel as nj
    from ntopjewel.notebook_api import ConsoleError
    from .fake_notebook import FakeNotebook
    h = nj.Helper(FakeNotebook())
    t = [h.rotation(f"R{k}", nj.angle_variable(h, f"A{k}", 10.0 * k)) for k in range(3)]
    facts = tmp_path / "facts.json"
    facts.write_text(json.dumps({"combine_transforms_order": "reverse"}))
    monkeypatch.setenv("NTOPJEWEL_API_FACTS", str(facts))
    c = h.combine("C", t)
    assert h.nb.blocks[c]["lists"]["Transforms"] == t[::-1]
    monkeypatch.setenv("NTOPJEWEL_API_FACTS", str(tmp_path / "missing.json"))
    monkeypatch.setattr(nj, "API_FACTS", tmp_path / "missing.json")
    with pytest.raises(ConsoleError, match="transform_probe"):
        h.combine("C2", t)
