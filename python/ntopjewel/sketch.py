"""The measurement sketches (9 Nov 2026, Mark: "terms like width are vague"): one picture per test part showing where
each row of the measurement sheet is taken, labelled with the row's own words - a face-on view for the diameters (the
bore with the calipers' inside jaws, the outer diameter over whatever stands proudest), a cross-section or an elevation
for the widths, the mandrel and the scale as small notes. Drawn to the design's proportions with matplotlib, saved as
PNG; `calibrate.write_workbook` puts each on its part's tab beside the table, and testprint saves them in the round's
folder as measure_<part>.png."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

PARTS = ("court", "hammered", "seraphine")   # the test parts a sketch exists for

ARROW = dict(arrowstyle="<|-|>", color="#1f4e79", lw=1.3, shrinkA=0, shrinkB=0, mutation_scale=10)
LABEL = dict(fontsize=8.5, color="#1f4e79", family="DejaVu Sans")
NOTE = dict(fontsize=7.5, color="#444444", family="DejaVu Sans")
METAL = "#d9d9d9"
EDGE = "#333333"


def _dim(ax, p, q, text, side="above", offset=0.0, align="center", **kw):
    """A dimension arrow between p and q with its label beside it (kw: text properties, e.g. rotation)."""
    ax.annotate("", xy=q, xytext=p, arrowprops=ARROW)
    mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
    props = dict(LABEL)
    if side == "above":
        props.update(ha=align, va="bottom"); pos = (mx, my + offset)
    elif side == "below":
        props.update(ha=align, va="top"); pos = (mx, my - offset)
    elif side == "left":
        props.update(ha="right", va="center"); pos = (mx - offset, my)
    else:
        props.update(ha="left", va="center"); pos = (mx + offset, my)
    props.update(kw)
    ax.text(pos[0], pos[1], text, **props)


def _ring_face(ax, r_in, r_out, title, outer_label, bead_ring=None, head=None, thickness=False):
    """The ring seen along its axis: the bore and the outer diameter."""
    from matplotlib.patches import Circle, Polygon
    ax.set_aspect("equal")
    ax.axis("off")
    ax.add_patch(Circle((0, 0), r_out, facecolor=METAL, edgecolor=EDGE, lw=1.2))
    ax.add_patch(Circle((0, 0), r_in, facecolor="white", edgecolor=EDGE, lw=1.2))
    if bead_ring:
        t = np.linspace(0, 2 * math.pi, 110, endpoint=False)
        ax.scatter(bead_ring * np.cos(t), bead_ring * np.sin(t), s=4, color="#777777", zorder=3)
    if head is not None:
        w, h = head
        y0 = r_out - 0.3
        ax.add_patch(Polygon([(-w / 2, y0), (w / 2, y0), (w / 2 * 0.8, y0 + h), (-w / 2 * 0.8, y0 + h)], closed=True,
                             facecolor=METAL, edgecolor=EDGE, lw=1.2))
        ax.add_patch(Circle((0, y0 + h * 0.55), w * 0.33, facecolor="#e8f1fb", edgecolor=EDGE, lw=1.0))
    # the bore: inside jaws, the arrow heads against the bore
    _dim(ax, (-r_in, 0), (r_in, 0), "Bore Ø, inside jaws (×3)", side="above", offset=0.35)
    ax.text(0, -0.6, "three places round the ring,\nabout 120° apart", ha="center", va="top", **NOTE)
    # the outer diameter, vertical, outside jaws
    x = r_out + 1.6
    ax.plot([-r_out, x + 0.3], [-r_out, -r_out], color="#1f4e79", lw=0.6, ls=":")
    ax.plot([-r_out, x + 0.3], [r_out, r_out], color="#1f4e79", lw=0.6, ls=":")
    _dim(ax, (x, -r_out), (x, r_out), outer_label, side="right", offset=0.3, rotation=90, rotation_mode="anchor", ha="center", va="top")
    if thickness:
        ax.annotate("", xy=(0, -r_in), xytext=(0, -r_out), arrowprops=dict(ARROW, lw=1.1, mutation_scale=6))
        ax.annotate("thickness at the printed bottom\n(where it stood on its supports)", xy=(0.1, -(r_in + r_out) / 2),
                    xytext=(2.2, -r_out - 1.6), arrowprops=dict(arrowstyle="-", color="#1f4e79", lw=0.6), ha="left", va="center", **LABEL)
        ax.annotate("", xy=(-r_in, 0.9), xytext=(-r_out, 0.9), arrowprops=dict(ARROW, lw=1.1, mutation_scale=6))
        ax.annotate("thickness at the side,\nhalf way up as printed", xy=(-(r_in + r_out) / 2, 1.0),
                    xytext=(-r_in + 0.8, 3.2), arrowprops=dict(arrowstyle="-", color="#1f4e79", lw=0.6), ha="left", va="center", **LABEL)
    ax.set_title(title, fontsize=9.5, color="#222222", loc="left")
    lim = r_out + 4.2
    ax.set_xlim(-r_out - 1.2, lim + 1.5)
    ax.set_ylim(-r_out - 2.4, r_out + (head[1] + 1.2 if head else 1.2))


def _section_court(ax, width, thickness, bead_d, groove_w, groove_depth, over_beads, labels):
    """The court band's cross-section: flat bore below, domed face above, a bead on each top corner, the groove in the middle."""
    from matplotlib.patches import Circle, Polygon
    ax.set_aspect("equal")
    ax.axis("off")
    w2 = width / 2
    sag = 0.3 * thickness
    xs = np.linspace(-w2, w2, 80)
    dome = thickness - sag * (xs / w2) ** 2
    pts = [(-w2, 0), (w2, 0)] + [(x, y) for x, y in zip(xs[::-1], dome[::-1])]
    ax.add_patch(Polygon(pts, closed=True, facecolor=METAL, edgecolor=EDGE, lw=1.2))
    if groove_w:
        ax.add_patch(Polygon([(-groove_w / 2, thickness + 0.02), (groove_w / 2, thickness + 0.02),
                              (groove_w / 2, thickness - groove_depth), (-groove_w / 2, thickness - groove_depth)],
                             closed=True, facecolor="white", edgecolor=EDGE, lw=1.0))
    r = bead_d / 2
    for sx in (-1, 1):
        ax.add_patch(Circle((sx * w2, thickness - sag), r, facecolor=METAL, edgecolor=EDGE, lw=1.2))
    ax.text(0, -0.08, "bore (engraving inside)", ha="center", va="top", **NOTE)
    top = thickness + 0.9
    _dim(ax, (-w2 - r, top), (w2 + r, top), labels["over_beads"], side="above", offset=0.08)
    for sx in (-1, 1):
        ax.plot([sx * (w2 + r), sx * (w2 + r)], [thickness - sag, top], color="#1f4e79", lw=0.6, ls=":")
    low = -0.75
    _dim(ax, (-w2, low), (w2, low), labels["width"], side="below", offset=0.08)
    for sx in (-1, 1):
        ax.plot([sx * w2, sx * w2], [low, 0], color="#1f4e79", lw=0.6, ls=":")
    ax.text(w2 + r + 0.25, thickness - sag, "milgrain bead", ha="left", va="center", **NOTE)
    ax.set_title("Cross-section of the band", fontsize=9.5, color="#222222", loc="left")
    ax.set_xlim(-w2 - 1.4, w2 + 2.6)
    ax.set_ylim(low - 0.9, top + 0.8)


