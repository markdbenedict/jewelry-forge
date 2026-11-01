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

Step 1c: a split (`split_mm`: the halves lofted the whole way round, the slot's fillets in the
bar) and a rope (`rope`: round strands twisted round the ring). Step 1e, Celtic knotwork
(`knot`, knotwork.py): strands interlaced in the ring's surface - a plait of two to four ribbons
(or round wires) weaving the whole way round, each strand rising over and sinking under the
others at its crossings, the band's width and thickness its envelope.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from . import band, catalog, config, gate, geom, knotwork, ntopcl, runs, tables

BAR_OVERLAP_MM = 1.0        # the bar runs this far past the turn at both ends: the seam is inside material
SECTION_POINTS = 256        # every station's outline resampled to this many points (lofted vertex to vertex)
CHECK_ANGLES_DEG = tuple(range(0, 360, 30))   # where the gate measures the built section against the design
SECTION_TOL_MM = 0.06       # width / thickness at a station: the mesh tolerance plus a little
SPLIT_STRAND_MIN_MM = 1.0   # each half of a split shank keeps at least this width at the head
SLOT_END_MM = 0.4           # a split closes into a round end this wide (a cast slot cannot end in a crack)
SPLIT_OVERLAP_MM = 0.1      # a split's two halves, lofted the whole way round, overlap this much where the slot is closed
SPLIT_INSET_MM = 0.01       # ... each half's surface drawn this far inside the other's across the overlap, so no faces coincide
BRIDGE_INSET_MM = 0.1       # a bridge runs this far into each strand it joins
ROPE_STRAND_MIN_MM = 0.8    # a rope's strand diameter: a prong-tip-sized rod casts; thinner does not
ROPE_POINTS = 48            # points round a rope strand's section (a 48-gon is 0.1 % under the circle)
KNOT_LOBE_MARGIN_MM = 0.3   # (the knot's width is measured to its lobes' outer edges, this much inside --knot-width / 2)
KNOT_NOSE_MM = 1.2          # the band under the head ends in a nose this long, narrowing between a knot's lobes
KNOT_NOSE_JOIN_MM = 0.3     # the knot's head-side crossing lies this far inside the nose's tip
KNOT_NOSE_CLEAR_MM = 0.25   # the knot's inner passes stay this clear of the nose's tip
# A knot's strand is swept in two pieces (a sweep crossing itself is no manifold) that share one section ring
# bit for bit, and the halves' lofts end in the strands' first and last rings the same way: bodies that meet in
# one identical face unite cleanly, where overlaps drawn a hair apart left needle faces (2026-11-01).
MIN_EDGE_MM = 2e-4          # every union's result has its shorter edges collapsed (geom.collapse_short_edges): nTop merges
                            # "very close vertices" on import, and did so into a self-intersecting bar (the trinity shank,
                            # edges of 1.5 µm, 2026-11-01); the split and rope bars it built cleanly had none under 75 µm
