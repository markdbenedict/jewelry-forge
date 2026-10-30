"""The solitaire: a prong head on a profiled band with cathedral shoulders - the Phase 2 gate.

Ring frame (nTop convention): ring axis Z, band centred on the origin, the head on +X.

    band       the profiled band (ring_band_profile's eleven numbers)
    arch       the cathedral: a gothic arch each side. The +y shoulder is the band's own section
               swept round a circle centred at c+ = -t(cos φ, sin φ) of radius ro + t: tangent to
               the band's outer surface at +φ (`shoulder_deg` from the top) and through the crest
               just under the girdle; the -y shoulder mirrors it about c- = -t(cos φ, -sin φ). At
               the tangent ray the arch's section IS the band's, so the band flows into the arch
               (no step, no crease); arch+ ∩ arch- ∩ the wedge |angle| <= φ + 2° minus a cylinder
               at mid-wall (the arch never reaches the bore), united with the band BEFORE the band's
               edge-round offsets, so one rounding runs over band and arch alike
    engraving  optional text inside (or outside) the shank, centred opposite the head: ring_features'
               pipeline (Python writes the text STL, Remap Cylindrical wraps it), then turned 180° about
               the ring axis
    milgrain   bead rows along both edges of each arch (the band's milgrain conventions: centre
               0.15 radii inside the edge corner, 2.2 radii apart), from the tangent point up to
               where the head's envelope + 0.2 mm begins; polar arrays about the arch centres
    seat       the stone_seat cutter (stone + straight drop-in path + clearance), placed with the
               head, subtracted from band + shoulders: the pavilion sits down into the metal
    head       the prong_head block (round), the outline_head block (pear and other fancy
               outlines: prongs on the outline, rails following the pavilion) or the bezel_head
               block (a wall and cup round any outline), placed: a quarter-turn about the line
               through (Pivot X, *, Pivot Z) parallel to +Y takes the head's +Z to +X and its
               origin (the girdle centre) to (Girdle Radius, 0, 0)

Placement: the culet sits `finger_clear_mm` (default the marginal wall floor + 0.1) above the
bore, so there is metal under the stone and the finger never touches it; the head's feet then
sit inside the shank. Everything here is Python arithmetic; `ring_mesh(inputs)` rebuilds the
same ring from the notebook's input numbers (trimesh + manifold3d) for the gate.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import band as bandmod, gems, geom, heads, tables

WALL_FLOOR = tables.FLOORS["wall_marginal"]
HEAD_ANGLE_DEG = 90.0
WEDGE_EXTRA_DEG = 2.0           # the arch is cut 2° past its tangent ray (it departs from the band by < 0.01 mm there)
BEAD_CORNER_INSET = 0.15        # as features.py: bead centre this many radii inside the edge corner
BEAD_PITCH = 2.2                # centre to centre, in bead radii
BEAD_HEAD_GAP = 0.2             # beads stop this far (surface to surface) from the head's envelope
MIN_BEAD_RADIUS = tables.FLOORS["bead_dia"] / 2


@dataclass
class SolitaireSpec:
    band: bandmod.BandSpec
    head: "heads.HeadSpec | heads.OutlineHeadSpec"
    finger_clear_mm: float | None = None    # metal between the bore and the culet
    shoulder_deg: float = 45.0              # where each shoulder leaves the band, from the top
    crown_below_girdle_mm: float = 0.6      # the arch's crest, below the girdle's underside
    milgrain: bool = True                   # bead rows along the arch edges
    bead_radius_mm: float = 0.3
    bead_pitch: float = BEAD_PITCH
    text: str | None = None                 # engraving
    engrave_side: str = "inside"
    engrave_height_mm: float | None = None
    engrave_depth_mm: float = 0.3
    font: dict | None = None
    shank_blend_mm: float | None = None     # nTop blend radius where the head meets the shank; default tables, 0 = sharp
    _cache: dict = field(default_factory=dict, init=False, repr=False, compare=False)

    @property
    def shank_blend(self) -> float:
        return tables.SETTINGS["blend_radius_mm"] if self.shank_blend_mm is None else float(self.shank_blend_mm)

    @property
    def bead_head_gap(self) -> float:
        """Beads stop this far from the head: at least BEAD_HEAD_GAP, and wider than the shank
        blend would bridge (a smooth union fills gaps narrower than about half its radius)."""
        return max(BEAD_HEAD_GAP, 0.8 * self.shank_blend)

    # ---- head kind -----------------------------------------------------------------------
    @property
    def kind(self) -> str:
        """round (prong_head), outline (outline_head) or bezel (bezel_head)."""
        if isinstance(self.head, heads.BezelSpec):
            return "bezel"
        return "outline" if isinstance(self.head, heads.OutlineHeadSpec) else "round"

    @property
    def outline(self) -> bool:
        return self.kind == "outline"

    @property
    def bezel(self) -> bool:
        return self.kind == "bezel"

    @property
    def floored(self) -> bool:
        """Heads placed by a floor under them (outline, bezel) rather than by raised feet (round)."""
        return self.kind != "round"

    @property
    def prong_count(self) -> int:
        return self.head.count if self.floored else self.head.prongs

    @property
    def catalog_name(self) -> str:
        return {"round": "solitaire", "outline": "solitaire_outline", "bezel": "solitaire_bezel"}[self.kind]

    @property
    def engraving(self):
        """The band-engraving helper (features.RingSpec) for this band and text: geometry, the STL,
        the pocket check. Kept, so the text info written per run stays with it."""
        if "eng" not in self._cache:
            from . import features
            self._cache["eng"] = features.RingSpec(self.band, text=self.text, engrave_side=self.engrave_side,
                                                   engrave_height_mm=self.engrave_height_mm,
                                                   engrave_depth_mm=self.engrave_depth_mm, font=self.font)
        return self._cache["eng"]

    @property
    def has_engraving(self) -> bool:
        return bool(self.text)

    # ---- placement ------------------------------------------------------------------------
    @property
    def placed_head(self):
        """The head as it goes on this band: nothing of it below 0.2 mm above the bore (the
        standalone head drops its feet below the culet; on a ring with 0.6 mm under the culet that
        would break into the finger hole). Round: the feet and lower rail raised; outline: the
        head's floor set there (feet and lower rail move up the pavilion); bezel: the cup carried
        down to that floor, so it stands in the band."""
        from dataclasses import replace
        if self.floored:
            _, pav = self.head.stone.heights
            floor = round(-(self.head.stone.girdle / 2 + pav + self.finger_clear - 0.2), 4)
            if self.bezel:                                   # the cup runs down into the band, to the floor
                return replace(self.head, floor_z=floor, bottom_frac=0.0)
            return replace(self.head, floor_z=floor)
        drop = self.finger_clear - (self.head.rail_rho + 0.2)
        return replace(self.head, base_drop_mm=round(drop, 4))

    @property
    def finger_clear(self) -> float:
        return WALL_FLOOR + 0.1 if self.finger_clear_mm is None else float(self.finger_clear_mm)

    @property
    def girdle_radius(self) -> float:
        """Ring-frame radius of the girdle's mid-plane (the head's origin)."""
        s = self.head.stone
        _, pav = s.heights
        return self.band.bore_radius_mm + self.finger_clear + pav + s.girdle / 2

    @property
    def pivot(self) -> tuple[float, float]:
        """(x, z) of the rotation axis: a +90° turn about it moves the origin to (girdle radius, 0, 0)."""
        R = self.girdle_radius
        return R / 2, -R / 2

    @property
    def crest_radius(self) -> float:
        return self.girdle_radius - self.head.stone.girdle / 2 - self.crown_below_girdle_mm

    def arch(self) -> dict:
        """The gothic arch: t (centre offset), R (arch outer radius), the +y centre, the dome torus
        ring radius around it, the wedge half-angle, the mid-wall cut radius and the radius the
        independent model hollows the arch to (any value between `inner_min` and `inner_max`)."""
        b = self.band
        ro, phi, xt = b.outer_radius_mm, math.radians(self.shoulder_deg), self.crest_radius
        den = 2 * (ro - xt * math.cos(phi))
        t = (xt ** 2 - ro ** 2) / den if den > 1e-6 else float("inf")
        dr, dt = b.dome_torus
        cx, cy = -t * math.cos(phi), -t * math.sin(phi)
        r_cut = b.bore_radius_at(b.width_mm / 2) + b.edge_thickness_mm / 2
        inner_max = math.hypot(t, r_cut) - 0.5                       # nearest wedge point outside the cut
        inner_min = dr + t - math.sqrt(max(dt ** 2 - (b.width_mm / 2) ** 2, 0.0)) + 0.3   # inside the dome tube
        return {"t": t, "R": ro + t, "cx": cx, "cy": cy, "dome_ring": dr + t, "dome_tube": dt,
                "wedge_deg": self.shoulder_deg + WEDGE_EXTRA_DEG, "r_cut": r_cut,
                "inner": (inner_min + inner_max) / 2, "inner_min": inner_min, "inner_max": inner_max,
                "crest": xt, "rise": xt - ro}

    def _head_envelope(self, x: float) -> float:
        """Radius (about the ring's X axis, the head's axis) the placed head and its seat occupy at
        ring x: prongs (as if a full cone), rails, the stone + clearance and its drop-in path."""
        h = self.placed_head
        lay, s = h.layout(), h.stone
        z = x - self.girdle_radius                                   # the head's own z
        env = 0.0
        if lay["z_base"] - h.rho <= z <= lay["z_tip"] + h.rho:
            zz = min(max(z, lay["z_base"]), lay["z_tip"])
            f = (zz - lay["z_base"]) / (lay["z_tip"] - lay["z_base"])
            env = max(env, lay["r_base"] + f * (lay["r_tip"] - lay["r_base"]) + h.rho)
        for zr, rr in (lay["rail_upper"], lay["rail_lower"]):
            if abs(z - zr) < h.rail_rho:
                env = max(env, rr + math.sqrt(h.rail_rho ** 2 - (z - zr) ** 2))
        _, pav = s.heights
        Rg, g, c = s.width / 2, s.girdle, h.clearance
        if -g / 2 - pav - c <= z < -g / 2:
            env = max(env, Rg * (1 + (z + g / 2) / pav) + c)
        elif z >= -g / 2:
            env = max(env, Rg + c)
        return env

    def _head_surface(self):
        """(placed design head ∪ placed seat cutter) for the beads' clearance: a KD-tree over
        points sampled on both surfaces and the meshes (for inside tests). Outline heads only."""
        if "head_surface" not in self._cache:
            import numpy as np
            import trimesh
            from scipy.spatial import cKDTree
            h = self.placed_head
            place = geom.rotation_about_y(HEAD_ANGLE_DEG, [self.pivot[0], 0.0, self.pivot[1]])
            head = (heads.outline_design_mesh(h) if self.outline else h.design_mesh()).copy()
            head.apply_transform(place)
            cutter = geom.offset_convex(h.seat.envelope(), h.clearance).copy()
            cutter.apply_transform(place)
            pts = np.vstack([trimesh.sample.sample_surface_even(m, 60000, seed=1)[0] for m in (head, cutter)])
            self._cache["head_surface"] = (cKDTree(pts), head, cutter)
        return self._cache["head_surface"]

    def _bead_clear(self, x: float, y: float, z: float) -> bool:
        rho = self.bead_radius_mm
        if not self.floored:
            return math.hypot(y, z) - rho >= self._head_envelope(x) + self.bead_head_gap
        tree, head, cutter = self._head_surface()
        p = [[x, y, z]]
        if cutter.contains(p)[0] or head.contains(p)[0]:
            return False
        return float(tree.query(p)[0][0]) >= rho + self.bead_head_gap

    def beads(self) -> dict:
        """The +y arch's bead row: angles (deg, about c+, from the tangent point towards the crest),
        radius, the row radius about c+, z, the spacing (deg); the -y row mirrors it."""
        if "beads" in self._cache:
            return self._cache["beads"]
        a, b, rho = self.arch(), self.band, self.bead_radius_mm
        r_row = b.outer_radius_at(b.width_mm / 2) + a["t"] - BEAD_CORNER_INSET * rho
        z = b.width_mm / 2 - BEAD_CORNER_INSET * rho
        step = math.degrees(self.bead_pitch * rho / r_row)
        angles = []
        psi = self.shoulder_deg
        while psi > 0 and len(angles) < 400:
            x = a["cx"] + r_row * math.cos(math.radians(psi))
            y = a["cy"] + r_row * math.sin(math.radians(psi))
            # both edges and both arches must clear (a pear is not symmetric along the finger)
            if not all(self._bead_clear(x, sy * y, sz * z) for sy in (1, -1) for sz in (1, -1)):
                break
            angles.append(psi)
            psi -= step
        self._cache["beads"] = {"radius": rho, "row_radius": r_row, "z": z, "angles": angles, "spacing": step}
        return self._cache["beads"]

    def bead_centres(self) -> list[tuple[float, float, float, int]]:
        """Every arch bead (x, y, z, side) in the ring frame; side +1 about c+, -1 about c-."""
        if not self.milgrain:
            return []
        a, bd = self.arch(), self.beads()
        out = []
        for psi in bd["angles"]:
            r = math.radians(psi)
            x, y = a["cx"] + bd["row_radius"] * math.cos(r), a["cy"] + bd["row_radius"] * math.sin(r)
            for z in (bd["z"], -bd["z"]):
                out.append((x, y, z, 1))
                out.append((x, -y, z, -1))
        return out

    # ---- the notebook's numbers ----------------------------------------------------------------
    def notebook_inputs(self, seat_path: str, output_path: str | None = None, *, prongs_path: str = "",
                        engraving_path: str = "", windows_path: str = "") -> dict:
        ins = self.band.notebook_inputs("")
        ins.pop("Output Path")
        if self.outline:                                              # Seat Path, Clearance, Prongs Path + the rail numbers
            head = self.placed_head.notebook_inputs(seat_path, prongs_path)
        elif self.bezel:                                              # Seat Path, Clearance, Windows Path, Wall, Bezel Bottom/Top
            head = self.placed_head.notebook_inputs(seat_path, windows_path)
        else:                                                         # Seat Path, Clearance + the 14 head numbers
            head = self.placed_head.notebook_inputs(seat_path)
        head["Head Blend"] = head.pop("Blend Radius")                 # the block's own blend, named for this notebook
        ins.update(head)
        px, pz = self.pivot
        a = self.arch()
        ins.update({"Pivot X": round(px, 4), "Pivot Z": round(pz, 4),
                    "Arch Centre X": round(a["cx"], 4), "Arch Centre Y": round(a["cy"], 4),
                    "Arch Centre Y Minus": round(-a["cy"], 4), "Arch Radius": round(a["R"], 4),
                    "Arch Dome Ring Radius": round(a["dome_ring"], 4), "Arch Cut Radius": round(a["r_cut"], 4),
                    "Wedge Angle": round(a["wedge_deg"], 4), "Wedge Angle Minus": round(-a["wedge_deg"], 4)})
        ins.update(self.bead_inputs())
        ins.update({"Engraving Path": engraving_path, "Engraving Wrap Length": round(self.engraving_wrap_length, 4),
                    "Shank Blend": round(self.shank_blend, 4)})
        if output_path is not None:
            ins["Output Path"] = output_path
        return ins

    @property
    def engraving_wrap_length(self) -> float:
        from . import engrave
        eng = self.engraving
        r = eng.engrave_geometry()["wrap_radius"] if self.has_engraving else self.band.bore_radius_mm
        return engrave.wrap_length_mm(r)

    def write_engraving(self, path: Path) -> dict:
        """The text STL (or the no-op speck far outside the ring) the notebook wraps and subtracts."""
        from . import engrave
        if self.has_engraving:
            return self.engraving.write_engraving(Path(path))
        return engrave.write_engraving(Path(path), None, 1.0, 0.3, self.band.bore_radius_mm, "inside")

    def engraving_mesh(self):
        """The same STL's mesh, in memory (the independent ring)."""
        from . import engrave
        if not self.has_engraving:
            return engrave.dummy_mesh(self.band.bore_radius_mm)
        g = self.engraving.engrave_geometry()
        return engrave.text_mesh(self.text, g["height"], self.engrave_depth_mm, g["radius"], g["side"], font=self.font)

    def bead_inputs(self) -> dict:
        """Start beads for the two polar arrays (each runs counter-clockwise about its arch centre):
        +y starts at the head end, -y at the band end. Milgrain off: one 0.05 mm bead buried in the
        shank opposite the head (it cannot change the ring)."""
        a, bd = self.arch(), self.beads()
        if not self.milgrain or not bd["angles"]:
            hidden = -(self.band.bore_radius_mm + self.band.thickness_mm / 2)
            return {"Bead Radius": 0.05, "Bead Z": 0.0, "Bead Z Minus": 0.0, "Bead Spacing": 1.0, "Bead Count": 1,
                    "Bead Start X": round(hidden, 4), "Bead Start Y": 0.0,
                    "Bead Start X Minus": round(hidden, 4), "Bead Start Y Minus": 0.0}
        last = math.radians(bd["angles"][-1])
        x = a["cx"] + bd["row_radius"] * math.cos(last)
        y = a["cy"] + bd["row_radius"] * math.sin(last)
        first = math.radians(bd["angles"][0])                        # the band end; the -y row starts at its mirror
        xm = a["cx"] + bd["row_radius"] * math.cos(first)
        ym = -(a["cy"] + bd["row_radius"] * math.sin(first))
        return {"Bead Radius": round(bd["radius"], 4), "Bead Z": round(bd["z"], 4), "Bead Z Minus": round(-bd["z"], 4),
                "Bead Spacing": round(bd["spacing"], 6), "Bead Count": len(bd["angles"]),
                "Bead Start X": round(x, 4), "Bead Start Y": round(y, 4),
                "Bead Start X Minus": round(xm, 4), "Bead Start Y Minus": round(ym, 4)}

    def design(self) -> dict:
        return {"band": self.band.design(), "head": self.placed_head.design(), "finger_clear_mm": self.finger_clear,
                "shoulder_deg": self.shoulder_deg, "crown_below_girdle_mm": self.crown_below_girdle_mm,
                "arch": "gothic-tangent", "milgrain": self.milgrain,
                "bead_radius_mm": self.bead_radius_mm if self.milgrain else None,
                "bead_pitch": self.bead_pitch if self.milgrain else None,
                "engraving": ({"text": self.text, "side": self.engrave_side, "height_mm": self.engraving.engrave_geometry()["height"],
                               "depth_mm": self.engrave_depth_mm, "font": self.font} if self.has_engraving else None),
                "shank_blend_mm": self.shank_blend}

    def blend_volume_mm3(self) -> float:
        """What the blends add (see blend_estimate): the head's own junctions where exposed, the
        head's rounded edges against, and the head-to-shank union."""
        if "blend_volume" not in self._cache:
            self._cache["blend_volume"] = blend_estimate(self.notebook_inputs(""), self.head.seat.envelope(),
                                                         prongs=self.placed_head.prongs_mesh() if self.outline else None,
                                                         windows=self.placed_head.windows_mesh() if self.bezel else None)
        return self._cache["blend_volume"]

    @property
    def stem(self) -> str:
        from . import runs
        b, s = self.band, self.head.stone
        setting = "bezel" if self.bezel else f"{self.prong_count}prong"
        return (f"solitaire_{b.profile}_{b.label}_{setting}_{s.stem[len('stone_'):]}_"
                f"{runs.spec_id(self.design())}")

    # ---- checks on the design ---------------------------------------------------------------
    def validate(self) -> list[str]:
        p = self.band.validate() + self.placed_head.validate()
        if self.finger_clear < WALL_FLOOR:
            p.append(f"{self.finger_clear} mm of metal under the culet is below the wall floor {WALL_FLOOR} mm")
        if self.floored:
            low = self.girdle_radius + self.placed_head.lowest_z()
            if low > self.band.outer_radius_mm - 0.2:
                p.append(f"the head's lowest metal (r {low:.2f}) does not reach into the band (outer r "
                         f"{self.band.outer_radius_mm:.2f}): less finger clearance")
            if low < self.band.bore_radius_mm + 0.1:
                p.append(f"the head (r {low:.2f}) breaks into the bore")
        else:
            lay = self.placed_head.layout()
            feet = self.girdle_radius + lay["z_base"]
            if feet > self.band.outer_radius_mm - 0.2:
                p.append(f"the head's feet (r {feet:.2f}) do not reach into the band (outer r {self.band.outer_radius_mm:.2f}): "
                         f"less finger clearance or a deeper base")
            if feet - self.head.rail_rho < self.band.bore_radius_mm + 0.1:
                p.append(f"the lower rail (inner r {feet - self.head.rail_rho:.2f}) breaks into the bore")
        if self.has_engraving:
            p += [q for q in self.engraving.validate() if q not in p]
        p += heads.blend_problems(self.shank_blend, self.band.edge_thickness_mm)
        if not 30 <= self.shoulder_deg <= 75:
            p.append("shoulder angle outside 30-75°")
            return p
        a = self.arch()
        if a["rise"] < 0.3:
            p.append(f"the arch's crest (r {a['crest']:.2f}) barely rises above the band (r {self.band.outer_radius_mm:.2f})")
        if not math.isfinite(a["t"]) or a["t"] > 60:
            p.append(f"no tangent arch from {self.shoulder_deg:g}° reaches the crest: a larger shoulder angle")
        elif a["inner_min"] >= a["inner_max"]:
            p.append("the arch section cannot be hollowed clear of the wedge (independent model): a larger shoulder angle")
        if self.milgrain:
            bd = self.beads()
            if self.bead_radius_mm < MIN_BEAD_RADIUS:
                p.append(f"bead radius {self.bead_radius_mm} mm below the milgrain floor {MIN_BEAD_RADIUS} mm")
            if self.bead_pitch < 2.0:
                p.append("bead pitch below 2 radii: beads would merge")
            if len(bd["angles"]) < 3:
                p.append(f"only {len(bd['angles'])} beads fit on each arch edge before the head: smaller beads or a lower shoulder angle")
        return p

    def describe(self) -> str:
        a = self.arch()
        px, pz = self.pivot
        low = self.placed_head.lowest_z() if self.floored else self.placed_head.layout()["z_base"]
        return (f"{self.stem}\n  {self.band.describe()}\n  {self.placed_head.describe()}\n"
                f"  placement: girdle at r {self.girdle_radius:.3f}, culet {self.finger_clear} mm above the bore, "
                f"{'lowest metal' if self.floored else 'feet'} at r {self.girdle_radius + low:.3f}; "
                f"quarter-turn about (x {px:.3f}, z {pz:.3f}) ∥ Y\n"
                f"  arch: gothic, tangent to the band at ±{self.shoulder_deg:g}°, radius {a['R']:.3f} about "
                f"({a['cx']:.3f}, ±{-a['cy']:.3f}); crest at r {a['crest']:.3f} ({a['rise']:.2f} mm above the band)"
                + (f"\n  milgrain: {len(self.beads()['angles'])} beads of r {self.bead_radius_mm} mm per arch edge (x4), "
                   f"{self.beads()['spacing']:.3f}° apart" if self.milgrain else "\n  milgrain: off")
                + (f"\n  engraving: {self.text!r} {self.engrave_side}, {self.engraving.engrave_geometry()['height']:.2f} mm high, "
                   f"{self.engrave_depth_mm} mm deep, centred opposite the head" if self.has_engraving else "")
                + f"\n  blends: head {self.placed_head.blend:g} mm, head into shank {self.shank_blend:g} mm")


