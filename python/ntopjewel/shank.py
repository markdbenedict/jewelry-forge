"""Phase 3 step 1: shaped shanks - a band whose section changes round the ring.

A tapered shank is the commonest thing in the reference set (rings 02, 03, 05): full width and
thickness at the head, easing to a narrower, thinner section at the bottom of the finger. The
notebook that builds it (`ring_shank.ntop`) is small, because the shape is made the way the
engraving is placed:

    Python writes a BAR: the ring unrolled, X radial (= r), Y along the ring, Z axial, one
    cross-section (the band profile at that angle's width and thickness) every few degrees,
    lofted; nTop imports it, makes it implicit and wraps it round the axis (Remap Cylindrical
    Body, Y mapping length = Wrap Length). X -> r and Z -> z are exact under that map, Y -> angle
    is exact, so the section nTop builds at every angle IS the section Python designed there.

The independent model never sees the bar: it sweeps the same sections round the axis directly
(`design_mesh`), and the gate measures the finished STL's section at twelve angles against the
design's (`check_shank`: "section profile") as well as the usual band checks and the design
volume. A notebook that forgot to wrap, or wrapped with the wrong length, fails there.

Every number comes from `ShankSpec`: the head section is a `BandSpec` (profile, width, thickness,
size); the bottom section's width and thickness; the angle the taper starts at (full section
until then, then a cosine ease to the bottom, so the shoulders show no crease); the number of
stations. Floors: every station's section must be a valid band (BandSpec.validate), so the thin
end respects the walls and the edge round the same way a plain band does.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from . import band, catalog, config, gate, geom, ntopcl, runs, tables

BAR_OVERLAP_MM = 1.0        # the bar runs this far past the turn at both ends: the seam is inside material
SECTION_POINTS = 256        # every station's outline resampled to this many points (lofted vertex to vertex)
CHECK_ANGLES_DEG = tuple(range(0, 360, 30))   # where the gate measures the built section against the design
SECTION_TOL_MM = 0.06       # width / thickness at a station: the mesh tolerance plus a little


def ease(frac: float) -> float:
    """1 -> 0 over frac 0 -> 1 with zero slope at both ends (a cosine), the taper's law."""
    f = min(max(float(frac), 0.0), 1.0)
    return 0.5 * (1.0 + math.cos(math.pi * f))


