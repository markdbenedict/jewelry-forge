"""Pavé: rows of small round stones set into a band's surface - Phase 3 step 2/3 (the pavé band).

Every stone sits in a seat cut along the band's surface normal: the stone's own envelope (crown
and girdle carried straight up as a drop-in path, the pavilion below) grown by the seat clearance,
with a light hole drilled on under the culet through to the bore. Beads raised from the metal in
the gaps between the stones hold them: each stands just clear of the openings it borders, so a
stone drops in past it, and the setter pushes it over the crown afterwards (tables:
pave_bead_gap_mm). The seats are cut AFTER the beads are added, so the drop-in path is clear by
construction; a bead in a tight interstice comes out trimmed by the openings, as on the bench.

    layout     rows of stones across the band (1..4), staggered (each row half a pitch on from
               the last, the stones nest) or aligned (a grid), centred on the head (+X) and
               covering `span_deg` of the ring (360: a full eternity). The pitch along a row and
               across rows is solved on the real geometry: the girdles' lower edges - where two
               stones whose normals converge towards the axis come closest - stand pave_stone_gap_mm
               apart (bisection on the 3-D girdle circles, so a domed band's tilted rows are right)
    beads      from every pair of neighbouring stones, the two points at the holding distance
               (girdle radius + clearance + bead radius + bead gap) from both; points closer than
               a bead's diameter merged (in a staggered layout the three a triangle of stones
               makes meet at its centre); beads off the band's top or holding no real stone dropped
    files      Python writes the seats (every stone's cutter, disjoint) and the beads (every
               sphere, disjoint) as one mesh each; the notebook (pave_band.ntop, built by
               ntop/recipes/pave_band.py) wraps the shank's bars as ring_shank.ntop does, opens
               them, unites the beads and subtracts the seats: (shank ∪ beads) − seats

Coordinates: nTop's ring frame (axis Z, the head at +X). A stone's frame: X along the ring (+θ),
Z its table's normal (the band's outward surface normal at its place), girdle mid-plane at z = 0.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import band, catalog, config, gate, gems, geom, ntopcl, runs, tables
from . import shank as shankmod

LAYOUTS = ("staggered", "aligned")
MAX_ROWS = 4
GIRDLE_POINTS = 128          # points on each girdle edge circle for the gap solve
SEAT_SECTIONS = 48           # facets round a seat cutter (nTop imports these very facets)
BEAD_SUBDIVISIONS = 2        # icosphere: 320 faces, within 0.3 % of the sphere's radius
NEIGHBOUR_PITCHES = 1.3      # stones closer than this many pitches are neighbours (row and diagonal)
HOLD_SLACK_MM = 0.2          # a bead holds a stone it stands within this of the holding distance from
DROP_ABOVE_MM = 0.8          # the seat's drop-in path reaches this far above the band's surface


def setting(name: str) -> float:
    return float(tables.SETTINGS[name])


@dataclass
class Stone:
    """A placed stone: where on the band (theta, z), its frame and whether it is real (a virtual
    stone beyond a half-eternity's end only shapes the end beads)."""
    row: int
    col: int
    theta_deg: float
    z_mm: float
    matrix: object = field(repr=False)          # 4x4 stone frame -> ring frame
    real: bool = True

    @property
    def origin(self):
        return self.matrix[:3, 3]

    @property
    def normal(self):
        return self.matrix[:3, 2]


@dataclass
class PaveSpec:
    shank: shankmod.ShankSpec
    stone_mm: float = 1.3
    rows: int = 1
    layout: str = "staggered"
    span_deg: float = 180.0                     # the arc the stones cover, centred on centre_deg; 360 = full eternity
    centre_deg: float = 0.0                     # where the arc is centred: 0 the head (a pavé band), 180 the bottom (round a multi-stone ring)
    gap_mm: float | None = None                 # girdle to girdle; None = tables pave_stone_gap_mm
    bead_mm: float | None = None                # bead diameter; None = pave_bead_frac x stone, at least floors.bead_dia
    material: str = tables.DEFAULT_STONE
    _cache: dict = field(default_factory=dict, repr=False, compare=False)

    # ---- numbers --------------------------------------------------------------------------
    @property
    def band(self) -> band.BandSpec:
        return self.shank.band

    @property
    def stone(self) -> gems.StoneSpec:
        return gems.StoneSpec(shape="round", length_mm=self.stone_mm, material=self.material)

    @property
    def clearance(self) -> float:
        return setting("seat_clearance_mm")

    @property
    def gap(self) -> float:
        return setting("pave_stone_gap_mm") if self.gap_mm is None else float(self.gap_mm)

    @property
    def bead_radius(self) -> float:
        if self.bead_mm is not None:
            return float(self.bead_mm) / 2
        return max(tables.FLOORS["bead_dia"], setting("pave_bead_frac") * self.stone_mm) / 2

    @property
    def bead_gap(self) -> float:
        return setting("pave_bead_gap_mm")

    @property
    def table_below(self) -> float:
        return setting("pave_table_below_mm")

    @property
    def hole_radius(self) -> float:
        return setting("pave_hole_frac") * self.stone_mm / 2

    @property
    def min_beads(self) -> int:
        return int(setting("pave_min_beads"))

    @property
    def full(self) -> bool:
        return self.span_deg >= 360.0 - 1e-9

    @property
    def girdle_radius(self) -> float:
        return self.stone.width / 2

    @property
    def hold_distance(self) -> float:
        """Stone axis to bead centre for a bead standing pave_bead_gap_mm outside the opening."""
        return self.girdle_radius + self.clearance + self.bead_radius + self.bead_gap

    @property
    def girdle_depth(self) -> float:
        """Band surface to the girdle's mid-plane, along the stone's axis."""
        crown, _ = self.stone.heights
        return self.table_below + crown + self.stone.girdle / 2

    @property
    def seat_depth(self) -> float:
        """Band surface to the bottom of the seat cutter (the offset culet), along the axis."""
        _, pav = self.stone.heights
        return self.girdle_depth + self.stone.girdle / 2 + pav + self.clearance

    # ---- the band's surface ---------------------------------------------------------------
    def surface_frame(self, theta_deg: float, z_mm: float):
        """4x4: the stone frame at (theta, z) with its origin ON the band's outer surface (X along
        the ring, Z the outward normal)."""
        import numpy as np
        sec = self.shank.section_spec(theta_deg)
        r = sec.outer_radius_at(z_mm)
        h = 1e-4
        dr = (sec.outer_radius_at(z_mm + h) - sec.outer_radius_at(z_mm - h)) / (2 * h)
        t = math.radians(theta_deg)
        radial = np.array([math.cos(t), math.sin(t), 0.0])
        n = radial - dr * np.array([0.0, 0.0, 1.0])
        n /= np.linalg.norm(n)
        x = np.array([-math.sin(t), math.cos(t), 0.0])
        y = np.cross(n, x)
        m = np.eye(4)
        m[:3, 0], m[:3, 1], m[:3, 2], m[:3, 3] = x, y, n, radial * r + np.array([0.0, 0.0, z_mm])
        return m

    def stone_frame(self, theta_deg: float, z_mm: float):
        """4x4: the stone's own frame (girdle mid-plane at z = 0) at (theta, z)."""
        m = self.surface_frame(theta_deg, z_mm)
        m[:3, 3] = m[:3, 3] - m[:3, 2] * self.girdle_depth
        return m

    def _girdle_edges(self, theta_deg: float, z_mm: float):
        """(2 x GIRDLE_POINTS, 3) points of a stone's girdle edges (top and bottom) in the ring frame."""
        import numpy as np
        m = self.stone_frame(theta_deg, z_mm)
        a = np.linspace(0, 2 * math.pi, GIRDLE_POINTS, endpoint=False)
        R, g = self.girdle_radius, self.stone.girdle
        pts = []
        for h in (-g / 2, g / 2):
            local = np.column_stack([R * np.cos(a), R * np.sin(a), np.full_like(a, h), np.ones_like(a)])
            pts.append((local @ m.T)[:, :3])
        return np.vstack(pts)

    def girdle_gap(self, a: tuple[float, float], b: tuple[float, float]) -> float:
        """Closest approach of two stones' girdles at (theta, z) each, mm (negative: they cross)."""
        import numpy as np
        from scipy.spatial import cKDTree
        pa, pb = self._girdle_edges(*a), self._girdle_edges(*b)
        d, _ = cKDTree(pb).query(pa)
        dist = float(d.min())
        # sampled circles: two stones whose girdles cross still show a positive distance; test
        # for overlap on the line between the centres (both girdles are discs of radius R)
        oa, ob = self.stone_frame(*a)[:3, 3], self.stone_frame(*b)[:3, 3]
        if np.linalg.norm(oa - ob) < 2 * self.girdle_radius - 1e-6:
            return -dist
        return dist

    @staticmethod
    def _bisect(f, lo: float, hi: float, target: float, steps: int = 50) -> float:
        """The x in [lo, hi] where the increasing f(x) reaches target."""
        for _ in range(steps):
            mid = (lo + hi) / 2
            if f(mid) < target:
                lo = mid
            else:
                hi = mid
        return hi

    # ---- the layout -----------------------------------------------------------------------
    def _row_z(self, across: float) -> list[float]:
        return [(k - (self.rows - 1) / 2) * across for k in range(self.rows)]

    @property
    def across_mm(self) -> float:
        """Row to row along the axis: the girdles of neighbouring rows' nearest stones gap apart."""
        if "across" not in self._cache:
            if self.rows == 1:
                self._cache["across"] = 0.0
            else:
                alpha0 = self._pitch_for([0.0])
                off = alpha0 / 2 if self.layout == "staggered" else 0.0
                f = lambda dz: self.girdle_gap((0.0, -dz / 2), (off, dz / 2))           # noqa: E731
                self._cache["across"] = self._bisect(f, 0.0, 4 * self.stone_mm, self.gap)
        return self._cache["across"]

    def _pitch_for(self, zs: list[float]) -> float:
        """Degrees between neighbours along a row: the widest any row at these heights needs."""
        alphas = []
        for z in zs:
            f = lambda a: self.girdle_gap((0.0, z), (a, z))                               # noqa: E731
            alphas.append(self._bisect(f, 0.0, 60.0, self.gap))
        return max(alphas)

    @property
    def pitch_deg(self) -> float:
        """Degrees between neighbours along a row (a full eternity: 360 / count, a little wider)."""
        if "pitch" not in self._cache:
            alpha = self._pitch_for(self._row_z(self.across_mm) if self.rows > 1 else [0.0])
            if self.full:
                alpha = 360.0 / math.floor(360.0 / alpha)
            self._cache["pitch"] = alpha
        return self._cache["pitch"]

    @property
    def count(self) -> int:
        """Stones in the first row (staggered: the next rows of a half eternity hold one fewer)."""
        if self.full:
            return int(round(360.0 / self.pitch_deg))
        return int(math.floor(self.span_deg / self.pitch_deg + 1e-9)) + 1

    def row_columns(self, row: int) -> list[float]:
        """The angles of a row's real stones, centred on the head."""
        a, n = self.pitch_deg, self.count
        shift = 0.5 if (self.layout == "staggered" and row % 2) else 0.0
        if self.full:
            return [(k + shift) * a for k in range(n)]
        m = n - 1 if shift else n
        return [float(self.centre_deg) + (k - (m - 1) / 2) * a for k in range(m)]

    def stones(self, virtual: bool = False) -> list[Stone]:
        """Every placed stone; with `virtual`, a half eternity's rows carried one stone past each
        end (they only shape the end beads)."""
        key = ("stones", virtual)
        if key not in self._cache:
            out = []
            zs = self._row_z(self.across_mm)
            for row, z in enumerate(zs):
                cols = self.row_columns(row)
                for col, th in enumerate(cols):
                    out.append(Stone(row, col, th, z, self.stone_frame(th, z)))
                if virtual and not self.full:
                    for col, th in ((-1, cols[0] - self.pitch_deg), (len(cols), cols[-1] + self.pitch_deg)):
                        out.append(Stone(row, col, th, z, self.stone_frame(th, z), real=False))
            self._cache[key] = out
        return self._cache[key]

    @property
    def stone_count(self) -> int:
        return len(self.stones())

    # ---- beads ----------------------------------------------------------------------------
    def _surface_point(self, theta_deg: float, z_mm: float):
        return self.surface_frame(theta_deg, z_mm)[:3, 3]

    def beads(self) -> list[dict]:
        """Every bead: {'theta', 'z', 'centre' (on the band's surface), 'holds' (indices of the real
        stones it holds)}; see the module doc."""
        if "beads" in self._cache:
            return self._cache["beads"]
        import numpy as np
        stones = self.stones(virtual=True)
        real = [s for s in stones if s.real]
        r0 = self.band.outer_radius_mm
        k = math.pi / 180.0 * r0                                                       # degrees -> mm along the ring
        hold, rb = self.hold_distance, self.bead_radius
        p_mm = self.pitch_deg * k

        def uv(s):                                                                     # the unrolled surface (mm)
            return np.array([s.theta_deg * k, s.z_mm])

        def wrap(d):                                                                   # a full eternity closes on itself
            if self.full:
                c = 360.0 * k
                d = d.copy()
                d[0] = (d[0] + c / 2) % c - c / 2
            return d

        cands = []
        for i, a in enumerate(stones):
            for j in range(i + 1, len(stones)):
                b = stones[j]
                if not (a.real or b.real):
                    continue
                d = wrap(uv(b) - uv(a))
                dist = float(np.linalg.norm(d))
                if dist < 1e-6 or dist > NEIGHBOUR_PITCHES * max(p_mm, self.across_mm or p_mm) or dist / 2 >= hold:
                    continue
                mid = uv(a) + d / 2
                u = np.array([-d[1], d[0]]) / dist
                h = math.sqrt(hold * hold - dist * dist / 4)
                cands += [mid + h * u, mid - h * u]
        # merge candidates closer than a bead's diameter (a triangle's three meet at its centre)
        pts = [np.array(c) for c in cands]
        merged = True
        while merged and len(pts) > 1:
            merged = False
            for i in range(len(pts)):
                for j in range(i + 1, len(pts)):
                    if np.linalg.norm(wrap(pts[j] - pts[i])) < 2 * rb:
                        pts[i] = pts[i] + wrap(pts[j] - pts[i]) / 2
                        del pts[j]
                        merged = True
                        break
                if merged:
                    break
        out = []
        half_w = self.band.width_mm / 2 - self.band.edge_round
        for p in pts:
            th, z = float(p[0] / k), float(p[1])
            if self.full:
                th %= 360.0
            if abs(z) + 0.5 * rb > half_w:
                continue                                                               # off the band's top
            c = self._surface_point(th, z)
            lateral = [self._lateral(s, c) for s in real]
            if min(lateral) < self.girdle_radius + self.clearance:
                continue                                                               # its apex inside an opening
            holds = [i for i, d in enumerate(lateral) if d <= hold + HOLD_SLACK_MM]
            if not holds:
                continue                                                               # past a half eternity's end
            out.append({"theta": th, "z": z, "centre": c, "holds": holds})
        self._cache["beads"] = out
        return out

    def _lateral(self, s: Stone, p) -> float:
        """Distance of a point from a stone's axis, on the stone's side of the ring (the axis runs
        on through the ring's centre to the stones opposite: inf beyond the seat's light hole)."""
        import numpy as np
        d = p - s.origin
        h = float(d @ s.normal)
        if h < -2 * self.seat_depth:
            return math.inf
        return float(np.linalg.norm(d - s.normal * h))

    def beads_per_stone(self) -> list[int]:
        counts = [0] * self.stone_count
        for b in self.beads():
            for i in b["holds"]:
                counts[i] += 1
        return counts

    # ---- meshes ---------------------------------------------------------------------------
    def stone_mesh(self, s: Stone):
        m = self.stone.mesh().copy()
        m.apply_transform(s.matrix)
        return m

    def stones_mesh(self):
        import trimesh
        return trimesh.util.concatenate([self.stone_mesh(s) for s in self.stones()])

    def _bottom_h(self, s: Stone) -> float:
        """The light hole's bottom in the stone's frame: through the bore with room to spare."""
        o, n = s.origin, s.normal
        sec = self.shank.section_spec(s.theta_deg)
        r_o = math.hypot(o[0], o[1])
        radial = math.hypot(n[0], n[1])
        return -((r_o - sec.bore_radius_at(s.z_mm)) / max(radial, 0.5) + 0.4)

    def cutter_profile(self, bottom_h: float):
        """The seat cutter's meridian (rho >= 0, h), from the axis at the top round to the axis at
        the bottom: the stone's envelope (drop-in path above the girdle) grown by the clearance,
        and the light hole on down to `bottom_h`."""
        import numpy as np
        from shapely.geometry import Polygon, box
        from shapely.ops import unary_union
        R, g = self.girdle_radius, self.stone.girdle
        _, pav = self.stone.heights
        top = self.girdle_depth + DROP_ABOVE_MM
        env = Polygon([(-R, top), (R, top), (R, -g / 2), (0.0, -g / 2 - pav), (-R, -g / 2)]).buffer(self.clearance, quad_segs=8)
        sec = unary_union([env, box(-self.hole_radius, bottom_h, self.hole_radius, -g / 2)])
        half = sec.intersection(box(0.0, bottom_h - 1.0, R + 1.0, top + 1.0))
        xy = np.asarray(half.exterior.coords)[:-1]
        on_axis = np.abs(xy[:, 0]) < 1e-9
        # rotate the ring of points so it starts at the top point on the axis and runs round the
        # outside to the bottom point on the axis (the axis segment itself is dropped)
        idx = np.flatnonzero(on_axis)
        ys = xy[idx, 1]
        start = idx[int(np.argmax(ys))]
        ring = np.roll(xy, -start, axis=0)
        if ring[1, 0] < 1e-9:                                                          # walking down the axis: turn round
            ring = np.vstack([ring[:1], ring[1:][::-1]])
        end = int(np.flatnonzero(np.abs(ring[1:, 0]) < 1e-9)[0]) + 1
        return ring[: end + 1]

    def seat_mesh(self, s: Stone):
        import trimesh
        prof = self.cutter_profile(self._bottom_h(s))
        m = trimesh.creation.revolve(prof, sections=SEAT_SECTIONS)
        if m.volume < 0:
            m.invert()
        m.apply_transform(s.matrix)
        return m

    def seats_mesh(self):
        import trimesh
        return trimesh.util.concatenate([self.seat_mesh(s) for s in self.stones()])

    def beads_mesh(self):
        import trimesh
        balls = []
        for b in self.beads():
            ball = trimesh.creation.icosphere(subdivisions=BEAD_SUBDIVISIONS, radius=self.bead_radius)
            ball.apply_translation(b["centre"])
            balls.append(ball)
        return trimesh.util.concatenate(balls)

    def design_mesh(self):
        """The independent ring: the shank's design ∪ beads − seats (manifold3d)."""
        if "design_mesh" not in self._cache:
            import trimesh
            body = trimesh.boolean.union([self.shank.design_mesh(), self.beads_mesh()], engine="manifold")
            self._cache["design_mesh"] = trimesh.boolean.difference([body, self.seats_mesh()], engine="manifold")
        return self._cache["design_mesh"]

    def design_volume_mm3(self) -> float:
        return float(self.design_mesh().volume)

    def expected_volume_mm3(self) -> float:
        """What nTop should report: the design less what the band's opening takes off the shank
        (ShankSpec.expected_volume_mm3's corrections; the pavé is added after the opening)."""
        return self.design_volume_mm3() - self.shank.sharp_edge_round_mm3() - self.shank.opening_overcut_mm3()

    def write_layer(self, directory: Path, stem: str) -> tuple[str, str]:
        """Writes <stem>.seats.stl and <stem>.beads.stl; returns their paths."""
        directory = Path(directory)
        seats, beads = directory / f"{stem}.seats.stl", directory / f"{stem}.beads.stl"
        self.seats_mesh().export(str(seats))
        self.beads_mesh().export(str(beads))
        return str(seats), str(beads)

    def notebook_inputs(self, bar_paths, seats_path: str, beads_path: str, output_path: str = "") -> dict:
        v = self.shank.notebook_inputs(bar_paths, output_path)
        out = v.pop("Output Path")
        v.update({"Pave Seats Path": str(seats_path), "Pave Beads Path": str(beads_path), "Output Path": out})
        return v

    # ---- identity -------------------------------------------------------------------------
    def design(self) -> dict:
        d = self.shank.design()
        d.update({"pave_stone": self.stone_mm, "pave_rows": self.rows, "pave_layout": self.layout if self.rows > 1 else "",
                  "pave_span_deg": 360.0 if self.full else self.span_deg, "pave_gap": self.gap, "pave_bead": 2 * self.bead_radius,
                  "pave_bead_gap": self.bead_gap, "pave_table_below": self.table_below, "pave_hole": 2 * self.hole_radius,
                  "seat_clearance": self.clearance, "pave_material": self.material})
        if self.centre_deg:                                            # only when set: the pavé bands keep their ids
            d["pave_centre_deg"] = self.centre_deg
        return d

    @property
    def spec_id(self) -> str:
        return runs.spec_id(self.design())

    @property
    def stem(self) -> str:
        b = self.band
        layout = {"staggered": "s", "aligned": "a"}[self.layout] if self.rows > 1 else ""
        reach = "eternity" if self.full else f"{self.span_deg:g}deg"
        return f"ring_pave_{b.profile}_{b.label}_w{b.width_mm:g}t{b.thickness_mm:g}_{self.rows}{layout}x{self.stone_mm:g}_{reach}_{self.spec_id}"

    @property
    def catalog_name(self) -> str:
        return "pave_band"

    # ---- checks on the design -------------------------------------------------------------
    def validate(self) -> list[str]:
        if self.shank.hammer is not None:
            return ["a hammered shank goes through ring_shank.ntop or a solitaire: pave_band.ntop has no Strikes section yet"]
        p = list(self.shank.validate())
        sh = self.shank
        if sh.rope or sh.knot or sh.strands > 1 or sh.split_mm or sh.dip_mm:
            p.append("pavé sits on a plain or tapered band (no rope, knot, double band, split or dip yet)")
        if not 0.8 <= self.stone_mm <= 3.0:
            p.append(f"pavé stones {self.stone_mm:g} mm: 0.8..3 mm (larger stones are heads, not pavé)")
        if not 1 <= self.rows <= MAX_ROWS:
            p.append(f"rows {self.rows}: 1..{MAX_ROWS}")
        if self.layout not in LAYOUTS:
            p.append(f"layout {self.layout!r}: one of {', '.join(LAYOUTS)}")
        if not 0.0 < self.span_deg <= 360.0:
            p.append(f"span {self.span_deg:g}°: 0..360")
        if self.gap < 2 * self.clearance + 0.05:
            p.append(f"stone gap {self.gap:g} mm leaves under 0.05 mm of metal between two openings (each seat is cut "
                     f"{self.clearance:g} mm wider than its stone)")
        if 2 * self.bead_radius < tables.FLOORS["bead_dia"] - 1e-9:
            p.append(f"beads {2 * self.bead_radius:g} mm: under the {tables.FLOORS['bead_dia']:g} mm floor")
        if p:
            return p
        b = self.band
        if not self.full and self.centre_deg == 0.0 and sh.width_bottom < b.width_mm - 1e-9 and self.span_deg / 2 + self.pitch_deg > sh.taper_from_deg:
            p.append(f"the pavé reaches {self.span_deg / 2:g}° from the head, past where the taper begins ({sh.taper_from_deg:g}°): "
                     "shorten the span or move the taper")
        if (self.full or self.centre_deg != 0.0) and (sh.width_bottom < b.width_mm - 1e-9 or sh.thickness_bottom < b.thickness_mm - 1e-9):
            p.append("a full eternity, or pavé round the bottom, needs the same section all round (no taper)")
        # the outer rows' openings must leave a wall to the band's edge
        wall = tables.FLOORS["wall_marginal"]
        zmax = max(abs(z) for z in self._row_z(self.across_mm)) + self.girdle_radius + self.clearance
        room = b.width_mm / 2 - zmax
        if room < wall - 1e-6:
            p.append(f"the outer rows' openings reach {zmax:.2f} mm from the centre line: {room:.2f} mm of wall to the "
                     f"band's edge, under {wall:g} mm - widen the band to {2 * (zmax + wall):.1f} mm or set fewer rows")
        floor = b.thickness_mm - (self.seat_depth - self.stone.heights[1] * self.hole_radius / self.girdle_radius)
        if floor < wall - 1e-6:
            p.append(f"{floor:.2f} mm of metal under the seats beside the light hole, under {wall:g} mm: a thicker band "
                     f"or smaller stones")
        if p:
            return p
        if self.count < (1 if self.full else 1):
            p.append("no stone fits the span")
        counts = self.beads_per_stone()
        few = [i for i, c in enumerate(counts) if c < self.min_beads]
        if few:
            p.append(f"{len(few)} stone(s) held by fewer than {self.min_beads} beads (the band edge drops the outer beads?): "
                     f"widen the band")
        # beads disjoint
        import numpy as np
        cs = np.array([bd["centre"] for bd in self.beads()])
        if len(cs) > 1:
            from scipy.spatial import cKDTree
            d, _ = cKDTree(cs).query(cs, k=2)
            if float(d[:, 1].min()) < 2 * self.bead_radius:
                p.append("two beads overlap")
        return p

    def warnings(self) -> list[str]:
        return list(self.shank.warnings()) + (
            [f"Mesh Tolerance {self.band.mesh_tolerance_mm:g} mm is coarse for pavé (tables pave_mesh_tolerance_mm "
             f"{setting('pave_mesh_tolerance_mm'):g}): the 0.1 mm webs between seats blur"]
            if self.band.mesh_tolerance_mm > setting("pave_mesh_tolerance_mm") + 1e-9 else [])

    def carats(self) -> float:
        return self.stone_count * self.stone.carats()

    def describe(self) -> str:
        b, s = self.band, self.stone
        counts = self.beads_per_stone()
        rows = ", ".join(str(len(self.row_columns(r))) for r in range(self.rows))
        where = "the top" if self.centre_deg == 0.0 else ("the bottom" if self.centre_deg == 180.0 else f"{self.centre_deg:g}°")
        reach = "all round (full eternity)" if self.full else f"over {self.span_deg:g}° centred on {where}"
        return (f"{self.stem}: {b.label}, inner Ø {b.inner_diameter_mm:.3f}, {b.profile} {b.width_mm:g} x {b.thickness_mm:g} mm\n"
                f"  pavé: {self.stone_count} round {s.material} stones of {self.stone_mm:g} mm ({self.carats():.2f} ct), "
                f"{self.rows} row{'s' if self.rows > 1 else ''} ({rows}){', ' + self.layout if self.rows > 1 else ''}, {reach}; "
                f"pitch {self.pitch_deg:.3f}° ({self.pitch_deg * math.pi / 180 * b.outer_radius_mm:.3f} mm at the surface)"
                + (f", rows {self.across_mm:.3f} mm apart" if self.rows > 1 else "") + "\n"
                f"  girdles {self.gap:g} mm apart, seats cut {self.clearance:g} mm wider, tables {self.table_below:g} mm below the "
                f"surface, light holes Ø {2 * self.hole_radius:.2f} to the bore; seat {self.seat_depth:.2f} mm deep\n"
                f"  {len(self.beads())} beads of Ø {2 * self.bead_radius:.2f} mm, {min(counts)}-{max(counts)} per stone, "
                f"{self.bead_gap:g} mm outside the openings\n"
                f"  design volume {self.design_volume_mm3():.2f} mm³ (band {self.shank.design_volume_mm3():.2f}); "
                f"Mesh Tolerance {b.mesh_tolerance_mm:g}")

    # ---- the gate -------------------------------------------------------------------------
    def in_pave(self, theta_deg: float, margin_deg: float | None = None) -> bool:
        if self.full:
            return True
        m = self.pitch_deg if margin_deg is None else margin_deg
        a = abs((float(theta_deg) - float(self.centre_deg) + 180.0) % 360.0 - 180.0)
        return a <= self.span_deg / 2 + m

    @property
    def reach_from_top_deg(self) -> float:
        """How near the top of the ring (+X) the pavé's stones come, girdle edge included, degrees."""
        if self.full:
            return 0.0
        near = min(abs((t + 180.0) % 360.0 - 180.0) for r in range(self.rows) for t in self.row_columns(r))
        return max(0.0, near - math.degrees((self.girdle_radius + self.clearance) / self.band.outer_radius_mm))

    def gate_section(self, theta_deg: float):
        """The section the gate expects: the design mesh's through the pavé, the shank's elsewhere."""
        if self.in_pave(theta_deg):
            return gate.section_geometry(self.design_mesh(), theta_deg)
        return self.shank.gate_section(theta_deg)

    def section_tolerance(self, theta_deg: float) -> float:
        """Through the pavé the whole mesh tolerance (beads and 0.1 mm webs are a few voxels);
        the band's rule elsewhere."""
        if self.in_pave(theta_deg):
            return max(self.shank.section_tolerance(theta_deg), float(self.band.mesh_tolerance_mm))
        return self.shank.section_tolerance(theta_deg)

    def wall_ray_filter(self):
        """Drops sample points on a seat cutter's faces (an opening's wall measures the 0.1 mm web
        to the next seat, a hole's the metal between holes) and on beads (a chord through a
        sphere): what is left measures the band, the floor under the stones from the bore, and
        the outer rows' walls to the band's edge."""
        import numpy as np
        stones = self.stones()
        mats = np.array([np.linalg.inv(s.matrix) for s in stones])
        bottoms = np.array([self._bottom_h(s) for s in stones])
        R, c, rh = self.girdle_radius, self.clearance, self.hole_radius
        _, pav = self.stone.heights
        g = self.stone.girdle
        low = -g / 2 - pav - c - 0.03
        centres = np.array([b["centre"] for b in self.beads()]) if self.beads() else np.zeros((0, 3))

        def keep(pts, normals):
            ok = np.ones(len(pts), dtype=bool)
            hom = np.column_stack([pts, np.ones(len(pts))])
            for m, hb in zip(mats, bottoms):
                loc = hom @ m.T
                rho = np.hypot(loc[:, 0], loc[:, 1])
                h = loc[:, 2]
                on_seat = (rho <= R + c + 0.03) & (h >= low)
                on_hole = (rho <= rh + 0.03) & (h >= hb - 0.03)
                ok &= ~(on_seat | on_hole)
            if len(centres):
                from scipy.spatial import cKDTree
                d, _ = cKDTree(centres).query(pts)
                ok &= d > self.bead_radius + 0.03
            return ok
        return keep


# ---- the gate's pavé checks ----------------------------------------------------------------------
def _first_hits(mesh, origins, dirs, limit):
    """Distance to the first hit along each ray within `limit` (inf when none)."""
    import numpy as np
    locs, idx, _ = mesh.ray.intersects_location(origins, dirs, multiple_hits=True)
    out = np.full(len(origins), np.inf)
    if len(idx):
        d = np.linalg.norm(locs - origins[idx], axis=1)
        for i, dist in zip(idx, d):
            if dist <= limit[i] and dist < out[i]:
                out[i] = dist
    return out


def pave_checks(spec: PaveSpec, ring) -> list[gate.Check]:
    """Each seat, hole and bead where the design has it, probed by rays cast identically on the
    built ring and on the independent design (so the faceting of the imported cutters and beads
    is the same on both): light holes open through to the bore, every seat's floor at its depth,
    every drop-in path clear down to the girdle, every bead's apex standing, every stone held by
    at least pave_min_beads of them; and the stones themselves clear of the metal."""
    import numpy as np
    import trimesh
    design = spec.design_mesh()
    tol = max(0.06, 1.5 * float(spec.band.mesh_tolerance_mm))
    R, c, rh = spec.girdle_radius, spec.clearance, spec.hole_radius
    stones = spec.stones()
    checks = []

    # stones clear of the metal
    st = spec.stones_mesh()
    inter = trimesh.boolean.intersection([ring, st], engine="manifold") if ring.is_watertight else None
    overlap = float(inter.volume) if inter is not None and len(inter.faces) else (0.0 if inter is not None else float("nan"))
    allowed = 0.002 * float(st.volume)
    checks.append(gate.Check("stones fit", overlap <= allowed, f"ring ∩ {len(stones)} stones {overlap:.4f} mm³ (allowed {allowed:.4f})"))

    def probe(kind_rays):
        o = np.array([r[0] for r in kind_rays]); d = np.array([r[1] for r in kind_rays]); lim = np.array([r[2] for r in kind_rays])
        return _first_hits(ring, o, d, lim), _first_hits(design, o, d, lim)

    def local(s, x, y, h):
        return (s.matrix @ np.array([x, y, h, 1.0]))[:3]

    top = spec.girdle_depth + DROP_ABOVE_MM - 0.05                                    # inside the drop path's top
    holes, floors, drops, owner_f, owner_d = [], [], [], [], []
    for i, s in enumerate(stones):
        n = s.normal
        bottom = spec._bottom_h(s)
        holes.append((local(s, 0, 0, top), -n, top - bottom - 0.1))
        rho = (R + rh) / 2
        for a in np.linspace(0, 2 * math.pi, 4, endpoint=False):
            floors.append((local(s, rho * math.cos(a), rho * math.sin(a), top), -n, top - bottom))
            owner_f.append(i)
        rho = R + c - 0.03
        for a in np.linspace(0, 2 * math.pi, 8, endpoint=False):
            drops.append((local(s, rho * math.cos(a), rho * math.sin(a), top), -n, top - bottom))
            owner_d.append(i)
    built, want = probe(holes)
    blocked = [i for i in range(len(stones)) if np.isfinite(built[i]) and not np.isfinite(want[i])]
    checks.append(gate.Check("light holes open", not blocked,
                             f"{len(stones) - len(blocked)}/{len(stones)} holes open from the table to the bore"
                             + (f"; blocked under stone(s) {blocked[:6]}" if blocked else "")))
    built, want = probe(floors)
    bad = sorted({owner_f[k] for k in range(len(floors)) if not (np.isfinite(built[k]) and abs(built[k] - want[k]) <= tol)})
    checks.append(gate.Check("seats", not bad, f"{len(stones) - len(bad)}/{len(stones)} seat floors at their depth (within {tol:.2f} mm)"
                             + (f"; wrong under stone(s) {bad[:6]}" if bad else "")))
    built, want = probe(drops)
    bad = sorted({owner_d[k] for k in range(len(drops)) if built[k] < want[k] - tol})
    checks.append(gate.Check("drop-in clear", not bad, f"{len(stones) - len(bad)}/{len(stones)} openings clear down to the girdle"
                             + (f"; metal in the way at stone(s) {bad[:6]}" if bad else "")))

    # beads: a ray from above each apex must meet it where the design does
    beads = spec.beads()
    rb = spec.bead_radius
    rays = []
    for b in beads:
        th = math.radians(b["theta"])
        n = spec.surface_frame(b["theta"], b["z"])[:3, 2]
        rays.append((b["centre"] + n * (rb + 0.5), -n, rb + 1.0))
    if rays:
        built, want = probe(rays)
        present = [k for k in range(len(beads)) if np.isfinite(built[k]) and abs(built[k] - want[k]) <= tol]
        checks.append(gate.Check("beads", len(present) == len(beads),
                                 f"{len(present)}/{len(beads)} beads standing where designed (apex within {tol:.2f} mm)"))
        held = [0] * len(stones)
        for k in present:
            for i in beads[k]["holds"]:
                held[i] += 1
        short = [i for i, h in enumerate(held) if h < spec.min_beads]
        checks.append(gate.Check("stones held", not short,
                                 f"every stone has {min(held)}-{max(held)} beads (at least {spec.min_beads})" if not short else
                                 f"{len(short)} stone(s) with fewer than {spec.min_beads} beads: {short[:6]}"))
    return checks


def check_pave(spec: PaveSpec, stl: Path, ntop_vol: float | None) -> gate.GateReport:
    """The band gate (bore, width, outer Ø over the beads, walls away from the seats, volume vs
    nTop, the section shape through the pavé against the design's), the design volume, and the
    pavé's own checks (pave_checks)."""
    import numpy as np
    b = spec.band
    d = spec.design_mesh()
    v = d.vertices
    rep = gate.check(stl, expect_inner=b.inner_diameter_mm, expect_outer=2 * float(np.hypot(v[:, 0], v[:, 1]).max()),
                     expect_width=float(v[:, 2].max() - v[:, 2].min()), expect_volume=ntop_vol,
                     wall_floor=spec.shank.wall_floor(), centre="origin", wall_ray_filter=spec.wall_ray_filter(),
                     section_design=spec.gate_section, section_tol_mm=spec.section_tolerance)
    c = band.design_volume_check(spec.expected_volume_mm3(), ntop_vol, 2.0)
    rounded, overcut = spec.shank.sharp_edge_round_mm3(), spec.shank.opening_overcut_mm3()
    if (rounded or overcut) and c.status != gate.INCOMPLETE:
        c.detail += (f" [design {spec.design_volume_mm3():.2f}" + (f" less {rounded:.2f} mm³ of edge rounding" if rounded else "")
                     + (f" less {overcut:.2f} mm³ the mesher's chamfer takes off the band's rounds" if overcut else "") + "]")
    rep.checks.append(c)
    ring = gate.load_mesh(stl)
    rep.checks += pave_checks(spec, ring)
    return rep


@dataclass
class PaveResult:
    spec: PaveSpec
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
        lines += [f"  note: {n}" for n in self.notes]
        return "\n".join(lines)


def build(spec: PaveSpec, out_dir: Path | None = None, *, notebook: Path | None = None,
          catalog_name: str = "pave_band", deliver: bool = False, deliver_project: str = "Pave",
          cast_metal: str | None = None) -> PaveResult:
    """Write the bars, the seats and the beads, run pave_band.ntop through nTopCL, gate the
    export, deliver a PASSED part."""
    problems = spec.validate()
    if problems:
        raise ValueError("; ".join(problems))
    cat = catalog.load(catalog_name)
    nb = Path(notebook) if notebook else cat.notebook
    built_notes = runs.require_built(cat, nb) if not notebook else []
    out_dir = Path(out_dir) if out_dir else config.out_dir() / "pave"
    stem = spec.stem
    run_dir, run_id = runs.fresh_run_dir(out_dir, stem)
    stl = run_dir / f"{stem}.stl"
    bars = shankmod.write_bars(spec.shank, run_dir, stem)
    seats, beads = spec.write_layer(run_dir, stem)
    values = spec.notebook_inputs(bars, seats, beads, str(stl))
    started = time.time()
    run = ntopcl.run(nb, cat.build_inputs(values), run_dir, tag=stem)
    try:
        runs.require_fresh(stl, started, "the exported ring")
    except FileNotFoundError as e:
        raise ntopcl.NtopclError(f"notebook reported success but {e}", run) from e
    entry = run.outputs.get(cat.output.get("name", "Volume"))
    ntop_vol = ntopcl.scalar_value(entry) if entry else None
    rep = check_pave(spec, stl, ntop_vol)
    gate.save(rep)
    res = PaveResult(spec, stl, run, rep, ntop_vol, run_dir, run_id)
    res.notes.append(f"stones {spec.stone_count} x {spec.stone_mm:g} mm = {spec.carats():.2f} ct {spec.material}; metal "
                     + ", ".join(f"{k} {w:.2f} g" for k, w in tables.weights_g(rep.volume_mm3).items()))
    res.notes += spec.warnings() + built_notes
    report = {
        "stem": stem, "spec_id": spec.spec_id, "run_id": run_id, "status": res.status, "ok": res.ok,
        "design": spec.design(), "inputs": values, "stl": str(stl), "bars": bars, "seats": seats, "beads": beads,
        "stones": [{"row": s.row, "col": s.col, "theta_deg": s.theta_deg, "z_mm": s.z_mm} for s in spec.stones()],
        "ntop_volume_mm3": ntop_vol, "design_volume_mm3": spec.design_volume_mm3(),
        "expected_volume_mm3": spec.expected_volume_mm3(), "gate": rep.to_dict(),
        "ntopcl_seconds": run.seconds, "block_timings": [t.__dict__ for t in run.log.timings], "notes": res.notes,
        "notebook": runs.notebook_identity(nb), "environment": runs.environment(ntopcl.version()),
    }
    (run_dir / f"{stem}.report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    if deliver and res.ok:
        res.delivered = runs.deliver(stl, run_dir, stem, deliver_project, report,
                                     extra_files=sorted(set(map(Path, bars))) + [Path(seats), Path(beads)], cast_metal=cast_metal)
    elif deliver:
        res.notes.append(f"not delivered: status {res.status}")
    return res


def band_for(stone_mm: float, rows: int, layout: str, size, *, system: str = "US", profile: str = "comfort-flat",
             thickness_mm: float | None = None, width_mm: float | None = None, mesh_tolerance_mm: float | None = None,
             **band_kw) -> band.BandSpec:
    """A band for a pavé layout: the width the rows need (their openings plus the edge walls,
    rounded up to 0.1 mm) unless given, the thickness the seats need (seat, light hole and the
    wall floor under them, at least 1.6 mm) unless given, and the pavé mesh tolerance."""
    tol = setting("pave_mesh_tolerance_mm") if mesh_tolerance_mm is None else mesh_tolerance_mm
    t = thickness_mm
    if t is None:
        probe = PaveSpec(shankmod.ShankSpec(band.BandSpec(size=size, system=system, width_mm=4.0, thickness_mm=2.0, profile=profile)),
                         stone_mm=stone_mm, rows=1)
        floor = probe.seat_depth - probe.stone.heights[1] * probe.hole_radius / probe.girdle_radius
        t = max(1.6, math.ceil((floor + tables.FLOORS["wall_good"]) * 10) / 10)
    w = width_mm
    if w is None:
        w = 6.0
        for _ in range(3):                                   # the rows' spacing barely depends on the width
            probe = PaveSpec(shankmod.ShankSpec(band.BandSpec(size=size, system=system, width_mm=w, thickness_mm=t, profile=profile,
                                                                **band_kw)), stone_mm=stone_mm, rows=rows, layout=layout)
            zmax = max(abs(z) for z in probe._row_z(probe.across_mm)) + probe.girdle_radius + probe.clearance
            w = math.ceil((2 * (zmax + tables.FLOORS["wall_marginal"]) + 1e-9) * 10) / 10
    return band.BandSpec(size=size, system=system, width_mm=w, thickness_mm=t, profile=profile, mesh_tolerance_mm=tol, **band_kw)
