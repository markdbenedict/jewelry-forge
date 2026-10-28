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
    arch       per side: Cylinder (Arch Radius) ∩ Torus (Arch Dome Ring Radius / Dome Tube Radius) about
               (Arch Centre X, Arch Centre Y[ Minus]) - the band's section swept round the arch circle;
               both sides ∩ a wedge (two corner boxes turned by ±Wedge Angle about +Z) - a cylinder of
               Arch Cut Radius; united with the shaped band BEFORE the edge-round offsets (seamless)
    milgrain   per side: two spheres at (Bead Start X[ Minus], Bead Start Y[ Minus], ±Bead Z) -> Polar
               Array (Bead Count, Bead Spacing) about the axis through that arch's centre ∥ Z
    ring       ((Band Body ∪ milgrain) - placed seat) ∪ placed head -> Volume, Mesh, Export

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
         + [("Pivot X", "mm"), ("Pivot Z", "mm"),
            ("Arch Centre X", "mm"), ("Arch Centre Y", "mm"), ("Arch Centre Y Minus", "mm"), ("Arch Radius", "mm"),
            ("Arch Dome Ring Radius", "mm"), ("Arch Cut Radius", "mm"), ("Wedge Angle", "deg"), ("Wedge Angle Minus", "deg"),
            ("Bead Radius", "mm"), ("Bead Z", "mm"), ("Bead Z Minus", "mm"), ("Bead Spacing", "deg"), ("Bead Count", "int"),
            ("Bead Start X", "mm"), ("Bead Start Y", "mm"), ("Bead Start X Minus", "mm"), ("Bead Start Y Minus", "mm")])
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
    "show": ["Ring", "Ring Body"],      # the GUI shows the finished ring only (the seat cutter, the unplaced head
                                        # and the construction points stay hidden; they still build)
    "lazy_ok": True,                    # nTopCL (`solitaire` command) is the test
    "fresh": True,
    "wait_s": 240,
    "volume_hint": "US6 court, 6.5 mm round, 6 prongs, arch milgrain: 287 mm³ (solitaire.design_mesh)",
}


def prepare(params: dict, work_dir: Path) -> dict:
    spec = _spec()
    TEST_ENVELOPE.parent.mkdir(parents=True, exist_ok=True)
    spec.head.seat.envelope().export(str(TEST_ENVELOPE))
    v = spec.notebook_inputs(str(TEST_ENVELOPE))
    params["values"] = {**v, **(params.get("values") or {})}
    return params


