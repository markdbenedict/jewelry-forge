"""Build `ring_band_profile.ntop` through nTop's Notebook API (Private Beta, nTop 6.3+).

What it builds (see band-profile.md for the geometry and ntopjewel.band for the numbers):

    inputs (12 real/text variables, in catalog order)
    Outer / Bore cylinders  ->  Boolean Subtract (Band)  ->  Boolean Intersect with Dome Torus
    and Comfort Torus (Shaped)  ->  Offset Body (−e) -> Offset Body (+e) = Band Profile
    -> Volume Integral of the constant 1 over the body (variable "Volume" = the notebook Output)
    -> Mesh from Implicit Body -> Export Mesh (file = Output Path)

Why a volume integral and not Mass Properties: Mass Properties needs a Density in kg/m3, and a
fresh notebook's unit table knows only mm ("kg/m3" is not a unit this notebook knows, 2026-10-27);
∫ 1 dV needs no unit anywhere.

How to run it
  * From Claude Code on the laptop (nTop open, View > Python Console open):
        python -m ntopjewel api build band_profile            # --scratch to save under out\api first
  * Without SSH: `python -m ntopjewel api build band_profile --dry-run` prints one
    exec(open(r"...band_profile.driver.py").read()) line to paste into the GUI console;
    then `python -m ntopjewel api collect band_profile` reads the result.

Block identifiers and input names are looked up at run time (nTop says they may change
between releases); whatever was used is reported in the result and logged. The script
starts from a NEW notebook (new_notebook() discards unsaved work in the open one).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from ntopjewel.notebook_api import ConsoleError, NotebookHelper

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]

# Court profile, US 6, 4 mm wide, 1.3 mm thick: `python -m ntopjewel band --size 6 --profile court --dry-run`
TEST_VALUES = {
    "Outer Radius": 9.5534,
    "Bore Radius": 8.2534,
    "Z Top": 2.0,
    "Z Bottom": -2.0,
    "Dome Ring Radius": 3.2371,
    "Dome Tube Radius": 6.3163,
    "Comfort Ring Radius": 15.3894,
    "Comfort Tube Radius": 7.136,
    "Edge Round": 0.25,
    "Edge Round Inward": -0.25,
    "Mesh Tolerance": 0.1,
}
INPUT_ORDER = list(TEST_VALUES) + ["Output Path"]

# Identifiers as nTop 6.3.3 lists them (api build discover, 2026-10-26): snake_case + type list, sometimes a
# [version] suffix; the helper prefers the unversioned definition, then the newest version. The `must`
# alternatives are tried in order; "implicit" keeps scalar overloads (subtract<real,real>) out.
POINT = "point<real,real,real>"
CYLINDER = "cylinder<point,point,real>"
TORUS = "torus<point,vector,real,real>"
SUBTRACT = [["boolean_subtract", "implicit,list<implicit>"], ["boolean_subtract", "implicit"], ["subtract", "implicit"]]
INTERSECT = [["boolean_intersect", "list<implicit>"], ["boolean_intersect", "implicit"], ["intersect", "implicit"]]
OFFSET = [["offset_implicit"], ["offset", "implicit"]]
VOLUME_INTEGRAL = [["volume_integral", "implicit", "real_field"], ["volume_integral"]]   # ∫ field dV over a body
MESH = [["implicit_to_mesh", "bool,bool"], ["implicit_to_mesh"], ["mesh_from_implicit_body"], ["mesh", "implicit"]]
EXPORT = [["export_mesh", "file_path"], ["export_mesh"]]
PATH_VARS = ("core.var<file_path>", "core.var<text>")      # the Output Path input; Export Mesh wants a file_path

DEFAULTS = {
    "values": TEST_VALUES,
    "test_output": str(REPO / "out" / "api" / "ring_band_profile_test.stl"),
    "save_to": str(REPO / "ntop" / "notebooks" / "ring_band_profile.ntop"),
    "recipe_to": str(REPO / "ntop" / "recipes" / "ring_band_profile.recipe.json"),
    "pause": True,            # batch the edits with paused_updates()
    "fresh": True,            # start from new_notebook()
    "wait_s": 120,
}


def _path_variable(h: NotebookHelper, name: str, value: str) -> str:
    """The file-path notebook input: a typed variable renamed to `name`. nTop 6.3.3's API cannot
    set a `file_path` parameter yet ("only real, vector, point, bool, integer and text"), so in
    practice this is a `core.var<text>`, which Export Mesh accepts on its file_path input and
    which nTopCL's template then spells `text` (as the Phase 0 notebook did)."""
    nb = h.nb
    avail = h.available()
    errors = []
    for ident in PATH_VARS:
        if ident not in avail:
            errors.append(f"{ident}: not available")
            continue
        info = None
        try:
            info = nb.add_block(ident)
            nb.set_block_input(info["id"], "Input", value)
            var_id = info["id"] if info["id"] == name else nb.rename_variable(info["id"], name)["id"]
            h.blocks[name] = var_id
            h.identifiers[name] = ident
            h.log.append(f"var {name} = {value!r} via {ident} (id {var_id})")
            return var_id
        except Exception as e:
            h.log.append(f"fallback: {ident} cannot hold {name} through this API (expected on 6.3.3), trying the next "
                         f"variable type - nTop said: {e}")
            errors.append(f"{ident}: {e}")
            if info:                              # an unset block left behind fails the nTopCL run
                h.remove(info["id"])
    raise ConsoleError(f"no variable type could hold the {name} input: " + "; ".join(errors))


