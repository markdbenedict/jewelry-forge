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
