---
name: ring-band
description: Build ring bands with nTop through ntopjewel - size (US/UK/ISO/mm), width, thickness and cross-section profile (flat, comfort-flat, court, d-shape, half-round), plain or tapered towards the bottom (the `shank` command), export STL, run the mesh gate and deliver to the Jewelry folder. Use for any request to make, resize, taper or batch band rings.
---

# ring-band

**Status.** Phase 0 notebook `ring_band.ntop` (flat band) passed its gate on 2026-10-25.
Phase 1 notebook `ring_band_profile.ntop` (dome, comfort bore, rounded edges) was authored
by `python -m ntopjewel api build band_profile` (the script `ntop/recipes/band_profile.py`,
through the Notebook API; `band-profile.md` is the GUI fallback) and all five profiles
passed the gate on 2026-10-27; it is committed in `ntop/notebooks/`. If `python -m ntopjewel
doctor` does not list it, build it that way first (nTop open, View > Python Console open);
do not improvise a notebook.

## Make bands

```powershell
python -m ntopjewel band --size 6 --profile court --out out\band          # default profile
python -m ntopjewel band --size 6.5 --profile comfort-flat --width 5 --thickness 1.5
python -m ntopjewel band --size L --system UK --profile d-shape
python -m ntopjewel band --size 52 --system ISO --profile half-round --deliver --project "Bands"
python -m ntopjewel band --size 6 --profile court --dome 0.4 --comfort 0.3 --edge-round 0.25
python -m ntopjewel band --size 6 --profile court --dry-run     # numbers only, no nTop run
python -m ntopjewel run ring_band --set "Outer Radius=9.553" ...   # the Phase 0 flat notebook
```

A set is a PowerShell loop, one STL per size:
`foreach ($s in 5,6,7) { python -m ntopjewel band --size $s --profile court --out out\band }`.

## Profiles (`ntopjewel.band.PROFILES`)

| profile | outside | bore | edge round | feel |
| --- | --- | --- | --- | --- |
| flat | flat | flat | 0.10 | modern, square |
| comfort-flat | flat | barrel, 0.22 x T | 0.20 | flat look, easy on the finger |
| court | dome 0.25 x T | barrel, 0.22 x T | 0.25 | the classic comfortable band |
| d-shape | dome 0.40 x T | flat | 0.20 | traditional wedding band |
| half-round | dome 0.55 x T | flat | 0.20 | needs T >= 1.3 mm at 4 mm wide |

T = thickness at the mid-plane. `--dome`, `--comfort`, `--edge-round` override a preset.
Validation refuses a band whose edge would be thinner than 0.45 mm (T - dome - comfort)
or whose edge round does not fit; `--dry-run` shows the numbers and any warning (a shallow
dome on a wide band can give a dome torus with ring radius <= 0, which nTop may reject).

## What Python decides vs the notebook

