"""Pavé (Phase 3 step 2/3): the layout on the real surface, the seats and beads, the notebook's
wiring, and the band end to end on the simulated nTop - including the gate catching a notebook
that lost the beads or never cut the seats."""
import math

import pytest

from ntopjewel import band, catalog, pave, shank, tables


def spec(rows=1, layout="staggered", span=180.0, **kw):
    b = pave.band_for(1.3, rows, layout, 6)
    return pave.PaveSpec(shank.ShankSpec(b), stone_mm=1.3, rows=rows, layout=layout, span_deg=span, **kw)


@pytest.mark.parametrize("rows,layout,span", [(1, "staggered", 180.0), (2, "staggered", 120.0), (2, "aligned", 360.0)])
def test_the_layout_is_solved_on_the_real_surface(rows, layout, span):
    p = spec(rows, layout, span)
    assert p.validate() == []
    gap = p.gap
    s = p.stones()
    row0 = [q for q in s if q.row == 0]
    # neighbours along a row: the girdles' closest approach is the gap (solved by bisection on the 3-D edges)
    along = p.girdle_gap((row0[0].theta_deg, row0[0].z_mm), (row0[1].theta_deg, row0[1].z_mm))
    if span >= 360:                                                         # the pitch widened to divide the circle evenly
        assert gap - 2e-3 <= along <= gap + p.stone_mm / p.count + 0.05
    else:
        assert along == pytest.approx(gap, abs=2e-3)
    if rows > 1:
        row1 = [q for q in s if q.row == 1]
        near = min(p.girdle_gap((row0[0].theta_deg, row0[0].z_mm), (q.theta_deg, q.z_mm)) for q in row1)
        assert near == pytest.approx(gap, abs=2e-3) if layout == "aligned" or span < 360 else near >= gap - 2e-3
    # the stones' girdles converge towards the axis: at the surface they stand further apart than the gap
    k = math.pi / 180 * p.band.outer_radius_mm
    assert p.pitch_deg * k > p.stone_mm + gap
    if span >= 360:
        assert p.count * p.pitch_deg == pytest.approx(360.0)
    else:
        assert (p.count - 1) * p.pitch_deg <= span + 1e-9
    counts = p.beads_per_stone()
    assert min(counts) >= tables.SETTINGS["pave_min_beads"]
    m = p.design_mesh()
    assert m.is_watertight and m.body_count == 1
    assert m.volume < p.shank.design_volume_mm3()                          # the seats take more than the beads add


def test_a_single_row_has_a_bead_either_side_of_every_gap_and_at_both_ends():
    p = spec(1, span=180.0)
    assert len(p.beads()) == 2 * (p.stone_count + 1) and set(p.beads_per_stone()) == {4}
    zs = sorted({round(b["z"], 4) for b in p.beads()})
    assert len(zs) == 2 and zs[0] == pytest.approx(-zs[1])
    # each bead stands just clear of the openings it borders (the drop-in path), on the stone's side of the ring
    for b in p.beads():
        lat = min(p._lateral(s, b["centre"]) for s in p.stones())
        assert lat == pytest.approx(p.hold_distance, abs=1e-3)
    # the end beads hold the end stones only: none stands past the span's end holding nothing
    ends = [b for b in p.beads() if len(b["holds"]) == 1]
    assert len(ends) == 4


def test_a_full_eternity_closes_on_itself():
    p = spec(1, span=360.0)
    assert p.validate() == [] and p.full
    assert len(p.beads()) == 2 * p.stone_count and set(p.beads_per_stone()) == {4}


def test_seats_are_disjoint_open_cutters_through_to_the_bore():
    p = spec(1, span=40.0)
    s = p.stones()[0]
    seat = p.seat_mesh(s)
    assert seat.is_watertight and seat.volume > 0
    # the cutter reaches above the surface (the drop-in path) and below the bore (the light hole)
    import numpy as np
    r = np.hypot(seat.vertices[:, 0], seat.vertices[:, 1])
    assert r.max() > p.band.outer_radius_mm + 0.5 and r.min() < p.band.bore_radius_mm
    seats = p.seats_mesh()
    assert seats.body_count == p.stone_count                                # disjoint: one body per stone, never a mesh union
    assert p.beads_mesh().body_count == len(p.beads())


