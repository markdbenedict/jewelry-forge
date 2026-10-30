import pytest

from ntopjewel import band, catalog, gems, heads, solitaire
from .pseudo_blend import Blended


def spec(size=6, **kw):
    """The round solitaire the offline tests build. Its shank join is sharp: the simulated nTop's
    blend fill is square-cornered, and where a foot of the round head meets the hollow under the
    arches that square stands 0.05 mm into the bore, which nTop's smooth fill did not (Mark's
    blended US6 run passed its bore check, 2026-10-30). The head's own blend, and the shank join
    of the pear and bezel rings, run blended through the fake."""
    kw.setdefault("shank_blend_mm", 0.0)
    return solitaire.SolitaireSpec(band.BandSpec(size=size, profile="court", mesh_tolerance_mm=0.05),
                                   heads.HeadSpec(gems.StoneSpec("round", 6.5), prongs=6), **kw)


def test_placement_numbers():
    import math
    s = spec()
    assert s.validate() == []
    _, pav = s.head.stone.heights
    assert s.girdle_radius - s.head.stone.girdle / 2 - pav == pytest.approx(s.band.bore_radius_mm + 0.6)   # culet clearance
    lay = s.placed_head.layout()
    assert s.girdle_radius + lay["z_base"] - s.head.rail_rho == pytest.approx(s.band.bore_radius_mm + 0.2)  # rail clear of the bore
    a, ro, phi = s.arch(), s.band.outer_radius_mm, math.radians(45)
    # tangent at +45°: the band's outer point there lies on the arch circle and on the line from its centre through the origin
    px, py = ro * math.cos(phi), ro * math.sin(phi)
    assert math.hypot(px - a["cx"], py - a["cy"]) == pytest.approx(a["R"])
    assert math.atan2(py - a["cy"], px - a["cx"]) == pytest.approx(phi)
    assert math.hypot(a["crest"] - a["cx"], a["cy"]) == pytest.approx(a["R"])                          # through the crest
    assert a["rise"] > 1.0 and a["inner_min"] < a["inner"] < a["inner_max"]
    assert spec(finger_clear_mm=0.3).validate()                                                          # under the wall floor
    assert spec(shoulder_deg=25).validate()                                                              # no tangent arch
    assert spec(bead_radius_mm=0.2).validate()                                                           # under the bead floor
    assert list(spec().notebook_inputs("E", "O")) == list(catalog.load("solitaire").inputs)


def test_beads_run_from_the_tangent_point_and_stop_clear_of_the_head():
    s = spec()
    bd = s.beads()
    assert bd["angles"][0] == pytest.approx(45.0) and len(bd["angles"]) >= 6
    for x, y, z, _ in s.bead_centres():
        import math
        assert math.hypot(y, z) - bd["radius"] >= s._head_envelope(x) + 0.2 - 1e-9
    off = spec(milgrain=False)
    assert off.bead_centres() == [] and off.notebook_inputs("E")["Bead Radius"] == 0.05
    assert off.stem != spec().stem


@pytest.mark.parametrize("size", [5, 7])
def test_design_ring_passes_its_gate(size, tmp_path):
    s = spec(size)
    m = solitaire.design_mesh(s, ops=Blended())            # as nTop builds it
    m.export(tmp_path / "r.stl")
    rep = solitaire.check_solitaire(s, tmp_path / "r.stl", float(m.volume))
    assert rep.status == "passed", rep.text()


def test_solitaire_end_to_end_and_an_unseated_ring_is_caught(fake_ntopcl, tmp_path, monkeypatch):
    nb = tmp_path / "solitaire.ntop"
    nb.write_bytes(b"fake")
    monkeypatch.setenv("JEWELRY_DELIVER", str(tmp_path / "Jewelry"))
    res = solitaire.build(spec(6), tmp_path / "out", notebook=nb, deliver=True, cast_metal="sterling")
    assert res.status == "passed", res.text()
    assert res.delivered and res.delivered.exists() and (res.delivered.parent / f"{res.spec.stem}.print_sterling.stl").exists()
    monkeypatch.setenv("FAKE_NTOPCL_SHAPE", "noseat")
    bad = solitaire.build(spec(6), tmp_path / "out", notebook=nb)
    assert bad.status == "failed" and {"stone fits", "drop-in clear"} <= {c.name for c in bad.gate.failures()}
    monkeypatch.setenv("FAKE_NTOPCL_SHAPE", "nobeads")                  # milgrain lost: ~1 % of volume, only the bead check sees it
    bare = solitaire.build(spec(6), tmp_path / "out", notebook=nb)
    assert bare.status == "failed" and [c.name for c in bare.gate.failures()] == ["arch milgrain"]