# ---- the independent ring ---------------------------------------------------------------------
def arch_mesh(v: dict, inner: float):
    """The cathedral arches from the notebook's numbers: arch+ ∩ arch- ∩ wedge - the mid-wall cylinder.
    Each arch is the band's outer section (dome torus, edge round) about its centre; `inner` hollows
    it (any radius clear of the wedge - nTop leaves the arch solid; the wedge and cut decide)."""
    import numpy as np
    import trimesh
    from shapely.geometry import Point, Polygon, box
    zb, zt, e = float(v["Z Bottom"]), float(v["Z Top"]), float(v.get("Edge Round", 0.0))
    R, dr, dt = float(v["Arch Radius"]), float(v["Arch Dome Ring Radius"]), float(v["Dome Tube Radius"])
    sec = box(inner, zb, R, zt).intersection(Point(dr, 0.0).buffer(dt, quad_segs=256))
    if e > 0:
        sec = sec.buffer(-e, quad_segs=16).buffer(e, quad_segs=16)
    parts = []
    for cy in (float(v["Arch Centre Y"]), float(v["Arch Centre Y Minus"])):
        m = geom.revolve_section(sec, sections=720)
        m.apply_translation([float(v["Arch Centre X"]), cy, 0.0])
        parts.append(m)
    w = math.radians(float(v["Wedge Angle"]))
    L = 40.0
    wedge = trimesh.creation.extrude_polygon(Polygon([(0, 0), (L * math.cos(w), -L * math.sin(w)), (L, 0),
                                                      (L * math.cos(w), L * math.sin(w))]), height=4 * (zt - zb) + 20)
    wedge.apply_translation([0, 0, -2 * (zt - zb) - 10])
    cut = trimesh.creation.cylinder(radius=float(v["Arch Cut Radius"]), height=40, sections=720)
    arch = trimesh.boolean.intersection(parts + [wedge], engine="manifold")
    return trimesh.boolean.difference([arch, cut], engine="manifold")


