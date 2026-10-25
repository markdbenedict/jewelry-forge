"""Pear bezel-cup ring builder (Blender 5.1+, needs jewelry_kit loaded as a module).

Cross-section loops (bezel cup + stone pocket) are generated from the fitted stone outline and
share the same N angles around the culet point C. Each ring = band (parametric ring, applied)
+ cup trimmed to clear the finger, minus the pocket, with the size engraved under the band.
Units: 1 Blender unit = 1 mm. The stone's long axis runs along the finger (Y), tip toward +Y.
"""
import bpy, bmesh, math, sys
from mathutils import Matrix, Vector

BAND = {"Size Allowance": 0.0, "Width": 3.2, "Thickness": 1.8, "Finish Stock": 0.0,
        "Outer Dome": 0.4, "Comfort Relief": 0.15, "Segments": 256, "Profile Points": 16}
LABEL_SIZE, LABEL_DEPTH = 1.6, 0.4      # engraved size number under the band (mm)

import numpy as np

STONE = dict(L=12.3, ratio=8.9 / 12.3, widest=0.41, n_round=2.4, culet=0.33)
# caliper measurements: 12.3 long x 8.9 wide x 4.6 deep; outline shape fitted to the photo
SETTING = dict(clr=0.25, wall=1.00, ch_o=0.30, ch_i=0.25, z_top=0.70, z_v=-0.30, groove=0.25,
               pocket=3.60, gap=0.60, floor=0.80, s_b=0.20, w_grow=0.30, n=256, m=1440,
               gallery=True, bearing=0.60, drop=0.60, shell=1.00,
               windows=(15, -15, 135, -135, 180), win_z=-2.40, win_w=1.25, win_h=1.60)
# gallery: under the seat the cup is hollow (1 mm shell); the stone rests on a 0.6 mm conical
# bearing just below its girdle, and oval windows (angles around the culet, deg) let light in.


def stone_outline(L, ratio, widest, n_round, **_):
    """Pear outline, head coords: X across, Y along (round end -L/2 .. tip +L/2)."""
    r, k = ratio * L / 2, widest * L
    Ra = (r * r + (L - k) ** 2) / (2 * r)
    vs = np.concatenate([np.linspace(0, k, 700, endpoint=False), np.linspace(k, L, 1000)])
    hw = np.where(vs <= k,
                  r * np.clip(1 - np.abs((k - vs) / k) ** n_round, 0, 1) ** (1 / n_round),
                  (r - Ra) + np.sqrt(np.clip(Ra * Ra - (vs - k) ** 2, 0, None)))
    right = np.stack([hw, vs - L / 2], 1)
    return np.concatenate([right, right[::-1] * [-1, 1]])


