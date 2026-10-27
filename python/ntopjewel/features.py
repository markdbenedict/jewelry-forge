"""Phase 1 step 2: a profiled band with milgrain, a channel groove and a wrapped engraving.

`RingSpec` wraps a `BandSpec` and works out every number `ring_features.ntop` needs
(`notebook_inputs`), the engraving STL it imports (`write_engraving`), what the mesh gate
should expect, and the design volume the nTop volume is checked against. A feature that is
off is sent as geometry that cannot change the band (a 0.05 mm bead inside the wall, a groove
torus 10 mm outside, a speck of an engraving mesh far away) - the notebook has no switches.
"""
from __future__ import annotations

import json
import math
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import catalog, config, engrave, gate, ntopcl, tables
from .band import BandSpec, MIN_EDGE_THICKNESS

BEAD_CORNER_INSET = 0.15     # bead centre sits this many radii inside the edge corner (both ways): ~55 % of the bead shows
BEAD_PITCH = 2.2             # centre-to-centre spacing in bead radii
MIN_BEAD_RADIUS = tables.FLOORS["bead_dia"] / 2
WALL_FLOOR = tables.FLOORS["wall_marginal"]
ENGRAVE_MIN_STROKE = 0.3


@dataclass
class RingSpec:
    band: BandSpec
    milgrain: bool = False
    bead_radius_mm: float = 0.3
    bead_pitch: float = BEAD_PITCH
    groove_depth_mm: float = 0.0          # 0 = no groove
    groove_width_mm: float = 0.6
    groove_z_mm: float = 0.0
    text: str | None = None
    engrave_side: str = "inside"
    engrave_height_mm: float | None = None
    engrave_depth_mm: float = 0.3
    font: dict | None = None
    engraving_info: dict = field(default_factory=dict)   # filled by write_engraving()

    # ---- derived geometry ---------------------------------------------------------------
    @property
    def has_groove(self) -> bool:
        return self.groove_depth_mm > 0

    @property
    def has_engraving(self) -> bool:
        return bool(self.text)

    @property
    def label(self) -> str:
        return self.band.label

    @property
    def stem(self) -> str:
        tags = []
        if self.milgrain:
            tags.append("milgrain")
        if self.has_groove:
            tags.append("groove")
        if self.has_engraving:
            tags.append("engraved")
        return f"ring_{self.band.profile}_{'_'.join(tags) or 'plain'}_{self.label}"

    def bead_geometry(self) -> dict:
        b = self.band
        if not self.milgrain:
            return {"radius": 0.05, "ring_radius": b.bore_radius_mm + b.thickness_mm / 2, "z": 0.0, "count": 1, "spacing": 360.0}
        rho = self.bead_radius_mm
        r_edge = b.outer_radius_at(b.width_mm / 2)          # outer surface radius at the band edge
        ring_radius = r_edge - BEAD_CORNER_INSET * rho
        z = b.width_mm / 2 - BEAD_CORNER_INSET * rho
        count = max(8, int(round(2 * math.pi * ring_radius / (self.bead_pitch * rho))))
        return {"radius": rho, "ring_radius": ring_radius, "z": z, "count": count, "spacing": 360.0 / count}

    def groove_geometry(self) -> dict:
        b = self.band
        if not self.has_groove:
            return {"ring_radius": b.outer_radius_mm + 10.0, "tube": 0.1, "z": 0.0}
        tube = self.groove_width_mm / 2
        return {"ring_radius": b.outer_radius_at(self.groove_z_mm) + tube - self.groove_depth_mm, "tube": tube, "z": self.groove_z_mm}

    def engrave_geometry(self) -> dict:
        """Where the text sits: the surface radius at the text's half-height (so the pocket is
        `depth` deep at the text's edges and a little deeper in the middle on a curved face),
        the wrap length (undistorted at the mid-plane radius) and the height used."""
        b = self.band
        h = self.engrave_height_mm or min(2.0, b.width_mm - 2 * b.edge_round - 0.6)
        if self.engrave_side == "inside":
            return {"height": h, "radius": b.bore_radius_at(h / 2), "wrap_radius": b.bore_radius_mm, "side": "inside"}
        return {"height": h, "radius": b.outer_radius_at(h / 2), "wrap_radius": b.outer_radius_mm, "side": "outside"}

    # ---- the engraving file ----------------------------------------------------------------
    def write_engraving(self, path: Path) -> dict:
        g = self.engrave_geometry()
        self.engraving_info = engrave.write_engraving(Path(path), self.text, g["height"], self.engrave_depth_mm,
                                                      g["radius"], g["side"], font=self.font)
        self.engraving_info["wrap_length_mm"] = engrave.wrap_length_mm(g["wrap_radius"])
        return self.engraving_info

    # ---- the notebook ------------------------------------------------------------------------
    def notebook_inputs(self, output_path: str, engraving_path: str) -> dict:
        beads, groove, eng = self.bead_geometry(), self.groove_geometry(), self.engrave_geometry()
        ins = self.band.notebook_inputs(output_path)
        ins.pop("Output Path")
        ins.update({
            "Bead Radius": round(beads["radius"], 4),
            "Bead Ring Radius": round(beads["ring_radius"], 4),
            "Bead Z": round(beads["z"], 4),
            "Bead Z Minus": round(-beads["z"], 4),
            "Bead Spacing": round(beads["spacing"], 4),
            "Bead Count": int(beads["count"]),
            "Groove Ring Radius": round(groove["ring_radius"], 4),
            "Groove Tube Radius": round(groove["tube"], 4),
            "Groove Z": round(groove["z"], 4),
            "Engraving Path": str(engraving_path),
            "Engraving Wrap Length": round(engrave.wrap_length_mm(eng["wrap_radius"]), 4),
            "Output Path": output_path,
        })
        return ins

    # ---- checks -------------------------------------------------------------------------------
    def validate(self) -> list[str]:
        b = self.band
        problems = list(b.validate())
        if self.milgrain:
            if self.bead_radius_mm < MIN_BEAD_RADIUS:
                problems.append(f"bead radius {self.bead_radius_mm} mm below the milgrain floor {MIN_BEAD_RADIUS} mm")
            if self.bead_pitch < 2.0:
                problems.append("bead pitch below 2 radii: beads would merge")
        if self.has_groove:
            if self.groove_depth_mm < 0.1:
                problems.append("groove depth below 0.1 mm would not survive casting")
            if b.thickness_at(self.groove_z_mm) - self.groove_depth_mm < WALL_FLOOR:
                problems.append(f"groove leaves {b.thickness_at(self.groove_z_mm) - self.groove_depth_mm:.2f} mm of wall "
                                f"under it; floor {WALL_FLOOR} mm")
            if abs(self.groove_z_mm) + self.groove_width_mm / 2 > b.width_mm / 2 - b.edge_round:
                problems.append("groove runs into the edge round; move or narrow it")
        if self.has_engraving:
            if self.engrave_side not in ("inside", "outside"):
                problems.append("engrave side must be inside or outside")
            if self.engrave_depth_mm < engrave.MIN_DEPTH_MM:
                problems.append(f"engraving depth {self.engrave_depth_mm} mm below the floor {engrave.MIN_DEPTH_MM} mm")
            g = self.engrave_geometry()
            if g["height"] > b.width_mm - 2 * b.edge_round - 0.2:
                problems.append(f"text height {g['height']:.2f} mm does not fit a {b.width_mm} mm band with {b.edge_round} mm edges")
            left = b.thickness_at(g["height"] / 2) - self.engrave_depth_mm
            if left < WALL_FLOOR:
                problems.append(f"engraving leaves {left:.2f} mm of wall at the text's edge; floor {WALL_FLOOR} mm "
                                f"(shallower cut, smaller text or a thicker band)")
            try:
                shape = engrave.text_polygons(self.text, g["height"], self.font)
                stroke = engrave.stroke_width_mm(shape)
                if stroke < ENGRAVE_MIN_STROKE:
                    problems.append(f"thinnest stroke {stroke:.2f} mm below {ENGRAVE_MIN_STROKE} mm at {g['height']:.2f} mm text height")
                arc = shape.bounds[2] - shape.bounds[0]
                if arc > 0.9 * 2 * math.pi * g["wrap_radius"]:
                    problems.append(f"text is {arc:.1f} mm long; the ring's circumference is {2 * math.pi * g['wrap_radius']:.1f} mm")
            except ValueError as e:
                problems.append(str(e))
        return problems

    def gate_expectations(self) -> dict:
        b = self.band
        beads = self.bead_geometry()
        width = b.width_mm
        outer = 2 * b.outer_radius_mm
        if self.has_groove:
            # the groove removes the outer surface over |z - groove z| < tube: the widest point left
            g = self.groove_geometry()
            zs = [z / 100 for z in range(-int(b.width_mm * 50), int(b.width_mm * 50) + 1)]
            outer = 2 * max(b.outer_radius_at(z) for z in zs if abs(z - g["z"]) >= g["tube"] and abs(z) <= b.width_mm / 2)
        exp = {"expect_inner": b.inner_diameter_mm, "wall_floor": min(WALL_FLOOR, 0.8 * b.edge_thickness_mm)}
        if self.milgrain:
            width = max(width, 2 * (beads["z"] + beads["radius"]))
            outer = max(outer, 2 * (beads["ring_radius"] + beads["radius"]))
            # beads are solid bumps on a solid band: a ray grazing one measures a chord, not a wall.
            # Measure the band between the bead rows.
            exp["wall_abs_axis_max"] = beads["z"] - beads["radius"] - 0.05
        exp.update({"expect_outer": outer, "expect_width": width})
        return exp

    def engraving_pocket(self, mesh) -> dict:
        """Is the text cut where the design put it? Counts mesh vertices lying 0.08..depth+0.08 mm
        below the engraved surface, within the text's height and angular span (centred on +X)."""
        import numpy as np
        if not self.has_engraving:
            return {"checked": False}
        g = self.engrave_geometry()
        v = mesh.vertices
        axis = 2
        z = v[:, axis]
        r = np.hypot(v[:, 0], v[:, 1])
        theta = np.arctan2(v[:, 1], v[:, 0])
        arc = float(self.engraving_info.get("arc_length_mm") or 0.0)
        half_angle = arc / 2 / g["wrap_radius"] + 0.1
        in_span = (np.abs(z) <= g["height"] / 2 + 0.1) & (np.abs(theta) <= half_angle)

        def depth(sel):
            """How far below the engraved surface each selected vertex lies (positive = into the metal)."""
            if not sel.any():
                return np.array([])
            surf = np.array([self.band.bore_radius_at(float(zz)) if g["side"] == "inside" else self.band.outer_radius_at(float(zz))
                             for zz in z[sel]])
            return (r[sel] - surf) if g["side"] == "inside" else (surf - r[sel])

        lo, hi = 0.08, self.engrave_depth_mm + 0.08
        d1 = depth(in_span)
        hits = int(((d1 > lo) & (d1 < hi)).sum()) if d1.size else 0
        # the same band of radii elsewhere round the ring must be empty: the pocket is local to the text
        d2 = depth((np.abs(z) <= g["height"] / 2) & (np.abs(theta) > half_angle + 0.4))
        stray = int(((d2 > lo) & (d2 < hi)).sum()) if d2.size else 0
        return {"checked": True, "pocket_vertices": hits, "stray_vertices": stray, "side": g["side"],
                "found": hits >= 200}

    def design_volume_mm3(self, step: float = 0.005) -> float:
        """Band design volume + the beads' protruding parts - the groove - the engraving cut."""
        import numpy as np
        b = self.band
        vol = b.design_volume_mm3(step)
        if self.milgrain:
            g = self.bead_geometry()
            rho, rc, zc = g["radius"], g["ring_radius"], g["z"]
            r, z, mask = b.opened_section(step, pad=rho + 0.1)
            s = step * 2
            ys = np.arange(-rho, rho + s / 2, s)
            rs = np.arange(rc - rho, rc + rho + s / 2, s)
            zs = np.arange(zc - rho, zc + rho + s / 2, s)
            RR, ZZ = np.meshgrid(rs, zs)
            ri = np.clip(np.round((RR - r[0]) / step).astype(int), 0, len(r) - 1)
            zi = np.clip(np.round((ZZ - z[0]) / step).astype(int), 0, len(z) - 1)
            in_band = mask[zi, ri]
            outside = 0.0
            for y in ys:
                rad2 = rho ** 2 - y ** 2
                if rad2 <= 0:
                    continue
                in_sphere = (RR - rc) ** 2 + (ZZ - zc) ** 2 <= rad2
                outside += float((in_sphere & ~in_band).sum()) * s * s * s
            vol += 2 * g["count"] * outside
        if self.has_groove:
            g = self.groove_geometry()
            t, d = g["tube"], self.groove_depth_mm
            d = min(d, 2 * t)
            seg = t * t * math.acos((t - d) / t) - (t - d) * math.sqrt(max(2 * t * d - d * d, 0.0))
            vol -= 2 * math.pi * (g["ring_radius"] - t + d / 2) * seg
        if self.has_engraving:
            cut = self.engraving_info.get("cut_volume_mm3")
            if cut is None:
                g = self.engrave_geometry()
                cut = engrave.text_polygons(self.text, g["height"], self.font).area * self.engrave_depth_mm
            vol -= float(cut)
        return float(vol)

    def describe(self) -> str:
        beads, groove, eng = self.bead_geometry(), self.groove_geometry(), self.engrave_geometry()
        lines = [self.band.describe(), f"  {self.stem}"]
        if self.milgrain:
            lines.append(f"  milgrain: {beads['count']} beads/row of r {beads['radius']} mm at r {beads['ring_radius']:.3f}, "
                         f"z ±{beads['z']:.3f}, {beads['spacing']:.3f}° apart")
        if self.has_groove:
            lines.append(f"  groove: {self.groove_width_mm} mm wide, {self.groove_depth_mm} mm deep at z {self.groove_z_mm} "
                         f"(torus R {groove['ring_radius']:.3f} / tube {groove['tube']:.3f})")
        if self.has_engraving:
            lines.append(f"  engraving: {self.text!r} {eng['side']}, {eng['height']:.2f} mm high, {self.engrave_depth_mm} mm deep, "
                         f"on r {eng['radius']:.3f}, wrap length {engrave.wrap_length_mm(eng['wrap_radius']):.3f} mm")
        return "\n".join(lines)


