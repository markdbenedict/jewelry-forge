"""Phase 2, step 0: can the Notebook API make and use a CUSTOM BLOCK?

    python -m ntopjewel api build custom_block_probe        # nTop open, View > Python Console open

Phase 2 is a block library (`ntop/blocks/`): band, bead row, groove, engraving wrap, gem
bodies, prong and bezel heads, each a custom block that a runner notebook drops in. The API
lists `embed_custom_block`, `open_custom_block`, `list_custom_blocks`,
`current_open_custom_block`, `close_current_open_custom_block` and `move_block_to_body`, but
nothing we have read says how a block is created or what the calls take. This script finds
out, touching nothing outside `out/api/`:

1. the signature and docstring of every custom-block-related method (inspect);
2. what `list_custom_blocks()` returns in a fresh notebook;
3. builds a tiny would-be block notebook - input `Radius` (mm), a sphere, Output = the body -
   and saves it as `out/api/probe_block.ntop`;
4. in a second fresh notebook, tries `embed_custom_block` with that path in the argument forms
   that seem plausible, then `list_custom_blocks`, `list_available_blocks("probe")`,
   `open_custom_block` / `current_open_custom_block` / `close_current_open_custom_block`,
   and, if a block came in, sets its Radius and checks it builds.

Every call is wrapped: a refusal is recorded verbatim, not fatal. The result says which route
works; the library's build scripts are written to that route.
"""
from __future__ import annotations

import inspect
import json
import time
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
OUT = REPO / "out" / "api"
METHOD_WORDS = ("custom", "embed", "move_block_to_body", "import_recipe", "save_notebook", "open_notebook", "add_block")


def _try(log: list, label: str, fn, *args, **kw):
    try:
        v = fn(*args, **kw)
        log.append(f"OK   {label} -> {v!r}"[:1500])
        return True, v
    except Exception as e:
        log.append(f"FAIL {label} -> {type(e).__name__}: {e}"[:1500])
        return False, e


def _m(notebook, name):
    """The method, or a stand-in that raises (a missing method is a finding, not a crash)."""
    fn = getattr(notebook, name, None)
    if callable(fn):
        return fn
    def missing(*a, **k):
        raise AttributeError(f"this API has no notebook.{name}")
    return missing


def _describe(notebook) -> dict:
    out = {}
    for name in sorted(n for n in dir(notebook) if not n.startswith("_") and any(w in n for w in METHOD_WORDS)):
        fn = getattr(notebook, name, None)
        if not callable(fn):
            continue
        try:
            sig = str(inspect.signature(fn))
        except (TypeError, ValueError):
            sig = "(signature unavailable)"
        out[name] = {"signature": sig, "doc": (inspect.getdoc(fn) or "")[:2000]}
    return out


def build(notebook, params: dict | None = None) -> dict:
    p = {"block_path": str(OUT / "probe_block.ntop"), **(params or {})}
    OUT.mkdir(parents=True, exist_ok=True)
    log: list[str] = []
    summary: list[str] = []

    # 1. what the methods say about themselves
    methods = _describe(notebook)
    summary.append("custom-block related methods:")
    for name, d in methods.items():
        summary.append(f"  {name}{d['signature']}")
        if d["doc"]:
            summary.append("      " + d["doc"].replace("\n", "\n      ")[:600])

    # 2. a fresh notebook's view
    notebook.new_notebook()
    _try(log, "list_custom_blocks()", _m(notebook, "list_custom_blocks"))
    _try(log, "current_open_custom_block()", _m(notebook, "current_open_custom_block"))

    # 3. a would-be block: Radius input -> sphere -> Output body
    block_path = p["block_path"]
    ok_r, _ = _try(log, 'add_real_variable("Radius", 2.0, "mm")', notebook.add_real_variable, "Radius", 2.0, "mm")
    ok_s, sph = _try(log, 'add_block("sphere<point,real>")', notebook.add_block, "sphere<point,real>")
    if ok_r and ok_s:
        sid = sph["id"]
        _try(log, "set Center Point", notebook.set_block_input, sid, "Center Point", [0.0, 0.0, 0.0], "mm")
        _try(log, "wire Radius", notebook.connect_block_property, "Radius", "", sid, "Radius")
        _try(log, 'add_variable("Body", sphere)', notebook.add_variable, "Body", sid)
        _try(log, "move_block_to_input(Radius)", notebook.move_block_to_input, "Radius")
        _try(log, "set_block_as_output(Body)", notebook.set_block_as_output, "Body")
        time.sleep(1.0)
        _try(log, "block_state(sphere)", notebook.block_state, sid)
        _try(log, f"save_notebook_as({block_path})", notebook.save_notebook_as, block_path)
    block_saved = Path(block_path).exists()
    summary.append(f"block notebook saved: {block_saved} ({block_path})")

    # 4. use it from a second notebook
    notebook.new_notebook()
    before = set(notebook.list_available_blocks())
    embedded = None
    for label, args in (("embed_custom_block(path)", (block_path,)),
                        ("embed_custom_block(path, '')", (block_path, "")),
                        ("embed_custom_block(path, 'section_0')", (block_path, "section_0"))):
        ok, v = _try(log, label, _m(notebook, "embed_custom_block"), *args)
        if ok:
            embedded = v
            break
    _try(log, "list_custom_blocks() after embed", _m(notebook, "list_custom_blocks"))
    after = set(notebook.list_available_blocks())
    new_ids = sorted(after - before)
    log.append(f"identifiers that appeared after the embed: {new_ids}")
    _try(log, 'list_available_blocks("probe")', notebook.list_available_blocks, "probe")

    block_id = None
    if isinstance(embedded, dict) and embedded.get("id"):
        block_id = embedded["id"]
    for ident in new_ids:
        if block_id:
            break
        ok, v = _try(log, f"add_block({ident})", notebook.add_block, ident)
        if ok and isinstance(v, dict):
            block_id = v.get("id")
    if block_id:
        ok, ins = _try(log, f"list_block_inputs({block_id})", notebook.list_block_inputs, block_id)
        _try(log, "set Radius = 3 mm", notebook.set_block_input, block_id, "Radius", 3.0, "mm")
        time.sleep(1.0)
        _try(log, "block_state(custom block)", notebook.block_state, block_id)
        ok, _ = _try(log, f"open_custom_block({block_id})", _m(notebook, "open_custom_block"), block_id)
        _try(log, "current_open_custom_block()", _m(notebook, "current_open_custom_block"))
        if ok:
            _try(log, "list_blocks() inside", _m(notebook, "list_blocks"))
            _try(log, "close_current_open_custom_block()", _m(notebook, "close_current_open_custom_block"))
        _try(log, f"save_notebook_as(probe_user.ntop)", notebook.save_notebook_as, str(OUT / "probe_user.ntop"))

    verdict = ("a saved notebook embeds as a custom block and builds" if block_id and any("OK   block_state(custom" in l and "e_OK" in l for l in log)
               else "embedded but did not build - see the log" if block_id
               else "no route found to bring a block notebook in - see the log")
    summary.append(f"VERDICT: {verdict}")
    summary.append("call log:")
    summary.extend("  " + l for l in log)
    return {"summary": summary, "methods": methods, "log": log, "verdict": verdict, "new_identifiers": new_ids,
            "block_path": block_path, "block_saved": block_saved}
