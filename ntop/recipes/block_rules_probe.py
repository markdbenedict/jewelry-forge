"""Which notebooks does embed_custom_block accept as custom blocks? (2026-10-28)

    python -m ntopjewel api build block_rules_probe      # nTop open, View > Python Console open

prong_head.ntop was saved with all 16 inputs and an Output and was refused on embed: "Not a
valid custom block; output may be absent or missing inputs", while stone_seat.ntop (text + real
inputs, Output built) embeds. prong_head differs in three ways; each variant here isolates one,
plus the design that avoids nesting (the seat cutter as an implicit INPUT of the head):

    base        Radius (real) -> sphere -> Output                      (known good)
    integer     + Count (integer) -> polar array of the sphere -> Output
    angle       + Spacing (deg) wired into that array
    combo       two spheres -> Boolean Union -> Output (a combination: may stay unbuilt in the GUI)
    nested      embeds `base` and outputs its instance
    implicit_in an implicit input (core.var<implicit>) offset by Radius -> Output

Each variant is saved to out/api/block_rules/<name>.ntop with its Output's build state at save
time, then embedded into a fresh notebook; the result records accept / refuse (verbatim).
Nothing outside out/api/ is touched.
"""
from __future__ import annotations

import time
from pathlib import Path

from ntopjewel import nb_jewel as nj
from ntopjewel.notebook_api import NotebookHelper

HERE = Path(__file__).resolve()
OUT = HERE.parents[2] / "out" / "api" / "block_rules"


def _sphere(h, label, radius_var, x=0.0):
    pt = nj.point_block(h, f"{label} P", x=x)
    s = h.add(label, nj.SPHERE, mask="sphere", must=[["sphere<point,real>"]])
    h.wire(pt, s, ["Center Point"])
    h.wire(radius_var, s, ["Radius"])
    return s


def _variant(notebook, name: str, log: list) -> dict:
    notebook.new_notebook()
    h = NotebookHelper(notebook)
    r = h.real_var("Radius", 1.0, "mm")
    inputs = [r]
    if name == "base":
        body = _sphere(h, "S", r)
    elif name in ("integer", "angle"):
        s = _sphere(h, "S", r, x=3.0)
        n = nj.integer_variable(h, "Count", 4)
        inputs.append(n)
        arr = h.add("Array", mask="polar_array", must=nj.POLAR_ARRAY)
        h.wire(s, arr, ["Body"])
        h.wire(n, arr, ["Count"])
        h.wire(nj.z_axis(h), arr, ["Axis"])
        if name == "angle":
            a = nj.angle_variable(h, "Spacing", 90.0)
            inputs.append(a)
            h.wire(a, arr, ["Angular Spacing"])
        else:
            h.set(arr, ["Angular Spacing"], 90.0, "deg")
        body = arr
    elif name == "combo":
        u = h.add("Union", mask="union", must=nj.UNION)
        for k, x in enumerate((0.0, 1.5)):
            h.to_list(_sphere(h, f"S{k}", r, x=x), u, ["Bodies"])
        body = u
    elif name == "nested":
        ident = h.embed_block(OUT / "base.ntop")
        body = h.add("Inner", ident)
        h.wire(r, body, ["Radius"])
    elif name == "implicit_in":
        cut = h.nb.add_block("core.var<implicit>")
        cid = cut["id"]
        h.blocks["Cutter"] = cid
        off = h.add("Offset", mask="offset", must=nj.OFFSET)
        h.wire(cid, off, ["Body"])
        h.wire(r, off, ["Distance"])
        inputs.append(cid)
        body = off
    out = h.wrap_var("Body", body)
    h.declare_inputs(inputs)
    h.set_output(out)
    st = h.state(body, 15)
    path = OUT / f"{name}.ntop"
    notebook.save_notebook_as(str(path))
    return {"state_at_save": st.get("buildState"), "inputs": len(inputs), "log": h.log[-8:], "path": str(path)}


def build(notebook, params: dict | None = None) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    results, summary = {}, []
    for name in ("base", "integer", "angle", "combo", "nested", "implicit_in"):
        rec = {}
        try:
            rec.update(_variant(notebook, name, []))
        except Exception as e:
            rec["build_error"] = f"{type(e).__name__}: {e}"[:600]
        if "path" in rec:
            notebook.new_notebook()
            try:
                notebook.embed_custom_block(rec["path"])
                blocks = notebook.list_custom_blocks()
                rec["embed"] = "ok"
                rec["custom_blocks"] = blocks
                ident = [b["id"] for b in blocks if b["name"] == name]
                if ident:
                    inst = notebook.add_block(ident[0])
                    rec["instance_inputs"] = notebook.list_block_inputs(inst["id"])
            except Exception as e:
                rec["embed"] = f"REFUSED: {e}"[:600]
        results[name] = rec
        summary.append(f"{name:12} saved-state {rec.get('state_at_save', '-'):9} embed: {rec.get('embed', rec.get('build_error'))}")
        time.sleep(0.2)
    return {"summary": summary, "results": results}
