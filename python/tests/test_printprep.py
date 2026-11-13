"""The print preparation (printprep, raster): the column model, the slicing's islands, overhangs and suction
cups on shapes whose answers are known, the surface model's classes, and whole jobs - a band oriented, supported
on plain metal only and stood on a raft as one body, through the API and the CLI (2026-11-07)."""
from __future__ import annotations

import importlib
import json
import math

import numpy as np
import pytest
import trimesh

from ntopjewel import band, cli, gate, geom, printprep, raster, summary, tables


def _union(*meshes):
    return trimesh.boolean.union(list(meshes), engine="manifold")


def _all(part, cls=printprep.POLISH):
    return np.full(len(part.faces), cls, np.int8)


# ---------------------------------------------------------------- the column model
def test_columns_measure_a_box_and_a_band_exactly():
    box = trimesh.creation.box((2.0, 3.0, 1.5))
    cols = raster.Columns(box.triangles, box.face_normals[:, 2] < 0, 0.1)
    pix, zin, zout, _, _ = cols.intervals()
    assert float(np.sum(zout - zin)) * 0.01 == pytest.approx(9.0, rel=1e-3)        # no pixel centre on a shared edge
    assert (cols.w_after >= 0).all() and (cols.w_after <= 1).all()
    centre = cols.pixel_at(np.array([0.0]), np.array([0.0]))
    assert cols.inside(centre, 0.0)[0] and not cols.inside(centre, 0.9)[0] and not cols.inside(centre, -0.9)[0]
    assert not cols.inside(np.array([-1]), 0.0)[0]                                    # off the grid: outside
    ring = geom.band_mesh(band.BandSpec(size=6).notebook_inputs(""))
    for b in ([1, 0, 0], [0, 0, 1], [0.6, 0.0, 0.8]):
        tri, R, _ = printprep.printer_triangles(ring, np.array(b, float))
        c = raster.Columns(tri, (ring.face_normals @ R[2]) < 0, 0.05)
        _, zi, zo, _, _ = c.intervals()
        assert float(np.sum(zo - zi)) * 0.0025 == pytest.approx(ring.volume, rel=2e-3), b


def test_layers_sweep_and_render_draw_what_is_there():
    box = trimesh.creation.box((2.0, 2.0, 1.0))
    box.apply_translation([0, 0, 0.5])
    cols = raster.Columns(box.triangles, box.face_normals[:, 2] < 0, 0.1)
    areas = [occ.sum() * 0.01 for _, occ in raster.layers(cols, 0.1)]
    assert len(areas) == 10 and all(a == pytest.approx(4.0, rel=0.05) for a in areas)
    img, proj = raster.render([box], [(200, 0, 0)], view=(0, 0, -1), size_px=100)
    assert img.shape[2] == 3 and (img[..., 0] > img[..., 1] + 50).mean() > 0.5        # mostly the red box
    col, row = raster.project(np.array([[0.0, 0.0, 1.0]]), proj)[0]
    assert 0 <= col < img.shape[1] and 0 <= row < img.shape[0]


# ---------------------------------------------------------------- slicing: overhangs, islands, suction
S = printprep.prep_settings()


def test_a_t_overhangs_and_its_foot_is_the_first_island():
    pillar = trimesh.creation.box((1.0, 1.0, 3.0))
    pillar.apply_translation([0, 0, 1.5])
    cap = trimesh.creation.box((4.0, 4.0, 0.5))
    cap.apply_translation([0, 0, 3.25])
    t = _union(pillar, cap)
    an = printprep.analyse(t, _all(t), [0, 0, 1], S, 0.1, 0.1)
    P = an.point(an.u)
    under = np.abs(P[:, 2] - 3.0) < 0.05
    assert under.sum() * 0.01 == pytest.approx(15.0, abs=0.8)                     # the cap's underside past the pillar
    assert (np.abs(P[~under, 2]) < 0.05).all()                                      # ... and the pillar's foot, nothing else
    assert len(an.islands) == 1 and an.islands[0]["layer"] == 0                      # the foot: the part's first layer
    assert an.cup_max_mm2 == 0 and an.layer_max_mm2 == pytest.approx(16.0, rel=0.05) and an.height_mm == pytest.approx(3.5)
    flip = printprep.analyse(t, _all(t), [0, 0, -1], S, 0.1, 0.1)                   # cap first: it prints flat on its supports
    assert len(flip.islands) == 1 and flip.islands[0]["px"] * 0.01 == pytest.approx(16.0, rel=0.1)