def make_loops(stone=STONE, s=SETTING):
    """Cross-section loops via support functions: offsetting a convex shape by d adds d to its
    support function, scaling about C multiplies it, so every loop is exact and shares N angles."""
    L = stone["L"]
    C = np.array([0.0, stone["culet"] * L - L / 2])
    pts = stone_outline(**stone) - C
    phi = np.linspace(0, 2 * np.pi, s["m"], endpoint=False)
    U = np.stack([np.sin(phi), np.cos(phi)], 1)              # angle 0 -> +Y (tip)
    h = (pts @ U.T).max(0)                                   # support function about C
    th = np.linspace(0, 2 * np.pi, s["n"], endpoint=False)
    cosd = np.cos(th[:, None] - phi[None, :])
    valid = cosd > 0.02

    def polar(scale, add):                                   # loop = scale*(stone (+) clr) (+) add
        hh = scale * (h + s["clr"]) + add
        return np.where(valid, hh[None, :] / np.where(valid, cosd, 1), np.inf).min(1)

    clr, wall = s["clr"], s["wall"]
    seat = s["gap"] + s["floor"] + s["pocket"]
    z_bot = -(seat + 1.0)
    cup = [(s["z_top"], polar(1, wall - s["ch_o"])), (s["z_top"] - s["ch_o"], polar(1, wall)),
           (s["z_v"], polar(1, wall)), (s["z_v"] - 0.15, polar(1, wall - s["groove"])),
           (s["z_v"] - 0.30, polar(1, wall))]
    z0 = s["z_v"] - 0.30
    for t in np.linspace(0, 1, 15)[1:]:
        cup.append((z0 + t * (z_bot - z0), polar(1 - (1 - s["s_b"]) * t ** 1.5, wall + s["w_grow"] * t)))
    pocket = [(s["z_top"] + 1.0, polar(1, s["ch_i"] + 1.0)), (s["z_top"], polar(1, s["ch_i"])),
              (s["z_top"] - s["ch_i"], polar(1, 0)), (0.0, polar(1, 0))]

    def taper(z):                                            # cup taper parameter at height z
        return min(1.0, max(0.0, (z0 - z) / (z0 - z_bot)))

    def shell_inner(z, sh=None):                             # inside face of a 1 mm cup shell
        t = taper(z)
        return polar(1 - (1 - s["s_b"]) * t ** 1.5, wall + s["w_grow"] * t - (sh or s["shell"]))

    windows = []
    if s.get("gallery"):
        lam = lambda d: 1 - d / s["pocket"]
        b, ceil = s["bearing"], s["bearing"] + s["drop"]
        pocket += [(-b / 2, polar(lam(b / 2), 0)), (-b, polar(lam(b), 0)), (-ceil, polar(lam(b), 0))]
        for zc in np.linspace(-ceil, -s["pocket"], 7):
            pocket.append((float(zc), shell_inner(zc)))
        t = taper(s["win_z"])
        outer_w = polar(1 - (1 - s["s_b"]) * t ** 1.5, wall + s["w_grow"] * t)
        inner_w = shell_inner(s["win_z"])
        n = s["n"]

        def pt(arr, k):
            k %= n
            return C + arr[k] * np.array([math.sin(th[k]), math.cos(th[k])])

        for ang in s["windows"]:                             # aim each window square to the wall
            i = int(round((ang % 360) / 360 * n)) % n
            tng = pt(outer_w, i + 2) - pt(outer_w, i - 2)
            nrm = np.array([tng[1], -tng[0]]) / np.linalg.norm(tng)
            if nrm @ (pt(outer_w, i) - C) < 0:
                nrm = -nrm
            mid = (pt(inner_w, i) + pt(outer_w, i)) / 2
            windows.append((float(mid[0]), float(mid[1]), s["win_z"], float(nrm[0]), float(nrm[1])))
    else:
        for d in np.linspace(0, s["pocket"], 11)[1:-1]:
            pocket.append((-d, polar(1 - d / s["pocket"], 0)))
    stone_r = np.where(valid, h[None, :] / np.where(valid, cosd, 1), np.inf).min(1)
    return {"N": s["n"], "C": (float(C[0]), float(C[1])), "seat_above_rin": seat,
            "pocket_depth": s["pocket"], "pocket_apex": None if s.get("gallery") else -s["pocket"],
            "windows": windows, "win_size": (s["win_w"], s["win_h"]), "cup": [(float(z), r.tolist()) for z, r in cup],
            "pocket": [(float(z), r.tolist()) for z, r in pocket], "stone_outline": [(0.0, stone_r.tolist())],
            "stone_size": (L, stone["ratio"] * L)}


def _loops(data, key):
    return data[key]


def _loft(name, data, loops, apex_z=None):
    """Closed solid from stacked loops (top -> bottom); optional apex point closes the bottom."""
    n, (cx, cy) = data["N"], data["C"]
    th = [2 * math.pi * i / n for i in range(n)]
    bm = bmesh.new()
    rings = [[bm.verts.new((cx + r * math.sin(t), cy + r * math.cos(t), z)) for t, r in zip(th, rr)]
             for z, rr in loops]
    for a, b in zip(rings, rings[1:]):
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((a[i], a[j], b[j], b[i]))
    bm.faces.new(rings[0])
    if apex_z is None:
        bm.faces.new(list(reversed(rings[-1])))
    else:
        av = bm.verts.new((cx, cy, apex_z))
        for i in range(n):
            bm.faces.new((rings[-1][i], rings[-1][(i + 1) % n], av))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return me


def _cylinder_y(name, radius, length=60.0, segments=256):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments,
                          radius1=radius, radius2=radius, depth=length,
                          matrix=Matrix.Rotation(math.pi / 2, 4, 'X'))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return me


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


def _bool(target, operand, op, solver='MANIFOLD'):
    m = target.modifiers.new(f"{op}_{operand.name}", 'BOOLEAN')
    m.operation, m.object, m.solver = op, operand, solver
    return m


