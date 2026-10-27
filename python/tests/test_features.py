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
    assert exp["expect_width"] == pytest.approx(2 * (g["z"] + g["radius"]))
    assert exp["expect_outer"] == pytest.approx(2 * b.outer_radius_at(0.3), abs=1e-3)       # the groove takes the widest point
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


def test_preview_build_shows_only_the_finished_ring(tmp_path):
    """`show` hides every geometry block but the finished ring; variables cannot be toggled and
    that is logged, not fatal."""
    mod = load_recipe("ring_features")
    nb = FakeNotebook()
    res = mod.build(nb, {"save_to": str(tmp_path / "rf.ntop"), "recipe_to": str(tmp_path / "rf.json"),
                         "test_output": str(tmp_path / "t.stl"), "values": {"Engraving Path": str(tmp_path / "e.stl")},
                         "show": features.PREVIEW_SHOW})
    disp = res["display"]
    assert disp["Engraved"] is True and nb.get_block_visibility(res["blocks"]["Engraved"]) is True
    hidden = [k for k, v in disp.items() if v is False]
    assert {"Outer", "Bore", "Dome Torus", "Milgrain", "Groove Torus", "Engraving Wrapped", "Mesh"} <= set(hidden)
    assert all(nb.get_block_visibility(res["blocks"][k]) is False for k in hidden)
    assert "variable" in disp["Ring Body"] and "Volume" not in hidden           # variables: refused, logged
    assert not any("display" in ln and "refused" in ln for ln in res["log"])
    assert any(ln.startswith("display: showing") for ln in res["log"])
    assert all(name not in disp for name in mod.INPUT_ORDER)                      # inputs are never touched


def test_preview_builds_this_ring_in_the_console(tmp_path, monkeypatch):
    """`ring --show`: the build script runs in the console with THIS ring's values (not the test
    values), saves a preview notebook, and the mesh the session exported is gated."""
    import sys
    import trimesh
    from ntopjewel.notebook_api import Console
    monkeypatch.setattr(features.config, "out_dir", lambda: tmp_path / "out")
    fake = FakeNotebook()

    def transport(line, timeout):
        keep = {k: v for k, v in sys.modules.items() if k == "ntopjewel" or k.startswith("ntopjewel.")}
        try:
            exec(line, {"notebook": fake})              # the exec(open(driver).read()) line, in-process
        finally:                                        # the driver purges our modules; put them back
            for k in [k for k in sys.modules if k == "ntopjewel" or k.startswith("ntopjewel.")]:
                del sys.modules[k]
            sys.modules.update(keep)
        # the GUI session's Export Mesh: a ring sized from the variables the script set
        v = fake.variables
        rho, zb = v["Bead Radius"]["value"], v["Bead Z"]["value"]
        m = trimesh.creation.annulus(r_min=v["Bore Radius"]["value"],
                                     r_max=max(v["Outer Radius"]["value"], v["Bead Ring Radius"]["value"] + rho),
                                     height=2 * (zb + rho), sections=720)
        m.export(v["Output Path"]["value"])
        return "__NTOPJEWEL_" + "DONE__\n"

    spec = features.RingSpec(band.BandSpec(size=4.5, profile="court"), milgrain=True, groove_depth_mm=0.25, text="Makena")
    res = features.preview(spec, console=Console(transport=transport))
    assert fake.saved == [str(res.notebook)] and res.notebook.name == f"{spec.stem}.ntop"
    assert res.notebook.parent == (tmp_path / "out" / "api" / "preview").resolve()
    want = spec.notebook_inputs(str(res.stl), str(res.notebook.parent / f"{spec.stem}.engraving.stl"))
    assert fake.variables["Bore Radius"]["value"] == pytest.approx(want["Bore Radius"])        # size 4.5, not the test US6
    assert fake.variables["Bead Count"]["value"] == want["Bead Count"]
    assert fake.variables["Engraving Path"]["value"].endswith(f"{spec.stem}.engraving.stl")
    assert Path(fake.variables["Engraving Path"]["value"]).exists()
    assert fake.variables["Engraving Wrap Length"]["value"] == pytest.approx(want["Engraving Wrap Length"])
    assert fake.get_block_visibility(res.build["blocks"]["Engraved"]) and not fake.get_block_visibility(res.build["blocks"]["Outer"])
    assert res.gate is not None and res.stl.exists()
    ok = {c.name: c.ok for c in res.gate.checks}
    assert ok["inner diameter"] and ok["width"] and ok["watertight"]
    assert not ok["engraving"]                                   # the fake export has no pocket
    assert any("Makena" in n for n in res.notes) and "built in nTop" in res.text()
    assert json.loads((res.notebook.parent / f"{spec.stem}.preview.json").read_text())["volume_mm3"] == pytest.approx(287.4)


