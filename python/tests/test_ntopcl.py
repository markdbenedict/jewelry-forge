import json
from pathlib import Path

import pytest

from ntopjewel import ntopcl
from .conftest import REAL_LOG_NO_INPUTS, REAL_LOG_SUCCESS


def test_parse_real_success_log():
    p = ntopcl.parse_log(REAL_LOG_SUCCESS)
    assert p.login and p.built and not p.errors
    assert [t.block for t in p.timings][:2] == ["Plane_2", "Box_0"]
    assert p.slowest(1)[0].block == "Implicit Body_5" and p.slowest(1)[0].ms == 22
    assert p.total_block_ms == 22


def test_parse_real_no_inputs_log():
    p = ntopcl.parse_log(REAL_LOG_NO_INPUTS)
    assert p.errors == ["JSON file has no inputs"]
    assert not p.built


def test_make_input_rules():
    assert ntopcl.make_input("W", "scalar", 4, "mm") == {"name": "W", "type": "scalar", "value": 4.0, "units": "mm"}
    assert ntopcl.make_input("T", "scalar", [0.1, 0.2], "mm")["values"] == [0.1, 0.2]
    assert ntopcl.make_input("P", "file_path", Path("C:/x/y.stl"))["value"] == str(Path("C:/x/y.stl"))  # native separators
    assert ntopcl.make_input("N", "integer", 6.0)["value"] == 6
    assert ntopcl.make_input("B", "bool", 1)["value"] is True
    assert ntopcl.make_input("C", "point", (1, 2, 3), "mm")["value"] == [1.0, 2.0, 3.0]
    with pytest.raises(ValueError):
        ntopcl.make_input("W", "scalar", 4)                 # scalar needs units
    with pytest.raises(ValueError):
        ntopcl.make_input("T", "text", "x", "mm")           # text takes no units
    with pytest.raises(ValueError):
        ntopcl.make_input("N", "integer", 6.5)
    with pytest.raises(ValueError):
        ntopcl.make_input("X", "matrix", 1)
    with pytest.raises(ValueError):
        ntopcl.input_json([ntopcl.make_input("A", "bool", True), ntopcl.make_input("A", "bool", False)])


def test_scalar_value_shapes():
    assert ntopcl.scalar_value({"value": 12.5}) == 12.5
    assert ntopcl.scalar_value({"value": {"value": 3, "units": "mm"}}) == 3.0
    assert ntopcl.scalar_value({"value": {"values": [7.0]}}) == 7.0
    assert ntopcl.scalar_value({"value": [1.5]}) == 1.5
    assert ntopcl.scalar_value({"value": {"base64": "AAAA"}}) is None


def test_run_without_inputs_omits_dash_j(fake_ntopcl, tmp_path):
    nb = tmp_path / "test.ntop"
    nb.write_bytes(b"x")
    res = ntopcl.run(nb, None, tmp_path / "out", tag="t")
    assert res.ok and res.input_json is None and "-j" not in res.command
    assert "Spherecube Shell" in res.outputs
    assert res.outputs["Spherecube Shell"]["type"] == "implicit"


def test_run_rejects_empty_inputs_like_ntopcl(fake_ntopcl, tmp_path):
    """If someone forces an empty -j the fake replies like the real ntopcl; the runner must fail."""
    nb = tmp_path / "test.ntop"
    nb.write_bytes(b"x")
    out = tmp_path / "out"
    out.mkdir()
    (out / "empty.json").write_text(json.dumps({"inputs": []}))
    with pytest.raises(ntopcl.NtopclError) as ei:
        ntopcl.run(nb, None, out, tag="e", extra_args=["-j", str(out / "empty.json")])
    assert "JSON file has no inputs" in str(ei.value)
    assert ei.value.result is not None and ei.value.result.returncode == 0   # exit 0 but failed


def test_failed_block_is_failure_despite_exit_zero(fake_ntopcl, tmp_path):
    nb = tmp_path / "will_fail.ntop"
    nb.write_bytes(b"x")
    with pytest.raises(ntopcl.NtopclError) as ei:
        ntopcl.run(nb, [ntopcl.make_input("W", "scalar", 1, "mm")], tmp_path / "out", tag="f")
    assert not ei.value.result.ok and ei.value.result.log.errors


def test_templates(fake_ntopcl, band_notebook, tmp_path):
    i, o = ntopcl.templates(band_notebook, tmp_path / "tpl")
    doc = json.loads(i.read_text())
    assert {e["name"] for e in doc["inputs"]} == {"Outer Radius", "Bore Radius", "Width", "Mesh Tolerance", "Output Path"}
    assert json.loads(o.read_text())[0]["name"] == "Volume"


def test_run_uses_template_type_names(fake_ntopcl, band_notebook, tmp_path, monkeypatch):
    """Types are spelled the way nTop's own -t template spells them (real, text)."""
    import json as _json
    monkeypatch.setenv("JEWELRY_OUT", str(tmp_path / "out"))
    inputs = [ntopcl.make_input("Outer Radius", "scalar", 9.553, "mm"),
              ntopcl.make_input("Bore Radius", "scalar", 8.253, "mm"),
              ntopcl.make_input("Width", "scalar", 4.0, "mm"),
              ntopcl.make_input("Mesh Tolerance", "scalar", 0.01, "mm"),
              ntopcl.make_input("Output Path", "file_path", str(tmp_path / "b.stl"))]
    res = ntopcl.run(band_notebook, inputs, tmp_path / "run", tag="b")
    sent = {e["name"]: e["type"] for e in _json.loads(res.input_json.read_text())["inputs"]}
    assert sent == {"Outer Radius": "real", "Bore Radius": "real", "Width": "real",
                    "Mesh Tolerance": "real", "Output Path": "text"}
    assert (tmp_path / "out" / "templates" / "ring_band" / "input_template.json").exists()


def test_run_with_relative_out_dir(fake_ntopcl, band_notebook, tmp_path, monkeypatch):
    """ntopcl is started inside out_dir, so relative out paths must be made absolute first."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("JEWELRY_OUT", str(tmp_path / "out"))
    inputs = [ntopcl.make_input("Outer Radius", "scalar", 9.553, "mm"),
              ntopcl.make_input("Bore Radius", "scalar", 8.253, "mm"),
              ntopcl.make_input("Width", "scalar", 4.0, "mm"),
              ntopcl.make_input("Mesh Tolerance", "scalar", 0.01, "mm"),
              ntopcl.make_input("Output Path", "text", str(tmp_path / "rel" / "b.stl"))]
    res = ntopcl.run(band_notebook, inputs, Path("rel"), tag="r")
    assert res.ok and res.input_json.is_absolute() and res.output_json.exists()
