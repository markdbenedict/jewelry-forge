"""Artwork on the band - Phase 3 step 5: sunk panels on a band's faces carrying a motif in relief.

A panel is a channel cut into one face of the band over an arc - the outer face (the one away from
the finger) or a side face - leaving a rail along each edge, with a motif standing in relief on the
channel's floor, its top `below_mm` under the face so the rails protect it (the Seraphine Celtic
ring, reference 2026-11-03: leaf rows in channels on both side faces, a vine scroll in a channel on
the outer face, from the shoulders to 120° from the top). Motifs are 2-D (shapely) in the panel's
own frame - u along the ring from the panel's start, v across the channel - so new ones are a
function returning polygons: `leaves` (a row of teardrop leaves with a shallow vein), `vine` (an
S-curve spine with leaves budding off it and a curl at each end), `volute` (a spiral scroll),
`plain` (the sunk channel alone).

Geometry: everything is built in the bar frame (X radial, Y along the ring - Y = wrap length is a
turn, angle 0 at the top - Z axial) and wrapped vertex-wise round Z (geom.remap_cylindrical,
exactly what nTop's Remap Cylindrical does), after subdividing so no facet spans more than a
fraction of a degree. Python writes two ring-frame meshes: the channel cutters (one body per
panel, disjoint) and the relief (one body per leaf or motif, disjoint, each plugged PLUG_MM into
the channel floor so the union sees an overlap, never a shared face). ring_artwork.ntop builds
(shank − cutters) ∪ relief: the band is opened by the edge round first, so the channel edges stay
crisp and the relief is never rounded. A panel's motif is a little distorted across a side face
(the wrap stretches along the ring in proportion to the radius: ±10 % over a 2 mm thick band),
as the fanning of a real ring's face would.

Angles are measured from the top (+X), positive towards +Y; a mirrored panel appears at −θ too,
its motif running from the head downwards on both sides.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import band, catalog, config, gate, geom, ntopcl, runs, tables
from . import shank as shankmod

MOTIFS = ("leaves", "vine", "volute", "plain")
FACES = ("outer", "side+", "side-")
PLUG_MM = 0.1                 # relief bodies sink this far into the channel floor
MAX_EDGE_MM = 0.25            # facets subdivided to this before the wrap (a chord under 0.001 mm at r 10)
VEIN_WIDTH_MM = 0.2
VEIN_DEPTH_MM = 0.12
PROBE_MM = 0.25               # the gate's probe grid over a panel
PROBE_MARGIN_MM = 0.12        # probes this close to a motif's edge are skipped (the mesher's blur)
RAIL_MIN_MM = 0.3             # a rail (a lip on a solid band, not a wall) must be at least this wide to cast


def setting(name: str, default: float) -> float:
    return float(tables.SETTINGS.get(name, default))


# ---- 2-D motifs (panel frame: u along the ring from the panel's start, v across the channel) -------
def leaf_polygon(length: float, width: float):
    """A teardrop leaf pointing along +u: the hull of a disc at its base and the tip."""
    from shapely.geometry import MultiPoint, Point
    base = Point(width / 2, 0.0).buffer(width / 2, quad_segs=24)
    return MultiPoint(list(base.exterior.coords) + [(length, 0.0)]).convex_hull


def leaf_vein(length: float, width: float | None = None) -> tuple:
    """The shallow groove down a leaf's middle as a segment ((u0, v0), (u1, v1), width): from a
    quarter along to short of the tip, VEIN_WIDTH_MM wide or a fifth of the leaf's width on a small
    leaf. A vein is a straight slit, so it is swept, never triangulated (vein_polygon draws it)."""
    w = VEIN_WIDTH_MM if width is None else min(VEIN_WIDTH_MM, 0.2 * width)
    return ((0.25 * length, 0.0), (0.82 * length, 0.0), w)


def vein_polygon(seg: tuple):
    from shapely.geometry import LineString
    (a, b, w) = seg
    return LineString([a, b]).buffer(w / 2, cap_style="round")


def _move_seg(seg: tuple, angle_deg: float, du: float, dv: float) -> tuple:
    """A vein segment rotated about the origin and shifted, as shapely's rotate + translate."""
    c, s = math.cos(math.radians(angle_deg)), math.sin(math.radians(angle_deg))
    (a, b, w) = seg
    rot = lambda q: (c * q[0] - s * q[1] + du, s * q[0] + c * q[1] + dv)             # noqa: E731
    return (rot(a), rot(b), w)


def motif_leaves(length_u: float, width_v: float, leaf: float, pitch: float, vein: bool) -> list[dict]:
    """A row of leaves along the panel, pointing away from the head, each {'poly', 'groove'}."""
    from shapely.affinity import translate
    out = []
    n = int(math.floor((length_u - leaf) / pitch + 1e-9)) + 1
    slack = (length_u - leaf - (n - 1) * pitch) / 2                    # centred in the panel
    width = min(width_v, 0.85 * leaf)
    for k in range(n):
        u0 = slack + k * pitch
        poly = translate(leaf_polygon(leaf, width), u0, 0.0)
        out.append({"poly": poly, "veins": [_move_seg(leaf_vein(leaf), 0.0, u0, 0.0)] if vein else []})
    return out


def _spiral(turns: float, r0: float, r1: float, n: int = 90):
    """An Archimedean spiral from radius r0 to r1 over `turns` turns, as (n, 2) points."""
    import numpy as np
    t = np.linspace(0.0, 2 * math.pi * turns, n)
    r = r0 + (r1 - r0) * t / t[-1]
    return np.column_stack([r * np.cos(t), r * np.sin(t)])


def motif_volute(length_u: float, width_v: float, stroke: float) -> list[dict]:
    """A scroll: a spiral of 1.4 turns filling the panel's width, its tail running on along u."""
    from shapely.geometry import LineString
    R = width_v / 2 - stroke / 2
    pts = _spiral(1.4, 0.25 * R, R)
    pts = pts + [R + stroke / 2, 0.0]
    tail = [(float(pts[-1, 0]), float(pts[-1, 1])), (length_u - stroke / 2, 0.0)] if length_u > 2 * R + stroke else []
    line = LineString(list(map(tuple, pts)) + tail)
    return [{"poly": line.buffer(stroke / 2, cap_style="round", join_style="round"), "veins": []}]


