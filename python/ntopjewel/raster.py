"""Triangles onto a grid of columns, for the print preparation (printprep) and its preview pictures.

`hits` finds every pixel centre that lies inside a triangle's projection on the XY plane and the height of
the triangle's plane there. `Columns` sorts a closed mesh's hits by pixel and height and keeps the winding
number after each crossing, so it answers "is (pixel, z) inside the solid?" for any number of points with one
binary search each - a voxel model exact in z, with no voxel array. `render` paints a mesh's nearest
triangles into an image for the preview.

The grid is offset from the mesh by fractions of a pixel that are no simple ratio (GRID_OFFSET), so a pixel
centre never lands on an edge two triangles share and a crossing is never counted twice - a box built on
round numbers included.
"""
from __future__ import annotations

import numpy as np

GRID_OFFSET = (0.3183098862, 0.2718281828)   # 1/π and e/10 of a pixel
CHUNK = 200000                               # triangles per pass: bounds the candidates' arrays (~100 MB at most)


def grid_for(points: np.ndarray, pixel: float, margin_px: int = 3):
    """(origin, (nx, ny)) of a grid covering the points' XY extent with `margin_px` empty pixels all round."""
    lo = points[:, :2].min(axis=0) - (margin_px + np.array(GRID_OFFSET)) * pixel
    hi = points[:, :2].max(axis=0) + margin_px * pixel
    n = np.ceil((hi - lo) / pixel).astype(int) + 1
    return lo, (int(n[0]), int(n[1]))


def hits(tri: np.ndarray, pixel: float, origin, shape, chunk: int = CHUNK):
    """Every pixel centre inside each triangle's XY projection. `tri` (n, 3, 3). Returns (pix, z, t): the pixel
    (j * nx + i, centre at origin + (i + ½, j + ½) x pixel), the triangle's plane height there, the triangle's
    index. A triangle seen edge-on (no area in XY) has none."""
    nx, ny = shape
    ox, oy = float(origin[0]), float(origin[1])
    P, Z, T = [], [], []
    for s in range(0, len(tri), chunk):
        tr = tri[s:s + chunk]
        u = (tr[:, :, 0] - ox) / pixel - 0.5                      # pixel centre i sits at u = i
        v = (tr[:, :, 1] - oy) / pixel - 0.5
        i0 = np.maximum(np.ceil(u.min(axis=1)), 0).astype(np.int64)
        i1 = np.minimum(np.floor(u.max(axis=1)), nx - 1).astype(np.int64)
        j0 = np.maximum(np.ceil(v.min(axis=1)), 0).astype(np.int64)
        j1 = np.minimum(np.floor(v.max(axis=1)), ny - 1).astype(np.int64)
        w = i1 - i0 + 1
        h = j1 - j0 + 1
        n = np.where((w > 0) & (h > 0), w * h, 0)
        total = int(n.sum())
        if total == 0:
            continue
        k = np.repeat(np.arange(len(tr)), n)
        first = np.cumsum(n) - n
        local = np.arange(total) - np.repeat(first, n)
        wk = w[k]
        ii = i0[k] + local % wk
        jj = j0[k] + local // wk
        u0, u1, u2 = u[k, 0], u[k, 1], u[k, 2]
        v0, v1, v2 = v[k, 0], v[k, 1], v[k, 2]
        d = (v1 - v2) * (u0 - u2) + (u2 - u1) * (v0 - v2)
        ok = np.abs(d) > 1e-12
        d = np.where(ok, d, 1.0)
        a = ((v1 - v2) * (ii - u2) + (u2 - u1) * (jj - v2)) / d
        b = ((v2 - v0) * (ii - u2) + (u0 - u2) * (jj - v2)) / d
        c = 1.0 - a - b
        inside = ok & (a >= 0) & (b >= 0) & (c >= 0)
        if not inside.any():
            continue
        k, ii, jj, a, b, c = k[inside], ii[inside], jj[inside], a[inside], b[inside], c[inside]
        z = a * tr[k, 0, 2] + b * tr[k, 1, 2] + c * tr[k, 2, 2]
        P.append(jj * nx + ii)
        Z.append(z)
        T.append(k + s)
    if not P:
        return np.empty(0, np.int64), np.empty(0), np.empty(0, np.int64)
    return np.concatenate(P), np.concatenate(Z), np.concatenate(T)


