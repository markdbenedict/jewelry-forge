"""Field textures: nTop's own texture blocks on a band, masked to the outer face, gated by an envelope (2026-11-06).

nTop's toolkits carry textures that take any implicit body and texture EVERY face of it - the bore, the sides
and the rims as much as the outer face (measured 6 Nov, `texture_probe`). Each product here puts one of them on
the profiled band and masks it to the outer face between polished rims (`ring_<kind>.ntop`: the dents (band −
textured) are kept inside a zone - a hollow cylinder between the rims, from just under the dome outwards - and
cut from the band; a texture that also adds metal has its bumps kept the same way and united). The texture stops
at the rims in a clean line.

The kinds, with what the probe measured of nTop's blocks:
  voronoi   `voronoi_deboss`: the walls of a 3-D voronoi tessellation carved as half-round grooves (groove width =
            Thickness, depth = half of it: 0.2 -> 0.102 in the real band), the cells flat between - a cracked-earth
            / mosaic net, about a hundred cells of a millimetre on a 4 mm band at 200 cells
  frost     `surface_roughness`: simplex noise both ways, ±amplitude (0.1 -> ±0.085), features about a fifth of
            the noise's period - a satin / sandblasted frost
  pitted    `simplex_noise_deboss`: the same noise cut in only (0.1 -> 0.082 deep), the rest of the face flat
  cellular  `cellular_noise_deboss`: soft dimples at the cells of a Worley noise, deep - the "Depth factor" is not a
            depth: 0.1 at a 2 mm period cut 0.68 (tables: cellular_noise_depth_per_factor_per_mm)
  ribbed    `triangle_wave_texture`: the surface displaced OUTWARD along its normal by a triangle wave of z -
            troughs on the design, peaks three times the "height" above it (tables: triangle_wave_peak_per_height)
            - so the band is eroded by the rib depth first and the ribs stand back up to the design surface
The noises' frequencies are per metre (nTop's SI inside): `grain_mm`, the noise's period, is 1000 / frequency.

The textures' randomness is nTop's (no seed on the voronoi; the noises take one), so Python cannot rebuild them
point for point. What the gate holds the part to is an **envelope** (`check_fieldtex`): every built vertex inside
the zone lies between the designed surface (+ the texture's rise, for one that adds metal) and the texture's
depth below it; every vertex outside the zone lies ON the designed section (the bore, the sides and the rims
untouched: the mask worked); the zone's face is covered (a share within the kind's bounds; for the voronoi also a
count of the cells the grooves enclose); the band checks; nTop's volume within [plain − zone face x depth, plain
+ zone face x rise]. What came out (deepest, highest, share, cells, volume taken) is reported.
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
ZONE_MARGIN_MM = 0.15       # the zone reaches this much deeper than the texture under the dome's lowest point
MIN_CELLS = 4               # flat regions the voronoi's grooves must enclose on the face (a plain band has one)
CELL_RASTER_MM = 0.05
NOISE_MAX_GRAIN_MM = 20.0
KINDS = ("voronoi", "frost", "pitted", "cellular", "ribbed")


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

    def area_mm2(self) -> float:
        ring = np.asarray(self.polygon.exterior.coords)
        ds = np.hypot(np.diff(ring[:, 0]), np.diff(ring[:, 1]))
        return float(2 * math.pi * np.sum((ring[1:, 0] + ring[:-1, 0]) / 2 * ds))


# ---- the specs ---------------------------------------------------------------------------------------------
@dataclass
class FieldTextureSpec:
    """What every field texture shares: the band, the polished rims, the mask zone, the envelope's bookkeeping.
    A kind sets `kind`, `adds_metal`, `coverage` (the share of the zone's face it must touch), `counts_cells`,
    and gives `depth_mm` (how deep it cuts), `rise_mm` (how high it stands, 0 for a deboss), `texture_inputs`,
    `texture_design`, `tag`, `texture_problems` and `texture_line`."""
    band: bandmod.BandSpec
    rim_mm: float | None = None             # polished rim kept at each edge of the face; None = edge round + 0.1
    _cache: dict = field(default_factory=dict, init=False, repr=False, compare=False)

    kind = ""
    adds_metal = False
    counts_cells = False
    coverage = (0.03, 1.0)

    # -- the zone --
    @property
    def rim(self) -> float:
        return float(self.rim_mm) if self.rim_mm is not None else self.band.edge_round + 0.1

    @property
    def zone_half_width(self) -> float:
        return self.band.width_mm / 2.0 - self.rim

    @property
    def zone_inner_radius(self) -> float:
        """Just under the dome's lowest point inside the zone, less the texture's depth and a margin: every
        outer-face dent is inside the zone, the bore is not."""
        zh = self.zone_half_width
        lowest = min(self.band.outer_radius_at(z) for z in np.linspace(-zh, zh, 41))
        return lowest - self.depth_mm - ZONE_MARGIN_MM

    def in_zone(self, r, z, pad: float = 0.0):
        """Inside the mask zone; `pad` widens it (the vertices on the zone's cut walls belong to neither side)."""
        return (np.abs(z) <= self.zone_half_width + pad) & (r >= self.zone_inner_radius - pad)

    def model(self) -> SectionModel:
        if "model" not in self._cache:
            self._cache["model"] = SectionModel(self.band)
        return self._cache["model"]

    @property
    def notebook_name(self) -> str:
        return f"ring_{self.kind}"

    # -- what the texture may do --
    @property
    def depth_mm(self) -> float:
        raise NotImplementedError

    @property
    def rise_mm(self) -> float:
        return 0.0

    def plain_volume_mm3(self) -> float:
        return self.band.design_volume_mm3()

    def zone_face_area_mm2(self) -> float:
        return self.model().outer_face_area_mm2(self.zone_half_width)

    def max_removal_mm3(self) -> float:
        """The most the texture can take: the zone's face sunk by its depth."""
        return self.zone_face_area_mm2() * self.depth_mm

    def max_addition_mm3(self) -> float:
        return self.zone_face_area_mm2() * self.rise_mm

    def triangles_estimate(self) -> float:
        """The plain band's surface and a little more (the voronoi's groove walls: 2.6 M at 0.05 against the band's 2.4 M)."""
        return tables.mesh_triangles_estimate(self.model().area_mm2() * 1.1, self.band.mesh_tolerance_mm)

    # -- the notebook --
    def zone_inputs(self) -> dict:
        return {"Zone Z Top": round(self.zone_half_width, 4), "Zone Z Bottom": -round(self.zone_half_width, 4),
                "Zone Inner Radius": round(self.zone_inner_radius, 4)}

    def texture_inputs(self) -> dict:
        raise NotImplementedError

    def notebook_inputs(self, output_path: str) -> dict:
        v = self.band.notebook_inputs(output_path)
        v.pop("Output Path")
        v.update(self.texture_inputs())
        v.update(self.zone_inputs())
        v["Output Path"] = output_path
        return v

    # -- identity --
    def texture_design(self) -> dict:
        raise NotImplementedError

    def design(self) -> dict:
        d = self.band.design()
        d.update({"texture": self.kind, "rim": round(self.rim, 4)})
        d.update(self.texture_design())
        return d

    @property
    def spec_id(self) -> str:
        return runs.spec_id(self.design())

    @property
    def tag(self) -> str:
        raise NotImplementedError

    @property
    def stem(self) -> str:
        b = self.band
        return f"ring_texture_{self.kind}_{b.profile}_{b.label}_w{b.width_mm:g}_t{b.thickness_mm:g}_{self.tag}_{self.spec_id}"

    # -- checks --
    def texture_problems(self) -> list[str]:
        return []

    def validate(self) -> list[str]:
        p = list(self.band.validate())
        if p:
            return p
        p += self.texture_problems()
        if self.rim < self.band.edge_round - 1e-9:
            p.append(f"rim {self.rim:g} mm: at least the edge round ({self.band.edge_round:g}), where the face ends")
        if self.zone_half_width < 0.5:
            p.append(f"the rims ({self.rim:g} each) leave {2 * self.zone_half_width:.2f} mm of face: at least 1.0")
        if p:
            return p
        thin = self.band.thickness_at(self.zone_half_width) - self.depth_mm
        if thin < tables.FLOORS["wall_good"] - 1e-9:
            p.append(f"under the texture at the zone's edge the wall is {thin:.2f} mm; at least {tables.FLOORS['wall_good']:g} "
                     f"(a thicker band, a shallower texture)")
        tri = self.triangles_estimate()
        if tri > texture.MAX_TRIANGLES:
            p.append(f"about {tri / 1e6:.1f} M triangles at Mesh Tolerance {self.band.mesh_tolerance_mm:g}: past the gate's "
                     f"{texture.MAX_TRIANGLES / 1e6:g} M limit (a coarser --tolerance)")
        return p

    def wall_floor(self) -> float:
        return tables.FLOORS["wall_marginal"]

    def texture_line(self) -> str:
        raise NotImplementedError

    def describe(self) -> str:
        b = self.band
        take = f"take at most {self.max_removal_mm3():.2f}"
        if self.adds_metal:
            take += f" and add at most {self.max_addition_mm3():.2f}"
        return (f"{self.stem}: {b.profile} {b.label}, inner Ø {b.inner_diameter_mm:.3f}, {b.width_mm:g} x {b.thickness_mm:g}\n"
                f"  {self.texture_line()}, within ±{self.zone_half_width:.2f} of the mid-plane (rims {self.rim:.2f}); "
                f"zone inner radius {self.zone_inner_radius:.2f}\n"
                f"  plain band {self.plain_volume_mm3():.2f} mm³, the texture may {take} (zone face "
                f"{self.zone_face_area_mm2():.1f} mm²); about {self.triangles_estimate() / 1e6:.1f} M triangles at "
                f"Mesh Tolerance {b.mesh_tolerance_mm:g}")


def _depth_floor_problem(depth: float, what: str) -> list[str]:
    floor = tables.FLOORS["texture_depth"]
    return [f"{what} {depth:.3f} mm deep; at least {floor:g}"] if depth < floor - 1e-9 else []


@dataclass
class VoronoiSpec(FieldTextureSpec):
    """A band with nTop's voronoi deboss on its outer face: half-round grooves along the cell walls."""
    groove_mm: float = 0.2                  # the groove's width (nTop's Thickness); its depth is half of it
    cells: int = 200                        # nTop's Voronoi cell count (3-D cells through the body; about a hundred show on a 4 mm face)
    cell_size_mm: float = 1.0               # nTop's Feature size
    iterations: int = 3                     # nTop's Relaxation iterations (Lloyd's: evens the cells)
    weighting_mm: float = 1.0               # nTop's Spatial weighting (a length; its effect unmeasured)
    blend_mm: float = 0.0                   # nTop's Blend radius at the groove junctions

    kind = "voronoi"
    counts_cells = True
    coverage = (0.03, 0.6)

    @property
    def depth_mm(self) -> float:
        """The groove's depth: a half-round of the groove's width (measured 2026-11-06: 0.2 -> 0.102)."""
        return self.groove_mm / 2.0

    def texture_inputs(self) -> dict:
        return {"Cell Size": self.cell_size_mm, "Cells": int(self.cells), "Iterations": int(self.iterations),
                "Groove": self.groove_mm, "Weighting": self.weighting_mm, "Blend": self.blend_mm}

    def texture_design(self) -> dict:
        return {"groove": self.groove_mm, "cells": int(self.cells), "cell_size": self.cell_size_mm,
                "iterations": int(self.iterations), "weighting": self.weighting_mm, "blend": self.blend_mm}

    @property
    def tag(self) -> str:
        return f"c{int(self.cells)}g{self.groove_mm:g}"

    def texture_problems(self) -> list[str]:
        p = []
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
        voxel = self.band.mesh_tolerance_mm / 2
        if self.groove_mm < 3 * voxel:
            p.append(f"a {self.groove_mm:g} mm groove spans under 3 voxels at Mesh Tolerance {self.band.mesh_tolerance_mm:g} "
                     f"(voxel {voxel:g}); --tolerance {self.groove_mm / 1.5:.3g} or finer")
        return p

    def texture_line(self) -> str:
        return (f"voronoi deboss (nTop's): {self.cells} cells, feature size {self.cell_size_mm:g}, {self.iterations} relaxations, "
                f"grooves {self.groove_mm:g} wide / {self.depth_mm:g} deep along the cell walls")


NOISE_KINDS = {
    # kind: (nTop's block, what it does, adds metal, the coverage it must reach)
    "frost": ("surface_roughness", "simplex noise both ways", True, (0.3, 1.0)),
    "pitted": ("simplex_noise_deboss", "simplex noise cut in only", False, (0.1, 1.0)),
    "cellular": ("cellular_noise_deboss", "soft dimples at the cells of a Worley noise", False, (0.5, 1.0)),
}


@dataclass
class NoiseSpec(FieldTextureSpec):
    """A band with one of nTop's noise textures on its outer face: `frost` (surface roughness, ± depth), `pitted`
    (simplex deboss, cut in only) or `cellular` (cellular noise deboss, soft dimples). `grain_mm` is the noise's
    period (nTop's frequency is per metre: 1000 / grain); `depth_mm` the amplitude - what the texture cuts (and,
    for the frost, rises); `seed` the noise's."""
    noise: str = "frost"
    grain_mm: float = 2.0
    amplitude_mm: float = 0.1               # what the noise cuts (and, for the frost, rises)
    seed: int = 1

    @property
    def kind(self) -> str:          # type: ignore[override]
        return self.noise

    @property
    def adds_metal(self) -> bool:   # type: ignore[override]
        return NOISE_KINDS[self.noise][2]

    @property
    def coverage(self):             # type: ignore[override]
        return NOISE_KINDS[self.noise][3]

    @property
    def depth_mm(self) -> float:
        return float(self.amplitude_mm)

    @property
    def rise_mm(self) -> float:
        return float(self.amplitude_mm) if self.adds_metal else 0.0

    @property
    def frequency(self) -> int:
        """nTop's Frequency, per metre: the noise's period in metres is 1 / f."""
        return max(1, int(round(1000.0 / self.grain_mm)))

    @property
    def cellular_factor(self) -> float:
        """The cellular noise's "Depth factor" (a length) for the wanted depth: the deepest dimple is about
        factor x cellular_noise_depth_per_factor_per_mm x the period (tables; one measurement)."""
        return self.depth_mm / (tables.SETTINGS["cellular_noise_depth_per_factor_per_mm"] * self.grain_mm)

    def texture_inputs(self) -> dict:
        if self.noise == "cellular":
            return {"Grain": self.grain_mm, "Factor": round(self.cellular_factor, 6), "Seed": int(self.seed)}
        return {"Frequency": self.frequency, "Amplitude": self.depth_mm, "Seed": int(self.seed)}

    def texture_design(self) -> dict:
        return {"grain": self.grain_mm, "depth": self.depth_mm, "seed": int(self.seed)}

    @property
    def tag(self) -> str:
        return f"g{self.grain_mm:g}d{self.depth_mm:g}s{int(self.seed)}"

    def texture_problems(self) -> list[str]:
        p = [] if self.noise in NOISE_KINDS else [f"noise {self.noise!r}: one of {', '.join(NOISE_KINDS)}"]
        if p:
            return p
        p += _depth_floor_problem(self.depth_mm, f"the {self.noise}'s amplitude makes the texture")
        if self.depth_mm > 0.5:
            p.append(f"amplitude {self.depth_mm:g} mm: at most 0.5 (deeper is carving, not a texture)")
        if not 0.2 <= self.grain_mm <= NOISE_MAX_GRAIN_MM:
            p.append(f"grain {self.grain_mm:g} mm: 0.2..{NOISE_MAX_GRAIN_MM:g} (the noise's period)")
        voxel = self.band.mesh_tolerance_mm / 2
        if self.grain_mm < 8 * voxel:
            p.append(f"a {self.grain_mm:g} mm grain spans under 8 voxels at Mesh Tolerance {self.band.mesh_tolerance_mm:g}: "
                     f"--tolerance {self.grain_mm / 4:.3g} or finer")
        if self.grain_mm > self.band.width_mm * 2:
            p.append(f"grain {self.grain_mm:g} mm on a {self.band.width_mm:g} mm band: the noise would be a few blotches "
                     f"(at most twice the width)")
        return p

    def texture_line(self) -> str:
        block, what, adds, _ = NOISE_KINDS[self.noise]
        amp = f"±{self.depth_mm:g} mm" if adds else f"{self.depth_mm:g} mm deep"
        extra = f", Depth factor {self.cellular_factor:.4f}" if self.noise == "cellular" else ""
        return f"{self.noise} ({block}, nTop's: {what}) {amp}, grain {self.grain_mm:g} mm (frequency {self.frequency} per metre), seed {self.seed}{extra}"


@dataclass
class RibbedSpec(FieldTextureSpec):
    """A band with nTop's triangle wave on its outer face: ribs round the ring (the wave runs along the ring axis),
    `rib_mm` apart, `depth_mm` deep. The wave stands outward, so the band is eroded by the depth first and the
    peaks come back up to the design surface (the wave's height input is the depth / triangle_wave_peak_per_height)."""
    rib_mm: float = 0.5
    rib_depth_mm: float = 0.2

    kind = "ribbed"
    coverage = (0.5, 1.0)

    @property
    def depth_mm(self) -> float:
        return float(self.rib_depth_mm)

    @property
    def wave_height(self) -> float:
        return self.depth_mm / tables.SETTINGS["triangle_wave_peak_per_height"]

    def texture_inputs(self) -> dict:
        return {"Rib Spacing": self.rib_mm, "Wave Height": round(self.wave_height, 6), "Erosion": -self.depth_mm}

    def texture_design(self) -> dict:
        return {"rib": self.rib_mm, "depth": self.depth_mm}

    @property
    def tag(self) -> str:
        return f"r{self.rib_mm:g}d{self.depth_mm:g}"

    def texture_problems(self) -> list[str]:
        p = _depth_floor_problem(self.depth_mm, "the ribs are")
        if self.depth_mm > 0.5:
            p.append(f"rib depth {self.depth_mm:g} mm: at most 0.5")
        if not 0.2 <= self.rib_mm <= 5.0:
            p.append(f"rib spacing {self.rib_mm:g} mm: 0.2..5")
        voxel = self.band.mesh_tolerance_mm / 2
        if self.rib_mm < 6 * voxel:
            p.append(f"ribs {self.rib_mm:g} mm apart span under 6 voxels at Mesh Tolerance {self.band.mesh_tolerance_mm:g}: "
                     f"--tolerance {self.rib_mm / 3:.3g} or finer")
        return p

    def texture_line(self) -> str:
        return (f"ribbed (triangle_wave_texture, nTop's): ribs {self.rib_mm:g} mm apart round the ring, {self.depth_mm:g} deep "
                f"(the band eroded by {self.depth_mm:g}, the wave's height {self.wave_height:.4f})")


def make_spec(kind: str, band: bandmod.BandSpec, **kw) -> FieldTextureSpec:
    """A spec by kind: voronoi (groove_mm, cells, ...), frost / pitted / cellular (grain_mm, amplitude_mm, seed), ribbed
    (rib_mm, rib_depth_mm)."""
    if kind == "voronoi":
        return VoronoiSpec(band, **kw)
    if kind in NOISE_KINDS:
        return NoiseSpec(band, noise=kind, **kw)
    if kind == "ribbed":
        return RibbedSpec(band, **kw)
    raise ValueError(f"texture kind {kind!r}: one of {', '.join(KINDS)}")


# ---- the envelope gate ----------------------------------------------------------------------------------------
def measure_texture(spec: FieldTextureSpec, mesh) -> dict:
    """Every vertex of the built STL against the designed section: inside the zone and outside it (the vertices on
    the zone's cut walls, within half a voxel of its edge, belong to neither)."""
    v = np.asarray(mesh.vertices)
    r = np.hypot(v[:, 0], v[:, 1])
    z = v[:, 2]
    d, face = spec.model().signed_distance(r, z)
    zone = spec.in_zone(r, z)
    pad = spec.band.mesh_tolerance_mm / 2
    outside = ~spec.in_zone(r, z, pad)
    out = {"zone_vertices": int(zone.sum()), "outside_vertices": int(outside.sum())}
    if zone.any():
        dz = d[zone]
        out.update({"zone_highest_mm": float(dz.max()), "zone_deepest_mm": float(-dz.min()),
                    "zone_touched_vertices": float((np.abs(dz) > TOUCHED_MM).mean())})
    if outside.any():
        do = d[outside]
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
        if spec.counts_cells:
            th = np.concatenate([np.arctan2(tc[zc_in, 1], tc[zc_in, 0]), np.arctan2(v[zone, 1], v[zone, 0])])
            out.update(count_cells(th, np.concatenate([zc[zc_in], z[zone]]), np.concatenate([dc, d[zone]]), spec))
    return out


def count_cells(theta, z, d, spec: FieldTextureSpec, cell=CELL_RASTER_MM) -> dict:
    """The flat regions the grooves enclose on the zone's face: a raster (arc, z) painted by the touched points
    (vertices and triangle centres, widened by a cell), the untouched connected components counted (scipy.ndimage),
    the seam at theta = 0 joined, slivers under 0.05 mm² dropped. The real voronoi band (6 Nov): 114 cells of 1.1 mm²."""
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
    pairs = {(int(a), int(b)) for a, b in zip(lab[:, 0], lab[:, -1]) if a and b and a != b}
    sizes = np.bincount(lab.ravel())[1:]
    for a, b in pairs:
        sizes[max(a, b) - 1] += sizes[min(a, b) - 1]
        sizes[min(a, b) - 1] = 0
    big = sizes[sizes * cell * cell > 0.05]
    return {"cells_on_face": int(len(big)), "cell_mm2": float(big.mean() * cell * cell) if len(big) else None}


def check_fieldtex(spec: FieldTextureSpec, stl: Path, ntop_vol: float | None) -> gate.GateReport:
    """The band gate (a deboss leaves the designed surface where it does not cut, so the outer Ø is the plain band's;
    a texture that adds metal may stand up to its rise above it), then the envelope."""
    b = spec.band
    tol = float(b.mesh_tolerance_mm)
    rise = spec.rise_mm
    rep = gate.check(stl, expect_inner=b.inner_diameter_mm, expect_outer=2 * b.outer_radius_mm + 2 * rise, expect_width=b.width_mm,
                     expect_volume=ntop_vol, wall_floor=spec.wall_floor(), centre="origin",
                     tol_mm=max(0.05, rise + 0.02) if rise else 0.05)
    mesh = gate.load_mesh(stl)
    m = measure_texture(spec, mesh)
    rep.texture = m
    pad = tol / 2 + ENVELOPE_PAD_MM
    depth = spec.depth_mm
    if "zone_highest_mm" in m:
        ok = m["zone_highest_mm"] <= rise + pad and m["zone_deepest_mm"] <= depth + pad
        rep.checks.append(gate.Check("texture envelope", ok,
                                     f"inside the zone the built surface lies {m['zone_highest_mm']:+.3f} .. -{m['zone_deepest_mm']:.3f} mm "
                                     f"from the design (allowed +{rise + pad:.3f} .. -{depth + pad:.3f}: "
                                     f"{'no metal added' if not rise else f'nothing above the rise of {rise:g}'}, nothing deeper than {depth:g})"))
    else:
        rep.checks.append(gate.incomplete("texture envelope", "no vertex inside the zone"))
    if "outside_worst_mm" in m:
        rep.checks.append(gate.Check("untouched outside the zone", m["outside_worst_mm"] <= pad,
                                     f"the bore, the sides and the rims lie within {m['outside_worst_mm']:.3f} mm of the design "
                                     f"(allowed {pad:.3f}): the mask {'held' if m['outside_worst_mm'] <= pad else 'did not hold'}"))
    cover = m.get("zone_touched")
    lo_c, hi_c = spec.coverage
    if cover is None:
        rep.checks.append(gate.incomplete("texture coverage", "no triangle inside the zone"))
    else:
        ok = lo_c <= cover <= hi_c
        detail = f"the texture over {cover:.0%} of the zone's face (allowed {lo_c:.0%}..{hi_c:.0%})"
        if spec.counts_cells:
            cells = m.get("cells_on_face", 0)
            ok = ok and cells >= MIN_CELLS
            across = f", about {math.sqrt(m['cell_mm2']):.1f} mm across" if m.get("cell_mm2") else ""
            detail += f", {cells} cells enclosed{across} (at least {MIN_CELLS})"
        detail += f"; mean depth over the face {m.get('zone_mean_depth_mm', 0):.3f} mm"
        rep.checks.append(gate.Check("texture coverage", ok, detail))
    plain = spec.plain_volume_mm3()
    most, add = spec.max_removal_mm3(), spec.max_addition_mm3()
    if ntop_vol is None:
        rep.checks.append(gate.incomplete("design volume", "nTop reported no volume; the notebook cannot be checked against the design"))
    else:
        lo, hi = plain - most - plain * 0.005, plain + add + plain * 0.005
        taken = plain - ntop_vol
        rep.checks.append(gate.Check("design volume", lo <= ntop_vol <= hi,
                                     f"nTop {ntop_vol:.2f} mm³: the plain band {plain:.2f} {'less' if taken >= 0 else 'plus'} {abs(taken):.2f} "
                                     f"({-taken / plain:+.2%}; the texture may take up to {most:.2f}"
                                     + (f" and add up to {add:.2f}" if add else "") + ")"))
    return rep


@dataclass
class FieldTextureResult(bandmod.BandResult):
    def text(self) -> str:
        s = self.spec
        head = f"{s.kind.capitalize()} {s.band.profile} {s.band.label}: {s.texture_line()}, {s.band.width_mm:g} x {s.band.thickness_mm:g} -> {self.stl.name}"
        lines = [head, self.run.summary(), self.gate.text(), f"  status: {self.status.upper()}  run {self.run_dir}"]
        if self.delivered:
            lines.append(f"  delivered to {self.delivered}")
        lines += [f"  note: {n}" for n in self.notes]
        return "\n".join(lines)


def build(spec: FieldTextureSpec, out_dir: Path | None = None, *, notebook: Path | None = None, catalog_name: str | None = None,
          deliver: bool = False, deliver_project: str = "Bands", cast_metal: str | None = None) -> FieldTextureResult:
    """Run the kind's notebook (ring_<kind>.ntop) through nTopCL, gate the textured band by its envelope (check_fieldtex)."""
    problems = spec.validate()
    if problems:
        raise ValueError("; ".join(problems))
    cat = catalog.load(catalog_name or spec.notebook_name)
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
        "max_addition_mm3": spec.max_addition_mm3(), "texture": getattr(rep, "texture", {}),
        "gate": rep.to_dict(), "ntopcl_seconds": run.seconds, "block_timings": [t.__dict__ for t in run.log.timings],
        "notes": result.notes, "notebook": runs.notebook_identity(nb), "environment": runs.environment(ntopcl.version()),
    }
    (run_dir / f"{stem}.report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    if deliver and result.ok:
        result.delivered = runs.deliver(stl, run_dir, stem, deliver_project, report, cast_metal=cast_metal)
    elif deliver:
        result.notes.append(f"not delivered: status {result.status}")
    return result
