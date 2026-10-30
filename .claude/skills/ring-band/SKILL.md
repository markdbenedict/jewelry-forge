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
design volume (Pappus over the opened section), gate expectations (inner/outer Ø and width
± 0.05 mm, volume ± 2 % vs nTop, **design volume ± 2 % vs nTop**, wall floor = min(0.5 mm,
0.8 x designed edge thickness)). Notebook: one intersect (band, dome torus, comfort torus),
two offsets, Volume Integral, mesh, export. Inputs are listed in `catalog/ring_band_profile.yaml`.

## Where the files go

Every run gets a fresh directory `out\band\<stem>\<run id>\` holding the STL, the input JSON,
the nTopCL log, `<stem>.gate.json` and `<stem>.report.json` (inputs, notebook sha256, versions,
status). Nothing is overwritten and an export left by an earlier run cannot pass for this
one. `--deliver` copies a **PASSED** part with all of that and a `manifest.json` to
`OneDrive\Documents\Jewelry\<project>\<stem>\`; a FAILED or INCOMPLETE part is never delivered
(the note says `not delivered: status ...`).

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
03, 05). Written 2026-10-30; the first real build is pending (`python -m ntopjewel api build
ring_shank`, then the commands below).

```powershell
python -m ntopjewel shank --size 6 --profile court --thickness 1.6 --width-bottom 2.2 --thickness-bottom 1.2
python -m ntopjewel shank --size 6 --profile court --width 5 --width-bottom 2.5 --taper-from 45   # the taper starts 45° from the head
python -m ntopjewel shank --size 6 --profile court --thickness 1.6 --width-bottom 2.2 --thickness-bottom 1.2 --dry-run
python -m ntopjewel shank --size 6 --width 3 --thickness 1.5 --dip 1.5 --dip-span 70                 # a contoured band: a smooth 1.5 mm bump at the head
python -m ntopjewel shank --size 6 --width 3 --thickness 1.5 --dip 2 --dip-shape chevron             # a V (chevron) band
python -m ntopjewel shank --size 6 --width 3 --thickness 1.5 --dip 2 --dip-shape chevron --double --gap 0.6 --bridges 180,100,-100   # ring 04's double chevron
python -m ntopjewel shank --size 6 --width 3 --thickness 1.5 --dip 1.2 --dip-span 80 --double --gap 0.4 --mirror   # a wishbone: the strands meet at the head
python -m ntopjewel shank --size 6 --width 4 --thickness 1.5 --split 1.6 --split-span 90                 # a split shank: a 1.6 mm slot at the head closing by 90° either side
python -m ntopjewel shank --size 6 --width 4 --thickness 1.5 --width-bottom 2.4 --thickness-bottom 1.2 --split 1.4 --split-span 70 --split-shape chevron   # split and tapered, the slot a V
python -m ntopjewel shank --size 6 --rope 2 --rope-turns 10 --rope-strand 1.2                            # a rope: two 1.2 mm strands twisted 10 times round the ring
python -m ntopjewel shank --size 6 --rope 3 --rope-turns 8 --rope-strand 1.0 --rope-offset 0.7           # three strands; --rope-offset sets how far off the centreline (in strand radii)
```

The centreline (step 1b): `--dip` moves the band's centre off the mid-plane at the head (+ towards
+Z), as a smooth cosine bump (`contour`, rings 08-style) or a V (`chevron`, its point at the
head) over `--dip-span` either side of the head. `--double` stacks two strands of the band
`--gap` apart (the second dips the same way - nested chevrons - or the other way with
`--mirror`, a wishbone), joined by full-thickness bridges `--bridge` long at `--bridges` angles
(default 180°, the bottom; two strands without a bridge are two rings and are refused, as are
mirrored strands that would cross). Taper, dip and strands combine. The gate's section-profile
check compares the section's z and r bounds at each angle, so a lost dip or a missing strand
fails it, and the width check uses the ring's overall width.

Split and rope shanks (step 1c): `--split` cuts a slot `--split` wide at the head that closes
towards the bottom over `--split-span` either side (`contour`: a cosine; `chevron`: linear),
ending in a round end (0.4 mm: a cast slot cannot end in a crack); each half must stay ≥ 1 mm
wide at the head, and a split combines with taper and dip but not with `--double`. `--rope`
replaces the profile altogether: 2 or 3 round strands of `--rope-strand` diameter, their centres
`--rope-offset` strand radii off the rope's centreline (< 1 so they overlap into one solid; the
innermost strand just touches the bore), twisted `--rope-turns` (a whole number) times round
the ring. No taper, dip, double or split on a rope. The gate reads a rope's section bounds off
the independent mesh (the strands cross a meridian obliquely) and gates walls at 0.8 × the
strand diameter.

The opening: after the wrap, `ring_shank.ntop` offsets the body by `Edge Round Inward` (−e)
then `Edge Round` (+e), e = the band's edge round (0 for a rope). The band's own edges are
rounded that much in the section already, so it changes nothing on a plain, tapered or
contoured band; it rounds the edges a slot or a bridge leaves sharp (a cast part should not
have them), and the gate's expected volume takes that off: e²(tan(δ/2) − δ/2) per mm of every
convex edge turning more than 30° in the design mesh (0.7 % on a 1.6 mm split over 180°, 0.1 %
on a bridged double). A bridge must be ≥ 2e + 0.1 mm long or the opening removes it.

How it is made: Python writes the ring **unrolled as a bar** (X radial, Y along the ring, Z
axial; one cross-section every 2.5°, the band profile at that angle's width and thickness,
lofted; a turn and a half plus a margin so the seam lies inside material) into the run
directory; `ring_shank.ntop` imports it, makes it implicit and wraps it round Z with Remap
Cylindrical Body (Y mapping length = Wrap Length). r and z are exact under that map and Y is
exactly the angle, so the section at every angle is the one `ShankSpec` designed. The taper
law: the full section until `--taper-from` degrees from the head, then a cosine ease to the
bottom (no crease at the shoulders or the bottom). The thin end must itself be a valid band
(floors, edge round): a 1.0 mm court bottom needs `--edge-round 0.15`.

The gate: the band checks measured about the axis (bore Ø, the widest width, the largest
outer Ø, walls against the thinnest station's edge), volume vs nTop, **section profile** (the
built width and thickness at 12 angles against the design, ± 0.06 mm: an unwrapped export or
a wrong wrap length fails here) and the design volume against the independent sweep of the
same sections (no bar, no wrap). Files: `out\shank\<stem>\<run id>\` with the bar
(`<stem>.bar.stl`) beside the STL; stem
`ring_shank_<profile>_<label>_w<head>-<bottom>_t<head>-<bottom>[_contour1.5|_chevron2][_x2|_x2m][_split1.6]_<spec id>`,
a rope `ring_shank_rope<strands>x<turns>_<label>_d<strand>_<spec id>`.

## Next in this family

The solitaire's shank becomes a bar too (step 1d), so a head can sit on a tapered, split or
contoured shank; Celtic knotwork last. All built as bars and wrapped the same way.