def test_a_part_whose_foot_is_a_feature_starts_on_the_film_and_that_outweighs_everything():
    """8 Nov 2026: the court band's bottom bead row (no contact allowed on beads) led its first contact by 12 layers
    and the ring stayed on the film while the supports printed. A T whose foot is a feature: tip down, the first
    contact is the cap's underside 3 mm up - the start term dwarfs the rest; cap down it starts on a held island."""
    pillar = trimesh.creation.box((1.0, 1.0, 3.0))
    pillar.apply_translation([0, 0, 1.5])
    cap = trimesh.creation.box((4.0, 4.0, 0.5))
    cap.apply_translation([0, 0, 3.25])
    t = _union(pillar, cap)
    cls = _all(t)
    cls[t.triangles_center[:, 2] < 0.4] = printprep.FEATURE                          # a knob on the pillar's end
    down = printprep.analyse(t, cls, [0, 0, 1], S, 0.1, 0.1)
    assert len(down.feature_islands) == 1 and down.z_first_mm == pytest.approx(3.0, abs=0.06)
    assert down.start_islands == down.feature_islands and down.terms["start"] >= printprep.W_START * 28
    assert down.terms["start"] > 10 * sum(v for k, v in down.terms.items() if k != "start")
    assert "STARTS ON THE FILM" in down.line() and "first contact 3.0" in down.line()
    up = printprep.analyse(t, cls, [0, 0, -1], S, 0.1, 0.1)                           # the cap first: held from its first layer
    assert up.z_first_mm == pytest.approx(0.0, abs=1e-6) and up.terms["start"] == 0 and not up.start_islands
    assert printprep.start_gap_layers(math.inf, S) == 100.0 and printprep.start_gap_layers(0.05, S) == 0.0
    assert printprep.start_gap_layers(0.6, S) == pytest.approx((0.6 - S["print_start_gap_mm"]) / S["print_layer_mm"])


def test_a_cone_tip_down_is_an_island_and_a_steep_one_needs_nothing_else():
    for half_angle, flat in ((60.0, True), (25.0, False)):
        h = 2.0
        cone = trimesh.creation.cone(radius=h * math.tan(math.radians(half_angle)), height=h, sections=64)
        cone.apply_transform(trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0]))   # apex down
        an = printprep.analyse(cone, _all(cone), [0, 0, 1], S, 0.05, 0.05)
        assert len(an.islands) == 1                                                   # the apex
        area = len(an.u) * 0.0025
        if flat:                                                                      # 30° from level: all of it overhangs
            assert area == pytest.approx(math.pi * (h * math.tan(math.radians(half_angle))) ** 2, rel=0.1)
        else:                                                                         # 65°: only round the apex
            assert area < 0.1


def test_a_cup_open_to_the_vat_is_a_suction_cup_and_open_to_the_plate_is_not():
    outer = trimesh.creation.cylinder(radius=3.0, height=3.0, sections=64)
    hole = trimesh.creation.cylinder(radius=2.0, height=3.0, sections=64)
    hole.apply_translation([0, 0, 1.0])                                               # a floor 1 mm thick, open at the top
    cup = trimesh.boolean.difference([outer, hole], engine="manifold")
    up = printprep.analyse(cup, _all(cup), [0, 0, 1], S, 0.1, 0.1)
    assert up.cup_max_mm2 == pytest.approx(math.pi * 4.0, rel=0.08) and up.cup_at is not None
    down = printprep.analyse(cup, _all(cup), [0, 0, -1], S, 0.1, 0.1)
    assert down.cup_max_mm2 == 0
    assert up.terms["suction"] > 0 and up.score > down.score - down.terms["contacts"] - 1      # suction costs


