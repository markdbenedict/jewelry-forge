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


def test_solitaire_end_to_end_and_an_unseated_ring_is_caught(fake_ntopcl, tmp_path, out_dir, monkeypatch):
    nb = tmp_path / "solitaire.ntop"
    nb.write_bytes(b"fake")
    monkeypatch.setenv("JEWELRY_DELIVER", str(tmp_path / "Jewelry"))
    res = solitaire.build(spec(6), out_dir, notebook=nb, deliver=True, cast_metal="sterling")
    assert res.status == "passed", res.text()
    assert res.delivered and res.delivered.exists() and (res.delivered.parent / f"{res.spec.stem}.print_sterling.stl").exists()
    monkeypatch.setenv("FAKE_NTOPCL_SHAPE", "noseat")
    bad = solitaire.build(spec(6), out_dir, notebook=nb)
    assert bad.status == "failed" and {"stone fits", "drop-in clear"} <= {c.name for c in bad.gate.failures()}
    monkeypatch.setenv("FAKE_NTOPCL_SHAPE", "nobeads")                  # milgrain lost: ~1 % of volume, only the bead check sees it
    bare = solitaire.build(spec(6), out_dir, notebook=nb)
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
    # the shank is the bar Python wrote: imported, opened on the bar (re-distanced), wrapped; the arches opened on
    # their own; both united sharp with the milgrain rows
    assert nb.blocks[b["Shank Mesh"]]["wired"]["Path"][0] == "Shank Path"
    assert nb.blocks[b["Shank Bar"]]["wired"]["Mesh"][0] == b["Shank Mesh"]
    assert nb.blocks[b["Shank Mesh 4"]]["wired"]["Path"][0] == "Shank Path 4"                     # four bars, each opened, then united
    assert nb.blocks[b["Shrunk"]]["wired"]["Body"][0] == b["Shank Bar"] and nb.blocks[b["Shrunk 4"]]["wired"]["Body"][0] == b["Shank Bar 4"]
    assert nb.blocks[b["Shank Bars"]]["lists"]["Bodies"] == [b["Opened"], b["Opened 2"], b["Opened 3"], b["Opened 4"]]
    assert nb.blocks[b["Shank"]]["wired"]["Body"][0] == b["Shank Bars"] and "Band + Extra" not in b and "Outer" not in b
    assert nb.blocks[b["Shank"]]["wired"]["Y Mapping Length"][0] == "Wrap Length"
    assert nb.variables["Band Body"]["wraps"] == b["Shank"]
    # the artwork carved into the opened band before anything joins it: (Band Body − Panel Cuts) ∪ Relief = Carved Band
    assert nb.blocks[b["Panel Cuts Mesh"]]["wired"]["Path"][0] == "Cut Path" and nb.blocks[b["Relief Mesh"]]["wired"]["Path"][0] == "Relief Path"
    assert nb.blocks[b["Carved"]]["wired"]["Primary Body"][0] == "Band Body" and nb.blocks[b["Carved"]]["lists"]["Subtraction Bodies"] == [b["Panel Cuts"]]
    assert nb.blocks[b["Carved + Relief"]]["lists"]["Bodies"] == [b["Carved"], b["Relief"]] and nb.variables["Carved Band"]["wraps"] == b["Carved + Relief"]
    assert nb.blocks[b["Slot Mesh"]]["wired"]["Path"][0] == "Slot Path" and nb.blocks[b["Slot Cutter"]]["wired"]["Mesh"][0] == b["Slot Mesh"]
    assert nb.blocks[b["Split Arches"]]["wired"]["Primary Body"][0] == b["Shoulders"] and nb.blocks[b["Split Arches"]]["lists"]["Subtraction Bodies"] == [b["Slot Cutter"]]
    assert nb.blocks[b["Arches Shrunk"]]["wired"]["Body"][0] == b["Split Arches"]
    assert nb.blocks[b["Arches Shrunk Body Mesh"]]["wired"]["Tolerance"][0] == "Mesh Tolerance"
    assert nb.blocks[b["Arches"]]["wired"]["Body"][0] == b["Arches Shrunk Body"] and nb.blocks[b["Arches"]]["wired"]["Distance"][0] == "Edge Round"
    assert {b["Arches"], b["Milgrain+"], b["Milgrain-"], "Carved Band"} <= set(nb.blocks[b["Shank Union"]]["lists"]["Bodies"])
    assert "Band Body" not in nb.blocks[b["Shank Union"]]["lists"]["Bodies"]                     # the carved band, not the bare one
    assert nb.blocks[b["Milgrain+"]]["wired"]["Axis"][0] == b["Beads+ Axis"]
    assert nb.inputs == mod.INPUT_ORDER and nb.output == "Volume" and nb.lint() == [] and res["warnings"] == []


