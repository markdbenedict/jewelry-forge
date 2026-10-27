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
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import catalog, config, engrave, gate, ntopcl, runs, tables
from .band import BandSpec, MIN_EDGE_THICKNESS, design_volume_check

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
    def features_tag(self) -> str:
        tags = []
        if self.milgrain:
            tags.append("milgrain")
        if self.has_groove:
            tags.append("groove")
        if self.has_engraving:
            tags.append("engraved")
        return "_".join(tags) or "plain"

    def design(self) -> dict:
        """Every number that defines this ring (what `spec_id` hashes): the band's design, the
        feature inputs without the two paths, and the engraving itself (text, side, height,
        depth, font), which the notebook sees only as a mesh."""
        d = self.notebook_inputs("", "")
        d.pop("Output Path")
        d.pop("Engraving Path")
        d["profile"] = self.band.profile
        if self.has_engraving:
            g = self.engrave_geometry()
            d["engraving"] = {"text": self.text, "side": self.engrave_side, "height_mm": round(g["height"], 4),
                              "depth_mm": self.engrave_depth_mm, "font": self.font or engrave.DEFAULT_FONT}
        return d

    @property
    def spec_id(self) -> str:
        return runs.spec_id(self.design())

    @property
    def stem(self) -> str:
        """ring_<profile>_<features>_<size>_w<width>_t<thickness>_<spec id>: distinct for every
        design (a different text or groove depth changes the spec id)."""
        b = self.band
        return f"ring_{b.profile}_{self.features_tag}_{self.label}_w{b.width_mm:g}_t{b.thickness_mm:g}_{self.spec_id}"

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
        if self.has_engraving:
            exp["wall_ray_filter"] = self.wall_ray_filter()      # no rib-measuring axial rays inside the text
        exp.update({"expect_outer": outer, "expect_width": width})
        return exp

    def _text_span(self):
        """(half height + margin, half angle + margin) of the engraving, centred on +X / z = 0."""
        g = self.engrave_geometry()
        arc = float(self.engraving_info.get("arc_length_mm") or 0.0)
        if not arc:
            shape = engrave.text_polygons(self.text, g["height"], self.font)
            arc = float(shape.bounds[2] - shape.bounds[0])
        return g["height"] / 2 + 0.1, arc / 2 / g["wrap_radius"] + 0.1

    def _depth_below_surface(self, points, side: str):
        """How far below the engraved surface each point lies (positive = into the metal)."""
        import numpy as np
        z = points[:, 2]
        r = np.hypot(points[:, 0], points[:, 1])
        if side == "inside":
            return r - np.array([self.band.bore_radius_at(float(zz)) for zz in z])
        return np.array([self.band.outer_radius_at(float(zz)) for zz in z]) - r

    def wall_ray_filter(self):
        """For the thickness check: inside the text span keep only radial rays. An axial ray
        off a letter's top or bottom wall crosses the rib to the next stroke (0.1-0.4 mm of
        relief on solid metal) and would be read as a thin wall; the radial rays from the
        pocket floor still measure the wall left under the engraving, which is the real
        question there."""
        import numpy as np
        if not self.has_engraving:
            return None
        half_h, half_a = self._text_span()

        def keep(points, normals):
            z = points[:, 2]
            theta = np.arctan2(points[:, 1], points[:, 0])
            in_span = (np.abs(z) <= half_h) & (np.abs(theta) <= half_a)
            radial = points.copy()
            radial[:, 2] = 0.0
            radial /= np.maximum(np.linalg.norm(radial, axis=1), 1e-9)[:, None]
            is_radial = np.abs(np.einsum("ij,ij->i", normals, radial)) >= 0.5
            return ~in_span | is_radial
        return keep

    def engraving_pocket(self, mesh, samples: int = 40000) -> dict:
        """Is the text cut where the design put it? Samples the surface and measures the area
        lying 0.08..depth+0.08 mm below the engraved surface within the text's height and
        angular span (centred on +X): the pocket's floor and walls. Found when that area is at
        least half the text's own area (the floor alone would be the text area). The same
        band of radii elsewhere round the ring must be empty. Area, not vertex count, so a
        coarse exact mesh and nTop's dense marching-cubes mesh are judged alike."""
        import numpy as np
        import trimesh
        if not self.has_engraving:
            return {"checked": False}
        g = self.engrave_geometry()
        half_h, half_a = self._text_span()
        pts, _ = trimesh.sample.sample_surface(mesh, samples, seed=np.random.default_rng(3))
        per_point = float(mesh.area) / samples
        z = pts[:, 2]
        theta = np.arctan2(pts[:, 1], pts[:, 0])
        lo, hi = 0.08, self.engrave_depth_mm + 0.08
        in_span = (np.abs(z) <= half_h) & (np.abs(theta) <= half_a)
        elsewhere = (np.abs(z) <= half_h - 0.1) & (np.abs(theta) > half_a + 0.4)
        d1 = self._depth_below_surface(pts[in_span], g["side"]) if in_span.any() else np.array([])
        d2 = self._depth_below_surface(pts[elsewhere], g["side"]) if elsewhere.any() else np.array([])
        pocket_area = float(((d1 > lo) & (d1 < hi)).sum()) * per_point
        stray_area = float(((d2 > lo) & (d2 < hi)).sum()) * per_point
        text_area = float(self.engraving_info.get("cut_volume_mm3") or 0.0) / self.engrave_depth_mm
        if not text_area:
            text_area = float(engrave.text_polygons(self.text, g["height"], self.font).area)
        v = mesh.vertices
        vz, vr, vt = v[:, 2], np.hypot(v[:, 0], v[:, 1]), np.arctan2(v[:, 1], v[:, 0])
        vsel = (np.abs(vz) <= half_h) & (np.abs(vt) <= half_a)
        vd = self._depth_below_surface(v[vsel], g["side"]) if vsel.any() else np.array([])
        return {"checked": True, "side": g["side"], "text_area_mm2": round(text_area, 3),
                "pocket_area_mm2": round(pocket_area, 3), "stray_area_mm2": round(stray_area, 3),
                "pocket_vertices": int(((vd > lo) & (vd < hi)).sum()) if vd.size else 0,
                "found": pocket_area >= 0.5 * text_area and stray_area <= 0.2 * text_area}

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
    run_dir: Path | None = None
    run_id: str = ""
    delivered: Path | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        """PASSED / FAILED / INCOMPLETE: the nTop run and every hard gate check."""
        return runs.status_of(self.run.ok, self.gate)

    @property
    def ok(self) -> bool:
        return self.status == gate.PASSED

    def text(self) -> str:
        lines = [self.spec.describe(), self.run.summary(), self.gate.text(),
                 f"  status: {self.status.upper()}  run {self.run_dir}"]
        if self.delivered:
            lines.append(f"  delivered to {self.delivered}")
        lines += [f"  note: {n}" for n in self.notes]
        return "\n".join(lines)