class Columns:
    """A closed mesh as columns of crossings. `tri` (n, 3, 3) in the frame whose Z is up; `entering` (n,) bool:
    a triangle whose outward normal points down is where a column, going up, enters the solid. Every crossing
    knows its pixel, height, triangle and the winding number before and after it (> 0: inside), so overlapping
    shells (a part and its supports) read as their union."""

    def __init__(self, tri: np.ndarray, entering: np.ndarray, pixel: float, origin=None, shape=None):
        tri = np.asarray(tri, float)
        if origin is None:
            origin, shape = grid_for(tri.reshape(-1, 3), pixel)
        self.pixel = float(pixel)
        self.origin = np.asarray(origin, float)
        self.nx, self.ny = int(shape[0]), int(shape[1])
        self.zmin = float(tri[:, :, 2].min()) if len(tri) else 0.0
        self.zmax = float(tri[:, :, 2].max()) if len(tri) else 0.0
        self.span = (self.zmax - self.zmin) + 4.0                  # a column's keys never reach the next column's
        p, z, t = hits(tri, self.pixel, self.origin, (self.nx, self.ny))
        order = np.lexsort((z, p))
        self.pix, self.z, self.tri = p[order], z[order], t[order]
        step = np.where(np.asarray(entering, bool)[self.tri], 1, -1).astype(np.int32)
        cs = np.cumsum(step)
        new = np.r_[True, self.pix[1:] != self.pix[:-1]] if len(self.pix) else np.zeros(0, bool)
        heads = np.flatnonzero(new)
        lengths = np.diff(np.r_[heads, len(self.pix)])
        base = np.repeat(cs[heads] - step[heads], lengths) if len(heads) else np.zeros(0, np.int32)
        self.w_after = cs - base
        self.w_before = self.w_after - step
        self.key = self.pix * self.span + (self.z - self.zmin + 1.0)

    # ---- the grid ----------------------------------------------------------------------------
    def centre(self, pix):
        pix = np.asarray(pix, np.int64)
        i, j = pix % self.nx, pix // self.nx
        return np.column_stack([self.origin[0] + (i + 0.5) * self.pixel, self.origin[1] + (j + 0.5) * self.pixel])

    def pixel_at(self, x, y):
        """The pixel whose centre is nearest (x, y); -1 off the grid."""
        i = np.floor((np.asarray(x, float) - self.origin[0]) / self.pixel).astype(np.int64)
        j = np.floor((np.asarray(y, float) - self.origin[1]) / self.pixel).astype(np.int64)
        ok = (i >= 0) & (i < self.nx) & (j >= 0) & (j < self.ny)
        return np.where(ok, j * self.nx + i, -1)

    def neighbour(self, pix, di: int, dj: int):
        """The pixel (di, dj) away; -1 off the grid."""
        pix = np.asarray(pix, np.int64)
        i, j = pix % self.nx + di, pix // self.nx + dj
        ok = (i >= 0) & (i < self.nx) & (j >= 0) & (j < self.ny)
        return np.where(ok, j * self.nx + i, -1)

    # ---- queries -----------------------------------------------------------------------------
    def _keys(self, pix, z):
        zc = np.clip(np.asarray(z, float), self.zmin - 1.0, self.zmax + 1.0)
        return np.asarray(pix, np.int64) * self.span + (zc - self.zmin + 1.0)

    def inside(self, pix, z) -> np.ndarray:
        """Whether each (pixel, z) lies inside the solid (pixel -1: off the grid, outside)."""
        pix = np.asarray(pix, np.int64)
        z = np.broadcast_to(np.asarray(z, float), pix.shape)
        out = np.zeros(pix.shape, bool)
        if not len(self.key):
            return out
        ok = pix >= 0
        idx = np.searchsorted(self.key, self._keys(pix[ok], z[ok]), side="right") - 1
        good = idx >= 0
        res = np.zeros(idx.shape, bool)
        res[good] = (self.pix[idx[good]] == pix[ok][good]) & (self.w_after[idx[good]] > 0)
        out[ok] = res
        return out

    def solid_between(self, pix, z0, z1) -> np.ndarray:
        """Whether any solid lies in each column between z0 and z1 (z0 < z1): inside at z0, or a crossing between."""
        pix = np.asarray(pix, np.int64)
        z0 = np.broadcast_to(np.asarray(z0, float), pix.shape)
        z1 = np.broadcast_to(np.asarray(z1, float), pix.shape)
        out = self.inside(pix, z0)
        ok = pix >= 0
        a = np.searchsorted(self.key, self._keys(pix[ok], z0[ok]), side="right")
        b = np.searchsorted(self.key, self._keys(pix[ok], z1[ok]), side="right")
        out[ok] |= b > a
        return out

    def below(self, pix, z):
        """The highest crossing in each column below z (index into the crossings, -1 if none): where a support
        going straight down from z first meets the solid (an exit) - or -1, the plate."""
        pix = np.asarray(pix, np.int64)
        idx = np.searchsorted(self.key, self._keys(pix, z), side="left") - 1
        ok = (pix >= 0) & (idx >= 0)
        ok[ok] &= self.pix[idx[ok]] == pix[ok]
        return np.where(ok, idx, -1)

    @property
    def starts(self) -> np.ndarray:
        """Crossings where a column enters the solid (indices)."""
        return np.flatnonzero((self.w_before <= 0) & (self.w_after > 0))

    @property
    def ends(self) -> np.ndarray:
        return np.flatnonzero((self.w_before > 0) & (self.w_after <= 0))

    def intervals(self):
        """(pix, z_in, z_out, start index, end index) of every solid run along a column."""
        s, e = self.starts, self.ends
        return self.pix[s], self.z[s], self.z[e], s, e

    def layer_counts(self, h: float, z0: float | None = None):
        """For layers of thickness h from z0 (default the lowest crossing): the events that switch each pixel on
        and off, sorted by layer - (layer, pixel, +1 / -1) - with a layer counted solid where its mid-height is."""
        z0 = self.zmin if z0 is None else z0
        pix, zin, zout, _, _ = self.intervals()
        k0 = np.ceil((zin - z0) / h - 0.5).astype(np.int64)
        k1 = np.floor((zout - z0) / h - 0.5).astype(np.int64)
        keep = k1 >= k0
        pix, k0, k1 = pix[keep], k0[keep], k1[keep]
        layer = np.r_[k0, k1 + 1]
        dpix = np.r_[pix, pix]
        sign = np.r_[np.ones(len(k0), np.int16), -np.ones(len(k1), np.int16)]
        order = np.argsort(layer, kind="stable")
        n_layers = int(k1.max()) + 1 if len(k1) else 0
        return layer[order], dpix[order], sign[order], n_layers