def test_unsupportable_overhang_and_islands_are_feature_trouble_not_contacts():
    pillar = trimesh.creation.box((1.0, 1.0, 3.0))
    pillar.apply_translation([0, 0, 1.5])
    cap = trimesh.creation.box((4.0, 4.0, 0.5))
    cap.apply_translation([0, 0, 3.25])
    t = _union(pillar, cap)
    feat = _all(t, printprep.FEATURE)
    an = printprep.analyse(t, feat, [0, 0, 1], S, 0.1, 0.1)
    assert len(an.feature_islands) == 1 and an.contacts_est == {"polish": 0, "bore": 0}
    assert len(an.feature_uncovered) * 0.01 == pytest.approx(16.0, abs=1.0)
    assert an.terms["feature islands"] == printprep.W_FEATURE_ISLAND


# ---------------------------------------------------------------- the surface model
def test_a_plain_band_is_polished_faces_and_bore_and_avoid_keeps_the_bore_clear():
    spec = band.BandSpec(size=6, profile="court")
    ring = geom.band_mesh(spec.notebook_inputs(""))
    model = printprep.surface_model(spec)
    cls = model.classify(ring)
    assert set(np.unique(cls)) == {printprep.POLISH, printprep.BORE}
    c, n = ring.triangles_center, ring.face_normals
    nr = (n[:, 0] * c[:, 0] + n[:, 1] * c[:, 1]) / np.hypot(c[:, 0], c[:, 1])
    assert (cls[nr < -0.6] == printprep.BORE).all() and (cls[nr > 0.2] == printprep.POLISH).all()
    clear = model.classify(ring, bore="avoid")
    assert (clear[cls == printprep.BORE] == printprep.CLEAR).all() and not (clear == printprep.BORE).any()


def test_a_bump_is_a_feature_and_keeps_contacts_half_a_millimetre_off():
    spec = band.BandSpec(size=6, profile="flat", width_mm=4.0)
    ring = geom.band_mesh(spec.notebook_inputs(""), chamfer_mm=0.0)
    bump = trimesh.creation.icosphere(subdivisions=3, radius=0.6)
    bump.apply_translation([spec.outer_radius_mm + 0.3, 0.0, 0.0])
    part = _union(ring, bump)
    cls = printprep.surface_model(spec).classify(part, keepoff_mm=0.5)
    c = part.triangles_center
    d_bump = np.linalg.norm(c - [spec.outer_radius_mm + 0.3, 0, 0], axis=1) - 0.6
    assert (cls[d_bump > 0.05] != printprep.FEATURE).sum() > 0.9 * (d_bump > 0.9).sum()
    on_bump = np.linalg.norm(c - [spec.outer_radius_mm + 0.3, 0, 0], axis=1) < 0.61
    outside = on_bump & (np.hypot(c[:, 0], c[:, 1]) > spec.outer_radius_mm + 0.05)
    assert (cls[outside] == printprep.FEATURE).all()
    near = (cls != printprep.FEATURE) & (np.linalg.norm(c - [spec.outer_radius_mm, 0, 0], axis=1) < 0.95)
    assert not near.any()                                                             # no plain face within the keep-off


