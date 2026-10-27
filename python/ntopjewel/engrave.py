"""Engraving meshes for the ring_features notebook.

The notebook imports an STL, turns it into an implicit, wraps it round the ring with nTop's
Remap Cylindrical Body and subtracts it. Remap Cylindrical maps the flat body's coordinates as

    X -> radial distance from the ring axis,   Y -> position along the circumference
    (a Y span of `Y mapping length` goes once round, so with Y mapping length = 2πR the text
    is undistorted at radius R),   Z -> axial, unchanged.

So an engraving mesh here is the text extruded along X across the surface it should cut:
outside: from (surface radius - depth) outwards;  inside: from the bore inwards (towards the
axis) ... i.e. radially from (bore - margin) to (bore + depth).  Text reads left-to-right as
seen by a viewer looking at that surface: +Y on the outside, -Y on the inside (mirror).

Glyphs come from matplotlib (DejaVu Sans Bold by default, always present with matplotlib),
polygons from shapely, the solid from trimesh (mapbox-earcut triangulation).
"""
from __future__ import annotations

import math
from pathlib import Path

DEFAULT_FONT = {"family": "DejaVu Sans", "weight": "bold"}
MIN_DEPTH_MM = 0.25        # tables.FLOORS: engraving >= 0.25 mm deep, strokes >= 0.3 mm


def text_polygons(text: str, height_mm: float, font: dict | None = None):
    """Shapely (Multi)Polygon of `text`, glyph bbox height scaled to `height_mm`, centred on
    (0, 0) with the baseline direction along +X of the 2-D plane."""
    from matplotlib.font_manager import FontProperties
    from matplotlib.textpath import TextPath
    from shapely.geometry import Polygon
    from shapely import affinity
    prop = FontProperties(**(font or DEFAULT_FONT))
    tp = TextPath((0, 0), text, size=10.0, prop=prop)
    polys = [Polygon(p) for p in tp.to_polygons() if len(p) >= 3]
    polys = [p if p.is_valid else p.buffer(0) for p in polys if p.area > 1e-9]
    if not polys:
        raise ValueError(f"no glyph outlines for {text!r}")
    shape = None
    for p in sorted(polys, key=lambda q: -q.area):       # outer contours first; holes punch through
        shape = p if shape is None else shape.symmetric_difference(p)
    minx, miny, maxx, maxy = shape.bounds
    scale = height_mm / (maxy - miny)
    shape = affinity.scale(shape, xfact=scale, yfact=scale, origin=(0, 0))
    minx, miny, maxx, maxy = shape.bounds
    shape = affinity.translate(shape, xoff=-(minx + maxx) / 2, yoff=-(miny + maxy) / 2)
    return shape


def stroke_width_mm(shape) -> float:
    """A conservative estimate of the thinnest stroke: twice the largest inset that still
    leaves every glyph some area (binary search on a negative buffer)."""
    lo, hi = 0.0, 1.0
    for _ in range(18):
        mid = (lo + hi) / 2
        if shape.buffer(-mid).area > 1e-6:
            lo = mid
        else:
            hi = mid
    return 2 * lo


def text_mesh(text: str, height_mm: float, depth_mm: float, radius_mm: float, side: str = "outside",
              overshoot_mm: float = 0.6, font: dict | None = None):
    """A watertight trimesh of `text` ready for the notebook (see the module docstring).

    radius_mm is the surface radius the text sits on (outer radius for `outside`, bore
    radius for `inside`); the solid spans radially from radius - depth to radius + overshoot
    (outside) or from radius - overshoot to radius + depth (inside), so the subtract cuts a
    pocket `depth_mm` deep that is open to the surface."""
    import numpy as np
    import trimesh
    if side not in ("outside", "inside"):
        raise ValueError("side must be 'outside' or 'inside'")
    shape = text_polygons(text, height_mm, font)
    geoms = list(shape.geoms) if hasattr(shape, "geoms") else [shape]
    span = depth_mm + overshoot_mm
    parts = [trimesh.creation.extrude_polygon(g, height=span) for g in geoms]
    m = trimesh.util.concatenate(parts)
    v = m.vertices.copy()
    # 2-D plane: (u = reading direction, v = up) extruded along w.  Notebook: X radial, Y along
    # the circumference, Z axial.  Reading direction -> +Y outside, -Y inside (mirror).
    u, w_up, w = v[:, 0], v[:, 1], v[:, 2]
    if side == "outside":
        x = radius_mm - depth_mm + w
        y = u
    else:
        x = radius_mm - overshoot_mm + w
        y = -u
    m.vertices = np.column_stack([x, y, w_up])
    if side == "inside":
        m.invert()                                          # the mirror flipped the winding
    m.fix_normals()
    return m


def dummy_mesh(radius_mm: float):
    """A speck far outside the ring (radially): subtracting it changes nothing. Used when a
    ring has no engraving, so the notebook needs no conditional."""
    import trimesh
    m = trimesh.creation.box(extents=(0.2, 0.2, 0.2))
    m.apply_translation((radius_mm + 6.0, 0.0, 0.0))
    return m


def wrap_length_mm(radius_mm: float) -> float:
    """Remap Cylindrical's Y mapping length for undistorted text at `radius_mm`."""
    return 2 * math.pi * radius_mm


def write_engraving(path: Path, text: str | None, height_mm: float, depth_mm: float, radius_mm: float,
                    side: str = "outside", font: dict | None = None) -> dict:
    """Write the engraving (or the no-op speck) STL; return what the notebook and the gate need."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if text:
        m = text_mesh(text, height_mm, depth_mm, radius_mm, side, font=font)
        shape = text_polygons(text, height_mm, font)
        info = {"text": text, "height_mm": height_mm, "depth_mm": depth_mm, "side": side,
                "arc_length_mm": float(shape.bounds[2] - shape.bounds[0]),
                "stroke_mm": stroke_width_mm(shape), "cut_volume_mm3": float(shape.area * depth_mm)}
    else:
        m = dummy_mesh(radius_mm)
        info = {"text": None, "cut_volume_mm3": 0.0}
    m.export(str(path))
    info.update({"path": str(path), "wrap_length_mm": wrap_length_mm(radius_mm), "watertight": bool(m.is_watertight)})
    return info