@dataclass
class RingResult:
    spec: RingSpec
    stl: Path
    run: ntopcl.RunResult
    gate: gate.GateReport
    ntop_volume_mm3: float | None
    delivered: Path | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.run.ok and self.gate.passed

    def text(self) -> str:
        lines = [self.spec.describe(), self.run.summary(), self.gate.text()]
        if self.delivered:
            lines.append(f"  delivered to {self.delivered}")
        lines += [f"  note: {n}" for n in self.notes]
        return "\n".join(lines)


def check_mesh(spec: RingSpec, stl: Path, ntop_vol: float | None, info: dict) -> tuple[gate.GateReport, list[str]]:
    """The mesh gate with this ring's expectations, the engraving-pocket check and the
    design-volume cross-check; shared by the nTopCL run and the GUI preview."""
    rep = gate.check(stl, expect_volume=ntop_vol, **spec.gate_expectations())
    notes = []
    if spec.has_engraving:
        pocket = spec.engraving_pocket(gate.load_mesh(stl))
        rep.checks.append(gate.Check("engraving", pocket["found"],
                                     f"{pocket['pocket_vertices']} mesh vertices in the {pocket['side']} pocket"
                                     + (f"; {pocket['stray_vertices']} stray" if pocket["stray_vertices"] else "")
                                     + ("" if pocket["found"] else " - the text did not cut (wrong side, units or wrap length?)")))
        notes.append(f"engraving {spec.text!r} on the {spec.engrave_side}: {info['arc_length_mm']:.1f} mm long, "
                     f"thinnest stroke {info['stroke_mm']:.2f} mm, cut volume ~{info['cut_volume_mm3']:.1f} mm³")
    if ntop_vol is None:
        notes.append("nTop volume not reported; volume not cross-checked.")
    else:
        design = spec.design_volume_mm3()
        dev = (ntop_vol - design) / design * 100
        tol = 3.0 if (spec.milgrain or spec.has_engraving) else 2.0
        verdict = "matches the design" if abs(dev) <= tol else "DIFFERS from the design - check the notebook"
        notes.append(f"nTop volume {ntop_vol:.2f} mm³ vs design {design:.2f} mm³ ({dev:+.2f} %): {verdict}")
    return rep, notes


