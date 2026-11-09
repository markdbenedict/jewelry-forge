"""The test-print set and its round folder (2026-11-08).

Every round of test prints is the same three parts, built at one size - the tables' test_print_size, US 4.5 since
8 Nov (Mark's call), each part's contacts thinned to about half (their own spacings in the tables: 33 and 36 contacts
at 1.5 mm would swell where they meet the part, Mark judged; the court band's bore takes struts since the 8 Nov round,
when it leaned on its bead row and stayed on the film) - each through its own command
with `--prep --deliver` (or `--prep-stl delivered`, `--reprep`: the parts already delivered, prepared again), and the
round's folder `Jewelry\\Test Print\\<date> US<size>\\` written from what came back: the print files
(`<stem>.supported.stl`, oriented and supported, sliced as they are), their previews, README.md (what each part is
and tests, how it stands and what it leaves unsupported) and measurements.md (the design numbers beside the blanks to
fill in). The earlier rounds' folders are left as they are.

`run` takes the runner that does one part (the CLI's `_run_part`: a command line in, {code, spec, res, prep}
out), so it is tested without nTop.
"""
from __future__ import annotations

import datetime
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import tables

FOLDER = "Test Print"


def size() -> str:
    """The test prints' ring size (the tables' test_print_size: US 4.5 since 8 Nov)."""
    return f"{tables.SETTINGS['test_print_size']:g}"


@dataclass(frozen=True)
class Part:
    key: str
    title: str
    args: tuple
    tests: str
    bore: str = "allow"
    spacing_key: str | None = None   # the tables' setting of its own support spacing (None: support_spacing_mm)
    rows: tuple = ()                 # the part's own rows of the measurement table
    questions: tuple = ()            # its yes / no feature questions


# The court band's bore takes supports since 9 Nov: with beads on both edges, nothing but its dome can start the print
# (leaning, the bead row led its first contact by 12 layers and the ring stayed on the film, 8 Nov), so it stands on
# edge, and then the bore's crown needs struts. The mandrel reads it after the nubs are sanded flush.
PARTS = (
    Part("court", 'Court band, 4 × 1.3 mm: milgrain on both edges, a 0.25 mm channel groove outside, "M+K 2026" engraved inside',
         ("ring", "--profile", "court", "--milgrain", "--groove", "0.25", "--engrave", "M+K 2026"),
         "the calibration piece: the bore on the mandrel (nubs sanded flush first), width and thickness; 0.5 mm beads; "
         "letters 0.25 deep, 0.6 mm strokes",
         spacing_key="test_print_court_spacing_mm",
         rows=("Outer Ø over the beads (×3)", "Width over the beads (×2)", "Width between the faces, beside a bead (×2)"),
         questions=("Beads: all present? ____  Missing or merged in a quarter turn: ____  Shape (round / blobby / flat): ____",
                    "Groove: continuous and crisp-edged? ____",
                    "Engraving: every letter legible (M + K 2 0 2 6)? ____  Strokes open to the floor or filled? ____",
                    "Bore nubs (crown and floor): how many ____  sanded flush before the mandrel? ____  bore read before / after: ____",
                    "Sits flat on glass (no rocking)? ____")),
    Part("hammered", "Hammered court band, 4 × 1.6 mm: about 150 strikes 0.10–0.19 mm deep, polished rims",
         ("texture", "--thickness", "1.6", "--tolerance", "0.05"),
         "does a texture this shallow read after printing (and later after casting)",
         spacing_key="test_print_hammered_spacing_mm",
         rows=("Outer Ø across the rims (×3)", "Width (×2)"),
         questions=("Dimples read by eye at arm's length? ____  Under a loupe? ____",
                    "The facet creases between strikes visible? ____  The lightest strikes (0.10) visible? ____",
                    "Do layer lines compete with the texture? ____",
                    "Rims flat and clean? ____")),
    Part("seraphine", "The Seraphine: a 6.5 mm round in a 4-prong head on a flat band 2.8 × 2.0 tapering to 2 × 1.5, "
                      "scroll-and-leaf relief panels, a trinity knot on each shoulder",
         ("solitaire", "--profile", "flat", "--width", "2.8", "--thickness", "2", "--prongs", "4", "--no-arches", "--sides",
          "scroll-leaves", "--outer", "scroll", "--shoulder-knot", "trinity", "--leaf-tilt", "7.5", "--leaf-stem", "0.5",
          "--stem-width", "0.15", "--width-bottom", "2", "--thickness-bottom", "1.5"),
         "every prong intact (the Phase 2 gate), 0.15 mm relief lines, the knots; a 6.5 mm stone should drop into the seat",
         spacing_key="test_print_seraphine_spacing_mm",
         rows=("Overall height, bottom of the band to the prong tips", "Band width at the bottom", "Band width at the head"),
         questions=("All four prongs intact and the same height? ____  Tips (sharp / rounded / blobbed): ____",
                    "A 6.5 mm stone (or a 6.5 mm drill shank) drops into the seat and sits level? ____",
                    "Knots: the over / under crossings readable, the strands separate? ____  Anything filled in: ____",
                    "Leaf rows and scroll: every leaf present? ____  The 0.15 mm stems whole? ____  Vein grooves visible? ____",
                    "Panel floors clean (no fuzz)? ____")),
)


