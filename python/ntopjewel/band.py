"""The band family. Phase 0: flat band from `ring_band.ntop` (two cylinders).

Python owns everything that is not geometry construction: size -> millimetres, file
naming, expectations for the gate, the report. The notebook only sees radii and widths.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import catalog, config, gate, ntopcl, tables


@dataclass
class BandSpec:
    size: float | str = 6
    system: str = "US"
    width_mm: float = 4.0
    thickness_mm: float = 1.3
    allowance_mm: float = 0.0        # added to the inner diameter (print/cast calibration)
    mesh_tolerance_mm: float = 0.1       # nTop: 2 x voxel size; 0.1 mm = 50 µm voxels

    @property
    def inner_diameter_mm(self) -> float:
        return tables.inner_diameter_mm(self.size, self.system) + self.allowance_mm

    @property
    def bore_radius_mm(self) -> float:
        return self.inner_diameter_mm / 2.0

    @property
    def outer_radius_mm(self) -> float:
        return self.bore_radius_mm + self.thickness_mm

    @property
    def label(self) -> str:
        return tables.size_label(self.size, self.system)

    def validate(self) -> list[str]:
        problems = []
        if self.thickness_mm < tables.FLOORS["band_min_thickness"]:
            problems.append(f"thickness {self.thickness_mm} mm below floor {tables.FLOORS['band_min_thickness']} mm")
        if self.width_mm < tables.FLOORS["band_min_width"]:
            problems.append(f"width {self.width_mm} mm below floor {tables.FLOORS['band_min_width']} mm")
        if not 10.0 <= self.inner_diameter_mm <= 25.0:
            problems.append(f"inner diameter {self.inner_diameter_mm:.2f} mm is outside 10..25 mm")
        return problems


@dataclass
class BandResult:
    spec: BandSpec
    stl: Path
    run: ntopcl.RunResult
    gate: gate.GateReport
    ntop_volume_mm3: float | None
    analytic_volume_mm3: float
    delivered: Path | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.run.ok and self.gate.passed

    def text(self) -> str:
        s = self.spec
        head = (f"Band {s.label}: inner Ø {s.inner_diameter_mm:.3f} mm, width {s.width_mm} mm, "
                f"thickness {s.thickness_mm} mm -> {self.stl.name}")
        lines = [head, self.run.summary(), self.gate.text()]
        if self.ntop_volume_mm3 is not None:
            lines.append(f"  nTop volume {self.ntop_volume_mm3:.2f} mm³; analytic flat-band volume {self.analytic_volume_mm3:.2f} mm³")
        if self.delivered:
            lines.append(f"  delivered to {self.delivered}")
        lines += [f"  note: {n}" for n in self.notes]
        return "\n".join(lines)


def build(spec: BandSpec, out_dir: Path | None = None, *, notebook: Path | None = None,
          catalog_name: str = "ring_band", deliver: bool = False, deliver_project: str = "Bands",
          wall_floor: float | None = None) -> BandResult:
    problems = spec.validate()
    if problems:
        raise ValueError("; ".join(problems))
    cat = catalog.load(catalog_name)
    nb = Path(notebook) if notebook else cat.notebook
    out_dir = Path(out_dir) if out_dir else config.out_dir() / "band"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"ring_band_{spec.label}"
    stl = (out_dir / f"{stem}.stl").resolve()

    inputs = cat.build_inputs({
        "Outer Radius": spec.outer_radius_mm,
        "Bore Radius": spec.bore_radius_mm,
        "Width": spec.width_mm,
        "Mesh Tolerance": spec.mesh_tolerance_mm,
        "Output Path": str(stl),
    })
    run = ntopcl.run(nb, inputs, out_dir, tag=stem)
    if not stl.exists():
        exported = any("export" in t.block.lower() for t in run.log.timings)
        why = ("the Export Mesh block's file input is not wired to the Output Path chip" if exported else
               "no Export block ran (none appears in the log): add an Export Mesh block with the mesh in its "
               "Mesh input and the Output Path chip in its file input")
        raise ntopcl.NtopclError(f"notebook reported success but {stl} was not written; {why}", run)

    vol_entry = run.outputs.get(cat.output.get("name", "Volume"))
    ntop_vol = ntopcl.scalar_value(vol_entry) if vol_entry else None
    analytic = gate.band_volume_mm3(spec.inner_diameter_mm, 2 * spec.outer_radius_mm, spec.width_mm)
    rep = gate.check(stl, expect_inner=spec.inner_diameter_mm, expect_outer=2 * spec.outer_radius_mm,
                     expect_width=spec.width_mm, expect_volume=ntop_vol or analytic,
                     wall_floor=tables.FLOORS["wall_marginal"] if wall_floor is None else wall_floor)
    result = BandResult(spec, stl, run, rep, ntop_vol, analytic)
    if ntop_vol is None:
        result.notes.append("nTop volume output not found in out.json; gate compared against the analytic volume. "
                            "Send the output JSON so scalar parsing can be confirmed.")

    if deliver and result.ok:
        dest = config.deliver_dir() / deliver_project
        dest.mkdir(parents=True, exist_ok=True)
        result.delivered = Path(shutil.copy2(stl, dest / stl.name))

    (out_dir / f"{stem}.report.json").write_text(json.dumps({
        "spec": spec.__dict__, "stl": str(stl), "ok": result.ok, "ntop_volume_mm3": ntop_vol,
        "analytic_volume_mm3": analytic, "gate": rep.to_dict(), "ntopcl_seconds": run.seconds,
        "block_timings": [t.__dict__ for t in run.log.timings], "notes": result.notes,
    }, indent=2), encoding="utf-8")
    return result
