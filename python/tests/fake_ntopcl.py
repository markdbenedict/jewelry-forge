#!/usr/bin/env python3
"""A stand-in for `ntopcl` that builds what the notebook would build.

It mimics the real executable's flags (-v -j -o -t --version), its 6.3.3 log format (per-block
timings, `JSON file has no inputs`, `nTop successfully built.`) and its output JSON (SI values
with dimension exponents). For the band notebooks it does what nTop does with the same
inputs - the designed cross-section (outer/bore cylinders ∩ dome torus ∩ comfort torus,
opened by the edge round) revolved about Z - and for `ring_features` it unions the bead
spheres, subtracts the groove torus and subtracts the cylindrically remapped engraving mesh
(trimesh + manifold3d), so the mesh gate, the design-volume cross-check and the engraving
pocket check all face the geometry they would face from nTop. The heads and the solitaire are
built by the same builders the independent model uses, but with tests/pseudo_blend.py's blended
booleans, which put the tables' blend volume into the mesh along every junction the notebook
blends. Nothing here reads the Python specs; the section is rebuilt from the notebook inputs
alone, as nTop would.

Knobs (environment variables) let a test make the fake misbehave the way a wrong notebook
would, so the rejections are tested rather than assumed:

  FAKE_NTOPCL_SHAPE   design (default) | noseat | nobeads | noengrave (solitaire, multistone) | plainshank (solitaire: the bar's head section
                      all round) | nocut / norelief (artwork, on a band or under a head: the channels never cut, the
                      relief lost) | noknot (the shoulder knots' layers lost) | noblend (the blend radii ignored:
                      sharp junctions) | noprongs (outline_head: the prongs mesh lost - claws, a pearl's post) | noside / nohood / fullbezel (partial_bezel_head: a wall never mirrored, the hoods lost, the mask's walls lost) | nowrap (ring_shank: the bar exported unwrapped) | annulus : a flat
                      rectangular section instead of the designed one (what a notebook that ignores the tori produces)
                      | nolattice / closed / thin (ring_lattice: the zone emptied and no lattice built; the zone's outer face left
                      as a skin over the lattice, every void a pocket; the sheets 0.6 x the Wall asked)
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
    print(f"{STAMP} [{level}]: {msg}", flush=True)       # as it goes: a killed run leaves its lines


def fail(msg: str) -> None:
    log("E", msg)
    log("I", "nTop exited with errors.")
    log("I", "Logout successful")
    sys.exit(0)                                   # nTopCL can exit 0 after a failed block (seen 2026-10-25)


# ----------------------------------------------------------------------------- templates
def write_templates(nb: Path) -> None:
    inputs = []
    if ("head" in nb.name or "solitaire" in nb.name or "shank" in nb.name or "pave" in nb.name or "multistone" in nb.name
            or "artwork" in nb.name or "texture" in nb.name
            or any(k in nb.name for k in ("voronoi", "frost", "pitted", "cellular", "ribbed", "lattice"))):
        import yaml
        cat_dir = HERE.parents[2] / "catalog"
        name = nb.stem if (cat_dir / f"{nb.stem}.yaml").exists() else ("solitaire" if "solitaire" in nb.name else
                                                                        "ring_shank" if "shank" in nb.name else "prong_head_harness")
        cat = yaml.safe_load((cat_dir / f"{name}.yaml").read_text())
        for name, e in cat["inputs"].items():
            t = {"scalar": "real", "integer": "integer", "text": "text", "enum": "enum"}[e["type"]]
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
    from ntopjewel import tables
    body = revolve_section(section_polygon(v, shape, tables.opening_chamfer_mm(float(v.get("Mesh Tolerance", 0.1)))))
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


def cut_strikes(mesh, values: dict, shape: str):
    """The Strikes section (nj.add_strikes): mesh less a sphere at every centre Import Points reads (x,y,z, in the
    unit Strikes Units names: 1 = mm, 2 = cm, measured by points_probe). "nostrikes": never cut; "light": a hammer
    struck 3 % softer."""
    import numpy as np
    import trimesh
    from ntopjewel.shank import MIN_EDGE_MM, drop_specks
    from ntopjewel import geom as _geom
    if not Path(values["Strikes Path"]).exists():
        fail("Strike Centres: file not found")
    if values.get("Strikes Units") is None:
        fail('Strike Centres: Input "Units" is incomplete')
    if shape == "nostrikes":
        return mesh
    scale = {1: 1.0, 2: 10.0}.get(int(values["Strikes Units"]), 25.4)
    centres = np.atleast_2d(np.loadtxt(values["Strikes Path"], delimiter=",")) * scale
    radius = float(values["Strike Radius"]) * (0.97 if shape == "light" else 1.0)
    unit = trimesh.creation.icosphere(subdivisions=4, radius=radius)
    near = [c for c in centres if np.linalg.norm(c) < 200.0]               # a far point (no hammering) cuts nothing
    if not near:
        return mesh
    out = trimesh.boolean.difference([mesh] + [unit.copy().apply_translation(c) for c in near], engine="manifold")
    return _geom.collapse_short_edges(drop_specks(out), MIN_EDGE_MM)


def voronoi_grooves(mesh, values: dict, shape: str):
    """ring_voronoi.ntop's Voronoi + Mask sections, stood in for: a 2-D voronoi net of seeded random points on the outer
    face (arc, z), periodic round the ring, its edges grooved by half-round cutters (capsules of radius Groove / 2 lying
    on the dome), kept inside the zone (Zone Z Bottom .. Zone Z Top). nTop's are 3-D cells with their own points; the
    gate's envelope does not care which. "notexture": the plain band; "unmasked": the grooves run over the rims and the
    side faces (the mask did not hold); "deep": grooves 1.6 x as deep."""
    import numpy as np
    import trimesh
    from scipy.spatial import Voronoi
    from ntopjewel.shank import drop_specks
    if shape == "notexture":
        return mesh
    R = float(values["Outer Radius"])
    rd, td = float(values["Dome Ring Radius"]), float(values["Dome Tube Radius"])
    zt, zb = float(values["Zone Z Top"]), float(values["Zone Z Bottom"])
    half_w = float(values["Z Top"])
    radius = float(values["Groove"]) / 2 * (1.6 if shape == "deep" else 1.0)
    if shape == "unmasked":
        z_lo, z_hi = -half_w - 0.3, half_w + 0.3
    else:
        z_lo, z_hi = zb + radius, zt - radius                      # no cutter passes the zone's edge (nTop cuts them there)
    n = max(8, int(values["Cells"]) // 4)                          # about a quarter of the 3-D cells show on the face
    rng = np.random.default_rng(int(values["Cells"]) + int(values["Iterations"]))
    circ = 2 * np.pi * R
    pts = rng.uniform([0.0, z_lo - 1.0], [circ, z_hi + 1.0], (n, 2))
    vor = Voronoi(np.concatenate([pts + [k * circ, 0.0] for k in (-1, 0, 1)]))

    def rho(z):
        return rd + np.sqrt(np.maximum(td * td - z * z, 0.0)) if td > 0 else R

    def p3(a, z):
        return np.array([rho(z) * np.cos(a / R), rho(z) * np.sin(a / R), z])
    cutters = []
    for rv in vor.ridge_vertices:
        if -1 in rv:
            continue
        a, b = vor.vertices[rv[0]], vor.vertices[rv[1]]
        if not (0.0 <= (a[0] + b[0]) / 2 < circ):
            continue
        # clip to the z range
        ta, tb = 0.0, 1.0
        dz = b[1] - a[1]
        for lim, side in ((z_lo, 1), (z_hi, -1)):
            if abs(dz) < 1e-12:
                if side * (a[1] - lim) < 0:
                    ta, tb = 1.0, 0.0
                continue
            tcross = (lim - a[1]) / dz
            if side * dz > 0:
                ta = max(ta, tcross)
            else:
                tb = min(tb, tcross)
        if tb <= ta:
            continue
        a2, b2 = a + ta * (b - a), a + tb * (b - a)
        length = float(np.hypot(*(b2 - a2)))
        pieces = max(1, int(np.ceil(length / 0.4)))
        for i in range(pieces):
            s0, s1 = a2 + (b2 - a2) * i / pieces, a2 + (b2 - a2) * (i + 1) / pieces
            q0, q1 = p3(*s0), p3(*s1)
            seg = q1 - q0
            h = float(np.linalg.norm(seg))
            cap = trimesh.creation.capsule(height=h, radius=radius, count=(8, 8))   # centred on the origin, along Z
            T = trimesh.geometry.align_vectors([0, 0, 1], seg / h) if h > 1e-9 else np.eye(4)
            cap.apply_transform(T)
            cap.apply_translation((q0 + q1) / 2)
            cutters.append(cap)
    if not cutters:
        return mesh
    out = drop_specks(trimesh.boolean.difference([mesh] + cutters, engine="manifold"))
    # as the STL will hold it: float32 vertices, the sub-micron edges the capsules' junctions leave merged away
    out = trimesh.Trimesh(np.asarray(out.vertices).astype(np.float32).astype(np.float64), out.faces, process=False)
    out.merge_vertices()
    out.update_faces(out.nondegenerate_faces())
    out.update_faces(out.unique_faces())
    return out


def displace_texture(mesh, values: dict, kind: str, shape: str):
    """ring_frost / ring_pitted / ring_cellular / ring_ribbed stood in for: the band's vertices inside the zone moved
    along the radial direction by a seeded field - frost: a smooth noise both ways (±Amplitude); pitted: the same cut
    in only; cellular: a Worley F1 (dimples, 3.4 x Factor x Grain deep as nTop's measured); ribbed: a triangle wave of z
    (the troughs Erosion deep, the peaks on the design). nTop's noises are its own; the gate's envelope does not care
    which. "notexture": the plain band; "unmasked": every vertex moved, the bore and rims too; "deep": 1.6 x."""
    import numpy as np
    import trimesh
    if shape == "notexture":
        return mesh
    v = np.array(mesh.vertices, float)
    r = np.hypot(v[:, 0], v[:, 1]); z = v[:, 2]; th = np.arctan2(v[:, 1], v[:, 0])
    R = float(values["Outer Radius"])
    arc = (th % (2 * np.pi)) * R
    circ = 2 * np.pi * R
    zt, zb, r_in = float(values["Zone Z Top"]), float(values["Zone Z Bottom"]), float(values["Zone Inner Radius"])
    zone = np.ones(len(v), bool) if shape == "unmasked" else ((z <= zt) & (z >= zb) & (r >= r_in))
    deep = 1.6 if shape == "deep" else 1.0
    if kind in ("frost", "pitted"):
        grain = 1000.0 / float(values["Frequency"])
        amp = float(values["Amplitude"]) * deep
        rng = np.random.default_rng(int(values["Seed"]))
        k = max(1, int(round(circ / grain)))                        # whole waves round the ring: periodic
        field = np.zeros(len(v))
        for _ in range(6):
            kk = rng.integers(max(1, k // 2), k * 2 + 1)
            ph, ph2 = rng.uniform(0, 2 * np.pi, 2)
            field += np.cos(2 * np.pi * kk * arc / circ + ph) * np.cos(2 * np.pi * z / grain + ph2)
        field /= np.abs(field).max()
        disp = amp * field if kind == "frost" else -amp * np.maximum(field, 0.0)
    elif kind == "cellular":
        grain = float(values["Grain"])
        depth = 3.4 * float(values["Factor"]) * grain * deep
        rng = np.random.default_rng(int(values["Seed"]))
        n = max(4, int(round(circ / grain))) * max(1, int(round((zt - zb) / grain)))
        pts = rng.uniform([0, zb - grain], [circ, zt + grain], (n, 2))
        pts = np.concatenate([pts + [kx * circ, 0] for kx in (-1, 0, 1)])
        from scipy.spatial import cKDTree
        f1, _ = cKDTree(pts).query(np.column_stack([arc, z]))
        disp = -depth * f1 / f1.max()
    elif kind == "ribbed":
        depth = -float(values["Erosion"]) * deep
        rib = float(values["Rib Spacing"])
        tri = 1.0 - 2.0 * np.abs((z / rib) % 1.0 - 0.5)              # 0 at the troughs, 1 at the peaks
        disp = -depth * (1.0 - tri)
    else:
        raise ValueError(kind)
    disp = np.where(zone, disp, 0.0)
    scale = (r + disp) / r
    v[:, 0] *= scale
    v[:, 1] *= scale
    return trimesh.Trimesh(v, mesh.faces, process=False)


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
    shape = os.environ.get("FAKE_NTOPCL_SHAPE", "design")
    if "solitaire" in nb.name or "head" in nb.name or "multistone" in nb.name:
        from ntopjewel import geom
        from pseudo_blend import Blended
        ops = geom.SHARP if shape == "noblend" else Blended()           # nTop blends where the radius says so
    if "solitaire" in nb.name:
        import trimesh
        from ntopjewel import solitaire
        from ntopjewel.nb_jewel import SLOT_NAMES
        for key in ("Seat Path", *SLOT_NAMES):
            if not Path(values[key]).exists():
                fail(f"{key.replace('Path', 'Mesh')}: file not found")
        envelope = trimesh.load(str(values["Seat Path"]), force="mesh")
        for key in ("Cut Path", "Relief Path", "Knot Path", "Knot Path 2"):
            if key in values and not Path(values[key]).exists():
                fail(f"{key.replace('Path', 'Mesh')}: file not found")
        if shape == "plainshank":
            # a notebook that ignored the bar's shape: the head section revolved all round (the bar's
            # section at Y = 0 swept about Z) - a tapered shank's gate must notice
            import numpy as np
            from ntopjewel import geom
            bar = trimesh.load(str(values["Shank Path"]), force="mesh")
            sec = bar.section(plane_origin=[0, 0, 0], plane_normal=[0, 1, 0])
            loops = [np.asarray(l) for l in sec.discrete]
            poly = max((trimesh.path.polygons.Polygon(l[:, [0, 2]]) for l in loops), key=lambda q: q.area)
            shank_mesh = geom.revolve_section(poly, sections=360)
        else:                                                               # the bars at Shank Path .., wrapped, carved by the
            shank_mesh = solitaire.carved_shank_from_inputs(values, cut=shape != "nocut", relief=shape != "norelief",
                                                            knots=shape != "noknot")                      # artwork and knot layers
        if "Strikes Path" in values:                                        # the Strikes section (solitaire 0.12.0 ...): the carved band struck
            shank_mesh = cut_strikes(shank_mesh, values, shape)
        mesh = solitaire.ring_mesh(values, envelope, cut_seat=shape != "noseat", beads=shape != "nobeads",
                                   engrave=shape != "noengrave", ops=ops, shank_mesh=shank_mesh)
        if os.environ.get("FAKE_NTOPCL_EXPORT", "1") != "0":
            mesh.export(values["Output Path"])
        for name in ("Bar 1 Mesh", "Bar 1", "Bars", "Shank", "Band Body", "Stone Seat", "Prong Head", "Placed Head", "Shoulders", "Arches", "Ring", "Mesh", "Export Mesh"):
            log("I", f"{name} complete 1ms")
        if os.environ.get("FAKE_NTOPCL_VOLUME", "mesh") != "none":
            outputs = [{"name": "Volume", "type": "real", "components": [],
                        "value": {"isFinite": True, "units": {"length": 3}, "val": float(mesh.volume) * 1e-9}}]
    elif "partial_bezel_head" in nb.name:
        import trimesh
        from ntopjewel import partial_bezel
        if not Path(values["Seat Path"]).exists():
            fail("Seat Body Mesh: file not found")
        envelope = trimesh.load(str(values["Seat Path"]), force="mesh")
        if shape == "fullbezel":                              # a notebook whose mask lost its walls: the cup to the top
            values = dict(values, **{"Cup Top": values["Bezel Top"]})
        mesh = partial_bezel.partial_bezel_mesh(values, envelope, cut_seat=shape != "noseat", ops=ops,
                                                mirror=shape != "noside", hoods=shape != "nohood")
        if os.environ.get("FAKE_NTOPCL_EXPORT", "1") != "0":
            mesh.export(values["Output Path"])
        for name in ("Bezel Grown", "Cup Slab", "Wall Sector Body", "Wall Sector Mirrored", "Hood Zone", "Mask",
                     "Partial Bezel", "Seated", "Mesh", "Export Mesh", "Volume Integral"):
            log("I", f"{name} complete 1ms")
        if os.environ.get("FAKE_NTOPCL_VOLUME", "mesh") != "none":
            outputs = [{"name": "Volume", "type": "real", "components": [],
                        "value": {"isFinite": True, "units": {"length": 3}, "val": float(mesh.volume) * 1e-9}}]
    elif "bezel_head" in nb.name:
        import trimesh
        from ntopjewel import heads
        for key in ("Seat Path", "Windows Path"):
            if not Path(values[key]).exists():
                fail(f"{key}: file not found")
        envelope = trimesh.load(str(values["Seat Path"]), force="mesh")
        windows = trimesh.load(str(values["Windows Path"]), force="mesh")
        mesh = heads.bezel_mesh(values, envelope, windows, cut_seat=shape != "noseat", ops=ops)
        if os.environ.get("FAKE_NTOPCL_EXPORT", "1") != "0":
            mesh.export(values["Output Path"])
        for name in ("Bezel Grown", "Bezel Cup", "Windows", "Seated", "Mesh", "Export Mesh", "Volume Integral"):
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
        if shape == "noprongs":                               # a notebook that never imported the prongs (claws, a pearl's post)
            foot = prongs.vertices[prongs.vertices[:, 2].argmin()] + [0.0, 0.0, 0.05]
            prongs = trimesh.creation.icosphere(subdivisions=2, radius=0.02)
            prongs.apply_translation(foot)                    # a speck inside the rails' metal
        mesh = heads.outline_head_mesh(values, envelope, prongs, cut_seat=shape != "noseat", ops=ops)
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
            fail("Seat Body Mesh: file not found")
        envelope = trimesh.load(str(values["Seat Path"]), force="mesh")
        mesh = heads.head_mesh(values, envelope, cut_seat=shape != "noseat", ops=ops)
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
            fail("Seat Body Mesh: file not found")
        mesh = offset_convex(trimesh.load(str(values["Seat Path"]), force="mesh"), float(values["Clearance"]))
        if os.environ.get("FAKE_NTOPCL_EXPORT", "1") != "0":
            mesh.export(values["Output Path"])
        for name in ("Seat Body Mesh", "Seat Body", "Stone Seat", "Mesh", "Export Mesh", "Volume Integral"):
            log("I", f"{name} complete 1ms")
        if os.environ.get("FAKE_NTOPCL_VOLUME", "mesh") != "none":
            outputs = [{"name": "Volume", "type": "real", "components": [],
                        "value": {"isFinite": True, "units": {"length": 3}, "val": float(mesh.volume) * 1e-9}}]
    elif "multistone" in nb.name:
        from ntopjewel import multistone
        from ntopjewel.nb_jewel import SLOT_NAMES
        for key in (*SLOT_NAMES, *(multistone.slot_input(n, k) for k in range(multistone.SLOTS) for n in ("Seat Path", "Prongs Path")),
                    "Pave Beads Path", "Pave Seats Path", "Gallery Path", "Shared Prongs Path", "Engraving Path"):
            if key in values and not Path(values[key]).exists():
                fail(f"{key.replace('Path', 'Mesh')}: file not found")
        if shape in ("nogallery", "noposts"):                 # a notebook that left the bridge / the shared prongs out
            from ntopjewel import artwork
            from ntopjewel.band import BandSpec
            sp = Path(values["Output Path"]).with_suffix(f".{shape}.stl")
            artwork.buried_speck(BandSpec(size=6, width_mm=2.6, thickness_mm=1.8)).export(str(sp))    # taken in by the band
            values["Gallery Path" if shape == "nogallery" else "Shared Prongs Path"] = str(sp)
        if shape == "nopave":                                 # a notebook that never cut the pavé's seats
            from ntopjewel import artwork
            from ntopjewel.band import BandSpec
            sp = Path(values["Output Path"]).with_suffix(".nopave_seats.stl")
            artwork.outside_speck(BandSpec(size=6)).export(str(sp))
            values["Pave Seats Path"] = str(sp)
        if shape == "noengrave":                              # a notebook that never cut the text
            values.pop("Engraving Path", None)
        if shape == "noside":                                 # a notebook whose slots 2.. never got their own values
            for k in range(1, multistone.SLOTS):
                for n, _ in multistone.SLOT_FIELDS:
                    values[multistone.slot_input(n, k)] = values[n]
        mesh = multistone.ring_from_inputs(values, ops)
        if os.environ.get("FAKE_NTOPCL_EXPORT", "1") != "0":
            mesh.export(values["Output Path"])
        for name in ("Bars", "Shank", "Stone Seat 1", "Outline Head 1", "Head 1 On Ring", "Gallery", "Shared Prongs", "Engraving", "Heads", "Joined",
                     "Ring", "Mesh", "Export Mesh", "Volume Integral"):
            log("I", f"{name} complete 1ms")
        if os.environ.get("FAKE_NTOPCL_VOLUME", "mesh") != "none":
            outputs = [{"name": "Volume", "type": "real", "components": [],
                        "value": {"isFinite": True, "units": {"length": 3}, "val": float(mesh.volume) * 1e-9}}]
    elif "artwork" in nb.name:
        import trimesh
        from ntopjewel.nb_jewel import SLOT_NAMES
        for key in (*SLOT_NAMES, "Cut Path", "Relief Path"):
            if not Path(values[key]).exists():
                fail(f"{key.replace('Path', 'Mesh')}: file not found")
        from ntopjewel.shank import bars_from_inputs
        mesh = bars_from_inputs(values)                                # the band (its opening not simulated)
        cuts = trimesh.load(str(values["Cut Path"]), force="mesh")
        relief = trimesh.load(str(values["Relief Path"]), force="mesh")
        if shape != "nocut":                                          # a notebook that never cut the channels ...
            mesh = trimesh.boolean.difference([mesh, cuts], engine="manifold")
        if shape != "norelief":                                       # ... or lost the relief
            mesh = trimesh.boolean.union([mesh, relief], engine="manifold")
        if os.environ.get("FAKE_NTOPCL_EXPORT", "1") != "0":
            mesh.export(values["Output Path"])
        for name in ("Bar 1 Mesh", "Bar 1", "Bar 1 Opened", "Bars", "Shank", "Panel Cuts Mesh", "Panel Cuts",
                     "Relief Mesh", "Relief", "Carved", "Ring", "Mesh", "Export Mesh", "Volume Integral"):
            log("I", f"{name} complete 1ms")
        if os.environ.get("FAKE_NTOPCL_VOLUME", "mesh") != "none":
            outputs = [{"name": "Volume", "type": "real", "components": [],
                        "value": {"isFinite": True, "units": {"length": 3}, "val": float(mesh.volume) * 1e-9}}]
    elif "pave" in nb.name:
        import trimesh
        from ntopjewel.nb_jewel import SLOT_NAMES
        for key in (*SLOT_NAMES, "Pave Seats Path", "Pave Beads Path"):
            if not Path(values[key]).exists():
                fail(f"{key.replace('Path', 'Mesh')}: file not found")
        # the band as ring_shank builds it (bars wrapped and united; the opening, as there, not
        # simulated), then (band ∪ beads) − seats
        from ntopjewel.shank import bars_from_inputs
        mesh = bars_from_inputs(values)
        beads = trimesh.load(str(values["Pave Beads Path"]), force="mesh")
        seats = trimesh.load(str(values["Pave Seats Path"]), force="mesh")
        if shape == "nobeads":                                # a notebook that lost the bead layer
            pass
        else:
            mesh = trimesh.boolean.union([mesh, beads], engine="manifold")
        if shape != "noseats":                                # ... or never cut the seats
            mesh = trimesh.boolean.difference([mesh, seats], engine="manifold")
        if os.environ.get("FAKE_NTOPCL_EXPORT", "1") != "0":
            mesh.export(values["Output Path"])
        for name in ("Bar 1 Mesh", "Bar 1", "Bar 1 Opened", "Bars", "Shank", "Pave Beads Mesh", "Pave Beads",
                     "Pave Seats Mesh", "Pave Seats", "Beaded", "Ring", "Mesh", "Export Mesh", "Volume Integral"):
            log("I", f"{name} complete 1ms")
        if os.environ.get("FAKE_NTOPCL_VOLUME", "mesh") != "none":
            outputs = [{"name": "Volume", "type": "real", "components": [],
                        "value": {"isFinite": True, "units": {"length": 3}, "val": float(mesh.volume) * 1e-9}}]
    elif any(k in nb.name for k in ("frost", "pitted", "cellular", "ribbed")):
        # ring_frost / pitted / cellular / ribbed: nTop's noise or wave masked to the outer face (displace_texture)
        kind = next(k for k in ("frost", "pitted", "cellular", "ribbed") if k in nb.name)
        mesh = displace_texture(band_mesh(values), values, kind, shape)
        if os.environ.get("FAKE_NTOPCL_EXPORT", "1") != "0":
            mesh.export(values["Output Path"])
        for name in ("Band Body", "Textured All Over", "Dents", "Zone", "Dents In Zone", "Textured", "Mesh", "Export Mesh", "Volume Integral"):
            log("I", f"{name} complete 1ms")
        if os.environ.get("FAKE_NTOPCL_VOLUME", "mesh") != "none":
            outputs = [{"name": "Volume", "type": "real", "components": [],
                        "value": {"isFinite": True, "units": {"length": 3}, "val": float(mesh.volume) * 1e-9}}]
    elif "lattice" in nb.name:
        # ring_lattice: the band less the zone ∪ the walled gyroid wrapped round the ring inside the grown zone, opened at the
        # dome - manifold3d's level set of the same field nTop's blocks make, from the inputs alone (lattice.lattice_mesh)
        from ntopjewel import lattice as _lat
        zh = (float(values["Zone Z Top"]) - float(values["Zone Z Bottom"])) / 2
        overlap = float(values["Zone Inner Radius"]) - float(values["Lattice Inner Radius"])
        wall = float(values["Wall"]) * (0.6 if shape == "thin" else 1.0)
        mesh = _lat.lattice_mesh(values, float(values["Cell Size"]), wall, float(values["Wrap Length"]), zh,
                                 float(values["Zone Inner Radius"]), float(values["Mesh Tolerance"]), lattice=shape != "nolattice",
                                 closed=shape == "closed", overlap=overlap, round_mm=float(values["Lattice Round"]))
        if os.environ.get("FAKE_NTOPCL_EXPORT", "1") != "0":
            mesh.export(values["Output Path"])
        for name in ("Band Body", "Gyroid", "Walled Gyroid", "Lattice Wrapped", "Zone", "Lattice Zone", "Lattice Trimmed", "Lattice Eroded",
                     "Lattice Re-distanced Mesh", "Lattice Re-distanced", "Lattice Opened", "Skin And Rims", "Lattice Band", "Mesh",
                     "Export Mesh", "Volume Integral"):
            log("I", f"{name} complete 1ms")
        if os.environ.get("FAKE_NTOPCL_VOLUME", "mesh") != "none":
            outputs = [{"name": "Volume", "type": "real", "components": [],
                        "value": {"isFinite": True, "units": {"length": 3}, "val": float(mesh.volume) * 1e-9}}]
    elif "voronoi" in nb.name:
        # ring_voronoi: the profiled band with nTop's voronoi deboss masked to the outer face (voronoi_grooves)
        mesh = voronoi_grooves(band_mesh(values), values, shape)
        if os.environ.get("FAKE_NTOPCL_EXPORT", "1") != "0":
            mesh.export(values["Output Path"])
        for name in ("Band Body", "Grooved", "Dents", "Zone", "Dents In Zone", "Textured", "Mesh", "Export Mesh", "Volume Integral"):
            log("I", f"{name} complete 1ms")
        if os.environ.get("FAKE_NTOPCL_VOLUME", "mesh") != "none":
            outputs = [{"name": "Volume", "type": "real", "components": [],
                        "value": {"isFinite": True, "units": {"length": 3}, "val": float(mesh.volume) * 1e-9}}]
    elif "texture_probe" in nb.name:
        # the texture probe: nTop's toolkit textures on the plain band, one STL each. The stand-in's texture: a row
        # of dents round the outer face's mid-line (depth = Depth), different per case only in their count - the
        # measurements, not nTop's noise, are what the offline suite exercises
        import numpy as np
        import trimesh
        from ntopjewel import nb_texture as _nt
        plain = band_mesh(values)
        depth, r_out = float(values["Depth"]), float(values["Outer Radius"])
        for i, label in enumerate(_nt.CASES):
            n = 24 + 6 * i
            rad = 1.0
            dents = [trimesh.creation.icosphere(subdivisions=3, radius=rad).apply_translation(
                [(r_out + rad - depth) * np.cos(a), (r_out + rad - depth) * np.sin(a), 0.0])
                for a in np.linspace(0, 2 * np.pi, n, endpoint=False)]
            mesh = trimesh.boolean.difference([plain] + dents, engine="manifold")
            mesh.export(values[f"Output {label}"])
            log("I", f"{label} complete 1ms")
        if os.environ.get("FAKE_NTOPCL_VOLUME", "mesh") != "none":
            outputs = [{"name": "Volume", "type": "real", "components": [],
                        "value": {"isFinite": True, "units": {"length": 3}, "val": float(plain.volume) * 1e-9}}]
    elif "texture" in nb.name:
        # ring_texture: the profiled band less a sphere at every centre Import Points reads (comma-separated
        # x,y,z, in the unit Strikes Units names: 1 = mm, 2 = cm, measured by points_probe)
        mesh = cut_strikes(band_mesh(values), values, shape)
        if os.environ.get("FAKE_NTOPCL_EXPORT", "1") != "0":
            mesh.export(values["Output Path"])
        for name in ("Band Body", "Strike Centres", "Strikes", "Strikes United", "Struck", "Mesh", "Export Mesh", "Volume Integral"):
            log("I", f"{name} complete 1ms")
        if os.environ.get("FAKE_NTOPCL_VOLUME", "mesh") != "none":
            outputs = [{"name": "Volume", "type": "real", "components": [],
                        "value": {"isFinite": True, "units": {"length": 3}, "val": float(mesh.volume) * 1e-9}}]
    elif "shank" in nb.name:
        import trimesh
        from ntopjewel.nb_jewel import SLOT_NAMES
        for key in SLOT_NAMES:
            if not Path(values[key]).exists():
                fail(f"{key.replace('Path', 'Mesh')}: file not found")
        # the notebook's opening (Edge Round / Edge Round Inward) is not simulated: a slot's or a
        # bridge's edges stay sharp here, which the gate's section-shape check then reports (as it
        # would for nTop); tests of those designs run with the edge round at 0
        if shape == "nowrap":                                 # a notebook that exports the first bar itself
            mesh = trimesh.load(str(values["Shank Path"]), force="mesh")
        else:
            # every bar wrapped vertex-wise, one turn each, cut between stations, the seam joined
            # (shank.wrap_bar: Remap Cylindrical Body is exactly that in r, z and angle), and the
            # wrapped bars united (nTop unites the implicits before the wrap; same thing)
            from ntopjewel.shank import bars_from_inputs
            mesh = bars_from_inputs(values)
        if "Strikes Path" in values:                          # ring_shank 0.4.0: the Strikes section
            mesh = cut_strikes(mesh, values, shape)
        if os.environ.get("FAKE_NTOPCL_EXPORT", "1") != "0":
            mesh.export(values["Output Path"])
        for name in ("Bar 1 Mesh", "Bar 1", "Bar 2 Mesh", "Bar 2", "Bar 1 Eroded", "Bar 1 Re-distanced Mesh", "Bar 1 Re-distanced", "Bar 1 Opened", "Bars", "Shank", "Mesh", "Export Mesh", "Volume Integral"):
            log("I", f"{name} complete 1ms")
        if os.environ.get("FAKE_NTOPCL_VOLUME", "mesh") != "none":
            outputs = [{"name": "Volume", "type": "real", "components": [],
                        "value": {"isFinite": True, "units": {"length": 3}, "val": float(mesh.volume) * 1e-9}}]
    elif "band" in nb.name or "features" in nb.name:
        if "Bead Count" in values and not Path(values["Engraving Path"]).exists():
            fail("Engraving Body Mesh: file not found")
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
