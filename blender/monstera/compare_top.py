import bpy, math
from mathutils import Vector
bpy.ops.wm.open_mainfile(filepath='/home/claude/monstera/out/test.blend')
scene = bpy.context.scene
for o in list(scene.objects):
    if o.type in ('LIGHT', 'CAMERA'): bpy.data.objects.remove(o)
w = bpy.data.worlds.new("W"); scene.world = w
w.node_tree.nodes['Background'].inputs['Color'].default_value = (0.03, 0.035, 0.045, 1)
for nm, e, d_, ang in (("key", 4.0, (0.45, 0.55, -0.6), 3), ("rim", 2.0, (-0.6, -0.3, -0.4), 8), ("fill", 0.9, (-0.3, 0.8, 0.2), 20)):
    l = bpy.data.objects.new(nm, bpy.data.lights.new(nm, 'SUN')); scene.collection.objects.link(l); l.data.energy = e
    l.data.angle = math.radians(ang); l.rotation_euler = Vector(d_).to_track_quat('-Z', 'Y').to_euler()
cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam")); scene.collection.objects.link(cam); scene.camera = cam
cam.data.clip_start = 0.5; cam.data.lens = 110
r = scene.render; r.engine = 'CYCLES'; scene.cycles.samples = 48; scene.cycles.use_denoising = True
r.resolution_x, r.resolution_y = 1100, 800
ring = bpy.data.objects["Monstera ring US 6"]
cam.location = Vector((34.01, -0.01, 72)); cam.rotation_euler = (Vector((34, 0, 10)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
r.filepath = '/home/claude/monstera/out/m_top6.png'; bpy.ops.render.render(write_still=True)
print("ok")
