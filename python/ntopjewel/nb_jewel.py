"""Shared building blocks for the Notebook API build scripts in ntop/recipes (stdlib only: this
module runs inside nTop's own Python).

Everything here was verified against nTop 6.3.3 on 2026-10-26/27 (see CLAUDE.md, "Notebook API
rules"): identifiers are snake_case + the input type list with the HIGHEST version taken,
file inputs are `core.var<text>` variables, `real_field` inputs are fed by wired variables,
measurement blocks build only once a typed variable consumes them, and the volume is a
`volume_integral` of a unitless 1 (a fresh notebook's unit table knows only mm).
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterable

from .notebook_api import ConsoleError, NotebookHelper

# ---- identifiers (candidates tried in order; the helper picks the highest version) -------------
POINT = "point<real,real,real>"
CYLINDER = "cylinder<point,point,real>"
TORUS = "torus<point,vector,real,real>"
SPHERE = "sphere<point,real>"
SUBTRACT = [["boolean_subtract", "implicit,list<implicit>"], ["boolean_subtract", "implicit"], ["subtract", "implicit"]]
INTERSECT = [["boolean_intersect", "list<implicit>"], ["boolean_intersect", "implicit"], ["intersect", "implicit"]]
UNION = [["boolean_union", "list<implicit>"], ["boolean_union", "implicit"], ["union", "implicit"]]
OFFSET = [["offset_implicit"], ["offset", "implicit"]]
VOLUME_INTEGRAL = [["volume_integral", "implicit", "real_field"], ["volume_integral"]]
MESH = [["implicit_to_mesh", "bool,bool"], ["implicit_to_mesh"], ["mesh_from_implicit_body"], ["mesh", "implicit"]]
EXPORT = [["export_mesh", "file_path"], ["export_mesh"]]
AXIS = [["axis<point,vector>"], ["axis", "point", "vector"]]
POLAR_ARRAY = [["polar_array_implicit", "axis"], ["polar_array", "implicit"]]
IMPORT_MESH = [["import_mesh", "file_path"], ["import_mesh"]]
IMPLICIT_FROM_MESH = [["implicit_from_mesh<mesh>"], ["implicit_from_mesh"], ["mesh_to_implicit"]]
REMAP_CYLINDRICAL = [["remap_cylindrical_implicit"], ["remap_cylindrical", "implicit"]]
PATH_VARS = ("core.var<file_path>", "core.var<text>")      # file inputs: the text route is the one that works
INTEGER_VARS = ("core.var<integer>", "core.var<int>")

# the profiled band's inputs, in catalog order (ring_band_profile.yaml); Output Path follows
BAND_INPUTS = ["Outer Radius", "Bore Radius", "Z Top", "Z Bottom", "Dome Ring Radius", "Dome Tube Radius",
               "Comfort Ring Radius", "Comfort Tube Radius", "Edge Round", "Edge Round Inward", "Mesh Tolerance"]


# ---- variables ----------------------------------------------------------------------------------
def path_variable(h: NotebookHelper, name: str, value: str) -> str:
    """A file-path notebook input: a typed variable renamed to `name`. nTop 6.3.3's API cannot
    set a `file_path` parameter ("only real, vector, point, bool, integer and text"), so this is
    a `core.var<text>`, which Export/Import blocks accept on their file_path input and which
    nTopCL's template spells `text`. The file_path route is still tried first for later APIs."""
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


def integer_variable(h: NotebookHelper, name: str, value: int) -> str:
    """An integer notebook input: a `core.var<integer>` block renamed to `name` (there is no
    add_integer_variable; integer parameters can be set)."""
    nb = h.nb
    avail = h.available()
    errors = []
    for ident in INTEGER_VARS:
        if ident not in avail:
            errors.append(f"{ident}: not available")
            continue
        info = None
        try:
            info = nb.add_block(ident)
            nb.set_block_input(info["id"], "Input", int(value))
            var_id = info["id"] if info["id"] == name else nb.rename_variable(info["id"], name)["id"]
            h.blocks[name] = var_id
            h.identifiers[name] = ident
            h.log.append(f"var {name} = {int(value)} via {ident} (id {var_id})")
            return var_id
        except Exception as e:
            errors.append(f"{ident}: {e}")
            if info:
                h.remove(info["id"])
    raise ConsoleError(f"no variable type could hold the integer input {name}: " + "; ".join(errors))


