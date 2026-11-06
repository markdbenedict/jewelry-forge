"""nTop's own textures on a band, masked to the outer face, gated by an envelope (2026-11-06): the voronoi deboss, the
frost / pitted / cellular noises and the ribbed wave."""
from __future__ import annotations

import json

import numpy as np
import pytest

from ntopjewel import band, catalog, fieldtex, runs


def probe_band(**kw):
    return band.BandSpec(**{"size": 6, "profile": "court", "width_mm": 4.0, "thickness_mm": 1.6, "mesh_tolerance_mm": 0.05, **kw})


def voronoi(**kw):
    b = kw.pop("band", None) or probe_band()
    return fieldtex.VoronoiSpec(b, **kw)


def spec_of(kind, **kw):
    b = kw.pop("band", None) or probe_band()
    if kind == "voronoi":
        kw.setdefault("cells", 120)
    if kind == "ribbed":
        kw.setdefault("rib_depth_mm", 0.1)
    return fieldtex.make_spec(kind, b, **kw)


KINDS = ["voronoi", "frost", "pitted", "cellular", "ribbed"]


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


def test_the_other_kinds_match_their_catalogs_and_refuse_what_they_should():
    for kind in KINDS[1:]:
        s = spec_of(kind)
        assert s.validate() == [], (kind, s.validate())
        v = s.notebook_inputs("O")
        assert list(v) == list(catalog.load(f"ring_{kind}").inputs), kind
        assert kind in s.describe() and s.stem.startswith(f"ring_texture_{kind}_court_US6_w4_t1.6_")
        assert s.depth_mm == pytest.approx(0.1)
    f = spec_of("frost")
    assert f.adds_metal and f.rise_mm == pytest.approx(0.1) and f.notebook_inputs("O")["Frequency"] == 500
    assert spec_of("pitted").rise_mm == 0 and spec_of("cellular").notebook_inputs("O")["Factor"] == pytest.approx(0.1 / (3.4 * 2), rel=1e-3)
    r = spec_of("ribbed")
    assert r.notebook_inputs("O")["Erosion"] == -0.1 and r.notebook_inputs("O")["Wave Height"] == pytest.approx(0.1 / 3, rel=1e-3)
    assert "at least 0.1" in spec_of("frost", amplitude_mm=0.05).validate()[0]
    assert "grain" in spec_of("pitted", grain_mm=0.1).validate()[0]
    assert "voxels" in spec_of("cellular", band=probe_band(mesh_tolerance_mm=0.1), grain_mm=0.3).validate()[0]
    assert "spacing" in spec_of("ribbed", rib_mm=0.1).validate()[0]
    assert spec_of("frost", seed=2).spec_id != f.spec_id
    with pytest.raises(ValueError):
        fieldtex.make_spec("satin", probe_band())


