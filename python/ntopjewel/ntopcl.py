"""Run nTop notebooks headlessly through nTopCL and read what came back.

Rules this module enforces (verified on nTop 6.3.3, 2026-10-25):

* `ntopcl -v 2 -j in.json -o out.json notebook.ntop`; `-t notebook.ntop` writes templates.
* A notebook with no inputs is run WITHOUT `-j` (nTopCL rejects an empty `inputs` list).
* Success means all of: exit code 0, no `[E]` log line, and `nTop successfully built.`
  present. nTopCL can exit 0 after a block fails.
* Input JSON entries: {"name", "type", "value"} plus "units" for scalar/point/vector.
  A scalar may carry {"values": [...]} to sweep one parameter in a single run.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from . import config

INPUT_TYPES = {"bool", "scalar", "integer", "text", "file_path", "point", "vector", "enum"}
UNIT_TYPES = {"scalar", "point", "vector"}

LOG_LINE = re.compile(r"^\s*(?P<time>\d{2}:\d{2}:\d{2})\s+\[(?P<level>[A-Z])\]:\s*(?P<msg>.*)$")
BLOCK_DONE = re.compile(r"^(?P<block>.+?) complete (?P<ms>\d+)ms$")
SUCCESS_TEXT = "nTop successfully built"


class NtopclError(RuntimeError):
    """Raised when a run fails; carries the parsed result."""

    def __init__(self, message: str, result: "RunResult | None" = None):
        super().__init__(message)
        self.result = result


# --------------------------------------------------------------------------- inputs
def make_input(name: str, type_: str, value: Any, units: str | None = None) -> dict:
    """One entry of the Automate input JSON, validated."""
    if type_ not in INPUT_TYPES:
        raise ValueError(f"{name}: unknown nTop input type {type_!r}; one of {sorted(INPUT_TYPES)}")
    entry: dict[str, Any] = {"name": name, "type": type_}
    if type_ == "bool":
        entry["value"] = bool(value)
    elif type_ == "integer":
        if isinstance(value, float) and not value.is_integer():
            raise ValueError(f"{name}: integer input got {value}")
        entry["value"] = int(value)
    elif type_ == "enum":
        entry["value"] = int(value)
    elif type_ in ("text", "file_path"):
        entry["value"] = str(value)
    elif type_ == "scalar":
        if isinstance(value, (list, tuple)):
            entry["values"] = [float(v) for v in value]
        else:
            entry["value"] = float(value)
    elif type_ in ("point", "vector"):
        if len(value) != 3:
            raise ValueError(f"{name}: {type_} needs 3 components, got {value}")
        entry["value"] = [float(v) for v in value]
    if type_ in UNIT_TYPES:
        if units is None:
            raise ValueError(f"{name}: {type_} inputs need units (e.g. 'mm')")
        entry["units"] = units
    elif units is not None:
        raise ValueError(f"{name}: {type_} inputs do not take units")
    return entry


def apply_template_types(inputs: Iterable[dict], input_template: Path) -> list[dict]:
    """Rename each input's `type` to what nTop's own `-t` template declares for that name.

    nTop's template is the authority for type spelling (6.3.3 writes `real`, the docs say
    `scalar`). Inputs the template does not know are left as they are.
    """
    tpl = json.loads(Path(input_template).read_text(encoding="utf-8"))
    tpl_types = {e["name"]: e.get("type") for e in tpl.get("inputs", []) if "name" in e}
    out = []
    for entry in inputs:
        e = dict(entry)
        t = tpl_types.get(e["name"])
        if t:
            e["type"] = t
        out.append(e)
    return out


def input_json(inputs: Iterable[dict], title: str = "", description: str = "") -> dict:
    inputs = list(inputs)
    names = [i["name"] for i in inputs]
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        raise ValueError(f"duplicate input names: {sorted(dupes)}")
    doc: dict[str, Any] = {"inputs": inputs}
    if title:
        doc["title"] = title
    if description:
        doc["description"] = description
    return doc


def write_input_json(path: Path, inputs: Iterable[dict], **meta) -> Path:
    doc = input_json(inputs, **meta)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- log parsing
@dataclass
class BlockTiming:
    block: str
    ms: int


@dataclass
class ParsedLog:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    infos: list[str] = field(default_factory=list)
    timings: list[BlockTiming] = field(default_factory=list)
    built: bool = False
    login: bool = False

    @property
    def total_block_ms(self) -> int:
        return sum(t.ms for t in self.timings)

    def slowest(self, n: int = 5) -> list[BlockTiming]:
        return sorted(self.timings, key=lambda t: -t.ms)[:n]


def parse_log(text: str) -> ParsedLog:
    out = ParsedLog()
    for raw in text.splitlines():
        m = LOG_LINE.match(raw)
        if not m:
            # lines without the timestamp prefix: still catch error markers
            if "[E]" in raw:
                out.errors.append(raw.strip())
            continue
        level, msg = m.group("level"), m.group("msg").strip()
        if level == "E":
            out.errors.append(msg)
        elif level == "W":
            out.warnings.append(msg)
        else:
            out.infos.append(msg)
            if SUCCESS_TEXT in msg:
                out.built = True
            elif msg.startswith("Login successful"):
                out.login = True
            else:
                b = BLOCK_DONE.match(msg)
                if b:
                    out.timings.append(BlockTiming(b.group("block"), int(b.group("ms"))))
    return out


# --------------------------------------------------------------------------- output parsing
def parse_output(path: Path) -> dict[str, dict]:
    """Output JSON -> {name: entry}. nTop writes a list of {name, type, value, components}.

    The scalar-output shape is still to be confirmed on the first real run; `value` may be
    a number or a dict. `scalar_value()` copes with both.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = [data]
    return {e.get("name", f"output_{i}"): e for i, e in enumerate(data)}


