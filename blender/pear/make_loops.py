"""Build the 2-D cross-section loops for a pear bezel cup and its stone pocket.

Stone outline fitted to the user's top-view photo: width/length 0.662, widest point 41% from the
round end, superellipse round end (n=2.4), circular arcs to the tip. Length from the user (1/2 in).
Every loop is resampled in polar form around the culet point C at the same N angles, so loops
can be bridged with quads in Blender. Output: pear_loops.json (compact, zlib+base64 uint16 radii).
"""
import json, math, zlib, base64, array
import numpy as np
from shapely.geometry import Polygon, LineString, Point
from shapely import affinity

L = 12.7                  # stone length, mm (user: 1/2")
RATIO = 0.662             # width / length, measured from the photo
K_WIDE = 0.41             # widest point, fraction of length from the round end
N_ROUND = 2.4             # superellipse exponent of the round end
CULET = 0.33              # culet position, fraction of length from the round end (photo)
CLR = 0.20                # radial clearance stone -> pocket
W_B = 1.00                # bezel wall
CH_O, CH_I = 0.30, 0.25   # outer top chamfer, inner rim chamfer
Z_TOP = 0.70              # bezel top above the seat plane (girdle ~0.2 + lip)
Z_V = -0.30               # bottom of the vertical bezel band
P_PK = 4.50               # pocket depth below the seat (pavilion up to ~4.3 mm)
GAP, FLOOR = 0.60, 0.80   # finger clearance under the cup, floor under the pocket tip
SEAT_ABOVE_RIN = GAP + FLOOR + P_PK          # seat plane height above the inner radius
Z_BOT = -(SEAT_ABOVE_RIN + 1.0)              # cup loft goes 1 mm below the finger line; cylinder trims it
S_B, W_GROW = 0.20, 0.30  # taper: outline scale at the bottom, extra wall at the bottom
GROOVE = 0.25              # decorative V-groove under the bezel (depth)
N = 256                   # samples around each loop
SCALE = 2e-4              # radius quantisation (mm per unit)

W = RATIO * L
r = W / 2
k = K_WIDE * L
Ra = (r**2 + (L - k)**2) / (2 * r)


def half_width(v):
    """v from 0 (round end) to L (tip)."""
    if v <= k:
        t = abs((k - v) / k)
        return r * max(0.0, 1 - t**N_ROUND) ** (1 / N_ROUND)
    return (r - Ra) + math.sqrt(max(0.0, Ra**2 - (v - k)**2))


# dense stone outline in head coordinates: X across, Y along (round end -L/2 .. tip +L/2)
vs = np.concatenate([np.linspace(0, k, 600, endpoint=False), np.linspace(k, L, 900)])
right = [(half_width(v), v - L / 2) for v in vs]
left = [(-x, y) for x, y in reversed(right)]
stone = Polygon(right + left[1:-1]).buffer(0)
assert stone.is_valid and stone.convex_hull.area - stone.area < 1e-3, "outline should be convex"
C = (0.0, CULET * L - L / 2)
thetas = [2 * math.pi * i / N for i in range(N)]          # 0 -> +Y (tip), direction (sin, cos)


def polar(poly):
    out = []
    for t in thetas:
        d = (math.sin(t), math.cos(t))
        ray = LineString([C, (C[0] + 60 * d[0], C[1] + 60 * d[1])])
        hit = ray.intersection(poly.exterior)
        pts = [hit] if hit.geom_type == 'Point' else list(getattr(hit, 'geoms', []))
        out.append(max(Point(C).distance(p) for p in pts))
    return out


def buf(p, d):
    return p.buffer(d, quad_segs=48, join_style='round')


pocket_top = buf(stone, CLR)
base = polar(pocket_top)
cup = [  # (z, radii) top -> bottom
    (Z_TOP, polar(buf(stone, CLR + W_B - CH_O))),
    (Z_TOP - CH_O, polar(buf(stone, CLR + W_B))),
    (Z_V, polar(buf(stone, CLR + W_B))),
    (Z_V - 0.15, polar(buf(stone, CLR + W_B - GROOVE))),
    (Z_V - 0.30, polar(buf(stone, CLR + W_B))),
]
for t in np.linspace(0, 1, 15)[1:]:
    z = (Z_V - 0.30) + t * (Z_BOT - (Z_V - 0.30))
    mu = 1 - (1 - S_B) * t ** 1.5          # tulip: stays full under the bezel, necks in toward the band
    cup.append((z, polar(buf(affinity.scale(pocket_top, mu, mu, origin=C), W_B + W_GROW * t))))

pocket = [
    (Z_TOP + 1.0, polar(buf(stone, CLR + CH_I + 1.0))),
    (Z_TOP, polar(buf(stone, CLR + CH_I))),
    (Z_TOP - CH_I, base),
    (0.0, base),
]
for d in np.linspace(0, P_PK, 11)[1:-1]:
    lam = 1 - d / P_PK
    pocket.append((-d, [lam * x for x in base]))


def pack(loops):
    a = array.array('H', [int(round(x / SCALE)) for _, rr in loops for x in rr])
    return {"z": [round(z, 5) for z, _ in loops], "blob": base64.b64encode(zlib.compress(a.tobytes(), 9)).decode()}


stone_polar = polar(stone)
data = {
    "N": N, "C": C, "scale": SCALE, "seat_above_rin": SEAT_ABOVE_RIN, "pocket_depth": P_PK,
    "stone": {"L": L, "W": round(W, 3), "clearance": CLR, "wall": W_B},
    "cup": pack(cup), "pocket": pack(pocket), "stone_outline": pack([(0.0, stone_polar)]),
}
json.dump(data, open("pear_loops.json", "w"))
print(f"stone {L} x {W:.2f} mm; culet at Y={C[1]:.2f}; seat {SEAT_ABOVE_RIN:.2f} mm above finger line")
print(f"bezel outside: {buf(stone, CLR + W_B).bounds}")
print("payload chars:", len(data['cup']['blob']) + len(data['pocket']['blob']) + len(data['stone_outline']['blob']))
