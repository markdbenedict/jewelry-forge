"""Build `multistone.ntop` through nTop's Notebook API: a centre stone and side stones in a row - Phase 3
step 2 (ntopjewel.multistone; reference rings 05 and 02).

    shank      Shank Path .. Shank Path 4 -> the band exactly as ring_shank.ntop builds it
               (nj.add_wrapped_shank: each bar opened on its own, united, wrapped) = Shank Body
    slots      five, each: stone_seat(Seat Path k, Clearance) -> Seat k (head frame, used twice);
               outline_head(Seat k, Prongs Path k, Rail Offset k, Upper/Lower Rail Bottom/Top k,
               Head Blend) -> Head k; both moved by three transforms in turn:
                 Spin k        Rotation Transform about the head's +Z through the origin
                 Placement k   Rotation Transform 90° about the line through (Pivot X k, 0, Pivot Z k) ∥ +Y
                 Turn k        Rotation Transform about the ring axis +Z through the origin
               An unused slot repeats the centre's values: the same head in the same place
    ring       ((Shank Body ∪ every placed head), blended by Shank Blend) − every placed seat
               -> Volume Integral of 1 (Output "Volume"), Mesh (Mesh Tolerance), Export Mesh (Output Path).
               The seats are cut AFTER the blended join: a smooth union fills every corner within its
               radius, the seats' included

Both blocks are embedded once (`api build stone_seat`, `api build outline_head` first) and placed five
times; rebuild this notebook after either block changes. Every number comes from
ntopjewel.multistone.MultiStoneSpec.notebook_inputs; the notebook has no arithmetic.

Run:  python -m ntopjewel api build multistone      (nTop open, View > Python Console open, in the foreground)
      python -m ntopjewel multistone --size 6 --shape cushion --length 7 --stone-width 6 --side-shape pear --side-length 6 --side-width 4
"""
from __future__ import annotations

from pathlib import Path

from ntopjewel import multistone as ms
from ntopjewel import nb_jewel as nj
from ntopjewel.notebook_api import ConsoleError

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
TEST_DIR = REPO / "out" / "api"
TEST_STEM = "multistone_test"
SPECS = ms.specs()
INPUT_ORDER = ms.input_order()
RAILS = ("Rail Offset", "Upper Rail Bottom", "Upper Rail Top", "Lower Rail Bottom", "Lower Rail Top")


def _spec():
    from ntopjewel import band, gems, heads
    b = band.BandSpec(size=6, width_mm=2.6, thickness_mm=1.8, profile="court", mesh_tolerance_mm=0.05)
    return ms.MultiStoneSpec(b, heads.OutlineHeadSpec(gems.StoneSpec("round", 6.5)),
                             heads.OutlineHeadSpec(gems.StoneSpec("round", 4.0)))


DEFAULTS = {
    "values": {},                       # prepare() (laptop side) computes them
    "input_order": INPUT_ORDER,
    "test_output": str(REPO / "out" / "api" / "multistone_test.stl"),
    "seat_block": str(REPO / "ntop" / "blocks" / "stone_seat.ntop"),
    "head_block": str(REPO / "ntop" / "blocks" / "outline_head.ntop"),
    "save_to": str(REPO / "ntop" / "notebooks" / "multistone.ntop"),
    "recipe_to": str(REPO / "ntop" / "recipes" / "multistone.recipe.json"),
    "pause": False,                     # embeds blocks: no paused updates
    "show": ["Ring Body"],
    "lazy_ok": True,                    # nTopCL (`multistone` command) is the test
    "fresh": True,
    "wait_s": 300,
    "volume_hint": "US6 court 2.6 x 1.8, round 6.5 centre + two 4 mm rounds: see `multistone --dry-run`",
}


def prepare(params: dict, work_dir: Path) -> dict:
    """Laptop side: the test ring's bars, each head's envelope and prongs, and every input value."""
    from ntopjewel import shank
    spec = _spec()
    TEST_DIR.mkdir(parents=True, exist_ok=True)
    bars = shank.write_bars(spec.shank_spec, TEST_DIR, TEST_STEM)
    files = spec.write_slot_files(TEST_DIR, TEST_STEM)
    v = spec.notebook_inputs(bars, files)
    v.pop("Output Path")
    params["values"] = {**v, **(params.get("values") or {})}
    return params


