"""Jewelry kit for Blender 5.1+.

- setup_mm_workspace(): 1 Blender unit = 1 mm, so STL exports come out in millimetres.
- add_ring(): a parametric ring (Geometry Nodes modifier) sized by US ring size.
- check_model(): print/cast readiness report (watertight, size, volume, metal weight)
  plus a colour-coded wall-thickness map placed beside the model.

Design thresholds follow Formlabs' "Jewelry 3D Printing: Basic Design Parameters":
0.5 mm walls cast but distort slightly; 0.75 mm worked well. Metal specific gravities are
typical values from jewelers (alloy-dependent), so weights are estimates.
"""
import bpy
import bmesh
import math
from mathutils import Vector
from mathutils.bvhtree import BVHTree

WALL_MIN_MM = 0.5      # below this: unlikely to cast cleanly
WALL_GOOD_MM = 0.75    # at or above this: comfortable
METALS = {             # specific gravity, g/cm^3
    "Sterling silver": 10.4,
    "14K yellow gold": 13.07,
    "14K white gold": 12.6,
    "18K yellow gold": 15.58,
    "Bronze": 8.8,
    "Brass": 8.4,
}
SPRUE_ALLOWANCE = 0.20  # extra metal for sprue and button (jewelers cite 15-25%)
RING_GROUP = "Ring (parametric)"


def us_size_to_inner_diameter_mm(size):
    """US/Canada ring size -> inner diameter in mm (0.458 in + 0.032 in per size)."""
    return 11.63 + 0.8128 * size


def mm_per_unit(scene=None):
    scene = scene or bpy.context.scene
    us = scene.unit_settings
    return (us.scale_length if us.system != 'NONE' else 1.0) * 1000.0


# ----------------------------------------------------------------------------- workspace
def setup_mm_workspace(scene=None):
    """Millimetre units and viewport clipping suited to small parts."""
    scene = scene or bpy.context.scene
    us = scene.unit_settings
    us.system = 'METRIC'
    us.length_unit = 'MILLIMETERS'
    us.scale_length = 0.001
    wm = bpy.context.window_manager
    for win in (wm.windows if wm else []):
        for area in win.screen.areas:
            if area.type != 'VIEW_3D':
                continue
            for sp in area.spaces:
                if sp.type == 'VIEW_3D':
                    sp.clip_start = 0.01
                    sp.clip_end = 10000.0
    return scene


# ----------------------------------------------------------------------------- materials
def preview_material(name="Silver (preview)"):
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name)
    if not mat.node_tree:
        mat.use_nodes = True
    b = mat.node_tree.nodes.get("Principled BSDF")
    b.inputs['Base Color'].default_value = (0.92, 0.92, 0.91, 1.0)
    b.inputs['Metallic'].default_value = 1.0
    b.inputs['Roughness'].default_value = 0.18
    mat.diffuse_color = (0.85, 0.85, 0.85, 1.0)
    mat.metallic, mat.roughness = 1.0, 0.25
    return mat