def build(spec: RingSpec, out_dir: Path | None = None, *, notebook: Path | None = None,
          catalog_name: str = "ring_features", deliver: bool = False, deliver_project: str = "Rings") -> RingResult:
    problems = spec.validate()
    if problems:
        raise ValueError("; ".join(problems))
    cat = catalog.load(catalog_name)
    nb = Path(notebook) if notebook else cat.notebook
    out_dir = Path(out_dir) if out_dir else config.out_dir() / "ring"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = spec.stem
    stl = (out_dir / f"{stem}.stl").resolve()
    engraving = (out_dir / f"{stem}.engraving.stl").resolve()
    info = spec.write_engraving(engraving)

    inputs = cat.build_inputs(spec.notebook_inputs(str(stl), str(engraving)))
    run = ntopcl.run(nb, inputs, out_dir, tag=stem)
    if not stl.exists():
        raise ntopcl.NtopclError(f"notebook reported success but {stl} was not written", run)

    vol_entry = run.outputs.get(cat.output.get("name", "Volume"))
    ntop_vol = ntopcl.scalar_value(vol_entry) if vol_entry else None
    rep, notes = check_mesh(spec, stl, ntop_vol, info)
    result = RingResult(spec, stl, run, rep, ntop_vol)
    result.notes += spec.band.warnings() + notes

    if deliver and result.ok:
        dest = config.deliver_dir() / deliver_project
        dest.mkdir(parents=True, exist_ok=True)
        result.delivered = Path(shutil.copy2(stl, dest / stl.name))

    (out_dir / f"{stem}.report.json").write_text(json.dumps({
        "band": spec.band.__dict__, "features": {k: v for k, v in spec.__dict__.items() if k not in ("band", "engraving_info")},
        "engraving": info, "inputs": spec.notebook_inputs(str(stl), str(engraving)), "stl": str(stl), "ok": result.ok,
        "ntop_volume_mm3": ntop_vol, "gate": rep.to_dict(), "ntopcl_seconds": run.seconds,
        "block_timings": [t.__dict__ for t in run.log.timings], "notes": result.notes,
    }, indent=2, default=str), encoding="utf-8")
    return result


