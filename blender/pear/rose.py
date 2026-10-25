"""Procedural rose (Blender 5.1+): spiral bud + three rings of cupped petals on a small base.

Rose-local frame: axis +Z, base at z=0. Petals are surfaces wrapped around the axis, given
thickness with a Solidify modifier, then unioned (manifold solver) into one closed solid.
Sizes in mm (1 Blender unit = 1 mm).
"""
import bpy, bmesh, math
from mathutils import Matrix, Vector

PETAL_T = 0.55   # petal thickness (>= 0.5 mm for strength)
# (count, start angle deg, base radius, outward reach, angular half-span rad, height, curl, lift)
LAYERS = [
    (3, 0, 0.30, 0.15, 1.90, 2.30, 0.05, 0.00),   # bud: tightly wrapped, staggered outward
    (4, 45, 0.72, 0.35, 0.95, 2.20, 0.12, 0.00),
    (5, 18, 1.12, 0.60, 0.78, 2.00, 0.22, -0.05),
    (5, 54, 1.48, 0.95, 0.72, 1.75, 0.35, -0.12),   # outer petals cup up, lips roll out
]


def _shape(v):
    """Petal width profile: narrow base, full belly, rounded top."""
    return max(0.12, math.sin(math.pi * (0.12 + 0.85 * v))) ** 0.7


def _petal_surface(alpha, rb, ro, span, height, curl, lift, twist=0.25, nu=16, nv=14):
    bm = bmesh.new()
    grid = []
    for j in range(nv):
        v = j / (nv - 1)
        row = []
        for i in range(nu):
            u = -1 + 2 * i / (nu - 1)
            r = rb + ro * v ** 1.6
            c = max(0.0, v - 0.68) / 0.32                    # 0 -> 1 over the top third
            r += curl * c * c                                 # lip rolls outward
            r -= 0.12 * u * u * v                             # slight extra cup at the edges
            z = lift + height * v - 0.6 * curl * c * c + 0.15 * u * u * v * height / 2
            a = alpha + twist * v + u * span * _shape(v)
            row.append(bm.verts.new((r * math.cos(a), r * math.sin(a), z)))
        grid.append(row)
    for j in range(nv - 1):
        for i in range(nu - 1):
            bm.faces.new((grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]))
    me = bpy.data.meshes.new("_petal")
    bm.to_mesh(me)
    bm.free()
    return me


def clean_mesh(me, min_volume=1e-3):
    """Drop zero-volume debris shells left by booleans, weld and remove degenerate faces."""
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-6)
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
    loose = [v for v in bm.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context='VERTS')
    bm.to_mesh(me)
    bm.free()
    return len(junk)


def build_rose(name="Rose", collection=None, scale=1.0, voxel=0.04, keep=0.3):
    """Returns a single closed mesh object (modifiers applied), rose-local coordinates.
    The petal union is voxel-remeshed (fuses petal contacts into one clean, watertight skin)
    and then decimated to keep the file light."""
    scene_col = bpy.context.scene.collection
    tmp = bpy.data.collections.new("_rose_parts")
    scene_col.children.link(tmp)
    parts = []
    for li, (count, a0, rb, ro, span, h, curl, lift) in enumerate(LAYERS):
        for k in range(count):
            alpha = math.radians(a0) + 2 * math.pi * k / count
            rb_k = rb + (0.12 * k if li == 0 else 0.0)        # bud petals spiral outward
            h_k = h - (0.1 * k if li == 0 else 0.0)
            ob = bpy.data.objects.new(f"_p{li}_{k}", _petal_surface(alpha, rb_k, ro, span, h_k, curl, lift))
            tmp.objects.link(ob)
            sub = ob.modifiers.new("s", 'SUBSURF')
            sub.levels = sub.render_levels = 1
            sol = ob.modifiers.new("t", 'SOLIDIFY')
            sol.thickness, sol.offset, sol.use_rim, sol.use_even_offset = PETAL_T, 0.0, True, True
            parts.append(ob)
    # receptacle: squat rounded base that ties every petal together
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=1.0)
    bmesh.ops.scale(bm, vec=(1.55, 1.55, 0.7), verts=bm.verts)
    bmesh.ops.translate(bm, vec=(0, 0, -0.1), verts=bm.verts)
    me = bpy.data.meshes.new("_base")
    bm.to_mesh(me)
    bm.free()
    base = bpy.data.objects.new("_base", me)
    tmp.objects.link(base)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=32, radius1=0.42, radius2=0.22, depth=1.9,
                          matrix=Matrix.Translation((0, 0, 0.95)))
    me = bpy.data.meshes.new("_core")
    bm.to_mesh(me)
    bm.free()
    core = bpy.data.objects.new("_core", me)
    tmp.objects.link(core)
    parts.append(core)

    union = base.modifiers.new("petals", 'BOOLEAN')
    union.operation, union.operand_type, union.solver = 'UNION', 'COLLECTION', 'MANIFOLD'
    petal_col = bpy.data.collections.new("_petals")
    for p in parts:
        tmp.objects.unlink(p)
        petal_col.objects.link(p)
    union.collection = petal_col
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    fused = bpy.data.meshes.new_from_object(base.evaluated_get(dg), depsgraph=dg)
    fused.transform(Matrix.Scale(scale, 4))
    skin = bpy.data.objects.new("_skin", fused)
    tmp.objects.link(skin)
    rm = skin.modifiers.new("remesh", 'REMESH')
    rm.mode, rm.voxel_size, rm.adaptivity = 'VOXEL', voxel, 0.0
    dec = skin.modifiers.new("decimate", 'DECIMATE')
    dec.decimate_type, dec.ratio = 'COLLAPSE', keep
    sm = skin.modifiers.new("smooth", 'LAPLACIANSMOOTH')
    sm.lambda_factor, sm.iterations, sm.use_volume_preserve = 0.6, 4, True
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    out = bpy.data.meshes.new_from_object(skin.evaluated_get(dg), depsgraph=dg)
    clean_mesh(out)
    out.name = name
    for ob in list(petal_col.objects) + list(tmp.objects):
        d = ob.data
        bpy.data.objects.remove(ob)
        if d and d.users == 0:
            bpy.data.meshes.remove(d)
    bpy.data.collections.remove(petal_col)
    bpy.data.collections.remove(tmp)
    rose = bpy.data.objects.new(name, out)
    (collection or scene_col).objects.link(rose)
    return rose
