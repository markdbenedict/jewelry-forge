"""Where things are: repo root, ntopcl, Blender, output and deliverable folders.

Everything can be overridden with environment variables so the same code runs on the
main laptop, the 128 GB build server and the Linux test container:

  NTOPCL          full path to ntopcl.exe (default: Program Files, else `ntopcl` on PATH)
  JEWELRY_OUT     scratch output folder (default: <repo>/out)
  JEWELRY_DELIVER deliverables folder (default: ~/OneDrive/Documents/Jewelry)
  BLENDER         full path to blender.exe (optional)
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

DEFAULT_NTOPCL_WIN = Path(r"C:\Program Files\nTopology\nTopology\ntopcl.exe")


def repo_root(start: Path | None = None) -> Path:
    """Walk up from `start` (or this file) to the folder holding CLAUDE.md."""
    p = (start or Path(__file__)).resolve()
    for parent in [p] + list(p.parents):
        if (parent / "CLAUDE.md").exists() and (parent / "python").exists():
            return parent
    return Path.cwd()


def ntopcl_path() -> Path | None:
    env = os.environ.get("NTOPCL")
    if env:
        return Path(env)
    if DEFAULT_NTOPCL_WIN.exists():
        return DEFAULT_NTOPCL_WIN
    found = shutil.which("ntopcl") or shutil.which("ntopcl.exe")
    return Path(found) if found else None


def blender_path() -> Path | None:
    env = os.environ.get("BLENDER")
    if env:
        return Path(env)
    found = shutil.which("blender") or shutil.which("blender.exe")
    if found:
        return Path(found)
    if sys.platform == "win32":
        for p in sorted(Path(r"C:\Program Files\Blender Foundation").glob("Blender */blender.exe"), reverse=True):
            return p
    return None


def out_dir() -> Path:
    env = os.environ.get("JEWELRY_OUT")
    d = Path(env) if env else repo_root() / "out"
    d.mkdir(parents=True, exist_ok=True)
    return d


def deliver_dir() -> Path:
    env = os.environ.get("JEWELRY_DELIVER")
    if env:
        return Path(env)
    home = Path.home()
    for cand in (home / "OneDrive" / "Documents" / "Jewelry", home / "Documents" / "Jewelry"):
        if cand.exists():
            return cand
    return home / "Documents" / "Jewelry"


def notebooks_dir() -> Path:
    return repo_root() / "ntop" / "notebooks"


def catalog_dir() -> Path:
    return repo_root() / "catalog"
