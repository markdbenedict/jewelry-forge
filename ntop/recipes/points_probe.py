"""What nTop 6.3.3 does with a points file, measured in the open session (2026-11-05) - the hammered
texture rests on it.

    python -m ntopjewel api build points_probe        # nTop open (in the foreground), View > Python Console open

A hammered band's dimples are equal spheres at centres Python lays out; their union is the distance to
the nearest centre less one radius. Built natively, that is Import Points (the discovery run found
`import_points<file_path,unit_length_enum>`) -> Sphere with the whole list on its Center Point -> one
Boolean Union. The discovery run found no block that places a body at every point of a list, so this
rests on nTop mapping a list fed into a single-item input - which nTop usually does, but nothing here
has measured it. Measured:

1. **Which file Import Points reads**: three points 10 mm apart written as comma-separated `x,y,z` lines
   (.csv), then, if that fails, whitespace-separated (.txt).
2. **Whether Sphere takes the whole list**: 1 mm balls at the three points, united, have three balls'
   volume (12.57 mm³) if nTop maps the list, one ball's (4.19) if it takes the first point only, or the
   wire is refused.

The answers are merged into `ntop/api_facts.json` (commit it) beside transform_probe's; nothing else is
touched. Each measurement is a fresh notebook whose Output is the volume (a typed consumer: the only way
a measurement builds in the GUI session, CLAUDE.md).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from ntopjewel import nb_jewel as nj

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
BALL_MM3 = 4.0 / 3.0 * 3.141592653589793          # a 1 mm ball
POINTS = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 10.0, 0.0)]
FORMATS = {"csv": ",", "txt": " "}
DEFAULTS = {"facts_to": str(REPO / "ntop" / "api_facts.json"), "wait_s": 90,
            "csv": str(REPO / "out" / "api" / "points_probe.csv"), "txt": str(REPO / "out" / "api" / "points_probe.txt")}


def prepare(params: dict, work_dir: Path) -> dict:
    """Laptop side: the three points in both spellings."""
    for fmt, sep in FORMATS.items():
        path = Path(params.get(fmt) or DEFAULTS[fmt])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(sep.join(f"{c:g}" for c in p) + "\n" for p in POINTS), encoding="ascii")
        params[fmt] = str(path)
    return params


def _measure(h, body, wait_s) -> float | None:
    """The volume of `body`, built in the session: a Volume Integral of 1 wrapped as the typed Output."""
    one = h.real_var("One", 1.0, "")
    integ = h.add("Volume Integral", mask="volume_integral", must=nj.VOLUME_INTEGRAL)
    h.wire(body, integ, ["Body"])
    h.wire(one, integ, ["Integrand"])
    vol = h.wrap_var("Volume", integ)
    h.set_output(vol)
    deadline = time.time() + wait_s
    while time.time() < deadline:
        value = h.pull_value(vol)
        if isinstance(value, (int, float)):
            return float(value)
        h.nudge_build(integ)
        time.sleep(1.0)
    return None


def balls_at_points(notebook, path: str, wait_s) -> dict:
    """Import Points from `path` -> Sphere (the list on Center Point, radius 1) -> Boolean Union -> volume."""
    notebook.new_notebook()
    h = nj.Helper(notebook)
    out = {"path": path}
    src = nj.path_variable(h, "Points Path", path)
    imp = h.add("Imported Points", "import_points<file_path,unit_length_enum>", mask="import_points", must=[["import_points"]])
    out["import_inputs"] = [(i.get("name"), i.get("type")) for i in h.inputs(imp)]
    h.wire(src, imp, [h.input_of_type(imp, "file_path")])
    out["import_state"] = h.state(imp, wait_s=30)
    out["points"] = repr(h.pull_value(imp))[:400]
    radius = h.real_var("Radius", 1.0, "mm")
    ball = h.add("Balls", nj.SPHERE, mask="sphere", must=[["sphere<point,real>"], ["sphere", "point", "real"]])
    h.wire(radius, ball, ["Radius"])
    try:
        h.wire(imp, ball, nj.CENTRE)
    except Exception as e:
        out["sphere_wire"] = f"refused: {type(e).__name__}: {e}"[:300]
        return out
    out["sphere_state"] = h.state(ball, wait_s=30)
    union = h.add("Union", mask="union", must=nj.UNION)
    try:
        h.wire(ball, union, nj.BODIES)                 # the whole list into the Bodies list
        out["union_wire"] = "connected"
    except Exception as e:
        out["union_wire"] = f"connect refused ({e}); appended"[:300]
        h.to_list(ball, union, nj.BODIES)
    out["volume"] = _measure(h, union, wait_s)
    out["log"] = h.log[-30:]
    return out


def _verdict(v: float | None) -> str:
    if v is None:
        return "unknown (no volume came back)"
    if abs(v - 3 * BALL_MM3) < 0.25 * BALL_MM3:
        return "list"                                  # one sphere per point
    if abs(v - BALL_MM3) < 0.25 * BALL_MM3:
        return "first"                                 # the first point only
    return f"unknown ({v:.3f} mm³: neither three balls nor one)"


def build(notebook, params: dict | None = None) -> dict:
    p = {**DEFAULTS, **(params or {})}
    results, summary, facts = {}, [], {}
    for fmt in FORMATS:
        try:
            r = balls_at_points(notebook, p[fmt], p["wait_s"])
        except Exception as e:
            r = {"error": f"{type(e).__name__}: {e}"[:600]}
        results[fmt] = r
        verdict = r.get("sphere_wire") or r.get("error") or _verdict(r.get("volume"))
        summary.append(f"{fmt:4} {verdict}")
        if verdict in ("list", "first"):
            facts = {"import_points_format": fmt, "sphere_on_point_list": verdict}
            break
    out = {"summary": summary, "results": results, "facts": facts}
    if facts:
        path = Path(p["facts_to"])
        known = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        known.update(facts)
        known["points_measured"] = time.strftime("%Y-%m-%d")
        known["points_how"] = "ntop/recipes/points_probe.py, in nTop's session"
        path.write_text(json.dumps(known, indent=2) + "\n", encoding="utf-8")
        out["facts_file"] = str(path)
        summary.append(f"merged into {path} - commit it")
    else:
        summary.append("not settled: nothing written; send out\\api\\points_probe.result.json to Claude")
    return out
