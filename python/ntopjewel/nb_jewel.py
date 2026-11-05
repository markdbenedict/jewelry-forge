"""Shared building blocks for the Notebook API build scripts in ntop/recipes (stdlib only: this
module runs inside nTop's own Python).

Everything here was verified against nTop 6.3.3 on 2026-10-26/27 (see CLAUDE.md, "Notebook API
rules"): identifiers are snake_case + the input type list with the HIGHEST version taken,
file inputs are `core.var<text>` variables, `real_field` inputs are fed by wired variables,
measurement blocks build only once a typed variable consumes them, and the volume is a
`volume_integral` of a unitless 1 (a fresh notebook's unit table knows only mm).

A build script talks to nTop through `Helper` (below): verbs that each add one kind of block and
wire it - `h.union("Joined", [shank, heads], blend=var)`, `h.subtract("Ring", joined, [seat])`,
`h.import_body("Relief", path_var)` - so a notebook body reads like the docstring that describes it.
The candidate input names (nTop's spellings and their fallbacks) live in the verbs, once. A body is
grouped into named sections (`with h.section("Arches"):`) and the blocks that carry a rule get a
comment (`h.comment(block, "why")`), so the canvas explains itself.
"""
from __future__ import annotations

import inspect
import json
import time
from contextlib import contextmanager
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
ROTATION_TRANSFORM = [["rotation_transform<point,vector,real>"], ["rotation_transform"]]
TRANSFORM_OBJECT = [["transform_object", "transformation"], ["transform_object"]]
BOX_FROM_CORNERS = [["box_from_corners<point,point>"], ["box_from_corners"]]
MIRROR_BODY = [["mirror_body<implicit,plane>"], ["mirror_body"]]
PLANE = [["plane<point,vector,vector>"]]                          # Origin, X axis, Y axis (docs.ntop.com, Plane)
COMBINE_TRANSFORMS = [["combine_transforms<list<transformation>>"], ["combine_transforms"]]
PATH_VARS = ("core.var<text>",)      # file inputs: 6.3.3 cannot set a file_path variable, and a text one serves (nTopCL types it text)
INTEGER_VARS = ("core.var<integer>", "core.var<int>")

# the input names nTop 6.3.3 gives these blocks, first, then the spellings we met on the way (2026-10-26/28)
PRIMARY = ["Primary Body", "Body"]
CUTS = ["Subtraction Bodies", "Bodies"]
BODIES = ["Bodies"]
PATH_IN = ["Path", "File Path", "File", "Filename"]
EXPORT_PATH_IN = ["File Path", "File", "Path", "Filename", "Output"]
DISTANCE = ["Distance", "Offset"]
BLEND = ["Blend Radius", "Blend radius", "Radius", "Blend"]
MAPPING_LENGTH = ["Y mapping length", "Y Mapping Length", "Mapping Length", "Length"]
TUBE = ["Torus Radius", "Torus radius", "Tube"]
CENTRE = ["Center Point", "Center", "Point"]
SPACING = ["Angular Spacing", "Angular spacing", "Angle", "Spacing"]
COUNT = ["Count", "Number", "Copies"]
AXIS_POINT = ["Point", "Origin", "Center", "Position"]

# the profiled band's inputs, in catalog order (ring_band_profile.yaml); Output Path follows
BAND_INPUTS = ["Outer Radius", "Bore Radius", "Z Top", "Z Bottom", "Dome Ring Radius", "Dome Tube Radius",
               "Comfort Ring Radius", "Comfort Tube Radius", "Edge Round", "Edge Round Inward", "Mesh Tolerance"]

# a shank's bars: ring_shank.ntop and the solitaires import this many (ntopjewel.shank.bar_meshes writes them,
# an unused slot repeats the smallest bar) and unite them (add_wrapped_shank)
BAR_SLOTS = 4


def slot_name(k: int) -> str:
    """The input that takes bar slot k (0-based): Shank Path, Shank Path 2, ..."""
    return "Shank Path" if k == 0 else f"Shank Path {k + 1}"


SLOT_NAMES = tuple(slot_name(k) for k in range(BAR_SLOTS))
# the inputs of a notebook built on the bars, in catalog order (ring_shank, pave_band, ring_artwork, multistone)
SHANK_SPECS = [(n, "path") for n in SLOT_NAMES] + [("Wrap Length", "mm"), ("Edge Round", "mm"), ("Edge Round Inward", "mm"),
                                                   ("Mesh Tolerance", "mm")]


OPEN_BAR_SPECS = [("Bar Path", "path"), ("Edge Round Inward", "mm"), ("Edge Round", "mm"), ("Mesh Tolerance", "mm")]
BLOCK_DEFAULTS = {"open_bar_block": ("ntop", "blocks", "open_bar.ntop")}   # library blocks every runner of that kind embeds


def input_order(specs: list[tuple[str, str]]) -> list[str]:
    """A runner notebook's inputs in catalog order: its specs, then Output Path."""
    return [n for n, _ in specs] + ["Output Path"]