def test_family_zones_mark_features_that_lie_on_the_plain_section():
    from ntopjewel import features, texture, fieldtex
    ring = features.RingSpec(band.BandSpec(size=6), text="AB", engrave_side="inside")
    m = printprep.surface_model(ring)
    name, f = m.zones[0]
    r = np.array([8.25, 8.25, 9.7])
    th = np.array([0.0, 180.0, 0.0])
    z = np.zeros(3)
    assert name == "engraving" and list(f(r, th, z, np.array([-1.0, -1.0, 1.0]))) == [True, False, False]
    ham = texture.HammeredSpec(band.BandSpec(size=6, thickness_mm=1.6))
    name, f = printprep.surface_model(ham).zones[0]
    assert list(f(np.array([9.8, 9.8, 8.3]), np.zeros(3), np.array([0.0, 1.98, 0.0]), np.array([1.0, 1.0, -1.0]))) == [True, False, False]
    lat = fieldtex.make_spec("frost", band.BandSpec(size=6, thickness_mm=1.6))
    assert "zone" in printprep.surface_model(lat).zones[0][0]
    with pytest.raises(ValueError, match="no print preparation"):
        printprep.surface_model(object())


# ---------------------------------------------------------------- orientation
def test_orientation_helpers_agree():
    for tilt, head in ((0, 90), (45, 45), (30, 20), (90, 0), (10, -60)):
        b = printprep.direction_for(tilt, head, 0.0)
        t, h = printprep.tilt_and_head(b, 0.0)
        assert t == pytest.approx(tilt, abs=1e-6) and h == pytest.approx(head, abs=1e-6)
        R = printprep.frame(b)
        assert np.allclose(R @ b, [0, 0, 1]) and np.allclose(R @ R.T, np.eye(3))
    assert printprep.describe([1, 0, 0], 0.0) == "standing on edge (axis level), head 90° up"
    assert printprep.describe([0, 0, 1], None) == "lying flat (axis upright)"
    with pytest.raises(ValueError, match="add up to at most 90"):
        printprep.direction_for(60, 60, 0.0)
    assert cli._parse_orient("2") == 2 and cli._parse_orient("45,45") == (45.0, 45.0) and cli._parse_orient(None) is None


# ---------------------------------------------------------------- whole jobs
def _band_stl(tmp_path, spec):
    stl = tmp_path / f"{spec.stem}.stl"
    geom.band_mesh(spec.notebook_inputs("")).export(str(stl))
    return stl


def test_a_band_is_oriented_supported_on_plain_metal_and_stood_on_a_raft(tmp_path):
    spec = band.BandSpec(size=6, profile="court")
    res = printprep.prepare(_band_stl(tmp_path, spec), spec, tmp_path / "prep")
    assert res.ok, res.text()
    assert res.ranked and res.ranked[0].score <= res.ranked[-1].score and res.chosen.pixel == printprep.FINAL_PIXEL_MM
    assert res.supports and all(printprep.SUPPORTABLE[sp.cls] for sp in res.supports)
    out = trimesh.load(res.files["print file"], force="mesh")
    assert out.is_watertight and len(out.split(only_watertight=False)) == 1
    lift = S["support_lift_mm"] + S["raft_thickness_mm"]
    assert out.bounds[0][2] == pytest.approx(0.0, abs=1e-4)
    assert out.volume > geom.band_mesh(spec.notebook_inputs("")).volume
    doc = json.loads(res.files["report"].read_text(encoding="utf-8"))
    assert doc["status"] == "passed" and len(doc["supports"]) == len(res.supports) and doc["candidates"]
    assert all(s["contact"][2] >= lift - 1e-6 for s in doc["supports"])                     # every contact on the part, above the lift
    assert all(s["on"] in ("polished face", "bore") for s in doc["supports"])
    assert res.files["preview"].exists() and res.files["preview"].stat().st_size > 10000
    assert "supports" in res.headline() and res.status == gate.PASSED


