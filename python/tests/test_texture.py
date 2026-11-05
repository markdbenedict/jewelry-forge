"""Surface textures: a hammered band - strikes of one round hammer face in a seeded dart-throwing layout,
the independent model (the band less the strikes' spheres) and its gate."""
import math

import numpy as np
import pytest

from ntopjewel import band, tables, texture


def hammered(**kw):
    b = kw.pop("band", None) or band.BandSpec(size=6, profile="court", width_mm=4.0, thickness_mm=1.6, mesh_tolerance_mm=0.05)
    return texture.HammeredSpec(b, **kw)


def test_the_hammer_and_its_layout():
    s = hammered()
    assert s.validate() == []
    R = s.sphere_radius
    assert R == pytest.approx((0.8 ** 2 + 0.15 ** 2) / 0.3) and s.footprint_mm(0.15) == pytest.approx(1.6)
    u, z, d = s.layout()
    assert s.count == len(u) > 100
    L, sp = s.face_length, s.spacing * s.dimple_mm
    du = np.abs(u[:, None] - u[None, :])
    du = np.minimum(du, L - du)
    dist = np.hypot(du, z[:, None] - z[None, :]) + np.eye(len(u)) * 99
    assert dist.min() >= sp - 1e-9                                                       # spaced, round the seam too
    assert np.abs(z).max() <= s.z_limit + 1e-9
    assert d.min() >= tables.FLOORS["texture_depth"] - 1e-9 and d.max() <= s.depth_range[1] + 1e-9
    reach = np.abs(z) + np.array([s.footprint_mm(q) for q in d]) / 2
    assert reach.max() <= s.edge_reach + 1e-6                                              # no footprint into a rim
    assert (d < s.depth_range[0] - 1e-9).any()                                            # lighter strikes by the rims
    # the same seed, the same hammering; another seed, another
    assert np.array_equal(hammered().layout()[0], u) and not np.array_equal(hammered(seed=2).layout()[0][:5], u[:5])
    # every centre on its face point's normal, R - d out
    P, N, dd, C = s.strikes()
    assert np.allclose(np.linalg.norm(C - P, axis=1), R - dd) and np.allclose(np.linalg.norm(N, axis=1), 1.0)
    assert np.allclose(s.centres(), C)


def test_the_design_passes_its_gate_and_a_wrong_build_is_caught(tmp_path):
    s = hammered()
    m = s.design_mesh()
    assert m.is_watertight and m.body_count == 1
    plain = s.band_mesh()
    lost = plain.volume - m.volume
    assert 0.03 * plain.volume < lost < 0.08 * plain.volume                                # a few % of the metal
    m.export(tmp_path / "h.stl")
    rep = texture.check_texture(s, tmp_path / "h.stl", float(m.volume))
    assert rep.status == "passed", rep.text()
    assert {"strikes", "section shape", "design volume", "wall thickness"} <= {c.name for c in rep.checks}
    plain.export(tmp_path / "p.stl")                                                      # the texture left out
    assert {"strikes", "design volume", "section shape"} <= {c.name for c in texture.check_texture(s, tmp_path / "p.stl", float(plain.volume)).failures()}
    light = hammered(depth_mm=0.12)                                                        # struck too lightly (a wrong radius)
    light.design_mesh().export(tmp_path / "l.stl")
    failed = {c.name for c in texture.check_texture(s, tmp_path / "l.stl", float(light.design_mesh().volume)).failures()}
    assert "strikes" in failed


def test_what_a_hammering_refuses():
    assert "voxels" in hammered(band=band.BandSpec(size=6, width_mm=4.0, thickness_mm=1.6, mesh_tolerance_mm=0.1)).validate()[0]
    assert "polishes flat" in hammered(depth_mm=0.12).validate()[0]
    assert "hemisphere" in hammered(dimple_mm=0.8, depth_mm=0.45, depth_var=0.0).validate()[0]
    assert "0.5..1.5" in hammered(spacing=0.3).validate()[0]
    assert "no room" in hammered(band=band.BandSpec(size=6, width_mm=2.0, thickness_mm=1.6, mesh_tolerance_mm=0.05), rim_mm=0.4).validate()[0]
    wide = hammered(band=band.BandSpec(size=10, profile="comfort-flat", width_mm=8.0, thickness_mm=2.0, mesh_tolerance_mm=0.03))
    assert "M triangles" in wide.validate()[-1]
    assert tables.mesh_triangles_estimate(1184.9, 0.05) == pytest.approx(5.29e6, rel=0.01)  # the run it was calibrated on


def test_cli_texture(capsys, tmp_path):
    from ntopjewel import cli
    assert cli.main(["texture", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "ring_texture_hammered_court_US6_w4_t1.6_d1.6x0.15_" in out and "strikes of a 2.21 mm hammer face" in out and "M triangles" in out
    assert cli.main(["texture", "--tolerance", "0.1", "--dry-run"]) == 1
    assert "--tolerance 0.06 or finer" in capsys.readouterr().out
    assert cli.main(["texture", "--write-design", "--out", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "not an nTop build" in out
    assert len(list(tmp_path.rglob("*.design.stl"))) == 1 and len(list(tmp_path.rglob("*.centres.csv"))) == 1
    csv = np.loadtxt(next(tmp_path.rglob("*.centres.csv")), delimiter=",")
    assert csv.shape == (hammered().count, 3)
    assert cli.main(["texture"]) == 2                                                       # no notebook yet
