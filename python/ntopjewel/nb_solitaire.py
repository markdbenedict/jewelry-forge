"""The solitaire notebooks' body, shared by ntop/recipes/solitaire.py (round stones, the prong_head
block -> solitaire.ntop) and ntop/recipes/solitaire_outline.py (pear and other fancy outlines, the
outline_head block -> solitaire_outline.ntop). Runs inside nTop's Python Console.

    shank      the band as Python wrote it, bars (Shank Path .. Shank Path 4; plain, tapered, split,
               knotted - ntopjewel.shank.bar_meshes, bodies that cross each other in different bars, an
               unused slot the smallest bar again): each Import Mesh -> Implicit from Mesh -> opened by
               the edge round, then united -> Remap Cylindrical (Wrap Length) = Band Body; the arches, less
               the slot cutter (Slot Path: the split's slot swept in the ring frame, a speck far outside
               when there is none), opened on their own and united afterwards
    artwork    (Band Body − Panel Cuts) ∪ Relief ∪ Knot ∪ Knot 2 = Carved Band (nj.add_carved, as
               ring_artwork.ntop): the panel channels and the motifs in relief Python writes (Cut Path,
               Relief Path; ntopjewel.artwork) and the knot ornaments standing on the shoulders (Knot
               Path / Knot Path 2: each knot's two pieces apart, ntopjewel.ornament), carved into and
               united with the opened band BEFORE the arches and the head join it - the panels stop
               short of the arches' wedge, or of the head (and the knots) on a plain-shouldered ring.
               No artwork: a cutter speck far outside the ring and relief/knot specks buried in the band
    seat       stone_seat(Seat Path, Clearance), embedded -> Seat Local (head frame)
    head       prong_head(Seat Local + 14 numbers), outline_head(Seat Local, Prongs Path + 5 rail
               numbers) or bezel_head(Seat Local, Windows Path, Wall, Bezel Bottom/Top), embedded -> head frame
    placement  Rotation Transform: 90° about the line through (Pivot X, 0, Pivot Z) parallel to +Y;
               Transform Object puts the head and the seat on the ring (head +Z -> ring +X)
    arch       per side: Cylinder (Arch Radius) ∩ Torus (Arch Dome Ring Radius / Dome Tube Radius) about
               (Arch Centre X, Arch Centre Y[ Minus]); both ∩ a wedge (two corner boxes turned by ±Wedge
               Angle about +Z) - a cylinder of Arch Cut Radius
    milgrain   per side: two spheres at (Bead Start X[ Minus], Bead Start Y[ Minus], ±Bead Z) -> Polar
               Array (Bead Count, Bead Spacing) about the axis through that arch's centre ∥ Z
    engraving  Import Mesh (Engraving Path) -> Implicit from Mesh -> Remap Cylindrical (Engraving Wrap
               Length) -> turned 180° about +Z (the text opposite the head)
    ring       ((Carved Band ∪ arches ∪ milgrain) ∪ placed head, blended by Shank Blend) - placed seat - engraving
               -> Volume, Mesh, Export. The cuts come AFTER the blend: a smooth union fills every corner
               two surfaces make within its radius, and the seat's corners must stay empty

Every number comes from ntopjewel.solitaire.SolitaireSpec.notebook_inputs; the notebook has no arithmetic.
"""
from __future__ import annotations

from pathlib import Path

from . import nb_jewel as nj

ROUND_HEAD = [("Prong Count", "int"), ("Prong Spacing", "deg"), ("Prong Radius", "mm"),
              ("Base X", "mm"), ("Base Y", "mm"), ("Base Z", "mm"), ("Tip X", "mm"), ("Tip Y", "mm"), ("Tip Z", "mm"),
              ("Upper Rail Z", "mm"), ("Upper Rail Radius", "mm"), ("Lower Rail Z", "mm"), ("Lower Rail Radius", "mm"),
              ("Rail Tube Radius", "mm"), ("Head Blend", "mm")]
OUTLINE_HEAD = [("Prongs Path", "path"), ("Rail Offset", "mm"), ("Upper Rail Bottom", "mm"), ("Upper Rail Top", "mm"),
                ("Lower Rail Bottom", "mm"), ("Lower Rail Top", "mm"), ("Head Blend", "mm")]
