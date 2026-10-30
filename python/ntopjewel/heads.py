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
    blend_mm: float | None = None          # nTop blend radius where the prongs meet the rails; default tables, 0 = sharp
    mesh_tolerance_mm: float = 0.05

    # ---- numbers -------------------------------------------------------------------------
    @property
    def rho(self) -> float:
        floor = PRONG_TIP_FLOOR + self.ledge_mm + self.clearance + 0.05          # what stays above the girdle >= the tip floor
        d = self.prong_dia_mm if self.prong_dia_mm is not None else max(floor, 0.18 * self.stone.width)
        return float(d) / 2

    @property
    def blend(self) -> float:
        return tables.SETTINGS["blend_radius_mm"] if self.blend_mm is None else float(self.blend_mm)

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
            "Blend Radius": round(self.blend, 4),
        }
        if output_path is not None:
            ins["Mesh Tolerance"] = self.mesh_tolerance_mm
            ins["Output Path"] = output_path
        return ins

    def design(self) -> dict:
        d = asdict(self)
        d["inputs"] = self.notebook_inputs("")
        return d

    def blend_volume_mm3(self) -> float:
        """The metal the blended prongs-to-rails union is expected to add (0 for a sharp union)."""
        from . import geom
        if self.blend <= 0:
            return 0.0
        prongs, rails = head_parts(self.notebook_inputs(""))
        return geom.blend_volume_mm3(self.blend, geom.junction_length(prongs, rails))

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
        p += blend_problems(self.blend, self.rho)
        return p

    def describe(self) -> str:
        lay = self.layout()
        return (f"{self.stem}: {self.prongs} prongs of {2 * self.rho:.2f} mm on a {self.stone.describe()}\n"
                f"  prong axis r {lay['r_base']:.3f} @ z {lay['z_base']:.3f} -> r {lay['r_tip']:.3f} @ z {lay['z_tip']:.3f}, "
                f"first at {self.offset_deg:g}°, every {self.spacing_deg:g}°; ledge {self.ledge_mm} mm, clearance {self.clearance} mm\n"
                f"  rails: upper r {lay['rail_upper'][1]:.3f} @ z {lay['rail_upper'][0]:.3f}, lower r {lay['rail_lower'][1]:.3f} @ "
                f"z {lay['rail_lower'][0]:.3f}, tube {2 * self.rail_rho:.2f} mm; tip left above the girdle "
                f"{2 * self.rho - self.ledge_mm - self.clearance:.2f} mm; blend {self.blend:g} mm")


# ---- the independent geometry ---------------------------------------------------------------
def head_parts(v: dict):
    """(prongs, rails): the two bodies the block unions (with a blend) from the notebook's numbers."""
    import numpy as np
    import trimesh
    rho = float(v["Prong Radius"])
    base = np.array([v["Base X"], v["Base Y"], v["Base Z"]], float)
    tip = np.array([v["Tip X"], v["Tip Y"], v["Tip Z"]], float)
    prongs = []
    for k in range(int(v["Prong Count"])):
        rot = trimesh.transformations.rotation_matrix(math.radians(k * float(v["Prong Spacing"])), [0, 0, 1])[:3, :3]
        a, b = rot @ base, rot @ tip
        rod = trimesh.creation.cylinder(radius=rho, segment=[a, b], sections=48)
        prongs += [rod, _ball(a, rho), _ball(b, rho)]
    rails = []
    for zk, rk in (("Upper Rail Z", "Upper Rail Radius"), ("Lower Rail Z", "Lower Rail Radius")):
        t = trimesh.creation.torus(float(v[rk]), float(v["Rail Tube Radius"]), major_sections=180, minor_sections=24)
        t.apply_translation((0.0, 0.0, float(v[zk])))
        rails.append(t)
    return trimesh.boolean.union(prongs, engine="manifold"), trimesh.boolean.union(rails, engine="manifold")


