"""The 2-D monstera leaf design, shared by the Blender build (monstera_ring.py) and the gallery
(gallery.py). Pure numpy/math, no bpy, so it runs inside Blender, in the system Python and in pytest.

Leaf-local coordinates: x along the midrib from the base (0) to the tip (length), y across it,
millimetres. LEAF is the base leaf and VARIETY the ranges a seeded generator draws each leaf from;
make_variant(rng) gives one leaf's parameters, and the random sequence is the leaf's identity, so
a rebuild from the same seed gives the same ring. outline_poly / slit_poly / hole_poly are the
closed polygons the 3-D build extrudes and cuts with, _vein_depth the groove field pressed into the
leaf top, _layout_ok the web check that keeps the cuts castable. BAND and RING_WIDTH describe the
band the leaves are laid over. monstera_ring re-exports all of this, so `mr.make_variant` and
`mr.outline_poly` still work.
"""
import math
import numpy as np

BAND = {"Size Allowance": 0.0, "Width": 6.2, "Thickness": 1.3, "Finish Stock": 0.0,
        "Outer Dome": 0.0, "Comfort Relief": 0.15, "Segments": 256, "Profile Points": 16}
LEAF = dict(                        # the base leaf; VARIETY randomises around these values
    length=9.5, ratio=0.735,        # length (mm) and width/length
    thick=(0.80, 0.45), step=0.60,  # thickness at midrib / edge; tilt along the leaf (shingle step)
    drape=0.45, cut_floor=-0.16,    # edges wrap down over the band edge; slits stop here (band = 0)
    u_wide=0.30, tip_q=2.2, tip_r=0.8,                       # outline: widest point, tip taper
    slit_w=(0.66, 0.38), slit_y=0.48, hole_y=0.22, hole_ab=(0.26, 0.21),   # *_y as fraction of W/2
    alpha=(75.0, 35.0),             # slit/vein lean, degrees from the midrib (base -> tip)
    vein_mid=0.26, vein_lat=0.18, vein_w=(0.19, 0.13),
    nu=220, nv=150, embed=(0.10, 0.12), min_web=0.40, pivot=0.42)
VARIETY = dict(seed=11, length=(0.88, 1.12), ratio=(0.66, 0.80), u_wide=(0.27, 0.36),
               tip_q=(1.9, 2.6), slits=(3, 5), first_slit=(0.20, 0.30), last_slit=(0.70, 0.80),
               slit_y=(0.36, 0.56), holes=(0, 3), yaw_deg=15.0, overlap=(2.0, 2.6),
               alpha_jitter=5.0)
RING_WIDTH = 7.3                    # lobes that swing past this overall width are trimmed flush


# ----------------------------------------------------------------------------- leaf variants
def make_variant(rng, tries=30):
    """One leaf's parameters, drawn around LEAF; holes are dropped if they crowd the slits."""
    V, B = VARIETY, LEAF
    U = lambda key: rng.uniform(*V[key])
    for _ in range(tries):
        L = B["length"] * U("length")
        W = L * U("ratio")
        s = L / B["length"]
        p = dict(B)
        p.update(length=L, width=W, u_wide=U("u_wide"), tip_q=U("tip_q"),
                 slit_w=(max(0.45, B["slit_w"][0] * s), max(0.30, B["slit_w"][1] * s)),
                 slit_y=U("slit_y") * W / 2, hole_y=B["hole_y"] * W / 2,
                 hole_ab=(max(0.19, B["hole_ab"][0] * s), max(0.16, B["hole_ab"][1] * s)),
                 alpha=(B["alpha"][0] + rng.uniform(-1, 1) * V["alpha_jitter"],
                        B["alpha"][1] + rng.uniform(-1, 1) * V["alpha_jitter"]),
                 yaw=math.radians(rng.uniform(-1, 1) * V["yaw_deg"]), overlap=U("overlap"),
                 slits={}, holes={}, veins={})
        for side in (1, -1):                                   # each side gets its own pattern
            n = int(rng.integers(V["slits"][0], V["slits"][1] + 1))
            u0, u1 = U("first_slit"), U("last_slit")
            us = np.linspace(u0, u1, n)
            if n > 1:
                us = us + rng.uniform(-0.15, 0.15, n) * (u1 - u0) / (n - 1)
            us = np.clip(np.sort(us), 0.18, 0.82)
            p["slits"][side] = list(us)
            lobes = np.concatenate([[max(0.10, us[0] - 0.13)], (us[:-1] + us[1:]) / 2,
                                    [min(0.88, us[-1] + 0.11)]])
            p["veins"][side] = list(lobes)
            n_h = int(rng.integers(V["holes"][0], V["holes"][1] + 1))
            inner = list(us[1:-1]) if n >= 3 else list(us)    # holes sit on the inner slit lines
            rng.shuffle(inner)
            p["holes"][side] = sorted(inner[:n_h])
        if _layout_ok(p):
            return p
    for side in (1, -1):                                       # give up on holes for this leaf
        p["holes"][side] = []
    return p