def test_cli_ring_show_reports_a_console_failure(tmp_path, monkeypatch, capsys):
    from ntopjewel import cli
    from ntopjewel.notebook_api import Console
    monkeypatch.setattr(features.config, "out_dir", lambda: tmp_path / "out")

    def refuse(self, line, timeout):
        raise ConsoleError("ssh: connection refused on localhost:2222")
    monkeypatch.setattr(Console, "_ssh_transport", refuse)
    rc = cli.main(["ring", "--size", "4.5", "--engrave", "Makena", "--show"])
    out = capsys.readouterr().out
    assert rc == 2 and "preview failed" in out and "connection refused" in out


def test_ring_features_prepare_writes_the_test_engraving(tmp_path):
    mod = load_recipe("ring_features")
    params = mod.prepare({"values": {"Engraving Path": str(tmp_path / "e.stl")}}, tmp_path)
    assert Path(params["values"]["Engraving Path"]).exists()
    assert params["values"]["Engraving Wrap Length"] == pytest.approx(2 * math.pi * 8.2534, abs=1e-3)
    params = mod.prepare({"text": "HI", "values": {"Engraving Path": str(tmp_path / "e2.stl")}}, tmp_path)
    import trimesh
    m = trimesh.load(tmp_path / "e2.stl")
    assert m.bounds[1, 0] < 9.0                                            # real text sits on the bore, not far away


# ------------------------------------------------------------------ the gate with features
def test_wall_thickness_zone_keeps_beads_out_of_the_sample():
    import trimesh, numpy as np
    from ntopjewel import gate
    ring = trimesh.creation.annulus(r_min=8.25, r_max=9.55, height=4.0, sections=360)
    beads = []
    for k in range(60):
        a = 2 * math.pi * k / 60
        for zc in (1.95, -1.95):
            s = trimesh.creation.icosphere(subdivisions=2, radius=0.3)
            s.apply_translation((9.5 * math.cos(a), 9.5 * math.sin(a), zc))
            beads.append(s)
    m = trimesh.util.concatenate([ring, *beads])
    whole = gate.wall_thickness(m, 3000, 0.5)
    banded = gate.wall_thickness(m, 3000, 0.5, zone=(2, 1.6), axis=2)
    assert whole["p01"] < 0.5 < banded["p01"]            # grazing bead chords fool the raw check; the zone does not
    assert banded["zone"].startswith("|z| <= 1.6") and banded["excluded"]["outside_zone"] > 0


def test_wall_thickness_ignores_engraving_ribs():
    """Engraved strokes leave 0.3 mm ribs between pockets: a ray off a pocket's side wall runs
    sideways through the rib and reads 0.3 mm. Those are not walls; the gate measures only
    along radial and axial directions."""
    import trimesh, numpy as np
    from shapely.geometry import Point, box
    from ntopjewel import gate
    ring = Point(0, 0).buffer(9.55, quad_segs=180).difference(Point(0, 0).buffer(8.25, quad_segs=180))
    for k in range(8):                                      # eight 0.3 mm notches 0.3 mm apart at the bore, near +X
        a = k * 0.6 / 8.25
        notch = box(8.25 - 0.1, -0.15, 8.25 + 0.3, 0.15)
        from shapely import affinity
        ring = ring.difference(affinity.rotate(notch, math.degrees(a), origin=(0, 0)))
    m = trimesh.creation.extrude_polygon(ring, height=4.0)
    m.apply_translation((0, 0, -2.0))
    raw = gate.wall_thickness(m, 3000, 0.5, seed=3)
    filtered = gate.wall_thickness(m, 3000, 0.5, seed=3, axis=2)
    assert filtered["p01"] >= 0.9 and filtered["excluded"]["tangential"] > 0
    assert raw["min"] < 0.4                                 # the ribs were visible to the raw check


