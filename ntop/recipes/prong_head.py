"""Phase 2 step 3: the `prong_head` library block and its harness.

    python -m ntopjewel api build stone_seat             # first, if ntop/blocks/stone_seat.ntop is not there
    python -m ntopjewel api build prong_head             # nTop open, View > Python Console open
    python -m ntopjewel api build prong_head --param bisect=true   # each build stage as its own block, test-embedded

1. Block `ntop/blocks/prong_head.ntop` (Seat Cutter is an implicit INPUT; no block inside):
       one prong   Cylinder Base -> Tip (Prong Radius) ∪ a sphere on each end
       prongs      Polar Array of it about +Z: Prong Count copies, Prong Spacing (deg) apart
       basket      ∪ two tori about Z: Upper Rail (Z, Radius), Lower Rail (Z, Radius), Rail Tube Radius,
                   the union blended by Blend Radius (prongs melt into the rails)
       seat        − Seat Cutter (the stone_seat block's output, wired in): trims the prongs back to the girdle line
                   above the girdle (the stone drops in) and leaves a ledge in each below it
       Output      Head (implicit)
2. Harness `ntop/notebooks/prong_head_harness.ntop`: Seat Path + Clearance (to an embedded
   stone_seat) and the 14 head numbers (to an embedded prong_head, with the seat's output as its
   cutter) + Mesh Tolerance + Output Path, measured (Volume Integral, Mesh, Export Mesh). Run by
   `python -m ntopjewel head ...` (ntopjewel.heads.build_head), gated for fit, ledges, drop-in
   and volume against the independent trimesh/manifold head.

Every number comes from ntopjewel.heads.HeadSpec; the notebook has no arithmetic. Both notebooks
carry embedded copies of the blocks they use: rebuild them (this script) after a block changes.
"""
from __future__ import annotations

from pathlib import Path

from ntopjewel import nb_jewel as nj
from ntopjewel.notebook_api import ConsoleError, NotebookHelper

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
TEST_ENVELOPE = REPO / "out" / "api" / "prong_head_test_envelope.stl"

# the block's numeric inputs; its first input is the seat cutter (implicit), wired in by whoever uses it
GEOMETRY_SPECS = [("Prong Count", "int"), ("Prong Spacing", "deg"),
                  ("Prong Radius", "mm"), ("Base X", "mm"), ("Base Y", "mm"), ("Base Z", "mm"),
                  ("Tip X", "mm"), ("Tip Y", "mm"), ("Tip Z", "mm"), ("Upper Rail Z", "mm"), ("Upper Rail Radius", "mm"),
                  ("Lower Rail Z", "mm"), ("Lower Rail Radius", "mm"), ("Rail Tube Radius", "mm"), ("Blend Radius", "mm")]
SEAT_SPECS = [("Seat Path", "path"), ("Clearance", "mm")]           # the harness's, for the stone_seat block
BLOCK_SPECS = SEAT_SPECS + GEOMETRY_SPECS                           # = the harness inputs before Mesh Tolerance
INPUT_ORDER = [n for n, _ in BLOCK_SPECS] + ["Mesh Tolerance", "Output Path"]
CUTTER_INPUT = "Seat Cutter"


def _test_values() -> dict:
    """6-prong head for a 6.5 mm round (ntopjewel.heads.HeadSpec defaults)."""
    from ntopjewel import gems, heads
    spec = heads.HeadSpec(gems.StoneSpec("round", 6.5), prongs=6)
    v = spec.notebook_inputs(str(TEST_ENVELOPE), "")
    v.pop("Output Path")
    return v


