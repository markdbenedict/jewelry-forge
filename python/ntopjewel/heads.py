"""Prong heads: N prongs on an open basket, the seat cut by the stone_seat block.

Coordinates as the stones: girdle mid-plane at z = 0, table up (+Z), head axis = Z.

    prongs   N straight rods (radius rho) from a foot below the culet (radius r_base,
             z_base) out to a tip above the girdle (radius R_prong, z_tip), a sphere on each
             end; one prong built at `angle offset`, polar-arrayed N times about Z
    basket   two torus rails through the prong axes: the lower one ties the feet, the upper
             one braces the prongs just under the girdle. Below it the basket is open - the
             light and cleaning gallery under the pavilion
    seat     minus the stone_seat cutter (stone + straight drop-in path, offset by the
             clearance): above the girdle it trims every prong back to the girdle line + the
             clearance, so the stone drops in from above and the setter bends the tips over;
             below it leaves a LEDGE `ledge_mm` deep in every prong that the girdle sits on

Python decides every number (`HeadSpec`), the notebook only builds; `head_mesh(inputs)`
builds the same head from the same input numbers with trimesh + manifold3d - the independent
figure the gate checks nTop's volume against, and what the simulated nTop returns in tests.
Version 1 is for round stones: the rails are tori. Fancy outlines need rails that follow the
outline (a Python-written rail mesh, like the seat envelope) - the next step after the
solitaire gate.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import gems, tables

PRONG_TIP_FLOOR = tables.FLOORS["prong_tip_dia"]        # 0.8 mm: what is left of a prong above the girdle
WALL_FLOOR = tables.FLOORS["wall_marginal"]


@dataclass
class HeadSpec:
    stone: gems.StoneSpec
    prongs: int = 6
    prong_dia_mm: float | None = None      # default: max(0.8 + ledge + clearance + 0.05, 0.18 x stone width)
    ledge_mm: float = 0.30                 # how far each prong reaches under the girdle
    tip_above_mm: float | None = None      # prong tip centre above the girdle top; default max(0.8, 0.8 x crown)
    base_drop_mm: float = 0.5              # foot centres this far below the culet
    base_ratio: float = 0.5                # foot radius / girdle radius (the basket's taper)
    rail_dia_mm: float | None = None       # default 0.8 x prong diameter, at least the wall floor
    rail_below_girdle_mm: float = 1.4      # upper rail centre this far below the girdle bottom (the pavilion narrows faster than the prongs)
    angle_offset_deg: float | None = None  # first prong's angle; default half a spacing (prongs off the band axis)
    clearance_mm: float | None = None      # stone_seat clearance; default tables settings
    mesh_tolerance_mm: float = 0.05

    # ---- numbers -------------------------------------------------------------------------
    @property
    def rho(self) -> float:
        floor = PRONG_TIP_FLOOR + self.ledge_mm + self.clearance + 0.05          # what stays above the girdle >= the tip floor
        d = self.prong_dia_mm if self.prong_dia_mm is not None else max(floor, 0.18 * self.stone.width)
        return float(d) / 2

    @property
    def rail_rho(self) -> float:
        d = self.rail_dia_mm if self.rail_dia_mm is not None else max(WALL_FLOOR * 1.6, 1.5 * self.rho)
        return float(d) / 2

    @property
    def clearance(self) -> float:
        return tables.SETTINGS["seat_clearance_mm"] if self.clearance_mm is None else float(self.clearance_mm)

    @property
    def seat(self) -> gems.SeatSpec:
        return gems.SeatSpec(self.stone, clearance_mm=self.clearance, mesh_tolerance_mm=self.mesh_tolerance_mm)

    @property
    def spacing_deg(self) -> float:
        return 360.0 / self.prongs

    @property
    def offset_deg(self) -> float:
        return self.spacing_deg / 2 if self.angle_offset_deg is None else float(self.angle_offset_deg)

    def layout(self) -> dict:
        """Prong axis end points (radius, z), rails (z, radius), all in mm."""
        s = self.stone
        Rg, g = s.width / 2, s.girdle
        crown, pav = s.heights
        rho = self.rho
        r_tip = Rg + rho - self.ledge_mm                       # prong axis radius at the tip
        z_tip = g / 2 + (self.tip_above_mm if self.tip_above_mm is not None else max(0.8, 0.8 * crown))
        z_base = -(g / 2 + pav) - self.base_drop_mm
        r_base = self.base_ratio * Rg

        def axis_r(z):                                         # prong axis radius at height z
            t = (z - z_base) / (z_tip - z_base)
            return r_base + t * (r_tip - r_base)

        z_rail = -g / 2 - self.rail_below_girdle_mm
        return {"r_tip": r_tip, "z_tip": z_tip, "r_base": r_base, "z_base": z_base,
                "rail_upper": (z_rail, axis_r(z_rail)), "rail_lower": (z_base, r_base),
                "axis_r_at_girdle": axis_r(-g / 2)}

    def notebook_inputs(self, seat_path: str, output_path: str | None = None) -> dict:
        lay = self.layout()
        a = math.radians(self.offset_deg)
        c, s_ = math.cos(a), math.sin(a)
        (zu, ru), (zl, rl) = lay["rail_upper"], lay["rail_lower"]
        ins = {
            "Seat Path": seat_path,
            "Clearance": round(self.clearance, 4),
            "Prong Count": int(self.prongs),
            "Prong Spacing": round(self.spacing_deg, 4),
            "Prong Radius": round(self.rho, 4),
            "Base X": round(lay["r_base"] * c, 4), "Base Y": round(lay["r_base"] * s_, 4), "Base Z": round(lay["z_base"], 4),
            "Tip X": round(lay["r_tip"] * c, 4), "Tip Y": round(lay["r_tip"] * s_, 4), "Tip Z": round(lay["z_tip"], 4),
            "Upper Rail Z": round(zu, 4), "Upper Rail Radius": round(ru, 4),
            "Lower Rail Z": round(zl, 4), "Lower Rail Radius": round(rl, 4),
            "Rail Tube Radius": round(self.rail_rho, 4),
        }
        if output_path is not None:
            ins["Mesh Tolerance"] = self.mesh_tolerance_mm
            ins["Output Path"] = output_path
        return ins

    def design(self) -> dict:
        d = asdict(self)
        d["inputs"] = self.notebook_inputs("")
        return d

    @property
    def stem(self) -> str:
        from . import runs
        return f"head_{self.prongs}prong_{self.stone.stem[len('stone_'):]}_{runs.spec_id(self.design())}"

    # ---- checks on the design --------------------------------------------------------------
    def validate(self) -> list[str]:
        p = self.stone.validate()
        if self.stone.shape != "round":
            p.append(f"prong_head v1 builds round stones (torus rails); {self.stone.shape} needs outline rails")
            return p
        if self.prongs not in (3, 4, 5, 6, 8):
            p.append("prongs: 3, 4, 5, 6 or 8")
        tip_left = 2 * self.rho - self.ledge_mm - self.clearance
        if tip_left < PRONG_TIP_FLOOR:
            p.append(f"prong left above the girdle is {tip_left:.2f} mm thick (diameter - ledge - clearance); "
                     f"floor {PRONG_TIP_FLOOR} mm: thicker prongs or a shallower ledge")
        if self.ledge_mm < 0.15:
            p.append("ledge under 0.15 mm will not carry the stone")
        if 2 * self.rail_rho < WALL_FLOOR:
            p.append(f"rail diameter {2 * self.rail_rho:.2f} mm below the wall floor {WALL_FLOOR} mm")
        lay = self.layout()
        zu, ru = lay["rail_upper"]
        _, pav = self.stone.heights
        g = self.stone.girdle
        pav_r = self.stone.width / 2 * max(0.0, 1 - (abs(zu) - g / 2) / pav)        # pavilion radius at the rail
        if ru - self.rail_rho < pav_r + self.clearance + 0.05:
            p.append(f"upper rail (inner edge r {ru - self.rail_rho:.2f}) runs into the pavilion (r {pav_r:.2f}): "
                     f"lower it or thin it")
        gap = 2 * lay["r_base"] * math.sin(math.pi / self.prongs) - 2 * self.rho
        if gap < 0:
            pass                                                                    # feet merge into a solid foot: fine
        if zu - self.rail_rho < lay["z_base"] + self.rail_rho:
            p.append("the two rails overlap: raise the upper rail or drop the base")
        return p

    def describe(self) -> str:
        lay = self.layout()
        return (f"{self.stem}: {self.prongs} prongs of {2 * self.rho:.2f} mm on a {self.stone.describe()}\n"
                f"  prong axis r {lay['r_base']:.3f} @ z {lay['z_base']:.3f} -> r {lay['r_tip']:.3f} @ z {lay['z_tip']:.3f}, "
                f"first at {self.offset_deg:g}°, every {self.spacing_deg:g}°; ledge {self.ledge_mm} mm, clearance {self.clearance} mm\n"
                f"  rails: upper r {lay['rail_upper'][1]:.3f} @ z {lay['rail_upper'][0]:.3f}, lower r {lay['rail_lower'][1]:.3f} @ "
                f"z {lay['rail_lower'][0]:.3f}, tube {2 * self.rail_rho:.2f} mm; tip left above the girdle "
                f"{2 * self.rho - self.ledge_mm - self.clearance:.2f} mm")


# ---- the independent geometry ---------------------------------------------------------------
def head_mesh(v: dict, seat_mesh=None, cut_seat: bool = True):
    """The head from the notebook's input numbers (trimesh + manifold3d). `seat_mesh` is the
    seat envelope (stone + drop path); it is offset by Clearance (exact for a convex body) and
    subtracted."""
    import numpy as np
    import trimesh
    rho = float(v["Prong Radius"])
    base = np.array([v["Base X"], v["Base Y"], v["Base Z"]], float)
    tip = np.array([v["Tip X"], v["Tip Y"], v["Tip Z"]], float)
    parts = []
    for k in range(int(v["Prong Count"])):
        rot = trimesh.transformations.rotation_matrix(math.radians(k * float(v["Prong Spacing"])), [0, 0, 1])[:3, :3]
        a, b = rot @ base, rot @ tip
        rod = trimesh.creation.cylinder(radius=rho, segment=[a, b], sections=48)
        parts += [rod, _ball(a, rho), _ball(b, rho)]
    for zk, rk in (("Upper Rail Z", "Upper Rail Radius"), ("Lower Rail Z", "Lower Rail Radius")):
        t = trimesh.creation.torus(float(v[rk]), float(v["Rail Tube Radius"]), major_sections=180, minor_sections=24)
        t.apply_translation((0.0, 0.0, float(v[zk])))
        parts.append(t)
    head = trimesh.boolean.union(parts, engine="manifold")
    if cut_seat and seat_mesh is not None:
        cutter = _offset_convex(seat_mesh, float(v["Clearance"]))
        head = trimesh.boolean.difference([head, cutter], engine="manifold")
    return head


def _ball(centre, r):
    import trimesh
    b = trimesh.creation.icosphere(subdivisions=3, radius=r)
    b.apply_translation(centre)
    return b


def _offset_convex(mesh, c: float):
    import trimesh
    if c <= 0:
        return mesh
    ball = trimesh.creation.icosphere(subdivisions=3, radius=c).vertices
    pts = (mesh.vertices[:, None, :] + ball[None, :, :]).reshape(-1, 3)
    return trimesh.convex.convex_hull(pts)


def design_mesh(spec: HeadSpec):
    return head_mesh(spec.notebook_inputs(""), spec.seat.envelope())


# ---- the gate for a head ----------------------------------------------------------------------
def check_head(spec: HeadSpec, stl: Path, ntop_vol: float | None):
    """Closed, one shell, nTop volume vs mesh and vs the independent design mesh, and the two
    things a head is for: the stone FITS (head ∩ stone ≈ 0) and it SITS (a ledge under the
    girdle in every prong, nothing inside the girdle line above it)."""
    import numpy as np
    import trimesh
    from . import band, gate
    rep = gate.check(stl, expect_volume=ntop_vol, wall_floor=0.0, wall_samples=0, tol_volume_pct=2.0)
    rep.checks = [c for c in rep.checks if c.name != "wall thickness"]
    head = gate.load_mesh(stl)
    stone = spec.stone.mesh()
    if head.is_watertight:
        inter = trimesh.boolean.intersection([head, stone], engine="manifold")
        overlap = float(inter.volume) if len(inter.faces) else 0.0
    else:
        overlap = float("nan")
    allowed = 0.002 * stone.volume
    rep.checks.append(gate.Check("stone fits", overlap <= allowed,
                                 f"head ∩ stone {overlap:.3f} mm³ (allowed {allowed:.3f}: meshing noise only)"))
    Rg, g = spec.stone.width / 2, spec.stone.girdle
    ledges = _inner_count(head, -g / 2 - 0.3, Rg - 0.1)          # metal under the girdle's rim, outside the pavilion
    above = _inner_count(head, g / 2 + 0.15, Rg + spec.clearance * 0.5)
    rep.checks.append(gate.Check("seat ledges", ledges == spec.prongs,
                                 f"{ledges} prongs reach under the girdle (expected {spec.prongs})"))
    rep.checks.append(gate.Check("drop-in clear", above == 0,
                                 f"{above} prongs inside the girdle line above the girdle (expected 0: the stone drops in)"))
    design = float(design_mesh(spec).volume)
    rep.checks.append(band.design_volume_check(design, ntop_vol, 3.0))
    return rep


def _inner_count(mesh, z: float, r_max: float) -> int:
    """How many separate pieces of the section at height z reach inside radius r_max."""
    import numpy as np
    sec = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    if sec is None:
        return 0
    planar, to3d = sec.to_2D()
    count = 0
    for poly in planar.polygons_full:
        pts = np.asarray(poly.exterior.coords)
        pts3 = (to3d @ np.column_stack([pts, np.zeros(len(pts)), np.ones(len(pts))]).T).T[:, :3]
        if np.hypot(pts3[:, 0], pts3[:, 1]).min() < r_max:
            count += 1
    return count


@dataclass
class HeadResult:
    spec: HeadSpec
    stl: Path
    run: object
    gate: object
    ntop_volume_mm3: float | None
    run_dir: Path
    run_id: str
    notes: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        from . import runs
        return runs.status_of(self.run.ok, self.gate)

    @property
    def ok(self) -> bool:
        from . import gate
        return self.status == gate.PASSED

    def text(self) -> str:
        return "\n".join([self.spec.describe(), self.run.summary(), self.gate.text(),
                          f"  status: {self.status.upper()}  run {self.run_dir}"] + [f"  note: {n}" for n in self.notes])


def build_head(spec: HeadSpec, out_dir: Path | None = None, *, notebook: Path | None = None,
               catalog_name: str = "prong_head_harness") -> HeadResult:
    """Run the prong_head block through its harness under nTopCL and gate the head."""
    from . import catalog, config, ntopcl, runs
    problems = spec.validate()
    if problems:
        raise ValueError("; ".join(problems))
    cat = catalog.load(catalog_name)
    nb = Path(notebook) if notebook else cat.notebook
    run_dir, run_id = runs.fresh_run_dir(Path(out_dir) if out_dir else config.out_dir() / "head", spec.stem)
    envelope = run_dir / f"{spec.stem}.envelope.stl"
    spec.seat.envelope().export(str(envelope))
    spec.stone.mesh().export(str(run_dir / f"{spec.stem}.stone.stl"))
    stl = run_dir / f"{spec.stem}.stl"
    started = time.time()
    run = ntopcl.run(nb, cat.build_inputs(spec.notebook_inputs(str(envelope), str(stl))), run_dir, tag=spec.stem)
    try:
        runs.require_fresh(stl, started, "the exported head")
    except FileNotFoundError as e:
        raise ntopcl.NtopclError(f"notebook reported success but {e}", run) from e
    entry = run.outputs.get(cat.output.get("name", "Volume"))
    ntop_vol = ntopcl.scalar_value(entry) if entry else None
    rep = check_head(spec, stl, ntop_vol)
    from . import gate as _gate
    _gate.save(rep)
    res = HeadResult(spec, stl, run, rep, ntop_vol, run_dir, run_id)
    res.notes.append(f"metal: " + ", ".join(f"{k} {v:.2f} g" for k, v in tables.weights_g(rep.volume_mm3).items()))
    (run_dir / f"{spec.stem}.report.json").write_text(json.dumps({
        "stem": spec.stem, "run_id": run_id, "status": res.status, "design": spec.design(),
        "inputs": spec.notebook_inputs(str(envelope), str(stl)), "ntop_volume_mm3": ntop_vol, "gate": rep.to_dict(),
        "notebook": runs.notebook_identity(nb), "environment": runs.environment(ntopcl.version()), "notes": res.notes,
    }, indent=2, default=str), encoding="utf-8")
    return res


# =============================================================================================
# Outline heads: prongs placed on any convex girdle outline (pear first), rails that follow it
# =============================================================================================
PEAR_PRONG_ANGLES = {5: (180.0, 105.0, -105.0, 35.0, -35.0)}    # about the round end's centre; 180 = the point


@dataclass
class OutlineHeadSpec:
    """A prong head for a fancy stone (the `outline_head` block). Head frame as HeadSpec.

        prongs   one per outline point: a rod up the pavilion, `d` = prong radius - ledge off its
                 surface along the pavilion's normal (so the prong's inner side overlaps the
                 pavilion by `ledge` all the way up and the seat cut leaves a groove the stone
                 rests in), from a foot low on the pavilion to a knee at the girdle, then straight
                 up to a tip above it; a sphere at the foot, the knee and the tip. Python writes the
                 rods as one STL (Prongs Path) - any count, any outline.
        rails    the seat cutter offset outward by Rail Offset, cut to a slab: a gallery hugging the
                 pavilion all the way round, whatever the outline. The prongs lie on the pavilion's
                 offset (a cone's normal is constant along each generator), so every rail meets
                 every prong.
        seat     minus the Seat Cutter, as prong_head.
    Pear: the point prong plus four on the round end (PEAR_PRONG_ANGLES). Other shapes: prongs on
    rays from the centre, evenly spaced, offset half a spacing."""
    stone: gems.StoneSpec
    prongs: int | None = None              # pear 5; others 4
    prong_dia_mm: float | None = None      # as HeadSpec
    ledge_mm: float = 0.30
    tip_above_mm: float | None = None
    clearance_mm: float | None = None
    rail_height_mm: float | None = None    # slab height; default max(0.75, 0.9 x prong radius)
    rail_width_mm: float | None = None     # metal outside the cutter; default max(0.75, d - clearance + prong radius / 2)
    rail_below_girdle_mm: float = 0.6      # the upper rail's top this far below the girdle's underside
    rail_gap_mm: float = 0.4               # open gallery between the rails
    foot_frac: float = 0.22                # where the prongs start on the pavilion (culet 0 -> girdle 1)
    floor_z: float | None = None           # nothing below this (head frame); raised feet/rail for a ring
    mesh_tolerance_mm: float = 0.05

    # ---- numbers ---------------------------------------------------------------------------
    @property
    def count(self) -> int:
        return int(self.prongs) if self.prongs is not None else (5 if self.stone.shape == "pear" else 4)

    @property
    def rho(self) -> float:
        floor = PRONG_TIP_FLOOR + self.ledge_mm + self.clearance + 0.05
        d = self.prong_dia_mm if self.prong_dia_mm is not None else max(floor, 0.18 * self.stone.width)
        return float(d) / 2

    @property
    def clearance(self) -> float:
        return tables.SETTINGS["seat_clearance_mm"] if self.clearance_mm is None else float(self.clearance_mm)

    @property
    def offset(self) -> float:
        """Prong axis distance off the pavilion surface."""
        return self.rho - self.ledge_mm

    @property
    def rail_half(self) -> float:
        return (self.rail_height_mm if self.rail_height_mm is not None else max(WALL_FLOOR * 1.5, 0.9 * self.rho)) / 2

    @property
    def rail_width(self) -> float:
        return float(self.rail_width_mm) if self.rail_width_mm is not None else max(WALL_FLOOR * 1.5, self.offset - self.clearance + self.rho / 2)

    @property
    def seat(self) -> gems.SeatSpec:
        return gems.SeatSpec(self.stone, clearance_mm=self.clearance, mesh_tolerance_mm=self.mesh_tolerance_mm)

    @property
    def z_culet(self) -> float:
        _, pav = self.stone.heights
        return -self.stone.girdle / 2 - pav

    @property
    def z_tip(self) -> float:
        crown, _ = self.stone.heights
        return self.stone.girdle / 2 + (self.tip_above_mm if self.tip_above_mm is not None else max(0.8, 0.8 * crown))

    def outline_points(self) -> list[tuple]:
        """[(q, m)]: the girdle outline points the prongs sit on and the outline's outward normals."""
        import numpy as np
        xy = self.stone.outline(2048)
        n = len(xy)
        tang = np.roll(xy, -1, axis=0) - np.roll(xy, 1, axis=0)
        normal = np.column_stack([tang[:, 1], -tang[:, 0]])
        normal /= np.linalg.norm(normal, axis=1)[:, None]
        if np.mean(np.einsum("ij,ij->i", normal, xy)) < 0:              # outward
            normal = -normal
        out = []
        if self.stone.shape == "pear":
            angles = PEAR_PRONG_ANGLES.get(self.count)
            centre = np.array([self.stone.length / 2 - self.stone.width / 2, 0.0])
        else:
            step = 360.0 / self.count
            angles = [step / 2 + k * step for k in range(self.count)]
            centre = np.zeros(2)
        for a in angles:
            if self.stone.shape == "pear" and a == 180.0:
                i = int(np.argmin(xy[:, 0]))
                out.append((xy[i], np.array([-1.0, 0.0])))                # the point: straight along the axis
                continue
            d = np.array([math.cos(math.radians(a)), math.sin(math.radians(a))])
            rel = xy - centre
            diff = np.arctan2(rel[:, 1], rel[:, 0]) - math.radians(a)
            ang = np.abs((diff + math.pi) % (2 * math.pi) - math.pi)        # wrapped to [0, π] (a prong past 180° once all landed on one point)
            i = int(np.argmin(ang + 1e-3 * np.abs(np.einsum("ij,j->i", rel, np.array([-d[1], d[0]])))))
            out.append((xy[i], normal[i]))
        return out

    def _pavilion_normal(self, q, m):
        """Outward unit normal of the pavilion along the generator culet -> (q, -g/2)."""
        import numpy as np
        Q = np.array([q[0], q[1], -self.stone.girdle / 2])
        C = np.array([0.0, 0.0, self.z_culet])
        t = np.array([-m[1], m[0], 0.0])                                 # outline tangent
        N = np.cross(Q - C, t)
        N /= np.linalg.norm(N)
        if N[0] * m[0] + N[1] * m[1] < 0:
            N = -N
        return N, Q, C

    def _foot_frac(self) -> float:
        """The prongs' start on the pavilion: `foot_frac`, raised until the feet clear `floor_z`."""
        _, pav = self.stone.heights
        s = self.foot_frac
        if self.floor_z is not None:
            worst_nz = min(self._pavilion_normal(q, m)[0][2] for q, m in self.outline_points())
            need = (self.floor_z + self.rho - self.offset * worst_nz - self.z_culet) / pav
            s = max(s, need + 0.01)
        return s

    def prong_axes(self) -> list[tuple]:
        """[(foot, knee, tip)] 3-D points per prong (head frame)."""
        import numpy as np
        _, pav = self.stone.heights
        s0, d = self._foot_frac(), self.offset
        out = []
        for q, m in self.outline_points():
            N, Q, C = self._pavilion_normal(q, m)
            foot = C + s0 * (Q - C) + d * N
            knee = Q + d * N
            tip = np.array([knee[0], knee[1], self.z_tip])
            out.append((foot, knee, tip))
        return out

    def rails(self) -> dict:
        """Upper rail just under the girdle, the lower one a gap below it - raised (with the gap
        shrinking to 0.3 mm) if it would go under `floor_z` or below the prong feet."""
        h = self.rail_half
        top = -self.stone.girdle / 2 - self.rail_below_girdle_mm
        zu = top - h
        zl = zu - 2 * h - self.rail_gap_mm
        lowest_ok = max(min(a[0][2] for a in self.prong_axes()) + 0.2,
                        (self.floor_z + h) if self.floor_z is not None else -1e9)
        zl = max(zl, min(lowest_ok, zu - 2 * h - 0.3))
        return {"upper": (zu - h, zu + h), "lower": (zl - h, zl + h), "offset": self.rail_width}

    def lowest_z(self) -> float:
        foots = [a[0][2] for a in self.prong_axes()]
        return min(min(foots) - self.rho, self.rails()["lower"][0])

    def prongs_mesh(self):
        """The prong rods (cylinders + spheres) as one watertight mesh: what Prongs Path points at."""
        import trimesh
        parts = []
        for foot, knee, tip in self.prong_axes():
            for a, b in ((foot, knee), (knee, tip)):
                parts.append(trimesh.creation.cylinder(radius=self.rho, segment=[a, b], sections=64))
            for c in (foot, knee, tip):
                ball = trimesh.creation.icosphere(subdivisions=4, radius=self.rho)
                ball.apply_translation(c)
                parts.append(ball)
        from . import geom
        return geom.clean(trimesh.boolean.union(parts, engine="manifold"))      # survives STL (float32) intact

    # ---- notebook ------------------------------------------------------------------------------
    def notebook_inputs(self, seat_path: str, prongs_path: str = "", output_path: str | None = None) -> dict:
        r = self.rails()
        ins = {"Seat Path": seat_path, "Clearance": round(self.clearance, 4), "Prongs Path": prongs_path,
               "Rail Offset": round(r["offset"], 4),
               "Upper Rail Bottom": round(r["upper"][0], 4), "Upper Rail Top": round(r["upper"][1], 4),
               "Lower Rail Bottom": round(r["lower"][0], 4), "Lower Rail Top": round(r["lower"][1], 4)}
        if output_path is not None:
            ins["Mesh Tolerance"] = self.mesh_tolerance_mm
            ins["Output Path"] = output_path
        return ins

    def design(self) -> dict:
        d = asdict(self)
        d["inputs"] = self.notebook_inputs("")
        d["prong_axes"] = [[[round(float(c), 4) for c in p] for p in axis] for axis in self.prong_axes()]
        return d

    @property
    def stem(self) -> str:
        from . import runs
        return f"head_{self.count}prong_{self.stone.stem[len('stone_'):]}_{runs.spec_id(self.design())}"

    def validate(self) -> list[str]:
        p = self.stone.validate()
        if p:
            return p
        if self.stone.shape == "pear" and self.count not in PEAR_PRONG_ANGLES:
            p.append(f"a pear head has {', '.join(map(str, PEAR_PRONG_ANGLES))} prongs (the point + the round end)")
            return p
        if self.stone.shape != "pear" and self.count not in (4, 6, 8):
            p.append("outline head prongs: 4, 6 or 8 (pear: 5)")
            return p
        tip_left = 2 * self.rho - self.ledge_mm - self.clearance
        if tip_left < PRONG_TIP_FLOOR:
            p.append(f"prong left above the girdle is {tip_left:.2f} mm thick; floor {PRONG_TIP_FLOOR} mm")
        if self.ledge_mm < 0.15:
            p.append("ledge under 0.15 mm will not carry the stone")
        r = self.rails()
        if r["upper"][1] > -self.stone.girdle / 2 - 0.3:
            p.append("the upper rail reaches the girdle: lower it")
        if r["lower"][1] > r["upper"][0] - 0.3 + 1e-9:
            p.append("the rails overlap or touch: lower the lower rail or raise the upper one")
        if self.floor_z is not None and self.lowest_z() < self.floor_z - 1e-6:
            p.append(f"the head reaches z {self.lowest_z():.2f}, below its floor {self.floor_z:.2f}")
        if self._foot_frac() > 0.7:
            p.append("the prong feet are pushed up past 70 % of the pavilion: more room under the stone")
        if min(r["upper"][1] - r["upper"][0], r["offset"]) < WALL_FLOOR:
            p.append(f"rail section under the wall floor {WALL_FLOOR} mm")
        return p

    def describe(self) -> str:
        r = self.rails()
        return (f"{self.stem}: {self.count} prongs of {2 * self.rho:.2f} mm on a {self.stone.describe()}\n"
                f"  prongs {self.offset:.2f} mm off the pavilion (ledge {self.ledge_mm} mm) from {self._foot_frac():.0%} of its "
                f"depth, upright from the girdle to z {self.z_tip:.2f}; clearance {self.clearance} mm\n"
                f"  rails: the seat + {r['offset']:.2f} mm, z {r['upper'][0]:.2f}..{r['upper'][1]:.2f} and "
                f"{r['lower'][0]:.2f}..{r['lower'][1]:.2f}; tip left above the girdle {2 * self.rho - self.ledge_mm - self.clearance:.2f} mm")


def outline_head_mesh(v: dict, envelope, prongs, cut_seat: bool = True):
    """The outline head from the block's input numbers, the seat envelope and the prong mesh."""
    import trimesh
    from . import geom
    c, off = float(v["Clearance"]), float(v["Rail Offset"])
    grown = _offset_convex(envelope, c + off)
    if not prongs.is_volume:                                     # read back from STL
        prongs = geom.clean(prongs)
    parts = [prongs]
    for lo, hi in (("Upper Rail Bottom", "Upper Rail Top"), ("Lower Rail Bottom", "Lower Rail Top")):
        z0, z1 = float(v[lo]), float(v[hi])
        slab = trimesh.creation.box(extents=(60.0, 60.0, z1 - z0))
        slab.apply_translation((0.0, 0.0, (z0 + z1) / 2))
        parts.append(trimesh.boolean.intersection([grown, slab], engine="manifold"))
    head = trimesh.boolean.union(parts, engine="manifold")
    if cut_seat:
        head = trimesh.boolean.difference([head, _offset_convex(envelope, c)], engine="manifold")
    return geom.clean(head)


def outline_design_mesh(spec: OutlineHeadSpec):
    return outline_head_mesh(spec.notebook_inputs(""), spec.seat.envelope(), spec.prongs_mesh())


def outline_count(mesh, z: float, region) -> int:
    """How many separate pieces of the section at height z overlap the 2-D `region` (shapely)."""
    import numpy as np
    from shapely.geometry import Polygon
    sec = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    if sec is None:
        return 0
    planar, to3d = sec.to_2D()
    count = 0
    for poly in planar.polygons_full:
        pts = np.asarray(poly.exterior.coords)
        pts3 = (to3d @ np.column_stack([pts, np.zeros(len(pts)), np.ones(len(pts))]).T).T[:, :3]
        if Polygon(pts3[:, :2]).buffer(0).intersection(region).area > 1e-4:
            count += 1
    return count


def seat_regions(stone: gems.StoneSpec, clearance: float):
    """(under, above): the girdle outline inset 0.1 mm (metal there under the girdle = a ledge)
    and grown by half the clearance (metal there above the girdle blocks the drop-in)."""
    from shapely.geometry import Polygon
    outline = Polygon(stone.outline())
    return outline.buffer(-0.1), outline.buffer(clearance * 0.5)


def check_outline_head(spec: OutlineHeadSpec, stl: Path, ntop_vol: float | None):
    """As check_head, for any outline: fits, ledges (every prong reaches under the girdle),
    drop-in clear, closed, one shell, volume vs nTop and vs the independent head."""
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
    ledges = outline_count(head, -g / 2 - 0.3, under)
    blocking = outline_count(head, g / 2 + 0.15, above)
    rep.checks.append(gate.Check("seat ledges", ledges == spec.count, f"{ledges} prongs reach under the girdle (expected {spec.count})"))
    rep.checks.append(gate.Check("drop-in clear", blocking == 0, f"{blocking} pieces inside the girdle line above the girdle"))
    rep.checks.append(band.design_volume_check(float(outline_design_mesh(spec).volume), ntop_vol, 3.0))
    return rep


def build_outline_head(spec: OutlineHeadSpec, out_dir: Path | None = None, *, notebook: Path | None = None,
                       catalog_name: str = "outline_head_harness") -> HeadResult:
    """Run the outline_head block through its harness under nTopCL and gate the head."""
    from . import catalog, config, ntopcl, runs
    from . import gate as _gate
    problems = spec.validate()
    if problems:
        raise ValueError("; ".join(problems))
    cat = catalog.load(catalog_name)
    nb = Path(notebook) if notebook else cat.notebook
    run_dir, run_id = runs.fresh_run_dir(Path(out_dir) if out_dir else config.out_dir() / "head", spec.stem)
    envelope, prongs = run_dir / f"{spec.stem}.envelope.stl", run_dir / f"{spec.stem}.prongs.stl"
    spec.seat.envelope().export(str(envelope))
    spec.prongs_mesh().export(str(prongs))
    spec.stone.mesh().export(str(run_dir / f"{spec.stem}.stone.stl"))
    stl = run_dir / f"{spec.stem}.stl"
    started = time.time()
    inputs = spec.notebook_inputs(str(envelope), str(prongs), str(stl))
    run = ntopcl.run(nb, cat.build_inputs(inputs), run_dir, tag=spec.stem)
    try:
        runs.require_fresh(stl, started, "the exported head")
    except FileNotFoundError as e:
        raise ntopcl.NtopclError(f"notebook reported success but {e}", run) from e
    entry = run.outputs.get(cat.output.get("name", "Volume"))
    ntop_vol = ntopcl.scalar_value(entry) if entry else None
    rep = check_outline_head(spec, stl, ntop_vol)
    _gate.save(rep)
    res = HeadResult(spec, stl, run, rep, ntop_vol, run_dir, run_id)
    res.notes.append(f"metal: " + ", ".join(f"{k} {v:.2f} g" for k, v in tables.weights_g(rep.volume_mm3).items()))
    (run_dir / f"{spec.stem}.report.json").write_text(json.dumps({
        "stem": spec.stem, "run_id": run_id, "status": res.status, "design": spec.design(), "inputs": inputs,
        "ntop_volume_mm3": ntop_vol, "gate": rep.to_dict(), "notebook": runs.notebook_identity(nb),
        "environment": runs.environment(ntopcl.version()), "notes": res.notes}, indent=2, default=str), encoding="utf-8")
    return res