def select(keys: str | None) -> tuple:
    """The parts named in a comma list (all of them for None)."""
    if not keys:
        return PARTS
    want = [k.strip() for k in keys.split(",") if k.strip()]
    known = {p.key: p for p in PARTS}
    bad = [k for k in want if k not in known]
    if bad:
        raise ValueError(f"no test part {', '.join(bad)} (the set: {', '.join(known)})")
    return tuple(known[k] for k in want)


def args_for(part: Part, size_=None, metal: str | None = None, spacing: float | None = None, reprep: bool = False) -> list[str]:
    """The command line that builds (or, reprep, prepares again) one part of the round: at the round's size, its bore
    rule, its own support spacing (unless one is given for all), delivered."""
    a = list(part.args) + ["--size", str(size_ or size()), "--bore", part.bore, "--deliver"]
    a += ["--prep-stl", "delivered"] if reprep else ["--prep"]
    if metal:
        a += ["--metal", metal]
    sp = spacing if spacing else (tables.SETTINGS[part.spacing_key] if part.spacing_key else None)
    if sp:
        a += ["--support-spacing", f"{sp:g}"]
    return a


def folder_for(deliver_dir: Path, size_=None, today: datetime.date | None = None) -> Path:
    today = today or datetime.date.today()
    return Path(deliver_dir) / FOLDER / f"{today:%Y-%m-%d} US{size_ or size()}"


def ok(rec: dict) -> bool:
    res, prep = rec.get("res"), rec.get("prep")
    return rec.get("code") == 0 and prep is not None and prep.ok and (res is None or res.ok)


def run(size_, parts, runner, deliver_dir: Path, metal=None, spacing=None, reprep=False, today=None, say=print):
    """Each part through `runner(command line) -> record`, then the round's folder from the parts that passed.
    Returns (folder, [(part, record)])."""
    size_ = size_ or size()
    done = []
    for i, p in enumerate(parts, 1):
        say(f"== test print {i}/{len(parts)}: {p.key} (US {size_}) ==")
        done.append((p, runner(args_for(p, size_, metal, spacing, reprep))))
    folder = folder_for(deliver_dir, size_, today)
    if any(ok(rec) for _, rec in done):
        write_round(folder, size_, done, metal, today)
    return folder, done


# ---------------------------------------------------------------- the round's folder
def numbers(spec, prep) -> dict:
    """The design numbers to measure against: the band's, the taper's, and the built part's volume and size."""
    b = spec.band
    d = {"bore": b.inner_diameter_mm, "width": b.width_mm, "thickness": b.thickness_mm, "outer": 2.0 * b.outer_radius_mm,
         "volume": prep.part_volume_mm3, "extents": prep.part_extents_mm, "resin_g": tables.weight_g(prep.part_volume_mm3, "resin")}
    sh = getattr(spec, "shank_spec", None)
    if sh is not None and sh.width_bottom_mm:
        d["width_bottom"] = sh.width_bottom_mm
        d["thickness_bottom"] = sh.thickness_bottom_mm or b.thickness_mm
    if getattr(spec, "milgrain", False) and prep.part_extents_mm:
        d["over_beads"] = prep.part_extents_mm[2]                  # the part's own reach along the axis: the beads'
    return d


def _design_line(n: dict) -> str:
    s = f"bore Ø {n['bore']:.3f}"
    if "width_bottom" in n:
        s += (f"; band {n['width']:g} wide × {n['thickness']:g} thick at the head, {n['width_bottom']:g} × "
              f"{n['thickness_bottom']:g} at the bottom; {' × '.join(f'{v:.1f}' for v in n['extents'])} mm overall")
    else:
        s += f", width {n['width']:.3f}" + (f" ({n['over_beads']:.2f} over the beads)" if "over_beads" in n else "")
        s += f", thickness {n['thickness']:.3f}, outer Ø {n['outer']:.2f}"
    return s + f"; {n['volume']:.1f} mm³ ({n['resin_g']:.2f} g of resin)"