BEZEL_HEAD = [("Windows Path", "path"), ("Wall", "mm"), ("Bezel Bottom", "mm"), ("Bezel Top", "mm"), ("Head Blend", "mm")]
JOIN = [("Shank Blend", "mm")]
BLOCK_INPUT = {"Head Blend": "Blend Radius"}          # a notebook input whose name differs from the block input it feeds
HEAD_LABEL = {"round": "Prong Head", "outline": "Outline Head", "bezel": "Bezel Head"}
ARCH = [("Pivot X", "mm"), ("Pivot Z", "mm"),
        ("Arch Centre X", "mm"), ("Arch Centre Y", "mm"), ("Arch Centre Y Minus", "mm"), ("Arch Radius", "mm"),
        ("Arch Dome Ring Radius", "mm"), ("Arch Cut Radius", "mm"), ("Wedge Angle", "deg"), ("Wedge Angle Minus", "deg"),
        ("Bead Radius", "mm"), ("Bead Z", "mm"), ("Bead Z Minus", "mm"), ("Bead Spacing", "deg"), ("Bead Count", "int"),
        ("Bead Start X", "mm"), ("Bead Start Y", "mm"), ("Bead Start X Minus", "mm"), ("Bead Start Y Minus", "mm")]
ENGRAVING = [("Engraving Path", "path"), ("Engraving Wrap Length", "mm")]
ENGRAVING_TURN_DEG = 180.0
SHANK = [(name, "path") for name in nj.SLOT_NAMES] + [("Wrap Length", "mm"), ("Slot Path", "path")]   # the bars nTop unites, then the wrap
ARTWORK = [("Cut Path", "path"), ("Relief Path", "path"), ("Knot Path", "path"), ("Knot Path 2", "path")]   # the panels carved into the band, the knots on it
BAND_FOR_ARCHES = ["Z Top", "Z Bottom", "Dome Tube Radius", "Edge Round", "Edge Round Inward", "Mesh Tolerance"]   # of nj.BAND_INPUTS


def head_specs(kind: str) -> list[tuple[str, str]]:
    return {"outline": OUTLINE_HEAD, "bezel": BEZEL_HEAD}.get(kind, ROUND_HEAD)


def specs(kind: str) -> list[tuple[str, str]]:
    return (SHANK + ARTWORK + [(n, "mm") for n in BAND_FOR_ARCHES] + [("Seat Path", "path"), ("Clearance", "mm")] + head_specs(kind)
            + ARCH + ENGRAVING + JOIN)


def input_order(kind: str) -> list[str]:
    return [n for n, _ in specs(kind)] + ["Output Path"]


def arches(h, ids) -> str:
    """The cathedral arches (see the module doc), before their opening: per side a cylinder ∩ a dome
    torus, both ∩ the wedge, less the cut cylinder. Returns the `Shoulders` block."""
    zero = h.real_var("Zero", 0.0, "mm")                        # a constant: point components need a variable
    parts = []
    for side, cy in (("+", "Arch Centre Y"), ("-", "Arch Centre Y Minus")):
        lo = nj.point_from_vars(h, f"Arch{side} Bottom", ids["Arch Centre X"], ids[cy], ids["Z Bottom"])
        hi = nj.point_from_vars(h, f"Arch{side} Top", ids["Arch Centre X"], ids[cy], ids["Z Top"])
        cyl = h.cylinder(f"Arch{side} Cylinder", lo, hi, ids["Arch Radius"])
        centre = nj.point_from_vars(h, f"Arch{side} Centre", ids["Arch Centre X"], ids[cy], zero)
        dome = h.torus(f"Arch{side} Dome", ids["Arch Dome Ring Radius"], ids["Dome Tube Radius"], centre=centre)
        parts += [cyl, dome]
    # the wedge |angle| <= Wedge Angle: the half-space y <= 0 turned by +W, y >= 0 turned by -W
    for side, (y0, y1), angle in (("+", (-80.0, 0.0), "Wedge Angle"), ("-", (0.0, 80.0), "Wedge Angle Minus")):
        box = h.add(f"Wedge{side} Half", mask="box_from_corners", must=nj.BOX_FROM_CORNERS)
        corners = [i["name"] for i in h.inputs(box) if "point" in str(i.get("type", ""))]
        h.set(box, [corners[0]], [-40.0, y0, -40.0], "mm")
        h.set(box, [corners[1]], [40.0, y1, 40.0], "mm")
        rot = h.rotation(f"Wedge{side} Turn", ids[angle])
        parts.append(h.transform(f"Wedge{side}", box, rot))
    arch = h.intersect("Arch", parts, comment="Each arch: the band's section swept round a circle tangent at the shoulder, "
                                              "kept within the wedge.")
    cut = h.cylinder("Arch Cut", None, None, ids["Arch Cut Radius"], z_span=(-20.0, 20.0))
    return h.subtract("Shoulders", arch, [cut])


