import sys, math, types, numpy as np
src = open('monstera_ring.py').read()
head = src[:src.index("# ----------------------------------------------------------------------------- 3-D construction")]
head = head.replace("import bpy, bmesh, math, sys", "import math, sys").replace("from mathutils import Vector", "")
m = types.ModuleType("mr"); exec(head, m.__dict__)
from shapely.geometry import Polygon, LineString
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
rng = np.random.default_rng(11 * 1000 + 20)
fig, axes = plt.subplots(3, 4, figsize=(16, 10))
worst = 9
for ax, k in zip(axes.ravel(), range(12)):
    p = m.make_variant(rng)
    outline = Polygon(m.outline_poly(p))
    cuts = [Polygon(m.slit_poly(u, s, p)) for s in (1, -1) for u in p["slits"][s]]
    holes = [Polygon(m.hole_poly(u, s, p)) for s in (1, -1) for u in p["holes"][s]]
    blade = outline
    for c in cuts + holes: blade = blade.difference(c)
    allc = cuts + holes
    gap = min([allc[i].distance(allc[j]) for i in range(len(allc)) for j in range(i + 1, len(allc))] + [9])
    hole_edge = min([h.distance(outline.exterior) for h in holes] + [9])
    worst = min(worst, gap, hole_edge)
    parts = [blade] if blade.geom_type == 'Polygon' else list(blade.geoms)
    for b in parts:
        ax.fill(*b.exterior.xy, color='#4f8a4b')
        for hole in b.interiors: ax.fill(*hole.xy, color='white')
    for side in (1, -1):
        for u in p["veins"][side]:
            E, d, a = m._line(u, p); s_mid = E[1] / math.sin(a)
            P0 = E + 0.08 * s_mid * d; P1 = E + s_mid * d
            ax.plot([P0[0], P1[0]], [side * P0[1], side * P1[1]], color='#1f3d1c', lw=1)
    ax.plot([0.3, 0.97 * p["length"]], [0, 0], color='#1f3d1c', lw=1.6)
    # yaw shown as the band direction line
    ps = p["yaw"]; xp = p["pivot"] * p["length"]
    ax.plot([xp - 4 * math.cos(ps), xp + 4 * math.cos(ps)], [4 * math.sin(ps), -4 * math.sin(ps)], 'k--', lw=0.6)
    ax.set_aspect("equal"); ax.set_xlim(-0.5, 11.3); ax.set_ylim(-4.4, 4.4); ax.grid(alpha=0.2)
    ax.set_title(f"L {p['length']:.1f}  W {p['width']:.1f}  slits {len(p['slits'][1])}/{len(p['slits'][-1])}  "
                 f"holes {len(p['holes'][1])}/{len(p['holes'][-1])}  yaw {math.degrees(p['yaw']):+.0f}°", fontsize=9)
plt.tight_layout(); plt.savefig('/home/claude/monstera/gallery.png', dpi=100)
print("worst web across 12 leaves: %.3f mm" % worst)
