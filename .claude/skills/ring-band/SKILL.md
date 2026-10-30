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
```

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
`ring_shank_<profile>_<label>_w<head>-<bottom>_t<head>-<bottom>_<spec id>`.

## Next in this family

Non-circular centrelines (chevron dips, contoured bands, double bands bridged), split and
twisted shanks, knotwork - all built as bars and wrapped the same way; then the solitaire's
shank becomes a bar too, so a head can sit on a tapered shank.