def motif_vine(length_u: float, width_v: float, stroke: float, leaf: float, vein: bool) -> list[dict]:
    """A vine: a gentle S-curve spine the length of the panel with a leaf budding outward and
    onward at each crest and a curl at each end, united into one polygon and clipped to the channel
    (nothing stands over the rails or past the band's edge)."""
    import numpy as np
    from shapely.affinity import rotate, translate
    from shapely.geometry import LineString, box
    from shapely.ops import unary_union
    half = width_v / 2
    A = 0.25 * width_v                                                  # the spine's swing
    period = max(3.0 * leaf, 2.5)
    n_half = max(2, int(round(2 * length_u / period)))                 # whole half-periods
    period = 2 * length_u / n_half
    u = np.linspace(0.0, length_u, max(20, int(length_u / 0.1)))
    v = A * np.sin(2 * math.pi * u / period)
    spine = LineString(np.column_stack([u, v])).buffer(stroke / 2, cap_style="round", join_style="round")
    parts, veins = [spine], []
    leaf_w = 0.5 * leaf
    for k in range(n_half):
        uc = (k + 0.5) * period / 2                                     # a crest
        side = 1.0 if k % 2 == 0 else -1.0
        ang, at = 32.0 * side, (uc - 0.1 * leaf, side * (A - 0.08))
        parts.append(translate(rotate(leaf_polygon(leaf, leaf_w), ang, origin=(0.0, 0.0)), *at))
        if vein:
            veins.append(_move_seg(leaf_vein(leaf, leaf_w), ang, *at))
    curl_r = max(0.25, min(half - stroke / 2 - 0.05, 0.6 * leaf))
    for end, sign in ((0.0, 1.0), (length_u, -1.0)):               # a hook at each end (a full spiral fills in at this stroke)
        pts = _spiral(0.75, 0.55 * curl_r, curl_r, 36)
        pts = pts * [sign, 1.0] + [end + sign * curl_r, 0.0]
        parts.append(LineString(list(map(tuple, pts))).buffer(stroke / 2, cap_style="round", join_style="round"))
    clip = box(0.0, -half + 0.08, length_u, half - 0.08)
    poly = unary_union(parts).intersection(clip)
    polys = [q for q in getattr(poly, "geoms", [poly]) if q.area > 0.02]
    out = []
    for q in polys:                                                     # a vein stays where its leaf survived the clip
        keep = [v for v in veins if q.buffer(-0.03).contains(vein_polygon(v))]
        out.append({"poly": q, "veins": keep})
    return out



# ---- clean meshes for the wrap --------------------------------------------------------------------
def prism_along_y(x0: float, x1: float, z0: float, z1: float, y0: float, y1: float, dy: float):
    """A box lofted along Y: a rectangle (x0..x1, z0..z1) at every station y0..y1 (at most `dy`
    apart), the four walls quad strips between stations, the ends two triangles - a structured
    watertight mesh whose every face spans one station, so the wrap bends it cleanly."""
    import numpy as np
    import trimesh
    n = max(2, int(math.ceil((y1 - y0) / dy)) + 1)
    ys = np.linspace(y0, y1, n)
    corners = np.array([[x0, z0], [x1, z0], [x1, z1], [x0, z1]])
    V = np.array([[cx, y, cz] for y in ys for cx, cz in corners])
    F = []
    for k in range(n - 1):
        a, b = 4 * k, 4 * (k + 1)
        for i in range(4):
            j = (i + 1) % 4
            F += [[a + i, b + i, b + j], [a + i, b + j, a + j]]
    F += [[0, 2, 1], [0, 3, 2]]                                   # the y0 end
    e = 4 * (n - 1)
    F += [[e, e + 1, e + 2], [e, e + 2, e + 3]]                   # the y1 end
    m = trimesh.Trimesh(V, np.array(F), process=False)
    trimesh.repair.fix_winding(m)
    if m.volume < 0:
        m.invert()
    return m


def densified(poly, step: float = MAX_EDGE_MM):
    """The polygon with a vertex at least every `step` along its boundary (shapely segmentize), so
    an extrusion's every wall quad is short and bends cleanly under the wrap; its caps need no
    refinement (planar after the wrap on a side face; on the outer face a cap triangle a leaf wide
    sags 0.01 mm under the cylinder at r 10). No 3-D subdivision: trimesh's subdivide_to_size
    leaves T-junctions that pierce their neighbours once wrapped, and uniform subdivision of
    earcut's sliver caps gave 18,000 intersecting pairs after float32 (2026-11-03)."""
    import shapely
    return shapely.segmentize(shapely.simplify(poly, 0.01, preserve_topology=True), step)   # a union's or clip's
                                                                                            # near-duplicate points out first



def swept_slit(p0, p1, width: float, r0: float, r1: float, wrap_length: float, step: float = MAX_EDGE_MM):
    """A rectangle `width` across x (r1 - r0) radial, swept along the segment p0 -> p1 in the bar
    frame's (y, z) at stations at most `step` apart, every vertex wrapped round Z: a vein's slit
    cutter on the outer face. Structured like prism_along_y, so it bends cleanly."""
    import numpy as np
    import trimesh
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    d = p1 - p0
    L = float(np.linalg.norm(d))
    n = max(2, int(math.ceil(L / step)) + 1)
    t_ = d / L
    nrm = np.array([-t_[1], t_[0]])
    V = []
    for k in np.linspace(0.0, 1.0, n):
        c = p0 + k * d
        for yz, r in ((c - nrm * width / 2, r0), (c + nrm * width / 2, r0), (c + nrm * width / 2, r1), (c - nrm * width / 2, r1)):
            th = 2 * math.pi * yz[0] / wrap_length
            V.append([r * math.cos(th), r * math.sin(th), yz[1]])
    F = []
    for k in range(n - 1):
        a, b = 4 * k, 4 * (k + 1)
        for i in range(4):
            j = (i + 1) % 4
            F += [[a + i, b + i, b + j], [a + i, b + j, a + j]]
    F += [[0, 2, 1], [0, 3, 2]]
    e = 4 * (n - 1)
    F += [[e, e + 1, e + 2], [e, e + 2, e + 3]]
    m = trimesh.Trimesh(np.array(V), np.array(F), process=False)
    trimesh.repair.fix_winding(m)
    if m.volume < 0:
        m.invert()
    return m