def build_ring(size, data, collection, x=0.0, label=True, material=None, extras=None):
    jk = sys.modules["jewelry_kit"]
    r_in = jk.us_size_to_inner_diameter_mm(size) / 2
    r_out = r_in + BAND["Thickness"]
    z_seat = r_in + data["seat_above_rin"]
    tmp = bpy.data.collections.new("_tmp_build")
    bpy.context.scene.collection.children.link(tmp)

    band = jk.add_ring("_band", tmp, **{"US Size": size, **BAND})
    cup = bpy.data.objects.new("_cup", _loft("_cup", data, _loops(data, "cup")))
    pocket = bpy.data.objects.new("_pocket", _loft("_pocket", data, _loops(data, "pocket"),
                                                   apex_z=data.get("pocket_apex", -data["pocket_depth"])))
    finger = bpy.data.objects.new("_finger", _cylinder_y("_finger", r_in + 0.6))
    for o in (cup, pocket, finger):
        tmp.objects.link(o)
    cup.location.z = pocket.location.z = z_seat

    _bool(cup, finger, 'DIFFERENCE')        # keep 0.6 mm clear of the finger
    _bool(cup, band, 'UNION')
    if extras is not None:                  # decorations join before the seat and gallery are cut
        m = cup.modifiers.new("extras", 'BOOLEAN')
        m.operation, m.operand_type, m.solver = 'UNION', 'COLLECTION', 'MANIFOLD'
        m.collection = extras
    _bool(cup, pocket, 'DIFFERENCE')
    ww, wh = data.get("win_size", (1.3, 1.9))
    for k, (mx, my, wz, nx, ny) in enumerate(data.get("windows", [])):
        normal = Vector((nx, ny, 0.0))                          # wall normal, outward
        tang = Vector((-ny, nx, 0.0))                           # right-handed with Z = normal
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=40, radius1=1.0, radius2=1.0, depth=3.0)
        bmesh.ops.scale(bm, vec=(ww / 2, wh / 2, 1.0), verts=bm.verts)
        basis = Matrix((tang, Vector((0.0, 0.0, 1.0)), normal)).transposed().to_4x4()
        centre = Vector((mx, my, z_seat + wz))
        bm.transform(Matrix.Translation(centre) @ basis)
        wme = bpy.data.meshes.new(f"_win{k}")
        bm.to_mesh(wme)
        bm.free()
        win = bpy.data.objects.new(f"_win{k}", wme)
        tmp.objects.link(win)
        _bool(cup, win, 'DIFFERENCE')
    if label:
        lab = bpy.data.objects.new("_label", _label_mesh(_size_text(size)))
        tmp.objects.link(lab)
        lab.rotation_euler = (math.pi, 0.0, 0.0)          # reads correctly from outside/below
        lab.location = (0.0, 0.0, -r_out + LABEL_DEPTH - 0.6)
        _bool(cup, lab, 'DIFFERENCE')
    bpy.context.view_layer.update()

    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(cup.evaluated_get(dg), depsgraph=dg)
    me.transform(cup.matrix_world)
    name = f"Pear ring US {_size_text(size)}"
    me.name = name
    old = bpy.data.objects.get(name)
    if old:
        bpy.data.objects.remove(old)
    ring = bpy.data.objects.new(name, me)
    collection.objects.link(ring)
    ring.location.x = x
    if material:
        me.materials.clear()
        me.materials.append(material)
    me.shade_smooth()
    me.set_sharp_from_angle(angle=math.radians(35))

    # clean up scratch objects/meshes
    for o in list(tmp.objects):
        data_block = o.data
        bpy.data.objects.remove(o)
        if data_block and data_block.users == 0:
            (bpy.data.meshes if isinstance(data_block, bpy.types.Mesh) else bpy.data.curves).remove(data_block)
    bpy.data.collections.remove(tmp)
    return ring


def stone_preview(data, collection, x=0.0, size=None, crown=1.4, girdle=0.2, pavilion=3.0):
    """Rough glass pear (for looks only) sitting in the seat of a ring of the given size."""
    jk = sys.modules["jewelry_kit"]
    outline = _loops(data, "stone_outline")[0][1]
    loops = [(girdle + crown, [0.55 * r for r in outline]), (girdle, outline), (0.0, outline)]
    me = _loft("Stone preview", data, loops, apex_z=-pavilion)
    ob = bpy.data.objects.new("Stone preview (not for printing)", me)
    collection.objects.link(ob)
    if size is not None:
        ob.location = (x, 0.0, jk.us_size_to_inner_diameter_mm(size) / 2 + data["seat_above_rin"] - 0.1)
    mat = bpy.data.materials.get("Glass stone (preview)") or bpy.data.materials.new("Glass stone (preview)")
    if not mat.node_tree:
        mat.use_nodes = True
    b = mat.node_tree.nodes.get("Principled BSDF")
    b.inputs['Base Color'].default_value = (1, 1, 1, 1)
    b.inputs['Roughness'].default_value = 0.02
    b.inputs['IOR'].default_value = 1.6
    tw = b.inputs.get('Transmission Weight') or b.inputs.get('Transmission')
    tw.default_value = 1.0
    mat.diffuse_color = (0.8, 0.9, 1.0, 0.4)
    me.materials.append(mat)
    return ob


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
