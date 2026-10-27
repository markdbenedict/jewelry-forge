"""Drive nTop's Notebook API (Private Beta, nTop 6.3+).

Two halves, both standard-library only so this module also imports inside nTop's own Python:

* `Console` — from Claude Code (or any shell) on the laptop: talks to the Python Console
  that nTop exposes over SSH at localhost:2222 while the console panel is open. Sends one
  line at a time, as nTop's documentation requires; a build script is run with
  `exec(open(driver).read())` and reports back through a JSON file.
* `NotebookHelper` — inside nTop's Python, wrapping the `notebook` object: identifier lookup
  by mask instead of hard-coded strings, input-name matching, wiring, build-state checks.

Facts from nTop's Notebook API documentation (October 2026, package v0.14):
  - every call is a method of `notebook`; ids are exact strings such as "sphere<point,real>";
  - `add_block` returns {"name","id","funcId"}; use the returned id;
  - a block output used in two places must go through a variable (`add_variable`);
  - invalid inputs fail at build time: check `block_state(id)["buildState"]` (e_OK / e_FAILED);
  - `save_notebook_as` / `export_as_recipe` overwrite without asking; `new_notebook` discards;
  - over SSH: keep the console panel open, send one line at a time, Ctrl-C ends the session.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterable

DEFAULT_PORT = 2222
DEFAULT_HOST = "localhost"
DONE = "__NTOPJEWEL_DONE__"
FAIL = "__NTOPJEWEL_FAIL__"


class ConsoleError(RuntimeError):
    pass


def default_key() -> Path:
    env = os.environ.get("NTOP_SSH_KEY")
    return Path(env) if env else Path.home() / ".ssh" / "id_ntopcli"


# =============================================================================== Console
class Console:
    """One SSH session to nTop's Python Console per call; nothing persistent.

    `transport` is injectable for tests: a callable (line, timeout) -> captured output text.
    """

    HEARTBEAT_S = 30.0       # while a line runs, say so this often (a build is silent otherwise)

    def __init__(self, key: Path | None = None, port: int = DEFAULT_PORT, host: str = DEFAULT_HOST,
                 ssh: str = "ssh", transport: Callable[[str, float], str] | None = None,
                 progress: Callable[[str], None] | None = None):
        self.key = Path(key) if key else default_key()
        self.port, self.host, self.ssh = port, host, ssh
        self._transport = transport or self._ssh_transport
        self.progress = progress            # called with a one-line status every HEARTBEAT_S while waiting

    def _heartbeat(self, stop: threading.Event, started: float) -> None:
        while not stop.wait(self.HEARTBEAT_S):
            waited = time.time() - started
            hint = (" - if nTop is showing a dialog (Save changes? / an error box), answer it: the console "
                    "waits behind it" if waited >= 60 else "")
            self.progress(f"waiting for nTop ({waited:.0f} s){hint}")

    # ---- transport -------------------------------------------------------------------
    def command(self) -> list[str]:
        return [self.ssh, "-tt", "-i", str(self.key), "-p", str(self.port),
                "-o", "StrictHostKeyChecking=accept-new", "-o", "LogLevel=ERROR", self.host]

    def _ssh_transport(self, line: str, timeout: float) -> str:
        if not self.key.exists():
            raise ConsoleError(f"SSH key not found: {self.key}. Create it per nTop's Notebook API doc "
                               f"(ssh-keygen -t ed25519 -f {self.key} -C \"nTop console key\") and append the .pub "
                               f"to ~/.ssh/authorized_keys.")
        try:
            proc = subprocess.Popen(self.command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, bufsize=1,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as e:
            raise ConsoleError(f"could not start ssh: {e}") from e
        out: list[str] = []
        timed_out = threading.Event()

        def _kill():
            timed_out.set()
            try:
                proc.kill()
            except Exception:
                pass

        watchdog = threading.Timer(timeout, _kill)
        watchdog.daemon = True
        watchdog.start()
        stop_beat = threading.Event()
        if self.progress:
            beat = threading.Thread(target=self._heartbeat, args=(stop_beat, time.time()), daemon=True)
            beat.start()
        found = False
        try:
            proc.stdin.write(line.rstrip("\n") + "\n")
            proc.stdin.flush()
            while True:
                chunk = proc.stdout.readline()
                if chunk == "":
                    if proc.poll() is not None:
                        break
                    time.sleep(0.1)                  # EOF before exit: do not spin
                    continue
                out.append(chunk)
                if DONE in chunk or FAIL in chunk:   # the sent line never contains the sentinel itself
                    found = True
                    break
        finally:
            stop_beat.set()
            watchdog.cancel()
            try:
                proc.stdin.write("\x03")          # Ctrl-C ends the SSH console session (never exit())
                proc.stdin.flush()
            except Exception:
                pass
            try:
                proc.terminate()
            except Exception:
                pass
            for stream in (proc.stdin, proc.stdout):
                try:
                    stream.close()
                except Exception:
                    pass
            try:
                proc.wait(timeout=5)
            except Exception:
                pass
        text = "".join(out)
        if timed_out.is_set() or (not found and not text.strip()):
            raise ConsoleError(f"timed out after {timeout:.0f}s waiting for nTop; partial output:\n{text[-3000:]}")
        if "Permission denied" in text:
            raise ConsoleError("ssh: Permission denied (publickey). Check ~/.ssh/authorized_keys holds the key, "
                               "was written without a BOM, and that only your account can write it.")
        if "Connection refused" in text or "Could not resolve" in text:
            raise ConsoleError("ssh: connection refused on localhost:2222. nTop must be running with a notebook "
                               "open and View > Python Console open; the endpoint exists only then.")
        return text

    # ---- high level ------------------------------------------------------------------
    def run_line(self, line: str, timeout: float = 60) -> str:
        """Send one Python line; return the console's echoed output.

        The console echoes what it receives, so the sentinel is assembled at run time
        (`"__NTOPJEWEL_" + "DONE__"`) and never appears verbatim in the sent line.
        """
        head, tail = DONE[:12], DONE[12:]
        marker = f'print("{head}" + "{tail}")'
        return self._transport(f"{line}; {marker}", timeout)

    def check(self, timeout: float = 30) -> str:
        """Prove the connection: sections of the open notebook."""
        return self.run_line("print(notebook.list_sections())", timeout)

    def run_script(self, script: Path, params: dict | None = None, *, work_dir: Path,
                   python_path: Path | None = None, timeout: float = 900, entry: str = "build") -> dict:
        """Run `entry(notebook, params)` from `script` inside nTop and return its result dict.

        A small driver file is written to `work_dir`; nTop runs it with exec(open(...).read()),
        which is the one-line form the SSH console accepts. The driver writes the result (or
        the traceback) to a JSON file and prints a sentinel.
        """
        driver_path, result_path = prepare_script(script, params, work_dir=work_dir, python_path=python_path, entry=entry)
        output = self._transport(exec_line(driver_path), timeout)
        return collect_result(Path(script), result_path, output)


def prepare_script(script: Path, params: dict | None = None, *, work_dir: Path,
                   python_path: Path | None = None, entry: str = "build") -> tuple[Path, Path]:
    """Write `<stem>.params.json` and `<stem>.driver.py` into `work_dir`; return (driver, result) paths.

    The driver is what nTop runs; it can also be pasted into the GUI's Python Console by hand
    as `exec_line(driver)` when SSH is not set up.
    """
    script = Path(script).resolve()
    work_dir = Path(work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    params_path = work_dir / f"{script.stem}.params.json"
    result_path = work_dir / f"{script.stem}.result.json"
    driver_path = work_dir / f"{script.stem}.driver.py"
    params_path.write_text(json.dumps(params or {}, indent=2), encoding="utf-8")
    if result_path.exists():
        result_path.unlink()
    driver_path.write_text(driver_source(script, params_path, result_path, python_path, entry), encoding="utf-8")
    return driver_path, result_path


def exec_line(driver_path: Path) -> str:
    """The one console line that runs a driver file."""
    return f'exec(open(r"{driver_path}").read())'


def collect_result(script: Path, result_path: Path, output: str = "") -> dict:
    """Read the driver's result file; raise ConsoleError with the traceback if the script failed."""
    if not result_path.exists():
        raise ConsoleError(f"the script produced no result file ({result_path}); console output:\n{output[-4000:]}")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["console_output"] = output[-4000:]
    if result.get("status") != "ok":
        raise ConsoleError(f"{Path(script).name} failed inside nTop:\n{result.get('traceback', '')}")
    return result