def test_solitaire_recipe_embeds_both_blocks_and_places_the_head(tmp_path):
    from .fake_notebook import FakeNotebook
    from .test_notebook_api import load_recipe
    env = tmp_path / "env.stl"
    gems.SeatSpec(gems.StoneSpec("round", 6.5)).envelope().export(str(env))
    load_recipe("stone_seat").build(FakeNotebook(), {"save_to": str(tmp_path / "sh.ntop"), "recipe_to": str(tmp_path / "sh.json"),
                                                     "test_output": str(tmp_path / "s.stl"), "values": {"Seat Path": str(env)}})
    ph = load_recipe("prong_head")
    pp = ph.prepare({}, tmp_path)
    pp.update({"save_to": str(tmp_path / "ph.ntop"), "recipe_to": str(tmp_path / "ph.json"), "test_output": str(tmp_path / "h.stl"),
               "seat_block": str(tmp_path / "stone_seat.ntop")})
    ph.build(FakeNotebook(), pp)
    mod = load_recipe("solitaire")
    params = mod.prepare({}, tmp_path)
    params.update({"save_to": str(tmp_path / "sol.ntop"), "recipe_to": str(tmp_path / "sol.json"), "test_output": str(tmp_path / "r.stl"),
                   "seat_block": str(tmp_path / "stone_seat.ntop"), "head_block": str(tmp_path / "prong_head.ntop")})
    nb = FakeNotebook()
    res = mod.build(nb, params)
    ids = res["identifiers"]
    assert ids["Head Placement"].startswith("rotation_transform") and ids["Placed Head"].startswith("transform_object")
    assert ids["block:stone_seat"].startswith("user_func_") and ids["block:prong_head"].startswith("user_func_")
    b = res["blocks"]
    assert nb.blocks[b["Prong Head"]]["wired"]["Seat Cutter"][0] == "Seat Local"
    assert nb.blocks[b["Placed Head"]]["wired"]["Transformation"][0] == "Placement"
    # the arches join the band before its edge-round offsets; the milgrain rows join after them
    assert b["Shoulders"] in nb.blocks[b["Band + Extra"]]["lists"]["Bodies"]
    assert nb.blocks[b["Shrunk"]]["wired"]["Body"][0] == b["Band + Extra"]
    assert {b["Milgrain+"], b["Milgrain-"]} <= set(nb.blocks[b["Shank"]]["lists"]["Bodies"])
    assert nb.blocks[b["Milgrain+"]]["wired"]["Axis"][0] == b["Beads+ Axis"]
    assert nb.inputs == mod.INPUT_ORDER and nb.output == "Volume" and nb.lint() == [] and res["warnings"] == []