def milgrain(h, ids) -> list[str]:
    """Two bead rows per arch: a sphere pair at the start bead, polar-arrayed about the arch centre."""
    rows = []
    for side, (sx, sy), cy in (("+", ("Bead Start X", "Bead Start Y"), "Arch Centre Y"),
                               ("-", ("Bead Start X Minus", "Bead Start Y Minus"), "Arch Centre Y Minus")):
        pair = h.add(f"Beads{side} Pair", mask="union", must=nj.UNION)
        for zs, zvar in (("top", "Bead Z"), ("bottom", "Bead Z Minus")):
            pt = nj.point_from_vars(h, f"Bead{side} {zs}", ids[sx], ids[sy], ids[zvar])
            h.to_list(h.sphere(f"Bead{side} {zs} Sphere", pt, ids["Bead Radius"]), pair, nj.BODIES)
        centre = nj.point_from_vars(h, f"Beads{side} Axis Point", ids["Arch Centre X"], ids[cy], h.blocks["Zero"])
        ax = nj.z_axis(h, f"Beads{side} Axis", point=centre)
        rows.append(h.polar_array(f"Milgrain{side}", pair, ids["Bead Spacing"], ids["Bead Count"], ax))
    return rows


def engraving(h, ids) -> str:
    """The text body: imported, wrapped round the ring centred on +X, turned to -X (under the finger)."""
    body = h.import_body("Engraving Body", ids["Engraving Path"])
    wrapped = h.remap_cylindrical("Engraving Wrapped", body, ids["Engraving Wrap Length"])
    rot = h.rotation("Engraving Turn", nj.angle_variable(h, "Engraving Turn Angle", ENGRAVING_TURN_DEG))
    return h.transform("Engraving", wrapped, rot)


