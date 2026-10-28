"""The solitaire: a prong head on a profiled band with cathedral shoulders - the Phase 2 gate.

Ring frame (nTop convention): ring axis Z, band centred on the origin, the head on +X.

    band       the profiled band (ring_band_profile's eleven numbers)
    cathedral  a cylinder along Z of radius R2 centred at (Cathedral X, 0): through the band's
               outer surface at ±`shoulder_deg` from the top and through a crown just below the
               girdle - each shoulder sweeps up from the band to the head. Intersected with the
               band's comfort torus, so it stops at the comfort bore and keeps its relief
    seat       the stone_seat cutter (stone + straight drop-in path + clearance), placed with the
               head, subtracted from band + shoulders: the pavilion sits down into the metal
    head       the prong_head block (its own seat cut), placed: a quarter-turn about the line
               through (Pivot X, *, Pivot Z) parallel to +Y takes the head's +Z to +X and its
               origin (the girdle centre) to (Girdle Radius, 0, 0)

Placement: the culet sits `finger_clear_mm` (default the marginal wall floor + 0.1) above the
bore, so there is metal under the stone and the finger never touches it; the head's feet then
sit inside the shank. Everything here is Python arithmetic; `ring_mesh(inputs)` rebuilds the
same ring from the notebook's input numbers (trimesh + manifold3d) for the gate.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import band as bandmod, gems, geom, heads, tables

WALL_FLOOR = tables.FLOORS["wall_marginal"]
HEAD_ANGLE_DEG = 90.0


@dataclass
class SolitaireSpec:
    band: bandmod.BandSpec
    head: heads.HeadSpec
    finger_clear_mm: float | None = None    # metal between the bore and the culet
    shoulder_deg: float = 45.0              # where each shoulder leaves the band, from the top
    crown_below_girdle_mm: float = 0.6      # the shoulders' crown, below the girdle's underside

    # ---- placement ------------------------------------------------------------------------
    @property
    def placed_head(self) -> heads.HeadSpec:
        """The head as it goes on this band: its feet raised so the lower rail stays inside the
        shank, 0.2 mm clear of the bore (the standalone head drops its feet below the culet; on a
        ring with 0.6 mm under the culet that rail would break into the finger hole)."""
        from dataclasses import replace
        drop = self.finger_clear - (self.head.rail_rho + 0.2)
        return replace(self.head, base_drop_mm=round(drop, 4))

    @property
    def finger_clear(self) -> float:
        return WALL_FLOOR + 0.1 if self.finger_clear_mm is None else float(self.finger_clear_mm)

    @property
    def girdle_radius(self) -> float:
        """Ring-frame radius of the girdle's mid-plane (the head's origin)."""
        s = self.head.stone
        _, pav = s.heights
        return self.band.bore_radius_mm + self.finger_clear + pav + s.girdle / 2

    @property
    def pivot(self) -> tuple[float, float]:
        """(x, z) of the rotation axis: a +90° turn about it moves the origin to (girdle radius, 0, 0)."""
        R = self.girdle_radius
        return R / 2, -R / 2

    def cathedral(self) -> tuple[float, float]:
        """(centre x, radius) of the shoulder circle through the band's outer surface at
        ±shoulder_deg and the crown just under the girdle."""
        ro = self.band.outer_radius_mm
        x_top = self.girdle_radius - self.head.stone.girdle / 2 - self.crown_below_girdle_mm
        phi = math.radians(self.shoulder_deg)
        xc = (x_top ** 2 - ro ** 2) / (2 * (x_top - ro * math.cos(phi)))
        return xc, x_top - xc

    # ---- the notebook's numbers ----------------------------------------------------------------
    def notebook_inputs(self, seat_path: str, output_path: str | None = None) -> dict:
        ins = self.band.notebook_inputs("")
        ins.pop("Output Path")
        head = self.placed_head.notebook_inputs(seat_path)            # Seat Path, Clearance + the 14 head numbers
        ins.update(head)
        px, pz = self.pivot
        xc, r2 = self.cathedral()
        ins.update({"Pivot X": round(px, 4), "Pivot Z": round(pz, 4),
                    "Cathedral X": round(xc, 4), "Cathedral Radius": round(r2, 4)})
        if output_path is not None:
            ins["Output Path"] = output_path
        return ins

    def design(self) -> dict:
        return {"band": self.band.design(), "head": self.placed_head.design(), "finger_clear_mm": self.finger_clear,
                "shoulder_deg": self.shoulder_deg, "crown_below_girdle_mm": self.crown_below_girdle_mm}

    @property
    def stem(self) -> str:
        from . import runs
        b, s = self.band, self.head.stone
        return (f"solitaire_{b.profile}_{b.label}_{self.head.prongs}prong_{s.stem[len('stone_'):]}_"
                f"{runs.spec_id(self.design())}")

    # ---- checks on the design ---------------------------------------------------------------
    def validate(self) -> list[str]:
        p = self.band.validate() + self.placed_head.validate()
        if self.finger_clear < WALL_FLOOR:
            p.append(f"{self.finger_clear} mm of metal under the culet is below the wall floor {WALL_FLOOR} mm")
        lay = self.placed_head.layout()
        feet = self.girdle_radius + lay["z_base"]
        if feet > self.band.outer_radius_mm - 0.2:
            p.append(f"the head's feet (r {feet:.2f}) do not reach into the band (outer r {self.band.outer_radius_mm:.2f}): "
                     f"less finger clearance or a deeper base")
        if feet - self.head.rail_rho < self.band.bore_radius_mm + 0.1:
            p.append(f"the lower rail (inner r {feet - self.head.rail_rho:.2f}) breaks into the bore")
        xc, r2 = self.cathedral()
        crown = xc + r2
        if crown < self.band.outer_radius_mm + 0.3:
            p.append(f"the shoulders' crown (r {crown:.2f}) barely rises above the band (r {self.band.outer_radius_mm:.2f})")
        if not 20 <= self.shoulder_deg <= 75:
            p.append("shoulder angle outside 20-75°")
        return p

    def describe(self) -> str:
        xc, r2 = self.cathedral()
        px, pz = self.pivot
        lay = self.placed_head.layout()
        return (f"{self.stem}\n  {self.band.describe()}\n  {self.placed_head.describe()}\n"
                f"  placement: girdle at r {self.girdle_radius:.3f}, culet {self.finger_clear} mm above the bore, "
                f"feet at r {self.girdle_radius + lay['z_base']:.3f}; quarter-turn about (x {px:.3f}, z {pz:.3f}) ∥ Y\n"
                f"  cathedral: circle centre x {xc:.3f}, radius {r2:.3f}: leaves the band at ±{self.shoulder_deg:g}°, "
                f"crown at r {xc + r2:.3f}")


# ---- the independent ring ---------------------------------------------------------------------
def ring_mesh(v: dict, envelope, cut_seat: bool = True):
    """The solitaire from the notebook's input numbers, as nTop builds it."""
    import trimesh
    band = geom.band_mesh(v)
    xc, r2 = float(v["Cathedral X"]), float(v["Cathedral Radius"])
    zb, zt = float(v["Z Bottom"]), float(v["Z Top"])
    cyl = trimesh.creation.cylinder(radius=r2, segment=[[xc, 0, zb], [xc, 0, zt]], sections=360)
    comfort = trimesh.creation.torus(float(v["Comfort Ring Radius"]), float(v["Comfort Tube Radius"]),
                                     major_sections=360, minor_sections=96)
    shoulders = trimesh.boolean.intersection([cyl, comfort], engine="manifold")
    shank = trimesh.boolean.union([band, shoulders], engine="manifold")
    place = geom.rotation_about_y(HEAD_ANGLE_DEG, [float(v["Pivot X"]), 0.0, float(v["Pivot Z"])])
    if cut_seat:
        cutter = geom.offset_convex(envelope, float(v["Clearance"])).copy()
        cutter.apply_transform(place)
        shank = trimesh.boolean.difference([shank, cutter], engine="manifold")
    head = heads.head_mesh(v, envelope, cut_seat=cut_seat)
    head.apply_transform(place)
    return geom.clean(trimesh.boolean.union([shank, head], engine="manifold"))


