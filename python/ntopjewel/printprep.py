"""Print preparation: a gated part made into the file the printer gets - oriented, supported on plain metal only,
standing on a raft (2026-11-07, after the first test prints: the slicer's supports swelled where they met the part,
and no orientation found by hand kept them off the features).

    surface model  every face of the part classed from the DESIGN, not from the mesh: a POLISHED face (on the plain
                   band's or shank's section - the dome, the side faces), the BORE (on it, facing the axis), a FEATURE
                   (off the section - beads, engraving, prongs, seat, arches, knots, relief, a slot's walls - or in a
                   zone the family names: a texture, the lattice, panels, pavé, the text), or CLEAR (the bore with
                   `--bore avoid`: plain metal no support may touch, e.g. a calibration ring's bore that the mandrel
                   reads). Contacts go on polished faces and the bore only, none nearer a feature than
                   support_keepoff_mm.
    search         build directions all over the sphere, scored first from the faces' normals (overhang area by
                   class, height), the best few then sliced (raster.Columns, exact in height): every down-facing
                   point flatter than print_overhang_deg (no solid within that angle below it), every island (a
                   layer's piece touching nothing printed before it), every suction cup (resin walled in by the
                   layer and sealed below), the largest layer and the height. THE PART MUST START ON ITS SUPPORTS:
                   until its first contact nothing but the film holds it, so a first contact later than
                   print_start_gap_mm (two layers) above its lowest point is fatal and outweighs everything - the
                   feature leading it cures onto the film, the part grows from it there, and every later layer
                   stays with the film while the supports print alone (the court band's first US 4.5 print,
                   8 Nov 2026: leaning 53°, its bottom bead row led its first contact by 12 layers; "the ring
                   itself stuck to the film, not the supports"). Then a feature island and a feature overhang
                   that no contact covers cost the most, then the contacts (the bore's a little more), then
                   suction, peel and height.
    supports       at the best direction: a contact on every island (its lowest supportable point) and along every
                   supportable overhang at support_spacing_mm, lowest first, then more under any layer that would
                   hang on fewer than one contact per support_hold_area_mm2 of its area (hold_layers: the lowest
                   layers of a ring standing on edge); each a breakaway tip - support_tip_mm
                   across at the surface, reaching support_contact_depth_mm in -, a cone to the column, the column
                   straight down to the raft or, where the part lies below, standing on it with a tip at that end too
                   (on a polished face or the bore only); every column kept support_clearance_mm off the part. The
                   raft is the bases' hull, its top edge chamfered.
    the file       part ∪ supports ∪ raft as one manifold (manifold3d), the raft's underside on z = 0:
                   `<stem>.supported.stl` (`<stem>.supported_<metal>.stl` scaled by tables.print_scale when the
                   part will be cast) - slice it as it is, adding nothing; `<stem>.prep.json` (every candidate,
                   every support, what is left unsupported and where, in the ring's own angles) and
                   `<stem>.prep.png` (the supported part, front and three-quarter, and the runners-up).

Ring frame as everywhere: axis Z, the head (a ring's top) at +X, θ from +X. Printer frame: Z up from the plate.
Every number comes from the tables' settings (print_*, support_*, raft_*); the weights of the score are this
module's.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import gate, raster, tables

POLISH, BORE, FEATURE, CLEAR = 0, 1, 2, 3
CLASS_NAMES = ("polished face", "bore", "feature", "kept clear")
SUPPORTABLE = np.array([True, True, False, False])
SETTING_KEYS = ("print_layer_mm", "print_overhang_deg", "print_start_gap_mm", "print_cure_through_mm", "support_tip_mm",
                "support_contact_depth_mm", "support_tip_length_mm", "support_column_mm", "support_spacing_mm",
                "support_min_spacing_mm", "support_hold_area_mm2", "support_lift_mm", "support_clearance_mm", "support_keepoff_mm",
                "raft_thickness_mm", "raft_margin_mm")

# ---- the surface model
SECTION_STEP_DEG = 2.0           # a shaped shank's plain section sampled this often round the ring (interpolated between)
BOUNDARY_STEP_MM = 0.01          # each section's outline as points this close
ON_SURFACE_MARGIN_MM = 0.03      # a face on the plain section: within its shape tolerance and this of the outline
RECESS_MM = 0.05                 # an outline this far inside the section's hull is a slot's or a gap's wall: a feature
LOOKUP_STEP_DEG = 0.25           # per-angle zone tests (panels, knots, pavé) tabulated this finely
KEEP_GRID_MM = 0.05              # feature points thinned to this grid for the keep-off distance

# ---- the search
SEARCH_DIRECTIONS = 600          # build directions scored from the normals (about 8° apart)
NORMAL_BINS = 2000               # the faces' normals binned on the sphere for that
CANDIDATES = 10                  # ... the best this many, at least CANDIDATE_SEPARATION_DEG apart, are sliced
CANDIDATE_SEPARATION_DEG = 15.0
FINALISTS = 3                    # ... and the best this many sliced again at the printer's layer, the best of them chosen
SEARCH_PIXEL_MM = 0.1            # their slicing: columns this far apart, layers this thick
FINAL_PIXEL_MM = 0.05            # the chosen direction's, at the printer's layer
W_START = 10000.0                # the score, lower better: per layer the part prints on the film alone before its first
                                 # contact, beyond print_start_gap_mm - it starts on the film and is lost (8 Nov), so one
                                 # layer of that outweighs every other term
W_FEATURE_ISLAND = 30.0          # ... a feature island (it fails or prints deformed)
W_FEATURE_AREA = 40.0            # ... per mm² of feature overhang no contact covers
W_CONTACT = 1.0                  # ... per contact on a polished face
W_BORE_CONTACT = 1.5             # ... per contact in the bore (a strut inside the ring, the bore to clean)
W_CUP = 4.0                      # ... per mm² of the largest suction cup
W_PEEL = 0.03                    # ... per mm² of the largest layer
W_HEIGHT = 0.05                  # ... per mm of height
COVER = 0.75                     # a contact holds the overhang - a feature's beside it too - within this fraction of the
                                 # spacing: the density chosen is the sag accepted, on plain metal and features alike

# ---- the supports
STRUT_EXTRA_MM = 0.4             # a support standing on the part is at least two tips and this long
SLENDERNESS = 15.0               # a column is at least a fifteenth of its length across ...
COLUMN_MAX_MM = 1.6              # ... and at most this
SEGMENTS = 16                    # round each support
BASE_FLARE = 0.9                 # a column's foot on the raft is this x its diameter in radius
NEIGHBOURS = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))


def prep_settings(**overrides) -> dict:
    """The print preparation's numbers from the tables (data/jewelry_tables.json settings), any given overriding."""
    s = {k: float(tables.SETTINGS[k]) for k in SETTING_KEYS}
    s.update({k: float(v) for k, v in overrides.items() if v is not None})
    return s


# ============================================================================ the surface model
@dataclass
class SurfaceModel:
    """Which faces of a part are plain metal: the plain body's section at each angle (shapely, (r, z), the ring frame)
    and the zones on it that are features all the same. `top_deg`: where the ring's head is (None: a band)."""
    label: str
    section: object
    axisymmetric: bool
    tolerance_mm: float
    zones: list = field(default_factory=list)          # (name, f(r, θ°, z, n_r) -> bool)
    top_deg: float | None = None
    zone_counts: dict = field(default_factory=dict)

    def _tables(self):
        if getattr(self, "_tab", None) is None:
            import shapely
            from scipy.spatial import cKDTree
            thetas = [0.0] if self.axisymmetric else list(np.arange(0.0, 360.0, SECTION_STEP_DEG))
            trees, hulls = [], []
            for t in thetas:
                g = self.section(float(t))
                if g is None or g.is_empty:
                    trees.append(None)
                    hulls.append(None)
                    continue
                trees.append(cKDTree(shapely.get_coordinates(shapely.segmentize(g.boundary, BOUNDARY_STEP_MM))))
                hull = g.convex_hull
                if hull.area - g.area > 1e-4 * max(hull.area, 1.0):
                    hulls.append(cKDTree(shapely.get_coordinates(shapely.segmentize(hull.boundary, BOUNDARY_STEP_MM))))
                else:
                    hulls.append(None)
            self._tab = (np.array(thetas), trees, hulls)
        return self._tab

    def distance(self, r, th, z):
        """(distance to the plain section's outline, recess) per point: inf where there is no plain section."""
        thetas, trees, hulls = self._tables()
        q = np.column_stack([r, z])
        if self.axisymmetric:
            if trees[0] is None:
                return np.full(len(r), np.inf), np.zeros(len(r), bool)
            d = trees[0].query(q)[0]
            rec = hulls[0].query(q)[0] > RECESS_MM if hulls[0] is not None else np.zeros(len(r), bool)
            return d, rec
        n = len(thetas)
        f = (np.asarray(th) % 360.0) / SECTION_STEP_DEG
        i0 = np.floor(f).astype(int) % n
        i1 = (i0 + 1) % n
        w = f - np.floor(f)
        d0, d1 = np.full(len(r), np.inf), np.full(len(r), np.inf)
        rec = np.zeros(len(r), bool)
        for i in range(n):
            if trees[i] is None:
                continue
            for sel, dd in ((i0 == i, d0), (i1 == i, d1)):
                if sel.any():
                    dd[sel] = trees[i].query(q[sel])[0]
                    if hulls[i] is not None:
                        rec[sel] |= hulls[i].query(q[sel])[0] > RECESS_MM
        both = np.isfinite(d0) & np.isfinite(d1)
        return np.where(both, (1.0 - w) * np.where(both, d0, 0.0) + w * np.where(both, d1, 0.0), np.inf), rec

    def classify(self, mesh, bore: str = "allow", keepoff_mm: float | None = None) -> np.ndarray:
        """Every face's class (POLISH / BORE / FEATURE / CLEAR) from its centre and normal."""
        from scipy.spatial import cKDTree
        c = np.asarray(mesh.triangles_center)
        n = np.asarray(mesh.face_normals)
        r = np.hypot(c[:, 0], c[:, 1])
        th = np.degrees(np.arctan2(c[:, 1], c[:, 0])) % 360.0
        z = c[:, 2]
        nr = (n[:, 0] * c[:, 0] + n[:, 1] * c[:, 1]) / np.maximum(r, 1e-9)
        d, recess = self.distance(r, th, z)
        on = (d <= self.tolerance_mm + ON_SURFACE_MARGIN_MM) & ~recess
        cls = np.full(len(c), FEATURE, np.int8)
        cls[on] = np.where(nr[on] < -0.5, BORE, POLISH)
        self.zone_counts = {}
        for name, f in self.zones:
            hit = np.asarray(f(r, th, z, nr), bool) & (cls != FEATURE)
            cls[hit] = FEATURE
            self.zone_counts[name] = int(hit.sum())
        keepoff = float(tables.SETTINGS["support_keepoff_mm"] if keepoff_mm is None else keepoff_mm)
        feat = cls == FEATURE
        if keepoff > 0 and feat.any() and (~feat).any():
            pts = np.unique(np.round(c[feat] / KEEP_GRID_MM).astype(np.int64), axis=0) * KEEP_GRID_MM
            cand = np.flatnonzero(~feat)
            dist = cKDTree(pts).query(c[cand], distance_upper_bound=keepoff + KEEP_GRID_MM)[0]
            cls[cand[dist <= keepoff]] = FEATURE
        if bore == "avoid":
            cls[cls == BORE] = CLEAR
        return cls


