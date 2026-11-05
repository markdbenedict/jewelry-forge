"""Galleries and shared prongs for stones in a row (Phase 3 step 2; reference rings 02 and 05).

    gallery bridge  two rails along the row, one each side of the band, at the height of the heads'
                    upper rails and flush with their outer sides: at each stone the bridge's section
                    IS that head's upper rail where the radial plane through the stone cuts it, and
                    between stones it runs straight from one to the next (in angle, radius and axial
                    offset). It ties the heads into one gallery instead of separate posts standing on
                    the band. A structured loft - one rounded-rectangle station every half degree,
                    quads between, fans at the ends - so it reaches nTop clean (no mesh boolean).
    shared prongs   where two stones face each other, the prong of each that faces the other on the
                    same side of the band becomes ONE post between them: a straight radial rod whose
                    axis stands `rho - ledge` outside BOTH girdles at the girdle's underside (so it
                    overlaps each by the ledge, as every prong overlaps its stone), solved for its
                    angle and axial position. Both seats are cut from it afterwards (the notebook cuts
                    every seat after the blended join), leaving a ledge under each girdle and a tip
                    above them; its radius is raised until what both drop-in paths leave of the tip
                    holds the prong-tip floor.

Everything here is in the ring frame (Z the ring axis, the head at +X), from the placed stones of a
multistone.MultiStoneSpec."""
from __future__ import annotations

import math
from dataclasses import dataclass

from . import geom, tables

PRONG_TIP_FLOOR = tables.FLOORS["prong_tip_dia"]
STATION_DEG = 0.5                  # the bridge's loft: a station every half degree
CORNER_SEGMENTS = 6                # per rounded corner of the bridge's section
POST_DEPTH_MM = 0.3                # a post's foot this far inside the band's outer surface
POST_RHO_STEP_MM = 0.025           # the post's radius grows by this until its tip holds the floor
POST_RHO_MAX_MM = 1.2


# ---- the bridge ----------------------------------------------------------------------------------
def rounded_rect(r0: float, r1: float, z0: float, z1: float, corner: float, n: int = CORNER_SEGMENTS) -> list[tuple]:
    """A rounded rectangle in (radius, axial) - always 4 * (n + 1) points, counter-clockwise - so
    every station of a loft has the same vertices."""
    c = max(0.0, min(corner, 0.45 * (r1 - r0), 0.45 * (z1 - z0)))
    pts = []
    for (cr, cz, a0) in ((r1 - c, z1 - c, 0.0), (r0 + c, z1 - c, 90.0), (r0 + c, z0 + c, 180.0), (r1 - c, z0 + c, 270.0)):
        for k in range(n + 1):
            a = math.radians(a0 + 90.0 * k / n)
            pts.append((cr + c * math.cos(a), cz + c * math.sin(a)))
    return pts


def loft_around_axis(stations: list[tuple[float, list[tuple]]]):
    """A closed mesh through `stations`: (angle in degrees about +Z, [(radius, z) ...]) with the same
    number of points each, in order of angle. Quads between neighbouring stations, a fan from the
    section's centroid at each end."""
    import numpy as np
    import trimesh
    m = len(stations[0][1])
    verts, faces = [], []
    for theta, sec in stations:
        t = math.radians(theta)
        verts += [(r * math.cos(t), r * math.sin(t), z) for r, z in sec]
    n = len(stations)
    for i in range(n - 1):
        a, b = i * m, (i + 1) * m
        for k in range(m):
            k2 = (k + 1) % m
            faces += [(a + k, b + k, b + k2), (a + k, b + k2, a + k2)]
    for end, flip in ((0, True), (n - 1, False)):
        theta, sec = stations[end]
        t = math.radians(theta)
        rc = sum(r for r, _ in sec) / m
        zc = sum(z for _, z in sec) / m
        c = len(verts)
        verts.append((rc * math.cos(t), rc * math.sin(t), zc))
        base = end * m
        for k in range(m):
            k2 = (k + 1) % m
            faces.append((c, base + k2, base + k) if flip else (c, base + k, base + k2))
    mesh = trimesh.Trimesh(np.asarray(verts, float), np.asarray(faces, int), process=False)
    mesh.fix_normals()                                               # one winding, outward
    return mesh


@dataclass
class RailSection:
    """A head's upper rail where the radial plane through its stone cuts it, on one side of the band."""
    theta_deg: float
    r0: float
    r1: float
    z0: float
    z1: float


def rail_section(rails_ring, theta_deg: float, side: int) -> RailSection | None:
    """The upper rail of a placed head (its rails, ring frame) in the radial plane at `theta_deg`,
    on side +1 (+Z) or -1: the outermost piece of the section there."""
    import numpy as np
    t = math.radians(theta_deg)
    normal = [-math.sin(t), math.cos(t), 0.0]
    sec = rails_ring.section(plane_origin=[0.0, 0.0, 0.0], plane_normal=normal)
    if sec is None:
        return None
    best = None
    u = np.array([math.cos(t), math.sin(t), 0.0])
    for poly in sec.discrete:
        p = np.asarray(poly)
        r = p @ u
        if r.mean() <= 0:                                            # the far half of the plane
            continue
        z = p[:, 2]
        if side * z.mean() <= 0:
            continue
        cand = RailSection(theta_deg, float(r.min()), float(r.max()), float(z.min()), float(z.max()))
        if best is None or cand.r1 > best.r1 + 1e-6 or (abs(cand.r1 - best.r1) <= 1e-6 and side * cand.z0 > side * best.z0):
            best = cand
    return best