class _Tri:
    """A triangulation with edge flips: triangles as index triples (counter-clockwise), an
    edge -> triangles map, Lawson flips to Delaunay quality and Sloan's constraint recovery."""

    def __init__(self, pts, tris):
        import numpy as np
        self.pts = np.asarray(pts, float)
        self.tris = {}
        self.edges = {}
        for k, t in enumerate(np.asarray(tris)):
            self._add(k, [int(x) for x in t])
        self.next_id = len(self.tris)

    @staticmethod
    def _key(u, v):
        return (u, v) if u < v else (v, u)

    def _add(self, k, t):
        a, b, c = t
        p = self.pts
        if (p[b, 0] - p[a, 0]) * (p[c, 1] - p[a, 1]) - (p[b, 1] - p[a, 1]) * (p[c, 0] - p[a, 0]) < 0:
            t = [a, c, b]
        self.tris[k] = t
        for u, v in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            self.edges.setdefault(self._key(u, v), set()).add(k)

    def _remove(self, k):
        t = self.tris.pop(k)
        for u, v in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            s = self.edges[self._key(u, v)]
            s.discard(k)
            if not s:
                del self.edges[self._key(u, v)]

    def _new(self, t):
        self.next_id += 1
        self._add(self.next_id, t)
        return self.next_id

    @staticmethod
    def _cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def _segments_cross(self, a, b, c, d):
        """Proper crossing of segments ab and cd (no shared endpoints)."""
        p = self.pts
        if len({a, b, c, d}) < 4:
            return False
        d1, d2 = self._cross(p[c], p[d], p[a]), self._cross(p[c], p[d], p[b])
        d3, d4 = self._cross(p[a], p[b], p[c]), self._cross(p[a], p[b], p[d])
        return (d1 * d2 < 0) and (d3 * d4 < 0)

    def flip(self, u, v):
        """Flip the edge uv shared by two triangles into the other diagonal; the new edge, or
        None when the quad is not convex (or uv is a boundary edge)."""
        ts = self.edges.get(self._key(u, v), set())
        if len(ts) != 2:
            return None
        k1, k2 = sorted(ts)
        e = [x for x in self.tris[k1] if x not in (u, v)][0]
        f = [x for x in self.tris[k2] if x not in (u, v)][0]
        if not self._segments_cross(u, v, e, f):
            return None
        self._remove(k1)
        self._remove(k2)
        self._new([e, f, u])
        self._new([f, e, v])
        return (e, f)

    def _circum_violates(self, u, v):
        ts = self.edges.get(self._key(u, v), set())
        if len(ts) != 2:
            return False
        k1, k2 = sorted(ts)
        a, b, c = self.tris[k1]
        d = [x for x in self.tris[k2] if x not in (u, v)][0]
        p = self.pts
        ax, ay = p[a] - p[d]
        bx, by = p[b] - p[d]
        cx, cy = p[c] - p[d]
        det = ((ax * ax + ay * ay) * (bx * cy - cx * by) - (bx * bx + by * by) * (ax * cy - cx * ay)
               + (cx * cx + cy * cy) * (ax * by - bx * ay))
        return det > 1e-12

    def recover(self, a, b):
        """Make ab an edge by flipping the edges that cross it (Sloan)."""
        for _ in range(10000):
            if self._key(a, b) in self.edges:
                return True
            crossing = [k for k in self.edges if self._segments_cross(a, b, k[0], k[1])]
            if not crossing:
                return False
            done = False
            for u, v in crossing:
                if self.flip(u, v) is not None:
                    done = True
                    break
            if not done:
                return False
        return False

    def delaunay(self, constraints: set, rounds: int = 20):
        """Lawson flips on every non-constraint edge until none violates the circumcircle test."""
        for _ in range(rounds):
            flipped = 0
            for key in list(self.edges):
                if key in constraints or key not in self.edges:
                    continue
                if self._circum_violates(*key) and self.flip(*key) is not None:
                    flipped += 1
            if not flipped:
                break


def quality_triangulate(poly, step: float = MAX_EDGE_MM):
    """A sliver-free constrained Delaunay triangulation of a polygon (holes allowed): Delaunay over
    its boundary densified every `step` plus an interior grid, every boundary edge recovered by edge
    flips, triangles outside dropped, the rest flipped back to Delaunay quality. Returns (points,
    triangles, rings) with each boundary ring's point indices in order; every boundary edge is the
    edge of exactly one triangle (else ValueError). Boundary triangles then stand at least a few
    hundredths of a millimetre tall, so a cap of them survives the cylindrical wrap (unconstrained
    Delaunay crossed or doubled an edge at a leaf's notch, 2026-11-03)."""
    import numpy as np
    import shapely
    from scipy.spatial import Delaunay
    poly = densified(poly, step)
    rings_xy = [np.asarray(poly.exterior.coords)[:-1]] + [np.asarray(h.coords)[:-1] for h in poly.interiors]
    pts = np.vstack(rings_xy)
    rings, k = [], 0
    for r in rings_xy:
        rings.append(np.arange(k, k + len(r)))
        k += len(r)
    inner = poly.buffer(-0.45 * step)
    x0, y0, x1, y1 = poly.bounds
    gx, gy = np.meshgrid(np.arange(x0 + 0.137 * step, x1, 0.8 * step), np.arange(y0 + 0.213 * step, y1, 0.8 * step))
    g = np.column_stack([gx.ravel(), gy.ravel()])
    if not inner.is_empty and len(g):
        g = g[shapely.contains_xy(inner, g[:, 0], g[:, 1])]
        if len(g):
            pts = np.vstack([pts, g])
    T = _Tri(pts, Delaunay(pts).simplices)
    constraints = set()
    for r in rings:
        for i in range(len(r)):
            a, b = int(r[i]), int(r[(i + 1) % len(r)])
            constraints.add(T._key(a, b))
            if not T.recover(a, b):
                raise ValueError("quality_triangulate: a boundary edge could not be recovered")
    tri = np.array(list(T.tris.values()))
    cent = pts[tri].mean(axis=1)
    e1, e2 = pts[tri[:, 1]] - pts[tri[:, 0]], pts[tri[:, 2]] - pts[tri[:, 0]]
    area2 = np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0])
    tri = tri[shapely.contains_xy(poly, cent[:, 0], cent[:, 1]) & (area2 > 1e-9)]   # flat triangles of three collinear
    T = _Tri(pts, tri)                                                                  # boundary points out (a straight clip edge)
    T.delaunay(constraints)
    tri = np.array(list(T.tris.values()))
    count: dict = {}
    for a, b, c in tri:
        for u, v in ((a, b), (b, c), (c, a)):
            count[T._key(int(u), int(v))] = count.get(T._key(int(u), int(v)), 0) + 1
    for key in constraints:
        if count.get(key, 0) != 1:
            raise ValueError("quality_triangulate: a boundary edge is not the edge of exactly one triangle")
    return pts, tri, rings


