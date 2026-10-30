"""Independent geometry: the same parts the notebooks build, rebuilt from the notebooks' own input
numbers with shapely, trimesh and manifold3d. The gate checks nTop's results against these
(design volume, extents), and the simulated nTop in the tests returns them.
"""
from __future__ import annotations

import math


def section_polygon(v: dict, shape: str = "design"):
    """The meridian section as a shapely polygon in (r, z), built the way the notebook builds
    it: band ∩ dome torus ∩ comfort torus, then Offset -e / +e (an opening = buffer in 2-D)."""
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
    e = float(v.get("Edge Round", 0.0))
    if e > 0:
        sec = sec.buffer(-e, quad_segs=16).buffer(e, quad_segs=16)
    return sec


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


def band_mesh(v: dict, shape: str = "design"):
    """The profiled band from ring_band_profile's inputs."""
    return revolve_section(section_polygon(v, shape))


def offset_convex(mesh, c: float):
    """Offset Body of a convex body by c > 0: the hull of its vertices each grown into a small
    sphere (exact up to the sphere's facetting)."""
    import trimesh
    if c <= 0:
        return mesh
    ball = trimesh.creation.icosphere(subdivisions=3, radius=c).vertices
    pts = (mesh.vertices[:, None, :] + ball[None, :, :]).reshape(-1, 3)
    return trimesh.convex.convex_hull(pts)


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


def junction_length(a, b) -> float:
    """Length (mm) of the curves where the surfaces of a and b meet in a ∪ b: the edges of the
    union whose two faces came from different inputs (manifold3d keeps each face's origin). A
    blended union fills these corners, so this bounds the metal a blend adds."""
    import numpy as np
    u = _manifold(a).as_original() + _manifold(b).as_original()
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
    order = np.lexsort((e[:, 1], e[:, 0]))
    e, owner = e[order], owner[order]
    same = (e[1:] == e[:-1]).all(axis=1)
    cross = same & (owner[1:] != owner[:-1])
    seg = e[:-1][cross]
    return float(np.linalg.norm(verts[seg[:, 0]] - verts[seg[:, 1]], axis=1).sum())


def blend_volume_mm3(radius_mm: float, junction_mm: float) -> float:
    """What a blended union of the given radius adds along that much junction (tables' factor)."""
    from . import tables
    return tables.SETTINGS["blend_volume_factor"] * radius_mm ** 2 * junction_mm
