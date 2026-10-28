#!/usr/bin/env python3
"""A stand-in for `ntopcl` that builds what the notebook would build.

It mimics the real executable's flags (-v -j -o -t --version), its 6.3.3 log format (per-block
timings, `JSON file has no inputs`, `nTop successfully built.`) and its output JSON (SI values
with dimension exponents). For the band notebooks it does what nTop does with the same
inputs - the designed cross-section (outer/bore cylinders ∩ dome torus ∩ comfort torus,
opened by the edge round) revolved about Z - and for `ring_features` it unions the bead
spheres, subtracts the groove torus and subtracts the cylindrically remapped engraving mesh
(trimesh + manifold3d), so the mesh gate, the design-volume cross-check and the engraving
pocket check all face the geometry they would face from nTop. Nothing here reads the Python
specs; the section is rebuilt from the notebook inputs alone, as nTop would.

Knobs (environment variables) let a test make the fake misbehave the way a wrong notebook
would, so the rejections are tested rather than assumed:

  FAKE_NTOPCL_SHAPE   design (default) | noseat | nobeads | noengrave (solitaire) | annulus : a flat rectangular section instead of the
                      designed one (what a notebook that ignores the tori produces)
  FAKE_NTOPCL_EXPORT  1 (default) | 0 : do not write the STL (an unwired Export block)
  FAKE_NTOPCL_VOLUME  mesh (default) | none : report no Volume output
  FAKE_NTOPCL_SLEEP   seconds to sleep before writing (default 0)
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))          # python/: so ntopjewel imports when run as a script

STAMP = time.strftime("%H:%M:%S")

BAND_INPUT_NAMES = ["Outer Radius", "Bore Radius", "Z Top", "Z Bottom", "Dome Ring Radius", "Dome Tube Radius",
                    "Comfort Ring Radius", "Comfort Tube Radius", "Edge Round", "Edge Round Inward", "Mesh Tolerance"]


def log(level: str, msg: str) -> None:
    print(f"{STAMP} [{level}]: {msg}")


def fail(msg: str) -> None:
    log("E", msg)
    log("I", "nTop exited with errors.")
    log("I", "Logout successful")
    sys.exit(0)                                   # nTopCL can exit 0 after a failed block (seen 2026-10-25)


# ----------------------------------------------------------------------------- templates
def write_templates(nb: Path) -> None:
    inputs = []
    if "head" in nb.name or "solitaire" in nb.name:
        import yaml
        cat_dir = HERE.parents[2] / "catalog"
        name = nb.stem if (cat_dir / f"{nb.stem}.yaml").exists() else ("solitaire" if "solitaire" in nb.name else "prong_head_harness")
        cat = yaml.safe_load((cat_dir / f"{name}.yaml").read_text())
        for name, e in cat["inputs"].items():
            t = {"scalar": "real", "integer": "integer", "text": "text"}[e["type"]]
            inputs.append({"name": name, "type": t, "value": 0 if t != "text" else "", **({"units": e["units"]} if "units" in e else {})})
    elif "seat" in nb.name:
        inputs = [{"name": "Seat Path", "type": "text", "value": ""},
                  {"name": "Clearance", "type": "real", "value": 0, "units": "mm"},
                  {"name": "Mesh Tolerance", "type": "real", "value": 0, "units": "mm"},
                  {"name": "Output Path", "type": "text", "value": ""}]
    elif "profile" in nb.name or "features" in nb.name:
        inputs = [{"name": n, "type": "real", "value": 0, "units": "mm"} for n in BAND_INPUT_NAMES]
        if "features" in nb.name:
            inputs += [{"name": n, "type": "real", "value": 0, "units": "mm"} for n in
                       ("Bead Radius", "Bead Ring Radius", "Bead Z", "Bead Z Minus")]
            inputs.append({"name": "Bead Spacing", "type": "real", "value": 0, "units": "deg"})
            inputs.append({"name": "Bead Count", "type": "integer", "value": 1})
            inputs += [{"name": n, "type": "real", "value": 0, "units": "mm"} for n in
                       ("Groove Ring Radius", "Groove Tube Radius", "Groove Z")]
            inputs.append({"name": "Engraving Path", "type": "text", "value": ""})
            inputs.append({"name": "Engraving Wrap Length", "type": "real", "value": 0, "units": "mm"})
        inputs.append({"name": "Output Path", "type": "text", "value": ""})
    elif "band" in nb.name:
        # nTop 6.3.3 spells these `real` and `text` in its own template (seen 2026-10-25)
        inputs = [{"name": "Outer Radius", "type": "real", "value": 0, "units": "mm"},
                  {"name": "Bore Radius", "type": "real", "value": 0, "units": "mm"},
                  {"name": "Width", "type": "real", "value": 0, "units": "mm"},
                  {"name": "Mesh Tolerance", "type": "real", "value": 0, "units": "mm"},
                  {"name": "Output Path", "type": "text", "value": ""}]
    Path("input_template.json").write_text(json.dumps({"title": nb.stem, "description": "", "inputs": inputs}, indent=4))
    if "unbuilt" in nb.name:
        # an API-authored notebook whose Output was never built in the GUI (seen 2026-10-27)
        print(f"{STAMP} [E]: Error generating output template : Output of function not built")
        sys.exit(1)
    Path("output_template.json").write_text(json.dumps([{"name": "Volume", "type": "scalar", "components": [], "value": 0}], indent=4))


# ----------------------------------------------------------------------------- geometry
from ntopjewel.geom import band_mesh, offset_convex, remap_cylindrical, revolve_section, section_polygon  # noqa: E402,F401


def build_mesh(v: dict, shape: str):
    """The notebook's body from its inputs: band, then (ring_features) beads, groove, engraving."""
    import numpy as np
    import trimesh
    body = revolve_section(section_polygon(v, shape))
    if "Bead Count" not in v:
        return body
    # milgrain: two spheres unioned, polar-arrayed about Z, unioned with the band
    rho, rr = float(v["Bead Radius"]), float(v["Bead Ring Radius"])
    count = int(v["Bead Count"])
    spacing = math.radians(float(v["Bead Spacing"]))
    spheres = []
    for k in range(count):
        a = k * spacing
        for zc in (float(v["Bead Z"]), float(v["Bead Z Minus"])):
            s = trimesh.creation.icosphere(subdivisions=2, radius=rho)
            s.apply_translation((rr * math.cos(a), rr * math.sin(a), zc))
            spheres.append(s)
    body = trimesh.boolean.union([body, *spheres], engine="manifold")
    # groove: a torus subtracted
    torus = trimesh.creation.torus(float(v["Groove Ring Radius"]), float(v["Groove Tube Radius"]),
                                   major_sections=240, minor_sections=32)
    torus.apply_translation((0.0, 0.0, float(v["Groove Z"])))
    body = trimesh.boolean.difference([body, torus], engine="manifold")
    # engraving: import the mesh, wrap it round the ring, subtract it
    engraving = trimesh.load(str(v["Engraving Path"]), force="mesh")
    wrapped = remap_cylindrical(engraving, float(v["Engraving Wrap Length"]))
    body = trimesh.boolean.difference([body, wrapped], engine="manifold")
    body.merge_vertices()
    return body


