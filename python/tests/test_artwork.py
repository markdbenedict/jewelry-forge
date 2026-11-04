"""Artwork on the band (Phase 3 step 5): the motifs stay inside their channels, the layers are clean
disjoint bodies, the notebook's wiring, and the band end to end on the simulated nTop - including the
gate catching a notebook that never cut the channels or lost the relief."""
import numpy as np
import pytest
from shapely.geometry import box

from ntopjewel import artwork, band, catalog, shank


def flat():
    return band.BandSpec(size=6, width_mm=2.8, thickness_mm=2.0, profile="flat", mesh_tolerance_mm=0.05)


def seraphine(**kw):
    return artwork.ArtworkSpec(shank.ShankSpec(flat()), artwork.seraphine_panels(), **kw)


@pytest.mark.parametrize("motif", artwork.MOTIFS)
def test_every_motif_stays_inside_its_channel_on_both_faces(motif):
    for face in ("outer", "side+"):
        a = artwork.ArtworkSpec(shank.ShankSpec(flat()), [artwork.Panel(face, motif, 25.0, 120.0)])
        assert a.validate() == [], (face, motif)
        w, Lu = a.channel_width(face), a.panel_length(a.panels[0])
        inside = box(0.0, -w / 2 + 0.02, Lu, w / 2 - 0.02)
        for d in a.motif(a.panels[0]):
            assert d["poly"].is_valid and d["poly"].area > 0.02
            assert inside.contains(d["poly"]), (face, motif, d["poly"].bounds)
        if motif != "plain":
            assert a.motif(a.panels[0])


def test_the_leaf_row_fills_the_panel_and_the_vine_is_one_piece():
    a = seraphine()
    side, outer = a.panels[1], a.panels[0]
    leaves = a.motif(side)
    assert len(leaves) == 7 and all(len(d["veins"]) == 1 for d in leaves)          # the side face is the edge thickness (1.96) less two rails
    starts = sorted(d["poly"].bounds[0] for d in leaves)
    assert np.allclose(np.diff(starts), a.leaf_pitch * a.leaf_length("side+"))          # evenly pitched
    assert len(a.motif(outer)) == 1                                                       # spine, leaves and hooks united
    assert artwork.leaf_polygon(1.0, 0.5).bounds == pytest.approx((0.0, -0.25, 1.0, 0.25), abs=1e-6)


def test_layers_are_disjoint_watertight_bodies_wrapped_onto_the_band():
    a = seraphine()
    cuts, relief = a.cutters_mesh(), a.relief_mesh()
    assert cuts.body_count == 6 and relief.body_count == a.relief_count == 30
    for m in cuts.split(only_watertight=False) + relief.split(only_watertight=False):
        assert m.is_watertight and m.volume > 0
    b = a.band
    r = np.hypot(relief.vertices[:, 0], relief.vertices[:, 1])
    # the outer vine stands from the channel floor (less its plug) to below the face; the side leaves inside the band's width
    outer = relief.split(only_watertight=False)[0]
    ro = np.hypot(outer.vertices[:, 0], outer.vertices[:, 1])
    assert ro.min() == pytest.approx(b.outer_radius_mm - a.channel_mm - artwork.PLUG_MM, abs=1e-3)
    assert ro.max() == pytest.approx(b.outer_radius_mm - a.below, abs=1e-3)
    assert np.abs(relief.vertices[:, 2]).max() <= b.width_mm / 2 - a.below + 1e-6
    th = np.degrees(np.arctan2(cuts.vertices[:, 1], cuts.vertices[:, 0]))
    assert 24.9 < np.abs(th).min() and np.abs(th).max() < 120.1                        # panels from 25° to 120°, both sides
    d = a.design_mesh()
    assert d.is_watertight and d.body_count == 1 and d.volume < a.shank.design_volume_mm3()


def test_validation_names_what_does_not_fit():
    assert any("touch along an edge" in x for x in seraphine(channel_mm=0.35, rail_mm=0.35).validate())
    assert any("at least 0.3 to cast" in x for x in seraphine(rail_mm=0.25).validate())
    assert any("below the face" in x for x in seraphine(relief_mm=0.3).validate())
    thin = band.BandSpec(size=6, width_mm=1.6, thickness_mm=2.0, profile="flat", mesh_tolerance_mm=0.05)
    assert any("between the side channels" in x for x in
               artwork.ArtworkSpec(shank.ShankSpec(thin), artwork.seraphine_panels(), channel_mm=0.6, rail_mm=0.7, relief_mm=0.5).validate())
    tapered = shank.ShankSpec(flat(), width_bottom_mm=2.0)
    assert any("plain band" in x for x in artwork.ArtworkSpec(tapered, artwork.seraphine_panels()).validate())
    assert artwork.ArtworkSpec(shank.ShankSpec(flat()), []).validate() == ["no panels"]


