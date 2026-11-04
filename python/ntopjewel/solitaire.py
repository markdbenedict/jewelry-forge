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
    artwork    optional panels on the band's faces (ntopjewel.artwork: leaf rows on the side faces, a
               scroll or vine on the outer face - the Seraphine Celtic ring), carved into the opened
               band before the arches and the head join it. Each panel's head end is held back past
               the arches' wedge, or (`cathedral=False`, the shoulders plain and the head standing on
               the band, as the reference ring) just clear of the head's reach along the ring and the
               shank blend; the band end is where the panel says
    knots      optional knot ornaments standing on the band's outer face on plain shoulders
               (ntopjewel.ornament: a trinity knot, wider than the band, between the head and the
               panels - the reference ring's), united with the carved band; placed just past the
               head unless `knot_at_deg` says where, the panels then held back past them
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

from . import artwork as artmod, band as bandmod, gems, geom, heads, ornament as ornmod, shank as shankmod, tables

WALL_FLOOR = tables.FLOORS["wall_marginal"]
HEAD_ANGLE_DEG = 90.0
KNOT_PAD_CLEAR_MM = 0.5          # a knot solitaire: the band's nose tip lies this far beyond the head's feet along the ring
PANEL_HEAD_CLEAR_MM = 0.5        # artwork on plain shoulders: a panel starts this far past the head's reach + the shank blend
PANEL_WEDGE_CLEAR_DEG = 1.0      # ... or this far past the arches' wedge
KNOT_HEAD_CLEAR_DEG = 0.5        # a shoulder knot begins this far past the head's clearance ...
PANEL_KNOT_CLEAR_DEG = 1.0       # ... and a panel this far past the knot
HEAD_ZONE_PAD_DEG = 5.0          # the bore under the head: the head's reach along the ring, plus this
BLEND_BORE_BULGE = 0.2           # the smooth union may bulge the bore under the head by this fraction of the shank blend
                                 # where the head's metal lies within the blend of it (0.12 of 0.3 at a 0.22 mm gap, 2026-11-03)
BURIED_ARCH_RADIUS_MM = 0.7      # arches off: the stub buried under the head is at most this fat (and 0.1 inside the band's faces)
BURIED_ARCH_MARGIN_MM = 0.1      # ... this far inside the bore and the outer face
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
    shank: "shankmod.ShankSpec | None" = None   # the shank's shape (taper ...); None = the band all round
    cathedral: bool = True                  # the gothic arches; False: plain shoulders, the head stands on the band
    panels: list = field(default_factory=list)   # artwork panels (artwork.Panel) on the band's faces; their head ends held back
    channel_mm: float = 0.30                # the artwork's numbers (artwork.ArtworkSpec)
    rail_mm: float = 0.35
    relief_mm: float = 0.25
    leaf_mm: float = 0.0
    leaf_pitch: float = 1.3
    stroke_mm: float = 0.3
    vein: bool = True
    shoulder_knot: str = ""                 # a knot ornament on each shoulder: "trinity" (ornament.KINDS), or none
    knot_at_deg: float = 0.0                # its centre from the top; 0 = just past the head
    knot_width_mm: float = 0.0              # across the band, lobe edge to lobe edge; 0 = the band's width + 1.2
    knot_ribbon_mm: float = 0.7
    knot_thickness_mm: float = 0.5
    _cache: dict = field(default_factory=dict, init=False, repr=False, compare=False)

    def __post_init__(self):
        if self.shank is not None and self.shank.band != self.band:
            raise ValueError("the shank's band must be the solitaire's band (its head section)")
        if not self.cathedral:
            self.milgrain = False                                        # the beads run along the arches
        if self.shank is not None and self.shank.knot == "trinity":
            # the band under the head runs out to a nose between the knot's lobes: its tip must clear
            # the head's feet along the ring; the arches and their milgrain give way to the knots
            from dataclasses import fields
            self.milgrain = False
            need = self.knot_pad_deg_needed()
            if self.shank.knot_pad_deg < need - 1e-6 or not self.shank.knot_pad_set:
                kw = {f.name: getattr(self.shank, f.name) for f in fields(self.shank) if f.name != "_cache"}
                kw["knot_pad_deg"], kw["knot_pad_set"] = need, True
                self.shank = shankmod.ShankSpec(**kw)

    @property
    def knot(self) -> str:
        return self.shank.knot if self.shank is not None else ""

    @property
    def arches(self) -> bool:
        """Cathedral arches between the shank and the head: every solitaire but the knotwork one
        and the plain-shouldered one (`cathedral=False`)."""
        return self.cathedral and not self.knot

    # ---- artwork ----------------------------------------------------------------------------
    @property
    def has_artwork(self) -> bool:
        return bool(self.panels)

    def head_clear_deg(self) -> float:
        """Where the band's faces are free of the head and the arches, from the top: past the arches'
        wedge (they fill the band's faces from mid-wall outward inside it), or on plain shoulders
        just past the head - its reach along the ring (the placed head and its seat cutter), the
        shank blend (a smooth union fills every corner within its radius) and PANEL_HEAD_CLEAR_MM."""
        if "head_clear" not in self._cache:
            if self.arches:
                deg = self.shoulder_deg + WEDGE_EXTRA_DEG + PANEL_WEDGE_CLEAR_DEG
            else:
                import numpy as np
                cutter = geom.offset_convex(self.head.seat.envelope(), self.head.clearance)
                reach = max(self.head_half_length(), float(np.abs(cutter.vertices[:, 1]).max()))
                ro = self.band.outer_radius_mm
                deg = math.degrees(math.asin(min(1.0, reach / ro))) + math.degrees((self.shank_blend + PANEL_HEAD_CLEAR_MM) / ro)
            self._cache["head_clear"] = round(deg, 2)
        return self._cache["head_clear"]

    def panel_start_min_deg(self) -> float:
        """Where a panel may begin: past the head and the arches (head_clear_deg), and past the
        shoulder knots by PANEL_KNOT_CLEAR_DEG when there are any."""
        lo = self.head_clear_deg()
        if self.has_knot:
            lo = max(lo, round(self.ornament.span_deg()[1] + PANEL_KNOT_CLEAR_DEG, 2))
        return lo

    # ---- knots ------------------------------------------------------------------------------
    @property
    def has_knot(self) -> bool:
        return bool(self.shoulder_knot)

    @property
    def ornament(self) -> "ornmod.KnotOrnament | None":
        """The shoulder knots (ornament.KnotOrnament over shank_spec): centred where knot_at_deg says,
        or just past the head (its span begins KNOT_HEAD_CLEAR_DEG past head_clear_deg)."""
        if not self.has_knot:
            return None
        if "ornament" not in self._cache:
            kw = dict(kind=self.shoulder_knot, width_mm=self.knot_width_mm, ribbon_mm=self.knot_ribbon_mm,
                      thickness_mm=self.knot_thickness_mm)
            at = float(self.knot_at_deg)
            if not at:
                probe = ornmod.KnotOrnament(self.shank_spec, at_deg=90.0, **kw)         # the span is the same anywhere
                lo, hi = probe.span_deg()
                at = round(self.head_clear_deg() + KNOT_HEAD_CLEAR_DEG + (90.0 - lo), 2)
            self._cache["ornament"] = ornmod.KnotOrnament(self.shank_spec, at_deg=at, **kw)
        return self._cache["ornament"]

    def write_knots(self, directory: Path, stem: str) -> tuple[str, str]:
        """<stem>.knot.stl and <stem>.knot2.stl for the notebook (ornament.write_layers), or two specks
        buried in the band when there are no knots."""
        orn = self.ornament
        if orn is not None:
            return orn.write_layers(Path(directory), stem)
        paths = [Path(directory) / f"{stem}.knot.stl", Path(directory) / f"{stem}.knot2.stl"]
        for path, speck in zip(paths, ornmod.buried_specks(self.band)):
            speck.export(str(path))
        return str(paths[0]), str(paths[1])

    def placed_panels(self) -> list:
        """The panels as they go on this ring: each one's head end held back to panel_start_min_deg."""
        from dataclasses import replace
        lo = self.panel_start_min_deg()
        return [replace(p, start_deg=max(float(p.start_deg), lo)) for p in self.panels]

    @property
    def artwork(self) -> "artmod.ArtworkSpec | None":
        """The artwork on this ring's shank (artwork.ArtworkSpec over shank_spec and placed_panels), or None."""
        if not self.has_artwork:
            return None
        if "artwork" not in self._cache:
            self._cache["artwork"] = artmod.ArtworkSpec(self.shank_spec, self.placed_panels(), channel_mm=self.channel_mm,
                                                        rail_mm=self.rail_mm, relief_mm=self.relief_mm, leaf_mm=self.leaf_mm,
                                                        leaf_pitch=self.leaf_pitch, stroke_mm=self.stroke_mm, vein=self.vein)
        return self._cache["artwork"]

    def write_artwork(self, directory: Path, stem: str) -> tuple[str, str]:
        """<stem>.cut.stl and <stem>.relief.stl for the notebook: the panel cutters and the relief
        (artwork.ArtworkSpec.write_layers, each refused if it crosses itself), or without artwork a
        cutter speck far outside the ring and a relief speck buried in the band - no-ops both."""
        art = self.artwork
        if art is not None:
            return art.write_layers(Path(directory), stem)
        cut, relief = Path(directory) / f"{stem}.cut.stl", Path(directory) / f"{stem}.relief.stl"
        artmod.outside_speck(self.band).export(str(cut))
        artmod.buried_speck(self.band).export(str(relief))
        return str(cut), str(relief)

    def carved_shank_mesh(self):
        """The shank body the notebook joins the arches and the head to: the independent shank
        carved by the artwork (artwork.design_mesh), the shoulder knots united onto it, or the
        plain shank."""
        if "carved_shank" not in self._cache:
            art = self.artwork
            body = art.design_mesh() if art is not None else self.shank_spec.design_mesh()
            if self.has_knot:
                body = shankmod.united([body] + self.ornament.design_parts())
            self._cache["carved_shank"] = body
        return self._cache["carved_shank"]

    def knot_pad_deg_needed(self) -> float:
        """How far the band must run either side of the head before a knot's nose: past everything
        of the head along the ring by KNOT_PAD_CLEAR_MM, so the knots hug the head without touching
        it (reference ring 01)."""
        r_m = self.band.bore_radius_mm + self.band.thickness_mm / 2
        return round(math.degrees((self.head_half_length() + KNOT_PAD_CLEAR_MM) / r_m), 2)

    @property
    def shank_blend(self) -> float:
        return tables.SETTINGS["blend_radius_mm"] if self.shank_blend_mm is None else float(self.shank_blend_mm)

    @property
    def shank_spec(self) -> "shankmod.ShankSpec":
        """The shank Python writes as a bar for the notebook: the given shape, or the band all round."""
        if self.shank is not None:
            return self.shank
        if "plain_shank" not in self._cache:
            self._cache["plain_shank"] = shankmod.ShankSpec(self.band)
        return self._cache["plain_shank"]

    @property
    def shaped(self) -> bool:
        return self.shank is not None and (self.shank.tapered or bool(self.shank.dip_mm) or self.shank.strands > 1
                                           or bool(self.shank.split_mm) or bool(self.shank.rope) or bool(self.shank.knot))

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
                        engraving_path: str = "", windows_path: str = "", shank_paths="", slot_path: str = "",
                        cut_path: str = "", relief_path: str = "", knot_paths=("", "")) -> dict:
        """`shank_paths`: the shank's shankmod.BAR_SLOTS bar files (shankmod.write_bars), or one path for every slot;
        `cut_path` / `relief_path`: the artwork layers (write_artwork; specks when there is no artwork); `knot_paths`:
        the knots' two layers (write_knots; specks when there are none)."""
        from .nb_solitaire import BAND_FOR_ARCHES
        band_ins = self.band.notebook_inputs("")
        sh = self.shank_spec.notebook_inputs(shank_paths, "")
        ins = {**{name: sh[name] for name in shankmod.SLOT_NAMES}, "Wrap Length": sh["Wrap Length"], "Slot Path": slot_path,
               "Cut Path": cut_path, "Relief Path": relief_path, "Knot Path": knot_paths[0], "Knot Path 2": knot_paths[1]}
        ins.update({k: band_ins[k] for k in BAND_FOR_ARCHES})
        ins["Edge Round"], ins["Edge Round Inward"] = sh["Edge Round"], sh["Edge Round Inward"]   # 0 for a rope or a knot
        if not self.arches:                                           # the buried stubs: short along the axis, in a fat torus
            ins.update({"Z Top": 0.5, "Z Bottom": -0.5, "Dome Tube Radius": 2.0})
        if self.outline:                                              # Seat Path, Clearance, Prongs Path + the rail numbers
            head = self.placed_head.notebook_inputs(seat_path, prongs_path)
        elif self.bezel:                                              # Seat Path, Clearance, Windows Path, Wall, Bezel Bottom/Top
            head = self.placed_head.notebook_inputs(seat_path, windows_path)
        else:                                                         # Seat Path, Clearance + the 14 head numbers
            head = self.placed_head.notebook_inputs(seat_path)
        head["Head Blend"] = head.pop("Blend Radius")                 # the block's own blend, named for this notebook
        ins.update(head)
        px, pz = self.pivot
        ins.update({"Pivot X": round(px, 4), "Pivot Z": round(pz, 4)})
        ins.update(self.arch_inputs())
        ins.update(self.bead_inputs())
        ins.update({"Engraving Path": engraving_path, "Engraving Wrap Length": round(self.engraving_wrap_length, 4),
                    "Shank Blend": round(self.shank_blend, 4)})
        if output_path is not None:
            ins["Output Path"] = output_path
        return ins

    @property
    def split(self) -> bool:
        return self.shank is not None and bool(self.shank.split_mm)

    def slot_mesh(self):
        """The slot cutter the notebook subtracts from the arches (ring frame, from inside the bore
        to above the arches' crest), or the speck far outside the ring when the shank is not split."""
        from . import engrave
        if not self.split or self.knot:                                   # a knot shank: the band under the head is whole
            return engrave.dummy_mesh(self.band.outer_radius_mm)
        return self.shank.slot_cutter(self.band.bore_radius_mm - 1.0, self.arch()["crest"] + 2.0)

    def _head_feet(self):
        """The placed head's lowest metal: the vertices within 0.8 mm of its base, in the head frame."""
        ph = self.placed_head
        m = ph.design_mesh() if self.bezel else (heads.outline_design_mesh(ph) if self.outline else heads.design_mesh(ph))
        low = m.vertices[:, 2] <= m.vertices[:, 2].min() + 0.8
        return m.vertices[low]

    def head_foot_half_span(self) -> float:
        """How far the placed head's lowest metal reaches across the band (the head frame's x) within
        0.8 mm of its base: what a split's slot must stay narrower than for the head to bridge it."""
        import numpy as np
        return float(np.abs(self._head_feet()[:, 0]).max())

    def head_foot_half_length(self) -> float:
        """How far the placed head's lowest metal reaches along the ring (the head frame's y)."""
        import numpy as np
        return float(np.abs(self._head_feet()[:, 1]).max())

    def head_half_length(self) -> float:
        """How far the placed head reaches along the ring at all (the head frame's y)."""
        import numpy as np
        if "head_half_length" not in self._cache:
            ph = self.placed_head
            m = ph.design_mesh() if self.bezel else (heads.outline_design_mesh(ph) if self.outline else heads.design_mesh(ph))
            self._cache["head_half_length"] = float(np.abs(m.vertices[:, 1]).max())
        return self._cache["head_half_length"]

    def head_zone_deg(self) -> float:
        """The angle either side of the head within which the head's metal (and the shank blend) can
        touch the bore: its reach along the ring at the bore radius, plus HEAD_ZONE_PAD_DEG."""
        return round(math.degrees(math.asin(min(1.0, self.head_half_length() / self.band.bore_radius_mm))) + HEAD_ZONE_PAD_DEG, 2)

    def head_bore_gap(self) -> float:
        """The placed head's lowest metal above the bore: the lower rail's underside (round) or the
        head's floor (outline, bezel). Within the shank blend of the bore, the smooth union bulges
        the bore under the head (36 µm on the flat Seraphine band at a 0.2 mm gap, 2026-11-03;
        a court band's comfort relief had kept the rail away from its bore)."""
        if self.floored:
            low = self.girdle_radius + self.placed_head.lowest_z()
        else:
            low = self.girdle_radius + self.placed_head.layout()["z_base"] - self.head.rail_rho
        return round(low - self.band.bore_radius_mm, 4)

    def blend_bore_note(self) -> str | None:
        gap = self.head_bore_gap()
        if self.shank_blend > 0 and gap < self.shank_blend:
            return (f"the head's lowest metal runs {gap:.2f} mm above the bore, within the {self.shank_blend:g} mm shank blend: the "
                    f"smooth union bulges the bore under the head by a few hundredths (the gate allows {BLEND_BORE_BULGE * self.shank_blend:.3f} "
                    f"on the radius there); --finger-clear {self.finger_clear + self.shank_blend - gap + 0.05:.2f} would clear it")
        return None

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

    def arch_inputs(self) -> dict:
        """The arches' numbers - or, with the arches off (a knot shank, plain shoulders), one stub
        buried in the band under the head: a 0.7 mm cylinder about a point on the +X axis at
        mid-thickness, 0.5 mm each way along the axis (Z Top / Z Bottom feed only the arches now),
        inside a fat torus and a 10° wedge, cut by nothing (the cut radius inside the bore). Both
        arch centres sit on that one point, so the arches' intersection is the whole cylinder: the
        opening erodes it by the edge round and it stays (two stubs 4° apart left a 0.11 mm lens,
        which a 0.1 mm erosion emptied before the mesh round trip - 2026-11-03, the flat band; the
        knot shank's edge round of 0 had hidden it). The notebook needs no conditional and its
        opening chain has a body to mesh; the independent model builds the same stub (ring_parts
        hollows it to a thin wall). Buried, it changes nothing."""
        if self.arches:
            a = self.arch()
            return {"Arch Centre X": round(a["cx"], 4), "Arch Centre Y": round(a["cy"], 4),
                    "Arch Centre Y Minus": round(-a["cy"], 4), "Arch Radius": round(a["R"], 4),
                    "Arch Dome Ring Radius": round(a["dome_ring"], 4), "Arch Cut Radius": round(a["r_cut"], 4),
                    "Wedge Angle": round(a["wedge_deg"], 4), "Wedge Angle Minus": round(-a["wedge_deg"], 4)}
        b = self.band
        r_m = b.bore_radius_mm + b.thickness_mm / 2
        rho = self.buried_stub_radius
        return {"Arch Centre X": round(r_m, 4), "Arch Centre Y": 0.0,
                "Arch Centre Y Minus": 0.0, "Arch Radius": round(rho, 4),
                "Arch Dome Ring Radius": round(rho, 4), "Arch Cut Radius": round(b.bore_radius_mm - 1.0, 4),
                "Wedge Angle": 10.0, "Wedge Angle Minus": -10.0}

    @property
    def buried_stub_radius(self) -> float:
        """The buried stub's radius (arches off): BURIED_ARCH_RADIUS_MM, or less on a band too thin to
        hold that inside its bore and outer face by BURIED_ARCH_MARGIN_MM."""
        return round(min(BURIED_ARCH_RADIUS_MM, self.band.thickness_mm / 2 - BURIED_ARCH_MARGIN_MM), 4)

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
        return {"band": self.band.design(), "shank": self.shank_spec.design(), "head": self.placed_head.design(),
                "finger_clear_mm": self.finger_clear,
                "shoulder_deg": self.shoulder_deg, "crown_below_girdle_mm": self.crown_below_girdle_mm,
                "arch": "gothic-tangent" if self.arches else "none", "milgrain": self.milgrain,
                "artwork": self.artwork.artwork_design() if self.has_artwork else None,
                "shoulder_knot": self.ornament.design() if self.has_knot else None,
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
                                                         windows=self.placed_head.windows_mesh() if self.bezel else None,
                                                         shank_mesh=self.carved_shank_mesh(), slot=self.slot_mesh())
        return self._cache["blend_volume"]

    @property
    def stem(self) -> str:
        from . import runs
        b, s = self.band, self.head.stone
        setting = "bezel" if self.bezel else f"{self.prong_count}prong"
        shape = f"_{self.shank_spec.shape_tag}" if self.shaped else ""
        art = ("_art" if self.has_artwork else "") + ("_knot" if self.has_knot else "")
        return (f"solitaire_{b.profile}_{b.label}{shape}_{setting}_{s.stem[len('stone_'):]}{art}_"
                f"{runs.spec_id(self.design())}")

    # ---- checks on the design ---------------------------------------------------------------
    def validate(self) -> list[str]:
        p = self.shank_spec.validate() + self.placed_head.validate()
        if self.shank is not None:
            sh = self.shank
            if sh.rope or sh.knot == "plait":
                p.append(f"a {'rope' if sh.rope else 'plait'} shank under a head: not yet (the head and the arches want a band to sit on)")
            if sh.dip_mm or sh.strands > 1:
                p.append("a contoured, chevron or double shank under a head: not yet (the head is placed on a band centred on the mid-plane)")
            if sh.split_mm and not p:
                span = self.head_foot_half_span()
                if sh.split_mm / 2 + 0.3 > span:
                    p.append(f"the slot ({sh.split_mm:g} mm) is too wide for the head to bridge: its foot reaches "
                             f"{span:.2f} mm either side of the centre, the slot may be {max(2 * (span - 0.3), 0):.1f} mm at most")
            wedge = self.shoulder_deg + WEDGE_EXTRA_DEG
            if sh.tapered and sh.taper_from_deg < wedge + 3.0:
                p.append(f"the taper starts {sh.taper_from_deg:g}° from the head, inside the arches (to ±{wedge:g}°): "
                         f"--taper-from at least {wedge + 3:g}")
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
        if self.has_knot and not p:
            if self.arches:
                p.append("a shoulder knot stands on the band's face: plain shoulders (--no-arches)")
            elif self.shank is not None and self.shaped:
                p.append("a shoulder knot stands on a plain band (a shaped shank later)")
            else:
                p += [q for q in self.ornament.validate() if q not in p]
                lo, hi = self.ornament.span_deg()
                if lo < self.head_clear_deg():
                    p.append(f"the knot begins at {lo:.1f}°, inside the head's clearance ({self.head_clear_deg():g}°): --knot-at later")
        if self.has_artwork and not p:
            art = self.artwork
            p += [q for q in art.validate() if q not in p]
            lo = self.panel_start_min_deg()
            for q, placed in zip(self.panels, art.panels):
                if placed.end_deg <= lo:
                    p.append(f"panel {q.face}: ends at {q.end_deg:g}°, inside the {'arches' if self.arches else 'head'} "
                             f"(a panel may begin at {lo:g}° at the earliest)")
            if self.has_engraving and self.engrave_side == "outside" and any(q.face == "outer" for q in self.panels):
                p.append("an outside engraving and an outer-face panel: not together")
        if not self.arches:
            if self.buried_stub_radius - self.shank_spec.edge_round < 0.1:
                p.append(f"the band ({self.band.thickness_mm:g} thick) is too thin to bury the arch stub under the head past "
                         f"its edge round {self.shank_spec.edge_round:g}")
            return p
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

    def free_angles(self) -> list[float]:
        """The gate's section-shape angles (gate.SHAPE_ANGLES_DEG) that see the plain shank: clear of
        the arches' wedge (and the head at 0°), and of the engraving opposite the head."""
        from . import gate
        wedge = self.shoulder_deg + WEDGE_EXTRA_DEG + 5.0
        text_half = 0.0
        if self.has_engraving:
            m = self.engraving_mesh()                                        # the text unwrapped: Y is along the ring
            text_half = math.degrees((m.bounds[1][1] - m.bounds[0][1]) / 2 / self.engraving.engrave_geometry()["wrap_radius"]) + 5.0
        out = []
        for a in gate.SHAPE_ANGLES_DEG:
            d_head = abs((a + 180.0) % 360.0 - 180.0)
            d_text = abs(((a - ENGRAVING_TURN_DEG) + 180.0) % 360.0 - 180.0)
            if self.knot and self.shank.trinity_section(a):                  # inside the knots and the band's nose
                continue
            if self.has_knot and self.ornament.in_span(a, 2.0):              # under a shoulder knot: the probes check it
                continue
            if d_head > wedge and d_text > text_half:
                out.append(a)
        return out

    def describe(self) -> str:
        a = self.arch()
        px, pz = self.pivot
        low = self.placed_head.lowest_z() if self.floored else self.placed_head.layout()["z_base"]
        return (f"{self.stem}\n  {self.shank_spec.describe() if self.shaped else self.band.describe()}\n  {self.placed_head.describe()}\n"
                f"  placement: girdle at r {self.girdle_radius:.3f}, culet {self.finger_clear} mm above the bore, "
                f"{'lowest metal' if self.floored else 'feet'} at r {self.girdle_radius + low:.3f}; "
                f"quarter-turn about (x {px:.3f}, z {pz:.3f}) ∥ Y\n"
                + (f"  arch: gothic, tangent to the band at ±{self.shoulder_deg:g}°, radius {a['R']:.3f} about "
                   f"({a['cx']:.3f}, ±{-a['cy']:.3f}); crest at r {a['crest']:.3f} ({a['rise']:.2f} mm above the band)"
                   + (f"\n  milgrain: {len(self.beads()['angles'])} beads of r {self.bead_radius_mm} mm per arch edge (x4), "
                      f"{self.beads()['spacing']:.3f}° apart" if self.milgrain else "\n  milgrain: off") if self.arches else
                   (f"  arches and milgrain: off - the band runs {self.shank.knot_pad_deg:g}° either side of the head (which reaches "
                    f"{self.head_half_length():.2f} mm along the ring) into the knots' noses" if self.knot else
                    f"  arches and milgrain: off - plain shoulders, the head (reaching {self.head_half_length():.2f} mm along the ring) "
                    "stands on the band"))
                + (f"\n  engraving: {self.text!r} {self.engrave_side}, {self.engraving.engrave_geometry()['height']:.2f} mm high, "
                   f"{self.engrave_depth_mm} mm deep, centred opposite the head" if self.has_engraving else "")
                + f"\n  blends: head {self.placed_head.blend:g} mm, head into shank {self.shank_blend:g} mm"
                + (f"\n  {self.ornament.describe()}" if self.has_knot else "")
                + (f"\n  artwork (panels begin at {self.panel_start_min_deg():g}° at the earliest, past the "
                   f"{'arches' if self.arches else ('knots' if self.has_knot else 'head')}):\n"
                   + "\n".join("  " + line for line in self.artwork.describe().splitlines()[1:])
                   if self.has_artwork else ""))


