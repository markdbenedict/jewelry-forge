"""Monstera leaf band (Blender 5.1+, needs jewelry_kit loaded as a module).

A solid inner band carries a sheath of monstera leaves laid nose-to-tail around the ring, each
leaf bent to the band's curve with its long axis roughly along the circumference. No two leaves
are alike: length, width, outline, the number and depth of the edge slits (independently on each
side of the midrib), the oval holes and a twist of up to +/- yaw_deg off the band direction are
all drawn from a seeded random generator, so a rebuild gives the same ring. Every leaf is a bent
slab (midrib and side veins pressed into the top, tip rising so it shingles over the next leaf's
base), trimmed to its outline and cut with slits and holes down to the band. The ring size is
engraved inside the band. Units: 1 Blender unit = 1 mm. Ring axis along Y.

The 2-D leaf design (LEAF, VARIETY, make_variant, the outline / slit / hole polygons, the vein
field) lives in leaf_design.py next to this file, which needs no bpy, and is re-exported here;
this module is the 3-D construction on top of it.
"""
import bpy, bmesh, math, sys
import numpy as np
from mathutils import Vector
from pathlib import Path

try:                                # imported from disk: leaf_design sits next to this file
    _here = Path(__file__).resolve().parent
    if (_here / "leaf_design.py").is_file() and str(_here) not in sys.path:
        sys.path.insert(0, str(_here))
except NameError:                   # exec'd from a Blender text block: no __file__, so the caller
    pass                            # must already have put this folder on sys.path
from leaf_design import (BAND, LEAF, VARIETY, RING_WIDTH, make_variant, outline_poly, slit_poly,
                         hole_poly, half_width, _alpha, _line, _vein_depth, _poly_gap, _layout_ok)

LABEL_SIZE, LABEL_DEPTH = 1.6, 0.30


# ----------------------------------------------------------------------------- 3-D construction
def _band_xy(x, y, F):
    """Leaf-local (x along the midrib, y across) -> band-local (s along the band, yb across),
    the leaf twisted by yaw about a pivot on its midrib."""
    x = np.asarray(x, float) - F["xp"]
    y = np.asarray(y, float)
    c, s = math.cos(F["psi"]), math.sin(F["psi"])
    return F["xp"] + x * c - y * s, x * s + y * c


def _bend(x, y, h, F):
    s, yb = _band_xy(x, y, F)
    th = F["theta0"] + s / F["R_m"]
    r = F["R_b"] + np.asarray(h, float)
    return r * np.sin(th), yb, -r * np.cos(th)


def _mesh_from(name, verts, faces):
    """Mesh from raw data, normals made consistent and everything triangulated: bent quads are
    twisted, and the boolean solver only merges output faces cleanly when its inputs are planar."""
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.to_mesh(me)
    bm.free()
    return me


def _triangulate(me):
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.to_mesh(me)
    bm.free()
    return me


def _slab_mesh(p, F, embed, band_w):
    L, W = p["length"], p["width"]
    t_mid, t_edge = p["thick"]
    nu, nv = p["nu"], p["nv"]
    xs = np.linspace(-0.4, L + 0.4, nu)
    ys = np.linspace(-(W / 2 + 0.25), W / 2 + 0.25, nv)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    u = X / L
    dome = t_edge + (t_mid - t_edge) * np.clip(1 - (Y / (W / 2)) ** 2, 0, 1)
    top = dome + p["step"] * np.clip(u, 0, 1) - _vein_depth(X, Y, p)
    _, Yb = _band_xy(X, Y, F)                                    # the band edge is in band coords
    y0, y1 = band_w / 2 - 0.30, band_w / 2 - 0.05               # inside the band: embedded a little;
    f = np.clip((np.abs(Yb) - y0) / (y1 - y0), 0, 1)             # past its edge: wraps down over it
    bot = -embed * (1 - f) - p["drape"] * f
    tx, ty, tz = _bend(X, Y, top, F)
    bx, by, bz = _bend(X, Y, bot, F)
    verts = list(zip(tx.ravel(), ty.ravel(), tz.ravel())) + list(zip(bx.ravel(), by.ravel(), bz.ravel()))
    N = nu * nv
    T = lambda i, j: i * nv + j
    B = lambda i, j: N + i * nv + j
    faces = []
    for i in range(nu - 1):
        for j in range(nv - 1):
            faces.append((T(i, j), T(i + 1, j), T(i + 1, j + 1), T(i, j + 1)))
            faces.append((B(i, j), B(i, j + 1), B(i + 1, j + 1), B(i + 1, j)))
    for j in range(nv - 1):                                       # ends (x = const)
        faces.append((T(0, j), T(0, j + 1), B(0, j + 1), B(0, j)))
        faces.append((T(nu - 1, j), B(nu - 1, j), B(nu - 1, j + 1), T(nu - 1, j + 1)))
    for i in range(nu - 1):                                       # sides (y = const)
        faces.append((T(i, 0), B(i, 0), B(i + 1, 0), T(i + 1, 0)))
        faces.append((T(i, nv - 1), T(i + 1, nv - 1), B(i + 1, nv - 1), B(i, nv - 1)))
    return _mesh_from("_slab", verts, faces)