def blend_problems(blend: float, feature_radius: float) -> list[str]:
    """A blend radius must be a castable fillet, not a reshaping: 0 .. 1 mm and no more than the
    feature it joins (a blend wider than a prong turns the basket into a web)."""
    p = []
    if blend < 0 or blend > 1.0:
        p.append(f"blend radius {blend:g} mm: 0 (sharp) to 1 mm")
    elif blend > feature_radius + 1e-9:
        p.append(f"blend radius {blend:g} mm exceeds the feature it joins ({feature_radius:.2f} mm): the junctions would web over")
    return p


def head_mesh(v: dict, seat_mesh=None, cut_seat: bool = True):
    """The head from the notebook's input numbers (trimesh + manifold3d), without the blend (an
    implicit operation the independent model estimates by volume instead). `seat_mesh` is the
    seat envelope (stone + drop path); it is offset by Clearance (exact for a convex body) and
    subtracted."""
    import trimesh
    prongs, rails = head_parts(v)
    head = trimesh.boolean.union([prongs, rails], engine="manifold")
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
    rep.checks.append(band.blended_design_volume_check(float(design_mesh(spec).volume), spec.blend_volume_mm3(), ntop_vol, 3.0))
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
POINTED = ("pear", "marquise")                                   # shapes whose points get V-prongs
V_BELOW_GIRDLE = 0.6                                             # the V reaches this far under the girdle


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
        V-prongs a stone's point (the pear's, both of the marquise's) gets a V instead of a round
                 prong: a chevron of metal `v_thickness` thick hugging the outline for `v_arm` back
                 from the point on both sides, from `V_BELOW_GIRDLE` under the girdle to just above
                 the prong tips, carried down the pavilion by a rod like the others. The seat cut
                 leaves a ledge under the girdle inside the V and a straight wall above it, so the
                 point drops in, sits, and is covered all round when the setter closes the V.
    Pear: the point (a V-prong) plus four on the round end (PEAR_PRONG_ANGLES). Marquise: a V at
    each end plus 4 side prongs. Other shapes: prongs on rays from the centre, evenly spaced,
    offset half a spacing."""
    stone: gems.StoneSpec
    prongs: int | None = None              # round prongs: pear 5 places (the point included); others 4
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
    v_prongs: bool | None = None           # V-prongs on the points; default on for the shapes that have points
    v_thickness_mm: float | None = None    # the V's wall; default the prong radius, at least the prong-tip floor
    v_arm_mm: float | None = None          # how far back from the point the V reaches; default max(1.5, 0.2 x width)
    blend_mm: float | None = None          # nTop blend radius: prongs into rails, and the rails' edges rounded; default tables
    mesh_tolerance_mm: float = 0.05

    # ---- numbers ---------------------------------------------------------------------------
    @property
    def blend(self) -> float:
        return tables.SETTINGS["blend_radius_mm"] if self.blend_mm is None else float(self.blend_mm)

    @property
    def has_points(self) -> bool:
        return self.stone.shape in POINTED

    @property
    def use_v(self) -> bool:
        return self.has_points if self.v_prongs is None else (bool(self.v_prongs) and self.has_points)

    @property
    def count(self) -> int:
        """Every prong, V-prongs included."""
        if self.stone.shape == "pear":
            return int(self.prongs) if self.prongs is not None else 5
        rays = int(self.prongs) if self.prongs is not None else 4
        return rays + (2 if self.stone.shape == "marquise" and self.use_v else 0)

    @property
    def v_thickness(self) -> float:
        return float(self.v_thickness_mm) if self.v_thickness_mm is not None else max(self.rho, PRONG_TIP_FLOOR)

    @property
    def v_arm(self) -> float:
        return float(self.v_arm_mm) if self.v_arm_mm is not None else max(1.5, 0.2 * self.stone.width)

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

    def point_kinds(self) -> list[str]:
        """"v" or "round" for each of outline_points()."""
        kinds = []
        for q, m in self.outline_points():
            is_point = self.has_points and abs(abs(float(m[0])) - 1.0) < 1e-9 and abs(float(m[1])) < 1e-9
            kinds.append("v" if (is_point and self.use_v) else "round")
        return kinds

    def outline_points(self) -> list[tuple]:
        """[(q, m)]: the girdle outline points the prongs sit on and the outline's outward normals.
        A stone's points come with their axis as the normal (exactly ±X)."""
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
            rays = self.count - (2 if self.stone.shape == "marquise" and self.use_v else 0)
            step = 360.0 / rays
            angles = [step / 2 + k * step for k in range(rays)]
            centre = np.zeros(2)
            if self.stone.shape == "marquise" and self.use_v:          # both points, on the axis
                out.append((xy[int(np.argmax(xy[:, 0]))], np.array([1.0, 0.0])))
                out.append((xy[int(np.argmin(xy[:, 0]))], np.array([-1.0, 0.0])))
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

    def v_block(self, q):
        """The V at the point q: the outline grown by the V's wall, within v_arm of the point, its
        vertical edges rounded, from V_BELOW_GIRDLE under the girdle to just above the prong tips."""
        import trimesh
        from shapely.geometry import Point, Polygon
        band = Polygon(self.stone.outline(2048)).buffer(self.v_thickness, quad_segs=32)
        shape = band.intersection(Point(float(q[0]), float(q[1])).buffer(self.v_arm, quad_segs=64))
        shape = shape.buffer(-0.2, quad_segs=16).buffer(0.2, quad_segs=16)
        z0 = -self.stone.girdle / 2 - V_BELOW_GIRDLE
        z1 = self.z_tip + 0.3
        block = trimesh.creation.extrude_polygon(shape, height=z1 - z0)
        block.apply_translation((0.0, 0.0, z0))
        return block

    def prongs_mesh(self):
        """The prong rods (cylinders + spheres) and V-prongs as one watertight mesh: what Prongs Path points at."""
        import trimesh
        parts = []
        for (foot, knee, tip), kind, (q, _m) in zip(self.prong_axes(), self.point_kinds(), self.outline_points()):
            if kind == "v":                                  # the support rod up the pavilion + the V
                parts.append(trimesh.creation.cylinder(radius=self.rho, segment=[foot, knee], sections=64))
                ends = (foot, knee)
                parts.append(self.v_block(q))
            else:
                for a, b in ((foot, knee), (knee, tip)):
                    parts.append(trimesh.creation.cylinder(radius=self.rho, segment=[a, b], sections=64))
                ends = (foot, knee, tip)
            for c in ends:
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
               "Lower Rail Bottom": round(r["lower"][0], 4), "Lower Rail Top": round(r["lower"][1], 4),
               "Blend Radius": round(self.blend, 4)}
        if output_path is not None:
            ins["Mesh Tolerance"] = self.mesh_tolerance_mm
            ins["Output Path"] = output_path
        return ins

    def design(self) -> dict:
        d = asdict(self)
        d["inputs"] = self.notebook_inputs("")
        d["prong_axes"] = [[[round(float(c), 4) for c in p] for p in axis] for axis in self.prong_axes()]
        return d

    def blend_volume_mm3(self) -> float:
        """What the blended prongs-to-rails union adds (the rails' rounded edges, which take a
        little away, are not counted)."""
        from . import geom
        if self.blend <= 0:
            return 0.0
        prongs, rails = outline_head_parts(self.notebook_inputs(""), self.seat.envelope(), self.prongs_mesh())
        return geom.blend_volume_mm3(self.blend, geom.junction_length(prongs, rails))

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
        rays = self.count - (2 if self.stone.shape == "marquise" and self.use_v else 0)
        if self.stone.shape != "pear" and rays not in (4, 6, 8):
            p.append("outline head prongs: 4, 6 or 8 (pear: 5; a marquise adds a V at each point)")
            return p
        if self.v_prongs and not self.has_points:
            p.append(f"a {self.stone.shape} has no points for V-prongs")
        if self.use_v:
            if self.v_thickness - self.clearance < PRONG_TIP_FLOOR - 0.05:
                p.append(f"V-prong wall {self.v_thickness - self.clearance:.2f} mm after the seat cut; floor {PRONG_TIP_FLOOR - 0.05:.2f} mm")
            if self.v_arm < 1.0:
                p.append("a V-prong reaching less than 1 mm back from the point will not hold it")
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
        p += blend_problems(self.blend, min(self.rho, self.rail_half))
        return p

    def describe(self) -> str:
        r = self.rails()
        nv = self.point_kinds().count("v")
        vline = (f"  V-prongs: {nv} (wall {self.v_thickness:.2f} mm, {self.v_arm:.2f} mm back from each point, "
                 f"{V_BELOW_GIRDLE} mm under the girdle)\n" if nv else "")
        return (f"{self.stem}: {self.count} prongs ({nv} V) of {2 * self.rho:.2f} mm on a {self.stone.describe()}\n" + vline +
                f"  prongs {self.offset:.2f} mm off the pavilion (ledge {self.ledge_mm} mm) from {self._foot_frac():.0%} of its "
                f"depth, upright from the girdle to z {self.z_tip:.2f}; clearance {self.clearance} mm\n"
                f"  rails: the seat + {r['offset']:.2f} mm, z {r['upper'][0]:.2f}..{r['upper'][1]:.2f} and "
                f"{r['lower'][0]:.2f}..{r['lower'][1]:.2f}; tip left above the girdle {2 * self.rho - self.ledge_mm - self.clearance:.2f} mm; "
                f"blend {self.blend:g} mm")