def _angle_lookup(fn):
    grid = np.arange(0.0, 360.0, LOOKUP_STEP_DEG)
    vals = np.array([bool(fn(float(t) if t <= 180.0 else float(t) - 360.0)) for t in grid])

    def f(th):
        return vals[np.round((np.asarray(th) % 360.0) / LOOKUP_STEP_DEG).astype(int) % len(vals)]
    return f


def angle_zone(name: str, fn):
    """A feature over every face but the bore at the angles where fn(θ°, -180..180) says so (panels, knots, pavé)."""
    look = _angle_lookup(fn)
    return name, lambda r, th, z, nr: look(th) & (nr > -0.5)


def engraving_zone(eng, centre_deg: float, side: str):
    """The text's face (the bore inside, the outer face outside) over its height and angular span, centred on
    centre_deg (features.RingSpec._text_span: half-height mm, half-span rad, centred on +X)."""
    half_h, half_a = eng._text_span()
    span = math.degrees(half_a) + 1.0

    def f(r, th, z, nr):
        d = np.abs((np.asarray(th) - centre_deg + 180.0) % 360.0 - 180.0)
        face = nr < -0.3 if side == "inside" else nr > 0.3
        return (np.abs(z) <= half_h + 0.1) & (d <= span) & face
    return "engraving", f


def outer_face_zone(name: str, r_mid: float, half_width: float | None = None):
    """The outer face (facing outward, outside the band's mid-radius), within ±half_width of the mid-plane if given."""
    def f(r, th, z, nr):
        m = (nr > 0.3) & (r > r_mid)
        return m & (np.abs(z) <= half_width) if half_width is not None else m
    return name, f


def _mid_radius(b) -> float:
    return (b.inner_diameter_mm / 2.0 + b.outer_radius_mm) / 2.0


def _band_model(b, label: str = "band", zones=(), top_deg=None) -> SurfaceModel:
    from . import band as bandmod
    sec = b.design_section()
    return SurfaceModel(label, lambda t: sec, True, bandmod.section_shape_tolerance(b.mesh_tolerance_mm), list(zones), top_deg)


def _shank_model(sh, label: str = "shank", zones=(), top_deg=0.0) -> SurfaceModel:
    from . import band as bandmod
    tol = bandmod.section_shape_tolerance(sh.band.mesh_tolerance_mm)
    zones = list(zones)
    if getattr(sh, "hammer", None):
        zones.append(outer_face_zone("hammered face", _mid_radius(sh.band)))
    shaped = (sh.tapered or bool(sh.dip_mm) or sh.strands > 1 or bool(sh.split_mm) or bool(sh.rope) or bool(sh.knot))
    if not shaped:
        sec = sh.band.design_section()
        return SurfaceModel(label, lambda t: sec, True, tol, zones, top_deg)
    if sh.knot:
        tol = max(tol, sh.band.mesh_tolerance_mm)                # a knot's step creases: the whole tolerance (the gate's rule)
    cache = {}

    def section(t):
        if t not in cache:
            cache[t] = sh.section_shape(t, skip=False, chamfer_mm=sh.opening_chamfer_mm)
        return cache[t]
    return SurfaceModel(label, section, False, tol, zones, top_deg)


def surface_model(spec) -> SurfaceModel:
    """The surface model of any ring family's spec: its plain body and its feature zones."""
    name = type(spec).__name__
    if name == "BandSpec":
        return _band_model(spec)
    if name == "RingSpec":
        zones = [engraving_zone(spec, 0.0, spec.engrave_side)] if spec.has_engraving else []
        return _band_model(spec.band, "ring", zones)
    if name == "ShankSpec":
        shaped = spec.tapered or spec.dip_mm or spec.strands > 1 or spec.split_mm or spec.rope or spec.knot
        return _shank_model(spec, top_deg=0.0 if shaped else None)
    if name == "HammeredSpec":
        return _band_model(spec.band, "hammered band", [outer_face_zone("hammered face", _mid_radius(spec.band), spec.edge_reach + 0.05)])
    from . import fieldtex
    if isinstance(spec, fieldtex.FieldTextureSpec):
        label = "lattice band" if name == "GyroidSpec" else f"{spec.kind} band"
        return _band_model(spec.band, label, [(label.split()[0] + " zone", lambda r, th, z, nr: spec.in_zone(r, z, pad=0.05))])
    if name == "SolitaireSpec":
        zones = []
        if spec.has_engraving:
            zones.append(engraving_zone(spec.engraving, 180.0, spec.engrave_side))
        if spec.artwork is not None:
            zones.append(angle_zone("artwork panels", spec.artwork.in_panel))
        if spec.has_knot:
            zones.append(angle_zone("shoulder knots", spec.ornament.in_span))
        return _shank_model(spec.shank_spec, "solitaire", zones, 0.0)
    if name == "MultiStoneSpec":
        zones = []
        if spec.pave is not None:
            zones.append(angle_zone("pavé", spec.pave.in_pave))
        if spec.text:
            zones.append(engraving_zone(spec.engraving, 180.0, spec.engrave_side))
        return _shank_model(spec.shank_spec, "multi-stone ring", zones, 0.0)
    if name == "PaveSpec":
        return _shank_model(spec.shank, "pavé band", [angle_zone("pavé", spec.in_pave)], float(spec.centre_deg))
    if name == "ArtworkSpec":
        return _shank_model(spec.shank, "artwork band", [angle_zone("artwork panels", spec.in_panel)], 0.0)
    raise ValueError(f"no print preparation for a {name}")


# ============================================================================ orientation
def frame(b) -> np.ndarray:
    """The rotation (rows: printer X, Y, Z in ring coordinates) that turns the build direction b (ring frame) up;
    the ring axis lies along printer X unless it is the build direction."""
    b = np.asarray(b, float)
    b = b / np.linalg.norm(b)
    x = np.array([0.0, 0.0, 1.0]) - b * b[2]
    if np.linalg.norm(x) < 1e-6:
        x = np.array([1.0, 0.0, 0.0]) - b * b[0]
    x /= np.linalg.norm(x)
    return np.vstack([x, np.cross(b, x), b])


def _head(top_deg: float) -> np.ndarray:
    a = math.radians(top_deg)
    return np.array([math.cos(a), math.sin(a), 0.0])


def tilt_and_head(b, top_deg: float | None):
    """(the ring axis's angle to the plate - 0 standing on edge, 90 lying flat -, the head's angle above level or None)."""
    b = np.asarray(b, float) / np.linalg.norm(b)
    tilt = math.degrees(math.asin(min(1.0, abs(float(b[2])))))
    if top_deg is None:
        return tilt, None
    return tilt, math.degrees(math.asin(float(np.clip(b @ _head(top_deg), -1.0, 1.0))))


def describe(b, top_deg: float | None) -> str:
    tilt, head = tilt_and_head(b, top_deg)
    s = f"axis {tilt:.0f}° to the plate"
    if tilt < 3:
        s = "standing on edge (axis level)"
    elif tilt > 87:
        s = "lying flat (axis upright)"
    if head is None:
        return s
    if abs(head) < 3:
        return s + ", head level"
    return s + f", head {abs(head):.0f}° {'up' if head > 0 else 'down'}"


def direction_for(tilt_deg: float, head_deg: float, top_deg: float | None) -> np.ndarray:
    """The build direction with the ring axis at tilt_deg to the plate and the head head_deg above level."""
    st, sh = math.sin(math.radians(tilt_deg)), math.sin(math.radians(head_deg))
    rest = 1.0 - st * st - sh * sh
    if rest < -1e-9:
        raise ValueError(f"no orientation has the axis {tilt_deg:g}° to the plate and the head {head_deg:g}° above level "
                         f"(the two add up to at most 90°)")
    h = _head(top_deg if top_deg is not None else 0.0)
    p = np.cross(np.array([0.0, 0.0, 1.0]), h)
    b = sh * h + math.sqrt(max(rest, 0.0)) * p + st * np.array([0.0, 0.0, 1.0])
    return b / np.linalg.norm(b)


def _sphere(n: int) -> np.ndarray:
    i = np.arange(n) + 0.5
    phi = np.arccos(1.0 - 2.0 * i / n)
    t = math.pi * (1.0 + 5 ** 0.5) * i
    return np.column_stack([np.cos(t) * np.sin(phi), np.sin(t) * np.sin(phi), np.cos(phi)])


