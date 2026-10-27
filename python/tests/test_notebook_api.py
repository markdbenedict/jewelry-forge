import importlib.util
import json
from pathlib import Path

import pytest

from ntopjewel import notebook_api as napi
from ntopjewel.notebook_api import Console, ConsoleError, NotebookHelper
from .fake_notebook import FakeNotebook

REPO = Path(__file__).resolve().parents[2]


def load_recipe(name: str):
    path = REPO / "ntop" / "recipes" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------ helper behaviour
def test_identifier_lookup_exact_then_mask():
    h = NotebookHelper(FakeNotebook())
    assert h.identifier("cylinder<point,point,real>") == "cylinder<point,point,real>"
    assert h.identifier("nope", mask="torus", must=["torus"]) == "torus<point,vector,real,real>"
    # spaces match underscores; the name match beats slice_stack_boolean_subtract; the highest version wins
    # (an unversioned identifier is the 1.0.0 definition, which nTopCL reports as deprecated)
    assert h.identifier(mask="subtract", must=["boolean subtract"]) == "boolean_subtract<blend_enum,real_field,implicit,list<implicit>>[5.44.0]"
    assert h.identifier(must=[["mass_properties", "implicit"]]) == "mass_properties<implicit,real_field,real>[1.1.0]"
    assert napi.identifier_version("offset_implicit<implicit,real_field>") == (1, 0, 0)
    assert napi.identifier_version("implicit_to_mesh<implicit,real,real,bool,bool>[2.5.0]") == (2, 5, 0)
    assert h.identifier(must=[["implicit_to_mesh", "bool,bool"]]) == "implicit_to_mesh<implicit,real,real,bool,bool>[2.5.0]"
    assert h.identifier(mask="export", must=[["export_mesh", "file_path"]]) == "export_mesh<file_path,mesh,unit_length_enum>"
    with pytest.raises(ConsoleError, match="no block identifier"):
        h.identifier("lathe<real>", mask="lathe", must=["lathe"])


def test_identifier_alternatives_skip_scalar_decoys():
    h = NotebookHelper(FakeNotebook())
    # "subtract<real,real>" is shorter; requiring "implicit" keeps it out
    assert h.identifier(mask="subtract", must=[["boolean subtract", "implicit"], ["subtract", "implicit"]]).endswith("[5.44.0]")
    assert h.identifier(mask="offset", must=[["offset_implicit"], ["offset", "implicit"]]) == "offset_implicit<implicit,real_field>"
    with pytest.raises(ConsoleError) as e:
        h.identifier(mask="subtract", must=["boolean subtract", "mesh"])
    msg = str(e.value)
    assert "nearest" in msg and "boolean_subtract<blend_enum" in msg and "subtract<real,real>" in msg


def test_identifier_falls_back_to_masked_queries():
    """list_available_blocks() returning a partial list must not hide blocks that a masked query finds."""
    nb = FakeNotebook(unmasked_limit=3)                 # only sphere, point, vector come back unmasked
    h = NotebookHelper(nb)
    assert len(h.available()) == 3
    ident = h.identifier(mask="subtract", must=[["boolean subtract", "implicit"]])
    assert ident.startswith("boolean_subtract<") and ident in h.available()
    assert h.identifier("torus<point,vector,real,real>") == "torus<point,vector,real,real>"   # exact, after a lookup


