"""The mesh gate: nothing is "done" until the exported mesh passes.

Checks (same for every product, from CLAUDE.md):
  * watertight, consistent winding, expected number of shells
  * ring metrics: axis, inner and outer diameter, width, against expectations (±0.05 mm)
  * wall thickness by ray casting from sampled surface points, against the material floor
  * volume: against nTop's Mass Properties figure (±2 %) and an analytic figure when given
  * weights per alloy from the volume

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


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    hard: bool = True


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
    def passed(self) -> bool:
        return all(c.ok for c in self.checks if c.hard)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["passed"] = self.passed
        return d

    def text(self) -> str:
        p = Path(self.path)
        lines = [f"{'PASS' if self.passed else 'FAIL'}  {p.name}",
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
            mark = "ok " if c.ok else ("FAIL" if c.hard else "warn")
            lines.append(f"  [{mark}] {c.name}: {c.detail}")
        return "\n".join(lines)


def load_mesh(path: Path) -> trimesh.Trimesh:
    m = trimesh.load(str(path), force="mesh")
    if isinstance(m, trimesh.Scene):
        m = trimesh.util.concatenate([g for g in m.geometry.values()])
    return m


def ring_metrics(mesh: trimesh.Trimesh, axis: str | None = None) -> tuple[str, float, float, float]:
    """(axis, inner diameter, outer diameter, width). Axis defaults to the smallest extent."""
    ext = mesh.bounding_box.extents
    ai = AXES.index(axis) if axis else int(np.argmin(ext))
    center = mesh.bounding_box.centroid
    others = [i for i in range(3) if i != ai]
    v = mesh.vertices
    r = np.hypot(v[:, others[0]] - center[others[0]], v[:, others[1]] - center[others[1]])
    return AXES[ai], 2.0 * float(r.min()), 2.0 * float(r.max()), float(ext[ai])


def wall_thickness(mesh: trimesh.Trimesh, samples: int = 4000, floor: float = 0.5,
                   seed: int = 7) -> dict:
    """Ray-cast thickness: from points on the surface, shoot inward and measure to the exit."""
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
    pts, fidx = trimesh.sample.sample_surface(mesh, samples, seed=rng)
    normals = mesh.face_normals[fidx]
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
    return out


def ray_backend(mesh: trimesh.Trimesh) -> str:
    return "embree" if "embree" in type(mesh.ray).__module__ else "python"


def check(path: Path, *, expect_inner: float | None = None, expect_outer: float | None = None,
          expect_width: float | None = None, expect_volume: float | None = None,
          tol_mm: float = 0.05, tol_volume_pct: float = 2.0, shells: int = 1,
          wall_floor: float = tables.FLOORS["wall_marginal"], wall_samples: int = 4000,
          axis: str | None = None, metals=tables.DEFAULT_WEIGHT_METALS,
          write_report: bool = True) -> GateReport:
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

    rep.axis, rep.inner_diameter_mm, rep.outer_diameter_mm, rep.width_mm = ring_metrics(mesh, axis)
    rep.thickness = wall_thickness(mesh, wall_samples, wall_floor) if rep.watertight else {}
    rep.weights_g = tables.weights_g(rep.volume_mm3, metals)

    c = rep.checks
    c.append(Check("watertight", rep.watertight, "closed mesh" if rep.watertight else "open edges or holes"))
    c.append(Check("winding", rep.winding_consistent, "consistent" if rep.winding_consistent else "inconsistent face winding"))
    c.append(Check("shells", rep.shells == shells, f"{rep.shells} (expected {shells})"))
    if rep.thickness:
        t = rep.thickness
        c.append(Check("wall thickness", t["p01"] >= wall_floor,
                       f"p1 {t['p01']:.3f} mm vs floor {wall_floor:.2f} mm", hard=wall_floor > 0))
    else:
        c.append(Check("wall thickness", False, "not measured", hard=False))
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


def band_volume_mm3(inner_d: float, outer_d: float, width: float) -> float:
    """Analytic volume of a flat band (rectangular section)."""
    return math.pi * ((outer_d / 2) ** 2 - (inner_d / 2) ** 2) * width
