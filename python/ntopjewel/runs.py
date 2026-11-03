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


WINDOWS_MAX_PATH = 259                   # MAX_PATH - 1: the longest path a Windows API call takes without long paths
LONGEST_SUFFIX = ".print_sterling.stl"    # the longest file name a run writes beside <stem>.stl
RUN_ID_CHARS = len("YYYYmmdd-HHMMSS-9")


class RunPathError(ValueError):
    """The run's files would have paths Windows cannot open (over MAX_PATH, long paths off)."""


def long_paths_enabled() -> bool:
    """Windows: the LongPathsEnabled policy (Python honours it; whether nTopCL does is unverified).
    Elsewhere: True."""
    if sys.platform != "win32":
        return True
    try:  # pragma: no cover - Windows only
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem") as k:
            return int(winreg.QueryValueEx(k, "LongPathsEnabled")[0]) == 1
    except OSError:  # pragma: no cover
        return False


def path_limit() -> int | None:
    """The longest path this machine's file calls accept, or None when there is no practical limit."""
    return None if long_paths_enabled() else WINDOWS_MAX_PATH


def fresh_run_dir(out_dir: Path, stem: str, max_path: int | None = None) -> tuple[Path, str]:
    """A directory no run has used: <out_dir>/<stem>/<YYYYmmdd-HHMMSS>[-n]. Returns (dir, run id).

    Refused (RunPathError) before anything is made when the longest file the run will write,
    `<dir>/<stem>/<run id>/<stem>.print_sterling.stl`, would exceed `max_path` (default: 259 on
    Windows without the LongPathsEnabled policy, no limit elsewhere): a stem appears twice in every
    file's path and a solitaire's runs to 90 characters, so a deep `--out` hits Windows' MAX_PATH
    with a FileNotFoundError from the middle of a build (seen 2026-11-03 under pytest's temp dir)."""
    base = Path(out_dir).resolve() / stem
    limit = path_limit() if max_path is None else max_path
    if limit is not None:
        longest = len(str(base)) + 1 + RUN_ID_CHARS + 1 + len(stem) + len(LONGEST_SUFFIX)
        if longest > limit:
            raise RunPathError(
                f"the run's files would have paths of {longest} characters under {base.parent}, over the "
                f"{limit} this machine's file calls accept (the stem is {len(stem)} characters and appears twice): "
                f"use a shorter --out, or enable long paths (Windows: LongPathsEnabled, `python -m ntopjewel doctor`)")
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


def build_stamp_path(notebook: Path) -> Path:
    """`ring_shank.ntop` -> `ring_shank.build.json` beside it: which catalog versions the notebook was built for."""
    nb = Path(notebook)
    return nb.with_name(nb.stem + ".build.json")


def write_build_stamp(notebook: Path, catalogs: dict[str, str] | None = None) -> dict | None:
    """After `api build` saved a notebook: record its hash and the version of every catalog that
    names it (the contract it was built to), so a run can tell a notebook that predates a change
    that needs a rebuild (require_built). None when no catalog names the notebook (a block, a
    scratch build)."""
    from . import catalog as catmod
    nb = Path(notebook).resolve()
    cats = dict(catalogs or {})
    for name in ([] if catalogs else catmod.names()):
        try:
            c = catmod.load(name)
        except Exception:
            continue
        if Path(c.notebook).resolve() == nb:
            cats[name] = c.version
    if not cats or not nb.exists():
        return None
    stamp = {"notebook": nb.name, "sha256": sha256(nb), "built": datetime.now(timezone.utc).isoformat(),
             "catalogs": cats, "git_commit": git_commit(), "ntopjewel": __version__}
    build_stamp_path(nb).write_text(json.dumps(stamp, indent=2), encoding="utf-8")
    return stamp


def _version_key(v: str) -> tuple:
    return tuple(int(x) if x.isdigit() else 0 for x in str(v).split("."))


def require_built(cat, notebook: Path) -> list[str]:
    """Refuse a notebook older than the catalog needs: when the catalog says `rebuild_since: X`
    (the notebook body changed in version X, its inputs perhaps not - nothing else would notice),
    the notebook's build stamp must name catalog version X or later. Returns warnings (a notebook
    changed since its stamp: built or edited outside `api build`). Raises ValueError naming the
    rebuild. 2026-11-02: four notebooks ran a day's old build and one design failed for it."""
    nb = Path(notebook)
    since = getattr(cat, "rebuild_since", None)
    stamp_path = build_stamp_path(nb)
    stamp = None
    if stamp_path.exists():
        try:
            stamp = json.loads(stamp_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            stamp = None
    fix = f"rebuild it: python -m ntopjewel api build {_recipe_for(nb)} (nTop open, Python Console open), then run again"
    if since:
        built_for = (stamp or {}).get("catalogs", {}).get(cat.name)
        if built_for is None:
            raise ValueError(f"{nb.name} has no build stamp for catalog {cat.name} {cat.version}, which needs a notebook "
                             f"built for {since} or later - {fix}")
        if _version_key(built_for) < _version_key(since):
            raise ValueError(f"{nb.name} was built for {cat.name} {built_for}; the catalog is {cat.version} and its notebook "
                             f"changed in {since} - {fix}")
    warnings = []
    if stamp and nb.exists() and stamp.get("sha256") and stamp["sha256"] != sha256(nb):
        warnings.append(f"{nb.name} changed since its build stamp ({stamp.get('built', '?')}): edited in the GUI or "
                        "pulled from elsewhere? Rebuild it if in doubt")
    return warnings


def _recipe_for(notebook: Path) -> str:
    """The `api build` name that writes a notebook (ntop/recipes/<name>.py saves ntop/notebooks/<x>.ntop)."""
    stem = Path(notebook).stem
    stem = stem[:-len("_harness")] if stem.endswith("_harness") else stem
    return {"ring_band_profile": "band_profile"}.get(stem, stem)


def stamp_fresh_builds(started: float) -> list[Path]:
    """Every catalogued notebook saved since `started` (an `api build` that just finished; a block
    recipe saves its harness too) gets its build stamp. Returns the notebooks stamped."""
    from . import catalog as catmod
    done = []
    for name in catmod.names():
        try:
            nb = Path(catmod.load(name).notebook)
        except Exception:
            continue
        if nb.exists() and nb.stat().st_mtime >= started - 1.0 and nb not in done and write_build_stamp(nb):
            done.append(nb)
    return done


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