# ---- the helper: verbs, sections, comments ------------------------------------------------------
class Helper(NotebookHelper):
    """NotebookHelper plus one verb per kind of block we build, named sections and block comments.

    Sections and comments are organisation only - nTopCL builds the same graph without them - and
    their argument lists on nTop 6.3.3 were not verified when this was written (2026-11-04): every
    call is guarded, the first refusal is logged with the method's real signature and the build
    carries on without them. A build never fails for a section or a comment."""

    def __init__(self, notebook):
        super().__init__(notebook)
        self.section_id = ""                        # where add() puts new blocks ("" = nTop's default)
        self.section_ids: dict[str, str] = {}       # our section name -> nTop id, in order
        self._top_level_noted = False
        self.sections_ok = True
        self.comments_ok = True
        self._signatures_logged = False

    # ---- organisation -----------------------------------------------------------------
    def _log_signatures(self) -> None:
        if self._signatures_logged:
            return
        self._signatures_logged = True
        for name in ("add_section", "move_block", "set_block_comment", "collapse_section", "list_sections",
                     "add_block", "add_real_variable", "add_variable"):
            fn = getattr(self.nb, name, None)
            if fn is None:
                self.log.append(f"api: {name} - not on this notebook object")
                continue
            try:
                sig = str(inspect.signature(fn))
            except (TypeError, ValueError):
                sig = "(signature not introspectable)"
            doc = (getattr(fn, "__doc__", "") or "").strip().splitlines()
            self.log.append(f"api: {name}{sig}" + (f" - {doc[0][:160]}" if doc else ""))

    def _sections_off(self, why: str) -> None:
        if self.sections_ok:
            self.sections_ok = False
            self.log.append(f"sections off for this build (organisation only, the geometry is unaffected): {why}")
        self.section_id = ""

    def _new_section(self, name: str) -> str:
        """nTop's id for a new section called `name` ("" when sections are off)."""
        self._log_signatures()
        if not self.sections_ok:
            return ""
        if name in self.section_ids:
            return self.section_ids[name]
        fn = getattr(self.nb, "add_section", None)
        if not callable(fn):
            self._sections_off("this API has no add_section")
            return ""
        try:
            before = {s.get("id") for s in self.nb.list_sections()}
            info = fn(name)
            sid = info.get("id") if isinstance(info, dict) else (info if isinstance(info, str) else "")
            if not sid:                                   # the call returned nothing useful: find the new one
                new = [s for s in self.nb.list_sections() if s.get("id") not in before]
                sid = new[-1]["id"] if new else ""
            if not sid:
                raise ConsoleError(f"add_section({name!r}) returned {info!r} and no new section appeared")
        except Exception as e:
            self._sections_off(f"add_section({name!r}) refused: {e}")
            return ""
        self.section_ids[name] = sid
        self.log.append(f"section {name}: {sid}")
        return sid

    @contextmanager
    def section(self, name: str):
        """Blocks added inside go into the section called `name` (made on first use)."""
        outer = self.section_id
        self.section_id = self._new_section(name)
        try:
            yield self.section_id
        finally:
            self.section_id = outer if self.sections_ok else ""

    def place(self, block_id: str) -> None:
        """Where a wrapping variable goes: nowhere - it stays at the notebook's top level. 6.3.3 gives
        no way into a section for it (2026-11-04): `add_variable(new_name, block_id)` takes no section,
        and `move_block(block_id, targetBlockId, placeBefore)` moves only next to a TOP-LEVEL block
        ('Block "Implicit Body_5" is not a top level block of the notebook'), so a block inside a
        section cannot be its target. Real variables are made in their section (`real_var`)."""
        if self.sections_ok and self.section_id and not self._top_level_noted:
            self._top_level_noted = True
            self.log.append("note: wrapping variables stay at the top level (6.3.3: add_variable takes no section and "
                            "move_block moves only next to top-level blocks)")

    def comment(self, block_id: str, text: str) -> None:
        """A note on the block, shown with it in nTop: why it is there or why it comes in this order."""
        if not self.comments_ok:
            return
        fn = getattr(self.nb, "set_block_comment", None)
        try:
            if not callable(fn):
                raise ConsoleError("this API has no set_block_comment")
            fn(block_id, text)
        except Exception as e:
            self._log_signatures()
            self.comments_ok = False
            self.log.append(f"comments off for this build (organisation only): set_block_comment refused: {e}")

    def collapse_all_but(self, keep: Iterable[str] = ()) -> None:
        """Collapse every section we made except `keep` (the notebook then reads as an outline)."""
        fn = getattr(self.nb, "collapse_section", None)
        if not (self.sections_ok and callable(fn)):
            return
        keep = set(keep)
        for name, sid in self.section_ids.items():
            if name in keep:
                continue
            try:
                fn(sid)
            except Exception as e:
                self.log.append(f"collapse_section({sid!r}) refused: {e}; sections left expanded")
                return

    # ---- blocks, in the current section --------------------------------------------------
    def add(self, label: str, *candidates: str, mask: str = "", must: Iterable[str] = (), section_id: str = "") -> str:
        sid = section_id or (self.section_id if self.sections_ok else "")
        if not sid:
            return super().add(label, *candidates, mask=mask, must=must)
        if label in self.blocks:
            return super().add(label, *candidates, mask=mask, must=must)     # raises the clash
        try:
            bid = super().add(label, *candidates, mask=mask, must=must, section_id=sid)
        except ConsoleError:
            raise
        except Exception as e:                       # add_block(ident, section_id) refused: without sections
            if label in self.blocks:
                raise
            self._sections_off(f"add_block(..., {sid!r}) refused: {e}")
            return super().add(label, *candidates, mask=mask, must=must)
        return bid

    def real_var(self, name: str, value: float, units: str = "mm") -> str:
        """A `core.var<real>`, made in the current section (6.3.3's add_real_variable takes section_id)."""
        sid = self.section_id if self.sections_ok else ""
        if sid and units:
            try:
                info = self.nb.add_real_variable(name, value, units, sid)
                self.blocks[name] = info["id"]
                self.log.append(f"var {name} = {value} {units} (in {sid})")
                return info["id"]
            except Exception as e:
                self.log.append(f"add_real_variable({name!r}, ..., section_id={sid!r}) refused ({e}); made outside the section")
        return super().real_var(name, value, units)

    def wrap_var(self, name: str, block_id: str) -> str:
        vid = super().wrap_var(name, block_id)
        self.place(vid)
        return vid

    # ---- verbs ---------------------------------------------------------------------------
    def union(self, label: str, bodies: Iterable[str], blend: str | None = None, comment: str = "") -> str:
        """Boolean Union of `bodies`; `blend`: a mm variable wired to its Blend Radius (a smooth union)."""
        u = self.add(label, mask="union", must=UNION)
        for b in bodies:
            self.to_list(b, u, BODIES)
        if blend is not None:
            wire_blend(self, u, blend)
        if comment:
            self.comment(u, comment)
        return u

    def intersect(self, label: str, bodies: Iterable[str], blend: str | None = None, comment: str = "") -> str:
        x = self.add(label, mask="intersect", must=INTERSECT)
        for b in bodies:
            self.to_list(b, x, BODIES)
        if blend is not None:
            wire_blend(self, x, blend)
        if comment:
            self.comment(x, comment)
        return x

    def subtract(self, label: str, body: str, cuts: Iterable[str], comment: str = "") -> str:
        """Boolean Subtract: `body` less every body in `cuts` (sharp)."""
        s = self.add(label, mask="subtract", must=SUBTRACT)
        self.wire(body, s, PRIMARY)
        for c in cuts:
            self.to_list(c, s, CUTS)
        if comment:
            self.comment(s, comment)
        return s

    def offset(self, label: str, body: str, distance_var: str) -> str:
        o = self.add(label, mask="offset", must=OFFSET)
        self.wire(body, o, ["Body"])
        self.wire(distance_var, o, DISTANCE)
        return o

    def import_body(self, label: str, path_var: str) -> str:
        """A ring-frame body Python wrote: Import Mesh (`<label> Mesh`, Path from the text variable)
        -> Implicit from Mesh (`<label>`). Returns the implicit's id."""
        imp = self.add(f"{label} Mesh", mask="import_mesh", must=IMPORT_MESH)
        self.wire(path_var, imp, PATH_IN)
        body = self.add(label, mask="implicit_from_mesh", must=IMPLICIT_FROM_MESH)
        self.wire(imp, body, ["Mesh"])
        return body

    def mesh(self, label: str, body: str, tolerance_var: str) -> str:
        m = self.add(label, mask="mesh", must=MESH)
        self.wire(body, m, ["Body"])
        self.wire(tolerance_var, m, ["Tolerance"])
        return m

    def remap_cylindrical(self, label: str, body: str, length_var: str) -> str:
        """Remap Cylindrical Body: a bar (X radial, Y along the ring, Z axial) wrapped round Z."""
        w = self.add(label, mask="remap_cylindrical", must=REMAP_CYLINDRICAL)
        self.wire(body, w, ["Body"])
        self.wire(length_var, w, MAPPING_LENGTH)
        return w

    def rotation(self, label: str, angle_var: str, axis=(0.0, 0.0, 1.0), point: str | None = None) -> str:
        """Rotation Transform about `axis` through `point` (a Point block or variable; the origin when None)."""
        rot = self.add(label, mask="rotation_transform", must=ROTATION_TRANSFORM)
        if point is None:
            self.set(rot, [self.input_of_type(rot, "point")], [0.0, 0.0, 0.0], "mm")
        else:
            self.wire(point, rot, [self.input_of_type(rot, "point")])
        self.set(rot, [self.input_of_type(rot, "vector")], list(axis))
        self.wire(angle_var, rot, [self.input_of_type(rot, "real")])
        return rot

    def transform(self, label: str, body: str, transformation: str) -> str:
        """Transform Object: `body` moved by a transformation block or variable."""
        t = self.add(label, mask="transform_object", must=TRANSFORM_OBJECT)
        self.wire(body, t, [self.input_of_type(t, "spatial3d")])
        self.wire(transformation, t, [self.input_of_type(t, "transformation")])
        return t

    def cylinder(self, label: str, p1: str | None, p2: str | None, radius_var: str,
                 z_span: tuple[float, float] | None = None) -> str:
        """Cylinder Point 1 -> Point 2 (blocks or variables), or along Z over `z_span` (mm) when the points are None."""
        c = self.add(label, CYLINDER, mask="cylinder", must=[["cylinder", "point,point,real"], ["cylinder", "point", "real"]])
        if z_span is not None:
            self.set(c, ["Point 1"], [0.0, 0.0, float(z_span[0])], "mm")
            self.set(c, ["Point 2"], [0.0, 0.0, float(z_span[1])], "mm")
        else:
            self.wire(p1, c, ["Point 1"])
            self.wire(p2, c, ["Point 2"])
        self.wire(radius_var, c, ["Radius"])
        return c

    def torus(self, label: str, ring_var: str, tube_var: str, centre: str | None = None) -> str:
        """Torus about +Z: Radius (ring) and Torus Radius (tube) from variables, centred at the origin or `centre`."""
        t = self.add(label, TORUS, mask="torus", must=[["torus", "point", "vector"], ["torus"]])
        if centre is None:
            self.set(t, ["Center"], [0.0, 0.0, 0.0], "mm")
        else:
            self.wire(centre, t, ["Center"])
        set_axis(self, t)
        self.wire(ring_var, t, ["Radius"])
        self.wire(tube_var, t, TUBE)
        return t

    def sphere(self, label: str, centre: str, radius_var: str) -> str:
        s = self.add(label, SPHERE, mask="sphere", must=[["sphere<point,real>"], ["sphere", "point", "real"]])
        self.wire(centre, s, CENTRE)
        self.wire(radius_var, s, ["Radius"])
        return s

    def mirror(self, label: str, body: str, plane: str) -> str:
        """Mirror Body: `body` reflected across `plane` (a Plane block or variable, plane_block)."""
        m = self.add(label, mask="mirror_body", must=MIRROR_BODY)
        self.wire(body, m, [self.input_of_type(m, "implicit")])
        self.wire(plane, m, [self.input_of_type(m, "plane")])
        return m

    def combine(self, label: str, transforms: Iterable[str], applied_in: str = "") -> str:
        """Combine Transforms: one transformation doing `transforms` IN THE ORDER GIVEN (first
        applied first). nTop's list order is measured (api_fact "combine_transforms_order",
        ntop/recipes/transform_probe.py) and the list is laid out to match it."""
        order = applied_in or api_fact("combine_transforms_order")
        transforms = list(transforms) if order == "list" else list(transforms)[::-1]
        c = self.add(label, mask="combine_transforms", must=COMBINE_TRANSFORMS)
        slot = self.input_of_type(c, "list")
        for t in transforms:
            self.to_list(t, c, [slot])
        return c

    def polar_array(self, label: str, body: str, spacing_var: str, count_var: str, axis: str) -> str:
        a = self.add(label, mask="polar_array", must=POLAR_ARRAY)
        self.wire(body, a, ["Body"])
        self.wire(spacing_var, a, SPACING)
        self.wire(count_var, a, COUNT)
        self.wire(axis, a, ["Axis"])
        return a


