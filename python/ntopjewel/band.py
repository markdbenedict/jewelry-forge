"""The band family.

Phase 0: `ring_band.ntop`, a flat band from two cylinders (catalog `ring_band`).
Phase 1: `ring_band_profile.ntop`, the same band shaped by two tori and an edge round
(catalog `ring_band_profile`), giving the classic cross-sections:

    flat          square section, barely rounded edges
    comfort-flat  flat outside, barrel bore, rounded edges
    court         domed outside, barrel bore (the classic comfortable band)
    d-shape       strong dome outside, flat bore
    half-round    outside close to a semicircle, flat bore

Python owns everything that is not geometry construction: size -> millimetres, the torus
arithmetic, file naming, gate expectations, the report. The notebook only sees numbers:

    bore r_i, outer r_o = r_i + T, z = ±W/2
    dome torus:    tube ρ_d = (W²/4 + d²) / (2d),  ring radius R_d = r_o - ρ_d   (intersect)
    comfort torus: tube ρ_c = (W²/4 + c²) / (2c),  ring radius R_c = r_i + ρ_c   (subtract)
    edge round:    Offset Body by -e then +e (an opening) rounds every edge with radius e
"""
from __future__ import annotations

import json
import math
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import catalog, config, gate, ntopcl, tables

# dome / comfort as a fraction of thickness unless given as "abs"; edge round absolute (mm)
PROFILES: dict[str, dict] = {
    "flat":         dict(dome_abs=0.02, comfort_abs=0.02, edge=0.10),
    "comfort-flat": dict(dome_abs=0.02, comfort_frac=0.22, edge=0.20),
    "court":        dict(dome_frac=0.25, comfort_frac=0.22, edge=0.25),
    "d-shape":      dict(dome_frac=0.40, comfort_abs=0.05, edge=0.20),
    "half-round":   dict(dome_frac=0.55, comfort_abs=0.05, edge=0.20),
}
MIN_SAGITTA = 0.02          # a 0.02 mm "dome" is flat to the eye and keeps the torus formula finite
MIN_EDGE_THICKNESS = 0.45   # band edge (T - dome - comfort) must stay at least this thick


