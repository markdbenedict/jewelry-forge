"""Celtic knotwork (Phase 3 step 1e): strands interlaced over the ring.

Reference ring 01 weaves the two strands of its split shank into a trinity knot on each shoulder;
Celtic bands weave two, three or four strands the whole way round. Every knot here is one
construction:

  1. Strand centrelines drawn in the ring's developed surface - the bar frame's (Y along the
     ring, Z axial) plane: a `Strand` is a polyline over one turn, periodic in Y (closed round the
     ring) or open (its ends run into other metal).
  2. Their crossings (`crossings`) and the interlace (`interlace`): at every crossing one strand
     passes over and the other under, and along every strand the crossings alternate - the rule
     every Celtic knot obeys. Which way each strand's first crossing goes is solved for so that
     every crossing has one strand over and one under; a diagram with no such solution is not
     knotwork and is refused.
  3. The radial law (`Interlace.depth`), two forms. `mid` (a plait band): a strand's centre sits
     at mid-depth between crossings and rises or sinks by h at each one, a cosine from crossing to
     crossing (zero slope at both). `bore` (a motif on a shank): a strand lies on the finger and
     lifts by 2h only to pass over another, a plateau as long as the two ribbons overlap in plan
     with a cosine ramp either side, back on the bore at every crossing it passes under. Either
     way the over strand's inner face lies KNOT_FUSE_MM inside the under strand's outer face where
     they cross: they fuse into one casting there, and from outside the ring reads as woven.
  4. A section swept along each centreline (`sweep_along`): a ribbon (a rounded rectangle, its
     width across the surface, its thickness radial) or a round wire; in the bar frame for nTop
     (Remap Cylindrical wraps the bar) and in the ring frame for the independent model - both in
     `shank.ShankSpec`.

Patterns:
  plait   - n strands weaving the whole way round (`plait_strands`): strand k is the sinusoid
            z = A sin(R 2π y / L + 2π k / n), amplitude A = (W - w) / 2 so the ribbons reach the
            band's edges, R repeats of the weave per turn. Two strands make the simple twist, three
            the classic plait, four a wide one.
  trinity - the triquetra on a split shank's shoulder (`trefoil_motif`, reference ring 01): the
            trefoil curve φ = 2t, ρ = R (1 + c cos 3t) - three lobes, three crossings at radius R,
            alternating - with the lobe that points down the shank opened and its two ends led out
            as the split's halves (cubic tails), the other two lobes flanking the band under the
            head, whose nose enters the knot's head-side crossing. One open strand with three
            self-crossings (shank.ShankSpec.trinity_*).

Meshing a woven strand (what 2026-11-01 taught): a sweep that passes over itself is no
manifold, so it is swept in pieces that each hold one pass of every crossing (`sweep_rings`,
`mesh_from_rings`); pieces, and the lofts a strand continues, meet in one identical face - the
same ring of vertices and the same cap triangles (`cap_triangles`) - because overlaps drawn a
hair apart leave needle faces that float32 STL cannot hold; and no station of one body may lie in
another's cap plane.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

KNOT_FUSE_MM = 0.1             # an over strand's inner face lies this far inside the under strand's outer face at a crossing
KNOT_GAP_MIN_MM = 0.3          # between crossings two strands open to at least this clear gap (a pierced weave, not a slab)
KNOT_ANGLE_MIN_DEG = 12.0      # a crossing shallower than this fuses the strands over a long run (a warning)
KNOT_POINTS_PER_REPEAT = 72    # centreline samples per weave repeat per strand (the sinusoid's chord error < 0.005 mm)
PROFILE_STEP_MM = 0.3          # a ribbon's flats are subdivided this finely (vertex-wise, a wrapped flat is a chord)
CORNER_SEGMENTS = 8            # segments on a ribbon's rounded corner (a 0.25 mm quarter round: 0.002 mm chord sag)
WIRE_POINTS = 48               # points round a round wire's section
RAMP_MM = 1.0                  # the bore law: an over strand comes back down to the finger over this run past its plateau
TREFOIL_RATIO = 0.5            # the trefoil's radial swing c (ρ = R (1 + c cos 3t)): crossings at 2 atan(1.5 c) = 74°
TREFOIL_POINTS = 240           # samples round the trefoil's open run
TAIL_POINTS = 40               # samples along each tail (a cubic from the knot to the half it continues)


@dataclass
class Strand:
    """A centreline in the developed surface: (m, 2) points (y, z), y along the ring. Closed: the
    points cover one turn and the last point's successor is the first, `period` further along y -
    or, with `period` 0, a loop that closes on itself in place (a knot ornament standing on a band:
    ornament.KnotOrnament). Open: a polyline whose ends run into other metal."""
    points: "numpy.ndarray"
    period: float = 0.0
    closed: bool = True

    def __post_init__(self):
        import numpy as np
        self.points = np.asarray(self.points, float)
        if self.closed and self.period < 0:
            raise ValueError("a closed strand's period is the length it repeats with (0: a loop closing in place)")

    @property
    def loop(self):
        """The polyline with its closing segment (the first point a period on) for a closed strand."""
        import numpy as np
        if not self.closed:
            return self.points
        return np.vstack([self.points, self.points[:1] + [self.period, 0.0]])

    @property
    def params(self):
        """Arc length along the polyline at each point, (m,)."""
        import numpy as np
        seg = np.linalg.norm(np.diff(self.points, axis=0), axis=1)
        return np.concatenate([[0.0], np.cumsum(seg)])

    @property
    def length(self) -> float:
        """The strand's whole length: round the loop (closed) or end to end."""
        import numpy as np
        return float(np.linalg.norm(np.diff(self.loop, axis=0), axis=1).sum())