Python: inner diameter from `tables.inner_diameter_mm(size, system)` + allowance, radii,
z = ±W/2, both torus radii, edge offsets, the stem
`ring_band_<profile>_<label>_w<width>_t<thickness>_<spec id>` (the spec id hashes every
input, so a different dome, edge round, allowance or tolerance is a different file), the
design volume (Pappus over the opened section polygon, exact), gate expectations (inner/outer
Ø and width ± 0.05 mm, volume ± 2 % vs nTop, **design volume ± 0.5 % vs nTop**, **section shape
within 0.03 mm** - the STL's outline at 12 angles against the opened section by Hausdorff
distance, which is what catches an edge left sharp (0.065 mm on a court band's 0.25 mm round) -
wall floor = min(0.5 mm, 0.8 x designed edge thickness)). Notebook: one intersect (band, dome
torus, comfort torus), the opening (offset −e, a mesh round trip to re-distance, offset +e:
`nj.add_opening` - an Offset pair on its own cancels in nTop, and until 2026-10-30 no band had
its edges rounded), Volume Integral, mesh, export. The re-distance mesh chamfers the eroded
corners by about a voxel (Mesh Tolerance / 2), so nTop's round is a little fuller than e; the
design section emulates that (`geom.open_polygon`, `tables.opening_chamfer_mm`; calibrated
31 Oct: the court band then matches to 0.00 %, where the exact opening sat 0.4 % high). Inputs
are listed in `catalog/ring_band_profile.yaml`.

## Where the files go

Every run gets a fresh directory `out\band\<stem>\<run id>\` holding the STL, the input JSON,
the nTopCL log, `<stem>.gate.json` and `<stem>.report.json` (inputs, notebook sha256, versions,
status). Nothing is overwritten and an export left by an earlier run cannot pass for this
one. `--deliver` copies a **PASSED** part with all of that and a `manifest.json` to
`OneDrive\Documents\Jewelry\<project>\<stem>\`; a FAILED or INCOMPLETE part is never delivered
(the note says `not delivered: status ...`).

**The print file**: add `--prep` to any build (or `--prep-stl <the STL>` with the arguments it was built with) for `<stem>.supported.stl` - oriented, supported on polished faces and the bore only, on a raft, one body to slice as it is (`--bore avoid`, `--orient`, `--metal`; see `jewelry-design-rules`, "Printing").

## Report back

Paste the gate text (PASS / FAIL / INCOMPLETE, inner Ø, outer Ø, width, wall, volume,
weights, each check), the `status:` line and where the files went. INCOMPLETE means a
mandatory measurement could not be made (no volume from nTop, no thickness rays) - it is
not a pass. A FAIL is reported as a FAIL with the failing check named; a failing `design
volume` means the notebook built the wrong section, however good the dimensions look. Mesh
density: 0.1 mm tolerance is the default; 0.05 mm quadruples the triangles and is only for
final files with fine detail.

## Floors and defaults

Width 4 mm, thickness 1.3 mm. Thickness floor 1.0 mm, width floor 1.5 mm (`tables.FLOORS`,
from `data/jewelry_tables.json`). Wide bands (> 6 mm) get +¼ size; see `jewelry-design-rules`.

## Shaped shanks (Phase 3 step 1: `shank`, `ring_shank.ntop`)

A band whose section changes round the ring: full width and thickness at the head (angle 0,
+X), easing to a narrower, thinner section at the bottom of the finger (reference rings 02,
03, 05). Written 2026-10-30; the tapered shank and the rope PASSED in nTop the same day
(`python -m ntopjewel api build ring_shank`, then the commands below).

```powershell
python -m ntopjewel shank --size 6 --profile court --thickness 1.6 --width-bottom 2.2 --thickness-bottom 1.2
python -m ntopjewel shank --size 6 --profile court --width 5 --width-bottom 2.5 --taper-from 45   # the taper starts 45° from the head
python -m ntopjewel shank --size 6 --profile court --thickness 1.6 --width-bottom 2.2 --thickness-bottom 1.2 --dry-run
python -m ntopjewel shank --size 6 --profile court --thickness 1.6 --width-bottom 2.6 --thickness-bottom 1.4 --tolerance 0.05 --hammered   # hammered (ring-features skill: textures)
python -m ntopjewel shank --size 6 --width 3 --thickness 1.5 --dip 1.5 --dip-span 70                 # a contoured band: a smooth 1.5 mm bump at the head
python -m ntopjewel shank --size 6 --width 3 --thickness 1.5 --dip 2 --dip-shape chevron             # a V (chevron) band
python -m ntopjewel shank --size 6 --width 3 --thickness 1.5 --dip 2 --dip-shape chevron --double --gap 0.6 --bridges 180,100,-100   # ring 04's double chevron
python -m ntopjewel shank --size 6 --width 3 --thickness 1.5 --dip 1.2 --dip-span 80 --double --gap 0.4 --mirror   # a wishbone: the strands meet at the head
python -m ntopjewel shank --size 6 --width 4 --thickness 1.5 --split 1.6 --split-span 90                 # a split shank: a 1.6 mm slot at the head closing by 90° either side
python -m ntopjewel shank --size 6 --width 4 --thickness 1.5 --width-bottom 2.4 --thickness-bottom 1.2 --split 1.4 --split-span 70 --split-shape chevron   # split and tapered, the slot a V
python -m ntopjewel shank --size 6 --rope 2 --rope-turns 10 --rope-strand 1.2                            # a rope: two 1.2 mm strands twisted 10 times round the ring
python -m ntopjewel shank --size 6 --rope 3 --rope-turns 8 --rope-strand 1.0 --rope-offset 0.7           # three strands; --rope-offset sets how far off the centreline (in strand radii)
python -m ntopjewel shank --size 6 --width 4 --thickness 1.6 --knot plait --knot-strands 3 --knot-repeats 4   # Celtic plait: three 1.2 mm ribbons woven round the ring
python -m ntopjewel shank --size 6 --width 4 --thickness 1.6 --knot plait --knot-strands 4 --knot-repeats 3 --knot-profile round   # four round wires
python -m ntopjewel shank --size 6 --width 4 --thickness 1.6 --split 1.6 --split-span 100 --knot trinity --knot-width 5.6   # trinity knots on a split shank's shoulders
python -m ntopjewel shank --size 6 --width 4 --thickness 1.6 --split 1.6 --split-span 110 --knot twist   # the halves cross over each other on each shoulder (rings 06, 07)
```

The centreline (step 1b): `--dip` moves the band's centre off the mid-plane at the head (+ towards
+Z), as a smooth cosine bump (`contour`, rings 08-style) or a V (`chevron`, its point at the
head) over `--dip-span` either side of the head. `--double` stacks two strands of the band
`--gap` apart (the second dips the same way - nested chevrons - or the other way with
`--mirror`, a wishbone), joined by full-thickness bridges `--bridge` long at `--bridges` angles
(default 180°, the bottom; two strands without a bridge are two rings and are refused, as are
mirrored strands that would cross). Taper, dip and strands combine. The gate's section-shape
check compares the built outline with the designed section at each angle, so a lost dip or a
missing strand fails it, and the width check uses the ring's overall width.

Split and rope shanks (step 1c): `--split` cuts a slot `--split` wide at the head that closes
towards the bottom over `--split-span` either side (`contour`: a cosine; `chevron`: linear),
ending in a round end (0.4 mm: a cast slot cannot end in a crack); each half must stay ≥ 1 mm
wide at the head, and a split combines with taper and dip but not with `--double`. `--rope`
replaces the profile altogether: 2 or 3 round strands of `--rope-strand` diameter, their centres
`--rope-offset` strand radii off the rope's centreline (< 1 so they overlap into one solid; the
innermost strand just touches the bore), twisted `--rope-turns` (a whole number) times round
the ring. No taper, dip, double or split on a rope. The gate reads a rope's designed sections
off the bar wrapped (the strands cross a meridian obliquely) and gates walls at 0.8 × the
strand diameter.

The fillets: a split's halves are lofted from the 2-D opened sections, so the slot's four
fillets (radius e, the band's edge round) are in the bar itself; a bridge's long faces sit flush
with the strands' edge surfaces (it runs 0.1 mm into each strand at the strands' relieved bore
and fallen-off dome), so only its two end faces have sharp edges. Before the wrap,
`ring_shank.ntop` opens the bar by `Edge Round Inward` (−e) / `Edge Round` (+e) with a mesh
round trip between (`nj.add_opening`: an Offset pair on its own cancels in nTop - see
`ntop-automate`), which rounds whatever is left sharp; the gate's expected volume takes that
off: e²(tan(δ/2) − δ/2) per mm of every convex edge turning more than 30° in the design mesh
(0.1 % on a bridged double, nothing on a plain or split shank). A bridge must be ≥ 2e + 0.1 mm
long or the opening removes it; a rope passes e = 0.

The section-shape check: the gate slices the STL at 12 angles (1.37° off the 30° marks, never a
station) and compares each outline with the designed 2-D section (`ShankSpec.section_shape`:
strands at their centrelines, a bridge where one spans the angle, the slot and its fillets,
all opened by e; a rope's from the bar wrapped) by Hausdorff distance, within 0.03 mm or half
the mesh tolerance (0.05 at the default 0.1: nTop's mesher rounds a sharp concave crease by a
voxel - a rope's strands met 0.034 mm fuller than the model). Angles within e of a slot's end
or a bridge's end are skipped (their faces look along the ring). An unwrapped export, a wrong
wrap length, a lost dip, a missing strand or a slot edge left sharp all fail here.

Real runs: the tapered court shank PASSED (outlines within 0.004 mm, volume +0.00 %) and the
2 x 10 rope PASSED (−0.02 %) on 30 Oct; the first split came back with sharp slot edges (0.12 mm
off the filleted section) because nTop's Offset pair was a no-op; rebuilt with the re-distanced
opening it PASSED on 31 Oct (outlines within 0.031 mm, volume +0.3 % of the expectation once
the mesher's chamfer on the rounds is counted: `ShankSpec.opening_overcut_mm3`, 2.2 mm³ on
that split, 0.8 on the tapered shank).

Celtic knotwork (step 1e, `knotwork.py`): `--knot plait` replaces the profile with 2..4 strands
woven the whole way round - strand k the sinusoid z = A sin(R·2πy/L + 2πk/n) in the ring's
developed surface, A reaching the band's edges, R = `--knot-repeats` - as ribbons `--strand-width`
wide (`--knot-profile flat`, corners rounded by the band's edge round) or round wires
(`round`). Every crossing has one strand over and one under, alternating along each strand (the
over/under of each strand's first crossing is solved so every crossing is consistent; a diagram
that cannot alternate is refused). The interlace is radial: a strand's centre sits at mid-depth
between crossings and rises or sinks by h = (t − 0.1)/2 at each, a cosine from crossing to
crossing, so the over strand's inner face lies 0.1 mm inside the under strand's outer face and
the two fuse into one casting there; a strand's thickness t = (T + 0.1)/2, so two stacked at a
crossing make the band's thickness T (an under strand's inner face on the bore, an over strand's
outer face at r_bore + T: the bore and outer Ø checks hold). Floors: t ≥ 0.75 mm (a 1.4 mm band or
thicker), ribbons ≥ 0.75 wide, each pair of strands parting ≥ w + 0.3 mm between crossings (a
pierced weave, not a slab), one body; a crossing angle under 12° is warned. No opening (e = 0),
no taper, dip, double or split; the gate reads the designed sections off the bar wrapped (as a
rope) and gates walls at 0.8 t. Stem `ring_shank_plait<strands>x<repeats>_<label>_w<width>t<t>_<id>`
(wires `_d<t>_`). Not under a head yet (the solitaire refuses it).

`--knot trinity` (reference ring 01) weaves a triquetra from a split shank's two halves on each
shoulder: the trefoil φ = 2t, ρ = R(1 + c cos 3t) (three lobes, three self-crossings at radius R,
`--knot-ratio` c = 0.5 gives 74° crossings) with the lobe that points down the shank opened and
its two ends led out as the halves (cubic tails, `--knot-tail` 3 mm long, which narrow and thin
the half's section into the knot's ribbon - `--strand-width` 0.9 x `--knot-thickness` 0.7 T, a
rounded rectangle); the other two lobes flank the band under the head, which runs out to a nose
(1.2 mm long, ribbon + 0.6 wide) that enters the knot's head-side crossing. `--knot-width` sets
the knot across the band (default W + 1.2; its three inner passes must stay a ribbon + 0.3 apart,
so a 4 mm band takes a 0.9 ribbon at 5.2 mm or more); `--knot-pad` where the nose tip lies (30°;
a solitaire sizes it from its head). The strand rides the mid law about a line 0.1 mm above the
bore (a pass under stays off the finger by that much; the bore law's full lift came back down
too steeply for the ribbon's thickness, 2026-11-01) and is swept in two pieces that share one
section ring and cap (a sweep that passes over itself is no manifold); the halves' lofts end in
the strands' first and last rings the same way - bodies that meet in one identical face unite
cleanly, where overlaps drawn a hair apart left needle faces. No opening (e = 0: every round is
in the bar); the union is tidied by manifold3d within 0.1 µm and, as every bar's union, has its
edges under 0.2 µm collapsed (`geom.collapse_short_edges`; nTop merges "very close vertices" on
import and made a self-intersecting, five-shell bar of 1.5 µm edges, 2026-11-01). The gate reads its sections off the
design itself inside the knots and the band under the head (|θ| to the tails' end + 0.5 mm) and
off the 2-D model elsewhere. Stem `..._split1.6_trinity5.6_<id>`.

`--knot twist` (reference rings 06 / 07) crosses a split shank's two halves over each other on
each shoulder. Each half stays ONE loft the whole way round - half k from the crossing zones round
the bottom, the other half under the head, the strand between - so the bars are the split's two
and nothing in nTop changes. In a zone `--twist-length` long (8 mm, 3..20) starting where the band
under the head ends (`--knot-pad`, 30°; a solitaire sizes it from its head plus the eye's round
end) the strand's section morphs from its half into the mirror-image half by a half cosine, the
centre following (the outlines all start on the bore below their own centre, so the morph is point
for point), its width stretched by the slope it crosses the ring at. Both strands thin to
`--knot-thickness` (0.7 T, at least 0.75) where they cross, the upper half (`TWIST_OVER`) lifted onto
the lower, fused 0.1, for as long as their footprints overlap (+0.05), easing back to the band by a
cosine over the rest of the zone. The slot becomes two eyes on each shoulder: closed under the
head with a round end split/2 deep, `--split` wide where the strands leave the band and where they
become the halves, then the split's law to `--split-span`. No opening (e = 0, the lofts carry
the band's rounds); the gate reads the design across the zones and the eyes' ends. Refused: no
`--split`; the slot closed before the zone ends; a taper starting inside it; an overlap leaving the
over strand under 1 mm to come down, or a rise tighter than t/2 + 0.1 (a longer twist; a wider split
makes narrower strands that overlap for less). Stem `..._split1.6_twist8_<id>`.

How it is made: Python writes the ring **unrolled as a bar** (X radial, Y along the ring, Z
axial; one cross-section every 2.5°, the band profile at that angle's width and thickness,
lofted; a turn and a half plus a margin so the seam lies inside material) into the run
directory; `ring_shank.ntop` imports it, makes it implicit and wraps it round Z with Remap
Cylindrical Body (Y mapping length = Wrap Length). r and z are exact under that map and Y is
exactly the angle, so the section at every angle is the one `ShankSpec` designed. The taper
law: the full section until `--taper-from` degrees from the head, then a cosine ease to the
bottom (no crease at the shoulders or the bottom). The thin end must itself be a valid band
(floors, edge round): a 1.0 mm court bottom needs `--edge-round 0.15`.

**Bodies that cross each other travel in separate bars** (`ShankSpec.bar_meshes`, up to four:
`Shank Path` .. `Shank Path 4`, catalog 0.3; an unused slot imports the smallest bar again),
each opened by the edge round on its own, and nTop's Boolean Union joins the opened
implicits before the wrap (opening the union eroded a 0.05 mm groove along a split's seam: a
union's field measures to a buried face inside an overlap). Bodies that overlap must overlap
by more than the edge round, because the opening rounds a body's cut edge starting that far
back from the cut (a split's halves overlap edge round + mesh tolerance where the slot is
closed, `split_overlap_mm`; at 0.1 mm the quarter-rounds met in a 0.055 mm groove along the
seam, 2026-11-03). The bars: a split's
two halves, a double band's strands and its bridges, a rope's or a plait's strands one each, a
trinity shank's lower half with the strands' first pieces, its upper half with their second
and the pad on its own (each piece runs a 0.1 mm plug into the half and the piece that continue
it, so the union sees overlaps, never a shared face). A mesh union of crossing bodies leaves
faces micrometres apart along its seams, which float32 STL and nTop's import turned into a
self-intersecting bar (the trinity shank, 2026-11-02: 5 shells). The `[W] ... very close
vertices have been merged` line on an Import Mesh is routine (an STL is a triangle soup);
`[W] Mesh_0: Output Mesh is self-intersecting` is the one that matters. nTop's mesher leaves
12-face bubbles of no volume where two surfaces kiss (a ribbon's rounded corner passing
another's at a fused crossing): the gate reports them as degenerate specks beside the shell
count (under 1e-6 mm³), not as shells. Through a trinity knot the section check allows the whole
mesh tolerance (a pass over another makes a step crease the mesher fills by a voxel per round
trip: 0.057 mm at 0.1), half of it elsewhere.

The gate: the band checks measured about the axis (bore Ø, the widest width, the largest
outer Ø, walls against the thinnest station's edge), volume vs nTop, **section shape** (above)
and the design volume against the independent sweep of the same sections (no bar, no wrap). Files: `out\shank\<stem>\<run id>\` with the bars
(`<stem>.bar.stl`, `.bar2.stl` ...) beside the STL; stem
`ring_shank_<profile>_<label>_w<head>-<bottom>_t<head>-<bottom>[_contour1.5|_chevron2][_x2|_x2m][_split1.6]_<spec id>`,
a rope `ring_shank_rope<strands>x<turns>_<label>_d<strand>_<spec id>`.

## Next in this family

The solitaire's shank is a bar too since step 1d (`solitaire --width-bottom ... --thickness-bottom
...`, `--split ...`, `--split ... --knot trinity | twist`; `gem-library`). Next: pavé along a twist's strand (ring 07); contoured, double, rope
and plait shanks under a head - all built as bars and wrapped the same way.
