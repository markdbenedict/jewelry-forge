"""Stones: parametric gem bodies as exact meshes, for seats, cutters and weights.

A stone here is the solid a setting is built around, not a faceted render: girdle outline,
crown (girdle top to table), girdle band, pavilion (girdle bottom to culet). Facets do not
change where metal goes. Python writes the stone as a watertight STL (like the engraving
text); nTop imports it (Import Mesh -> Implicit from Mesh) wherever a setting needs it, so
one code path serves every shape and every stone is checked offline against its exact
volume and dimensions.

    coordinates: X along the stone's length, Y across, Z up; table on top (+Z), culet at
    the bottom, the girdle's mid-plane at z = 0, the outline centred on its bounding box

Shapes: round, oval, pear (point toward -X), marquise, cushion, emerald (step-cut octagon),
each from length x width (round: diameter). Proportions default to an ideal round's (table
57 %, crown 15 %, girdle 3 %, pavilion 43 % of the width); give a total depth (a calipered
stone) and crown and pavilion scale to fit it, girdle unchanged.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import tables

SHAPES = ("round", "oval", "pear", "marquise", "cushion", "emerald")
# fractions of the stone's WIDTH (the round's diameter)
TABLE_FRAC = {"round": 0.57, "oval": 0.57, "pear": 0.55, "marquise": 0.55, "cushion": 0.60, "emerald": 0.65}
CROWN_FRAC, GIRDLE_FRAC, PAVILION_FRAC = 0.15, 0.03, 0.43
MIN_GIRDLE_MM = 0.10
OUTLINE_POINTS = 256


@dataclass
class StoneSpec:
    shape: str = "round"
    length_mm: float = 6.5            # round: the diameter (width is ignored)
    width_mm: float | None = None
    depth_mm: float | None = None     # total height table to culet; None = ideal proportions
    table_frac: float | None = None
    girdle_mm: float | None = None
    material: str = tables.DEFAULT_STONE

    # ---- dimensions ------------------------------------------------------------------
    @property
    def length(self) -> float:
        return float(self.length_mm)

    @property
    def width(self) -> float:
        return float(self.length_mm if self.shape == "round" or self.width_mm is None else self.width_mm)

    @property
    def girdle(self) -> float:
        return max(MIN_GIRDLE_MM, float(self.girdle_mm) if self.girdle_mm is not None else GIRDLE_FRAC * self.width)

    @property
    def heights(self) -> tuple[float, float]:
        """(crown height, pavilion depth) in mm; scaled to the total depth when one is given."""
        crown, pav = CROWN_FRAC * self.width, PAVILION_FRAC * self.width
        if self.depth_mm is not None:
            k = (float(self.depth_mm) - self.girdle) / (crown + pav)
            crown, pav = crown * k, pav * k
        return crown, pav

    @property
    def depth(self) -> float:
        c, p = self.heights
        return c + self.girdle + p

    @property
    def table(self) -> float:
        return float(self.table_frac) if self.table_frac is not None else TABLE_FRAC[self.shape]

    @property
    def stem(self) -> str:
        dims = f"{self.length:g}" if self.shape == "round" else f"{self.length:g}x{self.width:g}"
        return f"stone_{self.shape}_{dims}x{self.depth:.2f}".replace(".", "p")

    # ---- outline -------------------------------------------------------------------------
    def outline(self, n: int = OUTLINE_POINTS):
        """Girdle outline as an (n, 2) array, counter-clockwise, centred on its bounding box."""
        import numpy as np
        L, W = self.length, self.width
        t = np.linspace(0, 2 * math.pi, n, endpoint=False)
        if self.shape in ("round", "oval"):
            xy = np.column_stack([L / 2 * np.cos(t), W / 2 * np.sin(t)])
        elif self.shape == "cushion":            # superellipse: a rounded rectangle
            e = 2 / 4.0
            c, s = np.cos(t), np.sin(t)
            xy = np.column_stack([L / 2 * np.sign(c) * np.abs(c) ** e, W / 2 * np.sign(s) * np.abs(s) ** e])
        elif self.shape == "emerald":            # rectangle with the corners cut at 45 deg
            cut = 0.18 * W
            hx, hy = L / 2, W / 2
            corners = [(hx, -hy + cut), (hx, hy - cut), (hx - cut, hy), (-hx + cut, hy), (-hx, hy - cut),
                       (-hx, -hy + cut), (-hx + cut, -hy), (hx - cut, -hy)]
            xy = _resample(np.array(corners), n)
        elif self.shape in ("pear", "marquise"):
            xy = _pear_or_marquise(L, W, n, self.shape == "marquise")
        else:
            raise ValueError(f"unknown shape {self.shape!r}; one of {', '.join(SHAPES)}")
        lo, hi = xy.min(axis=0), xy.max(axis=0)
        return xy - (lo + hi) / 2

    # ---- solid ---------------------------------------------------------------------------
    def mesh(self):
        """Watertight trimesh: table cap, crown, girdle band, pavilion to a culet point.

        The table and pavilion are fans from the centre, valid only for a CONVEX outline (all
        six shapes are). A concave cut (heart, a trillion with indented sides) must switch to
        polygon triangulation and a keel/culet model first; until then it is refused here
        rather than meshed into self-intersecting triangles (review 2026-10-28)."""
        import numpy as np
        import trimesh
        xy = self.outline()
        if not _is_convex(xy):
            raise ValueError(f"{self.shape} outline is not convex: the fan-triangulated table/pavilion would self-intersect")
        n = len(xy)
        crown, pav = self.heights
        g = self.girdle
        rings = [(xy * self.table, g / 2 + crown), (xy, g / 2), (xy, -g / 2)]
        verts = [np.column_stack([r, np.full(n, z)]) for r, z in rings]
        V = np.vstack(verts + [np.array([[0.0, 0.0, g / 2 + crown]]), np.array([[0.0, 0.0, -g / 2 - pav]])])
        top, bottom = 3 * n, 3 * n + 1
        F = []
        for k in range(2):                                          # crown and girdle band
            a, b = k * n, (k + 1) * n
            for i in range(n):
                j = (i + 1) % n
                F += [[a + i, b + i, b + j], [a + i, b + j, a + j]]
        for i in range(n):
            j = (i + 1) % n
            F.append([top, i, j])                                   # table fan
            F.append([bottom, 2 * n + j, 2 * n + i])                # pavilion to the culet
        m = trimesh.Trimesh(V, np.array(F), process=True)
        if m.volume < 0:
            m.invert()
        trimesh.repair.fix_normals(m)
        return m

    def volume_mm3(self) -> float:
        return float(self.mesh().volume)

    def carats(self, material: str | None = None) -> float:
        return tables.carats(self.volume_mm3(), material or self.material)

    def validate(self) -> list[str]:
        p = []
        if self.shape not in SHAPES:
            p.append(f"unknown shape {self.shape!r}; one of {', '.join(SHAPES)}")
            return p
        if self.width > self.length + 1e-9 and self.shape != "round":
            p.append("length is the long side: swap length and width")
        if self.depth_mm is not None and float(self.depth_mm) <= self.girdle + 0.2:
            p.append(f"depth {self.depth_mm} mm leaves no crown or pavilion")
        if not 0.3 <= self.table <= 0.8:
            p.append(f"table {self.table:.0%} is outside 30-80 %")
        if self.material not in tables.STONE_DENSITY_G_CM3:
            p.append(f"unknown stone material {self.material!r}; one of {', '.join(tables.STONE_DENSITY_G_CM3)}")
        return p

    def describe(self) -> str:
        crown, pav = self.heights
        return (f"{self.stem}: {self.shape} {self.length:g} x {self.width:g} mm, depth {self.depth:.2f} mm "
                f"(crown {crown:.2f}, girdle {self.girdle:.2f}, pavilion {pav:.2f}), table {self.table:.0%}; "
                f"volume {self.volume_mm3():.2f} mm³ = {self.carats():.2f} ct {self.material}")

    def write(self, out_dir: Path) -> dict:
        """<stem>.stl and <stem>.stone.json (spec, derived numbers, mesh checks)."""
        problems = self.validate()
        if problems:
            raise ValueError("; ".join(problems))
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        m = self.mesh()
        stl = out_dir / f"{self.stem}.stl"
        m.export(str(stl))
        crown, pav = self.heights
        info = {"spec": asdict(self), "stl": str(stl), "length_mm": self.length, "width_mm": self.width,
                "depth_mm": self.depth, "crown_mm": crown, "girdle_mm": self.girdle, "pavilion_mm": pav,
                "table_frac": self.table, "volume_mm3": float(m.volume), "carats": self.carats(),
                "extents_mm": [float(x) for x in m.extents], "watertight": bool(m.is_watertight)}
        (out_dir / f"{self.stem}.stone.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
        return info


def _is_convex(xy) -> bool:
    """Every turn of the closed outline has the same sign (collinear points allowed)."""
    import numpy as np
    a = np.roll(xy, -1, axis=0) - xy
    b = np.roll(xy, -2, axis=0) - np.roll(xy, -1, axis=0)
    cross = a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]
    tol = 1e-9 * float(np.abs(xy).max()) ** 2
    return bool(np.all(cross >= -tol) or np.all(cross <= tol))


def _resample(poly, n: int):
    """n points evenly spaced along a closed polygon."""
    import numpy as np
    closed = np.vstack([poly, poly[:1]])
    seg = np.linalg.norm(np.diff(closed, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)])
    s = np.linspace(0, cum[-1], n, endpoint=False)
    x = np.interp(s, cum, closed[:, 0])
    y = np.interp(s, cum, closed[:, 1])
    return np.column_stack([x, y])


def _pear_or_marquise(L: float, W: float, n: int, marquise: bool):
    """Pear: a semicircle of radius W/2 at +X tapering to a point at -X; the taper's half-width
    is r * sin(pi/2 * t) ** 0.9 (t = 0 at the point, 1 where it meets the circle), so the
    outline is convex, has no kink where the two meet and comes to a point. Marquise: the
    taper at both ends."""
    import numpy as np
    r = W / 2
    m = n // 2
    if marquise:
        x = np.linspace(-L / 2, L / 2, m + 1)
        t = 1 - np.abs(x) / (L / 2)
        y = r * np.sin(math.pi / 2 * t) ** 0.9
    else:
        c = L / 2 - r                                   # centre of the round end
        x = np.linspace(-L / 2, L / 2, m + 1)
        y = np.empty_like(x)
        taper = x <= c
        t = (x[taper] + L / 2) / (c + L / 2)
        y[taper] = r * np.sin(math.pi / 2 * t) ** 0.9
        y[~taper] = np.sqrt(np.maximum(r * r - (x[~taper] - c) ** 2, 0.0))
    upper = np.column_stack([x[::-1], y[::-1]])          # +X to -X across the top
    lower = np.column_stack([x[1:-1], -y[1:-1]])          # back along the bottom
    return _resample(np.vstack([upper, lower]), n)


# ---- seats: the cutter a setting subtracts -------------------------------------------------
def seat_envelope(spec: StoneSpec, drop_mm: float | None = None):
    """The stone plus a straight drop-in path: the girdle outline carried up to `drop_mm` above
    the girdle's mid-plane. Every stone here is convex, so this is the convex hull of the stone
    and the outline lifted to that height. Offset by the clearance (in nTop: the stone_seat
    block), it is what a head subtracts so the stone drops in from above and sits on its
    girdle with the clearance all round."""
    import numpy as np
    import trimesh
    drop = tables.SETTINGS["seat_drop_mm"] if drop_mm is None else float(drop_mm)
    stone = spec.mesh()
    crown, _ = spec.heights
    if drop <= spec.girdle / 2 + crown:
        raise ValueError(f"drop {drop} mm does not clear the table ({spec.girdle / 2 + crown:.2f} mm above the girdle)")
    xy = spec.outline()
    lifted = np.column_stack([xy, np.full(len(xy), drop)])
    return trimesh.convex.convex_hull(np.vstack([stone.vertices, lifted]))


def offset_volume_mm3(mesh, clearance_mm: float) -> float:
    """Volume of a CONVEX polyhedron offset outward by c, exactly (Steiner's formula):
    V + S c + M c^2 + 4/3 pi c^3, with M = 1/2 sum over edges of length x exterior dihedral
    angle. The independent figure nTop's offset seat is checked against."""
    import numpy as np
    c = float(clearance_mm)
    edges = mesh.vertices[mesh.face_adjacency_edges]
    lengths = np.linalg.norm(edges[:, 0] - edges[:, 1], axis=1)
    m = 0.5 * float(np.sum(lengths * mesh.face_adjacency_angles))
    return float(mesh.volume + mesh.area * c + m * c * c + 4.0 / 3.0 * math.pi * c ** 3)


@dataclass
class SeatSpec:
    stone: StoneSpec
    clearance_mm: float | None = None
    drop_mm: float | None = None
    mesh_tolerance_mm: float = 0.05     # small part: 25 µm voxels

    @property
    def clearance(self) -> float:
        return tables.SETTINGS["seat_clearance_mm"] if self.clearance_mm is None else float(self.clearance_mm)

    @property
    def drop(self) -> float:
        return tables.SETTINGS["seat_drop_mm"] if self.drop_mm is None else float(self.drop_mm)

    def envelope(self):
        return seat_envelope(self.stone, self.drop)

    def design(self) -> dict:
        return {"stone": asdict(self.stone), "clearance_mm": self.clearance, "drop_mm": self.drop,
                "mesh_tolerance_mm": self.mesh_tolerance_mm}

    @property
    def stem(self) -> str:
        from . import runs
        return f"seat_{self.stone.stem[len('stone_'):]}_c{self.clearance:g}_{runs.spec_id(self.design())}".replace(".", "p")

    def design_volume_mm3(self) -> float:
        return offset_volume_mm3(self.envelope(), self.clearance)

    def expected_extents(self) -> list[float]:
        _, pav = self.stone.heights
        c = self.clearance
        return [self.stone.length + 2 * c, self.stone.width + 2 * c, self.stone.girdle / 2 + pav + self.drop + 2 * c]

    def validate(self) -> list[str]:
        p = self.stone.validate()
        if not 0.0 <= self.clearance <= 0.5:
            p.append(f"clearance {self.clearance} mm outside 0..0.5 mm")
        if self.mesh_tolerance_mm > self.clearance * 4 and self.clearance > 0:
            p.append(f"mesh tolerance {self.mesh_tolerance_mm} mm is coarse for a {self.clearance} mm clearance")
        return p

    def notebook_inputs(self, seat_path: str, output_path: str) -> dict:
        return {"Seat Path": seat_path, "Clearance": round(self.clearance, 4),
                "Mesh Tolerance": self.mesh_tolerance_mm, "Output Path": output_path}

    def describe(self) -> str:
        e = self.envelope()
        return (f"{self.stem}: {self.stone.describe()}\n  seat: clearance {self.clearance} mm, drop-in path to "
                f"{self.drop} mm above the girdle; envelope {e.volume:.2f} mm³ -> seat {self.design_volume_mm3():.2f} mm³; "
                f"extents " + " x ".join(f"{x:.3f}" for x in self.expected_extents()) + " mm")


@dataclass
class SeatResult:
    spec: SeatSpec
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


def check_seat(spec: SeatSpec, stl: Path, ntop_vol: float | None):
    """Gate for a seat cutter: closed, one shell, nTop's volume against the mesh and against
    Steiner's exact offset volume, and the bounding box against the stone + clearance. No wall
    check: a cutter is not metal."""
    import numpy as np
    from . import band, gate
    rep = gate.check(stl, expect_volume=ntop_vol, wall_floor=0.0, wall_samples=0, tol_volume_pct=2.0)
    rep.checks = [c for c in rep.checks if c.name != "wall thickness"]
    ext = np.array(rep.extents_mm)
    want = np.array(spec.expected_extents())
    tol = max(0.05, spec.mesh_tolerance_mm)
    d = ext - want
    rep.checks.append(gate.Check("extents", bool(np.all(np.abs(d) <= tol)),
                                 "x".join(f"{x:.3f}" for x in ext) + " vs " + "x".join(f"{x:.3f}" for x in want)
                                 + " mm (Δ " + ", ".join(f"{x:+.3f}" for x in d) + f", tolerance ±{tol:g})"))
    rep.checks.append(band.design_volume_check(spec.design_volume_mm3(), ntop_vol, 2.0))
    return rep


def build_seat(spec: SeatSpec, out_dir: Path | None = None, *, notebook: Path | None = None,
               catalog_name: str = "stone_seat_harness") -> SeatResult:
    """Run the stone_seat block through its harness notebook under nTopCL and gate the cutter."""
    import time
    from . import catalog, config, ntopcl, runs
    problems = spec.validate()
    if problems:
        raise ValueError("; ".join(problems))
    cat = catalog.load(catalog_name)
    nb = Path(notebook) if notebook else cat.notebook
    run_dir, run_id = runs.fresh_run_dir(Path(out_dir) if out_dir else config.out_dir() / "seat", spec.stem)
    envelope_stl = run_dir / f"{spec.stem}.envelope.stl"
    spec.envelope().export(str(envelope_stl))
    stl = run_dir / f"{spec.stem}.stl"
    started = time.time()
    run = ntopcl.run(nb, cat.build_inputs(spec.notebook_inputs(str(envelope_stl), str(stl))), run_dir, tag=spec.stem)
    try:
        runs.require_fresh(stl, started, "the exported seat")
    except FileNotFoundError as e:
        raise ntopcl.NtopclError(f"notebook reported success but {e}", run) from e
    entry = run.outputs.get(cat.output.get("name", "Volume"))
    ntop_vol = ntopcl.scalar_value(entry) if entry else None
    rep = check_seat(spec, stl, ntop_vol)
    from . import gate as _gate
    _gate.save(rep)
    res = SeatResult(spec, stl, run, rep, ntop_vol, run_dir, run_id)
    (run_dir / f"{spec.stem}.report.json").write_text(json.dumps({
        "stem": spec.stem, "run_id": run_id, "status": res.status, "design": spec.design(),
        "inputs": spec.notebook_inputs(str(envelope_stl), str(stl)), "ntop_volume_mm3": ntop_vol,
        "design_volume_mm3": spec.design_volume_mm3(), "gate": rep.to_dict(),
        "notebook": runs.notebook_identity(nb), "environment": runs.environment(ntopcl.version()),
    }, indent=2, default=str), encoding="utf-8")
    return res