# ---- variables ----------------------------------------------------------------------------------
def path_variable(h: NotebookHelper, name: str, value: str) -> str:
    """A file-path notebook input: a typed variable renamed to `name`. nTop 6.3.3's API cannot
    set a `file_path` parameter ("only real, vector, point, bool, integer and text"), so this is
    a `core.var<text>`, which Export/Import blocks accept on their file_path input and which
    nTopCL's template spells `text`."""
    return _typed_variable(h, name, value, PATH_VARS, str, "the {name} input")


def enum_input(h: NotebookHelper, name: str, enum_type: str, target: str, input_name: str) -> str:
    """An enum the API cannot set, made a notebook input for nTopCL to set at run time (an integer id in
    the input JSON): a `core.var<enum_type>` renamed to `name`, wired to `target`'s `input_name`, left
    without a value. nTop 6.3.3 refuses to set or read an enum ("has type "unit_length_enum", which cannot
    be set yet; only real, vector, point, bool, integer and text", 2026-11-05) - the real_field limit
    again, met the same way: a variable wired in. Import Points' Units has no default (nTopCL: `Input
    "Units" is incomplete`), unlike Import / Export Mesh's; the catalog gives the id."""
    ident = f"core.var<{enum_type}>"
    info = h.nb.add_block(ident)
    var_id = info["id"] if info["id"] == name else h.nb.rename_variable(info["id"], name)["id"]
    h.blocks[name] = var_id
    h.identifiers[name] = ident
    h.log.append(f"var {name}: {ident} (id {var_id}), no value - nTopCL sets it")
    h.wire(var_id, target, [input_name])
    return var_id