def test_validation_names_what_does_not_fit():
    b = band.BandSpec(size=6, width_mm=2.0, thickness_mm=1.6, profile="comfort-flat", mesh_tolerance_mm=0.05)
    assert any("wall to the band's edge" in x for x in pave.PaveSpec(shank.ShankSpec(b), stone_mm=1.3).validate())
    thin = band.BandSpec(size=6, width_mm=2.5, thickness_mm=1.1, profile="comfort-flat", mesh_tolerance_mm=0.05)
    assert any("under the seats" in x for x in pave.PaveSpec(shank.ShankSpec(thin), stone_mm=1.3).validate())
    assert any("between two openings" in x for x in spec(gap_mm=0.1).validate())
    assert any("plain or tapered" in x for x in pave.PaveSpec(shank.ShankSpec(band.BandSpec(size=6), rope=2)).validate())
    tapered = shank.ShankSpec(pave.band_for(1.3, 1, "staggered", 6), width_bottom_mm=2.0, taper_from_deg=60)
    assert any("taper" in x for x in pave.PaveSpec(tapered, stone_mm=1.3, span_deg=180).validate())
    assert pave.PaveSpec(tapered, stone_mm=1.3, span_deg=90).validate() == []
    assert any("Mesh Tolerance" in w for w in pave.PaveSpec(shank.ShankSpec(band.BandSpec(size=6, width_mm=2.5, thickness_mm=1.6,
                                                                                             profile="comfort-flat"))).warnings())


def test_band_for_sizes_the_band_to_the_layout():
    b1, b2 = pave.band_for(1.3, 1, "staggered", 6), pave.band_for(1.3, 2, "staggered", 6)
    assert b1.profile == "comfort-flat" and b1.mesh_tolerance_mm == tables.SETTINGS["pave_mesh_tolerance_mm"]
    assert b2.width_mm > b1.width_mm and b1.thickness_mm >= 1.6
    assert pave.band_for(1.3, 1, "staggered", 6, width_mm=3.0).width_mm == 3.0


def test_recipe_builds_on_the_fake_notebook(tmp_path):
    from .fake_notebook import FakeNotebook
    from .test_notebook_api import load_recipe
    mod = load_recipe("pave_band")
    params = mod.prepare({}, tmp_path)
    params.update({"save_to": str(tmp_path / "p.ntop"), "recipe_to": str(tmp_path / "p.json"), "test_output": str(tmp_path / "p.stl")})
    nb = FakeNotebook()
    res = mod.build(nb, params)
    b = res["blocks"]
    assert nb.inputs == mod.INPUT_ORDER and res["warnings"] == []
    assert list(catalog.load("pave_band").inputs) == mod.INPUT_ORDER
    assert nb.blocks[b["Pave Beads Mesh"]]["wired"]["Path"][0] == b["Pave Beads Path"]
    assert nb.blocks[b["Pave Seats Mesh"]]["wired"]["Path"][0] == b["Pave Seats Path"]
    assert nb.blocks[b["Beaded"]]["lists"]["Bodies"] == [b["Shank Body"], b["Pave Beads"]]          # the beads on the opened band ...
    assert nb.blocks[b["Ring"]]["wired"]["Primary Body"][0] == b["Beaded"]                            # ... THEN the seats cut
    assert nb.blocks[b["Ring"]]["lists"]["Subtraction Bodies"] == [b["Pave Seats"]]
    assert nb.blocks[b["Shank"]]["wired"]["Y Mapping Length"][0] == b["Wrap Length"]                 # the band is ring_shank's


def _build(out_dir, tmp_path, **kw):
    nb = tmp_path / "pave_band.ntop"
    nb.write_bytes(b"fake")
    return pave.build(spec(**kw), out_dir, notebook=nb)


def test_pave_band_end_to_end(fake_ntopcl, tmp_path, out_dir):
    import json
    res = _build(out_dir, tmp_path, rows=2, span=60.0)
    assert res.ok, res.text()
    names = {c.name for c in res.gate.checks}
    assert {"stones fit", "light holes open", "seats", "drop-in clear", "beads", "stones held", "section shape", "design volume"} <= names
    report = json.loads((res.run_dir / f"{res.spec.stem}.report.json").read_text())
    assert len(report["stones"]) == res.spec.stone_count and report["inputs"]["Pave Seats Path"].endswith(".seats.stl")


@pytest.mark.parametrize("shape,caught", [("nobeads", {"beads", "stones held"}),
                                          ("noseats", {"stones fit", "light holes open", "seats", "drop-in clear", "design volume"})])
def test_the_gate_catches_a_lost_layer(shape, caught, fake_ntopcl, tmp_path, out_dir, monkeypatch):
    monkeypatch.setenv("FAKE_NTOPCL_SHAPE", shape)
    res = _build(out_dir, tmp_path, rows=1, span=60.0)
    failed = {c.name for c in res.gate.checks if not c.ok}
    assert not res.ok and caught <= failed


def test_cli_pave_dry_run(capsys):
    from ntopjewel import cli
    assert cli.main(["pave", "--rows", "2", "--span", "120", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "2 rows" in out and "Pave Seats Path" in out and "staggered" in out
    assert cli.main(["pave", "--width", "2.0", "--dry-run"]) == 1
