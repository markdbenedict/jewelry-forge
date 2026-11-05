"""Phase 3: the `partial_bezel_head` library block and its harness - a bezel kept on two mirrored wall
stretches along the stone's flanks, with a hood over each point (the open pear of the reference photo;
a half-bezel on a round, oval or emerald). Every piece is an nTop primitive; Python gives only numbers.

    python -m ntopjewel api build stone_seat                 # first, if ntop/blocks/stone_seat.ntop is not there
    python -m ntopjewel api build partial_bezel_head         # nTop open, View > Python Console open

1. Block `ntop/blocks/partial_bezel_head.ntop` (Seat Cutter is an implicit INPUT, as the other heads'):
       grown    Offset Body (Seat Cutter, Wall)
       cup      Box from Corners, z Bezel Bottom .. Cup Top               the full cup under the girdle (bearing)
       wall     Box from Corners y >= 0 turned by Wall To Angle  ∩  Box from Corners y <= 0 turned by Wall
                From Angle, both about the vertical through (Wall Centre X, 0), z Bezel Bottom .. Bezel Top:
                the +y wall's sector (a variable: itself and its Mirror Body across the plane y = 0)
       hoods    Cylinder (Hood X, 0, Bezel Bottom) -> (Hood X, 0, Hood Top), radius Hood Reach; the same at
                Hood 2 X (an unused hood stands far outside the stone)
       mask     Boolean Union of cup, wall, mirrored wall, hoods - SHARP: the pieces overlap, none shares a face
       head     (grown ∩ mask, blended by Blend Radius: the rim, the wall ends and the hood rounded) − Seat Cutter
   No blended union: a smooth union of bodies meeting on a face swells them (the pearl's cup, 2026-11-05).
2. Harness `ntop/notebooks/partial_bezel_head_harness.ntop`: Seat Path + Clearance (an embedded
   stone_seat) and the block's numbers + Mesh Tolerance + Output Path, measured. Run by
   `python -m ntopjewel head --partial-bezel ...` (partial_bezel.build_partial_bezel), gated for fit, seat,
   drop-in, walls, open stretches, hoods, the point, the bearing and volume.
"""
from __future__ import annotations

from pathlib import Path

from ntopjewel import nb_jewel as nj

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
TEST_ENVELOPE = REPO / "out" / "api" / "partial_bezel_head_test_envelope.stl"

GEOMETRY_SPECS = [("Wall", "mm"), ("Bezel Bottom", "mm"), ("Cup Top", "mm"), ("Bezel Top", "mm"),
                  ("Wall Centre X", "mm"), ("Wall From Angle", "deg"), ("Wall To Angle", "deg"),
                  ("Hood X", "mm"), ("Hood 2 X", "mm"), ("Hood Reach", "mm"), ("Hood Top", "mm"), ("Blend Radius", "mm")]
SEAT_SPECS = [("Seat Path", "path"), ("Clearance", "mm")]
BLOCK_SPECS = SEAT_SPECS + GEOMETRY_SPECS
INPUT_ORDER = [n for n, _ in BLOCK_SPECS] + ["Mesh Tolerance", "Output Path"]
CUTTER_INPUT = "Seat Cutter"
HALF = 40.0                     # the boxes' x/y half extent (any stone fits; partial_bezel.HALF_BOX_MM)


def _spec():
    from ntopjewel import gems, partial_bezel
    return partial_bezel.PartialBezelSpec(gems.StoneSpec("pear", 10.0, 7.0, 4.5))


DEFAULTS = {
    "values": {},
    "input_order": INPUT_ORDER,
    "test_output": str(REPO / "out" / "api" / "partial_bezel_head_test.stl"),
    "seat_block": str(REPO / "ntop" / "blocks" / "stone_seat.ntop"),
    "block_to": str(REPO / "ntop" / "blocks" / "partial_bezel_head.ntop"),
    "block_recipe_to": str(REPO / "ntop" / "recipes" / "partial_bezel_head.block.recipe.json"),
    "save_to": str(REPO / "ntop" / "notebooks" / "partial_bezel_head_harness.ntop"),
    "recipe_to": str(REPO / "ntop" / "recipes" / "partial_bezel_head_harness.recipe.json"),
    "pause": False,
    "lazy_ok": True,
    "fresh": True,
    "wait_s": 240,
    "volume_hint": "partial bezel, 10 x 7 x 4.5 pear: about 50 mm³ with the blends (partial_bezel.PartialBezelSpec.design_mesh)",
}