DEFAULTS = {
    "values": {},                       # filled by prepare() (laptop side) - nTop's Python has no trimesh
    "input_order": INPUT_ORDER,
    "test_output": str(REPO / "out" / "api" / "prong_head_test.stl"),
    "seat_block": str(REPO / "ntop" / "blocks" / "stone_seat.ntop"),
    "block_to": str(REPO / "ntop" / "blocks" / "prong_head.ntop"),
    "block_recipe_to": str(REPO / "ntop" / "recipes" / "prong_head.block.recipe.json"),
    "save_to": str(REPO / "ntop" / "notebooks" / "prong_head_harness.ntop"),
    "recipe_to": str(REPO / "ntop" / "recipes" / "prong_head_harness.recipe.json"),
    "pause": False,                     # embeds: no paused updates
    "lazy_ok": True,                    # the GUI may leave the head unbuilt; `head` under nTopCL is the test
    "fresh": True,
    "wait_s": 240,
    "volume_hint": "6-prong head, 6.5 mm round: 38.6 mm³ unblended + ~1.3 mm³ of blend (heads.design_mesh, blend_volume_mm3)",
}


def prepare(params: dict, work_dir: Path) -> dict:
    """Laptop side: the test seat envelope and every input value (heads.HeadSpec)."""
    from ntopjewel import gems, heads
    spec = heads.HeadSpec(gems.StoneSpec("round", 6.5), prongs=6)
    TEST_ENVELOPE.parent.mkdir(parents=True, exist_ok=True)
    spec.seat.envelope().export(str(TEST_ENVELOPE))
    params["values"] = {**_test_values(), **(params.get("values") or {})}
    return params


STAGES = ("point_sphere", "prong", "array", "basket", "cut_only", "full")


def _head_body(notebook, values: dict, stage: str = "full"):
    """Build the head block's body in a fresh notebook up to `stage`; returns (helper, body block,
    the input variables that stage uses). Stages, cumulative except cut_only:
        point_sphere  a sphere at the Base point (3 wired inputs) of Prong Radius
        prong         + Tip point, the rod, both end spheres, their union
        array         + Count, Spacing, Z axis, the polar array
        basket        + both rails and the basket union
        cut_only      a sphere at the origin minus the Seat Cutter input (the cutter on its own)
        full          the basket minus the Seat Cutter input: the block"""
    h = NotebookHelper(notebook)
    notebook.new_notebook()
    used = []

    def inp(name):
        if name not in h.blocks:
            kind = dict(GEOMETRY_SPECS)[name]
            nj.add_typed_inputs(h, [(name, kind)], values)
        if h.blocks[name] not in used:
            used.append(h.blocks[name])
        return h.blocks[name]

    def cutter_input():
        cut = notebook.add_block("core.var<implicit>")
        cid = cut["id"] if cut["id"] == CUTTER_INPUT else notebook.rename_variable(cut["id"], CUTTER_INPUT)["id"]
        h.blocks[CUTTER_INPUT] = cid
        h.identifiers[CUTTER_INPUT] = "core.var<implicit>"
        h.log.append(f"var {CUTTER_INPUT}: core.var<implicit> (an input: the seat cutter)")
        used.insert(0, cid)
        return cid

    def sphere(label, centre):
        s_ = h.add(label, nj.SPHERE, mask="sphere", must=[["sphere<point,real>"], ["sphere", "point", "real"]])
        h.wire(centre, s_, ["Center Point", "Center", "Point"])
        h.wire(inp("Prong Radius"), s_, ["Radius"])
        return s_

    if stage == "cut_only":
        cutter = cutter_input()
        ball = sphere("Ball", nj.point_block(h, "Origin"))
        body = h.add("Seated", mask="subtract", must=nj.SUBTRACT)
        h.wire(ball, body, ["Primary Body", "Body"])
        h.to_list(cutter, body, ["Subtraction Bodies", "Bodies"])
        return h, body, used

    cutter = cutter_input() if stage == "full" else None
    # a block output used twice goes through a variable - in a custom block this is not optional:
    # the stage that fed one Point to both the rod and a sphere was refused (bisect, 2026-10-28)
    base = h.wrap_var("Base Point", nj.point_from_vars(h, "Base", inp("Base X"), inp("Base Y"), inp("Base Z")))
    foot = sphere("Prong Foot", base)
    if stage == "point_sphere":
        return h, foot, used
    tip = h.wrap_var("Tip Point", nj.point_from_vars(h, "Tip", inp("Tip X"), inp("Tip Y"), inp("Tip Z")))
    rod = h.add("Prong Rod", nj.CYLINDER, mask="cylinder", must=[["cylinder", "point,point,real"]])
    h.wire(base, rod, ["Point 1"])
    h.wire(tip, rod, ["Point 2"])
    h.wire(inp("Prong Radius"), rod, ["Radius"])
    tip_ball = sphere("Prong Tip", tip)
    prong = h.add("Prong", mask="union", must=nj.UNION)
    for b in (rod, foot, tip_ball):
        h.to_list(b, prong, ["Bodies"])
    if stage == "prong":
        return h, prong, used
    prongs = h.add("Prongs", mask="polar_array", must=nj.POLAR_ARRAY)
    h.wire(prong, prongs, ["Body"])
    h.wire(inp("Prong Spacing"), prongs, ["Angular Spacing", "Angular spacing", "Angle", "Spacing"])
    h.wire(inp("Prong Count"), prongs, ["Count", "Number", "Copies"])
    h.wire(nj.z_axis(h), prongs, ["Axis"])
    if stage == "array":
        return h, prongs, used
    rails = []
    for label, zk, rk in (("Upper Rail", "Upper Rail Z", "Upper Rail Radius"), ("Lower Rail", "Lower Rail Z", "Lower Rail Radius")):
        c = nj.point_block(h, f"{label} Centre", z_var=inp(zk))
        t = h.add(label, nj.TORUS, mask="torus", must=[["torus", "point", "vector"], ["torus"]])
        h.wire(c, t, ["Center"])
        nj.set_axis(h, t)
        h.wire(inp(rk), t, ["Radius"])
        h.wire(inp("Rail Tube Radius"), t, ["Torus Radius", "Torus radius", "Tube"])
        rails.append(t)
    basket = h.add("Basket", mask="union", must=nj.UNION)
    for b in (prongs, *rails):
        h.to_list(b, basket, ["Bodies"])
    nj.wire_blend(h, basket, inp("Blend Radius"))              # prongs melt into the rails (a real_field: wired, not set)
    if stage == "basket":
        return h, basket, used
    head = h.add("Seated", mask="subtract", must=nj.SUBTRACT)
    h.wire(basket, head, ["Primary Body", "Body"])
    h.to_list(cutter, head, ["Subtraction Bodies", "Bodies"])
    return h, head, used