def test_recipe_builds_on_the_fake_notebook(tmp_path):
    from .fake_notebook import FakeNotebook
    from .test_notebook_api import load_recipe
    mod = load_recipe("ring_artwork")
    params = mod.prepare({}, tmp_path)
    params.update({"save_to": str(tmp_path / "a.ntop"), "recipe_to": str(tmp_path / "a.json"), "test_output": str(tmp_path / "a.stl")})
    nb = FakeNotebook()
    res = mod.build(nb, params)
    b = res["blocks"]
    assert nb.inputs == mod.INPUT_ORDER and res["warnings"] == []
    assert list(catalog.load("ring_artwork").inputs) == mod.INPUT_ORDER
    assert nb.blocks[b["Panel Cuts Mesh"]]["wired"]["Path"][0] == b["Cut Path"]
    assert nb.blocks[b["Relief Mesh"]]["wired"]["Path"][0] == b["Relief Path"]
    assert nb.blocks[b["Carved"]]["wired"]["Primary Body"][0] == b["Shank Body"]            # the opened band, cut ...
    assert nb.blocks[b["Carved"]]["lists"]["Subtraction Bodies"] == [b["Panel Cuts"]]
    assert nb.blocks[b["Ring"]]["lists"]["Bodies"] == [b["Carved"], b["Relief"]]            # ... then the relief added


def _build(out_dir, tmp_path, spec):
    nb = tmp_path / "ring_artwork.ntop"
    nb.write_bytes(b"fake")
    return artwork.build(spec, out_dir, notebook=nb)


def test_artwork_band_end_to_end(fake_ntopcl, tmp_path, out_dir):
    res = _build(out_dir, tmp_path, seraphine())
    assert res.ok, res.text()
    names = {c.name for c in res.gate.checks}
    assert {"channel floors", "relief", "rails", "section shape", "design volume", "wall thickness"} <= names
    assert (res.run_dir / f"{res.spec.stem}.relief.stl").exists()


@pytest.mark.parametrize("shape,caught", [("nocut", {"channel floors", "design volume"}), ("norelief", {"relief"})])   # 1 % of volume: the relief check is what catches it
def test_the_gate_catches_a_lost_layer(shape, caught, fake_ntopcl, tmp_path, out_dir, monkeypatch):
    monkeypatch.setenv("FAKE_NTOPCL_SHAPE", shape)
    res = _build(out_dir, tmp_path, artwork.ArtworkSpec(shank.ShankSpec(flat()), artwork.seraphine_panels(25.0, 60.0)))
    failed = {c.name for c in res.gate.checks if not c.ok}
    assert not res.ok and caught <= failed