@dataclass
class BandSpec:
    size: float | str = 6
    system: str = "US"
    width_mm: float = 4.0
    thickness_mm: float = 1.3          # radial, at the band's mid-plane
    profile: str = "court"
    dome_mm: float | None = None       # outer drop from mid-plane to edge; None = from profile
    comfort_mm: float | None = None    # bore relief at the edges; None = from profile
    edge_round_mm: float | None = None # radius rounded onto every edge; None = from profile
    allowance_mm: float = 0.0          # added to the inner diameter (print/cast calibration)
    mesh_tolerance_mm: float = 0.1     # nTop: 2 x voxel size; 0.1 mm = 50 µm voxels

    # ---- derived millimetres -------------------------------------------------------
    @property
    def inner_diameter_mm(self) -> float:
        return tables.inner_diameter_mm(self.size, self.system) + self.allowance_mm

    @property
    def bore_radius_mm(self) -> float:
        return self.inner_diameter_mm / 2.0

    @property
    def outer_radius_mm(self) -> float:
        return self.bore_radius_mm + self.thickness_mm

    def _preset(self) -> dict:
        if self.profile not in PROFILES:
            raise ValueError(f"unknown profile {self.profile!r}; one of {', '.join(PROFILES)}")
        return PROFILES[self.profile]

    @property
    def dome(self) -> float:
        if self.dome_mm is not None:
            return max(MIN_SAGITTA, float(self.dome_mm))
        p = self._preset()
        return max(MIN_SAGITTA, p.get("dome_abs", p.get("dome_frac", 0.0) * self.thickness_mm))

    @property
    def comfort(self) -> float:
        if self.comfort_mm is not None:
            return max(MIN_SAGITTA, float(self.comfort_mm))
        p = self._preset()
        return max(MIN_SAGITTA, p.get("comfort_abs", p.get("comfort_frac", 0.0) * self.thickness_mm))

    @property
    def edge_round(self) -> float:
        return float(self.edge_round_mm) if self.edge_round_mm is not None else self._preset()["edge"]

    @property
    def edge_thickness_mm(self) -> float:
        """Radial thickness at the band's edges (before edge rounding)."""
        return self.thickness_mm - self.dome - self.comfort

    @property
    def dome_torus(self) -> tuple[float, float]:
        """(ring radius R_d, tube radius ρ_d) of the torus whose outer surface is the dome.

        A flat outside (dome <= MIN_SAGITTA) is a torus centred ON the outer surface and big
        enough to swallow the whole section, so the intersect removes nothing and every
        radius stays positive.
        """
        if self.dome <= MIN_SAGITTA:
            rho = math.hypot(self.thickness_mm, self.width_mm / 2) + 0.5
            return self.outer_radius_mm, rho
        rho, _ = tables.torus_for_sagitta(self.width_mm, self.dome)
        return self.outer_radius_mm - rho, rho

    @property
    def comfort_torus(self) -> tuple[float, float]:
        """(ring radius R_c, tube radius ρ_c) of the torus the band is INTERSECTED with to
        make the barrel bore: its tube circle is centred outside the bore at r_i + ρ_c, so
        its inner side touches the bore at the mid-plane and stands `c` further out at the
        edges. (Subtracting this torus removes the band instead - seen 2026-10-26.)

        No relief (comfort <= MIN_SAGITTA) is a torus centred ON the bore and big enough to
        swallow the whole section, so the intersect removes nothing.
        """
        if self.comfort <= MIN_SAGITTA:
            rho = math.hypot(self.thickness_mm, self.width_mm / 2) + 0.5
            return self.bore_radius_mm, rho
        rho, _ = tables.torus_for_sagitta(self.width_mm, self.comfort)
        return self.bore_radius_mm + rho, rho

    def section_mask(self, r, z):
        """True where (r, z) lies in the designed cross-section before edge rounding:
        band ∩ dome torus ∩ comfort torus. Pure arithmetic; used by the tests and the gate."""
        rd, td = self.dome_torus
        rc, tc = self.comfort_torus
        in_band = (r >= self.bore_radius_mm) & (r <= self.outer_radius_mm) & (abs(z) <= self.width_mm / 2)
        in_dome = (r - rd) ** 2 + z ** 2 <= td ** 2
        in_comfort = (r - rc) ** 2 + z ** 2 <= tc ** 2
        return in_band & in_dome & in_comfort

    def design_volume_mm3(self, step: float = 0.005) -> float:
        """Volume the notebook should produce, from the design alone: the section (band ∩ both
        tori) opened by the edge round - offsetting a body of revolution in 3D is the 2D offset
        of its meridian section - then Pappus: V = 2π ∫∫ r dA. Agrees with nTop to < 1 %."""
        import numpy as np
        from scipy import ndimage
        pad = self.edge_round + 0.2
        r = np.arange(self.bore_radius_mm - pad, self.outer_radius_mm + pad, step)
        z = np.arange(-self.width_mm / 2 - pad, self.width_mm / 2 + pad, step)
        R, Z = np.meshgrid(r, z)
        mask = self.section_mask(R, Z)
        if self.edge_round > 0:
            # pixel centres sit half a step inside the true edge: edt == 1 at the first inside pixel
            px = self.edge_round / step + 0.5
            eroded = ndimage.distance_transform_edt(mask) >= px
            mask = ndimage.distance_transform_edt(~eroded) <= px
        return float(2 * math.pi * (R[mask] * step * step).sum())

    @property
    def label(self) -> str:
        return tables.size_label(self.size, self.system)

    @property
    def stem(self) -> str:
        return f"ring_band_{self.profile}_{self.label}"

    def notebook_inputs(self, output_path: str) -> dict:
        """Values for every input of ring_band_profile.ntop (names must match the catalog)."""
        rd, td = self.dome_torus
        rc, tc = self.comfort_torus
        return {
            "Outer Radius": round(self.outer_radius_mm, 4),
            "Bore Radius": round(self.bore_radius_mm, 4),
            "Z Top": round(self.width_mm / 2, 4),
            "Z Bottom": round(-self.width_mm / 2, 4),
            "Dome Ring Radius": round(rd, 4),
            "Dome Tube Radius": round(td, 4),
            "Comfort Ring Radius": round(rc, 4),
            "Comfort Tube Radius": round(tc, 4),
            "Edge Round": round(self.edge_round, 4),
            "Edge Round Inward": round(-self.edge_round, 4),
            "Mesh Tolerance": self.mesh_tolerance_mm,
            "Output Path": output_path,
        }

    def validate(self) -> list[str]:
        problems = []
        if self.thickness_mm < tables.FLOORS["band_min_thickness"]:
            problems.append(f"thickness {self.thickness_mm} mm below floor {tables.FLOORS['band_min_thickness']} mm")
        if self.width_mm < tables.FLOORS["band_min_width"]:
            problems.append(f"width {self.width_mm} mm below floor {tables.FLOORS['band_min_width']} mm")
        if not 10.0 <= self.inner_diameter_mm <= 25.0:
            problems.append(f"inner diameter {self.inner_diameter_mm:.2f} mm is outside 10..25 mm")
        try:
            self._preset()
        except ValueError as e:
            return problems + [str(e)]
        if self.edge_thickness_mm < MIN_EDGE_THICKNESS:
            problems.append(f"band edge would be {self.edge_thickness_mm:.2f} mm thick (thickness {self.thickness_mm} "
                            f"- dome {self.dome:.2f} - comfort {self.comfort:.2f}); need >= {MIN_EDGE_THICKNESS} mm: "
                            f"use a thicker band or a flatter profile")
        if 2 * self.edge_round > self.edge_thickness_mm - 0.1:
            problems.append(f"edge round {self.edge_round} mm too large for a {self.edge_thickness_mm:.2f} mm edge "
                            f"(needs 2 x round + 0.1 mm)")
        if self.edge_round > self.width_mm / 4:
            problems.append(f"edge round {self.edge_round} mm too large for a {self.width_mm} mm wide band")
        return problems

    def warnings(self) -> list[str]:
        w = []
        if self.dome > MIN_SAGITTA and self.dome_torus[0] <= 0:
            w.append(f"dome torus ring radius {self.dome_torus[0]:.2f} mm <= 0 (shallow dome on a wide band): "
                     f"nTop may reject it; if the run fails, raise --dome or narrow the band")
        return w

    def describe(self) -> str:
        rd, td = self.dome_torus
        rc, tc = self.comfort_torus
        return (f"{self.stem}: inner Ø {self.inner_diameter_mm:.3f}  bore r {self.bore_radius_mm:.3f}  "
                f"outer r {self.outer_radius_mm:.3f}  width {self.width_mm}  thickness {self.thickness_mm}\n"
                f"  profile {self.profile}: dome {self.dome:.3f}  comfort {self.comfort:.3f}  "
                f"edge round {self.edge_round:.2f}  edge thickness {self.edge_thickness_mm:.3f}\n"
                f"  dome torus R {rd:.3f} / tube {td:.3f}   comfort torus R {rc:.3f} / tube {tc:.3f}   "
                f"tolerance {self.mesh_tolerance_mm}")


