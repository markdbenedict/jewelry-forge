"""The mesh gate: nothing is "done" until the exported mesh passes.

Checks (same for every product, from CLAUDE.md):
  * watertight, consistent winding, expected number of shells
  * ring metrics: axis, inner and outer diameter, width, against expectations (±0.05 mm)
  * wall thickness by ray casting from sampled surface points, against the material floor
  * volume: against nTop's figure (±2 %); the product builders add "design volume" (nTop
    against the independent design arithmetic) and, for engraved rings, "engraving"
  * weights per alloy from the volume

Every check has a status: PASSED, FAILED or INCOMPLETE (it could not be measured - no rays
came back, nTop reported no volume). A report is `passed` only when every hard check PASSED;
an INCOMPLETE hard check makes the report INCOMPLETE, which is not a pass and never delivers
(2026-10-27 review: "unmeasured wall thickness was advisory and allowed an overall pass").

Ported from `blender/jewelry_kit.py: check_model` so it runs without Blender (trimesh).
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import trimesh

from . import tables

AXES = ("x", "y", "z")
PASSED, FAILED, INCOMPLETE = "passed", "failed", "incomplete"


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    hard: bool = True
    status: str = ""          # PASSED / FAILED / INCOMPLETE; derived from `ok` when not given

    def __post_init__(self):
        self.ok = bool(self.ok)                  # a numpy bool would not serialise
        if self.status == INCOMPLETE:
            self.ok = False
        elif self.status not in (PASSED, FAILED):
            self.status = PASSED if self.ok else FAILED
        else:
            self.ok = self.status == PASSED


def incomplete(name: str, detail: str, hard: bool = True) -> Check:
    """A mandatory measurement that could not be made."""
    return Check(name, False, detail, hard, INCOMPLETE)


@dataclass
class GateReport:
    path: str
    triangles: int = 0
    vertices: int = 0
    watertight: bool = False
    winding_consistent: bool = False
    normals_flipped: bool = False
    shells: int = 0
    volume_mm3: float = 0.0
    area_mm2: float = 0.0
    extents_mm: list[float] = field(default_factory=list)
    axis: str = "z"
    inner_diameter_mm: float | None = None
    outer_diameter_mm: float | None = None
    width_mm: float | None = None
    thickness: dict = field(default_factory=dict)
    weights_g: dict = field(default_factory=dict)
    checks: list[Check] = field(default_factory=list)

    @property
    def status(self) -> str:
        """FAILED if any hard check failed, else INCOMPLETE if any hard check could not be
        measured, else PASSED. Advisory (hard=False) checks never change it."""
        hard = [c for c in self.checks if c.hard]
        if any(c.status == FAILED for c in hard):
            return FAILED
        if any(c.status == INCOMPLETE for c in hard):
            return INCOMPLETE
        return PASSED

    @property
    def passed(self) -> bool:
        return self.status == PASSED

    @property
    def incomplete(self) -> bool:
        return self.status == INCOMPLETE

    def failures(self) -> list[Check]:
        return [c for c in self.checks if c.hard and c.status != PASSED]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status
        d["passed"] = self.passed
        return d

    def text(self) -> str:
        p = Path(self.path)
        word = {PASSED: "PASS", FAILED: "FAIL", INCOMPLETE: "INCOMPLETE"}[self.status]
        lines = [f"{word}  {p.name}",
                 f"  {self.triangles:,} tris, {self.vertices:,} verts, shells {self.shells}, "
                 f"watertight {self.watertight}, winding ok {self.winding_consistent}"
                 + (", normals were flipped" if self.normals_flipped else ""),
                 f"  extents {self.extents_mm[0]:.2f} x {self.extents_mm[1]:.2f} x {self.extents_mm[2]:.2f} mm, "
                 f"ring axis {self.axis}"]
        if self.inner_diameter_mm is not None:
            lines.append(f"  inner Ø {self.inner_diameter_mm:.3f} mm  outer Ø {self.outer_diameter_mm:.3f} mm  "
                         f"width {self.width_mm:.3f} mm")
        lines.append(f"  volume {self.volume_mm3:.2f} mm³ ({self.volume_mm3 / 1000:.3f} ml), area {self.area_mm2:.1f} mm²")
        if self.thickness:
            t = self.thickness
            lines.append(f"  wall: min {t['min']:.3f}  p1 {t['p01']:.3f}  p5 {t['p05']:.3f}  median {t['median']:.3f} mm "
                         f"({t['samples']} samples, {100 * t['below_floor_fraction']:.1f}% under {t['floor']:.2f} mm)"
                         + (f"; {t['note']}" if t.get("note") else ""))
        if self.weights_g:
            lines.append("  weight: " + ", ".join(f"{k} {v:.2f} g" for k, v in self.weights_g.items()))
        for c in self.checks:
            if c.status == PASSED:
                mark = "ok  "
            elif not c.hard:
                mark = "warn"
            else:
                mark = "FAIL" if c.status == FAILED else "INC "
            lines.append(f"  [{mark}] {c.name}: {c.detail}")
        return "\n".join(lines)


def load_mesh(path: Path) -> trimesh.Trimesh:
    m = trimesh.load(str(path), force="mesh")
    if isinstance(m, trimesh.Scene):
        m = trimesh.util.concatenate([g for g in m.geometry.values()])
    return m


MIN_WALL_SAMPLES = 1000      # fewer usable rays and p1 rests on a handful of them: not a measurement


def ring_axis(mesh: trimesh.Trimesh) -> int:
    """The ring axis: the bounding-box axis along which a line through the centre passes
    through the bore without touching metal. Only when that does not single out one axis (no
    bore, or a ball) does it fall back to the smallest extent - which alone would pick the
    wrong axis on a band wider than its diameter (a cigar band, a signet sleeve)."""
    ext = mesh.bounding_box.extents
    centre = mesh.bounding_box.centroid
    open_axes = []
    for i in range(3):
        d = np.zeros(3)
        d[i] = 1.0
        start = centre - d * (ext[i] + 1.0)
        try:
            hits = mesh.ray.intersects_any([start], [d])
        except BaseException:
            return int(np.argmin(ext))
        if not bool(hits[0]):
            open_axes.append(i)
    return open_axes[0] if len(open_axes) == 1 else int(np.argmin(ext))


def ring_metrics(mesh: trimesh.Trimesh, axis: str | None = None, centre: str = "bbox") -> tuple[str, float, float, float]:
    """(axis, inner diameter, outer diameter, width). Axis: given, else `ring_axis`. The diameters
    are measured about the bounding box's centre, or about the origin (`centre="origin"`) for a
    part the pipeline built round the origin whose outside is not symmetric - a shank thicker at
    the head than at the bottom has its box centre 0.2 mm off the axis (2026-10-30)."""
    ext = mesh.bounding_box.extents
    ai = AXES.index(axis) if axis else ring_axis(mesh)
    center = np.zeros(3) if centre == "origin" else mesh.bounding_box.centroid
    others = [i for i in range(3) if i != ai]
    v = mesh.vertices
    r = np.hypot(v[:, others[0]] - center[others[0]], v[:, others[1]] - center[others[1]])
    return AXES[ai], 2.0 * float(r.min()), 2.0 * float(r.max()), float(ext[ai])


def wall_thickness(mesh: trimesh.Trimesh, samples: int = 4000, floor: float = 0.5,
                   seed: int = 7, zone: tuple[int, float] | None = None, axis: int | None = None,
                   min_alignment: float = 0.5, ray_filter=None) -> dict:
    """Ray-cast thickness: from points on the surface, shoot inward and measure to the exit.

    `zone` = (axis index, abs max): sample only surface points with |coord[axis]| <= abs max.
    Decorative bumps (milgrain beads) are solid on solid: a ray grazing a bead measures a short
    chord through the sphere, not a wall, so a featured ring keeps its bead rows out of the
    sample and measures the band itself.

    `axis` (the ring axis): keep only rays whose direction is within 60° of radial or of axial
    (|n·r̂| >= min_alignment or |n·ẑ| >= min_alignment). On a ring those are the directions a
    wall is measured in: the band wall, a pocket or groove floor, the faces. A ray leaving a
    letter's side wall runs sideways through the rib between two strokes - a 0.3 mm ridge on
    a solid band, not a wall - and a ray off a union seam exits through a sliver facet; both
    read as "thin" without this filter (seen 2026-10-27: p1 0.28 mm on a sound ring).

    `ray_filter(points, normals) -> bool array`: the product's own exclusions, applied last
    (an engraved ring drops the axial rays inside its text span: a letter's top wall measures
    the rib to the next stroke, not a wall - seen on the simulated ring, p1 0.25 mm)."""
    if samples <= 0:
        return {}
    fast = ray_backend(mesh) == "embree"
    note = ""
    if not fast:
        # the pure-python intersector needs gigabytes per few hundred rays on a 1M-triangle
        # mesh; keep the gate alive with a small sample and say so in the report
        cap = 300 if len(mesh.faces) > 200_000 else 800
        if samples > cap:
            samples = cap
        note = "embreex not installed: pure-python ray backend, sample reduced"
    rng = np.random.default_rng(seed)
    oversample = 4 if (zone is not None or axis is not None or ray_filter is not None) else 1
    pts, fidx = trimesh.sample.sample_surface(mesh, samples * oversample, seed=rng)
    normals = mesh.face_normals[fidx]
    excluded = {}
    keep = np.ones(len(pts), dtype=bool)
    if zone is not None:
        ax, lim = zone
        inzone = np.abs(pts[:, ax]) <= lim
        excluded["outside_zone"] = int((~inzone).sum())
        keep &= inzone
    if axis is not None:
        centre = mesh.bounding_box.centroid
        radial = pts - centre
        radial[:, axis] = 0.0
        norm = np.linalg.norm(radial, axis=1)
        norm[norm == 0] = 1.0
        radial /= norm[:, None]
        axial = np.abs(normals[:, axis])
        rad = np.abs(np.einsum("ij,ij->i", normals, radial))
        aligned = (rad >= min_alignment) | (axial >= min_alignment)
        excluded["tangential"] = int((~aligned & keep).sum())
        keep &= aligned
    if ray_filter is not None:
        wanted = np.asarray(ray_filter(pts, normals), dtype=bool)
        excluded["product_filter"] = int((~wanted & keep).sum())
        keep &= wanted
    pts, fidx, normals = pts[keep][:samples], fidx[keep][:samples], normals[keep][:samples]
    samples = len(pts)
    if samples == 0:
        return {}
    eps = 1e-4
    origins = pts - normals * eps
    dirs = -normals
    dists = []
    batch = samples if fast else 50
    try:
        for s in range(0, samples, batch):
            locs, ray_idx, _ = mesh.ray.intersects_location(origins[s:s + batch], dirs[s:s + batch],
                                                            multiple_hits=False)
            if len(ray_idx):
                dists.append(np.linalg.norm(locs - origins[s:s + batch][ray_idx], axis=1))
    except BaseException:          # a ray backend hiccup must not kill the gate
        return {}
    if not dists:
        return {}
    d = np.concatenate(dists)
    d = d[d > 10 * eps]
    if d.size == 0:
        return {}
    out = {
        "min": float(d.min()),
        "p01": float(np.percentile(d, 1)),
        "p05": float(np.percentile(d, 5)),
        "median": float(np.median(d)),
        "samples": int(d.size),
        "floor": float(floor),
        "below_floor_fraction": float(np.mean(d < floor)),
    }
    if note:
        out["note"] = note
    if zone is not None:
        out["zone"] = f"|{'xyz'[zone[0]]}| <= {zone[1]:.3f} mm"
    if excluded:
        out["excluded"] = excluded
    return out


def ray_backend(mesh: trimesh.Trimesh) -> str:
    return "embree" if "embree" in type(mesh.ray).__module__ else "python"


def check(path: Path, *, expect_inner: float | None = None, expect_outer: float | None = None,
          expect_width: float | None = None, expect_volume: float | None = None,
          tol_mm: float = 0.05, tol_volume_pct: float = 2.0, shells: int = 1,
          wall_floor: float = tables.FLOORS["wall_marginal"], wall_samples: int = 4000,
          axis: str | None = None, metals=tables.DEFAULT_WEIGHT_METALS,
          write_report: bool = True, wall_abs_axis_max: float | None = None, wall_ray_filter=None,
          centre: str = "bbox") -> GateReport:
    path = Path(path)
    mesh = load_mesh(path)
    rep = GateReport(path=str(path), triangles=int(len(mesh.faces)), vertices=int(len(mesh.vertices)))

    rep.winding_consistent = bool(mesh.is_winding_consistent)
    rep.watertight = bool(mesh.is_watertight)
    if rep.watertight and mesh.volume < 0:
        mesh.invert()
        rep.normals_flipped = True
    parts = mesh.split(only_watertight=False)
    rep.shells = int(len(parts)) if len(parts) else 1
    rep.volume_mm3 = float(abs(mesh.volume)) if rep.watertight else float(abs(mesh.volume))
    rep.area_mm2 = float(mesh.area)
    rep.extents_mm = [float(x) for x in mesh.bounding_box.extents]

    rep.axis, rep.inner_diameter_mm, rep.outer_diameter_mm, rep.width_mm = ring_metrics(mesh, axis, centre)
    ax = "xyz".index(rep.axis) if rep.axis in "xyz" else None
    zone = (ax, wall_abs_axis_max) if (wall_abs_axis_max is not None and ax is not None) else None
    rep.thickness = (wall_thickness(mesh, wall_samples, wall_floor, zone=zone, axis=ax, ray_filter=wall_ray_filter)
                     if rep.watertight else {})
    rep.weights_g = tables.weights_g(rep.volume_mm3, metals)

    c = rep.checks
    dense = rep.triangles > 5_000_000
    c.append(Check("mesh density", not dense,
                   f"{rep.triangles:,} triangles" + ("; far denser than a printer can use: raise Mesh Tolerance "
                                                     "(nTop tolerance = 2 x voxel size)" if dense else ""),
                   hard=False))
    c.append(Check("watertight", rep.watertight, "closed mesh" if rep.watertight else "open edges or holes"))
    c.append(Check("winding", rep.winding_consistent, "consistent" if rep.winding_consistent else "inconsistent face winding"))
    c.append(Check("shells", rep.shells == shells, f"{rep.shells} (expected {shells})"))
    if rep.thickness and rep.thickness["samples"] < MIN_WALL_SAMPLES and wall_floor > 0:
        t = rep.thickness
        c.append(incomplete("wall thickness", f"only {t['samples']} usable rays (need {MIN_WALL_SAMPLES}): p1 {t['p01']:.3f} mm "
                            "is not a measurement" + ("; install embreex (python -m pip install -e .\\python -c "
                            ".\\python\\constraints.txt)" if t.get("note") else "; raise --samples")))
    elif rep.thickness:
        t = rep.thickness
        c.append(Check("wall thickness", t["p01"] >= wall_floor,
                       f"p1 {t['p01']:.3f} mm vs floor {wall_floor:.2f} mm" + (f" ({t['zone']})" if t.get("zone") else ""),
                       hard=wall_floor > 0))
    else:
        why = ("mesh not closed" if not rep.watertight else
               "no rays requested" if wall_samples <= 0 else "no ray returned a distance")
        c.append(incomplete("wall thickness", f"not measured ({why})", hard=wall_floor > 0))
    if expect_inner is not None:
        d = rep.inner_diameter_mm - expect_inner
        c.append(Check("inner diameter", abs(d) <= tol_mm, f"{rep.inner_diameter_mm:.3f} vs {expect_inner:.3f} mm (Δ {d:+.3f})"))
    if expect_outer is not None:
        d = rep.outer_diameter_mm - expect_outer
        c.append(Check("outer diameter", abs(d) <= tol_mm, f"{rep.outer_diameter_mm:.3f} vs {expect_outer:.3f} mm (Δ {d:+.3f})"))
    if expect_width is not None:
        d = rep.width_mm - expect_width
        c.append(Check("width", abs(d) <= tol_mm, f"{rep.width_mm:.3f} vs {expect_width:.3f} mm (Δ {d:+.3f})"))
    if expect_volume:
        pct = 100.0 * (rep.volume_mm3 - expect_volume) / expect_volume
        c.append(Check("volume", abs(pct) <= tol_volume_pct, f"{rep.volume_mm3:.2f} vs {expect_volume:.2f} mm³ ({pct:+.2f}%)"))

    if write_report:
        path.with_suffix(".gate.json").write_text(json.dumps(rep.to_dict(), indent=2), encoding="utf-8")
    return rep


def save(rep: "GateReport") -> None:
    """Rewrite <stem>.gate.json from the finished report. gate.check writes it once with the generic
    checks; a family that appends its own (bore, extents, stone fits, design volume ...) calls this
    after them, so the file on disk is the gate that decided the status (it was not, 2026-10-28)."""
    Path(rep.path).with_suffix(".gate.json").write_text(json.dumps(rep.to_dict(), indent=2), encoding="utf-8")


def band_volume_mm3(inner_d: float, outer_d: float, width: float) -> float:
    """Analytic volume of a flat band (rectangular section)."""
    return math.pi * ((outer_d / 2) ** 2 - (inner_d / 2) ** 2) * width
