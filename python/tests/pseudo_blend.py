"""Blended booleans for the simulated nTop (tests/fake_ntopcl.py): a crude geometric stand-in for
nTop's smooth union / intersection, so the fake's STL and volume carry what a blend adds.

nTop's blend is an implicit operation; what the tables know about it is its volume:
`blend_volume_factor` x radius² per mm of junction, filled along a union's concave junction,
removed along an intersection's convex edges (calibrated 2026-10-30 against nTop 6.3.3). The
fake reproduces that volume with geometry: along every junction loop of the sharp result it
lays convex pieces whose cross-section is the corner {0 < u < s, 0 < v < s} between the two
faces (u, v the distances outside the a-face and the b-face), united for a union, cut off for
an intersection, with s chosen so the cross-sections add up to the tables' volume where the
faces meet squarely (a slim crease gets less: see _sections). It is a square-cornered fill, not
nTop's smooth one, and planes stand in for curved faces (a union is scaled by UNION_SCALE for
that: measured on the round and pear heads, 2026-10-30), but the gate sees a one-shell
watertight mesh whose volume is within a percent of what nTop reports, and the design-volume
check faces the geometry it faces from nTop.

What it took to make manifold3d's results survive the STL round trip (an STL has no
connectivity; the loader joins vertices by position): the junction loops are resampled (the
boolean leaves coincident vertices along a junction; two cross-sections at one point kiss),
consecutive pieces overlap by a whole segment (pieces that merely touch leave kissing sheets),
zero-volume shells are dropped, and the coincident vertices a boolean leaves on sheets that
touch are nudged apart by a few nanometres along their own normals, so the loader keeps them
apart and the result keeps the topology manifold3d gave it. Pushing the mesh's own vertices
instead (no new booleans) was tried first and folded the primitives' long thin triangles.
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np

from ntopjewel import geom, tables

UNION_SCALE = 0.88          # the planar corner over-fills a curved crease by about this much
EPS_MM = 0.01               # the pieces sink this far into the body: no coplanar faces in the boolean
MIN_STEP_MM = 0.04          # loop vertices closer than this share a cross-section
NUDGE_MM = 2e-5             # coincident vertices are set this far apart (float32 resolves 5e-7 at 8 mm)
MAX_EXTENT = 1.5            # a section's corners reach at most this many radii along either face
MIN_ANGLE_DEG = 30.0        # faces meeting more nearly parallel than this get no piece


def _trimesh(man, tolerance_mm: float = 1e-5):
    """A boolean result as a trimesh that survives the STL round trip: manifold3d's own
    simplification at `tolerance_mm` first (as geom.clean does, but at 10 nm: at 100 nm it
    turned a sliver under a prong into a fin the ledge count saw, 2026-10-30), its zero-volume
    shells dropped, then any vertices still sharing a position (a needle's two ends, two sheets
    touching, a fold) moved apart: the first of a group by NUDGE_MM along its normal, the next
    against its own normal, each with a small tangential part of its own, so the loader keeps
    them distinct (float32 resolves 5e-7 mm at 8 mm) and the result keeps the topology
    manifold3d gave it."""
    import trimesh
    from scipy.spatial import cKDTree
    g = _solid(man.set_tolerance(tolerance_mm)).to_mesh()          # the simplification can leave a speck
    mesh = trimesh.Trimesh(np.asarray(g.vert_properties)[:, :3], np.asarray(g.tri_verts).reshape(-1, 3), process=False)
    pairs = cKDTree(mesh.vertices).query_pairs(NUDGE_MM / 4)
    if not pairs:
        return mesh
    groups = defaultdict(list)                                  # representative -> members (union-find lite)
    rep = {}
    for a, b in sorted(pairs):
        ra, rb = rep.get(a, a), rep.get(b, b)
        r = min(ra, rb)
        for m in set(groups.pop(ra, [ra]) + groups.pop(rb, [rb])):
            rep[m] = r
            groups[r].append(m)
    normals = np.asarray(mesh.vertex_normals, float)
    moved = np.asarray(mesh.vertices, float).copy()
    for members in groups.values():
        for j, m in enumerate(sorted(set(members))):
            n = normals[m]
            axis = np.zeros(3)
            axis[np.argmin(np.abs(n))] = 1.0
            t = np.cross(n, axis)
            t /= max(np.linalg.norm(t), 1e-12)
            moved[m] += NUDGE_MM * ((1.0 if j % 2 == 0 else -1.0) * n + 0.5 * j * t)
    return trimesh.Trimesh(moved, np.asarray(mesh.faces).copy(), process=False)


def _solid(man, min_volume: float = 1e-6):
    """Drop the zero-volume shells a boolean with near-coplanar faces can leave behind."""
    import manifold3d as mf
    parts = [p for p in man.decompose() if p.volume() > min_volume]
    if len(parts) == 1:
        return parts[0]
    return mf.Manifold.compose(parts) if parts else man


def _loops(edges):
    """Chain edges (N, 2 vertex ids) into closed loops: (vertex ids, edge ids) each. The meeting
    curves of two closed surfaces are loops; a vertex of degree != 2 ends its chain, which is
    dropped."""
    adj = defaultdict(list)
    for k, (i, j) in enumerate(edges):
        adj[i].append((j, k))
        adj[j].append((i, k))
    used = np.zeros(len(edges), dtype=bool)
    loops = []
    for start in adj:
        if len(adj[start]) != 2:
            continue
        for nxt, k0 in adj[start]:
            if used[k0]:
                continue
            loop, ek = [start], [k0]
            used[k0] = True
            cur, ok = nxt, True
            while cur != start:
                if len(adj[cur]) != 2:
                    ok = False
                    break
                loop.append(cur)
                (c1, k1), (c2, k2) = adj[cur]
                nxt_v, nxt_k = (c2, k2) if k1 == ek[-1] else (c1, k1)
                if used[nxt_k]:
                    ok = False
                    break
                used[nxt_k] = True
                ek.append(nxt_k)
                cur = nxt_v
            if ok and len(loop) >= 3:
                loops.append((np.asarray(loop), np.asarray(ek)))
            break
    return loops


def _sections(edges, verts, na, nb, area_mm2, corners_uv, max_extent):
    """Per junction loop: the cross-section corners (m, k, 3) at each kept loop vertex, the
    polygon `corners_uv(s)` (a list of (u, v) points) in the frame u = (p - e)·n_a,
    v = (p - e)·n_b of the two faces' mean normals over the edges between the neighbouring kept
    vertices, with s such that the section's area is `area_mm2` (= s² / sin θ for faces whose
    normals differ by θ, when the polygon's area in (u, v) is s²). Kept vertices are at least
    MIN_STEP_MM apart along the loop."""
    out = []
    for vids, eids in _loops(edges):
        pts = verts[vids]
        step = np.linalg.norm(pts - np.roll(pts, 1, axis=0), axis=1)         # step[k]: from vertex k-1 to k
        keep, run = [0], 0.0
        for k in range(1, len(vids)):
            run += step[k]
            if run >= MIN_STEP_MM:
                keep.append(k)
                run = 0.0
        if run + step[0] < MIN_STEP_MM and len(keep) > 1:                     # the last one crowds the first
            keep.pop()
        if len(keep) < 3:
            continue
        keep = np.asarray(keep)
        m, n = len(keep), len(vids)
        va, vb = np.zeros((m, 3)), np.zeros((m, 3))
        for i in range(m):                     # edge k enters vertex k: the edges from kept i-1 to kept i+1
            lo_k = keep[i - 1] if i else keep[-1] - n
            hi_k = keep[i + 1] if i + 1 < m else keep[0] + n
            es = eids[np.arange(lo_k + 1, hi_k + 1) % n]
            va[i], vb[i] = na[es].sum(axis=0), nb[es].sum(axis=0)
        va /= np.maximum(np.linalg.norm(va, axis=1), 1e-12)[:, None]
        vb /= np.maximum(np.linalg.norm(vb, axis=1), 1e-12)[:, None]
        c = np.clip(np.einsum("ij,ij->i", va, vb), -0.995, 0.995)
        sin = np.sqrt(1.0 - c * c)
        s = np.sqrt(area_mm2 * sin)                  # area s² in (u, v) is s² / sin θ on the ground
        # a slim crease (faces within MIN_ANGLE of parallel) gets no piece: its corner would run
        # along the surface instead of standing in a crease (into a ring's bore, 2026-10-30),
        # and a piece small enough not to becomes a speck in the STL
        slim = sin < np.sin(np.radians(MIN_ANGLE_DEG))
        s[slim] = 0.0
        d = 1.0 - c * c
        corners = []
        if slim.all():
            continue
        for u, v in corners_uv(s):
            al, be = (u - c * v) / d, (v - c * u) / d
            offset = al[:, None] * va + be[:, None] * vb
            # faces that are nearly parallel send the corners off along the surface (u ≈ v for
            # every point); the fill of a slim crease reaches about a blend radius, so shorten
            # such an offset to max_extent, keeping its direction
            far = np.linalg.norm(offset, axis=1)
            offset *= np.minimum(1.0, max_extent / np.maximum(far, 1e-12))[:, None]
            corners.append(pts[keep] + offset)
        out.append(np.stack(corners, axis=1))
    return out


def _fill_corners(s):
    """A union's fill: the square corner {0 < u < s, 0 < v < s}, sunk EPS_MM into the body."""
    return [(-EPS_MM, -EPS_MM), (s, -EPS_MM), (s, s), (-EPS_MM, s)]


