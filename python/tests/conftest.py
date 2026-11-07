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
def out_dir(tmp_path) -> Path:
    """Where a test's runs go. On Windows a solitaire stem (up to 90 characters, twice in every
    file's path) under pytest's deep temp dir runs past MAX_PATH (2026-11-03: two end-to-end tests
    failed with FileNotFoundError on the laptop and passed in CI), so there it is a short directory
    straight under %TEMP%, removed afterwards."""
    if os.name != "nt":
        yield tmp_path / "out"
        return
    import shutil, tempfile  # pragma: no cover - the Linux container runs the tests
    d = Path(tempfile.mkdtemp(prefix="jf-"))
    yield d
    shutil.rmtree(d, ignore_errors=True)


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


@pytest.fixture(scope="session")
def fake_open_bar(tmp_path_factory) -> Path:
    """The open_bar library block as the fake notebook saves it, built once per session: every
    runner with a shank embeds it (ntop/recipes/open_bar.py)."""
    from .fake_notebook import FakeNotebook
    from .test_notebook_api import load_recipe
    d = tmp_path_factory.mktemp("open_bar")
    mod = load_recipe("open_bar")
    params = mod.prepare({}, d)
    params.update({"save_to": str(d / "open_bar_harness.ntop"), "recipe_to": str(d / "ob.json"),
                   "test_output": str(d / "ob.stl"), "block_to": str(d / "open_bar.ntop"),
                   "block_recipe_to": str(d / "ob.block.json")})
    mod.build(FakeNotebook(), params)
    return d / "open_bar.ntop"


@pytest.fixture(autouse=True)
def _open_bar_block_default(monkeypatch, fake_open_bar):
    """Runners built on the fake find the fake open_bar block where they would find ntop/blocks/open_bar.ntop."""
    from ntopjewel import nb_jewel
    monkeypatch.setitem(nb_jewel.BLOCK_DEFAULTS, "open_bar_block", (str(fake_open_bar),))


@pytest.fixture(autouse=True)
def _api_facts(tmp_path_factory, monkeypatch):
    """What ntop/recipes/transform_probe.py measures in nTop, for builds on the fake (the fake
    cannot measure it): Combine Transforms applies its list in order, Mirror Body works; and what
    the first lattice run measured, the gyroid field's gradient (1.6)."""
    import json
    f = tmp_path_factory.getbasetemp() / "api_facts.json"
    if not f.exists():
        f.write_text(json.dumps({"combine_transforms_order": "list", "mirror_body": "ok", "gyroid_field_gradient": 1.6}))
    monkeypatch.setenv("NTOPJEWEL_API_FACTS", str(f))
