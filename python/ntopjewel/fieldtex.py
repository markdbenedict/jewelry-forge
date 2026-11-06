"""Field textures: nTop's own texture blocks on a band, masked to the outer face, gated by an envelope (2026-11-06).

The first: the **voronoi deboss** - nTop's `voronoi_deboss` toolkit block carves the walls of a 3-D voronoi
tessellation of the body into its surface as half-round grooves (groove width = the block's Thickness, depth =
half of it; measured 6 Nov: Thickness 0.15 gave 0.077 mm deep grooves), leaving the cells flat: a cracked-earth
/ mosaic net, cells a few millimetres across. The block textures EVERY face (bore, sides and rims as much as the
outer face), so `ring_voronoi.ntop` masks it to the outer face: the dents (band − grooved band) are kept only
inside a zone - a hollow cylinder between the rims, from just under the dome outwards - and cut from the band
(`Textured = Band − (Dents ∩ Zone)`). The grooves stop at the rim in a clean line.

The cells are nTop's (its random points, no seed input), so Python cannot rebuild the texture point for point.
What the gate holds the part to is an **envelope** (`check_fieldtex`): every built vertex inside the zone lies
between the designed surface and the groove's depth below it (no metal added, no groove deeper than designed);
every vertex outside the zone lies ON the designed section (the bore, the sides and the rims untouched: the
mask worked); the zone's face is covered by grooves (a share within bounds, and a count of the cells they
enclose: a plain band fails); the band checks; nTop's volume within [plain − zone area × depth, plain]. What
came out (deepest, share, cells, volume taken) is reported.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from . import band as bandmod
from . import catalog, config, gate, ntopcl, runs, tables, texture

TOUCHED_MM = 0.01           # a vertex further than this from the designed section has been moved by the texture
FACES = ("outer", "bore", "side", "edge")
ENVELOPE_PAD_MM = 0.015     # on top of half the Mesh Tolerance: the mesher's rounding of a groove's lip
ZONE_MARGIN_MM = 0.15       # the zone reaches this much deeper than the grooves under the dome's lowest point
MIN_COVER, MAX_COVER = 0.03, 0.6      # the share of the zone's face the grooves may take
MIN_CELLS = 4               # flat regions the grooves must enclose on the face (a plain band has one)
CELL_RASTER_MM = 0.05


@dataclass
class SectionModel:
    """The designed band section's boundary, sampled densely, each sample labelled by its face."""
    b: bandmod.BandSpec
    step: float = 0.005
    pts: np.ndarray = field(init=False)
    face: np.ndarray = field(init=False)
    polygon: object = field(init=False)

    def __post_init__(self):
        poly = self.b.design_section()
        if hasattr(poly, "geoms"):
            poly = max(poly.geoms, key=lambda g: g.area)
        self.polygon = poly
        ring = np.asarray(poly.exterior.coords)                    # (r, z)
        seg = np.diff(ring, axis=0)
        n = np.maximum(1, np.ceil(np.hypot(seg[:, 0], seg[:, 1]) / self.step).astype(int))
        pts = np.concatenate([ring[i] + np.outer(np.arange(n[i]) / n[i], seg[i]) for i in range(len(seg))])
        self.pts = pts
        half = self.b.width_mm / 2
        e = self.b.edge_round + 0.05                               # the rounded edges and a margin
        r_mid = (self.b.bore_radius_mm + self.b.outer_radius_mm) / 2
        face = np.full(len(pts), "edge", dtype=object)
        flat = np.abs(pts[:, 1]) < half - e
        face[flat & (pts[:, 0] >= r_mid)] = "outer"
        face[flat & (pts[:, 0] < r_mid)] = "bore"
        side = (np.abs(pts[:, 1]) >= half - 1e-3) & (pts[:, 0] > self.b.bore_radius_mm + e) & (pts[:, 0] < self.b.outer_radius_mm - e)
        face[side] = "side"
        self.face = face

    def signed_distance(self, r, z):
        """Distance from (r, z) to the section's boundary: − inside the metal, + outside; and the nearest face."""
        from scipy.spatial import cKDTree
        from shapely import contains_xy
        d, k = cKDTree(self.pts).query(np.column_stack([r, z]))
        inside = contains_xy(self.polygon, r, z)
        return np.where(inside, -d, d), self.face[k]

    def volume_mm3(self) -> float:
        c = self.polygon.centroid
        return 2 * math.pi * c.x * self.polygon.area

    def outer_face_area_mm2(self, z_half: float) -> float:
        """Area of the outer face within |z| <= z_half (the section's outer boundary revolved)."""
        sel = (self.face == "outer") & (np.abs(self.pts[:, 1]) <= z_half)
        p = self.pts[sel]
        if len(p) < 2:
            return 0.0
        o = np.argsort(p[:, 1])
        p = p[o]
        ds = np.hypot(np.diff(p[:, 0]), np.diff(p[:, 1]))
        r_mid = (p[1:, 0] + p[:-1, 0]) / 2
        return float(2 * math.pi * np.sum(r_mid * ds))