def test_engraving_pocket_detection():
    import numpy as np
    b = band.BandSpec(size=6, profile="court")
    s = features.RingSpec(b, text="Makena", engrave_side="inside")
    s.engraving_info = {"arc_length_mm": 10.9}
    g = s.engrave_geometry()
    rng = np.random.default_rng(1)

    def points(n, depth, theta_lo, theta_hi):
        th = rng.uniform(theta_lo, theta_hi, n)
        z = rng.uniform(-g["height"] / 2, g["height"] / 2, n)
        r = np.array([b.bore_radius_at(zz) for zz in z]) + depth
        return np.column_stack([r * np.cos(th), r * np.sin(th), z])

    class M:
        def __init__(self, v):
            self.vertices = v
    half = 10.9 / 2 / b.bore_radius_mm
    surface = points(2000, 0.0, -math.pi, math.pi)
    pocket = points(400, 0.2, -half, half)
    assert s.engraving_pocket(M(np.vstack([surface, pocket])))["found"]
    assert not s.engraving_pocket(M(surface))["found"]
    stray = points(400, 0.2, 2.0, 2.8)                      # a pocket at the wrong angle counts as stray, not found
    res = s.engraving_pocket(M(np.vstack([surface, stray])))
    assert not res["found"] and res["stray_vertices"] > 300


def test_gate_expectations_with_groove_and_beads():
    b = band.BandSpec(size=6, profile="court")
    exp = features.RingSpec(b, milgrain=True, groove_depth_mm=0.25).gate_expectations()
    assert exp["wall_abs_axis_max"] == pytest.approx(1.955 - 0.3 - 0.05)
    assert exp["expect_outer"] < 2 * b.outer_radius_mm and exp["expect_outer"] > 2 * b.outer_radius_mm - 0.05   # the groove takes the widest point
    assert "wall_abs_axis_max" not in features.RingSpec(b).gate_expectations()


# ------------------------------------------------------------------ end to end with the fake ntopcl
def test_ring_end_to_end_with_fake_ntopcl(fake_ntopcl, features_notebook, tmp_path, monkeypatch):
    monkeypatch.setenv("JEWELRY_DELIVER", str(tmp_path / "deliver"))
    spec = features.RingSpec(band.BandSpec(size=6, profile="flat"), milgrain=True, groove_depth_mm=0.2)
    res = features.build(spec, tmp_path / "out" / "ring", notebook=features_notebook, deliver=True)
    assert res.run.ok and res.stl.exists() and (tmp_path / "out" / "ring" / f"{spec.stem}.engraving.stl").exists()
    rep = json.loads((tmp_path / "out" / "ring" / f"{spec.stem}.report.json").read_text(encoding="utf-8"))
    assert rep["inputs"]["Bead Count"] == spec.bead_geometry()["count"] and rep["engraving"]["text"] is None
    # the fake ntopcl widens the ring by the beads, as nTop will: the gate expects exactly that width
    assert any(c["name"] == "width" and c["ok"] for c in rep["gate"]["checks"])
    assert res.ok and res.delivered and res.delivered.exists()
    # with text: the fake ntopcl does not cut, and the gate's engraving check says so
    spec2 = features.RingSpec(band.BandSpec(size=6, profile="flat"), text="M+K")
    res2 = features.build(spec2, tmp_path / "out" / "ring2", notebook=features_notebook)
    eng = [c for c in res2.gate.checks if c.name == "engraving"]
    assert eng and not eng[0].ok and "did not cut" in eng[0].detail and not res2.ok
    assert any("engraving 'M+K' on the inside" in n for n in res2.notes)


def test_cli_ring_dry_run(capsys):
    from ntopjewel import cli
    rc = cli.main(["ring", "--size", "6", "--profile", "court", "--milgrain", "--groove", "0.25", "--engrave", "M+K 2026", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0 and "87 beads/row" in out and "Bead Count: 87" in out and "design volume" in out
    rc = cli.main(["ring", "--size", "6", "--groove", "0.9", "--dry-run"])
    assert rc == 1 and "problems" in capsys.readouterr().out


def test_engraving_names_the_missing_triangulation_engine(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def no_engines(name, *a, **k):
        if name in ("mapbox_earcut", "manifold3d", "triangle"):
            raise ImportError(name)
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", no_engines)
    with pytest.raises(RuntimeError, match="pip install"):
        engrave.text_mesh("A", 1.5, 0.3, 9.5)