def integer_variable(h: NotebookHelper, name: str, value: int) -> str:
    """An integer notebook input: a `core.var<integer>` block renamed to `name` (there is no
    add_integer_variable; integer parameters can be set)."""
    return _typed_variable(h, name, value, INTEGER_VARS, int, "the integer input {name}")


def _typed_variable(h: NotebookHelper, name: str, value, idents, cast, what: str) -> str:
    nb = h.nb
    avail = h.available()
    errors = []
    for ident in idents:
        if ident not in avail:
            errors.append(f"{ident}: not available")
            continue
        info = None
        try:
            info = nb.add_block(ident)
            nb.set_block_input(info["id"], "Input", cast(value))
            var_id = info["id"] if info["id"] == name else nb.rename_variable(info["id"], name)["id"]
            h.blocks[name] = var_id
            h.identifiers[name] = ident
            h.log.append(f"var {name} = {cast(value)!r} via {ident} (id {var_id})")
            return var_id
        except Exception as e:
            h.log.append(f"fallback: {ident} cannot hold {name} through this API - nTop said: {e}")
            errors.append(f"{ident}: {e}")
            if info:                              # an unset block left behind fails the nTopCL run
                h.remove(info["id"])
    raise ConsoleError(f"no variable type could hold {what.format(name=name)}: " + "; ".join(errors))


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


def point_from_vars(h: NotebookHelper, label: str, x_var: str, y_var: str, z_var: str) -> str:
    """A Point block whose three components are wired from real variables."""
    pid = h.add(label, POINT, mask="point", must=[["point<real,real,real"], ["point", "real,real,real"]])
    h.wire(x_var, pid, ["X"])
    h.wire(y_var, pid, ["Y"])
    h.wire(z_var, pid, ["Z"])
    return pid


def plane_block(h: NotebookHelper, label: str, origin=(0.0, 0.0, 0.0), x_axis=(1.0, 0.0, 0.0), y_axis=(0.0, 1.0, 0.0)) -> str:
    """A Plane block (`plane<point,vector,vector>`: Origin, X axis, Y axis - the normal is X × Y,
    its sign irrelevant to a mirror). The inputs are found by type, in order: their names are
    not in the discovery dump."""
    pl = h.add(label, mask="plane", must=PLANE)
    ins = h.inputs(pl)
    point = next(i["name"] for i in ins if "point" in str(i.get("type", "")))
    vectors = [i["name"] for i in ins if "vector" in str(i.get("type", ""))]
    h.set(pl, [point], list(origin), "mm")
    h.set(pl, [vectors[0]], list(x_axis))
    h.set(pl, [vectors[1]], list(y_axis))
    return pl


def z_axis(h: NotebookHelper, label: str = "Z Axis", point: str | None = None) -> str:
    """An Axis along +Z through the origin, or through `point` (a Point block): `axis<point,vector>`,
    inputs `Point` and `Vector` (verified 2026-10-27)."""
    ax = h.add(label, mask="axis", must=AXIS)
    if point is None:
        try:
            h.set(ax, AXIS_POINT, [0.0, 0.0, 0.0], "mm")
        except Exception as e:
            h.log.append(f"axis origin not set ({e}); default kept")
    else:
        h.wire(point, ax, AXIS_POINT)
    set_axis(h, ax, name=h.input_name(ax, "Vector", "Direction", "Axis", "Normal"))
    return ax


def implicit_input(h: NotebookHelper, name: str) -> str:
    """A `core.var<implicit>` called `name`, for a block notebook to declare as an input (the seat
    cutter a head subtracts): a block takes another block's result this way instead of embedding it."""
    info = h.nb.add_block("core.var<implicit>")
    vid = info["id"] if info["id"] == name else h.nb.rename_variable(info["id"], name)["id"]
    h.blocks[name] = vid
    h.identifiers[name] = "core.var<implicit>"
    h.log.append(f"var {name}: core.var<implicit> (an input)")
    return vid