def rough_scores(part, classes, s: dict, n_dirs: int = SEARCH_DIRECTIONS):
    """Every direction of a sphere scored from the normals alone: (directions, overhang area by class (n, 4), height, score)."""
    from scipy.spatial import cKDTree
    bins = _sphere(NORMAL_BINS)
    bi = cKDTree(bins).query(np.asarray(part.face_normals))[1]
    H = np.zeros((4, NORMAL_BINS))
    np.add.at(H, (np.asarray(classes, int), bi), np.asarray(part.area_faces))
    D = _sphere(n_dirs)
    over = (-(D @ bins.T)) > math.cos(math.radians(s["print_overhang_deg"]))
    A = over.astype(float) @ H.T
    hv = np.asarray(part.convex_hull.vertices)
    proj = hv @ D.T
    height = proj.max(axis=0) - proj.min(axis=0)
    per = 1.0 / (s["support_spacing_mm"] ** 2)
    score = (W_FEATURE_AREA * (A[:, FEATURE] + A[:, CLEAR]) + W_CONTACT * per * A[:, POLISH] + W_BORE_CONTACT * per * A[:, BORE]
             + W_HEIGHT * height)
    return D, A, height, score


def candidate_directions(D, score, top_deg, n: int = CANDIDATES, sep_deg: float = CANDIDATE_SEPARATION_DEG):
    """The best-scored directions at least sep_deg apart, and the usual orientations of a ring beside them. A band
    without a head (top_deg None) looks alike from every side round its axis, so its candidates differ by TILT: two
    directions at the same angle to the axis are one candidate (8 Nov: three finalists at 67-71° on the hammered band)."""
    if top_deg is None:
        def axis_tilt(u):
            return math.degrees(math.asin(min(1.0, abs(float(u[2])))))

        def apart(u, v, deg):
            return abs(axis_tilt(u) - axis_tilt(v)) >= deg / 3.0
    else:
        def apart(u, v, deg):
            return float(u @ v) < math.cos(math.radians(deg))
    out = []
    for i in np.argsort(score):
        if all(apart(D[i], o, sep_deg) for o in out):
            out.append(D[i])
            if len(out) == n:
                break
    usual = [np.array([0.0, 0.0, 1.0]), np.array([0.0, 0.0, -1.0])]
    for t in (0.0, 30.0, 45.0, 60.0):
        usual.append(direction_for(t, 90.0 - t, top_deg))
    for u in usual:                                              # the usual ones unless already there
        if all(apart(u, o, 3.0 if top_deg is None else 5.0) for o in out):
            out.append(u)
    return out


# ============================================================================ slicing
@dataclass
class Analysis:
    """A part sliced in one build direction (printer frame: the part's lowest point at z = 0)."""
    b: np.ndarray
    R: np.ndarray
    z_shift: float
    pixel: float
    layer: float
    cols: raster.Columns
    u: np.ndarray                    # unsupported starts (crossing indices)
    u_cls: np.ndarray
    islands: list
    cup_max_mm2: float
    cup_mm3: float
    cup_at: list | None
    layer_max_mm2: float
    height_mm: float
    contacts_est: dict
    feature_uncovered: np.ndarray    # feature / clear unsupported starts no supportable one covers
    feature_islands: list
    terms: dict
    score: float
    top_deg: float | None = None
    start_islands: list = field(default_factory=list)   # the feature islands below the first contact: the part starts on them
    z_first_mm: float = math.inf                        # the lowest contact's height above the part's lowest point (estimated)
    layer_mm2: np.ndarray = field(default_factory=lambda: np.empty(0))   # every layer's area, bottom up (the sweep's layers)

    def slim(self) -> "Analysis":
        """Let the columns go once the analysis is scored (a runner-up's 16 slicings of a 3 M-triangle part held at once
        ran a 7 GB machine out of memory, 2026-11-08): only the trouble spots stay, for the preview."""
        if self.cols is not None:
            self.trouble = self.trouble_points()
            self.cols = None
            self.u = self.u_cls = None
            for isl in self.islands:
                isl["supportable"] = None
        return self

    def trouble_points(self) -> np.ndarray:
        """The feature overhang no contact covers and the feature islands' lowest points (printer frame)."""
        if getattr(self, "trouble", None) is not None:
            return self.trouble
        bad = list(self.feature_uncovered[:4000]) + [isl["lowest"] for isl in self.feature_islands]
        return self.point(bad) if bad else np.empty((0, 3))

    def point(self, idx) -> np.ndarray:
        """The 3-D points (printer frame) of crossings."""
        idx = np.asarray(idx, np.int64)
        return np.column_stack([self.cols.centre(self.cols.pix[idx]), self.cols.z[idx]])

    def to_ring(self, P) -> np.ndarray:
        """Printer-frame points (this analysis's frame) back in the ring frame."""
        P = np.atleast_2d(np.asarray(P, float)).copy()
        P[:, 2] += self.z_shift
        return P @ self.R

    def summary(self) -> dict:
        return {"build_direction": [round(float(x), 4) for x in self.b], "orientation": describe(self.b, self.top_deg),
                "tilt_deg": round(tilt_and_head(self.b, self.top_deg)[0], 1),
                "head_deg": (None if self.top_deg is None else round(tilt_and_head(self.b, self.top_deg)[1], 1)),
                "score": round(self.score, 2), "terms": {k: round(v, 2) for k, v in self.terms.items()},
                "start_islands": len(self.start_islands),
                "first_contact_mm": (None if not math.isfinite(self.z_first_mm) else round(self.z_first_mm, 3)),
                "feature_islands": len(self.feature_islands),
                "feature_overhang_mm2": round(len(self.feature_uncovered) * self.pixel ** 2, 3),
                "contacts_estimate": self.contacts_est, "suction_cup_max_mm2": round(self.cup_max_mm2, 2),
                "largest_layer_mm2": round(self.layer_max_mm2, 1), "height_mm": round(self.height_mm, 2),
                "pixel_mm": self.pixel, "layer_mm": self.layer}

    def line(self) -> str:
        e = self.contacts_est
        bits = [f"~{e['polish'] + e['bore']} contacts" + (f" ({e['bore']} in the bore)" if e["bore"] else "")]
        if self.terms.get("start", 0.0) > 0:
            bits.append("STARTS ON THE FILM: " + ("no contact at all" if not math.isfinite(self.z_first_mm) else
                        f"the first contact {self.z_first_mm:.2f} mm up, {len(self.start_islands)} feature island"
                        f"{'s' if len(self.start_islands) != 1 else ''} before it"))
        fo = len(self.feature_uncovered) * self.pixel ** 2
        bits.append(f"{len(self.feature_islands)} feature island{'s' if len(self.feature_islands) != 1 else ''}"
                    if self.feature_islands else "no feature islands")
        bits.append(f"{fo:.2f} mm² feature overhang" if fo >= 0.005 else "no feature overhang")
        bits.append(f"suction {self.cup_max_mm2:.1f} mm²" if self.cup_max_mm2 >= 0.05 else "no suction cups")
        bits.append(f"layer ≤ {self.layer_max_mm2:.0f} mm², {self.height_mm:.1f} mm high")
        return f"{describe(self.b, self.top_deg)}: " + "; ".join(bits) + f"  [score {self.score:.1f}]"


def _unsupported(cols: raster.Columns, starts: np.ndarray, tan_s: float) -> np.ndarray:
    """The starts with no solid within the self-supporting angle below them in any neighbouring column."""
    pix, z = cols.pix[starts], cols.z[starts]
    sup = np.zeros(len(starts), bool)
    for di, dj in NEIGHBOURS:
        todo = np.flatnonzero(~sup)
        if not len(todo):
            break
        d = cols.pixel * math.hypot(di, dj)
        q = cols.neighbour(pix[todo], di, dj)
        sup[todo] = cols.inside(q, z[todo] - d * tan_s)
    return starts[~sup]


def _sweep(cols: raster.Columns, h: float, classes, tan_s: float):
    """Layer by layer: islands (a piece of the layer touching nothing printed before it within the overhang
    reach), suction cups (resin the layer walls in, sealed below), layer areas."""
    from scipy import ndimage
    struct = np.ones((3, 3), bool)
    reach = max(1, int(round(h / tan_s / cols.pixel)))
    prev = None
    vented_prev = None
    islands, layer_px = [], []
    cup_best, cup_total, cup_at = 0, 0, None
    for k, occ in raster.layers(cols, h):
        zk = cols.zmin + (k + 0.5) * h
        n_solid = int(occ.sum())
        layer_px.append(n_solid)
        if n_solid:
            lab, n = ndimage.label(occ, structure=struct)
            if prev is None or not prev.any():
                new = np.arange(1, n + 1)
            else:
                near = ndimage.binary_dilation(prev, structure=struct, iterations=reach)
                ov = np.bincount(lab[occ & near], minlength=n + 1)
                new = np.flatnonzero(ov[1:] == 0) + 1
            if len(new):
                flat = lab.ravel()
                sel = np.flatnonzero(np.isin(flat, new))
                labs = flat[sel]
                idx = cols.below(sel, np.full(len(sel), zk))
                order = np.argsort(labs, kind="stable")
                labs, sel, idx = labs[order], sel[order], idx[order]
                cuts = np.flatnonzero(np.r_[True, labs[1:] != labs[:-1], True])
                for a, b in zip(cuts[:-1], cuts[1:]):
                    ii = idx[a:b]
                    ii = ii[ii >= 0]
                    if not len(ii):
                        continue
                    cl = np.asarray(classes)[cols.tri[ii]]
                    ok = SUPPORTABLE[cl]
                    lowest = int(ii[np.argmin(cols.z[ii])])
                    islands.append({"layer": k, "z": float(zk), "z_low": float(cols.z[lowest]), "px": int(b - a), "lowest": lowest,
                                    "cls": int(np.asarray(classes)[cols.tri[lowest]]),
                                    "supportable": ii[ok][np.argsort(cols.z[ii[ok]])]})
        air = ~occ
        lab_a, na = ndimage.label(air, structure=struct)
        vent = np.zeros(na + 1, bool)
        vent[np.r_[lab_a[0], lab_a[-1], lab_a[:, 0], lab_a[:, -1]]] = True
        if vented_prev is None:
            vent[:] = True
        else:
            vent[lab_a[vented_prev & air]] = True
        vent[0] = False
        vented = vent[lab_a]
        cup = air & ~vented
        nc = int(cup.sum())
        cup_total += nc
        if nc > cup_best:
            jj, ii_ = np.nonzero(cup)
            cup_best = nc
            cup_at = [float(cols.origin[0] + (ii_.mean() + 0.5) * cols.pixel), float(cols.origin[1] + (jj.mean() + 0.5) * cols.pixel), float(zk)]
        vented_prev = vented
        prev = occ
    p2 = cols.pixel ** 2
    return islands, cup_best * p2, cup_total * p2 * h, cup_at, np.asarray(layer_px, float) * p2