KNOT_LIFT_MM = 0.1          # a trinity knot's ribbon runs this far above the bore (buried clear of the pad's bore where it enters it)
KNOT_TAPER_MM = 1.5         # the tail narrows from the half's section to the knot's ribbon over this run
PAD_STEP_DEG = 1.0          # stations along the pad a knot's lobes run into


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
    knot: str = ""                                  # "" or "plait": Celtic knotwork - strands interlaced round the ring instead of a profile
    knot_strands: int = 3                           # plait: strands (2..4)
    knot_repeats: int = 4                           # plait: the weave repeats this many times round the ring
    knot_strand_mm: float = 0.0                     # a ribbon's width across the surface: 0 = the pattern's own (plait 1.2, trinity 0.9)
    knot_profile: str = "flat"                      # flat: a ribbon (thickness (T + fuse) / 2) | round: a wire of that diameter
    knot_mm: float = 0.0                            # trinity: the knot's width across the band, lobe edge to lobe edge; 0 = band width + 1.2
    knot_thickness_mm: float = 0.0                  # trinity: the knot's ribbon thickness (radial); 0 = 0.7 x the band's
    knot_ratio: float = knotwork.TREFOIL_RATIO      # trinity: the trefoil's radial swing (crossing angle 2 atan(1.5 x ratio))
    knot_pad_deg: float = 30.0                      # trinity: the band under the head reaches this far either side of it (its nose's tip)
    knot_pad_set: bool = False                      # trinity: knot_pad_deg was asked for (else a solitaire sizes it from its head)
    knot_tail_mm: float = 3.0                       # trinity: the tails from the knot's crossings to where the halves' lofts begin
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

    # ---- knotwork: strands interlaced in the ring's surface (knotwork.py) -------------------
    @property
    def knot_thickness(self) -> float:
        """A knot strand's radial thickness: two strands stacked at a crossing, fused KNOT_FUSE_MM
        into each other, make the band's thickness."""
        return (self.band.thickness_mm + knotwork.KNOT_FUSE_MM) / 2

    @property
    def knot_width(self) -> float:
        """A plait strand's width across the surface (a round wire: its diameter = its thickness)."""
        return self.knot_thickness if self.knot_profile == "round" else (float(self.knot_strand_mm) or 1.2)

    @property
    def knot_rise(self) -> float:
        """How far a strand's centre rises over (sinks under) the mid-depth at a crossing."""
        return (self.knot_thickness - knotwork.KNOT_FUSE_MM) / 2

    @property
    def knot_mid_radius(self) -> float:
        """A strand centre's radius between crossings: an under strand's inner face then lies on
        the bore, an over strand's outer face on the band's outer radius."""
        return self.band.bore_radius_mm + self.knot_thickness / 2 + self.knot_rise

    @property
    def knot_amplitude(self) -> float:
        """The sinusoids' amplitude: the strands' outer edges reach the band's edges."""
        return (self.band.width_mm - self.knot_width) / 2

    @property
    def knot_points(self) -> int:
        """Centreline samples per strand per turn."""
        return max(self.stations, knotwork.KNOT_POINTS_PER_REPEAT * self.knot_repeats)

    def knot_strand_set(self) -> list[knotwork.Strand]:
        """The strands' centrelines in the developed surface (y along the ring, z axial)."""
        if "knot_strands" not in self._cache:
            self._cache["knot_strands"] = knotwork.plait_strands(self.knot_strands, self.knot_repeats, self.knot_amplitude,
                                                                 self.wrap_length_mm, self.knot_points)
        return self._cache["knot_strands"]

    def knot_layout(self) -> knotwork.Interlace:
        """The solved weave (knotwork.interlace): every crossing's over strand, the radial law."""
        if "knot_layout" not in self._cache:
            self._cache["knot_layout"] = knotwork.interlace(self.knot_strand_set())
        return self._cache["knot_layout"]

    def knot_section_profile(self):
        """The strand's section in the sweep's frame: a ribbon with the band's edge round on its
        corners, or a round wire."""
        if self.knot_profile == "round":
            return knotwork.wire_profile(self.knot_thickness)
        return knotwork.ribbon_profile(self.knot_width, self.knot_thickness, self.band.edge_round)

    def knot_strand_bar(self, strand: int):
        """One strand in the bar frame: its centreline over a turn and a half plus the overlap
        (x = mid radius + rise x the interlace depth, y along, z the weave), swept with the
        section, the radial direction +X, capped at the bar's ends."""
        import numpy as np
        st, lace = self.knot_strand_set()[strand], self.knot_layout()
        m = len(st.points)
        L = self.wrap_length_mm
        step = L / m
        k0 = -(m // 2) - int(math.ceil(BAR_OVERLAP_MM / step))
        k1 = m + int(math.ceil(BAR_OVERLAP_MM / step))
        q = np.arange(k0, k1 + 1)
        idx = q % m
        u = lace.depth(strand, st.params[idx])
        x = self.knot_mid_radius + self.knot_rise * u
        y = st.points[idx, 0] + (q // m) * L
        path = np.column_stack([x, y, st.points[idx, 1]])
        return knotwork.sweep_along(path, self.knot_section_profile(), closed=False, up=(1.0, 0.0, 0.0))

    def knot_strand_ring(self, strand: int):
        """The same strand in the ring frame: the centreline wrapped round the axis (y -> angle, x
        -> r), swept closed with the local radial direction up."""
        import numpy as np
        st, lace = self.knot_strand_set()[strand], self.knot_layout()
        u = lace.depth(strand, st.params)
        r = self.knot_mid_radius + self.knot_rise * u
        t = 2 * math.pi * st.points[:, 0] / self.wrap_length_mm
        path = np.column_stack([r * np.cos(t), r * np.sin(t), st.points[:, 1]])
        up = np.column_stack([np.cos(t), np.sin(t), np.zeros_like(t)])
        return knotwork.sweep_along(path, self.knot_section_profile(), closed=True, up=up)

    # ---- trinity: the triquetra on each shoulder of a split shank (knotwork.trefoil_motif) -----
    @property
    def trinity(self) -> bool:
        return self.knot == "trinity"

    @property
    def deg_per_mm(self) -> float:
        return 360.0 / self.wrap_length_mm

    @property
    def trinity_width(self) -> float:
        return float(self.knot_mm) if self.knot_mm else self.band.width_mm + 1.2

    @property
    def trinity_ribbon(self) -> float:
        """The knot's ribbon width across the surface (the tails narrow the halves to it)."""
        return float(self.knot_strand_mm) or 0.9

    @property
    def trinity_thickness_max(self) -> float:
        """The thickest ribbon the band takes: a pass under inside the band's nose keeps clear of the
        nose's crown (the nose's end is rounded by the edge round)."""
        return self.band.thickness_mm - max(self.band.edge_round, 0.2) - 0.1

    @property
    def trinity_thickness(self) -> float:
        """The knot's ribbon thickness, radial (the tails thin the halves to it): 0.7 x the band's,
        within trinity_thickness_max."""
        return float(self.knot_thickness_mm) if self.knot_thickness_mm else min(0.7 * self.band.thickness_mm, self.trinity_thickness_max)

    @property
    def trinity_radius(self) -> float:
        """The trefoil's R (its crossings' radius): the lobes' outer edges reach KNOT_LOBE_MARGIN_MM
        inside ±knot width / 2."""
        return (self.trinity_width / 2 - KNOT_LOBE_MARGIN_MM - self.trinity_ribbon / 2) / (math.sin(math.radians(60.0)) * (1 + self.knot_ratio))

    def trinity_layout(self) -> dict:
        """Where everything sits on the +θ shoulder (the other mirrors it), in mm along the ring
        (y, the head at 0) and degrees: the nose's tip y_pad, the knot's centre y_c (its head-side
        crossing KNOT_NOSE_JOIN_MM inside the nose), the tail crossings' y, the tails' end y_1 /
        theta_1 (where the halves' lofts take over) and the upper half's outline there (its centre
        r_c, z_c, its inner face r_in, its width and thickness, which the tails taper to the
        ribbon's)."""
        if "trinity" not in self._cache:
            R, c = self.trinity_radius, self.knot_ratio
            y_pad = self.knot_pad_deg / self.deg_per_mm
            y_c = y_pad - KNOT_NOSE_JOIN_MM + R                            # the crossing on the axis: y_c - R
            y_x = y_c + 0.5 * R                                            # the tail crossings (60° / 300° off +y)
            y_1 = y_x + self.knot_tail_mm
            theta_1 = y_1 * self.deg_per_mm
            upper = self.loft_outline(1, theta_1, 0.5)
            self._cache["trinity"] = dict(R=R, y_pad=y_pad, y_c=y_c, y_x=y_x, y_1=y_1, theta_1=theta_1,
                                          r_c=float(upper[:, 0].mean()), z_c=float(upper[:, 1].mean()),
                                          r_in=float(upper[:, 0].min()), upper=upper,
                                          half_width=float(upper[:, 1].max() - upper[:, 1].min()),
                                          half_thickness=float(upper[:, 0].max() - upper[:, 0].min()))
        return self._cache["trinity"]

    def trinity_strand(self, side: int) -> knotwork.Strand:
        """The woven strand of one shoulder (side +1: +θ, -1: -θ) in the developed surface: from
        the upper half's end at theta_1, its tail, the opened trefoil, the other tail, to the lower
        half's end."""
        lay = self.trinity_layout()
        sgn = float(side)
        return knotwork.trefoil_motif((sgn * lay["y_c"], 0.0), lay["R"], ((sgn * lay["y_1"], lay["z_c"]), (sgn * lay["y_1"], -lay["z_c"])),
                                      towards_tail=sgn, ratio=self.knot_ratio)

    def trinity_laces(self) -> list[knotwork.Interlace]:
        """The two shoulders' weaves, each solved on its own (the strands never meet)."""
        if "trinity_laces" not in self._cache:
            self._cache["trinity_laces"] = [knotwork.interlace([self.trinity_strand(side)]) for side in (1, -1)]
        return self._cache["trinity_laces"]

    def trinity_widths(self) -> list[float]:
        return [self.trinity_ribbon]

    def trinity_profile(self, side: int):
        """The sweep's section where it leaves the half: the upper half's outline about its centre
        (n radial, b across); the -θ shoulder's strand runs the other way round the ring, so its b
        is mirrored, which makes the section the lower half's where the strand starts - its tails
        are swapped."""
        import numpy as np
        lay = self.trinity_layout()
        prof = np.column_stack([lay["upper"][:, 0] - lay["r_c"], lay["upper"][:, 1] - lay["z_c"]])
        return prof if side > 0 else prof * [1.0, -1.0]

    def trinity_ribbon_profile(self, side: int):
        """The knot's own section: a rounded rectangle, ribbon wide (across) x thickness (radial),
        its corners the band's edge round, sampled like the half's outline (SECTION_POINTS,
        counter-clockwise from the inner face's middle) so the tail can morph one into the other."""
        from shapely.geometry import Polygon
        t_k, w_k = self.trinity_thickness, self.trinity_ribbon
        corner = min(self.band.edge_round, t_k / 2 - 0.05, w_k / 2 - 0.05)
        rect = Polygon(knotwork.ribbon_profile(w_k, t_k, corner))
        pts = outline_points(rect, SECTION_POINTS, start=(-t_k / 2, 0.0))
        return pts if side > 0 else pts * [1.0, -1.0]

    def trinity_path(self, side: int) -> dict:
        """One shoulder's strand as a 3-D path in the ring frame with its section at every station:
        the half's outline where it leaves the loft, morphing over KNOT_TAPER_MM into the knot's
        ribbon (trinity_ribbon_profile), whose centre rides the mid law (knotwork.Interlace.depth:
        mid-depth between crossings, up or down by h = (t - fuse) / 2 at each; the plait's law -
        the bore law's full lift came back down too steeply for the ribbon's thickness, 2026-11-01)
        about a line (t / 2 + h + KNOT_LIFT_MM) above the bore, so a pass under lies KNOT_LIFT_MM
        clear of the bore. Returns the vertex rings too (knotwork.sweep_rings)."""
        import numpy as np
        lay = self.trinity_layout()
        st = self.trinity_strand(side)
        lace = self.trinity_laces()[0 if side > 0 else 1]
        s = st.params
        S = st.length
        d_end = np.minimum(s, S - s)                                        # distance to the nearer end
        prof = self.trinity_profile(side)
        ribbon = self.trinity_ribbon_profile(side)
        f = np.clip(d_end / KNOT_TAPER_MM, 0.0, 1.0)
        f = 0.5 * (1 - np.cos(np.pi * f))                                   # 0 at the half, 1 past the taper
        sections = prof[None, :, :] + (ribbon - prof)[None, :, :] * f[:, None, None]
        t_k = self.trinity_thickness
        h = (t_k - knotwork.KNOT_FUSE_MM) / 2
        r_half = lay["r_c"]                                                 # the half's centre, on the loft
        r_knot = self.band.bore_radius_mm + KNOT_LIFT_MM + t_k / 2 + h      # the knot's mid line
        u = lace.depth(0, s, law="mid")
        r = (1 - f) * r_half + f * (r_knot + h * u)
        t = np.radians(st.points[:, 0] * self.deg_per_mm)
        path = np.column_stack([r * np.cos(t), r * np.sin(t), st.points[:, 1]])
        up = np.column_stack([np.cos(t), np.sin(t), np.zeros_like(t)])
        rings, reversed_ = knotwork.sweep_rings(path, closed=False, up=up, profiles=sections)
        return dict(path=path, up=up, sections=sections, s=s, params=lace.params[0], rings=rings, reversed=reversed_)

    def trinity_strand_ring(self, side: int) -> list:
        """One shoulder's strand swept in the ring frame (trinity_path), in two pieces that share one
        section ring and its cap triangles: a sweep that passes over itself is no manifold
        (manifold3d left slivers in the union, 2026-11-01), so the strand is cut between its third
        and fourth crossing passes - each piece then holds one pass of every crossing. The strand's
        first and last caps are the ones the halves' lofts end in (trinity_end)."""
        import numpy as np
        d = self.trinity_path(side)
        s, cs = d["s"], d["params"]
        half = len(cs) // 2
        k = int(np.searchsorted(s, 0.5 * (cs[half - 1] + cs[half])))
        cut = knotwork.cap_triangles(d["sections"][k] if not d["reversed"] else d["sections"][k][::-1])
        first, last = self.trinity_end(side, "start"), self.trinity_end(side, "end")
        return [knotwork.mesh_from_rings(d["rings"][:k + 1], start_cap=first["strand_cap"], end_cap=cut),
                knotwork.mesh_from_rings(d["rings"][k:], start_cap=cut, end_cap=last["strand_cap"])]

    def trinity_end(self, side: int, end: str) -> dict:
        """Where a strand meets a half's loft: its first (`end` "start", the upper half) or last
        ring put in the order the loft runs its outline (counter-clockwise in (r, z) from the
        bore-side start: `ring`), the cap triangles over that ring (`cap`), and the same triangles
        indexed in the strand's own order (`strand_cap`) - one identical face for both bodies."""
        import numpy as np
        key = ("trinity_end", side, end)
        if key in self._cache:
            return self._cache[key]
        d = self.trinity_path(side)
        k = 1 if end == "start" else 0
        ring = d["rings"][0] if end == "start" else d["rings"][-1]
        theta = self.trinity_layout()["theta_1"] * (1 if side > 0 else -1)
        rz = self.loft_outline(k, theta, 0.5 * k)
        c, s_ = math.cos(math.radians(theta)), math.sin(math.radians(theta))
        target = np.column_stack([rz[:, 0] * c, rz[:, 0] * s_, rz[:, 1]])
        m = len(ring)
        best, best_err = None, float("inf")
        for sign in (1, -1):
            order = np.arange(m) if sign > 0 else np.arange(m)[::-1]
            for roll in range(m):
                perm = np.roll(order, roll)
                err = float(np.abs(ring[perm] - target).max())
                if err < best_err:
                    best, best_err = perm, err
                if best_err < 1e-9:
                    break
            if best_err < 1e-9:
                break
        if best_err > 0.05:
            raise RuntimeError(f"trinity: the strand's {end} ring does not meet the half's outline at {theta:.2f}° (off by {best_err:.3f} mm)")
        ordered = ring[best]
        cap = knotwork.cap_triangles(_rz(ordered, theta))
        out = dict(ring=ordered, cap=cap, strand_cap=best[cap], theta=theta)
        self._cache[key] = out
        return out

    def trinity_bend_radii(self, side: int = 1) -> tuple[float, float]:
        """(the strand's tightest bend in the surface, its tightest bend in 3-D), mm: a sweep whose
        path bends tighter than its section reaches turns inside out."""
        import numpy as np
        st = self.trinity_strand(side)
        d = self.trinity_path(side)

        def min_radius(P):
            P = np.asarray(P, float)
            a, b, c = P[:-2], P[1:-1], P[2:]
            ab, bc, ca = np.linalg.norm(b - a, axis=1), np.linalg.norm(c - b, axis=1), np.linalg.norm(c - a, axis=1)
            if P.shape[1] == 2:
                area2 = np.abs((b - a)[:, 0] * (c - a)[:, 1] - (b - a)[:, 1] * (c - a)[:, 0])
            else:
                area2 = np.linalg.norm(np.cross(b - a, c - a), axis=1)
            with np.errstate(divide="ignore", invalid="ignore"):
                radius = np.where(area2 > 1e-12, ab * bc * ca / np.where(area2 > 1e-12, 2 * area2, 1.0), np.inf)
            return float(np.nanmin(radius)) if len(radius) else float("inf")
        return min_radius(st.points), min_radius(d["path"])

    def trinity_half_angles(self, k: int) -> list[float]:
        """Station angles of half k's loft: from just past the tails' end round the bottom to just
        past the other shoulder's (the knots take over inside), the upper half's stations half a
        step on from the lower's (station_angles: coincident meridians across the overlap wedge
        came out of the union in slivers an STL round trip opened - seen again 2026-11-01). The
        loft's end stations are the strands' end rings themselves (trinity_end_ring)."""
        t1 = self.trinity_layout()["theta_1"]
        step = 360.0 / self.stations
        inner = [a for a in (step * (q + 0.5 * k) for q in range(self.stations + 1)) if t1 + 0.2 < a < 360.0 - t1 - 0.2]
        return [t1] + inner + [360.0 - t1]

    @property
    def nose_width(self) -> float:
        """The nose's width at its tip: the ribbon's two passes there and a little."""
        return self.trinity_ribbon + 0.6

    def pad_outline(self, theta_deg: float):
        """The section under the head at an angle: the band's own section, narrowing over the last
        KNOT_NOSE_MM of arc to a nose between the knot's lobes (the section clipped in z and
        re-rounded by the edge round), eroded towards a round end over the last edge round of arc
        (a cast end, not a step)."""
        from shapely.geometry import box
        sec = geom.section_polygon(self.band.notebook_inputs(""))
        e = self.band.edge_round
        a = abs(float(theta_deg))
        nose_deg = KNOT_NOSE_MM * self.deg_per_mm
        f = (a - (self.knot_pad_deg - nose_deg)) / nose_deg
        if f > 0:
            width = self.nose_width + (self.band.width_mm - self.nose_width) * 0.5 * (1 + math.cos(math.pi * min(f, 1.0)))
            b = self.band
            sec = geom.open_polygon(sec.intersection(box(b.bore_radius_mm - 1.0, -width / 2, b.outer_radius_mm + 1.0, width / 2)), e)
        e_deg = e * self.deg_per_mm
        over = a - (self.knot_pad_deg - e_deg)
        if over > 0:
            g = min(over / e_deg, 1.0)
            d = e * (1.0 - math.sqrt(max(0.0, 1.0 - g * g)))
            if d > 0:
                sec = sec.buffer(-min(d, e - 0.02), join_style="round")
        return outline_points(sec, SECTION_POINTS, start=(self.band.bore_radius_mm, 0.0))

    def pad_angles(self) -> list[float]:
        """Stations of the band under the head: the regular grid between the noses (never the
        wrap's cut angle, which lies between grid stations) and PAD_STEP_DEG steps along each nose."""
        tb = self.knot_pad_deg
        nose = KNOT_NOSE_MM * self.deg_per_mm
        step = 360.0 / self.stations
        grid = [a for a in (step * q for q in range(-self.stations // 2, self.stations // 2 + 1)) if abs(a) < tb - nose]
        n = max(int(math.ceil(nose / PAD_STEP_DEG)), 4)
        fine = [tb - nose * q / n for q in range(n + 1)]                    # tb - nose .. tb
        return sorted({-a for a in fine} | set(grid) | set(fine))

    def pad_ring(self):
        """The band under the head, lofted round the axis over ±knot_pad_deg, a nose at each end."""
        return loft_ring([(float(a), self.pad_outline(a)) for a in self.pad_angles()])

    def trinity_parts(self) -> list:
        """The bodies of the trinity shank in the ring frame: the two halves' lofts (clear of the
        knots), the two shoulders' strands and the pad."""
        parts = []
        for k in range(2):
            angles = self.trinity_half_angles(k)
            ends = ("start" if k == 1 else "end")                           # the strand starts in the upper half, ends in the lower
            first, last = self.trinity_end(1, ends), self.trinity_end(-1, ends)
            parts.append(loft_ring([(a, self.loft_outline(k, a, 0.5 * k)) for a in angles],
                                   first_ring=first["ring"], last_ring=last["ring"], first_cap=first["cap"], last_cap=last["cap"]))
        for side in (1, -1):
            parts += self.trinity_strand_ring(side)
        parts.append(self.pad_ring())
        return parts

    def trinity_section(self, theta_deg: float):
        """Which model the gate's section comes from at an angle: the design itself inside the knots
        and the pad (|θ| up to the tails' end plus half a millimetre), where the 2-D section model
        is not the body."""
        a = abs((float(theta_deg) + 180.0) % 360.0 - 180.0)
        return a <= self.trinity_layout()["theta_1"] + 0.5 * self.deg_per_mm

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

    @property
    def opening_chamfer_mm(self) -> float:
        """The chamfer nTop's re-distanced opening puts on the eroded corners (tables.opening_chamfer_mm)."""
        return 0.0 if (self.rope or self.knot) else tables.opening_chamfer_mm(self.band.mesh_tolerance_mm)

    def section_shape(self, theta_deg: float, skip: bool = True, chamfer_mm: float = 0.0):
        """The designed cross-section at an angle as a shapely geometry in (r, z): every strand's
        band section at its centreline, a bridge where one spans the angle, the slot taken out,
        and the whole opened by the edge round the way the notebook opens the bar - so a slot's
        and a bridge's fresh edges carry their fillets (the band's own are in the section already).
        A rope's or a knot's comes from the bar wrapped. None at an angle the model cannot show
        (shape_check_skips), unless `skip` is off (the lofts sample it everywhere). `chamfer_mm`
        emulates nTop's re-distanced opening (geom.open_polygon): the gate's model passes
        opening_chamfer_mm, the lofts stay exact."""
        from shapely.affinity import translate
        from shapely.geometry import box
        from shapely.ops import unary_union
        if self.rope or self.knot == "plait":
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
        return geom.open_polygon(sec, self.edge_round, chamfer_mm)

    def gate_section(self, theta_deg: float):
        """The section the gate expects nTop to have built at an angle (section_shape with the
        mesher's chamfer); through a trinity shank's knots and pad, the design itself (the 2-D
        section model is the halves' lofts, not the woven strands)."""
        if self.trinity and self.trinity_section(theta_deg):
            return gate.section_geometry(self.design_mesh(), theta_deg)
        return self.section_shape(theta_deg, chamfer_mm=self.opening_chamfer_mm)

    def opening_overcut_mm3(self) -> float:
        """What nTop's opening takes off beyond the design's rounds: the exact sections' volume
        less the chamfer-emulated sections' (Pappus station by station) - 1.0 mm³ on a court band,
        2 on a split, at 0.1 mm Mesh Tolerance (2026-10-31)."""
        if "overcut" not in self._cache:
            a = self.opening_chamfer_mm
            if a <= 0:
                self._cache["overcut"] = 0.0
            else:
                n = self.stations
                exact = chamfered = 0.0
                for k in range(n):
                    th = 360.0 * (k + 0.5) / n
                    exact += geom.polygon_revolved_volume(self.section_shape(th, skip=False)) / n
                    chamfered += geom.polygon_revolved_volume(self.section_shape(th, skip=False, chamfer_mm=a)) / n
                self._cache["overcut"] = max(0.0, exact - chamfered)
        return self._cache["overcut"]

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
        return 2 * math.pi * (self.band.bore_radius_mm + self.band.thickness_mm / 2)   # a knot's strands weave about it

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

    def slot_cutter(self, r_in: float, r_out: float, z_centre: float = 0.0):
        """The split's slot as a cutter in the ring frame: a sweep of rectangles r_in..r_out x
        ±slot_half_at(θ) round the axis over the slot's span (its round ends included), for
        whatever else straddles the slot - a solitaire's arches. The band itself carries its slot
        in its halves; this cutter has the same law."""
        import numpy as np
        import trimesh
        if self.split_mm <= 0.0:
            return None
        span = self.split_span_deg
        end_deg = (SLOT_END_MM / 2) / (self.wrap_length_mm / 360.0)
        n_in = max(int(math.ceil(2 * span / (360.0 / self.stations))), 8) + 1
        angles = ([-span + end_deg * (1.0 - math.cos(q * math.pi / 2)) for q in np.linspace(0.0, 1.0, 7)[:-1]]
                  + list(np.linspace(-span + end_deg, span - end_deg, n_in))
                  + [span - end_deg * (1.0 - math.cos(q * math.pi / 2)) for q in np.linspace(1.0, 0.0, 7)[1:]])
        secs = [(float(a), max(self.slot_half_at(a), 0.01)) for a in angles]
        V = []
        for a, h in secs:
            c, sn = math.cos(math.radians(a)), math.sin(math.radians(a))
            for r, z in ((r_in, -h), (r_out, -h), (r_out, h), (r_in, h)):
                V.append((r * c, r * sn, z_centre + z))
        V = np.asarray(V, float)
        F = []
        n = len(secs)
        for i in range(n - 1):
            a0 = 4 * i + np.arange(4)
            b0 = a0 + 4
            an, bn = np.roll(a0, -1), np.roll(b0, -1)
            F.append(np.column_stack([a0, an, bn]))
            F.append(np.column_stack([a0, bn, b0]))
        F = np.vstack(F + [np.array([[0, 2, 1], [0, 3, 2]]), 4 * (n - 1) + np.array([[0, 1, 2], [0, 2, 3]])])
        mesh = trimesh.Trimesh(V, F, process=False)
        trimesh.repair.fix_winding(mesh)
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
            return united([self.rope_tube_bar(k) for k in range(self.rope)])
        if self.knot == "plait":
            return united([self.knot_strand_bar(k) for k in range(self.knot_strands)])
        if self.split_mm:                                                   # a trinity shank is a split shank too
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
        return parts[0] if len(parts) == 1 else united(parts)

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
        bridges as sectors, united, a split cut out; a rope's or a knot's strands united."""
        if "design_mesh" not in self._cache:
            import trimesh
            if self.rope:
                body = united([self.rope_tube_ring(k) for k in range(self.rope)])
            elif self.knot == "plait":
                body = united([self.knot_strand_ring(k) for k in range(self.knot_strands)])
            elif self.trinity:
                # the lofts, sweeps and pad meet along many near-grazing lines; manifold3d leaves needle
                # faces there that float32 STL cannot hold (2026-11-01): merged within 0.1 µm, then united()'s collapse
                body = united(self.trinity_parts(), clean_mm=1e-4)
            else:
                parts = [self.strand_ring(k) for k in range(self.lofts)]
                parts += [self.bridge_sector(*b) for b in self.bridge_spans()]
                body = parts[0] if len(parts) == 1 else united(parts)
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
        rope or a knot (their strands cross the meridian obliquely)."""
        import numpy as np
        if self.rope or self.knot:
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
        if self.knot == "plait":
            return 2 * self.knot_amplitude + self.knot_width                   # the band's width: the weave fills it
        if self.trinity:
            b = self.design_mesh().bounds
            return float(b[1][2] - b[0][2])                                    # the knots reach past the band's edges
        lo = min(self.section_bounds(t)[0] for t in self.station_angles())
        hi = max(self.section_bounds(t)[1] for t in self.station_angles())
        return hi - lo

    @property
    def outer_radius_mm(self) -> float:
        """The largest radius the ring reaches (at the head)."""
        if self.rope:
            return self.rope_centre_radius + self.rope_offset + self.rope_radius
        if self.trinity:
            import numpy as np
            v = self.design_mesh().vertices
            return float(np.hypot(v[:, 0], v[:, 1]).max())                    # a strand passing over stands proud
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
                  "rope_offset_frac": self.rope_offset_frac if self.rope else 0.0,
                  "knot": self.knot, "knot_strands": self.knot_strands if self.knot else 0,
                  "knot_repeats": self.knot_repeats if self.knot else 0,
                  "knot_strand": (self.trinity_ribbon if self.trinity else self.knot_width) if self.knot else 0.0,
                  "knot_profile": self.knot_profile if self.knot else "", "knot_fuse": knotwork.KNOT_FUSE_MM if self.knot else 0.0,
                  "knot_width": self.trinity_width if self.trinity else 0.0, "knot_ratio": self.knot_ratio if self.trinity else 0.0,
                  "knot_pad_deg": self.knot_pad_deg if self.trinity else 0.0, "knot_tail": self.knot_tail_mm if self.trinity else 0.0})
        return d

    @property
    def spec_id(self) -> str:
        return runs.spec_id(self.design())

    @property
    def shape_tag(self) -> str:
        """The shank's shape in a file stem: `w<head>-<bottom>_t<head>-<bottom>[_contour1.5|_chevron2][_x2|_x2m][_split1.6]`,
        a rope `rope<strands>x<turns>_d<strand>`, a knot `plait<strands>x<repeats>_w<strand>t<thickness>` (a wire
        `_d<diameter>`)."""
        b = self.band
        if self.rope:
            return f"rope{self.rope}x{self.rope_turns:g}_d{self.rope_strand_mm:g}"
        if self.knot == "plait":
            section = f"d{self.knot_thickness:g}" if self.knot_profile == "round" else f"w{self.knot_width:g}t{self.knot_thickness:g}"
            return f"{self.knot}{self.knot_strands}x{self.knot_repeats}_{section}"
        shape = ""
        if self.dip_mm:
            shape += f"_{self.dip_shape}{self.dip_mm:g}"
        if self.strands > 1:
            shape += f"_x2{'m' if self.mirror else ''}"
        if self.split_mm:
            shape += f"_split{self.split_mm:g}"
        if self.trinity:
            shape += f"_trinity{self.trinity_width:g}"
        return f"w{b.width_mm:g}-{self.width_bottom:g}_t{b.thickness_mm:g}-{self.thickness_bottom:g}{shape}"

    @property
    def stem(self) -> str:
        b = self.band
        if self.rope or self.knot == "plait":
            head, _, section = self.shape_tag.partition("_")                   # rope2x10_US6_d1.2, plait3x4_US6_w1.2t0.85
            return f"ring_shank_{head}_{b.label}_{section}_{self.spec_id}"
        return f"ring_shank_{b.profile}_{b.label}_{self.shape_tag}_{self.spec_id}"

    @property
    def edge_round(self) -> float:
        """The opening (Offset -e, +e) the notebook runs over the wrapped body: the band's edge
        round. The band's own edges are rounded that much in the section already (a no-op for
        them); it rounds the edges the cuts and unions leave sharp - a split's slot, a bridge."""
        return 0.0 if (self.rope or self.knot) else self.band.edge_round

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
        """What the notebook's opening takes off the design's sharp convex edges (a bridge's ends:
        geom.sharp_edge_round_mm3 over the design mesh); the band's rounded edges turn in small
        steps and do not count."""
        return geom.sharp_edge_round_mm3(self.design_mesh(), self.edge_round) if self.edge_round > 0 else 0.0

    def expected_volume_mm3(self) -> float:
        """What nTop should report: the design sweep less the opening's rounding of its sharp edges,
        less the mesher's chamfer on every round (opening_overcut_mm3)."""
        return self.design_volume_mm3() - self.sharp_edge_round_mm3() - self.opening_overcut_mm3()

    def validate(self) -> list[str]:
        if self.rope:
            return self._validate_rope()
        if self.knot == "plait":
            return self._validate_knot()
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
        if not p and self.knot:
            p += self._validate_trinity()
        if not p and self.lofts == 2:
            m = self.design_mesh()
            if m.body_count != 1:
                p.append(f"the strands and bridges make {m.body_count} bodies, not one ring")
        return p

    def _validate_trinity(self) -> list[str]:
        if self.knot != "trinity":
            return [f"knot {self.knot!r}: plait (a band) or trinity (on a split shank)"]
        p = []
        if not self.split_mm:
            p.append("trinity knots are woven from a split shank's two halves: --split")
        floor = tables.FLOORS["wall_good"]
        if self.trinity_ribbon < floor or self.trinity_thickness < floor:
            p.append(f"the knot's ribbon ({self.trinity_ribbon:g} wide x {self.trinity_thickness:.2f} thick): at least {floor:g} mm each way")
        if self.split_mm and self.trinity_ribbon > (self.band.width_mm - self.split_mm) / 2 + 1e-9:
            p.append(f"the knot's ribbon ({self.trinity_ribbon:g} mm) is wider than a half of the split ({(self.band.width_mm - self.split_mm) / 2:g} mm)")
        if self.trinity_thickness > self.trinity_thickness_max + 1e-9:
            p.append(f"the knot's ribbon ({self.trinity_thickness:.2f} mm thick): at most {self.trinity_thickness_max:.2f} on a "
                     f"{self.band.thickness_mm:g} mm band (a pass under the band's nose keeps clear of its crown)")
        if self.dip_mm or self.strands > 1 or self.rope:
            p.append("trinity knots take no dip, double or rope")
        if not 0.3 <= self.knot_ratio <= 0.7:
            p.append(f"knot ratio {self.knot_ratio:g}: 0.3..0.7")
        if not 5.0 <= self.knot_pad_deg <= 80.0:
            p.append(f"pad {self.knot_pad_deg:g}°: 5..80° either side of the head")
        if not 0.5 <= self.knot_tail_mm <= 10.0:
            p.append(f"tail {self.knot_tail_mm:g} mm: 0.5..10")
        if self.trinity_width < self.band.width_mm:
            p.append(f"knot width {self.trinity_width:g} mm: at least the band's {self.band.width_mm:g}")
        if p:
            return p
        lay = self.trinity_layout()
        R, c = lay["R"], self.knot_ratio
        inner = math.sqrt(3.0) * R * (1 - c)                                # between the three inner passes
        if inner < self.trinity_ribbon + knotwork.KNOT_GAP_MIN_MM:
            p.append(f"the knot's centre closes: its three inner passes are {inner:.2f} mm apart for a {self.trinity_ribbon:g} mm "
                     f"ribbon (needs {self.trinity_ribbon + knotwork.KNOT_GAP_MIN_MM:g}): a wider knot, a narrower ribbon or a smaller ratio")
        clear = (lay["y_c"] - 0.5 * R * (1 - c) - self.trinity_ribbon / 2) - lay["y_pad"]   # the inner passes past the nose's tip
        if clear < KNOT_NOSE_CLEAR_MM:
            p.append(f"the knot's inner passes come within {clear:.2f} mm of the nose under the head (need {KNOT_NOSE_CLEAR_MM:g}): "
                     f"a wider knot or a narrower ribbon")
        if self.trinity_width > 2 * self.band.width_mm:
            p.append(f"knot width {self.trinity_width:g} mm: at most twice the band's")
        end_deg = (SLOT_END_MM / 2) * self.deg_per_mm
        if lay["theta_1"] + 3.0 > self.split_span_deg - end_deg:
            p.append(f"the tails end {lay['theta_1']:.1f}° from the head, where the slot has closed (span {self.split_span_deg:g}°): "
                     f"a longer split span, a shorter tail or a smaller pad")
        if self.tapered and self.taper_from_deg < lay["theta_1"] + 2.0:
            p.append(f"the taper starts {self.taper_from_deg:g}° from the head, inside the knot (to {lay['theta_1']:.1f}°)")
        if p:
            return p
        for side, lace in zip((1, -1), self.trinity_laces()):
            if lace.problems:
                p.append(f"{'+' if side > 0 else '-'}θ knot: " + "; ".join(lace.problems))
                break
        if not p:
            flat, solid = self.trinity_bend_radii()
            if flat < self.trinity_ribbon / 2 + 0.1:
                p.append(f"the knot's strand bends to a {flat:.2f} mm radius in the surface, tighter than its {self.trinity_ribbon:g} mm "
                         f"ribbon turns (needs {self.trinity_ribbon / 2 + 0.1:.2f}): a wider knot, a narrower ribbon or a smaller ratio")
            if solid < self.trinity_thickness / 2 + 0.1:
                p.append(f"the knot's strand rises and falls on a {solid:.2f} mm radius, tighter than its {self.trinity_thickness:.2f} mm "
                         f"thickness turns (needs {self.trinity_thickness / 2 + 0.1:.2f}): a wider knot or a thinner ribbon")
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

    def _validate_knot(self) -> list[str]:
        p = []
        if self.knot != "plait":
            return [f"knot {self.knot!r}: plait is the pattern there is"]
        if not 2 <= self.knot_strands <= 4:
            p.append(f"plait of {self.knot_strands} strands: 2..4")
        if not (1 <= self.knot_repeats <= 12 and self.knot_repeats == int(self.knot_repeats)):
            p.append(f"plait repeats {self.knot_repeats!r}: a whole number, 1..12 round the ring")
        if self.knot_profile not in ("flat", "round"):
            p.append(f"knot profile {self.knot_profile!r}: flat or round")
        t, w = self.knot_thickness, self.knot_width
        floor = tables.FLOORS["wall_good"]
        if t < floor:
            p.append(f"a strand would be {t:.2f} mm thick (half the band's {self.band.thickness_mm:g} mm plus the "
                     f"{knotwork.KNOT_FUSE_MM:g} mm fuse); at least {floor:g} mm: a band {2 * floor - knotwork.KNOT_FUSE_MM:g} mm thick or more")
        if self.knot_profile == "flat" and w < floor:
            p.append(f"strand width {w:g} mm: at least {floor:g} mm")
        if 2 * self.knot_amplitude < w:
            p.append(f"{self.knot_strands} strands {w:g} mm wide do not weave in a {self.band.width_mm:g} mm band: "
                     f"at least {2 * w:g} mm wide")
        if not 10.0 <= self.band.inner_diameter_mm <= 25.0:
            p.append(f"inner diameter {self.band.inner_diameter_mm:.2f} mm is outside 10..25 mm")
        if self.tapered or self.dip_mm or self.strands > 1 or self.split_mm:
            p.append("a knot takes no taper, dip, double or split")
        if p:
            return p
        lace = self.knot_layout()
        p += lace.problems
        least = w + knotwork.KNOT_GAP_MIN_MM
        tight = [(k, d) for k, d in knotwork.pair_openings(self.knot_strand_set()).items() if d < least]
        if tight:
            k, d = min(tight, key=lambda kd: kd[1])
            p.append(f"strands {k[0]} and {k[1]} part by only {d:.2f} mm between crossings; {least:g} mm "
                     f"({knotwork.KNOT_GAP_MIN_MM:g} mm clear) keeps the weave open: a wider band, narrower strands or fewer of them")
        if not p:
            m = self.design_mesh()
            if m.body_count != 1:
                p.append(f"the {self.knot_strands} strands make {m.body_count} bodies, not one ring")
        return p

    def warnings(self) -> list[str]:
        if self.rope:
            return []
        if self.knot:
            w = []
            ang = knotwork.plait_crossing_angle_deg(self.knot_amplitude, self.knot_repeats, self.wrap_length_mm)
            if ang < knotwork.KNOT_ANGLE_MIN_DEG:
                w.append(f"the strands cross at {ang:.0f}°: a shallow weave fuses them over long runs (more repeats, or a wider band)")
            return w
        return list(self.band.warnings())

    def wall_floor(self) -> float:
        """The ray-cast thickness floor: the material floor, or 0.8 x the thinnest station's edge
        (a rope: 0.8 x a strand's diameter)."""
        if self.rope:
            return min(tables.FLOORS["wall_marginal"], 0.8 * self.rope_strand_mm)
        if self.knot:
            return min(tables.FLOORS["wall_marginal"], 0.8 * self.knot_thickness)
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
        if self.knot == "plait":
            lace = self.knot_layout()
            section = (f"round wires {self.knot_thickness:g} mm" if self.knot_profile == "round"
                       else f"ribbons {self.knot_width:g} wide x {self.knot_thickness:g} thick (corners {min(b.edge_round, self.knot_thickness / 2):g})")
            return (f"{self.stem}: {b.label}, inner Ø {b.inner_diameter_mm:.3f}\n"
                    f"  {self.knot} of {self.knot_strands} {section}, {self.knot_repeats} repeat{'s' if self.knot_repeats != 1 else ''} round the ring: "
                    f"{len(lace.crossings)} crossings, {lace.count(0)} on each strand, over and under in turn; "
                    f"rise {self.knot_rise:.3f} mm either way about r {self.knot_mid_radius:.3f}, fused {knotwork.KNOT_FUSE_MM:g} mm; "
                    f"crossing angle {knotwork.plait_crossing_angle_deg(self.knot_amplitude, self.knot_repeats, self.wrap_length_mm):.0f}°\n"
                    f"  envelope {self.overall_width_mm:g} wide x {b.thickness_mm:g} thick (bore r {b.bore_radius_mm:.3f}, outer r {b.outer_radius_mm:.3f}); "
                    f"{self.knot_points} samples per strand; wrap length {self.wrap_length_mm:.3f} mm; design volume {self.design_volume_mm3():.2f} mm³")
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
        if self.trinity:
            lay = self.trinity_layout()
            lace = self.trinity_laces()[0]
            line += (f"\n  trinity knots on the shoulders: trefoil R {lay['R']:.2f} (ratio {self.knot_ratio:g}) centred {lay['y_c'] * self.deg_per_mm:.1f}° from the head, "
                     f"{len(lace.crossings)} self-crossings at {lace.crossings[0].angle_deg:.0f}°; ribbon {self.trinity_ribbon:g} wide x "
                     f"{self.trinity_thickness:.2f} thick, lifting {self.trinity_thickness - knotwork.KNOT_FUSE_MM:.2f} mm to pass over itself; "
                     f"lobes {self.trinity_width:g} mm across either side of the band's nose under the head (to ±{self.knot_pad_deg:g}°); "
                     f"tails to {lay['theta_1']:.1f}°")
        line += (f"\n  {self.stations} stations x {SECTION_POINTS} points; wrap length {self.wrap_length_mm:.3f} mm; "
                 f"overall width {self.overall_width_mm:.2f} mm; design volume {self.design_volume_mm3():.2f} mm³")
        rounded, overcut = self.sharp_edge_round_mm3(), self.opening_overcut_mm3()
        if rounded or overcut:
            line += (f"; nTop's {self.edge_round:g} mm opening takes off " + (f"{rounded:.2f} mm³ at the sharp edges" if rounded else "")
                     + (" and " if rounded and overcut else "") + (f"{overcut:.2f} mm³ with its mesher's chamfer on the rounds" if overcut else "")
                     + f" (expect {self.expected_volume_mm3():.2f})")
        return line


# ---- outlines ----------------------------------------------------------------------------------
def loft_ring(stations: list[tuple[float, "numpy.ndarray"]], first_ring=None, last_ring=None, first_cap=None, last_cap=None):
    """An open loft round the axis: (angle, (SECTION_POINTS, 2) outline in (r, z)) stations joined
    vertex to vertex, capped at both ends. `first_ring` / `last_ring` ((SECTION_POINTS, 3) vertices
    in the outline's order) replace the end stations' vertices, `first_cap` / `last_cap` ((t, 3)
    index triangles) the caps' triangulation: the exact ring and cap of the body that continues
    the loft, so the two meet in one identical face."""
    import numpy as np
    import trimesh
    m = SECTION_POINTS
    verts = []
    for a, rz in stations:
        c, s_ = math.cos(math.radians(a)), math.sin(math.radians(a))
        verts.append(np.column_stack([rz[:, 0] * c, rz[:, 0] * s_, rz[:, 1]]))
    if first_ring is not None:
        verts[0] = np.asarray(first_ring, float)
    if last_ring is not None:
        verts[-1] = np.asarray(last_ring, float)
    V = np.vstack(verts)
    faces = []
    for i in range(len(stations) - 1):
        a0 = i * m + np.arange(m)
        b0 = a0 + m
        an, bn = np.roll(a0, -1), np.roll(b0, -1)
        faces.append(np.column_stack([a0, an, bn]))
        faces.append(np.column_stack([a0, bn, b0]))
    F = np.vstack(faces)
    tri0 = np.asarray(first_cap, int) if first_cap is not None else _outline_triangles(_rz(verts[0], stations[0][0]))
    tri1 = np.asarray(last_cap, int) if last_cap is not None else _outline_triangles(_rz(verts[-1], stations[-1][0]))
    F = np.vstack([F, tri0[:, ::-1], tri1 + (len(stations) - 1) * m])
    mesh = trimesh.Trimesh(V, F, process=False)
    trimesh.repair.fix_winding(mesh)
    if mesh.volume < 0:
        mesh.invert()
    return mesh


def _rz(ring, angle_deg: float):
    """(r, z) of a vertex ring at a meridian angle."""
    import numpy as np
    c, s_ = math.cos(math.radians(angle_deg)), math.sin(math.radians(angle_deg))
    return np.column_stack([ring[:, 0] * c + ring[:, 1] * s_, ring[:, 2]])


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
    if not mesh.is_watertight:
        # a bar read back from float32 STL: a vertex a hair off its twin leaves a slit at the seam
        # (a trinity shank, 2026-11-01); merging within 0.01 µm closes it without moving a surface
        mesh.merge_vertices(digits_vertex=5)
        mesh.update_faces(mesh.nondegenerate_faces(height=1e-7))
        mesh.remove_unreferenced_vertices()
    return mesh


def united(parts, clean_mm: float = 0.0):
    """manifold3d's union of `parts`, its zero-volume specks dropped (drop_specks), optionally
    tidied within `clean_mm` (geom.clean), and every edge shorter than MIN_EDGE_MM collapsed
    (geom.collapse_short_edges) - the mesh every bar and every design body comes from."""
    import trimesh
    body = drop_specks(trimesh.boolean.union(parts, engine="manifold"))
    if clean_mm > 0:
        body = geom.clean(body, clean_mm)
    return geom.collapse_short_edges(body, MIN_EDGE_MM)


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
    comes back from a turn rotated, and the bar's two cuts no longer matched - 2026-10-30).
    knotwork.sweep_along with a round section."""
    return knotwork.sweep_along(path, knotwork.wire_profile(2 * radius, points), closed, up)


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
                     section_design=spec.gate_section, section_tol_mm=band.section_shape_tolerance(b.mesh_tolerance_mm))
    c = band.design_volume_check(spec.expected_volume_mm3(), ntop_vol, 2.0)
    rounded, overcut = spec.sharp_edge_round_mm3(), spec.opening_overcut_mm3()
    if (rounded or overcut) and c.status != gate.INCOMPLETE:
        c.detail += (f" [design {spec.design_volume_mm3():.2f}" + (f" less {rounded:.2f} mm³ of edge rounding" if rounded else "")
                     + (f" less {overcut:.2f} mm³ the mesher's chamfer takes off the rounds" if overcut else "") + "]")
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
        "expected_volume_mm3": spec.expected_volume_mm3(), "opening_overcut_mm3": spec.opening_overcut_mm3(), "gate": rep.to_dict(),
        "ntopcl_seconds": run.seconds, "block_timings": [t.__dict__ for t in run.log.timings], "notes": result.notes,
        "notebook": runs.notebook_identity(nb), "environment": runs.environment(ntopcl.version()),
    }
    (run_dir / f"{stem}.report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    if deliver and result.ok:
        result.delivered = runs.deliver(stl, run_dir, stem, deliver_project, report, extra_files=[bar], cast_metal=cast_metal)
    elif deliver:
        result.notes.append(f"not delivered: status {result.status}")
    return result
