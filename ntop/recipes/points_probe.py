"""What nTop 6.3.3 does with a points file - the hammered texture rests on it (2026-11-05).

A hammered band's dimples are equal spheres at centres Python lays out; their union is the distance to
the nearest centre less one radius. Built natively that is Import Points (the discovery run found
`import_points<file_path,unit_length_enum>`: inputs Path, Units) -> Sphere with the whole list on its
Center Point -> one Boolean Union. Discovery found no block that places a body at every point of a list,
so this rests on nTop mapping a list fed into a single-item input - which nTop accepted (the wire was not
refused) but nothing has measured.

First try (5 Nov), measured in the GUI session: every block stayed e_DIRTY and no volume came back - a lazy
block's input errors stay hidden there (CLAUDE.md, "What only nTopCL tells you"). So the probe is a small
runner notebook, measured by nTopCL, which names any incomplete input and returns the volume. Its first run
named one: `Point List_0: Input "Units" is incomplete` - Import Points has no default unit (Import / Export
Mesh do), so `nj.set_units_mm` sets it, learning how nTop spells the value from an Import Mesh's default:

    python -m ntopjewel api build points_probe           # nTop open (foreground), Python Console open; writes the two point files
    python -m ntopjewel run points_probe --set "Points Path=out/api/points_probe.csv" --set "Output Path=out/api/points_probe.stl"
    python -m ntopjewel run points_probe --set "Points Path=out/api/points_probe.txt" --set "Output Path=out/api/points_probe_txt.stl"

Three 1 mm balls 10 mm apart: Volume 12.57 mm³ (and three shells in the STL) means Sphere maps the list;
4.19 the first point only; an [E] line names what nTop could not read. Comma-separated `x,y,z` lines
(.csv) and whitespace-separated (.txt) are both written, to learn which Import Points reads.
"""
from __future__ import annotations

from pathlib import Path

from ntopjewel import nb_jewel as nj

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
POINTS = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 10.0, 0.0)]
FORMATS = {"csv": ",", "txt": " "}
BALL_MM3 = 4.0 / 3.0 * 3.141592653589793          # a 1 mm ball
SPECS = [("Points Path", "path"), ("Radius", "mm"), ("Mesh Tolerance", "mm")]
INPUT_ORDER = [n for n, _ in SPECS] + ["Output Path"]
CSV = REPO / "out" / "api" / "points_probe.csv"

DEFAULTS = {
    "values": {"Points Path": str(CSV), "Radius": 1.0, "Mesh Tolerance": 0.1},
    "input_order": INPUT_ORDER,
    "test_output": str(REPO / "out" / "api" / "points_probe_test.stl"),
    "save_to": str(REPO / "ntop" / "notebooks" / "points_probe.ntop"),
    "recipe_to": str(REPO / "ntop" / "recipes" / "points_probe.recipe.json"),
    "pause": False,
    "lazy_ok": True,          # nTopCL is the test: the GUI session kept these blocks e_DIRTY
    "fresh": True,
    "wait_s": 60,
    "volume_hint": f"three 1 mm balls: {3 * BALL_MM3:.2f} mm³ if Sphere maps the imported list, {BALL_MM3:.2f} if it takes the first point",
}


def write_points(directory: Path) -> dict[str, str]:
    """The three points in both spellings; returns {format: path}."""
    out = {}
    for fmt, sep in FORMATS.items():
        path = Path(directory) / f"points_probe.{fmt}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(sep.join(f"{c:g}" for c in p) + "\n" for p in POINTS), encoding="ascii")
        out[fmt] = str(path)
    return out


def prepare(params: dict, work_dir: Path) -> dict:
    """Laptop side: the point files beside the notebook's test output."""
    paths = write_points(Path(params.get("points_dir") or CSV.parent))
    params["values"] = {**DEFAULTS["values"], "Points Path": paths["csv"], **(params.get("values") or {})}
    return params


def _body(h, p, values, test_output):
    ids = nj.add_typed_inputs(h, SPECS, values)
    out_var = nj.path_variable(h, "Output Path", test_output)
    with h.section("Balls"):
        pts = h.add("Imported Points", "import_points<file_path,unit_length_enum>", mask="import_points", must=[["import_points"]])
        h.wire(ids["Points Path"], pts, [h.input_of_type(pts, "file_path")])
        nj.set_units_mm(h, pts)                         # no default here (nTopCL: Input "Units" is incomplete)
        h.comment(pts, "Import Points: one point per line of the file, in mm.")
        ball = h.add("Balls", nj.SPHERE, mask="sphere", must=[["sphere<point,real>"], ["sphere", "point", "real"]])
        h.wire(pts, ball, nj.CENTRE)                    # the whole list on a single point input
        h.wire(ids["Radius"], ball, ["Radius"])
        h.comment(ball, "The imported list wired to one Sphere: nTop maps it if this unites into three balls.")
        union = h.add("Union", mask="union", must=nj.UNION)
        h.wire(ball, union, nj.BODIES)                  # the list of balls into Bodies
    with h.section("Result"):
        integ, _mesh, export = nj.add_measure_mesh_export(h, union, out_var, ids["Mesh Tolerance"])
    return integ, export


def build(notebook, params: dict | None = None) -> dict:
    """Entry point for `api build points_probe`."""
    return nj.standard_build(notebook, params, DEFAULTS, _body, "points_probe")
