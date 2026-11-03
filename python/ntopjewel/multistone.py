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
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from . import band as bandmod, catalog, config, gate, gems, geom, heads, ntopcl, runs, tables
from . import shank as shankmod

SLOTS = 5
WALL_FLOOR = tables.FLOORS["wall_marginal"]
HEAD_ANGLE_DEG = 90.0
SIDE_GAP_MM = 0.3                  # girdle to girdle between neighbouring stones (default)
CUT_ALLOWED_MM3 = 1e-3             # a seat may take no more than this from a neighbour's head
SLOT_FIELDS = [("Seat Path", "path"), ("Prongs Path", "path"), ("Rail Offset", "mm"), ("Upper Rail Bottom", "mm"),
               ("Upper Rail Top", "mm"), ("Lower Rail Bottom", "mm"), ("Lower Rail Top", "mm"),
               ("Spin", "deg"), ("Pivot X", "mm"), ("Pivot Z", "mm"), ("Turn", "deg")]
COMMON = [("Clearance", "mm"), ("Head Blend", "mm"), ("Shank Blend", "mm")]


def slot_input(name: str, k: int) -> str:
    """The notebook input of slot k (0-based): `Seat Path`, `Seat Path 2` ..."""
    return name if k == 0 else f"{name} {k + 1}"


def specs() -> list[tuple[str, str]]:
    """Every notebook input but the output, in order (the catalog's order)."""
    shank_in = [(n, "path") for n in shankmod.SLOT_NAMES] + [("Wrap Length", "mm"), ("Edge Round", "mm"),
                                                               ("Edge Round Inward", "mm"), ("Mesh Tolerance", "mm")]
    return shank_in + COMMON + [(slot_input(n, k), t) for k in range(SLOTS) for n, t in SLOT_FIELDS]