def test_input_name_matching_and_wiring():
    nb = FakeNotebook()
    h = NotebookHelper(nb)
    cyl = h.add("Outer", "cylinder<point,point,real>")
    r = h.real_var("Outer Radius", 9.5534, "mm")
    assert h.input_name(cyl, "radius") == "Radius"            # case-insensitive
    assert h.input_name(cyl, "Point 2") == "Point 2"
    h.wire(r, cyl, ["Radius"])
    assert nb.blocks[cyl]["wired"]["Radius"] == ("Outer Radius", "")
    h.set(cyl, ["Point 1"], [0, 0, -10], "mm")
    assert nb.blocks[cyl]["inputs"]["Point 1"] == ([0, 0, -10], "mm")
    with pytest.raises(ConsoleError, match="no input like"):
        h.set(cyl, ["Height"], 4, "mm")                        # the Cylinder has no Height (learned 2026-10-25)
    sub = h.add("Band", mask="subtract", must=["boolean subtract"])
    h.to_list(cyl, sub, ["Subtraction Bodies"])
    assert nb.blocks[sub]["lists"]["Subtraction Bodies"] == [cyl]
    with pytest.raises(ValueError):
        nb.append_to_list(cyl, sub, "Primary Body")           # not a list input


def test_assert_ok_reports_errors():
    nb = FakeNotebook(fail_blocks={"Torus_0"})
    h = NotebookHelper(nb)
    t = h.add("T", mask="torus", must=["torus"])
    with pytest.raises(ConsoleError, match="forced failure"):
        h.assert_ok(t, wait_s=0)


# ------------------------------------------------------------------ the band build script
def test_band_profile_builds_on_fake_notebook(tmp_path):
    mod = load_recipe("band_profile")
    nb = FakeNotebook()
    res = mod.build(nb, {"save_to": str(tmp_path / "rb.ntop"), "recipe_to": str(tmp_path / "rb.json"),
                         "test_output": str(tmp_path / "t.stl")})
    # inputs declared in catalog order, output is the Volume variable
    assert nb.inputs == mod.INPUT_ORDER
    assert nb.output == "Volume"
    assert nb.fresh == 1 and nb.saved == [str(tmp_path / "rb.ntop")] and nb.recipes == [str(tmp_path / "rb.json")]
    # wiring: both cylinders fed by variables, band = outer minus bore, one intersect with both tori, two offsets
    b = nb.blocks
    outer, bore = res["blocks"]["Outer"], res["blocks"]["Bore"]
    assert b[outer]["wired"]["Radius"][0] == "Outer Radius" and b[bore]["wired"]["Radius"][0] == "Bore Radius"
    assert b[outer]["wired"]["Point 2"][0] == res["blocks"]["P Top"]
    band = res["blocks"]["Band"]
    assert b[band]["wired"]["Primary Body"][0] == outer and b[band]["lists"]["Subtraction Bodies"] == [bore]
    shaped = res["blocks"]["Shaped"]
    assert b[shaped]["lists"]["Bodies"] == [band, res["blocks"]["Dome Torus"], res["blocks"]["Comfort Torus"]]
    assert "Domed" not in res["blocks"]
    for t in ("Dome Torus", "Comfort Torus"):
        assert b[res["blocks"][t]]["inputs"]["Axis"] == ([0.0, 0.0, 1.0], "") and b[res["blocks"][t]]["wired"]["Torus Radius"]
    assert b[res["blocks"]["Shrunk"]]["wired"]["Body"][0] == shaped
    prof = res["blocks"]["Band Profile"]
    assert b[prof]["wired"]["Distance"][0] == "Edge Round"
    assert b[res["blocks"]["Shrunk"]]["wired"]["Distance"][0] == "Edge Round Inward"
    # tail: mass properties -> Volume variable, mesh tolerance from the input, export file from Output Path
    assert nb.variables["Volume"]["wired"] == (res["blocks"]["Mass Properties"], "volume")   # nTop names it in lower case
    assert b[res["blocks"]["Mesh"]]["wired"]["Tolerance"][0] == "Mesh Tolerance"
    # the final body feeds two blocks, so it goes through a variable (nTop's rule)
    assert nb.variables["Band Body"]["wraps"] == prof
    assert b[res["blocks"]["Mesh"]]["wired"]["Body"][0] == "Band Body" == b[res["blocks"]["Mass Properties"]]["wired"]["Body"][0]
    assert b[res["blocks"]["Export Mesh"]]["wired"]["Path"][0] == "Output Path"
    # file_path variables cannot be given a value through the API (2026-10-26), so the path is a text variable
    assert nb.variables["Output Path"]["funcId"] == "core.var<text>" and nb.variables["Output Path"]["value"] == str(tmp_path / "t.stl")
    assert any("cannot be set yet" in ln for ln in res["log"])
    assert res["warnings"] == [] and nb.variables["Volume"]["wired"][0] in nb.built
    assert res["volume"] == pytest.approx(287.4)
    assert set(res["states"]) == set(res["blocks"])
    assert all(v == ("input" if k in mod.INPUT_ORDER else "e_OK") for k, v in res["states"].items())
    ids = res["identifiers"]
    assert ids["Band"] == "boolean_subtract<blend_enum,real_field,implicit,list<implicit>>[5.44.0]"
    assert ids["Shaped"] == "boolean_intersect<blend_enum,real_field,list<implicit>>[5.44.0]"
    assert ids["Shrunk"] == "offset_implicit<implicit,real_field>"
    assert ids["Mass Properties"] == "mass_properties<implicit,real_field,real>[1.1.0]"
    # what nTopCL complained about on 2026-10-27: an unset leftover Path_0 and an unset Density
    assert nb.lint() == []
    assert "Path_0" not in nb.variables and any("removed Path_0" in ln for ln in res["log"])
    # Density is a real_field: it cannot be set, only fed by a variable (a core.var<real> in kg/m^3)
    assert b[res["blocks"]["Mass Properties"]]["wired"]["Density"] == ("Density", "")
    assert nb.variables["Density"]["value"] == 1000.0 and nb.variables["Density"]["units"] == "kg/m^3"
    assert "Density" not in nb.inputs                                                  # a body variable, not a notebook input
    # the Output is a typed real variable (nTopCL -t needs the type before anything is built)
    assert nb.variables["Volume"]["funcId"] == "core.var<real>" and nb.variables["Volume"]["units"] == "mm^3"
    assert ids["Mesh"] == "implicit_to_mesh<implicit,real,real,bool,bool>[2.5.0]"
    assert ids["Export Mesh"] == "export_mesh<file_path,mesh,unit_length_enum>"
    assert ids["Output Path"] == "core.var<text>"
    # the catalog and the script agree on the input names
    from ntopjewel import catalog
    assert list(catalog.load("ring_band_profile").inputs) == mod.INPUT_ORDER


