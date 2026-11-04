"""Artwork under a solitaire head (Phase 3 step 5, the Seraphine's second half): the panels held
back from the head or the arches, the notebook inputs, the carved ring through its gate, and the
simulated nTop losing a layer."""
import pytest

from ntopjewel import artwork, band, catalog, gems, heads, solitaire
from .pseudo_blend import Blended


def flat():
    return band.BandSpec(size=6, width_mm=2.8, thickness_mm=2.0, profile="flat", mesh_tolerance_mm=0.05)


def seraphine(**kw):
    """The reference ring's layout on a 4-prong round: leaf rows on the side faces, a scroll outside,
    plain shoulders (the head standing on the band). Sharp shank join, as test_solitaire.spec."""
    kw.setdefault("shank_blend_mm", 0.0)
    kw.setdefault("cathedral", False)
    kw.setdefault("panels", artwork.seraphine_panels(25.0, 120.0, outer="scroll", sides="leaves"))
    return solitaire.SolitaireSpec(flat(), heads.HeadSpec(gems.StoneSpec("round", 6.5), prongs=4), **kw)


def test_panels_are_held_back_from_the_head_or_the_arches():
    s = seraphine()
    assert s.validate() == [] and s.has_artwork and not s.arches and not s.milgrain
    lo = s.panel_start_min_deg()
    assert 15.0 < lo < 30.0                                                       # past the head's 3.1 mm reach + 0.5 at r 10.25
    assert all(p.start_deg == max(25.0, lo) for p in s.placed_panels()) and all(p.end_deg == 120.0 for p in s.placed_panels())
    assert s.artwork.panels == s.placed_panels() and s.artwork.shank == s.shank_spec
    arched = seraphine(cathedral=True, shoulder_deg=45.0)                        # (a flat band takes no arches in the
    assert arched.panel_start_min_deg() == pytest.approx(48.0)                    # independent model; the clamp alone: wedge 47° + 1)
    assert all(p.start_deg == 48.0 for p in arched.placed_panels())
    assert "_art_" in s.stem and s.stem != arched.stem and "_art_" not in plain().stem
    short = seraphine(panels=[artwork.Panel("outer", "scroll", 25.0, 20.0)])
    assert any("ends at 20°" in q for q in short.validate())
    court = solitaire.SolitaireSpec(band.BandSpec(size=6, profile="court", mesh_tolerance_mm=0.05),
                                    heads.HeadSpec(gems.StoneSpec("round", 6.5), prongs=6), panels=artwork.seraphine_panels())
    assert any("stand proud" in q for q in court.validate())                      # the dome falls away under the relief


def plain():
    return solitaire.SolitaireSpec(flat(), heads.HeadSpec(gems.StoneSpec("round", 6.5), prongs=4), shank_blend_mm=0.0)


def test_plain():
    """No artwork: the notebook still takes Cut Path / Relief Path, fed no-op specks."""
    s = plain()
    assert s.artwork is None and s.design()["artwork"] is None
    for name in ("solitaire", "solitaire_outline", "solitaire_bezel"):
        kind = {"solitaire": "round", "solitaire_outline": "outline", "solitaire_bezel": "bezel"}[name]
        from ntopjewel import nb_solitaire
        assert nb_solitaire.input_order(kind) == list(catalog.load(name).inputs)
    v = s.notebook_inputs("E", "O", cut_path="C", relief_path="R")
    assert v["Cut Path"] == "C" and v["Relief Path"] == "R" and list(v) == list(catalog.load("solitaire").inputs)