def _prism(pts, tri, rings, lo, hi):
    """A watertight body from a cap triangulation placed twice: `lo` and `hi` are (n, 3) arrays
    of the cap points' 3-D positions; walls join the rings' consecutive points."""
    import numpy as np
    import trimesh
    n = len(pts)
    V = np.vstack([lo, hi])
    F = [list(t[::-1]) for t in tri] + [[t[0] + n, t[1] + n, t[2] + n] for t in tri]
    for r in rings:
        for i in range(len(r)):
            a, b = int(r[i]), int(r[(i + 1) % len(r)])
            F += [[a, b, b + n], [a, b + n, a + n]]
    m = trimesh.Trimesh(V, np.array(F), process=False)
    trimesh.repair.fix_winding(m)
    if m.volume < 0:
        m.invert()
    return m


def radial_prism(poly_yz, r0: float, r1: float, wrap_length: float):
    """A polygon in the bar frame's (y, z) swept radially from r0 to r1 and wrapped round Z
    (y -> angle, y = wrap_length a turn): caps on the two cylinders, walls between the rings'
    consecutive points. Watertight, outward-wound."""
    import numpy as np
    pts, tri, rings = quality_triangulate(poly_yz)
    th = 2 * math.pi * pts[:, 0] / wrap_length
    lo = np.column_stack([r0 * np.cos(th), r0 * np.sin(th), pts[:, 1]])
    hi = np.column_stack([r1 * np.cos(th), r1 * np.sin(th), pts[:, 1]])
    return _prism(pts, tri, rings, lo, hi)


def axial_prism(poly_xy, z0: float, z1: float):
    """A ring-frame polygon in (X, Y) extruded along the ring axis from z0 to z1, its caps
    triangulated by quality_triangulate (trimesh's earcut extrusion crossed itself on a cap with
    a hole, a vine's closed hook, 2026-11-03)."""
    import numpy as np
    pts, tri, rings = quality_triangulate(poly_xy)
    lo = np.column_stack([pts, np.full(len(pts), min(z0, z1))])
    hi = np.column_stack([pts, np.full(len(pts), max(z0, z1))])
    return _prism(pts, tri, rings, lo, hi)


# ---- the spec ----------------------------------------------------------------------------------------
@dataclass
class Panel:
    face: str = "outer"           # outer | side+ | side-
    motif: str = "leaves"         # leaves | vine | volute | plain
    start_deg: float = 25.0       # from the top, the end nearest the head
    end_deg: float = 120.0
    mirror: bool = True           # the same panel on the -Y side


