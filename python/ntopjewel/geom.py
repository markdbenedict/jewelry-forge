"""Independent geometry: the same parts the notebooks build, rebuilt from the notebooks' own input
numbers with shapely, trimesh and manifold3d. The gate checks nTop's results against these
(design volume, extents), and the simulated nTop in the tests returns them.
"""
from __future__ import annotations

import math


def open_polygon(sec, e: float, chamfer_mm: float = 0.0):
    """The morphological opening of a section by e in 2-D (buffer -e, +e): every convex corner
    sharper than e rounded, nothing else moved. With `chamfer_mm`, what nTop's opening makes of
    it: between its offsets the body is re-distanced through a mesh (nb_jewel.add_opening) whose
    mesher chamfers the eroded body's sharp convex corners by about a voxel
    (tables.opening_chamfer_mm), so the round comes out a little fuller - emulated by an opening
    of that size with bevelled joins on the eroded polygon."""
    if e <= 0:
        return sec
    eroded = sec.buffer(-e, quad_segs=16)
    if chamfer_mm > 0:
        eroded = eroded.buffer(-chamfer_mm, join_style="mitre").buffer(chamfer_mm, join_style="bevel")
    return eroded.buffer(e, quad_segs=16)


def section_polygon(v: dict, shape: str = "design", chamfer_mm: float = 0.0):
    """The meridian section as a shapely polygon in (r, z), built the way the notebook builds
    it: band ∩ dome torus ∩ comfort torus, then the opening by the edge round (open_polygon;
    `chamfer_mm` > 0 emulates nTop's re-distanced opening - the design models pass
    tables.opening_chamfer_mm(Mesh Tolerance), the shank's bar stays exact)."""
    from shapely.geometry import Point, box
    ro, ri = float(v["Outer Radius"]), float(v["Bore Radius"])
    if "Width" in v:                                            # the Phase 0 hello band: z = 0 .. W
        zb, zt = 0.0, float(v["Width"])
    else:
        zt, zb = float(v["Z Top"]), float(v["Z Bottom"])
    sec = box(ri, zb, ro, zt)
    if shape == "annulus" or "Dome Ring Radius" not in v:
        return sec
    dome = Point(float(v["Dome Ring Radius"]), 0.0).buffer(float(v["Dome Tube Radius"]), quad_segs=128)
    comfort = Point(float(v["Comfort Ring Radius"]), 0.0).buffer(float(v["Comfort Tube Radius"]), quad_segs=128)
    sec = sec.intersection(dome).intersection(comfort)
    return open_polygon(sec, float(v.get("Edge Round", 0.0)), chamfer_mm)


SHARP_EDGE_DEG = 30.0       # a convex edge whose faces turn more than this is one an opening rounds


def sharp_edge_round_mm3(mesh, e: float, min_deg: float = SHARP_EDGE_DEG) -> float:
    """What an opening by e takes off a mesh's sharp convex edges: a ball of radius e rolled along
    an edge whose faces turn by δ removes e² (tan(δ/2) - δ/2) per unit length; edges turning less
    than `min_deg` (a round sampled in small steps) do not count."""
    import numpy as np
    if e <= 0:
        return 0.0
    ang = mesh.face_adjacency_angles
    sharp = mesh.face_adjacency_convex & (ang > math.radians(min_deg))
    if not sharp.any():
        return 0.0
    edges = mesh.face_adjacency_edges[sharp]
    length = np.linalg.norm(mesh.vertices[edges[:, 0]] - mesh.vertices[edges[:, 1]], axis=1)
    d = ang[sharp]
    return float((e * e * (np.tan(d / 2) - d / 2) * length).sum())


def polygon_revolved_volume(sec) -> float:
    """Pappus for a shapely polygon in (r, z) revolved about the z axis: V = 2π ∫∫ r dA, the
    polygon's first moment about the axis, exactly (holes subtracted)."""
    import numpy as np

    def moment(coords):
        xy = np.asarray(coords, float)
        x, y = xy[:, 0], xy[:, 1]
        cross = x[:-1] * y[1:] - x[1:] * y[:-1]
        return abs(((x[:-1] + x[1:]) * cross).sum() / 6.0)

    polys = list(sec.geoms) if hasattr(sec, "geoms") else [sec]
    total = 0.0
    for poly in polys:
        total += moment(poly.exterior.coords) - sum(moment(h.coords) for h in poly.interiors)
    return float(2 * math.pi * total)