@pytest.mark.parametrize("kind", KINDS)
def test_recipe_builds_on_the_fake_api(tmp_path, kind):
    from .fake_notebook import FakeNotebook
    from .test_notebook_api import load_recipe
    mod = load_recipe(f"ring_{kind}")
    params = mod.prepare({}, tmp_path)
    params.update({"save_to": str(tmp_path / "v.ntop"), "recipe_to": str(tmp_path / "v.json"), "test_output": str(tmp_path / "v.stl")})
    nb = FakeNotebook()
    res = mod.build(nb, params)
    assert nb.inputs == mod.INPUT_ORDER == list(catalog.load(f"ring_{kind}").inputs)
    assert nb.lint() == [] and res["warnings"] == []
    b = res["blocks"]
    assert nb.blocks[b["Dents"]]["wired"]["Primary Body"][0] == "Band Body"
    if kind == "voronoi":
        assert res["identifiers"]["Grooved"].startswith("ntoptoolkits.architected_materials.voronoi_deboss")
        g = nb.blocks[b["Grooved"]]
        assert g["wired"]["Thickness"][0] == "Groove" and g["wired"]["Spatial weighting"][0] == "Weighting"
        assert g["wired"]["Voronoi cell count"][0] == "Cells" and g["wired"]["Body"][0] == "Band Body"
        assert nb.blocks[b["Textured"]]["wired"]["Primary Body"][0] == "Band Body"
        assert set(nb.blocks[b["Dents In Zone"]]["lists"]["Bodies"]) == {b["Dents"], b["Zone"]}
    elif kind == "frost":
        g = nb.blocks[b["Textured All Over"]]
        assert res["identifiers"]["Textured All Over"].endswith("surface_roughness<implicit,integer,real_field,integer>")
        assert g["wired"]["Roughess amplitude"][0] == "Amplitude" and g["wired"]["Roughness frequency"][0] == "Frequency"
        assert nb.blocks[b["Bumps"]]["wired"]["Primary Body"][0] == "Textured All Over Body"        # two-sided mask
        assert set(nb.blocks[b["Bumps In Zone"]]["lists"]["Bodies"]) == {b["Bumps"], "Zone Body"}
        assert set(nb.blocks[b["Textured"]]["lists"]["Bodies"]) == {b["Cut"], b["Bumps In Zone"]}
    elif kind == "pitted":
        g = nb.blocks[b["Textured All Over"]]
        assert g["wired"]["Depth factor"][0] == "Amplitude" and g["wired"]["Random seed"][0] == "Seed"
    elif kind == "cellular":
        g = nb.blocks[b["Textured All Over"]]
        assert g["wired"]["Frequency"][0] == b["Noise Frequency"] and g["wired"]["Depth factor"][0] == "Factor"
        f = nb.blocks[b["Noise Frequency"]]
        assert f["wired"]["A"][0] == "Thousand" and f["wired"]["B"][0] == "Grain"
    elif kind == "ribbed":
        g = nb.blocks[b["Textured All Over"]]
        assert g["wired"]["Body"][0] == b["Eroded"] and g["wired"]["Wave spacing"][0] == "Rib Spacing" and g["wired"]["Wave height"][0] == "Wave Height"
        assert nb.blocks[b["Eroded"]]["wired"]["Distance"][0] == "Erosion"


@pytest.mark.parametrize("kind", KINDS)
def test_end_to_end_and_the_faults_are_caught(fake_ntopcl, tmp_path, out_dir, monkeypatch, kind):
    nb = tmp_path / f"ring_{kind}.ntop"
    nb.write_bytes(b"fake")
    s = spec_of(kind)
    res = fieldtex.build(s, out_dir, notebook=nb)
    assert res.status == "passed", res.text()
    names = {c.name for c in res.gate.checks}
    assert {"texture envelope", "untouched outside the zone", "texture coverage", "design volume"} <= names
    t = res.gate.texture
    assert 0.08 < t["zone_deepest_mm"] < 0.115 and s.coverage[0] < t["zone_touched"] <= s.coverage[1]
    if kind == "voronoi":
        assert t["cells_on_face"] >= 10
        assert s.plain_volume_mm3() - s.max_removal_mm3() < res.ntop_volume_mm3 < s.plain_volume_mm3()
    if kind == "frost":
        assert t["zone_highest_mm"] > 0.08                                   # it adds as much as it takes
    rep = json.loads(next(res.run_dir.glob("*.report.json")).read_text())
    assert rep["status"] == "passed" and rep["texture"]["zone_touched"] == t["zone_touched"]
    for fault, check in (("notexture", "texture coverage"), ("unmasked", "untouched outside the zone"), ("deep", "texture envelope")):
        monkeypatch.setenv("FAKE_NTOPCL_SHAPE", fault)
        bad = fieldtex.build(s, out_dir, notebook=nb)
        assert bad.status == "failed" and check in {c.name for c in bad.gate.failures()}, (kind, fault, bad.text())
