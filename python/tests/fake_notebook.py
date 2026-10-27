"""An in-memory stand-in for nTop's `notebook` object (Notebook API v0.14 surface we use).

It mimics the documented behaviour closely enough to exercise build scripts offline:
exact identifiers, returned ids with numeric suffixes, list-type inputs, variables whose
id is their name, build states, properties that exist only once a block has "built".
"""
from __future__ import annotations

from contextlib import contextmanager

# identifier -> (display name, [(input name, type), ...], output type)
# Taken from `api build discover` on nTop 6.3.3 (2026-10-26): snake_case identifiers with the type
# list, sometimes a [version] suffix; typed variables are core.var<T>; decoys included on purpose.
BOOL_SUB = [("Blend Type", "blend_enum"), ("Blend Radius", "real_field"), ("Primary Body", "implicit"),
            ("Subtraction Bodies", "list<implicit>")]
BOOL_N = [("Blend Type", "blend_enum"), ("Blend Radius", "real_field"), ("Bodies", "list<implicit>")]
MESH_IN = [("Body", "implicit"), ("Tolerance", "real"), ("Min. feature size", "real"), ("Sharpen", "bool"), ("Simplify", "bool")]
SIGNATURES = {
    "sphere<point,real>": ("Sphere", [("Center Point", "point"), ("Radius", "real")], "sphere"),
    "point<real,real,real>": ("Point", [("X", "real"), ("Y", "real"), ("Z", "real")], "point"),
    "vector<real,real,real>": ("Vector", [("X", "real"), ("Y", "real"), ("Z", "real")], "vector"),
    "cylinder<point,point,real>": ("Cylinder", [("Point 1", "point"), ("Point 2", "point"), ("Radius", "real")], "cylinder"),
    "cylinder_from_lineseg<line_segment,real>": ("Cylinder from Line Segment", [("Line", "line_segment"), ("Radius", "real")], "cylinder"),
    "torus<point,vector,real,real>": ("Torus", [("Center", "point"), ("Axis", "vector"), ("Radius", "real"), ("Torus Radius", "real")], "torus"),
    "boolean_subtract<blend_enum,real_field,implicit,list<implicit>>[5.44.0]": ("Boolean Subtract", BOOL_SUB, "implicit"),
    "boolean_subtract<blend_enum,real_field,implicit,list<implicit>>[1.1.0]": ("Boolean Subtract", BOOL_SUB, "implicit"),
    "boolean_subtract<blend_enum,real_field,implicit,list<implicit>>": ("Boolean Subtract", BOOL_SUB, "implicit"),
    "slice_stack_boolean_subtract<slice_stack,list<slice_stack>>": ("Slice Stack Boolean Subtract", [("Primary", "slice_stack"), ("Others", "list<slice_stack>")], "slice_stack"),
    "boolean_intersect<blend_enum,real_field,list<implicit>>[5.44.0]": ("Boolean Intersect", BOOL_N, "implicit"),
    "boolean_intersect<blend_enum,real_field,list<implicit>>": ("Boolean Intersect", BOOL_N, "implicit"),
    "boolean_union<blend_enum,real_field,list<implicit>>": ("Boolean Union", BOOL_N, "implicit"),
    "offset_implicit<implicit,real_field>": ("Offset Body", [("Body", "implicit"), ("Distance", "real_field")], "implicit"),
    "thicken_implicit<implicit,real_field>": ("Thicken Body", [("Body", "implicit"), ("Thickness", "real_field")], "implicit"),
    "mass_properties<mesh,real>[2.1.0]": ("Mass Properties", [("Mesh", "mesh"), ("Density", "real")], "body_mass_props"),
    "mass_properties<implicit,real_field,real>[1.1.0]": ("Mass Properties", [("Body", "implicit"), ("Density", "real_field"), ("Relative Error", "real")], "body_mass_props"),
    "mass_properties_from_body<implicit,real_field,real>": ("Mass Properties", [("Body", "implicit"), ("Density", "real_field"), ("Relative error", "real")], "body_mass_props"),
    "implicit_to_mesh<implicit,real,real,bool,bool>[2.4.0]": ("Mesh from Implicit Body", MESH_IN, "mesh"),
    "implicit_to_mesh<implicit,real,real,bool,bool>[2.5.0]": ("Mesh from Implicit Body", MESH_IN, "mesh"),
    "implicit_to_mesh<implicit,real,real,integer,implicit,bool>[2.5.0]": ("Mesh from Implicit Body", [("Body", "implicit"), ("Tolerance", "real"), ("Min. feature size", "real"), ("Iterations", "integer"), ("Keep", "implicit"), ("Simplify", "bool")], "mesh"),
    "mesh_from_implicit_body_2<implicit,real>": ("Mesh from Implicit Body", [("Body", "implicit"), ("Tolerance", "real")], "mesh"),
    "export_mesh<file_path,mesh,unit_length_enum>": ("Export Mesh", [("Path", "file_path"), ("Mesh", "mesh"), ("Units", "unit_length_enum")], "file"),
    "export_multi_region_mesh<file_path,mr_mesh,unit_length_enum>[5.51.0]": ("Export Multi-Region Mesh", [("File Path", "file_path"), ("Mesh", "mr_mesh"), ("Units", "unit_length_enum")], "file"),
    "subtract<real,real>": ("Subtract", [("A", "real"), ("B", "real")], "real"),          # scalar decoy
    "offset_voxel_grid<voxel_grid,real>[1.1.0]": ("Offset Voxel Grid", [("Grid", "voxel_grid"), ("Distance", "real")], "voxel_grid"),
    "core.var<real>": ("Scalar Variable", [("Input", "real")], "real"),
    "core.var<text>": ("Text Variable", [("Input", "text")], "text"),
    "core.var<file_path>": ("File Path Variable", [("Input", "file_path")], "file_path"),
    "core.var<implicit>": ("Implicit Body Variable", [("Input", "implicit")], "implicit"),
    "core.var_any<any>": ("Variable", [("x", "any")], "any"),
}
PROPERTIES = {"body_mass_props": ["Mass", "Volume", "Center of Mass", "Surface Area"], "implicit": ["Bounding Box"]}
DISPLAY_BASE = {"implicit": "Implicit Body", "body_mass_props": "Mass properties", "file": "Mesh File Data", "file_path": "Path",
                "text": "Text", "real": "Scalar"}
