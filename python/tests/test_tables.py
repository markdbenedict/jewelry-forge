import math

import pytest

from ntopjewel import tables


def test_us_sizes_match_known_values():
    # US 5 = 15.69 mm, US 6 = 16.51 mm, US 7 = 17.32 mm (standard tables, ±0.02 mm)
    assert tables.us_size_to_inner_diameter_mm(5) == pytest.approx(15.69, abs=0.02)
    assert tables.us_size_to_inner_diameter_mm(6) == pytest.approx(16.51, abs=0.02)
    assert tables.us_size_to_inner_diameter_mm(7) == pytest.approx(17.32, abs=0.02)
    assert tables.inner_diameter_mm_to_us_size(16.51) == pytest.approx(6.0, abs=0.03)


def test_other_systems_round_trip():
    d = tables.inner_diameter_mm(52, "ISO")
    assert d == pytest.approx(52 / math.pi)
    assert tables.inner_diameter_mm_to_iso_circumference(d) == pytest.approx(52)
    assert tables.inner_diameter_mm("L", "UK") == pytest.approx(16.51, abs=0.1)   # UK L ≈ US 6
    assert tables.inner_diameter_mm("L 1/2", "UK") > tables.inner_diameter_mm("L", "UK")
    assert tables.inner_diameter_mm(17.0, "MM") == 17.0
    with pytest.raises(ValueError):
        tables.inner_diameter_mm("7", "UK")
    with pytest.raises(ValueError):
        tables.inner_diameter_mm(7, "martian")


def test_labels():
    assert tables.size_label(6, "US") == "US6"
    assert tables.size_label(6.5, "US") == "US6.5"
    assert tables.size_label("L 1/2", "UK") == "UKLhalf"
    assert tables.size_label(52, "ISO") == "ISO52"


def test_weights_and_shrink():
    v = 734.0  # mm³, the size-5 monstera band
    w = tables.weights_g(v)
    assert w["sterling"] == pytest.approx(7.6, abs=0.1)
    assert w["18k_yellow"] > w["14k_yellow"] > w["sterling"]
    assert tables.shrink_scale("sterling") == pytest.approx(1.017)
    assert tables.shrink_scale("resin") == 1.0


def test_torus_for_sagitta():
    r, off = tables.torus_for_sagitta(chord_mm=4.0, sagitta_mm=0.2)
    # circle through (±2, 0) and (0, 0.2): r = (4 + 0.04)/0.4 = 10.1
    assert r == pytest.approx(10.1)
    assert off == pytest.approx(9.9)
    with pytest.raises(ValueError):
        tables.torus_for_sagitta(4.0, 0.0)