def test_no_op_layers_change_nothing(tmp_path):
    import numpy as np
    import trimesh
    from ntopjewel import shank
    s = plain()
    cut, relief = s.write_artwork(tmp_path, "t")
    bars = shank.write_bars(s.shank_spec, tmp_path, "t")
    speck = trimesh.load(relief, force="mesh")
    r = np.hypot(speck.vertices[:, 0], speck.vertices[:, 1])
    assert s.band.bore_radius_mm + 0.5 < r.min() and r.max() < s.band.outer_radius_mm - 0.5 and speck.vertices[:, 0].max() < 0   # buried, opposite the head
    assert trimesh.load(cut, force="mesh").bounds[0][0] > s.band.outer_radius_mm + 2                   # far outside
    v = s.notebook_inputs("E", "O", cut_path=cut, relief_path=relief, shank_paths=bars)
    carved = solitaire.carved_shank_from_inputs(v)
    assert carved.body_count == 1 and carved.volume == pytest.approx(solitaire.shank_from_inputs(v).volume, rel=1e-7)


def test_design_ring_passes_its_gate(tmp_path):
    s = seraphine()
    m = solitaire.design_mesh(s, ops=Blended())
    m.export(tmp_path / "r.stl")
    rep = solitaire.check_solitaire(s, tmp_path / "r.stl", float(m.volume))
    assert rep.status == "passed", rep.text()
    names = {c.name for c in rep.checks}
    assert {"channel floors", "relief", "rails", "section shape", "seat ledges", "design volume"} <= names
    assert "arch milgrain" not in names


def test_artwork_solitaire_end_to_end_and_a_lost_layer_is_caught(fake_ntopcl, tmp_path, out_dir, monkeypatch):
    nb = tmp_path / "solitaire.ntop"
    nb.write_bytes(b"fake")
    res = solitaire.build(seraphine(), out_dir, notebook=nb)
    assert res.status == "passed", res.text()
    assert (res.run_dir / f"{res.spec.stem}.relief.stl").exists() and (res.run_dir / f"{res.spec.stem}.cut.stl").exists()
    monkeypatch.setenv("FAKE_NTOPCL_SHAPE", "nocut")                              # the channels never cut
    bad = solitaire.build(seraphine(), out_dir, notebook=nb)
    assert bad.status == "failed" and "channel floors" in {c.name for c in bad.gate.failures()}
    monkeypatch.setenv("FAKE_NTOPCL_SHAPE", "norelief")                           # the relief lost: ~1 % of the volume
    bare = solitaire.build(seraphine(), out_dir, notebook=nb)
    assert bare.status == "failed" and "relief" in {c.name for c in bare.gate.failures()}


def test_cli_artwork_solitaire_dry_run(capsys):
    from ntopjewel import cli
    args = ["solitaire", "--profile", "flat", "--width", "2.8", "--thickness", "2", "--prongs", "4", "--no-arches",
            "--sides", "leaves", "--outer", "scroll", "--dry-run"]
    assert cli.main(args) == 0
    out = capsys.readouterr().out
    assert "plain shoulders" in out and "volute at the head end" in out and "leaves of" in out and "Relief Path: <relief path>" in out
    assert cli.main(["solitaire", "--sides", "leaves", "--outer", "vine", "--dry-run"]) == 1   # the default court band: refused, with why
    assert "stand proud" in capsys.readouterr().out


def test_the_section_window_inside_a_panel_is_the_bands_core():
    from shapely.geometry import box
    a = seraphine().artwork
    b = a.band
    assert a.section_clip(181.37) is None                                        # outside the panels: the whole section
    w = a.section_clip(91.37)                                                    # inside: below every channel floor
    assert w.equals(box(b.bore_radius_mm - 1.0, -(b.width_mm / 2 - a.channel_mm - artwork.CORE_CLIP_MM),
                        b.outer_radius_mm - a.channel_mm - artwork.CORE_CLIP_MM, b.width_mm / 2 - a.channel_mm - artwork.CORE_CLIP_MM))
    only_outer = artwork.ArtworkSpec(a.shank, [artwork.Panel("outer", "vine", 25.0, 120.0)])
    w = only_outer.section_clip(91.37)
    assert w.bounds[3] > b.width_mm / 2 and w.bounds[2] == pytest.approx(b.outer_radius_mm - a.channel_mm - artwork.CORE_CLIP_MM)