def bead_mesh(v: dict):
    """The four bead rows (or the one buried bead) from the notebook's numbers, as the polar arrays build them."""
    import trimesh
    rho, n, step = float(v["Bead Radius"]), int(v["Bead Count"]), math.radians(float(v["Bead Spacing"]))
    beads = []
    for (sx, sy), cy in (((float(v["Bead Start X"]), float(v["Bead Start Y"])), float(v["Arch Centre Y"])),
                         ((float(v["Bead Start X Minus"]), float(v["Bead Start Y Minus"])), float(v["Arch Centre Y Minus"]))):
        cx = float(v["Arch Centre X"])
        r0, a0 = math.hypot(sx - cx, sy - cy), math.atan2(sy - cy, sx - cx)
        for k in range(n):
            a = a0 + k * step
            for z in {float(v["Bead Z"]), float(v["Bead Z Minus"])}:
                beads.append(trimesh.creation.icosphere(subdivisions=3, radius=rho).apply_translation(
                    [cx + r0 * math.cos(a), cy + r0 * math.sin(a), z]))
    return trimesh.boolean.union(beads, engine="manifold") if len(beads) > 1 else beads[0]


ENGRAVING_TURN_DEG = 180.0       # the text is wrapped centred on +X (ring_features), then turned under the finger


