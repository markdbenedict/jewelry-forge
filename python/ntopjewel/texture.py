"""Surface textures on a band (5 Nov): the first is a hammered finish on a plain band.

A hammered face is the band's outer face struck again and again with a round-faced hammer: shallow
spherical dimples, overlapping into facets with sharp ridges between them, a polished rim left at
each edge. The hammer's face is one sphere (radius `sphere_radius`), so every dimple is that sphere
pressed in to its own depth (each strike a little harder or lighter, `depth_var`), its centre on the
face's normal. Where the dimples lie is a dart-throwing (Poisson-disk) layout on the developed face,
periodic round the ring, from a seed - so a design is reproducible and Python knows every dimple.

Why that matters for nTop: the union of equal spheres is {p : min_i |p - c_i| < R} - the distance to
the nearest of a set of points, less one radius. nTop can build that natively as a field, from the
centres alone (`write_centres`), and subtract it from the band; Python never sends a mesh of the
dimples. How the points reach nTop is settled by the discovery run (`api build discover`, its texture
keywords); this module is the design, the independent model and the gate, and none of it depends on
that choice - and nTop has it (points_probe, 2026-11-05): Import Points reads the CSV, one Sphere on the whole
list makes a sphere per point, `ring_texture.ntop` subtracts their union from the profiled band.

The independent model (`design_mesh`) is the band nTop builds (geom.band_mesh, its opening's chamfer
included) less the spheres, unioned by manifold3d. The gate (`check_texture`): the band checks, the
section shape at the gate's twelve angles against the design's own sections, the design volume (a
4 x 1.6 band loses about a tenth of its metal to the dimples - a missing texture fails it), and a
probe along every strike's normal comparing the built depth with the design's there.

Mesh density is the texture's real constraint: a dimple 0.15 mm deep wants a Mesh Tolerance near
0.05 (three voxels at least in its shallowest strike), and triangles grow with 1 / tolerance².
`triangles_estimate` (tables.mesh_triangles_estimate, calibrated on the partial-bezel ring) refuses a
design that would pass the gate's 5 M limit before anything runs.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import json
import time
from dataclasses import asdict

from . import band, catalog, config, gate, geom, ntopcl, runs, tables

KINDS = ("hammered",)
SPHERE_SUBDIV = 4               # icosphere level of a dimple's sphere: 0.15 mm facets, 1 µm sag at R 2.4
LAYOUT_TRIES = 4000             # darts rejected in a row that end the layout (it is then as full as it gets)
MAX_TRIANGLES = 5_000_000       # the gate's mesh density limit (gate.check)
DEPTH_VOXELS = 3.0              # the shallowest strike spans at least this many voxels (half the Mesh Tolerance each)
PROBE_TOL_MM = 0.02             # a probe's built depth within this of the design's, beyond half the Mesh Tolerance
FACE_STEP_DEG = 1.0             # a shank's face is tabulated every degree round the ring ...
FACE_STEP_Z = 0.02              # ... and every 0.02 mm across it
FAR_STRIKE = (1000.0, 0.0, 0.0) # the one centre an unhammered notebook gets: a sphere a metre off, cutting nothing


# ---- the hammer and the faces it strikes ------------------------------------------------------------
@dataclass
class Hammer:
    """One round hammer face struck again and again: the numbers that make a hammered finish, on any face
    (a plain band's: HammeredSpec; a shank's: ShankSpec.hammer; a solitaire's shank, clear of the head)."""
    dimple_mm: float = 1.6                  # a nominal strike's footprint diameter on the face
    depth_mm: float = 0.15                  # a nominal strike's depth along the face's normal
    depth_var: float = 0.25                 # each strike's depth varies by up to ± this fraction (seeded)
    spacing: float = 0.5                    # centres at least this many nominal diameters apart (0.5: nothing unstruck)
    rim_mm: float | None = None             # polished rim kept at each edge of the face; None = the edge round + 0.1
    seed: int = 1                           # the layout's and the strikes' random seed
    clear_deg: float = 0.0                  # no strike within this angle either side of the head (a solitaire's head, its arches)

    @property
    def sphere_radius(self) -> float:
        a, d = self.dimple_mm / 2, self.depth_mm
        return (a * a + d * d) / (2 * d)

    @property
    def depth_range(self) -> tuple[float, float]:
        return self.depth_mm * (1 - self.depth_var), self.depth_mm * (1 + self.depth_var)

    def footprint_mm(self, depth: float) -> float:
        R = self.sphere_radius
        return 2 * math.sqrt(max(2 * R * depth - depth * depth, 0.0))

    def depth_fitting(self, half_width: float) -> float:
        R, a = self.sphere_radius, min(max(half_width, 0.0), self.sphere_radius)
        return R - math.sqrt(R * R - a * a)

    def rim(self, edge_round: float) -> float:
        return float(self.rim_mm) if self.rim_mm is not None else edge_round + 0.1

    @property
    def floor_half(self) -> float:
        """Half the footprint of a strike at the depth floor: how far from a rim a centre may come."""
        return self.footprint_mm(tables.FLOORS["texture_depth"]) / 2

    def design(self) -> dict:
        d = {"texture": "hammered", "dimple": self.dimple_mm, "depth": self.depth_mm, "depth_var": self.depth_var,
             "spacing": self.spacing, "rim": self.rim_mm, "seed": int(self.seed), "sphere_subdiv": SPHERE_SUBDIV}
        if self.clear_deg:
            d["clear_deg"] = round(self.clear_deg, 3)
        return d

    def problems(self, light: float | None = None) -> list[str]:
        """The hammer's own floors (`light`: the lightest strike laid out, when known)."""
        p = []
        lo, _hi = self.depth_range
        floor = tables.FLOORS["texture_depth"]
        if not 0.0 <= self.depth_var <= 0.5:
            p.append(f"depth variation {self.depth_var:g}: 0..0.5 of the depth")
        if lo < floor - 1e-9:
            p.append(f"the lightest strike would be {lo:.3f} mm deep ({self.depth_mm:g} less {self.depth_var:.0%}); at least "
                     f"{floor:g} mm (a shallower dimple polishes flat): a deeper strike or less variation")
        stroke = 2 * tables.FLOORS["engrave_stroke"]
        if self.footprint_mm(lo) < stroke:
            p.append(f"the lightest strike's footprint would be {self.footprint_mm(lo):.2f} mm across; at least {stroke:g} "
                     f"(two engraving strokes: narrower fills in casting)")
        if self.depth_mm * 2 > self.dimple_mm:
            p.append(f"a {self.depth_mm:g} mm strike {self.dimple_mm:g} mm across is deeper than a hemisphere")
        if not 0.5 <= self.spacing <= 1.5:
            p.append(f"spacing {self.spacing:g} dimples: 0.5..1.5")
        if self.rim_mm is not None and self.rim_mm < 0:
            p.append("the rim is a width, at least 0")
        return p


class BandFace:
    """A plain band's outer face: one stretch across, -W/2 .. W/2, the same all round."""

    def __init__(self, b: band.BandSpec):
        self.band = b
        self.edge_round = b.edge_round

    @property
    def radius(self) -> float:
        return self.band.outer_radius_mm

    @property
    def length(self) -> float:
        return 2 * math.pi * self.radius

    def intervals(self, theta_deg: float) -> list[tuple[float, float]]:
        return [(-self.band.width_mm / 2, self.band.width_mm / 2)]

    def z_bounds(self) -> tuple[float, float]:
        return -self.band.width_mm / 2, self.band.width_mm / 2

    def point_normal(self, theta_deg, z):
        """Face points and outward unit normals (ring frame) at angles (deg) and heights."""
        import numpy as np
        theta = np.radians(np.asarray(theta_deg, float))
        z = np.asarray(z, float)
        r = np.array([self.band.outer_radius_at(float(q)) for q in np.atleast_1d(z)]).reshape(z.shape)
        if self.band.dome > band.MIN_SAGITTA:
            rd, td = self.band.dome_torus
            nr, nz = (r - rd) / td, z / td
        else:
            nr, nz = np.ones_like(r), np.zeros_like(z)
        c, s = np.cos(theta), np.sin(theta)
        return (np.column_stack([r * c, r * s, z]), np.column_stack([nr * c, nr * s, nz]))


class ShankFace:
    """A shaped shank's outer face, read off its designed sections (ShankSpec.section_shape, opened as the
    notebook opens the bars): tabulated every FACE_STEP_DEG round the ring and FACE_STEP_Z across, each
    angle's stretches of face (a split's two halves, a double band's two strands) and the outer radius over
    them. A taper, a dip, a split's slot - the face follows whatever the shank does."""

    def __init__(self, shank):
        import numpy as np
        from shapely.geometry import LineString
        self.shank = shank
        self.edge_round = shank.band.edge_round
        self.thetas = np.arange(0.0, 360.0, FACE_STEP_DEG)
        secs = [shank.section_shape(float(t), skip=False, chamfer_mm=shank.opening_chamfer_mm) for t in self.thetas]
        lo = min(g.bounds[1] for g in secs)
        hi = max(g.bounds[3] for g in secs)
        self.zs = np.arange(lo - FACE_STEP_Z, hi + 2 * FACE_STEP_Z, FACE_STEP_Z)
        rmax = max(g.bounds[2] for g in secs) + 1.0
        rmin = min(g.bounds[0] for g in secs) - 1.0
        self.r = np.full((len(self.thetas), len(self.zs)), np.nan)
        self._intervals = []
        for i, g in enumerate(secs):
            parts = sorted(getattr(g, "geoms", [g]), key=lambda q: q.bounds[1])
            self._intervals.append([(q.bounds[1], q.bounds[3]) for q in parts])
            for j, z in enumerate(self.zs):
                cut = LineString([(rmin, z), (rmax, z)]).intersection(g)
                if not cut.is_empty:
                    self.r[i, j] = cut.bounds[2]
        self._radius = float(np.nanmax(self.r[0])) if np.isfinite(self.r[0]).any() else shank.band.outer_radius_mm

    @property
    def radius(self) -> float:
        return self._radius

    @property
    def length(self) -> float:
        return 2 * math.pi * self.radius

    def _index(self, theta_deg: float) -> int:
        return int(round((theta_deg % 360.0) / FACE_STEP_DEG)) % len(self.thetas)

    def intervals(self, theta_deg: float) -> list[tuple[float, float]]:
        return self._intervals[self._index(theta_deg)]

    def z_bounds(self) -> tuple[float, float]:
        return min(a for iv in self._intervals for a, _ in iv), max(b for iv in self._intervals for _, b in iv)

    def _r(self, theta_deg, z):
        """The outer radius, bilinear in (angle, height); NaN off the face."""
        import numpy as np
        t = (np.asarray(theta_deg, float) % 360.0) / FACE_STEP_DEG
        i0 = np.floor(t).astype(int) % len(self.thetas)
        i1 = (i0 + 1) % len(self.thetas)
        ft = t - np.floor(t)
        zz = (np.asarray(z, float) - self.zs[0]) / FACE_STEP_Z
        j0 = np.clip(np.floor(zz).astype(int), 0, len(self.zs) - 2)
        fz = np.clip(zz - j0, 0.0, 1.0)
        r00, r01 = self.r[i0, j0], self.r[i0, j0 + 1]
        r10, r11 = self.r[i1, j0], self.r[i1, j0 + 1]
        return (1 - ft) * ((1 - fz) * r00 + fz * r01) + ft * ((1 - fz) * r10 + fz * r11)

    def point_normal(self, theta_deg, z):
        import numpy as np
        th, z = np.asarray(theta_deg, float), np.asarray(z, float)
        r = self._r(th, z)
        dz = FACE_STEP_Z
        drdz = (self._r(th, z + dz) - self._r(th, z - dz)) / (2 * dz)
        dt = FACE_STEP_DEG
        drdt = (self._r(th + dt, z) - self._r(th - dt, z)) / (2 * math.radians(dt))      # dr / dθ (rad)
        # the face r = f(θ, z): outward normal ∝ e_r - (1/r) ∂f/∂θ e_θ - ∂f/∂z e_z
        nr, nt, nz = np.ones_like(r), -drdt / r, -drdz
        norm = np.sqrt(nr * nr + nt * nt + nz * nz)
        nr, nt, nz = nr / norm, nt / norm, nz / norm
        a = np.radians(th)
        c, s = np.cos(a), np.sin(a)
        P = np.column_stack([r * c, r * s, z])
        N = np.column_stack([nr * c - nt * s, nr * s + nt * c, nz])
        return P, N


def _edge_room(face, h: Hammer, u: float, z: float) -> float:
    """How far (mm) the point lies inside its stretch of face, the nearest end at the angle or a footprint
    either side of it (a slot narrowing, a taper); -1 when it is off the face at any of them."""
    th = math.degrees(u / face.radius)
    reach = math.degrees(h.footprint_mm(h.depth_range[1]) / 2 / face.radius)
    room = float("inf")
    for t in (th - reach, th, th + reach):
        inside = [min(z - a, b - z) for a, b in face.intervals(t) if a <= z <= b]
        if not inside:
            return -1.0
        room = min(room, max(inside))
    return room


def strike_layout(h: Hammer, face):
    """(u, z, depth) per strike: u along the face round the ring (mm at the face's crown radius, 0 at the
    head), z across, the strike's depth - darts thrown over the face's widest span (periodic round the
    ring), kept where they land at least a rim and a floor strike's half-footprint inside their stretch of
    face and clear of the head (`clear_deg`), centres spacing x dimple apart, ended after LAYOUT_TRIES
    darts in a row found no room (so nothing is left unstruck at spacing 0.5). A strike near a rim is
    struck lighter, its footprint ending at the rim (never under the depth floor: centres stay where a
    floor strike fits). On a plain band this is draw for draw HammeredSpec's first layout (2026-11-05)."""
    import numpy as np
    rng = np.random.default_rng(int(h.seed))
    rim = h.rim(face.edge_round)
    lo, hi = face.z_bounds()
    zl_lo, zl_hi = lo + rim + h.floor_half, hi - rim - h.floor_half
    if zl_hi < zl_lo:
        return np.empty(0), np.empty(0), np.empty(0)
    plain = isinstance(face, BandFace)
    L = face.length
    s = h.spacing * h.dimple_mm
    clear = math.radians(h.clear_deg) * face.radius + h.footprint_mm(h.depth_range[1]) / 2 if h.clear_deg else 0.0
    us, zs = np.empty(0), np.empty(0)
    misses = 0
    while misses < LAYOUT_TRIES:
        u, z = rng.uniform(0.0, L), rng.uniform(zl_lo, zl_hi)
        if clear and min(u, L - u) < clear:
            misses += 1
            continue
        if not plain and _edge_room(face, h, u, z) < rim + h.floor_half - 1e-9:
            misses += 1
            continue
        du = np.abs(us - u)
        du = np.minimum(du, L - du)
        if len(us) and (du * du + (zs - z) ** 2).min() < s * s:
            misses += 1
            continue
        us, zs = np.append(us, u), np.append(zs, z)
        misses = 0
    d = h.depth_mm * (1 + h.depth_var * rng.uniform(-1.0, 1.0, len(us)))
    if plain:
        room = np.array([(hi - lo) / 2 - abs(z) for z in zs])
    else:
        room = np.array([_edge_room(face, h, u, z) for u, z in zip(us, zs)])
    fit = np.array([h.depth_fitting(r - rim) for r in room])
    return us, zs, np.minimum(d, fit)


def strike_points(h: Hammer, face, layout):
    """(face points, normals, depths, sphere centres) in the ring frame for a layout."""
    us, zs, d = layout
    import numpy as np
    P, N = face.point_normal(np.degrees(us / face.radius), zs)
    C = P + N * (h.sphere_radius - d)[:, None]
    return P, N, d, C


def write_centres_file(path: Path, centres) -> Path:
    """Centres as CSV, x,y,z in mm (Import Points reads comma-separated lines, points_probe 2026-11-05);
    none at all -> FAR_STRIKE alone, which cuts nothing."""
    import numpy as np
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    c = np.asarray(centres, float).reshape(-1, 3) if len(centres) else np.array([FAR_STRIKE])
    np.savetxt(path, c, fmt="%.5f", delimiter=",")
    return path


def struck(body, centres, radius: float):
    """`body` less a sphere of `radius` at every centre (manifold3d), tidied like the knots (three strikes
    meeting near a point left slivers float32 STL could not hold)."""
    import trimesh
    from .shank import MIN_EDGE_MM, drop_specks
    if len(centres) == 0:
        return body
    unit = trimesh.creation.icosphere(subdivisions=SPHERE_SUBDIV, radius=radius)
    spheres = []
    for c in centres:
        q = unit.copy()
        q.apply_translation(c)
        spheres.append(q)
    out = trimesh.boolean.difference([body] + spheres, engine="manifold")
    return geom.collapse_short_edges(drop_specks(out), MIN_EDGE_MM)


def probe_depths(P, N, mesh):
    """Along every strike's normal, from 2 mm outside the face inward: how far below the face point the
    mesh's surface lies (NaN where no ray came back)."""
    import numpy as np
    origins = P + 2.0 * N
    loc, idx_ray, _ = mesh.ray.intersects_location(origins, -N, multiple_hits=True)
    out = np.full(len(P), np.nan)
    for k in range(len(P)):
        hits = loc[idx_ray == k]
        if len(hits):
            out[k] = ((origins[k] - hits) @ N[k]).min() - 2.0
    return out


def strikes_check(P, N, design, built, mesh_tolerance: float):
    """The `strikes` check: down every strike's normal, the built surface's depth against the design's."""
    import numpy as np
    want, got = probe_depths(P, N, design), probe_depths(P, N, built)
    allowed = mesh_tolerance / 2 + PROBE_TOL_MM
    n = len(want)
    if n == 0 or not np.isfinite(got).any():
        return gate.incomplete("strikes", "no probe came back")
    ok = np.isfinite(got) & (np.abs(got - want) <= allowed)
    err = np.abs(np.where(np.isfinite(got), got - want, np.inf))
    k = int(np.argmax(err))
    return gate.Check("strikes", bool(ok.all()),
                      f"{int(ok.sum())}/{n} dimples within {allowed:.3f} mm of the design's depth along the strike; "
                      f"worst #{k}: built {got[k]:.3f} vs design {want[k]:.3f} mm")


@dataclass
class HammeredSpec:
    band: band.BandSpec                     # the plain band struck; its Mesh Tolerance meshes the texture too
    dimple_mm: float = 1.6                  # a nominal strike's footprint diameter on the face
    depth_mm: float = 0.15                  # a nominal strike's depth along the face's normal
    depth_var: float = 0.25                 # each strike's depth varies by up to ± this fraction (seeded)
    spacing: float = 0.5                    # centres at least this many nominal diameters apart: at 0.5 or less every point
                                            # of the face lies inside some footprint (facets about a millimetre across)
    rim_mm: float | None = None             # polished rim kept at each edge of the face: no dimple reaches nearer the edge; None = edge round + 0.1
    seed: int = 1                           # the layout's and the strikes' random seed
    _cache: dict = field(default_factory=dict, init=False, repr=False, compare=False)

    kind = "hammered"

    # ---- the hammer --------------------------------------------------------------------------
    @property
    def sphere_radius(self) -> float:
        """The hammer face's radius: the sphere a nominal strike presses depth_mm in, footprint dimple_mm across."""
        a, d = self.dimple_mm / 2, self.depth_mm
        return (a * a + d * d) / (2 * d)

    @property
    def depth_range(self) -> tuple[float, float]:
        return self.depth_mm * (1 - self.depth_var), self.depth_mm * (1 + self.depth_var)

    def footprint_mm(self, depth: float) -> float:
        """A strike's footprint diameter at this depth (on a flat face)."""
        R = self.sphere_radius
        return 2 * math.sqrt(max(2 * R * depth - depth * depth, 0.0))

    @property
    def rim(self) -> float:
        return float(self.rim_mm) if self.rim_mm is not None else self.band.edge_round + 0.1

    def depth_fitting(self, half_width: float) -> float:
        """The strike whose footprint is this half-width across (on a flat face)."""
        R, a = self.sphere_radius, min(max(half_width, 0.0), self.sphere_radius)
        return R - math.sqrt(R * R - a * a)

    @property
    def edge_reach(self) -> float:
        """From the mid-plane to the rim: no footprint reaches past it."""
        return self.band.width_mm / 2 - self.rim

    @property
    def z_limit(self) -> float:
        """How far from the mid-plane a dimple's centre may lie: a strike there at the depth floor just
        reaches the rim (strikes nearer the edge are struck lighter, so their footprints end at it)."""
        return self.edge_reach - self.footprint_mm(tables.FLOORS["texture_depth"]) / 2

    @property
    def face_radius(self) -> float:
        return self.band.outer_radius_mm

    @property
    def face_length(self) -> float:
        """The face developed round the ring (at its crown): the layout's period."""
        return 2 * math.pi * self.face_radius

    # ---- the layout ----------------------------------------------------------------------------
    def layout(self):
        """(u, z, depth) per dimple: u along the face round the ring (mm at the crown, 0 at the head),
        z across, the strike's depth - a dart-throwing layout, periodic round the ring, centres at
        least spacing x dimple apart, ended after LAYOUT_TRIES darts in a row found no room (so no
        point of the strip is more than that spacing from a centre: footprints at least that wide in
        radius leave nothing unstruck). A strike near a rim is lighter, its footprint ending at the rim."""
        if "layout" not in self._cache:
            if self.z_limit < 0:
                import numpy as np
                self._cache["layout"] = (np.empty(0), np.empty(0), np.empty(0))
            else:
                self._cache["layout"] = strike_layout(self.hammer, BandFace(self.band))      # lighter towards the rims
        return self._cache["layout"]

    @property
    def hammer(self) -> Hammer:
        return Hammer(self.dimple_mm, self.depth_mm, self.depth_var, self.spacing, self.rim_mm, self.seed)

    @property
    def count(self) -> int:
        return len(self.layout()[0])

    def face_point(self, z):
        """(r, z) of the face at height z and its outward normal there (the dome's torus, or radial on a flat face)."""
        import numpy as np
        z = np.asarray(z, float)
        r = np.array([self.band.outer_radius_at(float(q)) for q in np.atleast_1d(z)]).reshape(z.shape)
        if self.band.dome > band.MIN_SAGITTA:
            rd, td = self.band.dome_torus
            n = np.stack([r - rd, z], axis=-1) / td
        else:
            n = np.stack([np.ones_like(r), np.zeros_like(z)], axis=-1)
        return np.stack([r, z], axis=-1), n

    def strikes(self):
        """Per dimple: (the face point it is struck at, the face's normal there, its depth), in the ring
        frame (axis Z, the head at +X), and its sphere's centre."""
        return strike_points(self.hammer, BandFace(self.band), self.layout())

    def centres(self):
        """(n, 3) sphere centres, mm, ring frame: what nTop needs besides the one radius."""
        return self.strikes()[3]

    def write_centres(self, path: Path) -> Path:
        """The centres as CSV (x, y, z in mm, one dimple a line) - the format the notebook reads is
        settled with the discovery run."""
        return write_centres_file(path, self.centres())

    # ---- the independent model ---------------------------------------------------------------
    def band_mesh(self):
        return geom.band_mesh(self.band.notebook_inputs(""))

    def design_mesh(self):
        """The struck band: the band nTop builds (its opening's chamfer included) less every strike's sphere."""
        if "design_mesh" not in self._cache:
            self._cache["design_mesh"] = struck(self.band_mesh(), self.centres(), self.sphere_radius)
        return self._cache["design_mesh"]

    def design_volume_mm3(self) -> float:
        return float(self.design_mesh().volume)

    def triangles_estimate(self) -> float:
        return tables.mesh_triangles_estimate(float(self.design_mesh().area), self.band.mesh_tolerance_mm)

    @property
    def outer_radius_mm(self) -> float:
        """The largest radius the struck band keeps (the face between strikes, or the rim)."""
        import numpy as np
        v = self.design_mesh().vertices
        return float(np.hypot(v[:, 0], v[:, 1]).max())

    def probe_depths(self, mesh):
        P, N, _, _ = self.strikes()
        return probe_depths(P, N, mesh)

    # ---- the notebook ------------------------------------------------------------------------------
    def notebook_inputs(self, centres_path: str, output_path: str) -> dict:
        """ring_texture.ntop's inputs: the band's, the strike centres file, the hammer's radius, the unit (mm)."""
        v = self.band.notebook_inputs(output_path)
        v.pop("Output Path")
        v.update({"Strikes Path": centres_path, "Strike Radius": round(self.sphere_radius, 6), "Strikes Units": "mm",
                  "Output Path": output_path})
        return v

    # ---- identity, checks ---------------------------------------------------------------------
    def design(self) -> dict:
        d = self.band.design()
        d.update({"texture": self.kind, "dimple": self.dimple_mm, "depth": self.depth_mm, "depth_var": self.depth_var,
                  "spacing": self.spacing, "rim": round(self.rim, 4), "seed": int(self.seed), "sphere_subdiv": SPHERE_SUBDIV})
        return d

    @property
    def spec_id(self) -> str:
        return runs.spec_id(self.design())

    @property
    def stem(self) -> str:
        b = self.band
        return f"ring_texture_{self.kind}_{b.profile}_{b.label}_w{b.width_mm:g}_t{b.thickness_mm:g}_d{self.dimple_mm:g}x{self.depth_mm:g}_{self.spec_id}"

    def validate(self) -> list[str]:
        p = list(self.band.validate())
        if p:
            return p
        lo, hi = self.depth_range
        floor = tables.FLOORS["texture_depth"]
        if not 0.0 <= self.depth_var <= 0.5:
            p.append(f"depth variation {self.depth_var:g}: 0..0.5 of the depth")
        if lo < floor - 1e-9:
            p.append(f"the lightest strike would be {lo:.3f} mm deep ({self.depth_mm:g} less {self.depth_var:.0%}); at least "
                     f"{floor:g} mm (a shallower dimple polishes flat): a deeper strike or less variation")
        stroke = 2 * tables.FLOORS["engrave_stroke"]
        if self.footprint_mm(lo) < stroke:
            p.append(f"the lightest strike's footprint would be {self.footprint_mm(lo):.2f} mm across; at least {stroke:g} "
                     f"(two engraving strokes: narrower fills in casting)")
        if self.depth_mm * 2 > self.dimple_mm:
            p.append(f"a {self.depth_mm:g} mm strike {self.dimple_mm:g} mm across is deeper than a hemisphere")
        if not 0.5 <= self.spacing <= 1.5:
            p.append(f"spacing {self.spacing:g} dimples: 0.5..1.5")
        if self.rim < 0:
            p.append("the rim is a width, at least 0")
        if self.z_limit < 0:
            p.append(f"a {self.band.width_mm:g} mm band keeps no room for {self.footprint_mm(hi):.2f} mm dimples inside "
                     f"{self.rim:.2f} mm rims: smaller dimples or narrower rims")
        if p:
            return p
        voxel = self.band.mesh_tolerance_mm / 2
        light = min(lo, float(self.layout()[2].min())) if self.count else lo            # the rims' strikes are lighter
        if light < DEPTH_VOXELS * voxel - 1e-9:
            p.append(f"the lightest strike ({light:.3f} mm) spans {light / voxel:.1f} voxels at Mesh Tolerance "
                     f"{self.band.mesh_tolerance_mm:g}; at least {DEPTH_VOXELS:g}: --tolerance "
                     f"{math.floor(2 * light / DEPTH_VOXELS * 100) / 100:g} or finer")
            return p
        wall = min(self.band.thickness_at(z) for z in (0.0, self.z_limit)) - hi
        if wall < tables.FLOORS["wall_good"]:
            p.append(f"the deepest strike leaves {wall:.2f} mm of band under it; at least {tables.FLOORS['wall_good']:g}")
        if self.count == 0:
            p.append("no dimple fits the face")
        if p:
            return p
        est = self.triangles_estimate()
        if est > MAX_TRIANGLES:
            p.append(f"meshed at {self.band.mesh_tolerance_mm:g} it would be about {est / 1e6:.1f} M triangles, past the "
                     f"{MAX_TRIANGLES / 1e6:g} M limit: a coarser --tolerance with deeper strikes")
        return p

    def wall_floor(self) -> float:
        return tables.FLOORS["wall_marginal"]

    def describe(self) -> str:
        b = self.band
        lo, hi = self.depth_range
        d = self.layout()[2]
        if len(d):
            lo, hi = float(d.min()), float(d.max())
        line = (f"{self.stem}: {b.profile} {b.label}, inner Ø {b.inner_diameter_mm:.3f}, {b.width_mm:g} x {b.thickness_mm:g}\n"
                f"  hammered: {self.count} strikes of a {self.sphere_radius:.2f} mm hammer face, {lo:.3f}..{hi:.3f} mm deep "
                f"({self.footprint_mm(lo):.2f}..{self.footprint_mm(hi):.2f} mm across; lighter towards the rims), centres {self.spacing * self.dimple_mm:.2f} mm "
                f"apart at least, within ±{self.z_limit:.2f} of the mid-plane (rims {self.rim:.2f}); seed {self.seed}")
        if "design_mesh" in self._cache or not self.validate():
            m = self.design_mesh()
            line += (f"\n  design volume {m.volume:.2f} mm³ (the plain band {self.band_mesh().volume:.2f}); surface {m.area:.1f} mm²; "
                     f"about {self.triangles_estimate() / 1e6:.1f} M triangles at Mesh Tolerance {b.mesh_tolerance_mm:g}")
        return line


def check_texture(spec: HammeredSpec, stl: Path, ntop_vol: float | None) -> gate.GateReport:
    """The band gate on the struck band, the section shape against the design's own sections (the whole
    Mesh Tolerance: a ridge between two strikes is a crease the mesher rounds by a voxel), the design
    volume, and a probe down every strike's normal."""
    import numpy as np
    design = spec.design_mesh()
    tol = float(spec.band.mesh_tolerance_mm)
    rep = gate.check(stl, expect_inner=spec.band.inner_diameter_mm, expect_outer=2 * spec.outer_radius_mm,
                     expect_width=spec.band.width_mm, expect_volume=ntop_vol, wall_floor=spec.wall_floor(), centre="origin",
                     section_design=lambda a: gate.section_geometry(design, a), section_tol_mm=lambda a: tol)
    rep.checks.append(band.design_volume_check(float(design.volume), ntop_vol, 1.5))
    P, N, _, _ = spec.strikes()
    rep.checks.append(strikes_check(P, N, design, gate.load_mesh(stl), tol))
    return rep


@dataclass
class TextureResult(band.BandResult):
    def text(self) -> str:
        s = self.spec
        head = (f"Hammered {s.band.profile} {s.band.label}: {s.count} strikes, {s.band.width_mm:g} x {s.band.thickness_mm:g} "
                f"-> {self.stl.name}")
        lines = [head, self.run.summary(), self.gate.text(), f"  status: {self.status.upper()}  run {self.run_dir}"]
        if self.delivered:
            lines.append(f"  delivered to {self.delivered}")
        lines += [f"  note: {n}" for n in self.notes]
        return "\n".join(lines)


def build(spec: HammeredSpec, out_dir: Path | None = None, *, notebook: Path | None = None, catalog_name: str = "ring_texture",
          deliver: bool = False, deliver_project: str = "Bands", cast_metal: str | None = None) -> TextureResult:
    """Write the strike centres, run ring_texture.ntop through nTopCL, gate the struck band (check_texture)."""
    problems = spec.validate()
    if problems:
        raise ValueError("; ".join(problems))
    cat = catalog.load(catalog_name)
    nb = Path(notebook) if notebook else cat.notebook
    built_notes = runs.require_built(cat, nb) if not notebook else []
    out_dir = Path(out_dir) if out_dir else config.out_dir() / "texture"
    stem = spec.stem
    run_dir, run_id = runs.fresh_run_dir(out_dir, stem)
    stl = run_dir / f"{stem}.stl"
    centres = spec.write_centres(run_dir / f"{stem}.centres.csv")
    values = spec.notebook_inputs(str(centres), str(stl))
    started = time.time()
    run = ntopcl.run(nb, cat.build_inputs(values), run_dir, tag=stem)
    try:
        runs.require_fresh(stl, started, "the exported mesh")
    except FileNotFoundError as e:
        raise ntopcl.NtopclError(f"notebook reported success but {e}", run) from e
    vol_entry = run.outputs.get(cat.output.get("name", "Volume"))
    ntop_vol = ntopcl.scalar_value(vol_entry) if vol_entry else None
    rep = check_texture(spec, stl, ntop_vol)
    gate.save(rep)
    result = TextureResult(spec, stl, run, rep, ntop_vol, run_dir, run_id)
    result.notes += built_notes + spec.band.warnings()
    report = {
        "stem": stem, "spec_id": spec.spec_id, "run_id": run_id, "status": result.status, "ok": result.ok,
        "spec": {**asdict(spec.band), "texture": spec.design()}, "design": spec.design(), "inputs": values, "stl": str(stl),
        "ntop_volume_mm3": ntop_vol, "design_volume_mm3": spec.design_volume_mm3(), "strikes": spec.count,
        "gate": rep.to_dict(), "ntopcl_seconds": run.seconds, "block_timings": [t.__dict__ for t in run.log.timings],
        "notes": result.notes, "notebook": runs.notebook_identity(nb), "environment": runs.environment(ntopcl.version()),
    }
    (run_dir / f"{stem}.report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    if deliver and result.ok:
        result.delivered = runs.deliver(stl, run_dir, stem, deliver_project, report, cast_metal=cast_metal)
    elif deliver:
        result.notes.append(f"not delivered: status {result.status}")
    return result
