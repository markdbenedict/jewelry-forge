"""Partial bezels (the open pear of the reference photo): two mirrored walls on the flanks, a hood over each
point, a full cup under the girdle - built in nTop from primitives, gated by probes of the design's intent."""
import math

import pytest

from ntopjewel import band, catalog, gems, partial_bezel as pb, shank, solitaire
from .pseudo_blend import Blended


def pear(**kw):
    return pb.PartialBezelSpec(gems.StoneSpec("pear", 10.0, 7.0, 4.5), **kw)


def test_the_walls_are_stretches_of_the_outline_turned_into_angles():
    s = pear()
    assert s.validate() == []
    lo, hi = s.span
    assert 0.1 < lo < 0.25 and hi == pytest.approx(0.70)
    a_from, a_to = s.angles()
    assert 90 < a_from < 180 and 0 < a_to < 90 and a_from > a_to                   # point side first
    for f, a in ((lo, a_from), (hi, a_to)):                                          # the angle lands on the outline point
        q, m = pb.station(s.stone, f)
        assert math.degrees(math.atan2(q[1], q[0] - s.centre_x)) == pytest.approx(a, abs=1e-6)
        assert q[1] > 0 and m @ (q - [s.centre_x, 0]) > 0                            # +y half, outward normal
    hq, _ = pb.station(s.stone, lo)
    assert math.hypot(hq[0] + 5.0, hq[1]) == pytest.approx(s.hood_reach + pb.HOOD_GAP_MM, abs=0.05)   # just past the hood
    assert s.hood_points == [-5.0] and pear(hoods=False).hood_points == []
    v = s.notebook_inputs("e", "", "o")
    assert list(v) == list(catalog.load("partial_bezel_head_harness").inputs)
    assert v["Hood 2 X"] == pb.FAR_X_MM and v["Cup Top"] < -s.stone.girdle / 2 < s.z_top < v["Hood Top"]


@pytest.mark.parametrize("shape,L,W,hoods", [("marquise", 10.0, 5.0, 2), ("oval", 8.0, 6.0, 0), ("round", 6.5, None, 0),
                                             ("emerald", 8.0, 6.0, 0)])
def test_any_outline(shape, L, W, hoods):
    s = pb.PartialBezelSpec(gems.StoneSpec(shape, L, W))
    assert s.validate() == [] and len(s.hood_points) == hoods
    lo, hi = s.span
    if shape == "marquise":
        assert lo == pytest.approx(1 - hi, abs=0.01)                                 # between its hoods, symmetric
    else:
        assert (lo, hi) == pb.SIDES_SPAN                                             # an east-west half bezel


def test_what_is_refused():
    assert any("full bezel" in q for q in pear(wall_from=0.0, wall_to=1.0).validate())
    assert any("0 <= from < to" in q for q in pear(wall_from=0.7, wall_to=0.3).validate())
    assert any("holds nothing" in q for q in pear(wall_from=0.40, wall_to=0.45).validate())
    assert any("wall floor" in q for q in pear(wall_mm=0.4).validate())
    assert any("partial bezel holds" in q for q in pb.PartialBezelSpec(gems.StoneSpec("pearl", 8.0)).validate())


@pytest.mark.parametrize("stone", [gems.StoneSpec("pear", 10.0, 7.0, 4.5), gems.StoneSpec("pear", 12.3, 8.9, 4.6),
                                   gems.StoneSpec("marquise", 10.0, 5.0), gems.StoneSpec("oval", 8.0, 6.0)])
def test_design_head_passes_its_gate(stone, tmp_path):
    s = pb.PartialBezelSpec(stone)
    m = s.design_mesh(ops=Blended())
    assert m.is_watertight and m.body_count == 1
    m.export(tmp_path / "h.stl")
    rep = pb.check_partial_bezel(s, tmp_path / "h.stl", float(m.volume))
    assert rep.status == "passed", rep.text()
    names = {c.name for c in rep.checks}
    assert {"walls", "bearing", "stone fits", "drop-in clear", "design volume"} <= names
    assert ("hoods" in names) == bool(s.hood_points)


@pytest.mark.parametrize("fault,lost", [("noside", "walls"), ("nohood", "hoods"), ("fullbezel", "open")])
def test_head_end_to_end_and_a_broken_notebook_is_caught(fault, lost, fake_ntopcl, tmp_path, monkeypatch):
    nb = tmp_path / "partial_bezel_head_harness.ntop"
    nb.write_bytes(b"fake")
    s = pear()
    res = pb.build_partial_bezel(s, tmp_path / "out", notebook=nb)
    assert res.status == "passed", res.text()
    monkeypatch.setenv("FAKE_NTOPCL_SHAPE", fault)
    bad = pb.build_partial_bezel(s, tmp_path / "out", notebook=nb)
    assert bad.status == "failed" and lost in {c.name for c in bad.gate.failures()}, bad.text()