def scalar_value(entry: dict, to_mm: bool = True) -> float | None:
    """Numeric value of a scalar ("real") output, converted from nTop's SI to mm / g.

    nTop 6.3.3 writes (seen 2026-10-25):
        {"name": "Volume", "type": "real", "components": [],
         "value": {"isFinite": true, "units": {"length": 3}, "val": 2.9098e-07}}
    i.e. the value in SI base units with the dimension exponents alongside. With `to_mm`
    (default) lengths are scaled m -> mm and masses kg -> g per exponent, so a volume
    comes back in mm³ and a mass in g.
    """
    v = entry.get("value")
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict):
        if "val" in v:
            x = float(v["val"])
            units = v.get("units") or {}
            if to_mm and isinstance(units, dict):
                x *= 1000.0 ** float(units.get("length", 0) or 0)
                x *= 1000.0 ** float(units.get("mass", 0) or 0)
            return x
        for key in ("value", "values", "scalar", "magnitude"):
            if key in v:
                x = v[key]
                if isinstance(x, list):
                    return float(x[0]) if x else None
                return float(x)
    if isinstance(v, list) and v and isinstance(v[0], (int, float)):
        return float(v[0])
    return None


def scalar_units(entry: dict) -> str:
    """Human label for a scalar output's units after scalar_value() conversion (mm-based)."""
    v = entry.get("value")
    units = v.get("units") if isinstance(v, dict) else None
    if not isinstance(units, dict) or not units:
        return ""
    parts = []
    base = {"length": "mm", "mass": "g", "time": "s"}
    for dim, exp in units.items():
        name = base.get(dim, dim)
        parts.append(name if exp == 1 else f"{name}^{exp}")
    return "*".join(parts)


# --------------------------------------------------------------------------- running
@dataclass
class RunResult:
    notebook: Path
    input_json: Path | None
    output_json: Path
    log_path: Path
    returncode: int
    seconds: float
    log: ParsedLog
    outputs: dict[str, dict] = field(default_factory=dict)
    command: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.log.errors and self.log.built

    def summary(self) -> str:
        state = "OK" if self.ok else "FAILED"
        lines = [f"ntopcl {state} in {self.seconds:.1f}s  ({self.notebook.name})"]
        if self.log.errors:
            lines += [f"  [E] {e}" for e in self.log.errors]
        if self.log.warnings:
            lines += [f"  [W] {w}" for w in self.log.warnings[:10]]
        if self.log.timings:
            top = ", ".join(f"{t.block} {t.ms}ms" for t in self.log.slowest(3))
            lines.append(f"  blocks: {len(self.log.timings)}, {self.log.total_block_ms} ms total; slowest: {top}")
        for name, entry in self.outputs.items():
            sv = scalar_value(entry)
            shown = f"{sv:.6g} {scalar_units(entry)}".rstrip() if sv is not None else entry.get("type", "?")
            lines.append(f"  output {name}: {shown}")
        return "\n".join(lines)


def _exe() -> Path:
    exe = config.ntopcl_path()
    if exe is None:
        raise NtopclError("ntopcl not found: install nTop, or set NTOPCL to the full path of ntopcl.exe")
    return exe


