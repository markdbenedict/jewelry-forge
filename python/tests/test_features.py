import importlib.util
import json
import math
from pathlib import Path

import pytest

from ntopjewel import band, catalog, engrave, features
from ntopjewel.notebook_api import ConsoleError
from .fake_notebook import FakeNotebook

REPO = Path(__file__).resolve().parents[2]


def load_recipe(name: str):
    path = REPO / "ntop" / "recipes" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------ engraving meshes
def test_engraving_mesh_is_watertight_and_placed_radially():
    m = engrave.text_mesh("M+K 2026", height_mm=1.6, depth_mm=0.3, radius_mm=9.5534, side="outside")
    assert m.is_watertight and m.is_winding_consistent
    assert m.bounds[0, 0] == pytest.approx(9.5534 - 0.3, abs=1e-6)        # cut starts `depth` under the surface
    assert m.bounds[1, 0] > 9.5534 + 0.5                                 # and reaches past it (open pocket)
    assert m.extents[2] == pytest.approx(1.6, abs=0.01)                  # text height along the ring axis
    assert abs(m.bounds[0, 1] + m.bounds[1, 1]) < 0.05                   # centred along the circumference
    inside = engrave.text_mesh("M+K 2026", height_mm=1.6, depth_mm=0.3, radius_mm=8.2534, side="inside")
    assert inside.is_watertight and inside.bounds[1, 0] == pytest.approx(8.2534 + 0.3, abs=1e-6)
    # mirrored reading direction on the inside: the first glyph sits at +Y there, -Y outside... i.e. opposite signs
    out_first = m.vertices[m.vertices[:, 1].argmin(), 1]
    in_first = inside.vertices[inside.vertices[:, 1].argmax(), 1]
    assert out_first < 0 < in_first
    assert engrave.wrap_length_mm(9.5534) == pytest.approx(2 * math.pi * 9.5534)


def test_engraving_file_and_dummy(tmp_path):
    info = engrave.write_engraving(tmp_path / "e.stl", "ABC", 1.5, 0.3, 9.5, "outside")
    assert (tmp_path / "e.stl").exists() and info["watertight"] and info["stroke_mm"] > 0.3 and info["cut_volume_mm3"] > 0
    none = engrave.write_engraving(tmp_path / "n.stl", None, 1.5, 0.3, 9.5, "outside")
    assert none["cut_volume_mm3"] == 0 and none["text"] is None
    import trimesh
    speck = trimesh.load(tmp_path / "n.stl")
    assert speck.bounds[0, 0] > 9.5 + 5                                  # far outside the ring: subtracting it does nothing


# ------------------------------------------------------------------ the spec's numbers
def test_ring_spec_numbers_and_switches():
    b = band.BandSpec(size=6, profile="court")
    plain = features.RingSpec(b)
    g = plain.bead_geometry()
    assert g["count"] == 1 and g["radius"] < 0.1 and b.bore_radius_mm < g["ring_radius"] < b.outer_radius_mm and g["z"] == 0
    assert plain.groove_geometry()["ring_radius"] > b.outer_radius_mm + 9
    assert plain.stem == "ring_court_plain_US6" and plain.validate() == []
    assert plain.design_volume_mm3() == pytest.approx(b.design_volume_mm3(), rel=1e-6)

    s = features.RingSpec(b, milgrain=True, groove_depth_mm=0.25, text="M+K 2026")
    g = s.bead_geometry()
    assert g["radius"] == 0.3 and g["count"] == 87 and g["spacing"] == pytest.approx(360 / 87)
    assert g["ring_radius"] == pytest.approx(b.outer_radius_at(2.0) - 0.15 * 0.3) and g["z"] == pytest.approx(2.0 - 0.045)
    gr = s.groove_geometry()
    assert gr["tube"] == 0.3 and gr["ring_radius"] == pytest.approx(b.outer_radius_mm + 0.3 - 0.25)
    e = s.engrave_geometry()
    assert e["side"] == "inside" and e["height"] == 2.0 and b.bore_radius_mm < e["radius"] < b.bore_radius_mm + 0.1
    exp = s.gate_expectations()
    assert exp["expect_width"] == pytest.approx(2 * (g["z"] + g["radius"])) and exp["expect_outer"] == pytest.approx(2 * b.outer_radius_mm)
    assert exp["expect_inner"] == pytest.approx(b.inner_diameter_mm)
    assert s.validate() == [] and s.stem == "ring_court_milgrain_groove_engraved_US6"
    v = s.design_volume_mm3()
    assert b.design_volume_mm3() - 10 < v < b.design_volume_mm3() + 15     # beads add ~11, groove and text remove ~9
    ins = s.notebook_inputs("X.stl", "E.stl")
    assert list(catalog.load("ring_features").inputs) == list(ins) and ins["Bead Count"] == 87
    assert ins["Bead Z Minus"] == -ins["Bead Z"] and ins["Engraving Wrap Length"] == pytest.approx(2 * math.pi * b.bore_radius_mm, abs=1e-3)