def wrapped_engraving(v: dict, engraving):
    """The engraving body as the notebook makes it: Remap Cylindrical, then 180° about the ring axis."""
    import numpy as np
    import trimesh
    w = geom.remap_cylindrical(engraving, float(v["Engraving Wrap Length"]))
    w.apply_transform(trimesh.transformations.rotation_matrix(math.radians(ENGRAVING_TURN_DEG), [0, 0, 1]))
    return w


def ring_parts(v: dict, envelope, prongs=None, windows=None, beads: bool = True, cut_seat: bool = True,
               ops: geom.Booleans = geom.SHARP):
    """(shank, placed head, placement, placed seat cutter) from the notebook's numbers: the bodies
    the notebook's blended join unites and the cut that follows it. `prongs` / `windows`: the
    meshes the notebook's Prongs Path / Windows Path point at (read from those paths when not
    given). The head is built the way its block builds it (`ops` decides the blends)."""
    import trimesh
    t = math.hypot(float(v["Arch Centre X"]), float(v["Arch Centre Y"]))
    lo = float(v["Arch Dome Ring Radius"]) - math.sqrt(max(float(v["Dome Tube Radius"]) ** 2 - float(v["Z Top"]) ** 2, 0)) + 0.3
    inner = (lo + math.hypot(t, float(v["Arch Cut Radius"])) - 0.5) / 2     # midway between the bounds SolitaireSpec.arch() computes
    shank = ops.union([geom.band_mesh(v), arch_mesh(v, inner)] + ([bead_mesh(v)] if beads else []))
    kind = heads.head_kind(v)
    if kind == "outline":
        if prongs is None:
            prongs = trimesh.load(str(v["Prongs Path"]), force="mesh")
        head = heads.outline_head_mesh(v, envelope, prongs, cut_seat=cut_seat, ops=ops)
    elif kind == "bezel":
        if windows is None:
            windows = trimesh.load(str(v["Windows Path"]), force="mesh")
        head = heads.bezel_mesh(v, envelope, windows, cut_seat=cut_seat, ops=ops)
    else:
        head = heads.head_mesh(v, envelope, cut_seat=cut_seat, ops=ops)
    place = geom.rotation_about_y(HEAD_ANGLE_DEG, [float(v["Pivot X"]), 0.0, float(v["Pivot Z"])])
    head = head.copy()
    head.apply_transform(place)
    cutter = geom.offset_convex(envelope, float(v["Clearance"])).copy()
    cutter.apply_transform(place)
    return shank, head, place, cutter