def _thin(P: np.ndarray, cell: float) -> np.ndarray:
    """Indices of the lowest point in each cell of a grid: a dense set of candidates thinned before the greedy pick."""
    if not len(P):
        return np.empty(0, np.int64)
    key = np.floor(P / cell).astype(np.int64)
    order = np.lexsort((P[:, 2], key[:, 2], key[:, 1], key[:, 0]))
    k = key[order]
    first = np.r_[True, np.any(k[1:] != k[:-1], axis=1)]
    return order[first]


def _poisson(P: np.ndarray, spacing: float, order=None) -> list[int]:
    """Greedy pick, lowest first: a point is taken unless one taken already lies within `spacing`."""
    grid: dict = {}
    out = []

    def add(p, i):
        grid.setdefault(tuple(np.floor(p / spacing).astype(int)), []).append(p)
        out.append(i)
    order = np.argsort(P[:, 2], kind="stable") if order is None else order
    for i in order:
        p = P[i]
        c = np.floor(p / spacing).astype(int)
        clash = False
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for q in grid.get((c[0] + dx, c[1] + dy, c[2] + dz), ()):
                        if float(np.sum((q - p) ** 2)) < spacing * spacing:
                            clash = True
                            break
                    if clash:
                        break
                if clash:
                    break
            if clash:
                break
        if not clash:
            add(p, int(i))
    return out


def start_islands(feature_islands: list, z_first: float) -> list:
    """The feature islands that begin below the first contact (z_first, the part's lowest point at 0): what prints on
    nothing but the film before any support has hold of the part."""
    return [isl for isl in feature_islands if isl["z_low"] < z_first]


def start_gap_layers(z_first: float, s: dict) -> float:
    """How many layers the part prints on the film alone beyond what it survives: the first contact's height above the
    part's lowest point less print_start_gap_mm, in layers (0 when the start is held in time; capped when there is no
    contact at all). Nothing but the film holds the part until the first contact: a layer or two of a feature cured onto
    the film comes away with the tips, but a stack of them is the part's foot, and the part then grows on the film while
    the supports print alone (the court band, 8 Nov 2026: leaning 53°, its bottom bead row led by 0.6 mm, 12 layers)."""
    if not math.isfinite(z_first):
        return 100.0
    return min(100.0, max(0.0, (z_first - s["print_start_gap_mm"]) / s["print_layer_mm"]))


def printer_triangles(part, b):
    """The part's triangles in the printer frame for build direction b, its lowest point at z = 0, and what that took."""
    R = frame(b)
    V = np.asarray(part.vertices) @ R.T
    z_shift = float(V[:, 2].min())
    V[:, 2] -= z_shift
    return V[np.asarray(part.faces)], R, z_shift


def analyse(part, classes, b, s: dict, pixel: float = SEARCH_PIXEL_MM, layer: float | None = None, top_deg=None) -> Analysis:
    """Slice the part in build direction b and score it (see the module docstring)."""
    from scipy.spatial import cKDTree
    layer = pixel if layer is None else layer
    tri, R, z_shift = printer_triangles(part, b)
    nz = np.asarray(part.face_normals) @ R[2]
    cols = raster.Columns(tri, nz < 0, pixel)
    classes = np.asarray(classes)
    tan_s = math.tan(math.radians(s["print_overhang_deg"]))
    u = _unsupported(cols, cols.starts, tan_s)
    u_cls = classes[cols.tri[u]]
    islands, cup_max, cup_mm3, cup_at, layer_mm2 = _sweep(cols, layer, classes, tan_s)
    layer_max = float(layer_mm2.max()) if len(layer_mm2) else 0.0
    an = Analysis(np.asarray(b, float) / np.linalg.norm(b), R, z_shift, pixel, layer, cols, u, u_cls, islands, cup_max, cup_mm3,
                  cup_at, layer_max, float(tri[:, :, 2].max()), {}, np.empty(0, np.int64), [], {}, 0.0, top_deg, layer_mm2=layer_mm2)
    sup = u[SUPPORTABLE[u_cls]]
    feat = u[~SUPPORTABLE[u_cls]]
    P = an.point(sup)
    spacing = s["support_spacing_mm"]
    th = _thin(P, spacing / 3.0)
    picks = [int(th[i]) for i in _poisson(P[th], spacing)] if len(th) else []
    held = [isl for isl in islands if len(isl["supportable"])]
    an.feature_islands = [isl for isl in islands if not len(isl["supportable"])]
    seeds = [an.point([isl["supportable"][0]])[0] for isl in held]
    lows = ([float(P[:, 2].min())] if len(P) else []) + [float(p[2]) for p in seeds]   # where the first contact would be
    an.z_first_mm = min(lows) if lows else math.inf
    an.start_islands = start_islands(an.feature_islands, an.z_first_mm)
    extra = 0
    if seeds:
        tree = cKDTree(P[picks]) if picks else None
        for p in seeds:
            if tree is None or tree.query(p)[0] > spacing / 2:
                extra += 1
    pick_cls = classes[cols.tri[sup[picks]]] if picks else np.empty(0, int)
    an.contacts_est = {"polish": int(np.sum(pick_cls == POLISH)) + extra, "bore": int(np.sum(pick_cls == BORE))}
    if len(feat):
        cover = [P[picks]] if picks else []
        if seeds:
            cover.append(np.asarray(seeds))
        if cover:
            near = cKDTree(np.vstack(cover)).query(an.point(feat))[0] <= COVER * spacing
            an.feature_uncovered = feat[~near]
        else:
            an.feature_uncovered = feat
    p2 = pixel ** 2
    an.terms = {"start": W_START * start_gap_layers(an.z_first_mm, s),
                "feature islands": W_FEATURE_ISLAND * len(an.feature_islands),
                "feature overhang": W_FEATURE_AREA * len(an.feature_uncovered) * p2,
                "contacts": W_CONTACT * an.contacts_est["polish"] + W_BORE_CONTACT * an.contacts_est["bore"],
                "suction": W_CUP * cup_max, "peel": W_PEEL * layer_max, "height": W_HEIGHT * an.height_mm}
    an.score = float(sum(an.terms.values()))
    return an


# ============================================================================ supports
@dataclass
class Support:
    x: float
    y: float
    z_top: float                 # the contact (analysis frame)
    z_bottom: float              # the raft's top, or the part below
    kind: str                    # "raft" | "part"
    cls: int
    foot_cls: int | None
    diameter: float
    depth_top: float
    depth_bottom: float
    island: bool = False
    hold: bool = False           # added by hold_layers: a layer below would have hung on too few tips

    @property
    def length(self) -> float:
        return self.z_top - self.z_bottom


def _disc(radius_px: float):
    r = int(math.ceil(radius_px))
    di, dj = np.meshgrid(np.arange(-r, r + 1), np.arange(-r, r + 1))
    m = di * di + dj * dj <= radius_px * radius_px
    return di[m], dj[m]


def _clear(cols: raster.Columns, pix: int, radius: float, z0: float, z1: float) -> bool:
    """No solid within `radius` of the pixel's column between z0 and z1."""
    if z1 <= z0:
        return True
    di, dj = _disc(radius / cols.pixel)
    i, j = pix % cols.nx + di, pix // cols.nx + dj
    ok = (i >= 0) & (i < cols.nx) & (j >= 0) & (j < cols.ny)
    q = (j * cols.nx + i)[ok]
    return not bool(cols.solid_between(q, np.full(len(q), z0), np.full(len(q), z1)).any())


def _slope_tan(nz: float) -> float:
    return math.sqrt(max(0.0, 1.0 - nz * nz)) / max(abs(nz), 1e-6)


def build_support(an: Analysis, idx: int, classes, nz_faces, s: dict, island: bool = False):
    """A support for the contact at crossing idx, or (None, why not)."""
    cols = an.cols
    pix = int(cols.pix[idx])
    x, y = cols.centre([pix])[0]
    zc = float(cols.z[idx])
    cls = int(classes[cols.tri[idx]])
    if not SUPPORTABLE[cls]:
        return None, "on a feature"
    r_tip = s["support_tip_mm"] / 2.0
    L = s["support_tip_length_mm"]
    clear = s["support_clearance_mm"]
    depth_top = s["support_contact_depth_mm"] + r_tip * min(_slope_tan(float(nz_faces[cols.tri[idx]])), 1.5)
    below = int(cols.below(np.array([pix]), np.array([zc - 1e-4]))[0])
    if below >= 0 and cols.w_after[below] <= 0:
        z_foot = float(cols.z[below])
        foot_cls = int(classes[cols.tri[below]])
        if not SUPPORTABLE[foot_cls]:
            return None, "the part below is a feature"
        if zc - z_foot < 2 * L + STRUT_EXTRA_MM:
            return None, f"the part below is only {zc - z_foot:.2f} mm away"
        kind = "part"
        depth_bottom = s["support_contact_depth_mm"] + r_tip * min(_slope_tan(float(nz_faces[cols.tri[below]])), 1.5)
        z_low = z_foot
    elif below >= 0:
        return None, "inside the part"
    else:
        kind, foot_cls, depth_bottom = "raft", None, 0.0
        z_low = -s["support_lift_mm"]
    d = min(max(s["support_column_mm"], (zc - z_low) / SLENDERNESS), COLUMN_MAX_MM)
    lo = z_low + (L if kind == "part" else 0.0)
    if not _clear(cols, pix, d / 2 + clear, lo, zc - L):
        return None, "its column would pass the part"
    half = (r_tip + d / 2) / 2 + clear / 2
    if not _clear(cols, pix, half, zc - L, zc - L / 2):
        return None, "its tip would graze the part"
    if kind == "part" and not _clear(cols, pix, half, z_low + L / 2, z_low + L):
        return None, "its foot would graze the part"
    return Support(float(x), float(y), zc, z_low, kind, cls, foot_cls, d, depth_top, depth_bottom, island), None