def _section_hammered(ax, width, thickness, rim, labels):
    """The hammered band's cross-section: a court dome struck between two polished rims."""
    from matplotlib.patches import Polygon
    ax.set_aspect("equal")
    ax.axis("off")
    w2 = width / 2
    sag = 0.3 * thickness
    xs = np.linspace(-w2, w2, 160)
    dome = thickness - sag * (xs / w2) ** 2
    strikes = np.zeros_like(xs)
    inner = np.abs(xs) < w2 - rim
    for c in np.linspace(-w2 + rim + 0.25, w2 - rim - 0.25, 5):
        strikes += 0.14 * np.exp(-((xs - c) / 0.22) ** 2)
    dome = dome - strikes * inner
    pts = [(-w2, 0), (w2, 0)] + [(x, y) for x, y in zip(xs[::-1], dome[::-1])]
    ax.add_patch(Polygon(pts, closed=True, facecolor=METAL, edgecolor=EDGE, lw=1.2))
    for sx in (-1, 1):
        ax.plot([sx * (w2 - rim), sx * w2], [thickness - sag * ((w2 - rim) / w2) ** 2, thickness - sag], color="#1f4e79", lw=2.2)
    ax.text(w2 + 0.2, thickness - sag + 0.05, "polished rim", ha="left", va="center", **NOTE)
    ax.text(0, thickness + 0.12, "hammered face", ha="center", va="bottom", **NOTE)
    low = -0.75
    _dim(ax, (-w2, low), (w2, low), labels["width"], side="below", offset=0.08)
    for sx in (-1, 1):
        ax.plot([sx * w2, sx * w2], [low, 0], color="#1f4e79", lw=0.6, ls=":")
    ax.text(0, -0.08, "bore", ha="center", va="top", **NOTE)
    ax.set_title("Cross-section of the band", fontsize=9.5, color="#222222", loc="left")
    ax.set_xlim(-w2 - 1.4, w2 + 2.6)
    ax.set_ylim(low - 0.9, thickness + 1.2)


