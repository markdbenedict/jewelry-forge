"""Two facts about nTop 6.3.3 the notebooks rely on, measured in the open session (2026-11-04).

    python -m ntopjewel api build transform_probe       # nTop open, View > Python Console open

1. **The order Combine Transforms applies its list in.** A 1 mm ball at the origin, moved by
   Combine Transforms [Translation (10, 0, 0), Rotation 90° about +Z]: applied in list order it
   ends at (0, 10, 0), applied last-first at (10, 0, 0). The ball ∩ a ball at (0, 10, 0) has the
   ball's whole volume (4.19 mm³) or none. nTop's block page does not say (docs.ntop.com, Combine
   Transforms: one input, "List of transforms to combine"); multistone.ntop's heads land by it.
2. **Mirror Body across a Plane** (Origin, X axis, Y axis): a ball at (3, 0, 0) mirrored across the
   plane through the origin spanned by +Y and +Z must land at (-3, 0, 0); the ball ∩ a ball there
   has the whole volume. The solitaires' arches and milgrain are a half and its mirror.

Both answers go to `ntop/api_facts.json` (commit it), which the recipes read at build time; nothing
else is touched. Each measurement is a fresh notebook whose Output is the volume (a typed consumer:
the only way a measurement builds in the GUI session, CLAUDE.md).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from ntopjewel import nb_jewel as nj

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
BALL_MM3 = 4.0 / 3.0 * 3.141592653589793          # a 1 mm ball
DEFAULTS = {"facts_to": str(REPO / "ntop" / "api_facts.json"), "wait_s": 60}


def _ball(h, label, x=0.0, y=0.0):
    return h.sphere(label, nj.point_block(h, f"{label} Centre", x=x, y=y), h.blocks.get("Radius") or h.real_var("Radius", 1.0, "mm"))


def _measure(notebook, h, body, wait_s) -> float | None:
    """The volume of `body`, built in the session: a Volume Integral of 1 wrapped as the typed Output."""
    one = h.real_var("One", 1.0, "")
    integ = h.add("Volume Integral", mask="volume_integral", must=nj.VOLUME_INTEGRAL)
    h.wire(body, integ, ["Body"])
    h.wire(one, integ, ["Integrand"])
    vol = h.wrap_var("Volume", integ)
    h.set_output(vol)
    value = None
    deadline = time.time() + wait_s
    while time.time() < deadline:
        value = h.pull_value(vol)
        if isinstance(value, (int, float)):
            return float(value)
        h.nudge_build(integ)
        time.sleep(1.0)
    return None


def _verdict(v: float | None, whole: str, none: str) -> str:
    if v is None:
        return "unknown (no volume came back)"
    if abs(v - BALL_MM3) < 0.25 * BALL_MM3:
        return whole
    if v < 0.02 * BALL_MM3:
        return none
    return f"unknown ({v:.3f} mm³, neither the whole ball nor none)"


def combine_order(notebook, wait_s) -> tuple[str, float | None, list]:
    notebook.new_notebook()
    h = nj.Helper(notebook)
    ball = _ball(h, "Ball")
    move = h.add("Move +X", "translation_transform<vector>", mask="translation_transform", must=[["translation_transform"]])
    h.set(move, [h.input_of_type(move, "vector")], [10.0, 0.0, 0.0], "mm")
    turn = h.rotation("Turn 90", nj.angle_variable(h, "Quarter", 90.0))
    both = h.add("Move then Turn", "combine_transforms<list<transformation>>", mask="combine_transforms",
                 must=[["combine_transforms"]])
    slot = h.input_of_type(both, "list")
    h.to_list(move, both, [slot])
    h.to_list(turn, both, [slot])
    moved = h.transform("Moved Ball", ball, both)
    probe = h.intersect("Overlap", [moved, _ball(h, "Target", y=10.0)])
    v = _measure(notebook, h, probe, wait_s)
    return _verdict(v, "list", "reverse"), v, h.log


def mirror(notebook, wait_s) -> tuple[str, float | None, list]:
    notebook.new_notebook()
    h = nj.Helper(notebook)
    ball = _ball(h, "Ball", x=3.0)
    plane = nj.plane_block(h, "Mirror Plane", x_axis=(0.0, 1.0, 0.0), y_axis=(0.0, 0.0, 1.0))
    mirrored = h.mirror("Mirrored Ball", ball, plane)
    probe = h.intersect("Overlap", [mirrored, _ball(h, "Target", x=-3.0)])
    v = _measure(notebook, h, probe, wait_s)
    return _verdict(v, "ok", "wrong"), v, h.log


def build(notebook, params: dict | None = None) -> dict:
    p = {**DEFAULTS, **(params or {})}
    facts, results, summary = {}, {}, []
    for key, fn in (("combine_transforms_order", combine_order), ("mirror_body", mirror)):
        try:
            verdict, v, log = fn(notebook, p["wait_s"])
            results[key] = {"verdict": verdict, "volume": v, "log": log[-30:]}
        except Exception as e:
            verdict, results[key] = f"unknown ({type(e).__name__}: {e})"[:300], {"error": str(e)[:600]}
        summary.append(f"{key:26} {verdict}")
        if not verdict.startswith("unknown"):
            facts[key] = verdict
    out = {"summary": summary, "results": results, "facts": facts}
    if len(facts) == 2:                                    # both settled: record them for the recipes
        facts["measured"] = time.strftime("%Y-%m-%d")
        facts["how"] = "ntop/recipes/transform_probe.py, in nTop's session"
        Path(p["facts_to"]).write_text(json.dumps(facts, indent=2) + "\n", encoding="utf-8")
        out["facts_file"] = p["facts_to"]
        summary.append(f"written to {p['facts_to']} - commit it")
    else:
        summary.append("not every fact settled: nothing written; send the result.json to Claude")
    return out