def revolve_section(sec, sections: int = 180):
    """Surface of revolution of the section about the ring axis, which is Z (nTop convention)."""
    import numpy as np
    import trimesh
    xy = np.asarray(sec.exterior.coords, dtype=float)
    if not np.isclose(xy[0], xy[-1]).all():
        xy = np.vstack([xy, xy[:1]])                 # closed profile -> closed surface
    # trimesh revolves a 2-D profile (x = radius, y = height) about its Y axis and returns the
    # solid with that axis along 3-D Z; the profile must not touch the axis (a ring never does)
    mesh = trimesh.creation.revolve(xy, sections=sections)
    if mesh.volume < 0:
        mesh.invert()
    mesh.merge_vertices()
    return mesh


def band_mesh(v: dict, shape: str = "design", chamfer_mm: float | None = None):
    """The profiled band from ring_band_profile's inputs, as nTop builds it: its opening
    re-distanced, so the rounds carry the mesher's chamfer (tables.opening_chamfer_mm of the
    inputs' Mesh Tolerance unless `chamfer_mm` is given)."""
    from . import tables
    if chamfer_mm is None:
        chamfer_mm = tables.opening_chamfer_mm(float(v.get("Mesh Tolerance", 0.1)))
    return revolve_section(section_polygon(v, shape, chamfer_mm))


DRILL_MIN_MM3 = 1e-3


def drill_of(mesh):
    """(radius, z_top) of a pearl's drill - an axial hole up the Z axis from below, all the convex
    body lacks (the seat envelope of a pearl on a post, gems.seat_envelope) - or None for a convex
    body. Read off the mesh, so a seat that comes back from STL (the simulated nTop) is known too."""
    import numpy as np
    import trimesh
    if mesh.is_convex:
        return None
    hull = mesh.convex_hull
    if hull.volume - mesh.volume < DRILL_MIN_MM3:
        return None
    d = trimesh.proximity.signed_distance(hull, mesh.vertices)          # > 0 inside the hull
    inner = mesh.vertices[d > 1e-5]
    if not len(inner):
        return None
    r = float(np.median(np.hypot(inner[:, 0], inner[:, 1])))
    return r, float(inner[:, 2].max())


def offset_convex(mesh, c: float):
    """Offset Body of a convex body by c > 0: the hull of its vertices each grown into a small
    sphere (exact up to the sphere's facetting). A pearl's seat (a convex body with an axial drill
    up into it, drill_of) offsets to the hull's offset less the drill shrunk by c - the post the
    drill holds survives the seat's cut, as it does under nTop's exact offset."""
    import trimesh
    if c <= 0:
        return mesh
    drill = drill_of(mesh)
    base = mesh.convex_hull if drill else mesh
    ball = trimesh.creation.icosphere(subdivisions=3, radius=c).vertices
    pts = (base.vertices[:, None, :] + ball[None, :, :]).reshape(-1, 3)
    out = trimesh.convex.convex_hull(pts)
    if drill and drill[0] > c:
        r, top = drill
        z0 = float(base.bounds[0][2]) - c - 1.0
        hole = trimesh.creation.cylinder(radius=r - c, segment=[[0, 0, z0], [0, 0, top - c]], sections=64)
        out = trimesh.boolean.difference([out, hole], engine="manifold")
    return out


def rotation_about_y(angle_deg: float, pivot) -> "numpy.ndarray":
    """4x4: rotation by angle_deg about the line through `pivot` parallel to +Y (right-handed)."""
    import numpy as np
    import trimesh
    return trimesh.transformations.rotation_matrix(math.radians(angle_deg), [0, 1, 0], point=np.asarray(pivot, float))


def clean(mesh, tolerance_mm: float = 1e-4):
    """A boolean result that survives being written as STL: manifold3d merges features closer
    than `tolerance_mm` (STL stores float32; slivers from many booleans otherwise collapse on
    reload into open edges - seen on the solitaire, 2026-10-28). Volume changes by < 0.01 %."""
    import numpy as np
    import manifold3d as mf
    import trimesh
    m = mf.Manifold(mf.Mesh(vert_properties=np.asarray(mesh.vertices, np.float32),
                            tri_verts=np.asarray(mesh.faces, np.uint32))).set_tolerance(tolerance_mm)
    out = m.to_mesh()
    return trimesh.Trimesh(np.asarray(out.vert_properties[:, :3], float), np.asarray(out.tri_verts), process=True)