@dataclass
class VoronoiSpec:
    """A band with nTop's voronoi deboss on its outer face: half-round grooves along the cell walls."""
    band: bandmod.BandSpec
    groove_mm: float = 0.2                  # the groove's width (nTop's Thickness); its depth is half of it
    cells: int = 200                        # nTop's Voronoi cell count (3-D cells through the body; a few dozen show on the face)
    cell_size_mm: float = 1.0               # nTop's Feature size
    iterations: int = 3                     # nTop's Relaxation iterations (Lloyd's: evens the cells)
    weighting_mm: float = 1.0               # nTop's Spatial weighting (a length; its effect unmeasured)
    blend_mm: float = 0.0                   # nTop's Blend radius at the groove junctions
    rim_mm: float | None = None             # polished rim kept at each edge of the face; None = edge round + 0.1
    _cache: dict = field(default_factory=dict, init=False, repr=False, compare=False)

    kind = "voronoi"

    @property
    def depth_mm(self) -> float:
        """The groove's depth: a half-round of the groove's width (measured 2026-11-06)."""
        return self.groove_mm / 2.0

    @property
    def rim(self) -> float:
        return float(self.rim_mm) if self.rim_mm is not None else self.band.edge_round + 0.1

    @property
    def zone_half_width(self) -> float:
        return self.band.width_mm / 2.0 - self.rim

    @property
    def zone_inner_radius(self) -> float:
        """Just under the dome's lowest point inside the zone, less the groove and a margin: every outer-face
        groove is inside the zone, the bore is not."""
        zh = self.zone_half_width
        lowest = min(self.band.outer_radius_at(z) for z in np.linspace(-zh, zh, 41))
        return lowest - self.depth_mm - ZONE_MARGIN_MM

    def in_zone(self, r, z):
        return (np.abs(z) <= self.zone_half_width) & (r >= self.zone_inner_radius)

    def model(self) -> SectionModel:
        if "model" not in self._cache:
            self._cache["model"] = SectionModel(self.band)
        return self._cache["model"]

    def plain_volume_mm3(self) -> float:
        return self.band.design_volume_mm3()

    def zone_face_area_mm2(self) -> float:
        return self.model().outer_face_area_mm2(self.zone_half_width)

    def max_removal_mm3(self) -> float:
        """The most the grooves can take: the zone's face sunk by the groove's depth."""
        return self.zone_face_area_mm2() * self.depth_mm

    def triangles_estimate(self) -> float:
        """The plain band's surface and a little more (the grooves' walls: 2.6 M at 0.05 measured against the band's 2.4 M)."""
        return tables.mesh_triangles_estimate(self._plain_area() * 1.1, self.band.mesh_tolerance_mm)

    def _plain_area(self) -> float:
        m = self.model()
        ring = np.asarray(m.polygon.exterior.coords)
        ds = np.hypot(np.diff(ring[:, 0]), np.diff(ring[:, 1]))
        return float(2 * math.pi * np.sum((ring[1:, 0] + ring[:-1, 0]) / 2 * ds))

    # ---- the notebook ---------------------------------------------------------------------------
    def notebook_inputs(self, output_path: str) -> dict:
        v = self.band.notebook_inputs(output_path)
        v.pop("Output Path")
        v.update({"Cell Size": self.cell_size_mm, "Cells": int(self.cells), "Iterations": int(self.iterations),
                  "Groove": self.groove_mm, "Weighting": self.weighting_mm, "Blend": self.blend_mm,
                  "Zone Z Top": round(self.zone_half_width, 4), "Zone Z Bottom": -round(self.zone_half_width, 4),
                  "Zone Inner Radius": round(self.zone_inner_radius, 4),
                  "Output Path": output_path})
        return v

    # ---- identity, checks ---------------------------------------------------------------------
    def design(self) -> dict:
        d = self.band.design()
        d.update({"texture": self.kind, "groove": self.groove_mm, "cells": int(self.cells), "cell_size": self.cell_size_mm,
                  "iterations": int(self.iterations), "weighting": self.weighting_mm, "blend": self.blend_mm,
                  "rim": round(self.rim, 4)})
        return d

    @property
    def spec_id(self) -> str:
        return runs.spec_id(self.design())

    @property
    def stem(self) -> str:
        b = self.band
        return (f"ring_texture_{self.kind}_{b.profile}_{b.label}_w{b.width_mm:g}_t{b.thickness_mm:g}"
                f"_c{int(self.cells)}g{self.groove_mm:g}_{self.spec_id}")

    def validate(self) -> list[str]:
        p = list(self.band.validate())
        if p:
            return p
        floor = tables.FLOORS["texture_depth"]
        if self.depth_mm < floor - 1e-9:
            p.append(f"a {self.groove_mm:g} mm groove is {self.depth_mm:.3f} mm deep (half its width); at least {floor:g} "
                     f"(--groove {2 * floor:g} or more)")
        if self.groove_mm > 1.0:
            p.append(f"groove {self.groove_mm:g} mm: at most 1.0 (wider is a channel, not a texture)")
        if not 10 <= int(self.cells) <= 5000:
            p.append(f"cells {self.cells}: 10..5000")
        if not 0 <= int(self.iterations) <= 20:
            p.append(f"iterations {self.iterations}: 0..20")
        if not 0.05 <= self.cell_size_mm <= 20:
            p.append(f"cell size {self.cell_size_mm:g} mm: 0.05..20")
        if not 0 <= self.blend_mm <= 1:
            p.append(f"blend {self.blend_mm:g} mm: 0..1")
        if self.rim < self.band.edge_round - 1e-9:
            p.append(f"rim {self.rim:g} mm: at least the edge round ({self.band.edge_round:g}), where the face ends")
        if self.zone_half_width < 0.5:
            p.append(f"the rims ({self.rim:g} each) leave {2 * self.zone_half_width:.2f} mm of face: at least 1.0")
        if p:
            return p
        thin = self.band.thickness_at(self.zone_half_width) - self.depth_mm
        if thin < tables.FLOORS["wall_good"] - 1e-9:
            p.append(f"under a groove at the zone's edge the wall is {thin:.2f} mm; at least {tables.FLOORS['wall_good']:g} "
                     f"(a thicker band, a narrower groove)")
        voxel = self.band.mesh_tolerance_mm / 2
        if self.groove_mm < 3 * voxel:
            p.append(f"a {self.groove_mm:g} mm groove spans under 3 voxels at Mesh Tolerance {self.band.mesh_tolerance_mm:g} "
                     f"(voxel {voxel:g}); --tolerance {self.groove_mm / 1.5:.3g} or finer")
        tri = self.triangles_estimate()
        if tri > texture.MAX_TRIANGLES:
            p.append(f"about {tri / 1e6:.1f} M triangles at Mesh Tolerance {self.band.mesh_tolerance_mm:g}: past the gate's "
                     f"{texture.MAX_TRIANGLES / 1e6:g} M limit (a coarser --tolerance)")
        return p

    def wall_floor(self) -> float:
        return tables.FLOORS["wall_marginal"]

    def describe(self) -> str:
        b = self.band
        return (f"{self.stem}: {b.profile} {b.label}, inner Ø {b.inner_diameter_mm:.3f}, {b.width_mm:g} x {b.thickness_mm:g}\n"
                f"  voronoi deboss (nTop's): {self.cells} cells, feature size {self.cell_size_mm:g}, {self.iterations} relaxations, "
                f"grooves {self.groove_mm:g} wide / {self.depth_mm:g} deep along the cell walls, within ±{self.zone_half_width:.2f} "
                f"of the mid-plane (rims {self.rim:.2f}); zone inner radius {self.zone_inner_radius:.2f}\n"
                f"  plain band {self.plain_volume_mm3():.2f} mm³, the grooves take at most {self.max_removal_mm3():.2f} "
                f"(zone face {self.zone_face_area_mm2():.1f} mm²); about {self.triangles_estimate() / 1e6:.1f} M triangles at "
                f"Mesh Tolerance {b.mesh_tolerance_mm:g}")