def test_avoid_keeps_supports_out_of_the_bore_and_metal_scales_the_print_file(tmp_path):
    spec = band.BandSpec(size=6, profile="court")
    res = printprep.prepare(_band_stl(tmp_path, spec), spec, tmp_path / "prep", bore="avoid", metal="sterling")
    assert res.ok, res.text()
    assert all(sp.cls == printprep.POLISH and sp.foot_cls in (None, printprep.POLISH) for sp in res.supports)
    assert res.files["print file"].name == f"{spec.stem}.supported_sterling.stl"
    factor, _ = tables.print_scale("sterling")
    assert res.scale == pytest.approx(factor)
    doc = json.loads(res.files["report"].read_text(encoding="utf-8"))
    assert doc["metal"] == "sterling" and doc["surface_mm2"]["kept clear"] > 0 and doc["surface_mm2"]["bore"] == 0


def test_a_forced_orientation_is_kept_and_a_standing_band_holds_its_bore_on_struts(tmp_path):
    spec = band.BandSpec(size=6, profile="flat")
    stl = _band_stl(tmp_path, spec)
    flat = printprep.prepare(stl, spec, tmp_path / "flat", orient=(90.0, 0.0), picture=False)
    assert flat.forced and printprep.tilt_and_head(flat.chosen.b, None)[0] == pytest.approx(90.0)
    assert "preview" not in flat.files
    stand = printprep.prepare(stl, spec, tmp_path / "stand", orient=(0.0, 90.0), picture=False)
    assert stand.ok, stand.text()
    struts = [sp for sp in stand.supports if sp.kind == "part"]
    assert struts and all(sp.cls == printprep.BORE and sp.foot_cls == printprep.BORE for sp in struts)  # ceiling to floor
    assert all(sp.length >= 2 * S["support_tip_length_mm"] + printprep.STRUT_EXTRA_MM for sp in struts)
    by_rank = printprep.prepare(stl, spec, tmp_path / "rank", orient=2, picture=False)
    assert np.allclose(by_rank.chosen.b, by_rank.ranked[1].b)
    with pytest.raises(ValueError, match="ranked"):
        printprep.prepare(stl, spec, tmp_path / "bad", orient=99, picture=False)


def test_a_beaded_band_stands_on_its_dome_and_a_leaning_one_that_starts_on_its_beads_is_refused(tmp_path):
    """The court band of 8 Nov 2026 in miniature: beads (a rim) on both edges take no contact, so leaning, the ring's
    first half millimetre is bead row on the film and the search must not choose it; standing on edge its dome leads
    and the first contact is on it within the allowed gap. Forced to lean, the preparation fails and says why."""
    spec = band.BandSpec(size=6, profile="court")
    ring = geom.band_mesh(spec.notebook_inputs(""))
    rims = []
    for z in (-spec.width_mm / 2, spec.width_mm / 2):
        t = trimesh.creation.torus(major_radius=9.05, minor_radius=0.25, major_sections=240, minor_sections=20)
        t.apply_translation([0, 0, z])
        rims.append(t)
    part = _union(ring, *rims)
    stl = tmp_path / f"{spec.stem}.stl"
    part.export(str(stl))
    cls = printprep.surface_model(spec).classify(part, bore="avoid")
    assert (cls == printprep.FEATURE).sum() > 0.2 * len(cls)                        # the rims and the keep-off round them
    res = printprep.prepare(stl, spec, tmp_path / "search", bore="avoid", picture=False)
    assert res.ok, res.text()
    tilt, _ = printprep.tilt_and_head(res.chosen.b, None)
    assert tilt < 10 and res.chosen.z_first_mm <= S["print_start_gap_mm"]           # standing on edge, the dome first
    assert res.chosen.terms["start"] == 0 and res.ranked[0].terms["start"] == 0
    assert any(a.terms["start"] > 0 for a in res.ranked)                              # the leaning ones were seen and shunned
    start = [c for c in res.checks if c.name == "starts on its supports"][0]
    assert start.status == gate.PASSED and "first contact 0.0" in start.detail
    held = [c for c in res.checks if c.name == "layers held"][0]
    assert held.status == gate.PASSED, held.detail
    worst, _ = printprep.layers_hold(res.chosen, res.supports, S)
    assert worst <= S["support_hold_area_mm2"] + 1e-6
    lean = printprep.prepare(stl, spec, tmp_path / "lean", bore="avoid", orient=(37.0, 53.0), picture=False)
    assert lean.status == gate.FAILED and lean.chosen.z_first_mm > S["print_start_gap_mm"]
    start = [c for c in lean.checks if c.name == "starts on its supports"][0]
    assert start.status == gate.FAILED and "prints on nothing but the film" in start.detail and lean.chosen.start_islands
    assert "STARTS ON THE FILM" in lean.text()
    assert summary.prep_verdict(lean).startswith("==> FAILED") and "starts on its supports" in summary.prep_verdict(lean)
    doc = json.loads(lean.files["report"].read_text(encoding="utf-8"))
    assert doc["status"] == "failed" and doc["unsupported"]["start_islands"] and doc["chosen"]["terms"]["start"] > 0