def _finish_block(notebook, h, body, used, path: str, recipe: str | None = None) -> list[str]:
    """Typed Output, inputs in the catalog's order, save (and recipe); returns warnings."""
    out = h.wrap_var("Head", body)
    order = [h.blocks[CUTTER_INPUT]] if CUTTER_INPUT in h.blocks else []
    order += [h.blocks[n] for n, _ in GEOMETRY_SPECS if n in h.blocks]
    h.declare_inputs([i for i in order if i in used])
    h.set_output(out)
    warnings = nj.settle(h, body, "the block's Output")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    notebook.save_notebook_as(path)
    if recipe:
        try:
            notebook.export_as_recipe(recipe, True)
        except Exception as e:
            h.log.append(f"export_as_recipe (block) failed: {e}")
    if not Path(path).exists():
        raise ConsoleError(f"the block was not saved to {path}")
    return warnings


def bisect(notebook, values: dict, out_dir: Path) -> dict:
    """Build each stage as its own block notebook and test-embed it: the first refused stage names
    the construct nTop will not take in a custom block."""
    summary, results = [], {}
    for stage in STAGES:
        rec = {}
        try:
            h, body, used = _head_body(notebook, values, stage)
            path = str(Path(out_dir) / f"head_stage_{stage}.ntop")
            rec["warnings"] = _finish_block(notebook, h, body, used, path)
            rec["inputs"] = len(used)
            try:
                rec["embed"] = embed_self_test(notebook, path)
            except ConsoleError as e:
                rec["embed"] = f"REFUSED: {e}"[:400]
        except Exception as e:
            rec["build_error"] = f"{type(e).__name__}: {e}"[:400]
        results[stage] = rec
        emb = rec.get("embed")
        summary.append(f"{stage:13} inputs {rec.get('inputs', '-'):>2}  " +
                       ("embed: ok" if isinstance(emb, dict) else f"embed: {emb or rec.get('build_error')}"))
    return {"summary": summary, "results": results}


