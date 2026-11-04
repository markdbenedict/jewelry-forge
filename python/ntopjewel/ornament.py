"""Knot ornaments standing on a band - the Seraphine's trinity knots on the shoulders (Phase 3
step 5/6; the reference ring 2026-11-03).

Ring 01's trinity knots are woven from a split shank's halves; the Seraphine's stand on a
continuous band, one on each shoulder between the head and the leaf panels, wider than the band.
This module builds such a knot as a closed Celtic ribbon lying on the band's OUTER face:

  curve      the trefoil φ = 2t, ρ = R (1 + c cos 3t), t over a full turn (two turns in angle, three
             lobes, three self-crossings at radius R) about a centre on the band's mid-line at
             `at_deg` from the top, its lone lobe pointing at the head and the other two spreading
             across the band below it (the reference ring's; `point` "shank" turns it round); the -Y
             shoulder's knot is its mirror (knotwork.Strand closed in place; the weave solved by knotwork.interlace: at
             every crossing one pass over, one under, alternating round the loop)
  law        the bore law (knotwork.Interlace.depth, "bore") about the band's outer face: the ribbon
             lies on the face with its underside PLUG_MM inside it, and lifts by 2h = thickness -
             KNOT_FUSE_MM only to pass over itself, a plateau as long as the two passes overlap in
             plan with a cosine ramp of RAMP_MM either side; the over pass's underside lies
             KNOT_FUSE_MM inside the under pass's top, so they fuse into one casting there
  ribbon     a rounded rectangle (knotwork.ribbon_profile), `ribbon_mm` across the surface x
             `thickness_mm` radial, swept along the curve in the ring frame (knotwork.sweep_rings)
  pieces     a closed sweep that passes over itself is no manifold, so each knot is cut into two open
             pieces between its third and fourth and its sixth and first passes: each holds one pass
             of every crossing. The independent model's pieces meet in one identical face (shared
             rings and cap triangles) and unite exactly; the notebook's run PLUG_MM into each other
             (shank.plug_rings) and go to nTop in two files - the first pieces of both knots in one,
             the second pieces in the other (bodies that cross each other never share a mesh) - as
             the Knot Path / Knot Path 2 inputs, united with the carved band after its opening (the
             ribbon's corners are its own rounds)

The gate probes the knot on a grid (ornament_checks): rays from outside the ring down onto the
ribbon and the band beside it, cast identically on the built ring and the design.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import band as bandmod, gate, geom, knotwork, shank as shankmod, tables

KINDS = ("trinity",)
POINTS_AT = ("head", "shank")  # where the trefoil's lone lobe points (the Seraphine's: at the head, the other two spread below it)
OVERHANG_MM = 0.8             # the knot's default width past the band's (about 1.3 x the band on the reference ring)
RAMP_MM = 1.0                 # the bore law's ramp down from an over pass: the lift's cosine then bends with a 0.5 mm radius,
                              # twice the ribbon's half-thickness (0.5 mm folded the sweep on itself, 2026-11-03)
PLUG_MM = 0.1                 # the ribbon's underside sinks this far into the band's face
LOBE_MARGIN_MM = 0.15         # the lobes' outer edges lie this far inside width_mm / 2
CORNER_MAX_MM = 0.2           # the ribbon's corner round, at most
HOLE_MIN_MM = 0.3             # each lobe's opening must be at least this wide (a pierced knot, not a blob)
POINTS = 288                  # samples round the trefoil (its chord error under 0.002 mm at R 1.2)
PROBE_MM = 0.2                # the gate's probe grid over the knot
PROBE_MARGIN_MM = 0.12        # probes this close to the ribbon's plan edge are skipped (the mesher's blur)
SPAN_PAD_DEG = 1.0            # the knot's angular span, for the checks that give it room


def setting(name: str, default: float) -> float:
    return float(tables.SETTINGS.get(name, default))


@dataclass
class KnotOrnament:
    shank: shankmod.ShankSpec
    kind: str = "trinity"
    at_deg: float = 32.0          # the knot's centre, from the top (a solitaire places it just past its head)
    width_mm: float = 0.0         # across the band, lobe edge to lobe edge; 0 = the band's width + OVERHANG_MM
    ribbon_mm: float = 0.6        # the ribbon's width across the surface (0.7 closed the lobes of a 3.6 mm knot to 0.22)
    thickness_mm: float = 0.5     # ... and its radial thickness
    ratio: float = knotwork.TREFOIL_RATIO   # the trefoil's radial swing c: crossings 2 atan(1.5 c) apart
    point: str = "head"           # the lone lobe points at the head (POINTS_AT), the other two spread across the band below
    mirror: bool = True           # the same knot on the -Y shoulder
    _cache: dict = field(default_factory=dict, repr=False, compare=False)

    # ---- numbers --------------------------------------------------------------------------------
    @property
    def band(self) -> bandmod.BandSpec:
        return self.shank.band

    @property
    def width(self) -> float:
        return float(self.width_mm) if self.width_mm else self.band.width_mm + OVERHANG_MM

    @property
    def radius(self) -> float:
        """The trefoil's R, so that the flanking lobes' outer edges reach LOBE_MARGIN_MM inside the
        width: the curve's extent across is `spread` x R (a lobe bulges past its tip's sine; 1.41 R
        at the default ratio, not the 1.5 R sin 60° = 1.30 R of the tips alone)."""
        return (self.width / 2 - LOBE_MARGIN_MM - self.ribbon_mm / 2) / self.spread

    @property
    def spread(self) -> float:
        """max over t of (1 + c cos 3t) |sin 2t|: the trefoil's half-extent across the band per unit R."""
        import numpy as np
        t = np.linspace(0.0, 2 * math.pi, 3600)
        return float(np.max((1 + self.ratio * np.cos(3 * t)) * np.abs(np.sin(2 * t))))

    @property
    def lift(self) -> float:
        """h: the ribbon's centre rises 2h to pass over itself (its underside then KNOT_FUSE_MM inside the under pass)."""
        return (self.thickness_mm - knotwork.KNOT_FUSE_MM) / 2

    @property
    def r_down(self) -> float:
        """The ribbon centre's radius lying on the face (its underside PLUG_MM inside the band)."""
        return self.band.outer_radius_mm - PLUG_MM + self.thickness_mm / 2

    @property
    def top_radius(self) -> float:
        """The knot's highest point: an over pass's top."""
        return self.r_down + 2 * self.lift + self.thickness_mm / 2

    @property
    def L(self) -> float:
        return self.shank.wrap_length_mm

    def y_of(self, theta_deg: float) -> float:
        return theta_deg / 360.0 * self.L

    def deg_of(self, y: float) -> float:
        return y * 360.0 / self.L

    def sides(self) -> list[int]:
        return [1, -1] if self.mirror else [1]

    # ---- the curve and its weave ---------------------------------------------------------------
    def strand(self, side: int) -> knotwork.Strand:
        """The closed trefoil in the developed surface (y along the ring, z across), about
        (±y_c, 0), its lone lobe pointing at the head (`point` "head": towards y = 0 on either
        shoulder) or away from it down the shank."""
        import numpy as np
        key = ("strand", side)
        if key not in self._cache:
            R, c = self.radius, self.ratio
            yc = side * self.y_of(self.at_deg)
            t = np.linspace(0.0, 2 * math.pi, POINTS, endpoint=False)
            rho = R * (1 + c * np.cos(3 * t))
            phi = 2 * t
            away = side if self.point == "shank" else -side
            pts = np.column_stack([yc + away * rho * np.cos(phi), rho * np.sin(phi)])
            self._cache[key] = knotwork.Strand(pts, period=0.0, closed=True)
        return self._cache[key]

    def lace(self, side: int) -> knotwork.Interlace:
        key = ("lace", side)
        if key not in self._cache:
            self._cache[key] = knotwork.interlace([self.strand(side)])
        return self._cache[key]

    def footprint(self, side: int):
        """The ribbon's plan outline (shapely), the lobes' openings its holes."""
        from shapely.geometry import LineString
        st = self.strand(side)
        return LineString(st.loop).buffer(self.ribbon_mm / 2, cap_style="round", join_style="round")

    def span_deg(self) -> tuple[float, float]:
        """The knot's angular extent from the top (the +Y copy's; the mirror's is the negative)."""
        y0, _, y1, _ = self.footprint(1).bounds
        return self.deg_of(y0), self.deg_of(y1)

    def in_span(self, theta_deg: float, pad_deg: float = SPAN_PAD_DEG) -> bool:
        a = (float(theta_deg) + 180.0) % 360.0 - 180.0
        lo, hi = self.span_deg()
        return any(lo - pad_deg <= s * a <= hi + pad_deg for s in self.sides())

    # ---- the ribbon in the ring frame -----------------------------------------------------------
    def profile(self):
        corner = min(CORNER_MAX_MM, self.thickness_mm / 2 - 0.05, self.ribbon_mm / 2 - 0.05)
        return knotwork.ribbon_profile(self.ribbon_mm, self.thickness_mm, corner)

    def path(self, side: int) -> dict:
        """The ribbon's centreline in the ring frame with the sweep's vertex rings: the strand's
        (y, z) at the mid-wall angle, its radius r_down + h (1 + u) under the bore law."""
        import numpy as np
        key = ("path", side)
        if key not in self._cache:
            st, lace = self.strand(side), self.lace(side)
            s = st.params
            u = lace.depth(0, s, law="bore", widths=[self.ribbon_mm], ramp_mm=RAMP_MM)
            r = self.r_down + self.lift * (1.0 + u)
            t = np.radians(st.points[:, 0] * 360.0 / self.L)
            path = np.column_stack([r * np.cos(t), r * np.sin(t), st.points[:, 1]])
            up = np.column_stack([np.cos(t), np.sin(t), np.zeros_like(t)])
            prof = self.profile()
            rings, reversed_ = knotwork.sweep_rings(path, profile=prof, closed=True, up=up)
            self._cache[key] = dict(path=path, s=s, rings=rings, reversed=reversed_, profile=prof)
        return self._cache[key]

    def cuts(self, side: int) -> tuple[int, int]:
        """The two stations the closed sweep is cut at: between the third and fourth passes and
        between the sixth and the first (round the loop), so each piece holds one pass of every
        crossing."""
        import numpy as np
        d, lace = self.path(side), self.lace(side)
        cs = list(lace.params[0])
        S = self.strand(side).length
        half = len(cs) // 2
        mid_a = 0.5 * (cs[half - 1] + cs[half])
        mid_b = (0.5 * (cs[-1] + cs[0] + S)) % S
        k_a = int(np.searchsorted(d["s"], mid_a)) % len(d["s"])
        k_b = int(np.searchsorted(d["s"], mid_b)) % len(d["s"])
        return k_a, k_b

    def piece_rings(self, side: int) -> list:
        """The two open pieces' vertex rings, consecutive (the first ends on the ring the second
        starts with, the second ends on the first's start)."""
        import numpy as np
        d = self.path(side)
        k_a, k_b = self.cuts(side)
        R = d["rings"]
        n = len(R)
        rolled = np.roll(R, -k_b, axis=0)                                   # the second cut first
        kk = (k_a - k_b) % n
        first = rolled[:kk + 1]
        second = np.concatenate([rolled[kk:], rolled[:1]])
        return [first, second]

    def pieces_ring(self, side: int) -> list:
        """The two pieces as watertight meshes sharing identical end faces (the independent model)."""
        d = self.path(side)
        prof = d["profile"] if not d["reversed"] else d["profile"][::-1]
        cap = knotwork.cap_triangles(prof)
        return [knotwork.mesh_from_rings(r, start_cap=cap, end_cap=cap) for r in self.piece_rings(side)]

    def pieces_plugged(self, side: int) -> list:
        """The same pieces for the notebook, each running PLUG_MM into the other at both cuts."""
        return [knotwork.mesh_from_rings(shankmod.plug_rings(r)) for r in self.piece_rings(side)]

    def layers(self) -> list:
        """The two files' meshes: the first pieces of every knot, then the second pieces."""
        import trimesh
        firsts, seconds = [], []
        for side in self.sides():
            a, b = self.pieces_plugged(side)
            firsts.append(a)
            seconds.append(b)
        return [trimesh.util.concatenate(firsts), trimesh.util.concatenate(seconds)]

    def design_parts(self) -> list:
        """Every piece of every knot, for the independent ring's union."""
        return [m for side in self.sides() for m in self.pieces_ring(side)]

    def volume_mm3(self) -> float:
        """The knots' metal above the band's face (their plugs inside it left out): the union of the
        pieces less what lies under the face."""
        import trimesh
        if "volume" not in self._cache:
            body = shankmod.united(self.design_parts())
            cyl = trimesh.creation.cylinder(radius=self.band.outer_radius_mm, height=self.width + 2.0, sections=720)
            above = trimesh.boolean.difference([body, cyl], engine="manifold")
            self._cache["volume"] = float(above.volume)
        return self._cache["volume"]

    def write_layers(self, directory: Path, stem: str) -> tuple[str, str]:
        """<stem>.knot.stl and <stem>.knot2.stl, each read back and refused if it crosses itself."""
        import trimesh
        directory = Path(directory)
        out = []
        for name, mesh in zip(("knot", "knot2"), self.layers()):
            path = directory / f"{stem}.{name}.stl"
            mesh.export(str(path))
            back = trimesh.load(str(path), force="mesh")
            pairs = geom.intersecting_faces(back, cell_mm=0.3)
            if len(pairs) or not back.is_volume:
                raise ValueError(f"the {name} layer crosses itself ({len(pairs)} face pairs) or is not a volume as written to "
                                 f"{path.name}: nTop would read a wrong implicit from it")
            out.append(str(path))
        return out[0], out[1]

    # ---- identity, checks -------------------------------------------------------------------------
    def design(self) -> dict:
        return {"kind": self.kind, "at_deg": self.at_deg, "width": self.width, "ribbon": self.ribbon_mm,
                "thickness": self.thickness_mm, "ratio": self.ratio, "point": self.point, "mirror": self.mirror, "ramp": RAMP_MM,
                "fuse": knotwork.KNOT_FUSE_MM, "plug": PLUG_MM}

    def validate(self) -> list[str]:
        p = []
        b = self.band
        if self.kind not in KINDS:
            return [f"knot {self.kind!r}: one of {', '.join(KINDS)}"]
        if self.point not in POINTS_AT:
            return [f"knot points {self.point!r}: one of {', '.join(POINTS_AT)}"]
        if b.dome > bandmod.MIN_SAGITTA:
            p.append(f"a knot stands on a flat outer face: the {b.profile} band's is domed (a flat band)")
        if self.thickness_mm < 0.3:
            p.append(f"knot ribbon {self.thickness_mm:g} mm thick: at least 0.3")
        if self.ribbon_mm < tables.FLOORS["wall_marginal"]:
            p.append(f"knot ribbon {self.ribbon_mm:g} mm wide: at least the wall floor {tables.FLOORS['wall_marginal']:g}")
        if self.lift <= 0.05:
            p.append("the ribbon is too thin to pass over itself (thickness - fuse)")
        if self.radius <= 0.2:
            p.append(f"the knot ({self.width:g} wide) is too small for a {self.ribbon_mm:g} mm ribbon")
        if not 0.0 < self.at_deg < 180.0:
            p.append("the knot's centre must lie between the top and the bottom of the ring")
        if p:
            return p
        lace = self.lace(1)
        p += lace.problems
        p += lace.bore_law_problems(widths=[self.ribbon_mm], ramp_mm=RAMP_MM)
        fp = self.footprint(1)
        holes = list(fp.interiors)
        if len(holes) < 3:
            p.append(f"the knot's lobes close up ({len(holes)} openings): a wider knot or a narrower ribbon")
        else:
            from shapely.geometry import Polygon
            import shapely
            narrow = min(2 * shapely.maximum_inscribed_circle(Polygon(h)).length for h in holes)
            if narrow < HOLE_MIN_MM:
                p.append(f"a lobe's opening is {narrow:.2f} mm wide; at least {HOLE_MIN_MM:g}: a wider knot or a narrower ribbon")
        return p

    def describe(self) -> str:
        lo, hi = self.span_deg()
        return (f"{self.kind} knot on each shoulder, its lobe at the {self.point}: {self.width:g} mm across (R {self.radius:.2f}), ribbon "
                f"{self.ribbon_mm:g} x {self.thickness_mm:g}, centred {self.at_deg:g}° from the top ({lo:.1f}°..{hi:.1f}°), standing "
                f"{self.top_radius - self.band.outer_radius_mm:.2f} mm above the face at its over passes; {len(self.lace(1).crossings)} self-crossings")

    # ---- the gate ----------------------------------------------------------------------------------
    def wall_ray_filter(self):
        """Drops wall-sample points within the knots' angular span: the knot overhangs the band's
        sides and a ray through a lobe reads the ribbon, not a wall."""
        import numpy as np

        def keep(pts, normals):
            th = np.degrees(np.arctan2(pts[:, 1], pts[:, 0]))
            ok = np.ones(len(pts), dtype=bool)
            lo, hi = self.span_deg()
            for s in self.sides():
                ok &= ~((s * th >= lo - 2.0) & (s * th <= hi + 2.0))
            return ok
        return keep

    def probes(self, side: int):
        """(origins, directions, limits, kinds) of the gate's rays over one knot: a grid over its
        footprint and the band beside it, from above the knot radially inward; kind 'ribbon' inside
        the ribbon's plan, 'face' on the band outside it, points within PROBE_MARGIN_MM of the
        ribbon's edge skipped."""
        import numpy as np
        from shapely import contains_xy
        b = self.band
        fp = self.footprint(side)
        inner, outer = fp.buffer(-PROBE_MARGIN_MM), fp.buffer(PROBE_MARGIN_MM)
        y0, z0, y1, z1 = fp.bounds
        ys = np.arange(y0 - 0.3, y1 + 0.3, PROBE_MM)
        zs = np.arange(z0 - 0.3, z1 + 0.3, PROBE_MM)
        Y, Z = np.meshgrid(ys, zs)
        Y, Z = Y.ravel(), Z.ravel()
        kinds = np.full(len(Y), "", dtype=object)
        kinds[contains_xy(inner, Y, Z)] = "ribbon"
        on_band = np.abs(Z) <= b.width_mm / 2 - 0.1
        kinds[~contains_xy(outer, Y, Z) & on_band] = "face"
        keep = kinds != ""
        Y, Z, kinds = Y[keep], Z[keep], kinds[keep]
        th = np.radians(Y * 360.0 / self.L)
        r0 = self.top_radius + 0.5
        origins = np.column_stack([r0 * np.cos(th), r0 * np.sin(th), Z])
        dirs = -np.column_stack([np.cos(th), np.sin(th), np.zeros_like(th)])
        limits = np.full(len(Y), r0 - b.outer_radius_mm + 0.5)
        return origins, dirs, limits, kinds