@dataclass
class Crossing:
    i: int          # the two strands (i < j)
    j: int
    s_i: float      # arc length along each where they cross
    s_j: float
    y: float        # where, in the developed surface
    z: float
    angle_deg: float = 90.0     # the angle the two centrelines cross at (0 < angle <= 90)

    @property
    def self_crossing(self) -> bool:
        return self.i == self.j


def crossings(strands: list[Strand]) -> list[Crossing]:
    """Every point where two strands cross, each once (a closed strand's crossings are those within
    its own turn; the others are met shifted a period either way), and every point where a strand
    crosses itself (`self_crossings`)."""
    from shapely.affinity import translate
    from shapely.geometry import LineString, Point
    import numpy as np
    lines = [LineString(s.loop) for s in strands]

    def detect(k: int):
        """The polyline crossings are searched on: a closed strand's loop with one segment more at
        each end (a crossing that falls on its first vertex - a plait's at y = 0 - is then met
        inside a segment, not grazed at an endpoint and lost to rounding)."""
        s = strands[k]
        if not s.closed:
            return lines[k]
        p = s.points
        return LineString(np.vstack([p[-1:] - [s.period, 0.0], p, p[:2] + [s.period, 0.0]]))

    out = []
    for i, a in enumerate(strands):
        for j in range(i + 1, len(strands)):
            b = strands[j]
            # the strand whose copies are shifted a period either way: b when it is closed, else a
            moving = j if b.closed else (i if a.closed else None)
            shifts = [-strands[moving].period, 0.0, strands[moving].period] if moving is not None else [0.0]
            found = {}
            for shift in shifts:
                la = translate(detect(i), shift, 0.0) if moving == i else detect(i)
                lb = translate(detect(j), shift, 0.0) if moving == j else detect(j)
                for p in _points(la.intersection(lb)):
                    if moving == j and a.closed:                                   # once per turn of strand i
                        y0 = float(a.points[0, 0])
                        if not (y0 - 1e-9 <= p.x < y0 + a.period - 1e-9):
                            continue
                    key = (round(p.x, 6), round(p.y, 6))                           # the extensions overlap: once each
                    if key in found:
                        continue
                    pa = Point(p.x - shift, p.y) if moving == i else p
                    pb = Point(p.x - shift, p.y) if moving == j else p
                    s_i, s_j = float(lines[i].project(pa)), float(lines[j].project(pb))
                    s_i, s_j = s_i % a.length if a.closed else s_i, s_j % b.length if b.closed else s_j
                    found[key] = Crossing(i, j, s_i, s_j, float(p.x), float(p.y),
                                          _angle_between(tangent_at(a, s_i), tangent_at(b, s_j)))
            out += list(found.values())
    for k, st in enumerate(strands):
        out += self_crossings(k, st)
    return out