def test_cli_solitaire_dry_run(capsys):
    from ntopjewel import cli
    assert cli.main(["solitaire", "--size", "6", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Arch Radius" in out and "milgrain: 8 beads" in out and "court" in out
    assert cli.main(["solitaire", "--size", "6", "--finger-clear", "0.2", "--dry-run"]) == 1


def test_gate_json_on_disk_holds_the_family_checks(fake_ntopcl, tmp_path, out_dir):
    """2026-10-28: the first real run's gate.json held only the generic checks (written before the
    solitaire ones were appended) - the report was right, the file Mark opened was not."""
    import json
    nb = tmp_path / "solitaire.ntop"
    nb.write_bytes(b"fake")
    res = solitaire.build(spec(6), out_dir, notebook=nb)
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


def test_pear_solitaire_end_to_end_and_lost_engraving_is_caught(fake_ntopcl, tmp_path, out_dir, monkeypatch):
    nb = tmp_path / "solitaire_outline.ntop"
    nb.write_bytes(b"fake")
    res = solitaire.build(makena(), out_dir, notebook=nb)
    assert res.status == "passed", res.text()
    names = {c.name for c in res.gate.checks}
    assert {"engraving", "arch milgrain", "seat ledges", "design volume"} <= names
    monkeypatch.setenv("FAKE_NTOPCL_SHAPE", "noengrave")
    bare = solitaire.build(makena(), out_dir, notebook=nb)
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


# ---- Phase 3 step 1d: the solitaire on a shaped shank ----------------------------------------------
def tapered(**kw):
    from ntopjewel import shank
    b = band.BandSpec(size=6, profile="court", mesh_tolerance_mm=0.05)
    return spec(6, shank=shank.ShankSpec(b, width_bottom_mm=2.4, thickness_bottom_mm=1.2, **kw))


def test_a_shaped_shank_under_the_head():
    from ntopjewel import shank
    s, plain = tapered(), spec(6)
    assert s.validate() == [] and s.shaped and not plain.shaped
    assert "_w4-2.4_t1.3-1.2_" in s.stem and s.stem != plain.stem
    assert plain.shank_spec.band == plain.band and not plain.shank_spec.tapered                 # the band all round
    v = s.notebook_inputs("S", "O", shank_paths=["B", "B2", "B3", "B4"])
    assert list(v) == list(catalog.load("solitaire").inputs)                                    # Shank Path .. Shank Path 4, Wrap Length ... Output Path
    assert v["Shank Path"] == "B" and v["Shank Path 4"] == "B4" and v["Wrap Length"] == s.shank_spec.notebook_inputs("B")["Wrap Length"]
    assert s.notebook_inputs("S", "O", shank_paths="B")["Shank Path 3"] == "B"                   # one path fills every slot (a dry run)
    assert "Outer Radius" not in v and v["Z Top"] == 2.0                                         # the arches still read the band's numbers
    assert tapered(taper_from_deg=40).validate()                                                 # inside the arches: refused
    b = s.band
    with pytest.raises(ValueError):
        solitaire.SolitaireSpec(b, s.head, shank=shank.ShankSpec(band.BandSpec(size=7, profile="court", mesh_tolerance_mm=0.05)))
    assert spec(6, shank=shank.ShankSpec(b, split_mm=1.6)).validate() == []                      # a split: allowed (its own test)
    assert any("plait shank under a head" in p for p in spec(6, shank=shank.ShankSpec(b, knot="plait")).validate())
    assert spec(6, shank=shank.ShankSpec(b, dip_mm=1.0)).validate()
    assert spec(6, shank=shank.ShankSpec(b, rope=2)).validate()
    ring = solitaire.design_mesh(s)
    assert ring.is_watertight and ring.body_count == 1
    assert ring.volume < solitaire.design_mesh(plain).volume - 20                                # the taper takes metal off the bottom
    assert set(s.free_angles()) == {61.37, 91.37, 121.37, 151.37, 181.37, 211.37, 241.37, 271.37, 301.37}


def test_tapered_solitaire_end_to_end_and_a_plain_shank_is_caught(fake_ntopcl, tmp_path, out_dir, monkeypatch):
    nb = tmp_path / "solitaire.ntop"
    nb.write_bytes(b"fake")
    res = solitaire.build(tapered(), out_dir, notebook=nb)
    assert res.status == "passed", res.text()
    assert (res.run_dir / f"{res.spec.stem}.bar.stl").exists() and "section shape" in {c.name for c in res.gate.checks}
    monkeypatch.setenv("FAKE_NTOPCL_SHAPE", "plainshank")                                        # the bar's head section all round
    bad = solitaire.build(tapered(), out_dir, notebook=nb)
    assert bad.status == "failed" and "section shape" in {c.name for c in bad.gate.failures()}


def test_cli_tapered_solitaire_dry_run(capsys):
    from ntopjewel import cli
    assert cli.main(["solitaire", "--size", "6", "--width-bottom", "2.4", "--thickness-bottom", "1.2", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "_w4-2.4_t1.3-1.2_" in out and "bottom: width 2.4 thickness 1.2" in out
    assert cli.main(["solitaire", "--size", "6", "--width-bottom", "2.4", "--taper-from", "30", "--dry-run"]) == 1


def split_shank(**kw):
    from ntopjewel import shank
    b = band.BandSpec(size=6, profile="court", mesh_tolerance_mm=0.05)
    return spec(6, shank=shank.ShankSpec(b, split_mm=kw.pop("split_mm", 1.6), split_span_deg=kw.pop("split_span_deg", 80), **kw))


def test_a_split_shank_under_the_head():
    from ntopjewel import shank
    s = split_shank()
    assert s.validate() == [] and s.split and "_split1.6_" in s.stem
    assert s.head_foot_half_span() == pytest.approx(2.075, abs=0.01)                               # the lower rail bridges the slot
    assert split_shank(split_mm=4.0, split_span_deg=80).validate()                                   # wider than the foot: refused
    cutter = s.slot_mesh()
    assert cutter.is_watertight and cutter.bounds[1][0] > s.arch()["crest"] + 1.5 and abs(cutter.bounds[1][2]) == pytest.approx(0.8)
    assert spec(6).slot_mesh().volume < 0.01                                                        # a speck when there is no split
    ring = solitaire.design_mesh(s)
    assert ring.is_watertight and ring.body_count == 1
    assert ring.volume < solitaire.design_mesh(spec(6)).volume - 25                                 # the slot, through band and arches
    v = s.notebook_inputs("S", "O", shank_paths="B", slot_path="C")
    assert v["Slot Path"] == "C" and list(v) == list(catalog.load("solitaire").inputs)


def test_split_solitaire_end_to_end(fake_ntopcl, tmp_path, out_dir):
    nb = tmp_path / "solitaire.ntop"
    nb.write_bytes(b"fake")
    res = solitaire.build(split_shank(), out_dir, notebook=nb)
    assert res.status == "passed", res.text()
    assert (res.run_dir / f"{res.spec.stem}.slot.stl").exists()
    detail = {c.name: c.detail for c in res.gate.checks}
    assert "beside the slot" in detail["bore closed under the stone"] and "slot's edges" in detail["design volume"]


def test_cli_split_solitaire_dry_run(capsys):
    from ntopjewel import cli
    assert cli.main(["solitaire", "--size", "6", "--split", "1.6", "--split-span", "80", "--dry-run"]) == 0
    assert "_split1.6_" in capsys.readouterr().out


def knotted(**kw):
    """Reference ring 01 in the pipeline's terms: a marquise with V-prongs on a split shank whose
    halves weave a trinity knot on each shoulder."""
    from ntopjewel import shank
    b = band.BandSpec(size=6, profile="court", width_mm=4.0, thickness_mm=1.6, mesh_tolerance_mm=0.1)
    stone = gems.StoneSpec(shape="marquise", length_mm=10.0, width_mm=5.0)
    head = heads.OutlineHeadSpec(stone, mesh_tolerance_mm=0.1)
    kw.setdefault("shank", shank.ShankSpec(b, split_mm=1.6, split_span_deg=100.0, knot="trinity", knot_strand_mm=0.9, knot_mm=5.6))
    return solitaire.SolitaireSpec(b, head, **kw)


def test_a_knot_shank_under_the_head():
    import math
    from ntopjewel import shank
    s = knotted()
    assert s.validate() == [] and s.shaped and s.knot == "trinity" and not s.arches and not s.milgrain
    assert s.shank.knot_pad_deg == s.knot_pad_deg_needed() == pytest.approx(math.degrees((s.head_half_length() + solitaire.KNOT_PAD_CLEAR_MM)
                                                                                           / (s.band.bore_radius_mm + 0.8)), abs=0.01)
    assert s.head_half_length() == pytest.approx(3.03, abs=0.05)                                     # the marquise head along the ring
    v = s.notebook_inputs("E", "O", prongs_path="P", engraving_path="T", shank_paths="B", slot_path="S")
    assert list(v) == list(catalog.load("solitaire_outline").inputs)
    assert v["Edge Round"] == 0.0 and v["Z Top"] == 0.5 and v["Dome Tube Radius"] == 2.0            # the buried stubs' numbers
    assert v["Arch Radius"] == solitaire.BURIED_ARCH_RADIUS_MM and v["Arch Centre X"] > 0 and v["Wedge Angle"] == 10.0
    assert v["Bead Count"] == 1 and v["Bead Radius"] == 0.05                                        # milgrain off: the buried bead
    catalog.load("solitaire_outline").build_inputs(v)                                               # inside the catalog's ranges
    assert s.slot_mesh().bounds[0][0] > s.band.outer_radius_mm + 5                                   # a speck: the band under the head is whole
    assert all(not s.shank.trinity_section(a) for a in s.free_angles()) and 181.37 in s.free_angles()
    assert "_split1.6_trinity5.6_" in s.stem
    # a knot shank keeps its own pad when it is wider than the head needs; a plait is refused
    wide = knotted(shank=shank.ShankSpec(s.band, split_mm=1.6, split_span_deg=100.0, knot="trinity", knot_strand_mm=0.9, knot_mm=5.6,
                                         knot_pad_deg=40.0, knot_pad_set=True))
    assert wide.shank.knot_pad_deg == 40.0 and wide.validate() == []
    b6 = spec(6).band
    assert any("plait shank under a head" in p for p in spec(6, shank=shank.ShankSpec(b6, knot="plait")).validate())
    ring = solitaire.design_mesh(s)
    assert ring.is_watertight and ring.body_count == 1
    import numpy as np
    assert np.hypot(ring.vertices[:, 0], ring.vertices[:, 1]).min() == pytest.approx(s.band.bore_radius_mm, abs=2e-3)


def test_knot_solitaire_end_to_end(fake_ntopcl, tmp_path, out_dir):
    nb = tmp_path / "solitaire_outline.ntop"
    nb.write_bytes(b"fake")
    s = knotted()
    res = solitaire.build(s, out_dir, notebook=nb)
    assert res.status == "passed", res.text()
    assert {c.name for c in res.gate.checks} >= {"section shape", "bore", "extents", "stone fits", "design volume"}


def test_cli_knot_solitaire_dry_run(capsys):
    from ntopjewel import cli
    assert cli.main(["solitaire", "--size", "6", "--shape", "marquise", "--length", "10", "--stone-width", "5",
                     "--split", "1.6", "--split-span", "100", "--knot", "trinity", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "_split1.6_trinity5.2_" in out and "arches and milgrain: off" in out and "Slot Path: <slot path>" not in out
    assert "Arch Radius: 0.55" in out