def place_supports(an: Analysis, part, classes, s: dict):
    """Contacts at the analysis: every island first (its lowest supportable point that takes a support), then the
    supportable overhangs at the spacing, lowest first. Returns (supports, misses: [(crossing, why)])."""
    classes = np.asarray(classes)
    nz_faces = np.asarray(part.face_normals) @ an.R[2]
    supports, misses = [], []
    taken = []
    for isl in an.islands:
        cands = list(isl["supportable"])
        why = "no supportable point"
        for idx in cands[:24]:
            sp, why = build_support(an, int(idx), classes, nz_faces, s, island=True)
            if sp is not None:
                supports.append(sp)
                taken.append(np.array([sp.x, sp.y, sp.z_top]))
                break
        else:
            if cands:
                misses.append((int(cands[0]), f"island: {why}"))
    sup = an.u[SUPPORTABLE[an.u_cls]]
    P = an.point(sup)
    spacing = max(s["support_spacing_mm"], s["support_min_spacing_mm"])
    th = _thin(P, spacing / 4.0)
    order = th[np.argsort(P[th, 2], kind="stable")]
    grid: dict = {}

    def near(p):
        c = np.floor(p / spacing).astype(int)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for q in grid.get((c[0] + dx, c[1] + dy, c[2] + dz), ()):
                        if float(np.sum((q - p) ** 2)) < spacing * spacing:
                            return True
        return False

    def add(p):
        grid.setdefault(tuple(np.floor(p / spacing).astype(int)), []).append(p)
    for p in taken:
        add(p)
    for i in order:
        p = P[i]
        if near(p):
            continue
        sp, why = build_support(an, int(sup[i]), classes, nz_faces, s)
        if sp is None:
            misses.append((int(sup[i]), why))
            continue
        supports.append(sp)
        add(np.array([sp.x, sp.y, sp.z_top]))
    hold_layers(an, supports, sup, P, classes, nz_faces, s)
    return supports, misses


def hold_layers(an: Analysis, supports: list, sup, P, classes, nz_faces, s: dict) -> list:
    """Contacts added where a layer would hang on too few tips. Nothing but the contacts engaged below a layer holds
    it off the film, so, bottom up, every layer needs a contact at or under its height per support_hold_area_mm2 of
    its area; where it has fewer, the supportable overhang at or below that height takes more, lowest first, at half
    the spacing - but NEVER nearer another contact than support_min_spacing_mm. A flat rim on its spacing's contacts
    usually has enough (the hammered band, 15 tips under 70 mm²); a ring standing on edge at a wide spacing would hang
    its first half millimetre - 24 mm² of dome - on the one tip at its lowest point (the court band at 3 mm, 9 Nov
    2026). The first version went down to a quarter of the spacing and packed five tips 0.75 mm apart under the ring's
    lowest point, where the surface lies flat to the vat: resin bridged from cone to cone and cured into a blob
    (Mark's prints, 13 Nov 2026). Spread tips beat a held layer: what the minimum spacing leaves hanging is reported
    by the soft check `layers held`, not fixed by crowding. Appends to `supports` (flagged `hold`) and returns what it
    added."""
    cols = an.cols
    spacing = s["support_spacing_mm"]
    per = s["support_hold_area_mm2"]
    gap = s["print_start_gap_mm"]                                # a contact this little above a layer still holds it (as at the start)
    if cols is None or not len(an.layer_mm2) or per <= 0 or not len(P):
        return []
    order = _thin(P, spacing / 8.0)
    order = order[np.argsort(P[order, 2], kind="stable")]
    z_cand = P[order, 2]
    taken = [np.array([sp.x, sp.y, sp.z_top]) for sp in supports]
    tops = sorted(sp.z_top for sp in supports)
    failed: set = set()
    added = []
    h = an.layer
    import bisect

    floor = 1.5 * s["support_column_mm"]                         # never two columns in one another (columns are vertical: in plan)
    least = s["support_min_spacing_mm"]                          # ... nor two tips near enough for resin to bridge them

    def far(p, d):
        return all(float(np.sum((q - p) ** 2)) >= d * d and float(np.sum((q[:2] - p[:2]) ** 2)) >= floor * floor for q in taken)
    stages = (max(spacing / 2.0, least),)
    for k, area in enumerate(an.layer_mm2):
        if area <= 0:
            continue
        zk = cols.zmin + (k + 1.0) * h                           # the layer's top: contacts at or under it hold it
        need = int(math.ceil(area / per))
        engaged = bisect.bisect_right(tops, zk + gap + 1e-9)
        if engaged >= need:
            continue
        last = int(np.searchsorted(z_cand, zk + gap + 1e-9, side="right"))
        for fine in stages:
            for j in range(last):
                if engaged >= need:
                    break
                i = int(order[j])
                if i in failed or not far(P[i], fine):
                    continue
                sp, why = build_support(an, int(sup[i]), classes, nz_faces, s)
                if sp is None:
                    failed.add(i)
                    continue
                sp.hold = True
                supports.append(sp)
                added.append(sp)
                taken.append(np.array([sp.x, sp.y, sp.z_top]))
                bisect.insort(tops, sp.z_top)
                engaged += 1
            if engaged >= need:
                break
    return added


def layers_hold(an: Analysis, supports, s: dict):
    """(the most mm² of a layer per contact engaged under it, the height of that layer) - what hold_layers left."""
    import bisect
    cols = an.cols
    if cols is None or not len(an.layer_mm2):
        return 0.0, 0.0
    tops = sorted(sp.z_top for sp in supports)
    worst, at = 0.0, 0.0
    for k, area in enumerate(an.layer_mm2):
        if area <= 0:
            continue
        zk = cols.zmin + (k + 1.0) * an.layer
        engaged = bisect.bisect_right(tops, zk + s["print_start_gap_mm"] + 1e-9)
        ratio = area / engaged if engaged else math.inf
        if ratio > worst:
            worst, at = ratio, zk
    return worst, at


def coverage(an: Analysis, supports, s: dict) -> dict:
    """What the supports leave: plain overhang farther than the spacing from every contact (where the greedy pick was
    refused), feature overhang farther than COVER x the spacing from every contact, islands without a contact
    (crossing index arrays / lists)."""
    from scipy.spatial import cKDTree
    C = np.array([[sp.x, sp.y, sp.z_top] for sp in supports]) if supports else np.empty((0, 3))
    tree = cKDTree(C) if len(C) else None

    def uncovered(idx, radius):
        if not len(idx) or tree is None:
            return idx
        return idx[tree.query(an.point(idx))[0] > radius]
    sup = an.u[SUPPORTABLE[an.u_cls]]
    feat = an.u[~SUPPORTABLE[an.u_cls]]
    reach = s["support_spacing_mm"] + 2 * an.pixel
    lost = []
    for isl in an.islands:
        if not len(isl["supportable"]):
            continue
        P = an.point(isl["supportable"])
        if tree is None or tree.query(P)[0].min() > s["support_tip_mm"] + an.pixel * 2:
            lost.append(isl)
    return {"supportable_uncovered": uncovered(sup, reach), "feature_uncovered": uncovered(feat, COVER * s["support_spacing_mm"]),
            "islands_lost": lost}


# ============================================================================ meshes
def _revolve(profile, x: float, y: float, segments: int = SEGMENTS):
    """A closed solid of revolution about the vertical through (x, y): profile [(r, z) ...] bottom to top, its first
    and last points on the axis."""
    import trimesh
    ang = np.linspace(0.0, 2.0 * math.pi, segments, endpoint=False)
    ca, sa = np.cos(ang), np.sin(ang)
    rings = profile[1:-1]
    V = [[x, y, profile[0][1]]]
    for r, z in rings:
        V += [[x + r * c, y + r * s_, z] for c, s_ in zip(ca, sa)]
    V.append([x, y, profile[-1][1]])
    F = []
    S = segments
    for k in range(S):                                   # the bottom fan
        F.append([0, 1 + (k + 1) % S, 1 + k])
    for i in range(len(rings) - 1):
        a, b = 1 + i * S, 1 + (i + 1) * S
        for k in range(S):
            k1 = (k + 1) % S
            F.append([a + k, a + k1, b + k1])
            F.append([a + k, b + k1, b + k])
    top = len(V) - 1
    last = 1 + (len(rings) - 1) * S
    for k in range(S):
        F.append([top, last + k, last + (k + 1) % S])
    m = trimesh.Trimesh(np.array(V, float), np.array(F, np.int64), process=False)
    if m.volume < 0:
        m.invert()
    return m


NECK_OUT_MM = 0.05               # the neck's straight run reaches this far out of the part (and a base this far above the raft):
                                 # a ring of the solid's vertices lying IN a flat face pinched the union, and the file came
                                 # back non-manifold from STL (8 Nov, a band lying at 73°); crossing the face, it does not


def support_mesh(sp: Support, s: dict):
    r_tip = s["support_tip_mm"] / 2.0
    L = s["support_tip_length_mm"]
    rc = sp.diameter / 2.0
    zc = sp.z_top
    n = NECK_OUT_MM
    if sp.kind == "raft":
        zr = sp.z_bottom
        rb = BASE_FLARE * sp.diameter
        prof = [(0.0, zr - 0.3), (rb, zr - 0.3), (rb, zr + 2 * n), (rc, zr + 0.6 + 2 * n), (rc, zc - L), (r_tip, zc - n),
                (r_tip, zc + sp.depth_top), (0.0, zc + sp.depth_top)]
    else:
        zf = sp.z_bottom
        prof = [(0.0, zf - sp.depth_bottom), (r_tip, zf - sp.depth_bottom), (r_tip, zf + n), (rc, zf + L), (rc, zc - L), (r_tip, zc - n),
                (r_tip, zc + sp.depth_top), (0.0, zc + sp.depth_top)]
    return _revolve(prof, sp.x, sp.y)