# ---- the independent ring ---------------------------------------------------------------------
def is_buried_stub(v: dict) -> bool:
    """Arches off: the arch inputs describe the stub buried under the head (SolitaireSpec.arch_inputs)."""
    return float(v["Arch Radius"]) <= BURIED_ARCH_RADIUS_MM + 1e-6


def arch_mesh(v: dict, inner: float):
    """The cathedral arches from the notebook's numbers: arch+ ∩ arch- ∩ wedge - the mid-wall cylinder.
    Each arch is the band's outer section (dome torus, edge round) about its centre; `inner` hollows
    it (any radius clear of the wedge - nTop leaves the arch solid; the wedge and cut decide). The
    buried stub (arches off) is built unopened: it is inside the band, its shape changes nothing,
    and the 2-D opening of its thin hollowed wall emptied it (2026-11-03)."""
    import numpy as np
    import trimesh
    from shapely.geometry import Point, Polygon, box
    zb, zt, e = float(v["Z Bottom"]), float(v["Z Top"]), float(v.get("Edge Round", 0.0))
    R, dr, dt = float(v["Arch Radius"]), float(v["Arch Dome Ring Radius"]), float(v["Dome Tube Radius"])
    sec = box(inner, zb, R, zt).intersection(Point(dr, 0.0).buffer(dt, quad_segs=256))
    if not is_buried_stub(v):
        sec = geom.open_polygon(sec, e, tables.opening_chamfer_mm(float(v.get("Mesh Tolerance", 0.1))))
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


