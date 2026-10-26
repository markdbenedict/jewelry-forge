"""An in-memory stand-in for nTop's `notebook` object (Notebook API v0.14 surface we use).

It mimics the documented behaviour closely enough to exercise build scripts offline:
exact identifiers, returned ids with numeric suffixes, list-type inputs, variables whose
id is their name, build states, properties that exist only once a block has "built".
"""
from __future__ import annotations

from contextlib import contextmanager

# identifier -> (display name, [(input name, type), ...], output type)
SIGNATURES = {
    "sphere<point,real>": ("Sphere", [("Center Point", "point"), ("Radius", "real")], "sphere"),
    "point<real,real,real>": ("Point", [("X", "real"), ("Y", "real"), ("Z", "real")], "point"),
    "cylinder<point,point,real>": ("Cylinder", [("Point 1", "point"), ("Point 2", "point"), ("Radius", "real")], "cylinder"),
    "cylinder from line segment<line,real>": ("Cylinder from Line Segment", [("Line", "line"), ("Radius", "real")], "cylinder"),
    "torus<point,vector,real,real>": ("Torus", [("Center", "point"), ("Axis", "vector"), ("Radius", "real"), ("Torus radius", "real")], "torus"),
    "boolean subtract<implicit body,list<implicit body>,blend,real>": (
        "Boolean Subtract", [("Blend Type", "blend"), ("Blend Radius", "real"), ("Primary Body", "implicit body"),
                             ("Subtraction Bodies", "list<implicit body>")], "implicit body"),
    "boolean intersect<list<implicit body>,blend,real>": (
        "Boolean Intersect", [("Blend Type", "blend"), ("Blend Radius", "real"), ("Bodies", "list<implicit body>")], "implicit body"),
    "boolean union<list<implicit body>,blend,real>": (
        "Boolean Union", [("Blend Type", "blend"), ("Blend Radius", "real"), ("Bodies", "list<implicit body>")], "implicit body"),
    "offset body<implicit body,real>": ("Offset Body", [("Body", "implicit body"), ("Distance", "real")], "implicit body"),
    "mass properties<implicit body,real,real>": ("Mass Properties", [("Body", "implicit body"), ("Density", "real"), ("Relative Error", "real")], "mass properties"),
    "mesh from implicit body<implicit body,real,real,bool,bool>": (
        "Mesh from Implicit Body", [("Body", "implicit body"), ("Tolerance", "real"), ("Min. feature size", "real"),
                                    ("Sharpen", "bool"), ("Simplify", "bool")], "mesh"),
    "export mesh<mesh,text,unit,format>": ("Export Mesh", [("Mesh", "mesh"), ("File", "text"), ("Units", "unit"), ("Format", "format")], "file"),
    "text<text>": ("Text", [("Text", "text")], "text"),
    "core.var": ("Variable", [("Input", "any")], "any"),
}
PROPERTIES = {"mass properties": ["Mass", "Volume", "Center of Mass", "Surface Area"], "implicit body": ["Bounding Box"]}


class FakeNotebook:
    def __init__(self, available=None, fail_blocks=()):
        self.available_ids = list(available or SIGNATURES)
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
        return [i for i in self.available_ids if mask in i]

    def list_sections(self):
        return [{"name": "Section 1", "id": "section_0"}]

    def list_blocks(self, section_id: str = ""):
        return [{"name": b["name"], "id": i, "funcId": b["funcId"]} for i, b in self.blocks.items()]

    def list_variables(self):
        return [{"name": i, "id": i, "funcId": "core.var", "blockFuncId": v.get("wraps_func", "")} for i, v in self.variables.items()]

    # ---- blocks -------------------------------------------------------------------
    def _new_id(self, base: str) -> str:
        n = self.counter.get(base, 0)
        self.counter[base] = n + 1
        return f"{base}_{n}"

    def add_block(self, identifier: str, section_id: str = "", targetBlockId: str = "", placeBefore: bool = False):
        if identifier not in self.available_ids:
            raise ValueError(f"'{identifier}' is not a block available to this notebook")
        name, inputs, out = SIGNATURES[identifier]
        if identifier == "core.var":
            bid = self._new_id("Variable")
            self.variables[bid] = {"value": None, "units": "", "wraps": None, "typed": None}
            return {"name": name, "id": bid, "funcId": identifier}
        bid = self._new_id(out.title().replace(" ", " ") if out != "implicit body" else "Implicit Body")
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
            return {"funcId": "core.var", "name": block_id, "inputs": {}, "lists": {}, "wired": {}, "out": "any",
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
            if input_name != "Input":
                raise ValueError(f"variable '{block_id}' has no parameter '{input_name}'")
            v["value"], v["units"] = value, units
            v["typed"] = "text" if isinstance(value, str) else "real"
            return
        b = self._resolve(block_id)
        names = [n for n, _ in b["defs"]]
        if input_name not in names:
            raise ValueError(f"'{block_id}' has no parameter '{input_name}'; it has {names}")
        t = dict(b["defs"])[input_name]
        if units and t not in ("real", "point", "vector"):
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
        if property_name:
            src = self._resolve(source_block_id)
            if property_name not in PROPERTIES.get(src["out"], []):
                raise ValueError(f"'{source_block_id}' offers no property '{property_name}'")
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
        self._resolve(block_id)
        if self.paused:
            return {"blockId": block_id, "buildState": "e_DIRTY", "pauseState": "e_PAUSED"}
        if block_id in self.fail_blocks:
            return {"blockId": block_id, "buildState": "e_FAILED", "pauseState": "e_UNPAUSED", "error": "forced failure"}
        return {"blockId": block_id, "buildState": "e_OK", "pauseState": "e_UNPAUSED"}

    def get_block_output_meta(self, block_id: str):
        if block_id in self.variables and self.variables[block_id].get("wired"):
            src, prop = self.variables[block_id]["wired"]
            if prop == "Volume":
                return {"type": "real", "value": 287.4, "units": "mm^3"}
        return {"type": "real", "value": None}

    # ---- variables, inputs, output -------------------------------------------------
    def add_real_variable(self, new_name: str, value, units: str = "", section_id: str = "", targetBlockId: str = "", placeBefore: bool = False):
        if new_name in self.variables or new_name in self.blocks:
            raise ValueError(f"'{new_name}' is already used")
        self.variables[new_name] = {"value": float(value), "units": units, "wraps": None, "typed": "real"}
        return {"name": new_name, "id": new_name, "funcId": "core.var"}

    def add_variable(self, new_name: str, block_id: str = ""):
        if new_name in self.variables or new_name in self.blocks:
            raise ValueError(f"'{new_name}' is already used")
        if block_id:
            self._resolve(block_id)
        self.variables[new_name] = {"value": None, "units": "", "wraps": block_id or None, "typed": None,
                                    "wraps_func": self.blocks.get(block_id, {}).get("funcId", "")}
        return {"name": new_name, "id": new_name, "funcId": "core.var" if block_id else "core.var_any"}

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
        self.__init__(self.available_ids, self.fail_blocks)
        self.fresh += 1

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