# ---- typed input lists (block notebooks and their harnesses declare the same ones) ----------
def add_typed_inputs(h: NotebookHelper, specs: list[tuple[str, str]], values: dict) -> dict[str, str]:
    """Create one variable per (name, kind) with the value from `values`: kind `mm` (real in mm),
    `deg` (angle), `int` (integer), `path` (a file path: text variable), `` (unitless real).
    Returns {name: variable id}, in order."""
    ids = {}
    for name, kind in specs:
        v = values[name]
        if kind == "path":
            ids[name] = path_variable(h, name, absolute(v, h, name))
        elif kind == "int":
            ids[name] = integer_variable(h, name, int(v))
        elif kind == "deg":
            ids[name] = angle_variable(h, name, float(v))
        else:
            ids[name] = h.real_var(name, float(v), kind)
    return ids


def add_band_inputs(h: NotebookHelper, values: dict) -> None:
    """The 11 real inputs of the profiled band, in catalog order, as mm variables."""
    for name in BAND_INPUTS:
        h.real_var(name, float(values[name]), "mm")


# ---- geometry shared by the notebooks -----------------------------------------------------------
OPENING_NOTE = ("The opening: offset in by the edge round, re-distance (a mesh round trip - Offset Body adds a constant to "
                "the field, so -e then +e would cancel), offset back out. Rounds every convex edge sharper than the "
                "radius and leaves the rest where it was.")


def add_redistance(h: Helper, base: str, body: str, tolerance_var: str) -> str:
    """Mesh from Implicit Body (at the notebook's Mesh Tolerance) -> Implicit Body from Mesh: the
    same body with a true distance field (`<base> Re-distanced Mesh` -> `<base> Re-distanced`). nTop's
    Offset Body adds a constant to the field it is given, so two offsets in a row (-e then +e, the
    opening that rounds every convex edge) cancel exactly unless the field is re-distanced between
    them: five band profiles built with the offsets back to back matched their UNopened sections to
    0.05 % (2026-10-30, nTop 6.3.3). Returns the id of the re-distanced implicit."""
    mesh = h.mesh(f"{base} Re-distanced Mesh", body, tolerance_var)
    out = h.add(f"{base} Re-distanced", mask="implicit_from_mesh", must=IMPLICIT_FROM_MESH)
    h.wire(mesh, out, ["Mesh"])
    return out


def add_opening(h: Helper, body: str, inward_var: str, outward_var: str, tolerance_var: str,
                name: str, base: str | None = None) -> str:
    """The morphological opening of a body by the edge round: `<base> Eroded` (Offset Body, -e) ->
    re-distance (add_redistance) -> `name` (Offset Body, +e). Rounds every convex edge sharper than
    the radius and leaves everything else exactly where it was; returns the id of the +e offset."""
    base = base or name
    eroded = h.offset(f"{base} Eroded", body, inward_var)
    exact = add_redistance(h, base, eroded, tolerance_var)
    opened = h.offset(name, exact, outward_var)
    h.comment(opened, OPENING_NOTE)
    return opened


def add_mesh_body(h: Helper, name: str, path_var: str) -> str:
    """A ring-frame body Python wrote (Helper.import_body)."""
    return h.import_body(name, path_var)


def add_carved(h: Helper, body_var: str, cut_var: str, relief_var: str, label: str = "Carved",
               knot_vars=()) -> str:
    """Artwork on a band (ntopjewel.artwork): (`body_var` − the panel cutters at Cut Path) ∪ the
    relief at Relief Path, as ring_artwork.ntop builds it - the band is opened before this, so the
    channel edges stay crisp and the relief is never rounded - ∪ the knot ornaments' layers at
    `knot_vars` (ntopjewel.ornament: two files, the pieces that cross each other apart). Returns
    the union's id."""
    cuts = h.import_body("Panel Cuts", cut_var)
    relief = h.import_body("Relief", relief_var)
    knots = [h.import_body("Knot" if k == 0 else f"Knot {k + 1}", var) for k, var in enumerate(knot_vars)]
    carved = h.subtract(label, body_var, [cuts],
                        comment="The panel channels, cut from the band after its opening: their edges stay crisp.")
    return h.union(f"{label} + Relief", [carved, relief, *knots],
                   comment="The motifs standing in the channels (and the knots on the face), never rounded.")


def open_bar_body(h: Helper, ids: dict) -> str:
    """The open_bar block's body (ntop/recipes/open_bar.py): the bar at Bar Path imported (`Bar`)
    and opened by the edge round (add_opening: `Bar Eroded` -> re-distance -> `Opened`)."""
    bar = h.import_body("Bar", ids["Bar Path"])
    return add_opening(h, bar, ids["Edge Round Inward"], ids["Edge Round"], ids["Mesh Tolerance"], name="Opened", base="Bar")


