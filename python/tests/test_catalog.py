import pytest

from ntopjewel import catalog, ntopcl


def test_ring_band_catalog_loads_and_builds():
    cat = catalog.load("ring_band")
    assert cat.output["name"] == "Volume"
    inputs = cat.build_inputs({"Outer Radius": 9.5, "Bore Radius": 8.25, "Output Path": "C:\\o\\b.stl"})
    by = {e["name"]: e for e in inputs}
    assert by["Width"]["value"] == 4.0 and by["Width"]["units"] == "mm"          # default applied
    assert by["Mesh Tolerance"]["value"] == 0.01
    assert by["Output Path"] == {"name": "Output Path", "type": "file_path", "value": "C:\\o\\b.stl"}
    assert "catalog" in cat.describe() or "ring_band" in cat.describe()


def test_catalog_validation():
    cat = catalog.load("ring_band")
    with pytest.raises(ValueError, match="missing required"):
        cat.build_inputs({"Outer Radius": 9.5})
    with pytest.raises(ValueError, match="unknown inputs"):
        cat.build_inputs({"Outer Radius": 9.5, "Bore Radius": 8, "Output Path": "x", "Colour": 1})
    with pytest.raises(ValueError, match="below min"):
        cat.build_inputs({"Outer Radius": 9.5, "Bore Radius": 1.0, "Output Path": "x"})


def test_template_diff(fake_ntopcl, band_notebook, tmp_path):
    cat = catalog.load("ring_band")
    i, _ = ntopcl.templates(band_notebook, tmp_path / "tpl")
    assert catalog.compare_with_template(cat, i) == []
