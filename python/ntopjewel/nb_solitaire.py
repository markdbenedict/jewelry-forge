"""The solitaire notebooks' body, shared by ntop/recipes/solitaire.py (round stones, the prong_head
block -> solitaire.ntop) and ntop/recipes/solitaire_outline.py (pear and other fancy outlines, the
outline_head block -> solitaire_outline.ntop). Runs inside nTop's Python Console.

    band       the profiled band (11 inputs) with the arches joined before its edge-round offsets
    seat       stone_seat(Seat Path, Clearance), embedded -> Seat Local (head frame)
    head       prong_head(Seat Local + 14 numbers) or outline_head(Seat Local, Prongs Path + 5 rail
               numbers), embedded -> head frame
    placement  Rotation Transform: 90° about the line through (Pivot X, 0, Pivot Z) parallel to +Y;
               Transform Object puts the head and the seat on the ring (head +Z -> ring +X)
    arch       per side: Cylinder (Arch Radius) ∩ Torus (Arch Dome Ring Radius / Dome Tube Radius) about
               (Arch Centre X, Arch Centre Y[ Minus]); both ∩ a wedge (two corner boxes turned by ±Wedge
               Angle about +Z) - a cylinder of Arch Cut Radius
    milgrain   per side: two spheres at (Bead Start X[ Minus], Bead Start Y[ Minus], ±Bead Z) -> Polar
               Array (Bead Count, Bead Spacing) about the axis through that arch's centre ∥ Z
    engraving  Import Mesh (Engraving Path) -> Implicit from Mesh -> Remap Cylindrical (Engraving Wrap
               Length) -> turned 180° about +Z (the text opposite the head)
    ring       ((Band Body ∪ milgrain) - placed seat - engraving) ∪ placed head -> Volume, Mesh, Export

Every number comes from ntopjewel.solitaire.SolitaireSpec.notebook_inputs; the notebook has no arithmetic.
"""
from __future__ import annotations

from pathlib import Path

from . import nb_jewel as nj
from .notebook_api import ConsoleError

ROUND_HEAD = [("Prong Count", "int"), ("Prong Spacing", "deg"), ("Prong Radius", "mm"),
              ("Base X", "mm"), ("Base Y", "mm"), ("Base Z", "mm"), ("Tip X", "mm"), ("Tip Y", "mm"), ("Tip Z", "mm"),
              ("Upper Rail Z", "mm"), ("Upper Rail Radius", "mm"), ("Lower Rail Z", "mm"), ("Lower Rail Radius", "mm"),
              ("Rail Tube Radius", "mm")]
OUTLINE_HEAD = [("Prongs Path", "path"), ("Rail Offset", "mm"), ("Upper Rail Bottom", "mm"), ("Upper Rail Top", "mm"),
                ("Lower Rail Bottom", "mm"), ("Lower Rail Top", "mm")]
ARCH = [("Pivot X", "mm"), ("Pivot Z", "mm"),
        ("Arch Centre X", "mm"), ("Arch Centre Y", "mm"), ("Arch Centre Y Minus", "mm"), ("Arch Radius", "mm"),
        ("Arch Dome Ring Radius", "mm"), ("Arch Cut Radius", "mm"), ("Wedge Angle", "deg"), ("Wedge Angle Minus", "deg"),
        ("Bead Radius", "mm"), ("Bead Z", "mm"), ("Bead Z Minus", "mm"), ("Bead Spacing", "deg"), ("Bead Count", "int"),
        ("Bead Start X", "mm"), ("Bead Start Y", "mm"), ("Bead Start X Minus", "mm"), ("Bead Start Y Minus", "mm")]
ENGRAVING = [("Engraving Path", "path"), ("Engraving Wrap Length", "mm")]
ENGRAVING_TURN_DEG = 180.0


def head_specs(kind: str) -> list[tuple[str, str]]:
    return OUTLINE_HEAD if kind == "outline" else ROUND_HEAD


def specs(kind: str) -> list[tuple[str, str]]:
    return ([(n, "mm") for n in nj.BAND_INPUTS] + [("Seat Path", "path"), ("Clearance", "mm")] + head_specs(kind)
            + ARCH + ENGRAVING)


def input_order(kind: str) -> list[str]:
    return [n for n, _ in specs(kind)] + ["Output Path"]


def arches(ids):
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


def milgrain(h, ids) -> list[str]:
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


def engraving(h, ids) -> str:
    """The text body: imported, wrapped round the ring centred on +X, turned to -X (under the finger)."""
    imp = h.add("Engraving Mesh", mask="import_mesh", must=nj.IMPORT_MESH)
    h.wire(ids["Engraving Path"], imp, ["Path", "File Path", "File", "Filename"])
    body = h.add("Engraving Body", mask="implicit_from_mesh", must=nj.IMPLICIT_FROM_MESH)
    h.wire(imp, body, ["Mesh"])
    wrapped = h.add("Engraving Wrapped", mask="remap_cylindrical", must=nj.REMAP_CYLINDRICAL)
    h.wire(body, wrapped, ["Body"])
    h.wire(ids["Engraving Wrap Length"], wrapped, ["Y mapping length", "Y Mapping Length", "Mapping Length", "Length"])
    rot = h.add("Engraving Turn", mask="rotation_transform", must=nj.ROTATION_TRANSFORM)
    h.set(rot, [h.input_of_type(rot, "point")], [0.0, 0.0, 0.0], "mm")
    h.set(rot, [h.input_of_type(rot, "vector")], [0.0, 0.0, 1.0])
    h.wire(nj.angle_variable(h, "Engraving Turn Angle", ENGRAVING_TURN_DEG), rot, [h.input_of_type(rot, "real")])
    turned = h.add("Engraving", mask="transform_object", must=nj.TRANSFORM_OBJECT)
    h.wire(wrapped, turned, [h.input_of_type(turned, "spatial3d")])
    h.wire(rot, turned, [h.input_of_type(turned, "transformation")])
    return turned