def add_wrapped_shank(h: Helper, path_vars, wrap_var: str, inward_var: str, outward_var: str,
                      tolerance_var: str, label: str = "Shank", opener: str | None = None) -> str:
    """The shank Python wrote as bars (ntopjewel.shank.ShankSpec.bar_meshes: X radial, Y along the
    ring, Z axial; `path_vars`: the text variables holding the shank.BAR_SLOTS paths, an unused
    slot repeating the smallest bar): per bar one `open_bar` block (`opener`: its identifier, from
    h.embed_block) = `Bar k Opened` - the bar imported and opened by the edge round, on the bar,
    where the field is exact; Boolean Union of the opened bars (`Bars`, sharp: bodies that cross
    each other - a knot's strands, a split's halves, a double band's bridges - are united here, as
    implicits, never as meshes: a mesh union leaves faces micrometres apart along its seams, which
    nTop's import read as self-intersecting, 2026-11-02) -> Remap Cylindrical Body (`label`, Y
    mapping length = wrap_var). Returns the id of the remap block, the ring-shaped shank. Without
    `opener` the six blocks per bar are laid out inline (open_bar_body's chain) - the fallback.

    Each bar is opened on its own, BEFORE the union: a union's field is the minimum of its bars'
    fields, so inside an overlap it measures to a bar's buried face, not to the part's surface,
    and the erosion cut a 0.05 mm groove along a split's seam (the halves' overlap wedge) all round
    the bottom of the ring (2026-11-02). Opened apart, each bar's convex edges round as designed
    (a slot's, a bridge's) and the overlap stays whole; a buried face's edges round inside the
    other bar, where nothing shows."""
    path_vars = [path_vars] if isinstance(path_vars, str) else list(path_vars)
    opened = []
    for k, path_var in enumerate(path_vars):
        bar = f"Bar {k + 1}"
        if opener:
            ob = h.add(f"{bar} Opened", opener)
            for var, name in ((path_var, "Bar Path"), (inward_var, "Edge Round Inward"), (outward_var, "Edge Round"),
                              (tolerance_var, "Mesh Tolerance")):
                h.wire(var, ob, [name])
            if k == 0:
                h.comment(ob, "open_bar: the bar imported and opened by the edge round on its own (offset in, "
                              "re-distance, offset out), before the union - one block per bar slot.")
            opened.append(ob)
        else:
            body = h.import_body(bar, path_var)
            opened.append(add_opening(h, body, inward_var, outward_var, tolerance_var, name=f"{bar} Opened", base=bar))
    if len(opened) == 1:
        joined = opened[0]
    else:
        joined = h.union("Bars", opened, comment=(
            "The opened bars united as implicits (sharp). Bodies that cross each other come in separate bars: "
            "a mesh union's seams import as self-intersections. An unused slot repeats the smallest bar."))
    wrapped = h.remap_cylindrical(label, joined, wrap_var)
    h.comment(wrapped, "The bar (X radial, Y along the ring, Z axial) wrapped round the ring axis: one turn = Wrap Length.")
    return wrapped


def add_profiled_band(h: Helper, extra=None) -> str:
    """Outer/Bore cylinders -> subtract -> ∩ dome torus ∩ comfort torus -> the opening by the edge
    round (add_opening). Expects the BAND_INPUTS variables (Mesh Tolerance included) to exist.
    Returns the id of the "Band Body" variable.

    `extra(h) -> body id`: a body united with the shaped band BEFORE the opening, so one rounding
    runs over both. Not for a body whose surface lies on the band's (the solitaire's arches did,
    and the re-distanced opening grew a 0.07 mm layer over their feet, 2026-10-31): open such a
    body on its own (add_opening) and unite it afterwards.

    Both tori are INTERSECTED: the dome torus (tube centred inside the outer surface) keeps the
    domed outside, the comfort torus (tube centred outside the bore) keeps the barrel bore.
    Subtracting the comfort torus removes the band (its tube covers the section) - 2026-10-26."""
    point_block(h, "P Bottom", z_var=h.blocks["Z Bottom"])
    point_block(h, "P Top", z_var=h.blocks["Z Top"])
    outer = h.cylinder("Outer", h.blocks["P Bottom"], h.blocks["P Top"], h.blocks["Outer Radius"])
    bore = h.cylinder("Bore", None, None, h.blocks["Bore Radius"], z_span=(-10.0, 10.0))
    band = h.subtract("Band", outer, [bore])
    tori = [h.torus(label, h.blocks[ring], h.blocks[tube])
            for label, ring, tube in (("Dome Torus", "Dome Ring Radius", "Dome Tube Radius"),
                                      ("Comfort Torus", "Comfort Ring Radius", "Comfort Tube Radius"))]
    shaped = h.intersect("Shaped", [band, *tori], comment=(
        "Both tori INTERSECTED: the dome torus keeps the domed outside, the comfort torus the barrel bore."))
    if extra is not None:
        shaped = h.union("Band + Extra", [shaped, extra(h)])
    profile = add_opening(h, shaped, h.blocks["Edge Round Inward"], h.blocks["Edge Round"], h.blocks["Mesh Tolerance"],
                          name="Band Profile", base="Band")
    return h.wrap_var("Band Body", profile)      # a variable: the body is consumed by more than one block


def wire_blend(h: NotebookHelper, block_id: str, var_id: str) -> str:
    """Feed a boolean's Blend Radius (a real_field: unsettable, wireable) from a mm variable. The
    Blend Type enum is left at nTop's default."""
    return h.wire(var_id, block_id, BLEND)


# ---- measure, mesh, export, finish --------------------------------------------------------------
def add_measure_mesh_export(h: Helper, body_var: str, out_var: str, tolerance_var: str) -> tuple[str, str, str]:
    """Volume Integral of 1 over the body (the Output), Mesh from Implicit Body, Export Mesh."""
    integ = h.add("Volume Integral", mask="volume_integral", must=VOLUME_INTEGRAL)
    h.wire(body_var, integ, h.input_of_type(integ, "implicit"))
    one = h.real_var("One", 1.0, "")           # dimensionless integrand: ∫ 1 dV = volume, no units needed
    h.wire(one, integ, h.input_of_type(integ, "real_field"))
    h.comment(integ, "The volume: ∫ 1 dV over the finished body (the notebook's Output; no density, no units).")
    mesh = h.mesh("Mesh", body_var, tolerance_var)
    export = h.add("Export Mesh", mask="export", must=EXPORT)
    h.wire(mesh, export, ["Mesh"])
    h.wire(out_var, export, EXPORT_PATH_IN)
    return integ, mesh, export