def _elevation_seraphine(ax, r_in, r_out, width_head, width_bottom, head_h, labels):
    """The Seraphine from the side, perpendicular to its axis: the band edge-on, widest under the head, the head on top."""
    from matplotlib.patches import Polygon, Rectangle
    ax.set_aspect("equal")
    ax.axis("off")
    ys = np.linspace(-r_out, r_out, 60)
    # the band's half-width along the ring: width_bottom at the bottom easing to width_head at the top
    frac = (ys + r_out) / (2 * r_out)
    half = (width_bottom + (width_head - width_bottom) * frac ** 2) / 2
    pts = [(-h, y) for h, y in zip(half, ys)] + [(h, y) for h, y in zip(half[::-1], ys[::-1])]
    ax.add_patch(Polygon(pts, closed=True, facecolor=METAL, edgecolor=EDGE, lw=1.2))
    # the head: a basket with four prongs over the band's top
    hw = width_head * 1.9
    y0 = r_out - 0.2
    ax.add_patch(Polygon([(-hw / 2 * 0.55, y0), (hw / 2 * 0.55, y0), (hw / 2, y0 + head_h * 0.55), (-hw / 2, y0 + head_h * 0.55)],
                         closed=True, facecolor=METAL, edgecolor=EDGE, lw=1.2))
    for sx in (-1, 1):
        ax.add_patch(Rectangle((sx * hw / 2 - (0.22 if sx > 0 else 0), y0 + head_h * 0.5), 0.22, head_h * 0.5,
                               facecolor=METAL, edgecolor=EDGE, lw=1.0))
    ax.text(0, y0 + head_h * 0.3, "stone", ha="center", va="center", **NOTE)
    top = y0 + head_h
    x = -max(width_head, hw) / 2 - 1.6
    _dim(ax, (x, -r_out), (x, top), labels["height"], side="left", offset=0.3, rotation=90, rotation_mode="anchor", ha="center", va="bottom")
    ax.plot([x - 0.3, 0], [-r_out, -r_out], color="#1f4e79", lw=0.6, ls=":")
    ax.plot([x - 0.3, -hw / 2], [top, top], color="#1f4e79", lw=0.6, ls=":")
    yh = r_out - 2.2
    hh = (width_bottom + (width_head - width_bottom) * ((yh + r_out) / (2 * r_out)) ** 2) / 2
    _dim(ax, (-hh - 1.2, yh), (hh + 1.2, yh), labels["width"], side="right", offset=hh + 1.6)     # the arrow drawn past the band's edges
    for sx in (-1, 1):
        ax.plot([sx * hh, sx * hh], [yh - 0.6, yh + 0.6], color="#1f4e79", lw=0.8)
    yb = -r_out + 0.8
    hb = (width_bottom + (width_head - width_bottom) * ((yb + r_out) / (2 * r_out)) ** 2) / 2
    _dim(ax, (-hb - 1.2, yb), (hb + 1.2, yb), labels["width_bottom"], side="right", offset=hb + 1.6)
    for sx in (-1, 1):
        ax.plot([sx * hb, sx * hb], [yb - 0.6, yb + 0.6], color="#1f4e79", lw=0.8)
    ax.text(0, -r_out - 0.5, "the band seen edge-on; its width is along this arrow", ha="center", va="top", **NOTE)
    ax.set_title("From the side, the ring standing on its bottom", fontsize=9.5, color="#222222", loc="left")
    ax.set_xlim(x - 2.4, max(hb, hh) + 9.5)
    ax.set_ylim(-r_out - 2.2, top + 1.0)


