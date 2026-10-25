"""The catalog is the single schema for every runner notebook's inputs.

catalog/<name>.yaml:

    notebook: ring_band.ntop            # relative to ntop/notebooks (or absolute)
    version: 0.1.0
    title: Flat band
    output: {name: Volume, type: scalar, units: mm^3}
    inputs:
      Outer Radius: {type: scalar, units: mm, min: 5, max: 25, doc: "..."}
      Width:        {type: scalar, units: mm, min: 1.5, max: 15, default: 4.0}
      Output Path:  {type: file_path}

Skills read it to know what a notebook takes; the runner validates against it before
nTop is launched; tests fail when a notebook's `-t` template and its catalog drift.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import config
from .ntopcl import INPUT_TYPES, make_input


@dataclass
class InputSpec:
    name: str
    type: str
    units: str | None = None
    default: Any = None
    min: float | None = None
    max: float | None = None
    choices: dict[str, int] | None = None   # enum label -> id
    doc: str = ""

    @property
    def required(self) -> bool:
        return self.default is None


@dataclass
class Catalog:
    name: str
    notebook: Path
    version: str
    title: str
    output: dict
    inputs: dict[str, InputSpec] = field(default_factory=dict)
    path: Path | None = None

    def build_inputs(self, values: dict[str, Any]) -> list[dict]:
        """Validate `values` against the schema and return Automate input entries."""
        unknown = set(values) - set(self.inputs)
        if unknown:
            raise ValueError(f"{self.name}: unknown inputs {sorted(unknown)}; "
                             f"known: {sorted(self.inputs)}")
        out = []
        for name, spec in self.inputs.items():
            if name in values:
                v = values[name]
            elif spec.default is not None:
                v = spec.default
            else:
                raise ValueError(f"{self.name}: missing required input {name!r}")
            if spec.type == "enum" and isinstance(v, str):
                if not spec.choices or v not in spec.choices:
                    raise ValueError(f"{self.name}: {name}={v!r} not in {sorted(spec.choices or {})}")
                v = spec.choices[v]
            if spec.type in ("scalar", "integer"):
                vals = v if isinstance(v, (list, tuple)) else [v]
                for x in vals:
                    if spec.min is not None and x < spec.min:
                        raise ValueError(f"{self.name}: {name}={x} below min {spec.min}")
                    if spec.max is not None and x > spec.max:
                        raise ValueError(f"{self.name}: {name}={x} above max {spec.max}")
            out.append(make_input(name, spec.type, v, spec.units))
        return out

    def describe(self) -> str:
        lines = [f"{self.name} v{self.version}: {self.title}", f"  notebook: {self.notebook}",
                 f"  output: {self.output.get('name')} ({self.output.get('type')}, {self.output.get('units', '')})"]
        for s in self.inputs.values():
            rng = ""
            if s.min is not None or s.max is not None:
                rng = f" [{s.min if s.min is not None else ''}..{s.max if s.max is not None else ''}]"
            dflt = f" = {s.default}" if s.default is not None else " (required)"
            unit = f" {s.units}" if s.units else ""
            lines.append(f"  - {s.name}: {s.type}{unit}{rng}{dflt}  {s.doc}".rstrip())
        return "\n".join(lines)


def load(name_or_path: str | Path) -> Catalog:
    p = Path(name_or_path)
    if p.suffix not in (".yaml", ".yml"):
        p = config.catalog_dir() / f"{name_or_path}.yaml"
    if not p.exists():
        raise FileNotFoundError(f"catalog entry not found: {p}")
    doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    inputs: dict[str, InputSpec] = {}
    for name, raw in (doc.get("inputs") or {}).items():
        raw = dict(raw or {})
        t = raw.get("type")
        if t not in INPUT_TYPES:
            raise ValueError(f"{p.name}: input {name!r} has unknown type {t!r}")
        inputs[name] = InputSpec(name=name, type=t, units=raw.get("units"), default=raw.get("default"),
                                 min=raw.get("min"), max=raw.get("max"), choices=raw.get("choices"),
                                 doc=raw.get("doc", ""))
    nb = Path(doc.get("notebook", f"{p.stem}.ntop"))
    if not nb.is_absolute():
        nb = config.notebooks_dir() / nb
    return Catalog(name=p.stem, notebook=nb, version=str(doc.get("version", "0")),
                   title=doc.get("title", p.stem), output=doc.get("output") or {}, inputs=inputs, path=p)


def names() -> list[str]:
    d = config.catalog_dir()
    return sorted(p.stem for p in d.glob("*.yaml")) if d.exists() else []


def compare_with_template(cat: Catalog, input_template: Path) -> list[str]:
    """Differences between a catalog entry and nTop's own `-t` input template."""
    tpl = json.loads(Path(input_template).read_text(encoding="utf-8"))
    tpl_inputs = {e["name"]: e for e in tpl.get("inputs", [])}
    problems = []
    for name in tpl_inputs:
        if name not in cat.inputs:
            problems.append(f"notebook declares input {name!r} missing from catalog")
        elif tpl_inputs[name].get("type") not in (None, cat.inputs[name].type):
            problems.append(f"input {name!r}: notebook type {tpl_inputs[name].get('type')!r} "
                            f"!= catalog type {cat.inputs[name].type!r}")
    for name in cat.inputs:
        if name not in tpl_inputs:
            problems.append(f"catalog input {name!r} is not declared in the notebook")
    return problems
