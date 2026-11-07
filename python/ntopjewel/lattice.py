"""Lattice bands: nTop's walled gyroid between a bore skin and the outer face, open to the outside (2026-11-06).

A lattice in jewelry has two masters the software never meets. The resin: a lattice closed inside a skin traps
uncured resin (and cups on the FEP), so every void has to open to the outside. The investment: the lattice's
negative space IS investment, which has to survive the burnout and the pour and then be washed out again - it can,
in an open lattice, the way it does in filigree, because the investment in the cells is one continuous network
anchored to the block through the open face, not a free-standing core, and after the quench water goes in at one
opening and out at another. A buried infill lattice (nTop's "shell and gyroid") has neither property, so this
module builds the exposed kind only:

    the profiled band; between a solid bore skin (`skin_mm`, tables lattice_skin_mm) and the outer face, between
    two solid rims (`rim_mm`), the metal is replaced by a walled gyroid - nTop's `gyroid_implicit` (cell `cell_mm`)
    thickened by `wall_mm` (`thicken_implicit`) - built in the bar frame (X radial, Y along the ring, Z axial) and
    wrapped round the ring by Remap Cylindrical Body with a mapping length of a whole number of cells
    (`cells_around` x `cell_mm`), so the pattern repeats N times round the ring and closes on itself.

    Band − Zone ∪ (Band ∩ Zone ∩ Lattice)    (ring_lattice.ntop; the zone as the textures': a hollow cylinder
                                              between the rims from the skin outwards)

Python holds the same geometry exactly - the gyroid is a formula, the wrap is the shank bars' (geom.remap_cylindrical:
X -> r, Y -> angle, Z -> z) - so the gate measures the built mesh against the design point by point, not against an
envelope: `lattice match` (the built mesh's inside / outside at thousands of points in the zone against the model),
`design volume` (nTop's integral against the model's grid integration), `sheet thickness` (rays through the sheets,
p1 against tables floors.lattice_member), `pore width` (rays across the voids against floors.lattice_pore and the
unit cell's own figure), **`open voids`** (the built mesh voxelised by scanline rays and flood-filled from the outer
face: a pocket that does not reach it fails the part - the trapped-resin check), the mask (bore, sides, rims as
designed) and the band checks. The design refuses a cell the floors cannot hold (unit_cell_stats: the sheet's share
and the pore - the sphere that passes - of the cell), a zone shallower than half a cell, a model whose metal is not
one piece or whose voids do not all reach the face (model_voids, the same flood fill on the design).

What nTop's blocks do, measured by the first real run (6 Nov, flat US 6 7 x 3.5, Mesh Tolerance 0.1; api_facts.json):
nTop's gyroid is the standard convention, unshifted (lattice match 98.7 %), Thicken is symmetric about the surface - but
**gyroid_implicit's field is the gyroid function scaled by cell / 2π, not a distance**: its gradient on the surface is
1.43-1.70 per cell radian (median 1.51), so Thicken Body's t gives a sheet t / |∇f| thick (0.450 for 0.6 asked, thinner
where the gradient is larger), and an Offset moves its faces by the offset / |∇f|. So the notebook thickens only a thin
SEED (`Seed Thickness`, in field units: gyroid_field_gradient x the true seed), re-distances it by the mesh round trip
(a true distance field) and grows it to the wall by an Offset (`Sheet Growth`, exact on a distance field). The second
run (7 Nov) read the sheet off the trim at p1 0.574, median 0.602 for 0.6, the faces where the ring-frame model puts
them (the seed is re-distanced AFTER the wrap, so the growth is a ring-frame distance: `seeded_sheet_sdf`), the design
volume +0.26 % - and found the LIPS: where a sheet runs nearly parallel under the outer face, the trim leaves a thin
plate (0.26-0.5 mm on that run). So the seed is trimmed by the band INSET by the growth before it is re-distanced and
grown: dilate(seed ∩ (band − g), g) is exactly the opening by g of the wall-thick sheet trimmed by the band (erosion
distributes over an intersection), so the growth is the opening - every lip is at least 2 g thick, and g = half the
marginal wall (tables floors.wall_marginal) - and one mesh round trip is gone. The seed is then wall − 2 g (0.1 at the
0.6 member floor), re-distanced at `Seed Mesh Tolerance` (SEED_VOXELS voxels across it). `lattice_sheet_correction_mm`
(tables settings) is the re-distance's loss on the sheet, added to the seed.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import band as bandmod
from . import fieldtex, gate, tables, texture
from .fieldtex import FieldTextureSpec, measure_texture

KIND = "gyroid"
LATTICE_RIM_MM = None        # a lattice band's rims: solid walls standing the zone's depth above the skin, so the good wall
                             # (tables floors.wall_good) rather than a texture's polished rim (the edge round + 0.1)
MIN_CELLS_DEEP = 0.5         # the zone at least this many cells deep, or the gyroid is a perforated plate
MAX_CELLS_DEEP = 6.0
MATCH_MIN = 0.98             # agreement of the built mesh with the model, point by point, inside the zone
MATCH_POINTS = 20000
VOLUME_TOL_PCT = 2.0         # nTop's integral against the model's (the first real run calibrates nTop's gyroid field)
LATTICE_OVERLAP_MM = 0.25    # the lattice body reaches at least this far into the skin and the rims (and past the growth): the
                             # union overlaps instead of meeting on a face (a face shared by two bodies is a membrane in the
                             # field and a crumb factory in a mesh boolean: 638 of them, 2026-11-06)
POCKET_MIN_MM3 = 0.03        # a void pocket counted only above this (thirty 0.1 mm voxels, a 0.3 mm pocket): under it the grid
                             # cannot tell a pocket from a sliver where a sheet leans on the skin (four of 0.004 mm³ on the first
                             # real part, at the grid's own size); slivers are counted and reported, not failed
SEED_MIN_MM = 0.1            # the thin seed sheet nTop thickens before the re-distance: at least this (the member floor less the
                             # lips' floor), re-distanced at a tolerance that puts SEED_VOXELS voxels across it
SEED_VOXELS = 4
LIP_MIN_SAMPLES = 100        # rays through lips for a p1; fewer are judged by their minimum
PORE_SHARE = 0.85            # the built pore statistic within this of the unit cell's own (the wrap stretches cells ±8 %)
RAY_SAMPLES = 4000
VOID_STEP_MM = 0.1           # the flood fill's voxel (the pore floor is ten of them)
GYROID_VARIANT = "standard"  # which convention nTop's gyroid_implicit follows: measured 2026-11-06 (api_facts: standard, unshifted)


def gyroid_field_gradient() -> float:
    """|∇f| of nTop's gyroid_implicit field at its surface (api_facts.json `gyroid_field_gradient`, measured 2026-11-06: 1.6):
    the field is the gyroid function scaled by cell / 2π, so a thickness or an offset in it is that many times smaller
    in millimetres. Refuses, naming the run, when it has not been measured."""
    from . import nb_jewel as nj
    try:
        return float(nj.api_fact("gyroid_field_gradient"))
    except nj.ConsoleError:
        raise ValueError("gyroid_field_gradient has not been measured on this nTop (ntop/api_facts.json): run `python -m ntopjewel "
                         "lattice` once with the fact set to 1.6 and read the sheet thickness the gate reports") from None


# ---- the gyroid --------------------------------------------------------------------------------------------
NEWTON_STEPS = 2             # the distance to the gyroid surface: two Newton steps along the gradient (1 % of the wall;
                             # the first alone is g / |∇g|, which reads a 0.6 mm sheet as 0.54 - measured 2026-11-06)


def gyroid_field(x, y, z, cell: float, variant: str = "standard"):
    """The gyroid level-set function g and its gradient at (x, y, z), cell size `cell` (numpy arrays or floats).
    `standard`: sin x cos y + sin y cos z + sin z cos x (x, y, z in cell radians); `mirrored`: its enantiomer
    (x and y exchanged). The surface is g = 0."""
    k = 2 * math.pi / cell
    if variant == "mirrored":
        x, y = y, x
    sx, cx = np.sin(k * x), np.cos(k * x)
    sy, cy = np.sin(k * y), np.cos(k * y)
    sz, cz = np.sin(k * z), np.cos(k * z)
    g = sx * cy + sy * cz + sz * cx
    gx = k * (cx * cy - sz * sx)
    gy = k * (-sx * sy + cy * cz)
    gz = k * (-sy * sz + cz * cx)
    if variant == "mirrored":
        gx, gy = gy, gx
    return g, gx, gy, gz


NEAR_WALLS = 1.5             # refine the distance only within this many walls of the surface by the first-order reading
                             # (which over-reads: a sixth at a wall, more further out, never under): further away a point
                             # is outside the sheet whatever the refinement would say, and Newton from far away (|∇g|
                             # small) lands anywhere


def surface_distance(x, y, z, cell: float, variant: str = "standard", steps: int = NEWTON_STEPS, near: float | None = None,
                     normal: bool = False):
    """The distance from (x, y, z) to the gyroid surface. The first-order reading g / |∇g| everywhere; within `near`
    of the surface by that reading, the point projected onto the surface by `steps` Newton steps along the gradient
    (p -> p − g ∇g / |∇g|²) and the distance to where it lands. One step is the first-order reading, which over-reads
    the distance by a tenth at the sheet's face (so a 0.6 mm sheet in a 3.5 mm cell comes out 0.54); two read it to 1 %
    (measured on the unit cell, 2026-11-06). `normal`: also the unit gradient at the foot (where the point projects;
    at the point itself when it was not refined) and the sign of g at the point - (d, sign, (nx, ny, nz))."""
    x0, y0, z0 = np.broadcast_arrays(np.asarray(x, dtype=float), np.asarray(y, dtype=float), np.asarray(z, dtype=float))
    scalar = x0.ndim == 0
    if scalar:
        x0, y0, z0 = x0.reshape(1), y0.reshape(1), z0.reshape(1)
    g, gx, gy, gz = gyroid_field(x0, y0, z0, cell, variant)
    n2 = np.maximum(gx * gx + gy * gy + gz * gz, 1e-12)
    n = np.sqrt(n2)
    d = np.abs(g) / n
    nx, ny, nz = gx / n, gy / n, gz / n
    sel = (np.ones(d.shape, dtype=bool) if near is None else d < near) if steps > 1 else np.zeros(d.shape, dtype=bool)
    if sel.any():
        px, py, pz = x0[sel] - (g * gx / n2)[sel], y0[sel] - (g * gy / n2)[sel], z0[sel] - (g * gz / n2)[sel]
        for _ in range(steps - 1):
            g2, gx2, gy2, gz2 = gyroid_field(px, py, pz, cell, variant)
            m2 = np.maximum(gx2 * gx2 + gy2 * gy2 + gz2 * gz2, 1e-12)
            px, py, pz = px - g2 * gx2 / m2, py - g2 * gy2 / m2, pz - g2 * gz2 / m2
        d[sel] = np.sqrt((px - x0[sel]) ** 2 + (py - y0[sel]) ** 2 + (pz - z0[sel]) ** 2)
        if normal:
            _, ex, ey, ez = gyroid_field(px, py, pz, cell, variant)
            en = np.sqrt(np.maximum(ex * ex + ey * ey + ez * ez, 1e-12))
            nx[sel], ny[sel], nz[sel] = ex / en, ey / en, ez / en
    if not normal:
        return float(d[0]) if scalar else d
    sign = np.where(g >= 0, 1.0, -1.0)
    if scalar:
        return float(d[0]), float(sign[0]), (float(nx[0]), float(ny[0]), float(nz[0]))
    return d, sign, (nx, ny, nz)


def sheet_sdf(x, y, z, cell: float, wall: float, variant: str = "standard", shift=(0.0, 0.0, 0.0)):
    """Signed distance to the walled gyroid in the bar frame: negative inside the sheet (the surface's two sides,
    wall / 2 each)."""
    d = surface_distance(np.asarray(x) - shift[0], np.asarray(y) - shift[1], np.asarray(z) - shift[2], cell, variant,
                         near=NEAR_WALLS * wall)
    return d - wall / 2.0


def _gyroid_scalar(x: float, y: float, z: float, k: float):
    sx, cx, sy, cy, sz, cz = math.sin(k * x), math.cos(k * x), math.sin(k * y), math.cos(k * y), math.sin(k * z), math.cos(k * z)
    return sx * cy + sy * cz + sz * cx, k * (cx * cy - sz * sx), k * (-sx * sy + cy * cz), k * (-sy * sz + cz * cx)


def _surface_distance_scalar(x: float, y: float, z: float, k: float, near: float):
    """surface_distance(normal=True) for one point in plain Python (manifold3d's level set calls it a million times):
    the distance, the sign of g at the point and the unit gradient at the foot."""
    g, gx, gy, gz = _gyroid_scalar(x, y, z, k)
    n2 = max(gx * gx + gy * gy + gz * gz, 1e-12)
    n = math.sqrt(n2)
    sign = 1.0 if g >= 0 else -1.0
    d1 = abs(g) / n
    if d1 >= near:
        return d1, sign, gx / n, gy / n, gz / n
    px, py, pz = x - g * gx / n2, y - g * gy / n2, z - g * gz / n2
    for _ in range(NEWTON_STEPS - 1):
        g2, gx2, gy2, gz2 = _gyroid_scalar(px, py, pz, k)
        m2 = max(gx2 * gx2 + gy2 * gy2 + gz2 * gz2, 1e-12)
        px, py, pz = px - g2 * gx2 / m2, py - g2 * gy2 / m2, pz - g2 * gz2 / m2
    _, ex, ey, ez = _gyroid_scalar(px, py, pz, k)
    en = math.sqrt(max(ex * ex + ey * ey + ez * ez, 1e-12))
    return math.sqrt((px - x) ** 2 + (py - y) ** 2 + (pz - z) ** 2), sign, ex / en, ey / en, ez / en


def _sheet_sdf_scalar(x: float, y: float, z: float, k: float, half: float) -> float:
    return _surface_distance_scalar(x, y, z, k, NEAR_WALLS * 2 * half)[0] - half


def _wedge_distance_scalar(a: float, b: float, cos_t: float) -> float:
    if a <= 0 and b <= 0:
        return max(a, b)
    best = math.inf
    if a > 0 and b - a * cos_t <= 0:
        best = a
    if b > 0 and a - b * cos_t <= 0:
        best = min(best, b)
    if best < math.inf:
        return best
    sin2 = max(1.0 - cos_t * cos_t, 1e-6)
    return math.sqrt(max(a * a + b * b - 2 * a * b * cos_t, 0.0) / sin2)


def _seeded_sheet_sdf_scalar(r: float, y: float, z: float, outer: float, k: float, seed_half: float, growth: float,
                             lam: float, near: float) -> float:
    """seeded_sheet_sdf for one point (bar coordinates r, y, z; `outer` the dome's radius at z; `lam` the wrap's
    L / 2πr)."""
    d, sign, nx, ny, nz = _surface_distance_scalar(r, y, z, k, near)
    factor = math.sqrt(nx * nx + (lam * ny) ** 2 + nz * nz)
    return _wedge_distance_scalar((d - seed_half) / factor, (r - outer) + growth, sign * nx / factor) - growth


def bar_coordinates(X, Y, Z, wrap_length: float):
    """Ring frame -> bar frame under Remap Cylindrical Body: x = r, y = wrap length x angle / 2π, z = z."""
    r = np.hypot(X, Y)
    th = np.mod(np.arctan2(Y, X), 2 * math.pi)
    return r, wrap_length * th / (2 * math.pi), np.asarray(Z)


def sheet_sdf_ring(X, Y, Z, cell: float, wall: float, wrap_length: float, variant: str = "standard", shift=(0.0, 0.0, 0.0)):
    x, y, z = bar_coordinates(X, Y, Z, wrap_length)
    return sheet_sdf(x, y, z, cell, wall, variant, shift)


def _wedge_distance(a, b, cos_t):
    """Distance to a convex wedge E = {a' <= 0} ∩ {b' <= 0} whose two faces have outward normals at angle θ
    (cos θ = `cos_t`), from a point at signed distances `a` and `b` outside those faces: the nearer face where its
    foot lies on E, else the wedge's edge (the linear local picture of a sheet's end at the dome). Negative inside."""
    a, b, cos_t = np.broadcast_arrays(np.asarray(a, float), np.asarray(b, float), np.asarray(cos_t, float))
    inside = (a <= 0) & (b <= 0)
    out = np.where(inside, np.maximum(a, b), np.inf)
    face_a = (a > 0) & (b - a * cos_t <= 0)
    face_b = (b > 0) & (a - b * cos_t <= 0)
    out = np.where(face_a, np.minimum(out, a), out)
    out = np.where(face_b, np.minimum(out, b), out)
    sin2 = np.maximum(1.0 - cos_t * cos_t, 1e-6)
    corner = np.sqrt(np.maximum(a * a + b * b - 2 * a * b * cos_t, 0.0) / sin2)
    return np.where(np.isinf(out), corner, out)


def ring_factor(nx, ny, nz, r, wrap_length: float):
    """A distance across the gyroid surface measured in the bar frame, divided by this, is the same distance in the ring
    frame: the wrap scales the bar's Y by 2πr / L, so a surface with unit bar normal n is |J^-T n| = sqrt(n_r² + (L / 2πr)²
    n_t² + n_z²) times closer in the ring frame. 0.96-1.08 across a 3.5 mm-cell band (7 Nov)."""
    lam = wrap_length / (2 * math.pi * np.maximum(r, 1e-9))
    return np.sqrt(nx * nx + (lam * ny) ** 2 + nz * nz)


def seeded_sheet_sdf(X, Y, Z, cell: float, seed: float, growth: float, wrap_length: float, outer_radius_at,
                     variant: str = "standard", shift=(0.0, 0.0, 0.0)):
    """Signed distance (negative inside) to the lattice sheet nTop builds in the zone, in the ring frame: the seed (the
    gyroid surface thickened to `seed` mm in the bar frame) wrapped round the ring, trimmed by the band inset by
    `growth`, re-distanced (in the ring frame: after the wrap) and grown by `growth` - dilate(seed ∩ (band − g), g),
    which is the opening by g of the wall-thick sheet trimmed by the band. Away from the dome that is the seed's ring
    distance less g (the bar distance over ring_factor: measured on the second run, rms 0.006 against the bar-frame
    sheet's 0.010); near it the inset seed ∩ the inset dome is a wedge whose two faces' outward normals meet at the
    angle whose cosine is the seed normal's radial component (_wedge_distance), and the sheet is everything within g of
    it: a sheet crossing the dome ends in a round of radius g, and a lip where a sheet runs under the dome is at least
    2 g thick."""
    r = np.hypot(X, Y)
    th = np.mod(np.arctan2(Y, X), 2 * math.pi)
    z = np.asarray(Z, float)
    x, y = r, wrap_length * th / (2 * math.pi)
    d, sign, (nx, ny, nz) = surface_distance(x - shift[0], y - shift[1], z - shift[2], cell, variant,
                                             near=NEAR_WALLS * (seed + 2 * growth), normal=True)
    factor = ring_factor(nx, ny, nz, r, wrap_length)
    a = (d - seed / 2) / factor                                 # outside the seed, in the ring frame
    b = (r - outer_radius_at(z)) + growth                       # outside the dome inset by the growth
    return _wedge_distance(a, b, sign * nx / factor) - growth


_CELL_STATS: dict = {}


def unit_cell_stats(cell: float, wall: float, n: int = 72) -> dict:
    """What a cell of the walled gyroid is: the sheet's share of the volume and the pore - the diameter of the
    largest sphere that passes through the void (its distance transform, on a periodic tiling). Cached."""
    key = (round(cell, 6), round(wall, 6), n)
    if key in _CELL_STATS:
        return _CELL_STATS[key]
    from scipy.ndimage import distance_transform_edt
    s = (np.arange(n) + 0.5) * cell / n
    x, y, z = np.meshgrid(s, s, s, indexing="ij")
    sheet = sheet_sdf(x, y, z, cell, wall) <= 0
    void = np.tile(~sheet, (2, 2, 2))
    pore = 2.0 * float(distance_transform_edt(void, sampling=cell / n).max())
    out = {"fraction": float(sheet.mean()), "pore_mm": pore}
    _CELL_STATS[key] = out
    return out


# ---- the spec ----------------------------------------------------------------------------------------------
@dataclass
class GyroidSpec(FieldTextureSpec):
    """A band whose metal between a bore skin and the outer face is a walled gyroid, open to the outside."""
    cell_mm: float = 3.5                    # the gyroid's cubic cell, in the bar frame (a cell round the ring at the zone's mid radius)
    wall_mm: float = 0.6                    # the sheet's thickness (nTop's Thicken Body)
    skin_mm: float | None = None            # the solid bore skin; None = tables lattice_skin_mm

    kind = KIND
    adds_metal = False

    # -- the zone: from the top of the skin to the outer face, between the rims --
    @property
    def skin(self) -> float:
        return float(self.skin_mm) if self.skin_mm is not None else tables.SETTINGS["lattice_skin_mm"]

    @property
    def rim(self) -> float:
        return float(self.rim_mm) if self.rim_mm is not None else max(tables.FLOORS["wall_good"], self.band.edge_round + 0.1)

    @property
    def zone_inner_radius(self) -> float:
        """The top of the skin: the bore's highest point inside the zone (a comfort relief lifts it at the edges) plus the skin."""
        zh = self.zone_half_width
        highest = max(self.band.bore_radius_at(z) for z in np.linspace(-zh, zh, 41))
        return highest + self.skin

    @property
    def depth_mm(self) -> float:
        """The zone's depth at its edge (the base's thin-wall check reads it: what is left under it is the skin)."""
        return self.band.outer_radius_at(self.zone_half_width) - self.zone_inner_radius

    @property
    def zone_depth_mm(self) -> float:
        """The zone's depth at the mid-plane, its deepest."""
        return self.band.outer_radius_at(0.0) - self.zone_inner_radius

    @property
    def mid_radius(self) -> float:
        return (self.zone_inner_radius + self.band.outer_radius_at(0.0)) / 2.0

    @property
    def cells_around(self) -> int:
        """Whole cells round the ring at the zone's mid radius: the wrap closes on itself."""
        return max(3, int(round(2 * math.pi * self.mid_radius / self.cell_mm)))

    @property
    def wrap_length(self) -> float:
        """Remap Cylindrical's Y mapping length: N cells, so the pattern is periodic round the ring (a cell at the
        mid radius is `cell_mm` long to within half a cell in N; the wrap stretches it by r / r_mid elsewhere)."""
        return self.cells_around * self.cell_mm

    @property
    def cells_deep(self) -> float:
        return self.zone_depth_mm / self.cell_mm

    @property
    def notebook_name(self) -> str:
        return "ring_lattice"

    def cell(self) -> dict:
        return unit_cell_stats(self.cell_mm, self.wall_mm)

    # -- the notebook --
    @property
    def growth_mm(self) -> float:
        """The Offset that grows the re-distanced seed to the wall - and the lattice's round: the seed is trimmed by the band
        inset by it, so the growth is the opening of the trimmed sheet and every lip where a sheet runs under the outer face
        comes out at least 2 g thick. Half the marginal wall (tables floors.wall_marginal), so the lips are walls."""
        return round(tables.FLOORS["wall_marginal"] / 2, 4)

    @property
    def seed_design_mm(self) -> float:
        """The seed as it should come out of the re-distance: the wall less twice the growth (0.1 at the member floor)."""
        return round(self.wall_mm - 2 * self.growth_mm, 4)

    @property
    def seed_mm(self) -> float:
        """The seed asked of nTop: the design's plus the re-distance's measured loss (tables lattice_sheet_correction_mm)."""
        return round(self.seed_design_mm + tables.SETTINGS["lattice_sheet_correction_mm"], 4)

    @property
    def seed_field_mm(self) -> float:
        """Thicken Body's input for the seed: the true seed times the field's gradient (api_facts gyroid_field_gradient)."""
        return round(self.seed_mm * gyroid_field_gradient(), 4)

    @property
    def seed_tolerance_mm(self) -> float:
        """The seed's re-distance mesh: the band's Mesh Tolerance, or finer, so SEED_VOXELS voxels (half the tolerance each)
        span the seed - 0.05 for a 0.1 seed."""
        return round(min(self.band.mesh_tolerance_mm, 2 * self.seed_design_mm / SEED_VOXELS), 4)

    @property
    def overlap(self) -> float:
        """How far the lattice zone reaches into the skin and the rims: past the growth, so the union overlaps and the grown
        seed's ends stay buried."""
        return round(max(LATTICE_OVERLAP_MM, self.growth_mm + 0.05), 4)

    @property
    def end_margin(self) -> float:
        """Rays along a sheet's normal start this far from the dome, the skin's top and the rims: off the rounded ends (a ray
        from a nose reads the nose)."""
        return self.growth_mm + 0.15

    @property
    def lip_margin(self) -> float:
        """The generic wall check's radial and axial rays keep this far from the dome inside the zone: a lip's nose spans 2 g
        below it, and a chord through a round is no wall."""
        return 2 * self.growth_mm + 0.15

    def texture_inputs(self) -> dict:
        """The lattice's inputs (nb_lattice.LATTICE_SPECS, before the zone's): the gyroid, the seed, its re-distance and growth
        (the band inset by the growth trims it), the grown zone."""
        zh = self.zone_half_width
        return {"Cell Size": self.cell_mm, "Seed Thickness": self.seed_field_mm, "Seed Mesh Tolerance": self.seed_tolerance_mm,
                "Sheet Growth": self.growth_mm, "Band Inset": -self.growth_mm, "Wrap Length": round(self.wrap_length, 4),
                "Lattice Inner Radius": round(self.zone_inner_radius - self.overlap, 4),
                "Lattice Z Top": round(zh + self.overlap, 4), "Lattice Z Bottom": -round(zh + self.overlap, 4)}

    def texture_design(self) -> dict:
        return {"cell": self.cell_mm, "wall": self.wall_mm, "skin": round(self.skin, 4), "cells_around": self.cells_around,
                "variant": GYROID_VARIANT, "seed": self.seed_mm, "seed_field": self.seed_field_mm, "seed_tolerance": self.seed_tolerance_mm,
                "growth": self.growth_mm, "overlap": self.overlap}

    @property
    def tag(self) -> str:
        return f"c{self.cell_mm:g}w{self.wall_mm:g}"

    @property
    def stem(self) -> str:
        b = self.band
        return f"ring_lattice_{self.kind}_{b.profile}_{b.label}_w{b.width_mm:g}_t{b.thickness_mm:g}_{self.tag}_{self.spec_id}"

    # -- the model --
    def outer_radius_at(self, z):
        """The zone's outside: the dome, vectorised (the band's outer_radius_at takes one z)."""
        b = self.band
        z = np.asarray(z, dtype=float)
        if b.dome <= bandmod.MIN_SAGITTA:
            return np.full(z.shape, b.outer_radius_mm)
        rd, td = b.dome_torus
        return rd + np.sqrt(np.maximum(td * td - z * z, 0.0))

    def in_zone_band(self, r, z, margin: float = 0.0):
        """Inside the zone ∩ band: from the skin's top to the dome, between the rims (`margin` shrinks it)."""
        zh = self.zone_half_width - margin
        return (np.abs(z) <= zh) & (r >= self.zone_inner_radius + margin) & (r <= self.outer_radius_at(z) - margin)

    def lattice_sdf(self, X, Y, Z):
        """The lattice sheet as nTop builds it in the zone (seeded_sheet_sdf: the inset seed grown by the growth)."""
        return seeded_sheet_sdf(X, Y, Z, self.cell_mm, self.seed_design_mm, self.growth_mm, self.wrap_length, self.outer_radius_at,
                                GYROID_VARIANT)

    def in_sheet(self, X, Y, Z):
        return self.lattice_sdf(X, Y, Z) <= 0.0

    def in_metal(self, X, Y, Z):
        """The designed body at ring-frame points: the band, less the zone where the sheet is not."""
        r = np.hypot(X, Y)
        band = self.band.section_mask(r, np.asarray(Z))
        return band & (~self.in_zone_band(r, Z) | self.in_sheet(X, Y, Z))

    def zone_band_volume_mm3(self) -> float:
        """The zone ∩ band: π (R(z)² − r_in²) integrated over the zone's width (the solid the lattice replaces)."""
        zh = self.zone_half_width
        z = np.linspace(-zh, zh, 801)
        f = math.pi * (self.outer_radius_at(z) ** 2 - self.zone_inner_radius ** 2)
        return float(np.trapezoid(f, z)) if hasattr(np, "trapezoid") else float(np.trapz(f, z))

    def sheet_volume_mm3(self, step: float = 0.025) -> float:
        """The walled gyroid inside the zone ∩ band, by grid integration over ONE angular period (the pattern
        repeats cells_around times) with a smoothed indicator (a cell within half a step of the sheet's surface counts
        by its distance), N times. Cached."""
        key = ("sheet", step)
        if key in self._cache:
            return self._cache[key]
        N, L = self.cells_around, self.wrap_length
        zh, r_in = self.zone_half_width, self.zone_inner_radius
        r_max = float(self.outer_radius_at(0.0))
        th_period = 2 * math.pi / N
        r = np.arange(r_in + step / 2, r_max, step)
        n_th = max(8, int(math.ceil(th_period * self.mid_radius / step)))
        dth = th_period / n_th
        th = (np.arange(n_th) + 0.5) * dth
        z = np.arange(-zh + step / 2, zh, step)
        total = 0.0
        R, TH = np.meshgrid(r, th, indexing="ij")
        X, Y = R * np.cos(TH), R * np.sin(TH)
        for zk in z:                                           # slice by slice: the arrays stay small
            d = self.lattice_sdf(X, Y, np.full(R.shape, zk))
            inside = np.clip(0.5 - d / step, 0.0, 1.0)         # a smoothed indicator: O(step²)
            total += float(np.sum(inside * R)) * step * dth * step
        vol = total * N
        self._cache[key] = vol
        return vol

    def design_volume_mm3(self) -> float:
        """The band, less the zone, plus the sheet inside it: the independent arithmetic nTop's integral is held to."""
        return self.band.design_volume_mm3() - self.zone_band_volume_mm3() + self.sheet_volume_mm3()

    def max_removal_mm3(self) -> float:
        return self.zone_band_volume_mm3()

    def triangles_estimate(self) -> float:
        """The band's surface, the zone's face replaced by the sheet's two faces (a gyroid has 3.09 / cell of surface per
        volume), at the band's Mesh Tolerance."""
        sheet_area = 2 * 3.09 / self.cell_mm * self.sheet_volume_mm3() / max(self.cell()["fraction"], 1e-6)
        area = self.model().area_mm2() - self.zone_face_area_mm2() + sheet_area
        return tables.mesh_triangles_estimate(area, self.band.mesh_tolerance_mm)

    def model_voids(self, step: float = 0.08) -> dict:
        """The design on a voxel grid: is the metal one piece (the sheet joined to the skin and the rims), and does
        every void inside the zone reach the outer face? The same flood fill the gate runs on the built mesh."""
        from scipy.ndimage import label
        b = self.band
        R = b.outer_radius_mm + step
        zh = self.zone_half_width
        xs = np.arange(-R, R + step / 2, step)
        zs = np.arange(-b.width_mm / 2 - step, b.width_mm / 2 + step, step)
        X, Y = np.meshgrid(xs, xs, indexing="ij")
        r = np.hypot(X, Y)
        metal = np.zeros((len(xs), len(xs), len(zs)), dtype=bool)
        zone_band = np.zeros_like(metal)
        for k, zk in enumerate(zs):
            Z = np.full(X.shape, zk)
            metal[:, :, k] = self.in_metal(X, Y, Z)
            zone_band[:, :, k] = self.in_zone_band(r, Z)
        lab, n = label(metal)
        sizes = np.bincount(lab.ravel())[1:]
        pieces = int((sizes * step ** 3 > POCKET_MIN_MM3).sum())
        return {"metal_pieces": pieces, **_void_components(~metal & zone_band, r, zs, self, step)}

    def design_mesh(self):
        """Python's own mesh of the design (manifold3d's level set of the lattice in the zone, united with the band
        less the zone): what the simulated nTop exports and what --write-design writes. Not the gate's reference -
        the gate's arithmetic never touches a mesh of the design."""
        if "mesh" not in self._cache:
            self._cache["mesh"] = lattice_mesh(self.band.notebook_inputs(""), self.cell_mm, self.seed_design_mm, self.growth_mm,
                                               self.wrap_length, self.zone_half_width, self.zone_inner_radius, self.band.mesh_tolerance_mm,
                                               overlap=self.overlap)
        return self._cache["mesh"]

    # -- checks --
    def validate(self) -> list[str]:
        p = list(self.band.validate())
        if p:
            return p
        fl = tables.FLOORS
        if self.wall_mm < fl["lattice_member"] - 1e-9:
            p.append(f"wall {self.wall_mm:g} mm: at least {fl['lattice_member']:g} (floors.lattice_member)")
        if self.wall_mm > 2.0:
            p.append(f"wall {self.wall_mm:g} mm: at most 2")
        if not 0.5 <= self.cell_mm <= 20:
            p.append(f"cell {self.cell_mm:g} mm: 0.5..20")
        if self.skin < fl["wall_good"] - 1e-9:
            p.append(f"skin {self.skin:g} mm: at least {fl['wall_good']:g} (the band the finger feels)")
        rim_floor = max(self.band.edge_round + 0.1, fl["wall_marginal"])
        if self.rim < rim_floor - 1e-9:
            p.append(f"rim {self.rim:g} mm: at least {rim_floor:g} (the edge round + 0.1, and a wall: the rims stand the zone's depth)")
        if self.zone_half_width < 0.5:
            p.append(f"the rims ({self.rim:g} each) leave {2 * self.zone_half_width:.2f} mm of face: at least 1.0")
        if p:
            return p
        if self.wall_mm >= self.cell_mm / 2:
            p.append(f"a {self.wall_mm:g} mm wall in a {self.cell_mm:g} mm cell leaves no void (wall under half the cell)")
            return p
        cell = self.cell()
        if cell["pore_mm"] < fl["lattice_pore"] - 1e-9:
            p.append(f"the void's pore is {cell['pore_mm']:.2f} mm (the sphere that passes between {self.wall_mm:g} mm sheets in a "
                     f"{self.cell_mm:g} mm cell); at least {fl['lattice_pore']:g} for the investment and the wash-out "
                     f"(floors.lattice_pore): a larger --cell or a thinner --member")
        deep = self.cells_deep
        if deep < MIN_CELLS_DEEP:
            p.append(f"the zone is {self.zone_depth_mm:.2f} mm deep, {deep:.2f} cells: at least {MIN_CELLS_DEEP:g} (a thicker band, "
                     f"a smaller cell) - shallower is a perforated plate, not a lattice")
        elif deep > MAX_CELLS_DEEP:
            p.append(f"{deep:.1f} cells deep: at most {MAX_CELLS_DEEP:g}")
        if self.depth_mm < self.wall_mm:
            p.append(f"at the zone's edge the lattice is {self.depth_mm:.2f} mm deep, under the wall ({self.wall_mm:g})")
        if self.seed_design_mm < SEED_MIN_MM - 1e-9:
            p.append(f"a {self.wall_mm:g} mm member leaves a {self.seed_design_mm:.2f} seed under the lips' {2 * self.growth_mm:g} round: "
                     f"at least {2 * self.growth_mm + SEED_MIN_MM:g}")
        reach = self.overlap + self.growth_mm
        if reach + 0.1 > self.skin + 1e-9:
            p.append(f"the lattice reaches {reach:.2f} mm into the {self.skin:g} mm skin (the overlap and the growth): a thicker --skin")
        if reach + 0.1 > self.rim + 1e-9:
            p.append(f"the lattice reaches {reach:.2f} mm into the {self.rim:g} mm rims (the overlap and the growth): a wider --rim")
        voxel = self.band.mesh_tolerance_mm / 2
        if self.wall_mm < 6 * voxel - 1e-9:
            p.append(f"a {self.wall_mm:g} mm sheet spans under 6 voxels at Mesh Tolerance {self.band.mesh_tolerance_mm:g}: "
                     f"--tolerance {self.wall_mm / 3:.3g} or finer")
        if p:
            return p
        tri = self.triangles_estimate()
        if tri > texture.MAX_TRIANGLES:
            p.append(f"about {tri / 1e6:.1f} M triangles at Mesh Tolerance {self.band.mesh_tolerance_mm:g}: past the gate's "
                     f"{texture.MAX_TRIANGLES / 1e6:g} M limit (a coarser --tolerance)")
        v = self.model_voids()
        if v["metal_pieces"] != 1:
            p.append(f"the design is {v['metal_pieces']} pieces of metal, not one: a sheet left unattached to the skin or the rims "
                     f"(another --cell, a deeper zone)")
        if v["pockets"]:
            worst = v["pockets"][0]
            p.append(f"{len(v['pockets'])} void pocket{'s' if len(v['pockets']) > 1 else ''} in the design never reach the outer face "
                     f"(the largest {worst['mm3']:.3f} mm³ at {worst['theta_deg']:.0f}°, z {worst['z']:+.2f}): resin and investment "
                     f"would be trapped there - another --cell or --member")
        return p

    def wall_floor(self) -> float:
        return tables.FLOORS["wall_marginal"]

    def texture_line(self) -> str:
        c = self.cell()
        return (f"gyroid (nTop's gyroid_implicit: a {self.seed_design_mm:g} seed wrapped, trimmed by the band inset {self.growth_mm:g}, "
                f"re-distanced at {self.seed_tolerance_mm:g} and grown by {self.growth_mm:g} - lips at least {2 * self.growth_mm:g}): "
                f"{self.cell_mm:g} mm cells, {self.wall_mm:g} mm sheets, {self.cells_around} cells round the ring (wrap length "
                f"{self.wrap_length:.3f}), {self.cells_deep:.2f} cells deep; the sheet {c['fraction']:.0%} of the cell, pore "
                f"{c['pore_mm']:.2f} mm; skin {self.skin:g}")

    def result_notes(self, ntop_vol: float | None) -> list[str]:
        plain = self.plain_volume_mm3()
        if ntop_vol is None:
            return []
        w_plain, w = tables.weight_g(plain, "sterling"), tables.weight_g(ntop_vol, "sterling")
        return [f"the lattice saves {plain - ntop_vol:.1f} mm³ of {plain:.1f} ({1 - ntop_vol / plain:.0%}): sterling {w:.2f} g "
                f"against the solid band's {w_plain:.2f} g"]

    def describe(self) -> str:
        b = self.band
        return (f"{self.stem}: {b.profile} {b.label}, inner Ø {b.inner_diameter_mm:.3f}, {b.width_mm:g} x {b.thickness_mm:g}\n"
                f"  {self.texture_line()}\n"
                f"  zone: r {self.zone_inner_radius:.3f} .. {self.outer_radius_at(0.0):.3f} (depth {self.zone_depth_mm:.2f}), "
                f"|z| <= {self.zone_half_width:.2f} (rims {self.rim:.2f})\n"
                f"  solid band {self.plain_volume_mm3():.2f} mm³, the lattice band {self.design_volume_mm3():.2f} "
                f"({self.design_volume_mm3() / self.plain_volume_mm3():.0%}; sterling {tables.weight_g(self.design_volume_mm3(), 'sterling'):.2f} g "
                f"against {tables.weight_g(self.plain_volume_mm3(), 'sterling'):.2f}); about {self.triangles_estimate() / 1e6:.1f} M triangles "
                f"at Mesh Tolerance {b.mesh_tolerance_mm:g}")


def make_spec(band: bandmod.BandSpec, **kw) -> GyroidSpec:
    return GyroidSpec(band, **kw)


# ---- the mesh of the design (Python's; the simulated nTop's) ---------------------------------------------
def _manifold_to_trimesh(man):
    """A manifold3d level set as a Trimesh, its topology kept (vertex merging on the float32 coordinates breaks the
    watertightness of a lattice: seen 2026-11-06)."""
    import trimesh
    mm = man.to_mesh()
    return trimesh.Trimesh(np.asarray(mm.vert_properties)[:, :3].astype(float), np.asarray(mm.tri_verts), process=False)


def lattice_mesh(values: dict, cell: float, seed: float, growth: float, wrap_length: float, zone_half_width: float,
                 zone_inner_radius: float, mesh_tolerance: float, lattice: bool = True, closed: bool = False,
                 overlap: float = LATTICE_OVERLAP_MM, min_edge: float = 0.12):
    """The lattice band from ring_lattice's numbers: the profiled band (geom.band_mesh of the band inputs, opened) less
    the zone, united with manifold3d's level set of the seeded sheet (seeded_sheet_sdf: the seed inset and grown)
    inside the zone (reaching `overlap` into the skin and the rims, so the union overlaps). The level set's edge is the
    Mesh Tolerance (at least `min_edge`): a 0.1 edge on a 7 x 3.5 band is 1.1 M triangles and half a minute.
    `lattice=False`: the zone simply emptied (a notebook whose lattice never built); `closed=True`: the zone's outer
    face left as a skin over the lattice (every void a pocket)."""
    import manifold3d as m3
    import shapely
    import trimesh
    from . import geom
    band = geom.band_mesh(values)
    R_out = float(values["Outer Radius"])
    rd, td = float(values["Dome Ring Radius"]), float(values["Dome Tube Radius"])
    zh, r_in = float(zone_half_width), float(zone_inner_radius)
    zone = geom.revolve_section(shapely.box(r_in, -zh, R_out + 1.0, zh), sections=360)
    body = trimesh.boolean.difference([band, zone], engine="manifold")
    if not lattice:
        return body
    k = 2 * math.pi / cell
    two_pi = 2 * math.pi
    seed_half, near = seed / 2.0, NEAR_WALLS * (seed + 2 * growth)

    def sdf(x, y, z):                                           # positive inside (manifold's convention)
        r = math.hypot(x, y)
        th = math.atan2(y, x) % two_pi
        dome = rd + math.sqrt(max(td * td - z * z, 0.0)) if td < 400 else R_out
        outer = min(R_out, dome)
        lam = wrap_length / (two_pi * max(r, 1e-9))
        body = _seeded_sheet_sdf_scalar(r, wrap_length * th / two_pi, z, outer, k, seed_half, growth, lam, near)
        d = max(r_in - overlap - r, abs(z) - zh - overlap, body)
        return -d

    edge = max(min_edge, mesh_tolerance)
    lat = m3.Manifold.level_set(sdf, (-R_out - 0.5, -R_out - 0.5, -zh - 0.2, R_out + 0.5, R_out + 0.5, zh + 0.2), edge, 0.0)
    lat_mesh = _manifold_to_trimesh(lat)
    parts = [body, lat_mesh]
    if closed:                                                  # a skin over the zone's outer face
        skin = geom.revolve_section(shapely.box(R_out - 0.3, -zh, R_out + 1.0, zh), sections=360)
        parts.append(trimesh.boolean.intersection([skin, band], engine="manifold"))
    out = trimesh.boolean.union(parts, engine="manifold")
    out.merge_vertices()
    return out


# ---- the gate ------------------------------------------------------------------------------------------------
def _void_components(void: np.ndarray, r_xy: np.ndarray, zs: np.ndarray, spec: GyroidSpec, step: float) -> dict:
    """Label the void voxels inside the zone (6-connected); a component reaches the outer face when one of its
    voxels lies within 1.5 steps of the dome. Returns the pockets that do not (largest first), the open area."""
    from scipy.ndimage import label
    lab, n = label(void)
    if n == 0:
        return {"void_components": 0, "pockets": [], "open_voxels": 0}
    outer = np.zeros_like(void)
    for k, zk in enumerate(zs):
        outer[:, :, k] = void[:, :, k] & (r_xy >= float(spec.outer_radius_at(zk)) - 1.5 * step)
    reach = np.zeros(n + 1, dtype=bool)
    reach[np.unique(lab[outer])] = True
    reach[0] = True
    sizes = np.bincount(lab.ravel(), minlength=n + 1)
    pockets = []
    slivers = 0
    for i in range(1, n + 1):
        if reach[i]:
            continue
        if sizes[i] * step ** 3 < POCKET_MIN_MM3:
            slivers += 1
            continue
        idx = np.argwhere(lab == i)
        c = idx.mean(axis=0)
        ix, iy, iz = int(round(c[0])), int(round(c[1])), int(round(c[2]))
        nx = void.shape[0]
        x = (ix - (nx - 1) / 2) * step
        y = (iy - (nx - 1) / 2) * step
        pockets.append({"mm3": float(sizes[i] * step ** 3), "theta_deg": float(math.degrees(math.atan2(y, x)) % 360),
                        "z": float(zs[min(iz, len(zs) - 1)]), "r": float(math.hypot(x, y))})
    pockets.sort(key=lambda d: -d["mm3"])
    return {"void_components": int((sizes[1:] * step ** 3 >= POCKET_MIN_MM3).sum()), "pockets": pockets, "slivers": slivers,
            "open_voxels": int(outer.sum())}


def built_voids(mesh, spec: GyroidSpec, step: float = VOID_STEP_MM, max_columns: int | None = None) -> dict:
    """The built mesh voxelised inside the zone by scanline rays along the ring axis (parity of the hits), then the
    flood fill from the outer face (`_void_components`). Pockets of void that reach no opening are where the resin
    and the investment would be trapped."""
    b = spec.band
    R = b.outer_radius_mm + step
    zh = spec.zone_half_width
    xs = np.arange(-R, R + step / 2, step)
    zs = np.arange(-zh + step / 2, zh, step)
    X, Y = np.meshgrid(xs, xs, indexing="ij")
    r_xy = np.hypot(X, Y)
    cols = np.argwhere((r_xy >= spec.zone_inner_radius - step) & (r_xy <= b.outer_radius_mm + step))
    if max_columns is not None and len(cols) > max_columns:
        return {"incomplete": f"{len(cols)} columns to cast at {step} mm, more than the {max_columns} the ray backend can take"}
    rng = np.random.default_rng(3)
    jitter = rng.uniform(-0.3, 0.3, (len(cols), 2)) * step          # off the grid lines: no ray through a vertex or an edge
    origins = np.column_stack([xs[cols[:, 0]] + jitter[:, 0], xs[cols[:, 1]] + jitter[:, 1], np.full(len(cols), -zh - 1.0)])
    dirs = np.tile([0.0, 0.0, 1.0], (len(cols), 1))
    inside = np.zeros((len(xs), len(xs), len(zs)), dtype=bool)
    try:
        locs, ray_idx, _ = mesh.ray.intersects_location(origins, dirs, multiple_hits=True)
    except BaseException as e:                                     # a ray backend hiccup must not kill the gate
        return {"incomplete": f"ray casting failed ({e})"}
    if len(ray_idx) == 0:
        return {"incomplete": "no ray hit the part"}
    order = np.lexsort((locs[:, 2], ray_idx))
    locs, ray_idx = locs[order], ray_idx[order]
    bounds = np.flatnonzero(np.diff(ray_idx)) + 1
    starts = np.concatenate([[0], bounds])
    ends = np.concatenate([bounds, [len(ray_idx)]])
    for s, e in zip(starts, ends):
        z = locs[s:e, 2]
        z = z[np.concatenate([[True], np.diff(z) > 1e-6])]        # a hit on a shared edge comes twice
        if len(z) % 2:
            z = z[:-1]
        if len(z) == 0:
            continue
        ix, iy = cols[ray_idx[s]]
        col = np.zeros(len(zs), dtype=bool)
        for z0, z1 in zip(z[0::2], z[1::2]):
            col |= (zs >= z0) & (zs <= z1)
        inside[ix, iy] = col
    zone_band = np.zeros_like(inside)
    for k, zk in enumerate(zs):
        zone_band[:, :, k] = spec.in_zone_band(r_xy, np.full(X.shape, zk))
    out = _void_components(~inside & zone_band, r_xy, zs, spec, step)
    dome_layer = np.zeros_like(zone_band)                           # the zone's voxels under the dome: open where void
    for k, zk in enumerate(zs):
        dome_layer[:, :, k] = zone_band[:, :, k] & (r_xy >= float(spec.outer_radius_at(zk)) - 1.5 * step)
    out["open_share"] = float((dome_layer & ~inside).sum() / max(1, dome_layer.sum()))
    out["zone_metal_share"] = float((inside & zone_band).sum() / max(1, zone_band.sum()))
    out["step_mm"] = step
    return out


_VARIANT_SHIFTS = [(sx, sy, sz) for sx in (0.0, 0.25, 0.5, 0.75) for sy in (0.0, 0.25, 0.5, 0.75) for sz in (0.0, 0.25, 0.5, 0.75)]


def lattice_match(mesh, spec: GyroidSpec, points: int = MATCH_POINTS, seed: int = 11) -> dict:
    """The built mesh against the model, point by point: random points inside the zone, away from any designed
    surface (half a voxel and 0.02 mm), the built mesh's inside / outside (trimesh.contains) against the model's.
    When the configured convention does not fit, the mirrored and shifted gyroids are tried and the best named."""
    b = spec.band
    rng = np.random.default_rng(seed)
    zh, r_in = spec.zone_half_width, spec.zone_inner_radius
    R = float(spec.outer_radius_at(0.0))
    n = points * 3
    r = np.sqrt(rng.uniform(r_in ** 2, R ** 2, n))
    th = rng.uniform(0, 2 * math.pi, n)
    z = rng.uniform(-zh, zh, n)
    X, Y = r * np.cos(th), r * np.sin(th)
    keep = spec.in_zone_band(r, z, margin=0.05)
    clear = b.mesh_tolerance_mm / 2 + 0.02
    d = spec.lattice_sdf(X, Y, z)
    keep &= np.abs(d) > clear
    X, Y, z, d = X[keep][:points], Y[keep][:points], z[keep][:points], d[keep][:points]
    if len(X) < 100:
        return {"incomplete": "too few points clear of the designed surfaces"}
    try:
        built = np.asarray(mesh.contains(np.column_stack([X, Y, z])), dtype=bool)
    except BaseException as e:
        return {"incomplete": f"containment failed ({e})"}
    designed = d <= 0
    agree = float((built == designed).mean())
    out = {"points": int(len(X)), "agreement": agree, "built_metal_share": float(built.mean()),
           "designed_metal_share": float(designed.mean())}
    if agree < MATCH_MIN:
        best = None
        for variant in ("standard", "mirrored"):
            for sh in _VARIANT_SHIFTS:
                shift = tuple(s * spec.cell_mm for s in sh)
                dd = seeded_sheet_sdf(X, Y, z, spec.cell_mm, spec.seed_design_mm, spec.growth_mm, spec.wrap_length, spec.outer_radius_at,
                                      variant, shift)
                a = float((built == (dd <= 0)).mean())
                if best is None or a > best[0]:
                    best = (a, variant, sh)
        out["best_variant"] = {"agreement": best[0], "variant": best[1], "shift_cells": list(best[2])}
    return out


def _zone_face_filter(spec: GyroidSpec, margin: float | None = None):
    """Keep sample points on the sheets: inside the zone, off the skin's top, the dome and the rims' faces (by the spec's
    end margin)."""
    margin = spec.end_margin if margin is None else margin

    def f(points, normals):
        r = np.hypot(points[:, 0], points[:, 1])
        return spec.in_zone_band(r, points[:, 2], margin=margin)
    return f


def _band_wall_filter(spec: GyroidSpec, margin: float | None = None):
    """The generic wall check's rays (radial and axial, not along the normal): everywhere but within the lip margin of the
    dome inside the zone, where a chord through a lip's round reads short (the lattice's own checks measure there)."""
    margin = spec.lip_margin if margin is None else margin

    def f(points, normals):
        r = np.hypot(points[:, 0], points[:, 1])
        z = points[:, 2]
        ends = spec.in_zone_band(r, z, margin=0.0) & (r > spec.outer_radius_at(z) - margin)
        return ~ends
    return f


def sheet_rays(mesh, spec: GyroidSpec, samples: int = RAY_SAMPLES, seed: int = 7, min_exit_cos: float = 0.3) -> dict:
    """From points on the sheets (inside the zone, off the skin's top and the rims, up to and on the outer face): inward
    along the normal to the sheet's other face (its thickness) and outward to the next surface (the void's width across).
    A thickness ray that starts within the end margin of the outer face or leaves through it crossed a sheet's END - its
    round, or a LIP where a sheet runs under the dome and is cut by it - and is reported apart (`lips`, held to twice the
    growth: the opening's inscribed ball), from four times the samples (the ends are a few percent of the sheets). A ray
    leaving through a face it barely crosses is counted, not measured."""
    import trimesh
    fast = gate.ray_backend(mesh) == "embree"
    if not fast:
        samples = min(samples, 300 if len(mesh.faces) > 200_000 else 800)
    rng = np.random.default_rng(seed)
    pts, fidx = trimesh.sample.sample_surface(mesh, samples * 16, seed=rng)
    normals = mesh.face_normals[fidx]
    lip_tol = spec.band.mesh_tolerance_mm / 2 + 0.02
    r0, z0 = np.hypot(pts[:, 0], pts[:, 1]), pts[:, 2]
    m = spec.end_margin
    keep = (np.abs(z0) <= spec.zone_half_width - m) & (r0 >= spec.zone_inner_radius + m) & (r0 <= spec.outer_radius_at(z0) + lip_tol)
    pts, normals = pts[keep][:samples * 4], normals[keep][:samples * 4]
    if len(pts) == 0:
        return {}
    at_end = np.hypot(pts[:, 0], pts[:, 1]) > spec.outer_radius_at(pts[:, 2]) - m
    eps = 1e-4
    out = {"samples": int(min(int((~at_end).sum()), samples))}
    for key, sign in (("thickness", -1.0), ("gap", 1.0)):
        if key == "thickness":
            p_use, n_use, end_use = pts, normals, at_end
        else:
            p_use, n_use = pts[~at_end][:samples], normals[~at_end][:samples]
            end_use = np.zeros(len(p_use), dtype=bool)
        origins = p_use + n_use * eps * sign
        dirs = n_use * sign
        dists, hits, ends, grazing = [], [], [], 0
        batch = len(p_use) if fast else 50
        try:
            for s in range(0, len(p_use), batch):
                locs, ray_idx, tri = mesh.ray.intersects_location(origins[s:s + batch], dirs[s:s + batch], multiple_hits=False)
                if len(ray_idx):
                    dd = np.linalg.norm(locs - origins[s:s + batch][ray_idx], axis=1)
                    exit_cos = np.abs(np.einsum("ij,ij->i", dirs[s:s + batch][ray_idx], mesh.face_normals[tri]))
                    ok = exit_cos >= min_exit_cos
                    grazing += int((~ok).sum())
                    dists.append(dd[ok])
                    hits.append(locs[ok])
                    ends.append(end_use[s:s + batch][ray_idx][ok])
        except BaseException:
            return out
        if not dists:
            continue
        d = np.concatenate(dists)
        hit = np.concatenate(hits)
        started_at_end = np.concatenate(ends)
        ok = d > 10 * eps
        hr = np.hypot(hit[:, 0], hit[:, 1])
        if key == "gap":                                            # across a void to the next SHEET: a hit on the skin's top or a
            ok &= spec.in_zone_band(hr, hit[:, 2], margin=0.05)     # rim's face is the wedge where a sheet leans on them, a ray out
            ok &= hr < spec.outer_radius_at(hit[:, 2]) - spec.end_margin   # through an opening is the ring's far side - neither
            ok &= d < 2 * spec.cell_mm                              # a pore
            groups = {"gap": ok}
        else:
            lip = started_at_end | (hr >= spec.outer_radius_at(hit[:, 2]) - lip_tol)   # an end's round, or out through the dome
            groups = {"thickness": ok & ~lip, "lips": ok & lip}
        for name, sel in groups.items():
            q = d[sel]
            if q.size == 0:
                continue
            out[name] = {"p01": float(np.percentile(q, 1)), "p05": float(np.percentile(q, 5)), "median": float(np.median(q)),
                         "min": float(q.min()), "samples": int(q.size), "grazing": grazing}
    return out


_CELL_RAYS: dict = {}


def unit_cell_rays(cell: float, wall: float, edge: float = 0.05) -> dict:
    """The sheet_rays statistics of the unit cell itself: three cells of the walled gyroid as a level set, rays from
    the middle cell's sheet faces. What a built lattice's pore statistic is held to (the wrap stretches cells ±8 %).
    Cached."""
    key = (round(cell, 6), round(wall, 6), edge)
    if key in _CELL_RAYS:
        return _CELL_RAYS[key]
    import manifold3d as m3
    import trimesh
    k = 2 * math.pi / cell
    half = wall / 2

    def sdf(x, y, z):
        return -_sheet_sdf_scalar(x, y, z, k, half)

    lo, hi = -cell / 2, 1.5 * cell                              # two cells each way: rays from the middle cell stay inside
    man = m3.Manifold.level_set(sdf, (lo, lo, lo, hi, hi, hi), max(edge, cell / 35), 0.0)
    mesh = _manifold_to_trimesh(man)
    rng = np.random.default_rng(5)
    pts, fidx = trimesh.sample.sample_surface(mesh, 20000, seed=rng)
    normals = mesh.face_normals[fidx]
    mid = np.all((pts > 0.0) & (pts < cell), axis=1)
    pts, normals = pts[mid][:4000], normals[mid][:4000]
    out = {}
    for key, sign in (("thickness", -1.0), ("gap", 1.0)):
        locs, ray_idx, tri = mesh.ray.intersects_location(pts + normals * 1e-4 * sign, normals * sign, multiple_hits=False)
        d = np.linalg.norm(locs - (pts + normals * 1e-4 * sign)[ray_idx], axis=1)
        d = d[d > 1e-3]
        out[key] = {"p01": float(np.percentile(d, 1)), "p05": float(np.percentile(d, 5)), "median": float(np.median(d))}
    _CELL_RAYS[key] = out
    return out


def check_lattice(spec: GyroidSpec, stl: Path, ntop_vol: float | None) -> gate.GateReport:
    """The band gate, then the lattice's own checks (module docstring)."""
    b = spec.band
    tol = float(b.mesh_tolerance_mm)
    rep = gate.check(stl, expect_inner=b.inner_diameter_mm, expect_outer=2 * b.outer_radius_mm, expect_width=b.width_mm,
                     expect_volume=ntop_vol, wall_floor=spec.wall_floor(), centre="origin", tol_mm=0.05,
                     wall_ray_filter=_band_wall_filter(spec))
    mesh = gate.load_mesh(stl)
    pad = tol / 2 + fieldtex.ENVELOPE_PAD_MM
    m = measure_texture(spec, mesh)
    rep.texture = m
    fl = tables.FLOORS
    c = rep.checks
    if "zone_highest_mm" in m:
        c.append(gate.Check("lattice envelope", m["zone_highest_mm"] <= pad,
                            f"inside the zone nothing stands further than {m['zone_highest_mm']:+.3f} mm outside the designed band "
                            f"(allowed {pad:.3f})"))
    else:
        c.append(gate.incomplete("lattice envelope", "no vertex inside the zone"))
    if "outside_worst_mm" in m:
        c.append(gate.Check("untouched outside the zone", m["outside_worst_mm"] <= pad,
                            f"the bore, the sides and the rims lie within {m['outside_worst_mm']:.3f} mm of the design "
                            f"(allowed {pad:.3f}): the mask {'held' if m['outside_worst_mm'] <= pad else 'did not hold'}"))
    # the lattice against the model, point by point
    match = lattice_match(mesh, spec)
    m["match"] = match
    if "incomplete" in match:
        c.append(gate.incomplete("lattice match", match["incomplete"]))
    else:
        detail = (f"the built mesh agrees with the designed gyroid at {match['agreement']:.1%} of {match['points']} points inside the "
                  f"zone (metal {match['built_metal_share']:.1%} built, {match['designed_metal_share']:.1%} designed; at least {MATCH_MIN:.0%})")
        if "best_variant" in match:
            bv = match["best_variant"]
            detail += (f"; the best fit is the {bv['variant']} gyroid shifted {bv['shift_cells']} cells at {bv['agreement']:.1%} - "
                       f"nTop's convention, to record in api_facts (GYROID_VARIANT)")
        c.append(gate.Check("lattice match", match["agreement"] >= MATCH_MIN, detail))
    # the sheets and the voids by rays
    rays = sheet_rays(mesh, spec)
    m["rays"] = rays
    cellr = unit_cell_rays(spec.cell_mm, spec.wall_mm)
    m["unit_cell"] = {**spec.cell(), "rays": cellr}
    th = rays.get("thickness")
    if th and th["samples"] >= gate.MIN_WALL_SAMPLES:
        floor = fl["lattice_member"]
        c.append(gate.Check("sheet thickness", th["p01"] >= min(floor, spec.wall_mm) - pad,
                            f"p1 {th['p01']:.3f} mm, median {th['median']:.3f} against the {spec.wall_mm:g} mm wall asked (floor "
                            f"{floor:g}; allowed {min(floor, spec.wall_mm) - pad:.3f}); {th['samples']} rays off the lips, "
                            f"{th['grazing']} off feather edges"))
    elif th:
        c.append(gate.incomplete("sheet thickness", f"only {th['samples']} usable rays (need {gate.MIN_WALL_SAMPLES})"))
    else:
        c.append(gate.incomplete("sheet thickness", "no ray through a sheet came back"))
    lips = rays.get("lips")
    lip_floor = 2 * spec.growth_mm
    if lips:
        n = lips["samples"]
        stat, what = (lips["p01"], "p1") if n >= LIP_MIN_SAMPLES else (lips["min"], "min")
        share = n / max(1, n + (th["samples"] if th else 0))
        c.append(gate.Check("lips at the outer face", stat >= lip_floor - pad,
                            f"the sheets' ends at the outer face - their rounds, and the lips where a sheet runs under it and is cut by it "
                            f"({n} rays, {share:.1%} of those through the sheets): {what} {stat:.3f} mm, median {lips['median']:.3f}; the "
                            f"seed's inset and growth keep every end at least 2 x {spec.growth_mm:g} = {lip_floor:g} thick, the marginal "
                            f"wall (allowed {lip_floor - pad:.3f})"))
    elif th:
        c.append(gate.Check("lips at the outer face", True, "no ray through a sheet left by the outer face: no sheet runs under it"))
    gp = rays.get("gap")
    if gp and gp["samples"] >= gate.MIN_WALL_SAMPLES:
        want = PORE_SHARE * cellr["gap"]["p05"]
        c.append(gate.Check("pore width", gp["p05"] >= want - pad,
                            f"across the voids p5 {gp['p05']:.3f} mm, median {gp['median']:.3f} (the unit cell's own p5 {cellr['gap']['p05']:.3f}, "
                            f"median {cellr['gap']['median']:.3f}; allowed {want - pad:.3f}); the pore {spec.cell()['pore_mm']:.2f} mm against the "
                            f"{fl['lattice_pore']:g} floor"))
    elif gp:
        c.append(gate.incomplete("pore width", f"only {gp['samples']} usable rays (need {gate.MIN_WALL_SAMPLES})"))
    else:
        c.append(gate.incomplete("pore width", "no ray across a void came back"))
    # the trapped-resin check: every void reaches the outer face
    fast = gate.ray_backend(mesh) == "embree"
    voids = built_voids(mesh, spec, max_columns=None if fast else 1500)
    m["voids"] = voids
    if "incomplete" in voids:
        c.append(gate.incomplete("open voids", voids["incomplete"]))
    else:
        pk = voids["pockets"]
        sl = voids.get("slivers", 0)
        sliver_note = (f"; {sl} sliver{'s' if sl != 1 else ''} under {POCKET_MIN_MM3:g} mm³ where a sheet leans on the skin, at the grid's "
                       f"own size, not counted") if sl else ""
        if pk:
            w = pk[0]
            c.append(gate.Check("open voids", False,
                                f"{len(pk)} pocket{'s' if len(pk) > 1 else ''} of void never reach the outer face (the largest "
                                f"{w['mm3']:.3f} mm³ at {w['theta_deg']:.0f}°, z {w['z']:+.2f}, r {w['r']:.2f}): resin and investment trapped"
                                + sliver_note))
        else:
            c.append(gate.Check("open voids", True,
                                f"every void reaches the outer face ({voids['void_components']} channel{'s' if voids['void_components'] != 1 else ''}; "
                                f"{voids['open_share']:.0%} of the face open; metal {voids['zone_metal_share']:.0%} of the zone; "
                                f"{voids['step_mm']:g} mm voxels)" + sliver_note))
    design = spec.design_volume_mm3()
    if ntop_vol is None:
        c.append(gate.incomplete("design volume", "nTop reported no volume; the notebook cannot be checked against the design"))
    else:
        pct = 100.0 * (ntop_vol - design) / design
        c.append(gate.Check("design volume", abs(pct) <= VOLUME_TOL_PCT,
                            f"nTop {ntop_vol:.2f} mm³ vs the model's {design:.2f} ({pct:+.2f}%; ±{VOLUME_TOL_PCT:g}%): the solid band "
                            f"{spec.plain_volume_mm3():.2f}, the zone {spec.zone_band_volume_mm3():.2f} of which the sheet keeps "
                            f"{spec.sheet_volume_mm3():.2f}"))
    return rep


def build(spec: GyroidSpec, out_dir: Path | None = None, *, notebook: Path | None = None, catalog_name: str | None = None,
          deliver: bool = False, deliver_project: str = "Bands", cast_metal: str | None = None) -> fieldtex.FieldTextureResult:
    """Run ring_lattice.ntop through nTopCL and gate the lattice band (check_lattice)."""
    return fieldtex.build(spec, out_dir, notebook=notebook, catalog_name=catalog_name, deliver=deliver, deliver_project=deliver_project,
                          cast_metal=cast_metal, check=check_lattice, family="lattice")
