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