def test_a_relief_edge_on_the_section_plane_no_longer_fails_the_section_check(tmp_path):
    """2026-11-03, the real Seraphine run: 0.243 mm at 91° with every built point within 0.008 of the
    design - the plane cut a leaf's edge in the design and missed it in the built mesh. The
    relief is the probes' business; the section check compares the core."""
    import numpy as np
    import trimesh
    from ntopjewel import gate
    s = seraphine()
    design = solitaire.design_mesh(s)
    # the built ring: the design with one side leaf shaved by a hundredth along the ring, as the mesher blurs it
    built = design.copy()
    v = built.vertices.copy()
    th = np.degrees(np.arctan2(v[:, 1], v[:, 0]))
    relief = (np.abs(v[:, 2]) > s.band.width_mm / 2 - s.channel_mm + 0.01) & (np.abs(th - 91.37) < 1.0)
    v[relief] = (trimesh.transformations.rotation_matrix(np.radians(0.08), [0, 0, 1])[:3, :3] @ v[relief].T).T
    built.vertices = v
    art = s.artwork
    clipped = gate.section_shape_check(built, art.gate_section, angles=[91.37], tol_mm=art.section_tolerance, clip=art.section_clip)
    assert clipped.ok, clipped.detail
    # and the window still sees the core: the bore pushed in by 0.1 mm at that angle fails it
    v2 = built.vertices.copy()
    core = (np.hypot(v2[:, 0], v2[:, 1]) < s.band.bore_radius_mm + 0.01) & (np.abs(th - 91.37) < 3.0)
    v2[core, :2] *= (s.band.bore_radius_mm - 0.1) / s.band.bore_radius_mm
    built.vertices = v2
    assert not gate.section_shape_check(built, art.gate_section, angles=[91.37], tol_mm=art.section_tolerance, clip=art.section_clip).ok


def test_the_bore_under_the_head_allows_the_shank_blends_bulge(tmp_path):
    """2026-11-03: nTop's smooth union bulged the flat band's bore 36 µm inward under the head, where
    the lower rail runs 0.2 mm above it - a court band's comfort relief had hidden the same thing."""
    import numpy as np
    s = seraphine(shank_blend_mm=0.3)
    assert s.head_bore_gap() == pytest.approx(0.2, abs=0.02) and "within the 0.3 mm shank blend" in s.blend_bore_note()
    assert seraphine(finger_clear_mm=0.75).blend_bore_note() is None
    m = solitaire.design_mesh(s).copy()                                           # sharp: the pseudo-blend's square fill
    v = m.vertices.copy()                                                          # itself stands into the bore
    r, th = np.hypot(v[:, 0], v[:, 1]), np.degrees(np.arctan2(v[:, 1], v[:, 0]))
    bore = s.band.bore_radius_mm
    bulge = (r < bore + 0.01) & (np.abs(th) < 10.0)
    v[bulge, :2] *= (bore - 0.04) / bore                                           # 40 µm in, under the head only
    m.vertices = v
    m.export(tmp_path / "r.stl")
    rep = solitaire.check_solitaire(s, tmp_path / "r.stl", float(m.volume))
    by = {c.name: c for c in rep.checks}
    assert by["bore"].ok and by["bore under the head"].ok and "blend's bulge" in by["bore under the head"].detail
    v[bulge, :2] *= (bore - 0.12) / (bore - 0.04)                                 # 120 µm: more than any blend explains
    m.vertices = v
    m.export(tmp_path / "r2.stl")
    rep = solitaire.check_solitaire(s, tmp_path / "r2.stl", float(m.volume))
    by = {c.name: c for c in rep.checks}
    assert by["bore"].ok and not by["bore under the head"].ok
    sharp = seraphine()                                                            # a sharp join allows nothing extra
    rep = solitaire.check_solitaire(sharp, tmp_path / "r.stl", float(m.volume))
    assert not {c.name: c for c in rep.checks}["bore under the head"].ok
