import pytest

from ntopjewel import band, catalog, gems, heads, solitaire


def spec(size=6, **kw):
    return solitaire.SolitaireSpec(band.BandSpec(size=size, profile="court", mesh_tolerance_mm=0.05),
                                   heads.HeadSpec(gems.StoneSpec("round", 6.5), prongs=6), **kw)


def test_placement_numbers():
    s = spec()
    assert s.validate() == []
    _, pav = s.head.stone.heights
    assert s.girdle_radius - s.head.stone.girdle / 2 - pav == pytest.approx(s.band.bore_radius_mm + 0.6)   # culet clearance
    lay = s.placed_head.layout()
    assert s.girdle_radius + lay["z_base"] - s.head.rail_rho == pytest.approx(s.band.bore_radius_mm + 0.2)  # rail clear of the bore
    xc, r2 = s.cathedral()
    import math
    ro, phi = s.band.outer_radius_mm, math.radians(45)
    assert math.hypot(ro * math.cos(phi) - xc, ro * math.sin(phi)) == pytest.approx(r2)                  # leaves the band at 45°
    assert spec(finger_clear_mm=0.3).validate()                                                          # under the wall floor
    assert list(spec().notebook_inputs("E", "O")) == list(catalog.load("solitaire").inputs)


@pytest.mark.parametrize("size", [5, 7])
def test_design_ring_passes_its_gate(size, tmp_path):
    s = spec(size)
    m = solitaire.design_mesh(s)
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
    assert nb.inputs == mod.INPUT_ORDER and nb.output == "Volume" and nb.lint() == [] and res["warnings"] == []


def test_cli_solitaire_dry_run(capsys):
    from ntopjewel import cli
    assert cli.main(["solitaire", "--size", "6", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Cathedral Radius" in out and "court" in out
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
