"""Command line: `python -m ntopjewel <command>` or `ntopjewel <command>`.

  doctor                      what this machine has (ntopcl, nTop, Blender, folders, catalog)
  templates NOTEBOOK          ntopcl -t -> input/output templates; diff against the catalog
  run CATALOG --set K=V ...   run any catalogued notebook with explicit inputs
  band --size 6 ...           Phase 0 band: build, export, gate, report
  gate FILE.stl [--expect-*]  run the mesh gate on any mesh
  sizes                       print the ring-size conversion table
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, band, catalog, config, gate, ntopcl, tables


def _parse_set(items: list[str]) -> dict:
    out = {}
    for it in items or []:
        if "=" not in it:
            raise SystemExit(f"--set expects Name=value, got {it!r}")
        k, v = it.split("=", 1)
        v = v.strip()
        if v.lower() in ("true", "false"):
            val = v.lower() == "true"
        else:
            try:
                val = float(v) if ("." in v or "e" in v.lower()) else int(v)
            except ValueError:
                val = v
        out[k.strip()] = val
    return out


def cmd_doctor(_: argparse.Namespace) -> int:
    root = config.repo_root()
    exe = config.ntopcl_path()
    print(f"ntopjewel {__version__}  python {sys.version.split()[0]}  platform {sys.platform}")
    print(f"repo root      : {root}")
    print(f"ntopcl         : {exe or 'NOT FOUND (set NTOPCL)'}")
    if exe and exe.exists():
        print(f"ntopcl version : {ntopcl.version(exe) or '?'}")
    print(f"blender        : {config.blender_path() or 'not found (optional; set BLENDER)'}")
    print(f"out dir        : {config.out_dir()}")
    print(f"deliver dir    : {config.deliver_dir()} ({'exists' if config.deliver_dir().exists() else 'missing'})")
    nbs = sorted(config.notebooks_dir().glob("*.ntop")) if config.notebooks_dir().exists() else []
    print(f"notebooks      : {', '.join(p.name for p in nbs) or 'none yet (build from ntop/recipes)'}")
    print(f"catalog        : {', '.join(catalog.names()) or 'none'}")
    try:
        import trimesh  # noqa
        ray = "embree" if "embree" in type(trimesh.Trimesh().ray).__module__ else "triangle (pure python)"
        print(f"trimesh        : {trimesh.__version__}, ray backend {ray}")
    except Exception as e:  # pragma: no cover
        print(f"trimesh        : missing ({e})")
    return 0


def cmd_templates(a: argparse.Namespace) -> int:
    out = Path(a.out) if a.out else config.out_dir() / "templates" / Path(a.notebook).stem
    try:
        i, o = ntopcl.templates(Path(a.notebook), out)
    except ntopcl.NtopclError as e:
        msg = str(e)
        print(msg.strip())
        if "Output of function not set" in msg:
            print("\nThe notebook's Output section is empty. In nTop, type the output variable's name "
                  "(e.g. Volume) into the Output section, save, and rerun.")
        return 2
    print(f"wrote {i}\n      {o}")
    print(i.read_text(encoding="utf-8"))
    if a.catalog:
        probs = catalog.compare_with_template(catalog.load(a.catalog), i)
        print("catalog matches the notebook" if not probs else "catalog drift:\n  " + "\n  ".join(probs))
        return 1 if probs else 0
    return 0


def cmd_run(a: argparse.Namespace) -> int:
    cat = catalog.load(a.catalog)
    values = _parse_set(a.set)
    inputs = cat.build_inputs(values)
    out = Path(a.out) if a.out else config.out_dir() / cat.name
    try:
        res = ntopcl.run(cat.notebook if not a.notebook else Path(a.notebook), inputs, out, tag=a.tag or cat.name)
    except ntopcl.NtopclError as e:
        print(e)
        if e.result:
            print(e.result.summary())
        return 2
    print(res.summary())
    return 0


def cmd_band(a: argparse.Namespace) -> int:
    spec = band.BandSpec(size=a.size, system=a.system, width_mm=a.width, thickness_mm=a.thickness,
                         allowance_mm=a.allowance, mesh_tolerance_mm=a.tolerance)
    if a.dry_run:
        print(f"{spec.label}: inner Ø {spec.inner_diameter_mm:.3f}  bore r {spec.bore_radius_mm:.3f}  "
              f"outer r {spec.outer_radius_mm:.3f}  width {spec.width_mm}  tolerance {spec.mesh_tolerance_mm}")
        probs = spec.validate()
        print("ok" if not probs else "problems: " + "; ".join(probs))
        return 1 if probs else 0
    try:
        res = band.build(spec, Path(a.out) if a.out else None, notebook=Path(a.notebook) if a.notebook else None,
                         deliver=a.deliver, deliver_project=a.project)
    except (ntopcl.NtopclError, ValueError) as e:
        print(f"band failed: {e}")
        if isinstance(e, ntopcl.NtopclError) and e.result:
            print(e.result.summary())
        return 2
    print(res.text())
    return 0 if res.ok else 1


def cmd_gate(a: argparse.Namespace) -> int:
    rep = gate.check(Path(a.file), expect_inner=a.expect_inner, expect_outer=a.expect_outer,
                     expect_width=a.expect_width, expect_volume=a.expect_volume, tol_mm=a.tol,
                     shells=a.shells, wall_floor=a.wall_floor, wall_samples=a.samples, axis=a.axis)
    print(rep.text())
    return 0 if rep.passed else 1


def cmd_sizes(_: argparse.Namespace) -> int:
    print(" US    inner Ø mm   ISO circ   UK≈")
    import string
    for q in range(8, 53):          # US 2 .. 13 in quarter steps
        us = q / 4
        d = tables.us_size_to_inner_diameter_mm(us)
        uk_idx = (d - tables.UK_A_INNER_DIAMETER_MM) / tables.UK_STEP_MM
        uk = string.ascii_uppercase[int(round(uk_idx))] if 0 <= round(uk_idx) < 26 else "-"
        print(f"{us:5.2f}   {d:8.3f}    {tables.inner_diameter_mm_to_iso_circumference(d):6.1f}    {uk}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ntopjewel", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)

    t = sub.add_parser("templates")
    t.add_argument("notebook")
    t.add_argument("--out")
    t.add_argument("--catalog", help="catalog entry to diff against")
    t.set_defaults(fn=cmd_templates)

    r = sub.add_parser("run")
    r.add_argument("catalog")
    r.add_argument("--set", action="append", default=[], metavar="NAME=VALUE")
    r.add_argument("--notebook")
    r.add_argument("--out")
    r.add_argument("--tag")
    r.set_defaults(fn=cmd_run)

    b = sub.add_parser("band")
    b.add_argument("--size", default="6")
    b.add_argument("--system", default="US", help="US | UK | ISO | MM")
    b.add_argument("--width", type=float, default=4.0)
    b.add_argument("--thickness", type=float, default=1.3)
    b.add_argument("--allowance", type=float, default=0.0, help="mm added to the inner diameter")
    b.add_argument("--tolerance", type=float, default=0.1, help="Mesh from Implicit Body tolerance (= 2 x voxel size), mm")
    b.add_argument("--out")
    b.add_argument("--notebook")
    b.add_argument("--deliver", action="store_true", help="copy a passing STL to the Jewelry folder")
    b.add_argument("--project", default="Bands")
    b.add_argument("--dry-run", action="store_true")
    b.set_defaults(fn=cmd_band)

    g = sub.add_parser("gate")
    g.add_argument("file")
    g.add_argument("--expect-inner", type=float)
    g.add_argument("--expect-outer", type=float)
    g.add_argument("--expect-width", type=float)
    g.add_argument("--expect-volume", type=float)
    g.add_argument("--tol", type=float, default=0.05)
    g.add_argument("--shells", type=int, default=1)
    g.add_argument("--wall-floor", type=float, default=tables.FLOORS["wall_marginal"])
    g.add_argument("--samples", type=int, default=4000)
    g.add_argument("--axis", choices=["x", "y", "z"])
    g.set_defaults(fn=cmd_gate)

    sub.add_parser("sizes").set_defaults(fn=cmd_sizes)

    a = p.parse_args(argv)
    if a.cmd == "band":
        try:
            a.size = float(a.size)
        except ValueError:
            pass
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
