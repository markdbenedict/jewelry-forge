"""Pear bezel ring with a rose on each shoulder (needs jewelry_kit, pear_setting, rose loaded).

One rose is built, then placed twice: on the right shoulder, tilted outward-up, and a copy turned
180 degrees about the ring's vertical axis for the left. A short stem anchors each rose into
the band, and two leaves per rose climb from under it toward the gem. Everything is unioned into one watertight solid.
"""
import bpy, bmesh, math, sys
from mathutils import Matrix, Vector

ROSE = dict(x=7.0, z_above_rin=0.05, tilt_deg=55.0, spin_deg=18.0, scale=1.15, stem_r=1.2)
LEAF = dict(length=5.2, width=2.9, thick=0.5, start=1.6, sink=0.3, splay_deg=40.0, lift_deg=12.0,
            arch=0.35, fold=0.5, curl=0.25, teeth=12, veins=5,   # two leaves per rose, climbing to the gem
            vein_mid=0.26, vein_lat=0.18, vein_w_mid=0.12, vein_w_lat=0.085)
# veins: the leaf sheet is pressed down along a midrib and one side vein per serration tooth, so
# they show as grooves on top (ridges underneath) while the leaf stays its full thickness.


def _envelope(u, width):
    """Leaf half-width along its length (no serrations), u = 0 base .. 1 tip."""
    return max(0.16, (width / 2) * math.sin(math.pi * u) ** 0.8 * (1.15 - 0.3 * u))


def _vein_depth(x, y, length, width, veins, vein_mid, vein_lat, vein_w_mid, vein_w_lat):
    u = x / length
    depth = vein_mid * math.exp(-(y / vein_w_mid) ** 2) * min(1.0, (1.0 - u) / 0.15, u / 0.05)
    for k in range(1, veins + 1):
        ue = k / (veins + 1)                               # ends at a serration tooth
        us = ue - 0.16                                     # leaves the midrib further back
        if us < 0.04:
            continue
        x0, x1 = us * length, ue * length - 0.05
        for side in (1, -1):
            y1 = side * 0.82 * _envelope(ue, width)
            dx, dy = x1 - x0, y1
            t = max(0.0, min(1.0, ((x - x0) * dx + y * dy) / (dx * dx + dy * dy)))
            dist = math.hypot(x - (x0 + t * dx), y - t * dy)
            fade = min(1.0, (1.0 - t) / 0.25)              # fades out before the edge
            depth = max(depth, vein_lat * fade * math.exp(-(dist / vein_w_lat) ** 2))
    return depth


def _leaf(name, matrix, tmp, length, width, thick, arch, fold, curl, teeth=0, veins=5, nu=120, nv=61,
          vein_mid=0.0, vein_lat=0.0, vein_w_mid=0.1, vein_w_lat=0.07, **_):
    """Pointed oval leaf: centre fold (midrib), gentle arch, small forward-pointing serrations.
    Base at the origin, tip along +X."""
    bm = bmesh.new()
    rows = []
    for i in range(nu):
        u = i / (nu - 1)
        hw = _envelope(u, width)
        if teeth and 0.15 < u < 0.92:
            hw *= 1.0 - 0.07 * ((u * teeth) % 1.0) ** 1.5       # fine serrations, pointing to the tip
        row = []
        for j in range(nv):
            v = -1 + 2 * j / (nv - 1)
            z = arch * math.sin(math.pi * u) + fold * abs(v) ** 1.5 * hw / (width / 2) - curl * u ** 3
            if vein_mid or vein_lat:
                z -= _vein_depth(u * length, v * hw, length, width, veins, vein_mid, vein_lat,
                                 vein_w_mid, vein_w_lat)
            row.append(bm.verts.new((u * length, v * hw, z)))
        rows.append(row)
    for i in range(nu - 1):
        for j in range(nv - 1):
            bm.faces.new((rows[i][j], rows[i][j + 1], rows[i + 1][j + 1], rows[i + 1][j]))
    bm.transform(matrix)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    tmp.objects.link(ob)
    sol = ob.modifiers.new("t", 'SOLIDIFY')
    sol.thickness, sol.offset, sol.use_rim, sol.use_even_offset = thick, 0.0, True, True
    return ob


def _leaf_frame(phi, lift, start, sink):
    """Leaf placement in rose-local coordinates (rose axis +Z)."""
    d = Vector((math.cos(phi) * math.cos(lift), math.sin(phi) * math.cos(lift), math.sin(lift)))
    z = Vector((0.0, 0.0, 1.0))
    z = (z - d * z.dot(d)).normalized()
    y = z.cross(d)
    m = Matrix((d, y, z)).transposed().to_4x4()
    m.translation = Vector((start * math.cos(phi), start * math.sin(phi), -sink))
    return m