def driver_source(script: Path, params_path: Path, result_path: Path, python_path: Path | None, entry: str) -> str:
    """Python that nTop's console runs: load the script by path, call entry(notebook, params)."""
    pp = f"sys.path.insert(0, r\"{python_path}\")" if python_path else ""
    return f'''import sys, json, traceback, importlib, importlib.util
{pp}
# nTop's Python lives on between runs: drop our cached modules so edited files are what runs
for _k in [k for k in list(sys.modules) if k == "ntopjewel" or k.startswith("ntopjewel.") or k == "{script.stem}"]:
    del sys.modules[_k]
importlib.invalidate_caches()
_result = {{"status": "fail", "script": r"{script}"}}
try:
    _spec = importlib.util.spec_from_file_location("{script.stem}", r"{script}")
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    _params = json.load(open(r"{params_path}", encoding="utf-8"))
    _out = getattr(_mod, "{entry}")(notebook, _params)
    _result = {{"status": "ok", "script": r"{script}", "result": _out}}
except Exception as _e:
    _result["traceback"] = traceback.format_exc()
    _result["error"] = f"{{type(_e).__name__}}: {{_e}}"
json.dump(_result, open(r"{result_path}", "w", encoding="utf-8"), indent=2, default=str)
if _result["status"] == "ok":
    print("{DONE}")
else:
    print("FAILED:", _result["error"].splitlines()[0][:300])
    print("details:", r"{result_path}")
    print("{FAIL}")
'''


