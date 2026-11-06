"""Lattice bands (2026-11-06): an open gyroid between a bore skin and the rims, held to Python's own model of the same
geometry - the lattice matched point by point, the sheets and the pores by rays, every void flood-filled from the
outer face (the trapped-resin check), the design volume."""
from __future__ import annotations

import json
import math

import numpy as np
import pytest

from ntopjewel import band, catalog, lattice, runs, tables


def flat_band(**kw):
    return band.BandSpec(**{"size": 6, "profile": "flat", "width_mm": 6.0, "thickness_mm": 3.3, "mesh_tolerance_mm": 0.2, **kw})


def spec(**kw):
    b = kw.pop("band", None) or flat_band()
    return lattice.GyroidSpec(b, **kw)


def test_the_gyroid_model_is_a_distance_and_the_wrap_is_periodic():
    cell, wall = 3.5, 0.6
    rng = np.random.default_rng(1)
    P = rng.uniform(-cell, 2 * cell, (20000, 3))
    g, gx, gy, gz = lattice.gyroid_field(P[:, 0], P[:, 1], P[:, 2], cell)
    n = np.sqrt(gx * gx + gy * gy + gz * gz)
    # points pushed wall / 2 along the normal from the surface lie on the sheet's faces (the Newton distance reads them)
    on = P - (g / n ** 2)[:, None] * np.column_stack([gx, gy, gz])
    for _ in range(6):                                                      # onto the surface
        g2, gx2, gy2, gz2 = lattice.gyroid_field(on[:, 0], on[:, 1], on[:, 2], cell)
        on -= (g2 / (gx2 ** 2 + gy2 ** 2 + gz2 ** 2))[:, None] * np.column_stack([gx2, gy2, gz2])
    g2, gx2, gy2, gz2 = lattice.gyroid_field(on[:, 0], on[:, 1], on[:, 2], cell)
    nrm = np.column_stack([gx2, gy2, gz2]) / np.sqrt(gx2 ** 2 + gy2 ** 2 + gz2 ** 2)[:, None]
    ok = np.abs(g2) < 1e-6
    face = on[ok] + nrm[ok] * wall / 2
    d = lattice.sheet_sdf(face[:, 0], face[:, 1], face[:, 2], cell, wall)
    assert np.abs(d).max() < 0.01                                           # within 1 % of the wall
    assert lattice.sheet_sdf(on[ok][:, 0], on[ok][:, 1], on[ok][:, 2], cell, wall).max() < -wall / 2 + 1e-6
    # the first-order reading alone over-reads the distance at the face, thinning the sheet (what the second Newton step is for)
    d1 = lattice.surface_distance(face[:, 0], face[:, 1], face[:, 2], cell, steps=1)
    assert 0.31 < np.median(d1) < 0.36
    # the unit cell: the sheet's share and the pore (0.6 mm sheets in a 3.5 mm cell: a 1.04 mm sphere passes)
    c = lattice.unit_cell_stats(cell, wall)
    assert 0.95 < c["pore_mm"] < 1.15 and 0.45 < c["fraction"] < 0.56
    assert lattice.unit_cell_stats(cell, 0.3)["pore_mm"] > c["pore_mm"]
    # the wrap: the field repeats cells_around times round the ring, and the scalar field is the numpy one
    s = spec()
    N, L = s.cells_around, s.wrap_length
    assert L == pytest.approx(N * cell) and N == round(2 * math.pi * s.mid_radius / cell)
    r = rng.uniform(s.zone_inner_radius, s.band.outer_radius_mm, 3000)
    th = rng.uniform(0, 2 * math.pi, 3000)
    z = rng.uniform(-s.zone_half_width, s.zone_half_width, 3000)
    a = s.lattice_sdf(r * np.cos(th), r * np.sin(th), z)
    b = s.lattice_sdf(r * np.cos(th + 2 * math.pi / N), r * np.sin(th + 2 * math.pi / N), z)
    assert np.abs(a - b).max() < 1e-9
    k, half = 2 * math.pi / cell, wall / 2
    scalar = np.array([lattice._opened_lattice_sdf_scalar(float(rr), float(L * (tt % (2 * math.pi)) / (2 * math.pi)), float(zz),
                                                            s.band.outer_radius_mm, k, half, lattice.LATTICE_ROUND_MM)
                       for rr, tt, zz in zip(r[:300], th[:300], z[:300])])
    assert np.abs(scalar - a[:300]).max() < 1e-9
    # the opening at the dome: a point just under the dome on a sheet leaning on it is outside the opened body
    sharp = lattice.sheet_sdf_ring(r * np.cos(th), r * np.sin(th), z, cell, wall, L)
    assert np.all(a >= sharp - 1e-9) and (a > sharp + 1e-6).any()