def test_ring_spec_rejects_what_will_not_cast():
    b = band.BandSpec(size=6, profile="court")
    assert any("bead radius" in p for p in features.RingSpec(b, milgrain=True, bead_radius_mm=0.2).validate())
    assert any("wall" in p for p in features.RingSpec(b, groove_depth_mm=0.9).validate())
    assert any("edge round" in p for p in features.RingSpec(b, groove_depth_mm=0.2, groove_z_mm=1.7).validate())
    assert any("depth" in p for p in features.RingSpec(b, text="A", engrave_depth_mm=0.1).validate())
    assert any("stroke" in p for p in features.RingSpec(b, text="illi", engrave_height_mm=0.8).validate())
    long = "A" * 60
    assert any("circumference" in p for p in features.RingSpec(b, text=long).validate())
    thin = band.BandSpec(size=6, profile="half-round", thickness_mm=1.1)
    assert any("engraving leaves" in p or "edge would be" in p for p in features.RingSpec(thin, text="AB", engrave_depth_mm=0.4).validate())


def test_flat_profile_surfaces_do_not_use_the_swallowing_tori():
    b = band.BandSpec(size=6, profile="flat")
    assert b.outer_radius_at(2.0) == pytest.approx(b.outer_radius_mm) and b.bore_radius_at(2.0) == pytest.approx(b.bore_radius_mm)
    s = features.RingSpec(b, milgrain=True)
    assert s.bead_geometry()["ring_radius"] < b.outer_radius_mm


# ------------------------------------------------------------------ the build script on the fake notebook
def test_ring_features_builds_on_fake_notebook(tmp_path):
    mod = load_recipe("ring_features")
    nb = FakeNotebook()
    res = mod.build(nb, {"save_to": str(tmp_path / "rf.ntop"), "recipe_to": str(tmp_path / "rf.json"),
                         "test_output": str(tmp_path / "t.stl"), "values": {"Engraving Path": str(tmp_path / "e.stl")}})
    assert nb.inputs == mod.INPUT_ORDER and len(nb.inputs) == 23 and nb.output == "Volume"
    assert nb.lint() == [] and res["warnings"] == [] and res["volume"] == pytest.approx(287.4)
    b = nb.blocks
    ids = res["identifiers"]
    assert ids["Milgrain"] == "polar_array_implicit<implicit,real,integer,axis>"
    assert ids["Engraving Mesh"] == "import_mesh<file_path,unit_length_enum>[1.1.0]"
    assert ids["Engraving Wrapped"] == "remap_cylindrical_implicit<implicit,real>"
    assert ids["Bead Count"] == "core.var<integer>" and nb.variables["Bead Count"]["value"] == 87
    assert nb.variables["Bead Spacing"]["units"] == "deg"
    arr = res["blocks"]["Milgrain"]
    assert b[arr]["wired"]["Count"][0] == "Bead Count" and b[arr]["wired"]["Angular Spacing"][0] == "Bead Spacing"
    assert b[arr]["wired"]["Axis"][0] == res["blocks"]["Z Axis"] and b[arr]["wired"]["Body"][0] == res["blocks"]["Bead Pair"]
    assert b[res["blocks"]["Bead Pair"]]["lists"]["Bodies"] == [res["blocks"]["Bead+"], res["blocks"]["Bead-"]]
    assert b[res["blocks"]["Bead+"]]["wired"]["Center Point"][0] == res["blocks"]["Bead+ P"]
    assert b[res["blocks"]["Bead+ P"]]["wired"]["X"][0] == "Bead Ring Radius" and b[res["blocks"]["Bead- P"]]["wired"]["Z"][0] == "Bead Z Minus"
    assert b[res["blocks"]["Beaded"]]["lists"]["Bodies"] == ["Band Body", arr]
    assert b[res["blocks"]["Grooved"]]["wired"]["Primary Body"][0] == res["blocks"]["Beaded"]
    assert b[res["blocks"]["Grooved"]]["lists"]["Subtraction Bodies"] == [res["blocks"]["Groove Torus"]]
    assert b[res["blocks"]["Groove Torus"]]["wired"]["Center"][0] == res["blocks"]["Groove P"]
    assert b[res["blocks"]["Engraving Mesh"]]["wired"]["Path"][0] == "Engraving Path"
    assert b[res["blocks"]["Engraving Wrapped"]]["wired"]["Y Mapping Length"][0] == "Engraving Wrap Length"
    assert b[res["blocks"]["Engraved"]]["lists"]["Subtraction Bodies"] == [res["blocks"]["Engraving Wrapped"]]
    assert nb.variables["Ring Body"]["wraps"] == res["blocks"]["Engraved"]
    assert b[res["blocks"]["Volume Integral"]]["wired"]["Body"][0] == "Ring Body" == b[res["blocks"]["Mesh"]]["wired"]["Body"][0]


