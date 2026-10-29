"""Jewelry product shot for the monstera rings (Blender 5.1+, Cycles).

setup(scene, rings): polished-silver material, a glossy dark sweep, three softboxes and a strip
light for the long highlights metal needs, a macro camera with shallow focus, and render settings.
The rings themselves are not moved: posed linked copies live in a "Photo setup" collection that
is hidden in the viewport, and the originals' collection is hidden from the render.
Units: 1 Blender unit = 1 mm, which is why the light powers look huge.
"""
import bpy, bmesh, math
from mathutils import Vector

SILVER = dict(color=(0.96, 0.94, 0.90), roughness=0.14)
BACKDROP = dict(color=(0.035, 0.036, 0.040), roughness=0.22)


def _material(name, color, roughness, metallic=0.0, specular=0.5):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    if not mat.node_tree:
        mat.use_nodes = True
    b = mat.node_tree.nodes.get("Principled BSDF")
    b.inputs['Base Color'].default_value = (*color, 1.0)
    b.inputs['Metallic'].default_value = metallic
    b.inputs['Roughness'].default_value = roughness
    ior = b.inputs.get('IOR Level') or b.inputs.get('Specular IOR Level')
    if ior is not None:
        ior.default_value = specular
    mat.diffuse_color = (*color, 1.0)
    mat.metallic, mat.roughness = metallic, roughness
    return mat


def silver_material():
    mat = _material("Polished silver", SILVER["color"], SILVER["roughness"], metallic=1.0)
    b = mat.node_tree.nodes.get("Principled BSDF")
    coat = b.inputs.get('Coat Weight')
    if coat is not None:                       # a whisper of clear coat reads as a fresh polish
        coat.default_value = 0.15
    return mat