# ---- look at one ring in nTop's GUI ------------------------------------------------------------
PREVIEW_SHOW = ["Ring Body", "Engraved"]     # the finished ring; every other block is hidden in the viewport
PREVIEW_RECIPE = "ring_features"


@dataclass
class PreviewResult:
    spec: RingSpec
    notebook: Path
    stl: Path
    build: dict                       # the build script's result (blocks, states, volume, log)
    gate: gate.GateReport | None      # on the mesh the GUI session exported, when it did
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.gate is not None and self.gate.passed

    def text(self) -> str:
        lines = [self.spec.describe(),
                 f"  built in nTop's open session and saved as {self.notebook}",
                 f"  volume {self.build.get('volume')} mm³ (nTop, GUI session)"]
        if self.gate is not None:
            lines.append(self.gate.text())
        else:
            lines.append(f"  the session did not export {self.stl}; nothing to gate (see the build log)")
        for w in self.build.get("warnings") or []:
            lines.append(f"  warning: {w}")
        lines += [f"  note: {n}" for n in self.notes]
        return "\n".join(lines)


def preview(spec: RingSpec, out_dir: Path | None = None, *, console=None, recipe: Path | None = None,
            timeout: float = 900) -> PreviewResult:
    """Build a notebook with THIS ring's numbers in nTop's open session, through the Notebook
    API, so the ring can be looked at (and poked at) in the GUI: `ring ... --show`.

    nTopCL never changes a notebook - a `ring` run leaves only an STL behind - so to see a
    particular ring in nTop the notebook has to be built with that ring's values. This runs the
    same build script as `api build ring_features`, with the values `notebook_inputs` works
    out instead of the test values, saves `out/api/preview/<stem>.ntop`, hides everything but
    the finished ring in the viewport, and gates the mesh the session exported. The repo's
    `ring_features.ntop` is untouched; nTop's open notebook is replaced (unsaved GUI changes
    to it are lost)."""
    from . import notebook_api
    problems = spec.validate()
    if problems:
        raise ValueError("; ".join(problems))
    # absolute: the script runs in nTop's Python, whose working directory is nTop's install folder
    out_dir = (Path(out_dir) if out_dir else config.out_dir() / "api" / "preview").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = spec.stem
    stl = out_dir / f"{stem}.stl"
    engraving = out_dir / f"{stem}.engraving.stl"
    notebook = out_dir / f"{stem}.ntop"
    info = spec.write_engraving(engraving)
    values = spec.notebook_inputs(str(stl), str(engraving))
    values.pop("Output Path")                       # the build script's test_output carries it
    if stl.exists():
        stl.unlink()                                # so an old export cannot pass for this build's
    params = {"values": values, "test_output": str(stl), "save_to": str(notebook),
              "recipe_to": str(out_dir / f"{stem}.recipe.json"), "show": list(PREVIEW_SHOW)}
    script = Path(recipe) if recipe else config.repo_root() / "ntop" / "recipes" / f"{PREVIEW_RECIPE}.py"
    console = console or notebook_api.Console()
    res = console.run_script(script, params, work_dir=out_dir, python_path=config.repo_root() / "python", timeout=timeout)
    r = res.get("result") or {}
    result = PreviewResult(spec, Path(r.get("saved") or notebook), stl, r, None)
    result.notes += spec.band.warnings()
    vol = r.get("volume")
    ntop_vol = float(vol) if isinstance(vol, (int, float)) else None
    if stl.exists():
        result.gate, notes = check_mesh(spec, stl, ntop_vol, info)
        result.notes += notes
    (out_dir / f"{stem}.preview.json").write_text(json.dumps({
        "inputs": spec.notebook_inputs(str(stl), str(engraving)), "notebook": str(result.notebook), "stl": str(stl),
        "engraving": info, "volume_mm3": ntop_vol, "gate": result.gate.to_dict() if result.gate else None,
        "display": r.get("display"), "notes": result.notes,
    }, indent=2, default=str), encoding="utf-8")
    return result
