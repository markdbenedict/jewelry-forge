"""Partial bezels: a bezel that keeps only two mirrored wall segments on the stone's flanks, with a hood
over each point (a pear's, both of a marquise's) - the open, east-west or tension look on any outline.

Head frame as every head (heads.HeadSpec): girdle mid-plane z = 0, table up +Z, length along X, a pear's
point at -X. The `partial_bezel_head` block builds it from nTop's own primitives, every number from
PartialBezelSpec.notebook_inputs:

    grown    Offset Body (Seat Cutter, Wall)                       the bezel's metal, as bezel_head
    mask     a sharp union of
               cup    Box from Corners, z Bezel Bottom .. Cup Top  the full cup under the girdle: the bearing
               wall   two half-space boxes (y >= 0 turned by Wall To Angle, y <= 0 turned by Wall From Angle,
                      both about the vertical line through (Wall Centre X, 0)), z Bezel Bottom .. Bezel Top -
                      the +y wall's sector - and its Mirror Body across y = 0
               hoods  vertical Cylinders at (Hood X, 0) and (Hood 2 X, 0), radius Hood Reach, z Bezel Bottom ..
                      Hood Top (an unused hood stands far outside the stone: it cuts nothing)
             the pieces overlap (the walls and hoods span the cup's height): no face is shared
    head     (grown ∩ mask, ONE blended intersection: the rim, the wall ends and the hood rounded) − Seat Cutter

No blended union anywhere: a smooth union of bodies that meet on a face swells them (2026-11-05, the
pearl's cup), so the pieces join as a sharp mask and the one blend is the intersection with the metal.

The walls are given as fractions of the half outline from the point (0) to the far pole (1) - a pear's
flanks are not circular sectors - and turned into angles about the outline's centroid for nTop. The
checks probe the design's intent, not the builder: metal along each wall, none over the open stretches,
a hood at each point, nothing touching the stone near its point, the bearing all round."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from . import gems, geom, tables
from .heads import (BezelSpec, PRONG_TIP_FLOOR, WALL_FLOOR, _offset_convex, _slab, blend_estimate, blend_problems,
                    head_blend_radius, outline_count, seat_regions)

HOOD_GAP_MM = 0.6              # between a hood's reach and the wall's start, by default
HOOD_RISE_MM = 0.3             # the hood stands this far above the walls' top, by default
CUP_BELOW_GIRDLE_MM = 0.1      # the full cup stops this far under the girdle: the girdle shows where there is no wall
FAR_X_MM = 60.0                # an unused hood's x: far outside any stone
PROBE_OUT_MM = 1.5             # probes start this far outside the wall
HALF_BOX_MM = 40.0             # the wall half-boxes' extent (any stone fits)

# default wall stretches (fractions of the half outline from the point / -X): a pear's flanks from just past
# its hood to past its widest point; a marquise's between its hoods; anything else its two sides (east-west)
DEFAULT_SPAN = {"pear": (None, 0.70), "marquise": (None, None)}
SIDES_SPAN = (0.30, 0.70)


def half_outline(stone: gems.StoneSpec, n: int = 4096):
    """The +y half of the girdle outline from the -X end to the +X end: (points (k, 2), cumulative
    arc length (k,), centroid x). Ordered by angle about the centroid, 180° down to 0°."""
    import numpy as np
    from shapely.geometry import Polygon
    xy = np.asarray(stone.outline(n), float)
    cx = float(Polygon(xy).centroid.x)
    ang = np.arctan2(xy[:, 1], xy[:, 0] - cx)
    keep = ang >= -1e-9
    pts, a = xy[keep], ang[keep]
    order = np.argsort(-a)
    pts = pts[order]
    ends = [np.array([float(xy[:, 0].min()), 0.0]), np.array([float(xy[:, 0].max()), 0.0])]
    pts = np.vstack([ends[0], pts, ends[1]])
    cum = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))])
    return pts, cum, cx


def station(stone: gems.StoneSpec, f: float, side: int = 1):
    """(point, outward unit normal) on the outline at fraction f of the half outline (side +1: +y, -1: -y)."""
    import numpy as np
    pts, cum, _ = half_outline(stone)
    s = float(np.clip(f, 0.0, 1.0)) * cum[-1]
    i = int(np.clip(np.searchsorted(cum, s), 1, len(pts) - 1))
    t = (s - cum[i - 1]) / max(cum[i] - cum[i - 1], 1e-12)
    q = pts[i - 1] + t * (pts[i] - pts[i - 1])
    a, b = pts[max(i - 2, 0)], pts[min(i + 1, len(pts) - 1)]
    tan = (b - a) / max(np.linalg.norm(b - a), 1e-12)
    m = np.array([tan[1], -tan[0]])
    cx = half_outline(stone)[2]
    if np.dot(m, q - np.array([cx, 0.0])) < 0:              # outward: away from the centroid (a convex outline)
        m = -m
    if side < 0:
        q, m = q * [1.0, -1.0], m * [1.0, -1.0]
    return q, m


@dataclass
class PartialBezelSpec(BezelSpec):
    """A bezel kept only on two mirrored wall stretches, with a hood over each point. Fractions of the half
    outline from the -X end (a pear's point); None: by shape (DEFAULT_SPAN). Inherits the bezel's wall, lip,
    cup depth, clearance and blend; it has no light windows."""
    HEAD_KIND = "partial"                 # what SolitaireSpec.kind reads: a marker, not isinstance - a test that purges and
                                          # re-imports ntopjewel leaves two copies of this class, and isinstance fails across them
    wall_from: float | None = None
    wall_to: float | None = None
    hoods: bool = True                    # a hood over each point (pear: one, marquise: two); others have none
    hood_reach_mm: float | None = None    # default max(1.5, 0.2 x the width), as a V-prong's arm
    hood_rise_mm: float = HOOD_RISE_MM
    cup_below_girdle_mm: float = CUP_BELOW_GIRDLE_MM

    def __post_init__(self):
        self.windows = 0

    # ---- numbers ----------------------------------------------------------------------------
    @property
    def hood_points(self) -> list[float]:
        """x of every hood (y = 0): a pear's point, both of a marquise's; none for the others or without hoods."""
        if not self.hoods:
            return []
        L = self.stone.length / 2
        return {"pear": [-L], "marquise": [-L, L]}.get(self.stone.shape, [])

    @property
    def hood_reach(self) -> float:
        return float(self.hood_reach_mm) if self.hood_reach_mm is not None else max(1.5, 0.2 * self.stone.width)

    def _fraction_past(self, x_end: float, reach: float) -> float:
        """The fraction of the half outline where the outline leaves the hood at x_end (reach + the gap)."""
        import numpy as np
        pts, cum, _ = half_outline(self.stone)
        d = np.hypot(pts[:, 0] - x_end, pts[:, 1])
        far = d >= reach + HOOD_GAP_MM
        idx = np.nonzero(far)[0]
        if not len(idx):
            return 0.5
        i = idx[0] if x_end < 0 else idx[-1]
        return float(cum[i] / cum[-1])

    @property
    def span(self) -> tuple[float, float]:
        """(from, to): the wall's stretch, fractions of the half outline from -X."""
        lo, hi = DEFAULT_SPAN.get(self.stone.shape, SIDES_SPAN)
        hp = self.hood_points
        if lo is None:
            lo = self._fraction_past(-self.stone.length / 2, self.hood_reach) if hp else SIDES_SPAN[0]
        if hi is None:
            hi = self._fraction_past(self.stone.length / 2, self.hood_reach) if len(hp) > 1 else SIDES_SPAN[1]
        return (float(self.wall_from) if self.wall_from is not None else lo,
                float(self.wall_to) if self.wall_to is not None else hi)

    @property
    def centre_x(self) -> float:
        return half_outline(self.stone)[2]

    def angles(self) -> tuple[float, float]:
        """(Wall From Angle, Wall To Angle), degrees about the vertical through (centre_x, 0) from +X: the
        stretch's start (nearer the point, the larger angle) and end."""
        cx = self.centre_x
        out = []
        for f in self.span:
            q, _ = station(self.stone, f)
            out.append(math.degrees(math.atan2(q[1], q[0] - cx)))
        return out[0], out[1]

    @property
    def cup_top(self) -> float:
        return -self.stone.girdle / 2 - self.cup_below_girdle_mm

    @property
    def hood_top(self) -> float:
        return self.z_top + self.hood_rise_mm

    def lowest_z(self) -> float:
        return self.z_bottom

    # ---- notebook ----------------------------------------------------------------------------
    def notebook_inputs(self, seat_path: str, windows_path: str = "", output_path: str | None = None) -> dict:
        a_from, a_to = self.angles()
        hx = self.hood_points + [FAR_X_MM] * (2 - len(self.hood_points))
        ins = {"Seat Path": seat_path, "Clearance": round(self.clearance, 4), "Wall": round(self.wall, 4),
               "Bezel Bottom": round(self.z_bottom, 4), "Cup Top": round(self.cup_top, 4), "Bezel Top": round(self.z_top, 4),
               "Wall Centre X": round(self.centre_x, 4), "Wall From Angle": round(a_from, 4), "Wall To Angle": round(a_to, 4),
               "Hood X": round(hx[0], 4), "Hood 2 X": round(hx[1], 4), "Hood Reach": round(self.hood_reach, 4),
               "Hood Top": round(self.hood_top, 4), "Blend Radius": round(self.blend, 4)}
        if output_path is not None:
            ins["Mesh Tolerance"] = self.mesh_tolerance_mm
            ins["Output Path"] = output_path
        return ins

    def design(self) -> dict:
        d = asdict(self)
        d["stone"] = self.stone.design()
        d["inputs"] = self.notebook_inputs("")
        d["span"] = [round(v, 4) for v in self.span]
        return d

    @property
    def stem(self) -> str:
        from . import runs
        return f"pbezel_{self.stone.stem[len('stone_'):]}_{runs.spec_id(self.design())}"

    def blend_junctions(self) -> dict:
        return partial_junctions(self.notebook_inputs(""), self.seat.envelope())

    def blend_volume_mm3(self) -> float:
        return blend_estimate(self.notebook_inputs(""), self.seat.envelope())

    def design_mesh(self, ops: geom.Booleans = geom.SHARP):
        return partial_bezel_mesh(self.notebook_inputs(""), self.seat.envelope(), ops=ops)

    # ---- checks ----------------------------------------------------------------------------
    def validate(self) -> list[str]:
        p = self.stone.validate()
        if p:
            return p
        if not self.stone.faceted and self.stone.shape != "cabochon":
            p.append(f"a partial bezel holds a faceted stone or a cabochon, not a {self.stone.shape}")
            return p
        if self.wall < WALL_FLOOR:
            p.append(f"bezel wall {self.wall} mm below the wall floor {WALL_FLOOR} mm")
        if self.wall > 1.2:
            p.append(f"a {self.wall} mm wall is too stiff to burnish over the stone (0.5-0.8 mm)")
        crown, _ = self.stone.heights
        if not 0.2 <= self.lip <= max(0.2, 0.8 * crown):
            p.append(f"lip {self.lip} mm: 0.2 mm up to 80 % of the crown ({0.8 * crown:.2f} mm)")
        lo, hi = self.span
        if not 0.0 <= lo < hi <= 1.0:
            p.append(f"the wall runs {lo:.2f} .. {hi:.2f} of the half outline: 0 <= from < to <= 1")
            return p
        if lo <= 0.0 and hi >= 1.0:
            p.append("a wall from end to end is a full bezel (--bezel)")
        if hi - lo < 0.1:
            p.append(f"a wall of {hi - lo:.0%} of the flank holds nothing: at least 10 %")
        a_from, a_to = self.angles()
        if not 0.0 < a_from - a_to < 175.0:
            p.append(f"the wall's sector {a_to:.0f}°..{a_from:.0f}° about the centre is not a wedge nTop's two half-spaces make")
        pts, cum, _ = half_outline(self.stone)
        wall_len = (hi - lo) * cum[-1]
        if wall_len < 2 * self.blend + WALL_FLOOR:
            p.append(f"the wall is {wall_len:.2f} mm long: its rounded ends ({self.blend:g} mm) leave too little")
        if self.hood_points:
            if self.hood_reach < PRONG_TIP_FLOOR:
                p.append(f"hood reach {self.hood_reach} mm under the prong-tip floor {PRONG_TIP_FLOOR} mm")
            if not 0.0 <= self.hood_rise_mm <= 1.0:
                p.append(f"the hood rises {self.hood_rise_mm} mm above the walls: 0 to 1 mm")
        if self.z_bottom > self.cup_top - 0.3:
            p.append("the cup is too shallow to carry the stone: more pavilion under the girdle")
        if not 0.0 <= self.cup_below_girdle_mm <= 0.5:
            p.append(f"the cup stops {self.cup_below_girdle_mm} mm under the girdle: 0 to 0.5 mm")
        p += blend_problems(self.blend, self.wall / 2)
        return p

    def describe(self) -> str:
        lo, hi = self.span
        a_from, a_to = self.angles()
        hoods = (f"a hood over {'each point' if len(self.hood_points) > 1 else 'the point'} (reach {self.hood_reach:.2f} mm, "
                 f"{self.hood_rise_mm:g} mm above the walls)" if self.hood_points else "no hoods")
        return (f"{self.stem}: partial bezel on a {self.stone.describe()}\n"
                f"  two walls {lo:.2f}..{hi:.2f} of each flank from the -X end ({a_to:.1f}°..{a_from:.1f}° about x "
                f"{self.centre_x:.2f}), wall {self.wall} mm, lip {self.lip} mm (top z {self.z_top:.2f}); {hoods}\n"
                f"  a full cup under the girdle from z {self.z_bottom:.2f} to {self.cup_top:.2f} (the bearing); clearance "
                f"{self.clearance} mm; edges blended {self.blend:g} mm")


# ---- the geometry from the block's numbers (the spec's model and the simulated nTop share it) ------
def _half_box(angle_deg: float, upper: bool, z0: float, z1: float, cx: float, cell: float = 0.6):
    """The half-space y >= 0 (upper) or y <= 0 as a box HALF_BOX_MM across, turned by angle about the
    vertical through (cx, 0): as the block's Box from Corners + Rotation Transform. Subdivided like _slab."""
    import trimesh
    h = HALF_BOX_MM
    box = trimesh.creation.box(bounds=[[-h, 0.0 if upper else -h, z0], [h, h if upper else 0.0, z1]])
    for _ in range(max(0, math.ceil(math.log2(2 * h / cell)) - 3)):
        box = box.subdivide()
    box.apply_translation((cx, 0.0, 0.0))
    box.apply_transform(trimesh.transformations.rotation_matrix(math.radians(angle_deg), [0, 0, 1], [cx, 0.0, 0.0]))
    return box


def partial_mask(v: dict, envelope, mirror: bool = True, hoods: bool = True):
    """The mask the block intersects with the grown cutter: cup slab ∪ the +y wall's sector (∪ its mirror)
    ∪ the hood cylinders. `mirror` / `hoods` False: the simulated nTop's faults (a notebook that never
    mirrored the wall, or lost the hoods)."""
    import trimesh
    c, wall = float(v["Clearance"]), float(v["Wall"])
    grown = _offset_convex(envelope, c + wall)
    zb, zc, zt, ztop = float(v["Bezel Bottom"]), float(v["Cup Top"]), float(v["Bezel Top"]), float(v["Hood Top"])
    cx = float(v["Wall Centre X"])
    cup = _slab(zb, zc, grown)
    sector = trimesh.boolean.intersection([_half_box(float(v["Wall To Angle"]), True, zb, zt, cx),
                                           _half_box(float(v["Wall From Angle"]), False, zb, zt, cx)], engine="manifold")
    parts = [cup, sector]
    if mirror:
        m = sector.copy()
        m.apply_transform(trimesh.transformations.reflection_matrix([0, 0, 0], [0, 1, 0]))   # trimesh keeps it outward
        parts.append(m)
    if hoods:
        r = float(v["Hood Reach"])
        for key in ("Hood X", "Hood 2 X"):
            x = float(v[key])
            cyl = trimesh.creation.cylinder(radius=r, segment=[[x, 0.0, zb], [x, 0.0, ztop]], sections=96)
            parts.append(cyl)
    return trimesh.boolean.union(parts, engine="manifold")


def partial_bezel_mesh(v: dict, envelope, cut_seat: bool = True, ops: geom.Booleans = geom.SHARP,
                       mirror: bool = True, hoods: bool = True):
    """The partial bezel in the block's order: grown cutter ∩ mask (ONE blended intersection; `ops`), then
    the seat cut."""
    c, wall = float(v["Clearance"]), float(v["Wall"])
    grown = _offset_convex(envelope, c + wall)
    head = ops.intersect(grown, partial_mask(v, envelope, mirror=mirror, hoods=hoods), head_blend_radius(v))
    if cut_seat:
        head = ops.difference(head, [_offset_convex(envelope, c)])
    return ops.clean(head)


def partial_junctions(v: dict, envelope) -> dict:
    """The one blended intersection's edges (rounded away); no union to fill."""
    import numpy as np
    grown = _offset_convex(envelope, float(v["Clearance"]) + float(v["Wall"]))
    return {"union": np.zeros((0, 2, 3)), "intersect": geom.junction_segments(grown, partial_mask(v, envelope), "intersect")}


# ---- the gate: the design's intent probed on the built head (head frame) ----------------------------
def _probe(mesh, q, m, z: float, reach: float):
    """Cast from PROBE_OUT_MM + reach outside the outline point q along -m at height z: the first metal's
    distance outside the outline (negative: inside it), or None if the ray meets nothing before 4 mm inside."""
    import numpy as np
    o = np.array([q[0] + m[0] * (reach + PROBE_OUT_MM), q[1] + m[1] * (reach + PROBE_OUT_MM), z])
    d = -np.array([m[0], m[1], 0.0])
    hits, _, _ = mesh.ray.intersects_location([o], [d], multiple_hits=False)
    if not len(hits):
        return None
    off = reach + PROBE_OUT_MM - float(np.linalg.norm(hits[0] - o))
    return off if off > -4.0 else None


def partial_bezel_checks(spec: PartialBezelSpec, local) -> list:
    """`walls` (metal along both stretches at the girdle and half way up the lip), `open` (no metal over
    the stretches without a wall, above the cup), `hoods` (metal at each point), `point clear` (the stone
    untouched near each point), `bearing` (the cup under the girdle all round) - on `local`, the head in its
    own frame. A missing probe hit is a failure, never a pass."""
    import numpy as np
    import trimesh
    from . import gate
    s, g = spec.stone, spec.stone.girdle
    reach = spec.clearance + spec.wall
    tol = 0.15 + spec.mesh_tolerance_mm
    lo, hi = spec.span
    pts, cum, _ = half_outline(s)
    pad = (spec.blend + 0.3) / cum[-1]                              # clear of the rounded wall ends
    z_mid = g / 2 + spec.lip / 2
    out = []

    want = [f for f in np.linspace(lo + pad, hi - pad, 5)] if hi - lo > 2 * pad else [(lo + hi) / 2]
    found, miss = 0, []
    for side in (1, -1):
        for f in want:
            for z in (0.0, z_mid):
                q, m = station(s, f, side)
                off = _probe(local, q, m, z, reach)
                if off is not None and spec.clearance - tol <= off <= reach + tol:
                    found += 1
                else:
                    miss.append(f"{'+' if side > 0 else '-'}y {f:.2f} z {z:.2f}")
    n = 2 * len(want) * 2
    out.append(gate.Check("walls", found == n, f"{found}/{n} probes meet the wall along both stretches "
                                               f"({lo:.2f}..{hi:.2f} of each flank)" + (f"; missing at {', '.join(miss[:4])}" if miss else "")))

    hood_x = spec.hood_points
    open_f = []
    for f in np.linspace(0.0, 1.0, 41):
        if lo - pad < f < hi + pad:
            continue
        q, _ = station(s, f)
        if any(math.hypot(q[0] - x, q[1]) < spec.hood_reach + spec.blend + 0.4 for x in hood_x):
            continue
        open_f.append(float(f))
    stray = []
    for side in (1, -1):
        for f in open_f:
            q, m = station(s, f, side)
            off = _probe(local, q, m, z_mid, reach)
            if off is not None and off > -0.1:
                stray.append(f"{'+' if side > 0 else '-'}y {f:.2f} ({off:+.2f})")
    if open_f:
        out.append(gate.Check("open", not stray, f"{2 * len(open_f) - len(stray)}/{2 * len(open_f)} probes over the "
                                                 f"stretches without a wall meet no metal above the cup"
                                                 + (f"; metal at {', '.join(stray[:4])}" if stray else "")))
    if hood_x:
        got, kept = 0, 0.0
        stone = s.mesh()
        for x in hood_x:
            m = np.array([-1.0 if x < 0 else 1.0, 0.0])
            off = _probe(local, np.array([x, 0.0]), m, z_mid, reach)
            got += off is not None and spec.clearance - tol <= off <= reach + tol
            ball = trimesh.creation.icosphere(subdivisions=3, radius=1.0)
            ball.apply_translation((x, 0.0, 0.0))
            if local.is_watertight:
                near = trimesh.boolean.intersection([local, trimesh.boolean.intersection([stone, ball], engine="manifold")],
                                                    engine="manifold")
                kept = max(kept, float(near.volume) if len(near.faces) else 0.0)
            else:
                kept = float("nan")
        out.append(gate.Check("hoods", got == len(hood_x), f"{got}/{len(hood_x)} hoods stand over the point"
                                                            f"{'s' if len(hood_x) > 1 else ''} (half way up the lip)"))
        out.append(gate.Check("point clear", kept <= 1e-3, f"metal ∩ stone within 1 mm of each point: {kept:.4f} mm³ "
                                                             f"(at most 0.001)"))
    seen = 0
    stations = np.linspace(0.02, 0.98, 6)
    for side in (1, -1):
        for f in stations:
            q, m = station(s, f, side)
            off = _probe(local, q, m, spec.cup_top - 0.2, reach)
            seen += off is not None and off > -2.0
    out.append(gate.Check("bearing", seen == 2 * len(stations), f"{seen}/{2 * len(stations)} probes meet the cup "
                                                                f"{0.2 + spec.cup_below_girdle_mm:.1f} mm under the girdle"))
    return out


def check_partial_bezel(spec: PartialBezelSpec, stl, ntop_vol: float | None):
    """Closed, one shell, stone fits, seated, drop-in clear, the partial-bezel probes, volume vs nTop and vs
    the independent head (with the blend's estimate)."""
    import trimesh
    from . import band, gate
    rep = gate.check(stl, expect_volume=ntop_vol, wall_floor=0.0, wall_samples=0, tol_volume_pct=2.0)
    rep.checks = [c for c in rep.checks if c.name != "wall thickness"]
    head = gate.load_mesh(stl)
    stone = spec.stone.mesh()
    overlap = float("nan")
    if head.is_watertight:
        inter = trimesh.boolean.intersection([head, stone], engine="manifold")
        overlap = float(inter.volume) if len(inter.faces) else 0.0
    allowed = 0.002 * stone.volume
    rep.checks.append(gate.Check("stone fits", overlap <= allowed, f"head ∩ stone {overlap:.3f} mm³ (allowed {allowed:.3f})"))
    under, above = seat_regions(spec.stone, spec.clearance)
    g = spec.stone.girdle
    seated = outline_count(head, -g / 2 - 0.3, under)
    blocking = outline_count(head, g / 2 + 0.15, above)
    rep.checks.append(gate.Check("seated", seated >= 1, f"{seated} piece(s) of the cup under the girdle"))
    rep.checks.append(gate.Check("drop-in clear", blocking == 0, f"{blocking} pieces inside the girdle line above the girdle"))
    rep.checks += partial_bezel_checks(spec, head)
    rep.checks.append(band.blended_design_volume_check(float(spec.design_mesh().volume), spec.blend_volume_mm3(), ntop_vol, 3.0))
    return rep


def build_partial_bezel(spec: PartialBezelSpec, out_dir=None, *, notebook=None,
                        catalog_name: str = "partial_bezel_head_harness"):
    """Run the partial_bezel_head block through its harness under nTopCL and gate it."""
    import json
    import time
    from pathlib import Path
    from . import catalog, config, ntopcl, runs
    from . import gate as _gate
    from .heads import HeadResult
    problems = spec.validate()
    if problems:
        raise ValueError("; ".join(problems))
    cat = catalog.load(catalog_name)
    nb = Path(notebook) if notebook else cat.notebook
    built_notes = runs.require_built(cat, nb) if not notebook else []
    run_dir, run_id = runs.fresh_run_dir(Path(out_dir) if out_dir else config.out_dir() / "head", spec.stem)
    envelope = run_dir / f"{spec.stem}.envelope.stl"
    spec.seat.envelope().export(str(envelope))
    spec.stone.mesh().export(str(run_dir / f"{spec.stem}.stone.stl"))
    stl = run_dir / f"{spec.stem}.stl"
    inputs = spec.notebook_inputs(str(envelope), "", str(stl))
    started = time.time()
    run = ntopcl.run(nb, cat.build_inputs(inputs), run_dir, tag=spec.stem)
    try:
        runs.require_fresh(stl, started, "the exported partial bezel")
    except FileNotFoundError as e:
        raise ntopcl.NtopclError(f"notebook reported success but {e}", run) from e
    entry = run.outputs.get(cat.output.get("name", "Volume"))
    ntop_vol = ntopcl.scalar_value(entry) if entry else None
    rep = check_partial_bezel(spec, stl, ntop_vol)
    _gate.save(rep)
    res = HeadResult(spec, stl, run, rep, ntop_vol, run_dir, run_id)
    res.notes.append("metal: " + ", ".join(f"{k} {w:.2f} g" for k, w in tables.weights_g(rep.volume_mm3).items()))
    res.notes += built_notes
    (run_dir / f"{spec.stem}.report.json").write_text(json.dumps({
        "stem": spec.stem, "run_id": run_id, "status": res.status, "design": spec.design(), "inputs": inputs,
        "ntop_volume_mm3": ntop_vol, "gate": rep.to_dict(), "notebook": runs.notebook_identity(nb),
        "environment": runs.environment(ntopcl.version()), "notes": res.notes}, indent=2, default=str), encoding="utf-8")
    return res