def collapse_short_edges(mesh, min_length_mm: float = 5e-5, passes: int = 8):
    """The mesh with every edge shorter than `min_length_mm` collapsed into one of its ends (the
    other end's faces re-pointed, the two faces on the edge dropped). manifold3d's booleans
    leave a few micron-short edges where an intersection curve passes a vertex; its own
    simplification keeps them (they sit on curved features), and nTop's importer merges "very
    close vertices" on its own terms - after which it called the trinity shank's bar
    self-intersecting and built it in five shells (2026-11-01). An edge whose ends share more
    than two neighbours is left alone (collapsing it would fold the surface); the result must
    stay watertight, else the input comes back unchanged."""
    import numpy as np
    import trimesh
    V, F = np.array(mesh.vertices, float), np.array(mesh.faces, int)
    for _ in range(passes):
        edges = np.sort(F[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2), axis=1)
        edges = np.unique(edges, axis=0)
        length = np.linalg.norm(V[edges[:, 0]] - V[edges[:, 1]], axis=1)
        short = edges[length < min_length_mm]
        if len(short) == 0:
            break
        neigh = [set() for _ in range(len(V))]
        for a, b in edges:
            neigh[a].add(b)
            neigh[b].add(a)
        remap = np.arange(len(V))
        touched = set()
        for a, b in short:
            if a in touched or b in touched or len(neigh[a] & neigh[b]) > 2:
                continue
            remap[b] = a
            touched.update((a, b))
        if not touched:
            break
        F = remap[F]
        F = F[(F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 2] != F[:, 0])]
        F = np.unique(F, axis=0) if len(F) != len(np.unique(np.sort(F, axis=1), axis=0)) else F
    out = trimesh.Trimesh(V, F, process=False)
    out.remove_unreferenced_vertices()
    if not out.is_watertight or out.body_count != mesh.body_count:
        return mesh
    return out