def write_round(folder: Path, size_, done, metal=None, today=None) -> Path:
    """README.md, measurements.md, the print files and their previews of the parts that passed."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    today = today or datetime.date.today()
    good = [(p, rec) for p, rec in done if ok(rec)]
    for _, rec in good:
        for key in ("print file", "preview"):
            f = rec["prep"].files.get(key)
            if f is not None and Path(f).exists():
                shutil.copy2(f, folder / Path(f).name)
    tip = good[0][1]["prep"].settings["support_tip_mm"] if good else tables.SETTINGS["support_tip_mm"]
    scale = f", scaled ×{good[0][1]['prep'].scale:.4f} for {metal}" if metal and good else " at finished size (no shrink scaling)"
    when = f"{today.day} {today:%b %Y}"
    lines = [f"# Test Print — {when}, US {size_}", "",
             f"{len(good)} part{'s' if len(good) != 1 else ''}{scale}, prepared for the Mars 5 Ultra in Royal Blue: each "
             "`.supported.stl` is the part on its supports and a raft, already oriented - **slice it as it is: add no "
             "supports, do not rotate it**; the raft takes the bottom layers. Supports touch polished faces and the bore "
             f"only, each a {tip:g} mm breakaway tip, spaced as the table says (about half as densely as the slicer-style "
             "1.5 mm, so fewer contacts crowd one face; a few more sit under each part's lowest layers, which nothing else "
             "holds off the film). Every part starts on a support within two layers of its lowest point - the 8 Nov court "
             "band leaned on its bead row for twelve layers first and stayed on the film. The court band's bore carries "
             "struts for its crown: sand their nubs flush before the mandrel reads it. The `.prep.png` beside each shows "
             "where the supports are; the `.prep.json` in the part's own folder (Rings\\, Bands\\, Solitaires\\) lists every "
             "support and every spot that prints unsupported.", "",
             "| File | What it is | Design numbers to measure against | How it prints | Tests |", "| --- | --- | --- | --- | --- |"]
    for p, rec in good:
        prep = rec["prep"]
        n = numbers(rec["spec"], prep)
        how = (prep.headline() + f", {prep.settings['support_spacing_mm']:g} mm apart"
               + (f"; {prep.cautions()}" if prep.cautions() else ""))
        lines.append(f"| `{Path(prep.files['print file']).name}` | {p.title} | {_design_line(n)} | {how} | {p.tests} |")
    bad = [(p, rec) for p, rec in done if not ok(rec)]
    if bad:
        lines += ["", "Not in this round (they did not pass; see their commands' reports): "
                  + ", ".join(p.key for p, _ in bad) + "."]
    lines += ["", "Please note when they are out: the bore reading (mandrel size or mm), width and thickness with calipers at the "
              "mid-plane, which features survived, the weight of each, and at the supports: any swelling where they met the "
              "part, how cleanly they broke, whether anything sagged where the preview marks it unsupported. "
              "`measurements.md` has the blanks."]
    (folder / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (folder / "measurements.md").write_text(_sheet(size_, good, when), encoding="utf-8")
    return folder


def _sheet(size_, good, when) -> str:
    out = [f"# Test Print — measurements (US {size_}, {when})", "",
           "Fill the blanks and tell Claude the sheet is in (it reads this file from the folder), or paste the numbers in",
           "the chat. Calipers to 0.01 mm. \"×3\" means three readings round the ring, about 120° apart; \"mandrel\" the size",
           "mark the ring stops at (half sizes count). Measure after the wash and the full UV cure — that is the pattern the",
           "investment will see — and say how long after the cure. Photos (phone macro) of a support scar on each, the",
           "engraving, a milgrain edge, the hammered face in raking light, the Seraphine's head and one shoulder.", "",
           "## Print settings (once)", "",
           "- Printer / resin: Elegoo Mars 5 Ultra, Siraya Tech Royal Blue",
           "- Layer height: ____ µm;  exposure: ____ s;  bottom layers: ____ at ____ s",
           "- Printed from the `.supported.stl` files as they are (no supports added, not rotated)? ____",
           "- Wash: IPA ____ min;  cure: ____ min;  measured ____ h after the cure",
           "- Scale resolution: ____ g;  calipers: ____", ""]
    for i, (p, rec) in enumerate(good, 1):
        prep = rec["prep"]
        n = numbers(rec["spec"], prep)
        out += [f"## {i}. {p.title}", "", f"Design: {_design_line(n)}.", f"Printed: {prep.headline()}, "
                f"{prep.settings['support_spacing_mm']:g} mm apart" + (f"; {prep.cautions()}" if prep.cautions() else "") + ".", "",
                "| Measure | 1 | 2 | 3 |", "| --- | --- | --- | --- |",
                "| Bore Ø, inside jaws (×3) | | | |", "| Mandrel size it stops at | | | |"]
        out += [f"| {r} | | | |" for r in p.rows]
        out += ["| Weight (g) | | | |", "", "Features (yes / no, a few words):"]
        out += [f"- {q}" for q in p.questions]
        out += ["- Supports: swelling where they met the part? ____  Broke off clean at the tip? ____  Nubs sanded flush? ____",
                "- Anything sagged or missing where the preview marks it unsupported? ____", ""]
    return "\n".join(out)
