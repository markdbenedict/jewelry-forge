import math

import pytest

from ntopjewel import catalog, gems, heads
from .pseudo_blend import Blended


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
    m = heads.design_mesh(s, ops=Blended())                # as nTop builds it: the junctions filled by the blend
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


def test_prong_head_recipe_builds_a_cutter_input_block_then_a_harness_wiring_both(tmp_path):
    """The head block takes the seat cutter as an implicit input and holds no other block; the
    build embeds the saved block in a fresh notebook at once (self-test); the harness embeds
    stone_seat and prong_head side by side and wires the seat's output into the head."""
    from .fake_notebook import FakeNotebook
    from .test_notebook_api import load_recipe
    seat = load_recipe("stone_seat")
    env = tmp_path / "env.stl"
    gems.SeatSpec(gems.StoneSpec("round", 6.5)).envelope().export(str(env))
    seat.build(FakeNotebook(), {"save_to": str(tmp_path / "sh.ntop"), "recipe_to": str(tmp_path / "sh.json"),
                                "test_output": str(tmp_path / "s.stl"), "values": {"Seat Path": str(env)}})
    mod = load_recipe("prong_head")
    params = mod.prepare({}, tmp_path)
    params.update({"save_to": str(tmp_path / "ph.ntop"), "recipe_to": str(tmp_path / "ph.json"),
                   "test_output": str(tmp_path / "h.stl"), "seat_block": str(tmp_path / "stone_seat.ntop")})
    nb = FakeNotebook()
    res = mod.build(nb, params)
    blk = res["block"]
    assert blk["identifiers"]["Seat Cutter"] == "core.var<implicit>" and "Seat" not in blk["identifiers"]
    assert blk["identifiers"]["Prongs"].startswith("polar_array_implicit") and blk["self_test"]["accepted"]
    head_id = res["identifiers"]["block:prong_head"]
    assert head_id.endswith("<implicit,integer," + ",".join(["real"] * 14) + ">")        # cutter, count, 13 reals + the blend radius
    assert res["identifiers"]["block:stone_seat"].endswith("<text,real>")
    head_inst = res["blocks"]["Prong Head"]
    assert nb.blocks[head_inst]["wired"]["Seat Cutter"][0] == res["blocks"]["Stone Seat"]
    assert nb.inputs == mod.INPUT_ORDER and nb.output == "Volume" and res["warnings"] == [] and nb.lint() == []
    assert list(catalog.load("prong_head_harness").inputs) == mod.INPUT_ORDER


def test_a_block_output_used_twice_is_refused_by_the_fake_as_by_ntop(tmp_path, monkeypatch):
    """nTop 6.3.3 (bisected 2026-10-28): a block notebook feeding one Point to the rod and a sphere
    was refused as a custom block; the fake refuses the same, and the recipe passes the points
    through variables."""
    import pytest
    from ntopjewel import nb_jewel as nj
    from ntopjewel.notebook_api import ConsoleError
    from .fake_notebook import FakeNotebook
    from .test_notebook_api import load_recipe
    mod = load_recipe("prong_head")
    p = {"block_to": str(tmp_path / "prong_head.ntop"), "block_recipe_to": str(tmp_path / "ph.block.json")}
    assert mod.build_block(FakeNotebook(), p, mod._test_values())["self_test"]["accepted"]
    wrap = nj.Helper.wrap_var
    monkeypatch.setattr(nj.Helper, "wrap_var",                                  # the old build: the points unwrapped
                        lambda self, name, bid: bid if name.endswith(" Point") else wrap(self, name, bid))
    with pytest.raises(ConsoleError, match="refuses"):
        mod.build_block(FakeNotebook(), p, mod._test_values())