# ========================================================================= NotebookHelper
VERSION_RE = re.compile(r"\[(\d+)\.(\d+)\.(\d+)\]$")


def _norm(s: str) -> str:
    """Identifiers are snake_case: compare case-insensitively with spaces as underscores."""
    return s.lower().replace(" ", "_")


def identifier_version(ident: str) -> tuple[int, int, int]:
    """`[x.y.z]` suffix as a tuple; an unversioned identifier is version 1.0.0 - the original,
    often deprecated definition (nTopCL 6.3.3: "Boolean Subtract version 1.0.0 is now
    deprecated" for the unversioned `boolean_subtract<…>`; the current block is `[5.44.0]`)."""
    m = VERSION_RE.search(ident)
    return tuple(int(x) for x in m.groups()) if m else (1, 0, 0)


def _rank(ident: str, terms: Iterable[str] = (), prefer_shortest: bool = True) -> tuple:
    """Sort key: the identifier whose *name* (before `<`) matches a search term earliest wins
    (`boolean_subtract<…>` over `slice_stack_boolean_subtract<…>`), then the HIGHEST version
    (unversioned counts as 1.0.0), then the shortest, then alphabetical."""
    ver = tuple(-v for v in identifier_version(ident))
    base = VERSION_RE.sub("", ident)
    name = _norm(base.split("<")[0])
    pos = min([name.find(_norm(t)) for t in terms if name.find(_norm(t)) >= 0] or [10 ** 6])
    return (pos, ver, len(base) if prefer_shortest else 0, ident)