def finish(h: Helper, notebook, p: dict, input_order: Iterable[str], integ: str, export: str,
           test_output: str, volume_hint: str) -> dict:
    """Wrap the integral as the typed Output, declare the inputs, wait for the export, coax the
    measurement, check every block, tidy the sections, save, export the recipe; return the result."""
    vol_var = h.wrap_var("Volume", integ)        # typed (real, mm³): what nTopCL -t and the Output need
    h.declare_inputs(h.blocks[name] for name in input_order)
    h.set_output(vol_var)

    if p.get("lazy_ok"):                         # a harness: nTopCL is its test, the GUI need not build it
        lazy_warnings = settle(h, export, "Export Mesh", min(p["wait_s"], 60))
    else:
        lazy_warnings = []
        h.assert_ok(export, p["wait_s"])         # Export Mesh is the end of the geometry chain
    volume = h.pull_value(vol_var)               # asking for the value may trigger the lazy build
    meas_state = h.state(vol_var, min(p["wait_s"], 30))
    if meas_state.get("buildState") != "e_OK":
        h.nudge_build(integ)
        meas_state = h.state(vol_var, min(p["wait_s"], 30))
        volume = h.pull_value(vol_var)
    warnings = list(lazy_warnings)
    if meas_state.get("buildState") == "e_FAILED":
        raise ConsoleError(f"the volume did not build: {meas_state.get('error', '')}")
    if meas_state.get("buildState") != "e_OK":
        warnings.append(f"Volume stayed {meas_state.get('buildState')} in the GUI session (lazy block, nothing "
                        f"displays it); the Output is wired - nTopCL computes it at run time")

    states = h.states(0)
    failed = {k: v for k, v in states.items() if v.startswith(("e_FAILED", "e_UNBUILDABLE"))}
    if failed:
        raise ConsoleError("blocks failed to build: " + json.dumps(failed, indent=2))
    display = h.display_only(p["show"]) if p.get("show") else None     # a preview shows the finished body only
    if isinstance(h, Helper) and h.section_ids:
        h.collapse_all_but([list(h.section_ids)[-1]])                    # an outline: the result section open
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
        "display": display,
        "sections": dict(getattr(h, "section_ids", {})),
        "log": h.log,
    }


REPO_ROOT = Path(__file__).resolve().parents[2]      # python/ntopjewel/nb_jewel.py -> the repo
API_FACTS = REPO_ROOT / "ntop" / "api_facts.json"    # what ntop/recipes/transform_probe.py measured in nTop


def api_fact(key: str) -> str:
    """A fact about nTop the probe measured (api_facts.json); refuses, naming the probe, without it."""
    import os
    path = os.environ.get("NTOPJEWEL_API_FACTS") or API_FACTS          # the env: tests point it at their own
    try:
        facts = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        facts = {}
    if key not in facts:
        raise ConsoleError(f"{key} has not been measured on this nTop: run `python -m ntopjewel api build transform_probe` "
                           f"first (it writes {API_FACTS}; commit it)")
    return facts[key]


def absolute(path, h: NotebookHelper | None = None, what: str = "path") -> str:
    """Paths handed to the script must be absolute: it runs in nTop's Python, whose working
    directory is nTop's install folder (2026-10-27: `--out out\\ring` became
    `C:\\Program Files\\nTopology\\...\\out`, "Access is denied"). A relative path is taken
    as relative to the repo, which is what the caller meant."""
    p = Path(str(path))
    if p.is_absolute():
        return str(p)
    fixed = REPO_ROOT / p
    if h is not None:
        h.log.append(f"{what} {path!r} is relative; using {fixed} (nTop's cwd is its own folder)")
    return str(fixed)


def run_build(notebook, params: dict | None, defaults: dict, body_fn) -> dict:
    """Common `build()` shell: merge params, make folders, fresh notebook, pause, run `body_fn(h, p,
    values, out_var)` -> (integ, export), finish; on any error raise with the helper's diagnostics."""
    h = Helper(notebook)
    try:
        p = {**defaults, **(params or {})}
        values = {**defaults["values"], **(p.get("values") or {})}
        for key in ("test_output", "save_to", "recipe_to"):
            p[key] = absolute(p[key], h, key)
        if "Engraving Path" in values:
            values["Engraving Path"] = absolute(values["Engraving Path"], h, "Engraving Path")
        test_output = p["test_output"]
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


def standard_build(notebook, params: dict | None, defaults: dict, body_fn, name: str, blocks: Iterable[str] = ()) -> dict:
    """`build()` for a runner notebook: merge the params, refuse to run without input values (only
    prepare() on the laptop computes them), make each block path in `blocks` (param keys:
    "seat_block", "head_block") absolute and refuse a missing one, then run_build."""
    p = {**defaults, **(params or {})}
    values = {**defaults["values"], **(p.get("values") or {})}
    if not values:
        raise ConsoleError(f"no input values: run through `python -m ntopjewel api build {name}` (prepare() computes them)")
    for key in blocks:
        if key in BLOCK_DEFAULTS and not p.get(key):
            p[key] = str(REPO_ROOT.joinpath(*BLOCK_DEFAULTS[key]))
        p[key] = absolute(p[key])
        if not Path(p[key]).exists():
            raise ConsoleError(f"{p[key]} is missing: build it first (api build {Path(p[key]).stem})")
    p["values"] = values
    return run_build(notebook, p, {**defaults, "values": values}, body_fn)


# ---- library blocks: save, self-test, harness ---------------------------------------------------
def embed_self_test(notebook, block_path: str) -> dict:
    """Embed the saved block into a fresh notebook at once, so a block nTop will not accept is
    named here rather than as a harness failure later."""
    notebook.new_notebook()
    try:
        notebook.embed_custom_block(block_path)
    except Exception as e:
        raise ConsoleError(f"nTop refuses the saved block as a custom block: {e}") from e
    found = [b for b in notebook.list_custom_blocks() if b.get("name") == Path(block_path).stem]
    if not found:
        raise ConsoleError(f"embedded {block_path} but list_custom_blocks() does not name it")
    return {"accepted": True, "id": found[0]["id"]}