def body(kind: str):
    """The notebook body for `nj.run_build`, for a round (prong_head), outline or bezel head."""
    def _body(h, p, values, test_output):
        ids = nj.add_typed_inputs(h, specs(kind), values)
        out_var = nj.path_variable(h, "Output Path", test_output)
        with h.section("Shank"):                                    # the bars united, opened, wrapped
            band = h.wrap_var("Band Body", nj.add_wrapped_shank(h, [ids[name] for name in nj.SLOT_NAMES], ids["Wrap Length"],
                                                                ids["Edge Round Inward"], ids["Edge Round"], ids["Mesh Tolerance"]))
        with h.section("Artwork"):                                  # the panels and the knots, before anything joins the band
            carved = h.wrap_var("Carved Band", nj.add_carved(h, band, ids["Cut Path"], ids["Relief Path"],
                                                             knot_vars=[ids["Knot Path"], ids["Knot Path 2"]]))
        with h.section("Arches"):
            # rounded on their own and united sharp: opening the union (band + arches) grew a 0.07 mm layer
            # over the arch feet, where the arch dome lies on the band's dome (2026-10-31)
            shoulders = arches(h, ids)
            slot = h.import_body("Slot Cutter", ids["Slot Path"])
            split_arches = h.subtract("Split Arches", shoulders, [slot], comment=(
                "A split shank's slot runs through the arches (a speck far outside when there is no split)."))
            arch_body = nj.add_opening(h, split_arches, ids["Edge Round Inward"], ids["Edge Round"], ids["Mesh Tolerance"],
                                       name="Arches", base="Arches")
            h.comment(arch_body, "The arches opened on their own, then united with the band: opening the union grew a "
                                 "layer over their feet, where the arch dome lies on the band's dome (2026-10-31).")
        with h.section("Head"):
            seat = h.add("Stone Seat", h.embed_block(p["seat_block"]))
            h.wire(ids["Seat Path"], seat, ["Seat Path"])
            h.wire(ids["Clearance"], seat, ["Clearance"])
            seat_local = h.wrap_var("Seat Local", seat)             # used twice: the head's cutter and the shank's
            head = h.add(HEAD_LABEL[kind], h.embed_block(p["head_block"]))
            h.wire(seat_local, head, ["Seat Cutter"])
            for name, _ in head_specs(kind):
                h.wire(ids[name], head, [BLOCK_INPUT.get(name, name)])
            pivot = nj.point_block(h, "Pivot", x_var=ids["Pivot X"], z_var=ids["Pivot Z"])
            rot = h.rotation("Head Placement", nj.angle_variable(h, "Head Angle", 90.0), axis=(0.0, 1.0, 0.0), point=pivot)
            h.comment(rot, "A quarter-turn about the line through (Pivot X, 0, Pivot Z) ∥ +Y: the head's +Z onto the ring's +X.")
            placement = h.wrap_var("Placement", rot)                # used twice
            placed_head = h.transform("Placed Head", head, placement)
            placed_seat = h.transform("Placed Seat", seat_local, placement)
        with h.section("Milgrain"):
            rows = milgrain(h, ids)
        with h.section("Engraving"):
            text = engraving(h, ids)
        with h.section("Ring"):
            shank = h.union("Shank Union", [carved, arch_body, *rows])
            joined = h.union("Joined", [shank, placed_head], blend=ids["Shank Blend"], comment=(
                "The head melts into the shank (a smooth union, Shank Blend). The seat and the engraving are cut AFTER it: "
                "a blend fills every corner within its radius, the seat's included."))
            ring = h.subtract("Ring", joined, [placed_seat, text])
            out = h.wrap_var("Ring Body", ring)
            integ, _mesh, export = nj.add_measure_mesh_export(h, out, out_var, ids["Mesh Tolerance"])
        return integ, export
    return _body


def prepare(spec, params: dict, test_dir: Path, tag: str) -> dict:
    """Laptop side: the test envelope / prongs / engraving files and every input value of `spec`."""
    test_dir.mkdir(parents=True, exist_ok=True)
    env, prongs, eng, win, slot = (test_dir / f"{tag}_test_envelope.stl", test_dir / f"{tag}_test_prongs.stl",
                                   test_dir / f"{tag}_test_engraving.stl", test_dir / f"{tag}_test_windows.stl",
                                   test_dir / f"{tag}_test_slot.stl")
    spec.head.seat.envelope().export(str(env))
    if spec.outline:
        spec.placed_head.prongs_mesh().export(str(prongs))
    if spec.bezel:
        spec.placed_head.windows_mesh().export(str(win))
    spec.write_engraving(eng)
    from .shank import write_bars
    bars = write_bars(spec.shank_spec, test_dir, f"{tag}_test")                   # <tag>_test.bar.stl ...
    spec.slot_mesh().export(str(slot))
    cut, relief = spec.write_artwork(test_dir, f"{tag}_test")                     # <tag>_test.cut.stl / .relief.stl (specks: no artwork)
    knot, knot2 = spec.write_knots(test_dir, f"{tag}_test")                       # <tag>_test.knot.stl / .knot2.stl (specks: no knots)
    v = spec.notebook_inputs(str(env), prongs_path=str(prongs) if spec.outline else "", engraving_path=str(eng),
                             windows_path=str(win) if spec.bezel else "", shank_paths=bars, slot_path=str(slot),
                             cut_path=cut, relief_path=relief, knot_paths=(knot, knot2))
    params["values"] = {**v, **(params.get("values") or {})}
    return params


def build(notebook, params: dict, defaults: dict, kind: str) -> dict:
    return nj.standard_build(notebook, params, defaults, body(kind), Path(defaults["save_to"]).stem,
                             blocks=("seat_block", "head_block"))