def template_dir(notebook: Path) -> Path:
    return config.out_dir() / "templates" / Path(notebook).stem


def ensure_template(notebook: Path, exe: Path | None = None, refresh: bool = False) -> Path:
    """nTop's own input template for this notebook (generated once, cached under out/templates)."""
    d = template_dir(notebook)
    i = d / "input_template.json"
    if refresh or not i.exists() or i.stat().st_mtime < Path(notebook).stat().st_mtime:
        i, _ = templates(notebook, d, exe)
    return i


def run(notebook: Path, inputs: Iterable[dict] | None, out_dir: Path, *, tag: str = "run",
        verbosity: int = 2, timeout_s: float = 3600, extra_args: Iterable[str] = (),
        exe: Path | None = None, use_template: bool = True) -> RunResult:
    """Run one notebook. `inputs` None or empty -> no `-j` (nTopCL rejects empty inputs).

    With `use_template` (default) the input types are spelled the way nTop's own `-t`
    template spells them for this notebook (regenerated when the notebook is newer).
    Writes <out_dir>/<tag>.input.json, <tag>.output.json and <tag>.ntopcl.log.
    Raises NtopclError on failure (with the RunResult attached).
    """
    notebook = Path(notebook).resolve()
    if not notebook.exists():
        raise NtopclError(f"notebook not found: {notebook}")
    out_dir = Path(out_dir).resolve()        # ntopcl runs with cwd=out_dir, so every path it gets must be absolute
    out_dir.mkdir(parents=True, exist_ok=True)
    exe = exe or _exe()

    inputs = list(inputs or [])
    if inputs and use_template:
        inputs = apply_template_types(inputs, ensure_template(notebook, exe))
    in_path = None
    if inputs:
        in_path = write_input_json(out_dir / f"{tag}.input.json", inputs, title=tag)
    out_path = out_dir / f"{tag}.output.json"
    log_path = out_dir / f"{tag}.ntopcl.log"
    for p in (out_path, log_path):
        if p.exists():
            p.unlink()

    cmd = [str(exe), "-v", str(verbosity)]
    if in_path is not None:
        cmd += ["-j", str(in_path)]
    cmd += ["-o", str(out_path), *extra_args, str(notebook)]

    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s,
                          cwd=str(out_dir), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    seconds = time.time() - t0
    text = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    log_path.write_text(text, encoding="utf-8")
    parsed = parse_log(text)
    outputs = parse_output(out_path) if out_path.exists() else {}
    result = RunResult(notebook, in_path, out_path, log_path, proc.returncode, seconds, parsed, outputs, cmd)
    if not result.ok:
        why = result.log.errors[0] if result.log.errors else (
            f"exit code {proc.returncode}" if proc.returncode else "no 'nTop successfully built' line")
        raise NtopclError(f"ntopcl failed: {why} (log: {log_path})", result)
    return result


def templates(notebook: Path, out_dir: Path, exe: Path | None = None) -> tuple[Path, Path]:
    """`ntopcl -t notebook` -> (input_template.json, output_template.json) in out_dir."""
    notebook = Path(notebook).resolve()
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    exe = exe or _exe()
    proc = subprocess.run([str(exe), "-t", str(notebook)], capture_output=True, text=True,
                          cwd=str(out_dir), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    i, o = out_dir / "input_template.json", out_dir / "output_template.json"
    text = f"{proc.stdout}\n{proc.stderr}"
    if not i.exists():
        raise NtopclError(f"template generation failed: {text}")
    if "Output of function not built" in text and not o.exists():
        # The Output exists but was never built in the GUI session (an API-authored notebook):
        # nTopCL cannot type it for the template, yet still builds and reports it at run time.
        o.write_text(json.dumps({"note": "nTopCL: Output of function not built; the output type is known after "
                                         "the first run (out.json)", "outputs": []}, indent=2), encoding="utf-8")
    elif proc.returncode != 0 or not o.exists():
        raise NtopclError(f"template generation failed: {text}")
    return i, o


def version(exe: Path | None = None) -> str | None:
    exe = exe or config.ntopcl_path()
    if exe is None:
        return None
    try:
        proc = subprocess.run([str(exe), "--version"], capture_output=True, text=True, timeout=60,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError:
        return None
    return (proc.stdout or proc.stderr).strip().splitlines()[0] if (proc.stdout or proc.stderr) else ""