@dataclass
class ArtworkSpec:
    shank: shankmod.ShankSpec
    panels: list = field(default_factory=list)
    channel_mm: float = 0.30      # the channel's depth into the face
    rail_mm: float = 0.35         # metal left along each edge of the face
    relief_mm: float = 0.25       # the motif's height above the channel floor
    leaf_mm: float = 0.0          # leaf length; 0 = from the channel's width
    leaf_pitch: float = 1.3       # leaf to leaf, in leaf lengths
    stroke_mm: float = 0.3        # a vine's or volute's stroke
    vein: bool = True
    _cache: dict = field(default_factory=dict, repr=False, compare=False)

    # ---- numbers ---------------------------------------------------------------------------
    @property
    def band(self) -> band.BandSpec:
        return self.shank.band

    @property
    def below(self) -> float:
        """The relief's top below the face (the rails stand proud of it by this)."""
        return self.channel_mm - self.relief_mm

    @property
    def L(self) -> float:
        return self.shank.wrap_length_mm

    def y_of(self, theta_deg: float) -> float:
        return theta_deg / 360.0 * self.L

    def channel_width(self, face: str) -> float:
        b = self.band
        return (b.width_mm if face == "outer" else b.thickness_mm) - 2 * self.rail_mm

    def leaf_length(self, face: str) -> float:
        return float(self.leaf_mm) if self.leaf_mm else round(min(1.35 * self.channel_width(face), 2.0), 3)

    def panel_length(self, p: Panel) -> float:
        return self.y_of(p.end_deg - p.start_deg)

    def motif(self, p: Panel) -> list[dict]:
        """The panel's motif polygons in the panel frame (cached)."""
        key = ("motif", id(p))
        if key not in self._cache:
            w, Lu = self.channel_width(p.face), self.panel_length(p)
            if p.motif == "leaves":
                leaf = self.leaf_length(p.face)
                m = motif_leaves(Lu - 0.3, w - 0.2, leaf, self.leaf_pitch * leaf, self.vein)
            elif p.motif == "vine":
                leaf = min(0.8 * self.leaf_length(p.face), 0.45 * (w - 0.2))
                m = motif_vine(Lu - 0.3, w - 0.2, self.stroke_mm, leaf, self.vein)
            elif p.motif == "volute":
                m = motif_volute(Lu - 0.3, w - 0.2, self.stroke_mm)
            else:
                m = []
            from shapely.affinity import translate                     # 0.15 mm in from the channel's head end
            m = [{"poly": translate(d["poly"], 0.15, 0.0), "veins": [_move_seg(v, 0.0, 0.15, 0.0) for v in d["veins"]]} for d in m]
            self._cache[key] = m
        return self._cache[key]

    def copies(self, p: Panel) -> list[float]:
        """The signs of the panel's copies: +1 (the +Y side), and -1 when mirrored."""
        return [1.0, -1.0] if p.mirror else [1.0]

    # ---- bar-frame geometry --------------------------------------------------------------------
    def _relief_body(self, p: Panel, sign: float, poly, h0: float, h1: float):
        """A panel-frame polygon from height h0 to h1 above the channel floor (negative: into the
        band), as a ring-frame body. On a side face the outline is wrapped in 2-D (the polar map
        of the face plane, injective) and extruded straight along the ring axis: an exact prism,
        nothing warped. On the outer face the outline is triangulated without slivers
        (quality_triangulate) and swept radially (radial_prism), every vertex wrapped: a cap
        triangle's chord sags under the cylinder by c²/8r, under 0.001 mm at the 0.25 mm edges,
        far less than any triangle's height, so nothing folds. (Extruding in the bar frame and
        warping the mesh folded earcut's sliver caps: 96 self-intersecting pairs in the leaves,
        2026-11-03.)"""
        import numpy as np
        import shapely
        import trimesh
        b = self.band
        y0 = sign * self.y_of(p.start_deg)
        poly = densified(poly)
        if p.face == "outer":
            floor = b.outer_radius_mm - self.channel_mm
            yz = shapely.transform(poly, lambda c: np.column_stack([y0 + sign * c[:, 0], c[:, 1]]))
            return radial_prism(yz, floor + h0, floor + h1, self.L)
        out = 1.0 if p.face == "side+" else -1.0
        floor = out * (b.width_mm / 2 - self.channel_mm)
        xmid = (b.bore_radius_mm + b.outer_radius_mm) / 2

        def wrap(c):
            r, y = xmid + c[:, 1], y0 + sign * c[:, 0]
            th = 2 * math.pi * y / self.L
            return np.column_stack([r * np.cos(th), r * np.sin(th)])
        ring = shapely.transform(poly, wrap)
        return axial_prism(ring, floor + out * h0, floor + out * h1)

    def cutter(self, p: Panel, sign: float):
        """The panel's channel: a box the channel's width and length, from the floor out past the
        face, lofted station by station along the ring (a clean quad grid, nothing to refine)."""
        b = self.band
        w, Lu = self.channel_width(p.face), self.panel_length(p)
        if p.face == "outer":
            floor = b.outer_radius_mm - self.channel_mm
            m = prism_along_y(floor, floor + self.channel_mm + 1.0, -w / 2, w / 2, 0.0, Lu, MAX_EDGE_MM)
        else:
            out = 1.0 if p.face == "side+" else -1.0
            zface = out * b.width_mm / 2
            xmid = (b.bore_radius_mm + b.outer_radius_mm) / 2
            z0, z1 = sorted((zface - out * self.channel_mm, zface + out * 1.0))
            m = prism_along_y(xmid - w / 2, xmid + w / 2, z0, z1, 0.0, Lu, MAX_EDGE_MM)
        if sign < 0:
            m.vertices[:, 1] *= -1.0
            m.invert()
        m.apply_translation([0.0, sign * self.y_of(p.start_deg), 0.0])
        return geom.remap_cylindrical(m, self.L)                       # every face spans one station: it bends cleanly

    def relief_bodies(self, p: Panel, sign: float) -> list:
        """The motif's bodies: each polygon from PLUG_MM below the floor to relief_mm above it,
        its vein (a shallow groove) taken out by manifold (one small clean difference per leaf)."""
        import trimesh
        out = []
        for d in self.motif(p):
            body = self._relief_body(p, sign, d["poly"], -PLUG_MM, self.relief_mm)
            for v in d["veins"]:                                                   # one shallow slit at a time
                cut = self._vein_body(p, sign, v, self.relief_mm - VEIN_DEPTH_MM, self.relief_mm + 0.5)
                body = trimesh.boolean.difference([body, cut], engine="manifold")
            out.append(body)
        return out

    def _vein_body(self, p: Panel, sign: float, seg: tuple, h0: float, h1: float):
        """A vein's slit cutter from h0 to h1 above the floor: on a side face the capsule, wrapped in
        2-D and extruded along the axis (exact); on the outer face a rectangle swept along the
        segment station by station (swept_slit), which bends cleanly - a 0.1 mm capsule is too
        thin to triangulate on a grid."""
        if p.face != "outer":
            return self._relief_body(p, sign, vein_polygon(seg), h0, h1)
        b = self.band
        floor = b.outer_radius_mm - self.channel_mm
        y0 = sign * self.y_of(p.start_deg)
        (a, c, w) = seg
        pa, pc = (y0 + sign * a[0], a[1]), (y0 + sign * c[0], c[1])
        return swept_slit(pa, pc, w, floor + h0, floor + h1, self.L)

    def cutters_mesh(self):
        import trimesh
        return trimesh.util.concatenate([self.cutter(p, s) for p in self.panels for s in self.copies(p)])

    def relief_mesh(self):
        import trimesh
        bodies = [b for p in self.panels for s in self.copies(p) for b in self.relief_bodies(p, s)]
        if not bodies:                                                 # plain channels: a speck far outside, so the
            speck = trimesh.creation.icosphere(subdivisions=1, radius=0.05)   # notebook's union has a body to take
            speck.apply_translation([60.0, 0.0, 0.0])
            return speck
        return trimesh.util.concatenate(bodies)

    @property
    def relief_count(self) -> int:
        return sum(len(self.motif(p)) * len(self.copies(p)) for p in self.panels)

    def design_mesh(self):
        """The independent ring: (shank − cutters) ∪ relief (manifold3d)."""
        if "design_mesh" not in self._cache:
            import trimesh
            carved = trimesh.boolean.difference([self.shank.design_mesh(), self.cutters_mesh()], engine="manifold")
            relief = self.relief_mesh()
            if self.relief_count:
                carved = trimesh.boolean.union([carved, relief], engine="manifold")
            self._cache["design_mesh"] = carved
        return self._cache["design_mesh"]

    def design_volume_mm3(self) -> float:
        return float(self.design_mesh().volume)

    def expected_volume_mm3(self) -> float:
        return self.design_volume_mm3() - self.shank.sharp_edge_round_mm3() - self.shank.opening_overcut_mm3()

    def write_layers(self, directory: Path, stem: str) -> tuple[str, str]:
        """Writes <stem>.cut.stl and <stem>.relief.stl, each read back and refused if it crosses
        itself the way nTop would read it (float32; geom.intersecting_faces): a self-intersecting
        layer builds a wrong implicit - the first real run's cutters left needles on the faces."""
        import trimesh
        directory = Path(directory)
        out = []
        for name, mesh in (("cut", self.cutters_mesh()), ("relief", self.relief_mesh())):
            path = directory / f"{stem}.{name}.stl"
            mesh.export(str(path))
            back = trimesh.load(str(path), force="mesh")
            pairs = geom.intersecting_faces(back, cell_mm=0.3)
            if len(pairs) or not back.is_volume:
                raise ValueError(f"the {name} layer crosses itself ({len(pairs)} face pairs) or is not a volume as written to "
                                 f"{path.name}: nTop would read a wrong implicit from it")
            out.append(str(path))
        return out[0], out[1]

    def notebook_inputs(self, bar_paths, cut_path: str, relief_path: str, output_path: str = "") -> dict:
        v = self.shank.notebook_inputs(bar_paths, output_path)
        out = v.pop("Output Path")
        v.update({"Cut Path": str(cut_path), "Relief Path": str(relief_path), "Output Path": out})
        return v

    # ---- identity --------------------------------------------------------------------------------
    def design(self) -> dict:
        d = self.shank.design()
        d.update({"panels": [asdict(p) for p in self.panels], "channel": self.channel_mm, "rail": self.rail_mm,
                  "relief": self.relief_mm, "leaf": self.leaf_mm, "leaf_pitch": self.leaf_pitch, "stroke": self.stroke_mm,
                  "vein": self.vein, "vein_width": VEIN_WIDTH_MM, "vein_depth": VEIN_DEPTH_MM})
        return d

    @property
    def spec_id(self) -> str:
        return runs.spec_id(self.design())

    @property
    def stem(self) -> str:
        b = self.band
        faces = {"outer": "o", "side+": "s", "side-": "s"}
        tag = "_".join(f"{faces[p.face]}{p.motif}" for p in self.panels) or "plain"
        return f"ring_art_{b.profile}_{b.label}_w{b.width_mm:g}t{b.thickness_mm:g}_{tag}_{self.spec_id}"

    @property
    def catalog_name(self) -> str:
        return "ring_artwork"

    # ---- checks on the design ---------------------------------------------------------------------
    def validate(self) -> list[str]:
        p = list(self.shank.validate())
        sh, b = self.shank, self.band
        if sh.rope or sh.knot or sh.strands > 1 or sh.split_mm or sh.dip_mm or sh.tapered:
            p.append("artwork sits on a plain band (a tapered, split, double, rope or knot shank later)")
        if not self.panels:
            p.append("no panels")
        for q in self.panels:
            if q.face not in FACES:
                p.append(f"face {q.face!r}: one of {', '.join(FACES)}")
            if q.motif not in MOTIFS:
                p.append(f"motif {q.motif!r}: one of {', '.join(MOTIFS)}")
            if not 0.0 <= q.start_deg < q.end_deg <= 180.0:
                p.append(f"panel {q.face}: angles {q.start_deg:g}..{q.end_deg:g} must run 0..180° from the top")
        if p:
            return p
        wall = tables.FLOORS["wall_marginal"]
        if self.rail_mm < RAIL_MIN_MM:
            p.append(f"rails {self.rail_mm:g} mm: at least {RAIL_MIN_MM:g} to cast")
        if self.rail_mm < b.edge_round + 0.15:
            p.append(f"rails {self.rail_mm:g} mm: at least the edge round + 0.15 ({b.edge_round + 0.15:.2f}), or the channel cuts into the round")
        if self.relief_mm >= self.channel_mm:
            p.append(f"relief {self.relief_mm:g} mm must stand below the face: less than the channel depth {self.channel_mm:g}")
        if self.relief_mm < 0.15:
            p.append("relief under 0.15 mm will polish away")
        if self.below < 0.03:
            p.append("the relief reaches within 0.03 mm of the face: deepen the channel")
        faces = {q.face for q in self.panels}
        sides = len(faces & {"side+", "side-"})
        if "outer" in faces and sides and self.channel_mm > self.rail_mm - 0.02:
            p.append(f"the outer channel ({self.channel_mm:g} deep) reaches the side channels' walls (rails {self.rail_mm:g}): "
                     "two cutters would touch along an edge, which the STL round trip turns into a non-manifold seam - "
                     "a shallower channel or wider rails")
        core_w = b.width_mm - sides * self.channel_mm
        core_t = b.thickness_mm - (self.channel_mm if "outer" in faces else 0.0)
        if core_w < wall:
            p.append(f"{core_w:.2f} mm of band left between the side channels, under {wall:g}: a wider band or shallower channels")
        if core_t < wall:
            p.append(f"{core_t:.2f} mm of band left under the outer channel, under {wall:g}: a thicker band")
        for q in self.panels:
            if self.channel_width(q.face) < 0.6:
                p.append(f"panel {q.face}: the channel is {self.channel_width(q.face):.2f} mm wide; at least 0.6")
            elif q.motif != "plain" and not self.motif(q):
                p.append(f"panel {q.face}: too short for a {q.motif}")
        if self.stroke_mm < tables.FLOORS["engrave_stroke"]:
            p.append(f"stroke {self.stroke_mm:g} mm under the {tables.FLOORS['engrave_stroke']:g} mm floor")
        return p

    def warnings(self) -> list[str]:
        w = list(self.shank.warnings())
        if self.band.mesh_tolerance_mm > 0.05 + 1e-9:
            w.append(f"Mesh Tolerance {self.band.mesh_tolerance_mm:g} mm is coarse for relief {self.relief_mm:g} mm high and "
                     f"{VEIN_WIDTH_MM:g} mm veins: 0.05 resolves them")
        return w

    def describe(self) -> str:
        b = self.band
        lines = [f"{self.stem}: {b.label}, inner Ø {b.inner_diameter_mm:.3f}, {b.profile} {b.width_mm:g} x {b.thickness_mm:g} mm"]
        for q in self.panels:
            n = len(self.motif(q))
            what = {"leaves": f"{n} leaves of {self.leaf_length(q.face):.2f} mm", "vine": "a vine scroll with leaves",
                    "volute": "a volute", "plain": "nothing (a sunk channel)"}[q.motif]
            lines.append(f"  {q.face} face: a channel {self.channel_width(q.face):.2f} wide x {self.channel_mm:g} deep from "
                         f"{q.start_deg:g}° to {q.end_deg:g}° ({self.panel_length(q):.1f} mm){' each side' if q.mirror else ''}, "
                         f"rails {self.rail_mm:g}; in relief: {what}, {self.relief_mm:g} high, {self.below:.2f} below the face")
        lines.append(f"  {self.relief_count} relief bodies; design volume {self.design_volume_mm3():.2f} mm³ "
                     f"(band {self.shank.design_volume_mm3():.2f}); Mesh Tolerance {b.mesh_tolerance_mm:g}")
        return "\n".join(lines)

    # ---- the gate -----------------------------------------------------------------------------------
    def in_panel(self, theta_deg: float, margin_deg: float = 3.0) -> bool:
        a = (float(theta_deg) + 180.0) % 360.0 - 180.0
        for q in self.panels:
            for s in self.copies(q):
                if q.start_deg - margin_deg <= s * a <= q.end_deg + margin_deg:
                    return True
        return False

    def gate_section(self, theta_deg: float):
        if self.in_panel(theta_deg):
            return gate.section_geometry(self.design_mesh(), theta_deg)
        return self.shank.gate_section(theta_deg)

    def section_tolerance(self, theta_deg: float) -> float:
        t = self.shank.section_tolerance(theta_deg)
        return max(t, float(self.band.mesh_tolerance_mm)) if self.in_panel(theta_deg) else t

    def wall_ray_filter(self):
        """Drops sample points in the channel zone of every panelled face - the channel's floor, walls
        and relief AND the rails beside it, the whole depth of the channel across the face: a rail is a
        lip on a solid band, and a ray through it (from the bore into a side channel, from the outer
        face into one) reads the rail's width, not a wall (p1 0.35 on the first simulated run,
        2026-11-03). Rails have their own floor (RAIL_MIN_MM, validate); what is left measures the
        band's core: the bore between the side channels, every face outside the panels."""
        import numpy as np
        b = self.band

        def keep(pts, normals):
            th = np.degrees(np.arctan2(pts[:, 1], pts[:, 0]))
            r = np.hypot(pts[:, 0], pts[:, 1])
            z = pts[:, 2]
            ok = np.ones(len(pts), dtype=bool)
            for q in self.panels:
                for s in self.copies(q):
                    span = (s * th >= q.start_deg - 0.5) & (s * th <= q.end_deg + 0.5)
                    if q.face == "outer":
                        zone = r > b.outer_radius_mm - self.channel_mm - 0.03
                    else:
                        zs = z if q.face == "side+" else -z
                        zone = zs > b.width_mm / 2 - self.channel_mm - 0.03
                    ok &= ~(span & zone)
            return ok
        return keep

    def probes(self, p: Panel, sign: float):
        """(origins, directions, limits, kinds) of the gate's rays over one panel copy: a grid over
        the channel and its rails, from outside the face inward; kind 'floor', 'relief' or 'rail',
        points within PROBE_MARGIN_MM of a motif's edge or the channel's wall skipped."""
        import numpy as np
        from shapely import contains_xy
        from shapely.ops import unary_union
        b = self.band
        w, Lu = self.channel_width(p.face), self.panel_length(p)
        full = w + 2 * self.rail_mm
        motif = unary_union([d["poly"] for d in self.motif(p)]) if self.motif(p) else None
        inner = motif.buffer(-PROBE_MARGIN_MM) if motif is not None else None
        outer = motif.buffer(PROBE_MARGIN_MM) if motif is not None else None
        us = np.arange(PROBE_MM, Lu, PROBE_MM)
        vs = np.arange(-full / 2 + 0.08, full / 2 - 0.08 + 1e-9, PROBE_MM / 2)
        U, V = np.meshgrid(us, vs)
        U, V = U.ravel(), V.ravel()
        kinds = np.full(len(U), "", dtype=object)
        on_rail = np.abs(V) > w / 2 + PROBE_MARGIN_MM
        in_channel = np.abs(V) < w / 2 - PROBE_MARGIN_MM
        kinds[on_rail] = "rail"
        if inner is not None:
            kinds[in_channel & contains_xy(inner, U, V)] = "relief"
            kinds[in_channel & ~contains_xy(outer, U, V)] = "floor"
        else:
            kinds[in_channel] = "floor"
        keep = kinds != ""
        U, V, kinds = U[keep], V[keep], kinds[keep]
        y = sign * (self.y_of(p.start_deg) + U)
        th = 2 * math.pi * y / self.L
        if p.face == "outer":
            r0 = b.outer_radius_mm + 0.5
            origins = np.column_stack([r0 * np.cos(th), r0 * np.sin(th), V])
            dirs = -np.column_stack([np.cos(th), np.sin(th), np.zeros_like(th)])
        else:
            out = 1.0 if p.face == "side+" else -1.0
            xmid = (b.bore_radius_mm + b.outer_radius_mm) / 2
            r = xmid + V
            z0 = out * (b.width_mm / 2 + 0.5)
            origins = np.column_stack([r * np.cos(th), r * np.sin(th), np.full_like(th, z0)])
            dirs = np.column_stack([np.zeros_like(th), np.zeros_like(th), np.full_like(th, -out)])
        limits = np.full(len(U), self.channel_mm + 1.5)
        return origins, dirs, limits, kinds