def intersecting_faces(mesh, cell_mm: float = 0.3, eps: float = 1e-9, as_written: bool = True, region=None, chunk: int = 200000):
    """Pairs of the mesh's faces that intersect without sharing a vertex ((n, 2) face indices):
    the exact separating-axis test over every pair whose boxes overlap (a uniform grid of
    `cell_mm` cells finds them), coplanar pairs included. `as_written`: test the vertices as an
    STL holds them (float32), which is what nTop reads - a mesh union of crossing bodies leaves
    faces micrometres apart along its seams, and those rounded into intersections (the trinity
    bar, 2026-11-02: 16 pairs in float32, none in float64). `region(centres) -> mask` restricts
    the faces considered (both faces of a pair must lie in it). Empty for a mesh nTop can import;
    about a minute per million faces."""
    import numpy as np
    V = np.asarray(mesh.vertices, float)
    if as_written:
        V = V.astype(np.float32).astype(np.float64)
    F = np.asarray(mesh.faces, int)
    keep = np.arange(len(F)) if region is None else np.flatnonzero(region(V[F].mean(axis=1)))
    F = F[keep]
    tri = V[F]
    lo, hi = tri.min(axis=1), tri.max(axis=1)
    origin = lo.min(axis=0)
    c0 = np.floor((lo - origin) / cell_mm).astype(np.int64)
    c1 = np.floor((hi - origin) / cell_mm).astype(np.int64)
    n_cells = (c1 - c0 + 1).prod(axis=1)
    face_of = np.repeat(np.arange(len(F)), n_cells)
    local = np.arange(len(face_of)) - np.repeat(np.cumsum(n_cells) - n_cells, n_cells)
    span = (c1 - c0 + 1)[face_of]
    ix = c0[face_of, 0] + local % span[:, 0]
    iy = c0[face_of, 1] + (local // span[:, 0]) % span[:, 1]
    iz = c0[face_of, 2] + local // (span[:, 0] * span[:, 1])
    ny, nz = int(c1[:, 1].max()) + 2, int(c1[:, 2].max()) + 2
    cell = (ix * ny + iy) * nz + iz
    order = np.argsort(cell, kind="stable")
    cell, face_of = cell[order], face_of[order]
    starts = np.flatnonzero(np.r_[True, cell[1:] != cell[:-1]])
    counts = np.diff(np.r_[starts, len(cell)])

    def intersect(p):
        """The separating-axis test over the pairs p ((m, 2)): True where the two overlap."""
        A, B = tri[p[:, 0]], tri[p[:, 1]]
        ea = np.stack([A[:, 1] - A[:, 0], A[:, 2] - A[:, 1], A[:, 0] - A[:, 2]], axis=1)
        eb = np.stack([B[:, 1] - B[:, 0], B[:, 2] - B[:, 1], B[:, 0] - B[:, 2]], axis=1)
        na, nb = np.cross(ea[:, 0], ea[:, 1]), np.cross(eb[:, 0], eb[:, 1])
        axes = ([na, nb] + [np.cross(ea[:, i], eb[:, j]) for i in range(3) for j in range(3)]
                + [np.cross(na, ea[:, i]) for i in range(3)] + [np.cross(nb, eb[:, j]) for j in range(3)])   # the last six: coplanar pairs
        separated = np.zeros(len(p), bool)
        for ax in axes:
            n = np.linalg.norm(ax, axis=1)
            good = n > 1e-14
            axn = ax / np.where(good, n, 1.0)[:, None]
            pa, pb = np.einsum("mij,mj->mi", A, axn), np.einsum("mij,mj->mi", B, axn)
            separated |= good & ((pa.max(axis=1) < pb.min(axis=1) - eps) | (pb.max(axis=1) < pa.min(axis=1) - eps))
        return ~separated

    hits = []
    for size in np.unique(counts[counts > 1]):
        heads = starts[counts == size]
        i, j = np.triu_indices(size, 1)
        per_group = len(i)
        step = max(1, chunk // per_group)                                   # groups per batch: memory stays bounded
        for s in range(0, len(heads), step):
            members = face_of[heads[s:s + step, None] + np.arange(size)[None, :]]   # (groups, size)
            P = np.column_stack([members[:, i].ravel(), members[:, j].ravel()])
            P = np.sort(P, axis=1)
            a, b = P[:, 0], P[:, 1]
            P = P[(lo[a] <= hi[b]).all(axis=1) & (lo[b] <= hi[a]).all(axis=1)]
            if len(P) == 0:
                continue
            fa, fb = F[P[:, 0]], F[P[:, 1]]
            P = P[~(fa[:, :, None] == fb[:, None, :]).any(axis=(1, 2))]    # neighbours touch by right
            if len(P):
                hits.append(P[intersect(P)])
    if not hits:
        return np.zeros((0, 2), int)
    return keep[np.unique(np.vstack(hits), axis=0)]


def remap_cylindrical(mesh, wrap_length: float):
    """nTop's Remap Cylindrical Body on a mesh: X -> radius, Y -> angle (Y = wrap length is one
    turn), Z unchanged. Vertex-wise; an engraving's facets are far smaller than the radius."""
    import numpy as np
    v = mesh.vertices.copy()
    theta = 2 * math.pi * v[:, 1] / wrap_length
    out = mesh.copy()
    out.vertices = np.column_stack([v[:, 0] * np.cos(theta), v[:, 0] * np.sin(theta), v[:, 2]])
    if out.volume < 0:
        out.invert()
    return out


def _manifold(mesh):
    import numpy as np
    import manifold3d as mf
    return mf.Manifold(mf.Mesh(vert_properties=np.asarray(mesh.vertices, np.float32), tri_verts=np.asarray(mesh.faces, np.uint32)))


def junction_edges(a, b, op: str = "union"):
    """The curves where the surfaces of a and b meet in a ∪ b (or a ∩ b): the edges of the result
    whose two faces came from different inputs (manifold3d keeps each face's origin). Returns
    (result manifold, edges (N, 2) vertex ids, vertices, n_a (N, 3), n_b (N, 3)) with the outward
    normal of the a-face and the b-face at each edge. A blended union fills these concave corners;
    a blended intersection rounds these convex edges away."""
    import numpy as np
    ma, mb = _manifold(a).as_original(), _manifold(b).as_original()
    ida = ma.original_id()
    u = ma + mb if op == "union" else ma ^ mb
    g = u.to_mesh()
    tris = np.asarray(g.tri_verts).reshape(-1, 3)
    verts = np.asarray(g.vert_properties)[:, :3]
    runs, ids = np.asarray(g.run_index), np.asarray(g.run_original_id)
    src = np.empty(len(tris), dtype=int)
    for k in range(len(ids)):
        src[runs[k] // 3: runs[k + 1] // 3] = ids[k]
    e = np.vstack([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
    e.sort(axis=1)
    owner = np.tile(src, 3)
    tri_of = np.tile(np.arange(len(tris)), 3)
    order = np.lexsort((e[:, 1], e[:, 0]))
    e, owner, tri_of = e[order], owner[order], tri_of[order]
    same = (e[1:] == e[:-1]).all(axis=1)
    cross = same & (owner[1:] != owner[:-1])
    idx = np.nonzero(cross)[0]
    if not len(idx):
        z = np.zeros((0, 3))
        return u, np.zeros((0, 2), dtype=int), verts, z, z
    p = verts[tris]
    normals = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    normals /= np.maximum(np.linalg.norm(normals, axis=1), 1e-12)[:, None]
    t0, t1 = tri_of[idx], tri_of[idx + 1]
    first_is_a = (owner[idx] == ida)[:, None]
    na = np.where(first_is_a, normals[t0], normals[t1])
    nb = np.where(first_is_a, normals[t1], normals[t0])
    return u, e[idx], verts, na, nb


def junction_segments(a, b, op: str = "union"):
    """The meeting curves of a and b (see junction_edges) as an (N, 2, 3) array of segment end points."""
    import numpy as np
    _, edges, verts, _, _ = junction_edges(a, b, op)
    return np.stack([verts[edges[:, 0]], verts[edges[:, 1]]], axis=1) if len(edges) else np.zeros((0, 2, 3))


def segments_length(segs) -> float:
    import numpy as np
    return float(np.linalg.norm(segs[:, 1] - segs[:, 0], axis=1).sum()) if len(segs) else 0.0


def junction_length(a, b, op: str = "union") -> float:
    """Length (mm) of the meeting curves of a and b (see junction_segments)."""
    return segments_length(junction_segments(a, b, op))


def transform_segments(segs, matrix):
    import numpy as np
    pts = segs.reshape(-1, 3)
    out = (matrix[:3, :3] @ pts.T).T + matrix[:3, 3]
    return out.reshape(segs.shape)


def exposed_segments(segs, *inside_of):
    """Keep the segments whose mid points lie outside every mesh in `inside_of`: a junction buried
    in other metal is not blended, and one inside a later cut is cut away."""
    import numpy as np
    if not len(segs):
        return segs
    keep = np.ones(len(segs), dtype=bool)
    mid = segs.mean(axis=1)
    for m in inside_of:
        keep &= ~m.contains(mid)
    return segs[keep]


def blend_volume_mm3(radius_mm: float, junction_mm: float) -> float:
    """What a blended union of the given radius adds along that much junction (tables' factor);
    a blended intersection removes the same along its edges, so pass that length negative."""
    from . import tables
    return tables.SETTINGS["blend_volume_factor"] * radius_mm ** 2 * junction_mm


# ---- the boolean operations the independent model is built with ---------------------------------
class Booleans:
    """Sharp union / intersection / difference (trimesh + manifold3d). The builders in heads and
    solitaire take one of these so that the simulated nTop in the tests can substitute blended
    operations; the blend radii are passed through and ignored here, because the independent
    model stays unblended and estimates the blends by volume (blend_volume_mm3)."""

    def union(self, parts, blend_mm: float = 0.0):
        import trimesh
        parts = [m for m in parts if m is not None]
        return parts[0] if len(parts) == 1 else trimesh.boolean.union(parts, engine="manifold")

    def intersect(self, a, b, blend_mm: float = 0.0):
        import trimesh
        return trimesh.boolean.intersection([a, b], engine="manifold")

    def difference(self, body, cuts):
        import trimesh
        cuts = [m for m in cuts if m is not None]
        return body if not cuts else trimesh.boolean.difference([body, *cuts], engine="manifold")

    def clean(self, mesh):
        """The finished body, fit to be written as STL (see clean)."""
        return clean(mesh)


SHARP = Booleans()
