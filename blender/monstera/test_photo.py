r"""Product shot of the three rings test_ring.py saved (sizes 5, 6, 7) through photo.setup, at the
sample count and resolution percentage given after `--`.

    blender -b -P blender\monstera\test_photo.py -- 64 50

Opens <out>\test.blend and writes <out>\photo_test.png; <out> is %JEWELRY_OUT%\blender\monstera
when JEWELRY_OUT is set, else <repo>\out\blender\monstera.
"""
import bpy, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))     # blender/, for forge_paths
import forge_paths
forge_paths.add_to_sys_path("monstera")
OUT = forge_paths.out_dir("blender", "monstera")
bpy.ops.wm.open_mainfile(filepath=str(OUT / "test.blend"))
import photo
scene = bpy.context.scene
for o in list(scene.objects):
    if o.type in ('LIGHT', 'CAMERA'):
        bpy.data.objects.remove(o)
rings = [bpy.data.objects[f"Monstera ring US {s}"] for s in (5, 6, 7)]
samples = int(sys.argv[-2]); scale = int(sys.argv[-1])
photo.setup(scene, rings, samples=samples, resolution=(1920, 1280), gpu=False)
scene.render.resolution_percentage = scale
scene.render.filepath = str(OUT / "photo_test.png")
t = time.time(); bpy.ops.render.render(write_still=True); print(f"rendered in {time.time()-t:.0f}s")
