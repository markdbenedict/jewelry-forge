"""Phase 2 gate notebook: `ntop/notebooks/solitaire.ntop` - a prong head on a profiled band with
cathedral shoulders.

    python -m ntopjewel api build stone_seat ; python -m ntopjewel api build prong_head   # the blocks, first
    python -m ntopjewel api build solitaire                                              # nTop open, Python Console open
    python -m ntopjewel solitaire --size 6 --length 6.5 --prongs 6                      # then run and gate a ring

    band       the profiled band (11 inputs) -> Band Body
    seat       stone_seat(Seat Path, Clearance), embedded -> Seat Local (head frame)
    head       prong_head(Seat Local + 14 numbers), embedded -> head frame
    placement  Rotation Transform: 90° about the line through (Pivot X, 0, Pivot Z) parallel to +Y;
               Transform Object puts the head and the seat on the ring (head +Z -> ring +X)
    shoulders  Cylinder along Z (centre Cathedral X, radius Cathedral Radius) ∩ the comfort torus
    ring       ((Band Body ∪ shoulders) - placed seat) ∪ placed head -> Volume, Mesh, Export

Every number comes from ntopjewel.solitaire.SolitaireSpec; the notebook has no arithmetic. It
embeds copies of both blocks: rebuild it after either block changes.
"""
from __future__ import annotations

from pathlib import Path

from ntopjewel import nb_jewel as nj
from ntopjewel.notebook_api import ConsoleError

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
TEST_ENVELOPE = REPO / "out" / "api" / "solitaire_test_envelope.stl"

HEAD_GEOMETRY = [("Prong Count", "int"), ("Prong Spacing", "deg"), ("Prong Radius", "mm"),
                 ("Base X", "mm"), ("Base Y", "mm"), ("Base Z", "mm"), ("Tip X", "mm"), ("Tip Y", "mm"), ("Tip Z", "mm"),
                 ("Upper Rail Z", "mm"), ("Upper Rail Radius", "mm"), ("Lower Rail Z", "mm"), ("Lower Rail Radius", "mm"),
                 ("Rail Tube Radius", "mm")]
SPECS = ([(n, "mm") for n in nj.BAND_INPUTS] + [("Seat Path", "path"), ("Clearance", "mm")] + HEAD_GEOMETRY
         + [("Pivot X", "mm"), ("Pivot Z", "mm"), ("Cathedral X", "mm"), ("Cathedral Radius", "mm")])
INPUT_ORDER = [n for n, _ in SPECS] + ["Output Path"]


def _spec():
    from ntopjewel import band, gems, heads, solitaire
    return solitaire.SolitaireSpec(band.BandSpec(size=6, profile="court", mesh_tolerance_mm=0.05),
                                   heads.HeadSpec(gems.StoneSpec("round", 6.5), prongs=6))


DEFAULTS = {
    "values": {},                       # prepare() (laptop side) computes them
    "input_order": INPUT_ORDER,
    "test_output": str(REPO / "out" / "api" / "solitaire_test.stl"),
    "seat_block": str(REPO / "ntop" / "blocks" / "stone_seat.ntop"),
    "head_block": str(REPO / "ntop" / "blocks" / "prong_head.ntop"),
    "save_to": str(REPO / "ntop" / "notebooks" / "solitaire.ntop"),
    "recipe_to": str(REPO / "ntop" / "recipes" / "solitaire.recipe.json"),
    "pause": False,                     # embeds blocks: no paused updates
    "lazy_ok": True,                    # nTopCL (`solitaire` command) is the test
    "fresh": True,
    "wait_s": 240,
    "volume_hint": "US6 court, 6.5 mm round, 6 prongs: 314 mm³ (solitaire.design_mesh)",
}


def prepare(params: dict, work_dir: Path) -> dict:
    spec = _spec()
    TEST_ENVELOPE.parent.mkdir(parents=True, exist_ok=True)
    spec.head.seat.envelope().export(str(TEST_ENVELOPE))
    v = spec.notebook_inputs(str(TEST_ENVELOPE))
    params["values"] = {**v, **(params.get("values") or {})}
    return params


