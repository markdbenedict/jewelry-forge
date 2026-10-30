"""Blended booleans: the blend radius inputs, the volume bound, and the notebooks' order of operations."""
import pytest

from ntopjewel import band, gems, geom, heads, solitaire, tables


def test_junction_length_is_the_meeting_curve():
    import trimesh
    plate = trimesh.creation.box(extents=(6, 6, 1))
    rod = trimesh.creation.cylinder(radius=0.5, height=4, sections=256)
    assert geom.junction_length(plate, rod) == pytest.approx(2 * 2 * 3.14159 * 0.5, rel=0.01)   # two circles where the rod leaves the plate
    apart = rod.copy()
    apart.apply_translation((10, 0, 0))
    assert geom.junction_length(plate, apart) == 0.0


def test_blend_defaults_and_limits():
    h = heads.HeadSpec(gems.StoneSpec("round", 6.5), prongs=6)
    assert h.blend == tables.SETTINGS["blend_radius_mm"] and h.notebook_inputs("E")["Blend Radius"] == h.blend
    assert heads.HeadSpec(gems.StoneSpec("round", 6.5), blend_mm=0.0).validate() == []                   # sharp is allowed
    assert heads.HeadSpec(gems.StoneSpec("round", 6.5), blend_mm=1.5).validate()                         # beyond a fillet
    assert heads.HeadSpec(gems.StoneSpec("round", 6.5), blend_mm=0.9).validate()                         # wider than the prong
    est = h.blend_volume_mm3()
    assert 0 < est < 0.1 * heads.design_mesh(h).volume                                                   # a fillet, not a reshaping
    assert heads.HeadSpec(gems.StoneSpec("round", 6.5), blend_mm=0.0).blend_volume_mm3() == 0.0
    assert heads.BezelSpec(gems.StoneSpec("round", 6.5)).blend_volume_mm3() == 0.0                       # rounds edges only


def test_blended_volume_check_widens_by_the_estimate():
    c = band.blended_design_volume_check(100.0, 2.0, 104.5, 3.0)        # +4.5 %: within 3 % + 2 %
    assert c.status == "passed" and "blend" in c.detail
    assert band.blended_design_volume_check(100.0, 2.0, 108.0, 3.0).status == "failed"     # +8 %: outside 3 % + 2 %
    assert band.blended_design_volume_check(100.0, 0.0, 103.5, 3.0).status == "failed"              # unblended: 3 % as before


def test_solitaire_blends_in_inputs_and_identity():
    s = solitaire.SolitaireSpec(band.BandSpec(size=6, profile="court", mesh_tolerance_mm=0.05),
                                heads.HeadSpec(gems.StoneSpec("round", 6.5), prongs=6))
    v = s.notebook_inputs("E", "O")
    assert v["Head Blend"] == s.head.blend and v["Shank Blend"] == s.shank_blend and list(v)[-2:] == ["Shank Blend", "Output Path"]
    sharp = solitaire.SolitaireSpec(s.band, s.head, shank_blend_mm=0.0)
    assert sharp.stem != s.stem and sharp.blend_volume_mm3() < s.blend_volume_mm3()
    assert s.bead_head_gap >= solitaire.BEAD_HEAD_GAP
    wide = solitaire.SolitaireSpec(s.band, s.head, shank_blend_mm=0.6)
    assert wide.bead_head_gap > s.bead_head_gap                                                           # beads keep clear of the blend
    assert solitaire.SolitaireSpec(s.band, s.head, shank_blend_mm=1.2).validate()


def test_notebooks_blend_the_joins_and_cut_the_seat_afterwards(tmp_path):
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
    nb = FakeNotebook()
    res = ph.build(nb, pp)
    blk = res["block"]["blocks"]
    # inside the block: the basket union is blended, and the seat is cut from the blended basket
    assert "Blend Radius" in str(res["block"]["log"])
    mod = load_recipe("solitaire")
    params = mod.prepare({}, tmp_path)
    params.update({"save_to": str(tmp_path / "sol.ntop"), "recipe_to": str(tmp_path / "sol.json"), "test_output": str(tmp_path / "r.stl"),
                   "seat_block": str(tmp_path / "stone_seat.ntop"), "head_block": str(tmp_path / "prong_head.ntop")})
    nb = FakeNotebook()
    res = mod.build(nb, params)
    b = res["blocks"]
    assert nb.blocks[b["Joined"]]["wired"]["Blend Radius"][0] == b["Shank Blend"]
    assert nb.blocks[b["Prong Head"]]["wired"]["Blend Radius"][0] == b["Head Blend"]
    assert nb.blocks[b["Ring"]]["wired"]["Primary Body"][0] == b["Joined"]                                # the cuts come after the blend
    assert b["Placed Seat"] in nb.blocks[b["Ring"]]["lists"]["Subtraction Bodies"]
    assert nb.inputs == mod.INPUT_ORDER and res["warnings"] == []


def test_cli_blend_options(capsys):
    from ntopjewel import cli
    assert cli.main(["solitaire", "--size", "6", "--blend", "0", "--shank-blend", "0.4", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Head Blend: 0.0" in out and "Shank Blend: 0.4" in out