def ring_mesh(v: dict, envelope, cut_seat: bool = True, beads: bool = True, prongs=None, engraving=None,
              engrave: bool = True, windows=None, ops: geom.Booleans = geom.SHARP):
    """The solitaire from the notebook's input numbers, in the notebook's order: shank ∪ placed
    head (blended in nTop by Shank Blend; `ops` decides), then the seat cutter and the engraving
    subtracted. `engraving`: the mesh Engraving Path points at (read from it when not given)."""
    import trimesh
    shank, head, place, cutter = ring_parts(v, envelope, prongs, windows, beads=beads, cut_seat=cut_seat, ops=ops)
    ring = ops.union([shank, head], float(v.get("Shank Blend", 0.0)))
    cuts = [cutter] if cut_seat else []
    if engrave and "Engraving Path" in v:
        if engraving is None:
            engraving = trimesh.load(str(v["Engraving Path"]), force="mesh")
        cuts.append(wrapped_engraving(v, engraving))
    return ops.clean(ops.difference(ring, cuts))


def blend_estimate(v: dict, envelope, prongs=None, windows=None) -> float:
    """What the ring's blends add (negative: remove), mm³, from the notebook's numbers: the head's
    own junctions where they are exposed (buried in the shank: already solid; inside the seat: cut
    away afterwards), its rounded edges against, plus the head-to-shank union."""
    hv = {k: v[k] for k in v if k not in ("Head Blend",)}
    hv["Blend Radius"] = v.get("Head Blend", 0.0)
    shank_blend = float(v.get("Shank Blend", 0.0))
    if float(hv["Blend Radius"]) <= 0 and shank_blend <= 0:
        return 0.0
    shank, head, place, cutter = ring_parts(v, envelope, prongs, windows)
    j = heads.blend_junctions(hv, envelope, prongs)
    exposed = {k: geom.exposed_segments(geom.transform_segments(seg, place), shank, cutter) for k, seg in j.items()}
    est = heads.blend_estimate(hv, envelope, prongs, junctions=exposed)
    if shank_blend > 0:
        est += geom.blend_volume_mm3(shank_blend, geom.segments_length(geom.exposed_segments(geom.junction_segments(shank, head), cutter)))
    return est