def ornament_checks(orn: KnotOrnament, ring, design) -> list[gate.Check]:
    """The knots probed by rays cast identically on the built ring and the design: the ribbon at its
    height (over passes lifted, under passes down) and the band bare beside it."""
    import numpy as np
    from .artwork import _first_hits
    tol = max(0.06, 1.5 * float(orn.band.mesh_tolerance_mm))
    totals = {"ribbon": [0, 0], "face": [0, 0]}
    worst = {"ribbon": 0.0, "face": 0.0}
    for side in orn.sides():
        o, d, lim, kinds = orn.probes(side)
        built, want = _first_hits(ring, o, d, lim), _first_hits(design, o, d, lim)
        both_miss = np.isinf(built) & np.isinf(want)
        diff = np.where(both_miss, 0.0, np.where(np.isfinite(built) & np.isfinite(want), np.abs(built - want), np.inf))
        for k in totals:
            sel = kinds == k
            n, bad = int(sel.sum()), int((diff[sel] > tol).sum())
            totals[k][0] += n
            totals[k][1] += bad
            if n:
                finite = diff[sel][np.isfinite(diff[sel])]
                worst[k] = max(worst[k], float(finite.max()) if len(finite) else 9.0)
    checks = []
    names = {"ribbon": "knot ribbon", "face": "knot surround"}
    for k, (n, bad) in totals.items():
        if n == 0:
            continue
        checks.append(gate.Check(names[k], bad == 0, f"{n - bad}/{n} probes where designed (within {tol:.2f} mm; worst {worst[k]:.3f})"))
    return checks


def buried_specks(b: bandmod.BandSpec) -> list:
    """The two no-op knot layers: SPECK cubes buried in the band opposite the head, apart from each
    other and from the relief's (artwork.buried_speck)."""
    import trimesh
    out = []
    for dz in (0.35, -0.35):
        speck = trimesh.creation.box(extents=(0.2, 0.2, 0.2))
        speck.apply_translation([-(b.bore_radius_mm + b.thickness_mm / 2), 0.0, dz])
        out.append(speck)
    return out