def bridge_rail(sections: list[RailSection], corner: float):
    """One side's bridge rail through the stones' rail sections (in order of angle)."""
    import numpy as np
    sections = sorted(sections, key=lambda s: s.theta_deg)
    t0, t1 = sections[0].theta_deg, sections[-1].theta_deg
    n = max(2, int(math.ceil((t1 - t0) / STATION_DEG)) + 1)
    thetas = np.linspace(t0, t1, n)
    ts = [s.theta_deg for s in sections]
    stations = []
    for th in thetas:
        r0, r1, z0, z1 = (float(np.interp(th, ts, [getattr(s, f) for s in sections])) for f in ("r0", "r1", "z0", "z1"))
        stations.append((float(th), rounded_rect(r0, r1, z0, z1, corner)))
    return loft_around_axis(stations)


# ---- shared prongs -------------------------------------------------------------------------------
@dataclass
class Post:
    """A shared prong between stones a and b (indices into the spec's stones()), on side +1 / -1."""
    a: int
    b: int
    side: int
    theta_deg: float
    z: float
    rho: float
    r_foot: float
    r_tip: float

    def axis(self):
        import numpy as np
        t = math.radians(self.theta_deg)
        u = np.array([math.cos(t), math.sin(t), 0.0])
        return u * self.r_foot + [0, 0, self.z], u * self.r_tip + [0, 0, self.z]

    def mesh(self):
        import trimesh
        foot, tip = self.axis()
        parts = [trimesh.creation.cylinder(radius=self.rho, segment=[foot, tip], sections=64)]
        for c in (foot, tip):
            ball = trimesh.creation.icosphere(subdivisions=4, radius=self.rho)
            ball.apply_translation(c)
            parts.append(ball)
        return geom.clean(trimesh.boolean.union(parts, engine="manifold"))

    def design(self) -> dict:
        return {k: round(float(getattr(self, k)), 4) if isinstance(getattr(self, k), float) else getattr(self, k)
                for k in ("a", "b", "side", "theta_deg", "z", "rho", "r_foot", "r_tip")}


def radial_point_at_head_z(M, theta_deg: float, z_axial: float, z_head: float):
    """The point of the radial line (angle theta, axial z) whose head-frame z (head -> ring matrix M)
    is z_head, in the head frame; None if the line runs parallel to that plane."""
    import numpy as np
    t = math.radians(theta_deg)
    Minv = np.linalg.inv(M)
    p0 = Minv @ np.array([0.0, 0.0, z_axial, 1.0])
    du = Minv[:3, :3] @ np.array([math.cos(t), math.sin(t), 0.0])
    if abs(du[2]) < 1e-9:
        return None
    s = (z_head - p0[2]) / du[2]
    return p0[:3] + s * du, s


def outline_distance(poly, x: float, y: float) -> float:
    """Signed distance from (x, y) to the outline: + outside, - inside."""
    from shapely.geometry import Point
    pt = Point(x, y)
    d = poly.exterior.distance(pt)
    return -d if poly.contains(pt) else d


def solve_post(frames, outlines, girdles, d: float, theta0: float, z0: float) -> tuple[float, float]:
    """(theta, z) of the radial line whose points at both stones' girdle undersides stand `d`
    outside both outlines. frames: the two head -> ring matrices; outlines: shapely polygons (head
    frame); girdles: the two girdle thicknesses."""
    from scipy.optimize import least_squares

    def f(x):
        out = []
        for M, poly, g in zip(frames, outlines, girdles):
            q = radial_point_at_head_z(M, x[0], x[1], -g / 2)
            out.append(1e3 if q is None else outline_distance(poly, q[0][0], q[0][1]) - d)
        return out
    sol = least_squares(f, [theta0, z0], bounds=([theta0 - 30.0, z0 - 6.0], [theta0 + 30.0, z0 + 6.0]),
                        xtol=1e-12, ftol=1e-12, gtol=1e-12, diff_step=1e-6)
    if max(abs(v) for v in f(sol.x)) > 1e-4:
        raise ValueError("no post position stands the ledge outside both girdles")
    return float(sol.x[0]), float(sol.x[1])


def post_tip_left(post: Post, cutters, plane_r: float) -> float:
    """The diameter of the largest circle inside what both seats leave of the post at radius
    `plane_r` (the plane square to the post's axis): what holds the prong-tip floor above the girdles."""
    import trimesh
    m = trimesh.boolean.difference([post.mesh(), *cutters], engine="manifold")
    return section_inscribed_dia(m, post.theta_deg, post.z, plane_r)


def section_inscribed_dia(mesh, theta_deg: float, z: float, plane_r: float, near: float = 1.2) -> float:
    """The largest inscribed circle's diameter of the piece of `mesh`'s section by the plane square
    to the radial direction at `theta_deg`, `plane_r` from the axis, near (theta, z) - by bisection on
    a negative buffer. 0 when nothing is there."""
    import numpy as np
    from shapely.geometry import Point, Polygon
    t = math.radians(theta_deg)
    u = np.array([math.cos(t), math.sin(t), 0.0])
    sec = mesh.section(plane_origin=u * plane_r, plane_normal=u)
    if sec is None:
        return 0.0
    tang = np.array([-math.sin(t), math.cos(t), 0.0])
    here = Point(0.0, z).buffer(near)
    best = 0.0
    for loop in sec.discrete:
        p = np.asarray(loop)
        poly = Polygon(np.column_stack([p @ tang, p[:, 2]])).buffer(0)
        piece = poly.intersection(here)
        if piece.is_empty:
            continue
        lo, hi = 0.0, 2.0
        for _ in range(24):
            mid = (lo + hi) / 2
            if piece.buffer(-mid / 2).is_empty:
                hi = mid
            else:
                lo = mid
        best = max(best, lo)
    return best