def design_mesh(spec: SolitaireSpec):
    return ring_mesh(spec.notebook_inputs(""), spec.head.seat.envelope())


# ---- the gate -----------------------------------------------------------------------------------
def check_solitaire(spec: SolitaireSpec, stl: Path, ntop_vol: float | None):
    """Closed, one shell; band walls (the half away from the head) and bore; the bore closed under
    the stone; the stone fits (ring ∩ stone ≈ 0), sits (ledges) and drops in - in the head's frame;
    extents and volume against the independent ring."""
    import numpy as np
    import trimesh
    from . import gate
    b = spec.band
    rep = gate.check(stl, expect_volume=ntop_vol, wall_floor=min(WALL_FLOOR, 0.8 * b.edge_thickness_mm),
                     wall_ray_filter=lambda pts, n: pts[:, 0] < -2.0)        # the shank away from the head
    ring = gate.load_mesh(stl)
    r = np.hypot(ring.vertices[:, 0], ring.vertices[:, 1])
    bore = 2 * float(r.min())
    rep.checks.append(gate.Check("bore", abs(bore - b.inner_diameter_mm) <= 0.05,
                                 f"Ø {bore:.3f} vs {b.inner_diameter_mm:.3f} mm (about the ring axis)"))
    hits, _, _ = ring.ray.intersects_location([[0.0, 0.0, 0.0]], [[1.0, 0.0, 0.0]], multiple_hits=False)
    first = float(np.linalg.norm(hits[0])) if len(hits) else float("inf")
    rep.checks.append(gate.Check("bore closed under the stone", abs(first - b.bore_radius_mm) <= 0.1,
                                 f"from the axis towards the head, metal starts at r {first:.3f} (bore r {b.bore_radius_mm:.3f})"))
    design = design_mesh(spec)
    d = np.array(rep.extents_mm) - np.array(design.extents)
    rep.checks.append(gate.Check("extents", bool(np.all(np.abs(d) <= max(0.1, 2 * spec.head.mesh_tolerance_mm))),
                                 " x ".join(f"{x:.2f}" for x in rep.extents_mm) + " vs design "
                                 + " x ".join(f"{x:.2f}" for x in design.extents) + " mm"))
    # the head's checks, in the head's own frame
    place = geom.rotation_about_y(HEAD_ANGLE_DEG, [spec.pivot[0], 0.0, spec.pivot[1]])
    local = ring.copy()
    local.apply_transform(np.linalg.inv(place))
    stone = spec.head.stone.mesh()
    inter = trimesh.boolean.intersection([local, stone], engine="manifold") if local.is_watertight else None
    overlap = float(inter.volume) if inter is not None and len(inter.faces) else (0.0 if inter is not None else float("nan"))
    allowed = 0.002 * stone.volume
    rep.checks.append(gate.Check("stone fits", overlap <= allowed, f"ring ∩ stone {overlap:.3f} mm³ (allowed {allowed:.3f})"))
    Rg, g = spec.head.stone.width / 2, spec.head.stone.girdle
    ledges = heads._inner_count(local, -g / 2 - 0.3, Rg - 0.1)
    above = heads._inner_count(local, g / 2 + 0.15, Rg + spec.head.clearance * 0.5)
    rep.checks.append(gate.Check("seat ledges", ledges >= spec.head.prongs,
                                 f"{ledges} pieces reach under the girdle (expected >= {spec.head.prongs})"))
    rep.checks.append(gate.Check("drop-in clear", above == 0, f"{above} pieces inside the girdle line above the girdle"))
    from .band import design_volume_check
    rep.checks.append(design_volume_check(float(design.volume), ntop_vol, 3.0))
    return rep