def _body(h, p, values, test_output):
    ids = nj.add_typed_inputs(h, SPECS, values)
    out_var = nj.path_variable(h, "Output Path", test_output)
    band = nj.add_profiled_band(h)

    seat = h.add("Stone Seat", h.embed_block(p["seat_block"]))
    h.wire(ids["Seat Path"], seat, ["Seat Path"])
    h.wire(ids["Clearance"], seat, ["Clearance"])
    seat_local = h.wrap_var("Seat Local", seat)                 # used twice: the head's cutter and the shank's
    head = h.add("Prong Head", h.embed_block(p["head_block"]))
    h.wire(seat_local, head, ["Seat Cutter"])
    for name, _ in HEAD_GEOMETRY:
        h.wire(ids[name], head, [name])

    pivot = nj.point_block(h, "Pivot", x_var=ids["Pivot X"], z_var=ids["Pivot Z"])
    rot = h.add("Head Placement", mask="rotation_transform", must=nj.ROTATION_TRANSFORM)
    h.wire(pivot, rot, [h.input_of_type(rot, "point")])
    h.set(rot, [h.input_of_type(rot, "vector")], [0.0, 1.0, 0.0])
    angle = nj.angle_variable(h, "Head Angle", 90.0)            # a constant, not an input
    h.wire(angle, rot, [h.input_of_type(rot, "real")])
    placement = h.wrap_var("Placement", rot)                    # used twice
    placed = {}
    for label, body in (("Placed Head", head), ("Placed Seat", seat_local)):
        t = h.add(label, mask="transform_object", must=nj.TRANSFORM_OBJECT)
        h.wire(body, t, [h.input_of_type(t, "spatial3d")])
        h.wire(placement, t, [h.input_of_type(t, "transformation")])
        placed[label] = t

    lo = nj.point_block(h, "Cathedral Bottom", x_var=ids["Cathedral X"], z_var=ids["Z Bottom"])
    hi = nj.point_block(h, "Cathedral Top", x_var=ids["Cathedral X"], z_var=ids["Z Top"])
    arc = h.add("Cathedral Arc", nj.CYLINDER, mask="cylinder", must=[["cylinder", "point,point,real"]])
    h.wire(lo, arc, ["Point 1"])
    h.wire(hi, arc, ["Point 2"])
    h.wire(ids["Cathedral Radius"], arc, ["Radius"])
    torus = h.add("Shoulder Comfort", nj.TORUS, mask="torus", must=[["torus", "point", "vector"], ["torus"]])
    h.set(torus, ["Center"], [0.0, 0.0, 0.0], "mm")
    nj.set_axis(h, torus)
    h.wire(ids["Comfort Ring Radius"], torus, ["Radius"])
    h.wire(ids["Comfort Tube Radius"], torus, ["Torus Radius", "Torus radius", "Tube"])
    shoulders = h.add("Shoulders", mask="intersect", must=nj.INTERSECT)
    h.to_list(arc, shoulders, ["Bodies"])
    h.to_list(torus, shoulders, ["Bodies"])

    shank = h.add("Shank", mask="union", must=nj.UNION)
    h.to_list(band, shank, ["Bodies"])
    h.to_list(shoulders, shank, ["Bodies"])
    seated = h.add("Seated Shank", mask="subtract", must=nj.SUBTRACT)
    h.wire(shank, seated, ["Primary Body", "Body"])
    h.to_list(placed["Placed Seat"], seated, ["Subtraction Bodies", "Bodies"])
    ring = h.add("Ring", mask="union", must=nj.UNION)
    h.to_list(seated, ring, ["Bodies"])
    h.to_list(placed["Placed Head"], ring, ["Bodies"])
    body = h.wrap_var("Ring Body", ring)
    integ, _mesh, export = nj.add_measure_mesh_export(h, body, out_var, ids["Mesh Tolerance"])
    return integ, export


def build(notebook, params: dict | None = None) -> dict:
    p = {**DEFAULTS, **(params or {})}
    values = {**DEFAULTS["values"], **(p.get("values") or {})}
    if not values:
        raise ConsoleError("no input values: run through `python -m ntopjewel api build solitaire` (prepare() computes them)")
    for key in ("seat_block", "head_block"):
        p[key] = nj.absolute(p[key])
        if not Path(p[key]).exists():
            raise ConsoleError(f"{p[key]} is missing: build it first (api build stone_seat / prong_head)")
    p["values"] = values
    return nj.run_build(notebook, p, {**DEFAULTS, "values": values}, _body)