def test_cli_artwork_dry_run(capsys):
    from ntopjewel import cli
    assert cli.main(["artwork", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "vine scroll" in out and "7 leaves" in out and "Relief Path" in out
    assert cli.main(["artwork", "--rail", "0.2", "--dry-run"]) == 1


@pytest.mark.parametrize("face", artwork.FACES)
@pytest.mark.parametrize("motif", artwork.MOTIFS)
def test_every_layer_survives_the_stl_round_trip_without_crossing_itself(face, motif, tmp_path):
    """2026-11-03, the real run: nTop read the first cutter layer as self-intersecting (trimesh's
    subdivide_to_size left T-junctions that the wrap bent into piercings) and left 0.013 mm needles
    standing on the side faces; earcut's sliver caps folded under the wrap (96 pairs in the leaves).
    Now lofted cutters, outlines densified in 2-D and caps from a constrained Delaunay: nothing
    crosses, on any face, for any motif, as written (float32) and read back."""
    import trimesh
    from ntopjewel import geom
    a = artwork.ArtworkSpec(shank.ShankSpec(flat()), [artwork.Panel(face, motif, 25.0, 120.0)])
    cut, relief = a.write_layers(tmp_path, "t")                                 # refuses a dirty layer itself
    for path in (cut, relief):
        back = trimesh.load(path, force="mesh")
        assert back.is_volume and len(geom.intersecting_faces(back, cell_mm=0.3)) == 0


def test_the_constrained_triangulation_keeps_every_boundary_edge_and_no_slivers():
    import numpy as np
    from shapely.geometry import Point
    from shapely.ops import unary_union
    # a leaf with a notch and a hole: the shapes a vine makes
    poly = unary_union([artwork.leaf_polygon(1.0, 0.5), Point(0.9, 0.0).buffer(0.3)]).difference(Point(0.4, 0.0).buffer(0.08))
    pts, tri, rings = artwork.quality_triangulate(poly)
    assert len(rings) == 2 and len(tri) > 30
    e1, e2 = pts[tri[:, 1]] - pts[tri[:, 0]], pts[tri[:, 2]] - pts[tri[:, 0]]
    area = 0.5 * (e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0])
    assert (area > 0).all()                                                      # all counter-clockwise, none flat
    longest = np.max([np.linalg.norm(pts[tri[:, (i + 1) % 3]] - pts[tri[:, i]], axis=1) for i in range(3)], axis=0)
    assert (2 * area / longest).min() > 0.01                                     # no sliver under 10 µm tall
    assert abs(area.sum() - artwork.densified(poly).area) < 1e-6                 # the triangles tile the polygon exactly


def test_tilted_leaves_on_a_serpentine_stem(fake_ntopcl, tmp_path, out_dir):
    """Each leaf turned ±7.5° in turn about its base and a stem half the relief high threaded through
    the row: the stem's pieces plug into the leaves (and into the volute on a scroll-leaves face), every
    panel copy's relief unites into one clean body, the gate's relief probes keep off the step, and the
    ring passes its gate on the simulated nTop."""
    a = seraphine(leaf_tilt_deg=7.5, leaf_stem=0.5)
    assert a.validate() == []
    side = a.panels[1]
    dicts = a.motif(side)
    leaves = [d for d in dicts if d["h_frac"] >= 1.0]
    stems = [d for d in dicts if d["h_frac"] < 1.0]
    assert len(leaves) == 7 and len(stems) >= 5 and all(d["h_frac"] == 0.5 for d in stems)
    slopes = []
    for d in leaves[1:]:                                                     # the volute has no vein; the leaves' veins follow the tilt
        (p, q, _w) = d["veins"][0]
        slopes.append((q[1] - p[1]) / (q[0] - p[0]))
    assert all(abs(abs(s) - np.tan(np.radians(7.5))) < 0.02 for s in slopes)   # turned by 7.5° ...
    assert all(s1 * s2 < 0 for s1, s2 in zip(slopes, slopes[1:]))             # ... alternately
    for d in stems:                                                          # every piece reaches into what it joins
        assert sum(d["poly"].intersection(q["poly"]).area > 1e-4 for q in leaves) >= 2
    plain = seraphine()
    assert a.motif(side)[1]["poly"].bounds[3] - a.motif(side)[1]["poly"].bounds[1] < \
        plain.motif(side)[1]["poly"].bounds[3] - plain.motif(side)[1]["poly"].bounds[1]   # the leaves narrowed for the tilt and the stem
    relief = a.relief_mesh()
    assert relief.body_count == 6                                            # one united body per panel copy
    for m in relief.split(only_watertight=False):
        assert m.is_watertight and m.volume > 0
    cut, rel = a.write_layers(tmp_path, "t")                                 # read back: nothing crosses
    assert a.spec_id != plain.spec_id and plain.spec_id == seraphine(leaf_tilt_deg=0.0, leaf_stem=0.0).spec_id   # the built design keeps its id
    o, d, lim, kinds = a.probes(side, 1.0)
    assert (kinds == "relief").sum() > 20 and (kinds == "floor").sum() > 50
    res = _build(out_dir, tmp_path, a)
    assert res.ok, res.text()
    assert any("at least 0.1 to cast" in x for x in seraphine(leaf_stem=0.3).validate())
    assert any("at most" in x for x in seraphine(leaf_tilt_deg=20.0).validate())
    from ntopjewel import cli
    assert cli.main(["artwork", "--sides", "scroll-leaves", "--leaf-tilt", "7.5", "--leaf-stem", "0.5", "--dry-run"]) == 0
    # a slender stem (Mark's half-width ask, 2026-11-04): the tables' relief_line floor, and the gate probes it along its centreline
    thin = seraphine(leaf_tilt_deg=7.5, leaf_stem=0.5, stem_width_mm=0.15)
    assert thin.validate() == [] and thin.spec_id != a.spec_id
    assert any("relief_line" in x for x in seraphine(leaf_stem=0.5, stem_width_mm=0.12).validate())
    stems = [d for d in thin.motif(side) if d["h_frac"] < 1.0]
    assert all(d["poly"].bounds[3] - d["poly"].bounds[1] < 0.8 for d in stems) and all(not d["line"].is_empty for d in stems)
    o, d, lim, kinds = thin.probes(side, 1.0)
    from shapely.geometry import Point
    from shapely.ops import unary_union
    centre = unary_union([d_["line"] for d_ in stems])
    th = np.degrees(np.arctan2(o[:, 1], o[:, 0]))                           # back to the panel frame (a side face: v is the radius)
    u, v = (th - side.start_deg) / 360.0 * thin.L, np.hypot(o[:, 0], o[:, 1]) - thin.side_mid_radius
    on_stem = [i for i in np.where(kinds == "relief")[0] if centre.distance(Point(u[i], v[i])) < 0.01]
    assert len(on_stem) >= 12                                                # a row of probes along the stem where it shows between the leaves
    assert thin.relief_mesh().body_count == 6
    res = _build(out_dir, tmp_path, thin)
    assert res.ok, res.text()


def test_the_built_seraphine_designs_keep_their_geometry():
    """The two Seraphine designs that PASSED in nTop (3-4 Nov) are pinned: the same numbers, the same
    relief, the same ids. The outer vine's leaves carry no veins (its 0.09 mm slits never fit the
    clipped leaves); the day they did, nTop could not resolve them (0.102 on the relief probes)."""
    for sides, outer, vol, sid in (("scroll-leaves", "scroll", 15.5775, "c38ad852"), ("leaves", "scroll", 16.1836, "93cfdf76")):
        a = artwork.ArtworkSpec(shank.ShankSpec(flat()), artwork.seraphine_panels(25.0, 120.0, outer=outer, sides=sides))
        m = a.relief_mesh()
        assert m.body_count == 30 and m.volume == pytest.approx(vol, abs=2e-4) and a.spec_id == sid
        assert sum(len(d["veins"]) for d in a.motif(a.panels[0])) == 0
        assert all(len(d["veins"]) == 1 for d in a.motif(a.panels[1]) if d["poly"].bounds[0] > 1.5)   # the row leaves keep theirs
    # the vein a narrowed leaf gets is the only one that stops short of the tip
    assert artwork.leaf_vein(1.7, 0.66)[1][0] == pytest.approx(0.82 * 1.7) and artwork.leaf_vein(1.7, 0.66, True)[1][0] < 0.72 * 1.7


def test_a_taper_below_the_panels(fake_ntopcl, tmp_path, out_dir):
    """The band tapers below the scrollwork (Mark, 2026-11-04): the ease may begin only past the last
    panel (the panels sit on the full section), the default taper start follows the panels, and the
    tapered ring passes its gate on the simulated nTop."""
    panels = artwork.seraphine_panels(25.0, 120.0, outer="scroll", sides="scroll-leaves")
    assert artwork.taper_start_deg(panels, None) == 121.0 and artwork.taper_start_deg([], None) == 60.0 and artwork.taper_start_deg(panels, 130.0) == 130.0
    early = artwork.ArtworkSpec(shank.ShankSpec(flat(), width_bottom_mm=2.0, thickness_bottom_mm=1.5), panels)
    assert any("inside the panels" in x and "at least 121" in x for x in early.validate())
    a = artwork.ArtworkSpec(shank.ShankSpec(flat(), width_bottom_mm=2.0, thickness_bottom_mm=1.5, taper_from_deg=121.0), panels,
                            leaf_tilt_deg=7.5, leaf_stem=0.5, stem_width_mm=0.15)
    assert a.validate() == []
    plain = artwork.ArtworkSpec(shank.ShankSpec(flat()), panels, leaf_tilt_deg=7.5, leaf_stem=0.5, stem_width_mm=0.15)
    assert a.design_volume_mm3() < plain.design_volume_mm3() - 20 and a.spec_id != plain.spec_id and "w2.8-2_t2-1.5" in a.stem
    assert a.relief_mesh().volume == pytest.approx(plain.relief_mesh().volume, abs=1e-6)      # the panels are untouched
    assert "tapered below the panels" in a.describe()
    res = _build(out_dir, tmp_path, a)
    assert res.ok, res.text()
    from ntopjewel import cli
    assert cli.main(["artwork", "--sides", "scroll-leaves", "--outer", "scroll", "--width-bottom", "2", "--thickness-bottom", "1.5", "--dry-run"]) == 0
    assert any("split, double, rope or knot" in x for x in
               artwork.ArtworkSpec(shank.ShankSpec(flat(), split_mm=1.0), panels).validate())
