import math

import numpy as np
import pytest

from ntopjewel import gems, tables


@pytest.mark.parametrize("shape,L,W", [("round", 6.5, None), ("oval", 8, 6), ("pear", 12.3, 8.9),
                                       ("marquise", 10, 5), ("cushion", 7, 7), ("emerald", 8, 6)])
def test_every_shape_is_an_exact_closed_convex_stone(shape, L, W):
    s = gems.StoneSpec(shape, L, W)
    m = s.mesh()
    assert s.validate() == [] and m.is_watertight and m.is_winding_consistent and m.is_convex
    assert np.allclose(m.extents, [L, W or L, s.depth], atol=1e-3)
    xy = s.outline()
    assert 0.5 * np.sum(xy[:, 0] * np.roll(xy[:, 1], -1) - np.roll(xy[:, 0], -1) * xy[:, 1]) > 0   # CCW


def test_round_matches_the_trade_carat_figure():
    """A 6.5 mm ideal round brilliant is 1.00 ct in the trade tables: the proportions are right."""
    assert gems.StoneSpec("round", 6.5).carats() == pytest.approx(1.0, abs=0.05)
    s = gems.StoneSpec("round", 6.5)
    crown, pav = s.heights
    cone = math.pi / 3 * (6.5 / 2) ** 2 * pav                        # the pavilion alone is a cone
    assert s.volume_mm3() > cone and s.depth == pytest.approx(0.61 * 6.5, abs=0.01)


def test_calipered_depth_scales_crown_and_pavilion_not_the_girdle():
    s = gems.StoneSpec("pear", 12.3, 8.9, 4.6, material="glass")
    crown, pav = s.heights
    assert s.depth == pytest.approx(4.6) and crown / pav == pytest.approx(15 / 43)
    assert s.girdle == pytest.approx(0.03 * 8.9)
    assert s.carats() == pytest.approx(s.volume_mm3() * 2.6 / 1000 / 0.2)
    xy = s.outline()
    assert xy[np.argmin(xy[:, 0]), 1] == pytest.approx(0.0, abs=0.05)   # the point is at -X, on the axis


def test_stone_names_and_validation(tmp_path):
    assert gems.StoneSpec("round", 6.5).stem == "stone_round_6p5x3p96"
    assert gems.StoneSpec("pear", 12.3, 8.9, 4.6).stem == "stone_pear_12p3x8p9x4p60"
    assert gems.StoneSpec("oval", 6, 8).validate()                    # length is the long side
    assert gems.StoneSpec("round", 6.5, depth_mm=0.2).validate()
    assert gems.StoneSpec("triangle", 6).validate()
    info = gems.StoneSpec("oval", 8, 6).write(tmp_path)
    assert info["watertight"] and (tmp_path / "stone_oval_8x6x3p66.stl").exists()
    assert (tmp_path / "stone_oval_8x6x3p66.stone.json").exists()