@dataclass
class SolitaireResult:
    spec: SolitaireSpec
    stl: Path
    run: object
    gate: object
    ntop_volume_mm3: float | None
    run_dir: Path
    run_id: str
    delivered: Path | None = None
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
        lines = [self.spec.describe(), self.run.summary(), self.gate.text(), f"  status: {self.status.upper()}  run {self.run_dir}"]
        if self.delivered:
            lines.append(f"  delivered to {self.delivered}")
        return "\n".join(lines + [f"  note: {n}" for n in self.notes])


def build(spec: SolitaireSpec, out_dir: Path | None = None, *, notebook: Path | None = None,
          catalog_name: str = "solitaire", deliver: bool = False, deliver_project: str = "Solitaires",
          cast_metal: str | None = None) -> SolitaireResult:
    from . import catalog, config, ntopcl, runs
    problems = spec.validate()
    if problems:
        raise ValueError("; ".join(problems))
    cat = catalog.load(catalog_name)
    nb = Path(notebook) if notebook else cat.notebook
    run_dir, run_id = runs.fresh_run_dir(Path(out_dir) if out_dir else config.out_dir() / "solitaire", spec.stem)
    envelope = run_dir / f"{spec.stem}.envelope.stl"
    spec.head.seat.envelope().export(str(envelope))
    stl = run_dir / f"{spec.stem}.stl"
    started = time.time()
    run = ntopcl.run(nb, cat.build_inputs(spec.notebook_inputs(str(envelope), str(stl))), run_dir, tag=spec.stem)
    try:
        runs.require_fresh(stl, started, "the exported ring")
    except FileNotFoundError as e:
        raise ntopcl.NtopclError(f"notebook reported success but {e}", run) from e
    entry = run.outputs.get(cat.output.get("name", "Volume"))
    ntop_vol = ntopcl.scalar_value(entry) if entry else None
    rep = check_solitaire(spec, stl, ntop_vol)
    res = SolitaireResult(spec, stl, run, rep, ntop_vol, run_dir, run_id)
    stone = spec.head.stone
    res.notes.append(f"stone {stone.carats():.2f} ct {stone.material}; metal " +
                     ", ".join(f"{k} {v:.2f} g" for k, v in tables.weights_g(rep.volume_mm3).items()))
    res.notes += spec.band.warnings()
    report = {"stem": spec.stem, "spec_id": runs.spec_id(spec.design()), "run_id": run_id, "status": res.status,
              "design": spec.design(), "inputs": spec.notebook_inputs(str(envelope), str(stl)), "stl": str(stl),
              "ntop_volume_mm3": ntop_vol, "gate": rep.to_dict(), "notes": res.notes,
              "notebook": runs.notebook_identity(nb), "environment": runs.environment(ntopcl.version())}
    (run_dir / f"{spec.stem}.report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    if deliver and res.ok:
        res.delivered = runs.deliver(stl, run_dir, spec.stem, deliver_project, report, cast_metal=cast_metal)
    elif deliver:
        res.notes.append(f"not delivered: status {res.status}")
    return res