def outline_head_parts(v: dict, envelope, prongs):
    """(prongs, rails) from the block's numbers: the two bodies its blended union joins."""
    import trimesh
    from . import geom
    c, off = float(v["Clearance"]), float(v["Rail Offset"])
    grown = _offset_convex(envelope, c + off)
    if not prongs.is_volume:                                     # read back from STL
        prongs = geom.clean(prongs)
    rails = []
    for lo, hi in (("Upper Rail Bottom", "Upper Rail Top"), ("Lower Rail Bottom", "Lower Rail Top")):
        z0, z1 = float(v[lo]), float(v[hi])
        slab = trimesh.creation.box(extents=(60.0, 60.0, z1 - z0))
        slab.apply_translation((0.0, 0.0, (z0 + z1) / 2))
        rails.append(trimesh.boolean.intersection([grown, slab], engine="manifold"))
    return prongs, trimesh.boolean.union(rails, engine="manifold")


def outline_head_mesh(v: dict, envelope, prongs, cut_seat: bool = True):
    """The outline head from the block's input numbers, the seat envelope and the prong mesh
    (unblended: the blend is estimated by volume)."""
    import trimesh
    from . import geom
    c = float(v["Clearance"])
    prongs, rails = outline_head_parts(v, envelope, prongs)
    head = trimesh.boolean.union([prongs, rails], engine="manifold")
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

    def lift(coords):
        pts = np.asarray(coords)
        return (to3d @ np.column_stack([pts, np.zeros(len(pts)), np.ones(len(pts))]).T).T[:, :2]
    count = 0
    for poly in planar.polygons_full:
        # with its holes: a bezel wall's section is a ring, and its outer boundary alone would
        # cover the opening the stone drops through (2026-10-29)
        piece = Polygon(lift(poly.exterior.coords), [lift(h.coords) for h in poly.interiors]).buffer(0)
        if piece.intersection(region).area > 1e-4:
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
    rep.checks.append(band.blended_design_volume_check(float(outline_design_mesh(spec).volume), spec.blend_volume_mm3(), ntop_vol, 3.0))
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