def shank_from_inputs(v: dict):
    """The shank the notebook's Shank Path .. Shank Path 4 point at, each bar wrapped the way Remap
    Cylindrical wraps it and the wrapped bars united (shank.bars_from_inputs): what the notebook
    builds when no spec is at hand (the simulated nTop)."""
    return shankmod.bars_from_inputs(v)


def carved_shank_from_inputs(v: dict, cut: bool = True, relief: bool = True, knots: bool = True):
    """The shank from the notebook's numbers with its artwork: (bars − the cutters at Cut Path) ∪
    the relief at Relief Path ∪ the knot layers at Knot Path / Knot Path 2, as nb_solitaire carves
    the band before the arches and the head join it. Without those inputs (an older notebook), the
    bare shank; `cut` / `relief` / `knots` off simulate a notebook that lost a layer."""
    import trimesh
    body = shank_from_inputs(v)
    if v.get("Cut Path") and cut:
        cutter = trimesh.load(str(v["Cut Path"]), force="mesh")
        if cutter.bounds[0][0] < body.bounds[1][0]:                        # not the speck far outside
            body = trimesh.boolean.difference([body, cutter], engine="manifold")
    if v.get("Relief Path") and relief:
        body = trimesh.boolean.union([body, trimesh.load(str(v["Relief Path"]), force="mesh")], engine="manifold")
    if knots:
        for key in ("Knot Path", "Knot Path 2"):
            if v.get(key):
                body = trimesh.boolean.union([body, trimesh.load(str(v[key]), force="mesh")], engine="manifold")
    return body


