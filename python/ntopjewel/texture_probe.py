"""Measuring what nTop's own texture blocks do to a band (2026-11-06; the notebook: ntop/recipes/texture_probe.py).

nTop's toolkit textures (simplex and cellular noise debosses, surface roughness, voronoi deboss / emboss,
the triangle wave) are its own fields - their random points and noise are nTop's, so Python cannot rebuild them
point for point. What Python can do is measure them, and what it measures here is what a gate for them would
check: every vertex of the textured STL against the designed band section (r, z), its signed distance
(− into the metal: a deboss; + out of it: an emboss), grouped by the face of the section it lies nearest -
the outer face, the bore, the two side faces, the rounded edges between them. Per face: how deep and how high,
how much of the face is touched, and on the outer face the feature size (the lag where the texture's
autocorrelation round the ring falls to a half). And the volume it took.

`texture-probe` runs the probe notebook once (nTopCL writes one STL per texture) and writes
`texture_probe.json` + a table beside the STLs; `texture-probe --measure <dir>` measures STLs already there.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import band as bandmod
from . import nb_texture as nt

TOUCHED_MM = 0.01           # a vertex further than this from the designed section has been moved by the texture
FACES = ("outer", "bore", "side", "edge")


def probe_band() -> bandmod.BandSpec:
    """The band every texture is tried on: US 6 court 4 x 1.6, Mesh Tolerance 0.05 (the hammered band's)."""
    return bandmod.BandSpec(size=6, profile="court", width_mm=4.0, thickness_mm=1.6, mesh_tolerance_mm=0.05)


def notebook_inputs(b: bandmod.BandSpec, outputs: dict[str, str], values: dict | None = None) -> dict:
    """The band's inputs, the probe's numbers (PROBE_VALUES, overridden by `values`) and one Output per case."""
    v = b.notebook_inputs("")
    v.pop("Output Path", None)
    v.update({k: (values or {}).get(k, d) for k, d in nt.PROBE_VALUES.items() if k not in nt.UNITLESS})
    v.update({k: outputs[k] for k in nt.OUTPUTS})
    return v


@dataclass
class SectionModel:
    """The designed section's boundary, sampled densely, each sample labelled by its face."""
    b: bandmod.BandSpec
    step: float = 0.005
    pts: np.ndarray = field(init=False)
    face: np.ndarray = field(init=False)
    polygon: object = field(init=False)

    def __post_init__(self):
        poly = self.b.design_section()
        if hasattr(poly, "geoms"):
            poly = max(poly.geoms, key=lambda g: g.area)
        self.polygon = poly
        ring = np.asarray(poly.exterior.coords)                    # (r, z)
        seg = np.diff(ring, axis=0)
        n = np.maximum(1, np.ceil(np.hypot(seg[:, 0], seg[:, 1]) / self.step).astype(int))
        pts = np.concatenate([ring[i] + np.outer(np.arange(n[i]) / n[i], seg[i]) for i in range(len(seg))])
        self.pts = pts
        half = self.b.width_mm / 2
        e = self.b.edge_round + 0.05                               # the rounded edges and a margin
        r_mid = (self.b.bore_radius_mm + self.b.outer_radius_mm) / 2
        face = np.full(len(pts), "edge", dtype=object)
        flat = np.abs(pts[:, 1]) < half - e
        face[flat & (pts[:, 0] >= r_mid)] = "outer"
        face[flat & (pts[:, 0] < r_mid)] = "bore"
        side = (np.abs(pts[:, 1]) >= half - 1e-3) & (pts[:, 0] > self.b.bore_radius_mm + e) & (pts[:, 0] < self.b.outer_radius_mm - e)
        face[side] = "side"
        self.face = face

    def signed_distance(self, r, z):
        """Distance from (r, z) to the section's boundary: − inside the metal, + outside; and the nearest face."""
        from scipy.spatial import cKDTree
        from shapely import contains_xy
        d, k = cKDTree(self.pts).query(np.column_stack([r, z]))
        inside = contains_xy(self.polygon, r, z)
        return np.where(inside, -d, d), self.face[k]

    def volume_mm3(self) -> float:
        c = self.polygon.centroid
        return 2 * math.pi * c.x * self.polygon.area


def measure(stl: Path, model: SectionModel) -> dict:
    """One textured STL against the designed section: per face, depth / height / touched share; on the outer
    face the feature size round the ring; the volume taken; shells and triangles."""
    import trimesh
    mesh = trimesh.load_mesh(stl, process=True)
    v = np.asarray(mesh.vertices)
    r = np.hypot(v[:, 0], v[:, 1])
    z = v[:, 2]
    d, face = model.signed_distance(r, z)
    out: dict = {"stl": str(stl), "triangles": int(len(mesh.faces)), "watertight": bool(mesh.is_watertight),
                 "shells": int(len(mesh.split(only_watertight=False))) if len(mesh.faces) < 6_000_000 else None}
    design_v = model.volume_mm3()
    vol = float(mesh.volume) if mesh.is_watertight else float("nan")
    out["volume_mm3"] = vol
    out["volume_change_pct"] = 100.0 * (vol - design_v) / design_v if math.isfinite(vol) else None
    faces = {}
    tri_c = mesh.triangles_center                                   # area-weighted shares: by triangle, not by vertex
    tri_a = mesh.area_faces
    dc, face_c = model.signed_distance(np.hypot(tri_c[:, 0], tri_c[:, 1]), tri_c[:, 2])
    for f in FACES:
        m, mc = face == f, face_c == f
        if not m.any() or not mc.any():
            continue
        df, w = dc[mc], tri_a[mc]
        dv = d[m]
        faces[f] = {"area_mm2": float(w.sum()), "deepest_mm": float(max(0.0, -dv.min())), "highest_mm": float(max(0.0, dv.max())),
                    "p01_mm": float(_wpercentile(df, w, 1)), "p99_mm": float(_wpercentile(df, w, 99)),
                    "mean_mm": float(np.average(df, weights=w)), "touched": float(w[np.abs(df) > TOUCHED_MM].sum() / w.sum())}
    out["faces"] = faces
    m = face == "outer"
    if m.sum() > 1000:
        out["feature_mm"] = feature_size(np.arctan2(v[m, 1], v[m, 0]), z[m], d[m], model.b.outer_radius_mm)
    return out


def _wpercentile(x, w, q):
    o = np.argsort(x)
    c = np.cumsum(w[o])
    return x[o][np.searchsorted(c, q / 100.0 * c[-1])]


def feature_size(theta, z, d, radius, cell=0.05, max_points=300_000, seed=0) -> float | None:
    """The lag (mm of arc) where the texture's autocorrelation round the ring first falls below a half, the
    median over the rows of the outer face resampled on a `cell` mm grid (linear interpolation of the vertices'
    depths); None for a texture with no variation round the ring."""
    from scipy.interpolate import griddata
    arc = (theta % (2 * math.pi)) * radius
    if len(arc) > max_points:
        k = np.random.default_rng(seed).choice(len(arc), max_points, replace=False)
        arc, z, d = arc[k], z[k], d[k]
    circ = 2 * math.pi * radius
    n_arc = int(round(circ / cell))
    zs = np.arange(np.percentile(z, 5), np.percentile(z, 95), cell)
    if len(zs) == 0:
        return None
    ga = (np.arange(n_arc) + 0.5) * circ / n_arc
    pad = arc < 1.0                                                   # wrap the seam: copy a mm past 2πr
    A = np.concatenate([arc, arc[pad] + circ])
    Z = np.concatenate([z, z[pad]])
    D = np.concatenate([d, d[pad]])
    grid = griddata((A, Z), D, (ga[None, :].repeat(len(zs), 0), zs[:, None].repeat(n_arc, 1)), method="linear")
    lags = []
    for x in grid:
        ok = np.isfinite(x)
        if ok.mean() < 0.9:
            continue
        x = np.where(ok, x, np.nanmean(x)) - np.nanmean(x)
        if x.std() < 1e-4:
            continue
        f = np.fft.rfft(x)
        ac = np.fft.irfft(f * np.conj(f), n=n_arc)
        ac = ac / ac[0]
        below = np.nonzero(ac[: n_arc // 2] < 0.5)[0]
        if len(below):
            lags.append(below[0] * circ / n_arc)
    return float(np.median(lags)) if lags else None


def measure_all(directory: Path, b: bandmod.BandSpec | None = None) -> dict:
    """Every case's STL in `directory` (texture_probe_<case>.stl), measured; a missing one is reported as such."""
    model = SectionModel(b or probe_band())
    res = {"band": (b or probe_band()).describe().splitlines()[0], "design_volume_mm3": model.volume_mm3(), "cases": {}}
    for label in nt.CASES:
        stl = Path(directory) / f"texture_probe_{nt.slug(label)}.stl"
        res["cases"][label] = measure(stl, model) if stl.exists() else {"missing": str(stl)}
    return res


def table(res: dict) -> str:
    rows = [f"{'texture':16} {'outer deepest/highest':>22} {'touched':>8} {'feature':>8} {'bore':>14} {'sides':>14} "
            f"{'edges':>14} {'volume':>8}"]

    def dh(f):
        return f"-{f['deepest_mm']:.3f}/+{f['highest_mm']:.3f}" if f else "-"
    for label, c in res["cases"].items():
        if "missing" in c:
            rows.append(f"{label:16} no STL ({c['missing']})")
            continue
        f = c["faces"]
        fs = c.get("feature_mm")
        vc = c.get("volume_change_pct")
        rows.append(f"{label:16} {dh(f.get('outer')):>22} {f.get('outer', {}).get('touched', 0):>7.0%} "
                    f"{(f'{fs:.2f} mm' if fs else '-'):>8} {dh(f.get('bore')):>14} {dh(f.get('side')):>14} "
                    f"{dh(f.get('edge')):>14} {(f'{vc:+.2f}%' if vc is not None else '-'):>8}")
    return "\n".join(rows)


def write(res: dict, directory: Path) -> Path:
    path = Path(directory) / "texture_probe.json"
    path.write_text(json.dumps(res, indent=1), encoding="utf-8")
    (Path(directory) / "texture_probe.txt").write_text(table(res) + "\n", encoding="utf-8")
    return path


def run(out_dir: Path | None = None, values: dict | None = None, notebook: Path | None = None) -> tuple[dict, Path]:
    """One nTopCL run of the probe notebook (each case's STL into a fresh run directory), then the measurements."""
    from . import catalog, config, ntopcl, runs
    cat = catalog.load("texture_probe")
    nb = Path(notebook) if notebook else cat.notebook
    if not notebook:
        runs.require_built(cat, cat.notebook)
    root = Path(out_dir) if out_dir else config.out_dir() / "texture_probe"
    run_dir, _run_id = runs.fresh_run_dir(root, "texture_probe")
    outputs = {k: str(run_dir / f"texture_probe_{nt.slug(k[len('Output '):])}.stl") for k in nt.OUTPUTS}
    inputs = cat.build_inputs(notebook_inputs(probe_band(), outputs, values))
    result = None
    try:
        result = ntopcl.run(nb, inputs, run_dir, tag="texture_probe")
    except ntopcl.NtopclError as e:           # a texture that failed still leaves the others' STLs: measure them
        result = e.result
        if result is None:
            raise
    res = measure_all(run_dir)
    # 2026-11-06: nTopCL built every texture ("nTop successfully built.", no [E]) and exited non-zero after
    # "[W]: Logout failed." - the textures stand on the log and the STLs, the exit code is reported beside them
    built = bool(result.log.built) and not result.log.errors
    res["ntopcl"] = {"ok": built, "exit_code": result.returncode, "errors": list(result.log.errors)[:20], "seconds": result.seconds,
                     "run_dir": str(run_dir), "values": {k: v for k, v in notebook_inputs(probe_band(), outputs, values).items()
                                                         if k in nt.PROBE_VALUES}}
    write(res, run_dir)
    return res, run_dir
