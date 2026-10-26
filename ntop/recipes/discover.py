"""Discover what this nTop's Notebook API offers: identifiers and input names.

    python -m ntopjewel api build discover          # prints a digest; full dump in out/api/discover.result.json

Starts a fresh, unsaved notebook (new_notebook()), lists every available block identifier,
groups them by the keywords below, and — unless `--param probe=false` — adds the first few
matches of each keyword to the scratch notebook under paused updates to read their exact
input names and types. Nothing is saved. Also probes how variables are made (real variable,
empty variable, core.var text variable).
"""
from __future__ import annotations

KEYWORDS = [
    "point", "vector", "cylinder", "torus", "sphere", "box",
    "subtract", "union", "intersect", "boolean", "difference",
    "offset", "shell", "thicken", "fillet", "blend", "round",
    "mass", "volume", "properties",
    "mesh from", "mesh", "export", "import", "stl", "3mf",
    "text", "var", "variable", "list", "clearance", "remap", "cylindrical", "pattern", "array",
    "transform", "rotate", "translate", "mirror", "scale", "sweep", "revolve", "extrude", "loft",
]
PROBE_LIMIT = 3            # blocks probed per keyword
IMPLICIT = ["point", "cylinder", "torus", "subtract", "union", "intersect", "offset", "mass", "mesh from", "export", "text"]


def _short(s: str, n: int = 110) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def build(notebook, params: dict | None = None) -> dict:
    p = {"keywords": KEYWORDS, "probe": True, "probe_limit": PROBE_LIMIT, "fresh": True, **(params or {})}
    probe = str(p["probe"]).lower() not in ("false", "0", "no")
    summary: list[str] = []
    if p["fresh"]:
        notebook.new_notebook()

    # ---- the complete list, plus masked queries in case the unmasked one is partial ---------------
    all_ids = list(notebook.list_available_blocks())
    masked: dict[str, list[str]] = {}
    for kw in p["keywords"]:
        got: list[str] = []
        for m in dict.fromkeys([kw, kw.title()]):
            try:
                got.extend(notebook.list_available_blocks(m))
            except Exception as e:
                got.append(f"<error {e}>")
        masked[kw] = list(dict.fromkeys(got))
    merged = list(dict.fromkeys(all_ids + [i for v in masked.values() for i in v if not i.startswith("<error")]))
    by_kw = {kw: [i for i in merged if kw in i.lower()] for kw in p["keywords"]}
    summary.append(f"list_available_blocks(): {len(all_ids)} identifiers; merged with masked queries: {len(merged)}")
    extra = [i for i in merged if i not in all_ids]
    if extra:
        summary.append(f"  the unmasked list is PARTIAL: {len(extra)} identifiers only came back from masked queries")
    for kw in p["keywords"]:
        hits = by_kw[kw]
        if hits:
            summary.append(f"[{kw}] {len(hits)}:")
            summary.extend("    " + _short(h) for h in hits[:8])
            if len(hits) > 8:
                summary.append(f"    … {len(hits) - 8} more in the result file")
        else:
            summary.append(f"[{kw}] none")

    # ---- probe input names of the blocks we will use ---------------------------------------------
    probed: dict[str, dict] = {}
    variables: dict[str, object] = {}
    if probe:
        pause = getattr(notebook, "paused_updates", None)
        ctx = pause() if callable(pause) else _NoPause()
        with ctx:
            for kw in [k for k in p["keywords"] if k in IMPLICIT or k in ("boolean", "difference", "variable", "var")]:
                for ident in by_kw.get(kw, [])[: int(p["probe_limit"])]:
                    if ident in probed:
                        continue
                    try:
                        info = notebook.add_block(ident)
                        ins = notebook.list_block_inputs(info["id"])
                        probed[ident] = {"id": info["id"], "name": info.get("name"), "funcId": info.get("funcId"),
                                         "inputs": [(i.get("name"), i.get("type"), bool(i.get("isReturnValue"))) for i in ins]}
                    except Exception as e:
                        probed[ident] = {"error": str(e)}
            # how variables look
            for label, fn in (
                ("add_real_variable('Probe Real', 1.0, 'mm')", lambda: notebook.add_real_variable("Probe Real", 1.0, "mm")),
                ("add_variable('Probe Empty')", lambda: notebook.add_variable("Probe Empty")),
                ("add_block('core.var')", lambda: notebook.add_block("core.var")),
            ):
                try:
                    info = fn()
                    vid = info["id"] if isinstance(info, dict) else info
                    try:
                        ins = notebook.list_block_inputs(vid)
                        ins = [(i.get("name"), i.get("type"), bool(i.get("isReturnValue"))) for i in ins]
                    except Exception as e:
                        ins = f"list_block_inputs failed: {e}"
                    variables[label] = {"returned": info, "inputs": ins}
                    if label.startswith("add_block('core.var')"):
                        try:
                            notebook.set_block_input(vid, "Input", "C:/probe.stl")
                            variables[label]["set_text"] = "ok"
                        except Exception as e:
                            variables[label]["set_text"] = f"failed: {e}"
                except Exception as e:
                    variables[label] = {"error": str(e)}
            try:
                variables["list_variables()"] = notebook.list_variables()
            except Exception as e:
                variables["list_variables()"] = f"failed: {e}"
        summary.append("")
        summary.append("probed blocks (identifier -> inputs name:type):")
        for ident, d in probed.items():
            if "error" in d:
                summary.append(f"  {_short(ident)}  ERROR {d['error']}")
            else:
                ins = ", ".join(f"{n}:{t}" + ("(ret)" if r else "") for n, t, r in d["inputs"])
                summary.append(f"  {_short(ident)}  ->  {ins}")
        summary.append("variables:")
        for label, d in variables.items():
            summary.append(f"  {label}: {d}")

    return {"summary": summary, "count": len(all_ids), "merged_count": len(merged), "by_keyword": by_kw,
            "masked": masked, "probed": probed, "variables": variables, "all": merged}


class _NoPause:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False