def test_band_profile_path_variable_needs_a_text_variable(tmp_path):
    """Without core.var<text> (and file_path variables unsettable) the script stops with a clear reason."""
    mod = load_recipe("band_profile")
    avail = [i for i in FakeNotebook().available_ids if i != "core.var<text>"]
    nb = FakeNotebook(available=avail)
    with pytest.raises(ConsoleError, match="no variable type could hold the Output Path input") as e:
        mod.build(nb, {"save_to": str(tmp_path / "rb.ntop"), "recipe_to": str(tmp_path / "rb.json"),
                       "test_output": str(tmp_path / "t.stl")})
    assert "cannot be set yet" in str(e.value) and "core.var<text>: not available" in str(e.value)


def test_band_profile_tolerates_lazy_mass_properties(tmp_path):
    """Mass Properties that never builds in the GUI session is a warning, not a failure: the notebook is
    still saved with Volume as its Output (nTopCL evaluates it). With a build method, the helper uses it."""
    mod = load_recipe("band_profile")
    nb = FakeNotebook(lazy_mass="never")
    res = mod.build(nb, {"save_to": str(tmp_path / "rb.ntop"), "recipe_to": str(tmp_path / "rb.json"),
                         "test_output": str(tmp_path / "t.stl"), "wait_s": 1})
    assert res["warnings"] and "lazy" in res["warnings"][0] and res["volume"] is None
    assert nb.saved == [str(tmp_path / "rb.ntop")] and nb.output == "Volume"
    assert res["states"]["Mass Properties"] == "e_DIRTY" and res["states"]["Export Mesh"] == "e_OK"
    assert any("no build/visibility method" in ln for ln in res["log"])
    nb = FakeNotebook(lazy_mass="method")
    res = mod.build(nb, {"save_to": str(tmp_path / "rb2.ntop"), "recipe_to": str(tmp_path / "rb2.json"),
                         "test_output": str(tmp_path / "t2.stl"), "wait_s": 1})
    assert res["warnings"] == [] and res["volume"] == pytest.approx(287.4)
    assert any("nudged" in ln and "build_block" in ln for ln in res["log"])