# ---- the envelope gate ----------------------------------------------------------------------------------------
def measure_texture(spec: VoronoiSpec, mesh) -> dict:
    """Every vertex of the built STL against the designed section: inside the zone and outside it."""
    v = np.asarray(mesh.vertices)
    r = np.hypot(v[:, 0], v[:, 1])
    z = v[:, 2]
    d, face = spec.model().signed_distance(r, z)
    zone = spec.in_zone(r, z)
    out = {"zone_vertices": int(zone.sum()), "outside_vertices": int((~zone).sum())}
    if zone.any():
        dz = d[zone]
        out.update({"zone_highest_mm": float(dz.max()), "zone_deepest_mm": float(-dz.min()),
                    "zone_touched_vertices": float((np.abs(dz) > TOUCHED_MM).mean())})
    if (~zone).any():
        do = d[~zone]
        out.update({"outside_worst_mm": float(np.abs(do).max()), "outside_p999_mm": float(np.percentile(np.abs(do), 99.9))})
    # the zone's face by area: triangles, and a raster of the untouched regions (the cells)
    tc = mesh.triangles_center
    rc, zc = np.hypot(tc[:, 0], tc[:, 1]), tc[:, 2]
    zc_in = spec.in_zone(rc, zc)
    if zc_in.any():
        dc, _ = spec.model().signed_distance(rc[zc_in], zc[zc_in])
        a = mesh.area_faces[zc_in]
        out["zone_touched"] = float(a[np.abs(dc) > TOUCHED_MM].sum() / a.sum())
        out["zone_mean_depth_mm"] = float(-np.average(dc, weights=a))
        th = np.concatenate([np.arctan2(tc[zc_in, 1], tc[zc_in, 0]), np.arctan2(v[zone, 1], v[zone, 0])])
        out.update(count_cells(th, np.concatenate([zc[zc_in], z[zone]]), np.concatenate([dc, d[zone]]), spec))
    return out