def build_block(notebook, p: dict, values: dict) -> dict:
    """The head block: Seat Cutter (implicit input) + 14 numbers -> Head. It holds no other block;
    a bezel can reuse the same seat cutter."""
    h, head, used = _head_body(notebook, values, "full")
    warnings = _finish_block(notebook, h, head, used, p["block_to"], p["block_recipe_to"])
    self_test = embed_self_test(notebook, p["block_to"])
    h.log.append(f"self-test: {self_test}")
    return {"saved": p["block_to"], "recipe": p["block_recipe_to"], "identifiers": h.identifiers, "warnings": warnings,
            "self_test": self_test, "blocks": h.blocks, "states": h.states(0), "log": h.log}


def embed_self_test(notebook, block_path: str) -> dict:
    """Embed the saved block into a fresh notebook at once, so a block nTop will not accept is
    named here rather than as a harness failure later."""
    notebook.new_notebook()
    try:
        notebook.embed_custom_block(block_path)
    except Exception as e:
        raise ConsoleError(f"nTop refuses the saved block as a custom block: {e}") from e
    blocks = [b for b in notebook.list_custom_blocks() if b.get("name") == Path(block_path).stem]
    if not blocks:
        raise ConsoleError(f"embedded {block_path} but list_custom_blocks() does not name it")
    return {"accepted": True, "id": blocks[0]["id"]}


def _harness(h, p, values, test_output):
    """Harness: the stone_seat block cuts, the prong_head block takes that cutter + its numbers."""
    ids = nj.add_typed_inputs(h, BLOCK_SPECS + [("Mesh Tolerance", "mm")], values)
    out_var = nj.path_variable(h, "Output Path", test_output)
    seat = h.add("Stone Seat", h.embed_block(p["seat_block"]))
    for name, _ in SEAT_SPECS:
        h.wire(ids[name], seat, [name])
    head = h.add("Prong Head", h.embed_block(p["block_to"]))
    h.wire(seat, head, [CUTTER_INPUT])
    for name, _ in GEOMETRY_SPECS:
        h.wire(ids[name], head, [name])
    body = h.wrap_var("Result", head)
    integ, _mesh, export = nj.add_measure_mesh_export(h, body, out_var, ids["Mesh Tolerance"])
    return integ, export


def build(notebook, params: dict | None = None) -> dict:
    """Entry point for `api build prong_head`: the block, then its harness."""
    params = dict(params or {})
    if "save_to" in params and "block_to" not in params:          # --scratch: the block beside the harness
        params["block_to"] = str(Path(params["save_to"]).parent / "prong_head.ntop")
        params.setdefault("block_recipe_to", str(Path(params["save_to"]).parent / "prong_head.block.recipe.json"))
    p = {**DEFAULTS, **params}
    values = {**DEFAULTS["values"], **(p.get("values") or {})}
    if not values:
        raise ConsoleError("no input values: run through `python -m ntopjewel api build prong_head` (prepare() computes them)")
    for key in ("block_to", "block_recipe_to", "seat_block"):
        p[key] = nj.absolute(p[key])
    if not Path(p["seat_block"]).exists():
        raise ConsoleError(f"{p['seat_block']} is missing: run `python -m ntopjewel api build stone_seat` first")
    p["values"] = values
    if p.get("bisect"):                     # `api build prong_head --param bisect=true`
        return bisect(notebook, values, REPO / "out" / "api" / "head_stages")
    block = build_block(notebook, p, values)
    res = nj.run_build(notebook, p, {**DEFAULTS, "values": values}, _harness)
    res["block"] = block
    res["warnings"] = block.get("warnings", []) + res.get("warnings", [])
    return res