def test_spec_inputs_identity_and_refusals():
    s = spec()
    assert s.validate() == []
    assert s.rim == pytest.approx(tables.FLOORS["wall_good"]) and s.skin == pytest.approx(tables.SETTINGS["lattice_skin_mm"])
    assert s.zone_inner_radius == pytest.approx(s.band.bore_radius_mm + 0.8) and s.zone_half_width == pytest.approx(2.25)
    v = s.notebook_inputs("O")
    assert list(v) == list(catalog.load("ring_lattice").inputs)
    assert v["Wrap Length"] == pytest.approx(s.cells_around * 3.5) and v["Wall"] == 0.6 and v["Cell Size"] == 3.5
    assert v["Lattice Inner Radius"] == pytest.approx(v["Zone Inner Radius"] - lattice.LATTICE_OVERLAP_MM)
    assert v["Lattice Z Top"] == pytest.approx(v["Zone Z Top"] + lattice.LATTICE_OVERLAP_MM) and v["Lattice Round Inward"] == -v["Lattice Round"]
    assert 0.6 < s.design_volume_mm3() / s.plain_volume_mm3() < 0.8
    assert s.design_volume_mm3() == pytest.approx(s.plain_volume_mm3() - s.zone_band_volume_mm3() + s.sheet_volume_mm3())
    assert s.stem.startswith("ring_lattice_gyroid_flat_US6_w6_t3.3_c3.5w0.6_")
    assert spec(cell_mm=3.6).spec_id != s.spec_id and runs.spec_id(spec(wall_mm=0.7).design()) != s.spec_id
    assert "gyroid" in s.describe() and "cells round the ring" in s.describe() and "saves" in s.result_notes(700.0)[0]
    assert "lattice_member" in spec(wall_mm=0.4).validate()[0]
    assert "pore" in spec(cell_mm=2.5).validate()[0]                                   # 0.6 sheets leave no 1 mm sphere a way through
    assert "cells" in spec(band=flat_band(thickness_mm=1.6)).validate()[0]            # the zone a fifth of a cell deep
    assert "skin" in spec(skin_mm=0.5).validate()[0]
    assert "rim" in spec(rim_mm=0.3).validate()[0]
    assert "voxels" in spec(band=flat_band(mesh_tolerance_mm=0.3)).validate()[0]
    assert "no void" in spec(wall_mm=2.0).validate()[0]
    v = s.model_voids()
    assert v["metal_pieces"] == 1 and v["pockets"] == [] and v["void_components"] >= 1


def test_the_flood_fill_tells_a_pocket_from_a_channel():
    s = spec()
    step = 0.2
    R = s.band.outer_radius_mm + step
    xs = np.arange(-R, R + step / 2, step)
    zs = np.arange(-s.zone_half_width + step / 2, s.zone_half_width, step)
    X, Y = np.meshgrid(xs, xs, indexing="ij")
    r_xy = np.hypot(X, Y)
    void = np.zeros((len(xs), len(xs), len(zs)), dtype=bool)
    dome = r_xy >= s.band.outer_radius_mm - 1.2 * step                          # a channel at the dome, half the ring round
    void[:, :, 3] = dome & (X > 0)
    kz = len(zs) // 2
    ix = int(np.argmin(np.abs(xs - 0.0)))
    iy = int(np.argmin(np.abs(xs + (s.zone_inner_radius + 0.5))))               # a pocket buried over the skin at 270°
    void[ix - 2:ix + 3, iy - 2:iy + 3, kz - 1:kz + 2] = True
    out = lattice._void_components(void, r_xy, zs, s, step)
    assert len(out["pockets"]) == 1 and out["void_components"] == 2
    p = out["pockets"][0]
    assert p["mm3"] == pytest.approx(75 * step ** 3) and 265 < p["theta_deg"] < 275 and abs(p["z"]) < 0.3


