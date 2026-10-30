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
design's (`check_shank`: "section shape") as well as the usual band checks and the design
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
SPLIT_STRAND_MIN_MM = 1.0   # each half of a split shank keeps at least this width at the head
SLOT_END_MM = 0.4           # a split closes into a round end this wide (a cast slot cannot end in a crack)
SPLIT_OVERLAP_MM = 0.1      # a split's two halves, lofted the whole way round, overlap this much where the slot is closed
SPLIT_INSET_MM = 0.01       # ... each half's surface drawn this far inside the other's across the overlap, so no faces coincide
BRIDGE_INSET_MM = 0.1       # a bridge runs this far into each strand it joins
SHARP_EDGE_DEG = 30.0       # a convex edge whose faces turn more than this is one the opening rounds
ROPE_STRAND_MIN_MM = 0.8    # a rope's strand diameter: a prong-tip-sized rod casts; thinner does not
ROPE_POINTS = 48            # points round a rope strand's section (a 48-gon is 0.1 % under the circle)


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
    split_mm: float = 0.0                           # the band splits towards the head: the slot's width at the head
    split_span_deg: float = 90.0                    # the split begins this far from the head
    split_shape: str = "contour"                    # how the slot opens: contour (smooth) | chevron (straight)
    rope: int = 0                                   # 0: a band; 2 or 3: that many round strands twisted round the ring
    rope_turns: float = 10.0                        # rope: full twists per ring
    rope_strand_mm: float = 1.2                     # rope: a strand's diameter
    rope_offset_frac: float = 0.7                   # rope: strand centre off the rope's centreline, in strand radii (< 1: they overlap into one solid)
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

    def split_at(self, theta_deg: float) -> float:
        """The slot's width at an angle: split_mm at the head, closing by split_span_deg (a cosine
        for contour, straight for chevron)."""
        if self.split_mm == 0.0:
            return 0.0
        a = abs((float(theta_deg) + 180.0) % 360.0 - 180.0)
        if a >= self.split_span_deg:
            return 0.0
        f = a / self.split_span_deg
        return self.split_mm * ((1.0 - f) if self.split_shape == "chevron" else 0.5 * (1.0 + math.cos(math.pi * f)))

    # ---- a rope: round strands twisted round the ring's centreline -------------------------
    @property
    def rope_radius(self) -> float:
        return self.rope_strand_mm / 2

    @property
    def rope_offset(self) -> float:
        """A strand centre's distance from the rope's centreline."""
        return self.rope_offset_frac * self.rope_radius

    @property
    def rope_centre_radius(self) -> float:
        """The rope's centreline radius: the innermost strand just touches the bore."""
        return self.band.bore_radius_mm + self.rope_offset + self.rope_radius

    @property
    def rope_stations(self) -> int:
        """Stations for a rope: at least 36 per twist, so a strand's helix is drawn, not chorded."""
        return max(self.stations, int(math.ceil(36 * self.rope_turns)))

    def rope_centre(self, theta_deg: float, strand: int) -> tuple[float, float]:
        """(r, z) of a strand's centre at an angle."""
        phi = math.radians(self.rope_turns * theta_deg) + 2 * math.pi * strand / self.rope
        return self.rope_centre_radius + self.rope_offset * math.cos(phi), self.rope_offset * math.sin(phi)

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

    def slot_half_at(self, theta_deg: float) -> float:
        """The slot's actual half width at an angle: the law (split_at), but never narrower than the
        round end's radius inside the span, and a quarter-round end of SLOT_END_MM diameter (a cast
        slot ends in a drill-sized round, not a crack tip)."""
        if self.split_mm <= 0.0:
            return 0.0
        span, r_end = self.split_span_deg, SLOT_END_MM / 2
        end_deg = r_end / (self.wrap_length_mm / 360.0)
        a = abs((float(theta_deg) + 180.0) % 360.0 - 180.0)
        if a >= span:
            return 0.0
        h = max(self.split_at(a) / 2, r_end)
        c = span - end_deg
        if a <= c:
            return h
        cos_phi = (a - c) / end_deg
        return h * math.sqrt(max(0.0, 1.0 - cos_phi * cos_phi))

    def bridge_half_deg(self) -> float:
        """Half a bridge's length round the ring, in degrees."""
        return (self.bridge_mm / 2) / (self.wrap_length_mm / 360.0)

    def shape_check_skips(self, theta_deg: float) -> bool:
        """Angles where the 2-D section model is not the body: within the edge round (plus a
        margin) of a slot's end or a bridge's end, whose faces look along the ring and whose
        rounding the section cannot show."""
        e_deg = (self.edge_round + 0.15) / (self.wrap_length_mm / 360.0)
        if self.split_mm:
            end_deg = (SLOT_END_MM / 2) / (self.wrap_length_mm / 360.0)
            a = abs((float(theta_deg) + 180.0) % 360.0 - 180.0)
            if self.split_span_deg - 2 * end_deg - e_deg <= a <= self.split_span_deg + e_deg:
                return True
        half = self.bridge_half_deg()
        for b, *_ in self.bridge_spans():
            d = abs((theta_deg - b + 180.0) % 360.0 - 180.0)
            if half - e_deg <= d <= half + e_deg:
                return True
        return False

    def section_shape(self, theta_deg: float, skip: bool = True):
        """The designed cross-section at an angle as a shapely geometry in (r, z): every strand's
        band section at its centreline, a bridge where one spans the angle, the slot taken out,
        and the whole opened by the edge round the way the notebook opens the bar - so a slot's
        and a bridge's fresh edges carry their fillets (the band's own are in the section already).
        A rope's comes from the bar wrapped. None at an angle the model cannot show
        (shape_check_skips), unless `skip` is off (the lofts sample it everywhere)."""
        from shapely.affinity import translate
        from shapely.geometry import box
        from shapely.ops import unary_union
        if self.rope:
            return gate.section_geometry(self.wrapped_ring(), theta_deg)
        if skip and self.shape_check_skips(theta_deg):
            return None
        parts = [translate(self.section_polygon(theta_deg), 0.0, self.z_offset(theta_deg, k)) for k in range(self.strands)]
        half = self.bridge_half_deg()
        for b, r_in, r_out, z_lo, z_hi in self.bridge_spans():
            if abs((theta_deg - b + 180.0) % 360.0 - 180.0) <= half:
                parts.append(box(r_in, z_lo, r_out, z_hi))
        sec = unary_union(parts)
        h = self.slot_half_at(theta_deg)
        if h > 0:
            zc = self.z_offset(theta_deg)
            sec = sec.difference(box(self.band.bore_radius_mm - 1.0, zc - h, self.band.outer_radius_mm + 1.0, zc + h))
        e = self.edge_round
        if e > 0:
            sec = sec.buffer(-e, quad_segs=16).buffer(e, quad_segs=16)
        return sec

    def section_outline(self, theta_deg: float, phase: float = 0.0):
        """(SECTION_POINTS, 2) array of (r, z) round the section: counter-clockwise from the bore's
        mid-plane point, equally spaced along the outline, so stations loft vertex to vertex.
        `phase` (0..1) starts the sampling that fraction of a step along: a second strand samples
        half a step off the first, so where the two cross their vertices do not coincide."""
        return outline_points(self.section_polygon(theta_deg), SECTION_POINTS, start=(self.band.bore_radius_mm, 0.0), phase=phase)

    @property
    def lofts(self) -> int:
        """How many bodies are lofted station to station: the strands, or a split's two halves."""
        return 2 if self.split_mm else self.strands

    def loft_outline(self, k: int, theta_deg: float, phase: float = 0.0):
        """(SECTION_POINTS, 2) outline of loft `k` at an angle: a strand's section at its centreline,
        or a split's lower (0) / upper (1) half - the opened 2-D section's part on that side where
        the slot is open (its fillets included); where it is closed, the section cut
        SPLIT_OVERLAP_MM past the centreline, so the halves overlap and unite, each half's surface
        drawn inward across the overlap, from nothing at the centreline to SPLIT_INSET_MM at its
        cut (a wedge, by scaling the points there about the section's middle): the ring's surface
        is exact, each half's surface beyond the centreline lies inside the other half, and no two
        faces coincide (coincident faces united in slivers that an STL round trip opened, and two
        exact surfaces over the same strip did the same, 2026-10-30)."""
        import numpy as np
        from shapely.geometry import box
        if not self.split_mm:
            return self.section_outline(theta_deg, phase) + [0.0, self.z_offset(theta_deg, k)]
        sec = self.section_shape(theta_deg, skip=False)
        zc = self.z_offset(theta_deg)
        parts = list(getattr(sec, "geoms", [sec]))
        if len(parts) >= 2:
            parts.sort(key=lambda q: q.centroid.y)
            half = parts[0] if k == 0 else parts[-1]
            return outline_points(half, SECTION_POINTS, start=(self.band.bore_radius_mm, zc), phase=phase)
        b = self.band
        lo, hi = b.bore_radius_mm - 2.0, b.outer_radius_mm + 2.0
        d = SPLIT_OVERLAP_MM
        half = sec.intersection(box(lo, zc - 10.0, hi, zc + d) if k == 0 else box(lo, zc - d, hi, zc + 10.0))
        if hasattr(half, "geoms"):
            half = max(half.geoms, key=lambda q: q.area)
        pts = outline_points(half, SECTION_POINTS, start=(self.band.bore_radius_mm, zc), phase=phase)
        beyond = (pts[:, 1] - zc) if k == 0 else (zc - pts[:, 1])        # how far past the centreline, into the other half
        frac = np.clip(beyond / d, 0.0, 1.0)
        centre = np.array([(b.bore_radius_mm + b.outer_radius_mm) / 2, zc + (d / 2 if k == 0 else -d / 2)])
        scale = 1.0 - frac * SPLIT_INSET_MM / (b.thickness_mm / 2)
        return centre + (pts - centre) * scale[:, None]

    def outlines(self, strand: int = 0):
        """Every station's outline for a loft (a strand, or a split's half)."""
        key = ("outlines", strand)
        if key not in self._cache:
            phase = 0.5 * strand
            self._cache[key] = [self.loft_outline(strand, t, phase) for t in self.station_angles(strand)]
        return self._cache[key]

    def bridge_spans(self) -> list[tuple[float, float, float, float, float]]:
        """Each bridge as (angle, r_in, r_out, z_lo, z_hi): from BRIDGE_INSET_MM inside the lower
        strand to as far inside the upper one, between the strands' bore and outer surfaces where
        the bridge enters them (the comfort relief and the dome have fallen off there), so it
        continues the strands' edge surfaces across the gap instead of standing proud of them."""
        if self.strands < 2:
            return []
        out = []
        for a in self.bridges_deg:
            w = self.width_at(a)
            lo, hi = sorted(self.z_offset(a, k) for k in range(2))
            sec = self.section_spec(a)
            z_in = w / 2 - BRIDGE_INSET_MM                          # where the bridge enters a strand, off its centre
            out.append((float(a), sec.bore_radius_at(z_in), sec.outer_radius_at(z_in), lo + z_in, hi - z_in))
        return out

    @property
    def wrap_length_mm(self) -> float:
        """Remap Cylindrical's Y mapping length: one turn of the bar; the mid-wall circumference
        (a rope's centreline), so the bar's facets are about isometric (the map itself is exact
        in r, z and angle, and a rope's volume comes out the same to first order)."""
        if self.rope:
            return 2 * math.pi * self.rope_centre_radius
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

    def rope_station_fraction(self, strand: int) -> float:
        """Each strand's path samples sit this fraction of a station step on from the first strand's:
        strands sampled on the same meridians (and closed at the same one) left a 0.003 mm³ void
        where three overlapped at the seam (2026-10-30); staggered, their vertices never coincide."""
        return strand / self.rope

    def rope_tube_bar(self, strand: int):
        """One rope strand in the bar frame: a tube round the helix (r_m + a cos φ, Y, a sin φ),
        φ advancing rope_turns per turn, capped at the bar's ends."""
        import numpy as np
        L = self.wrap_length_mm
        n = self.rope_stations
        step = L / n
        k0 = -(n // 2) - int(math.ceil(BAR_OVERLAP_MM / step))
        k1 = n + int(math.ceil(BAR_OVERLAP_MM / step))
        ks = np.arange(k0, k1 + 1) + self.rope_station_fraction(strand)
        y = ks * step
        rz = np.array([self.rope_centre(360.0 * k / n, strand) for k in ks])
        path = np.column_stack([rz[:, 0], y, rz[:, 1]])
        return tube_along(path, self.rope_radius, closed=False, up=(0.0, 0.0, 1.0))

    def rope_tube_ring(self, strand: int):
        """The same strand in the ring frame: the helix wrapped round the axis, a closed tube."""
        import numpy as np
        n = self.rope_stations
        angs = (np.arange(n) + self.rope_station_fraction(strand)) * 360.0 / n
        rz = np.array([self.rope_centre(a, strand) for a in angs])
        t = np.radians(angs)
        path = np.column_stack([rz[:, 0] * np.cos(t), rz[:, 0] * np.sin(t), rz[:, 1]])
        return tube_along(path, self.rope_radius, closed=True, up=(0.0, 0.0, 1.0))

    def bar_mesh(self):
        """The unrolled shank for the notebook: every strand's bar and, for two strands, the
        bridges (boxes along Y, one copy per turn the bar covers), united; a rope's strands
        united; a split's halves united in the ring frame and unrolled (unwrap_ring: where the
        halves cross, the bar frame's straight intersection line came out of the union as one
        28 mm edge, which a wrap turns into a chord through the ring - 2026-10-30)."""
        import trimesh
        if self.rope:
            return drop_specks(trimesh.boolean.union([self.rope_tube_bar(k) for k in range(self.rope)], engine="manifold"))
        if self.split_mm:
            return unwrap_ring(self.design_mesh(), self.wrap_length_mm)
        parts = [self.strand_bar(k) for k in range(self.lofts)]
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
        return parts[0] if len(parts) == 1 else drop_specks(trimesh.boolean.union(parts, engine="manifold"))

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
        bridges as sectors, united, a split cut out; a rope's strands united."""
        if "design_mesh" not in self._cache:
            import trimesh
            if self.rope:
                body = drop_specks(trimesh.boolean.union([self.rope_tube_ring(k) for k in range(self.rope)], engine="manifold"))
            else:
                parts = [self.strand_ring(k) for k in range(self.lofts)]
                parts += [self.bridge_sector(*b) for b in self.bridge_spans()]
                body = parts[0] if len(parts) == 1 else drop_specks(trimesh.boolean.union(parts, engine="manifold"))
            self._cache["design_mesh"] = body
        return self._cache["design_mesh"]

    def design_volume_mm3(self) -> float:
        return float(self.design_mesh().volume)

    def wrapped_ring(self):
        """One turn of the bar wrapped round the axis vertex-wise (wrap_bar): what Remap Cylindrical
        makes of it, as a mesh. A rope's strands cross the meridian obliquely, so their wrapped
        sections are not the ring-built tubes' (0.03 mm apart on a 1.2 mm strand, 2026-10-30): the
        section-shape check compares nTop's with this."""
        if "wrapped_ring" not in self._cache:
            self._cache["wrapped_ring"] = wrap_bar(self.bar_mesh(), self.wrap_length_mm)
        return self._cache["wrapped_ring"]

    def section_bounds(self, theta_deg: float) -> tuple[float, float, float, float]:
        """(z_lo, z_hi, r_lo, r_hi) of the designed section at an angle, every loft together (a
        split's halves carry the slot and its fillets: inside the span the bore and the dome are
        first reached beyond the slot's edge - nTop measured r 8.312..9.687 against a full outline's
        8.253..9.753 at the head of a 1.6 mm split, 2026-10-30); from the independent mesh for a
        rope (its strands cross the meridian obliquely)."""
        import numpy as np
        if self.rope:
            return section_bounds(self.design_mesh(), theta_deg)
        pts = np.vstack([self.loft_outline(k, theta_deg) for k in range(self.lofts)])
        return float(pts[:, 1].min()), float(pts[:, 1].max()), float(pts[:, 0].min()), float(pts[:, 0].max())

    def section_extents(self, theta_deg: float) -> tuple[float, float]:
        """(width, thickness) of the designed section at an angle, every strand together."""
        z0, z1, r0, r1 = self.section_bounds(theta_deg)
        return z1 - z0, r1 - r0

    @property
    def overall_width_mm(self) -> float:
        """The ring's extent along the axis: the widest station, dips and stacking included."""
        if self.rope:
            return 2 * (self.rope_offset + self.rope_radius)
        lo = min(self.section_bounds(t)[0] for t in self.station_angles())
        hi = max(self.section_bounds(t)[1] for t in self.station_angles())
        return hi - lo

    @property
    def outer_radius_mm(self) -> float:
        """The largest radius the ring reaches (at the head)."""
        if self.rope:
            return self.rope_centre_radius + self.rope_offset + self.rope_radius
        return self.band.outer_radius_mm

    # ---- identity, inputs, checks ------------------------------------------------------------
    def design(self) -> dict:
        d = self.band.design()
        d.update({"width_bottom": self.width_bottom, "thickness_bottom": self.thickness_bottom,
                  "taper_from_deg": self.taper_from_deg, "stations": self.stations, "section_points": SECTION_POINTS,
                  "wrap_length": round(self.wrap_length_mm, 4),
                  "dip": self.dip_mm, "dip_span_deg": self.dip_span_deg, "dip_shape": self.dip_shape,
                  "strands": self.strands, "gap": self.gap_mm if self.strands > 1 else 0.0, "mirror": bool(self.mirror and self.strands > 1),
                  "bridges_deg": [float(a) for a in self.bridges_deg] if self.strands > 1 else [],
                  "bridge": self.bridge_mm if self.strands > 1 else 0.0,
                  "split": self.split_mm, "split_span_deg": self.split_span_deg if self.split_mm else 0.0,
                  "split_shape": self.split_shape if self.split_mm else "",
                  "rope": self.rope, "rope_turns": self.rope_turns if self.rope else 0.0,
                  "rope_strand": self.rope_strand_mm if self.rope else 0.0,
                  "rope_offset_frac": self.rope_offset_frac if self.rope else 0.0})
        return d

    @property
    def spec_id(self) -> str:
        return runs.spec_id(self.design())

    @property
    def stem(self) -> str:
        b = self.band
        if self.rope:
            return f"ring_shank_rope{self.rope}x{self.rope_turns:g}_{b.label}_d{self.rope_strand_mm:g}_{self.spec_id}"
        shape = ""
        if self.dip_mm:
            shape += f"_{self.dip_shape}{self.dip_mm:g}"
        if self.strands > 1:
            shape += f"_x2{'m' if self.mirror else ''}"
        if self.split_mm:
            shape += f"_split{self.split_mm:g}"
        return (f"ring_shank_{b.profile}_{b.label}_w{b.width_mm:g}-{self.width_bottom:g}_t{b.thickness_mm:g}-{self.thickness_bottom:g}"
                f"{shape}_{self.spec_id}")

    @property
    def edge_round(self) -> float:
        """The opening (Offset -e, +e) the notebook runs over the wrapped body: the band's edge
        round. The band's own edges are rounded that much in the section already (a no-op for
        them); it rounds the edges the cuts and unions leave sharp - a split's slot, a bridge."""
        return 0.0 if self.rope else self.band.edge_round

    def notebook_inputs(self, bar_path: str, output_path: str = "") -> dict:
        """Values for every input of ring_shank.ntop (names must match the catalog)."""
        return {
            "Shank Path": str(bar_path),
            "Wrap Length": round(self.wrap_length_mm, 4),
            "Edge Round": round(self.edge_round, 4),
            "Edge Round Inward": -round(self.edge_round, 4) if self.edge_round else 0.0,
            "Mesh Tolerance": self.band.mesh_tolerance_mm,
            "Output Path": str(output_path),
        }

    def sharp_edge_round_mm3(self) -> float:
        """What the notebook's opening takes off the design's sharp convex edges (a slot's, a
        bridge's): a ball of radius e rolled along an edge whose faces turn by δ removes
        e² (tan(δ/2) - δ/2) per unit length. The band's rounded edges turn in small steps and
        do not count."""
        import numpy as np
        e = self.edge_round
        if e <= 0:
            return 0.0
        m = self.design_mesh()
        ang = m.face_adjacency_angles
        sharp = m.face_adjacency_convex & (ang > math.radians(SHARP_EDGE_DEG))
        if not sharp.any():
            return 0.0
        edges = m.face_adjacency_edges[sharp]
        length = np.linalg.norm(m.vertices[edges[:, 0]] - m.vertices[edges[:, 1]], axis=1)
        d = ang[sharp]
        return float((e * e * (np.tan(d / 2) - d / 2) * length).sum())

    def expected_volume_mm3(self) -> float:
        """What nTop should report: the design sweep less the opening's rounding of its sharp edges."""
        return self.design_volume_mm3() - self.sharp_edge_round_mm3()

    def validate(self) -> list[str]:
        if self.rope:
            return self._validate_rope()
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
            least = max(0.5, 2 * self.edge_round + 0.1)
            if self.bridge_mm < least:
                p.append(f"bridge {self.bridge_mm:g} mm long: at least {least:g} mm (the edge round opens {self.edge_round:g} mm "
                         f"off each side)")
            if self.mirror and self.dip_mm and self.gap_mm + self.band.width_mm < 2 * abs(self.dip_mm) + 0.3:
                p.append(f"mirrored strands dipping {self.dip_mm:g} mm would cross: widen the gap or ease the dip")
        if self.split_mm:
            if self.split_mm < 0:
                p.append("a split's width is positive")
            if self.strands > 1:
                p.append("a split is two strands already: not with --double")
            if self.split_shape not in ("contour", "chevron"):
                p.append(f"split shape {self.split_shape!r}: contour or chevron")
            if not 10.0 <= self.split_span_deg <= 180.0:
                p.append(f"split span {self.split_span_deg:g}°: 10..180°")
            half = (self.band.width_mm - self.split_mm) / 2
            if half < SPLIT_STRAND_MIN_MM:
                p.append(f"each half of the split would be {half:.2f} mm wide at the head; at least {SPLIT_STRAND_MIN_MM} mm "
                         f"(a {self.band.width_mm:g} mm band takes a split of at most {self.band.width_mm - 2 * SPLIT_STRAND_MIN_MM:g} mm)")
        if not p:
            for t in (90.0, 180.0):                            # the thin end and the shoulder must be valid bands too
                probs = self.section_spec(t).validate()
                if probs:
                    p.append(f"at {t:g}° (width {self.width_at(t):.2f}, thickness {self.thickness_at(t):.2f}): " + "; ".join(probs))
                    break
        if not p and self.lofts == 2:
            m = self.design_mesh()
            if m.body_count != 1:
                p.append(f"the strands and bridges make {m.body_count} bodies, not one ring")
        return p

    def _validate_rope(self) -> list[str]:
        p = []
        if self.rope not in (2, 3):
            p.append(f"rope {self.rope}: 2 or 3 strands")
        if self.rope_strand_mm < ROPE_STRAND_MIN_MM:
            p.append(f"rope strand {self.rope_strand_mm:g} mm: at least {ROPE_STRAND_MIN_MM} mm (a castable strand)")
        if not 0.3 <= self.rope_offset_frac <= 0.9:
            p.append(f"rope offset {self.rope_offset_frac:g} strand radii: 0.3..0.9 (the strands must overlap into one solid)")
        if not 1.0 <= self.rope_turns <= 20.0:
            p.append(f"rope turns {self.rope_turns:g}: 1..20 per ring")
        elif self.rope_turns != int(self.rope_turns):
            p.append(f"rope turns {self.rope_turns:g}: a whole number, or the twist does not meet itself round the ring")
        if not 10.0 <= self.band.inner_diameter_mm <= 25.0:
            p.append(f"inner diameter {self.band.inner_diameter_mm:.2f} mm is outside 10..25 mm")
        if self.tapered or self.dip_mm or self.strands > 1 or self.split_mm:
            p.append("a rope takes no taper, dip, double or split")
        if not p:
            m = self.design_mesh()
            if m.body_count != 1:
                p.append(f"the {self.rope} strands make {m.body_count} bodies, not one ring: bring them closer (--rope-offset)")
        return p

    def warnings(self) -> list[str]:
        return [] if self.rope else list(self.band.warnings())

    def wall_floor(self) -> float:
        """The ray-cast thickness floor: the material floor, or 0.8 x the thinnest station's edge
        (a rope: 0.8 x a strand's diameter)."""
        if self.rope:
            return min(tables.FLOORS["wall_marginal"], 0.8 * self.rope_strand_mm)
        thin = min(self.section_spec(t).edge_thickness_mm for t in (0.0, 180.0))
        return min(tables.FLOORS["wall_marginal"], 0.8 * thin)

    def describe(self) -> str:
        b = self.band
        if self.rope:
            return (f"{self.stem}: {b.label}, inner Ø {b.inner_diameter_mm:.3f}\n"
                    f"  {self.rope} strands of {self.rope_strand_mm:g} mm twisted {self.rope_turns:g} times round the ring, "
                    f"centres {self.rope_offset:.2f} mm off the centreline (r {self.rope_centre_radius:.3f}); overall "
                    f"{self.overall_width_mm:.2f} wide, {2 * (self.rope_offset + self.rope_radius):.2f} thick\n"
                    f"  {self.rope_stations} stations; wrap length {self.wrap_length_mm:.3f} mm; design volume {self.design_volume_mm3():.2f} mm³")
        line = (f"{self.stem}: {b.profile} {b.label}, inner Ø {b.inner_diameter_mm:.3f}\n"
                f"  head: width {b.width_mm:g} thickness {b.thickness_mm:g}; bottom: width {self.width_bottom:g} "
                f"thickness {self.thickness_bottom:g}; full section to {self.taper_from_deg:g}° then a cosine ease")
        if self.dip_mm:
            line += f"\n  centreline: a {self.dip_shape} of {self.dip_mm:g} mm at the head over ±{self.dip_span_deg:g}°"
        if self.strands == 2:
            line += (f"\n  two strands {self.gap_mm:g} mm apart{', mirrored' if self.mirror else ''}, bridged at "
                     + ", ".join(f"{a:g}°" for a in self.bridges_deg) + f" ({self.bridge_mm:g} mm)")
        if self.split_mm:
            line += f"\n  split: a {self.split_shape} slot {self.split_mm:g} mm wide at the head, closing by ±{self.split_span_deg:g}°"
        line += (f"\n  {self.stations} stations x {SECTION_POINTS} points; wrap length {self.wrap_length_mm:.3f} mm; "
                 f"overall width {self.overall_width_mm:.2f} mm; design volume {self.design_volume_mm3():.2f} mm³")
        rounded = self.sharp_edge_round_mm3()
        if rounded:
            line += f"; the {self.edge_round:g} mm opening rounds {rounded:.2f} mm³ off the sharp edges (expect {self.expected_volume_mm3():.2f})"
        return line


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


def unwrap_ring(ring, wrap_length: float):
    """A ring mesh unrolled into a bar (the inverse of wrap_bar: X = r, Y = angle x L / 2π, Z = z)
    running from -3L/4 to 5L/4, so it covers the turn and a half plus margins a bar needs. The
    ring is cut into two halves by the plane through the axis (turned a little first, so the cut
    runs between stations), each half unrolled, and the halves with their shifted copies welded
    at the cuts vertex to twin - no boolean: a union of overlapping lofts in the bar frame, where
    the facets are coplanar, came out in slivers (2026-10-30)."""
    import numpy as np
    import trimesh
    L = float(wrap_length)
    nudge = 360.0 / 730.0
    m = ring.copy()
    m.apply_transform(trimesh.transformations.rotation_matrix(math.radians(-nudge), [0, 0, 1]))
    pieces = []
    for sign, lo_deg in ((1.0, -90.0), (-1.0, 90.0)):
        half = trimesh.intersections.slice_mesh_plane(m, [sign, 0.0, 0.0], [0.0, 0.0, 0.0], cap=True)
        v = half.vertices
        r = np.hypot(v[:, 0], v[:, 1])
        th = np.degrees(np.arctan2(v[:, 1], v[:, 0]))
        th = np.where(th < lo_deg - 1e-9, th + 360.0, th)                 # the far half: 90 .. 270
        th = np.clip(th, lo_deg, lo_deg + 180.0)
        y = (th + nudge) / 360.0 * L                                        # the angle origin restored
        pieces.append(trimesh.Trimesh(np.column_stack([r, y, v[:, 2]]), half.faces, process=False))
    a, b = pieces
    parts = []
    for piece, shift in ((b, -1), (a, 0), (b, 0), (a, 1)):                    # -3L/4 .. -L/4 .. L/4 .. 3L/4 .. 5L/4
        q = piece.copy()
        q.vertices = q.vertices + np.array([0.0, shift * L, 0.0])
        parts.append(q)
    bar = trimesh.util.concatenate(parts)
    bar.merge_vertices()                                                   # the twins on a shared cut are identical
    y_nudge = nudge / 360.0 * L
    cuts = [-L / 4 + y_nudge + k * L / 2 for k in range(3)]                # the interior cuts; the ends keep their caps
    V = bar.vertices
    on_cut = np.zeros(len(V), bool)
    for y_cut in cuts:
        on_cut |= np.abs(V[:, 1] - y_cut) < 1e-6
    bar.update_faces(~on_cut[bar.faces].all(axis=1))                       # both caps at every interior cut go
    bar.remove_unreferenced_vertices()
    if bar.volume < 0:
        bar.invert()
    assert bar.is_watertight, "unwrap_ring: the welded bar is not closed"
    y_lo, y_hi = -3 * L / 4 + y_nudge, 5 * L / 4 + y_nudge
    assert abs(bar.bounds[0][1] - y_lo) < 1e-6 and abs(bar.bounds[1][1] - y_hi) < 1e-6
    return bar


def wrap_bar(bar, wrap_length: float):
    """One turn of a bar wrapped round Z the way Remap Cylindrical Body does it (geom.remap_cylindrical,
    vertex-wise): the bar is cut a little before Y = 0 and a turn further on (wrap_length / 730 back -
    between stations, never through one, for any station count up to 720), the two cut faces then
    coincide at the same angle, so they are dropped and the seam joined vertex to twin. The
    simulated nTop does exactly this."""
    import numpy as np
    import trimesh
    from scipy.spatial import cKDTree
    L = float(wrap_length)
    y0 = -L / 730.0
    y1 = y0 + L
    one = trimesh.intersections.slice_mesh_plane(bar, [0, 1, 0], [0, y0, 0], cap=True)
    one = trimesh.intersections.slice_mesh_plane(one, [0, -1, 0], [0, y1, 0], cap=True)
    side0 = np.abs(one.vertices[:, 1] - y0) < 1e-6
    side1 = np.abs(one.vertices[:, 1] - y1) < 1e-6
    mesh = geom.remap_cylindrical(one, L)
    mesh.update_faces(~(side0 | side1)[mesh.faces].all(axis=1))
    i0, i1 = np.nonzero(side0)[0], np.nonzero(side1)[0]
    _, twin = cKDTree(mesh.vertices[i0]).query(mesh.vertices[i1])
    remap = np.arange(len(mesh.vertices))
    remap[i1] = i0[twin]
    mesh = trimesh.Trimesh(mesh.vertices, remap[mesh.faces], process=False)
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.remove_unreferenced_vertices()
    return mesh


def drop_specks(mesh, min_volume_mm3: float = 1e-6):
    """A boolean's result without the zero-volume specks manifold3d can leave where surfaces meet
    (4-face tetrahedra at a rope strand's closing seam, 2026-10-30): only the components that hold
    volume. A body count above one after this is real - strands that do not overlap."""
    import trimesh
    parts = mesh.split(only_watertight=False)
    keep = [q for q in parts if abs(q.volume) > min_volume_mm3]
    if len(keep) == len(parts):
        return mesh
    return keep[0] if len(keep) == 1 else trimesh.util.concatenate(keep)


def tube_along(path, radius: float, closed: bool, points: int = ROPE_POINTS, up=None):
    """A watertight tube of `radius` round a 3-D polyline (N, 3): sections perpendicular to the
    path, joined vertex to vertex; a closed loop joins its ends, an open one is capped. The
    section's frame is parallel-transported (no twist of its own) or, with `up`, the direction
    `up` projected off the tangent - a frame that depends on the local tangent alone, so a
    periodic path gets a periodic tube (a rope strand: the ring's axis is `up`; parallel transport
    comes back from a turn rotated, and the bar's two cuts no longer matched - 2026-10-30)."""
    import numpy as np
    import trimesh
    P = np.asarray(path, float)
    n = len(P)
    if closed:
        T = np.roll(P, -1, axis=0) - np.roll(P, 1, axis=0)
    else:
        T = np.gradient(P, axis=0)
    T /= np.linalg.norm(T, axis=1)[:, None]
    N = np.zeros_like(T)
    if up is not None:
        u = np.asarray(up, float) / np.linalg.norm(up)
        N = u[None, :] - T * (T @ u)[:, None]
        if (np.linalg.norm(N, axis=1) < 1e-6).any():
            raise ValueError("tube_along: the path runs along `up`")
        N /= np.linalg.norm(N, axis=1)[:, None]
    else:
        # parallel transport: start with any normal, rotate it along with the tangent
        a = np.array([0.0, 0.0, 1.0]) if abs(T[0][2]) < 0.9 else np.array([1.0, 0.0, 0.0])
        N[0] = a - T[0] * (a @ T[0])
        N[0] /= np.linalg.norm(N[0])
        for i in range(1, n):
            b = np.cross(T[i - 1], T[i])
            s = np.linalg.norm(b)
            if s < 1e-12:
                N[i] = N[i - 1]
            else:
                b /= s
                c = float(np.clip(T[i - 1] @ T[i], -1.0, 1.0))
                ang = math.atan2(s, c)
                v = N[i - 1]
                N[i] = v * math.cos(ang) + np.cross(b, v) * math.sin(ang) + b * (b @ v) * (1 - math.cos(ang))
            N[i] -= T[i] * (N[i] @ T[i])
            N[i] /= np.linalg.norm(N[i])
    B = np.cross(T, N)
    ang = np.arange(points) * 2 * math.pi / points
    ring = np.cos(ang)[:, None, None] * N[None, :, :] + np.sin(ang)[:, None, None] * B[None, :, :]   # (points, n, 3)
    V = (P[None, :, :] + radius * ring).transpose(1, 0, 2).reshape(-1, 3)                            # station-major
    m = points
    faces = []
    last = n if closed else n - 1
    for i in range(last):
        a0 = i * m + np.arange(m)
        b0 = ((i + 1) % n) * m + np.arange(m)
        an, bn = np.roll(a0, -1), np.roll(b0, -1)
        faces.append(np.column_stack([a0, bn, an]))
        faces.append(np.column_stack([a0, b0, bn]))
    F = np.vstack(faces)
    if not closed:
        c0, c1 = len(V), len(V) + 1
        V = np.vstack([V, P[0], P[-1]])
        idx = np.arange(m)
        F = np.vstack([F, np.column_stack([np.full(m, c0), np.roll(idx, -1), idx]),
                       np.column_stack([np.full(m, c1), (n - 1) * m + idx, (n - 1) * m + np.roll(idx, -1)])])
    mesh = trimesh.Trimesh(V, F, process=False)
    trimesh.repair.fix_winding(mesh)                      # the caps' sense against the sides'
    if mesh.volume < 0:
        mesh.invert()
    return mesh


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
    plus the two checks only the design can add: the section shape at the gate's angles (the
    built outline against the designed one, ShankSpec.section_shape: a lost dip, a missing
    strand, a slot's edge left sharp, a notebook that did not wrap or wrapped with the wrong
    length all show) and the design volume."""
    b = spec.band
    rep = gate.check(stl, expect_inner=b.inner_diameter_mm, expect_outer=2 * spec.outer_radius_mm,
                     expect_width=spec.overall_width_mm, expect_volume=ntop_vol, wall_floor=spec.wall_floor(),
                     centre="origin",                      # the box centre sits off the axis on a tapered ring
                     section_design=spec.section_shape, section_tol_mm=band.section_shape_tolerance(b.mesh_tolerance_mm))
    c = band.design_volume_check(spec.expected_volume_mm3(), ntop_vol, 2.0)
    rounded = spec.sharp_edge_round_mm3()
    if rounded and c.status != gate.INCOMPLETE:
        c.detail += f" [design {spec.design_volume_mm3():.2f} less {rounded:.2f} mm³ of edge rounding]"
    rep.checks.append(c)
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
        "ntop_volume_mm3": ntop_vol, "design_volume_mm3": spec.design_volume_mm3(),
        "expected_volume_mm3": spec.expected_volume_mm3(), "gate": rep.to_dict(),
        "ntopcl_seconds": run.seconds, "block_timings": [t.__dict__ for t in run.log.timings], "notes": result.notes,
        "notebook": runs.notebook_identity(nb), "environment": runs.environment(ntopcl.version()),
    }
    (run_dir / f"{stem}.report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    if deliver and result.ok:
        result.delivered = runs.deliver(stl, run_dir, stem, deliver_project, report, extra_files=[bar], cast_metal=cast_metal)
    elif deliver:
        result.notes.append(f"not delivered: status {result.status}")
    return result