def count_cells(theta, z, d, spec: VoronoiSpec, cell=CELL_RASTER_MM) -> dict:
    """The flat regions the grooves enclose on the zone's face: a raster (arc, z) painted by the touched points
    (vertices and triangle centres, widened by a cell), the untouched connected components counted (scipy.ndimage),
    the seam at theta = 0 joined, slivers under 0.05 mm² dropped."""
    from scipy.ndimage import binary_dilation, label
    R = spec.band.outer_radius_mm
    arc = (theta % (2 * math.pi)) * R
    n_arc = max(8, int(round(2 * math.pi * R / cell)))
    zh = spec.zone_half_width
    n_z = max(4, int(round(2 * zh / cell)))
    ai = np.minimum((arc / (2 * math.pi * R) * n_arc).astype(int), n_arc - 1)
    zi = np.clip(((z + zh) / (2 * zh) * n_z).astype(int), 0, n_z - 1)
    touched = np.zeros((n_z, n_arc), dtype=bool)
    hit = np.abs(d) > TOUCHED_MM
    touched[zi[hit], ai[hit]] = True
    touched = binary_dilation(np.concatenate([touched[:, -1:], touched, touched[:, :1]], axis=1))[:, 1:-1]
    flat = ~touched
    lab, n = label(flat)
    if n == 0:
        return {"cells_on_face": 0}
    # join regions split by the seam (first and last columns)
    pairs = {(int(a), int(b)) for a, b in zip(lab[:, 0], lab[:, -1]) if a and b and a != b}
    sizes = np.bincount(lab.ravel())[1:]
    for a, b in pairs:
        sizes[max(a, b) - 1] += sizes[min(a, b) - 1]
        sizes[min(a, b) - 1] = 0
    big = sizes[sizes * cell * cell > 0.05]
    return {"cells_on_face": int(len(big)), "cell_mm2": float(big.mean() * cell * cell) if len(big) else None}