def _first_hits(mesh, origins, dirs, limits):
    import numpy as np
    locs, idx, _ = mesh.ray.intersects_location(origins, dirs, multiple_hits=True)
    out = np.full(len(origins), np.inf)
    if len(idx):
        d = np.linalg.norm(locs - origins[idx], axis=1)
        for i, dist in zip(idx, d):
            if dist <= limits[i] and dist < out[i]:
                out[i] = dist
    return out


def artwork_checks(spec: ArtworkSpec, ring) -> list[gate.Check]:
    """Every panel probed by rays cast identically on the built ring and on the design: the
    channel floor at its depth, the relief standing at its height, the rails at the face."""
    import numpy as np
    design = spec.design_mesh()
    tol = max(0.06, 1.5 * float(spec.band.mesh_tolerance_mm))
    totals = {"floor": [0, 0], "relief": [0, 0], "rail": [0, 0]}
    worst = {"floor": 0.0, "relief": 0.0, "rail": 0.0}
    bad_panels = set()
    for p in spec.panels:
        for s in spec.copies(p):
            o, d, lim, kinds = spec.probes(p, s)
            if not len(o):
                continue
            built, want = _first_hits(ring, o, d, lim), _first_hits(design, o, d, lim)
            diff = np.where(np.isfinite(built) & np.isfinite(want), np.abs(built - want), np.inf)
            for k in totals:
                sel = kinds == k
                n, bad = int(sel.sum()), int((diff[sel] > tol).sum())
                totals[k][0] += n
                totals[k][1] += bad
                if n:
                    worst[k] = max(worst[k], float(np.nan_to_num(diff[sel][np.isfinite(diff[sel])].max() if np.isfinite(diff[sel]).any() else np.inf, posinf=9.0)))
                if bad:
                    bad_panels.add(f"{p.face} {'+' if s > 0 else '-'}")
    checks = []
    names = {"floor": "channel floors", "relief": "relief", "rail": "rails"}
    for k, (n, bad) in totals.items():
        if n == 0:
            continue
        ok = bad == 0
        checks.append(gate.Check(names[k], ok, f"{n - bad}/{n} probes where designed (within {tol:.2f} mm; worst {worst[k]:.3f})"
                                 + (f"; wrong on {', '.join(sorted(bad_panels))}" if not ok else "")))
    return checks