def tangent_at(strand: Strand, s: float):
    """The unit tangent of a strand's polyline at arc length s."""
    import numpy as np
    pts = strand.loop
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    k = int(np.clip(np.searchsorted(cum, s, side="right") - 1, 0, len(seg) - 1))
    d = pts[k + 1] - pts[k]
    return d / max(np.linalg.norm(d), 1e-12)


def _angle_between(u, v) -> float:
    import numpy as np
    c = abs(float(np.dot(u, v)))
    return math.degrees(math.acos(min(1.0, c)))


def self_crossings(k: int, strand: Strand) -> list[Crossing]:
    """Where a strand crosses itself (a trefoil: three times): every pair of non-adjacent segments
    tested, the two passes' arc lengths kept apart (s_i the earlier)."""
    import numpy as np
    P = strand.loop
    n = len(P) - 1
    if n < 3:
        return []
    A, B = P[:-1], P[1:]
    seg = np.linalg.norm(B - A, axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    out = []
    d1 = B - A
    for a in range(n - 2):
        bs = np.arange(a + 2, n)
        if strand.closed and a == 0:
            bs = bs[bs != n - 1]                                            # the loop's first and last segments touch
        if len(bs) == 0:
            continue
        p, r = A[a], d1[a]
        q, s2 = A[bs], d1[bs]
        denom = r[0] * s2[:, 1] - r[1] * s2[:, 0]
        ok = np.abs(denom) > 1e-12
        qp = q - p
        t = np.where(ok, (qp[:, 0] * s2[:, 1] - qp[:, 1] * s2[:, 0]) / np.where(ok, denom, 1.0), -1.0)
        u = np.where(ok, (qp[:, 0] * r[1] - qp[:, 1] * r[0]) / np.where(ok, denom, 1.0), -1.0)
        hit = ok & (t >= 0.0) & (t < 1.0) & (u >= 0.0) & (u < 1.0)
        for b_idx, tt, uu in zip(bs[hit], t[hit], u[hit]):
            pt = p + tt * r
            s_a, s_b = float(cum[a] + tt * seg[a]), float(cum[b_idx] + uu * seg[b_idx])
            ang = _angle_between(r / seg[a], d1[b_idx] / seg[b_idx])
            out.append(Crossing(k, k, s_a % strand.length if strand.closed else s_a,
                                s_b % strand.length if strand.closed else s_b, float(pt[0]), float(pt[1]), ang))
    return out


def _points(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type == "Point":
        return [geometry]
    if hasattr(geometry, "geoms"):
        pts = []
        for g in geometry.geoms:
            pts += _points(g)
        return pts
    return [geometry.representative_point()]           # an overlap (strands lying along each other): one touch


@dataclass
class Interlace:
    """The solved weave: for every strand its crossings in order (arc length) and whether it passes
    over at each; `problems` names what stopped the diagram from alternating (then it is unusable)."""
    strands: list[Strand]
    crossings: list[Crossing]
    params: list = field(default_factory=list)       # per strand: sorted arc lengths of its crossings
    over: list = field(default_factory=list)         # per strand: True where it passes over, same order
    entries: list = field(default_factory=list)      # per strand: the index into `crossings` of each entry, same order
    problems: list = field(default_factory=list)

    def count(self, k: int) -> int:
        return len(self.params[k])

    def depth(self, k: int, s, law: str = "mid", widths=None, ramp_mm: float = RAMP_MM):
        """The radial law along strand k at arc lengths `s`, in [-1, 1] (x = mid radius + rise x depth).
        `mid`: +1 at a crossing it passes over, -1 at one it passes under, a cosine between
        consecutive crossings (so 0 midway, zero slope at each); an open strand's ends lie at 0.
        `bore`: -1 (on the finger) everywhere but round the crossings it passes over, where it
        lifts to +1 over a plateau as long as the two ribbons overlap in plan (`widths`, per
        strand, decide that with the crossing angle) and comes down again over `ramp_mm` either
        side with a cosine; a crossing it passes under inside such a bump is a problem the caller
        checks (`bump_reach`)."""
        import numpy as np
        s = np.asarray(s, float)
        st = self.strands[k]
        cs, ov = np.asarray(self.params[k], float), np.asarray(self.over[k], bool)
        if len(cs) == 0:
            return np.zeros_like(s) if law == "mid" else np.full_like(s, -1.0)
        if law == "bore":
            u = np.full_like(s, -1.0)
            S = st.length
            for a in np.nonzero(ov)[0]:
                lo, hi = self.bump_reach(k, a, widths, ramp_mm)
                d = np.abs(s - cs[a])
                if st.closed:
                    d = np.minimum(d, S - d)
                plateau, ramp = lo, hi - lo
                bump = np.where(d <= plateau, 1.0, np.where(d >= hi, -1.0, np.cos(np.pi * (d - plateau) / ramp)))
                u = np.maximum(u, bump)
            return u
        vs = np.where(ov, 1.0, -1.0)
        if st.closed:
            S = st.length
            ext_s = np.concatenate([[cs[-1] - S], cs, [cs[0] + S]])
            ext_v = np.concatenate([[vs[-1]], vs, [vs[0]]])
            idx = np.clip(np.searchsorted(ext_s, s, side="right") - 1, 0, len(ext_s) - 2)
            s0, s1, v0 = ext_s[idx], ext_s[idx + 1], ext_v[idx]
            return v0 * np.cos(np.pi * (s - s0) / (s1 - s0))
        S = st.length
        ext_s = np.concatenate([[0.0], cs, [S]])
        ext_v = np.concatenate([[0.0], vs, [0.0]])
        idx = np.clip(np.searchsorted(ext_s, s, side="right") - 1, 0, len(ext_s) - 2)
        s0, s1, v0, v1 = ext_s[idx], ext_s[idx + 1], ext_v[idx], ext_v[idx + 1]
        tau = np.clip((s - s0) / np.where(s1 > s0, s1 - s0, 1.0), 0.0, 1.0)
        return v0 + (v1 - v0) * 0.5 * (1.0 - np.cos(np.pi * tau))       # a smooth step from one value to the next

    def crossing_of(self, k: int, a: int) -> Crossing:
        """The crossing behind strand k's a-th entry."""
        return self.crossings[self.entries[k][a]]

    def bump_reach(self, k: int, a: int, widths=None, ramp_mm: float = RAMP_MM) -> tuple[float, float]:
        """(plateau half-length, total half-length) of the lift strand k makes at its a-th crossing
        under the bore law: the plateau covers the plan overlap of the two ribbons (the other's
        width across the crossing angle plus this one's half-width along it), the ramp follows."""
        c = self.crossing_of(k, a)
        other = c.j if (c.i == k and not c.self_crossing) else c.i
        w_self = widths[k] if widths is not None else 0.0
        w_other = widths[other] if widths is not None else 0.0
        ang = math.radians(max(min(c.angle_deg, 90.0), 5.0))
        plateau = (w_other / 2) / math.sin(ang) + (w_self / 2) / math.tan(ang)
        return plateau, plateau + ramp_mm

    def bore_law_problems(self, widths=None, ramp_mm: float = RAMP_MM) -> list[str]:
        """Under the bore law a strand must be back on the finger at every crossing it passes
        under: an under crossing inside an over crossing's bump is reported."""
        out = []
        for k, st in enumerate(self.strands):
            cs = self.params[k]
            S = st.length
            for a, over in enumerate(self.over[k]):
                if not over:
                    continue
                _, reach = self.bump_reach(k, a, widths, ramp_mm)
                for b, over_b in enumerate(self.over[k]):
                    if over_b:
                        continue
                    d = abs(cs[b] - cs[a])
                    if st.closed:
                        d = min(d, S - d)
                    if d < reach:
                        out.append(f"strand {k} passes under {d:.2f} mm from where it passes over: it cannot get back "
                                   f"down in time (needs {reach:.2f} mm; a wider knot or a narrower ribbon)")
                        break
        return out


def interlace(strands: list[Strand], xs: list[Crossing] | None = None) -> Interlace:
    """Solve the weave: order each strand's crossings, then choose for every strand whether its
    first crossing goes over or under so that at every crossing exactly one strand is over
    (over/under alternating along each strand). A closed strand with an odd number of crossings,
    or a set of strands whose orders conflict, cannot alternate: reported in `problems`."""
    if xs is None:
        xs = crossings(strands)
    per: list[list[tuple[float, int, int]]] = [[] for _ in strands]          # (arc length, crossing, end)
    for c_idx, c in enumerate(xs):
        per[c.i].append((c.s_i, c_idx, 0))
        per[c.j].append((c.s_j, c_idx, 1))
    index = {}
    params, entries = [], []
    for k, lst in enumerate(per):
        lst.sort()
        params.append([s for s, _, _ in lst])
        entries.append([c_idx for _, c_idx, _ in lst])
        for a, (_, c_idx, end) in enumerate(lst):
            index[(c_idx, end)] = a
    lace = Interlace(strands, xs, params, [], entries, [])
    for k, st in enumerate(strands):
        if st.closed and len(per[k]) % 2:
            lace.problems.append(f"strand {k} crosses {len(per[k])} times round the ring: an odd count cannot alternate")
    # p_i xor a xor p_j xor b = 1  ->  p_i xor p_j = 1 xor a xor b : two-colour the strands
    parity = [None] * len(strands)
    edges: dict[int, list[tuple[int, int]]] = {k: [] for k in range(len(strands))}
    for c_idx, c in enumerate(xs):
        want = 1 ^ (index[(c_idx, 0)] & 1) ^ (index[(c_idx, 1)] & 1)
        if c.self_crossing:
            if want:                                                        # the two passes must differ in parity
                lace.problems.append(f"strand {c.i} crosses itself at ({c.y:.2f}, {c.z:.2f}) with the same side up both ways")
            continue
        edges[c.i].append((c.j, want))
        edges[c.j].append((c.i, want))
    for start in range(len(strands)):
        if parity[start] is not None:
            continue
        parity[start] = 0
        queue = [start]
        while queue:
            k = queue.pop()
            for other, want in edges[k]:
                need = parity[k] ^ want
                if parity[other] is None:
                    parity[other] = need
                    queue.append(other)
                elif parity[other] != need and not any(p.startswith("the diagram") for p in lace.problems):
                    lace.problems.append(f"the diagram does not alternate: strands {k} and {other} meet with the same side up")
    lace.over = [[((parity[k] + a) % 2 == 0) for a in range(len(params[k]))] for k in range(len(strands))]
    return lace


# ---- patterns ------------------------------------------------------------------------------------
def plait_strands(n: int, repeats: int, amplitude: float, period: float, points: int) -> list[Strand]:
    """n strands weaving the whole way round: strand k is z = A sin(R 2π y / L + 2π k / n), sampled
    at `points` per turn, each strand's samples k/n of a step on from the first's (strands sampled
    on the same meridians left coincident vertices in the booleans - the rope's lesson)."""
    import numpy as np
    out = []
    for k in range(n):
        y = (np.arange(points) + k / n) * period / points
        z = amplitude * np.sin(2 * math.pi * repeats * y / period + 2 * math.pi * k / n)
        out.append(Strand(np.column_stack([y, z]), period, True))
    return out


def plait_crossing_angle_deg(amplitude: float, repeats: int, period: float) -> float:
    """The angle two plait strands cross at, at its shallowest (both strands at their steepest,
    equal and opposite slopes: a two-strand plait's every crossing)."""
    slope = amplitude * 2 * math.pi * repeats / period
    return 2 * math.degrees(math.atan(slope))


def pair_openings(strands: list[Strand], samples: int = 720) -> dict[tuple[int, int], float]:
    """For each pair of closed strands that are graphs over y, the widest their centrelines part
    along the turn (max |z_i - z_j| at the same y): a weave whose pairs never part wider than a
    strand is a slab."""
    import numpy as np
    out = {}
    for i, a in enumerate(strands):
        for j in range(i + 1, len(strands)):
            b = strands[j]
            if not (a.closed and b.closed):
                continue
            y = np.linspace(0.0, a.period, samples, endpoint=False)
            za = np.interp(y, a.loop[:, 0], a.loop[:, 1], period=a.period)
            zb = np.interp(y, b.loop[:, 0], b.loop[:, 1], period=b.period)
            out[(i, j)] = float(np.abs(za - zb).max())
    return out


def trefoil_motif(centre: tuple[float, float], radius: float, tail_ends: tuple[tuple[float, float], tuple[float, float]],
                  towards_tail: float = 1.0, ratio: float = TREFOIL_RATIO) -> Strand:
    """The triquetra opened for a split shank's two halves: the trefoil φ = 2t, ρ = R (1 + c cos 3t)
    about `centre` (y, z), its lobe pointing along `towards_tail` (+1: +y, -1: -y) left out
    (t from 30° to 330°, crossing to crossing), and a cubic tail from each of those two crossings
    to the matching tail end (upper first), arriving along the ring. One open strand, traversed
    from the upper tail through the knot to the lower tail; its three self-crossings lie at
    radius R, 2 atan(1.5 c) apart in angle."""
    import numpy as np
    cy, cz = centre
    R, c = float(radius), float(ratio)
    sgn = 1.0 if towards_tail >= 0 else -1.0

    def point(t):
        phi, rho = 2 * t, R * (1 + c * math.cos(3 * t))
        return np.array([cy + sgn * rho * math.cos(phi), cz + rho * math.sin(phi)])

    def velocity(t):
        phi, rho = 2 * t, R * (1 + c * math.cos(3 * t))
        drho = -3 * R * c * math.sin(3 * t)
        return np.array([sgn * (drho * math.cos(phi) - 2 * rho * math.sin(phi)), drho * math.sin(phi) + 2 * rho * math.cos(phi)])

    ts = np.linspace(math.radians(30.0), math.radians(330.0), TREFOIL_POINTS)
    knot = np.array([point(t) for t in ts])
    v_in, v_out = velocity(ts[0]), velocity(ts[-1])

    def tail(end, p, v, into: bool):
        """A cubic from the tail end `end` (tangent along the ring, towards the knot) to `p`,
        arriving with the knot's tangent `v` (into the knot) - or the reverse for the way out."""
        end = np.asarray(end, float)
        t_end = np.array([-sgn, 0.0])                                        # from the tail end towards the knot
        d = float(np.linalg.norm(p - end))
        v = v / max(np.linalg.norm(v), 1e-12)
        if into:
            P0, P1, P2, P3 = end, end + t_end * d / 3, p - v * d / 3, p
        else:
            P0, P1, P2, P3 = p, p + v * d / 3, end + t_end * d / 3, end
        u = np.linspace(0.0, 1.0, TAIL_POINTS + 1)[:, None]
        return ((1 - u) ** 3 * P0 + 3 * (1 - u) ** 2 * u * P1 + 3 * (1 - u) * u ** 2 * P2 + u ** 3 * P3)

    upper, lower = tail_ends
    head = tail(upper, knot[0], v_in, into=True)[:-1]                       # ends on the knot's first point
    foot = tail(lower, knot[-1], v_out, into=False)[1:]                     # starts after the knot's last point
    return Strand(np.vstack([head, knot, foot]), closed=False)


# ---- sections and sweeps -------------------------------------------------------------------------
def ribbon_profile(width: float, thickness: float, corner: float, step: float = PROFILE_STEP_MM):
    """A rounded rectangle in the sweep's section plane as (m, 2) points (n, b), counter-clockwise:
    n along the frame's N (radial on the ring: the thickness), b along B (across the surface: the
    width); corners rounded by `corner`, flats subdivided every `step` so that wrapped vertex-wise
    the ribbon's faces follow the cylinder."""
    import numpy as np
    hw, ht = width / 2, thickness / 2
    rc = min(max(corner, 0.0), hw - 1e-6, ht - 1e-6)
    pts = []

    def flat(p, q):
        p, q = np.asarray(p, float), np.asarray(q, float)
        n = max(1, int(math.ceil(np.linalg.norm(q - p) / step)))
        for k in range(n):
            pts.append(p + (q - p) * k / n)

    def arc(centre, a0, a1):
        for k in range(CORNER_SEGMENTS):
            a = a0 + (a1 - a0) * k / CORNER_SEGMENTS
            pts.append((centre[0] + rc * math.cos(a), centre[1] + rc * math.sin(a)))

    flat((ht, -hw + rc), (ht, hw - rc))                       # outer face, b increasing
    arc((ht - rc, hw - rc), 0.0, math.pi / 2)
    flat((ht - rc, hw), (-ht + rc, hw))                       # the +b edge
    arc((-ht + rc, hw - rc), math.pi / 2, math.pi)
    flat((-ht, hw - rc), (-ht, -hw + rc))                     # inner face
    arc((-ht + rc, -hw + rc), math.pi, 1.5 * math.pi)
    flat((-ht + rc, -hw), (ht - rc, -hw))                     # the -b edge
    arc((ht - rc, -hw + rc), 1.5 * math.pi, 2 * math.pi)
    return np.asarray(pts, float)


def wire_profile(diameter: float, points: int = WIRE_POINTS):
    """A circle in the section plane, (points, 2)."""
    import numpy as np
    ang = np.arange(points) * 2 * math.pi / points
    return np.column_stack([np.cos(ang), np.sin(ang)]) * (diameter / 2)


def offset_profile(profile, inward: float):
    """A profile's points moved `inward` along the inward normal (the polygon's own orientation
    found from its signed area): a true inset, the same point count."""
    import numpy as np
    P = np.asarray(profile, float)
    nxt, prv = np.roll(P, -1, axis=0), np.roll(P, 1, axis=0)
    t = nxt - prv
    t /= np.linalg.norm(t, axis=1)[:, None]
    normal = np.column_stack([t[:, 1], -t[:, 0]])                       # the right-hand normal: outward for a CCW loop
    area = 0.5 * float(np.sum(P[:, 0] * nxt[:, 1] - nxt[:, 0] * P[:, 1]))
    if area < 0:
        normal = -normal
    return P - inward * normal


def sweep_rings(path, profile=None, closed: bool = False, up=None, scale=None, profiles=None):
    """The vertex rings of sweep_along, (n, m, 3), before any faces are built - a body that
    continues the sweep takes its end ring as its own (bit for bit, so the two meet in one shared
    face). `reversed` says whether the profile was turned to run counter-clockwise."""
    import numpy as np
    P = np.asarray(path, float)
    n = len(P)
    if profiles is not None:
        prof = np.asarray(profiles, float)                                 # (n, m, 2)
    else:
        prof = np.broadcast_to(np.asarray(profile, float)[None, :, :], (n, len(profile), 2))
    sc = np.ones((n, 2)) if scale is None else np.asarray(scale, float)
    if sc.ndim == 1:
        sc = np.column_stack([sc, sc])
    if closed:
        T = np.roll(P, -1, axis=0) - np.roll(P, 1, axis=0)
    else:
        T = np.gradient(P, axis=0)
    T /= np.linalg.norm(T, axis=1)[:, None]
    N = np.zeros_like(T)
    if up is not None:
        u = np.asarray(up, float)
        if u.ndim == 1:
            u = np.broadcast_to(u / np.linalg.norm(u), T.shape)
        else:
            u = u / np.linalg.norm(u, axis=1)[:, None]
        N = u - T * np.einsum("ij,ij->i", T, u)[:, None]
        if (np.linalg.norm(N, axis=1) < 1e-6).any():
            raise ValueError("sweep_along: the path runs along `up`")
        N /= np.linalg.norm(N, axis=1)[:, None]
    else:
        a = np.array([0.0, 0.0, 1.0]) if abs(T[0][2]) < 0.9 else np.array([1.0, 0.0, 0.0])
        N[0] = a - T[0] * (a @ T[0])
        N[0] /= np.linalg.norm(N[0])
        for i in range(1, n):
            b = np.cross(T[i - 1], T[i])
            s_ = np.linalg.norm(b)
            if s_ < 1e-12:
                N[i] = N[i - 1]
            else:
                b /= s_
                c = float(np.clip(T[i - 1] @ T[i], -1.0, 1.0))
                ang = math.atan2(s_, c)
                v = N[i - 1]
                N[i] = v * math.cos(ang) + np.cross(b, v) * math.sin(ang) + b * (b @ v) * (1 - math.cos(ang))
            N[i] -= T[i] * (N[i] @ T[i])
            N[i] /= np.linalg.norm(N[i])
    B = np.cross(T, N)
    # every section counter-clockwise in (N, B): with (N, B, T) right-handed the side faces face outward
    area = 0.5 * np.sum(prof[0, :, 0] * np.roll(prof[0, :, 1], -1) - np.roll(prof[0, :, 0], -1) * prof[0, :, 1])
    reversed_ = bool(area < 0)
    if reversed_:
        prof = prof[:, ::-1, :]
    ring = (prof[:, :, 0] * sc[:, 0, None])[:, :, None] * N[:, None, :] + (prof[:, :, 1] * sc[:, 1, None])[:, :, None] * B[:, None, :]   # (n, m, 3)
    return P[:, None, :] + ring, reversed_


def mesh_from_rings(rings, closed: bool = False, start_cap=None, end_cap=None):
    """The watertight sweep over vertex rings (n, m, 3) (sweep_rings): rings joined vertex to vertex,
    a closed loop joined end to start, an open one capped - with a fan about each end ring's mean
    (the section must be star-shaped about it), or with `start_cap` / `end_cap`, (t, 3) index
    triangles over the ring: a body that continues the sweep caps its own end with the same
    triangles, so the two caps cancel exactly in the union (cap_triangles)."""
    import numpy as np
    import trimesh
    R = np.asarray(rings, float)
    n, m = R.shape[0], R.shape[1]
    V = R.reshape(-1, 3)
    faces = []
    last = n if closed else n - 1
    for i in range(last):
        a0 = i * m + np.arange(m)
        b0 = ((i + 1) % n) * m + np.arange(m)
        an, bn = np.roll(a0, -1), np.roll(b0, -1)
        faces.append(np.column_stack([a0, an, bn]))
        faces.append(np.column_stack([a0, bn, b0]))
    F = np.vstack(faces)
    if not closed:
        extra = []
        for which, cap in (("start", start_cap), ("end", end_cap)):
            base = 0 if which == "start" else (n - 1) * m
            T = (R[1].mean(axis=0) - R[0].mean(axis=0)) if which == "start" else (R[-1].mean(axis=0) - R[-2].mean(axis=0))
            want = -T if which == "start" else T                            # the cap faces out along the path's end
            if cap is None:
                c = len(V)
                V = np.vstack([V, R[0 if which == "start" else -1].mean(axis=0)])
                idx = np.arange(m)
                tri = np.column_stack([np.full(m, c), base + np.roll(idx, -1), base + idx])
            else:
                tri = base + np.asarray(cap, int)
            normal = np.cross(V[tri[:, 1]] - V[tri[:, 0]], V[tri[:, 2]] - V[tri[:, 0]]).sum(axis=0)
            if normal @ want < 0:
                tri = tri[:, ::-1]
            extra.append(tri)
        F = np.vstack([F] + extra)
    mesh = trimesh.Trimesh(V, F, process=False)
    if mesh.volume < 0:                                   # a left-handed frame (parallel transport may start one): turn it
        mesh.invert()
    return mesh


def cap_triangles(section):
    """Index triangles covering a section ((m, 2) points, a simple loop): the cap both bodies that
    meet in that section use (earcut, deterministic for one vertex sequence)."""
    import numpy as np
    from shapely.geometry import Polygon
    from trimesh.creation import triangulate_polygon
    from scipy.spatial import cKDTree
    pts = np.asarray(section, float)
    v, f = triangulate_polygon(Polygon(pts), engine="earcut")
    _, idx = cKDTree(pts).query(v)
    return idx[np.asarray(f)]


def sweep_along(path, profile=None, closed: bool = False, up=None, scale=None, profiles=None):
    """A watertight sweep of a 2-D profile ((m, 2) points (n, b) in the section plane, a simple
    loop) along a 3-D polyline (N, 3): the section's N axis is `up` (one vector, or one per path
    point) projected off the tangent, B = T x N; without `up` the frame is parallel-transported.
    A closed loop joins its ends, an open one is capped (a fan about the end section's mean: the
    profile must be star-shaped about it). Joined vertex to vertex, no twist of its own. `up` as a
    function of the local tangent alone gives a periodic path a periodic sweep (parallel transport
    comes back from a turn rotated: the rope, 2026-10-30). `scale` (one factor per path point, or
    a pair (n, b) per point) scales the section about its origin there; `profiles` ((N, m, 2), one
    section per path point) replaces `profile` where the section changes along the way - a tail
    narrowing to a knot's ribbon."""
    rings, _ = sweep_rings(path, profile, closed, up, scale, profiles)
    return mesh_from_rings(rings, closed)