def _rotation(h, label: str, angle_var: str, axis, point=None) -> str:
    rot = h.add(label, mask="rotation_transform", must=nj.ROTATION_TRANSFORM)
    if point is None:
        h.set(rot, [h.input_of_type(rot, "point")], [0.0, 0.0, 0.0], "mm")
    else:
        h.wire(point, rot, [h.input_of_type(rot, "point")])
    h.set(rot, [h.input_of_type(rot, "vector")], list(axis))
    h.wire(angle_var, rot, [h.input_of_type(rot, "real")])
    return h.wrap_var(f"{label} T", rot)                            # each moves a head and its seat: used twice


def _moved(h, label: str, body: str, transforms: list[str]) -> str:
    cur = body
    for i, t in enumerate(transforms):
        obj = h.add(f"{label} {i + 1}", mask="transform_object", must=nj.TRANSFORM_OBJECT)
        h.wire(cur, obj, [h.input_of_type(obj, "spatial3d")])
        h.wire(t, obj, [h.input_of_type(obj, "transformation")])
        cur = obj
    return cur


def _body(h, p, values, test_output):
    ids = nj.add_typed_inputs(h, SPECS, values)
    out_var = nj.path_variable(h, "Output Path", test_output)
    shank_body = h.wrap_var("Shank Body", nj.add_wrapped_shank(h, [ids[n] for n in nj.SLOT_NAMES], ids["Wrap Length"],
                                                               ids["Edge Round Inward"], ids["Edge Round"], ids["Mesh Tolerance"]))
    seat_fn = h.embed_block(p["seat_block"])
    head_fn = h.embed_block(p["head_block"])
    quarter = nj.angle_variable(h, "Quarter Turn", 90.0)          # a constant, not an input
    placed_heads, placed_seats = [], []
    for k in range(ms.SLOTS):
        def i(name):
            return ids[ms.slot_input(name, k)]
        tag = f" {k + 1}"
        seat = h.add(f"Stone Seat{tag}", seat_fn)
        h.wire(i("Seat Path"), seat, ["Seat Path"])
        h.wire(ids["Clearance"], seat, ["Clearance"])
        seat_local = h.wrap_var(f"Seat Local{tag}", seat)
        head = h.add(f"Outline Head{tag}", head_fn)
        h.wire(seat_local, head, ["Seat Cutter"])                  # the clearance is in the cutter already
        h.wire(i("Prongs Path"), head, ["Prongs Path"])
        for name in RAILS:
            h.wire(i(name), head, [name])
        h.wire(ids["Head Blend"], head, ["Blend Radius"])
        spin = _rotation(h, f"Spin Rotation{tag}", i("Spin"), (0.0, 0.0, 1.0))      # labels never an input's name
        pivot = nj.point_block(h, f"Pivot{tag}", x_var=i("Pivot X"), z_var=i("Pivot Z"))
        place = _rotation(h, f"Placement{tag}", quarter, (0.0, 1.0, 0.0), point=pivot)
        turn = _rotation(h, f"Turn Rotation{tag}", i("Turn"), (0.0, 0.0, 1.0))
        placed_heads.append(_moved(h, f"Placed Head{tag}", head, [spin, place, turn]))
        placed_seats.append(_moved(h, f"Placed Seat{tag}", seat_local, [spin, place, turn]))
    heads_union = h.add("Heads", mask="union", must=nj.UNION)
    for ph in placed_heads:
        h.to_list(ph, heads_union, ["Bodies"])
    joined = h.add("Joined", mask="union", must=nj.UNION)
    h.to_list(shank_body, joined, ["Bodies"])
    h.to_list(heads_union, joined, ["Bodies"])
    nj.wire_blend(h, joined, ids["Shank Blend"])
    ring = h.add("Ring", mask="subtract", must=nj.SUBTRACT)
    h.wire(joined, ring, ["Primary Body", "Body"])
    for ps in placed_seats:
        h.to_list(ps, ring, ["Subtraction Bodies", "Bodies"])
    out = h.wrap_var("Ring Body", ring)
    integ, _mesh, export = nj.add_measure_mesh_export(h, out, out_var, ids["Mesh Tolerance"])
    return integ, export


def build(notebook, params: dict | None = None) -> dict:
    """Entry point for `api build multistone`; see the module docstring."""
    p = {**DEFAULTS, **(params or {})}
    values = {**DEFAULTS["values"], **(p.get("values") or {})}
    if not values:
        raise ConsoleError("no input values: run through `python -m ntopjewel api build multistone` (prepare() computes them)")
    for key in ("seat_block", "head_block"):
        p[key] = nj.absolute(p[key])
        if not Path(p[key]).exists():
            raise ConsoleError(f"{p[key]} is missing: build it first (api build stone_seat / {Path(p[key]).stem})")
    p["values"] = values
    return nj.run_build(notebook, p, {**DEFAULTS, "values": values}, _body)