def test_a_wide_spacing_still_holds_the_lowest_layers(tmp_path):
    """A ring standing on edge at a wide spacing would hang its first half millimetre on the one tip at its lowest
    point: hold_layers adds contacts under the lowest layers until no layer has more than support_hold_area_mm2 per
    tip engaged below it, and leaves the spacing alone above."""
    spec = band.BandSpec(size=6, profile="flat")
    stl = _band_stl(tmp_path, spec)
    res = printprep.prepare(stl, spec, tmp_path / "wide", orient=(0.0, 90.0), settings={"support_spacing_mm": 4.0}, picture=False)
    assert res.ok, res.text()
    hold = [sp for sp in res.supports if sp.hold]
    assert hold and max(sp.z_top for sp in hold) < 2.0                                 # added low down only
    worst, _ = printprep.layers_hold(res.chosen, res.supports, res.settings)
    assert worst <= S["support_hold_area_mm2"] + 1e-6
    bare = [sp for sp in res.supports if not sp.hold]
    without, _ = printprep.layers_hold(res.chosen, bare, res.settings)
    assert without > S["support_hold_area_mm2"]                                       # the spacing alone left a layer hanging
    assert "added under the lowest layers" in res.headline()
    doc = json.loads(res.files["report"].read_text(encoding="utf-8"))
    assert sum(s["hold"] for s in doc["supports"]) == len(hold)


def test_cure_through_thins_only_what_faces_the_vat_and_keeps_each_faces_class():
    """13 Nov 2026 (Mark's Supercast prints: "a thickened downside"): the file is the part less what the resin cures
    beyond each layer - a box loses exactly the depth off its underside, nothing off its top or its walls."""
    box = trimesh.creation.box((4.0, 3.0, 2.0))
    cls = _all(box)
    cls[box.triangles_center[:, 2] < -0.99] = printprep.BORE                         # its underside, to follow
    out, ocls, removed, bodies = printprep.compensate_cure_through(box, cls, [0, 0, 1], 0.25)
    assert bodies == 1 and out.is_watertight and removed == pytest.approx(4 * 3 * 0.25, rel=1e-4)
    assert out.bounds[0][2] == pytest.approx(-0.75, abs=1e-5) and out.bounds[1][2] == pytest.approx(1.0, abs=1e-5)
    assert np.allclose(out.bounds[:, :2], box.bounds[:, :2], atol=1e-5)
    low = out.triangles_center[:, 2] < -0.74
    assert low.any() and (ocls[low] == printprep.BORE).all() and (ocls[~low] == printprep.POLISH).all()
    with pytest.raises(ValueError, match="nothing is left"):
        printprep.compensate_cure_through(box, cls, [0, 0, 1], 2.5)
    plate = _union(box, trimesh.creation.box((1.0, 1.0, 0.2)).apply_translation([0, 0, -1.6]),
                   trimesh.creation.box((0.3, 0.3, 0.6)).apply_translation([0, 0, -1.25]))
    _, _, _, pieces = printprep.compensate_cure_through(plate, _all(plate), [1, 0, 0], 0.5)   # the 0.3 stalk is thinner than 0.5 along x
    assert pieces == 2