def arches_with_slot(v: dict, inner: float, slot=None):
    """The arches less the split's slot cutter (the mesh at Slot Path when not given; a speck far
    outside the ring when the shank is not split, which changes nothing)."""
    import trimesh
    arch = arch_mesh(v, inner)
    if slot is None and v.get("Slot Path"):
        slot = trimesh.load(str(v["Slot Path"]), force="mesh")
    if slot is None or not slot.bounds[0][0] < arch.bounds[1][0] or slot.bounds.T[1][0] > arch.bounds[1][1]:
        return arch                                                         # no cutter, or one far outside
    return trimesh.boolean.difference([arch, slot], engine="manifold")


def ring_parts(v: dict, envelope, prongs=None, windows=None, beads: bool = True, cut_seat: bool = True,
               ops: geom.Booleans = geom.SHARP, shank_mesh=None, slot=None):
    """(shank, placed head, placement, placed seat cutter) from the notebook's numbers: the bodies
    the notebook's blended join unites and the cut that follows it. `prongs` / `windows`: the
    meshes the notebook's Prongs Path / Windows Path point at (read from those paths when not
    given); `shank_mesh`: the band/shank body with its artwork (the spec's carved independent
    sweep, or the bars at Shank Path .. wrapped and carved by the layers at Cut Path / Relief Path
    when not given). The head is built the way its block builds it (`ops` decides the blends)."""
    import trimesh
    t = math.hypot(float(v["Arch Centre X"]), float(v["Arch Centre Y"]))
    lo = float(v["Arch Dome Ring Radius"]) - math.sqrt(max(float(v["Dome Tube Radius"]) ** 2 - float(v["Z Top"]) ** 2, 0)) + 0.3
    inner = (lo + math.hypot(t, float(v["Arch Cut Radius"])) - 0.5) / 2     # midway between the bounds SolitaireSpec.arch() computes
    if is_buried_stub(v):
        inner = float(v["Arch Radius"]) - 0.1                                  # the buried stub: a 0.1 mm wall (unopened, see arch_mesh)
    if shank_mesh is None:
        shank_mesh = carved_shank_from_inputs(v)
    shank = ops.union([shank_mesh, arches_with_slot(v, inner, slot)] + ([bead_mesh(v)] if beads else []))
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
              engrave: bool = True, windows=None, ops: geom.Booleans = geom.SHARP, shank_mesh=None, slot=None):
    """The solitaire from the notebook's input numbers, in the notebook's order: shank ∪ placed
    head (blended in nTop by Shank Blend; `ops` decides), then the seat cutter and the engraving
    subtracted. `engraving`: the mesh Engraving Path points at (read from it when not given);
    `shank_mesh` as in ring_parts."""
    import trimesh
    shank, head, place, cutter = ring_parts(v, envelope, prongs, windows, beads=beads, cut_seat=cut_seat, ops=ops,
                                            shank_mesh=shank_mesh, slot=slot)
    ring = ops.union([shank, head], float(v.get("Shank Blend", 0.0)))
    cuts = [cutter] if cut_seat else []
    if engrave and "Engraving Path" in v:
        if engraving is None:
            engraving = trimesh.load(str(v["Engraving Path"]), force="mesh")
        cuts.append(wrapped_engraving(v, engraving))
    return ops.clean(ops.difference(ring, cuts))


