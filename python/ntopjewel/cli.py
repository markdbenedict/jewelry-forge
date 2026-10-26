"""Command line: `python -m ntopjewel <command>` or `ntopjewel <command>`.

  doctor                      what this machine has (ntopcl, nTop, Blender, folders, catalog)
  templates NOTEBOOK          ntopcl -t -> input/output templates; diff against the catalog
  run CATALOG --set K=V ...   run any catalogued notebook with explicit inputs
  band --size 6 ...           Phase 0 band: build, export, gate, report
  gate FILE.stl [--expect-*]  run the mesh gate on any mesh
  sizes                       print the ring-size conversion table
  api check                   prove the SSH link to nTop's Python Console (Notebook API)
  api build RECIPE            author a notebook through the Notebook API (ntop/recipes/<RECIPE>.py)
  api line "CODE"             send one Python line to the console (discovery, debugging)
  api collect RECIPE          read the result of a driver you pasted into the GUI console by hand
"""
from __future__ import annotations

import argparse
import json
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
                         profile=a.profile, dome_mm=a.dome, comfort_mm=a.comfort, edge_round_mm=a.edge_round,
                         allowance_mm=a.allowance, mesh_tolerance_mm=a.tolerance)
    if a.dry_run:
        probs = spec.validate()
        print(spec.describe() if not probs else f"{spec.stem}: problems: " + "; ".join(probs))
        for w in spec.warnings():
            print("  warning: " + w)
        if not probs:
            for k, v in spec.notebook_inputs("<output path>").items():
                print(f"    {k}: {v}")
        return 1 if probs else 0
    try:
        res = band.build(spec, Path(a.out) if a.out else None, notebook=Path(a.notebook) if a.notebook else None,
                         catalog_name=a.catalog, deliver=a.deliver, deliver_project=a.project)
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


def _recipe_script(name: str) -> Path:
    """`band_profile` -> ntop/recipes/band_profile.py; an existing path is used as is."""
    p = Path(name)
    if p.suffix == ".py" and p.exists():
        return p.resolve()
    script = config.repo_root() / "ntop" / "recipes" / f"{p.stem}.py"
    if not script.exists():
        have = sorted(x.stem for x in script.parent.glob("*.py"))
        raise SystemExit(f"no build script {script}; recipes with a script: {have}")
    return script


def _console(a: argparse.Namespace):
    from . import notebook_api
    return notebook_api.Console(key=Path(a.key) if a.key else None, port=a.port)


def _print_build_result(res: dict) -> None:
    r = res.get("result") or {}
    if r.get("summary"):                      # discovery-style scripts speak for themselves
        print("\n".join(str(x) for x in r["summary"]))
        return
    print(f"saved     : {r.get('saved')}")
    print(f"recipe    : {r.get('recipe')}")
    if "volume" in r:
        print(f"volume    : {r.get('volume')}  ({r.get('expected_volume_hint', '')})")
    if "test_output" in r:
        print(f"test STL  : {r.get('test_output')}  ({'written' if r.get('test_output_exists') else 'NOT written'})")
    bad = {k: v for k, v in (r.get("states") or {}).items() if not str(v).startswith("e_OK")}
    print(f"states    : {len(r.get('states') or {})} blocks checked" + (f", not OK: {bad}" if bad else ", all e_OK"))
    if r.get("identifiers"):
        print("identifiers used:")
        for k, v in r["identifiers"].items():
            print(f"    {k:<16} {v}")
    notes = [ln for ln in r.get("log", []) if "failed" in ln or "not set" in ln or "fall" in ln]
    if notes:
        print("notes     :\n    " + "\n    ".join(notes))