def input_order() -> list[str]:
    return [n for n, _ in specs()] + ["Output Path"]


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
    finger_clear_mm: float | None = None
    shank_blend_mm: float | None = None
    shank: shankmod.ShankSpec | None = None
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
            head = self._placed(h2, t2, s2, 0)
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
        return 90.0 if theta_deg > 0 else -90.0

    # ---- the layout ---------------------------------------------------------------------------
    def stones(self) -> list[Placed]:
        """The centre, then the side stones +Y and -Y outwards, each at its solved angle."""
        if "stones" in self._cache:
            return self._cache["stones"]
        out = [Placed(self.centre, 0.0, self.centre_spin_deg, "centre")]
        if self.side is not None:
            prev = (self.centre, 0.0, self.centre_spin_deg)
            for _ in range(self.side_pairs):
                lo, hi = prev[1], prev[1] + 90.0

                def ok(t):
                    return self._clear(prev, (self.side, t, self.side_spin(t)))
                if not ok(hi):
                    raise ValueError("no side-stone angle up to 90° clears its neighbour")
                for _ in range(30):                                       # 0.0001° on 90
                    mid = (lo + hi) / 2
                    if ok(mid):
                        hi = mid
                    else:
                        lo = mid
                theta = round(hi + 0.01, 3)                               # a hair past the bound
                out.append(Placed(self.side, theta, self.side_spin(theta), "side"))
                prev = (self.side, theta, self.side_spin(theta))
            for p in list(out[1:]):
                out.append(Placed(self.side, -p.theta_deg, self.side_spin(-p.theta_deg), "side"))
        self._cache["stones"] = out
        return out

    def placed_heads_mesh(self, which: int = 0):
        """Every placed head (0) or seat cutter (1), concatenated (they may overlap: for looking only)."""
        import trimesh
        return trimesh.util.concatenate([self._placed(p.head, p.theta_deg, p.spin_deg, which) for p in self.stones()])

    @property
    def head_span_deg(self) -> float:
        """How far from the top the outermost stone's head reaches (deg)."""
        import numpy as np
        v = self.placed_heads_mesh(0).vertices
        return float(np.degrees(np.abs(np.arctan2(v[:, 1], v[:, 0]))).max())

    # ---- notebook ----------------------------------------------------------------------------
    def slot_values(self, p: Placed, seat_path: str, prongs_path: str) -> dict:
        ph = self.placed_head(p.head)
        ins = ph.notebook_inputs(seat_path, prongs_path)
        px, pz = self.pivot(p.head)
        return {"Seat Path": seat_path, "Prongs Path": prongs_path,
                **{k: ins[k] for k in ("Rail Offset", "Upper Rail Bottom", "Upper Rail Top", "Lower Rail Bottom", "Lower Rail Top")},
                "Spin": round(p.spin_deg, 4), "Pivot X": round(px, 4), "Pivot Z": round(pz, 4), "Turn": round(p.theta_deg, 4)}

    def notebook_inputs(self, shank_paths, slot_files: list[tuple[str, str]], output_path: str = "") -> dict:
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
        v["Output Path"] = str(output_path)
        return v

    def write_slot_files(self, directory: Path, stem: str) -> list[tuple[str, str]]:
        """Each distinct head's seat envelope and prongs (head frame) once; a path pair per stone."""
        directory = Path(directory)
        out, done = [], {}
        for p in self.stones():
            role = p.role
            if role not in done:
                ph = self.placed_head(p.head)
                env, prongs = directory / f"{stem}.{role}.envelope.stl", directory / f"{stem}.{role}.prongs.stl"
                ph.seat.envelope().export(str(env))
                ph.prongs_mesh().export(str(prongs))
                done[role] = (str(env), str(prongs))
            out.append(done[role])
        return out

    # ---- identity ----------------------------------------------------------------------------
    def design(self) -> dict:
        d = self.shank_spec.design()
        d.update({"centre": self.placed_head(self.centre).design(),
                  "side": self.placed_head(self.side).design() if self.side is not None else None,
                  "side_pairs": self.side_pairs if self.side is not None else 0, "side_gap": self.side_gap_mm,
                  "centre_spin": self.centre_spin_deg, "finger_clear": self.finger_clear, "shank_blend": self.shank_blend})
        return d

    @property
    def spec_id(self) -> str:
        return runs.spec_id(self.design())

    @staticmethod
    def _short(s: gems.StoneSpec) -> str:
        dims = f"{s.length:g}" if s.shape == "round" else f"{s.length:g}x{s.width:g}"
        return f"{s.shape}{dims}".replace(".", "p")

    @property
    def stem(self) -> str:
        side = f"_{self._short(self.side.stone)}" if self.side is not None else ""
        return f"ring_multi_{self.stone_count}_{self._short(self.centre.stone)}{side}_{self.band.label}_{self.spec_id}"

    @property
    def catalog_name(self) -> str:
        return "multistone"

    # ---- the independent ring -------------------------------------------------------------------
    def design_mesh(self, ops: geom.Booleans = geom.SHARP):
        """shank ∪ every placed head, then every placed seat cut (sharp unless `ops` blends)."""
        key = "design_mesh" if ops is geom.SHARP else None
        if key is None or key not in self._cache:
            stones = self.stones()
            hs = [self._placed(p.head, p.theta_deg, p.spin_deg, 0) for p in stones]
            cuts = [self._placed(p.head, p.theta_deg, p.spin_deg, 1) for p in stones]
            ring = ops.union([self.shank_spec.design_mesh(), ops.union(hs)], self.shank_blend)
            mesh = ops.clean(ops.difference(ring, cuts))
            if key is None:
                return mesh
            self._cache[key] = mesh
        return self._cache[key]

    def blend_volume_mm3(self) -> float:
        """What the blends add: each head's own (prongs into rails, the rails' edges), plus the
        heads-into-shank union along its exposed junction."""
        est = 0.0
        for p in self.stones():
            ph = self.placed_head(p.head)
            est += ph.blend_volume_mm3()
        if self.shank_blend > 0:
            import trimesh
            hs = trimesh.boolean.union([self._placed(p.head, p.theta_deg, p.spin_deg, 0) for p in self.stones()], engine="manifold")
            cuts = [self._placed(p.head, p.theta_deg, p.spin_deg, 1) for p in self.stones()]
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
        if self.stone_count > SLOTS:
            p.append(f"{self.stone_count} stones: the notebook has {SLOTS} head slots")
        if self.side is not None and self.side_pairs < 1:
            p.append("side pairs: at least 1 with a side stone")
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
        except ValueError as e:
            return [str(e)]
        span = self.head_span_deg
        if sh.tapered and span > sh.taper_from_deg:
            p.append(f"the heads reach {span:.0f}° from the top, past where the taper begins ({sh.taper_from_deg:g}°)")
        if span > 100.0:
            p.append(f"the heads reach {span:.0f}° from the top: fewer or smaller side stones")
        return p

    def warnings(self) -> list[str]:
        return list(self.shank_spec.warnings())

    def carats(self) -> float:
        return sum(p.head.stone.carats() for p in self.stones())

    def describe(self) -> str:
        b = self.band
        lines = [f"{self.stem}: {b.label}, inner Ø {b.inner_diameter_mm:.3f}, {b.profile} {b.width_mm:g} x {b.thickness_mm:g} mm"]
        for p in self.stones():
            if p.role == "side" and p.theta_deg < 0:
                continue
            s = p.head.stone
            where = "at the top" if p.role == "centre" else f"at ±{p.theta_deg:.2f}° (spun {abs(p.spin_deg):g}°, point inward)"
            lines.append(f"  {p.role}: {s.describe()} in {self.placed_head(p.head).count} prongs, {where}; "
                         f"girdle at r {self.girdle_radius(p.head):.3f}")
        gaps = ""
        if self.side is not None:
            n = 1 + self.side_pairs
            g = [self.girdle_gap(0 if k == 1 else k - 1, k) for k in range(1, n)]
            gaps = (f"girdles {', '.join(f'{x:.2f}' for x in g)} mm apart from the centre out (at least {self.side_gap_mm:g}; "
                    f"each side angle the smallest at which no seat cuts a neighbour's prongs); ")
        lines.append(f"  {self.stone_count} stones, {self.carats():.2f} ct; {gaps}heads reach ±{self.head_span_deg:.1f}°; "
                     f"culets at least {self.finger_clear:g} mm above the bore")
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
    ring = ops.union([shank, ops.union(hs)], float(v["Shank Blend"]))
    return ops.clean(ops.difference(ring, cuts))