def offset_convex(mesh, c: float):
    """Offset Body of a convex body by c > 0: the hull of the body's vertices each grown into a
    small sphere (exact up to the sphere's facetting)."""
    import numpy as np
    import trimesh
    if c <= 0:
        return mesh
    ball = trimesh.creation.icosphere(subdivisions=3, radius=c).vertices
    pts = (mesh.vertices[:, None, :] + ball[None, :, :]).reshape(-1, 3)
    return trimesh.convex.convex_hull(pts)


# ----------------------------------------------------------------------------- main
def main(argv: list[str]) -> int:
    if argv == ["--version"]:
        print("6.3.3")
        return 0
    if argv and argv[0] == "-t":
        write_templates(Path(argv[1]))
        return 0

    in_json = out_json = None
    i = 0
    while i < len(argv):
        if argv[i] == "-j":
            in_json = Path(argv[i + 1]); i += 2
        elif argv[i] == "-o":
            out_json = Path(argv[i + 1]); i += 2
        elif argv[i] == "-v":
            i += 2
        else:
            i += 1
    nb = Path(argv[-1])
    log("I", "Login successful")
    log("I", "Notebook started")
    values: dict = {}
    if in_json is not None:
        doc = json.loads(in_json.read_text())
        if not doc.get("inputs"):
            fail("JSON file has no inputs")
        values = {e["name"]: e.get("value", e.get("values")) for e in doc["inputs"]}
    if "fail" in nb.name:
        fail("Boolean Subtract_0: input Bodies is not connected")
    sleep = float(os.environ.get("FAKE_NTOPCL_SLEEP", "0") or 0)
    if sleep:
        time.sleep(sleep)

    outputs: list[dict] = []
    if "solitaire" in nb.name:
        import trimesh
        from ntopjewel import solitaire
        if not Path(values["Seat Path"]).exists():
            fail("Seat Mesh: file not found")
        envelope = trimesh.load(str(values["Seat Path"]), force="mesh")
        shape = os.environ.get("FAKE_NTOPCL_SHAPE", "design")
        mesh = solitaire.ring_mesh(values, envelope, cut_seat=shape != "noseat", beads=shape != "nobeads",
                                   engrave=shape != "noengrave")
        if os.environ.get("FAKE_NTOPCL_EXPORT", "1") != "0":
            mesh.export(values["Output Path"])
        for name in ("Band", "Stone Seat", "Prong Head", "Placed Head", "Shoulders", "Ring", "Mesh", "Export Mesh"):
            log("I", f"{name} complete 1ms")
        if os.environ.get("FAKE_NTOPCL_VOLUME", "mesh") != "none":
            outputs = [{"name": "Volume", "type": "real", "components": [],
                        "value": {"isFinite": True, "units": {"length": 3}, "val": float(mesh.volume) * 1e-9}}]
    elif "outline_head" in nb.name:
        import trimesh
        from ntopjewel import heads
        for key in ("Seat Path", "Prongs Path"):
            if not Path(values[key]).exists():
                fail(f"{key}: file not found")
        envelope = trimesh.load(str(values["Seat Path"]), force="mesh")
        prongs = trimesh.load(str(values["Prongs Path"]), force="mesh")
        mesh = heads.outline_head_mesh(values, envelope, prongs, cut_seat=os.environ.get("FAKE_NTOPCL_SHAPE", "design") != "noseat")
        if os.environ.get("FAKE_NTOPCL_EXPORT", "1") != "0":
            mesh.export(values["Output Path"])
        for name in ("Prongs", "Upper Rail", "Lower Rail", "Basket", "Seated", "Mesh", "Export Mesh", "Volume Integral"):
            log("I", f"{name} complete 1ms")
        if os.environ.get("FAKE_NTOPCL_VOLUME", "mesh") != "none":
            outputs = [{"name": "Volume", "type": "real", "components": [],
                        "value": {"isFinite": True, "units": {"length": 3}, "val": float(mesh.volume) * 1e-9}}]
    elif "head" in nb.name:
        import trimesh
        from ntopjewel import heads
        if not Path(values["Seat Path"]).exists():
            fail("Seat Mesh: file not found")
        envelope = trimesh.load(str(values["Seat Path"]), force="mesh")
        mesh = heads.head_mesh(values, envelope, cut_seat=os.environ.get("FAKE_NTOPCL_SHAPE", "design") != "noseat")
        if os.environ.get("FAKE_NTOPCL_EXPORT", "1") != "0":
            mesh.export(values["Output Path"])
        for name in ("Prong Rod", "Prongs", "Basket", "Seat", "Seated", "Mesh", "Export Mesh", "Volume Integral"):
            log("I", f"{name} complete 1ms")
        if os.environ.get("FAKE_NTOPCL_VOLUME", "mesh") != "none":
            outputs = [{"name": "Volume", "type": "real", "components": [],
                        "value": {"isFinite": True, "units": {"length": 3}, "val": float(mesh.volume) * 1e-9}}]
    elif "seat" in nb.name:
        import trimesh
        if not Path(values["Seat Path"]).exists():
            fail("Seat Mesh: file not found")
        mesh = offset_convex(trimesh.load(str(values["Seat Path"]), force="mesh"), float(values["Clearance"]))
        if os.environ.get("FAKE_NTOPCL_EXPORT", "1") != "0":
            mesh.export(values["Output Path"])
        for name in ("Seat Mesh", "Seat Body", "Stone Seat", "Mesh", "Export Mesh", "Volume Integral"):
            log("I", f"{name} complete 1ms")
        if os.environ.get("FAKE_NTOPCL_VOLUME", "mesh") != "none":
            outputs = [{"name": "Volume", "type": "real", "components": [],
                        "value": {"isFinite": True, "units": {"length": 3}, "val": float(mesh.volume) * 1e-9}}]
    elif "band" in nb.name or "features" in nb.name:
        if "Bead Count" in values and not Path(values["Engraving Path"]).exists():
            fail("Engraving Mesh: file not found")
        shape = os.environ.get("FAKE_NTOPCL_SHAPE", "design")
        mesh = build_mesh(values, shape)
        if os.environ.get("FAKE_NTOPCL_EXPORT", "1") != "0":
            mesh.export(values["Output Path"])
        for name in ("Outer Cylinder", "Bore", "Band", "Mesh from Implicit Body", "Export Mesh", "Volume Integral"):
            log("I", f"{name} complete 1ms")
        if os.environ.get("FAKE_NTOPCL_VOLUME", "mesh") != "none":
            outputs = [{"name": "Volume", "type": "real", "components": [],
                        "value": {"isFinite": True, "units": {"length": 3}, "val": float(mesh.volume) * 1e-9}}]
    else:
        for name in ("Sphere_0", "Implicit Body_5"):
            log("I", f"{name} complete 0ms")
        outputs = [{"name": "Spherecube Shell", "type": "implicit", "components": [], "value": {"base64": "AAAA"}}]
    if out_json is not None:
        out_json.write_text(json.dumps(outputs, indent=4))
    log("I", "nTop successfully built.")
    log("I", "Logout successful")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