# =============================================================================================
# Bezel heads: a wall round the stone, a lip to burnish over it, light windows in the cup
# =============================================================================================
@dataclass
class BezelSpec:
    """A bezel head (the `bezel_head` block). Head frame as HeadSpec; any convex outline.

        cup      the Seat Cutter offset outward by `wall`, kept between Bezel Bottom and Bezel
                 Top, minus the cutter: above the girdle a straight wall round the outline (the
                 cutter's drop-in path is vertical), rising `lip` above the girdle top to be pushed
                 over the crown; below it a cup hugging the pavilion, the stone's seat
        windows  light openings through the cup below a solid bearing band under the girdle:
                 stadium-shaped slots, evenly spaced round the outline, that Python writes as one
                 STL (Windows Path) and the block subtracts; none = a speck far outside
    Every number from the tables' settings unless given."""
    stone: gems.StoneSpec
    wall_mm: float | None = None
    lip_mm: float | None = None
    bearing_mm: float | None = None
    windows: int | None = None             # default 6 where there is room, else 0 (a closed cup)
    window_width_mm: float | None = None   # default min(1.6, 0.4 x the spacing along the outline)
    bottom_frac: float = 0.35              # the cup's bottom edge, as a fraction of the pavilion above the culet
    floor_z: float | None = None           # nothing below this (head frame): raised for a ring
    clearance_mm: float | None = None
    blend_mm: float | None = None          # nTop blend radius on the cup's edges (its rim and lip rounded); default tables
    mesh_tolerance_mm: float = 0.05

    # ---- numbers ---------------------------------------------------------------------------
    @property
    def blend(self) -> float:
        return tables.SETTINGS["blend_radius_mm"] if self.blend_mm is None else float(self.blend_mm)

    @property
    def wall(self) -> float:
        return float(self.wall_mm) if self.wall_mm is not None else tables.SETTINGS["bezel_wall_mm"]

    @property
    def lip(self) -> float:
        return float(self.lip_mm) if self.lip_mm is not None else tables.SETTINGS["bezel_lip_mm"]

    @property
    def bearing(self) -> float:
        return float(self.bearing_mm) if self.bearing_mm is not None else tables.SETTINGS["bezel_bearing_mm"]

    @property
    def clearance(self) -> float:
        return tables.SETTINGS["seat_clearance_mm"] if self.clearance_mm is None else float(self.clearance_mm)

    @property
    def seat(self) -> gems.SeatSpec:
        return gems.SeatSpec(self.stone, clearance_mm=self.clearance, mesh_tolerance_mm=self.mesh_tolerance_mm)

    @property
    def count(self) -> int:                 # a bezel has no prongs; the solitaire's ledge check wants one piece
        return 1

    @property
    def n_windows(self) -> int:
        """`windows`, or by default 6 where the cup has room for them (a shallow pavilion: none)."""
        if self.windows is not None:
            return int(self.windows)
        z0, z1 = self.window_zone()
        return 6 if z1 - z0 >= 0.5 else 0

    @property
    def z_culet(self) -> float:
        _, pav = self.stone.heights
        return -self.stone.girdle / 2 - pav

    @property
    def z_bottom(self) -> float:
        _, pav = self.stone.heights
        z = self.z_culet + self.bottom_frac * pav
        return max(z, self.floor_z) if self.floor_z is not None else z

    @property
    def z_top(self) -> float:
        return self.stone.girdle / 2 + self.lip

    def window_zone(self) -> tuple[float, float]:
        """(bottom, top) of the light windows: above the cup's bottom edge, below the bearing band."""
        return self.z_bottom + 0.45, -self.stone.girdle / 2 - self.bearing

    def window_points(self) -> list[tuple]:
        """[(q, m)] evenly spaced round the girdle outline by arc length, offset half a spacing."""
        import numpy as np
        xy = self.stone.outline(2048)
        closed = np.vstack([xy, xy[:1]])
        seg = np.linalg.norm(np.diff(closed, axis=0), axis=1)
        cum = np.concatenate([[0.0], np.cumsum(seg)])
        per = cum[-1]
        out = []
        for k in range(self.n_windows):
            s = (k + 0.5) * per / self.n_windows
            i = int(np.searchsorted(cum, s)) % len(xy)
            t = xy[(i + 1) % len(xy)] - xy[i - 1]
            m = np.array([t[1], -t[0]]) / np.linalg.norm(t)
            if np.dot(m, xy[i]) < 0:
                m = -m
            out.append((xy[i], m))
        return out

    @property
    def window_width(self) -> float:
        if self.window_width_mm is not None:
            return float(self.window_width_mm)
        per = float(sum(__import__("numpy").linalg.norm(__import__("numpy").diff(
            __import__("numpy").vstack([self.stone.outline(512), self.stone.outline(512)[:1]]), axis=0), axis=1)))
        return min(1.6, 0.4 * per / max(1, self.n_windows))

    def windows_mesh(self):
        """The light windows as one watertight mesh (Windows Path): a stadium slot per window,
        through the cup along the outline's normal. No windows: a speck far outside the head."""
        import numpy as np
        import trimesh
        from shapely.geometry import LineString
        z0, z1 = self.window_zone()
        if self.n_windows == 0 or z1 - z0 < 0.5:
            speck = trimesh.creation.box(extents=(0.2, 0.2, 0.2))
            speck.apply_translation((self.stone.length + 10.0, 0.0, 0.0))
            return speck
        w = self.window_width
        r = min(w, z1 - z0) / 2
        parts = []
        for q, m in self.window_points():
            # the stadium in the (tangent, z) plane, extruded along the outward normal through the wall
            zc0, zc1 = z0 + r, z1 - r
            hw = max(w / 2 - r, 0.0)
            shape = LineString([(-hw, zc0), (hw, zc0), (hw, zc1), (-hw, zc1), (-hw, zc0)]).buffer(r, quad_segs=16) \
                if hw > 0 else LineString([(0, zc0), (0, zc1)]).buffer(r, quad_segs=16)
            slot = trimesh.creation.extrude_polygon(shape.convex_hull, height=4.0 + self.wall)
            # local (u, v, w) = (tangent, z, normal) -> head frame; the slot runs from 2 mm inside the girdle outward
            t = np.array([-m[1], m[0], 0.0]); n = np.array([m[0], m[1], 0.0]); zax = np.array([0.0, 0.0, 1.0])
            M = np.eye(4)
            M[:3, 0], M[:3, 1], M[:3, 2] = t, zax, n
            M[:3, 3] = np.array([q[0], q[1], 0.0]) - 2.0 * n
            slot.apply_transform(M)
            parts.append(slot)
        from . import geom
        return geom.clean(trimesh.boolean.union(parts, engine="manifold") if len(parts) > 1 else parts[0])

    def lowest_z(self) -> float:
        return self.z_bottom

    # ---- notebook ------------------------------------------------------------------------------
    def notebook_inputs(self, seat_path: str, windows_path: str = "", output_path: str | None = None) -> dict:
        ins = {"Seat Path": seat_path, "Clearance": round(self.clearance, 4), "Windows Path": windows_path,
               "Wall": round(self.wall, 4), "Bezel Bottom": round(self.z_bottom, 4), "Bezel Top": round(self.z_top, 4),
               "Blend Radius": round(self.blend, 4)}
        if output_path is not None:
            ins["Mesh Tolerance"] = self.mesh_tolerance_mm
            ins["Output Path"] = output_path
        return ins

    def design(self) -> dict:
        d = asdict(self)
        d["inputs"] = self.notebook_inputs("")
        d["window_zone"] = [round(v, 4) for v in self.window_zone()]
        return d

    def blend_volume_mm3(self) -> float:
        """A bezel blends only an intersection (its edges rounded): nothing is added."""
        return 0.0

    @property
    def stem(self) -> str:
        from . import runs
        return f"bezel_{self.stone.stem[len('stone_'):]}_{runs.spec_id(self.design())}"

    def validate(self) -> list[str]:
        p = self.stone.validate()
        if p:
            return p
        if self.wall < WALL_FLOOR:
            p.append(f"bezel wall {self.wall} mm below the wall floor {WALL_FLOOR} mm")
        if self.wall > 1.2:
            p.append(f"a {self.wall} mm bezel wall is too stiff to burnish over the stone (0.5-0.8 mm)")
        crown, _ = self.stone.heights
        if not 0.2 <= self.lip <= 0.8 * crown:
            p.append(f"bezel lip {self.lip} mm: 0.2 mm up to 80 % of the crown ({0.8 * crown:.2f} mm)")
        if self.n_windows:
            z0, z1 = self.window_zone()
            if z1 - z0 < 0.5:
                p.append(f"no room for light windows ({z1 - z0:.2f} mm between the cup's edge and the bearing): windows=0")
            if self.window_width < WALL_FLOOR:
                p.append("windows narrower than the wall floor will not print or cast open")
        if self.z_bottom > -self.stone.girdle / 2 - self.bearing - 0.3:
            p.append("the cup is too shallow to carry the stone: more pavilion under the bearing")
        p += blend_problems(self.blend, self.wall / 2)
        return p

    def describe(self) -> str:
        z0, z1 = self.window_zone()
        win = (f"{self.n_windows} light windows {self.window_width:.2f} mm wide, z {z0:.2f}..{z1:.2f}" if self.n_windows
               else "a closed cup")
        return (f"{self.stem}: bezel on a {self.stone.describe()}\n"
                f"  wall {self.wall} mm, lip {self.lip} mm above the girdle (top z {self.z_top:.2f}), cup down to z "
                f"{self.z_bottom:.2f}, bearing {self.bearing} mm under the girdle; {win}; clearance {self.clearance} mm; "
                f"edges blended {self.blend:g} mm")

    def design_mesh(self):
        return bezel_mesh(self.notebook_inputs(""), self.seat.envelope(), self.windows_mesh())


