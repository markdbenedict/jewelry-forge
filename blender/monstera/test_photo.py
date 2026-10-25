import bpy, sys, time
sys.path.insert(0, '/home/claude/monstera')
bpy.ops.wm.open_mainfile(filepath='/home/claude/monstera/out/test.blend')
import photo
scene = bpy.context.scene
for o in list(scene.objects):
    if o.type in ('LIGHT', 'CAMERA'):
        bpy.data.objects.remove(o)
rings = [bpy.data.objects[f"Monstera ring US {s}"] for s in (5, 6, 7)]
samples = int(sys.argv[-2]); scale = int(sys.argv[-1])
photo.setup(scene, rings, samples=samples, resolution=(1920, 1280), gpu=False)
scene.render.resolution_percentage = scale
scene.render.filepath = '/home/claude/monstera/out/photo_test.png'
t = time.time(); bpy.ops.render.render(write_still=True); print(f"rendered in {time.time()-t:.0f}s")
