"""The texture probe (2026-11-06): nTop's own texture blocks on a plain band, measured against the designed section."""
from __future__ import annotations

import numpy as np
import pytest

from ntopjewel import nb_texture as nt
from ntopjewel import texture, texture_probe as tp


def test_the_rules_give_every_known_input_its_variable():
    assert nt.match("Random seed", "integer") == "Seed"
    assert nt.match("Depth factor", "real_field") == "Depth Factor"
    assert nt.match("Wave height", "real_field") == "Depth"
    assert nt.match("Wave spacing", "real_field") == "Wave Spacing"
    assert nt.match("Frequency", "real") == "Frequency"
    assert nt.match("Cell size", "real") == "Cell Size"
    assert nt.match("Octaves", "integer") == "Count"
    assert nt.match("Seed", "real") is None                         # a rule keeps to its types
    assert nt.match("Mystery", "real") is None


def test_recipe_builds_every_texture_on_the_fake_api(tmp_path):
    from ntopjewel import catalog
    from .fake_notebook import FakeNotebook
    from .test_notebook_api import load_recipe
    mod = load_recipe("texture_probe")
    params = mod.prepare({}, tmp_path)
    params.update({"save_to": str(tmp_path / "p.ntop"), "recipe_to": str(tmp_path / "p.json"), "test_output": str(tmp_path / "p.stl")})
    nb = FakeNotebook()
    res = mod.build(nb, params)
    assert nb.inputs == mod.INPUT_ORDER == list(catalog.load("texture_probe").inputs)
    assert nb.lint() == []
    for label in nt.CASES:
        assert res["identifiers"][label].startswith(nt.TK)
        assert any(line.startswith(f"{label}: ") and "<- Band Body" in line for line in res["log"]), label
    log = "\n".join(res["log"])
    assert "Depth factor (real_field) <- Depth Factor" in log and "Direction = [0.0, 0.0, 1.0]" in log
    assert "left at nTop's default" in log                           # the enums: the API cannot set them


def test_the_measurements_read_a_texture_and_leave_a_plain_band_alone(tmp_path):
    b = tp.probe_band()
    h = texture.HammeredSpec(b)
    h.design_mesh().export(tmp_path / "texture_probe_simplex.stl")            # a deboss on the outer face only
    h.band_mesh().export(tmp_path / "texture_probe_cellular.stl")             # nothing done
    res = tp.measure_all(tmp_path)
    s, c = res["cases"]["Simplex"], res["cases"]["Cellular"]
    assert s["faces"]["outer"]["deepest_mm"] == pytest.approx(h.depth_range[1], abs=0.01)
    assert s["faces"]["outer"]["touched"] > 0.5 and s["faces"]["bore"]["touched"] == 0.0
    assert s["volume_change_pct"] == pytest.approx(-100 * (1 - h.design_volume_mm3() / b.design_volume_mm3()), abs=0.1)
    assert 0.1 < s["feature_mm"] < 1.0                                          # 1.6 mm dimples
    assert c["faces"]["outer"]["touched"] == 0.0 and c.get("feature_mm") is None
    assert "missing" in res["cases"]["Triangle Wave"]
    assert "Simplex" in tp.table(res)


def test_probe_end_to_end_on_the_simulated_ntop(fake_ntopcl, tmp_path, monkeypatch):
    from ntopjewel import catalog
    nb = tmp_path / "texture_probe.ntop"
    nb.write_bytes(b"fake")
    res, run_dir = tp.run(tmp_path / "out", notebook=nb)
    assert res["ntopcl"]["ok"], res["ntopcl"]
    assert set(res["cases"]) == set(nt.CASES) and not any("missing" in c for c in res["cases"].values())
    wave = res["cases"]["Triangle Wave"]["faces"]["outer"]
    assert wave["deepest_mm"] > 0.05 and res["cases"]["Triangle Wave"]["faces"]["bore"]["touched"] == 0.0
    assert (run_dir / "texture_probe.json").exists() and (run_dir / "texture_probe.txt").exists()
    assert list(catalog.load("texture_probe").inputs)[-1] == "Output Triangle Wave"