def angle_variable(h: NotebookHelper, name: str, degrees: float) -> str:
    """An angle in degrees. A fresh notebook's unit table knows `deg` (verified 2026-10-27,
    `add_real_variable("Bead Spacing", 4.1379, "deg")`); the other spellings stay as fallbacks."""
    import math
    errors = []
    for u in ("deg", "°", "degree", "degrees"):
        try:
            return h.real_var(name, float(degrees), u)
        except Exception as e:
            errors.append(f"{u}: {e}")
    h.log.append(f"angle units refused ({'; '.join(errors)}); using unitless radians")
    try:
        return h.real_var(name, math.radians(degrees), "rad")
    except Exception as e:
        errors.append(f"rad: {e}")
    return h.real_var(name, math.radians(degrees), "")


def set_axis(h: NotebookHelper, block_id: str, name: str = "Axis") -> None:
    """A unit vector input; nTop takes it without units (verified), mm as a fallback."""
    try:
        h.set(block_id, [name], [0.0, 0.0, 1.0])
    except Exception as e:
        h.log.append(f"{name} without units refused ({e}); retrying with mm")
        h.set(block_id, [name], [0.0, 0.0, 1.0], "mm")


def point_block(h: NotebookHelper, label: str, x_var: str | None = None, z_var: str | None = None,
                x: float = 0.0, y: float = 0.0, z: float = 0.0) -> str:
    """A Point block whose X and/or Z come from real variables (Point inputs cannot be chips of
    a point variable, but a Point block's components can be wired - learned in the GUI 2026-10-25)."""
    pid = h.add(label, POINT, mask="point", must=[["point<real,real,real"], ["point", "real,real,real"]])
    if x_var:
        h.wire(x_var, pid, ["X"])
    else:
        h.set(pid, ["X"], float(x), "mm")
    h.set(pid, ["Y"], float(y), "mm")
    if z_var:
        h.wire(z_var, pid, ["Z"])
    else:
        h.set(pid, ["Z"], float(z), "mm")
    return pid


def z_axis(h: NotebookHelper, label: str = "Z Axis") -> str:
    """An Axis through the origin along +Z (for polar arrays): `axis<point,vector>`, inputs
    `Point` and `Vector` (verified 2026-10-27)."""
    ax = h.add(label, mask="axis", must=AXIS)
    try:
        h.set(ax, ["Point", "Origin", "Center", "Position"], [0.0, 0.0, 0.0], "mm")
    except Exception as e:
        h.log.append(f"axis origin not set ({e}); default kept")
    set_axis(h, ax, name=h.input_name(ax, "Vector", "Direction", "Axis", "Normal"))
    return ax


# ---- the profiled band --------------------------------------------------------------------------
def add_band_inputs(h: NotebookHelper, values: dict) -> None:
    """The 11 real inputs of the profiled band, in catalog order, as mm variables."""
    for name in BAND_INPUTS:
        h.real_var(name, float(values[name]), "mm")


def add_profiled_band(h: NotebookHelper) -> str:
    """Outer/Bore cylinders -> subtract -> ∩ dome torus ∩ comfort torus -> offset -e -> offset +e.
    Expects the BAND_INPUTS variables to exist. Returns the id of the "Band Body" variable.

    Both tori are INTERSECTED: the dome torus (tube centred inside the outer surface) keeps the
    domed outside, the comfort torus (tube centred outside the bore) keeps the barrel bore.
    Subtracting the comfort torus removes the band (its tube covers the section) - 2026-10-26."""
    point_block(h, "P Bottom", z_var=h.blocks["Z Bottom"])
    point_block(h, "P Top", z_var=h.blocks["Z Top"])

    outer = h.add("Outer", CYLINDER, mask="cylinder", must=[["cylinder", "point,point,real"], ["cylinder", "point", "real"]])
    h.wire(h.blocks["P Bottom"], outer, ["Point 1"])
    h.wire(h.blocks["P Top"], outer, ["Point 2"])
    h.wire(h.blocks["Outer Radius"], outer, ["Radius"])

    bore = h.add("Bore", CYLINDER, mask="cylinder", must=[["cylinder", "point,point,real"], ["cylinder", "point", "real"]])
    h.set(bore, ["Point 1"], [0.0, 0.0, -10.0], "mm")
    h.set(bore, ["Point 2"], [0.0, 0.0, 10.0], "mm")
    h.wire(h.blocks["Bore Radius"], bore, ["Radius"])

    band = h.add("Band", mask="subtract", must=SUBTRACT)
    h.wire(outer, band, ["Primary Body", "Body"])
    h.to_list(bore, band, ["Subtraction Bodies", "Bodies"])

    tori = []
    for label, ring, tube in (("Dome Torus", "Dome Ring Radius", "Dome Tube Radius"),
                              ("Comfort Torus", "Comfort Ring Radius", "Comfort Tube Radius")):
        t = h.add(label, TORUS, mask="torus", must=[["torus", "point", "vector"], ["torus"]])
        h.set(t, ["Center"], [0.0, 0.0, 0.0], "mm")
        set_axis(h, t)
        h.wire(h.blocks[ring], t, ["Radius"])
        h.wire(h.blocks[tube], t, ["Torus radius", "Torus Radius", "Tube"])
        tori.append(t)

    shaped = h.add("Shaped", mask="intersect", must=INTERSECT)
    for body_id in (band, *tori):
        h.to_list(body_id, shaped, ["Bodies"])

    shrunk = h.add("Shrunk", mask="offset", must=OFFSET)
    h.wire(shaped, shrunk, ["Body"])
    h.wire(h.blocks["Edge Round Inward"], shrunk, ["Distance", "Offset"])
    profile = h.add("Band Profile", mask="offset", must=OFFSET)
    h.wire(shrunk, profile, ["Body"])
    h.wire(h.blocks["Edge Round"], profile, ["Distance", "Offset"])
    return h.wrap_var("Band Body", profile)      # a variable: the body is consumed by more than one block


