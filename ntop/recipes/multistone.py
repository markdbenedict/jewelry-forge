"""Build `multistone.ntop` through nTop's Notebook API: a centre stone and side stones in a row - Phase 3
step 2 (ntopjewel.multistone; reference rings 05 and 02).

    shank      Shank Path .. Shank Path 4 -> the band exactly as ring_shank.ntop builds it
               (nj.add_wrapped_shank: each bar opened on its own, united, wrapped) = Shank Body
    slots      five, each: stone_seat(Seat Path k, Clearance) -> Seat k (head frame, used twice);
               outline_head(Seat k, Prongs Path k, Rail Offset k, Upper/Lower Rail Bottom/Top k,
               Head Blend) -> Outline Head k; both moved by ONE transform (section Head k), Head k
               Placement = Combine Transforms of, applied in this order:
                 Head k Spin          Rotation Transform about the head's +Z through the origin
                 Head k Quarter Turn  Rotation Transform 90° about the line through Head k Pivot ∥ +Y
                 Head k Turn          Rotation Transform about the ring axis +Z through the origin
               (the list laid out in the order nTop applies it: api_facts.json, transform_probe)
               -> Head k On Ring / Seat k On Ring
               An unused slot repeats the centre's values: the same head in the same place
    pavé       Pave Beads Path / Pave Seats Path (0.2.0): the beads (Import Mesh -> Implicit Body) united
               with the shank before the heads join it, the seats cut with the heads' seats at the end -
               as pave_band.ntop does; no-op specks when the ring has no pavé
    ring       (((Shank Body ∪ Pave Beads) ∪ every placed head), blended by Shank Blend) − every placed
               seat − Pave Seats -> Volume Integral of 1 (Output "Volume"), Mesh (Mesh Tolerance), Export
               Mesh (Output Path). The seats are cut AFTER the blended join: a smooth union fills every
               corner within its radius, the seats' included

Both blocks are embedded once (`api build stone_seat`, `api build outline_head` first) and placed five
times; rebuild this notebook after either block changes. Every number comes from
ntopjewel.multistone.MultiStoneSpec.notebook_inputs; the notebook has no arithmetic.

Run:  python -m ntopjewel api build multistone      (nTop open, View > Python Console open, in the foreground)
      python -m ntopjewel multistone --size 6 --shape cushion --length 7 --stone-width 6 --side-shape pear --side-length 6 --side-width 4
"""
from __future__ import annotations

from pathlib import Path

from ntopjewel import nb_multistone as ms           # console-safe: nTop's Python has no yaml / trimesh
from ntopjewel import nb_jewel as nj

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
TEST_DIR = REPO / "out" / "api"
TEST_STEM = "multistone_test"
SPECS = ms.specs()
INPUT_ORDER = ms.input_order()
RAILS = ("Rail Offset", "Upper Rail Bottom", "Upper Rail Top", "Lower Rail Bottom", "Lower Rail Top")


def _spec():
    from ntopjewel import band, gems, heads, multistone                # laptop side only (prepare)
    b = band.BandSpec(size=6, width_mm=2.6, thickness_mm=1.8, profile="court", mesh_tolerance_mm=0.05)
    return multistone.MultiStoneSpec(b, heads.OutlineHeadSpec(gems.StoneSpec("round", 6.5)),
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
    beads, seats = spec.write_pave_layers(TEST_DIR, TEST_STEM)
    v = spec.notebook_inputs(bars, files, pave_paths=(beads, seats))
    v.pop("Output Path")
    params["values"] = {**v, **(params.get("values") or {})}
    return params


def _body(h, p, values, test_output):
    ids = nj.add_typed_inputs(h, SPECS, values)
    out_var = nj.path_variable(h, "Output Path", test_output)
    with h.section("Shank"):
        shank_body = h.wrap_var("Shank Body", nj.add_wrapped_shank(h, [ids[n] for n in nj.SLOT_NAMES], ids["Wrap Length"],
                                                                   ids["Edge Round Inward"], ids["Edge Round"], ids["Mesh Tolerance"],
                                                                   opener=h.embed_block(p["open_bar_block"])))
    with h.section("Pavé"):
        pave_beads = h.import_body("Pave Beads", ids["Pave Beads Path"])
        pave_seats = h.import_body("Pave Seats", ids["Pave Seats Path"])
        beaded = h.union("Beaded Shank", [shank_body, pave_beads], comment=(
            "The pavé's beads on the shank (sharp: they are the pavé's own geometry). No pavé: a speck buried in the band."))
    seat_fn = h.embed_block(p["seat_block"])
    head_fn = h.embed_block(p["head_block"])
    quarter = nj.angle_variable(h, "Quarter Turn", 90.0)          # a constant, not an input
    placed_heads, placed_seats = [], []
    for k in range(ms.SLOTS):
        def i(name):
            return ids[ms.slot_input(name, k)]
        n = k + 1
        with h.section(f"Head {n}"):
            seat = h.add(f"Stone Seat {n}", seat_fn)
            h.wire(i("Seat Path"), seat, ["Seat Path"])
            h.wire(ids["Clearance"], seat, ["Clearance"])
            seat_local = h.wrap_var(f"Seat Local {n}", seat)
            head = h.add(f"Outline Head {n}", head_fn)
            h.wire(seat_local, head, ["Seat Cutter"])                  # the clearance is in the cutter already
            h.wire(i("Prongs Path"), head, ["Prongs Path"])
            for name in RAILS:
                h.wire(i(name), head, [name])
            h.wire(ids["Head Blend"], head, ["Blend Radius"])
            # three moves combined into one placement (a variable: the head and its seat both use it);
            # labels never an input's name ("Spin 2" is slot 2's input)
            spin = h.rotation(f"Head {n} Spin", i("Spin"))
            pivot = nj.point_block(h, f"Head {n} Pivot", x_var=i("Pivot X"), z_var=i("Pivot Z"))
            quarter_turn = h.rotation(f"Head {n} Quarter Turn", quarter, axis=(0.0, 1.0, 0.0), point=pivot)
            turn = h.rotation(f"Head {n} Turn", i("Turn"))
            moves = h.combine(f"Head {n} Moves", [spin, quarter_turn, turn])
            placement = h.wrap_var(f"Head {n} Placement", moves)
            placed_heads.append(h.transform(f"Head {n} On Ring", head, placement))
            placed_seats.append(h.transform(f"Seat {n} On Ring", seat_local, placement))
            if k == 0:
                h.comment(moves, "Spun about its own axis, a quarter-turn onto +X about the line through the pivot ∥ +Y, "
                                 "turned about the ring axis to its angle - in that order, one transform. An unused slot "
                                 "repeats the centre: the same head in the same place.")
    with h.section("Ring"):
        heads_union = h.union("Heads", placed_heads)
        joined = h.union("Joined", [beaded, heads_union], blend=ids["Shank Blend"], comment=(
            "The heads melt into the shank (a smooth union). Every seat is cut AFTER it, the pavé's last."))
        ring = h.subtract("Ring", joined, [*placed_seats, pave_seats])
        out = h.wrap_var("Ring Body", ring)
        integ, _mesh, export = nj.add_measure_mesh_export(h, out, out_var, ids["Mesh Tolerance"])
    return integ, export


def build(notebook, params: dict | None = None) -> dict:
    """Entry point for `api build multistone`; see the module docstring."""
    return nj.standard_build(notebook, params, DEFAULTS, _body, "multistone", blocks=("seat_block", "head_block", "open_bar_block"))