def raft_mesh(supports, s: dict):
    """The raft under the supports that stand on it: their bases' hull, raft_margin_mm wider, raft_thickness_mm
    thick, its top edge chamfered (analysis frame: its top at -support_lift_mm)."""
    import trimesh
    from shapely.geometry import MultiPoint
    feet = [sp for sp in supports if sp.kind == "raft"]
    if not feet:
        return None
    rb = max(BASE_FLARE * sp.diameter for sp in feet)
    hull = MultiPoint([(sp.x, sp.y) for sp in feet]).convex_hull.buffer(rb + s["raft_margin_mm"], quad_segs=8)
    t = s["raft_thickness_mm"]
    c = min(0.4, t / 2.0)
    top = -s["support_lift_mm"]
    lo = np.asarray(hull.exterior.coords)[:-1]
    hi = np.asarray(hull.buffer(-c, quad_segs=8).exterior.coords)[:-1]
    pts = np.vstack([np.column_stack([lo, np.full(len(lo), top - t)]), np.column_stack([hi, np.full(len(hi), top)])])
    return trimesh.convex.convex_hull(pts)


def assemble(part_printer, supports, raft, s: dict):
    """part ∪ supports ∪ raft as one manifold. Returns (trimesh, bodies)."""
    import manifold3d as mf
    import trimesh
    from . import geom
    pieces = [geom._manifold(part_printer)] + [geom._manifold(support_mesh(sp, s)) for sp in supports]
    if raft is not None:
        pieces.append(geom._manifold(raft))
    bad = [i for i, p in enumerate(pieces) if p.status() != mf.Error.NoError]
    if bad:
        raise ValueError(f"manifold3d could not read {'the part' if 0 in bad else f'{len(bad)} supports'} "
                         f"({pieces[bad[0]].status()})")
    u = mf.Manifold.batch_boolean(pieces, mf.OpType.Add)
    m = u.to_mesh()
    out = trimesh.Trimesh(np.asarray(m.vert_properties)[:, :3].astype(float), np.asarray(m.tri_verts, np.int64), process=False)
    return out, len(u.decompose())


# ============================================================================ cure-through
def compensate_cure_through(part, classes, b, depth: float):
    """The part thinned where it faces the vat, so that it prints at size. Light passes through each new layer and
    cures resin beyond it: every surface facing the vat grows towards it by the cure-through depth (the "thickened
    downside" of Mark's Supercast prints, 13 Nov 2026 - worst where a ring standing on edge lies flat to the vat). The
    printed solid is the sliced one swept that far towards the vat, so the file is the part less that sweep: the part ∩
    the part moved `depth` along the build direction b (an erosion by a segment - exact for this model; whatever is
    thinner than `depth` along b is gone, so the depth must stay well under the thinnest feature). Up-facing surfaces
    and walls parallel to b do not move. Returns (mesh in the part's frame, its faces' classes - each face keeps the
    class of the face it came from -, the volume removed, the bodies it is in)."""
    import manifold3d as mf
    import trimesh
    from . import geom
    b = np.asarray(b, float) / np.linalg.norm(b)
    a = geom._manifold(part)
    if a.status() != mf.Error.NoError:
        raise ValueError(f"manifold3d could not read the part for the cure-through compensation ({a.status()})")
    out = a ^ a.translate(tuple(float(v) for v in b * depth))
    m = out.to_mesh()
    faces = np.asarray(m.tri_verts, np.int64)
    if not len(faces):
        raise ValueError(f"nothing is left of the part after a cure-through compensation of {depth:g} mm")
    mesh = trimesh.Trimesh(np.asarray(m.vert_properties)[:, :3].astype(float), faces, process=False)
    cls = np.asarray(classes)[np.asarray(m.face_id, np.int64)]   # the part's triangle each one came from (either copy)
    # the cut leaves slivers where a wall runs along b and zero-volume crumbs where the two copies kiss (the real court
    # band, 13 Nov 2026: 3016 slivers, one 6-triangle crumb; unhealed it read back from STL with 1073 open edges)
    mesh.merge_vertices(digits_vertex=HEAL_DIGITS)
    f = np.asarray(mesh.faces)
    keep = (f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])
    mesh.update_faces(keep)
    cls = cls[keep]
    labels = trimesh.graph.connected_component_labels(mesh.face_adjacency, node_count=len(mesh.faces))
    counts = np.bincount(labels)
    bodies = 0
    keep = np.ones(len(mesh.faces), bool)
    for lab in np.flatnonzero(counts):
        sel = labels == lab
        if len(counts) > 1 and gate.is_speck(mesh.submesh([np.flatnonzero(sel)], append=True, repair=False)):
            keep &= ~sel
        else:
            bodies += 1
    if not keep.all():
        mesh.update_faces(keep)
        cls = cls[keep]
    mesh.remove_unreferenced_vertices()
    return mesh, cls, float(a.volume() - mesh.volume), bodies


# ============================================================================ the part
HEAL_DIGITS = 5                  # vertices within 10 nm are one: ten times the float32 STL's own quantum at 10 mm


def load_part(stl):
    """The gated part without the mesher's specks (gate.is_speck): one closed body, its nanometre slivers collapsed
    (vertices within 10^-HEAL_DIGITS mm merged and the triangles that lose a vertex dropped - the mesh stays closed and
    its volume the same to 1e-8; a boolean's slivers a few nanometres wide, rotated into the printer frame, united and
    read back from float32, came back as edges shared by four faces, 9 Nov 2026 - the fake nTopCL's court band; nTop's
    meshes have none). `metadata["collapsed"]` counts them."""
    import trimesh
    m = gate.load_mesh(Path(stl))
    n0 = len(m.faces)
    m.merge_vertices(digits_vertex=HEAL_DIGITS)
    f = np.asarray(m.faces)
    m.update_faces((f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2]))
    m.remove_unreferenced_vertices()
    collapsed = n0 - len(m.faces)
    m.metadata["collapsed"] = collapsed
    labels = trimesh.graph.connected_component_labels(m.face_adjacency, node_count=len(m.faces))
    counts = np.bincount(labels)
    if len(counts) <= 1:
        return m, 0
    big = int(np.argmax(counts))
    keep = np.ones(len(m.faces), bool)
    dropped = 0
    for lab in np.flatnonzero(counts):
        if lab == big:
            continue
        sel = labels == lab
        piece = m.submesh([np.flatnonzero(sel)], append=True, repair=False)
        if gate.is_speck(piece):
            keep &= ~sel
            dropped += 1
    if dropped:
        m = m.submesh([np.flatnonzero(keep)], append=True, repair=False)
        m.metadata["collapsed"] = collapsed
    return m, dropped


