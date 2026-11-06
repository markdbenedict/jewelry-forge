"""nTop's own textures on a band, masked to the outer face, gated by an envelope (2026-11-06): the voronoi deboss."""
from __future__ import annotations

import json

import numpy as np
import pytest

from ntopjewel import band, catalog, fieldtex, runs


def voronoi(**kw):
    b = kw.pop("band", None) or band.BandSpec(size=6, profile="court", width_mm=4.0, thickness_mm=1.6, mesh_tolerance_mm=0.05)
    return fieldtex.VoronoiSpec(b, **kw)


def test_spec_zone_inputs_identity_and_refusals():
    s = voronoi()
    assert s.validate() == []
    assert s.depth_mm == pytest.approx(0.1) and s.rim == pytest.approx(0.35) and s.zone_half_width == pytest.approx(1.65)
    assert s.band.bore_radius_mm < s.zone_inner_radius < s.band.outer_radius_at(s.zone_half_width) - s.depth_mm
    v = s.notebook_inputs("O")
    assert list(v) == list(catalog.load("ring_voronoi").inputs)
    assert v["Zone Z Bottom"] == -v["Zone Z Top"] and v["Groove"] == 0.2 and v["Cells"] == 200
    assert 0 < s.max_removal_mm3() < 0.1 * s.plain_volume_mm3()
    assert s.stem.startswith("ring_texture_voronoi_court_US6_w4_t1.6_c200g0.2_")
    assert runs.spec_id(voronoi(groove_mm=0.3).design()) != s.spec_id and "voronoi" in json.dumps(s.design())
    assert "at least 0.1" in voronoi(groove_mm=0.15).validate()[0]                 # under the texture_depth floor
    assert "cells" in voronoi(cells=5).validate()[0]
    assert "rims" in voronoi(rim_mm=1.6).validate()[0]
    thin = voronoi(band=band.BandSpec(size=6, profile="court", width_mm=4.0, thickness_mm=1.2, edge_round_mm=0.15, mesh_tolerance_mm=0.05),
                   groove_mm=0.5)
    assert "wall" in thin.validate()[0]
    assert "voxels" in voronoi(band=band.BandSpec(size=6, profile="court", thickness_mm=1.6, mesh_tolerance_mm=0.2)).validate()[0]
    assert "voronoi deboss" in s.describe()


def test_recipe_builds_on_the_fake_api(tmp_path):
    from .fake_notebook import FakeNotebook
    from .test_notebook_api import load_recipe
    mod = load_recipe("ring_voronoi")
    params = mod.prepare({}, tmp_path)
    params.update({"save_to": str(tmp_path / "v.ntop"), "recipe_to": str(tmp_path / "v.json"), "test_output": str(tmp_path / "v.stl")})
    nb = FakeNotebook()
    res = mod.build(nb, params)
    assert nb.inputs == mod.INPUT_ORDER == list(catalog.load("ring_voronoi").inputs)
    assert nb.lint() == [] and res["warnings"] == []
    assert res["identifiers"]["Grooved"].startswith("ntoptoolkits.architected_materials.voronoi_deboss")
    b = res["blocks"]
    g = nb.blocks[b["Grooved"]]
    assert g["wired"]["Thickness"][0] == "Groove" and g["wired"]["Spatial weighting"][0] == "Weighting"
    assert g["wired"]["Voronoi cell count"][0] == "Cells" and g["wired"]["Body"][0] == "Band Body"
    assert nb.blocks[b["Dents"]]["wired"]["Primary Body"][0] == "Band Body"
    assert nb.blocks[b["Textured"]]["wired"]["Primary Body"][0] == "Band Body"
    assert set(nb.blocks[b["Dents In Zone"]]["lists"]["Bodies"]) == {b["Dents"], b["Zone"]}


def test_voronoi_end_to_end_and_the_faults_are_caught(fake_ntopcl, tmp_path, out_dir, monkeypatch):
    nb = tmp_path / "ring_voronoi.ntop"
    nb.write_bytes(b"fake")
    s = voronoi(cells=120)
    res = fieldtex.build(s, out_dir, notebook=nb)
    assert res.status == "passed", res.text()
    names = {c.name for c in res.gate.checks}
    assert {"texture envelope", "untouched outside the zone", "texture coverage", "design volume"} <= names
    t = res.gate.texture
    assert 0.08 < t["zone_deepest_mm"] < 0.115 and t["cells_on_face"] >= 10 and 0.03 < t["zone_touched"] < 0.5
    assert s.plain_volume_mm3() - s.max_removal_mm3() < res.ntop_volume_mm3 < s.plain_volume_mm3()
    rep = json.loads(next(res.run_dir.glob("*.report.json")).read_text())
    assert rep["texture"]["cells_on_face"] == t["cells_on_face"] and rep["status"] == "passed"
    for fault, check in (("notexture", "texture coverage"), ("unmasked", "untouched outside the zone"), ("deep", "texture envelope")):
        monkeypatch.setenv("FAKE_NTOPCL_SHAPE", fault)
        bad = fieldtex.build(s, out_dir, notebook=nb)
        assert bad.status == "failed" and check in {c.name for c in bad.gate.failures()}, (fault, bad.text())