def test_recipe_builds_on_the_fake_api(tmp_path):
    from .fake_notebook import FakeNotebook
    from .test_notebook_api import load_recipe
    mod = load_recipe("ring_lattice")
    params = mod.prepare({}, tmp_path)
    params.update({"save_to": str(tmp_path / "l.ntop"), "recipe_to": str(tmp_path / "l.json"), "test_output": str(tmp_path / "l.stl")})
    nb = FakeNotebook()
    res = mod.build(nb, params)
    assert nb.inputs == mod.INPUT_ORDER == list(catalog.load("ring_lattice").inputs)
    assert nb.lint() == [] and res["warnings"] == []
    b = res["blocks"]
    assert res["identifiers"]["Gyroid"] == "gyroid_implicit<real>[1.1.0]" and res["identifiers"]["Walled Gyroid"].startswith("thicken_implicit")
    assert nb.blocks[b["Gyroid"]]["wired"]["Cell Size"][0] == "Cell Size"
    w = nb.blocks[b["Walled Gyroid"]]["wired"]
    assert w["Body"][0] == b["Gyroid"] and w["Thickness"][0] == "Wall"
    assert nb.blocks[b["Lattice Wrapped"]]["wired"]["Y Mapping Length"][0] == "Wrap Length"
    assert set(nb.blocks[b["Lattice Trimmed"]]["lists"]["Bodies"]) == {"Band Body", b["Lattice Zone"], b["Lattice Wrapped"]}
    assert nb.blocks[b["Lattice Eroded"]]["wired"]["Distance"][0] == "Lattice Round Inward"
    assert nb.blocks[b["Lattice Opened"]]["wired"]["Distance"][0] == "Lattice Round"
    assert nb.blocks[b["Skin And Rims"]]["wired"]["Primary Body"][0] == "Band Body"
    assert nb.blocks[b["Skin And Rims"]]["lists"]["Subtraction Bodies"] == [b["Zone"]]
    assert set(nb.blocks[b["Lattice Band"]]["lists"]["Bodies"]) == {b["Skin And Rims"], b["Lattice Opened"]}
    assert nb.blocks[b["Lattice Zone Inside"]]["wired"]["Radius"][0] == "Lattice Inner Radius"


def test_end_to_end_and_the_faults_are_caught(fake_ntopcl, tmp_path, out_dir, monkeypatch):
    nb = tmp_path / "ring_lattice.ntop"
    nb.write_bytes(b"fake")
    s = spec()
    res = lattice.build(s, out_dir, notebook=nb)
    assert res.status == "passed", res.text()
    names = {c.name for c in res.gate.checks}
    assert {"lattice envelope", "untouched outside the zone", "lattice match", "sheet thickness", "pore width", "open voids",
            "design volume"} <= names
    t = res.gate.texture
    assert t["match"]["agreement"] > 0.99 and "best_variant" not in t["match"]
    assert t["rays"]["thickness"]["median"] == pytest.approx(0.6, abs=0.03) and t["rays"]["gap"]["p05"] > 0.85
    assert t["voids"]["pockets"] == [] and 0.4 < t["voids"]["open_share"] < 0.8
    assert abs(res.ntop_volume_mm3 - s.design_volume_mm3()) / s.design_volume_mm3() < 0.005
    assert any("saves" in n for n in res.notes)
    rep = json.loads(next(res.run_dir.glob("*.report.json")).read_text())
    assert rep["status"] == "passed" and rep["design_volume_mm3"] == pytest.approx(s.design_volume_mm3())
    for fault, check in (("nolattice", "lattice match"), ("closed", "open voids"), ("thin", "sheet thickness")):
        monkeypatch.setenv("FAKE_NTOPCL_SHAPE", fault)
        bad = lattice.build(s, out_dir, notebook=nb)
        assert bad.status == "failed" and check in {c.name for c in bad.gate.failures()}, (fault, bad.text())


def test_the_match_names_ntops_convention_when_the_configured_one_is_wrong(monkeypatch):
    s = spec()
    mesh = s.design_mesh()                                              # the standard gyroid, unshifted
    monkeypatch.setattr(lattice, "GYROID_VARIANT", "mirrored")
    m = lattice.lattice_match(mesh, s, points=4000)
    assert m["agreement"] < lattice.MATCH_MIN and m["best_variant"]["variant"] == "standard"
    assert m["best_variant"]["shift_cells"] == [0.0, 0.0, 0.0] and m["best_variant"]["agreement"] > 0.99