def check_artwork(spec: ArtworkSpec, stl: Path, ntop_vol: float | None) -> gate.GateReport:
    b = spec.band
    rep = gate.check(stl, expect_inner=b.inner_diameter_mm, expect_outer=2 * spec.shank.outer_radius_mm,
                     expect_width=spec.shank.overall_width_mm, expect_volume=ntop_vol, wall_floor=spec.shank.wall_floor(),
                     centre="origin", wall_ray_filter=spec.wall_ray_filter(),
                     section_design=spec.gate_section, section_tol_mm=spec.section_tolerance)
    c = band.design_volume_check(spec.expected_volume_mm3(), ntop_vol, 2.0)
    rounded, overcut = spec.shank.sharp_edge_round_mm3(), spec.shank.opening_overcut_mm3()
    if (rounded or overcut) and c.status != gate.INCOMPLETE:
        c.detail += (f" [design {spec.design_volume_mm3():.2f}" + (f" less {rounded:.2f} mm³ of edge rounding" if rounded else "")
                     + (f" less {overcut:.2f} mm³ the mesher's chamfer takes off the band's rounds" if overcut else "") + "]")
    rep.checks.append(c)
    rep.checks += artwork_checks(spec, gate.load_mesh(stl))
    return rep


@dataclass
class ArtworkResult:
    spec: ArtworkSpec
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
        return "\n".join(lines + [f"  note: {n}" for n in self.notes])


