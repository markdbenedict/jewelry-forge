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
bridges at `bridges_deg` (full-thickness bars `bridge_mm` long round the ring). Each strand goes
in a bar of its own and the bridges in another, and nTop unites them (`bar_meshes`); the
independent sweep unites them in the ring frame (a bridge there is the sector the wrapped bar
makes of it).

Step 1c: a split (`split_mm`: the halves lofted the whole way round, the slot's fillets in the
bar) and a rope (`rope`: round strands twisted round the ring). Step 1e, Celtic knotwork
(`knot`, knotwork.py): strands interlaced in the ring's surface - a plait of two to four ribbons
(or round wires) weaving the whole way round, each strand rising over and sinking under the
others at its crossings, the band's width and thickness its envelope. A twist (`knot="twist"`,
rings 06 / 07) crosses a split's halves over each other on each shoulder: still the split's two
lofts, each the whole way round, their sections morphing through the crossing zones.

Bodies that cross or overlap each other travel to nTop in separate bars (up to BAR_SLOTS files,
each clean on its own) and nTop's implicit union joins them: a mesh union of crossing bodies
leaves faces micrometres apart along its seams, which float32 STL and nTop's import turned into
a self-intersecting bar (the trinity shank, 2026-11-02). No bar carries a mesh union; the
independent model (`design_mesh`) still unites in the ring frame, in memory, for the gate.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from . import band, catalog, config, gate, geom, knotwork, ntopcl, runs, tables
from .nb_jewel import BAR_SLOTS, SLOT_NAMES, slot_name   # the notebook's bar inputs (ring_shank.ntop and the solitaires)

BAR_OVERLAP_MM = 1.0        # the bar runs this far past the turn at both ends: the seam is inside material
SECTION_POINTS = 256        # every station's outline resampled to this many points (lofted vertex to vertex)
CHECK_ANGLES_DEG = tuple(range(0, 360, 30))   # where the gate measures the built section against the design
SECTION_TOL_MM = 0.06       # width / thickness at a station: the mesh tolerance plus a little
SPLIT_STRAND_MIN_MM = 1.0   # each half of a split shank keeps at least this width at the head
SLOT_END_MM = 0.4           # a split closes into a round end this wide (a cast slot cannot end in a crack)
SPLIT_OVERLAP_MM = 0.1      # a split's two halves, lofted the whole way round, overlap at least this much where the slot is
                            # closed - and more than the edge round when the notebook opens the bars (split_overlap_mm)
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
# one identical face unite cleanly in the independent model, where overlaps drawn a hair apart left needle
# faces (2026-11-01). The bars nTop gets are different: there every piece runs PLUG_MM into the body that
# continues it (plug_rings), because an implicit union of two bodies that share a face sees a zero-thickness
# interface, and bodies that cross each other go in separate bars (bar_meshes).
MIN_EDGE_MM = 2e-4          # every union's result has its shorter edges collapsed (geom.collapse_short_edges): nTop merges
                            # "very close vertices" on import (routine: an STL is a triangle soup), and edges of 1.5 µm
                            # went with them (the trinity shank, 2026-11-01)
PLUG_MM = 0.1               # a bar piece runs this far into the body that continues it (a knot's strand into its half, its other piece)
PLUG_INSET = 0.04           # ... its section drawn in by this fraction over the plug, so the plug lies inside that body
KNOT_LIFT_MM = 0.1          # a trinity knot's ribbon runs this far above the bore (buried clear of the pad's bore where it enters it)
KNOT_TAPER_MM = 1.5         # the tail narrows from the half's section to the knot's ribbon over this run
PAD_STEP_DEG = 1.0          # stations along the pad a knot's lobes run into
TWIST_OVER = 1              # a twist: the loft that is the upper half (z > 0) round the bottom passes over at both crossings
                            # (the shoulders mirror each other, as a ring seen from the front should)