def _notes(fig, size, mandrel=True):
    txt = []
    if mandrel:
        txt.append(f"Mandrel size it stops at: slide the ring onto the mandrel without force and read the size mark it stops at "
                   f"(quarter sizes count; the design is US {size}). Sand the support nubs flush first.")
    txt.append("Weight (g): the ring alone, supports and raft broken off and the nubs sanded, after the wash and the full cure.")
    txt.append("×3 / ×2: that many readings at different places round the ring; the sheet has three cells a row, leave the rest empty.")
    fig.text(0.015, 0.02, "\n".join(txt), ha="left", va="bottom", fontsize=7.5, color="#444444", wrap=True)


def sketch(key: str, design: dict, path: Path, size: str | None = None, labels: dict | None = None) -> Path:
    """The measurement sketch for a test part (key: court, hammered, seraphine) from its design numbers, saved as PNG."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    labels = labels or {}
    bore = design.get("bore", 15.288)
    outer = design.get("outer", bore + 2 * design.get("thickness", 1.3))
    r_in, r_out = bore / 2, outer / 2
    fig = plt.figure(figsize=(9.0, 4.6), dpi=150)
    if key == "court":
        ax1 = fig.add_axes([0.02, 0.20, 0.46, 0.75])
        ax2 = fig.add_axes([0.50, 0.20, 0.48, 0.75])
        _ring_face(ax1, r_in, r_out, "Seen along the axis", labels.get("outer", "Outer Ø over the beads (×3)"), bead_ring=r_out - 0.22, thickness=True)
        _section_court(ax2, design.get("width", 4.0), design.get("thickness", 1.3), 0.5, 0.6, 0.25, design.get("over_beads"),
                       {"over_beads": labels.get("over_beads", "Width over the beads (×2)"),
                        "width": labels.get("width", "Width between the faces, beside a bead (×2)")})
        _notes(fig, size or "4.5")
    elif key == "hammered":
        ax1 = fig.add_axes([0.02, 0.20, 0.46, 0.75])
        ax2 = fig.add_axes([0.50, 0.20, 0.48, 0.75])
        _ring_face(ax1, r_in, r_out, "Seen along the axis", labels.get("outer", "Outer Ø across the rims (×3)"))
        _section_hammered(ax2, design.get("width", 4.0), design.get("thickness", 1.6), 0.75, {"width": labels.get("width", "Width (×2)")})
        _notes(fig, size or "4.5")
    else:
        ax1 = fig.add_axes([0.02, 0.20, 0.40, 0.75])
        ax2 = fig.add_axes([0.44, 0.20, 0.54, 0.75])
        ext = design.get("extents") or [21.8, 19.3, 6.2]
        head_h = max(ext[0] - outer, 3.0)
        _ring_face(ax1, r_in, r_out, "Seen along the axis", "outer Ø (not on the sheet)", head=(design.get("width", 2.8) * 2.0, head_h))
        _elevation_seraphine(ax2, r_in, r_out, design.get("width", 2.8), design.get("width_bottom", 2.0), head_h,
                             {"height": labels.get("height", "Overall height, bottom of the band to the prong tips"),
                              "width": labels.get("width", "Band width at the head"),
                              "width_bottom": labels.get("width_bottom", "Band width at the bottom")})
        _notes(fig, size or "4.5")
    path = Path(path)
    fig.savefig(path, dpi=150, facecolor="white")
    plt.close(fig)
    return path