def build(spec: ArtworkSpec, out_dir: Path | None = None, *, notebook: Path | None = None,
          catalog_name: str = "ring_artwork", deliver: bool = False, deliver_project: str = "Artwork",
          cast_metal: str | None = None) -> ArtworkResult:
    """Write the bars, the cutters and the relief, run ring_artwork.ntop, gate the export."""
    problems = spec.validate()
    if problems:
        raise ValueError("; ".join(problems))
    cat = catalog.load(catalog_name)
    nb = Path(notebook) if notebook else cat.notebook
    built_notes = runs.require_built(cat, nb) if not notebook else []
    stem = spec.stem
    run_dir, run_id = runs.fresh_run_dir(Path(out_dir) if out_dir else config.out_dir() / "artwork", stem)
    stl = run_dir / f"{stem}.stl"
    bars = shankmod.write_bars(spec.shank, run_dir, stem)
    cut, relief = spec.write_layers(run_dir, stem)
    values = spec.notebook_inputs(bars, cut, relief, str(stl))
    started = time.time()
    run = ntopcl.run(nb, cat.build_inputs(values), run_dir, tag=stem)
    try:
        runs.require_fresh(stl, started, "the exported ring")
    except FileNotFoundError as e:
        raise ntopcl.NtopclError(f"notebook reported success but {e}", run) from e
    entry = run.outputs.get(cat.output.get("name", "Volume"))
    ntop_vol = ntopcl.scalar_value(entry) if entry else None
    rep = check_artwork(spec, stl, ntop_vol)
    gate.save(rep)
    res = ArtworkResult(spec, stl, run, rep, ntop_vol, run_dir, run_id)
    res.notes.append("metal " + ", ".join(f"{k} {w:.2f} g" for k, w in tables.weights_g(rep.volume_mm3).items()))
    res.notes += spec.warnings() + built_notes
    report = {"stem": stem, "spec_id": spec.spec_id, "run_id": run_id, "status": res.status, "ok": res.ok,
              "design": spec.design(), "inputs": values, "stl": str(stl), "bars": bars, "cut": cut, "relief": relief,
              "ntop_volume_mm3": ntop_vol, "design_volume_mm3": spec.design_volume_mm3(),
              "expected_volume_mm3": spec.expected_volume_mm3(), "gate": rep.to_dict(),
              "ntopcl_seconds": run.seconds, "block_timings": [t.__dict__ for t in run.log.timings], "notes": res.notes,
              "notebook": runs.notebook_identity(nb), "environment": runs.environment(ntopcl.version())}
    (run_dir / f"{stem}.report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    if deliver and res.ok:
        res.delivered = runs.deliver(stl, run_dir, stem, deliver_project, report,
                                     extra_files=sorted(set(map(Path, bars))) + [Path(cut), Path(relief)], cast_metal=cast_metal)
    elif deliver:
        res.notes.append(f"not delivered: status {res.status}")
    return res


def seraphine_panels(start_deg: float = 25.0, end_deg: float = 120.0, outer: str = "vine", sides: str = "leaves") -> list[Panel]:
    """The reference ring's layout: a leaf row on each side face, a vine on the outer face."""
    out = []
    if outer != "none":
        out.append(Panel("outer", outer, start_deg, end_deg))
    if sides != "none":
        out += [Panel("side+", sides, start_deg, end_deg), Panel("side-", sides, start_deg, end_deg)]
    return out