def design_mesh(spec: SolitaireSpec, ops: geom.Booleans = geom.SHARP):
    """The independent ring (sharp by default; cached per spec)."""
    key = "design_mesh" if ops is geom.SHARP else None
    if key is None or key not in spec._cache:
        prongs = spec.placed_head.prongs_mesh() if spec.outline else None
        windows = spec.placed_head.windows_mesh() if spec.bezel else None
        mesh = ring_mesh(spec.notebook_inputs(""), spec.head.seat.envelope(), prongs=prongs,
                         engraving=spec.engraving_mesh(), windows=windows, ops=ops)
        if key is None:
            return mesh
        spec._cache[key] = mesh
    return spec._cache[key]


# ---- the gate -----------------------------------------------------------------------------------
def check_solitaire(spec: SolitaireSpec, stl: Path, ntop_vol: float | None):
    """Closed, one shell; band walls (the half away from the head) and bore; the bore closed under
    the stone; the stone fits (ring ∩ stone ≈ 0), sits (ledges) and drops in - in the head's frame;
    extents and volume against the independent ring."""
    import numpy as np
    import trimesh
    from . import gate
    b = spec.band
    text_filter = spec.engraving.wall_ray_filter() if spec.has_engraving else None
    flip = np.array([-1.0, -1.0, 1.0])                                       # the text sits at -X: its filter works at +X

    def shank_rays(pts, n):                                                  # the shank away from the head
        keep = pts[:, 0] < -2.0
        return keep & text_filter(pts * flip, n * flip) if text_filter else keep
    rep = gate.check(stl, expect_volume=ntop_vol, wall_floor=min(WALL_FLOOR, 0.8 * b.edge_thickness_mm),
                     wall_ray_filter=shank_rays)
    ring = gate.load_mesh(stl)
    r = np.hypot(ring.vertices[:, 0], ring.vertices[:, 1])
    bore = 2 * float(r.min())
    rep.checks.append(gate.Check("bore", abs(bore - b.inner_diameter_mm) <= 0.05,
                                 f"Ø {bore:.3f} vs {b.inner_diameter_mm:.3f} mm (about the ring axis)"))
    hits, _, _ = ring.ray.intersects_location([[0.0, 0.0, 0.0]], [[1.0, 0.0, 0.0]], multiple_hits=False)
    first = float(np.linalg.norm(hits[0])) if len(hits) else float("inf")
    rep.checks.append(gate.Check("bore closed under the stone", abs(first - b.bore_radius_mm) <= 0.1,
                                 f"from the axis towards the head, metal starts at r {first:.3f} (bore r {b.bore_radius_mm:.3f})"))
    design = design_mesh(spec)
    d = np.array(rep.extents_mm) - np.array(design.extents)
    tol = max(0.1, 2 * spec.head.mesh_tolerance_mm)
    shrink = tol + spec.placed_head.blend          # a blended intersection rounds the head's outermost edges away
    rep.checks.append(gate.Check("extents", bool(np.all(d <= tol) and np.all(d >= -shrink)),
                                 " x ".join(f"{x:.2f}" for x in rep.extents_mm) + " vs design "
                                 + " x ".join(f"{x:.2f}" for x in design.extents) + f" mm (+{tol:.2f} / -{shrink:.2f})"))
    # the head's checks, in the head's own frame
    place = geom.rotation_about_y(HEAD_ANGLE_DEG, [spec.pivot[0], 0.0, spec.pivot[1]])
    local = ring.copy()
    local.apply_transform(np.linalg.inv(place))
    stone = spec.head.stone.mesh()
    inter = trimesh.boolean.intersection([local, stone], engine="manifold") if local.is_watertight else None
    overlap = float(inter.volume) if inter is not None and len(inter.faces) else (0.0 if inter is not None else float("nan"))
    allowed = 0.002 * stone.volume
    rep.checks.append(gate.Check("stone fits", overlap <= allowed, f"ring ∩ stone {overlap:.3f} mm³ (allowed {allowed:.3f})"))
    Rg, g = spec.head.stone.width / 2, spec.head.stone.girdle
    if spec.floored:
        under, over = heads.seat_regions(spec.head.stone, spec.head.clearance)
        ledges = heads.outline_count(local, -g / 2 - 0.3, under)
        above = heads.outline_count(local, g / 2 + 0.15, over)
    else:
        ledges = heads._inner_count(local, -g / 2 - 0.3, Rg - 0.1)
        above = heads._inner_count(local, g / 2 + 0.15, Rg + spec.head.clearance * 0.5)
    if spec.bezel:
        rep.checks.append(gate.Check("seated", ledges >= 1, f"{ledges} piece(s) of the cup under the girdle"))
    else:
        rep.checks.append(gate.Check("seat ledges", ledges >= spec.prong_count,
                                     f"{ledges} pieces reach under the girdle (expected >= {spec.prong_count})"))
    rep.checks.append(gate.Check("drop-in clear", above == 0, f"{above} pieces inside the girdle line above the girdle"))
    if spec.bezel:
        rep.checks.append(heads.bezel_wall_check(spec.placed_head, local))
    if spec.milgrain:
        rep.checks.append(milgrain_check(spec, ring))
    if spec.has_engraving:
        turned = ring.copy()
        turned.apply_transform(trimesh.transformations.rotation_matrix(math.pi, [0, 0, 1]))   # the text back to +X
        pocket = spec.engraving.engraving_pocket(turned)
        rep.checks.append(gate.Check("engraving", pocket["found"],
                                     f"{pocket['pocket_area_mm2']:.1f} mm² of pocket on the {pocket['side']} for "
                                     f"{pocket['text_area_mm2']:.1f} mm² of text, opposite the head"
                                     + (f"; {pocket['stray_area_mm2']:.1f} mm² stray" if pocket["stray_area_mm2"] > 0.05 else "")))
    from .band import blended_design_volume_check
    rep.checks.append(blended_design_volume_check(float(design.volume), spec.blend_volume_mm3(), ntop_vol, 3.0))
    return rep