def _prism_mesh(name, poly, h0, h1, F):
    """Bent prism over a convex 2-D polygon, radial range h0..h1 (fan-capped)."""
    n = len(poly)
    cx, cy = poly.mean(0)
    verts = []
    for h in (h0, h1):
        x, y, z = _bend(poly[:, 0], poly[:, 1], h, F)
        verts += list(zip(x, y, z))
    for h in (h0, h1):
        x, y, z = _bend(cx, cy, h, F)
        verts.append((float(x), float(y), float(z)))
    c0, c1 = 2 * n, 2 * n + 1
    faces = []
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, n + j, n + i))
        faces.append((c0, j, i))
        faces.append((c1, n + i, n + j))
    return _mesh_from(name, verts, faces)


def _leaf_solid(k, p, F, band_w, collection):
    embed = p["embed"][k % 2]
    tmp = bpy.data.collections.new("_leaf_ops")
    bpy.context.scene.collection.children.link(tmp)
    cutters = bpy.data.collections.new("_leaf_cutters")
    bpy.context.scene.collection.children.link(cutters)

    slab = bpy.data.objects.new("_slab", _slab_mesh(p, F, embed, band_w))
    tmp.objects.link(slab)
    outline = bpy.data.objects.new("_outline", _prism_mesh("_outline", outline_poly(p), -2.5, 3.5, F))
    tmp.objects.link(outline)
    polys = [slit_poly(u, s, p) for s in (1, -1) for u in p["slits"][s]]
    polys += [hole_poly(u, s, p) for s in (1, -1) for u in p["holes"][s]]
    for i, poly in enumerate(polys):
        ob = bpy.data.objects.new(f"_cut{i}", _prism_mesh(f"_cut{i}", poly, p["cut_floor"], 2.5, F))
        cutters.objects.link(ob)

    m = slab.modifiers.new("outline", 'BOOLEAN')
    m.operation, m.object, m.solver = 'INTERSECT', outline, 'MANIFOLD'
    m = slab.modifiers.new("cuts", 'BOOLEAN')
    m.operation, m.operand_type, m.solver = 'DIFFERENCE', 'COLLECTION', 'MANIFOLD'
    m.collection = cutters
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(slab.evaluated_get(dg), depsgraph=dg)
    me.name = f"_leaf{k}"
    for c in (cutters, tmp):
        for o in list(c.objects):
            d = o.data
            bpy.data.objects.remove(o)
            if d and d.users == 0:
                bpy.data.meshes.remove(d)
        bpy.data.collections.remove(c)
    leaf = bpy.data.objects.new(f"_leaf{k}", me)
    collection.objects.link(leaf)
    return leaf