TWIST_RAMP_MIN_MM = 1.0     # ... the over strand rises from the band (comes back down to it) over at least this run each side
TWIST_CLEAR_MM = 0.05       # ... and stays up until the two strands' footprints across the ring are this far apart
TWIST_STATIONS = 360        # a twist's lofts take a section every degree at least (its over strand lifts within a few mm)
TWIST_SAMPLES = 801         # samples along a crossing zone for its layout (where the strands cross, how long they overlap)


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
    twist_length_mm: float = 8.0                    # twist: the halves cross over this run of each shoulder (mm along the ring),
                                                    # between the band under the head (to ±knot_pad_deg) and the split
    hammer: object = None                           # texture.Hammer: a hammered outer face (ring_shank's Strikes; the solitaires')
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
        for contour, straight for chevron). A twist's slot is two eyes on each shoulder: closed under
        the head, split_mm where the strands leave the band and again where they reach the halves
        (the crossing zone between), then the law from there to split_span_deg."""
        if self.split_mm == 0.0:
            return 0.0
        a = abs((float(theta_deg) + 180.0) % 360.0 - 180.0)
        if a >= self.split_span_deg:
            return 0.0
        f = a / self.split_span_deg
        if self.twist:
            tp, t1 = self.twist_span()[:2]
            if a < t1:
                return self.split_mm if a >= tp else 0.0
            f = (a - t1) / max(self.split_span_deg - t1, 1e-9)
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

    def trinity_cut(self, side: int) -> int:
        """The station a shoulder's strand is cut at: between its third and fourth crossing passes
        (a sweep that passes over itself is no manifold - manifold3d left slivers in the union,
        2026-11-01), so each piece holds one pass of every crossing."""
        import numpy as np
        d = self.trinity_path(side)
        s, cs = d["s"], d["params"]
        half = len(cs) // 2
        return int(np.searchsorted(s, 0.5 * (cs[half - 1] + cs[half])))

    def trinity_strand_ring(self, side: int) -> list:
        """One shoulder's strand swept in the ring frame (trinity_path), in two pieces (trinity_cut)
        that share one section ring and its cap triangles; the strand's first and last caps are the
        ones the halves' lofts end in (trinity_end). The independent model's pieces: bodies that
        meet in one identical face unite exactly."""
        d = self.trinity_path(side)
        k = self.trinity_cut(side)
        cut = knotwork.cap_triangles(d["sections"][k] if not d["reversed"] else d["sections"][k][::-1])
        first, last = self.trinity_end(side, "start"), self.trinity_end(side, "end")
        return [knotwork.mesh_from_rings(d["rings"][:k + 1], start_cap=first["strand_cap"], end_cap=cut),
                knotwork.mesh_from_rings(d["rings"][k:], start_cap=cut, end_cap=last["strand_cap"])]

    def trinity_strand_bars(self, side: int) -> list:
        """The same two pieces for the notebook: each runs PLUG_MM into the body that continues it -
        the half's loft at the strand's ends, the other piece at the cut - its section drawn in by
        PLUG_INSET over the plug (plug_rings), so nTop's union sees an overlap, never a shared face
        (a zero-thickness interface to an implicit union). The first piece travels with the lower
        half's loft, the second with the upper's (bar_meshes): a piece and the half it does not
        touch."""
        d = self.trinity_path(side)
        k = self.trinity_cut(side)
        return [knotwork.mesh_from_rings(plug_rings(d["rings"][:k + 1])), knotwork.mesh_from_rings(plug_rings(d["rings"][k:]))]

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

    def trinity_half_loft(self, k: int):
        """Half k's loft in the ring frame (trinity_half_angles), clear of the knots: it ends in the
        strands' end rings themselves (trinity_end) - the lower half (0) where the strands end, the
        upper (1) where they start."""
        angles = self.trinity_half_angles(k)
        ends = ("start" if k == 1 else "end")                               # the strand starts in the upper half, ends in the lower
        first, last = self.trinity_end(1, ends), self.trinity_end(-1, ends)
        return loft_ring([(a, self.loft_outline(k, a, 0.5 * k)) for a in angles],
                         first_ring=first["ring"], last_ring=last["ring"], first_cap=first["cap"], last_cap=last["cap"])

    def trinity_parts(self) -> list:
        """The bodies of the trinity shank in the ring frame: the two halves' lofts (clear of the
        knots), the two shoulders' strands and the pad."""
        parts = [self.trinity_half_loft(k) for k in range(2)]
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

    def woven_section(self, theta_deg: float) -> bool:
        """Whether the gate's section at an angle comes from the design itself: inside a trinity's
        knots and nose, or a twist's crossing zone and the eye's end under the head."""
        return bool((self.trinity and self.trinity_section(theta_deg)) or (self.twist and self.twist_section(theta_deg)))

    # ---- twist: the halves of a split shank cross over each other on each shoulder (rings 06, 07) ---
    @property
    def twist(self) -> bool:
        return self.knot == "twist"

    @property
    def twist_thickness(self) -> float:
        """Each strand's radial thickness where the two cross (both thin to it there, the over strand
        lying on the under one, fused KNOT_FUSE_MM): --knot-thickness, or 0.7 x the band's, at
        least the good wall."""
        if self.knot_thickness_mm:
            return float(self.knot_thickness_mm)
        return min(self.band.thickness_mm, max(0.7 * self.band.thickness_mm, tables.FLOORS["wall_good"]))

    def twist_span(self) -> tuple[float, float, float, float]:
        """(theta_p, theta_1, y_p, y_1): a shoulder's crossing zone in degrees from the head and in mm
        along the ring - from where the strands leave the band under the head (knot_pad_deg, the
        eye's widest point there) to where they become the split's halves (twist_length_mm on)."""
        tp = float(self.knot_pad_deg)
        t1 = tp + self.twist_length_mm * self.deg_per_mm
        return tp, t1, tp / self.deg_per_mm, t1 / self.deg_per_mm

    def twist_zone(self, theta_deg: float) -> bool:
        """Inside a crossing zone (its two end angles, where the strands are the halves, are not)."""
        a = abs((float(theta_deg) + 180.0) % 360.0 - 180.0)
        tp, t1 = self.twist_span()[:2]
        return tp + 1e-9 < a < t1 - 1e-9

    def twist_section(self, theta_deg: float) -> bool:
        """The gate takes a twist's section from the design across the crossing zone and the eye's
        round end into the band under the head (plus half a millimetre either side)."""
        a = abs((float(theta_deg) + 180.0) % 360.0 - 180.0)
        tp, t1 = self.twist_span()[:2]
        margin = (self.split_mm / 2 + 0.5) * self.deg_per_mm
        return tp - margin <= a <= t1 + 0.5 * self.deg_per_mm

    def _twist_ends(self, k: int, phase: float):
        """Loft k's outline where its strand begins (half k at theta_1) and ends (the other half,
        under the head, at theta_p), both started below their own centre."""
        key = ("twist_ends", k, phase)
        if key not in self._cache:
            tp, t1 = self.twist_span()[:2]
            self._cache[key] = (self._split_outline(k, t1, phase, centred=True), self._split_outline(1 - k, tp, phase, centred=True))
        return self._cache[key]

    def _twist_base(self, k: int, y: float, phase: float = 0.0):
        """Loft k's strand at y mm from the head before the crossing's lift and thinning: (its centre
        (r, z), its shape about the centre, the centre's slope dr/dy). The shape morphs from the half
        at y_1 into the mirror-image half at y_p and the centre follows (both by g = (1 - cos πτ) / 2,
        so the path is a half cosine, level at both ends); the shape is stretched across the ring by
        the path's slope, so the meridian section of an oblique strand keeps the strand's width."""
        import numpy as np
        A, B = self._twist_ends(k, phase)
        _, _, y_p, y_1 = self.twist_span()
        tau = min(max((y_1 - y) / (y_1 - y_p), 0.0), 1.0)
        g = 0.5 * (1.0 - math.cos(math.pi * tau))
        dg = 0.5 * math.pi * math.sin(math.pi * tau) / (y_1 - y_p)          # |dg/dy|
        cA, cB = A.mean(axis=0), B.mean(axis=0)
        S = (1.0 - g) * (A - cA) + g * (B - cB)
        c = cA + g * (cB - cA)
        S[:, 1] *= math.sqrt(1.0 + ((cB[1] - cA[1]) * dg) ** 2)
        return c, S, (cB[0] - cA[0]) * dg

    def twist_layout(self) -> dict:
        """A shoulder's crossing, measured on the strands' centres and widths along the zone: where
        they cross (y_x, the angle between them), how far either side their footprints across the
        ring overlap (+ TWIST_CLEAR_MM: the over strand's plateau, plat_lo / plat_hi), the ramps left
        between the plateau and the zone's ends, and the over strand's lift at the crossing (its
        inner face on the under strand's outer face, the strands thinned to twist_thickness, fused
        KNOT_FUSE_MM)."""
        if "twist" in self._cache:
            return self._cache["twist"]
        import numpy as np
        tp, t1, y_p, y_1 = self.twist_span()
        ys = np.linspace(y_p, y_1, TWIST_SAMPLES)
        base = [[self._twist_base(k, float(y)) for y in ys] for k in (0, 1)]
        cz = np.array([[b[0][1] for b in base[k]] for k in (0, 1)])
        w = np.array([[float(np.ptp(b[1][:, 1])) for b in base[k]] for k in (0, 1)])
        d = cz[0] - cz[1]
        sign = np.nonzero(np.diff(np.sign(d)) != 0)[0]
        if len(sign) == 0:
            raise ValueError("twist: the strands do not cross in the zone")
        i = int(sign[len(sign) // 2])
        f = d[i] / (d[i] - d[i + 1])
        y_x = float(ys[i] + f * (ys[i + 1] - ys[i]))
        overlap = np.abs(d) < (w[0] + w[1]) / 2 + TWIST_CLEAR_MM
        lo = i
        while lo > 0 and overlap[lo - 1]:
            lo -= 1
        hi = i + 1
        while hi < len(ys) - 1 and overlap[hi + 1]:
            hi += 1
        plat_lo, plat_hi = y_x - float(ys[max(lo - 1, 0)]), float(ys[min(hi + 1, len(ys) - 1)]) - y_x
        slopes = np.gradient(cz, ys, axis=1)
        s0, s1 = float(np.interp(y_x, ys, slopes[0])), float(np.interp(y_x, ys, slopes[1]))
        angle = math.degrees(abs(math.atan(s0) - math.atan(s1)))
        cu, Su, _ = self._twist_base(1 - TWIST_OVER, y_x)
        co, So, _ = self._twist_base(TWIST_OVER, y_x)
        t_x = self.twist_thickness
        lift = (cu[0] + Su[:, 0].min() + t_x - knotwork.KNOT_FUSE_MM) - (co[0] + So[:, 0].min())
        out = dict(theta_p=tp, theta_1=t1, y_p=y_p, y_1=y_1, y_x=y_x, theta_x=y_x * self.deg_per_mm,
                   plat_lo=plat_lo, plat_hi=plat_hi, ramp_lo=(y_x - plat_lo) - y_p, ramp_hi=y_1 - (y_x + plat_hi),
                   lift=float(lift), angle_deg=angle, width_x=float(np.interp(y_x, ys, w[TWIST_OVER])),
                   z_1=float(abs(cz[0][-1])), z_p=float(abs(cz[0][0])))
        self._cache["twist"] = out
        return out

    def twist_bump(self, y: float) -> tuple[float, float]:
        """(the crossing's law at y, its slope): 1 over the plateau, easing to 0 by a cosine over each
        ramp, 0 at the zone's ends (level there too)."""
        lay = self.twist_layout()
        lo_edge, hi_edge = lay["y_x"] - lay["plat_lo"], lay["y_x"] + lay["plat_hi"]
        if lo_edge <= y <= hi_edge:
            return 1.0, 0.0
        if y < lo_edge:
            ramp = max(lay["ramp_lo"], 1e-9)
            u = min((lo_edge - y) / ramp, 1.0)
            return 0.5 * (1.0 + math.cos(math.pi * u)), 0.5 * math.pi * math.sin(math.pi * u) / ramp
        ramp = max(lay["ramp_hi"], 1e-9)
        u = min((y - hi_edge) / ramp, 1.0)
        return 0.5 * (1.0 + math.cos(math.pi * u)), -0.5 * math.pi * math.sin(math.pi * u) / ramp

    def twist_outline(self, k: int, a: float, phase: float = 0.0):
        """Loft k's section at |angle| a inside a crossing zone: the morphing half (_twist_base),
        thinned towards twist_thickness about its inner face and - the over strand - lifted onto the
        under one by the crossing's law (twist_bump), its depth stretched by the slope it climbs at
        (the meridian section of a rising strand is deeper than the strand, as it is wider where the
        strand runs across the ring). The over strand's top still rises steadily to the crossing. Where
        the strands cross, the morph between a half and its mirror image has averaged the comfort
        bore's tilt away: the under strand's inner face lies a little off the finger there (0.16 mm on
        a 4 x 1.6 court band)."""
        import numpy as np
        y = a / self.deg_per_mm
        c, S, dr0 = self._twist_base(k, y, phase)
        b, db = self.twist_bump(y)
        lay = self.twist_layout()
        r_min = float(S[:, 0].min())
        t_full = float(S[:, 0].max()) - r_min
        s_t = 1.0 - (1.0 - min(1.0, self.twist_thickness / t_full)) * b
        lift, dlift = (lay["lift"] * b, lay["lift"] * db) if k == TWIST_OVER else (0.0, 0.0)
        stretch = math.sqrt(1.0 + (dr0 + dlift) ** 2)
        r = c[0] + lift + r_min + (S[:, 0] - r_min) * s_t * stretch
        return np.column_stack([r, c[1] + S[:, 1]])

    def twist_paths(self, k: int):
        """(y, centre z, inner face r) of loft k's strand along a zone, finely sampled (the bend checks)."""
        import numpy as np
        _, _, y_p, y_1 = self.twist_span()
        ys = np.linspace(y_p, y_1, TWIST_SAMPLES)
        z, r = [], []
        for y in ys:
            q = self.twist_outline(k, float(y) * self.deg_per_mm)
            z.append(float(q[:, 1].mean()))
            r.append(float(q[:, 0].min()))
        return ys, np.array(z), np.array(r)

    def twist_bend_radii(self) -> tuple[float, float]:
        """(the strands' tightest bend across the ring, the over strand's tightest bend as it rises
        and falls), mm."""
        import numpy as np

        def min_radius(x, f):
            d1, d2 = np.gradient(f, x), np.gradient(np.gradient(f, x), x)
            kappa = np.abs(d2) / (1.0 + d1 ** 2) ** 1.5
            return float(1.0 / kappa.max()) if kappa.max() > 0 else float("inf")
        flat = []
        rise = float("inf")
        for k in (0, 1):
            ys, z, r = self.twist_paths(k)
            flat.append(min_radius(ys, z))
            if k == TWIST_OVER:
                rise = min_radius(ys, r)
        return min(flat), rise

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

    def engraving_band(self) -> band.BandSpec:
        """The band under an engraving centred opposite the head: the section at the bottom (a taper's
        narrowest and thinnest: its width sizes the letters, its thickness the wall left under them);
        the head's band when the shank is not tapered."""
        return self.section_spec(180.0) if self.tapered else self.band

    def section_spec(self, theta_deg: float) -> band.BandSpec:
        """The band whose section this angle gets: the head's band at the local width and thickness."""
        return replace(self.band, width_mm=round(self.width_at(theta_deg), 6), thickness_mm=round(self.thickness_at(theta_deg), 6))

    def station_angles(self, strand: int = 0):
        """Where a strand's sections sit: every 360/stations degrees, a second strand half a
        step on (its meridians never coincide with the first strand's, so where mirrored strands
        cross, the boolean meets no coincident vertices - seen 2026-10-30)."""
        n = self.loft_stations
        return [360.0 * (k + 0.5 * strand) / n for k in range(n)]

    @property
    def loft_stations(self) -> int:
        """Sections per loft round the ring: `stations`, or a degree apart at least on a twist."""
        return max(self.stations, TWIST_STATIONS) if self.twist else self.stations

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
        if self.twist:                                     # the eye under the head: a full round end into the band
            tp, t1 = self.twist_span()[:2]
            if a < t1:
                r_e = self.split_mm / 2
                e_deg = r_e * self.deg_per_mm
                if a > tp:
                    return r_e
                cos_phi = (tp - a) / e_deg
                return r_e * math.sqrt(max(0.0, 1.0 - cos_phi * cos_phi)) if cos_phi < 1.0 else 0.0
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
        if self.twist and self.twist_zone(theta_deg):                      # the two strands where they cross
            from shapely.geometry import Polygon
            return unary_union([Polygon(self.loft_outline(k, theta_deg)).buffer(0) for k in range(2)])
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
        return geom.open_polygon(sec, self.section_round, chamfer_mm)

    @property
    def section_round(self) -> float:
        """The round on the designed section's fresh edges (a slot's): the notebook's opening
        (edge_round), or on a twist the band's own - its lofts carry the rounds, nTop opens nothing."""
        return self.band.edge_round if self.twist else self.edge_round

    def gate_section(self, theta_deg: float):
        """The section the gate expects nTop to have built at an angle (section_shape with the
        mesher's chamfer); through a trinity shank's knots and pad, the design itself (the 2-D
        section model is the halves' lofts, not the woven strands)."""
        if self.hammer:                                     # the struck face: the design itself
            return gate.section_geometry(self.struck_mesh(), theta_deg)
        if self.woven_section(theta_deg):
            return gate.section_geometry(self.design_mesh(), theta_deg)
        return self.section_shape(theta_deg, chamfer_mm=self.opening_chamfer_mm)

    def section_tolerance(self, theta_deg: float) -> float:
        """How far the built section may stray from gate_section at an angle: the band's rule
        (band.section_shape_tolerance: half the mesh tolerance, a shallow crease's fill), or the
        whole mesh tolerance through a trinity knot, where a pass over another makes a step that
        the mesher fills by a voxel at each of its two round trips (0.056 mm at 0.1 mm, 2026-11-02;
        a pass missing or lifted wrong reads ten times that)."""
        t = band.section_shape_tolerance(self.band.mesh_tolerance_mm)
        if self.hammer:                                     # a ridge between two strikes is a crease the mesher rounds
            return max(t, float(self.band.mesh_tolerance_mm))
        if self.woven_section(theta_deg):
            return max(t, float(self.band.mesh_tolerance_mm))
        return t

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

    @property
    def split_overlap_mm(self) -> float:
        """How far past the centreline each half of a split is lofted where the slot is closed: the
        edge round plus the mesh tolerance, at least SPLIT_OVERLAP_MM. The notebook opens each bar
        on its own, and the opening rounds the edge where a half's cut face meets the ring's surface
        by the edge round, beginning that far back from the cut - so each half's surface must run
        exact past the centreline by more than the round for the round to lie buried in the other
        half. At 0.1 mm with a 0.25 mm round the two quarter-rounds met in a groove 0.055 mm deep
        along the seam all round the bottom (2026-11-02/03, the real split shank, before and after
        the bars were opened apart: r = 9.603 + sqrt(0.25² - 0.15²) = 9.803 vs 9.853 designed, built
        9.798). The mesh tolerance is the margin for the re-distance mesh's voxel."""
        return max(SPLIT_OVERLAP_MM, self.edge_round + float(self.band.mesh_tolerance_mm))

    def loft_outline(self, k: int, theta_deg: float, phase: float = 0.0):
        """(SECTION_POINTS, 2) outline of loft `k` at an angle: a strand's section at its centreline,
        or a split's lower (0) / upper (1) half - the opened 2-D section's part on that side where
        the slot is open (its fillets included); where it is closed, the section cut
        split_overlap_mm past the centreline, so the halves overlap and unite, each half's surface
        drawn inward across the overlap, from nothing at the centreline to SPLIT_INSET_MM at its
        cut (a wedge, by scaling the points there about the section's middle): the ring's surface
        is exact, each half's surface beyond the centreline lies inside the other half, and no two
        faces coincide (coincident faces united in slivers that an STL round trip opened, and two
        exact surfaces over the same strip did the same, 2026-10-30). A twist's loft k is half k from
        its shoulders' crossing zones round the bottom, the other half under the head, and the strand
        between (twist_outline); its outlines all start on the bore below their own centre, so the
        crossing morphs a half into its mirror image point for point."""
        if self.twist:
            a = abs((float(theta_deg) + 180.0) % 360.0 - 180.0)
            tp, t1 = self.twist_span()[:2]
            if self.twist_zone(a):
                return self.twist_outline(k, a, phase)
            return self._split_outline(k if a >= 0.5 * (tp + t1) else 1 - k, theta_deg, phase, centred=True)
        return self._split_outline(k, theta_deg, phase)

    def _split_outline(self, k: int, theta_deg: float, phase: float = 0.0, centred: bool = False):
        """loft_outline's body for a strand or a split's half k; `centred` starts the outline on the
        bore below the half's own centroid instead of below the ring's mid-plane."""
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
            start = (self.band.bore_radius_mm, half.centroid.y if centred else zc)
            return outline_points(half, SECTION_POINTS, start=start, phase=phase)
        b = self.band
        lo, hi = b.bore_radius_mm - 2.0, b.outer_radius_mm + 2.0
        d = self.split_overlap_mm
        half = sec.intersection(box(lo, zc - 10.0, hi, zc + d) if k == 0 else box(lo, zc - d, hi, zc + 10.0))
        if hasattr(half, "geoms"):
            half = max(half.geoms, key=lambda q: q.area)
        start = (self.band.bore_radius_mm, half.centroid.y if centred else zc)
        pts = outline_points(half, SECTION_POINTS, start=start, phase=phase)
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

    def bridge_boxes(self) -> list:
        """A double band's bridges in the bar frame: boxes along Y, one copy per turn the bar
        covers (bridge_spans)."""
        import trimesh
        L = self.wrap_length_mm
        step, ks = self._bar_range()
        y_lo, y_hi = ks[0] * step, ks[-1] * step
        boxes = []
        for a, r_in, r_out, z_lo, z_hi in self.bridge_spans():
            for turn in (-1, 0, 1):
                y = (a / 360.0 + turn) * L
                if y_lo - self.bridge_mm <= y <= y_hi + self.bridge_mm:
                    box = trimesh.creation.box(extents=(r_out - r_in, self.bridge_mm, z_hi - z_lo))
                    box.apply_translation(((r_in + r_out) / 2, y, (z_lo + z_hi) / 2))
                    boxes.append(box)
        return boxes

    def bar_meshes(self) -> list:
        """The unrolled shank for the notebook, as the bars it imports and unites (at most
        BAR_SLOTS; write_bars fills the rest with the smallest bar again): one bar per set of bodies that touch
        nothing else in it, so each bar is a clean mesh on its own and every union is nTop's. A
        plain shank is one bar; a double band's strands one each (a wishbone's meet at the head) and
        its bridges another; a rope's or a plait's strands one each; a split's halves one each
        (unwrap_ring: lofted the whole way round, they overlap along the bottom - a wedge that
        unites cleanly in the ring frame, where the independent model joins them, but whose
        straight seam a bar-frame union made one 28 mm edge of, 2026-10-30); a trinity shank's
        lower half with the strands' first pieces, its upper
        half with their second pieces (trinity_strand_bars: each piece runs a plug into the half
        and the piece that continue it), and the pad on its own - the pieces cross each other and
        the pad's noses, and a mesh union of them left faces micrometres apart that float32 STL and
        nTop's import turned into a self-intersecting bar (2026-11-02). Raw, never geom.clean: it
        merges coplanar facets into mm-long ones, which a vertex-wise wrap turns into chords."""
        import trimesh
        L = self.wrap_length_mm
        if self.rope:
            return [self.rope_tube_bar(k) for k in range(self.rope)]
        if self.knot == "plait":
            return [self.knot_strand_bar(k) for k in range(self.knot_strands)]
        if self.trinity:
            halves = [self.trinity_half_loft(k) for k in range(2)]
            pieces = [self.trinity_strand_bars(side) for side in (1, -1)]     # [+θ shoulder, -θ shoulder], each [first, second]
            return [unwrap_ring(trimesh.util.concatenate([halves[0], pieces[0][0], pieces[1][0]]), L),
                    unwrap_ring(trimesh.util.concatenate([halves[1], pieces[0][1], pieces[1][1]]), L),
                    unwrap_ring(self.pad_ring(), L, full=False)]
        if self.split_mm:
            return [unwrap_ring(self.strand_ring(k), L) for k in range(self.lofts)]
        bars = [self.strand_bar(k) for k in range(self.lofts)]                # a wishbone's strands meet at the head
        boxes = self.bridge_boxes()
        if boxes:
            bars.append(trimesh.util.concatenate(boxes))
        return bars

    @property
    def bar_count(self) -> int:
        """How many bars bar_meshes writes (the rest of the notebook's BAR_SLOTS repeat the smallest)."""
        if self.rope:
            return int(self.rope)
        if self.knot == "plait":
            return int(self.knot_strands)
        if self.trinity:
            return 3
        if self.split_mm:
            return int(self.lofts)
        return int(self.lofts) + (1 if self.bridge_spans() else 0)

    def bar_placeholders(self) -> list[str]:
        """What a dry run shows for the bar inputs: the files write_bars will write (an unused slot
        repeats the smallest bar; the dry run names the first)."""
        names = [f"<{self.stem}.bar.stl>"] + [f"<{self.stem}.bar{k + 1}.stl>" for k in range(1, self.bar_count)]
        return names + [names[0]] * (BAR_SLOTS - len(names))

    def bar_mesh(self):
        """Every bar in one, for the rope's and plait's section model (wrapped_ring) and for tests:
        the bars united in the bar frame. Not for a split's (a trinity's included): its halves'
        straight seam unites into long edges in the bar frame - its bars only ever travel apart,
        and the simulated nTop unites them wrapped (bars_from_inputs)."""
        bars = self.bar_meshes()
        if len(bars) == 1:
            return bars[0]
        if self.split_mm:                                                   # a trinity shank is a split shank too
            raise NotImplementedError("a split shank's bars unite only in the ring frame (bars_from_inputs)")
        return united(bars)

    def strand_ring(self, strand: int = 0):
        """One strand swept round the axis (Z) directly: no bar, no wrap."""
        import numpy as np
        import trimesh
        n, m = len(self.station_angles(strand)), SECTION_POINTS
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
                # faces and micrometre gaps there that float32 STL cannot hold (2026-11-01): tidied within
                # 0.1 µm. This model is measured in memory and never unrolled (the bars come from the parts,
                # bar_meshes): geom.clean merges coplanar facets into mm-long triangles, which a vertex-wise
                # unwrap turned into a self-intersecting bar (2026-11-02)
                body = united(self.trinity_parts(), clean_mm=1e-4)
            else:
                parts = [self.strand_ring(k) for k in range(self.lofts)]
                parts += [self.bridge_sector(*b) for b in self.bridge_spans()]
                body = parts[0] if len(parts) == 1 else united(parts)
            self._cache["design_mesh"] = body
        return self._cache["design_mesh"]

    def design_volume_mm3(self) -> float:
        return float((self.struck_mesh() if self.hammer else self.design_mesh()).volume)

    # ---- a hammered face (texture.Hammer): nTop's spheres at Python's centres, cut after the opening ----
    def hammer_face(self):
        if "hammer_face" not in self._cache:
            from . import texture
            self._cache["hammer_face"] = texture.ShankFace(self)
        return self._cache["hammer_face"]

    def strike_layout(self):
        if "strike_layout" not in self._cache:
            from . import texture
            self._cache["strike_layout"] = texture.strike_layout(self.hammer, self.hammer_face())
        return self._cache["strike_layout"]

    def strikes(self):
        """(face points, normals, depths, sphere centres) of the hammer's strikes, ring frame."""
        from . import texture
        return texture.strike_points(self.hammer, self.hammer_face(), self.strike_layout())

    @property
    def strike_count(self) -> int:
        return len(self.strike_layout()[0]) if self.hammer else 0

    def struck_mesh(self):
        """The design less a sphere of the hammer's radius at every strike (the notebook cuts them after the
        bars are opened and wrapped, so the ridges between strikes stay sharp)."""
        if "struck_mesh" not in self._cache:
            from . import texture
            self._cache["struck_mesh"] = texture.struck(self.design_mesh(), self.strikes()[3], self.hammer.sphere_radius)
        return self._cache["struck_mesh"]

    def write_strikes(self, path) -> Path:
        """The strike centres for Import Points (x,y,z in mm); an unhammered shank gets one far point, cutting nothing."""
        from . import texture
        return texture.write_centres_file(path, self.strikes()[3] if self.hammer else [])

    def strike_inputs(self, strikes_path: str) -> dict:
        """The Strikes inputs (ring_shank.ntop 0.2.0, the solitaires): the centres file, the hammer's radius, mm."""
        return {"Strikes Path": str(strikes_path), "Strike Radius": round(self.hammer.sphere_radius, 6) if self.hammer else 1.0,
                "Strikes Units": "mm"}

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
        if self.trinity or self.twist:
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
        if self.trinity or self.twist or self.hammer:
            import numpy as np
            v = (self.struck_mesh() if self.hammer else self.design_mesh()).vertices
            return float(np.hypot(v[:, 0], v[:, 1]).max())                    # a strand passing over stands proud; the crown struck
        return self.band.outer_radius_mm

    # ---- identity, inputs, checks ------------------------------------------------------------
    def design(self) -> dict:
        woven = self.knot in ("plait", "trinity")
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
                  "knot": self.knot, "knot_strands": self.knot_strands if woven else 0,
                  "knot_repeats": self.knot_repeats if woven else 0,
                  "knot_strand": (self.trinity_ribbon if self.trinity else self.knot_width) if woven else 0.0,
                  "knot_profile": self.knot_profile if woven else "", "knot_fuse": knotwork.KNOT_FUSE_MM if self.knot else 0.0,
                  "knot_width": self.trinity_width if self.trinity else 0.0, "knot_ratio": self.knot_ratio if self.trinity else 0.0,
                  "knot_pad_deg": self.knot_pad_deg if (self.trinity or self.twist) else 0.0,
                  "knot_tail": self.knot_tail_mm if self.trinity else 0.0})
        if self.hammer:                                    # (only when set: earlier designs keep their ids)
            d["hammer"] = self.hammer.design()
        if self.twist:                                     # (new fields enter only when set: earlier designs keep their ids)
            d.update({"twist_length": self.twist_length_mm, "twist_thickness": round(self.twist_thickness, 4),
                      "twist_over": TWIST_OVER, "loft_stations": self.loft_stations})
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
        if self.twist:
            shape += f"_twist{self.twist_length_mm:g}"
        if self.hammer:
            shape += f"_hammered{self.hammer.dimple_mm:g}x{self.hammer.depth_mm:g}"
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

    def notebook_inputs(self, bar_paths, output_path: str = "") -> dict:
        """Values for every input of ring_shank.ntop (names must match the catalog). `bar_paths`:
        the BAR_SLOTS bar files in slot order (write_bars), or one path for every slot (a dry run)."""
        paths = [str(bar_paths)] * BAR_SLOTS if isinstance(bar_paths, (str, Path)) else [str(p) for p in bar_paths]
        if len(paths) != BAR_SLOTS:
            raise ValueError(f"{len(paths)} bar paths, the notebook takes {BAR_SLOTS}")
        return {
            **{slot_name(k): paths[k] for k in range(BAR_SLOTS)},
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
        if self.hammer:
            if self.rope or self.knot:
                return ["a hammered face goes on a profiled shank (plain, tapered, dipped, double, split), not a rope or a knot"]
            p = self._validate_unhammered()
            return p or self._validate_hammer()
        return self._validate_unhammered()

    def _validate_hammer(self) -> list[str]:
        from . import texture
        h = self.hammer
        p = h.problems()
        if p:
            return p
        if self.strike_count == 0:
            return ["no strike fits the face (a narrow band, wide rims or big strikes)"]
        d = self.strike_layout()[2]
        voxel = self.band.mesh_tolerance_mm / 2
        light = float(d.min())
        if light < texture.DEPTH_VOXELS * voxel - 1e-9:
            return [f"the lightest strike ({light:.3f} mm) spans {light / voxel:.1f} voxels at Mesh Tolerance "
                    f"{self.band.mesh_tolerance_mm:g}; at least {texture.DEPTH_VOXELS:g}: --tolerance "
                    f"{math.floor(2 * light / texture.DEPTH_VOXELS * 100) / 100:g} or finer"]
        thin = min(self.thickness_at(t) for t in range(0, 360, 5))
        if thin - float(d.max()) < tables.FLOORS["wall_good"]:
            return [f"the deepest strike leaves {thin - float(d.max()):.2f} mm where the shank is thinnest; at least "
                    f"{tables.FLOORS['wall_good']:g}"]
        est = tables.mesh_triangles_estimate(float(self.struck_mesh().area), self.band.mesh_tolerance_mm)
        if est > texture.MAX_TRIANGLES:
            return [f"meshed at {self.band.mesh_tolerance_mm:g} it would be about {est / 1e6:.1f} M triangles, past the "
                    f"{texture.MAX_TRIANGLES / 1e6:g} M limit: a coarser --tolerance with deeper strikes"]
        return []

    def _validate_unhammered(self) -> list[str]:
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
            p += self._validate_twist() if self.twist else self._validate_trinity()
        if not p and self.lofts == 2:
            m = self.design_mesh()
            if m.body_count != 1:
                p.append(f"the strands and bridges make {m.body_count} bodies, not one ring")
        return p

    def _validate_trinity(self) -> list[str]:
        if self.knot != "trinity":
            return [f"knot {self.knot!r}: plait (a band), trinity or twist (on a split shank)"]
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

    def _validate_twist(self) -> list[str]:
        p = []
        if not self.split_mm:
            p.append("a twist crosses a split shank's two halves: --split")
        if self.dip_mm or self.strands > 1 or self.rope:
            p.append("a twist takes no dip, double or rope")
        floor = tables.FLOORS["wall_good"]
        t_x = self.twist_thickness
        if t_x < floor:
            p.append(f"the strands where they cross ({t_x:.2f} mm thick): at least {floor:g} mm")
        if t_x > self.band.thickness_mm + 1e-9:
            p.append(f"the strands where they cross ({t_x:.2f} mm thick): at most the band's {self.band.thickness_mm:g} mm")
        if not 5.0 <= self.knot_pad_deg <= 80.0:
            p.append(f"pad {self.knot_pad_deg:g}°: 5..80° either side of the head")
        if not 3.0 <= self.twist_length_mm <= 20.0:
            p.append(f"twist length {self.twist_length_mm:g} mm: 3..20")
        if p:
            return p
        tp, t1 = self.twist_span()[:2]
        end_deg = (SLOT_END_MM / 2) * self.deg_per_mm
        if t1 + 3.0 > self.split_span_deg - end_deg:
            p.append(f"the twist runs to {t1:.1f}° from the head, where the slot has closed (span {self.split_span_deg:g}°): "
                     f"a longer split span, a shorter twist or a smaller pad")
        if self.tapered and self.taper_from_deg < t1 + 2.0:
            p.append(f"the taper starts {self.taper_from_deg:g}° from the head, inside the twist (to {t1:.1f}°): --taper-from "
                     f"at least {math.ceil(t1 + 2.0):g}")
        if p:
            return p
        try:
            lay = self.twist_layout()
        except ValueError as e:
            return [str(e)]
        for side, ramp in (("head", lay["ramp_lo"]), ("halves", lay["ramp_hi"])):
            if ramp < TWIST_RAMP_MIN_MM:
                p.append(f"the strands overlap for {lay['plat_lo'] + lay['plat_hi']:.2f} mm about the crossing, leaving the over strand "
                         f"{max(ramp, 0):.2f} mm to come back down on the {side} side (needs {TWIST_RAMP_MIN_MM:g}): a longer twist "
                         f"(--twist-length) or a wider split (narrower strands overlap for less)")
                break
        if not p:
            flat, rise = self.twist_bend_radii()
            if flat < lay["width_x"] / 2 + 0.1:
                p.append(f"the strands bend to a {flat:.2f} mm radius across the ring, tighter than their {lay['width_x']:.2f} mm "
                         f"width turns: a longer twist")
            if rise < t_x / 2 + 0.1:
                p.append(f"the over strand rises on a {rise:.2f} mm radius, tighter than its {t_x:.2f} mm thickness turns "
                         f"(needs {t_x / 2 + 0.1:.2f}): a longer twist or thinner strands where they cross")
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
        w = self._warnings()
        if self.hammer and not self.validate():
            w += self.hammer_gaps()
        return w

    def hammer_gaps(self) -> list[str]:
        """Where the face is too narrow for a strike (a split's halves, a taper's bottom): the angles, and what fits."""
        h, f = self.hammer, self.hammer_face()
        need = 2 * (h.rim(self.band.edge_round) + h.floor_half)
        bare = [t for t in range(0, 360) if (not h.clear_deg or min(t, 360 - t) > h.clear_deg)
                and all(b - a < need for a, b in f.intervals(float(t)))]
        if not bare:
            return []
        widest = max((b - a) for t in bare for a, b in f.intervals(float(t)))
        runs, start = [], bare[0]
        for a, b in zip(bare, bare[1:] + [None]):
            if b != a + 1:
                runs.append((start, a))
                start = b
        span = ", ".join(f"{lo}°..{hi}°" if hi > lo else f"{lo}°" for lo, hi in runs[:4]) + (" ..." if len(runs) > 4 else "")
        return [f"no strike where the face is narrower than {need:.2f} mm (two {h.rim(self.band.edge_round):.2f} mm rims and a lightest "
                f"strike's footprint): {len(bare)}° of the ring ({span}) stays polished - the widest there is {widest:.2f} mm; "
                f"smaller strikes (--dimple) or narrower rims (--rim) reach it"]

    def _warnings(self) -> list[str]:
        if self.rope:
            return []
        if self.twist:
            w = list(self.band.warnings())
            if not self.validate():
                ang = self.twist_layout()["angle_deg"]
                if ang < knotwork.KNOT_ANGLE_MIN_DEG:
                    w.append(f"the strands cross at {ang:.0f}°: a shallow crossing fuses them over a long run (a shorter twist)")
            return w
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
        if self.knot and not self.twist:
            return min(tables.FLOORS["wall_marginal"], 0.8 * self.knot_thickness)
        thin = min(self.section_spec(t).edge_thickness_mm for t in (0.0, 180.0))
        if self.twist:
            return min(tables.FLOORS["wall_marginal"], 0.8 * min(thin, self.twist_thickness))
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
            where = "where the halves leave the twist" if self.twist else "at the head"
            line += f"\n  split: a {self.split_shape} slot {self.split_mm:g} mm wide {where}, closing by ±{self.split_span_deg:g}°"
        if self.trinity:
            lay = self.trinity_layout()
            lace = self.trinity_laces()[0]
            line += (f"\n  trinity knots on the shoulders: trefoil R {lay['R']:.2f} (ratio {self.knot_ratio:g}) centred {lay['y_c'] * self.deg_per_mm:.1f}° from the head, "
                     f"{len(lace.crossings)} self-crossings at {lace.crossings[0].angle_deg:.0f}°; ribbon {self.trinity_ribbon:g} wide x "
                     f"{self.trinity_thickness:.2f} thick, lifting {self.trinity_thickness - knotwork.KNOT_FUSE_MM:.2f} mm to pass over itself; "
                     f"lobes {self.trinity_width:g} mm across either side of the band's nose under the head (to ±{self.knot_pad_deg:g}°); "
                     f"tails to {lay['theta_1']:.1f}°")
        if self.twist:
            lay = self.twist_layout()
            line += (f"\n  twist: the halves cross on each shoulder between ±{lay['theta_p']:g}° (the band under the head) and "
                     f"±{lay['theta_1']:.1f}° ({self.twist_length_mm:g} mm), at {lay['theta_x']:.1f}° and {lay['angle_deg']:.0f}° to each other; "
                     f"the {'upper' if TWIST_OVER else 'lower'} half passes over, both thinned to {self.twist_thickness:.2f} mm there, "
                     f"lifted {lay['lift']:.2f} mm over {lay['plat_lo'] + lay['plat_hi']:.2f} mm; an eye {self.split_mm:g} mm wide either "
                     f"side of each crossing")
        if self.hammer:
            h, d = self.hammer, self.strike_layout()[2]
            line += (f"\n  hammered: {self.strike_count} strikes of a {h.sphere_radius:.2f} mm hammer face, "
                     + (f"{d.min():.3f}..{d.max():.3f} mm deep" if len(d) else "none fits")
                     + f", centres {h.spacing * h.dimple_mm:.2f} mm apart at least, rims {h.rim(self.band.edge_round):.2f}"
                     + (f", none within ±{h.clear_deg:g}° of the head" if h.clear_deg else "") + f"; seed {h.seed}")
        line += (f"\n  {self.loft_stations} stations x {SECTION_POINTS} points; wrap length {self.wrap_length_mm:.3f} mm; "
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


def unwrap_ring(ring, wrap_length: float, full: bool = True):
    """A ring-frame mesh unrolled into a bar (the inverse of wrap_bar: X = r, Y = angle x L / 2π,
    Z = z) running from -3L/4 to 5L/4, so it covers the turn and a half plus margins a bar needs.
    The mesh is cut into two halves by the plane through the axis (turned a little first, so the
    cut runs between stations), each half unrolled, and the halves with their shifted copies
    welded at the cuts vertex to twin - no boolean: a union of overlapping lofts in the bar frame,
    where the facets are coplanar, came out in slivers (2026-10-30). `full`: the mesh runs the whole
    way round, so the bar reaches both ends; off for a body that does not (a knot's pad, a
    strand's piece), which appears once per turn the bar covers - at its angle, and a turn on."""
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
        if len(piece.faces) == 0:
            continue
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
    if full:
        assert abs(bar.bounds[0][1] - y_lo) < 1e-6 and abs(bar.bounds[1][1] - y_hi) < 1e-6
    else:
        assert y_lo - 1e-6 <= bar.bounds[0][1] and bar.bounds[1][1] <= y_hi + 1e-6
    return bar


def plug_rings(rings, length: float = PLUG_MM, inset: float = PLUG_INSET):
    """An open sweep's vertex rings ((n, m, 3), knotwork.sweep_rings) with a plug ring beyond each
    end: the end ring drawn in about its mean by `inset` and moved `length` on along the end's
    direction, so the sweep runs that far into whatever continues it and a union sees an overlap,
    not a shared face. The plug's straight run leaves a curved continuation by at most
    length² / (2 x bend radius), well inside the inset."""
    import numpy as np
    R = np.asarray(rings, float)
    out = [R]
    for which in ("start", "end"):
        ring, nxt = (R[0], R[1]) if which == "start" else (R[-1], R[-2])
        c = ring.mean(axis=0)
        t = c - nxt.mean(axis=0)
        t = t / np.linalg.norm(t)
        plug = (c + (ring - c) * (1.0 - inset) + t * length)[None]
        out = [plug] + out if which == "start" else out + [plug]
    return np.concatenate(out)


def bars_from_inputs(v: dict):
    """The shank a notebook's bar inputs describe, the way the simulated nTop builds it: every bar
    at Shank Path .. Shank Path 4 wrapped vertex-wise (wrap_bar) and the wrapped bars united in the
    ring frame (a bar-frame union of a split's halves made one long edge of their straight seam,
    2026-10-30; nTop unites implicits, where the frame does not matter). A slot pointing at a file
    already taken is read once."""
    import trimesh
    L = float(v["Wrap Length"])
    seen, wrapped = set(), []
    for name in SLOT_NAMES:
        path = str(v.get(name, "") or "")
        if not path or path in seen:
            continue
        seen.add(path)
        wrapped.append(wrap_bar(trimesh.load(path, force="mesh"), L))
    return wrapped[0] if len(wrapped) == 1 else united(wrapped)


def write_bars(spec: ShankSpec, directory: Path, stem: str) -> list[str]:
    """The notebook's BAR_SLOTS bar files for `spec` in `directory`: `<stem>.bar.stl`,
    `<stem>.bar2.stl` ... (bar_meshes), the unused slots all pointing at the smallest of them
    again - a body united with itself is itself, and it survives the notebook's per-bar opening
    (a speck inside the first bar did not: eroded by the edge round it was empty, nTop's Mesh
    block failed on it and nothing downstream built, 2026-11-02). Returns the BAR_SLOTS paths in
    slot order."""
    directory = Path(directory)
    bars = spec.bar_meshes()
    if len(bars) > BAR_SLOTS:
        raise ValueError(f"{len(bars)} bars, the notebook takes {BAR_SLOTS}")
    assert len(bars) == spec.bar_count, (len(bars), spec.bar_count)
    paths = []
    for k, bar in enumerate(bars):
        path = directory / (f"{stem}.bar.stl" if k == 0 else f"{stem}.bar{k + 1}.stl")
        bar.export(str(path))
        paths.append(str(path))
    if len(bars) < BAR_SLOTS:
        smallest = paths[min(range(len(bars)), key=lambda k: len(bars[k].faces))]
        paths += [smallest] * (BAR_SLOTS - len(bars))
    return paths


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
    remap = np.arange(len(mesh.vertices))
    if len(i0) and len(i1):                                                # a bar with no material at the seam has no twins
        _, twin = cKDTree(mesh.vertices[i0]).query(mesh.vertices[i1])
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
                     section_design=spec.gate_section, section_tol_mm=spec.section_tolerance)
    c = band.design_volume_check(spec.expected_volume_mm3(), ntop_vol, 2.0)
    rounded, overcut = spec.sharp_edge_round_mm3(), spec.opening_overcut_mm3()
    if (rounded or overcut) and c.status != gate.INCOMPLETE:
        c.detail += (f" [design {spec.design_volume_mm3():.2f}" + (f" less {rounded:.2f} mm³ of edge rounding" if rounded else "")
                     + (f" less {overcut:.2f} mm³ the mesher's chamfer takes off the rounds" if overcut else "") + "]")
    rep.checks.append(c)
    if spec.hammer:
        from . import texture
        P, N, _, _ = spec.strikes()
        rep.checks.append(texture.strikes_check(P, N, spec.struck_mesh(), gate.load_mesh(stl), spec.band.mesh_tolerance_mm))
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
    built_notes = runs.require_built(cat, nb) if not notebook else []   # a notebook older than the catalog needs: refused
    out_dir = Path(out_dir) if out_dir else config.out_dir() / "shank"
    stem = spec.stem
    run_dir, run_id = runs.fresh_run_dir(out_dir, stem)
    stl = run_dir / f"{stem}.stl"
    bars = write_bars(spec, run_dir, stem)
    strikes = spec.write_strikes(run_dir / f"{stem}.strikes.csv")      # the hammer's centres, or one far point
    values = {**spec.notebook_inputs(bars, str(stl)), **spec.strike_inputs(str(strikes))}
    inputs = cat.build_inputs(values)
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
    result.notes += spec.warnings() + built_notes
    report = {
        "stem": stem, "spec_id": spec.spec_id, "run_id": run_id, "status": result.status, "ok": result.ok,
        "band": asdict(spec.band), "shank": {k: v for k, v in asdict(spec).items() if k not in ("band", "_cache")},
        "design": spec.design(), "inputs": values, "stl": str(stl), "bar": bars[0], "bars": bars, "strikes": spec.strike_count,
        "ntop_volume_mm3": ntop_vol, "design_volume_mm3": spec.design_volume_mm3(),
        "expected_volume_mm3": spec.expected_volume_mm3(), "opening_overcut_mm3": spec.opening_overcut_mm3(), "gate": rep.to_dict(),
        "ntopcl_seconds": run.seconds, "block_timings": [t.__dict__ for t in run.log.timings], "notes": result.notes,
        "notebook": runs.notebook_identity(nb), "environment": runs.environment(ntopcl.version()),
    }
    (run_dir / f"{stem}.report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    if deliver and result.ok:
        result.delivered = runs.deliver(stl, run_dir, stem, deliver_project, report, extra_files=sorted(set(map(Path, bars))),
                                        cast_metal=cast_metal)
    elif deliver:
        result.notes.append(f"not delivered: status {result.status}")
    return result