def milgrain_check(spec: SolitaireSpec, ring):
    """Every arch bead is there: a ray from 3 bead radii outside each designed bead centre (along
    the edge corner's diagonal) must meet the bead's apex (2 radii in) - a bare arch edge is met a
    radius later. Missing milgrain changes the volume by ~1 %, inside the design-volume tolerance,
    so only this check catches it."""
    import numpy as np
    from . import gate
    a, rho = spec.arch(), spec.bead_radius_mm
    origins, dirs = [], []
    for x, y, z, side in spec.bead_centres():
        c = np.array([a["cx"], a["cy"] * side])
        radial = np.array([x, y]) - c
        radial /= np.linalg.norm(radial)
        n = np.array([radial[0], radial[1], np.sign(z)]) / math.sqrt(2)
        origins.append(np.array([x, y, z]) + 3 * rho * n)
        dirs.append(-n)
    if not origins:
        return gate.Check("arch milgrain", False, "the design has no beads", status=gate.INCOMPLETE)
    locs, idx, _ = ring.ray.intersects_location(np.array(origins), np.array(dirs), multiple_hits=False)
    hit = {int(i): float(np.linalg.norm(l - origins[i])) for l, i in zip(locs, idx)}
    tol = max(0.08, 2 * spec.head.mesh_tolerance_mm)
    missing = [i for i in range(len(origins)) if abs(hit.get(i, 1e9) - 2 * rho) > tol]
    return gate.Check("arch milgrain", not missing,
                      f"{len(origins) - len(missing)}/{len(origins)} beads where designed (apex within {tol:.2f} mm)"
                      + (f"; missing near {[tuple(round(float(q), 2) for q in origins[i][:2]) for i in missing[:4]]}" if missing else ""))