def _arches(ids):
    """The cathedral arches (see the module doc). Returns a builder for add_profiled_band(extra=)."""
    def build(h):
        zero = h.real_var("Zero", 0.0, "mm")                    # a constant: point components need a variable
        parts = []
        for side, cy in (("+", "Arch Centre Y"), ("-", "Arch Centre Y Minus")):
            lo = nj.point_from_vars(h, f"Arch{side} Bottom", ids["Arch Centre X"], ids[cy], ids["Z Bottom"])
            hi = nj.point_from_vars(h, f"Arch{side} Top", ids["Arch Centre X"], ids[cy], ids["Z Top"])
            cyl = h.add(f"Arch{side} Cylinder", nj.CYLINDER, mask="cylinder", must=[["cylinder", "point,point,real"]])
            h.wire(lo, cyl, ["Point 1"])
            h.wire(hi, cyl, ["Point 2"])
            h.wire(ids["Arch Radius"], cyl, ["Radius"])
            centre = nj.point_from_vars(h, f"Arch{side} Centre", ids["Arch Centre X"], ids[cy], zero)
            dome = h.add(f"Arch{side} Dome", nj.TORUS, mask="torus", must=[["torus", "point", "vector"], ["torus"]])
            h.wire(centre, dome, ["Center"])
            nj.set_axis(h, dome)
            h.wire(ids["Arch Dome Ring Radius"], dome, ["Radius"])
            h.wire(ids["Dome Tube Radius"], dome, ["Torus Radius", "Torus radius", "Tube"])
            parts += [cyl, dome]
        # the wedge |angle| <= Wedge Angle: the half-space y <= 0 turned by +W, y >= 0 turned by -W
        for side, (y0, y1), angle in (("+", (-80.0, 0.0), "Wedge Angle"), ("-", (0.0, 80.0), "Wedge Angle Minus")):
            box = h.add(f"Wedge{side} Half", mask="box_from_corners", must=nj.BOX_FROM_CORNERS)
            corners = [i["name"] for i in h.inputs(box) if "point" in str(i.get("type", ""))]
            h.set(box, [corners[0]], [-40.0, y0, -40.0], "mm")
            h.set(box, [corners[1]], [40.0, y1, 40.0], "mm")
            rot = h.add(f"Wedge{side} Turn", mask="rotation_transform", must=nj.ROTATION_TRANSFORM)
            h.set(rot, [h.input_of_type(rot, "point")], [0.0, 0.0, 0.0], "mm")
            h.set(rot, [h.input_of_type(rot, "vector")], [0.0, 0.0, 1.0])
            h.wire(ids[angle], rot, [h.input_of_type(rot, "real")])
            turned = h.add(f"Wedge{side}", mask="transform_object", must=nj.TRANSFORM_OBJECT)
            h.wire(box, turned, [h.input_of_type(turned, "spatial3d")])
            h.wire(rot, turned, [h.input_of_type(turned, "transformation")])
            parts.append(turned)
        arch = h.add("Arch", mask="intersect", must=nj.INTERSECT)
        for part in parts:
            h.to_list(part, arch, ["Bodies"])
        cut = h.add("Arch Cut", nj.CYLINDER, mask="cylinder", must=[["cylinder", "point,point,real"]])
        h.set(cut, ["Point 1"], [0.0, 0.0, -20.0], "mm")
        h.set(cut, ["Point 2"], [0.0, 0.0, 20.0], "mm")
        h.wire(ids["Arch Cut Radius"], cut, ["Radius"])
        shoulders = h.add("Shoulders", mask="subtract", must=nj.SUBTRACT)
        h.wire(arch, shoulders, ["Primary Body", "Body"])
        h.to_list(cut, shoulders, ["Subtraction Bodies", "Bodies"])
        return shoulders
    return build


def _milgrain(h, ids) -> list[str]:
    """Two bead rows per arch: a sphere pair at the start bead, polar-arrayed about the arch centre."""
    rows = []
    for side, (sx, sy), cy in (("+", ("Bead Start X", "Bead Start Y"), "Arch Centre Y"),
                               ("-", ("Bead Start X Minus", "Bead Start Y Minus"), "Arch Centre Y Minus")):
        pair = h.add(f"Beads{side} Pair", mask="union", must=nj.UNION)
        for zs, zvar in (("top", "Bead Z"), ("bottom", "Bead Z Minus")):
            pt = nj.point_from_vars(h, f"Bead{side} {zs}", ids[sx], ids[sy], ids[zvar])
            ball = h.add(f"Bead{side} {zs} Sphere", nj.SPHERE, mask="sphere", must=[["sphere<point,real>"], ["sphere", "point", "real"]])
            h.wire(pt, ball, ["Center Point", "Center"])
            h.wire(ids["Bead Radius"], ball, ["Radius"])
            h.to_list(ball, pair, ["Bodies"])
        centre = nj.point_from_vars(h, f"Beads{side} Axis Point", ids["Arch Centre X"], ids[cy], h.blocks["Zero"])
        ax = h.add(f"Beads{side} Axis", mask="axis", must=nj.AXIS)
        h.wire(centre, ax, ["Point", "Origin", "Center", "Position"])
        nj.set_axis(h, ax, name=h.input_name(ax, "Vector", "Direction", "Axis", "Normal"))
        row = h.add(f"Milgrain{side}", mask="polar_array", must=nj.POLAR_ARRAY)
        h.wire(pair, row, ["Body"])
        h.wire(ids["Bead Spacing"], row, ["Angular spacing", "Angular Spacing", "Angle", "Spacing"])
        h.wire(ids["Bead Count"], row, ["Count", "Number", "Copies"])
        h.wire(ax, row, ["Axis"])
        rows.append(row)
    return rows


def _body(h, p, values, test_output):
    ids = nj.add_typed_inputs(h, SPECS, values)
    out_var = nj.path_variable(h, "Output Path", test_output)
    band = nj.add_profiled_band(h, extra=_arches(ids))           # band + arches, one edge rounding

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

    shank = h.add("Shank", mask="union", must=nj.UNION)
    h.to_list(band, shank, ["Bodies"])
    for row in _milgrain(h, ids):
        h.to_list(row, shank, ["Bodies"])
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