def layers(cols: Columns, h: float, z0: float | None = None):
    """Yield (k, occupancy as an (ny, nx) bool array) for every layer from the bottom: a sweep over the run
    events, one pixel array in memory however fine the grid."""
    layer, pix, sign, n = cols.layer_counts(h, z0)
    count = np.zeros(cols.nx * cols.ny, np.int16)
    bounds = np.searchsorted(layer, np.arange(n + 1))
    for k in range(n):
        a, b = bounds[k], bounds[k + 1]
        if b > a:
            np.add.at(count, pix[a:b], sign[a:b])
        yield k, (count > 0).reshape(cols.ny, cols.nx)


def render(meshes, colours, view, size_px: int = 900, light=(0.35, -0.45, 0.82), background=(244, 244, 241),
           extent=None):
    """An orthographic picture of meshes: `colours` per mesh an (n_faces, 3) uint8 array or one RGB triple;
    `view` the direction looked along (from the eye into the scene). Flat shading from `light` (in the view's
    frame: x right, y up, z towards the eye) with some ambient. Returns an (h, w, 3) uint8 image and the
    projection used (origin, pixel, axes) so callers can mark points on it."""
    view = np.asarray(view, float)
    view /= np.linalg.norm(view)
    up = np.array([0.0, 0.0, 1.0]) if abs(view[2]) < 0.95 else np.array([0.0, 1.0, 0.0])
    right = np.cross(view, up)
    right /= np.linalg.norm(right)
    upv = np.cross(right, view)
    axes = np.vstack([right, upv, -view])                         # screen x, screen y, towards the eye
    allv = np.vstack([np.asarray(m.vertices) @ axes.T for m in meshes])
    lo, hi = (allv[:, :2].min(axis=0), allv[:, :2].max(axis=0)) if extent is None else extent
    pad = 0.04 * float(max(hi - lo))
    lo, hi = lo - pad, hi + pad
    pixel = float(max(hi - lo)) / size_px
    shape = (int(np.ceil((hi[0] - lo[0]) / pixel)) + 1, int(np.ceil((hi[1] - lo[1]) / pixel)) + 1)
    depth = np.full(shape[0] * shape[1], -np.inf)
    rgb = np.empty((shape[0] * shape[1], 3))
    rgb[:] = background
    L = np.asarray(light, float)
    L /= np.linalg.norm(L)
    for m, col in zip(meshes, colours):
        V = np.asarray(m.vertices) @ axes.T
        tri = V[np.asarray(m.faces)]
        n = np.asarray(m.face_normals) @ axes.T
        p, z, t = hits(tri, pixel, lo, shape)
        if not len(p):
            continue
        order = np.lexsort((-z, p))                               # per pixel the nearest first
        p, z, t = p[order], z[order], t[order]
        first = np.r_[True, p[1:] != p[:-1]]
        p, z, t = p[first], z[first], t[first]
        nearer = z > depth[p]
        p, z, t = p[nearer], z[nearer], t[nearer]
        depth[p] = z
        c = np.asarray(col, float)
        base = c[t] if c.ndim == 2 else np.broadcast_to(c, (len(t), 3))
        nn = n[t]
        nn = np.where((nn[:, 2] < 0)[:, None], -nn, nn)           # a back face seen through a gap: shade it as a front
        shade = 0.38 + 0.62 * np.clip(nn @ L, 0.0, 1.0)
        spec = 0.25 * np.clip(nn @ (L + np.array([0, 0, 1.0])) / np.linalg.norm(L + np.array([0, 0, 1.0])), 0, 1) ** 24
        rgb[p] = np.clip(base * shade[:, None] + 255 * spec[:, None], 0, 255)
    img = rgb.reshape(shape[1], shape[0], 3)[::-1].astype(np.uint8)    # row 0 at the top
    return img, {"origin": lo, "pixel": pixel, "axes": axes, "shape": shape}


def project(points, proj) -> np.ndarray:
    """Image (column, row) of 3-D points under a render's projection."""
    q = np.asarray(points, float) @ proj["axes"].T
    col = (q[:, 0] - proj["origin"][0]) / proj["pixel"] - 0.5
    row = proj["shape"][1] - 1 - ((q[:, 1] - proj["origin"][1]) / proj["pixel"] - 0.5)
    return np.column_stack([col, row])