def test_band_profile_raises_on_failed_block(tmp_path):
    mod = load_recipe("band_profile")
    nb = FakeNotebook(fail_blocks={"Implicit Body_1"})     # the intersect (Shaped)
    with pytest.raises(ConsoleError, match="failed to build") as e:
        mod.build(nb, {"save_to": str(tmp_path / "rb.ntop"), "recipe_to": str(tmp_path / "rb.json"),
                       "test_output": str(tmp_path / "t.stl")})
    msg = str(e.value)
    assert "diagnostics" in msg and "forced failure" in msg and "boolean_intersect" in msg   # log + states travel with the error


def test_discover_script_reports_identifiers_and_inputs():
    mod = load_recipe("discover")
    nb = FakeNotebook(unmasked_limit=4)
    res = mod.build(nb, {})
    text = "\n".join(res["summary"])
    assert "PARTIAL" in text                                  # the fake hides most blocks from the unmasked call
    assert "boolean_subtract<blend_enum" in text and "Primary Body:implicit" in text
    assert "Subtraction Bodies:list<implicit>" in text
    assert "add_real_variable" in text and "core.var" in text
    assert res["probed"]["torus<point,vector,real,real>"]["inputs"][0][0] == "Center"
    assert nb.saved == [] and nb.fresh == 1                   # scratch only, never saved


# ------------------------------------------------------------------ the SSH console wrapper
def test_console_run_script_round_trip(tmp_path):
    """The transport is faked: it 'runs' the driver with a fake notebook and prints the sentinel."""
    script = REPO / "ntop" / "recipes" / "band_profile.py"

    def transport(line: str, timeout: float) -> str:
        assert line.startswith('exec(open(r"') and line.endswith('").read())')
        driver = Path(line[len('exec(open(r"'):-len('").read())')])
        ns = {"notebook": FakeNotebook()}
        exec(driver.read_text(encoding="utf-8"), ns)         # same thing nTop's console does
        return ">>> " + line + "\n" + napi.DONE + "\n"

    c = Console(key=tmp_path / "nokey", transport=transport)
    res = c.run_script(script, {"save_to": str(tmp_path / "x.ntop"), "recipe_to": str(tmp_path / "x.json"),
                                "test_output": str(tmp_path / "x.stl")},
                       work_dir=tmp_path / "api", python_path=REPO / "python")
    assert res["status"] == "ok" and res["result"]["volume"] == pytest.approx(287.4)
    assert (tmp_path / "api" / "band_profile.result.json").exists()