FILE_PATH_REFUSAL = ('Parameter "Input" of block "{bid}" has type "file_path", which cannot be set yet; only "real", "vector", '
                     '"point", "bool", "integer" and "text" parameters can.')


class FakeNotebook:
    def __init__(self, available=None, fail_blocks=(), unmasked_limit=None, lazy_mass="pull"):
        self.available_ids = list(available or SIGNATURES)
        self.unmasked_limit = unmasked_limit      # simulate a partial list from list_available_blocks()
        # nTop builds lazily: Mass Properties stays e_DIRTY until something consumes it. "pull": builds once
        # a variable wired from it is asked for its value; "method": builds on build_block(id); "never": stays dirty.
        self.lazy_mass = lazy_mass
        self.built: set[str] = set()
        if lazy_mass == "method":
            self.build_block = self._build_block
        self.blocks: dict[str, dict] = {}       # id -> {funcId, name, inputs: {name: value}, lists: {name: [ids]}, wired: {input: (src, prop)}}
        self.variables: dict[str, dict] = {}    # id -> {value, units, wraps, wired}
        self.counter: dict[str, int] = {}
        self.inputs: list[str] = []
        self.output: str | None = None
        self.saved: list[str] = []
        self.recipes: list[str] = []
        self.fresh = 0
        self.paused = False
        self.fail_blocks = set(fail_blocks)

    # ---- discovery ----------------------------------------------------------------
    def list_available_blocks(self, mask: str = ""):
        hits = [i for i in self.available_ids if mask in i]         # case-sensitive, like a real substring match
        if not mask and self.unmasked_limit is not None:
            hits = hits[: self.unmasked_limit]
        return hits

    def list_sections(self):
        return [{"name": "Section 1", "id": "section_0"}]

    def list_blocks(self, section_id: str = ""):
        return [{"name": b["name"], "id": i, "funcId": b["funcId"]} for i, b in self.blocks.items()]

    def list_variables(self):
        return [{"name": i, "id": i, "funcId": v.get("funcId", "core.var<...>"), "blockFuncId": v.get("wraps_func", "")}
                for i, v in self.variables.items()]

    # ---- blocks -------------------------------------------------------------------
    def _new_id(self, base: str) -> str:
        n = self.counter.get(base, 0)
        self.counter[base] = n + 1
        return f"{base}_{n}"

    def add_block(self, identifier: str, section_id: str = "", targetBlockId: str = "", placeBefore: bool = False):
        if identifier not in self.available_ids:
            raise ValueError(f"'{identifier}' is not a block available to this notebook")
        name, inputs, out = SIGNATURES[identifier]
        if identifier.startswith("core.var<"):              # a typed variable block; its id is a display name
            bid = self._new_id(DISPLAY_BASE.get(out, out.title()))
            self.variables[bid] = {"value": None, "units": "", "wraps": None, "typed": out, "funcId": identifier}
            return {"name": name, "id": bid, "funcId": identifier}
        bid = self._new_id(DISPLAY_BASE.get(out, out.title()))
        self.blocks[bid] = {"funcId": identifier, "name": name, "inputs": {}, "lists": {}, "wired": {}, "out": out,
                            "defs": inputs}
        return {"name": name, "id": bid, "funcId": identifier}

    def _resolve(self, block_id: str) -> dict:
        if block_id in self.blocks:
            return self.blocks[block_id]
        if block_id in self.variables:
            v = self.variables[block_id]
            if v.get("wraps") in self.blocks:
                return self.blocks[v["wraps"]]
            return {"funcId": v.get("funcId", "core.var"), "name": block_id, "inputs": {}, "lists": {}, "wired": {},
                    "out": v.get("typed") or "any",
                    "defs": [("Input" if v.get("typed") else "x", v.get("typed") or "any")]}
        raise ValueError(f"no block with id '{block_id}'")

    def list_block_inputs(self, id: str):
        b = self._resolve(id)
        out = [{"name": n, "type": t, "isReturnValue": False} for n, t in b["defs"]]
        out.append({"name": id, "type": b["out"], "isReturnValue": True})
        return out

    def list_block_properties(self, block_id: str):
        b = self._resolve(block_id)
        if self.paused:
            return []
        return [{"name": n, "type": "real"} for n in PROPERTIES.get(b["out"], [])]

    def set_block_input(self, block_id: str, input_name: str, value, units: str = ""):
        if block_id in self.variables and self.variables[block_id].get("wraps") is None:
            v = self.variables[block_id]
            expected = "Input" if v.get("typed") else "x"
            if input_name != expected:
                raise ValueError(f"variable '{block_id}' has no parameter '{input_name}'; it has ['{expected}']")
            if v.get("typed") == "file_path":
                raise ValueError(FILE_PATH_REFUSAL.format(bid=block_id))
            if v.get("typed") in ("text", "file_path") and not isinstance(value, str):
                raise ValueError(f"'{block_id}' takes a {v['typed']}, not {type(value).__name__}")
            if v.get("typed") == "real" and isinstance(value, str):
                raise ValueError(f"'{block_id}' takes a real, not text")
            v["value"], v["units"] = value, units
            if not v.get("typed"):
                v["typed"] = "text" if isinstance(value, str) else "real"
            return
        b = self._resolve(block_id)
        names = [n for n, _ in b["defs"]]
        if input_name not in names:
            raise ValueError(f"'{block_id}' has no parameter '{input_name}'; it has {names}")
        t = dict(b["defs"])[input_name]
        if units and t not in ("real", "real_field", "point", "vector"):
            raise ValueError(f"'{input_name}' carries no unit")
        b["inputs"][input_name] = (value, units)

    def connect_block_property(self, source_block_id: str, property_name: str, target_block_id: str, input_name: str):
        self._resolve(source_block_id)
        if target_block_id in self.variables and self.variables[target_block_id].get("wraps") is None:
            v = self.variables[target_block_id]
            if input_name not in ("x", "Input"):
                raise ValueError(f"variable has no parameter '{input_name}'")
            v["wired"] = (source_block_id, property_name)
            v["typed"] = "real"
            return
        b = self._resolve(target_block_id)
        names = [n for n, _ in b["defs"]]
        if input_name not in names:
            raise ValueError(f"'{target_block_id}' has no parameter '{input_name}'; it has {names}")
        src = self._resolve(source_block_id)
        if property_name:
            if property_name not in PROPERTIES.get(src["out"], []):
                raise ValueError(f"'{source_block_id}' offers no property '{property_name}'")
        else:
            want = dict(b["defs"])[input_name]
            have = src["out"]
            compatible = {("file_path", "file_path"), ("text", "file_path"), ("real", "real_field"), ("real", "real"),
                          ("point", "point"), ("vector", "vector"), ("mesh", "mesh"), ("implicit", "implicit"),
                          ("cylinder", "implicit"), ("torus", "implicit"), ("sphere", "implicit"), ("any", want)}
            if (have, want) not in compatible and have != want:
                raise ValueError(f"cannot connect a {have} to '{input_name}' ({want}) of '{target_block_id}'")
        b["wired"][input_name] = (source_block_id, property_name)

    def append_to_list(self, source_block_id: str, target_block_id: str, target_list_id: str):
        self._resolve(source_block_id)
        b = self._resolve(target_block_id)
        t = dict(b["defs"]).get(target_list_id)
        if t is None or not t.startswith("list<"):
            raise ValueError(f"'{target_list_id}' is not a list input of '{target_block_id}'")
        b["lists"].setdefault(target_list_id, []).append(source_block_id)

    def clear_block_input(self, block_id, input_name):
        self._resolve(block_id)["inputs"].pop(input_name, None)

    def block_state(self, block_id: str):
        b = self._resolve(block_id)
        if self.paused:
            return {"blockId": block_id, "buildState": "e_DIRTY", "pauseState": "e_PAUSED"}
        if block_id in self.fail_blocks:
            return {"blockId": block_id, "buildState": "e_FAILED", "pauseState": "e_UNPAUSED", "error": "forced failure"}
        if b.get("out") == "body_mass_props" and block_id in self.blocks and block_id not in self.built:
            return {"blockId": block_id, "buildState": "e_DIRTY", "pauseState": "e_UNPAUSED"}
        return {"blockId": block_id, "buildState": "e_OK", "pauseState": "e_UNPAUSED"}

    def _build_block(self, block_id: str):
        self._resolve(block_id)
        self.built.add(block_id)

    def get_block_output_meta(self, block_id: str):
        if block_id in self.variables and self.variables[block_id].get("wired"):
            src, prop = self.variables[block_id]["wired"]
            if self.lazy_mass == "pull":
                self.built.add(src)
            if prop == "Volume" and src in self.built:
                return {"type": "real", "value": 287.4, "units": "mm^3"}
        return {"type": "real", "value": None}

    # ---- variables, inputs, output -------------------------------------------------
    def add_real_variable(self, new_name: str, value, units: str = "", section_id: str = "", targetBlockId: str = "", placeBefore: bool = False):
        if new_name in self.variables or new_name in self.blocks:
            raise ValueError(f"'{new_name}' is already used")
        self.variables[new_name] = {"value": float(value), "units": units, "wraps": None, "typed": "real", "funcId": "core.var<real>"}
        return {"name": "Scalar Variable", "id": new_name, "funcId": "core.var<real>"}

    def add_variable(self, new_name: str, block_id: str = ""):
        if new_name in self.variables or new_name in self.blocks:
            raise ValueError(f"'{new_name}' is already used")
        if block_id:
            self._resolve(block_id)
        self.variables[new_name] = {"value": None, "units": "", "wraps": block_id or None, "typed": None,
                                    "wraps_func": self.blocks.get(block_id, {}).get("funcId", ""),
                                    "funcId": "core.var<...>" if block_id else "core.var_any<any>"}
        return {"name": new_name, "id": new_name, "funcId": self.variables[new_name]["funcId"]}

    def rename_variable(self, block_id: str, new_block_id: str):
        if block_id not in self.variables:
            raise ValueError(f"'{block_id}' is not a variable")
        if new_block_id in self.variables or new_block_id in self.blocks:
            raise ValueError(f"'{new_block_id}' is already used")
        self.variables[new_block_id] = self.variables.pop(block_id)
        return {"name": new_block_id, "id": new_block_id, "funcId": "core.var"}

    def move_block_to_input(self, block_id: str):
        self._resolve(block_id)
        if block_id in self.inputs:
            raise ValueError(f"'{block_id}' is already an input")
        self.inputs.append(block_id)
        return {"name": block_id, "id": block_id, "funcId": "core.var"}

    def set_block_as_output(self, block_id: str):
        self._resolve(block_id)
        if self.output is not None:
            raise ValueError("the notebook already has an output")
        if block_id in self.inputs:
            raise ValueError("an input cannot be the output")
        self.output = block_id
        return {"name": block_id, "id": block_id, "funcId": "core.var"}

    # ---- files --------------------------------------------------------------------
    def new_notebook(self):
        fresh = self.fresh
        self.__init__(self.available_ids, self.fail_blocks, self.unmasked_limit, self.lazy_mass)
        self.fresh = fresh + 1

    def save_notebook_as(self, notebook_path: str):
        self.saved.append(notebook_path)

    def export_as_recipe(self, recipe_path: str, recipe_only: bool = False):
        self.recipes.append(recipe_path)

    @contextmanager
    def paused_updates(self, mode=None):
        self.paused = True
        try:
            yield self
        finally:
            self.paused = False