def _poly_gap(A, B):
    """Smallest distance between two closed polygons (vertex-to-segment, both ways)."""
    def v2s(Q, P):
        P0, P1 = P, np.roll(P, -1, 0)
        D = P1 - P0
        t = ((Q[:, None, :] - P0[None]) * D[None]).sum(-1) / np.maximum((D * D).sum(-1)[None], 1e-12)
        t = np.clip(t, 0, 1)
        C = P0[None] + t[..., None] * D[None]
        return np.sqrt(((Q[:, None, :] - C) ** 2).sum(-1)).min()
    return min(v2s(A, B), v2s(B, A))


def _layout_ok(p):
    web = p["min_web"]
    cuts = [slit_poly(u, s, p) for s in (1, -1) for u in p["slits"][s]]
    holes = [hole_poly(u, s, p) for s in (1, -1) for u in p["holes"][s]]
    allc = cuts + holes
    for i in range(len(allc)):
        for j in range(i + 1, len(allc)):
            if _poly_gap(allc[i], allc[j]) < web:
                return False
    outline = outline_poly(p)
    midrib = np.array([[0.0, 0.0], [p["length"], 0.0]])
    for h in holes:
        if _poly_gap(h, outline) < web or _poly_gap(h, midrib) < 0.30:
            return False
    return True


# ----------------------------------------------------------------------------- 2-D leaf design
def half_width(u, p):
    um, W2 = p["u_wide"], p["width"] / 2
    u = np.asarray(u, float)
    base = np.sqrt(np.clip(1 - ((um - u) / um) ** 2, 0, 1))
    v = np.clip((u - um) / (1 - um), 0, 1)
    tip = (1 - v ** p["tip_q"]) ** p["tip_r"]
    return W2 * np.where(u < um, base, tip)


def _alpha(u, p):
    a0, a1 = p["alpha"]
    return math.radians(a0 - (a0 - a1) * u)


def _line(u_e, p):
    """Edge point and inward (toward the midrib, leaning back) unit direction of a feature line."""
    a = _alpha(u_e, p)
    E = np.array([u_e * p["length"], float(half_width(u_e, p))])
    d = -np.array([math.cos(a), math.sin(a)])
    return E, d, a


def outline_poly(p, n=120):
    u = np.linspace(0, 1, n)
    h = half_width(u, p)
    right = np.stack([u * p["length"], h], 1)
    left = np.stack([u * p["length"], -h], 1)[::-1][1:-1]
    return np.concatenate([right, left])


def slit_poly(u_e, side, p):
    """Tapered slot from just outside the edge to |y| = slit_y, round ends."""
    E, d, a = _line(u_e, p)
    nrm = np.array([-d[1], d[0]])
    w_edge, w_in = p["slit_w"]
    s_in = max(0.3, (E[1] - p["slit_y"]) / math.sin(a))
    s0 = -0.45
    pts = []
    for s in np.linspace(s0, s_in, 14):
        w = w_edge + (w_in - w_edge) * np.clip(s / s_in, 0, 1)
        pts.append(E + s * d + nrm * w / 2)
    c = E + s_in * d
    for t in np.linspace(0, math.pi, 10)[1:-1]:                 # inner cap
        pts.append(c + (w_in / 2) * (math.cos(t) * nrm + math.sin(t) * d))
    for s in np.linspace(s_in, s0, 14):
        w = w_edge + (w_in - w_edge) * np.clip(s / s_in, 0, 1)
        pts.append(E + s * d - nrm * w / 2)
    c = E + s0 * d
    for t in np.linspace(0, math.pi, 10)[1:-1]:                 # outer cap
        pts.append(c + (w_edge / 2) * (-math.cos(t) * nrm - math.sin(t) * d))
    pts = np.array(pts)
    pts[:, 1] *= side
    return pts


def hole_poly(u_e, side, p, n=32):
    E, d, a = _line(u_e, p)
    nrm = np.array([-d[1], d[0]])
    s_h = (E[1] - p["hole_y"]) / math.sin(a)
    c = E + s_h * d
    A, B = p["hole_ab"]
    t = np.linspace(0, 2 * math.pi, n, endpoint=False)
    pts = c + np.outer(A * np.cos(t), d) + np.outer(B * np.sin(t), nrm)
    pts[:, 1] *= side
    return pts


def _vein_depth(X, Y, p):
    """Groove depth on the leaf top: midrib plus one side vein down the middle of each lobe."""
    L = p["length"]
    w_mid, w_lat = p["vein_w"]
    u = X / L
    fade = np.clip(u / 0.04, 0, 1) * np.clip((0.97 - u) / 0.08, 0, 1)
    depth = p["vein_mid"] * np.exp(-(Y / w_mid) ** 2) * fade
    ay = np.abs(Y)
    for side in (1, -1):
        on_side = (Y * side) >= 0
        for u_v in p["veins"][side]:
            E, d, a = _line(u_v, p)
            s_mid = E[1] / math.sin(a)                            # edge -> midrib length
            t = np.clip((X - E[0]) * d[0] + (ay - E[1]) * d[1], 0, s_mid)
            px, py = E[0] + t * d[0], E[1] + t * d[1]
            dist = np.hypot(X - px, ay - py)
            f = np.clip(t / (0.22 * s_mid), 0, 1)                 # fades out toward the edge
            depth = np.maximum(depth, np.where(on_side, p["vein_lat"] * f * np.exp(-(dist / w_lat) ** 2), 0))
    return depth
