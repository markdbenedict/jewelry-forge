"""Every build script must import, and the notebook-building ones must build, inside nTop's Python
Console - which has none of this package's dependencies. `api build multistone` failed there on
2026-11-03 ("No module named 'yaml'"): the recipe imported ntopjewel.multistone at the top. These
tests run each recipe in a child Python where the third-party packages cannot be imported."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
RECIPES = sorted(p.stem for p in (REPO / "ntop" / "recipes").glob("*.py"))
BLOCKED = ["yaml", "numpy", "scipy", "trimesh", "shapely", "manifold3d", "embreex", "PIL", "networkx", "mapbox_earcut"]

PRELUDE = f"""
import sys, importlib.abc
BLOCKED = {BLOCKED!r}
class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split('.')[0] in BLOCKED:
            raise ModuleNotFoundError(f"No module named {{name!r}} (nTop's Python)")
        return None
sys.meta_path.insert(0, Blocker())
sys.path[:0] = [{str(REPO / 'python')!r}, {str(REPO / 'python' / 'tests')!r}]
import importlib.util
def load(name):
    spec = importlib.util.spec_from_file_location(name, {str(REPO / 'ntop' / 'recipes')!r} + '/' + name + '.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
"""


def _run(code: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", PRELUDE + code], capture_output=True, text=True, timeout=300)


@pytest.mark.parametrize("name", RECIPES)
def test_every_recipe_imports_without_the_dependencies(name):
    r = _run(f"load({name!r})")
    assert r.returncode == 0, r.stderr[-2000:]


@pytest.mark.parametrize("name", ["multistone", "pave_band", "ring_shank", "ring_artwork", "open_bar", "transform_probe", "points_probe"])
def test_the_new_recipes_build_without_the_dependencies(name, tmp_path, fake_open_bar):
    """prepare() runs on the laptop (here, with everything); build() then runs in the blocked child."""
    from .fake_notebook import FakeNotebook
    from .test_notebook_api import load_recipe
    from ntopjewel import gems
    mod = load_recipe(name)
    params = mod.prepare({}, tmp_path) if hasattr(mod, "prepare") else {}
    params.update({"save_to": str(tmp_path / "x.ntop"), "recipe_to": str(tmp_path / "x.json"), "test_output": str(tmp_path / "x.stl"),
                   "open_bar_block": str(fake_open_bar)})
    if name == "open_bar":
        params.update({"block_to": str(tmp_path / "open_bar.ntop"), "block_recipe_to": str(tmp_path / "ob.block.json")})
    if name == "multistone":                                      # its two blocks, built by the fake first
        env = tmp_path / "env.stl"
        gems.SeatSpec(gems.StoneSpec("round", 6.5)).envelope().export(str(env))
        load_recipe("stone_seat").build(FakeNotebook(), {"save_to": str(tmp_path / "sh.ntop"), "recipe_to": str(tmp_path / "sh.json"),
                                                         "test_output": str(tmp_path / "s.stl"), "values": {"Seat Path": str(env)}})
        oh = load_recipe("outline_head")
        pp = oh.prepare({}, tmp_path)
        pp.update({"save_to": str(tmp_path / "oh.ntop"), "recipe_to": str(tmp_path / "oh.json"), "test_output": str(tmp_path / "h.stl"),
                   "seat_block": str(tmp_path / "stone_seat.ntop")})
        oh.build(FakeNotebook(), pp)
        params.update({"seat_block": str(tmp_path / "stone_seat.ntop"), "head_block": str(tmp_path / "outline_head.ntop")})
    pfile = tmp_path / "params.json"
    pfile.write_text(json.dumps(params, default=str))
    r = _run(f"""
import json
from fake_notebook import FakeNotebook
res = load({name!r}).build(FakeNotebook(), json.loads(open({str(pfile)!r}).read()))
assert res.get("warnings", []) == [], res["warnings"]
""")
    assert r.returncode == 0, r.stderr[-3000:]
