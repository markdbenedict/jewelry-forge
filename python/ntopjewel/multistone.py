"""Multi-stone rings: a centre stone and side stones in a row along the band - Phase 3 step 2
(reference rings 05, the three-stone, and 02, stones in a row).

Every stone is set in an outline head (the `outline_head` block: prongs on its outline, rails
following its pavilion - any of the six shapes, round included) and placed on the band the way the
solitaire places its one head, then turned about the ring axis to its own angle:

    spin       about the head's own axis first: a side stone's length runs along the band and its
               point (a pear's, a marquise's) faces the centre stone (+90° on the +Y side, -90° on
               the -Y side); the centre keeps its length along the finger unless told otherwise
    placement  a quarter-turn about the line through (Pivot X, *, Pivot Z) parallel to +Y takes the
               head's +Z to +X and its girdle centre to (girdle radius, 0, 0); the girdle radius puts
               every culet `finger_clear` above the bore, so a smaller side stone sits lower
    turn       about the ring axis (+Z) by the stone's angle (+ towards +Y)

The side stones' angles are solved, not guessed: the smallest turn at which the stone's girdle stands
`side_gap_mm` clear of its neighbour's AND neither stone's seat cutter (drop-in path included) takes
metal from the other's head - prongs may touch and fuse, a seat may not cut a neighbour's prong.

The notebook (multistone.ntop, ntop/recipes/multistone.py) has SLOTS head slots (Seat Path, Prongs
Path, five rail numbers, Spin, Pivot X, Pivot Z, Turn; slot k > 1 suffixed " k"); a ring with fewer
stones repeats the centre in the unused slots - an identical head at the same place unites to
nothing new and an identical seat cuts nothing more. The shank is the bars Python writes (any
ShankSpec: plain, tapered ...), as every solitaire's. Ring = ((shank ∪ placed heads, blended by
Shank Blend) − placed seats.

Pavé round the rest of the ring (`pave`, a pave.PaveSpec over the same shank, centred on the bottom,
180°): its beads join the shank before the heads, its seats are cut with the heads' (Pave Beads Path /
Pave Seats Path, catalog 0.2.0); the arc ends PAVE_HEAD_CLEAR_MM short of the outermost head's metal
at the band's surface, unless asked otherwise (`pave_from_deg`). No pavé: a speck buried in the band
and a speck far outside it, which change nothing.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from . import band as bandmod, catalog, config, gallery as gallerymod, gate, gems, geom, heads, ntopcl, runs, tables
from . import shank as shankmod
from .nb_multistone import COMMON, GALLERY, PAVE, SLOT_FIELDS, SLOTS, input_order, slot_input, specs  # noqa: F401  (console-safe)

WALL_FLOOR = tables.FLOORS["wall_marginal"]
HEAD_ANGLE_DEG = 90.0
SIDE_GAP_MM = 0.3                  # girdle to girdle between neighbouring stones (default)
CUT_ALLOWED_MM3 = 1e-3             # a seat may take no more than this from a neighbour's head
PAVE_HEAD_CLEAR_MM = 0.4           # the pavé's first girdle edge stands this far (at the outer surface) past the side heads' metal


@dataclass
class Placed:
    """A stone on the ring: its head as it goes on the band, where, and how it is spun."""
    head: heads.OutlineHeadSpec
    theta_deg: float
    spin_deg: float
    role: str                      # "centre" | "side"


@dataclass
class MultiStoneSpec:
    band: bandmod.BandSpec
    centre: heads.OutlineHeadSpec
    side: heads.OutlineHeadSpec | None = None
    side_pairs: int = 1                        # side stones each side of the centre (1: a three-stone ring)
    side_gap_mm: float = SIDE_GAP_MM
    centre_spin_deg: float = 0.0               # 90: the centre's length along the band
    side_point: str = "in"                    # a pear's / marquise's point: "in" towards the centre, "out" away from it
    finger_clear_mm: float | None = None
    shank_blend_mm: float | None = None
    shank: shankmod.ShankSpec | None = None
    pave_stone_mm: float = 0.0                 # pavé round the rest of the ring: the stones' size (0: none)
    pave_rows: int = 1
    pave_layout: str = "staggered"
    pave_from_deg: float = 0.0                 # where the pavé begins, from the top (0: just past the side heads)
    pave_material: str = tables.DEFAULT_STONE
    row: int = 0                               # stones in a row: N stones of the centre's kind symmetric about the top (an even N has none at it); 0: centre + side pairs
    shared_prongs: bool = False                # neighbours share the prongs facing each other: one post between them each side of the band
    gallery: bool = False                      # a bridge rail along the row each side of the band, at the heads' upper rails
    _cache: dict = field(default_factory=dict, init=False, repr=False, compare=False)

    def __post_init__(self):
        if self.shank is not None and self.shank.band != self.band:
            raise ValueError("the shank's band must be the ring's band (its head section)")

    # ---- numbers ----------------------------------------------------------------------------
    @property
    def finger_clear(self) -> float:
        return WALL_FLOOR + 0.1 if self.finger_clear_mm is None else float(self.finger_clear_mm)

    @property
    def shank_blend(self) -> float:
        return tables.SETTINGS["blend_radius_mm"] if self.shank_blend_mm is None else float(self.shank_blend_mm)

    @property
    def shank_spec(self) -> shankmod.ShankSpec:
        if self.shank is not None:
            return self.shank
        if "plain_shank" not in self._cache:
            self._cache["plain_shank"] = shankmod.ShankSpec(self.band)
        return self._cache["plain_shank"]

    @property
    def stone_count(self) -> int:
        if self.row:
            return int(self.row)
        return 1 + (2 * self.side_pairs if self.side is not None else 0)

    def _seating(self, h: heads.OutlineHeadSpec) -> tuple[float, float]:
        """(girdle radius, floor in the head's frame): the culet `finger_clear` above the bore and
        nothing of the head below 0.2 mm above it, as the solitaire's; a head whose rails cannot
        fit under its stone in that room (a small side stone's gallery is deeper than its pavilion
        plus the clearance) stands higher, until its lowest metal is at that floor."""
        key = ("seating", id(h))
        if key not in self._cache:
            _, pav = h.stone.heights
            bore = self.band.bore_radius_mm
            R = bore + self.finger_clear + pav + h.stone.girdle / 2
            for _ in range(20):
                floor = round(bore + 0.2 - R, 4)
                low = replace(h, floor_z=floor).lowest_z()
                if low >= floor - 1e-6:
                    break
                R += floor - low
            self._cache[key] = (R, floor)
        return self._cache[key]

    def placed_head(self, h: heads.OutlineHeadSpec) -> heads.OutlineHeadSpec:
        """The head with nothing of it below 0.2 mm above the bore (its floor)."""
        return replace(h, floor_z=self._seating(h)[1])

    def girdle_radius(self, h: heads.OutlineHeadSpec) -> float:
        return self._seating(h)[0]

    def pivot(self, h: heads.OutlineHeadSpec) -> tuple[float, float]:
        R = self.girdle_radius(h)
        return R / 2, -R / 2

    def matrix(self, h: heads.OutlineHeadSpec, theta_deg: float, spin_deg: float):
        """4x4 head frame -> ring frame: spin about the head's Z, the quarter-turn onto +X, the turn about the ring axis."""
        import numpy as np
        import trimesh
        px, pz = self.pivot(h)
        spin = trimesh.transformations.rotation_matrix(math.radians(spin_deg), [0, 0, 1])
        place = geom.rotation_about_y(HEAD_ANGLE_DEG, [px, 0.0, pz])
        turn = trimesh.transformations.rotation_matrix(math.radians(theta_deg), [0, 0, 1])
        return np.asarray(turn @ place @ spin)

    # ---- per head geometry (cached) -----------------------------------------------------------
    def _head_parts(self, h: heads.OutlineHeadSpec):
        """(head mesh in its frame with its own seat cut, seat cutter in its frame, prongs mesh, envelope)."""
        key = ("parts", id(h))
        if key not in self._cache:
            ph = self.placed_head(h)
            env = ph.seat.envelope()
            prongs = ph.prongs_mesh()
            mesh = heads.outline_head_mesh(ph.notebook_inputs(""), env, prongs)
            cutter = geom.offset_convex(env, ph.clearance)
            self._cache[key] = (mesh, cutter, prongs, env)
        return self._cache[key]

    def _placed(self, h, theta, spin, which: int):
        m = self._head_parts(h)[which].copy()
        m.apply_transform(self.matrix(h, theta, spin))
        return m

    def _girdle_points(self, h, theta, spin):
        import numpy as np
        xy = h.stone.outline(256)
        g = h.stone.girdle
        pts = np.vstack([np.column_stack([xy, np.full(len(xy), z), np.ones(len(xy))]) for z in (-g / 2, g / 2)])
        return (pts @ self.matrix(h, theta, spin).T)[:, :3]

    def _clear(self, a: tuple, b: tuple) -> bool:
        """Stones a and b, each (head, theta, spin): girdles side_gap_mm apart and neither seat
        cutting the other's head."""
        import trimesh
        from scipy.spatial import cKDTree
        d, _ = cKDTree(self._girdle_points(*b)).query(self._girdle_points(*a))
        if float(d.min()) < self.side_gap_mm:
            return False
        for (h1, t1, s1), (h2, t2, s2) in ((a, b), (b, a)):
            cut = self._placed(h1, t1, s1, 1)
            head = self._placed_rails(h2, t2, s2) if self.shared_prongs else self._placed(h2, t2, s2, 0)
            if not (cut.bounds[0] < head.bounds[1]).all() or not (head.bounds[0] < cut.bounds[1]).all():
                continue
            inter = trimesh.boolean.intersection([cut, head], engine="manifold")
            if len(inter.faces) and float(inter.volume) > CUT_ALLOWED_MM3:
                return False
        return True

    def girdle_gap(self, i: int, j: int) -> float:
        """Girdle to girdle between stones i and j of stones(), mm."""
        from scipy.spatial import cKDTree
        a, b = self.stones()[i], self.stones()[j]
        d, _ = cKDTree(self._girdle_points(b.head, b.theta_deg, b.spin_deg)).query(
            self._girdle_points(a.head, a.theta_deg, a.spin_deg))
        return float(d.min())

    def side_spin(self, theta_deg: float) -> float:
        """A side stone's length runs along the band; its point (the stone's -X) faces the centre
        (side_point "in") or away from it ("out"). In a row every stone is spun as the centre."""
        if self.row:
            return self.centre_spin_deg
        s = 90.0 if theta_deg > 0 else -90.0
        return s if self.side_point == "in" else -s

    # ---- the layout ---------------------------------------------------------------------------
    @staticmethod
    def _smallest_angle(ok, lo: float) -> float:
        """The smallest angle in (lo, lo + 90] at which ok(angle) holds (bisection to 0.0001°), a hair past it."""
        hi = lo + 90.0
        if not ok(hi):
            raise ValueError("no stone angle up to 90° clears its neighbour")
        for _ in range(30):
            mid = (lo + hi) / 2
            if ok(mid):
                hi = mid
            else:
                lo = mid
        return round(hi + 0.01, 3)

    def stones(self) -> list[Placed]:
        """The centre, then the side stones +Y and -Y outwards, each at its solved angle. In a row
        (`row` N): N stones of the centre's kind, one at the top when N is odd, the first pair either
        side of it - or, N even, the first pair straddling the top at the smallest angle that clears
        them of each other - each next one the smallest step on that clears its neighbour."""
        if "stones" in self._cache:
            return self._cache["stones"]
        if self.row:
            h, sp = self.centre, self.centre_spin_deg
            n = int(self.row)
            if n % 2:
                out, prev, pairs = [Placed(h, 0.0, sp, "centre")], (h, 0.0, sp), (n - 1) // 2
            else:
                t = self._smallest_angle(lambda x: self._clear((h, -x, sp), (h, x, sp)), 0.0)
                out, prev, pairs = [Placed(h, t, sp, "row")], (h, t, sp), n // 2 - 1
            for _ in range(pairs):
                t = self._smallest_angle(lambda x, prev=prev: self._clear(prev, (h, x, sp)), prev[1])
                out.append(Placed(h, t, sp, "row"))
                prev = (h, t, sp)
            for q in [q for q in out if q.theta_deg > 0]:
                out.append(Placed(h, -q.theta_deg, sp, "row"))
            self._cache["stones"] = out
            return out
        out = [Placed(self.centre, 0.0, self.centre_spin_deg, "centre")]
        if self.side is not None:
            prev = (self.centre, 0.0, self.centre_spin_deg)
            for _ in range(self.side_pairs):
                theta = self._smallest_angle(lambda t, prev=prev: self._clear(prev, (self.side, t, self.side_spin(t))), prev[1])
                out.append(Placed(self.side, theta, self.side_spin(theta), "side"))
                prev = (self.side, theta, self.side_spin(theta))
            for p in list(out[1:]):
                out.append(Placed(self.side, -p.theta_deg, self.side_spin(-p.theta_deg), "side"))
        self._cache["stones"] = out
        return out

    def neighbours(self) -> list[tuple[int, int]]:
        """Pairs of stones next to each other along the band (indices into stones(), in order of angle)."""
        st = self.stones()
        order = sorted(range(len(st)), key=lambda i: st[i].theta_deg)
        return [(order[k], order[k + 1]) for k in range(len(order) - 1)]

    # ---- the stones' own heads: their prongs (less the shared ones), parts, placement -------------
    def _rails_parts(self, h: heads.OutlineHeadSpec):
        """The head's rails alone with its seat cut (head frame): what a neighbour's seat may not touch
        when the prongs between them are shared."""
        key = ("rails", id(h))
        if key not in self._cache:
            import trimesh
            ph = self.placed_head(h)
            env = ph.seat.envelope()
            _, rails = heads.outline_head_parts(ph.notebook_inputs(""), env, ph.prongs_mesh())
            cutter = geom.offset_convex(env, ph.clearance)
            self._cache[key] = geom.clean(trimesh.boolean.difference([rails, cutter], engine="manifold"))
        return self._cache[key]

    def _placed_rails(self, h, theta, spin):
        m = self._rails_parts(h).copy()
        m.apply_transform(self.matrix(h, theta, spin))
        return m

    def _ring_knees(self, i: int):
        """Stone i's prong knees in the ring frame, with each prong's kind."""
        import numpy as np
        p = self.stones()[i]
        ph = self.placed_head(p.head)
        M = self.matrix(p.head, p.theta_deg, p.spin_deg)
        return [((M @ np.array([*knee, 1.0]))[:3], kind) for (_f, knee, _t), kind in zip(ph.prong_axes(), ph.point_kinds())]

    def facing_prongs(self, i: int, j: int) -> dict[int, int]:
        """{side (+1: +Z, -1: -Z): the index of stone i's prong that faces stone j on that side}: the
        prongs standing more than their own radius past stone i's centre line towards j. Refused
        unless there is exactly one round prong each side (a V-prong cannot be shared)."""
        st = self.stones()
        a, b = st[i], st[j]
        rho = self.placed_head(a.head).rho
        t = math.radians(a.theta_deg)
        sgn = 1.0 if b.theta_deg > a.theta_deg else -1.0
        out = {}
        for k, (kr, kind) in enumerate(self._ring_knees(i)):
            tang = -math.sin(t) * kr[0] + math.cos(t) * kr[1]
            if tang * sgn <= rho:
                continue
            side = 1 if kr[2] > 0 else -1
            if kind != "round":
                raise ValueError(f"stone {i + 1}'s prong facing stone {j + 1} is a V-prong: only round prongs are shared")
            if side in out:
                raise ValueError(f"stone {i + 1} has more than one prong facing stone {j + 1} on one side: shared prongs want "
                                 f"4-prong heads (one prong each side towards each neighbour)")
            out[side] = k
        if set(out) != {1, -1}:
            raise ValueError(f"stone {i + 1} has no prong facing stone {j + 1} on each side of the band")
        return out

    def posts(self) -> list[gallerymod.Post]:
        """The shared prongs, two per pair of neighbours (one each side of the band); [] without."""
        if not self.shared_prongs:
            return []
        if "posts" not in self._cache:
            out = []
            for i, j in self.neighbours():
                fi, fj = self.facing_prongs(i, j), self.facing_prongs(j, i)
                for side in (1, -1):
                    out.append(self._post(i, j, side, fi[side], fj[side]))
            self._cache["posts"] = out
        return self._cache["posts"]

    def _post(self, i: int, j: int, side: int, ki: int, kj: int) -> gallerymod.Post:
        """The post replacing stone i's prong ki and stone j's prong kj: solved for its place, its
        radius raised from the heads' prong radius until both seats leave the tip-floor of it."""
        import numpy as np
        from shapely.geometry import Polygon
        st = self.stones()
        pa, pb = st[i], st[j]
        ha, hb = self.placed_head(pa.head), self.placed_head(pb.head)
        Ma, Mb = self.matrix(pa.head, pa.theta_deg, pa.spin_deg), self.matrix(pb.head, pb.theta_deg, pb.spin_deg)
        ka, kb = self._ring_knees(i)[ki][0], self._ring_knees(j)[kj][0]
        theta0 = math.degrees((math.atan2(ka[1], ka[0]) + math.atan2(kb[1], kb[0])) / 2)
        z0 = float(ka[2] + kb[2]) / 2
        polys = [Polygon(ha.stone.outline(512)), Polygon(hb.stone.outline(512))]
        girdles = [ha.stone.girdle, hb.stone.girdle]
        cutters = [self._placed(pa.head, pa.theta_deg, pa.spin_deg, 1), self._placed(pb.head, pb.theta_deg, pb.spin_deg, 1)]
        b = self.band
        rho = max(ha.rho, hb.rho)
        while True:
            d = rho - min(ha.ledge_mm, hb.ledge_mm)
            theta, z = gallerymod.solve_post([Ma, Mb], polys, girdles, d, theta0, z0)
            r_at = [gallerymod.radial_point_at_head_z(M, theta, z, zh)[1]
                    for M, h in ((Ma, ha), (Mb, hb)) for zh in (h.z_tip, h.rails()["lower"][0])]
            r_tip, r_rails = max(r_at[0], r_at[2]), min(r_at[1], r_at[3])
            if abs(z) < b.width_mm / 2 - rho / 2:                    # over the band: its foot just inside the band's face
                r_foot = b.outer_radius_at(abs(z)) - gallerymod.POST_DEPTH_MM
            else:                                                    # past the band's edge: it stands in the heads' rails
                r_foot = r_rails + rho
            post = gallerymod.Post(i, j, side, theta, z, round(rho, 4), r_foot, r_tip)
            plane_r = max(gallerymod.radial_point_at_head_z(M, theta, z, h.stone.girdle / 2 + 0.15)[1]
                          for M, h in ((Ma, ha), (Mb, hb)))
            if gallerymod.post_tip_left(post, cutters, plane_r) >= heads.PRONG_TIP_FLOOR:
                return post
            rho += gallerymod.POST_RHO_STEP_MM
            if rho > gallerymod.POST_RHO_MAX_MM:
                raise ValueError(f"the post between stones {i + 1} and {j + 1} cannot keep a {heads.PRONG_TIP_FLOOR} mm tip "
                                 f"under both seats: more room between the stones (--side-gap)")

    def kept_prongs(self, i: int) -> list[int]:
        """Stone i's own prongs: all, less those that became posts."""
        n = len(self.placed_head(self.stones()[i].head).prong_axes())
        if not self.shared_prongs:
            return list(range(n))
        gone = set()
        for a, b in self.neighbours():
            for me, other in ((a, b), (b, a)):
                if me == i:
                    gone |= set(self.facing_prongs(me, other).values())
        return [k for k in range(n) if k not in gone]

    def stone_prongs(self, i: int):
        """Stone i's prongs mesh (head frame, what its Prongs Path holds): its kept prongs, or - all of
        them shared - a speck buried in the band under it, which the head block and the ring take in
        and lose."""
        key = ("prongs", i)
        if key not in self._cache:
            p = self.stones()[i]
            ph = self.placed_head(p.head)
            keep = self.kept_prongs(i)
            if len(keep) == len(ph.prong_axes()):
                mesh = self._head_parts(p.head)[2]
            elif keep:
                mesh = ph.prongs_mesh(keep)
            else:
                import trimesh
                from .artwork import SPECK_MM
                mesh = trimesh.creation.box(extents=(SPECK_MM, SPECK_MM, SPECK_MM))
                mesh.apply_translation([0.0, 0.0, self.band.bore_radius_mm + self.band.thickness_mm / 2 - self.girdle_radius(p.head)])
            self._cache[key] = mesh
        return self._cache[key]

    def _stone_parts(self, i: int):
        """(head mesh with its own seat cut, seat cutter, prongs, envelope), head frame, for stone i."""
        p = self.stones()[i]
        if not self.shared_prongs:
            return self._head_parts(p.head)
        key = ("stone_parts", i)
        if key not in self._cache:
            ph = self.placed_head(p.head)
            env = ph.seat.envelope()
            prongs = self.stone_prongs(i)
            mesh = heads.outline_head_mesh(ph.notebook_inputs(""), env, prongs)
            self._cache[key] = (mesh, geom.offset_convex(env, ph.clearance), prongs, env)
        return self._cache[key]

    def placed_stone(self, i: int, which: int = 0):
        """Stone i's head (0) or seat cutter (1) on the ring."""
        p = self.stones()[i]
        m = self._stone_parts(i)[which].copy()
        m.apply_transform(self.matrix(p.head, p.theta_deg, p.spin_deg))
        return m

    def stone_knees(self, i: int) -> list[tuple[float, float, float]]:
        """[(x, y, radius)] in stone i's head frame: where each prong holding it meets its girdle - its
        kept prongs' knees and, for each post beside it, the post's axis at the girdle's underside."""
        p = self.stones()[i]
        ph = self.placed_head(p.head)
        axes = ph.prong_axes()
        out = [(float(axes[k][1][0]), float(axes[k][1][1]), ph.rho) for k in self.kept_prongs(i)]
        M = self.matrix(p.head, p.theta_deg, p.spin_deg)
        for q in self.posts():
            if i in (q.a, q.b):
                pt, _ = gallerymod.radial_point_at_head_z(M, q.theta_deg, q.z, -p.head.stone.girdle / 2)
                out.append((float(pt[0]), float(pt[1]), q.rho))
        return out

    # ---- the gallery bridge ---------------------------------------------------------------------------
    def gallery_rails(self):
        """The bridge: one rail each side of the band through the stones' upper-rail sections (ring frame)."""
        if "gallery" not in self._cache:
            import trimesh
            st = self.stones()
            corner = min(self.centre.blend, (self.side or self.centre).blend)
            rails = []
            for side in (1, -1):
                secs = []
                for p in st:
                    sec = gallerymod.rail_section(self._placed_rails(p.head, p.theta_deg, p.spin_deg), p.theta_deg, side)
                    if sec is None:
                        raise ValueError(f"no upper rail under the stone at {p.theta_deg:.1f}° on the {'+' if side > 0 else '-'}Z side")
                    secs.append(sec)
                rails.append(gallerymod.bridge_rail(secs, corner))
            self._cache["gallery"] = trimesh.util.concatenate(rails)
        return self._cache["gallery"]

    def gallery_probes(self) -> list[tuple]:
        """Where to look for the bridge on a built ring: per pair of neighbours and side, the ray (from
        outside, towards the axis) nearest mid-way between them along which the bridge is the outermost
        metal of the design - (i, j, side, origin, direction, distance to the design's surface)."""
        if "gallery_probes" in self._cache:
            return self._cache["gallery_probes"]
        import numpy as np
        st = self.stones()
        rails, design = self.gallery_rails(), self.design_mesh()
        out = []
        for i, j in self.neighbours():
            a, b = st[i], st[j]
            for side in (1, -1):
                secs = [gallerymod.rail_section(self._placed_rails(x.head, x.theta_deg, x.spin_deg), x.theta_deg, side) for x in (a, b)]
                best = None
                for f in sorted(np.linspace(0.05, 0.95, 19), key=lambda f: abs(f - 0.5)):
                    th = a.theta_deg + f * (b.theta_deg - a.theta_deg)
                    r1 = secs[0].r1 + f * (secs[1].r1 - secs[0].r1)
                    z = (secs[0].z0 + secs[0].z1) / 2 + f * ((secs[1].z0 + secs[1].z1) / 2 - (secs[0].z0 + secs[0].z1) / 2)
                    t = math.radians(th)
                    u = np.array([math.cos(t), math.sin(t), 0.0])
                    origin, direction = u * (r1 + 3.0) + np.array([0.0, 0.0, z]), -u
                    hr, _, _ = rails.ray.intersects_location([origin], [direction], multiple_hits=False)
                    hd, _, _ = design.ray.intersects_location([origin], [direction], multiple_hits=False)
                    if len(hr) and len(hd) and np.linalg.norm(hr[0] - hd[0]) < 0.02:
                        best = (i, j, side, origin, direction, float(np.linalg.norm(hd[0] - origin)))
                        break
                if best is not None:
                    out.append(best)
        self._cache["gallery_probes"] = out
        return out

    def gallery_layers(self):
        """(gallery, shared prongs) meshes for the notebook: the bridge rails and the posts, or the
        no-op specks buried in the band."""
        import trimesh
        from . import artwork as artmod
        g = self.gallery_rails() if self.gallery else artmod.buried_speck(self.band)
        posts = trimesh.util.concatenate([q.mesh() for q in self.posts()]) if self.shared_prongs else artmod.buried_speck(self.band)
        return g, posts

    def write_gallery_layers(self, directory: Path, stem: str) -> tuple[str, str]:
        """Write both layers and read each back: a layer with crossing faces (as nTop would read them,
        float32) is refused - it would import as self-intersecting."""
        import trimesh
        directory = Path(directory)
        paths = (directory / f"{stem}.gallery.stl", directory / f"{stem}.shared_prongs.stl")
        for mesh, path in zip(self.gallery_layers(), paths):
            mesh.export(str(path))
            back = trimesh.load(str(path), force="mesh")
            bad = geom.intersecting_faces(back)
            if len(bad):
                raise ValueError(f"{path.name}: {len(bad)} pairs of faces cross (nTop would import it as self-intersecting)")
        return str(paths[0]), str(paths[1])

    def placed_heads_mesh(self, which: int = 0):
        """Every placed head (0) or seat cutter (1), concatenated (they may overlap: for looking only)."""
        import trimesh
        return trimesh.util.concatenate([self.placed_stone(i, which) for i in range(len(self.stones()))])

    @property
    def head_span_deg(self) -> float:
        """How far from the top the outermost stone's head reaches (deg)."""
        import numpy as np
        v = self.placed_heads_mesh(0).vertices
        return float(np.degrees(np.abs(np.arctan2(v[:, 1], v[:, 0]))).max())

    # ---- pavé round the rest of the ring ----------------------------------------------------------
    @property
    def has_pave(self) -> bool:
        return bool(self.pave_stone_mm)

    def head_face_reach_deg(self) -> float:
        """How far from the top the heads' metal (and their seat cutters) reach at the band's outer
        surface: the angle the pavé must clear (less than head_span_deg, the prongs' splay above)."""
        import numpy as np
        if "face_reach" not in self._cache:
            ro = self.band.outer_radius_mm
            reach = 0.0
            for which in (0, 1):
                v = self.placed_heads_mesh(which).vertices
                near = np.hypot(v[:, 0], v[:, 1]) <= ro + 0.3
                if near.any():
                    reach = max(reach, float(np.degrees(np.abs(np.arctan2(v[near, 1], v[near, 0]))).max()))
            self._cache["face_reach"] = reach
        return self._cache["face_reach"]

    def pave_start_deg(self) -> float:
        """Where the pavé's first girdle edge may be, from the top: as asked, or past the heads' reach
        at the surface by PAVE_HEAD_CLEAR_MM and the shank blend (the smooth union's fillet round the
        heads' feet)."""
        if self.pave_from_deg:
            return float(self.pave_from_deg)
        ro = self.band.outer_radius_mm
        return self.head_face_reach_deg() + math.degrees((PAVE_HEAD_CLEAR_MM + self.shank_blend) / ro)

    @property
    def pave(self):
        """The pavé (pave.PaveSpec) over the shank, centred on the bottom, its arc ending where
        pave_start_deg says (the first stone's centre a girdle radius + clearance further on); None without."""
        if not self.has_pave:
            return None
        if "pave" not in self._cache:
            from . import pave as pavemod
            probe = pavemod.PaveSpec(self.shank_spec, stone_mm=self.pave_stone_mm, rows=self.pave_rows, layout=self.pave_layout,
                                     span_deg=10.0, centre_deg=180.0, material=self.pave_material)
            edge = math.degrees((probe.girdle_radius + probe.clearance) / self.band.outer_radius_mm)
            span = 2.0 * (180.0 - self.pave_start_deg() - edge)
            self._cache["pave"] = pavemod.PaveSpec(self.shank_spec, stone_mm=self.pave_stone_mm, rows=self.pave_rows,
                                                   layout=self.pave_layout, span_deg=round(span, 3), centre_deg=180.0,
                                                   material=self.pave_material)
        return self._cache["pave"]

    def pave_layers(self):
        """(beads, seats) meshes for the notebook: the pavé's, or the no-op specks."""
        from . import artwork as artmod
        if not self.has_pave:
            return artmod.buried_speck(self.band), artmod.outside_speck(self.band)
        return self.pave.beads_mesh(), self.pave.seats_mesh()

    def write_pave_layers(self, directory: Path, stem: str) -> tuple[str, str]:
        directory = Path(directory)
        beads, seats = directory / f"{stem}.pave_beads.stl", directory / f"{stem}.pave_seats.stl"
        b, c = self.pave_layers()
        b.export(str(beads))
        c.export(str(seats))
        return str(beads), str(seats)

    # ---- notebook ----------------------------------------------------------------------------
    def slot_values(self, p: Placed, seat_path: str, prongs_path: str) -> dict:
        ph = self.placed_head(p.head)
        ins = ph.notebook_inputs(seat_path, prongs_path)
        px, pz = self.pivot(p.head)
        return {"Seat Path": seat_path, "Prongs Path": prongs_path,
                **{k: ins[k] for k in ("Rail Offset", "Upper Rail Bottom", "Upper Rail Top", "Lower Rail Bottom", "Lower Rail Top")},
                "Spin": round(p.spin_deg, 4), "Pivot X": round(px, 4), "Pivot Z": round(pz, 4), "Turn": round(p.theta_deg, 4)}

    def notebook_inputs(self, shank_paths, slot_files: list[tuple[str, str]], output_path: str = "",
                        pave_paths: tuple[str, str] = ("<pave beads path>", "<pave seats path>"),
                        gallery_paths: tuple[str, str] = ("<gallery path>", "<shared prongs path>")) -> dict:
        """`slot_files`: (seat envelope path, prongs path) per stone, in stones() order."""
        sh = self.shank_spec.notebook_inputs(shank_paths, "")
        v = {k: sh[k] for k in (*shankmod.SLOT_NAMES, "Wrap Length", "Edge Round", "Edge Round Inward", "Mesh Tolerance")}
        c = self.centre.clearance
        v.update({"Clearance": round(c, 4), "Head Blend": round(self.centre.blend, 4), "Shank Blend": round(self.shank_blend, 4)})
        stones = self.stones()
        for k in range(SLOTS):
            p = stones[k] if k < len(stones) else stones[0]                   # unused: the centre again
            seat, prongs = slot_files[k] if k < len(stones) else slot_files[0]
            for name, val in self.slot_values(p, seat, prongs).items():
                v[slot_input(name, k)] = val
        v["Pave Beads Path"], v["Pave Seats Path"] = str(pave_paths[0]), str(pave_paths[1])
        v["Gallery Path"], v["Shared Prongs Path"] = str(gallery_paths[0]), str(gallery_paths[1])
        v["Output Path"] = str(output_path)
        return v

    def write_slot_files(self, directory: Path, stem: str) -> list[tuple[str, str]]:
        """Each distinct head's seat envelope and prongs (head frame) once; a path pair per stone. With
        shared prongs every stone keeps different prongs: one prongs file per stone."""
        directory = Path(directory)
        out, envs, done = [], {}, {}
        for i, p in enumerate(self.stones()):
            role = p.role
            if role not in envs:
                env = directory / f"{stem}.{role}.envelope.stl"
                self.placed_head(p.head).seat.envelope().export(str(env))
                envs[role] = str(env)
            key = f"stone{i + 1}" if self.shared_prongs else role
            if key not in done:
                prongs = directory / f"{stem}.{key}.prongs.stl"
                self.stone_prongs(i).export(str(prongs))
                done[key] = str(prongs)
            out.append((envs[role], done[key]))
        return out

    # ---- identity ----------------------------------------------------------------------------
    def design(self) -> dict:
        d = self.shank_spec.design()
        d.update({"centre": self.placed_head(self.centre).design(),
                  "side": self.placed_head(self.side).design() if self.side is not None else None,
                  "side_pairs": self.side_pairs if self.side is not None else 0, "side_gap": self.side_gap_mm,
                  "centre_spin": self.centre_spin_deg, "finger_clear": self.finger_clear, "shank_blend": self.shank_blend})
        if self.side_point != "in":                                   # only when set: earlier designs keep their ids
            d["side_point"] = self.side_point
        if self.row:
            d["row"] = int(self.row)
        if self.shared_prongs:
            d["shared_prongs"] = [q.design() for q in self.posts()]
        if self.gallery:
            d["gallery"] = True
        if self.has_pave:
            pv = self.pave.design()
            d["pave"] = {k: v for k, v in pv.items() if k.startswith("pave_") or k == "seat_clearance"}
        return d

    @property
    def spec_id(self) -> str:
        return runs.spec_id(self.design())

    @staticmethod
    def _short(s: gems.StoneSpec) -> str:
        dims = f"{s.length:g}" if s.shape in gems.ONE_SIZE + gems.SQUARE else f"{s.length:g}x{s.width:g}"
        return f"{s.shape}{dims}".replace(".", "p")

    @property
    def stem(self) -> str:
        side = f"_{self._short(self.side.stone)}" if self.side is not None else ""
        pave = f"_pave{self.pave_rows}x{self.pave_stone_mm:g}".replace(".", "p") if self.has_pave else ""
        extra = ("_row" if self.row else "") + ("_shared" if self.shared_prongs else "") + ("_gallery" if self.gallery else "")
        return f"ring_multi_{self.stone_count}_{self._short(self.centre.stone)}{side}{extra}{pave}_{self.band.label}_{self.spec_id}"

    @property
    def catalog_name(self) -> str:
        return "multistone"

    # ---- the independent ring -------------------------------------------------------------------
    def design_mesh(self, ops: geom.Booleans = geom.SHARP):
        """shank ∪ every placed head, then every placed seat cut (sharp unless `ops` blends)."""
        key = "design_mesh" if ops is geom.SHARP else None
        if key is None or key not in self._cache:
            n = len(self.stones())
            hs = [self.placed_stone(i, 0) for i in range(n)]
            cuts = [self.placed_stone(i, 1) for i in range(n)]
            shank = self.shank_spec.design_mesh()
            if self.has_pave:                                             # the beads join the shank before the heads
                import trimesh
                shank = trimesh.boolean.union([shank, self.pave.beads_mesh()], engine="manifold")
                cuts = cuts + [self.pave.seats_mesh()]
            ring = ops.union([shank, ops.union([*hs, *self.gallery_bodies()])], self.shank_blend)
            mesh = ops.clean(ops.difference(ring, cuts))
            if key is None:
                return mesh
            self._cache[key] = mesh
        return self._cache[key]

    def gallery_bodies(self) -> list:
        """What the heads' union takes besides the heads: the bridge rails and the posts (none without)."""
        out = []
        if self.gallery:
            out.append(self.gallery_rails())
        if self.shared_prongs:
            import trimesh
            out.append(trimesh.util.concatenate([q.mesh() for q in self.posts()]))
        return out

    def blend_volume_mm3(self) -> float:
        """What the blends add: each head's own (prongs into rails, the rails' edges), plus the
        heads-into-shank union along its exposed junction."""
        est = 0.0
        for i, p in enumerate(self.stones()):
            ph = self.placed_head(p.head)
            est += (ph.blend_volume_mm3() if not self.shared_prongs
                    else heads.blend_estimate(ph.notebook_inputs(""), ph.seat.envelope(), self.stone_prongs(i)))
        if self.shank_blend > 0:
            import trimesh
            n = len(self.stones())
            hs = trimesh.boolean.union([self.placed_stone(i, 0) for i in range(n)] + self.gallery_bodies(), engine="manifold")
            cuts = [self.placed_stone(i, 1) for i in range(n)]
            seg = geom.exposed_segments(geom.junction_segments(self.shank_spec.design_mesh(), hs), *cuts)
            est += geom.blend_volume_mm3(self.shank_blend, geom.segments_length(seg))
        return est

    # ---- checks on the design -------------------------------------------------------------------
    def validate(self) -> list[str]:
        p = list(self.shank_spec.validate())
        for role, h in (("centre", self.centre), ("side", self.side)):
            if h is None:
                continue
            p += [f"{role}: {x}" for x in self.placed_head(h).validate()]
        if p:
            return p
        if self.side_point not in ("in", "out"):
            p.append(f"side point {self.side_point!r}: in or out")
        if self.stone_count > SLOTS:
            p.append(f"{self.stone_count} stones: the notebook has {SLOTS} head slots")
        if self.side is not None and self.side_pairs < 1:
            p.append("side pairs: at least 1 with a side stone")
        if self.row and self.side is not None:
            p.append("a row is stones of one kind (the centre's): no side stone with --row")
        if self.row and not 2 <= int(self.row) <= SLOTS:
            p.append(f"a row of {self.row}: 2 to {SLOTS} stones (the notebook's head slots)")
        if (self.shared_prongs or self.gallery) and self.stone_count < 2:
            p.append("shared prongs and a gallery join neighbouring stones: at least two")
        if self.side is not None and self.side.clearance != self.centre.clearance:
            p.append("centre and side stones share one seat clearance (the notebook's Clearance)")
        if self.side is not None and self.side.blend != self.centre.blend:
            p.append("centre and side heads share one head blend (the notebook's Head Blend)")
        sh = self.shank_spec
        if sh.rope or sh.knot or sh.strands > 1 or sh.split_mm:
            p.append("a multi-stone ring sits on a plain or tapered shank (no rope, knot, double band or split yet)")
        if p:
            return p
        try:
            stones = self.stones()
            self.posts()
            if self.gallery:
                self.gallery_rails()
        except ValueError as e:
            return [str(e)]
        span = self.head_span_deg
        if sh.tapered and span > sh.taper_from_deg:
            p.append(f"the heads reach {span:.0f}° from the top, past where the taper begins ({sh.taper_from_deg:g}°)")
        if span > 100.0:
            p.append(f"the heads reach {span:.0f}° from the top: fewer or smaller side stones")
        if self.has_pave and not p:
            pv = self.pave
            if sh.tapered:
                p.append("pavé round a multi-stone ring wants the same section all round (no taper)")
            elif pv.span_deg < 2 * pv.pitch_deg:
                p.append(f"the heads leave {pv.span_deg:.0f}° for the pavé: too little for a row")
            else:
                p += [f"pavé: {x}" for x in pv.validate()]
            if not p:
                import trimesh
                hs = trimesh.boolean.union([self.placed_stone(i, 0) for i in range(len(stones))], engine="manifold")
                cut = trimesh.boolean.intersection([hs, pv.seats_mesh()], engine="manifold")
                if len(cut.faces) and cut.volume > CUT_ALLOWED_MM3:
                    p.append(f"the pavé's seats cut {cut.volume:.3f} mm³ from the side heads: start it later (--pave-from)")
        return p

    def warnings(self) -> list[str]:
        return list(self.shank_spec.warnings())

    def carats(self) -> float:
        return sum(p.head.stone.carats() for p in self.stones()) + (self.pave.carats() if self.has_pave else 0.0)

    def describe(self) -> str:
        b = self.band
        lines = [f"{self.stem}: {b.label}, inner Ø {b.inner_diameter_mm:.3f}, {b.profile} {b.width_mm:g} x {b.thickness_mm:g} mm"]
        for i, p in enumerate(self.stones()):
            if p.role in ("side", "row") and p.theta_deg < 0:
                continue
            s = p.head.stone
            where = "at the top" if p.role == "centre" else (f"at ±{p.theta_deg:.2f}° (spun {abs(p.spin_deg):g}°"
                                                             + (f", point {'inward' if self.side_point == 'in' else 'outward'})"
                                                                if p.head.stone.shape in ("pear", "marquise") else ")"))
            held = (f"held by {len(self.stone_knees(i))} prongs ({len(self.kept_prongs(i))} its own, the rest shared)"
                    if self.shared_prongs else f"in {self.placed_head(p.head).count} prongs")
            lines.append(f"  {p.role}: {s.describe()} {held}, {where}; "
                         f"girdle at r {self.girdle_radius(p.head):.3f}")
        gaps = ""
        if self.stone_count > 1:
            g = [self.girdle_gap(i, j) for i, j in self.neighbours()]
            g = g[len(g) // 2:]                                              # symmetric: from the top out
            what = "rails" if self.shared_prongs else "prongs"
            gaps = (f"girdles {', '.join(f'{x:.2f}' for x in g)} mm apart from the top out (at least {self.side_gap_mm:g}; "
                    f"each angle the smallest at which no seat cuts a neighbour's {what}); ")
        lines.append(f"  {self.stone_count} stones, {self.carats():.2f} ct; {gaps}heads reach ±{self.head_span_deg:.1f}°; "
                     f"culets at least {self.finger_clear:g} mm above the bore")
        if self.has_pave:
            pv = self.pave
            rows = ", ".join(str(len(pv.row_columns(r))) for r in range(pv.rows))
            lines.append(f"  pavé: {pv.stone_count} round {pv.material} stones of {pv.stone_mm:g} mm ({pv.carats():.2f} ct), "
                         f"{pv.rows} row{'s' if pv.rows > 1 else ''} ({rows}) round the bottom from ±{pv.reach_from_top_deg:.1f}° "
                         f"(the heads' metal at the surface reaches ±{self.head_face_reach_deg():.1f}°), {len(pv.beads())} beads "
                         f"of Ø {2 * pv.bead_radius:.2f} mm")
        if self.shared_prongs:
            ps = self.posts()
            own = [len(self.kept_prongs(i)) for i in range(len(self.stones()))]
            lines.append(f"  shared prongs: {len(ps)} posts of Ø {2 * max(q.rho for q in ps):.2f} mm between neighbours (one each side "
                         f"of the band); the stones keep {', '.join(map(str, own))} prongs of their own")
        if self.gallery:
            lines.append(f"  gallery: a bridge rail each side of the band at the heads' upper rails, "
                         f"±{max(abs(p.theta_deg) for p in self.stones()):.1f}° from the top")
        lines.append(f"  blends: head {self.centre.blend:g} mm, heads into shank {self.shank_blend:g} mm")
        return "\n".join(lines)


# ---- from the notebook's numbers (the simulated nTop) ---------------------------------------------
def ring_from_inputs(v: dict, ops: geom.Booleans = geom.SHARP):
    """The ring the notebook builds from its input values: the shank's bars wrapped and united;
    every slot's outline head (from its seat envelope, prongs and rail numbers, blended by Head
    Blend), spun, placed and turned; shank ∪ heads blended by Shank Blend; every placed seat cut."""
    import trimesh
    shank = shankmod.bars_from_inputs(v)
    hs, cuts = [], []
    for k in range(SLOTS):
        def g(name):
            return v[slot_input(name, k)]
        env = trimesh.load(str(g("Seat Path")), force="mesh")
        prongs = trimesh.load(str(g("Prongs Path")), force="mesh")
        hv = {"Clearance": v["Clearance"], "Blend Radius": v["Head Blend"],
              **{n: g(n) for n in ("Rail Offset", "Upper Rail Bottom", "Upper Rail Top", "Lower Rail Bottom", "Lower Rail Top")}}
        head = heads.outline_head_mesh(hv, env, prongs, ops=ops)
        cutter = geom.offset_convex(env, float(v["Clearance"]))
        spin = trimesh.transformations.rotation_matrix(math.radians(float(g("Spin"))), [0, 0, 1])
        place = geom.rotation_about_y(HEAD_ANGLE_DEG, [float(g("Pivot X")), 0.0, float(g("Pivot Z"))])
        turn = trimesh.transformations.rotation_matrix(math.radians(float(g("Turn"))), [0, 0, 1])
        m = turn @ place @ spin
        head = head.copy(); head.apply_transform(m)
        cutter = cutter.copy(); cutter.apply_transform(m)
        hs.append(head)
        cuts.append(cutter)
    if v.get("Pave Beads Path"):                                       # 0.2.0: the pavé (or its no-op specks)
        beads = trimesh.load(str(v["Pave Beads Path"]), force="mesh")
        shank = trimesh.boolean.union([shank, beads], engine="manifold")
        cuts.append(trimesh.load(str(v["Pave Seats Path"]), force="mesh"))
    extra = []
    if v.get("Gallery Path"):                                          # 0.3.0: the bridge and the shared prongs (or specks)
        extra = [geom.clean(trimesh.load(str(v[k]), force="mesh")) for k in ("Gallery Path", "Shared Prongs Path")]
    ring = ops.union([shank, ops.union([*hs, *extra])], float(v["Shank Blend"]))
    return ops.clean(ops.difference(ring, cuts))


# ---- the gate -------------------------------------------------------------------------------------
def prong_ledges(local, head: heads.OutlineHeadSpec, z: float, under, knees=None) -> int:
    """How many of the head's prongs carry metal under the girdle, prong by prong: the section at
    height z (head frame) near each prong's knee overlapping the girdle region. Counting separate
    pieces (heads.outline_count, the solitaire's way) undercounts here: a side stone's prongs fuse
    with the neighbouring head's metal into one piece (two pear prongs read as one, 2026-11-03).
    `knees`: [(x, y, radius)] in the head frame - the stone's kept prongs and the shared posts
    beside it (MultiStoneSpec.stone_knees); default the head's own prongs."""
    import numpy as np
    from shapely.geometry import Point, Polygon
    sec = local.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    if sec is None:
        return 0
    planar, to3d = sec.to_2D()

    def lift(coords):
        pts = np.asarray(coords)
        return (to3d @ np.column_stack([pts, np.zeros(len(pts)), np.ones(len(pts))]).T).T[:, :2]
    pieces = [Polygon(lift(q.exterior.coords), [lift(h.coords) for h in q.interiors]).buffer(0) for q in planar.polygons_full]
    count = 0
    knees = knees if knees is not None else [(float(k[0]), float(k[1]), head.rho) for (_f, k, _t) in head.prong_axes()]
    for (kx, ky, rho) in knees:
        near = Point(kx, ky).buffer(rho + 0.05)
        if any(pc.intersection(near).intersection(under).area > 1e-4 for pc in pieces):
            count += 1
    return count


def rail_corner_shrink(h: heads.OutlineHeadSpec) -> float:
    """How far a blended rail's outermost edge may retreat, each side: the rails follow the pavilion,
    so the corner between a rail's top and its outer face is acute (90° less the pavilion's lean from
    vertical, 41° on an ideal round), and rounding a corner of angle a by r takes its tip back by
    r (1/sin(a/2) - 1) - 0.56 mm at r 0.3 against r (√2 - 1) on a square corner. The real three-stone
    came out 0.225 mm a side narrower along the finger than the sharp design (2026-11-03), where the
    square-corner allowance gave 0.2."""
    _, pav = h.stone.heights
    lean = math.atan((max(h.stone.length, h.stone.width) / 2) / pav)
    a = math.pi / 2 - lean
    return max(h.blend, h.blend * (1 / math.sin(a / 2) - 1))


def check_multistone(spec: MultiStoneSpec, stl: Path, ntop_vol: float | None) -> gate.GateReport:
    """The shank's checks away from the heads (walls, section shape, bore), the bore closed under
    every stone, extents against the design, the design volume with the blends' estimate, and per
    stone in its own frame: it fits, its prongs reach under its girdle, its drop-in path is clear."""
    import numpy as np
    import trimesh
    b = spec.band
    sh = spec.shank_spec
    span = spec.head_span_deg + 8.0

    def far(a):
        return abs((float(a) + 180.0) % 360.0 - 180.0) > span

    pv = spec.pave
    pave_keep = pv.wall_ray_filter() if pv is not None else None

    def shank_rays(pts, n):
        ok = np.array([far(math.degrees(math.atan2(p[1], p[0]))) for p in pts])
        if pave_keep is not None:                                     # a seat's wall measures the web to the next seat
            ok &= pave_keep(pts, n)
        return ok

    def shank_section(a):
        if not far(a):
            return None
        if pv is not None and pv.in_pave(a):                          # through the pavé: the design's own section
            return gate.section_geometry(spec.design_mesh(), a)
        return sh.gate_section(a)

    def section_tol(a):
        if pv is not None and pv.in_pave(a):
            return pv.section_tolerance(a)
        return sh.section_tolerance(a)
    rep = gate.check(stl, expect_volume=ntop_vol, wall_floor=sh.wall_floor(), wall_ray_filter=shank_rays,
                     section_design=shank_section, section_tol_mm=section_tol, centre="origin")
    ring = gate.load_mesh(stl)
    r = np.hypot(ring.vertices[:, 0], ring.vertices[:, 1])
    bore = 2 * float(r.min())
    rep.checks.append(gate.Check("bore", abs(bore - b.inner_diameter_mm) <= 0.05,
                                 f"Ø {bore:.3f} vs {b.inner_diameter_mm:.3f} mm (about the ring axis)"))
    stones = spec.stones()
    closed = []
    for p in stones:
        t = math.radians(p.theta_deg)
        hits, _, _ = ring.ray.intersects_location([[0.0, 0.0, 0.0]], [[math.cos(t), math.sin(t), 0.0]], multiple_hits=False)
        first = float(np.hypot(hits[0][0], hits[0][1])) if len(hits) else float("inf")
        closed.append(abs(first - b.bore_radius_mm) <= 0.1)
    rep.checks.append(gate.Check("bore closed under the stones", all(closed),
                                 f"{sum(closed)}/{len(stones)}: from the axis towards each stone, metal starts at the bore"))
    design = spec.design_mesh()
    d = np.array(rep.extents_mm) - np.array(design.extents)
    tol = max(0.1, 2 * spec.centre.mesh_tolerance_mm)
    shrink = tol + 2 * max(rail_corner_shrink(p.head) for p in stones)
    rep.checks.append(gate.Check("extents", bool(np.all(d <= tol) and np.all(d >= -shrink)),
                                 " x ".join(f"{x:.2f}" for x in rep.extents_mm) + " vs design "
                                 + " x ".join(f"{x:.2f}" for x in design.extents) + f" mm (+{tol:.2f} / -{shrink:.2f})"))
    fits, ledges, drops, holds = [], [], [], {}
    for p in stones:
        local = ring.copy()
        local.apply_transform(np.linalg.inv(spec.matrix(p.head, p.theta_deg, p.spin_deg)))
        stone = p.head.stone.mesh()
        inter = trimesh.boolean.intersection([local, stone], engine="manifold") if local.is_watertight else None
        overlap = float(inter.volume) if inter is not None and len(inter.faces) else (0.0 if inter is not None else float("nan"))
        fits.append((overlap, 0.002 * stone.volume))
        under, over = heads.seat_regions(p.head.stone, p.head.clearance)
        g = p.head.stone.girdle
        knees = spec.stone_knees(stones.index(p))
        ph = spec.placed_head(p.head)
        if ph.kind == "faceted":
            ledges.append((prong_ledges(local, ph, -g / 2 - 0.3, under, knees), len(knees)))
        else:                                                         # a cabochon's plate, a pearl's cup and post, the prongs
            for c in heads.hold_checks(ph, local, knees):
                holds.setdefault(c.name, []).append(c)
        drops.append(heads.outline_count(local, g / 2 + 0.15, over))
    bad = [i for i, (o, a) in enumerate(fits) if not o <= a]
    rep.checks.append(gate.Check("stones fit", not bad, f"{len(stones) - len(bad)}/{len(stones)} stones clear of the metal "
                                 f"(worst ∩ {max(o for o, _ in fits):.3f} mm³)"))
    if ledges:
        bad = [i for i, (n, want) in enumerate(ledges) if n < want]
        rep.checks.append(gate.Check("seat ledges", not bad, "every faceted stone: " + ", ".join(f"{n}/{w}" for n, w in ledges)
                                     + " prongs reach under the girdle"))
    for name, cs in holds.items():                                    # the unfaceted stones' holds, one check each
        rep.checks.append(gate.Check(name, all(c.ok for c in cs), "; ".join(c.detail for c in cs)))
    rep.checks.append(gate.Check("drop-in clear", not any(drops), f"{sum(drops)} pieces inside a girdle line above its girdle"))
    mtol = spec.centre.mesh_tolerance_mm
    if spec.shared_prongs:                                            # what both seats leave of each post above the girdles
        left = []
        for q in spec.posts():
            a, bb = stones[q.a], stones[q.b]
            plane_r = max(gallerymod.radial_point_at_head_z(spec.matrix(x.head, x.theta_deg, x.spin_deg), q.theta_deg, q.z,
                                                            x.head.stone.girdle / 2 + 0.15)[1] for x in (a, bb))
            left.append(gallerymod.section_inscribed_dia(ring, q.theta_deg, q.z, plane_r))
        floor = heads.PRONG_TIP_FLOOR - mtol
        worst = min(range(len(left)), key=lambda k: left[k])
        rep.checks.append(gate.Check("shared prong tips", all(x >= floor for x in left),
                                     f"{sum(x >= floor for x in left)}/{len(left)} posts keep Ø {floor:.2f} mm above both girdles "
                                     f"(thinnest {left[worst]:.2f} mm, post {worst + 1} at {spec.posts()[worst].theta_deg:.1f}°)"))
    if spec.gallery:                                                  # the bridge under every gap, both sides
        found, missing = 0, []
        for i, j, side, origin, direction, want in spec.gallery_probes():
            hits, _, _ = ring.ray.intersects_location([origin], [direction], multiple_hits=False)
            got = float(np.linalg.norm(hits[0] - origin)) if len(hits) else float("inf")
            if abs(got - want) <= 0.15 + mtol:
                found += 1
            else:
                missing.append(f"{i + 1}-{j + 1}{'+' if side > 0 else '-'}")
        n = 2 * len(spec.neighbours())
        rep.checks.append(gate.Check("gallery", found == n and n > 0,
                                     f"{found}/{n} bridge rails found where the design shows them (within 0.15 mm)"
                                     + (f"; missing between stones {', '.join(missing)}" if missing else "")))
    if pv is not None:                                                # the pavé's seats, holes, beads, held stones
        from . import pave as pavemod
        for c in pavemod.pave_checks(pv, ring):
            c.name = f"pavé {c.name}"
            rep.checks.append(c)
    from .band import blended_design_volume_check
    overcut = sh.opening_overcut_mm3() + sh.sharp_edge_round_mm3()
    c = blended_design_volume_check(float(design.volume) - overcut, spec.blend_volume_mm3(), ntop_vol, 3.0)
    if overcut and c.status != gate.INCOMPLETE:
        c.detail += f" [less {overcut:.2f} mm³ nTop's opening takes off the shank's rounds]"
    rep.checks.append(c)
    return rep


@dataclass
class MultiStoneResult:
    spec: MultiStoneSpec
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


def build(spec: MultiStoneSpec, out_dir: Path | None = None, *, notebook: Path | None = None,
          catalog_name: str = "multistone", deliver: bool = False, deliver_project: str = "Multistone",
          cast_metal: str | None = None) -> MultiStoneResult:
    """Write the bars and every head's envelope and prongs, run multistone.ntop, gate the ring."""
    problems = spec.validate()
    if problems:
        raise ValueError("; ".join(problems))
    cat = catalog.load(catalog_name)
    nb = Path(notebook) if notebook else cat.notebook
    built_notes = runs.require_built(cat, nb) if not notebook else []
    run_dir, run_id = runs.fresh_run_dir(Path(out_dir) if out_dir else config.out_dir() / "multistone", spec.stem)
    stl = run_dir / f"{spec.stem}.stl"
    bars = shankmod.write_bars(spec.shank_spec, run_dir, spec.stem)
    files = spec.write_slot_files(run_dir, spec.stem)
    pave_paths = spec.write_pave_layers(run_dir, spec.stem)
    gallery_paths = spec.write_gallery_layers(run_dir, spec.stem)
    values = spec.notebook_inputs(bars, files, str(stl), pave_paths=pave_paths, gallery_paths=gallery_paths)
    started = time.time()
    run = ntopcl.run(nb, cat.build_inputs(values), run_dir, tag=spec.stem)
    try:
        runs.require_fresh(stl, started, "the exported ring")
    except FileNotFoundError as e:
        raise ntopcl.NtopclError(f"notebook reported success but {e}", run) from e
    entry = run.outputs.get(cat.output.get("name", "Volume"))
    ntop_vol = ntopcl.scalar_value(entry) if entry else None
    rep = check_multistone(spec, stl, ntop_vol)
    gate.save(rep)
    res = MultiStoneResult(spec, stl, run, rep, ntop_vol, run_dir, run_id)
    res.notes.append(f"stones {spec.carats():.2f} ct; metal " + ", ".join(f"{k} {w:.2f} g" for k, w in tables.weights_g(rep.volume_mm3).items()))
    res.notes += spec.warnings() + built_notes
    report = {"stem": spec.stem, "spec_id": spec.spec_id, "run_id": run_id, "status": res.status, "ok": res.ok,
              "design": spec.design(), "inputs": values, "stl": str(stl), "bars": bars,
              "stones": [{"role": p.role, "theta_deg": p.theta_deg, "spin_deg": p.spin_deg, "stone": asdict(p.head.stone)} for p in spec.stones()],
              "pave": ({"stones": [{"row": q.row, "col": q.col, "theta_deg": q.theta_deg, "z_mm": q.z_mm} for q in spec.pave.stones()],
                        "beads": len(spec.pave.beads()), "layers": pave_paths} if spec.has_pave else None),
              "ntop_volume_mm3": ntop_vol, "gate": rep.to_dict(), "notes": res.notes,
              "notebook": runs.notebook_identity(nb), "environment": runs.environment(ntopcl.version())}
    (run_dir / f"{spec.stem}.report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    if deliver and res.ok:
        res.delivered = runs.deliver(stl, run_dir, spec.stem, deliver_project, report, cast_metal=cast_metal)
    elif deliver:
        res.notes.append(f"not delivered: status {res.status}")
    return res
