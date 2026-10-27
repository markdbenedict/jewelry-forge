"""Shared fixtures: a fake `ntopcl` (tests/fake_ntopcl.py) that behaves like the real one on
2026-10-25 and builds the geometry the notebook would build, so the gate, the design-volume
cross-check and the engraving check are exercised against the real thing's shape offline.
"""
from __future__ import annotations

import os
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

FAKE_NTOPCL = Path(__file__).resolve().parent / "fake_ntopcl.py"      # the stand-in executable (see its docstring)


@pytest.fixture
def fake_ntopcl(tmp_path, monkeypatch) -> Path:
    """`ntopcl` for the tests: a launcher that runs tests/fake_ntopcl.py under this Python.
    Set FAKE_NTOPCL_SHAPE / _EXPORT / _VOLUME in a test to make it misbehave (see its docstring)."""
    exe = FAKE_NTOPCL
    # ntopcl.run() calls [exe, ...]; point it at a tiny launcher that runs the fake under this python
    if os.name == "nt":  # pragma: no cover - the Linux container runs the tests
        launcher = tmp_path / "ntopcl.cmd"
        launcher.write_text(f'@"{sys.executable}" "{exe}" %*\n')
    else:
        launcher = tmp_path / "ntopcl"
        launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{exe}" "$@"\n')
        launcher.chmod(0o755)
    monkeypatch.setenv("NTOPCL", str(launcher))
    for var in ("FAKE_NTOPCL_SHAPE", "FAKE_NTOPCL_EXPORT", "FAKE_NTOPCL_VOLUME", "FAKE_NTOPCL_SLEEP"):
        monkeypatch.delenv(var, raising=False)
    return launcher


@pytest.fixture
def band_notebook(tmp_path) -> Path:
    nb = tmp_path / "ring_band.ntop"
    nb.write_bytes(b"fake notebook")
    return nb


@pytest.fixture
def profile_notebook(tmp_path) -> Path:
    nb = tmp_path / "ring_band_profile.ntop"
    nb.write_bytes(b"fake notebook")
    return nb


@pytest.fixture
def features_notebook(tmp_path) -> Path:
    nb = tmp_path / "ring_features.ntop"
    nb.write_bytes(b"fake notebook")
    return nb