def test_recipe_builds_on_the_fake_api_from_ntop_primitives(tmp_path):
    from .fake_notebook import FakeNotebook
    from .test_notebook_api import load_recipe
    env = tmp_path / "env.stl"
    gems.SeatSpec(gems.StoneSpec("pear", 10.0, 7.0, 4.5)).envelope().export(str(env))
    load_recipe("stone_seat").build(FakeNotebook(), {"save_to": str(tmp_path / "sh.ntop"), "recipe_to": str(tmp_path / "sh.json"),
                                                     "test_output": str(tmp_path / "s.stl"), "values": {"Seat Path": str(env)}})
    ph = load_recipe("partial_bezel_head")
    pp = ph.prepare({}, tmp_path)
    pp.update({"save_to": str(tmp_path / "ph.ntop"), "recipe_to": str(tmp_path / "ph.json"), "test_output": str(tmp_path / "p.stl"),
               "seat_block": str(tmp_path / "stone_seat.ntop"), "block_to": str(tmp_path / "partial_bezel_head.ntop")})
    nb = FakeNotebook()
    res = ph.build(nb, pp)
    assert res["block"]["self_test"]["accepted"] and nb.inputs == ph.INPUT_ORDER and res["warnings"] == []
    assert list(catalog.load("partial_bezel_head_harness").inputs) == ph.INPUT_ORDER


def test_cli_partial_bezel_dry_run(capsys):
    from ntopjewel import cli
    assert cli.main(["head", "--partial-bezel", "--shape", "pear", "--length", "10", "--width", "7", "--depth", "4.5", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "partial bezel" in out and "Wall From Angle" in out and "a hood over the point" in out
    assert cli.main(["head", "--partial-bezel", "--shape", "oval", "--length", "8", "--width", "6", "--no-hood", "--dry-run"]) == 0
    assert "no hoods" in capsys.readouterr().out


# ---- the ring ------------------------------------------------------------------------------------
def reference_ring(**kw):
    """The reference photo's ring: a 10 x 7 pear in a partial bezel low between broad domed shoulders,
    the band 9.5 x 3.3 at the head tapering to 2.8 x 1.7, no arches."""
    b = band.BandSpec(size=6, profile="half-round", width_mm=9.5, thickness_mm=3.3, mesh_tolerance_mm=0.05)
    sh = shank.ShankSpec(b, width_bottom_mm=2.8, thickness_bottom_mm=1.7)
    return solitaire.SolitaireSpec(b, pear(lip_mm=0.8, mesh_tolerance_mm=0.05), shank=sh, cathedral=False, **kw)


def test_reference_ring_spec():
    s = reference_ring()
    assert s.validate() == [] and s.kind == "partial" and s.cupped and not s.bezel
    assert s.catalog_name == "solitaire_partial_bezel" and "_pbezel_" in s.stem
    assert s.placed_head.bottom_frac == 0.0 and s.placed_head.floor_z is not None        # the cup carried down into the band
    v = s.notebook_inputs("E", "O")
    assert list(v) == list(catalog.load("solitaire_partial_bezel").inputs)
    assert "Windows Path" not in v and v["Head Blend"] == s.head.blend


def test_reference_ring_end_to_end(fake_ntopcl, tmp_path, out_dir):
    nb = tmp_path / "solitaire_partial_bezel.ntop"
    nb.write_bytes(b"fake")
    res = solitaire.build(reference_ring(), out_dir, notebook=nb)
    assert res.status == "passed", res.text()
    names = {c.name for c in res.gate.checks}
    assert {"walls", "open", "hoods", "point clear", "bearing", "seated", "section shape", "design volume"} <= names


def test_solitaire_recipe_builds_on_the_fake_api(tmp_path):
    from .fake_notebook import FakeNotebook
    from .test_notebook_api import load_recipe
    env = tmp_path / "env.stl"
    gems.SeatSpec(gems.StoneSpec("pear", 10.0, 7.0, 4.5)).envelope().export(str(env))
    load_recipe("stone_seat").build(FakeNotebook(), {"save_to": str(tmp_path / "sh.ntop"), "recipe_to": str(tmp_path / "sh.json"),
                                                     "test_output": str(tmp_path / "s.stl"), "values": {"Seat Path": str(env)}})
    ph = load_recipe("partial_bezel_head")
    pp = ph.prepare({}, tmp_path)
    pp.update({"save_to": str(tmp_path / "ph.ntop"), "recipe_to": str(tmp_path / "ph.json"), "test_output": str(tmp_path / "p.stl"),
               "seat_block": str(tmp_path / "stone_seat.ntop"), "block_to": str(tmp_path / "partial_bezel_head.ntop")})
    ph.build(FakeNotebook(), pp)
    sp = load_recipe("solitaire_partial_bezel")
    params = sp.prepare({}, tmp_path)
    params.update({"save_to": str(tmp_path / "sp.ntop"), "recipe_to": str(tmp_path / "sp.json"), "test_output": str(tmp_path / "r.stl"),
                   "seat_block": str(tmp_path / "stone_seat.ntop"), "head_block": str(tmp_path / "partial_bezel_head.ntop")})
    nb = FakeNotebook()
    res = sp.build(nb, params)
    assert nb.blocks[res["blocks"]["Partial Bezel Head"]]["wired"]["Seat Cutter"][0] == "Seat Local"
    assert nb.inputs == sp.INPUT_ORDER == list(catalog.load("solitaire_partial_bezel").inputs) and res["warnings"] == []


def test_cli_solitaire_partial_bezel_dry_run(capsys):
    from ntopjewel import cli
    assert cli.main(["solitaire", "--partial-bezel", "--shape", "pear", "--length", "10", "--stone-width", "7", "--stone-depth", "4.5",
                     "--profile", "half-round", "--width", "9.5", "--thickness", "3.3", "--width-bottom", "2.8",
                     "--thickness-bottom", "1.7", "--lip", "0.8", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "_pbezel_" in out and "Wall From Angle" in out and "arch:" not in out.split("Wall From Angle")[0].split("partial bezel")[1]