# ============================================================================ the whole job
@dataclass
class PrepResult:
    stem: str
    source: Path
    model: SurfaceModel
    settings: dict
    ranked: list
    chosen: Analysis
    supports: list
    misses: list
    cover: dict
    checks: list
    files: dict
    class_area: dict
    metal: str | None = None
    scale: float = 1.0
    warnings: list = field(default_factory=list)
    seconds: float = 0.0
    forced: bool = False
    bodies: int = 0
    finalists: list = field(default_factory=list)   # the search's best few, sliced again at the printer's layer
    part_volume_mm3: float = 0.0     # the part as built (design size, specks dropped)
    part_extents_mm: list = field(default_factory=list)   # its extents along the ring frame's X (head), Y, Z (axis)

    @property
    def status(self) -> str:
        hard = [c for c in self.checks if c.hard]
        if any(c.status == gate.FAILED for c in hard):
            return gate.FAILED
        if any(c.status == gate.INCOMPLETE for c in hard):
            return gate.INCOMPLETE
        return gate.PASSED

    @property
    def ok(self) -> bool:
        return self.status == gate.PASSED

    def counts(self) -> dict:
        n = {"polish": 0, "bore": 0, "on the part": 0, "hold": 0}
        for sp in self.supports:
            n["bore" if sp.cls == BORE else "polish"] += 1
            n["on the part"] += sp.kind == "part"
            n["hold"] += sp.hold
        return n

    def cautions(self) -> str:
        """What the print file leaves to chance, in a few words (the soft checks): islands and overhang on features."""
        out = []
        if self.chosen.feature_islands:
            out.append(f"{len(self.chosen.feature_islands)} feature island{'s' if len(self.chosen.feature_islands) != 1 else ''} unsupported")
        fo = len(self.cover["feature_uncovered"]) * self.chosen.pixel ** 2
        if fo >= 0.05:
            out.append(f"{fo:.1f} mm² of feature overhang")
        return ", ".join(out)

    def headline(self) -> str:
        n = self.counts()
        where = []
        if n["polish"]:
            where.append(f"{n['polish']} on polished faces")
        if n["bore"]:
            where.append(f"{n['bore']} in the bore")
        tail = f", {n['on the part']} standing on the part" if n["on the part"] else ""
        tail += f", {n['hold']} added under the lowest layers" if n["hold"] else ""
        return f"{len(self.supports)} supports ({', '.join(where) or 'none'}{tail}), {describe(self.chosen.b, self.model.top_deg)}"

    def text(self) -> str:
        p2 = self.chosen.pixel ** 2
        lines = [f"Print prep {self.stem}: {self.model.label}" + (f", scaled {self.scale:.4f} for {self.metal}" if self.metal else "")]
        lines.append("  surface: " + ", ".join(f"{CLASS_NAMES[i]} {a:.0f} mm²" for i, a in self.class_area.items() if a > 0))
        lines.append("  orientations (best first):")
        for i, an in enumerate(self.ranked[:6]):
            lines.append(f"    {i + 1}. {an.line()}")
        if len(self.finalists) > 1:
            lines.append(f"  the best {len(self.finalists)} sliced again at {self.finalists[0].layer:g} mm:")
            for an in self.finalists:
                lines.append(f"    {'*' if an is self.chosen else ' '} {an.line()}")
        lines.append(f"  chosen{' (as asked)' if self.forced else ''}: {self.headline()}")
        c = self.cover
        if self.chosen.terms.get("start", 0.0) > 0:
            lines.append("  STARTS ON THE FILM: " + ("no contact holds the part" if not self.supports else
                         f"the first contact {self.chosen.z_first_mm:.2f} mm above the part's lowest point; before it "
                         f"{len(self.chosen.start_islands)} island(s) on features - "
                         + "; ".join(self._where(isl["lowest"]) for isl in self.chosen.start_islands[:6])))
        if self.chosen.feature_islands:
            lines.append(f"  unsupported: {len(self.chosen.feature_islands)} island(s) on features - "
                         + "; ".join(self._where(isl["lowest"]) for isl in self.chosen.feature_islands[:6]))
        fo = len(c["feature_uncovered"]) * p2
        if fo >= 0.005:
            lines.append(f"  unsupported: {fo:.2f} mm² of feature overhang (no contact allowed there) - {self._spread(c['feature_uncovered'])}")
        so = len(c["supportable_uncovered"]) * p2
        if so >= 0.005:
            lines.append(f"  missed: {so:.2f} mm² of plain overhang no support could reach - {self._spread(c['supportable_uncovered'])}")
        if c["islands_lost"]:
            lines.append(f"  missed: {len(c['islands_lost'])} island(s) on plain metal no support could reach")
        if self.chosen.cup_max_mm2 >= 0.05:
            lines.append(f"  suction: a cup of up to {self.chosen.cup_max_mm2:.1f} mm² (resin walled in and sealed below)")
        lines += [f"  [{'ok  ' if ch.status == gate.PASSED else ('warn' if not ch.hard else 'FAIL')}] {ch.name}: {ch.detail}" for ch in self.checks]
        for k, v in self.files.items():
            lines.append(f"  {k}: {v}")
        lines += [f"  note: {w}" for w in self.warnings]
        return "\n".join(lines)

    def _where(self, idx) -> str:
        P = self.chosen.to_ring(self.chosen.point([idx]))[0] / self.scale
        th = math.degrees(math.atan2(P[1], P[0]))
        return f"θ {th:+.0f}° r {math.hypot(P[0], P[1]):.2f} z {P[2]:+.2f}"

    def _spread(self, idx) -> str:
        if not len(idx):
            return ""
        P = self.chosen.to_ring(self.chosen.point(idx)) / self.scale
        th = np.degrees(np.arctan2(P[:, 1], P[:, 0]))
        return f"θ {th.min():+.0f}° .. {th.max():+.0f}°, worst near {self._where(idx[0])}"

    def to_dict(self) -> dict:
        an = self.chosen
        sup = []
        for sp in self.supports:
            ring = an.to_ring([[sp.x, sp.y, sp.z_top]])[0] / self.scale
            sup.append({"contact": [round(sp.x, 3), round(sp.y, 3), round(sp.z_top + self._lift, 3)],
                        "contact_ring": [round(float(v), 3) for v in ring], "theta_deg": round(math.degrees(math.atan2(ring[1], ring[0])), 1),
                        "on": CLASS_NAMES[sp.cls], "stands_on": "raft" if sp.kind == "raft" else CLASS_NAMES[sp.foot_cls],
                        "length_mm": round(sp.length, 2), "diameter_mm": round(sp.diameter, 2), "island": sp.island, "hold": sp.hold})
        p2 = an.pixel ** 2
        return {"stem": self.stem, "source": str(self.source), "model": self.model.label, "metal": self.metal, "scale": self.scale,
                "part_volume_mm3": round(self.part_volume_mm3, 2), "part_extents_mm": [round(v, 2) for v in self.part_extents_mm],
                "settings": self.settings, "surface_mm2": {CLASS_NAMES[i]: round(a, 1) for i, a in self.class_area.items()},
                "zones": self.model.zone_counts, "forced": self.forced,
                "candidates": [a.summary() for a in self.ranked], "finalists": [a.summary() for a in self.finalists],
                "chosen": an.summary(), "supports": sup,
                "unsupported": {"start_islands": [self._where(isl["lowest"]) for isl in an.start_islands],
                                "first_contact_mm": (None if not math.isfinite(an.z_first_mm) else round(an.z_first_mm, 3)),
                                "feature_islands": [self._where(isl["lowest"]) for isl in an.feature_islands],
                                "feature_overhang_mm2": round(len(self.cover["feature_uncovered"]) * p2, 3),
                                "plain_overhang_missed_mm2": round(len(self.cover["supportable_uncovered"]) * p2, 3),
                                "islands_missed": len(self.cover["islands_lost"]),
                                "misses": [{"at": self._where(i), "why": w} for i, w in self.misses[:40]]},
                "checks": [ch.__dict__ for ch in self.checks], "status": self.status, "bodies": self.bodies,
                "files": {k: str(v) for k, v in self.files.items()}, "warnings": self.warnings, "seconds": round(self.seconds, 1)}

    _lift: float = 0.0


def _class_area(part, classes) -> dict:
    a = np.asarray(part.area_faces)
    return {i: float(a[np.asarray(classes) == i].sum()) for i in range(4)}


def prepare(stl, spec, out_dir, stem: str | None = None, metal: str | None = None, bore: str = "allow", orient=None,
            settings: dict | None = None, picture: bool = True, progress=None) -> PrepResult:
    """Orient, support and write the print file of a gated part (see the module docstring). `orient`: None (the
    best), a rank in the search (1 = the best), a (tilt°, head°) pair, or a build direction (3 numbers, ring frame)."""
    t0 = time.time()
    say = progress or (lambda m: None)
    s = prep_settings(**(settings or {}))
    stl = Path(stl)
    stem = stem or getattr(spec, "stem", None) or stl.stem
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    model = surface_model(spec)
    say("reading the part")
    part, specks = load_part(stl)
    say(f"classing {len(part.faces):,} faces")
    classes = model.classify(part, bore=bore, keepoff_mm=s["support_keepoff_mm"])
    area = _class_area(part, classes)
    part_volume, part_extents = float(part.volume), [float(v) for v in part.extents]     # at the design's size
    warnings = []
    scale = 1.0
    if metal:
        scale, warnings = tables.print_scale(metal)
        part.apply_scale(scale)
    say("scoring directions")
    D, _, _, rough = rough_scores(part, classes, s)
    dirs = candidate_directions(D, rough, model.top_deg)
    ranked = []
    for i, b in enumerate(dirs):
        say(f"slicing candidate {i + 1}/{len(dirs)}")
        ranked.append(analyse(part, classes, b, s, SEARCH_PIXEL_MM, SEARCH_PIXEL_MM, model.top_deg).slim())
    ranked.sort(key=lambda a: a.score)
    forced = orient is not None
    finalists = []
    if orient is None:
        b = None
        for i, cand in enumerate(ranked[:FINALISTS]):            # the coarse slicing misses small islands (8 Nov: a 71° tilt
            say(f"slicing finalist {i + 1}/{min(FINALISTS, len(ranked))} at the printer's layer")    # won at 0.1 mm, and
            finalists.append(analyse(part, classes, cand.b, s, FINAL_PIXEL_MM, s["print_layer_mm"], model.top_deg))  # had one at 0.05)
        final = min(finalists, key=lambda a: a.score)
        for f in finalists:
            if f is not final:
                f.slim()
    elif isinstance(orient, int):
        if not 1 <= orient <= len(ranked):
            raise ValueError(f"--orient {orient}: the search ranked {len(ranked)} orientations")
        b = ranked[orient - 1].b
    elif len(orient) == 2:
        b = direction_for(float(orient[0]), float(orient[1]), model.top_deg)
    else:
        b = np.asarray(orient, float) / np.linalg.norm(orient)
    if b is not None:
        say("slicing the chosen orientation at the printer's layer")
        final = analyse(part, classes, b, s, FINAL_PIXEL_MM, s["print_layer_mm"], model.top_deg)
    cure = s["print_cure_through_mm"]
    cure_check = None
    if cure > 0:
        say(f"thinning the vat-facing surfaces by the cure-through depth ({cure:g} mm)")
        before = float(part.volume)
        part, classes, removed, comp_bodies = compensate_cure_through(part, classes, final.b, cure)
        final = analyse(part, classes, final.b, s, FINAL_PIXEL_MM, s["print_layer_mm"], model.top_deg)
        cure_check = gate.Check("cure-through compensated", comp_bodies == 1,
                                f"vat-facing surfaces moved {cure:g} mm into the part ({removed:.2f} mm³, {100 * removed / before:.1f} % "
                                f"of it, for the resin to cure back)" if comp_bodies == 1 else
                                f"a compensation of {cure:g} mm cuts the part into {comp_bodies} pieces: something is thinner than "
                                f"that along the build direction - another orientation, or a smaller depth")
    say("placing supports")
    supports, misses = place_supports(final, part, classes, s)
    cover = coverage(final, supports, s)
    lift = s["support_lift_mm"] + s["raft_thickness_mm"]
    import trimesh
    V = np.asarray(part.vertices) @ final.R.T
    V[:, 2] -= final.z_shift
    part_pr = trimesh.Trimesh(V, np.asarray(part.faces), process=False)
    raft = raft_mesh(supports, s)
    say(f"joining {len(supports)} supports and the raft to the part")
    checks = []
    files = {}
    bodies = 0
    try:
        whole, bodies = assemble(part_pr, supports, raft, s)
        whole.apply_translation([0.0, 0.0, lift])
    except ValueError as e:
        whole = None
        checks.append(gate.Check("one body", False, str(e)))
    if whole is not None:
        checks.append(gate.Check("one body", bodies == 1 and whole.is_watertight,
                                 f"{bodies} bod{'y' if bodies == 1 else 'ies'}, watertight {whole.is_watertight}, {len(whole.faces):,} triangles"))
        kept = float(whole.volume) - float(part_pr.volume)
        checks.append(gate.Check("part kept whole", kept >= -1e-3 * float(part_pr.volume),
                                 f"{float(whole.volume):.2f} mm³ in all, the part {float(part_pr.volume):.2f} (+{kept:.2f} supports and raft)"))
        zmin = float(whole.bounds[0][2])
        checks.append(gate.Check("on the plate", abs(zmin) < 1e-3 and raft is not None,
                                 f"the raft's underside at z {zmin:.3f}, the part's lowest point {lift:.2f} above it"
                                 if raft is not None else "nothing stands on the raft: the part's lowest point has no support"))
    if cure_check is not None:
        checks.append(cure_check)
    on_plain = all(SUPPORTABLE[sp.cls] and (sp.foot_cls is None or SUPPORTABLE[sp.foot_cls]) for sp in supports)
    apart = min((math.dist((p.x, p.y, p.z_top), (q.x, q.y, q.z_top)) for i, p in enumerate(supports) for q in supports[i + 1:]
                 if not (p.island or q.island)), default=math.inf)
    least = s["support_min_spacing_mm"]
    checks.append(gate.Check("contacts spread", apart >= 0.9 * least,       # (a tip sits a contact depth off the point picked)
                             (f"no two contacts nearer than {apart:.2f} mm ({least:g} at least: nearer, resin bridges the tips and "
                              f"cures into a blob)") if math.isfinite(apart) else "fewer than two contacts"))
    checks.append(gate.Check("contacts on plain metal", on_plain, f"{len(supports)} contacts, every one on a polished face or the bore"
                             if on_plain else "a contact on a feature"))
    z_first = min((sp.z_top for sp in supports), default=math.inf)        # the contacts as placed, not the search's estimate
    final.z_first_mm, final.start_islands = z_first, start_islands(final.feature_islands, z_first)
    final.terms["start"] = W_START * start_gap_layers(z_first, s)
    final.score = float(sum(final.terms.values()))
    gap = s["print_start_gap_mm"]
    if not supports:
        start_detail = "no support holds the part at all"
    elif z_first > gap:
        start_detail = (f"the first contact only {z_first:.2f} mm above the part's lowest point ({z_first / s['print_layer_mm']:.0f} layers, "
                        f"{gap:g} mm allowed): the part prints on nothing but the film until then and is lost"
                        + (" - on the film before it: " + "; ".join(_where_text(final, isl["lowest"], scale) for isl in final.start_islands[:4])
                           if final.start_islands else ""))
    else:
        start_detail = f"the first contact {z_first:.2f} mm above the part's lowest point ({gap:g} allowed)" + (
            f"; {len(final.start_islands)} feature island(s) cure on the film a layer before it" if final.start_islands else "")
    checks.append(gate.Check("starts on its supports", bool(supports) and z_first <= gap, start_detail))
    worst, at = layers_hold(final, supports, s)
    held = [sp for sp in supports if sp.hold]
    per = s["support_hold_area_mm2"]
    checks.append(gate.Check("layers held", worst <= per + 1e-6,
                             f"no layer hangs on more than {worst:.1f} mm² per contact engaged under it ({per:g} allowed)"
                             + (f"; {len(held)} contact{'s' if len(held) != 1 else ''} added for that, the highest {max(sp.z_top for sp in held):.2f} mm up"
                                if held else "")
                             if worst <= per + 1e-6 else
                             f"the layer {at:.2f} mm up hangs on {worst:.1f} mm² per contact ({per:g} allowed) and no more overhang below it "
                             f"takes a contact" + (f"; {len(held)} added" if held else ""), hard=False))
    lost = cover["islands_lost"]
    checks.append(gate.Check("islands held", not lost, "every island on plain metal has a support" if not lost
                             else f"{len(lost)} island(s) on plain metal no support could reach"))
    fi = final.feature_islands
    checks.append(gate.Check("feature islands", not fi, "none" if not fi else
                             f"{len(fi)} island(s) on features print unsupported (they fail or come out short): "
                             + "; ".join(_where_text(final, isl["lowest"], scale) for isl in fi[:4]), hard=False))
    fo = len(cover["feature_uncovered"]) * FINAL_PIXEL_MM ** 2
    checks.append(gate.Check("feature overhang", fo < 0.05, f"{fo:.2f} mm² of feature overhang no contact covers", hard=False))
    so = len(cover["supportable_uncovered"]) * FINAL_PIXEL_MM ** 2
    checks.append(gate.Check("plain overhang reached", so < 0.5, f"{so:.2f} mm² of plain overhang no support could reach"
                             + (f" ({len(misses)} contacts refused: {misses[0][1]}, ...)" if misses else ""), hard=False))
    res = PrepResult(stem, stl, model, s, ranked, final, supports, misses, cover, checks, files, area, metal, scale, warnings,
                     forced=forced, bodies=bodies, part_volume_mm3=part_volume, part_extents_mm=part_extents, finalists=finalists)
    res._lift = lift
    if specks:
        res.warnings.append(f"{specks} degenerate speck(s) of the mesher dropped from the part")
    if part.metadata.get("collapsed"):
        res.warnings.append(f"{part.metadata['collapsed']} sliver triangle(s) under {10 ** -HEAL_DIGITS:g} mm collapsed before the part was rotated")
    suffix = f".supported_{metal}.stl" if metal else ".supported.stl"
    if whole is not None:
        path = out_dir / f"{stem}{suffix}"
        whole.export(str(path))
        files["print file"] = path
        say("reading the print file back")
        back = trimesh.load(str(path), force="mesh")                 # what the slicer gets: float32, vertices merged
        sound = bool(back.is_watertight) and int(back.body_count) == 1
        checks.insert(1, gate.Check("file reads back sound", sound, f"{len(back.faces):,} triangles, watertight {back.is_watertight}, "
                                    f"{int(back.body_count)} bod{'y' if int(back.body_count) == 1 else 'ies'}"))
    if picture:
        say("drawing the preview")
        try:
            files["preview"] = preview(res, part_pr, classes, supports, raft, lift, out_dir / f"{stem}.prep.png")
        except Exception as e:                                          # a picture never fails the job
            res.warnings.append(f"no preview: {type(e).__name__}: {e}")
    res.seconds = time.time() - t0
    report = out_dir / f"{stem}.prep.json"
    files["report"] = report
    report.write_text(json.dumps(res.to_dict(), indent=2, default=str), encoding="utf-8")
    return res