def _sweep(name, width=900.0, depth=500.0, back=160.0, height=400.0, radius=120.0, segs=24):
    """Floor running back into a curved wall: the classic photo sweep. Flat from -depth to +back."""
    bm = bmesh.new()
    prof = [(-depth, 0.0)]
    for i in range(segs + 1):
        a = math.pi / 2 * i / segs
        prof.append((back + radius * math.sin(a), radius - radius * math.cos(a)))
    prof.append((back + radius, height))
    rows = []
    for yy, zz in prof:
        rows.append([bm.verts.new((-width / 2, yy, zz)), bm.verts.new((width / 2, yy, zz))])
    for a, b in zip(rows, rows[1:]):
        bm.faces.new((a[0], a[1], b[1], b[0]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    return me


def _area_light(col, name, size, power, loc, target, shape='SQUARE', size_y=None, color=(1, 1, 1)):
    data = bpy.data.lights.new(name, 'AREA')
    data.shape = shape
    data.size = size
    if size_y:
        data.size_y = size_y
    data.energy = power
    data.color = color
    ob = bpy.data.objects.new(name, data)
    col.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    return ob


def _world(scene):
    w = scene.world or bpy.data.worlds.new("Studio")
    scene.world = w
    if not w.node_tree:
        w.use_nodes = True
    nt = w.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new('ShaderNodeOutputWorld')
    bg = nt.nodes.new('ShaderNodeBackground')
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    grad = nt.nodes.new('ShaderNodeTexGradient')
    mapping = nt.nodes.new('ShaderNodeMapping')
    coord = nt.nodes.new('ShaderNodeTexCoord')
    grad.gradient_type = 'LINEAR'
    mapping.inputs['Rotation'].default_value = (0.0, -math.pi / 2, 0.0)   # gradient along world Z
    ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[0].color = 0.45, (0.02, 0.02, 0.025, 1)
    ramp.color_ramp.elements[1].position, ramp.color_ramp.elements[1].color = 0.75, (0.35, 0.37, 0.42, 1)
    bg.inputs['Strength'].default_value = 0.35
    nt.links.new(coord.outputs['Generated'], mapping.inputs['Vector'])
    nt.links.new(mapping.outputs['Vector'], grad.inputs['Vector'])
    nt.links.new(grad.outputs['Fac'], ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], bg.inputs['Color'])
    nt.links.new(bg.outputs['Background'], out.inputs['Surface'])


def setup(scene, rings, samples=256, resolution=(1920, 1280), gpu=True):
    """rings: list of ring objects, largest last. Returns the camera."""
    root = scene.collection
    name = "Photo setup"
    old = bpy.data.collections.get(name)
    if old:
        for o in list(old.objects):
            d = o.data
            bpy.data.objects.remove(o)
            if d and d.users == 0 and isinstance(d, (bpy.types.Light, bpy.types.Camera)):
                (bpy.data.lights if isinstance(d, bpy.types.Light) else bpy.data.cameras).remove(d)
            elif d and d.users == 0 and isinstance(d, bpy.types.Mesh) and d.name.startswith("_"):
                bpy.data.meshes.remove(d)
        bpy.data.collections.remove(old)
    col = bpy.data.collections.new(name)
    root.children.link(col)
    for r in rings:
        r.hide_render = True                                  # originals stay in the viewport only

    silver = silver_material()
    poses = [                                                 # (x, y, z-lift, rot x, rot z) in mm/deg
        (-26.0, 22.0, None, 0.0, 40.0),
        (0.0, 0.0, None, 0.0, -30.0),
        (21.0, 10.0, "flat", 90.0, 20.0),
    ]
    copies = []
    if len(rings) == 1:                                     # one piece: the hero pose, centre
        poses = [poses[1]]
    for r, (px, py, lift, rx, rz) in zip(rings, poses):
        c = bpy.data.objects.new(r.name + " (photo)", r.data)
        col.objects.link(c)
        for slot in c.material_slots:
            slot.link = 'OBJECT'
            slot.material = silver
        c.rotation_euler = (math.radians(rx), 0.0, math.radians(rz))
        half_h = r.dimensions.y / 2 if lift == "flat" else r.dimensions.z / 2
        c.location = (px, py, half_h + 0.02)
        copies.append(c)

    sweep = bpy.data.objects.new("_sweep", _sweep("_sweep"))
    col.objects.link(sweep)
    sweep.data.materials.append(_material("Dark acrylic sweep", BACKDROP["color"], BACKDROP["roughness"], specular=0.6))

    focus = Vector((0.0, 3.0, 9.0))
    _area_light(col, "Key softbox", 180.0, 1.8e6, (-150.0, -140.0, 210.0), focus, color=(1.0, 0.97, 0.93))
    _area_light(col, "Fill softbox", 300.0, 6.0e5, (230.0, -170.0, 120.0), focus, color=(0.93, 0.96, 1.0))
    _area_light(col, "Strip light", 420.0, 1.2e6, (20.0, 140.0, 260.0), focus, shape='RECTANGLE', size_y=60.0)
    _area_light(col, "Kicker", 90.0, 3.0e5, (170.0, 90.0, 40.0), focus)
    _world(scene)

    cam_data = bpy.data.cameras.new("Photo camera")
    cam_data.lens = 85.0
    cam_data.sensor_width = 36.0
    cam_data.clip_start, cam_data.clip_end = 5.0, 5000.0
    cam_data.dof.use_dof = True
    cam_data.dof.focus_object = copies[min(1, len(copies) - 1)]
    cam_data.dof.aperture_fstop = 5.6
    cam = bpy.data.objects.new("Photo camera", cam_data)
    col.objects.link(cam)
    cam.location = (5.0, -158.0, 60.0)
    cam.rotation_euler = (focus - cam.location).to_track_quat('-Z', 'Y').to_euler()
    scene.camera = cam

    r = scene.render
    r.engine = 'CYCLES'
    r.resolution_x, r.resolution_y = resolution
    r.resolution_percentage = 100
    r.image_settings.file_format = 'PNG'
    r.image_settings.color_depth = '16'
    r.film_transparent = False
    cy = scene.cycles
    cy.samples = samples
    cy.use_denoising = True
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = 0.01
    cy.max_bounces = 12
    cy.glossy_bounces = 8
    cy.caustics_reflective = False
    cy.caustics_refractive = False
    cy.device = 'GPU' if gpu and _enable_gpu() else 'CPU'
    vs = scene.view_settings
    vs.view_transform = 'AgX'
    try:
        vs.look = 'AgX - Medium High Contrast'
    except TypeError:
        pass
    vs.exposure = 0.0
    col.hide_viewport = True                                  # the photo set stays out of the way
    return cam


def _enable_gpu():
    """Turn on any CUDA/OptiX/HIP/Metal/oneAPI device; True if one is available."""
    try:
        prefs = bpy.context.preferences.addons['cycles'].preferences
    except Exception:
        return False
    for kind in ('OPTIX', 'CUDA', 'HIP', 'METAL', 'ONEAPI'):
        try:
            prefs.compute_device_type = kind
        except TypeError:
            continue
        prefs.get_devices()
        found = False
        for d in prefs.devices:
            if d.type == kind:
                d.use = True
                found = True
        if found:
            return True
    return False