def _set_axis(h: NotebookHelper, block_id: str) -> None:
    """A unit vector input; nTop may insist on units for vectors, so try without, then with mm."""
    try:
        h.set(block_id, ["Axis"], [0.0, 0.0, 1.0])
    except Exception as e:
        h.log.append(f"Axis without units refused ({e}); retrying with mm")
        h.set(block_id, ["Axis"], [0.0, 0.0, 1.0], "mm")


def build(notebook, params: dict | None = None) -> dict:
    """Entry point for `api build band_profile`; see the module docstring."""
    h = NotebookHelper(notebook)
    try:
        return _build(notebook, params, h)
    except Exception as e:
        raise ConsoleError(f"{type(e).__name__}: {e}\n--- diagnostics ---\n{json.dumps(h.diagnostics(), indent=1, default=str)[:8000]}") from e


def _build(notebook, params: dict | None, h: NotebookHelper) -> dict:
    p = {**DEFAULTS, **(params or {})}
    values = {**TEST_VALUES, **(p.get("values") or {})}
    test_output = str(p["test_output"])
    Path(test_output).parent.mkdir(parents=True, exist_ok=True)
    for key in ("save_to", "recipe_to"):
        Path(p[key]).parent.mkdir(parents=True, exist_ok=True)

    if p["fresh"]:
        notebook.new_notebook()
        h._available = None

    with h.paused(p["pause"]):
        # ---- inputs as variables -------------------------------------------------------
        for name in TEST_VALUES:
            h.real_var(name, float(values[name]), "mm")
        out_var = _path_variable(h, "Output Path", test_output)

        # ---- points on the axis, z from the Z variables --------------------------------
        for label, zvar in (("P Bottom", "Z Bottom"), ("P Top", "Z Top")):
            pid = h.add(label, POINT, mask="point", must=[["point<real,real,real"], ["point", "real,real,real"]])
            h.set(pid, ["X"], 0.0, "mm")
            h.set(pid, ["Y"], 0.0, "mm")
            h.wire(h.blocks[zvar], pid, ["Z"])

        # ---- cylinders -------------------------------------------------------------------
        outer = h.add("Outer", CYLINDER, mask="cylinder", must=[["cylinder", "point,point,real"], ["cylinder", "point", "real"]])
        h.wire(h.blocks["P Bottom"], outer, ["Point 1"])
        h.wire(h.blocks["P Top"], outer, ["Point 2"])
        h.wire(h.blocks["Outer Radius"], outer, ["Radius"])

        bore = h.add("Bore", CYLINDER, mask="cylinder", must=[["cylinder", "point,point,real"], ["cylinder", "point", "real"]])
        h.set(bore, ["Point 1"], [0.0, 0.0, -10.0], "mm")
        h.set(bore, ["Point 2"], [0.0, 0.0, 10.0], "mm")
        h.wire(h.blocks["Bore Radius"], bore, ["Radius"])

        # ---- flat band -------------------------------------------------------------------
        band = h.add("Band", mask="subtract", must=SUBTRACT)
        h.wire(outer, band, ["Primary Body", "Body"])
        h.to_list(bore, band, ["Subtraction Bodies", "Bodies"])

        # ---- dome and comfort bore: both tori are INTERSECTED with the band ----------------
        # The dome torus (centred inside the outer surface) keeps the domed outside; the comfort
        # torus (centred outside the bore) keeps the barrel bore. Subtracting the comfort torus
        # removes the band instead (its tube covers the whole section) - seen 2026-10-26.
        dome_t = h.add("Dome Torus", TORUS, mask="torus", must=[["torus", "point", "vector"], ["torus"]])
        h.set(dome_t, ["Center"], [0.0, 0.0, 0.0], "mm")
        _set_axis(h, dome_t)
        h.wire(h.blocks["Dome Ring Radius"], dome_t, ["Radius"])
        h.wire(h.blocks["Dome Tube Radius"], dome_t, ["Torus radius", "Torus Radius", "Tube"])

        comfort_t = h.add("Comfort Torus", TORUS, mask="torus", must=[["torus", "point", "vector"], ["torus"]])
        h.set(comfort_t, ["Center"], [0.0, 0.0, 0.0], "mm")
        _set_axis(h, comfort_t)
        h.wire(h.blocks["Comfort Ring Radius"], comfort_t, ["Radius"])
        h.wire(h.blocks["Comfort Tube Radius"], comfort_t, ["Torus radius", "Torus Radius", "Tube"])

        shaped = h.add("Shaped", mask="intersect", must=INTERSECT)
        for body_id in (band, dome_t, comfort_t):
            h.to_list(body_id, shaped, ["Bodies"])

        # ---- edge round: offset in, offset out ------------------------------------------
        shrunk = h.add("Shrunk", mask="offset", must=OFFSET)
        h.wire(shaped, shrunk, ["Body"])
        h.wire(h.blocks["Edge Round Inward"], shrunk, ["Distance", "Offset"])
        profile = h.add("Band Profile", mask="offset", must=OFFSET)
        h.wire(shrunk, profile, ["Body"])
        h.wire(h.blocks["Edge Round"], profile, ["Distance", "Offset"])
        body = h.wrap_var("Band Body", profile)   # used twice below: nTop wants a variable for that

        # ---- measure, mesh, export ------------------------------------------------------
        integ = h.add("Volume Integral", mask="volume_integral", must=VOLUME_INTEGRAL)
        h.wire(body, integ, h.input_of_type(integ, "implicit"))
        one = h.real_var("One", 1.0, "")           # dimensionless integrand: ∫ 1 dV = volume, no units needed
        h.wire(one, integ, h.input_of_type(integ, "real_field"))

        mesh = h.add("Mesh", mask="mesh", must=MESH)
        h.wire(body, mesh, ["Body"])
        h.wire(h.blocks["Mesh Tolerance"], mesh, ["Tolerance"])

        export = h.add("Export Mesh", mask="export", must=EXPORT)
        h.wire(mesh, export, ["Mesh"])
        h.wire(out_var, export, ["File Path", "File", "Path", "Filename", "Output"])

    # ---- the Volume variable is the notebook Output, and the only consumer of the integral ----
    # nTop builds lazily: a block nothing displays or consumes stays e_DIRTY (seen 2026-10-26, a
    # 300 s wait for nothing). So wire the Output first, wait for the geometry chain, and treat a
    # measurement that still never builds in the GUI session as a warning: nTopCL evaluates the
    # Output at run time, which is what the notebook is for.
    vol_var = h.wrap_var("Volume", integ)        # a typed variable (real, mm³): what nTopCL -t and the Output need

    # ---- declare the notebook inputs and the output -----------------------------------
    h.declare_inputs(h.blocks[name] for name in INPUT_ORDER)
    h.set_output(vol_var)

    # ---- wait for the geometry chain and the export; then coax the measurement block ---
    h.assert_ok(export, p["wait_s"])             # Export Mesh is the end of the geometry chain
    volume = h.pull_value(vol_var)               # asking for the value may trigger the lazy build
    meas_state = h.state(vol_var, min(p["wait_s"], 30))
    if meas_state.get("buildState") != "e_OK":
        h.nudge_build(integ)                     # whatever build/visibility call this API has
        meas_state = h.state(vol_var, min(p["wait_s"], 30))
        volume = h.pull_value(vol_var)
    warnings = []
    if meas_state.get("buildState") == "e_FAILED":
        raise ConsoleError(f"the volume did not build: {meas_state.get('error', '')}")
    if meas_state.get("buildState") != "e_OK":
        warnings.append(f"Volume stayed {meas_state.get('buildState')} in the GUI session (lazy block, nothing "
                        f"displays it); the Output is wired - nTopCL computes it at run time")

    # ---- verify every block, save, export the recipe ----------------------------------
    states = h.states(min(10, p["wait_s"]))
    failed = {k: v for k, v in states.items() if v.startswith(("e_FAILED", "e_UNBUILDABLE"))}
    if failed:
        raise ConsoleError("blocks failed to build: " + json.dumps(failed, indent=2))
    notebook.save_notebook_as(p["save_to"])
    try:
        notebook.export_as_recipe(p["recipe_to"], True)
    except Exception as e:
        h.log.append(f"export_as_recipe failed: {e}")
    time.sleep(0.2)
    return {
        "saved": p["save_to"],
        "recipe": p["recipe_to"],
        "test_output": test_output,
        "test_output_exists": Path(test_output).exists(),
        "volume": volume,
        "expected_volume_hint": "about 244 mm³ for the court test values (BandSpec.design_volume_mm3)",
        "warnings": warnings,
        "blocks": h.blocks,
        "identifiers": h.identifiers,
        "states": states,
        "log": h.log,
    }