@dataclass
class ShankSpec:
    band: band.BandSpec                             # the section at the head (angle 0, +X): the full one
    width_bottom_mm: float | None = None            # width at the bottom (180°); None = the head's
    thickness_bottom_mm: float | None = None        # thickness at the bottom; None = the head's
    taper_from_deg: float = 60.0                    # full section this far from the head, then the ease to the bottom
    stations: int = 144                             # sections round the ring (2.5° apart)
    _cache: dict = field(default_factory=dict, repr=False, compare=False)

    # ---- the law -------------------------------------------------------------------------
    @property
    def width_bottom(self) -> float:
        return float(self.band.width_mm if self.width_bottom_mm is None else self.width_bottom_mm)

    @property
    def thickness_bottom(self) -> float:
        return float(self.band.thickness_mm if self.thickness_bottom_mm is None else self.thickness_bottom_mm)

    @property
    def tapered(self) -> bool:
        return self.width_bottom != self.band.width_mm or self.thickness_bottom != self.band.thickness_mm

    def blend_fraction(self, theta_deg: float) -> float:
        """1 at the head, 0 at the bottom: how much of the head's section an angle keeps."""
        a = abs((float(theta_deg) + 180.0) % 360.0 - 180.0)           # 0 .. 180 from the head
        if a <= self.taper_from_deg:
            return 1.0
        return ease((a - self.taper_from_deg) / max(180.0 - self.taper_from_deg, 1e-9))

    def width_at(self, theta_deg: float) -> float:
        f = self.blend_fraction(theta_deg)
        return self.width_bottom + (self.band.width_mm - self.width_bottom) * f

    def thickness_at(self, theta_deg: float) -> float:
        f = self.blend_fraction(theta_deg)
        return self.thickness_bottom + (self.band.thickness_mm - self.thickness_bottom) * f

    def section_spec(self, theta_deg: float) -> band.BandSpec:
        """The band whose section this angle gets: the head's band at the local width and thickness."""
        return replace(self.band, width_mm=round(self.width_at(theta_deg), 6), thickness_mm=round(self.thickness_at(theta_deg), 6))

    def station_angles(self):
        return [360.0 * k / self.stations for k in range(self.stations)]

    # ---- geometry -------------------------------------------------------------------------
    def section_polygon(self, theta_deg: float):
        """The finished meridian section at this angle, a shapely polygon in (r, z)."""
        return geom.section_polygon(self.section_spec(theta_deg).notebook_inputs(""))

    def section_outline(self, theta_deg: float):
        """(SECTION_POINTS, 2) array of (r, z) round the section: counter-clockwise from the bore's
        mid-plane point, equally spaced along the outline, so stations loft vertex to vertex."""
        return outline_points(self.section_polygon(theta_deg), SECTION_POINTS, start=(self.band.bore_radius_mm, 0.0))

    def outlines(self):
        if "outlines" not in self._cache:
            self._cache["outlines"] = [self.section_outline(t) for t in self.station_angles()]
        return self._cache["outlines"]

    @property
    def wrap_length_mm(self) -> float:
        """Remap Cylindrical's Y mapping length: one turn of the bar; the mid-wall circumference,
        so the bar's facets are about isometric (the map itself is exact in r, z and angle)."""
        return 2 * math.pi * (self.band.bore_radius_mm + self.band.thickness_mm / 2)

    def bar_mesh(self):
        """The unrolled shank for the notebook: X radial, Y along the ring (Y = wrap length is one
        turn, angle 0 at Y = 0), Z axial. It covers a turn and a half plus BAR_OVERLAP_MM at both
        ends (Y from -L/2 - o to L + o), so whichever way nTop reads the angle (0..360 or
        ±180) every angle finds material and the seam lies inside the bar."""
        import numpy as np
        import trimesh
        L = self.wrap_length_mm
        n, m = self.stations, SECTION_POINTS
        outlines = self.outlines()
        step = L / n
        k0 = -(n // 2) - int(math.ceil(BAR_OVERLAP_MM / step))
        k1 = n + int(math.ceil(BAR_OVERLAP_MM / step))
        ks = list(range(k0, k1 + 1))
        verts = []
        for k in ks:
            rz = outlines[k % n]
            y = k * step
            verts.append(np.column_stack([rz[:, 0], np.full(m, y), rz[:, 1]]))
        V = np.vstack(verts)
        faces = []
        for i in range(len(ks) - 1):
            a = i * m + np.arange(m)
            b = a + m
            an, bn = np.roll(a, -1), np.roll(b, -1)
            faces.append(np.column_stack([a, an, bn]))          # outline counter-clockwise in (r, z), +y along: outward
            faces.append(np.column_stack([a, bn, b]))
        F = np.vstack(faces)
        # the caps: a triangulation of the outline, one at each end
        tri = _outline_triangles(outlines[ks[0] % n])
        F = np.vstack([F, tri[:, ::-1], tri + (len(ks) - 1) * m])
        mesh = trimesh.Trimesh(V, F, process=False)
        if mesh.volume < 0:
            mesh.invert()
        return mesh

    def design_mesh(self):
        """The independent ring: the same sections swept round the axis (Z), no bar, no wrap."""
        if "design_mesh" not in self._cache:
            import numpy as np
            import trimesh
            n, m = self.stations, SECTION_POINTS
            verts = []
            for t, rz in zip(self.station_angles(), self.outlines()):
                c, s = math.cos(math.radians(t)), math.sin(math.radians(t))
                verts.append(np.column_stack([rz[:, 0] * c, rz[:, 0] * s, rz[:, 1]]))
            V = np.vstack(verts)
            faces = []
            for i in range(n):
                a = i * m + np.arange(m)
                b = ((i + 1) % n) * m + np.arange(m)
                an, bn = np.roll(a, -1), np.roll(b, -1)
                faces.append(np.column_stack([a, an, bn]))
                faces.append(np.column_stack([a, bn, b]))
            mesh = trimesh.Trimesh(V, np.vstack(faces), process=False)
            if mesh.volume < 0:
                mesh.invert()
            self._cache["design_mesh"] = mesh
        return self._cache["design_mesh"]

    def design_volume_mm3(self) -> float:
        return float(self.design_mesh().volume)

    def section_extents(self, theta_deg: float) -> tuple[float, float]:
        """(width, thickness) of the designed section at an angle: the outline's z and r extents."""
        rz = self.section_outline(theta_deg)
        return float(rz[:, 1].max() - rz[:, 1].min()), float(rz[:, 0].max() - rz[:, 0].min())

    # ---- identity, inputs, checks ------------------------------------------------------------
    def design(self) -> dict:
        d = self.band.design()
        d.update({"width_bottom": self.width_bottom, "thickness_bottom": self.thickness_bottom,
                  "taper_from_deg": self.taper_from_deg, "stations": self.stations, "section_points": SECTION_POINTS,
                  "wrap_length": round(self.wrap_length_mm, 4)})
        return d

    @property
    def spec_id(self) -> str:
        return runs.spec_id(self.design())

    @property
    def stem(self) -> str:
        b = self.band
        return (f"ring_shank_{b.profile}_{b.label}_w{b.width_mm:g}-{self.width_bottom:g}_t{b.thickness_mm:g}-{self.thickness_bottom:g}"
                f"_{self.spec_id}")

    def notebook_inputs(self, bar_path: str, output_path: str = "") -> dict:
        """Values for every input of ring_shank.ntop (names must match the catalog)."""
        return {
            "Shank Path": str(bar_path),
            "Wrap Length": round(self.wrap_length_mm, 4),
            "Mesh Tolerance": self.band.mesh_tolerance_mm,
            "Output Path": str(output_path),
        }

    def validate(self) -> list[str]:
        p = list(self.band.validate())
        if self.width_bottom > self.band.width_mm + 1e-9:
            p.append(f"bottom width {self.width_bottom:g} mm wider than the head's {self.band.width_mm:g} mm: a shank tapers towards the bottom")
        if self.thickness_bottom > self.band.thickness_mm + 1e-9:
            p.append(f"bottom thickness {self.thickness_bottom:g} mm thicker than the head's {self.band.thickness_mm:g} mm")
        if not 0.0 <= self.taper_from_deg <= 170.0:
            p.append(f"taper start {self.taper_from_deg:g}° must be 0..170° from the head")
        if not 24 <= self.stations <= 720:
            p.append(f"stations {self.stations}: 24..720")
        if not p:
            for t in (90.0, 180.0):                            # the thin end and the shoulder must be valid bands too
                probs = self.section_spec(t).validate()
                if probs:
                    p.append(f"at {t:g}° (width {self.width_at(t):.2f}, thickness {self.thickness_at(t):.2f}): " + "; ".join(probs))
                    break
        return p

    def warnings(self) -> list[str]:
        return list(self.band.warnings())

    def wall_floor(self) -> float:
        """The ray-cast thickness floor: the material floor, or 0.8 x the thinnest station's edge."""
        thin = min(self.section_spec(t).edge_thickness_mm for t in (0.0, 180.0))
        return min(tables.FLOORS["wall_marginal"], 0.8 * thin)

    def describe(self) -> str:
        b = self.band
        return (f"{self.stem}: {b.profile} {b.label}, inner Ø {b.inner_diameter_mm:.3f}\n"
                f"  head: width {b.width_mm:g} thickness {b.thickness_mm:g}; bottom: width {self.width_bottom:g} "
                f"thickness {self.thickness_bottom:g}; full section to {self.taper_from_deg:g}° then a cosine ease\n"
                f"  {self.stations} stations x {SECTION_POINTS} points; wrap length {self.wrap_length_mm:.3f} mm; "
                f"design volume {self.design_volume_mm3():.2f} mm³")


# ---- outlines ----------------------------------------------------------------------------------
def outline_points(poly, n: int, start: tuple[float, float]):
    """`n` points equally spaced along a shapely polygon's exterior, counter-clockwise, the first
    one where the outline passes closest to `start`; (n, 2) array."""
    import numpy as np
    from shapely.geometry.polygon import orient
    ring = np.asarray(orient(poly, 1.0).exterior.coords, dtype=float)[:-1]      # open, CCW
    k = int(np.argmin(np.hypot(ring[:, 0] - start[0], ring[:, 1] - start[1])))
    ring = np.roll(ring, -k, axis=0)
    closed = np.vstack([ring, ring[:1]])
    seg = np.linalg.norm(np.diff(closed, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = cum[-1]
    targets = np.arange(n) * total / n
    idx = np.searchsorted(cum, targets, side="right") - 1
    idx = np.clip(idx, 0, len(seg) - 1)
    frac = np.where(seg[idx] > 0, (targets - cum[idx]) / np.where(seg[idx] > 0, seg[idx], 1.0), 0.0)
    return closed[idx] + (closed[idx + 1] - closed[idx]) * frac[:, None]


def _outline_triangles(rz):
    """Triangles (indices into the outline) covering the section, for a bar's end cap."""
    import numpy as np
    from shapely.geometry import Polygon
    from trimesh.creation import triangulate_polygon
    v, f = triangulate_polygon(Polygon(rz), engine="earcut")
    # earcut keeps the input vertex order for a hole-free polygon; map back to be safe
    from scipy.spatial import cKDTree
    _, idx = cKDTree(rz).query(v)
    return idx[np.asarray(f)]


# ---- the gate ---------------------------------------------------------------------------------
def section_profile(mesh, theta_deg: float):
    """(width, thickness) of a ring mesh's section at an angle: the lobe of the cut through the
    axis (Z) on the +angle side, its z and radial extents."""
    import numpy as np
    t = math.radians(theta_deg)
    normal = [-math.sin(t), math.cos(t), 0.0]
    sec = mesh.section(plane_origin=[0.0, 0.0, 0.0], plane_normal=normal)
    if sec is None:
        return float("nan"), float("nan")
    pts = np.asarray(sec.vertices)
    r = pts[:, 0] * math.cos(t) + pts[:, 1] * math.sin(t)
    lobe = pts[r > 0]
    if len(lobe) < 3:
        return float("nan"), float("nan")
    rr = r[r > 0]
    return float(lobe[:, 2].max() - lobe[:, 2].min()), float(rr.max() - rr.min())


def check_shank(spec: ShankSpec, stl: Path, ntop_vol: float | None) -> gate.GateReport:
    """The band gate (bore, the widest width, the largest outer diameter, walls, volume vs nTop)
    plus the two checks only the design can add: the section profile at CHECK_ANGLES_DEG (the
    built width and thickness against the designed ones - a notebook that did not wrap, or wrapped
    with the wrong length, fails here) and the design volume."""
    b = spec.band
    rep = gate.check(stl, expect_inner=b.inner_diameter_mm, expect_outer=2 * b.outer_radius_mm,
                     expect_width=b.width_mm, expect_volume=ntop_vol, wall_floor=spec.wall_floor(),
                     centre="origin")                      # the box centre sits off the axis on a tapered ring
    mesh = gate.load_mesh(stl)
    worst, where, detail = 0.0, None, []
    ok = True
    for t in CHECK_ANGLES_DEG:
        w, th = section_profile(mesh, t)
        dw, dth = spec.section_extents(t)
        if math.isnan(w):
            ok = False
            detail.append(f"{t:g}°: no section")
            continue
        err = max(abs(w - dw), abs(th - dth))
        if err > worst:
            worst, where = err, (t, w, dw, th, dth)
        if err > SECTION_TOL_MM:
            ok = False
    if where:
        t, w, dw, th, dth = where
        detail.append(f"worst at {t:g}°: width {w:.3f} vs {dw:.3f}, thickness {th:.3f} vs {dth:.3f} mm")
    rep.checks.append(gate.Check("section profile", ok, f"{len(CHECK_ANGLES_DEG)} angles within ±{SECTION_TOL_MM:g} mm; " + "; ".join(detail)
                                 + ("" if ok else " - the bar was not wrapped as designed (wrap length, units or an unwrapped export?)")))
    rep.checks.append(band.design_volume_check(spec.design_volume_mm3(), ntop_vol, 2.0))
    return rep


@dataclass
class ShankResult:
    spec: ShankSpec
    stl: Path
    run: ntopcl.RunResult
    gate: gate.GateReport
    ntop_volume_mm3: float | None
    run_dir: Path | None = None
    run_id: str = ""
    delivered: Path | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return runs.status_of(self.run.ok, self.gate)

    @property
    def ok(self) -> bool:
        return self.status == gate.PASSED

    def text(self) -> str:
        lines = [self.spec.describe(), self.run.summary(), self.gate.text(), f"  status: {self.status.upper()}  run {self.run_dir}"]
        if self.delivered:
            lines.append(f"  delivered to {self.delivered}")
        lines += [f"  note: {n}" for n in self.notes]
        return "\n".join(lines)


def build(spec: ShankSpec, out_dir: Path | None = None, *, notebook: Path | None = None,
          catalog_name: str = "ring_shank", deliver: bool = False, deliver_project: str = "Bands",
          cast_metal: str | None = None) -> ShankResult:
    """Write the bar, run ring_shank.ntop through nTopCL, gate the export, deliver a PASSED part."""
    problems = spec.validate()
    if problems:
        raise ValueError("; ".join(problems))
    cat = catalog.load(catalog_name)
    nb = Path(notebook) if notebook else cat.notebook
    out_dir = Path(out_dir) if out_dir else config.out_dir() / "shank"
    stem = spec.stem
    run_dir, run_id = runs.fresh_run_dir(out_dir, stem)
    stl = run_dir / f"{stem}.stl"
    bar = run_dir / f"{stem}.bar.stl"
    spec.bar_mesh().export(str(bar))

    inputs = cat.build_inputs(spec.notebook_inputs(str(bar), str(stl)))
    started = time.time()
    run = ntopcl.run(nb, inputs, run_dir, tag=stem)
    try:
        runs.require_fresh(stl, started, "the exported mesh")
    except FileNotFoundError as e:
        raise ntopcl.NtopclError(f"notebook reported success but {e}", run) from e

    vol_entry = run.outputs.get(cat.output.get("name", "Volume"))
    ntop_vol = ntopcl.scalar_value(vol_entry) if vol_entry else None
    rep = check_shank(spec, stl, ntop_vol)
    gate.save(rep)
    result = ShankResult(spec, stl, run, rep, ntop_vol, run_dir, run_id)
    result.notes += spec.warnings()
    report = {
        "stem": stem, "spec_id": spec.spec_id, "run_id": run_id, "status": result.status, "ok": result.ok,
        "band": asdict(spec.band), "shank": {k: v for k, v in asdict(spec).items() if k not in ("band", "_cache")},
        "design": spec.design(), "inputs": spec.notebook_inputs(str(bar), str(stl)), "stl": str(stl), "bar": str(bar),
        "ntop_volume_mm3": ntop_vol, "design_volume_mm3": spec.design_volume_mm3(), "gate": rep.to_dict(),
        "ntopcl_seconds": run.seconds, "block_timings": [t.__dict__ for t in run.log.timings], "notes": result.notes,
        "notebook": runs.notebook_identity(nb), "environment": runs.environment(ntopcl.version()),
    }
    (run_dir / f"{stem}.report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    if deliver and result.ok:
        result.delivered = runs.deliver(stl, run_dir, stem, deliver_project, report, extra_files=[bar], cast_metal=cast_metal)
    elif deliver:
        result.notes.append(f"not delivered: status {result.status}")
    return result