def test_ring_features_prepare_writes_the_test_engraving(tmp_path):
    mod = load_recipe("ring_features")
    params = mod.prepare({"values": {"Engraving Path": str(tmp_path / "e.stl")}}, tmp_path)
    assert Path(params["values"]["Engraving Path"]).exists()
    assert params["values"]["Engraving Wrap Length"] == pytest.approx(2 * math.pi * 8.2534, abs=1e-3)
    params = mod.prepare({"text": "HI", "values": {"Engraving Path": str(tmp_path / "e2.stl")}}, tmp_path)
    import trimesh
    m = trimesh.load(tmp_path / "e2.stl")
    assert m.bounds[1, 0] < 9.0                                            # real text sits on the bore, not far away


# ------------------------------------------------------------------ end to end with the fake ntopcl
def test_ring_end_to_end_with_fake_ntopcl(fake_ntopcl, features_notebook, tmp_path, monkeypatch):
    monkeypatch.setenv("JEWELRY_DELIVER", str(tmp_path / "deliver"))
    spec = features.RingSpec(band.BandSpec(size=6, profile="flat"), milgrain=True, groove_depth_mm=0.2, text="M+K")
    res = features.build(spec, tmp_path / "out" / "ring", notebook=features_notebook, deliver=True)
    assert res.run.ok and res.stl.exists() and (tmp_path / "out" / "ring" / f"{spec.stem}.engraving.stl").exists()
    rep = json.loads((tmp_path / "out" / "ring" / f"{spec.stem}.report.json").read_text(encoding="utf-8"))
    assert rep["inputs"]["Bead Count"] == spec.bead_geometry()["count"] and rep["engraving"]["text"] == "M+K"
    # the fake ntopcl widens the ring by the beads, as nTop will: the gate expects exactly that width
    assert any(c["name"] == "width" and c["ok"] for c in rep["gate"]["checks"])
    assert any("engraving 'M+K'" in n for n in res.notes) and any("design" in n for n in res.notes)
    if res.ok:
        assert res.delivered and res.delivered.exists()


def test_cli_ring_dry_run(capsys):
    from ntopjewel import cli
    rc = cli.main(["ring", "--size", "6", "--profile", "court", "--milgrain", "--groove", "0.25", "--engrave", "M+K 2026", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0 and "87 beads/row" in out and "Bead Count: 87" in out and "design volume" in out
    rc = cli.main(["ring", "--size", "6", "--groove", "0.9", "--dry-run"])
    assert rc == 1 and "problems" in capsys.readouterr().out