def blend_estimate(v: dict, envelope, prongs=None, windows=None, shank_mesh=None, slot=None) -> float:
    """What the ring's blends add (negative: remove), mm³, from the notebook's numbers: the head's
    own junctions where they are exposed (buried in the shank: already solid; inside the seat: cut
    away afterwards), its rounded edges against, plus the head-to-shank union."""
    hv = {k: v[k] for k in v if k not in ("Head Blend",)}
    hv["Blend Radius"] = v.get("Head Blend", 0.0)
    shank_blend = float(v.get("Shank Blend", 0.0))
    if float(hv["Blend Radius"]) <= 0 and shank_blend <= 0:
        return 0.0
    shank, head, place, cutter = ring_parts(v, envelope, prongs, windows, shank_mesh=shank_mesh, slot=slot)
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
                         engraving=spec.engraving_mesh(), windows=windows, ops=ops, shank_mesh=spec.carved_shank_mesh(),
                         slot=spec.slot_mesh())
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
    art = spec.artwork
    art_filter = art.wall_ray_filter() if art is not None else None          # the channel zones measure rails, not walls
    knot_filter = spec.ornament.wall_ray_filter() if spec.has_knot else None   # a lobe overhanging the side is no wall

    def shank_rays(pts, n):                                                  # the shank away from the head
        keep = pts[:, 0] < -2.0
        if text_filter:
            keep = keep & text_filter(pts * flip, n * flip)
        if art_filter:
            keep = keep & art_filter(pts, n)
        if knot_filter:
            keep = keep & knot_filter(pts, n)
        return keep
    sh = spec.shank_spec
    free = spec.free_angles()

    def is_free(a):
        return any(abs((a - f + 180.0) % 360.0 - 180.0) < 1e-6 for f in free)

    def shank_section(a):                                                    # the designed section, away from head, arches and text
        if not is_free(a):
            return None
        return art.gate_section(a) if art is not None and art.in_panel(a) else sh.gate_section(a)

    def section_tol(a):
        return art.section_tolerance(a) if art is not None and art.in_panel(a) else sh.section_tolerance(a)
    rep = gate.check(stl, expect_volume=ntop_vol, wall_floor=sh.wall_floor(), wall_ray_filter=shank_rays,
                     section_design=shank_section, section_tol_mm=section_tol,
                     section_clip=art.section_clip if art is not None else None)
    ring = gate.load_mesh(stl)
    r = np.hypot(ring.vertices[:, 0], ring.vertices[:, 1])
    th = np.degrees(np.arctan2(ring.vertices[:, 1], ring.vertices[:, 0]))
    zone = spec.head_zone_deg()
    under = np.abs(th) <= zone
    bore = 2 * float(r[~under].min())
    rep.checks.append(gate.Check("bore", abs(bore - b.inner_diameter_mm) <= 0.05,
                                 f"Ø {bore:.3f} vs {b.inner_diameter_mm:.3f} mm (about the ring axis, outside ±{zone:g}° of the head)"))
    # under the head the shank blend may bulge the bore inward where the head's metal lies within its
    # radius; wider there is the design (a split's slot, a comfort relief at the halves' edges)
    bore_head = 2 * float(r[under].min()) if under.any() else bore
    allow = 0.05 + 2 * BLEND_BORE_BULGE * spec.shank_blend
    rep.checks.append(gate.Check("bore under the head", b.inner_diameter_mm - bore_head <= allow,
                                 f"Ø {bore_head:.3f} vs {b.inner_diameter_mm:.3f} mm within ±{zone:g}° (Δ {bore_head - b.inner_diameter_mm:+.3f}, "
                                 f"at most {allow:.3f} under" + (f": the {spec.shank_blend:g} mm shank blend's bulge" if spec.shank_blend > 0 else "") + ")"))
    z_ray = (spec.shank.split_mm / 2 + 0.3) if spec.split else 0.0          # a split shank: through a half, not the slot
    hits, _, _ = ring.ray.intersects_location([[0.0, 0.0, z_ray]], [[1.0, 0.0, 0.0]], multiple_hits=False)
    first = float(np.hypot(hits[0][0], hits[0][1])) if len(hits) else float("inf")
    rep.checks.append(gate.Check("bore closed under the stone", abs(first - b.bore_radius_at(z_ray)) <= 0.1,
                                 f"from the axis towards the head{f' (z {z_ray:.2f}, beside the slot)' if z_ray else ''}, "
                                 f"metal starts at r {first:.3f} (bore r {b.bore_radius_at(z_ray):.3f})"))
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
    if art is not None:
        rep.checks += artmod.artwork_checks(art, ring)                       # every panel probed, built against the carved band
    if spec.has_knot:
        rep.checks += ornmod.ornament_checks(spec.ornament, ring, design)    # the knots probed, built against the design
    if spec.has_engraving:
        turned = ring.copy()
        turned.apply_transform(trimesh.transformations.rotation_matrix(math.pi, [0, 0, 1]))   # the text back to +X
        pocket = spec.engraving.engraving_pocket(turned)
        rep.checks.append(gate.Check("engraving", pocket["found"],
                                     f"{pocket['pocket_area_mm2']:.1f} mm² of pocket on the {pocket['side']} for "
                                     f"{pocket['text_area_mm2']:.1f} mm² of text, opposite the head"
                                     + (f"; {pocket['stray_area_mm2']:.1f} mm² stray" if pocket["stray_area_mm2"] > 0.05 else "")))
    from .band import blended_design_volume_check
    overcut = sh.opening_overcut_mm3() + sh.sharp_edge_round_mm3()           # the shank's rounds as nTop's opening cuts them
    if spec.split and spec.arches and sh.edge_round > 0:                     # and the arches' slot edges, which nTop rounds
        a = spec.arch()
        overcut += geom.sharp_edge_round_mm3(arches_with_slot(spec.notebook_inputs(""), a["inner"], spec.slot_mesh()), sh.edge_round)
    c = blended_design_volume_check(float(design.volume) - overcut, spec.blend_volume_mm3(), ntop_vol, 3.0)
    if overcut and c.status != gate.INCOMPLETE:
        c.detail += f" [less {overcut:.2f} mm³ nTop's opening takes off the shank's rounds and the slot's edges]"
    rep.checks.append(c)
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
    built_notes = runs.require_built(cat, nb) if not notebook else []   # a notebook older than the catalog needs: refused
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
    bars = shankmod.write_bars(spec.shank_spec, run_dir, spec.stem)
    slot = run_dir / f"{spec.stem}.slot.stl"
    spec.slot_mesh().export(str(slot))
    cut, relief = spec.write_artwork(run_dir, spec.stem)                        # the panel cutters and the relief, or specks
    knots = spec.write_knots(run_dir, spec.stem)                                 # the shoulder knots' two layers, or specks
    stl = run_dir / f"{spec.stem}.stl"
    inputs = spec.notebook_inputs(str(envelope), str(stl), prongs_path=str(prongs) if spec.outline else "",
                                  engraving_path=str(engraving), windows_path=str(windows) if spec.bezel else "",
                                  shank_paths=bars, slot_path=str(slot), cut_path=cut, relief_path=relief, knot_paths=knots)
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
    res.notes += (spec.artwork.warnings() if spec.has_artwork else spec.band.warnings()) + built_notes
    if spec.blend_bore_note():
        res.notes.append(spec.blend_bore_note())
    report = {"stem": spec.stem, "spec_id": runs.spec_id(spec.design()), "run_id": run_id, "status": res.status,
              "design": spec.design(), "inputs": inputs, "stl": str(stl), "cut": cut, "relief": relief, "knots": list(knots),
              "ntop_volume_mm3": ntop_vol, "gate": rep.to_dict(), "notes": res.notes,
              "notebook": runs.notebook_identity(nb), "environment": runs.environment(ntopcl.version())}
    (run_dir / f"{spec.stem}.report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    if deliver and res.ok:
        res.delivered = runs.deliver(stl, run_dir, spec.stem, deliver_project, report, cast_metal=cast_metal,
                                     extra_files=([Path(cut), Path(relief)] if spec.has_artwork else [])
                                     + ([Path(k) for k in knots] if spec.has_knot else []))
    elif deliver:
        res.notes.append(f"not delivered: status {res.status}")
    return res