def bezel_mesh(v: dict, envelope, windows, cut_seat: bool = True):
    """The bezel from the block's numbers, the seat envelope and the windows mesh (as nTop builds it)."""
    import trimesh
    from . import geom
    c, wall = float(v["Clearance"]), float(v["Wall"])
    z0, z1 = float(v["Bezel Bottom"]), float(v["Bezel Top"])
    grown = _offset_convex(envelope, c + wall)
    slab = trimesh.creation.box(extents=(80.0, 80.0, z1 - z0))
    slab.apply_translation((0.0, 0.0, (z0 + z1) / 2))
    cup = trimesh.boolean.intersection([grown, slab], engine="manifold")
    if not windows.is_volume:
        windows = geom.clean(windows)
    cuts = [windows] + ([_offset_convex(envelope, c)] if cut_seat else [])
    return geom.clean(trimesh.boolean.difference([cup] + cuts, engine="manifold"))


def bezel_wall_check(spec: BezelSpec, mesh, frame=None):
    """The wall above the girdle is a closed ring at least the wall floor thick everywhere:
    shrunk by half the floor, the section half way up the lip must still be one ring."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    from . import gate
    import numpy as np
    z = spec.stone.girdle / 2 + spec.lip / 2
    sec = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    if sec is None:
        return gate.Check("bezel wall", False, f"no metal at z {z:.2f}", status=gate.INCOMPLETE)
    planar, to3d = sec.to_2D()
    polys = []
    for poly in planar.polygons_full:
        ext = (to3d @ np.column_stack([np.asarray(poly.exterior.coords), np.zeros(len(poly.exterior.coords)),
                                        np.ones(len(poly.exterior.coords))]).T).T[:, :2]
        holes = [(to3d @ np.column_stack([np.asarray(h.coords), np.zeros(len(h.coords)), np.ones(len(h.coords))]).T).T[:, :2]
                 for h in poly.interiors]
        polys.append(Polygon(ext, holes).buffer(0))
    outline = Polygon(spec.stone.outline())
    ring = unary_union(polys).intersection(outline.buffer(spec.wall + spec.clearance + 0.3).difference(outline.buffer(-0.1)))
    thin = ring.buffer(-WALL_FLOOR / 2 + 1e-3)
    pieces = list(thin.geoms) if hasattr(thin, "geoms") else ([thin] if not thin.is_empty else [])
    closed = len(pieces) == 1 and len(pieces[0].interiors) == 1
    width = ring.area / max(outline.length, 1e-9)
    return gate.Check("bezel wall", closed, f"{'a closed ring' if closed else 'broken or thin'} at z {z:.2f}, "
                                            f"mean {width:.2f} mm, every part >= {WALL_FLOOR} mm" if closed else
                      f"the wall at z {z:.2f} is broken or under {WALL_FLOOR} mm somewhere (mean {width:.2f} mm)")


def check_bezel(spec: BezelSpec, stl: Path, ntop_vol: float | None):
    """Closed, one shell, stone fits, seated (metal under the girdle all round), drop-in clear,
    the wall a closed ring >= the floor, volume vs nTop and vs the independent bezel."""
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
    rep.checks.append(gate.Check("stone fits", overlap <= allowed, f"bezel ∩ stone {overlap:.3f} mm³ (allowed {allowed:.3f})"))
    under, above = seat_regions(spec.stone, spec.clearance)
    g = spec.stone.girdle
    seated = outline_count(head, -g / 2 - 0.3, under)
    blocking = outline_count(head, g / 2 + 0.15, above)
    rep.checks.append(gate.Check("seated", seated >= 1, f"{seated} piece(s) of the cup under the girdle"))
    rep.checks.append(gate.Check("drop-in clear", blocking == 0, f"{blocking} pieces inside the girdle line above the girdle"))
    rep.checks.append(bezel_wall_check(spec, head))
    rep.checks.append(band.design_volume_check(float(spec.design_mesh().volume), ntop_vol, 3.0))
    return rep


def build_bezel(spec: BezelSpec, out_dir: Path | None = None, *, notebook: Path | None = None,
                catalog_name: str = "bezel_head_harness") -> HeadResult:
    """Run the bezel_head block through its harness under nTopCL and gate it."""
    from . import catalog, config, ntopcl, runs
    from . import gate as _gate
    problems = spec.validate()
    if problems:
        raise ValueError("; ".join(problems))
    cat = catalog.load(catalog_name)
    nb = Path(notebook) if notebook else cat.notebook
    run_dir, run_id = runs.fresh_run_dir(Path(out_dir) if out_dir else config.out_dir() / "head", spec.stem)
    envelope, windows = run_dir / f"{spec.stem}.envelope.stl", run_dir / f"{spec.stem}.windows.stl"
    spec.seat.envelope().export(str(envelope))
    spec.windows_mesh().export(str(windows))
    spec.stone.mesh().export(str(run_dir / f"{spec.stem}.stone.stl"))
    stl = run_dir / f"{spec.stem}.stl"
    inputs = spec.notebook_inputs(str(envelope), str(windows), str(stl))
    started = time.time()
    run = ntopcl.run(nb, cat.build_inputs(inputs), run_dir, tag=spec.stem)
    try:
        runs.require_fresh(stl, started, "the exported bezel")
    except FileNotFoundError as e:
        raise ntopcl.NtopclError(f"notebook reported success but {e}", run) from e
    entry = run.outputs.get(cat.output.get("name", "Volume"))
    ntop_vol = ntopcl.scalar_value(entry) if entry else None
    rep = check_bezel(spec, stl, ntop_vol)
    _gate.save(rep)
    res = HeadResult(spec, stl, run, rep, ntop_vol, run_dir, run_id)
    res.notes.append(f"metal: " + ", ".join(f"{k} {v:.2f} g" for k, v in tables.weights_g(rep.volume_mm3).items()))
    (run_dir / f"{spec.stem}.report.json").write_text(json.dumps({
        "stem": spec.stem, "run_id": run_id, "status": res.status, "design": spec.design(), "inputs": inputs,
        "ntop_volume_mm3": ntop_vol, "gate": rep.to_dict(), "notebook": runs.notebook_identity(nb),
        "environment": runs.environment(ntopcl.version()), "notes": res.notes}, indent=2, default=str), encoding="utf-8")
    return res
