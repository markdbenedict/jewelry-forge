import bpy, sys, math, time
from mathutils import Vector
bpy.ops.wm.read_factory_settings(use_empty=True)
sys.path.insert(0, '/home/claude/jewelry'); sys.path.insert(0, '/home/claude/monstera')
import jewelry_kit as jk, monstera_ring as mr
jk.setup_mm_workspace()
scene = bpy.context.scene
mat = bpy.data.materials.new("resin"); b = mat.node_tree.nodes["Principled BSDF"]
b.inputs['Base Color'].default_value = (0.55, 0.57, 0.62, 1); b.inputs['Roughness'].default_value = 0.42
sizes = [float(s) for s in sys.argv[sys.argv.index("--") + 1:]] if "--" in sys.argv else [5.0]
rings = []
for i, s in enumerate(sizes):
    t = time.time(); r = mr.build(s, material=mat, x=i * 34.0); rings.append(r)
    text, d = jk.check_model(r, make_map=False)
    print(f"{r.name}: {time.time()-t:.1f}s leaves={mr.ring_plan(s)['n']} tris={sum(len(p.vertices)-2 for p in r.data.polygons):,}")
    print("  " + "\n  ".join(text.split("\n")[1:6]))
bpy.ops.wm.save_as_mainfile(filepath='/home/claude/monstera/out/test.blend')
w = bpy.data.worlds.new("W"); scene.world = w
w.node_tree.nodes['Background'].inputs['Color'].default_value = (0.03, 0.035, 0.045, 1)
for nm, e, d_, ang in (("key", 4.0, (0.45, 0.55, -0.6), 3), ("rim", 2.0, (-0.6, -0.3, -0.4), 8), ("fill", 0.9, (-0.3, 0.8, 0.2), 20)):
    l = bpy.data.objects.new(nm, bpy.data.lights.new(nm, 'SUN')); scene.collection.objects.link(l); l.data.energy = e
    l.data.angle = math.radians(ang); l.rotation_euler = Vector(d_).to_track_quat('-Z', 'Y').to_euler()
cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam")); scene.collection.objects.link(cam); scene.camera = cam
cam.data.clip_start = 0.5
r = scene.render; r.engine = 'CYCLES'; scene.cycles.samples = 48; scene.cycles.use_denoising = True
r.resolution_x, r.resolution_y = 1100, 800
def shot(loc, look, lens, path):
    cam.location = Vector(loc); cam.data.lens = lens
    cam.rotation_euler = (Vector(look) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    r.filepath = '/home/claude/monstera/out/' + path; bpy.ops.render.render(write_still=True)
R = rings[0]
shot((34, -40, 30), (0, 0, 0), 70, 'm_34.png')
shot((0.01, -60, 0.01), (0, 0, 0), 60, 'm_side.png')
shot((6, -16, 22), (1, 0, 9.2), 95, 'm_close.png')
shot((0.01, -0.01, 70), (0, 0, 9), 110, 'm_top.png')
print("rendered")