def save_block(notebook, h: NotebookHelper, body: str, inputs: Iterable[str], output_name: str, p: dict,
               self_test: bool = True) -> dict:
    """Finish a library block notebook: `body` wrapped as the typed Output `output_name`, `inputs`
    declared in order, saved to p["block_to"] (its recipe to p["block_recipe_to"]), then embedded
    in a fresh notebook as a self-test. A block notebook has no sections: nothing but its inputs,
    its few blocks and its Output, and a custom block's validity rules are strict enough (a block
    output used twice was refused, 2026-10-28) not to add anything untried."""
    out = h.wrap_var(output_name, body)
    h.declare_inputs(list(inputs))
    h.set_output(out)
    warnings = settle(h, body, "the block's Output")
    Path(p["block_to"]).parent.mkdir(parents=True, exist_ok=True)
    notebook.save_notebook_as(p["block_to"])
    try:
        notebook.export_as_recipe(p["block_recipe_to"], True)
    except Exception as e:
        h.log.append(f"export_as_recipe (block) failed: {e}")
    if not Path(p["block_to"]).exists():
        raise ConsoleError(f"the block was not saved to {p['block_to']}")
    res = {"saved": p["block_to"], "recipe": p["block_recipe_to"], "identifiers": h.identifiers, "warnings": warnings,
           "blocks": h.blocks, "states": h.states(0), "log": h.log}
    if self_test:
        res["self_test"] = embed_self_test(notebook, p["block_to"])
        h.log.append(f"self-test: {res['self_test']}")
    return res


def block_build(notebook, params: dict | None, defaults: dict, name: str, build_block_fn, harness_fn,
                needs_seat: bool = True) -> dict:
    """`build()` for a library block recipe: the block (`build_block_fn(notebook, p, values)`), then
    its harness (`harness_fn`, through run_build). `--scratch` puts the block beside the harness."""
    params = dict(params or {})
    if "save_to" in params and "block_to" not in params:          # --scratch: the block beside the harness
        params["block_to"] = str(Path(params["save_to"]).parent / f"{name}.ntop")
        params.setdefault("block_recipe_to", str(Path(params["save_to"]).parent / f"{name}.block.recipe.json"))
    p = {**defaults, **params}
    values = {**defaults["values"], **(p.get("values") or {})}
    if not values:
        raise ConsoleError(f"no input values: run through `python -m ntopjewel api build {name}` (prepare() computes them)")
    keys = ("block_to", "block_recipe_to") + (("seat_block",) if needs_seat else ())
    for key in keys:
        p[key] = absolute(p[key])
    if needs_seat and not Path(p["seat_block"]).exists():
        raise ConsoleError(f"{p['seat_block']} is missing: run `python -m ntopjewel api build stone_seat` first")
    p["values"] = values
    block = build_block_fn(notebook, p, values)
    res = run_build(notebook, p, {**defaults, "values": values}, harness_fn)
    res["block"] = block
    res["warnings"] = block.get("warnings", []) + res.get("warnings", [])
    return res


def seat_head_harness(head_label: str, seat_specs, geometry_specs, cutter_input: str, mesh_tolerance: bool = True):
    """The harness body of a head block: its inputs as notebook inputs, an embedded stone_seat fed
    Seat Path + Clearance, the embedded head fed the seat's cutter and its numbers, the result
    measured, meshed and exported."""
    def _harness(h, p, values, test_output):
        ids = add_typed_inputs(h, list(seat_specs) + list(geometry_specs) + [("Mesh Tolerance", "mm")], values)
        out_var = path_variable(h, "Output Path", test_output)
        seat = h.add("Stone Seat", h.embed_block(p["seat_block"]))
        for n, _ in seat_specs:
            h.wire(ids[n], seat, [n])
        head = h.add(head_label, h.embed_block(p["block_to"]))
        h.wire(seat, head, [cutter_input])
        for n, _ in geometry_specs:
            h.wire(ids[n], head, [n])
        body = h.wrap_var("Result", head)
        integ, _mesh, export = add_measure_mesh_export(h, body, out_var, ids["Mesh Tolerance"])
        return integ, export
    return _harness


def harness(h: NotebookHelper, p: dict, values: dict, test_output: str, block_path: str,
            specs: list[tuple[str, str]], label: str) -> tuple[str, str]:
    """The harness body every library block gets: its inputs as notebook inputs, the block
    embedded and fed them, the result measured, meshed and exported (Mesh Tolerance and Output
    Path after the block's own inputs). Must run without paused updates (the embed)."""
    ids = add_typed_inputs(h, specs + [("Mesh Tolerance", "mm")], values)
    out_var = path_variable(h, "Output Path", test_output)
    ident = h.embed_block(block_path)
    inst = h.add(label, ident)
    for name, _ in specs:
        h.wire(ids[name], inst, [name])
    body = h.wrap_var("Result", inst)
    integ, _mesh, export = add_measure_mesh_export(h, body, out_var, ids["Mesh Tolerance"])
    return integ, export


def settle(h: NotebookHelper, block_id: str, label: str, wait_s: float = 20) -> list[str]:
    """For the last block of a BLOCK notebook: raise if nTop reports it failed; if it is still
    unbuilt (e_DIRTY) after `wait_s`, return a warning and go on. A block notebook is never run
    on its own - the harness's nTopCL run builds and measures it - and nTop builds a combination
    in the GUI only when something displayed needs it (2026-10-28: prong_head's subtraction stayed
    e_DIRTY for minutes while its primitives showed). Waiting longer waits for nothing."""
    st = h.state(block_id, wait_s)
    state = st.get("buildState")
    if state in ("e_FAILED", "e_UNBUILDABLE"):
        raise ConsoleError(f"{label} ({block_id}) failed to build: {st.get('error', '')}")
    if state != "e_OK":
        msg = (f"{label} stayed {state} in the GUI session (lazy: nothing displayed needs it); saved anyway - "
               f"the harness run under nTopCL builds and gates it")
        h.log.append("warning: " + msg)
        return [msg]
    return []
