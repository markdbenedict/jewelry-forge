"""The bezel head: a wall and cup round any outline, a lip, light windows."""
import pytest

from ntopjewel import band, catalog, gems, heads, solitaire, tables
from .pseudo_blend import Blended


def round_bezel(**kw):
    return heads.BezelSpec(gems.StoneSpec("round", 6.5), **kw)


def test_bezel_numbers_come_from_the_tables():
    b = round_bezel()
    assert b.wall == tables.SETTINGS["bezel_wall_mm"] and b.lip == tables.SETTINGS["bezel_lip_mm"]
    assert b.z_top == pytest.approx(b.stone.girdle / 2 + b.lip)
    z0, z1 = b.window_zone()
    assert z1 == pytest.approx(-b.stone.girdle / 2 - b.bearing) and b.n_windows == 6 and b.validate() == []
    assert round_bezel(wall_mm=0.4).validate() and round_bezel(wall_mm=1.5).validate()       # under the floor / too stiff to burnish
    shallow = heads.BezelSpec(gems.StoneSpec("marquise", 10, 5))
    assert shallow.n_windows == 0 and shallow.validate() == []                              # no room: a closed cup by default
    assert heads.BezelSpec(gems.StoneSpec("marquise", 10, 5), windows=6).validate()          # asked for, and no room: refused


@pytest.mark.parametrize("shape,L,W", [("round", 6.5, None), ("pear", 12.3, 8.9), ("emerald", 8.0, 6.0)])
def test_design_bezels_pass_their_gate(shape, L, W, tmp_path):
    b = heads.BezelSpec(gems.StoneSpec(shape, L, W))
    m = b.design_mesh(ops=Blended())                      # as nTop builds it: the rim rounded by the blend
    m.export(tmp_path / "b.stl")
    rep = heads.check_bezel(b, tmp_path / "b.stl", float(m.volume))
    assert rep.status == "passed", rep.text()
    assert {"seated", "drop-in clear", "bezel wall", "stone fits"} <= {c.name for c in rep.checks}


def test_a_wall_too_thin_is_caught(tmp_path):
    """The wall ring check sees a bezel thinner than the floor (built so on purpose)."""
    b = round_bezel()
    thin = heads.bezel_mesh({**b.notebook_inputs(""), "Wall": 0.3}, b.seat.envelope(), b.windows_mesh())
    thin.export(tmp_path / "t.stl")
    assert heads.bezel_wall_check(b, thin).status == "failed"


def test_bezel_end_to_end_and_an_uncut_seat_is_caught(fake_ntopcl, tmp_path, monkeypatch):
    nb = tmp_path / "bezel_head_harness.ntop"
    nb.write_bytes(b"fake")
    res = heads.build_bezel(round_bezel(), tmp_path / "out", notebook=nb)
    assert res.status == "passed", res.text()
    monkeypatch.setenv("FAKE_NTOPCL_SHAPE", "noseat")
    bad = heads.build_bezel(round_bezel(), tmp_path / "out", notebook=nb)
    assert bad.status == "failed" and "stone fits" in {c.name for c in bad.gate.failures()}


def bezel_ring():
    return solitaire.SolitaireSpec(band.BandSpec(size=6, profile="court", mesh_tolerance_mm=0.05), round_bezel())


def test_bezel_solitaire_spec_and_inputs():
    s = bezel_ring()
    assert s.validate() == [] and s.bezel and "_bezel_" in s.stem and s.catalog_name == "solitaire_bezel"
    assert s.girdle_radius + s.placed_head.lowest_z() < s.band.outer_radius_mm - 0.2       # the cup stands in the band
    assert s.girdle_radius + s.placed_head.lowest_z() >= s.band.bore_radius_mm + 0.2 - 1e-6
    assert list(s.notebook_inputs("E", "O")) == list(catalog.load("solitaire_bezel").inputs)


def test_bezel_solitaire_end_to_end(fake_ntopcl, tmp_path):
    nb = tmp_path / "solitaire_bezel.ntop"
    nb.write_bytes(b"fake")
    res = solitaire.build(bezel_ring(), tmp_path / "out", notebook=nb)
    assert res.status == "passed", res.text()
    assert {"seated", "bezel wall", "arch milgrain"} <= {c.name for c in res.gate.checks}


def test_bezel_recipes_build_on_the_fake_api(tmp_path):
    from .fake_notebook import FakeNotebook
    from .test_notebook_api import load_recipe
    env = tmp_path / "env.stl"
    gems.SeatSpec(gems.StoneSpec("round", 6.5)).envelope().export(str(env))
    load_recipe("stone_seat").build(FakeNotebook(), {"save_to": str(tmp_path / "sh.ntop"), "recipe_to": str(tmp_path / "sh.json"),
                                                     "test_output": str(tmp_path / "s.stl"), "values": {"Seat Path": str(env)}})
    bh = load_recipe("bezel_head")
    pp = bh.prepare({}, tmp_path)
    pp.update({"save_to": str(tmp_path / "bh.ntop"), "recipe_to": str(tmp_path / "bh.json"), "test_output": str(tmp_path / "b.stl"),
               "seat_block": str(tmp_path / "stone_seat.ntop")})
    nb = FakeNotebook()
    res = bh.build(nb, pp)
    assert res["block"]["self_test"]["accepted"] and nb.inputs == bh.INPUT_ORDER and res["warnings"] == []
    sb = load_recipe("solitaire_bezel")
    params = sb.prepare({}, tmp_path)
    params.update({"save_to": str(tmp_path / "sb.ntop"), "recipe_to": str(tmp_path / "sb.json"), "test_output": str(tmp_path / "r.stl"),
                   "seat_block": str(tmp_path / "stone_seat.ntop"), "head_block": str(tmp_path / "bezel_head.ntop")})
    nb = FakeNotebook()
    res = sb.build(nb, params)
    assert nb.blocks[res["blocks"]["Bezel Head"]]["wired"]["Seat Cutter"][0] == "Seat Local"
    assert nb.inputs == sb.INPUT_ORDER and res["warnings"] == []


def test_cli_bezel_dry_runs(capsys):
    from ntopjewel import cli
    assert cli.main(["head", "--bezel", "--length", "6.5", "--dry-run"]) == 0
    assert "Windows Path" in capsys.readouterr().out
    assert cli.main(["solitaire", "--bezel", "--size", "6", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "_bezel_" in out and "Bezel Top" in out