def _fuse(objects, name, collection, voxel=0.03, keep=0.45):
    """Union objects, voxel-remesh the result into one clean watertight skin, then decimate.
    Removes the knife-edge contacts that appear where leaves, stems and petals just touch."""
    jk_rs = sys.modules["rose"]
    base, rest = objects[0], objects[1:]
    ops = bpy.data.collections.new("_fuse_ops")
    bpy.context.scene.collection.children.link(ops)
    for o in rest:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        ops.objects.link(o)
    u = base.modifiers.new("u", 'BOOLEAN')
    u.operation, u.operand_type, u.solver = 'UNION', 'COLLECTION', 'MANIFOLD'
    u.collection = ops
    rm = base.modifiers.new("rm", 'REMESH')
    rm.mode, rm.voxel_size, rm.adaptivity = 'VOXEL', voxel, 0.0
    dec = base.modifiers.new("dec", 'DECIMATE')
    dec.decimate_type, dec.ratio = 'COLLAPSE', keep
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(base.evaluated_get(dg), depsgraph=dg)
    jk_rs.clean_mesh(me)
    for o in list(ops.objects) + [base]:
        d = o.data
        bpy.data.objects.remove(o)
        if d and d.users == 0:
            bpy.data.meshes.remove(d)
    bpy.data.collections.remove(ops)
    me.name = name
    ob = bpy.data.objects.new(name, me)
    collection.objects.link(ob)
    return ob


def _stem(start, end, radius):
    """Cylinder from start to end (world coordinates)."""
    start, end = Vector(start), Vector(end)
    axis = end - start
    rot = axis.to_track_quat('Z', 'Y').to_matrix().to_4x4()
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=48, radius1=radius, radius2=radius,
                          depth=axis.length, matrix=Matrix.Translation((start + end) / 2) @ rot)
    me = bpy.data.meshes.new("_stem")
    bm.to_mesh(me)
    bm.free()
    return me


def build(size=5.0, collection=None, material=None, name=None):
    jk, ps, rs = (sys.modules[m] for m in ("jewelry_kit", "pear_setting", "rose"))
    col = collection or bpy.context.scene.collection
    data = ps.make_loops()
    r_in = jk.us_size_to_inner_diameter_mm(size) / 2
    r_mid = r_in + ps.BAND["Thickness"] / 2
    beta = math.radians(ROSE["tilt_deg"])
    rose_src = rs.build_rose("_rose_src", scale=ROSE["scale"])
    deco = bpy.data.collections.new("_decor")
    bpy.context.scene.collection.children.link(deco)
    for side in (1, -1):
        base = (Matrix.Translation((side * ROSE["x"], 0.0, r_in + ROSE["z_above_rin"]))
                @ Matrix.Rotation(0 if side > 0 else math.pi, 4, 'Z')
                @ Matrix.Rotation(math.pi / 2 - beta, 4, 'Y'))
        place = base @ Matrix.Rotation(math.radians(ROSE["spin_deg"]), 4, 'Z')
        group = bpy.data.collections.new("_group")
        bpy.context.scene.collection.children.link(group)
        centre = place.to_translation()
        anchor = Vector((centre.x, 0.0, centre.z)).normalized() * r_mid   # straight into the band
        stem = bpy.data.objects.new(f"_stem{side}", _stem(centre, anchor, ROSE["stem_r"]))
        group.objects.link(stem)
        me = rose_src.data.copy()
        me.transform(place)
        rose = bpy.data.objects.new(f"_rose{side}", me)
        group.objects.link(rose)
        leaves = []
        for k, sgn in enumerate((1, -1)):                     # rose-local -X points at the gem
            phi = math.pi + sgn * math.radians(LEAF["splay_deg"])
            frame = _leaf_frame(phi, math.radians(LEAF["lift_deg"]), LEAF["start"], LEAF["sink"])
            leaves.append(_leaf(f"_leaf{side}{k}", base @ frame, group, **LEAF))
        _fuse([stem, rose] + leaves, f"_decor{side}", deco)   # one clean solid per side
        bpy.data.collections.remove(group)
    bpy.data.objects.remove(rose_src)

    ring = ps.build_ring(size, data, col, x=0.0, material=material, extras=deco)
    rs.clean_mesh(ring.data)
    for o in list(deco.objects):
        d = o.data
        bpy.data.objects.remove(o)
        if d and d.users == 0:
            bpy.data.meshes.remove(d)
    bpy.data.collections.remove(deco)
    ring.name = ring.data.name = name or f"Pear rose ring US {ps._size_text(size)}"
    if material:
        ring.data.materials.clear()
        ring.data.materials.append(material)
    ring.data.shade_smooth()
    ring.data.set_sharp_from_angle(angle=math.radians(35))
    return ring