# ---- measure, mesh, export, finish --------------------------------------------------------------
def add_measure_mesh_export(h: NotebookHelper, body_var: str, out_var: str, tolerance_var: str) -> tuple[str, str, str]:
    """Volume Integral of 1 over the body (the Output), Mesh from Implicit Body, Export Mesh."""
    integ = h.add("Volume Integral", mask="volume_integral", must=VOLUME_INTEGRAL)
    h.wire(body_var, integ, h.input_of_type(integ, "implicit"))
    one = h.real_var("One", 1.0, "")           # dimensionless integrand: ∫ 1 dV = volume, no units needed
    h.wire(one, integ, h.input_of_type(integ, "real_field"))

    mesh = h.add("Mesh", mask="mesh", must=MESH)
    h.wire(body_var, mesh, ["Body"])
    h.wire(tolerance_var, mesh, ["Tolerance"])

    export = h.add("Export Mesh", mask="export", must=EXPORT)
    h.wire(mesh, export, ["Mesh"])
    h.wire(out_var, export, ["File Path", "File", "Path", "Filename", "Output"])
    return integ, mesh, export


def finish(h: NotebookHelper, notebook, p: dict, input_order: Iterable[str], integ: str, export: str,
           test_output: str, volume_hint: str) -> dict:
    """Wrap the integral as the typed Output, declare the inputs, wait for the export, coax the
    measurement, check every block, save, export the recipe; return the result dict."""
    vol_var = h.wrap_var("Volume", integ)        # typed (real, mm³): what nTopCL -t and the Output need
    h.declare_inputs(h.blocks[name] for name in input_order)
    h.set_output(vol_var)

    h.assert_ok(export, p["wait_s"])             # Export Mesh is the end of the geometry chain
    volume = h.pull_value(vol_var)               # asking for the value may trigger the lazy build
    meas_state = h.state(vol_var, min(p["wait_s"], 30))
    if meas_state.get("buildState") != "e_OK":
        h.nudge_build(integ)
        meas_state = h.state(vol_var, min(p["wait_s"], 30))
        volume = h.pull_value(vol_var)
    warnings = []
    if meas_state.get("buildState") == "e_FAILED":
        raise ConsoleError(f"the volume did not build: {meas_state.get('error', '')}")
    if meas_state.get("buildState") != "e_OK":
        warnings.append(f"Volume stayed {meas_state.get('buildState')} in the GUI session (lazy block, nothing "
                        f"displays it); the Output is wired - nTopCL computes it at run time")

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
        "expected_volume_hint": volume_hint,
        "warnings": warnings,
        "blocks": h.blocks,
        "identifiers": h.identifiers,
        "states": states,
        "log": h.log,
    }


def run_build(notebook, params: dict | None, defaults: dict, body_fn) -> dict:
    """Common `build()` shell: merge params, make folders, fresh notebook, pause, run `body_fn(h, p,
    values, out_var)` -> (integ, export), finish; on any error raise with the helper's diagnostics."""
    h = NotebookHelper(notebook)
    try:
        p = {**defaults, **(params or {})}
        values = {**defaults["values"], **(p.get("values") or {})}
        test_output = str(p["test_output"])
        Path(test_output).parent.mkdir(parents=True, exist_ok=True)
        for key in ("save_to", "recipe_to"):
            Path(p[key]).parent.mkdir(parents=True, exist_ok=True)
        if p["fresh"]:
            notebook.new_notebook()
            h._available = None
        with h.paused(p["pause"]):
            integ, export = body_fn(h, p, values, test_output)
        return finish(h, notebook, p, p["input_order"], integ, export, test_output, p.get("volume_hint", ""))
    except Exception as e:
        raise ConsoleError(f"{type(e).__name__}: {e}\n--- diagnostics ---\n"
                           f"{json.dumps(h.diagnostics(), indent=1, default=str)[:8000]}") from e
