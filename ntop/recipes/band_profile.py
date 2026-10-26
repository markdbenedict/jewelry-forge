"""Build `ring_band_profile.ntop` through nTop's Notebook API (Private Beta, nTop 6.3+).

What it builds (see band-profile.md for the geometry and ntopjewel.band for the numbers):

    inputs (12 real/text variables, in catalog order)
    Outer / Bore cylinders  ->  Boolean Subtract  ->  ∩ Dome Torus  ->  − Comfort Torus
    -> Offset Body (−e) -> Offset Body (+e) = Band Profile
    -> Mass Properties (Volume -> variable "Volume" = the notebook Output)
    -> Mesh from Implicit Body -> Export Mesh (file = Output Path)

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

# Identifier alternatives, tried in order; "implicit" keeps scalar/mesh overloads (subtract<real,real>) out.
SUBTRACT = [["boolean subtract", "implicit"], ["subtract", "implicit"], ["difference", "implicit"], ["boolean subtract"]]
INTERSECT = [["boolean intersect", "implicit"], ["intersect", "implicit"], ["boolean intersect"]]
OFFSET = [["offset body", "implicit"], ["offset", "implicit body"], ["offset body"]]

DEFAULTS = {
    "values": TEST_VALUES,
    "test_output": str(REPO / "out" / "api" / "ring_band_profile_test.stl"),
    "save_to": str(REPO / "ntop" / "notebooks" / "ring_band_profile.ntop"),
    "recipe_to": str(REPO / "ntop" / "recipes" / "ring_band_profile.recipe.json"),
    "pause": True,            # batch the edits with paused_updates()
    "fresh": True,            # start from new_notebook()
    "density": (1000.0, "kg/m^3"),
    "wait_s": 300,
}


def _text_variable(h: NotebookHelper, name: str, value: str) -> str:
    """A Text notebook input. Two documented routes; the first that works wins."""
    nb = h.nb
    try:
        info = nb.add_block("core.var")
        nb.set_block_input(info["id"], "Input", value)
        var_id = nb.rename_variable(info["id"], name)["id"] if info["id"] != name else info["id"]
        h.blocks[name] = var_id
        h.log.append(f"text var {name} via core.var")
        return var_id
    except Exception as e:                      # fall back to a Text block wrapped in a variable
        h.log.append(f"core.var route failed ({e}); using a text block")
    tid = h.add(f"{name} text", "text<text>", "text", mask="text", must=["text"])
    h.set(tid, ["Text", "Value", "Input", "String"], value)
    return h.wrap_var(name, tid)


def build(notebook, params: dict | None = None) -> dict:
    p = {**DEFAULTS, **(params or {})}
    values = {**TEST_VALUES, **(p.get("values") or {})}
    test_output = str(p["test_output"])
    Path(test_output).parent.mkdir(parents=True, exist_ok=True)
    for key in ("save_to", "recipe_to"):
        Path(p[key]).parent.mkdir(parents=True, exist_ok=True)

    h = NotebookHelper(notebook)
    if p["fresh"]:
        notebook.new_notebook()
        h._available = None

    with h.paused(p["pause"]):
        # ---- inputs as variables -------------------------------------------------------
        for name in TEST_VALUES:
            h.real_var(name, float(values[name]), "mm")
        out_var = _text_variable(h, "Output Path", test_output)

        # ---- points on the axis, z from the Z variables --------------------------------
        for label, zvar in (("P Bottom", "Z Bottom"), ("P Top", "Z Top")):
            pid = h.add(label, "point<real,real,real>", mask="point", must=[["point<real,real,real"], ["point", "real,real,real"]])
            h.set(pid, ["X"], 0.0, "mm")
            h.set(pid, ["Y"], 0.0, "mm")
            h.wire(h.blocks[zvar], pid, ["Z"])

        # ---- cylinders -------------------------------------------------------------------
        outer = h.add("Outer", "cylinder<point,point,real>", mask="cylinder", must=[["cylinder", "point,point,real"], ["cylinder", "point", "real"]])
        h.wire(h.blocks["P Bottom"], outer, ["Point 1"])
        h.wire(h.blocks["P Top"], outer, ["Point 2"])
        h.wire(h.blocks["Outer Radius"], outer, ["Radius"])

        bore = h.add("Bore", "cylinder<point,point,real>", mask="cylinder", must=[["cylinder", "point,point,real"], ["cylinder", "point", "real"]])
        h.set(bore, ["Point 1"], [0.0, 0.0, -10.0], "mm")
        h.set(bore, ["Point 2"], [0.0, 0.0, 10.0], "mm")
        h.wire(h.blocks["Bore Radius"], bore, ["Radius"])

        # ---- flat band -------------------------------------------------------------------
        band = h.add("Band", mask="subtract", must=SUBTRACT)
        h.wire(outer, band, ["Primary Body", "Body"])
        h.to_list(bore, band, ["Subtraction Bodies", "Bodies"])

        # ---- dome: intersect with a torus ------------------------------------------------
        dome_t = h.add("Dome Torus", "torus<point,vector,real,real>", mask="torus", must=[["torus", "point", "vector"], ["torus"]])
        h.set(dome_t, ["Center"], [0.0, 0.0, 0.0], "mm")
        h.set(dome_t, ["Axis"], [0.0, 0.0, 1.0])
        h.wire(h.blocks["Dome Ring Radius"], dome_t, ["Radius"])
        h.wire(h.blocks["Dome Tube Radius"], dome_t, ["Torus radius", "Torus Radius", "Tube"])

        domed = h.add("Domed", mask="intersect", must=INTERSECT)
        h.to_list(band, domed, ["Bodies"])
        h.to_list(dome_t, domed, ["Bodies"])

        # ---- comfort bore: subtract a torus ----------------------------------------------
        comfort_t = h.add("Comfort Torus", "torus<point,vector,real,real>", mask="torus", must=[["torus", "point", "vector"], ["torus"]])
        h.set(comfort_t, ["Center"], [0.0, 0.0, 0.0], "mm")
        h.set(comfort_t, ["Axis"], [0.0, 0.0, 1.0])
        h.wire(h.blocks["Comfort Ring Radius"], comfort_t, ["Radius"])
        h.wire(h.blocks["Comfort Tube Radius"], comfort_t, ["Torus radius", "Torus Radius", "Tube"])

        shaped = h.add("Shaped", mask="subtract", must=SUBTRACT)
        h.wire(domed, shaped, ["Primary Body", "Body"])
        h.to_list(comfort_t, shaped, ["Subtraction Bodies", "Bodies"])

        # ---- edge round: offset in, offset out ------------------------------------------
        shrunk = h.add("Shrunk", mask="offset", must=OFFSET)
        h.wire(shaped, shrunk, ["Body"])
        h.wire(h.blocks["Edge Round Inward"], shrunk, ["Distance", "Offset"])
        profile = h.add("Band Profile", mask="offset", must=OFFSET)
        h.wire(shrunk, profile, ["Body"])
        h.wire(h.blocks["Edge Round"], profile, ["Distance", "Offset"])

        # ---- measure, mesh, export ------------------------------------------------------
        mass = h.add("Mass Properties", mask="mass", must=[["mass properties", "implicit"], ["mass properties"], ["mass", "implicit"]])
        h.wire(profile, mass, ["Body"])
        dens, dens_units = p["density"]
        try:
            h.set(mass, ["Density"], float(dens), dens_units)
        except Exception as e:                  # some overloads take no density
            h.log.append(f"density not set ({e})")

        mesh = h.add("Mesh", mask="mesh", must=[["mesh from implicit body"], ["mesh from implicit"], ["mesh", "implicit body"]])
        h.wire(profile, mesh, ["Body"])
        h.wire(h.blocks["Mesh Tolerance"], mesh, ["Tolerance"])

        export = h.add("Export Mesh", mask="export", must=[["export mesh"], ["export", "mesh"]])
        h.wire(mesh, export, ["Mesh"])
        h.wire(out_var, export, ["File", "Path", "Filename", "File Path", "Output"])

    # ---- let it build, then read the volume through a variable ------------------------
    h.assert_ok(mass, p["wait_s"])
    props = [pr["name"] for pr in notebook.list_block_properties(mass)]
    vol_prop = next((n for n in props if n.lower() == "volume"), None) or next((n for n in props if "volume" in n.lower()), None)
    if not vol_prop:
        raise ConsoleError(f"Mass Properties has no Volume property; it offers {props}")
    vol_var = h.property_var("Volume", mass, vol_prop)

    # ---- declare the notebook inputs and the output -----------------------------------
    h.declare_inputs(h.blocks[name] for name in INPUT_ORDER)
    h.set_output(vol_var)

    # ---- verify every block, save, export the recipe ----------------------------------
    states = h.states(p["wait_s"])
    failed = {k: v for k, v in states.items() if not v.startswith("e_OK") and not v.startswith("?")}
    if failed:
        raise ConsoleError("blocks failed to build: " + json.dumps(failed, indent=2))
    volume = h.output_value(vol_var)
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
        "expected_volume_hint": "a little under 290.95 mm³ for the court test values",
        "blocks": h.blocks,
        "identifiers": h.identifiers,
        "states": states,
        "log": h.log,
    }
