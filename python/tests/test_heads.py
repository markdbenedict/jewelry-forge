import math

import pytest

from ntopjewel import catalog, gems, heads


def spec(n=6, **kw):
    return heads.HeadSpec(gems.StoneSpec("round", 6.5), prongs=n, **kw)


def test_defaults_respect_the_floors_and_the_pavilion():
    for n in (4, 6):
        s = spec(n)
        assert s.validate() == []
        assert 2 * s.rho - s.ledge_mm - s.clearance >= 0.8          # the prong left above the girdle
    assert spec(prong_dia_mm=1.0).validate()                         # 0.65 mm left: refused
    assert spec(rail_below_girdle_mm=0.4).validate()                 # rail in the pavilion: refused
    assert heads.HeadSpec(gems.StoneSpec("oval", 8, 6)).validate()  # v1 is round only


def test_notebook_inputs_match_the_catalog_and_place_the_first_prong():
    s = spec(4)
    ins = s.notebook_inputs("E.stl", "O.stl")
    assert list(ins) == list(catalog.load("prong_head_harness").inputs)
    assert ins["Prong Count"] == 4 and ins["Prong Spacing"] == 90.0
    assert math.degrees(math.atan2(ins["Tip Y"], ins["Tip X"])) == pytest.approx(45.0)
    assert math.hypot(ins["Tip X"], ins["Tip Y"]) == pytest.approx(3.25 + s.rho - 0.3, abs=1e-3)


def test_the_design_head_fits_sits_and_drops_in(tmp_path):
    s = spec(6)
    m = heads.design_mesh(s)
    assert m.is_watertight and len(m.split(only_watertight=False)) == 1
    m.export(tmp_path / "h.stl")
    rep = heads.check_head(s, tmp_path / "h.stl", float(m.volume))
    assert rep.status == "passed", rep.text()


def test_head_end_to_end_and_the_missing_seat_is_caught(fake_ntopcl, tmp_path, monkeypatch):
    nb = tmp_path / "prong_head_harness.ntop"
    nb.write_bytes(b"fake")
    res = heads.build_head(spec(6), tmp_path / "out", notebook=nb)
    assert res.status == "passed", res.text()
    monkeypatch.setenv("FAKE_NTOPCL_SHAPE", "noseat")                 # a block that never subtracts the seat
    bad = heads.build_head(spec(6), tmp_path / "out", notebook=nb)
    failed = {c.name for c in bad.gate.failures()}
    assert bad.status == "failed" and {"stone fits", "drop-in clear", "design volume"} <= failed


def test_prong_head_recipe_builds_the_block_with_the_seat_inside_then_the_harness(tmp_path, monkeypatch):
    from .fake_notebook import FakeNotebook
    from .test_notebook_api import load_recipe
    seat = load_recipe("stone_seat")
    env = tmp_path / "env.stl"
    gems.SeatSpec(gems.StoneSpec("round", 6.5)).envelope().export(str(env))
    nb = FakeNotebook()
    seat.build(nb, {"save_to": str(tmp_path / "sh.ntop"), "recipe_to": str(tmp_path / "sh.json"),
                    "test_output": str(tmp_path / "s.stl"), "values": {"Seat Path": str(env)}})
    mod = load_recipe("prong_head")
    params = mod.prepare({}, tmp_path)
    params.update({"save_to": str(tmp_path / "ph.ntop"), "recipe_to": str(tmp_path / "ph.json"),
                   "test_output": str(tmp_path / "h.stl"), "seat_block": str(tmp_path / "stone_seat.ntop")})
    nb2 = FakeNotebook()
    res = mod.build(nb2, params)
    blk = res["block"]
    assert blk["identifiers"]["Prongs"].startswith("polar_array_implicit") and blk["identifiers"]["Seat"].startswith("user_func_")
    assert blk["identifiers"]["Seated"].startswith("boolean_subtract") and (tmp_path / "prong_head.ntop").exists()
    ident = res["identifiers"]["block:prong_head"]
    assert ident.startswith("user_func_") and ident.endswith("<text,real,integer,real,real,real,real,real,real,real,real,real,real,real,real,real>")
    assert nb2.inputs == mod.INPUT_ORDER and nb2.output == "Volume" and res["warnings"] == [] and nb2.lint() == []
    assert list(catalog.load("prong_head_harness").inputs) == mod.INPUT_ORDER