# ---- the gate -------------------------------------------------------------------------------------
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

    def shank_rays(pts, n):
        return np.array([far(math.degrees(math.atan2(p[1], p[0]))) for p in pts])

    def shank_section(a):
        return sh.gate_section(a) if far(a) else None
    rep = gate.check(stl, expect_volume=ntop_vol, wall_floor=sh.wall_floor(), wall_ray_filter=shank_rays,
                     section_design=shank_section, section_tol_mm=sh.section_tolerance, centre="origin")
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
    shrink = tol + spec.centre.blend
    rep.checks.append(gate.Check("extents", bool(np.all(d <= tol) and np.all(d >= -shrink)),
                                 " x ".join(f"{x:.2f}" for x in rep.extents_mm) + " vs design "
                                 + " x ".join(f"{x:.2f}" for x in design.extents) + f" mm (+{tol:.2f} / -{shrink:.2f})"))
    fits, ledges, drops = [], [], []
    for p in stones:
        local = ring.copy()
        local.apply_transform(np.linalg.inv(spec.matrix(p.head, p.theta_deg, p.spin_deg)))
        stone = p.head.stone.mesh()
        inter = trimesh.boolean.intersection([local, stone], engine="manifold") if local.is_watertight else None
        overlap = float(inter.volume) if inter is not None and len(inter.faces) else (0.0 if inter is not None else float("nan"))
        fits.append((overlap, 0.002 * stone.volume))
        under, over = heads.seat_regions(p.head.stone, p.head.clearance)
        g = p.head.stone.girdle
        ledges.append((heads.outline_count(local, -g / 2 - 0.3, under), spec.placed_head(p.head).count))
        drops.append(heads.outline_count(local, g / 2 + 0.15, over))
    bad = [i for i, (o, a) in enumerate(fits) if not o <= a]
    rep.checks.append(gate.Check("stones fit", not bad, f"{len(stones) - len(bad)}/{len(stones)} stones clear of the metal "
                                 f"(worst ∩ {max(o for o, _ in fits):.3f} mm³)"))
    bad = [i for i, (n, want) in enumerate(ledges) if n < want]
    rep.checks.append(gate.Check("seat ledges", not bad, "every stone: " + ", ".join(f"{n}/{w}" for n, w in ledges)
                                 + " prongs reach under the girdle"))
    rep.checks.append(gate.Check("drop-in clear", not any(drops), f"{sum(drops)} pieces inside a girdle line above its girdle"))
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
    values = spec.notebook_inputs(bars, files, str(stl))
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
              "ntop_volume_mm3": ntop_vol, "gate": rep.to_dict(), "notes": res.notes,
              "notebook": runs.notebook_identity(nb), "environment": runs.environment(ntopcl.version())}
    (run_dir / f"{spec.stem}.report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    if deliver and res.ok:
        res.delivered = runs.deliver(stl, run_dir, spec.stem, deliver_project, report, cast_metal=cast_metal)
    elif deliver:
        res.notes.append(f"not delivered: status {res.status}")
    return res
