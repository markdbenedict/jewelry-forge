"""Identity and bookkeeping for builds: what a run is called, where its files go, and what a
delivered part carries with it.

Rules (2026-10-27 review):
  * Every variant has a distinct name. A stem carries the profile, the size label, width and
    thickness, and a `spec_id`: a short hash of every number that defines the design, so two
    rings that differ only in a dome or an engraving never share a file name.
  * Every run writes into a fresh directory, `<out>/<stem>/<run id>/`, so an export left by an
    earlier run can never pass for this run's; `require_fresh` checks the file's time as well.
  * A delivered part is a folder, `<deliver>/<project>/<stem>/`, holding the STL, the inputs
    that produced it, the gate and build reports and a manifest (spec, notebook sha256 and
    recipe, ntopjewel version, git commit, nTopCL version, status). Delivery happens only
    when the status is PASSED - the caller checks; `deliver()` refuses anything else.
"""
from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import __version__, config, gate

SPEC_ID_CHARS = 8


def spec_id(design: dict) -> str:
    """Short, stable identifier of a design: sha1 of its defining numbers (sorted JSON)."""
    blob = json.dumps(design, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:SPEC_ID_CHARS]


def fresh_run_dir(out_dir: Path, stem: str) -> tuple[Path, str]:
    """A directory no run has used: <out_dir>/<stem>/<YYYYmmdd-HHMMSS>[-n]. Returns (dir, run id)."""
    base = Path(out_dir).resolve() / stem
    base.mkdir(parents=True, exist_ok=True)
    run_id = time.strftime("%Y%m%d-%H%M%S")
    cand, n = base / run_id, 1
    while cand.exists():
        n += 1
        cand = base / f"{run_id}-{n}"
    cand.mkdir()
    return cand, cand.name


def require_fresh(path: Path, started: float, what: str = "export") -> None:
    """The file must exist and have been written after `started` (time.time())."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"{what} {path} was not written")
    if path.stat().st_mtime < started - 2.0:          # 2 s: FAT/OneDrive timestamp granularity
        raise FileNotFoundError(f"{what} {path} predates this run (an old export, not this run's)")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def notebook_identity(notebook: Path) -> dict:
    """What built the part: the .ntop (hash, size, time) and its exported recipe when one sits
    in ntop/recipes next to the build script."""
    nb = Path(notebook).resolve()
    out = {"path": str(nb), "sha256": sha256(nb) if nb.exists() else None,
           "bytes": nb.stat().st_size if nb.exists() else None,
           "modified": datetime.fromtimestamp(nb.stat().st_mtime, timezone.utc).isoformat() if nb.exists() else None}
    recipe = config.repo_root() / "ntop" / "recipes" / f"{nb.stem}.recipe.json"
    if recipe.exists():
        out["recipe"] = {"path": str(recipe), "sha256": sha256(recipe)}
    return out


def git_commit() -> str | None:
    try:
        proc = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], capture_output=True, text=True,
                              cwd=str(config.repo_root()), timeout=10,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() or None


def environment(ntopcl_version: str | None = None) -> dict:
    return {"ntopjewel": __version__, "python": sys.version.split()[0], "platform": platform.platform(),
            "git_commit": git_commit(), "ntopcl": ntopcl_version}


def status_of(run_ok: bool, report: gate.GateReport | None) -> str:
    """PASSED only when the nTop run succeeded and every hard gate check passed."""
    if not run_ok or report is None:
        return gate.FAILED if not run_ok else gate.INCOMPLETE
    return report.status


def deliver(stl: Path, run_dir: Path, stem: str, project: str, manifest: dict,
            extra_files: list[Path] = (), cast_metal: str | None = None) -> Path:
    """Copy an accepted part and its evidence to <deliver>/<project>/<stem>/. Returns the STL
    there. Refuses unless manifest["status"] is PASSED.

    With `cast_metal`, also writes `<stem>.print_<metal>.stl`: the gated design scaled about the
    origin by tables.print_scale(metal) (casting + resin shrink, isotropic), the file to print
    when the part will be cast. The design-size STL stays beside it; the manifest records the
    factor and whether its figures are calibrated."""
    if manifest.get("status") != gate.PASSED:
        raise ValueError(f"refusing to deliver {stem}: status is {manifest.get('status')!r}, not {gate.PASSED!r}")
    dest = config.deliver_dir() / project / stem
    dest.mkdir(parents=True, exist_ok=True)
    out = Path(shutil.copy2(stl, dest / Path(stl).name))
    for p in [*extra_files, *sorted(Path(run_dir).glob(f"{stem}.*.json")), *sorted(Path(run_dir).glob(f"{stem}.*.log"))]:
        p = Path(p)
        if p.exists() and p.resolve() != Path(stl).resolve():
            shutil.copy2(p, dest / p.name)
    manifest = {**manifest, "delivered_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "delivered_stl": str(out), "sha256": sha256(out)}
    if cast_metal:
        from . import tables
        import trimesh
        factor, warnings = tables.print_scale(cast_metal)
        m = trimesh.load(str(stl), force="mesh")
        m.apply_scale(factor)                          # about the origin: the ring stays on its axis
        printed = dest / f"{stem}.print_{cast_metal}.stl"
        m.export(str(printed))
        manifest["print"] = {"stl": str(printed), "sha256": sha256(printed), "metal": cast_metal, "scale": factor,
                             "warnings": warnings}
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    return out