def prepare(params: dict, work_dir: Path) -> dict:
    """Laptop side: the test envelope and every input value."""
    spec = _spec()
    TEST_ENVELOPE.parent.mkdir(parents=True, exist_ok=True)
    spec.seat.envelope().export(str(TEST_ENVELOPE))
    v = spec.notebook_inputs(str(TEST_ENVELOPE), "", "")
    v.pop("Output Path")
    params["values"] = {**v, **(params.get("values") or {})}
    return params


def _box(h, label: str, lo: str, hi: str) -> str:
    """Box from Corners between two Point blocks (its corner inputs found by type, in order)."""
    box = h.add(label, mask="box_from_corners", must=nj.BOX_FROM_CORNERS)
    corners = [i["name"] for i in h.inputs(box) if "point" in str(i.get("type", ""))]
    h.wire(lo, box, [corners[0]])
    h.wire(hi, box, [corners[1]])
    return box


def _block_body(notebook, values: dict):
    """Fresh notebook -> (helper, partial bezel body, input ids in order)."""
    h = nj.Helper(notebook)
    notebook.new_notebook()
    cutter = nj.implicit_input(h, CUTTER_INPUT)
    ids = nj.add_typed_inputs(h, GEOMETRY_SPECS, values)
    grown = h.offset("Bezel Grown", cutter, ids["Wall"])                            # the cutter + the wall
    # the full cup under the girdle: the bearing all round
    cup = _box(h, "Cup Slab",
               nj.point_block(h, "Cup Low Corner", z_var=ids["Bezel Bottom"], x=-HALF, y=-HALF),
               nj.point_block(h, "Cup High Corner", z_var=ids["Cup Top"], x=HALF, y=HALF))
    # the +y wall's sector: two half-spaces turned about the vertical through (Wall Centre X, 0)
    pivot = h.wrap_var("Wall Pivot", nj.point_block(h, "Wall Pivot Point", x_var=ids["Wall Centre X"]))   # two rotations use it
    upper = _box(h, "Wall Upper Box",
                 nj.point_block(h, "Wall Upper Low", z_var=ids["Bezel Bottom"], x=-HALF, y=0.0),
                 nj.point_block(h, "Wall Upper High", z_var=ids["Bezel Top"], x=HALF, y=HALF))
    lower = _box(h, "Wall Lower Box",
                 nj.point_block(h, "Wall Lower Low", z_var=ids["Bezel Bottom"], x=-HALF, y=-HALF),
                 nj.point_block(h, "Wall Lower High", z_var=ids["Bezel Top"], x=HALF, y=0.0))
    upper_t = h.transform("Wall Upper Half", upper, h.rotation("Wall To Turn", ids["Wall To Angle"], point=pivot))
    lower_t = h.transform("Wall Lower Half", lower, h.rotation("Wall From Turn", ids["Wall From Angle"], point=pivot))
    sector = h.wrap_var("Wall Sector", h.intersect("Wall Sector Body", [upper_t, lower_t]))      # itself and its mirror
    plane = nj.plane_block(h, "Mirror Plane", x_axis=(1.0, 0.0, 0.0), y_axis=(0.0, 0.0, 1.0))     # y = 0
    mirrored = h.mirror("Wall Sector Mirrored", sector, plane)
    # a hood over each point: a vertical cylinder; an unused one far outside the stone
    hoods = []
    for tag, xname in (("Hood", "Hood X"), ("Hood 2", "Hood 2 X")):
        p1 = nj.point_block(h, f"{tag} Foot", x_var=ids[xname], z_var=ids["Bezel Bottom"])
        p2 = nj.point_block(h, f"{tag} Crown", x_var=ids[xname], z_var=ids["Hood Top"])
        hoods.append(h.cylinder(f"{tag} Zone", p1, p2, ids["Hood Reach"]))
    mask = h.union("Mask", [cup, sector, mirrored, *hoods])                         # sharp: the pieces overlap
    body = h.intersect("Partial Bezel", [grown, mask], blend=ids["Blend Radius"])   # the one blend: edges rounded
    head = h.subtract("Seated", body, [cutter])
    return h, head, [cutter] + [ids[n] for n, _ in GEOMETRY_SPECS]


def build_block(notebook, p: dict, values: dict) -> dict:
    h, head, order = _block_body(notebook, values)
    return nj.save_block(notebook, h, head, order, "Head", p)


_harness = nj.seat_head_harness("Partial Bezel Head", SEAT_SPECS, GEOMETRY_SPECS, CUTTER_INPUT)


def build(notebook, params: dict | None = None) -> dict:
    """Entry point for `api build partial_bezel_head`: the block, then its harness."""
    return nj.block_build(notebook, params, DEFAULTS, "partial_bezel_head", build_block, _harness)
