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

Step 1b, the centreline (rings 04, 08): the band's centre may leave the mid-plane near the head -
a smooth `contour` bump or a `chevron` V of `dip_mm`, over `dip_span_deg` either side of the head -
and a shank may be two strands (`strands=2`): the same band stacked in z with a `gap_mm` between
them, the second strand's dip the same way (nested chevrons) or mirrored (a wishbone), joined by
bridges at `bridges_deg` (full-thickness bars `bridge_mm` long round the ring). Strands and
bridges are united in the bar before it is written, and the independent sweep unites them in
the ring frame (a bridge there is the sector the wrapped bar makes of it).
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
    dip_mm: float = 0.0                             # the band's centre at the head leaves the mid-plane by this (+ towards +Z)
    dip_span_deg: float = 60.0                      # the dip reaches this far either side of the head
    dip_shape: str = "contour"                      # contour (a smooth bump) | chevron (a V, its point at the head)
    strands: int = 1                                # 1, or 2: the band twice, stacked in z
    gap_mm: float = 0.6                             # strands=2: clear gap between the strands (where neither dips)
    mirror: bool = False                            # strands=2: the second strand dips the other way (a wishbone)
    bridges_deg: tuple = (180.0,)                   # strands=2: where full-thickness bars join the strands
    bridge_mm: float = 1.2                          # strands=2: a bridge's length round the ring
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

    def dip_at(self, theta_deg: float) -> float:
        """The centreline's z at an angle for a strand that dips towards +Z: a cosine bump (contour)
        or a V (chevron) of dip_mm at the head, nothing beyond dip_span_deg."""
        if self.dip_mm == 0.0:
            return 0.0
        a = abs((float(theta_deg) + 180.0) % 360.0 - 180.0)
        if a >= self.dip_span_deg:
            return 0.0
        f = a / self.dip_span_deg
        return self.dip_mm * ((1.0 - f) if self.dip_shape == "chevron" else 0.5 * (1.0 + math.cos(math.pi * f)))

    @property
    def strand_centres(self) -> list[float]:
        """Each strand's z offset away from the dip (strands stacked about the mid-plane)."""
        if self.strands == 1:
            return [0.0]
        half = (self.band.width_mm + self.gap_mm) / 2
        return [-half, half]

    def z_offset(self, theta_deg: float, strand: int = 0) -> float:
        """Where a strand's section centre sits in z at an angle: its stack offset plus the dip
        (the second strand's dip mirrored when asked)."""
        sign = -1.0 if (self.mirror and strand == 1) else 1.0
        return self.strand_centres[strand] + sign * self.dip_at(theta_deg)

    def section_spec(self, theta_deg: float) -> band.BandSpec:
        """The band whose section this angle gets: the head's band at the local width and thickness."""
        return replace(self.band, width_mm=round(self.width_at(theta_deg), 6), thickness_mm=round(self.thickness_at(theta_deg), 6))

    def station_angles(self, strand: int = 0):
        """Where a strand's sections sit: every 360/stations degrees, a second strand half a
        step on (its meridians never coincide with the first strand's, so where mirrored strands
        cross, the boolean meets no coincident vertices - seen 2026-10-30)."""
        return [360.0 * (k + 0.5 * strand) / self.stations for k in range(self.stations)]

    # ---- geometry -------------------------------------------------------------------------
    def section_polygon(self, theta_deg: float):
        """The finished meridian section at this angle, a shapely polygon in (r, z)."""
        return geom.section_polygon(self.section_spec(theta_deg).notebook_inputs(""))

    def section_outline(self, theta_deg: float, phase: float = 0.0):
        """(SECTION_POINTS, 2) array of (r, z) round the section: counter-clockwise from the bore's
        mid-plane point, equally spaced along the outline, so stations loft vertex to vertex.
        `phase` (0..1) starts the sampling that fraction of a step along: a second strand samples
        half a step off the first, so where the two cross their vertices do not coincide."""
        return outline_points(self.section_polygon(theta_deg), SECTION_POINTS, start=(self.band.bore_radius_mm, 0.0), phase=phase)

    def outlines(self, strand: int = 0):
        """Every station's outline for a strand, shifted to its centreline."""
        key = ("outlines", strand)
        if key not in self._cache:
            phase = 0.5 * strand
            self._cache[key] = [self.section_outline(t, phase) + [0.0, self.z_offset(t, strand)] for t in self.station_angles(strand)]
        return self._cache[key]

    def bridge_spans(self) -> list[tuple[float, float, float, float, float]]:
        """Each bridge as (angle, r_in, r_out, z_lo, z_hi): full thickness at that angle, from a
        little inside the lower strand to a little inside the upper one."""
        if self.strands < 2:
            return []
        out = []
        for a in self.bridges_deg:
            w = self.width_at(a)
            lo, hi = sorted(self.z_offset(a, k) for k in range(2))
            sec = self.section_spec(a)
            out.append((float(a), sec.bore_radius_mm, sec.outer_radius_mm, lo + w / 2 - 0.1, hi - w / 2 + 0.1))
        return out

    @property
    def wrap_length_mm(self) -> float:
        """Remap Cylindrical's Y mapping length: one turn of the bar; the mid-wall circumference,
        so the bar's facets are about isometric (the map itself is exact in r, z and angle)."""
        return 2 * math.pi * (self.band.bore_radius_mm + self.band.thickness_mm / 2)

    def _bar_range(self) -> tuple[float, list[int]]:
        """(station step along Y, station indices): a turn and a half plus BAR_OVERLAP_MM at both
        ends (Y from -L/2 - o to L + o), so whichever way nTop reads the angle (0..360 or ±180)
        every angle finds material and the seam lies inside the bar."""
        L = self.wrap_length_mm
        step = L / self.stations
        k0 = -(self.stations // 2) - int(math.ceil(BAR_OVERLAP_MM / step))
        k1 = self.stations + int(math.ceil(BAR_OVERLAP_MM / step))
        return step, list(range(k0, k1 + 1))

    def strand_bar(self, strand: int = 0):
        """One strand unrolled: X radial, Y along the ring (Y = wrap length is one turn, angle 0 at
        Y = 0), Z axial; stations lofted vertex to vertex, capped at both ends."""
        import numpy as np
        import trimesh
        n, m = self.stations, SECTION_POINTS
        outlines = self.outlines(strand)
        step, ks = self._bar_range()
        verts = []
        for k in ks:
            rz = outlines[k % n]
            verts.append(np.column_stack([rz[:, 0], np.full(m, (k + 0.5 * strand) * step), rz[:, 1]]))
        V = np.vstack(verts)
        faces = []
        for i in range(len(ks) - 1):
            a = i * m + np.arange(m)
            b = a + m
            an, bn = np.roll(a, -1), np.roll(b, -1)
            faces.append(np.column_stack([a, an, bn]))          # outline counter-clockwise in (r, z), +y along: outward
            faces.append(np.column_stack([a, bn, b]))
        F = np.vstack(faces)
        tri = _outline_triangles(outlines[ks[0] % n])           # the caps: a triangulation of the outline, one at each end
        F = np.vstack([F, tri[:, ::-1], tri + (len(ks) - 1) * m])
        mesh = trimesh.Trimesh(V, F, process=False)
        if mesh.volume < 0:
            mesh.invert()
        return mesh

    def bar_mesh(self):
        """The unrolled shank for the notebook: every strand's bar and, for two strands, the
        bridges (boxes along Y, one copy per turn the bar covers), united."""
        import trimesh
        parts = [self.strand_bar(k) for k in range(self.strands)]
        L = self.wrap_length_mm
        step, ks = self._bar_range()
        y_lo, y_hi = ks[0] * step, ks[-1] * step
        for a, r_in, r_out, z_lo, z_hi in self.bridge_spans():
            for turn in (-1, 0, 1):
                y = (a / 360.0 + turn) * L
                if y_lo - self.bridge_mm <= y <= y_hi + self.bridge_mm:
                    box = trimesh.creation.box(extents=(r_out - r_in, self.bridge_mm, z_hi - z_lo))
                    box.apply_translation(((r_in + r_out) / 2, y, (z_lo + z_hi) / 2))
                    parts.append(box)
        # raw: geom.clean would merge the bar's coplanar facets into mm-long ones, which a vertex-wise
        # wrap (the simulated nTop) would then turn into chords
        return parts[0] if len(parts) == 1 else trimesh.boolean.union(parts, engine="manifold")

    def strand_ring(self, strand: int = 0):
        """One strand swept round the axis (Z) directly: no bar, no wrap."""
        import numpy as np
        import trimesh
        n, m = self.stations, SECTION_POINTS
        verts = []
        for t, rz in zip(self.station_angles(strand), self.outlines(strand)):
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
        return mesh

    def bridge_sector(self, a: float, r_in: float, r_out: float, z_lo: float, z_hi: float):
        """A bridge in the ring frame: the annular sector the wrapped box makes, bridge_mm long at
        the mid-wall radius (Y maps to the angle, so the box's ends become radial planes)."""
        import numpy as np
        import trimesh
        from shapely.geometry import Polygon
        half = math.degrees(self.bridge_mm / 2 / (self.wrap_length_mm / (2 * math.pi)))
        angs = np.radians(np.linspace(a - half, a + half, 9))
        outer = np.column_stack([r_out * np.cos(angs), r_out * np.sin(angs)])
        inner = np.column_stack([r_in * np.cos(angs[::-1]), r_in * np.sin(angs[::-1])])
        sector = trimesh.creation.extrude_polygon(Polygon(np.vstack([outer, inner])), height=z_hi - z_lo)
        sector.apply_translation((0.0, 0.0, z_lo))
        return sector

    def design_mesh(self):
        """The independent ring: every strand swept round the axis and, for two strands, the
        bridges as sectors, united."""
        if "design_mesh" not in self._cache:
            import trimesh
            parts = [self.strand_ring(k) for k in range(self.strands)]
            parts += [self.bridge_sector(*b) for b in self.bridge_spans()]
            self._cache["design_mesh"] = parts[0] if len(parts) == 1 else trimesh.boolean.union(parts, engine="manifold")
        return self._cache["design_mesh"]

    def design_volume_mm3(self) -> float:
        return float(self.design_mesh().volume)

    def section_bounds(self, theta_deg: float) -> tuple[float, float, float, float]:
        """(z_lo, z_hi, r_lo, r_hi) of the designed section at an angle, every strand together."""
        import numpy as np
        rz = self.section_outline(theta_deg)
        pts = np.vstack([rz + [0.0, self.z_offset(theta_deg, k)] for k in range(self.strands)])
        return float(pts[:, 1].min()), float(pts[:, 1].max()), float(pts[:, 0].min()), float(pts[:, 0].max())

    def section_extents(self, theta_deg: float) -> tuple[float, float]:
        """(width, thickness) of the designed section at an angle, every strand together."""
        z0, z1, r0, r1 = self.section_bounds(theta_deg)
        return z1 - z0, r1 - r0

    @property
    def overall_width_mm(self) -> float:
        """The ring's extent along the axis: the widest station, dips and stacking included."""
        lo = min(self.section_bounds(t)[0] for t in self.station_angles())
        hi = max(self.section_bounds(t)[1] for t in self.station_angles())
        return hi - lo

    # ---- identity, inputs, checks ------------------------------------------------------------
    def design(self) -> dict:
        d = self.band.design()
        d.update({"width_bottom": self.width_bottom, "thickness_bottom": self.thickness_bottom,
                  "taper_from_deg": self.taper_from_deg, "stations": self.stations, "section_points": SECTION_POINTS,
                  "wrap_length": round(self.wrap_length_mm, 4),
                  "dip": self.dip_mm, "dip_span_deg": self.dip_span_deg, "dip_shape": self.dip_shape,
                  "strands": self.strands, "gap": self.gap_mm if self.strands > 1 else 0.0, "mirror": bool(self.mirror and self.strands > 1),
                  "bridges_deg": [float(a) for a in self.bridges_deg] if self.strands > 1 else [],
                  "bridge": self.bridge_mm if self.strands > 1 else 0.0})
        return d

    @property
    def spec_id(self) -> str:
        return runs.spec_id(self.design())

    @property
    def stem(self) -> str:
        b = self.band
        shape = ""
        if self.dip_mm:
            shape += f"_{self.dip_shape}{self.dip_mm:g}"
        if self.strands > 1:
            shape += f"_x2{'m' if self.mirror else ''}"
        return (f"ring_shank_{b.profile}_{b.label}_w{b.width_mm:g}-{self.width_bottom:g}_t{b.thickness_mm:g}-{self.thickness_bottom:g}"
                f"{shape}_{self.spec_id}")

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
        if self.dip_shape not in ("contour", "chevron"):
            p.append(f"dip shape {self.dip_shape!r}: contour or chevron")
        if abs(self.dip_mm) > 10.0:
            p.append(f"dip {self.dip_mm:g} mm: at most 10 mm either way")
        if self.dip_mm and not 5.0 <= self.dip_span_deg <= 180.0:
            p.append(f"dip span {self.dip_span_deg:g}°: 5..180°")
        if self.strands not in (1, 2):
            p.append(f"strands {self.strands}: 1 or 2")
        elif self.strands == 2:
            if self.gap_mm < 0.0:
                p.append(f"gap {self.gap_mm:g} mm: the strands may touch (0) but not overlap")
            if not self.bridges_deg:
                p.append("two strands need at least one bridge (--bridges), or they are two rings")
            if self.bridge_mm < 0.5:
                p.append(f"bridge {self.bridge_mm:g} mm long: at least 0.5 mm")
            if self.mirror and self.dip_mm and self.gap_mm + self.band.width_mm < 2 * abs(self.dip_mm) + 0.3:
                p.append(f"mirrored strands dipping {self.dip_mm:g} mm would cross: widen the gap or ease the dip")
        if not p:
            for t in (90.0, 180.0):                            # the thin end and the shoulder must be valid bands too
                probs = self.section_spec(t).validate()
                if probs:
                    p.append(f"at {t:g}° (width {self.width_at(t):.2f}, thickness {self.thickness_at(t):.2f}): " + "; ".join(probs))
                    break
        if not p and self.strands == 2:
            m = self.design_mesh()
            if m.body_count != 1:
                p.append(f"the strands and bridges make {m.body_count} bodies, not one ring")
        return p

    def warnings(self) -> list[str]:
        return list(self.band.warnings())

    def wall_floor(self) -> float:
        """The ray-cast thickness floor: the material floor, or 0.8 x the thinnest station's edge."""
        thin = min(self.section_spec(t).edge_thickness_mm for t in (0.0, 180.0))
        return min(tables.FLOORS["wall_marginal"], 0.8 * thin)

    def describe(self) -> str:
        b = self.band
        line = (f"{self.stem}: {b.profile} {b.label}, inner Ø {b.inner_diameter_mm:.3f}\n"
                f"  head: width {b.width_mm:g} thickness {b.thickness_mm:g}; bottom: width {self.width_bottom:g} "
                f"thickness {self.thickness_bottom:g}; full section to {self.taper_from_deg:g}° then a cosine ease")
        if self.dip_mm:
            line += f"\n  centreline: a {self.dip_shape} of {self.dip_mm:g} mm at the head over ±{self.dip_span_deg:g}°"
        if self.strands == 2:
            line += (f"\n  two strands {self.gap_mm:g} mm apart{', mirrored' if self.mirror else ''}, bridged at "
                     + ", ".join(f"{a:g}°" for a in self.bridges_deg) + f" ({self.bridge_mm:g} mm)")
        return line + (f"\n  {self.stations} stations x {SECTION_POINTS} points; wrap length {self.wrap_length_mm:.3f} mm; "
                       f"overall width {self.overall_width_mm:.2f} mm; design volume {self.design_volume_mm3():.2f} mm³")


# ---- outlines ----------------------------------------------------------------------------------
def outline_points(poly, n: int, start: tuple[float, float], phase: float = 0.0):
    """`n` points equally spaced along a shapely polygon's exterior, counter-clockwise, the first
    one `phase` steps past where the outline passes closest to `start`; (n, 2) array."""
    import numpy as np
    from shapely.geometry.polygon import orient
    ring = np.asarray(orient(poly, 1.0).exterior.coords, dtype=float)[:-1]      # open, CCW
    k = int(np.argmin(np.hypot(ring[:, 0] - start[0], ring[:, 1] - start[1])))
    ring = np.roll(ring, -k, axis=0)
    closed = np.vstack([ring, ring[:1]])
    seg = np.linalg.norm(np.diff(closed, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = cum[-1]
    targets = (np.arange(n) + phase) * total / n
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
def section_bounds(mesh, theta_deg: float):
    """(z_lo, z_hi, r_lo, r_hi) of a ring mesh's section at an angle: the lobe of the cut through
    the axis (Z) on the +angle side (every strand together); NaNs when there is none."""
    import numpy as np
    t = math.radians(theta_deg)
    normal = [-math.sin(t), math.cos(t), 0.0]
    sec = mesh.section(plane_origin=[0.0, 0.0, 0.0], plane_normal=normal)
    nan = (float("nan"),) * 4
    if sec is None:
        return nan
    pts = np.asarray(sec.vertices)
    r = pts[:, 0] * math.cos(t) + pts[:, 1] * math.sin(t)
    lobe, rr = pts[r > 0], r[r > 0]
    if len(lobe) < 3:
        return nan
    return float(lobe[:, 2].min()), float(lobe[:, 2].max()), float(rr.min()), float(rr.max())


def section_profile(mesh, theta_deg: float):
    """(width, thickness) of a ring mesh's section at an angle (see section_bounds)."""
    z0, z1, r0, r1 = section_bounds(mesh, theta_deg)
    return z1 - z0, r1 - r0


def check_shank(spec: ShankSpec, stl: Path, ntop_vol: float | None) -> gate.GateReport:
    """The band gate (bore, the widest width, the largest outer diameter, walls, volume vs nTop)
    plus the two checks only the design can add: the section profile at CHECK_ANGLES_DEG (the
    built section's z and r bounds against the designed ones, so a lost dip or a missing strand
    shows as well as a notebook that did not wrap, or wrapped with the wrong length) and the
    design volume."""
    b = spec.band
    rep = gate.check(stl, expect_inner=b.inner_diameter_mm, expect_outer=2 * b.outer_radius_mm,
                     expect_width=spec.overall_width_mm, expect_volume=ntop_vol, wall_floor=spec.wall_floor(),
                     centre="origin")                      # the box centre sits off the axis on a tapered ring
    mesh = gate.load_mesh(stl)
    worst, where, detail = 0.0, None, []
    ok = True
    for t in CHECK_ANGLES_DEG:
        got = section_bounds(mesh, t)
        want = spec.section_bounds(t)
        if math.isnan(got[0]):
            ok = False
            detail.append(f"{t:g}°: no section")
            continue
        err = max(abs(g - w) for g, w in zip(got, want))
        if err > worst:
            worst, where = err, (t, got, want)
        if err > SECTION_TOL_MM:
            ok = False
    if where:
        t, got, want = where
        detail.append(f"worst at {t:g}°: z {got[0]:.3f}..{got[1]:.3f} vs {want[0]:.3f}..{want[1]:.3f}, "
                      f"r {got[2]:.3f}..{got[3]:.3f} vs {want[2]:.3f}..{want[3]:.3f} mm")
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