@dataclass
class SolitaireResult:
    spec: SolitaireSpec
    stl: Path
    run: object
    gate: object
    ntop_volume_mm3: float | None
    run_dir: Path
    run_id: str
    delivered: Path | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        from . import runs
        return runs.status_of(self.run.ok, self.gate)

    @property
    def ok(self) -> bool:
        from . import gate
        return self.status == gate.PASSED

    def text(self) -> str:
        lines = [self.spec.describe(), self.run.summary(), self.gate.text(), f"  status: {self.status.upper()}  run {self.run_dir}"]
        if self.delivered:
            lines.append(f"  delivered to {self.delivered}")
        return "\n".join(lines + [f"  note: {n}" for n in self.notes])


def build(spec: SolitaireSpec, out_dir: Path | None = None, *, notebook: Path | None = None,
          catalog_name: str | None = None, deliver: bool = False, deliver_project: str = "Solitaires",
          cast_metal: str | None = None) -> SolitaireResult:
    """solitaire.ntop (round, prong_head), solitaire_outline.ntop (fancy, outline_head) or
    solitaire_bezel.ntop (any stone, bezel_head), gated."""
    from . import catalog, config, ntopcl, runs
    problems = spec.validate()
    if problems:
        raise ValueError("; ".join(problems))
    cat = catalog.load(catalog_name or spec.catalog_name)
    nb = Path(notebook) if notebook else cat.notebook
    run_dir, run_id = runs.fresh_run_dir(Path(out_dir) if out_dir else config.out_dir() / "solitaire", spec.stem)
    envelope = run_dir / f"{spec.stem}.envelope.stl"
    spec.head.seat.envelope().export(str(envelope))
    prongs = run_dir / f"{spec.stem}.prongs.stl"
    if spec.outline:
        spec.placed_head.prongs_mesh().export(str(prongs))
    windows = run_dir / f"{spec.stem}.windows.stl"
    if spec.bezel:
        spec.placed_head.windows_mesh().export(str(windows))
    engraving = run_dir / f"{spec.stem}.engraving.stl"
    spec.write_engraving(engraving)
    stl = run_dir / f"{spec.stem}.stl"
    inputs = spec.notebook_inputs(str(envelope), str(stl), prongs_path=str(prongs) if spec.outline else "",
                                  engraving_path=str(engraving), windows_path=str(windows) if spec.bezel else "")
    started = time.time()
    run = ntopcl.run(nb, cat.build_inputs(inputs), run_dir, tag=spec.stem)
    try:
        runs.require_fresh(stl, started, "the exported ring")
    except FileNotFoundError as e:
        raise ntopcl.NtopclError(f"notebook reported success but {e}", run) from e
    entry = run.outputs.get(cat.output.get("name", "Volume"))
    ntop_vol = ntopcl.scalar_value(entry) if entry else None
    rep = check_solitaire(spec, stl, ntop_vol)
    from . import gate as _gate
    _gate.save(rep)
    res = SolitaireResult(spec, stl, run, rep, ntop_vol, run_dir, run_id)
    stone = spec.head.stone
    res.notes.append(f"stone {stone.carats():.2f} ct {stone.material}; metal " +
                     ", ".join(f"{k} {v:.2f} g" for k, v in tables.weights_g(rep.volume_mm3).items()))
    res.notes += spec.band.warnings()
    report = {"stem": spec.stem, "spec_id": runs.spec_id(spec.design()), "run_id": run_id, "status": res.status,
              "design": spec.design(), "inputs": inputs, "stl": str(stl),
              "ntop_volume_mm3": ntop_vol, "gate": rep.to_dict(), "notes": res.notes,
              "notebook": runs.notebook_identity(nb), "environment": runs.environment(ntopcl.version())}
    (run_dir / f"{spec.stem}.report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    if deliver and res.ok:
        res.delivered = runs.deliver(stl, run_dir, spec.stem, deliver_project, report, cast_metal=cast_metal)
    elif deliver:
        res.notes.append(f"not delivered: status {res.status}")
    return res
