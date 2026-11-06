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
Mesh do), and the API cannot set an enum at all ("unit_length_enum, which cannot be set yet"). So the unit is a
notebook input, `Points Units` (`nj.enum_input`), which nTopCL sets as an integer id - and which id means mm is
measured too: the points are 0.1 unit apart, so the three 1 mm balls' union says the unit (Python's own
union, POINT_UNIT_VOLUMES: mm 4.73 mm³, cm 9.83, inch / foot / metre 12.57 - apart, um 4.19):

    python -m ntopjewel api build points_probe           # nTop open (foreground), Python Console open; writes the two point files
    python -m ntopjewel templates ntop\notebooks\points_probe.ntop   # nTop's own template: does it name the unit ids?
    python -m ntopjewel run points_probe --set "Points Units=0" --set "Points Path=<repo>\out\api\points_probe.csv" --set "Output Path=<repo>\out\api\points_probe_0.stl"
    ... Points Units 1, 2, 3 ... until one comes back 4.73 mm³

A volume of 4.73 says that id is mm AND that Sphere maps the list (one ball alone is 4.19); 9.83 / 12.57 / 4.19
another unit; an [E] line what nTop could not read. (Run 3, 5 Nov: `Scalar_0: Input "Body" is incomplete` - the
Union fed the Mesh and the Volume Integral unwrapped, and nTop's exported recipe kept only the Mesh's wire;
the recipe also showed Sphere typed `list<sphere>`: nTop maps the list.) Comma-separated `x,y,z` lines (.csv) and whitespace-separated
(.txt) are both written, to learn which Import Points reads.
"""
from __future__ import annotations

from pathlib import Path

from ntopjewel import nb_jewel as nj

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
POINTS = [(0.0, 0.0, 0.0), (0.1, 0.0, 0.0), (0.0, 0.1, 0.0)]      # 0.1 unit apart: the balls' union says the unit
POINT_UNIT_VOLUMES = {"mm": 4.734, "cm": 9.83, "in": 12.565, "ft": 12.565, "m": 12.565, "um": 4.189}   # manifold3d, 2026-11-05
FORMATS = {"csv": ",", "txt": " "}
BALL_MM3 = 4.0 / 3.0 * 3.141592653589793          # a 1 mm ball
SPECS = [("Points Path", "path"), ("Radius", "mm"), ("Mesh Tolerance", "mm")]
INPUT_ORDER = [n for n, _ in SPECS] + ["Points Units", "Output Path"]
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
    "volume_hint": "three 1 mm balls 0.1 unit apart: 4.73 mm³ when the unit is mm and Sphere maps the list (POINT_UNIT_VOLUMES)",
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
        nj.enum_input(h, "Points Units", "unit_length_enum", pts, "Units")   # no default, and the API cannot set an enum
        h.comment(pts, "Import Points: one point per line of the file; Units is the notebook input Points Units (nTopCL sets it).")
        ball = h.add("Balls", nj.SPHERE, mask="sphere", must=[["sphere<point,real>"], ["sphere", "point", "real"]])
        h.wire(pts, ball, nj.CENTRE)                    # the whole list on a single point input
        h.wire(ids["Radius"], ball, ["Radius"])
        h.comment(ball, "The imported list wired to one Sphere: nTop maps it if this unites into three balls.")
        union = h.add("Union", mask="union", must=nj.UNION)
        h.wire(ball, union, nj.BODIES)                  # the list of balls into Bodies
        balls = h.wrap_var("Balls Body", union)         # measured AND meshed: a block output used twice loses a wire
    with h.section("Result"):
        integ, _mesh, export = nj.add_measure_mesh_export(h, balls, out_var, ids["Mesh Tolerance"])
    return integ, export


def build(notebook, params: dict | None = None) -> dict:
    """Entry point for `api build points_probe`."""
    return nj.standard_build(notebook, params, DEFAULTS, _body, "points_probe")