# ----------------------------------------------------------------------------- ring
def ring_node_group():
    """Band swept around the finger: profile = domed outside + comfort-relieved inside."""
    ng = bpy.data.node_groups.get(RING_GROUP)
    if ng:
        return ng
    ng = bpy.data.node_groups.new(RING_GROUP, 'GeometryNodeTree')
    try:
        ng.is_modifier = True
    except AttributeError:
        pass
    io = ng.interface
    io.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    specs = [
        ("US Size", 'NodeSocketFloat', 10.0, 0.0, 16.0, "Finished ring size (US/Canada)"),
        ("Size Allowance", 'NodeSocketFloat', 0.25, -2.0, 2.0,
         "Extra sizes to offset casting shrinkage. Set 0 for a fit-test print"),
        ("Width", 'NodeSocketFloat', 5.0, 1.0, 25.0, "Band width along the finger (mm)"),
        ("Thickness", 'NodeSocketFloat', 1.6, 0.5, 6.0, "Finished band thickness at the centre (mm)"),
        ("Finish Stock", 'NodeSocketFloat', 0.2, 0.0, 1.0,
         "Extra outside thickness removed by cleanup and polishing (mm)"),
        ("Outer Dome", 'NodeSocketFloat', 0.5, 0.0, 3.0,
         "How far the outside falls toward the edges (mm). 0 = flat band"),
        ("Comfort Relief", 'NodeSocketFloat', 0.25, 0.0, 1.5,
         "How far the inside relieves toward the edges (mm). 0 = flat inside"),
        ("Segments", 'NodeSocketInt', 192, 16, 1024, "Divisions around the ring"),
        ("Profile Points", 'NodeSocketInt', 24, 4, 128, "Points per side of the cross-section"),
    ]
    for nm, st, d, lo, hi, desc in specs:
        s = io.new_socket(nm, in_out='INPUT', socket_type=st)
        s.default_value, s.min_value, s.max_value = d, lo, hi
        s.description = desc
    io.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')

    N, L = ng.nodes, ng.links
    gi, go = N.new('NodeGroupInput'), N.new('NodeGroupOutput')
    G = gi.outputs

    def m(op, a, b=None):
        n = N.new('ShaderNodeMath')
        n.operation = op
        for i, v in enumerate((a, b)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                n.inputs[i].default_value = float(v)
            else:
                L.new(v, n.inputs[i])
        return n.outputs[0]

    def lerp(a, b, t):  # a + t*(b-a)
        return m('ADD', a, m('MULTIPLY', t, m('SUBTRACT', b, a)))

    P = G['Profile Points']
    size = m('ADD', G['US Size'], G['Size Allowance'])
    r_in = m('MULTIPLY', m('ADD', m('MULTIPLY', size, 0.8128), 11.63), 0.5)
    t_tot = m('ADD', G['Thickness'], G['Finish Stock'])
    half_w = m('MULTIPLY', G['Width'], 0.5)
    relief = G['Comfort Relief']
    # keep at least 0.3 mm at the band edge whatever the dome/relief settings
    dome = m('MAXIMUM', m('MINIMUM', G['Outer Dome'], m('SUBTRACT', m('SUBTRACT', t_tot, relief), 0.3)), 0.0)

    # (Segments+1) x (2P+1) grid; x -> angle around the finger, y -> walk around the profile
    grid = N.new('GeometryNodeMeshGrid')
    grid.inputs['Size X'].default_value = 1.0
    grid.inputs['Size Y'].default_value = 1.0
    L.new(m('ADD', G['Segments'], 1), grid.inputs['Vertices X'])
    two_p = m('MULTIPLY', P, 2)
    L.new(m('ADD', two_p, 1), grid.inputs['Vertices Y'])

    pos = N.new('GeometryNodeInputPosition').outputs[0]
    sep = N.new('ShaderNodeSeparateXYZ')
    L.new(pos, sep.inputs[0])
    u = m('MULTIPLY', m('ADD', sep.outputs['X'], 0.5), 2 * math.pi)
    j = m('FLOORED_MODULO', m('ROUND', m('MULTIPLY', m('ADD', sep.outputs['Y'], 0.5), two_p)), two_p)
    outer = m('LESS_THAN', j, P)                  # 1 = outside surface, 0 = inside surface
    p1 = m('SUBTRACT', P, 1)
    a_out = m('SUBTRACT', m('MULTIPLY', m('DIVIDE', j, p1), G['Width']), half_w)
    a_in = m('SUBTRACT', half_w, m('MULTIPLY', m('DIVIDE', m('SUBTRACT', j, P), p1), G['Width']))
    a = lerp(a_in, a_out, outer)                  # position across the band (mm)
    s = m('POWER', m('DIVIDE', a, half_w), 2.0)   # 0 at centre line, 1 at the edges
    r_outer = m('SUBTRACT', m('ADD', r_in, t_tot), m('MULTIPLY', dome, s))
    r_inner = m('ADD', r_in, m('MULTIPLY', relief, s))
    r = lerp(r_inner, r_outer, outer)

    comb = N.new('ShaderNodeCombineXYZ')          # ring axis along Y (stands upright in front view)
    L.new(m('MULTIPLY', r, m('COSINE', u)), comb.inputs['X'])
    L.new(a, comb.inputs['Y'])
    L.new(m('MULTIPLY', r, m('SINE', u)), comb.inputs['Z'])

    setpos = N.new('GeometryNodeSetPosition')
    L.new(grid.outputs['Mesh'], setpos.inputs['Geometry'])
    L.new(comb.outputs[0], setpos.inputs['Position'])
    weld = N.new('GeometryNodeMergeByDistance')   # closes the seams -> watertight band
    weld.inputs['Distance'].default_value = 0.001
    L.new(setpos.outputs[0], weld.inputs['Geometry'])
    flip = N.new('GeometryNodeFlipFaces')         # grid winding points inward; make normals face out
    L.new(weld.outputs[0], flip.inputs['Mesh'])

    smooth = N.new('GeometryNodeSetShadeSmooth')
    smooth.domain = 'FACE'
    smooth.inputs['Shade Smooth'].default_value = True
    L.new(flip.outputs[0], smooth.inputs['Mesh'])
    crisp = N.new('GeometryNodeSetShadeSmooth')   # keep the band edges crisp
    crisp.domain = 'EDGE'
    crisp.inputs['Shade Smooth'].default_value = False
    angle = N.new('GeometryNodeInputMeshEdgeAngle').outputs['Unsigned Angle']
    L.new(m('GREATER_THAN', angle, math.radians(35)), crisp.inputs['Selection'])
    L.new(smooth.outputs[0], crisp.inputs['Mesh'])
    setmat = N.new('GeometryNodeSetMaterial')
    setmat.inputs['Material'].default_value = preview_material()
    L.new(crisp.outputs[0], setmat.inputs['Geometry'])
    L.new(setmat.outputs[0], go.inputs['Geometry'])

    for i, n in enumerate(N):                      # rough layout so the tree is browsable
        n.location = ((i % 12) * 190, -(i // 12) * 220)
    gi.location, go.location = (-300, 0), (12 * 190, 0)
    return ng


def set_inputs(mod, **values):
    """Set Geometry Nodes modifier inputs by their UI names, e.g. set_inputs(mod, **{'US Size': 9.5})."""
    by_name = {it.name: it for it in mod.node_group.interface.items_tree
               if it.item_type == 'SOCKET' and it.in_out == 'INPUT'}
    inputs = getattr(getattr(mod, "properties", None), "inputs", None)   # Blender 5.2+ API
    for name, v in values.items():
        it = by_name[name]
        v = int(v) if it.socket_type == 'NodeSocketInt' else float(v)
        holder = getattr(inputs, it.identifier, None) if inputs is not None else None
        if holder is not None:
            holder.value = v
        else:                                                             # older ID-property API
            mod[it.identifier] = v
    mod.id_data.update_tag()


def get_inputs(mod):
    out = {}
    inputs = getattr(getattr(mod, "properties", None), "inputs", None)
    for it in mod.node_group.interface.items_tree:
        if it.item_type == 'SOCKET' and it.in_out == 'INPUT' and it.socket_type != 'NodeSocketGeometry':
            holder = getattr(inputs, it.identifier, None) if inputs is not None else None
            out[it.name] = holder.value if holder is not None else mod.get(it.identifier)
    return out


def add_ring(name="Ring", collection=None, **values):
    me = bpy.data.meshes.new(name)
    ob = bpy.data.objects.new(name, me)
    (collection or bpy.context.scene.collection).objects.link(ob)
    mod = ob.modifiers.new("Ring", 'NODES')
    mod.node_group = ring_node_group()
    if values:
        set_inputs(mod, **values)
    return ob


# ----------------------------------------------------------------------------- checks
def _shells(bm):
    seen, count = set(), 0
    for f in bm.faces:
        if f.index in seen:
            continue
        count += 1
        stack = [f]
        seen.add(f.index)
        while stack:
            for e in stack.pop().edges:
                for g in e.link_faces:
                    if g.index not in seen:
                        seen.add(g.index)
                        stack.append(g)
    return count


def _map_material():
    name = "Wall thickness map"
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name)
    if not mat.node_tree:
        mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes.get("Principled BSDF")
    b.inputs['Roughness'].default_value = 0.6
    attr = nt.nodes.new('ShaderNodeVertexColor')
    attr.layer_name = "Wall thickness"
    attr.location = (-300, 200)
    nt.links.new(attr.outputs['Color'], b.inputs['Base Color'])
    return mat


def check_model(obj, make_map=True, wall_min=WALL_MIN_MM, wall_good=WALL_GOOD_MM):
    """Print/cast readiness report for obj (modifiers applied). Returns (text, data)."""
    k = mm_per_unit()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.transform(obj.matrix_world)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    bm.normal_update()

    open_edges = sum(1 for e in bm.edges if not e.is_manifold)
    shells = _shells(bm)
    vol_signed = bm.calc_volume(signed=True) * k ** 3            # mm^3
    vol = abs(vol_signed)
    lo = Vector((min(v.co[i] for v in bm.verts) for i in range(3)))
    hi = Vector((max(v.co[i] for v in bm.verts) for i in range(3)))
    dims = (hi - lo) * k

    # wall thickness: ray from each vertex straight into the part
    tree = BVHTree.FromBMesh(bm)
    eps = 1e-5 / k
    thick = []
    for v in bm.verts:
        n = v.normal if vol_signed >= 0 else -v.normal
        adj = {f.index for f in v.link_faces}
        origin, travelled, t = v.co - n * eps, eps, float('inf')
        for _ in range(4):        # step past grazing hits on the vertex's own faces (sliver corners)
            hit = tree.ray_cast(origin, -n)
            if hit[0] is None:
                break
            if hit[2] in adj and hit[3] < 0.05 / k:
                origin, travelled = hit[0] - n * eps, travelled + hit[3] + eps
                continue
            t = (travelled + hit[3]) * k
            break
        thick.append(t)
    finite = sorted(t for t in thick if math.isfinite(t))
    tmin = finite[0] if finite else float('nan')
    p01 = finite[int(0.01 * (len(finite) - 1))] if finite else float('nan')
    below_min = sum(1 for t in finite if t < wall_min) / max(len(finite), 1)
    below_good = sum(1 for t in finite if t < wall_good) / max(len(finite), 1)
    thin_at = bm.verts[thick.index(tmin)].co * k if finite else None
    bm.free()
    ev.to_mesh_clear()

    cm3 = vol / 1000.0
    data = dict(name=obj.name, watertight=(open_edges == 0), open_edges=open_edges, shells=shells,
                normals_out=(vol_signed > 0), dims_mm=tuple(dims), volume_mm3=vol, resin_ml=cm3,
                wall_min_mm=tmin, wall_p01_mm=p01, frac_below_min=below_min, frac_below_good=below_good,
                metals={m: (cm3 * sg, cm3 * sg * (1 + SPRUE_ALLOWANCE)) for m, sg in METALS.items()})

    ok = lambda b: "OK" if b else "PROBLEM"
    wall_flag = ("OK" if tmin >= wall_good else
                 "MARGINAL (castable, may distort)" if tmin >= wall_min else "TOO THIN to cast reliably")
    lines = [
        f"== {obj.name}: print/cast check ==",
        f"Watertight: {ok(open_edges == 0)} ({open_edges} open/non-manifold edges); "
        f"pieces: {shells}; normals outward: {ok(vol_signed > 0)}",
        f"Size: {dims.x:.2f} x {dims.y:.2f} x {dims.z:.2f} mm",
        f"Volume: {vol:,.1f} mm^3 = {cm3:.3f} ml of resin (model only, before supports)",
        f"Thinnest wall: {tmin:.2f} mm -> {wall_flag}"
        + (f" near ({thin_at.x:.1f}, {thin_at.y:.1f}, {thin_at.z:.1f}) mm" if thin_at is not None and tmin < wall_good else ""),
        f"  1% of surface is under {p01:.2f} mm; {below_min:.1%} under {wall_min} mm; "
        f"{below_good:.1%} under {wall_good} mm",
        f"Estimated metal (piece / to melt incl. {SPRUE_ALLOWANCE:.0%} sprue+button):",
    ]
    lines += [f"  {m:<16} {a:6.2f} g / {b:6.2f} g" for m, (a, b) in data['metals'].items()]
    text = "\n".join(lines)

    if make_map:
        map_name = f"{obj.name} - wall thickness"
        old = bpy.data.objects.get(map_name)
        if old:
            bpy.data.objects.remove(old, do_unlink=True)
        mm = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=False, depsgraph=dg)
        mm.name = map_name
        col = mm.color_attributes.new("Wall thickness", 'FLOAT_COLOR', 'POINT')
        red, amber, green = (0.85, 0.07, 0.06, 1), (0.98, 0.62, 0.05, 1), (0.12, 0.62, 0.28, 1)
        flat = []
        for t in thick:
            flat += red if t < wall_min else amber if t < wall_good else green
        col.data.foreach_set("color", flat)
        mm.color_attributes.active_color = col
        mm.materials.clear()
        mm.materials.append(_map_material())
        mob = bpy.data.objects.new(map_name, mm)
        for c in obj.users_collection:
            c.objects.link(mob)
        mob.matrix_world = obj.matrix_world.copy()
        mob.location.x += (dims.x / k) + 4.0 / k               # park it beside the model
        data['map_object'] = mob.name
    return text, data