def test_cli_gem(tmp_path, capsys):
    from ntopjewel import cli
    assert cli.main(["gem", "--shape", "pear", "--length", "12.3", "--width", "8.9", "--depth", "4.6",
                     "--material", "glass", "--out", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "2.03 ct glass" in out and "diamond" in out and (tmp_path / "stone_pear_12p3x8p9x4p60.stl").exists()


# ------------------------------------------------------------------ seats
def test_steiner_offset_volume_is_exact_for_a_box():
    import trimesh
    c = 0.1
    assert gems.offset_volume_mm3(trimesh.creation.box((1, 1, 1)), c) == pytest.approx(
        1 + 6 * c + 3 * math.pi * c * c + 4 / 3 * math.pi * c ** 3, rel=1e-12)


def test_seat_envelope_is_the_stone_with_a_straight_drop_in_path():
    s = gems.SeatSpec(gems.StoneSpec("pear", 12.3, 8.9, 4.6))
    e = s.envelope()
    assert e.is_convex and e.is_watertight
    _, pav = s.stone.heights
    assert e.bounds[1, 2] == pytest.approx(s.drop) and e.bounds[0, 2] == pytest.approx(-s.stone.girdle / 2 - pav)
    assert e.volume > s.stone.volume_mm3()
    assert s.clearance == tables.SETTINGS["seat_clearance_mm"] and s.stem.startswith("seat_pear_12p3x8p9x4p60_c0p05_")
    with pytest.raises(ValueError, match="does not clear"):
        gems.seat_envelope(s.stone, 1.0)


def test_seat_end_to_end_with_fake_ntopcl(fake_ntopcl, tmp_path):
    nb = tmp_path / "stone_seat_harness.ntop"
    nb.write_bytes(b"fake")
    spec = gems.SeatSpec(gems.StoneSpec("round", 6.5))
    res = gems.build_seat(spec, tmp_path / "out", notebook=nb)
    assert res.status == "passed", res.text()
    checks = {c.name: c for c in res.gate.checks}
    assert checks["design volume"].ok and checks["extents"].ok and "wall thickness" not in checks
    assert res.ntop_volume_mm3 == pytest.approx(spec.design_volume_mm3(), rel=0.01)
    assert (res.run_dir / f"{spec.stem}.envelope.stl").exists() and (res.run_dir / f"{spec.stem}.report.json").exists()


def test_seat_without_clearance_applied_is_rejected(fake_ntopcl, tmp_path, monkeypatch):
    """A block that ignores its Clearance input returns the bare envelope: the extents and the
    design volume both catch it."""
    nb = tmp_path / "stone_seat_harness.ntop"
    nb.write_bytes(b"fake")
    spec = gems.SeatSpec(gems.StoneSpec("round", 6.5), clearance_mm=0.15)
    monkeypatch.setattr(gems.SeatSpec, "notebook_inputs",
                        lambda self, a, b: {"Seat Path": a, "Clearance": 0.0, "Mesh Tolerance": 0.05, "Output Path": b})
    res = gems.build_seat(spec, tmp_path / "out", notebook=nb)
    failed = {c.name for c in res.gate.failures()}
    assert res.status == "failed" and {"extents", "design volume"} <= failed


def test_stone_seat_recipe_builds_block_then_harness(tmp_path):
    from .fake_notebook import FakeNotebook
    from .test_notebook_api import load_recipe
    mod = load_recipe("stone_seat")
    env = tmp_path / "env.stl"
    gems.SeatSpec(gems.StoneSpec("round", 6.5)).envelope().export(str(env))
    nb = FakeNotebook()
    res = mod.build(nb, {"save_to": str(tmp_path / "h.ntop"), "recipe_to": str(tmp_path / "h.json"),
                         "test_output": str(tmp_path / "t.stl"), "values": {"Seat Path": str(env)}})
    blk = res["block"]
    assert blk["saved"] == str(tmp_path / "stone_seat.ntop") and (tmp_path / "stone_seat.ntop").exists()
    assert blk["identifiers"]["Seat Offset"].startswith("offset_implicit")
    ident = res["identifiers"]["block:stone_seat"]
    assert ident.startswith("user_func_") and ident.endswith("<text,real>")
    assert res["identifiers"]["Stone Seat"] == ident and nb.inputs == mod.INPUT_ORDER and nb.output == "Volume"
    assert nb.saved[-1] == str(tmp_path / "h.ntop") and res["warnings"] == [] and nb.lint() == []
    from ntopjewel import catalog
    assert list(catalog.load("stone_seat_harness").inputs) == mod.INPUT_ORDER


def test_a_concave_outline_is_refused_not_mis_meshed(monkeypatch):
    import numpy as np
    t = np.linspace(0, 2 * math.pi, 64, endpoint=False)
    r = 3 + 0.8 * np.cos(3 * t)                                   # a three-lobed, concave outline
    monkeypatch.setattr(gems.StoneSpec, "outline", lambda self, n=0: np.column_stack([r * np.cos(t), r * np.sin(t)]))
    with pytest.raises(ValueError, match="not convex"):
        gems.StoneSpec("round", 6.5).mesh()
