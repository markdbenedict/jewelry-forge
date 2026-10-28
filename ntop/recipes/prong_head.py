"""Phase 2 step 3: the `prong_head` library block and its harness.

    python -m ntopjewel api build stone_seat             # first, if ntop/blocks/stone_seat.ntop is not there
    python -m ntopjewel api build prong_head             # nTop open, View > Python Console open

1. Block `ntop/blocks/prong_head.ntop` (embeds `stone_seat`):
       one prong   Cylinder Base -> Tip (Prong Radius) ∪ a sphere on each end
       prongs      Polar Array of it about +Z: Prong Count copies, Prong Spacing (deg) apart
       basket      ∪ two tori about Z: Upper Rail (Z, Radius), Lower Rail (Z, Radius), Rail Tube Radius
       seat        − stone_seat(Seat Path, Clearance): trims the prongs back to the girdle line
                   above the girdle (the stone drops in) and leaves a ledge in each below it
       Output      Head (implicit)
2. Harness `ntop/notebooks/prong_head_harness.ntop`: the block's 16 inputs + Mesh Tolerance +
   Output Path, the block embedded and measured (Volume Integral, Mesh, Export Mesh). Run by
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

BLOCK_SPECS = [("Seat Path", "path"), ("Clearance", "mm"), ("Prong Count", "int"), ("Prong Spacing", "deg"),
               ("Prong Radius", "mm"), ("Base X", "mm"), ("Base Y", "mm"), ("Base Z", "mm"),
               ("Tip X", "mm"), ("Tip Y", "mm"), ("Tip Z", "mm"), ("Upper Rail Z", "mm"), ("Upper Rail Radius", "mm"),
               ("Lower Rail Z", "mm"), ("Lower Rail Radius", "mm"), ("Rail Tube Radius", "mm")]
INPUT_ORDER = [n for n, _ in BLOCK_SPECS] + ["Mesh Tolerance", "Output Path"]


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
    "fresh": True,
    "wait_s": 240,
    "volume_hint": "6-prong head, 6.5 mm round: 38.6 mm³ (heads.design_mesh)",
}


def prepare(params: dict, work_dir: Path) -> dict:
    """Laptop side: the test seat envelope and every input value (heads.HeadSpec)."""
    from ntopjewel import gems, heads
    spec = heads.HeadSpec(gems.StoneSpec("round", 6.5), prongs=6)
    TEST_ENVELOPE.parent.mkdir(parents=True, exist_ok=True)
    spec.seat.envelope().export(str(TEST_ENVELOPE))
    params["values"] = {**_test_values(), **(params.get("values") or {})}
    return params


def build_block(notebook, p: dict, values: dict) -> dict:
    h = NotebookHelper(notebook)
    notebook.new_notebook()
    v = nj.add_typed_inputs(h, BLOCK_SPECS, values)

    base = nj.point_from_vars(h, "Base", v["Base X"], v["Base Y"], v["Base Z"])
    tip = nj.point_from_vars(h, "Tip", v["Tip X"], v["Tip Y"], v["Tip Z"])
    rod = h.add("Prong Rod", nj.CYLINDER, mask="cylinder", must=[["cylinder", "point,point,real"]])
    h.wire(base, rod, ["Point 1"])
    h.wire(tip, rod, ["Point 2"])
    h.wire(v["Prong Radius"], rod, ["Radius"])
    ends = []
    for label, pt in (("Prong Foot", base), ("Prong Tip", tip)):
        s = h.add(label, nj.SPHERE, mask="sphere", must=[["sphere<point,real>"], ["sphere", "point", "real"]])
        h.wire(pt, s, ["Center Point", "Center", "Point"])
        h.wire(v["Prong Radius"], s, ["Radius"])
        ends.append(s)
    prong = h.add("Prong", mask="union", must=nj.UNION)
    for b in (rod, *ends):
        h.to_list(b, prong, ["Bodies"])
    axis = nj.z_axis(h)
    prongs = h.add("Prongs", mask="polar_array", must=nj.POLAR_ARRAY)
    h.wire(prong, prongs, ["Body"])
    h.wire(v["Prong Spacing"], prongs, ["Angular Spacing", "Angular spacing", "Angle", "Spacing"])
    h.wire(v["Prong Count"], prongs, ["Count", "Number", "Copies"])
    h.wire(axis, prongs, ["Axis"])

    rails = []
    for label, zk, rk in (("Upper Rail", "Upper Rail Z", "Upper Rail Radius"), ("Lower Rail", "Lower Rail Z", "Lower Rail Radius")):
        c = nj.point_block(h, f"{label} Centre", z_var=v[zk])
        t = h.add(label, nj.TORUS, mask="torus", must=[["torus", "point", "vector"], ["torus"]])
        h.wire(c, t, ["Center"])
        nj.set_axis(h, t)
        h.wire(v[rk], t, ["Radius"])
        h.wire(v["Rail Tube Radius"], t, ["Torus Radius", "Torus radius", "Tube"])
        rails.append(t)
    basket = h.add("Basket", mask="union", must=nj.UNION)
    for b in (prongs, *rails):
        h.to_list(b, basket, ["Bodies"])

    seat_ident = h.embed_block(p["seat_block"])
    seat = h.add("Seat", seat_ident)
    h.wire(v["Seat Path"], seat, ["Seat Path"])
    h.wire(v["Clearance"], seat, ["Clearance"])
    head = h.add("Seated", mask="subtract", must=nj.SUBTRACT)
    h.wire(basket, head, ["Primary Body", "Body"])
    h.to_list(seat, head, ["Subtraction Bodies", "Bodies"])

    out = h.wrap_var("Head", head)
    h.declare_inputs(list(v.values()))
    h.set_output(out)
    h.assert_ok(head, p["wait_s"])
    Path(p["block_to"]).parent.mkdir(parents=True, exist_ok=True)
    notebook.save_notebook_as(p["block_to"])
    try:
        notebook.export_as_recipe(p["block_recipe_to"], True)
    except Exception as e:
        h.log.append(f"export_as_recipe (block) failed: {e}")
    if not Path(p["block_to"]).exists():
        raise ConsoleError(f"the block was not saved to {p['block_to']}")
    return {"saved": p["block_to"], "recipe": p["block_recipe_to"], "identifiers": h.identifiers,
            "blocks": h.blocks, "states": h.states(10), "log": h.log}


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
    block = build_block(notebook, p, values)
    res = nj.run_build(notebook, p, {**DEFAULTS, "values": values},
                       lambda h, pp, vals, out: nj.harness(h, pp, vals, out, p["block_to"], BLOCK_SPECS, "Prong Head"))
    res["block"] = block
    return res