def test_the_prepared_file_is_compensated_and_its_tips_stay_apart(tmp_path):
    spec = band.BandSpec(size=6, profile="flat")
    stl = _band_stl(tmp_path, spec)
    plain = printprep.prepare(stl, spec, tmp_path / "plain", orient=(0.0, 90.0), settings={"support_spacing_mm": 4.0}, picture=False)
    res = printprep.prepare(stl, spec, tmp_path / "comp", orient=(0.0, 90.0), picture=False,
                            settings={"support_spacing_mm": 4.0, "print_cure_through_mm": 0.2})
    assert res.ok and plain.ok, res.text()
    names = [c.name for c in res.checks]
    assert "cure-through compensated" in names and "cure-through compensated" not in [c.name for c in plain.checks]
    comp = [c for c in res.checks if c.name == "cure-through compensated"][0]
    assert comp.status == gate.PASSED and "0.2 mm into the part" in comp.detail
    a, b = trimesh.load(str(plain.files["print file"]), force="mesh"), trimesh.load(str(res.files["print file"]), force="mesh")
    assert b.volume < a.volume - 1.0 and a.extents[2] - b.extents[2] == pytest.approx(0.2, abs=0.02)   # the underside moved up, the top where it was
    for r in (plain, res):                                                           # 13 Nov: no cluster under the lowest point
        spread = [c for c in r.checks if c.name == "contacts spread"][0]
        assert spread.status == gate.PASSED, spread.detail
        pts = np.array([(sp.x, sp.y, sp.z_top) for sp in r.supports if not sp.island])
        d = np.linalg.norm(pts[:, None] - pts[None], axis=2) + np.eye(len(pts)) * 99
        assert d.min() >= 0.9 * S["support_min_spacing_mm"]
    assert json.loads(res.files["report"].read_text(encoding="utf-8"))["settings"]["print_cure_through_mm"] == 0.2


