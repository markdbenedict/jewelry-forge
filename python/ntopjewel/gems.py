"""Stones: parametric gem bodies as exact meshes, for seats, cutters and weights.

A stone here is the solid a setting is built around, not a faceted render: girdle outline,
crown (girdle top to table), girdle band, pavilion (girdle bottom to culet). Facets do not
change where metal goes. Python writes the stone as a watertight STL (like the engraving
text); nTop imports it (Import Mesh -> Implicit from Mesh) wherever a setting needs it, so
one code path serves every shape and every stone is checked offline against its exact
volume and dimensions.

    coordinates: X along the stone's length, Y across, Z up; table on top (+Z), culet at
    the bottom, the girdle's mid-plane at z = 0, the outline centred on its bounding box

Shapes: round, oval, pear (point toward -X), marquise, cushion, emerald (step-cut octagon),
each from length x width (round: diameter). Proportions default to an ideal round's (table
57 %, crown 15 %, girdle 3 %, pavilion 43 % of the width); give a total depth (a calipered
stone) and crown and pavilion scale to fit it, girdle unchanged.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import tables

SHAPES = ("round", "oval", "pear", "marquise", "cushion", "emerald")
# fractions of the stone's WIDTH (the round's diameter)
TABLE_FRAC = {"round": 0.57, "oval": 0.57, "pear": 0.55, "marquise": 0.55, "cushion": 0.60, "emerald": 0.65}
CROWN_FRAC, GIRDLE_FRAC, PAVILION_FRAC = 0.15, 0.03, 0.43
MIN_GIRDLE_MM = 0.10
OUTLINE_POINTS = 256


@dataclass
class StoneSpec:
    shape: str = "round"
    length_mm: float = 6.5            # round: the diameter (width is ignored)
    width_mm: float | None = None
    depth_mm: float | None = None     # total height table to culet; None = ideal proportions
    table_frac: float | None = None
    girdle_mm: float | None = None
    material: str = tables.DEFAULT_STONE

    # ---- dimensions ------------------------------------------------------------------
    @property
    def length(self) -> float:
        return float(self.length_mm)

    @property
    def width(self) -> float:
        return float(self.length_mm if self.shape == "round" or self.width_mm is None else self.width_mm)

    @property
    def girdle(self) -> float:
        return max(MIN_GIRDLE_MM, float(self.girdle_mm) if self.girdle_mm is not None else GIRDLE_FRAC * self.width)

    @property
    def heights(self) -> tuple[float, float]:
        """(crown height, pavilion depth) in mm; scaled to the total depth when one is given."""
        crown, pav = CROWN_FRAC * self.width, PAVILION_FRAC * self.width
        if self.depth_mm is not None:
            k = (float(self.depth_mm) - self.girdle) / (crown + pav)
            crown, pav = crown * k, pav * k
        return crown, pav

    @property
    def depth(self) -> float:
        c, p = self.heights
        return c + self.girdle + p

    @property
    def table(self) -> float:
        return float(self.table_frac) if self.table_frac is not None else TABLE_FRAC[self.shape]

    @property
    def stem(self) -> str:
        dims = f"{self.length:g}" if self.shape == "round" else f"{self.length:g}x{self.width:g}"
        return f"stone_{self.shape}_{dims}x{self.depth:.2f}".replace(".", "p")

    # ---- outline -------------------------------------------------------------------------
    def outline(self, n: int = OUTLINE_POINTS):
        """Girdle outline as an (n, 2) array, counter-clockwise, centred on its bounding box."""
        import numpy as np
        L, W = self.length, self.width
        t = np.linspace(0, 2 * math.pi, n, endpoint=False)
        if self.shape in ("round", "oval"):
            xy = np.column_stack([L / 2 * np.cos(t), W / 2 * np.sin(t)])
        elif self.shape == "cushion":            # superellipse: a rounded rectangle
            e = 2 / 4.0
            c, s = np.cos(t), np.sin(t)
            xy = np.column_stack([L / 2 * np.sign(c) * np.abs(c) ** e, W / 2 * np.sign(s) * np.abs(s) ** e])
        elif self.shape == "emerald":            # rectangle with the corners cut at 45 deg
            cut = 0.18 * W
            hx, hy = L / 2, W / 2
            corners = [(hx, -hy + cut), (hx, hy - cut), (hx - cut, hy), (-hx + cut, hy), (-hx, hy - cut),
                       (-hx, -hy + cut), (-hx + cut, -hy), (hx - cut, -hy)]
            xy = _resample(np.array(corners), n)
        elif self.shape in ("pear", "marquise"):
            xy = _pear_or_marquise(L, W, n, self.shape == "marquise")
        else:
            raise ValueError(f"unknown shape {self.shape!r}; one of {', '.join(SHAPES)}")
        lo, hi = xy.min(axis=0), xy.max(axis=0)
        return xy - (lo + hi) / 2

    # ---- solid ---------------------------------------------------------------------------
    def mesh(self):
        """Watertight trimesh: table cap, crown, girdle band, pavilion to a culet point."""
        import numpy as np
        import trimesh
        xy = self.outline()
        n = len(xy)
        crown, pav = self.heights
        g = self.girdle
        rings = [(xy * self.table, g / 2 + crown), (xy, g / 2), (xy, -g / 2)]
        verts = [np.column_stack([r, np.full(n, z)]) for r, z in rings]
        V = np.vstack(verts + [np.array([[0.0, 0.0, g / 2 + crown]]), np.array([[0.0, 0.0, -g / 2 - pav]])])
        top, bottom = 3 * n, 3 * n + 1
        F = []
        for k in range(2):                                          # crown and girdle band
            a, b = k * n, (k + 1) * n
            for i in range(n):
                j = (i + 1) % n
                F += [[a + i, b + i, b + j], [a + i, b + j, a + j]]
        for i in range(n):
            j = (i + 1) % n
            F.append([top, i, j])                                   # table fan
            F.append([bottom, 2 * n + j, 2 * n + i])                # pavilion to the culet
        m = trimesh.Trimesh(V, np.array(F), process=True)
        if m.volume < 0:
            m.invert()
        trimesh.repair.fix_normals(m)
        return m

    def volume_mm3(self) -> float:
        return float(self.mesh().volume)

    def carats(self, material: str | None = None) -> float:
        return tables.carats(self.volume_mm3(), material or self.material)

    def validate(self) -> list[str]:
        p = []
        if self.shape not in SHAPES:
            p.append(f"unknown shape {self.shape!r}; one of {', '.join(SHAPES)}")
            return p
        if self.width > self.length + 1e-9 and self.shape != "round":
            p.append("length is the long side: swap length and width")
        if self.depth_mm is not None and float(self.depth_mm) <= self.girdle + 0.2:
            p.append(f"depth {self.depth_mm} mm leaves no crown or pavilion")
        if not 0.3 <= self.table <= 0.8:
            p.append(f"table {self.table:.0%} is outside 30-80 %")
        if self.material not in tables.STONE_DENSITY_G_CM3:
            p.append(f"unknown stone material {self.material!r}; one of {', '.join(tables.STONE_DENSITY_G_CM3)}")
        return p

    def describe(self) -> str:
        crown, pav = self.heights
        return (f"{self.stem}: {self.shape} {self.length:g} x {self.width:g} mm, depth {self.depth:.2f} mm "
                f"(crown {crown:.2f}, girdle {self.girdle:.2f}, pavilion {pav:.2f}), table {self.table:.0%}; "
                f"volume {self.volume_mm3():.2f} mm³ = {self.carats():.2f} ct {self.material}")

    def write(self, out_dir: Path) -> dict:
        """<stem>.stl and <stem>.stone.json (spec, derived numbers, mesh checks)."""
        problems = self.validate()
        if problems:
            raise ValueError("; ".join(problems))
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        m = self.mesh()
        stl = out_dir / f"{self.stem}.stl"
        m.export(str(stl))
        crown, pav = self.heights
        info = {"spec": asdict(self), "stl": str(stl), "length_mm": self.length, "width_mm": self.width,
                "depth_mm": self.depth, "crown_mm": crown, "girdle_mm": self.girdle, "pavilion_mm": pav,
                "table_frac": self.table, "volume_mm3": float(m.volume), "carats": self.carats(),
                "extents_mm": [float(x) for x in m.extents], "watertight": bool(m.is_watertight)}
        (out_dir / f"{self.stem}.stone.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
        return info


def _resample(poly, n: int):
    """n points evenly spaced along a closed polygon."""
    import numpy as np
    closed = np.vstack([poly, poly[:1]])
    seg = np.linalg.norm(np.diff(closed, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)])
    s = np.linspace(0, cum[-1], n, endpoint=False)
    x = np.interp(s, cum, closed[:, 0])
    y = np.interp(s, cum, closed[:, 1])
    return np.column_stack([x, y])


def _pear_or_marquise(L: float, W: float, n: int, marquise: bool):
    """Pear: a semicircle of radius W/2 at +X tapering to a point at -X; the taper's half-width
    is r * sin(pi/2 * t) ** 0.9 (t = 0 at the point, 1 where it meets the circle), so the
    outline is convex, has no kink where the two meet and comes to a point. Marquise: the
    taper at both ends."""
    import numpy as np
    r = W / 2
    m = n // 2
    if marquise:
        x = np.linspace(-L / 2, L / 2, m + 1)
        t = 1 - np.abs(x) / (L / 2)
        y = r * np.sin(math.pi / 2 * t) ** 0.9
    else:
        c = L / 2 - r                                   # centre of the round end
        x = np.linspace(-L / 2, L / 2, m + 1)
        y = np.empty_like(x)
        taper = x <= c
        t = (x[taper] + L / 2) / (c + L / 2)
        y[taper] = r * np.sin(math.pi / 2 * t) ** 0.9
        y[~taper] = np.sqrt(np.maximum(r * r - (x[~taper] - c) ** 2, 0.0))
    upper = np.column_stack([x[::-1], y[::-1]])          # +X to -X across the top
    lower = np.column_stack([x[1:-1], -y[1:-1]])          # back along the bottom
    return _resample(np.vstack([upper, lower]), n)
