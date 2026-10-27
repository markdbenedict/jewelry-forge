"""The Blender side, tested without Blender: jewelry_kit reads the shared engineering tables (and its
embedded fallback cannot drift from data/jewelry_tables.json), leaf_design is pure numpy,
monstera_ring re-exports it, and gallery.py runs on the system Python.

bpy, bmesh and mathutils are stand-in modules with just the names the files touch at import time.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
BLENDER = REPO / "blender"
TABLES_JSON = REPO / "data" / "jewelry_tables.json"
TABLES = json.loads(TABLES_JSON.read_text(encoding="utf-8"))


@pytest.fixture
def clean_imports():
    """Leave sys.modules and sys.path as they were: the scripts put their folders on sys.path."""
    modules, path = set(sys.modules), list(sys.path)
    yield
    for name in [n for n in sys.modules if n not in modules]:
        del sys.modules[name]
    sys.path[:] = path


@pytest.fixture
def blender_stubs(monkeypatch, clean_imports):
    bpy = types.ModuleType("bpy")
    bpy.data = SimpleNamespace(texts={})            # load_tables looks for a text block here
    bmesh = types.ModuleType("bmesh")
    mathutils = types.ModuleType("mathutils")
    mathutils.Vector = type("Vector", (), {})
    bvhtree = types.ModuleType("mathutils.bvhtree")
    bvhtree.BVHTree = type("BVHTree", (), {})
    mathutils.bvhtree = bvhtree
    for name, mod in (("bpy", bpy), ("bmesh", bmesh), ("mathutils", mathutils), ("mathutils.bvhtree", bvhtree)):
        monkeypatch.setitem(sys.modules, name, mod)
    return bpy


def _import(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------- jewelry_kit
def test_jewelry_kit_reads_the_shared_tables(blender_stubs):
    jk = _import("jewelry_kit", BLENDER / "jewelry_kit.py")
    assert Path(jk.TABLES_SOURCE).resolve() == TABLES_JSON.resolve()     # case (b): the checkout
    assert jk.WALL_MIN_MM == 0.5 == TABLES["floors"]["wall_marginal"]["mm"]
    assert jk.WALL_GOOD_MM == 0.75 == TABLES["floors"]["wall_good"]["mm"]
    assert jk.SPRUE_ALLOWANCE == TABLES["weight"]["sprue_allowance_fraction"]["value"]
    assert jk.METALS["Brass"] == 8.5 == TABLES["metals"]["brass"]["density_g_cm3"]
    # the report's display names, in the order check_model prints them
    assert list(jk.METALS) == ["Sterling silver", "14K yellow gold", "14K white gold",
                               "18K yellow gold", "Bronze", "Brass"]
    for key, label in jk._METAL_LABELS.items():
        assert jk.METALS[label] == TABLES["metals"][key]["density_g_cm3"]
    assert jk.check_model.__defaults__[1:] == (jk.WALL_MIN_MM, jk.WALL_GOOD_MM)


def test_jewelry_kit_fallback_matches_the_json(blender_stubs):
    jk = _import("jewelry_kit", BLENDER / "jewelry_kit.py")
    assert set(jk._FALLBACK_TABLES) == {"metals", "floors", "weight"}
    for section in ("metals", "floors", "weight"):
        assert jk._FALLBACK_TABLES[section] == TABLES[section], f"{section}: update _FALLBACK_TABLES"


def test_load_tables_order(blender_stubs, monkeypatch, tmp_path):
    jk = _import("jewelry_kit", BLENDER / "jewelry_kit.py")
    # (a) JEWELRY_FORGE_ROOT wins over the checkout
    other = tmp_path / "root" / "data"
    other.mkdir(parents=True)
    doc = json.loads(TABLES_JSON.read_text(encoding="utf-8"))
    doc["metals"]["brass"]["density_g_cm3"] = 8.6
    (other / "jewelry_tables.json").write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setenv("JEWELRY_FORGE_ROOT", str(tmp_path / "root"))
    tables, source = jk.load_tables()
    assert tables["metals"]["brass"]["density_g_cm3"] == 8.6 and Path(source) == other / "jewelry_tables.json"
    # (c) no repo anywhere: a text block named jewelry_tables.json in the .blend
    monkeypatch.delenv("JEWELRY_FORGE_ROOT")
    monkeypatch.setattr(jk, "__file__", str(tmp_path / "elsewhere" / "jewelry_kit.py"))
    doc["metals"]["brass"]["density_g_cm3"] = 8.7
    blender_stubs.data.texts["jewelry_tables.json"] = SimpleNamespace(as_string=lambda: json.dumps(doc))
    tables, source = jk.load_tables()
    assert tables["metals"]["brass"]["density_g_cm3"] == 8.7 and "text block" in source
    # (d) nothing at all: the embedded copy
    del blender_stubs.data.texts["jewelry_tables.json"]
    tables, source = jk.load_tables()
    assert tables is jk._FALLBACK_TABLES and "embedded" in source
    # and __file__ missing altogether (exec'd from a text block) is survived
    monkeypatch.delattr(jk, "__file__")
    assert jk.load_tables()[0] is jk._FALLBACK_TABLES


def test_photo_imports_under_stubs(blender_stubs):
    photo = _import("photo", BLENDER / "photo.py")
    assert callable(photo.setup) and photo.SILVER["roughness"] < 0.2


# --------------------------------------------------------------------------- monstera
def test_leaf_design_is_pure(clean_imports):
    for name in ("bpy", "bmesh", "mathutils"):
        assert name not in sys.modules
    ld = _import("leaf_design", BLENDER / "monstera" / "leaf_design.py")
    p = ld.make_variant(np.random.default_rng(11020))
    assert {"length", "width", "slits", "holes", "veins", "yaw", "overlap", "pivot", "min_web",
            "slit_w", "slit_y", "hole_y", "hole_ab", "alpha", "u_wide", "tip_q"} <= set(p)
    assert set(p["slits"]) == {1, -1} and all(3 <= len(p["slits"][s]) <= 5 for s in (1, -1))
    assert 0.88 * ld.LEAF["length"] <= p["length"] <= 1.12 * ld.LEAF["length"]
    outline = ld.outline_poly(p)
    assert outline.shape[1] == 2 and len(outline) > 50
    assert np.allclose(outline[0], (0.0, 0.0)) and outline[:, 0].max() == pytest.approx(p["length"])
    slit = ld.slit_poly(p["slits"][1][0], 1, p)
    assert slit.shape[1] == 2 and len(slit) > 20
    # the same seed gives the same leaf, the identity the ring is rebuilt from
    q = ld.make_variant(np.random.default_rng(11020))
    assert q["length"] == p["length"] and q["slits"] == p["slits"] and q["holes"] == p["holes"]
    for name in ("bpy", "bmesh", "mathutils"):
        assert name not in sys.modules


def test_monstera_ring_reexports_leaf_design(blender_stubs):
    mr = _import("monstera_ring", BLENDER / "monstera" / "monstera_ring.py")
    ld = sys.modules["leaf_design"]                 # found through monstera_ring's own sys.path insert
    assert Path(ld.__file__).resolve() == (BLENDER / "monstera" / "leaf_design.py").resolve()
    for name in ("make_variant", "outline_poly", "slit_poly", "hole_poly", "_line", "_vein_depth",
                 "half_width", "_poly_gap", "_layout_ok", "_alpha"):
        assert getattr(mr, name) is getattr(ld, name), name
    for name in ("BAND", "LEAF", "VARIETY"):
        assert getattr(mr, name) is getattr(ld, name), name
    assert mr.RING_WIDTH == ld.RING_WIDTH
    for name in ("ring_plan", "build", "export_stl", "clean_mesh"):      # the 3-D side stayed here
        assert callable(getattr(mr, name))
    assert mr.LABEL_SIZE == 1.6


def test_gallery_runs_without_blender(tmp_path):
    out = tmp_path / "gallery"
    res = subprocess.run([sys.executable, str(BLENDER / "monstera" / "gallery.py"), "--out", str(out)],
                         cwd=tmp_path, capture_output=True, text=True, timeout=300)
    assert res.returncode == 0, res.stderr
    assert "worst web" in res.stdout
    assert (out / "gallery.png").stat().st_size > 10_000