# ---------------------------------------------------------------- the CLI
def test_band_prep_after_a_passed_build_and_into_the_delivery(fake_ntopcl, profile_notebook, out_dir, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("JEWELRY_DELIVER", str(tmp_path / "Jewelry"))
    spec = band.BandSpec(size=6, profile="court")
    code = cli.main(["band", "--size", "6", "--profile", "court", "--notebook", str(profile_notebook), "--out", str(out_dir),
                     "--deliver", "--prep"])
    text = capsys.readouterr().out
    assert code == 0, text
    last = text.strip().splitlines()[-1]
    assert last.startswith(f"==> PASSED  {spec.stem}") and "print file:" in last and "supports" in last
    folder = tmp_path / "Jewelry" / "Bands" / spec.stem
    assert (folder / f"{spec.stem}.supported.stl").exists() and (folder / f"{spec.stem}.prep.json").exists()
    man = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert man["prep"]["status"] == "passed" and man["prep"]["print_file"] == f"{spec.stem}.supported.stl" and man["prep"]["sha256"]
    run_stl = next((out_dir / spec.stem).glob(f"*/{spec.stem}.stl"))
    assert (run_stl.parent / f"{spec.stem}.supported.stl").exists()


def test_prep_stl_prepares_an_existing_part_of_the_design_only(fake_ntopcl, profile_notebook, out_dir, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("JEWELRY_DELIVER", str(tmp_path / "Jewelry"))
    monkeypatch.setenv("JEWELRY_OUT", str(out_dir))
    spec = band.BandSpec(size=6, profile="court")
    stl = _band_stl(tmp_path, spec)
    code = cli.main(["band", "--size", "7", "--profile", "court", "--prep-stl", str(stl)])
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert code == 2 and last.startswith("==> ERROR   prep") and "is not this design" in last
    code = cli.main(["band", "--size", "6", "--profile", "court", "--prep-stl", str(stl), "--bore", "avoid", "--deliver"])
    text = capsys.readouterr().out
    last = text.strip().splitlines()[-1]
    assert code == 0, text
    assert last.startswith(f"==> PASSED  {spec.stem}.supported") and "not delivered" in text      # no PASSED delivery to add to
    runs_ = summary.scan_runs(out_dir)
    assert any(r.family == "prep" and r.status == "passed" and r.stem == spec.stem for r in runs_)


FAMILIES = [
    (["band"], "BandSpec"),
    (["ring", "--milgrain", "--groove", "0.25", "--engrave", "AB"], "RingSpec"),
    (["shank", "--thickness", "1.6", "--width-bottom", "2.2", "--thickness-bottom", "1.2"], "ShankSpec"),
    (["shank", "--width", "4", "--thickness", "1.6", "--split", "1.6", "--split-span", "90"], "ShankSpec"),
    (["texture", "--thickness", "1.6"], "HammeredSpec"),
    (["texture", "--kind", "frost", "--thickness", "1.6"], "NoiseSpec"),
    (["lattice"], "GyroidSpec"),
    (["pave"], "PaveSpec"),
    (["artwork"], "ArtworkSpec"),
    (["multistone", "--shape", "cushion", "--length", "7", "--stone-width", "6", "--side-shape", "pear", "--side-length", "6",
      "--side-width", "4", "--engrave", "AB"], "MultiStoneSpec"),
    (["solitaire", "--engrave", "AB"], "SolitaireSpec"),
    (["solitaire", "--profile", "flat", "--width", "2.8", "--thickness", "2", "--prongs", "4", "--no-arches", "--sides",
      "scroll-leaves", "--outer", "scroll", "--shoulder-knot", "trinity", "--width-bottom", "2", "--thickness-bottom", "1.5"],
     "SolitaireSpec"),
]


@pytest.mark.parametrize("args,kind", FAMILIES, ids=[" ".join(a[:2]) for a, _ in FAMILIES])
def test_every_ring_command_takes_prep_stl_and_its_spec_has_a_surface_model(args, kind, tmp_path, out_dir, monkeypatch, capsys):
    """--prep-stl on every ring command: refused for a file of another design (naming the design the arguments
    describe), handed to printprep with the command's own spec otherwise - whose surface model classes a band."""
    monkeypatch.setenv("JEWELRY_OUT", str(out_dir))                  # short on Windows: a solitaire's stem is long
    other = tmp_path / "other.stl"
    other.write_bytes(b"solid x\nendsolid x\n")
    assert cli.main(args + ["--prep-stl", str(other)]) == 2
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert "is not this design" in line, line
    stem = line.split("these arguments describe ")[1].split(" ")[0]
    seen = {}
    # the module cli's lazy import will find: the notebook API driver's tests purge ntopjewel* from sys.modules (as the
    # driver does in nTop), so the one imported at the top of this file may no longer be it
    pp = importlib.import_module("ntopjewel.printprep")

    def stub(stl, spec, out_dir, **kw):
        seen["spec"], seen["kw"] = spec, kw
        model = pp.surface_model(spec)
        ring = geom.band_mesh(band.BandSpec(size=6).notebook_inputs(""))
        seen["classes"] = np.bincount(model.classify(ring, bore=kw["bore"]), minlength=4)
        raise ValueError("stub")
    monkeypatch.setattr(pp, "prepare", stub)
    mine = tmp_path / f"{stem}.stl"
    mine.write_bytes(b"solid x\nendsolid x\n")
    assert cli.main(args + ["--prep-stl", str(mine), "--bore", "avoid", "--orient", "45,45"]) == 2
    assert type(seen["spec"]).__name__ == kind and seen["spec"].stem == stem
    assert seen["kw"]["bore"] == "avoid" and seen["kw"]["orient"] == (45.0, 45.0)
    assert seen["classes"].sum() > 0 and seen["classes"][pp.BORE] == 0