def check_fieldtex(spec: VoronoiSpec, stl: Path, ntop_vol: float | None) -> gate.GateReport:
    """The band gate (the cells are flat on the designed surface: the outer Ø is the plain band's), then the envelope."""
    b = spec.band
    tol = float(b.mesh_tolerance_mm)
    rep = gate.check(stl, expect_inner=b.inner_diameter_mm, expect_outer=2 * b.outer_radius_mm, expect_width=b.width_mm,
                     expect_volume=ntop_vol, wall_floor=spec.wall_floor(), centre="origin")
    mesh = gate.load_mesh(stl)
    m = measure_texture(spec, mesh)
    rep.texture = m
    pad = tol / 2 + ENVELOPE_PAD_MM
    depth = spec.depth_mm
    if "zone_highest_mm" in m:
        ok = m["zone_highest_mm"] <= pad and m["zone_deepest_mm"] <= depth + pad
        rep.checks.append(gate.Check("texture envelope", ok,
                                     f"inside the zone the built surface lies {m['zone_highest_mm']:+.3f} .. -{m['zone_deepest_mm']:.3f} mm "
                                     f"from the design (allowed +{pad:.3f} .. -{depth + pad:.3f}: no metal added, no groove deeper "
                                     f"than {depth:g})"))
    else:
        rep.checks.append(gate.incomplete("texture envelope", "no vertex inside the zone"))
    if "outside_worst_mm" in m:
        rep.checks.append(gate.Check("untouched outside the zone", m["outside_worst_mm"] <= pad,
                                     f"the bore, the sides and the rims lie within {m['outside_worst_mm']:.3f} mm of the design "
                                     f"(allowed {pad:.3f}): the mask {'held' if m['outside_worst_mm'] <= pad else 'did not hold'}"))
    cover = m.get("zone_touched")
    if cover is None:
        rep.checks.append(gate.incomplete("texture coverage", "no triangle inside the zone"))
    else:
        cells = m.get("cells_on_face", 0)
        ok = MIN_COVER <= cover <= MAX_COVER and cells >= MIN_CELLS
        across = f", about {math.sqrt(m['cell_mm2']):.1f} mm across" if m.get("cell_mm2") else ""
        rep.checks.append(gate.Check("texture coverage", ok,
                                     f"grooves over {cover:.0%} of the zone's face (allowed {MIN_COVER:.0%}..{MAX_COVER:.0%}), "
                                     f"{cells} cells enclosed{across} (at least {MIN_CELLS}); mean depth over the face "
                                     f"{m.get('zone_mean_depth_mm', 0):.3f} mm"))
    plain = spec.plain_volume_mm3()
    most = spec.max_removal_mm3()
    if ntop_vol is None:
        rep.checks.append(gate.incomplete("design volume", "nTop reported no volume; the notebook cannot be checked against the design"))
    else:
        lo, hi = plain - most - plain * 0.005, plain + plain * 0.005
        taken = plain - ntop_vol
        rep.checks.append(gate.Check("design volume", lo <= ntop_vol <= hi,
                                     f"nTop {ntop_vol:.2f} mm³: the plain band {plain:.2f} less {taken:.2f} "
                                     f"({taken / plain:+.2%}; the grooves may take up to {most:.2f}, the zone's face sunk by {depth:g})"))
    return rep