def check_mesh(spec: RingSpec, stl: Path, ntop_vol: float | None, info: dict) -> tuple[gate.GateReport, list[str]]:
    """The mesh gate with this ring's expectations plus the two checks only the builder can
    add: `engraving` (the pocket is really there) and `design volume` (nTop against the
    independent design arithmetic; INCOMPLETE when nTop reported no volume). Shared by the
    nTopCL run and the GUI preview."""
    rep = gate.check(stl, expect_volume=ntop_vol, **spec.gate_expectations())
    notes = []
    if spec.has_engraving:
        pocket = spec.engraving_pocket(gate.load_mesh(stl))
        rep.checks.append(gate.Check("engraving", pocket["found"],
                                     f"{pocket['pocket_area_mm2']:.1f} mm² of pocket on the {pocket['side']} for "
                                     f"{pocket['text_area_mm2']:.1f} mm² of text ({pocket['pocket_vertices']} vertices)"
                                     + (f"; {pocket['stray_area_mm2']:.1f} mm² stray" if pocket["stray_area_mm2"] > 0.05 else "")
                                     + ("" if pocket["found"] else " - the text did not cut (wrong side, units or wrap length?)")))
        notes.append(f"engraving {spec.text!r} on the {spec.engrave_side}: {info['arc_length_mm']:.1f} mm long, "
                     f"thinnest stroke {info['stroke_mm']:.2f} mm, cut volume ~{info['cut_volume_mm3']:.1f} mm³")
    tol = 3.0 if (spec.milgrain or spec.has_engraving) else 2.0
    rep.checks.append(design_volume_check(spec.design_volume_mm3(), ntop_vol, tol))
    return rep, notes


def build(spec: RingSpec, out_dir: Path | None = None, *, notebook: Path | None = None,
          catalog_name: str = "ring_features", deliver: bool = False, deliver_project: str = "Rings") -> RingResult:
    problems = spec.validate()
    if problems:
        raise ValueError("; ".join(problems))
    cat = catalog.load(catalog_name)
    nb = Path(notebook) if notebook else cat.notebook
    out_dir = Path(out_dir) if out_dir else config.out_dir() / "ring"
    stem = spec.stem
    run_dir, run_id = runs.fresh_run_dir(out_dir, stem)      # nothing from an earlier run can be mistaken for this one
    stl = run_dir / f"{stem}.stl"
    engraving = run_dir / f"{stem}.engraving.stl"
    info = spec.write_engraving(engraving)

    inputs = cat.build_inputs(spec.notebook_inputs(str(stl), str(engraving)))
    started = time.time()
    run = ntopcl.run(nb, inputs, run_dir, tag=stem)
    try:
        runs.require_fresh(stl, started, "the exported mesh")
    except FileNotFoundError as e:
        raise ntopcl.NtopclError(f"notebook reported success but {e}", run) from e

    vol_entry = run.outputs.get(cat.output.get("name", "Volume"))
    ntop_vol = ntopcl.scalar_value(vol_entry) if vol_entry else None
    rep, notes = check_mesh(spec, stl, ntop_vol, info)
    result = RingResult(spec, stl, run, rep, ntop_vol, run_dir, run_id)
    result.notes += spec.band.warnings() + notes

    report = {
        "stem": stem, "spec_id": spec.spec_id, "run_id": run_id, "status": result.status, "ok": result.ok,
        "band": spec.band.__dict__, "features": {k: v for k, v in spec.__dict__.items() if k not in ("band", "engraving_info")},
        "design": spec.design(), "engraving": info, "inputs": spec.notebook_inputs(str(stl), str(engraving)), "stl": str(stl),
        "ntop_volume_mm3": ntop_vol, "design_volume_mm3": spec.design_volume_mm3(), "gate": rep.to_dict(),
        "ntopcl_seconds": run.seconds, "block_timings": [t.__dict__ for t in run.log.timings], "notes": result.notes,
        "notebook": runs.notebook_identity(nb), "environment": runs.environment(ntopcl.version()),
    }
    (run_dir / f"{stem}.report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    if deliver and result.ok:
        result.delivered = runs.deliver(stl, run_dir, stem, deliver_project, report, extra_files=[engraving])
    elif deliver:
        result.notes.append(f"not delivered: status {result.status}")
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
