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
that choice.

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

from . import band, gate, geom, runs, tables

KINDS = ("hammered",)
SPHERE_SUBDIV = 4               # icosphere level of a dimple's sphere: 0.15 mm facets, 1 µm sag at R 2.4
LAYOUT_TRIES = 4000             # darts rejected in a row that end the layout (it is then as full as it gets)
MAX_TRIANGLES = 5_000_000       # the gate's mesh density limit (gate.check)
DEPTH_VOXELS = 3.0              # the shallowest strike spans at least this many voxels (half the Mesh Tolerance each)
PROBE_TOL_MM = 0.02             # a probe's built depth within this of the design's, beyond half the Mesh Tolerance


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
            import numpy as np
            rng = np.random.default_rng(int(self.seed))
            L, zl = self.face_length, max(self.z_limit, 0.0)
            s = self.spacing * self.dimple_mm
            us, zs = np.empty(0), np.empty(0)
            misses = 0
            while misses < LAYOUT_TRIES:
                u, z = rng.uniform(0.0, L), rng.uniform(-zl, zl)
                du = np.abs(us - u)
                du = np.minimum(du, L - du)
                if len(us) and (du * du + (zs - z) ** 2).min() < s * s:
                    misses += 1
                    continue
                us, zs = np.append(us, u), np.append(zs, z)
                misses = 0
            d = self.depth_mm * (1 + self.depth_var * rng.uniform(-1.0, 1.0, len(us)))
            fit = np.array([self.depth_fitting(self.edge_reach - abs(z)) for z in zs])
            self._cache["layout"] = (us, zs, np.minimum(d, fit))                    # lighter towards the rims
        return self._cache["layout"]

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
        import numpy as np
        u, z, d = self.layout()
        theta = u / self.face_radius
        p_rz, n_rz = self.face_point(z)
        c, s = np.cos(theta), np.sin(theta)
        P = np.column_stack([p_rz[:, 0] * c, p_rz[:, 0] * s, p_rz[:, 1]])
        N = np.column_stack([n_rz[:, 0] * c, n_rz[:, 0] * s, n_rz[:, 1]])
        C = P + N * (self.sphere_radius - d)[:, None]
        return P, N, d, C

    def centres(self):
        """(n, 3) sphere centres, mm, ring frame: what nTop needs besides the one radius."""
        return self.strikes()[3]

    def write_centres(self, path: Path) -> Path:
        """The centres as CSV (x, y, z in mm, one dimple a line) - the format the notebook reads is
        settled with the discovery run."""
        import numpy as np
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savetxt(path, self.centres(), fmt="%.5f", delimiter=",")
        return path

    # ---- the independent model ---------------------------------------------------------------
    def band_mesh(self):
        return geom.band_mesh(self.band.notebook_inputs(""))

    def design_mesh(self):
        """The struck band: the band nTop builds (its opening's chamfer included) less every strike's sphere."""
        if "design_mesh" not in self._cache:
            import trimesh
            R = self.sphere_radius
            unit = trimesh.creation.icosphere(subdivisions=SPHERE_SUBDIV, radius=R)
            spheres = []
            for c in self.centres():
                q = unit.copy()
                q.apply_translation(c)
                spheres.append(q)
            body = trimesh.boolean.difference([self.band_mesh()] + spheres, engine="manifold")
            # where three strikes meet almost at a point the boolean leaves slivers float32 STL cannot hold
            # (the knots' lesson, 2026-11-01): specks dropped, sub-0.2 µm edges collapsed (shank.united's tidy)
            from .shank import MIN_EDGE_MM, drop_specks
            body = geom.collapse_short_edges(drop_specks(body), MIN_EDGE_MM)
            self._cache["design_mesh"] = body
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
        """Along every strike's normal, from 2 mm outside the face inward: how far below the face
        point the mesh's surface lies (NaN where no ray came back)."""
        import numpy as np
        P, N, _, _ = self.strikes()
        origins = P + 2.0 * N
        loc, idx_ray, _ = mesh.ray.intersects_location(origins, -N, multiple_hits=True)
        out = np.full(len(P), np.nan)
        for k in range(len(P)):
            hits = loc[idx_ray == k]
            if len(hits):
                t = ((origins[k] - hits) @ N[k]).min()                  # the first surface the ray meets
                out[k] = t - 2.0
        return out

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
    built = gate.load_mesh(stl)
    want, got = spec.probe_depths(design), spec.probe_depths(built)
    allowed = tol / 2 + PROBE_TOL_MM
    ok = np.isfinite(got) & (np.abs(got - want) <= allowed)
    n = len(want)
    if n == 0 or not np.isfinite(got).any():
        rep.checks.append(gate.incomplete("strikes", "no probe came back"))
    else:
        err = np.abs(np.where(np.isfinite(got), got - want, np.inf))
        k = int(np.argmax(err))
        rep.checks.append(gate.Check("strikes", bool(ok.all()),
                                     f"{int(ok.sum())}/{n} dimples within {allowed:.3f} mm of the design's depth along the strike; "
                                     f"worst #{k}: built {got[k]:.3f} vs design {want[k]:.3f} mm"))
    return rep