def _fix_slivers(bm, area=1e-8, dist=2e-3):
    """Needle faces left by the booleans: weld only their own vertices, drop duplicate faces.
    Welding never creates polygons, so the mesh stays all-triangles."""
    for _ in range(3):
        tiny = [f for f in bm.faces if f.calc_area() < area]
        if not tiny:
            break
        verts = list({v for f in tiny for v in f.verts})
        bmesh.ops.remove_doubles(bm, verts=verts, dist=dist)
        bm.verts.index_update()
        seen, dup = {}, []
        for f in bm.faces:
            key = frozenset(v.index for v in f.verts)
            if key in seen:
                dup += [f, seen[key]]
            else:
                seen[key] = f
        if dup:
            bmesh.ops.delete(bm, geom=list(set(dup)), context='FACES_ONLY')
            loose_e = [e for e in bm.edges if not e.link_faces]
            if loose_e:
                bmesh.ops.delete(bm, geom=loose_e, context='EDGES')
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()


def clean_mesh(me, min_volume=1e-3):
    """Triangulate, weld, drop degenerate faces and zero-volume debris shells left by booleans."""
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    _fix_slivers(bm)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
    bm.faces.ensure_lookup_table()
    seen, junk = set(), []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack, comp = [f], []
        seen.add(f.index)
        while stack:
            c = stack.pop()
            comp.append(c)
            for e in c.edges:
                for g in e.link_faces:
                    if g.index not in seen:
                        seen.add(g.index)
                        stack.append(g)
        vol = 0.0
        for fc in comp:
            vs = [v.co for v in fc.verts]
            for k in range(1, len(vs) - 1):
                vol += vs[0].dot(vs[k].cross(vs[k + 1])) / 6
        if abs(vol) < min_volume:
            junk += comp
    if junk:
        bmesh.ops.delete(bm, geom=list(set(junk)), context='FACES')
    for _ in range(4):                                             # flaps hanging by one edge
        flaps = [f for f in bm.faces
                 if sum(1 for e in f.edges if len(e.link_faces) == 1) >= 2 and f.calc_area() < 1e-4]
        if not flaps:
            break
        bmesh.ops.delete(bm, geom=flaps, context='FACES')
    rim = [e for e in bm.edges if len(e.link_faces) == 1]
    if rim:                                                        # tiny holes left behind
        res = bmesh.ops.holes_fill(bm, edges=rim, sides=4)
        if res.get("faces"):
            bmesh.ops.triangulate(bm, faces=[f for f in res["faces"] if f.is_valid and len(f.verts) > 3])
    loose = [v for v in bm.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context='VERTS')
    bm.to_mesh(me)
    bm.free()
    return len(junk)


def _annulus_mesh(name, r0, r1, y0, y1, segments=256):
    """Closed ring-shaped slab (r0 < r < r1, y0 < y < y1) around the ring axis (Y)."""
    th = np.linspace(0, 2 * math.pi, segments, endpoint=False)
    verts = []
    for y in (y0, y1):
        for r in (r0, r1):
            verts += list(zip(r * np.sin(th), np.full(segments, y), -r * np.cos(th)))
    n = segments
    I0, O0, I1, O1 = 0, n, 2 * n, 3 * n
    faces = []
    for i in range(n):
        j = (i + 1) % n
        faces.append((O0 + i, O0 + j, O1 + j, O1 + i))              # outer wall
        faces.append((I0 + j, I0 + i, I1 + i, I1 + j))              # inner wall
        faces.append((I0 + i, I0 + j, O0 + j, O0 + i))              # cap y0
        faces.append((I1 + j, I1 + i, O1 + i, O1 + j))              # cap y1
    return _mesh_from(name, verts, faces)


def _label_mesh(text):
    cu = bpy.data.curves.new("_label", 'FONT')
    cu.body = text
    cu.size = LABEL_SIZE
    cu.align_x, cu.align_y = 'CENTER', 'CENTER'
    cu.extrude = 0.6
    ob = bpy.data.objects.new("_label", cu)
    bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), depsgraph=dg)
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    return me


def _size_text(size):
    return f"{size:.2f}".rstrip("0").rstrip(".")