def test_console_reports_script_failure(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("def build(notebook, params):\n    raise RuntimeError('boom')\n", encoding="utf-8")

    def transport(line, timeout):
        driver = Path(line[len('exec(open(r"'):-len('").read())')])
        ns = {"notebook": FakeNotebook()}
        exec(driver.read_text(encoding="utf-8"), ns)
        return napi.FAIL + "\n"

    c = Console(key=tmp_path / "nokey", transport=transport)
    with pytest.raises(ConsoleError, match="boom"):
        c.run_script(bad, {}, work_dir=tmp_path / "api")
    res = json.loads((tmp_path / "api" / "bad.result.json").read_text(encoding="utf-8"))
    assert res["error"] == "RuntimeError: boom"            # the console also prints this line before the sentinel


def test_console_missing_key_message(tmp_path):
    c = Console(key=tmp_path / "missing")
    with pytest.raises(ConsoleError, match="SSH key not found"):
        c.check()


FAKE_SSH = r'''
"""Stands in for `ssh -tt ... localhost`: echoes the line like nTop's console, then answers."""
import sys, time
args = sys.argv[1:]
mode = "hang" if "hang" in args[-1] else "ok"
sys.stdout.write(">>> ")
sys.stdout.flush()
line = sys.stdin.readline()
sys.stdout.write(line)                      # the console echoes what it received (sentinel split)
sys.stdout.flush()
if mode == "hang":
    time.sleep(30)
time.sleep(0.1)
sys.stdout.write("[{'name': 'Section 1', 'id': 'section_0'}]\n")
sys.stdout.write("__NTOPJEWEL_" + "DONE__" + "\n")
sys.stdout.flush()
sys.stdin.readline()                        # waits for the Ctrl-C the client sends
'''


@pytest.fixture
def fake_ssh(tmp_path):
    import os, stat, sys
    script = tmp_path / "fake_ssh.py"
    script.write_text(FAKE_SSH, encoding="utf-8")
    if os.name == "nt":  # pragma: no cover
        launcher = tmp_path / "ssh.cmd"
        launcher.write_text(f'@"{sys.executable}" "{script}" %*\n')
    else:
        launcher = tmp_path / "ssh"
        launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n')
        launcher.chmod(launcher.stat().st_mode | stat.S_IEXEC)
    key = tmp_path / "id_ntopcli"
    key.write_text("fake key", encoding="utf-8")
    return launcher, key


def test_ssh_transport_reads_past_the_echo(fake_ssh):
    launcher, key = fake_ssh
    out = Console(key=key, ssh=str(launcher), host="localhost").check(timeout=10)
    assert "Section 1" in out and napi.DONE in out            # the echoed line did not end the read early
    assert out.index("Section 1") > out.index('"DONE__"')


def test_ssh_transport_times_out(fake_ssh):
    launcher, key = fake_ssh
    with pytest.raises(ConsoleError, match="timed out"):
        Console(key=key, ssh=str(launcher), host="hang").check(timeout=1)


# ------------------------------------------------------------------ the CLI, no SSH needed
def test_cli_api_dry_run_then_collect(tmp_path, capsys):
    """`api build --dry-run` writes the driver for pasting into the GUI console; `api collect` reads the result."""
    from ntopjewel import cli
    rc = cli.main(["api", "--out", str(tmp_path), "build", "band_profile", "--dry-run", "--scratch",
                   "--param", f"test_output={tmp_path / 't.stl'}"])
    assert rc == 0
    out = capsys.readouterr().out
    assert 'exec(open(r"' in out and "band_profile.driver.py" in out and "ssh" in out
    driver = tmp_path / "band_profile.driver.py"
    params = json.loads((tmp_path / "band_profile.params.json").read_text(encoding="utf-8"))
    assert params["save_to"] == str(tmp_path / "band_profile.ntop") and params["test_output"] == str(tmp_path / "t.stl")
    # nothing to collect yet
    assert cli.main(["api", "--out", str(tmp_path), "collect", "band_profile"]) == 2
    capsys.readouterr()
    # "paste" the driver into a console that has a (fake) notebook
    ns = {"notebook": FakeNotebook()}
    exec(driver.read_text(encoding="utf-8"), ns)
    assert cli.main(["api", "--out", str(tmp_path), "collect", "band_profile"]) == 0
    out = capsys.readouterr().out
    assert "all e_OK" in out and "287.4" in out and "boolean_subtract<" in out


def test_cli_api_unknown_recipe(tmp_path):
    from ntopjewel import cli
    with pytest.raises(SystemExit, match="no build script"):
        cli.main(["api", "--out", str(tmp_path), "build", "no_such_thing", "--dry-run"])