def _round_corners(s):
    """An intersection's rounding: the square corner {-s < u < 0, -s < v < 0} cut off the edge."""
    return [(EPS_MM, EPS_MM), (-s, EPS_MM), (-s, -s), (EPS_MM, -s)]


def _pieces(edges, verts, na, nb, area_mm2, corners_uv, max_extent):
    """The fill along every junction loop as convex pieces: the hull of each run of three
    consecutive cross-sections (see _sections), so neighbours overlap by a whole segment."""
    import manifold3d as mf
    out = []
    for sec in _sections(edges, verts, na, nb, area_mm2, corners_uv, max_extent):
        m = len(sec)
        for k in range(m):
            pts = np.vstack([sec[k], sec[(k + 1) % m], sec[(k + 2) % m]]).astype(np.float64)
            if np.ptp(pts, axis=0).max() < 2 * EPS_MM:                    # a slim stretch: nothing to lay
                continue
            try:
                piece = mf.Manifold.hull_points(pts)
            except Exception:                                              # pragma: no cover - degenerate (flat) run
                continue
            if piece.status() == mf.Error.NoError and piece.volume() > 1e-12:
                out.append(piece)
    return out


class Blended(geom.Booleans):
    """geom.Booleans whose union and intersection carry the blend the radius asks for."""

    def __init__(self, factor: float | None = None):
        self.factor = tables.SETTINGS["blend_volume_factor"] if factor is None else float(factor)

    def union(self, parts, blend_mm: float = 0.0):
        import manifold3d as mf
        parts = [m for m in parts if m is not None]
        if blend_mm <= 0 or len(parts) != 2:
            return super().union(parts)
        u, edges, verts, na, nb = geom.junction_edges(parts[0], parts[1], "union")
        pieces = _pieces(edges, verts, na, nb, UNION_SCALE * self.factor * blend_mm ** 2, _fill_corners,
                         MAX_EXTENT * blend_mm) if len(edges) else []
        return _trimesh(_solid(mf.Manifold.batch_boolean([u, *pieces], mf.OpType.Add)) if pieces else u)

    def intersect(self, a, b, blend_mm: float = 0.0):
        import manifold3d as mf
        if blend_mm <= 0:
            return super().intersect(a, b)
        u, edges, verts, na, nb = geom.junction_edges(a, b, "intersect")
        pieces = _pieces(edges, verts, na, nb, self.factor * blend_mm ** 2, _round_corners,
                         MAX_EXTENT * blend_mm) if len(edges) else []
        return _trimesh(_solid(u - mf.Manifold.batch_boolean(pieces, mf.OpType.Add)) if pieces else u)

    def difference(self, body, cuts):
        import manifold3d as mf
        cuts = [m for m in cuts if m is not None]
        if not cuts:
            return body
        return _trimesh(_solid(geom._manifold(body) - mf.Manifold.batch_boolean([geom._manifold(c) for c in cuts], mf.OpType.Add)))

    def clean(self, mesh):
        """Already done: every result left _trimesh fit for the STL (geom.clean's merge of close
        vertices would put the nudged sheets back together)."""
        return mesh