class NotebookHelper:
    """Conveniences over the `notebook` object inside nTop's Python Console."""

    BUILDING = {"e_DIRTY", "e_QUEUED", "e_BUILDING"}

    def __init__(self, notebook):
        self.nb = notebook
        self._available: list[str] | None = None
        self.log: list[str] = []
        self.blocks: dict[str, str] = {}       # our label -> nTop id
        self.identifiers: dict[str, str] = {}  # our label -> identifier used
        self.moved_inputs: list[str] = []      # ids moved to the Inputs section (block_state no longer finds them)

    # ---- identifiers ----------------------------------------------------------------
    def available(self) -> list[str]:
        if self._available is None:
            self._available = list(self.nb.list_available_blocks())
        return self._available

    def lookup(self, mask: str) -> list[str]:
        """Ask nTop for identifiers matching `mask` (both spellings) and merge them into the cache."""
        found: list[str] = []
        for m in dict.fromkeys([mask, mask.lower(), mask.title()]):
            try:
                found.extend(self.nb.list_available_blocks(m))
            except Exception as e:  # pragma: no cover - depends on nTop
                self.log.append(f"list_available_blocks({m!r}) failed: {e}")
        avail = self.available()
        new = [f for f in dict.fromkeys(found) if f not in avail]
        avail.extend(new)
        return found

    @staticmethod
    def _alternatives(must) -> list[list[str]]:
        """`must` is a list of substrings (all required) or a list of such lists (tried in order)."""
        must = list(must) if not isinstance(must, str) else [must]
        if must and all(isinstance(m, (list, tuple)) for m in must):
            return [list(m) for m in must]
        return [must] if must else [[]]

    def identifier(self, *candidates: str, mask: str = "", must: Iterable = (), prefer_shortest: bool = True) -> str:
        """First exact candidate that exists, else the identifier containing every `must`
        substring (case-insensitive) among those matching `mask`; `must` may list
        alternatives (`[["boolean subtract", "implicit"], ["subtract", "implicit"]]`).
        Falls back to masked `list_available_blocks` queries in case the unmasked list is
        incomplete. Raises with the nearest identifiers it saw."""
        avail = self.available()
        for c in candidates:
            if c in avail:
                return c
        alts = self._alternatives(must)
        if alts == [[]] and candidates:            # no `must`: the candidates themselves, then their head words
            alts = [[c.lower()] for c in candidates] + [[c.split("<")[0].lower()] for c in candidates]
        words = {w for c in candidates for w in re.findall(r"[a-z]+", c.split("<")[0].lower())}
        words |= {w for alt in alts for m in alt for w in re.findall(r"[a-z]+", m.lower())}
        if mask:
            words |= set(re.findall(r"[a-z]+", mask.lower()))
        words -= {"body", "real", "point", "list", "implicit", "of", "from", "to", "by", "and", "a", "the"}

        def search() -> tuple[list[str], list[str], list[str]]:
            pool = [a for a in avail if _norm(mask) in _norm(a)] if mask else list(avail)
            for alt in alts:
                hits = [a for a in pool if all(_norm(m) in _norm(a) for m in alt)]
                if hits:
                    return hits, pool, list(alt) + ([mask] if mask else [])
            return [], pool, []

        hits, pool, terms = search()
        if not hits:                                   # the unmasked list may be partial: ask again by word
            for q in dict.fromkeys([mask, *(w for w in words)]):
                if q:
                    self.lookup(q)
            for c in candidates:
                if c in avail:
                    return c
            hits, pool, terms = search()
        if not hits:
            near = pool[:25] if pool else [a for a in avail if any(w in a.lower() for w in words)][:25]
            raise ConsoleError(f"no block identifier for {candidates or must} (mask {mask!r}) among {len(avail)} "
                               f"available; nearest: {near}")
        hits.sort(key=lambda s: _rank(s, terms, prefer_shortest))
        return hits[0]

    # ---- blocks ------------------------------------------------------------------------
    def add(self, label: str, *candidates: str, mask: str = "", must: Iterable[str] = (), section_id: str = "") -> str:
        ident = self.identifier(*candidates, mask=mask, must=must)
        info = self.nb.add_block(ident, section_id) if section_id else self.nb.add_block(ident)
        self.blocks[label] = info["id"]
        self.identifiers[label] = ident
        self.log.append(f"add {label}: {ident} -> {info['id']}")
        return info["id"]

    def inputs(self, block_id: str) -> list[dict]:
        return [i for i in self.nb.list_block_inputs(block_id) if not i.get("isReturnValue")]

    def properties(self, block_id: str) -> list[str]:
        """Property names of a built block; tolerates dicts, strings or a dict-of-dicts answer."""
        try:
            raw = self.nb.list_block_properties(block_id)
        except Exception as e:
            self.log.append(f"list_block_properties({block_id}) failed: {e}")
            return []
        if isinstance(raw, dict):
            raw = list(raw.get("properties", raw.keys()))
        out = []
        for pr in raw or []:
            if isinstance(pr, dict):
                out.append(str(pr.get("name") or pr.get("id") or pr))
            else:
                out.append(str(pr))
        return out

    def input_name(self, block_id: str, *candidates: str) -> str:
        """The block's actual input name matching one of `candidates` (exact, then case-insensitive, then contains)."""
        names = [i["name"] for i in self.inputs(block_id)]
        for c in candidates:
            if c in names:
                return c
        low = {n.lower(): n for n in names}
        for c in candidates:
            if c.lower() in low:
                return low[c.lower()]
        for c in candidates:
            for n in names:
                if c.lower() in n.lower():
                    return n
        raise ConsoleError(f"block {block_id} has no input like {candidates}; it has {names}")

    def input_of_type(self, block_id: str, type_substring: str) -> str:
        """The first input whose type contains `type_substring` ("implicit", "real_field"):
        robust where input names are unknown (a fresh block from the discovery dump)."""
        ins = self.inputs(block_id)
        for i in ins:
            if type_substring in str(i.get("type", "")):
                return i["name"]
        raise ConsoleError(f"block {block_id} has no input of type ~{type_substring!r}; it has "
                           f"{[(i.get('name'), i.get('type')) for i in ins]}")

    def set(self, block_id: str, input_candidates: str | Iterable[str], value: Any, units: str = "") -> str:
        cands = [input_candidates] if isinstance(input_candidates, str) else list(input_candidates)
        name = self.input_name(block_id, *cands)
        if units:
            self.nb.set_block_input(block_id, name, value, units)
        else:
            self.nb.set_block_input(block_id, name, value)
        self.log.append(f"set {block_id}.{name} = {value} {units}")
        return name

    def wire(self, source_id: str, target_id: str, input_candidates: str | Iterable[str], prop: str = "") -> str:
        cands = [input_candidates] if isinstance(input_candidates, str) else list(input_candidates)
        name = self.input_name(target_id, *cands)
        self.nb.connect_block_property(source_id, prop, target_id, name)
        self.log.append(f"wire {source_id}{'.' + prop if prop else ''} -> {target_id}.{name}")
        return name

    def to_list(self, source_id: str, target_id: str, list_candidates: str | Iterable[str]) -> str:
        cands = [list_candidates] if isinstance(list_candidates, str) else list(list_candidates)
        name = self.input_name(target_id, *cands)
        self.nb.append_to_list(source_id, target_id, name)
        self.log.append(f"list {source_id} -> {target_id}.{name}")
        return name

    # ---- variables, inputs, output ---------------------------------------------------
    def real_var(self, name: str, value: float, units: str = "mm") -> str:
        """A `core.var<real>`. With units: `add_real_variable(name, value, units)`, else the
        unitless variable plus `set_block_input_units(id, "Input", units)`. Raises (listing
        both refusals) rather than silently making a unitless variable - a unitless value on
        a dimensioned input fails the build ("requires units of mass/length^3", 2026-10-27)."""
        if not units:
            info = self.nb.add_real_variable(name, value)
            self.blocks[name] = info["id"]
            self.log.append(f"var {name} = {value} (no units)")
            return info["id"]
        attempts = []
        try:
            info = self.nb.add_real_variable(name, value, units)
            self.blocks[name] = info["id"]
            self.log.append(f"var {name} = {value} {units}")
            return info["id"]
        except Exception as e:
            attempts.append(f"add_real_variable(..., {units!r}): {e}")
        set_units = getattr(self.nb, "set_block_input_units", None)
        if callable(set_units):
            info = None
            try:
                info = self.nb.add_real_variable(name, value)
                set_units(info["id"], "Input", units)
                self.blocks[name] = info["id"]
                self.log.append(f"var {name} = {value} {units} (units set afterwards with set_block_input_units)")
                return info["id"]
            except Exception as e:
                attempts.append(f"set_block_input_units(..., 'Input', {units!r}): {e}")
                if info:
                    self.remove(info["id"])
        raise ConsoleError(f"could not make a real variable {name!r} in {units!r}: " + "; ".join(attempts))

    def units_of(self, block_id: str, input_name: str) -> str:
        """What nTop says an input's units are (`get_block_input_units`), '' if it will not say."""
        fn = getattr(self.nb, "get_block_input_units", None)
        if not callable(fn):
            return ""
        try:
            u = fn(block_id, input_name)
            self.log.append(f"units of {block_id}.{input_name}: {u!r}")
            return u if isinstance(u, str) else str(u)
        except Exception as e:
            self.log.append(f"get_block_input_units({block_id}, {input_name}) failed: {e}")
            return ""

    def wrap_var(self, name: str, block_id: str) -> str:
        info = self.nb.add_variable(name, block_id)
        self.blocks[name] = info["id"]
        self.log.append(f"var {name} wraps {block_id}")
        return info["id"]

    VOLUME_UNITS = ("mm^3", "mm³", "mm3", "m^3", "m³", "cm^3", "")

    def property_var(self, name: str, source_id: str, prop: str, units: Iterable[str] = VOLUME_UNITS) -> str:
        """A variable fed by a property of `source_id` (e.g. Mass Properties -> volume).

        A TYPED real variable first (`core.var<real>`, like the chip the GUI makes when a
        property is dragged out): its type is known even before it builds, which nTopCL's
        `-t` needs ("Output of function not built" with an untyped output, 2026-10-27). The
        untyped `add_variable` + input `x` route is the fallback."""
        errors = []
        for u in units:
            tmp = f"{name} tmp"
            try:
                var_id = self.real_var(tmp, 0.0, u)
            except Exception as e:
                errors.append(f"real variable ({u or 'no units'}): {e}")
                self.log.append(f"{name}: {u or 'no units'} refused: {e}")
                continue
            self.blocks.pop(tmp, None)
            try:
                self.nb.connect_block_property(source_id, prop, var_id, "Input")
            except Exception as e:
                errors.append(f"connect to real variable ({u or 'no units'}): {e}")
                self.remove(var_id)
                continue
            try:
                var_id = self.nb.rename_variable(var_id, name)["id"]
            except Exception as e:  # keep the temporary name rather than fail
                self.log.append(f"rename of {var_id} failed: {e}")
            self.blocks[name] = var_id
            self.log.append(f"var {name} <- {source_id}.{prop} (real variable {var_id}, units {u or 'none'})")
            return var_id
        try:
            info = self.nb.add_variable(name)
            var_id = info["id"]
            names = [i["name"] for i in self.nb.list_block_inputs(var_id) if not i.get("isReturnValue")] or ["x"]
            self.nb.connect_block_property(source_id, prop, var_id, names[0])
            self.blocks[name] = var_id
            self.log.append(f"var {name} <- {source_id}.{prop} (untyped variable, input {names[0]})")
            return var_id
        except Exception as e:
            errors.append(f"untyped variable: {e}")
        raise ConsoleError(f"could not feed a variable from {source_id}.{prop}: " + "; ".join(errors))

    def remove(self, block_id: str) -> bool:
        """Delete a block or variable we added and cannot use (an unset one makes nTopCL fail
        with `Input "Input" is incomplete`). Tries delete_variable, then delete_block."""
        for name in ("delete_variable", "delete_block"):
            fn = getattr(self.nb, name, None)
            if callable(fn):
                try:
                    fn(block_id)
                    self.log.append(f"removed {block_id} with {name}")
                    return True
                except Exception as e:
                    self.log.append(f"{name}({block_id}) refused: {e}")
        return False

    def diagnostics(self) -> dict:
        """What the helper knows, for an error report: identifiers, ids, log, best-effort states."""
        states = {}
        for label, bid in list(self.blocks.items())[-40:]:
            try:
                st = self.nb.block_state(bid)
                states[label] = st.get("buildState", "?") + (f": {st['error']}" if st.get("error") else "")
            except Exception as e:
                states[label] = f"?: {e}"
        return {"identifiers": self.identifiers, "blocks": self.blocks, "states": states, "log": self.log[-60:]}

    def declare_inputs(self, ids: Iterable[str]) -> None:
        """Move variables to the notebook's Inputs section. After the move nTop no longer answers
        block_state for the old id ("No block with the id ... exists in the notebook", seen
        2026-10-26); the wires from it stay intact."""
        for i in ids:
            info = self.nb.move_block_to_input(i)
            new_id = info.get("id", i) if isinstance(info, dict) else i
            self.moved_inputs.append(new_id)
            if new_id != i:
                for label, bid in self.blocks.items():
                    if bid == i:
                        self.blocks[label] = new_id
            self.log.append(f"input {i}" + (f" -> {new_id}" if new_id != i else ""))

    def set_output(self, block_id: str) -> None:
        self.nb.set_block_as_output(block_id)
        self.log.append(f"output {block_id}")

    # ---- build state -----------------------------------------------------------------
    def state(self, block_id: str, wait_s: float = 120) -> dict:
        deadline = time.time() + wait_s
        st = self.nb.block_state(block_id)
        while st.get("buildState") in self.BUILDING and time.time() < deadline:
            time.sleep(0.5)
            st = self.nb.block_state(block_id)
        return st

    def assert_ok(self, block_id: str, wait_s: float = 120) -> dict:
        st = self.state(block_id, wait_s)
        if st.get("buildState") != "e_OK":
            raise ConsoleError(f"{block_id}: {st.get('buildState')} {st.get('error', '')}".strip())
        return st

    def states(self, wait_s: float = 120) -> dict[str, str]:
        out = {}
        for label, bid in self.blocks.items():
            if bid in self.moved_inputs:
                out[label] = "input"                 # lives in the Inputs section now; not a body block
                continue
            try:
                st = self.state(bid, wait_s)
                out[label] = st.get("buildState", "?") + (f": {st['error']}" if st.get("error") else "")
            except Exception as e:  # a variable may not answer block_state
                out[label] = f"?: {e}"
        return out

    def output_value(self, block_id: str) -> Any:
        meta = self.nb.get_block_output_meta(block_id)
        return meta.get("value") if isinstance(meta, dict) else meta

    def pull_value(self, block_id: str) -> Any:
        """`output_value` that never raises: None when nTop has no value (yet)."""
        try:
            v = self.output_value(block_id)
            self.log.append(f"value of {block_id}: {v!r}")
            return v
        except Exception as e:
            self.log.append(f"get_block_output_meta({block_id}) failed: {e}")
            return None

    # nTop 6.3.3's API (2026-10-26) has none of the build/evaluate names and only set_block_visibility,
    # which did not make a lazy Mass Properties build; the probe stays for later API versions.
    NUDGE_METHODS = ("build_block", "build", "rebuild_block", "rebuild", "update_block", "evaluate_block", "evaluate",
                     "set_block_visibility", "set_block_visible", "show_block", "set_visibility")

    def nudge_build(self, block_id: str) -> str | None:
        """Ask nTop to build a lazy block with whichever of the documented-sounding methods exists
        (tried in order, (id) then (id, True)); returns the method that accepted the call."""
        for name in self.NUDGE_METHODS:
            fn = getattr(self.nb, name, None)
            if not callable(fn):
                continue
            for args in ((block_id,), (block_id, True), ()):
                try:
                    fn(*args)
                    self.log.append(f"nudged {block_id} with {name}{args}")
                    return name
                except TypeError:
                    continue
                except Exception as e:
                    self.log.append(f"{name}{args} refused: {e}")
                    break
        self.log.append(f"no build/visibility method accepted {block_id}; methods: "
                        + ", ".join(n for n in dir(self.nb) if not n.startswith("_"))[:1500])
        return None

    def display_only(self, labels: Iterable[str]) -> dict:
        """Show only the blocks with these labels in nTop's viewport and hide the rest of this
        helper's blocks (inputs are left alone). Visibility is cosmetic - a hidden block still
        builds for whatever consumes it. Returns {label: True | False | "<why not>"}; a block
        that cannot be toggled (a variable, say) is logged, never fatal."""
        fn = getattr(self.nb, "set_block_visibility", None)
        if not callable(fn):
            self.log.append("display: this API has no set_block_visibility; the viewport is left as nTop made it")
            return {}
        want = set(labels)
        out: dict[str, Any] = {}
        for label, bid in self.blocks.items():
            if bid in self.moved_inputs:
                continue
            try:
                fn(bid, label in want)
                out[label] = label in want
            except Exception as e:
                out[label] = f"{e}"
                self.log.append(f"display: {label} ({bid}) cannot be toggled: {e}")
        self.log.append(f"display: showing {sorted(k for k, v in out.items() if v is True)}, "
                        f"hid {sum(1 for v in out.values() if v is False)} blocks")
        return out

    @contextmanager
    def paused(self, enabled: bool = True):
        if enabled and hasattr(self.nb, "paused_updates"):
            with self.nb.paused_updates():
                yield
        else:
            yield