def _where_text(an: Analysis, idx, scale: float) -> str:
    P = an.to_ring(an.point([idx]))[0] / scale
    return f"θ {math.degrees(math.atan2(P[1], P[0])):+.0f}° r {math.hypot(P[0], P[1]):.2f} z {P[2]:+.2f}"


# ============================================================================ the picture
CLASS_RGB = np.array([[198, 199, 204], [128, 156, 204], [222, 172, 92], [178, 142, 206]], np.uint8)
SUPPORT_RGB = (62, 160, 148)
RAFT_RGB = (118, 124, 130)


def preview(res: PrepResult, part_pr, classes, supports, raft, lift, path: Path) -> Path:
    """The supported part three-quarter and front, and the runners-up as thumbnails with their trouble spots."""
    import trimesh
    from PIL import Image, ImageDraw, ImageFont
    part = part_pr.copy()
    part.apply_translation([0, 0, lift])
    sups = [support_mesh(sp, res.settings) for sp in supports]
    for m in sups:
        m.apply_translation([0, 0, lift])
    meshes = [part] + ([trimesh.util.concatenate(sups)] if sups else [])
    cols = [CLASS_RGB[np.asarray(classes)]] + ([SUPPORT_RGB] if sups else [])
    if raft is not None:
        r = raft.copy()
        r.apply_translation([0, 0, lift])
        meshes.append(r)
        cols.append(RAFT_RGB)
    big = 760
    a, _ = raster.render(meshes, cols, view=(0.55, 0.72, -0.42), size_px=big)
    f, _ = raster.render(meshes, cols, view=(0.0, 1.0, -0.12), size_px=big)
    try:
        font = ImageFont.load_default(size=17)
        small = ImageFont.load_default(size=14)
    except TypeError:                                                  # an older Pillow
        font = small = ImageFont.load_default()
    W = 2 * big + 60
    thumbs = res.ranked[:4]
    tw = (W - 50) // 4
    H = 70 + max(a.shape[0], f.shape[0]) + 40 + (tw + 60 if thumbs else 0)
    img = Image.new("RGB", (W, H), (244, 244, 241))
    d = ImageDraw.Draw(img)
    d.text((20, 14), f"{res.stem}", fill=(30, 30, 30), font=font)
    d.text((20, 38), f"{res.headline()}  -  {res.status.upper()}", fill=(60, 60, 60), font=small)
    img.paste(Image.fromarray(a), (20, 70))
    img.paste(Image.fromarray(f), (40 + big, 70))
    y0 = 70 + max(a.shape[0], f.shape[0]) + 10
    key = [("polished face", CLASS_RGB[0]), ("bore", CLASS_RGB[1]), ("feature", CLASS_RGB[2]), ("kept clear", CLASS_RGB[3]),
           ("supports", SUPPORT_RGB), ("unsupported", (210, 40, 40))]
    x = 20
    for name, c in key:
        d.rectangle([x, y0 + 4, x + 14, y0 + 18], fill=tuple(int(v) for v in c))
        d.text((x + 20, y0 + 2), name, fill=(40, 40, 40), font=small)
        x += 30 + int(d.textlength(name, font=small))
    y1 = y0 + 34
    for i, an in enumerate(thumbs):
        m = reframed(part_pr, res.chosen, an)
        t_img, proj = raster.render([m], [CLASS_RGB[np.asarray(classes)]], view=(0.55, 0.72, -0.42), size_px=tw - 10)
        timg = Image.fromarray(t_img)
        td = ImageDraw.Draw(timg)
        bad = an.trouble_points()
        if len(bad):
            for cx, cy in raster.project(bad, proj):
                td.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=(210, 40, 40))
        xx = 20 + i * (tw + 3)
        img.paste(timg, (xx, y1))
        film = an.terms.get("start", 0.0) > 0
        d.text((xx, y1 + timg.size[1] + 4), f"{i + 1}. {describe(an.b, res.model.top_deg)}" + (" - STARTS ON THE FILM" if film else ""),
               fill=(190, 40, 40) if film else (30, 30, 30), font=small)
        d.text((xx, y1 + timg.size[1] + 22), f"score {an.score:.1f}: ~{an.contacts_est['polish'] + an.contacts_est['bore']} contacts, "
               f"{len(an.feature_islands)} feat. islands", fill=(80, 80, 80), font=small)
    path = Path(path)
    img.save(str(path))
    return path


def reframed(part_printer, frm: Analysis, to: Analysis):
    """The part, given in one analysis's frame, in another's (its lowest point at z = 0, as that analysis sliced it)."""
    import trimesh
    ring = np.asarray(part_printer.vertices).copy()
    ring[:, 2] += frm.z_shift
    ring = ring @ frm.R                                          # back to the ring frame (scaled)
    V = ring @ to.R.T
    V[:, 2] -= to.z_shift
    return trimesh.Trimesh(V, np.asarray(part_printer.faces), process=False)
