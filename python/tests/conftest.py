"""Shared fixtures: a fake `ntopcl` that behaves like the real one on 2026-10-25.

The fake reproduces the real log format (including the per-block timings and the
`JSON file has no inputs` rejection), writes the output JSON, and, for the band
notebook, writes a real STL so the whole band -> gate path can be tested offline.
"""
from __future__ import annotations

import os
import stat
import sys
import textwrap
from pathlib import Path

import pytest

REAL_LOG_SUCCESS = textwrap.dedent("""\
    15:57:33 [I]: Login successful
    15:57:33 [I]: Notebook started
    15:57:33 [I]: Plane_2 complete 0ms
    15:57:33 [I]: Box_0 complete 0ms
    15:57:33 [I]: Cone_0 complete 0ms
    15:57:33 [I]: Sphere_0 complete 0ms
    15:57:33 [I]: Implicit Body List_0 complete 0ms
    15:57:33 [I]: Spherecube complete 0ms
    15:57:33 [I]: Cube Minus Sphere complete 0ms
    15:57:33 [I]: Spherecube Shell complete 0ms
    15:57:33 [I]: Implicit Body_5 complete 22ms
    15:57:33 [I]: Spherecube Mirror complete 0ms
    15:57:33 [I]: nTop successfully built.
    15:57:33 [I]: Logout successful
    """)

REAL_LOG_NO_INPUTS = textwrap.dedent("""\
    15:53:39 [I]: Login successful
    15:53:39 [I]: Notebook started
    15:53:39 [E]: JSON file has no inputs
    15:53:39 [I]: nTop exited with errors.
    15:53:39 [I]: Logout successful
    """)

FAKE_NTOPCL = r'''#!/usr/bin/env python3
"""Fake ntopcl for tests. Mimics flags -v -j -o -t --version and the 6.3.3 log format."""
import json, math, sys, time
from pathlib import Path

args = sys.argv[1:]
if args == ["--version"]:
    print("6.3.3"); sys.exit(0)
if args and args[0] == "-t":
    nb = Path(args[1])
    inputs = []
    if "band" in nb.name:
        # nTop 6.3.3 spells these `real` and `text` in its own template (seen 2026-10-25)
        inputs = [{"name": "Outer Radius", "type": "real", "value": 0, "units": "mm"},
                  {"name": "Bore Radius", "type": "real", "value": 0, "units": "mm"},
                  {"name": "Width", "type": "real", "value": 0, "units": "mm"},
                  {"name": "Mesh Tolerance", "type": "real", "value": 0, "units": "mm"},
                  {"name": "Output Path", "type": "text", "value": ""}]
    Path("input_template.json").write_text(json.dumps({"title": nb.stem, "description": "", "inputs": inputs}, indent=4))
    Path("output_template.json").write_text(json.dumps([{"name": "Volume", "type": "scalar", "components": [], "value": 0}], indent=4))
    sys.exit(0)

in_json = out_json = None
i = 0
while i < len(args):
    if args[i] == "-j": in_json = Path(args[i + 1]); i += 2
    elif args[i] == "-o": out_json = Path(args[i + 1]); i += 2
    elif args[i] == "-v": i += 2
    else: i += 1
nb = Path(args[-1])
stamp = time.strftime("%H:%M:%S")
def log(level, msg): print(f"{stamp} [{level}]: {msg}")
log("I", "Login successful")
log("I", "Notebook started")
values = {}
if in_json is not None:
    doc = json.loads(in_json.read_text())
    if not doc.get("inputs"):
        log("E", "JSON file has no inputs"); log("I", "nTop exited with errors."); log("I", "Logout successful"); sys.exit(0)
    values = {e["name"]: e.get("value", e.get("values")) for e in doc["inputs"]}
if "fail" in nb.name:
    log("E", "Boolean Subtract_0: input Bodies is not connected"); log("I", "nTop exited with errors."); log("I", "Logout successful"); sys.exit(0)
outputs = []
if "band" in nb.name:
    import trimesh
    R, r, W = float(values["Outer Radius"]), float(values["Bore Radius"]), float(values["Width"])
    mesh = trimesh.creation.annulus(r_min=r, r_max=R, height=W, sections=720)
    mesh.export(values["Output Path"])
    vol = math.pi * (R * R - r * r) * W
    for name in ("Outer Cylinder", "Bore", "Band", "Mesh from Implicit Body", "Export Mesh", "Mass Properties"):
        log("I", f"{name} complete 1ms")
    outputs = [{"name": "Volume", "type": "scalar", "components": [], "value": vol, "units": "mm^3"}]
else:
    for name in ("Sphere_0", "Implicit Body_5"):
        log("I", f"{name} complete 0ms")
    outputs = [{"name": "Spherecube Shell", "type": "implicit", "components": [], "value": {"base64": "AAAA"}}]
if out_json is not None:
    out_json.write_text(json.dumps(outputs, indent=4))
log("I", "nTop successfully built.")
log("I", "Logout successful")
'''


@pytest.fixture
def fake_ntopcl(tmp_path, monkeypatch) -> Path:
    exe = tmp_path / "ntopcl.py"
    exe.write_text(FAKE_NTOPCL, encoding="utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    # ntopcl.run() calls [exe, ...]; point it at a tiny launcher that runs the fake under this python
    if os.name == "nt":  # pragma: no cover - the Linux container runs the tests
        launcher = tmp_path / "ntopcl.cmd"
        launcher.write_text(f'@"{sys.executable}" "{exe}" %*\n')
    else:
        launcher = tmp_path / "ntopcl"
        launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{exe}" "$@"\n')
        launcher.chmod(0o755)
    monkeypatch.setenv("NTOPCL", str(launcher))
    return launcher


@pytest.fixture
def band_notebook(tmp_path) -> Path:
    nb = tmp_path / "ring_band.ntop"
    nb.write_bytes(b"fake notebook")
    return nb