def ring_plan(size, seed=None):
    """Leaf variants and where each one starts around the band, for a given ring size."""
    jk = sys.modules["jewelry_kit"]
    r_in = jk.us_size_to_inner_diameter_mm(size) / 2
    R_b = r_in + BAND["Thickness"]
    R_m = R_b + LEAF["thick"][0] / 2
    C = 2 * math.pi * R_m
    mean_pitch = LEAF["length"] * sum(VARIETY["length"]) / 2 - sum(VARIETY["overlap"]) / 2
    n = max(6, int(round(C / mean_pitch)))
    seed = VARIETY["seed"] if seed is None else seed
    rng = np.random.default_rng(seed * 1000 + int(round(size * 4)))
    variants = [make_variant(rng) for _ in range(n)]
    pitches = np.array([v["length"] - v["overlap"] for v in variants])
    pitches *= C / pitches.sum()                                  # close the circle exactly
    starts = np.concatenate([[0.0], np.cumsum(pitches)[:-1]])
    frames = [dict(theta0=float(s0 / R_m), psi=v["yaw"], xp=v["pivot"] * v["length"], R_b=R_b, R_m=R_m)
              for s0, v in zip(starts, variants)]
    return dict(r_in=r_in, R_b=R_b, R_m=R_m, n=n, variants=variants, frames=frames)


def build(size, collection=None, material=None, x=0.0, name=None, seed=None):
    jk = sys.modules["jewelry_kit"]
    col = collection or bpy.context.scene.collection
    plan = ring_plan(size, seed)
    r_in = plan["r_in"]

    tmp = bpy.data.collections.new("_ring_ops")
    bpy.context.scene.collection.children.link(tmp)
    leaves = bpy.data.collections.new("_leaves")
    bpy.context.scene.collection.children.link(leaves)
    band = jk.add_ring("_band", tmp, **{"US Size": size, **BAND})
    for k, (p, F) in enumerate(zip(plan["variants"], plan["frames"])):
        _leaf_solid(k, p, F, BAND["Width"], leaves)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    core = bpy.data.objects.new("_core", _triangulate(bpy.data.meshes.new_from_object(band.evaluated_get(dg), depsgraph=dg)))
    tmp.objects.link(core)
    m = core.modifiers.new("leaves", 'BOOLEAN')
    m.operation, m.operand_type, m.solver = 'UNION', 'COLLECTION', 'MANIFOLD'
    m.collection = leaves
    cut = bpy.data.collections.new("_ring_cutters")
    bpy.context.scene.collection.children.link(cut)
    lab = bpy.data.objects.new("_label", _label_mesh(_size_text(size)))
    cut.objects.link(lab)
    lab.location = (0.0, 0.0, -r_in - LABEL_DEPTH + 0.6)       # engraved inside, at the bottom
    half = RING_WIDTH / 2                                       # trim lobes to the overall width
    for side, nm in ((1, "_trimR"), (-1, "_trimL")):
        y0, y1 = sorted((side * half, side * (half + 3.0)))
        cut.objects.link(bpy.data.objects.new(nm, _annulus_mesh(nm, r_in - 1.0, plan["R_b"] + 3.0, y0, y1)))
    m = core.modifiers.new("trim", 'BOOLEAN')
    m.operation, m.operand_type, m.solver = 'DIFFERENCE', 'COLLECTION', 'MANIFOLD'
    m.collection = cut
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(core.evaluated_get(dg), depsgraph=dg)
    clean_mesh(me)

    for c in (leaves, cut, tmp):
        for o in list(c.objects):
            d = o.data
            bpy.data.objects.remove(o)
            if d and d.users == 0:
                bpy.data.meshes.remove(d)
        bpy.data.collections.remove(c)
    name = name or f"Monstera ring US {_size_text(size)}"
    me.name = name
    old = bpy.data.objects.get(name)
    if old:
        bpy.data.objects.remove(old)
    ring = bpy.data.objects.new(name, me)
    col.objects.link(ring)
    ring.location.x = x
    if material:
        me.materials.clear()
        me.materials.append(material)
    me.shade_smooth()
    me.set_sharp_from_angle(angle=math.radians(35))
    return ring


def documents_dir():
    import os
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:
            return buf.value
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Documents")


def export_stl(obj, path):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True, apply_modifiers=True,
                          ascii_format=False)
    obj.select_set(False)