def body(kind: str):
    """The notebook body for `nj.run_build`, for a round (prong_head) or outline (outline_head) head."""
    def _body(h, p, values, test_output):
        ids = nj.add_typed_inputs(h, specs(kind), values)
        out_var = nj.path_variable(h, "Output Path", test_output)
        band = nj.add_profiled_band(h, extra=arches(ids))            # band + arches, one edge rounding

        seat = h.add("Stone Seat", h.embed_block(p["seat_block"]))
        h.wire(ids["Seat Path"], seat, ["Seat Path"])
        h.wire(ids["Clearance"], seat, ["Clearance"])
        seat_local = h.wrap_var("Seat Local", seat)                 # used twice: the head's cutter and the shank's
        head = h.add("Outline Head" if kind == "outline" else "Prong Head", h.embed_block(p["head_block"]))
        h.wire(seat_local, head, ["Seat Cutter"])
        for name, _ in head_specs(kind):
            h.wire(ids[name], head, [name])

        pivot = nj.point_block(h, "Pivot", x_var=ids["Pivot X"], z_var=ids["Pivot Z"])
        rot = h.add("Head Placement", mask="rotation_transform", must=nj.ROTATION_TRANSFORM)
        h.wire(pivot, rot, [h.input_of_type(rot, "point")])
        h.set(rot, [h.input_of_type(rot, "vector")], [0.0, 1.0, 0.0])
        angle = nj.angle_variable(h, "Head Angle", 90.0)            # a constant, not an input
        h.wire(angle, rot, [h.input_of_type(rot, "real")])
        placement = h.wrap_var("Placement", rot)                    # used twice
        placed = {}
        for label, b in (("Placed Head", head), ("Placed Seat", seat_local)):
            t = h.add(label, mask="transform_object", must=nj.TRANSFORM_OBJECT)
            h.wire(b, t, [h.input_of_type(t, "spatial3d")])
            h.wire(placement, t, [h.input_of_type(t, "transformation")])
            placed[label] = t

        shank = h.add("Shank", mask="union", must=nj.UNION)
        h.to_list(band, shank, ["Bodies"])
        for row in milgrain(h, ids):
            h.to_list(row, shank, ["Bodies"])
        seated = h.add("Seated Shank", mask="subtract", must=nj.SUBTRACT)
        h.wire(shank, seated, ["Primary Body", "Body"])
        h.to_list(placed["Placed Seat"], seated, ["Subtraction Bodies", "Bodies"])
        h.to_list(engraving(h, ids), seated, ["Subtraction Bodies", "Bodies"])
        ring = h.add("Ring", mask="union", must=nj.UNION)
        h.to_list(seated, ring, ["Bodies"])
        h.to_list(placed["Placed Head"], ring, ["Bodies"])
        out = h.wrap_var("Ring Body", ring)
        integ, _mesh, export = nj.add_measure_mesh_export(h, out, out_var, ids["Mesh Tolerance"])
        return integ, export
    return _body


def prepare(spec, params: dict, test_dir: Path, tag: str) -> dict:
    """Laptop side: the test envelope / prongs / engraving files and every input value of `spec`."""
    test_dir.mkdir(parents=True, exist_ok=True)
    env, prongs, eng = (test_dir / f"{tag}_test_envelope.stl", test_dir / f"{tag}_test_prongs.stl",
                        test_dir / f"{tag}_test_engraving.stl")
    spec.head.seat.envelope().export(str(env))
    if spec.outline:
        spec.placed_head.prongs_mesh().export(str(prongs))
    spec.write_engraving(eng)
    v = spec.notebook_inputs(str(env), prongs_path=str(prongs) if spec.outline else "", engraving_path=str(eng))
    params["values"] = {**v, **(params.get("values") or {})}
    return params


def build(notebook, params: dict, defaults: dict, kind: str) -> dict:
    p = {**defaults, **(params or {})}
    values = {**defaults["values"], **(p.get("values") or {})}
    if not values:
        raise ConsoleError("no input values: run through `python -m ntopjewel api build ...` (prepare() computes them)")
    for key in ("seat_block", "head_block"):
        p[key] = nj.absolute(p[key])
        if not Path(p[key]).exists():
            raise ConsoleError(f"{p[key]} is missing: build it first (api build stone_seat / {Path(p[key]).stem})")
    p["values"] = values
    return nj.run_build(notebook, p, {**defaults, "values": values}, body(kind))