def cmd_api(a: argparse.Namespace) -> int:
    from . import notebook_api
    work_dir = Path(a.out) if a.out else config.out_dir() / "api"
    if a.api_cmd == "check":
        try:
            out = _console(a).check(timeout=a.timeout)
        except notebook_api.ConsoleError as e:
            print(f"console check failed: {e}")
            return 2
        print("connected; the console answered:")
        print(out.strip()[-2000:])
        return 0
    if a.api_cmd == "line":
        try:
            out = _console(a).run_line(a.code, timeout=a.timeout)
        except notebook_api.ConsoleError as e:
            print(f"console failed: {e}")
            return 2
        print(out.strip()[-6000:])
        return 0
    script = _recipe_script(a.recipe)
    if a.api_cmd == "collect":
        result_path = work_dir / f"{script.stem}.result.json"
        try:
            res = notebook_api.collect_result(script, result_path)
        except notebook_api.ConsoleError as e:
            print(e)
            return 2
        _print_build_result(res)
        return 0
    # build
    params = _parse_set(a.param)
    if a.scratch:
        params.setdefault("save_to", str(work_dir / f"{script.stem}.ntop"))
        params.setdefault("recipe_to", str(work_dir / f"{script.stem}.recipe.json"))
    python_path = config.repo_root() / "python"
    if a.dry_run:
        driver, result = notebook_api.prepare_script(script, params, work_dir=work_dir, python_path=python_path)
        print(f"driver : {driver}\nresult : {result} (written by the driver)\nparams : {json.dumps(params)}")
        print("\nPaste this one line into nTop's Python Console (View > Python Console), then run "
              f"`python -m ntopjewel api collect {script.stem}`:\n\n    {notebook_api.exec_line(driver)}\n")
        print("Or over SSH: " + " ".join(_console(a).command()))
        return 0
    try:
        res = _console(a).run_script(script, params, work_dir=work_dir, python_path=python_path, timeout=a.timeout)
    except notebook_api.ConsoleError as e:
        print(f"api build failed: {e}")
        return 2
    _print_build_result(res)
    print(f"\nfull result: {work_dir / (script.stem + '.result.json')}")
    return 0


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
    b.add_argument("--thickness", type=float, default=1.3, help="radial thickness at the mid-plane, mm")
    b.add_argument("--profile", default="court", choices=sorted(band.PROFILES), help="cross-section preset")
    b.add_argument("--dome", type=float, help="outer drop from mid-plane to edge, mm (overrides the preset)")
    b.add_argument("--comfort", type=float, help="bore relief at the edges, mm (overrides the preset)")
    b.add_argument("--edge-round", type=float, help="radius rounded onto every edge, mm (overrides the preset)")
    b.add_argument("--catalog", default="ring_band_profile", help="catalog entry / notebook family")
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

    api = sub.add_parser("api", help="nTop Notebook API through the Python Console (SSH localhost:2222)")
    api.add_argument("--key", help="SSH private key (default: NTOP_SSH_KEY or ~/.ssh/id_ntopcli)")
    api.add_argument("--port", type=int, default=2222)
    api.add_argument("--timeout", type=float, default=900, help="seconds to wait for nTop")
    api.add_argument("--out", help="work dir for driver/params/result files (default out/api)")
    api_sub = api.add_subparsers(dest="api_cmd", required=True)
    api_sub.add_parser("check")
    ln = api_sub.add_parser("line")
    ln.add_argument("code", help='one Python line, e.g. "print(notebook.list_available_blocks(\'torus\'))"')
    bd = api_sub.add_parser("build")
    bd.add_argument("recipe", help="name under ntop/recipes (band_profile) or a path to a .py build script")
    bd.add_argument("--param", action="append", default=[], metavar="KEY=VALUE",
                    help="override a DEFAULTS entry of the script (save_to=..., fresh=false, wait_s=600)")
    bd.add_argument("--scratch", action="store_true", help="save the notebook and recipe under out/api, not the repo")
    bd.add_argument("--dry-run", action="store_true", help="write the driver and print the console line; do not connect")
    co = api_sub.add_parser("collect")
    co.add_argument("recipe")
    api.set_defaults(fn=cmd_api)

    a = p.parse_args(argv)
    if a.cmd == "band":
        try:
            a.size = float(a.size)
        except ValueError:
            pass
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