@dataclass
class FieldTextureResult(bandmod.BandResult):
    def text(self) -> str:
        s = self.spec
        head = (f"Voronoi {s.band.profile} {s.band.label}: {s.cells} cells, grooves {s.groove_mm:g} wide, "
                f"{s.band.width_mm:g} x {s.band.thickness_mm:g} -> {self.stl.name}")
        lines = [head, self.run.summary(), self.gate.text(), f"  status: {self.status.upper()}  run {self.run_dir}"]
        if self.delivered:
            lines.append(f"  delivered to {self.delivered}")
        lines += [f"  note: {n}" for n in self.notes]
        return "\n".join(lines)


def build(spec: VoronoiSpec, out_dir: Path | None = None, *, notebook: Path | None = None, catalog_name: str = "ring_voronoi",
          deliver: bool = False, deliver_project: str = "Bands", cast_metal: str | None = None) -> FieldTextureResult:
    """Run ring_voronoi.ntop through nTopCL, gate the textured band by its envelope (check_fieldtex)."""
    problems = spec.validate()
    if problems:
        raise ValueError("; ".join(problems))
    cat = catalog.load(catalog_name)
    nb = Path(notebook) if notebook else cat.notebook
    built_notes = runs.require_built(cat, nb) if not notebook else []
    out_dir = Path(out_dir) if out_dir else config.out_dir() / "texture"
    stem = spec.stem
    run_dir, run_id = runs.fresh_run_dir(out_dir, stem)
    stl = run_dir / f"{stem}.stl"
    values = spec.notebook_inputs(str(stl))
    started = time.time()
    run = ntopcl.run(nb, cat.build_inputs(values), run_dir, tag=stem)
    try:
        runs.require_fresh(stl, started, "the exported mesh")
    except FileNotFoundError as e:
        raise ntopcl.NtopclError(f"notebook reported success but {e}", run) from e
    vol_entry = run.outputs.get(cat.output.get("name", "Volume"))
    ntop_vol = ntopcl.scalar_value(vol_entry) if vol_entry else None
    rep = check_fieldtex(spec, stl, ntop_vol)
    gate.save(rep)
    result = FieldTextureResult(spec, stl, run, rep, ntop_vol, run_dir, run_id)
    result.notes += built_notes + spec.band.warnings()
    report = {
        "stem": stem, "spec_id": spec.spec_id, "run_id": run_id, "status": result.status, "ok": result.ok,
        "spec": {**asdict(spec.band), "texture": spec.design()}, "design": spec.design(), "inputs": values, "stl": str(stl),
        "ntop_volume_mm3": ntop_vol, "plain_volume_mm3": spec.plain_volume_mm3(), "max_removal_mm3": spec.max_removal_mm3(),
        "texture": getattr(rep, "texture", {}),
        "gate": rep.to_dict(), "ntopcl_seconds": run.seconds, "block_timings": [t.__dict__ for t in run.log.timings],
        "notes": result.notes, "notebook": runs.notebook_identity(nb), "environment": runs.environment(ntopcl.version()),
    }
    (run_dir / f"{stem}.report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    if deliver and result.ok:
        result.delivered = runs.deliver(stl, run_dir, stem, deliver_project, report, cast_metal=cast_metal)
    elif deliver:
        result.notes.append(f"not delivered: status {result.status}")
    return result
