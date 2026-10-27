r"""Where the Blender scripts find the checkout and put their output. Pure Python (no bpy), so it
imports in Blender's Python, the system Python and pytest alike, on either laptop.

  REPO                      the checkout: this file is <repo>/blender/forge_paths.py
  out_dir(*parts)           scratch output folder, created on demand: $JEWELRY_OUT when set,
                            else <repo>/out (the same JEWELRY_OUT ntopjewel.config honours), plus
                            the given sub-folders, e.g. out_dir("blender", "monstera")
  add_to_sys_path(*names)   puts <repo>/blender and the named sub-folders of it at the front of
                            sys.path (once), so jewelry_kit, photo, monstera_ring and leaf_design
                            import by name

A script that runs as `blender -b -P blender\monstera\test_ring.py` starts with

    import sys; from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))     # blender/, for this module
    import forge_paths
    forge_paths.add_to_sys_path("monstera")
    OUT = forge_paths.out_dir("blender", "monstera")
"""
import os
import sys
from pathlib import Path

BLENDER_DIR = Path(__file__).resolve().parent
REPO = BLENDER_DIR.parent


def out_dir(*parts):
    env = os.environ.get("JEWELRY_OUT")
    d = (Path(env) if env else REPO / "out").joinpath(*parts)
    d.mkdir(parents=True, exist_ok=True)
    return d


def add_to_sys_path(*names):
    for d in (BLENDER_DIR, *(BLENDER_DIR / n for n in names)):
        if str(d) not in sys.path:
            sys.path.insert(0, str(d))