def test_cli_solitaire_dry_run(capsys):
    from ntopjewel import cli
    assert cli.main(["solitaire", "--size", "6", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Arch Radius" in out and "milgrain: 8 beads" in out and "court" in out
    assert cli.main(["solitaire", "--size", "6", "--finger-clear", "0.2", "--dry-run"]) == 1


def test_gate_json_on_disk_holds_the_family_checks(fake_ntopcl, tmp_path):
    """2026-10-28: the first real run's gate.json held only the generic checks (written before the
    solitaire ones were appended) - the report was right, the file Mark opened was not."""
    import json
    nb = tmp_path / "solitaire.ntop"
    nb.write_bytes(b"fake")
    res = solitaire.build(spec(6), tmp_path / "out", notebook=nb)
    names = [c["name"] for c in json.loads(res.stl.with_suffix(".gate.json").read_text())["checks"]]
    assert {"bore", "extents", "stone fits", "design volume"} <= set(names)


def test_solitaire_gui_shows_only_the_ring():
    from .test_notebook_api import load_recipe
    assert load_recipe("solitaire").DEFAULTS["show"] == ["Ring", "Ring Body"]


def makena():
    return solitaire.SolitaireSpec(band.BandSpec(size=4.5, profile="court", mesh_tolerance_mm=0.05),
                                   heads.OutlineHeadSpec(gems.StoneSpec("pear", 12.3, 8.9, 4.6, material="glass")), text="Makena")


def test_pear_solitaire_spec():
    s = makena()
    assert s.validate() == [] and s.outline and s.prong_count == 5
    assert s.girdle_radius + s.placed_head.lowest_z() >= s.band.bore_radius_mm + 0.2 - 1e-6       # nothing in the bore
    assert len(s.beads()["angles"]) >= 3
    v = s.notebook_inputs("E", "O", prongs_path="P", engraving_path="T")
    assert list(v) == list(catalog.load("solitaire_outline").inputs)
    assert v["Engraving Wrap Length"] > 2 * 3.14159 * s.band.bore_radius_mm                        # wrapped a little inside the bore surface
    assert makena().stem == s.stem and "Makena" not in s.stem
    assert solitaire.SolitaireSpec(s.band, s.head, text="Makenna").stem != s.stem                  # the text is part of the identity


def test_pear_solitaire_end_to_end_and_lost_engraving_is_caught(fake_ntopcl, tmp_path, monkeypatch):
    nb = tmp_path / "solitaire_outline.ntop"
    nb.write_bytes(b"fake")
    res = solitaire.build(makena(), tmp_path / "out", notebook=nb)
    assert res.status == "passed", res.text()
    names = {c.name for c in res.gate.checks}
    assert {"engraving", "arch milgrain", "seat ledges", "design volume"} <= names
    monkeypatch.setenv("FAKE_NTOPCL_SHAPE", "noengrave")
    bare = solitaire.build(makena(), tmp_path / "out", notebook=nb)
    assert bare.status == "failed" and [c.name for c in bare.gate.failures()] == ["engraving"]


def test_solitaire_outline_recipe_embeds_the_outline_head(tmp_path):
    from .fake_notebook import FakeNotebook
    from .test_notebook_api import load_recipe
    stone = gems.StoneSpec("pear", 12.3, 8.9, 4.6, material="glass")
    env = tmp_path / "env.stl"
    gems.SeatSpec(stone).envelope().export(str(env))
    load_recipe("stone_seat").build(FakeNotebook(), {"save_to": str(tmp_path / "sh.ntop"), "recipe_to": str(tmp_path / "sh.json"),
                                                     "test_output": str(tmp_path / "s.stl"), "values": {"Seat Path": str(env)}})
    oh = load_recipe("outline_head")
    pp = oh.prepare({}, tmp_path)
    pp.update({"save_to": str(tmp_path / "oh.ntop"), "recipe_to": str(tmp_path / "oh.json"), "test_output": str(tmp_path / "h.stl"),
               "seat_block": str(tmp_path / "stone_seat.ntop")})
    oh.build(FakeNotebook(), pp)
    mod = load_recipe("solitaire_outline")
    params = mod.prepare({}, tmp_path)
    params.update({"save_to": str(tmp_path / "so.ntop"), "recipe_to": str(tmp_path / "so.json"), "test_output": str(tmp_path / "r.stl"),
                   "seat_block": str(tmp_path / "stone_seat.ntop"), "head_block": str(tmp_path / "outline_head.ntop")})
    nb = FakeNotebook()
    res = mod.build(nb, params)
    b = res["blocks"]
    assert nb.blocks[b["Outline Head"]]["wired"]["Seat Cutter"][0] == "Seat Local"
    assert b["Engraving"] in nb.blocks[b["Ring"]]["lists"]["Subtraction Bodies"]            # cut after the blended join
    assert nb.inputs == mod.INPUT_ORDER and res["warnings"] == []