@dataclass
class BandResult:
    spec: BandSpec
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
        s = self.spec
        head = (f"Band {s.label} {s.profile}: inner Ø {s.inner_diameter_mm:.3f} mm, width {s.width_mm} mm, "
                f"thickness {s.thickness_mm} mm (edge {s.edge_thickness_mm:.2f}) -> {self.stl.name}")
        lines = [head, self.run.summary(), self.gate.text()]
        if self.delivered:
            lines.append(f"  delivered to {self.delivered}")
        lines += [f"  note: {n}" for n in self.notes]
        return "\n".join(lines)


def build(spec: BandSpec, out_dir: Path | None = None, *, notebook: Path | None = None,
          catalog_name: str = "ring_band_profile", deliver: bool = False, deliver_project: str = "Bands",
          wall_floor: float | None = None) -> BandResult:
    problems = spec.validate()
    if problems:
        raise ValueError("; ".join(problems))
    cat = catalog.load(catalog_name)
    nb = Path(notebook) if notebook else cat.notebook
    out_dir = Path(out_dir) if out_dir else config.out_dir() / "band"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = spec.stem
    stl = (out_dir / f"{stem}.stl").resolve()

    inputs = cat.build_inputs(spec.notebook_inputs(str(stl)))
    run = ntopcl.run(nb, inputs, out_dir, tag=stem)
    if not stl.exists():
        exported = any("export" in t.block.lower() for t in run.log.timings)
        why = ("the Export Mesh block's file input is not wired to the Output Path chip" if exported else
               "no Export block ran (none appears in the log): add an Export Mesh block with the mesh in its "
               "Mesh input and the Output Path chip in its file input")
        raise ntopcl.NtopclError(f"notebook reported success but {stl} was not written; {why}", run)

    vol_entry = run.outputs.get(cat.output.get("name", "Volume"))
    ntop_vol = ntopcl.scalar_value(vol_entry) if vol_entry else None
    # a band's edge is a wedge into solid metal, not a free-standing wall: the floor for the
    # ray-cast thickness check is the smaller of the material floor and the designed edge
    floor = tables.FLOORS["wall_marginal"] if wall_floor is None else wall_floor
    floor = min(floor, 0.8 * spec.edge_thickness_mm)
    rep = gate.check(stl, expect_inner=spec.inner_diameter_mm, expect_outer=2 * spec.outer_radius_mm,
                     expect_width=spec.width_mm, expect_volume=ntop_vol, wall_floor=floor)
    result = BandResult(spec, stl, run, rep, ntop_vol)
    result.notes += spec.warnings()
    if ntop_vol is None:
        result.notes.append("nTop volume output not found in out.json; volume not cross-checked.")
    else:
        design = spec.design_volume_mm3()
        dev = (ntop_vol - design) / design * 100
        verdict = "matches the design" if abs(dev) <= 2.0 else "DIFFERS from the design - check the notebook"
        result.notes.append(f"nTop volume {ntop_vol:.2f} mm³ vs design {design:.2f} mm³ ({dev:+.2f} %): {verdict}")

    if deliver and result.ok:
        dest = config.deliver_dir() / deliver_project
        dest.mkdir(parents=True, exist_ok=True)
        result.delivered = Path(shutil.copy2(stl, dest / stl.name))

    (out_dir / f"{stem}.report.json").write_text(json.dumps({
        "spec": spec.__dict__, "inputs": spec.notebook_inputs(str(stl)), "stl": str(stl), "ok": result.ok,
        "ntop_volume_mm3": ntop_vol, "gate": rep.to_dict(), "ntopcl_seconds": run.seconds,
        "block_timings": [t.__dict__ for t in run.log.timings], "notes": result.notes,
    }, indent=2), encoding="utf-8")
    return result
