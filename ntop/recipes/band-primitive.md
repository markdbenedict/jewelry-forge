# Recipe: `ring_band.ntop` — flat band from two cylinders (Phase 0 "hello band")

**Goal.** One Automate-ready notebook that takes radii and a width, writes an STL, and
reports the volume. It proves the whole chain (JSON → nTopCL → STL → mesh gate) and gives
us the first printed sizing test. Profiles (D, court, comfort fit) come in Phase 1 as a
custom block; this notebook stays as the simplest possible runner.

**Time.** 20–30 minutes in the nTop GUI. Save as `ntop/notebooks/ring_band.ntop`.

**Conventions.** Units mm. Ring axis = Z. In this Phase 0 notebook the band spans
z = 0 … Width (not centred on the origin); the gate does not care, and centring arrives
with the profile block in Phase 1. Input names must match `catalog/ring_band.yaml`
exactly (case and spaces).

**Two nTop habits that avoid most errors.**
1. *Build with plain numbers first, then turn inputs into variables.* Right-click an
   input's name → **Make Variable**. The variable inherits the input's unit. A variable
   created on its own has no unit, and a length input will refuse it (unit mismatch);
   if that happens, type the value with its unit (`9.553 mm`) into the variable.
2. *Variables are chips.* Drag a chip into an input to use it; hold CTRL while dragging
   to reuse a chip that is already placed somewhere.

## 1. Geometry (Body section)

The nTop **Cylinder** block takes **Point 1, Point 2, Radius** (the two points are the
ends of the axis).

1. **Outer** — add a Cylinder. Point 1 = `0 mm, 0 mm, 0 mm`; Point 2 = `0 mm, 0 mm, 4 mm`;
   Radius = `9.553 mm`. Rename the block `Outer` (double-click its name).
2. Right-click the **Radius** input name on `Outer` → **Make Variable**. Rename the new
   variable `Outer Radius` (it already holds 9.553 mm).
3. **Width** — the components of a Point input cannot be made variables, and a scalar
   chip dropped on the Point 2 row is rejected (it would replace the whole point). So:
   add a **Scalar** variable with the value `4 mm` (unit included) and rename it `Width`;
   add a **Point** block (X, Y, Z inputs) with X `0 mm`, Y `0 mm`, and drag the `Width`
   chip into its **Z**; then drag the Point block's name chip onto `Outer`'s **Point 2**
   row (a Point chip on a Point input is accepted). `Width` must stay a scalar; making
   the Point block itself an input gives a `point`, which the catalog rejects.
4. **Bore** — add a second Cylinder. Point 1 = `0 mm, 0 mm, -10 mm`; Point 2 =
   `0 mm, 0 mm, 40 mm` (far longer than any band, so no arithmetic is needed);
   Radius = `8.253 mm`. Rename `Bore`. Right-click Radius → Make Variable → `Bore Radius`.
5. **Band** — add **Boolean Subtract** (Modeling > Booleans). Drag `Outer` into the body
   input and `Bore` into the subtraction input. Blend type Sharp. Rename `Band`.
   *Check:* a flat ring, 19.11 mm across, 4 mm tall.
6. **Volume** — add **Mass Properties** (Modeling > Evaluation). Body = `Band`, Density
   `1 g/cm^3`. Open the block's info panel (`?`), Properties tab, and drag **Volume** into
   the notebook; rename that variable `Volume`. *Check:* ≈ 290.95 mm³
   (π · (9.553² − 8.253²) · 4).
7. **Mesh** — add **Mesh from Implicit Body** (Structures > Mesh). Body = `Band`,
   Tolerance `0.01 mm`. Right-click Tolerance → Make Variable → `Mesh Tolerance`.
   Leave feature size and sharpening at their defaults. Rename the block `Mesh`.
8. **Export** — add **Export Mesh** (Utilities > Exchange). Mesh = `Mesh`; file =
   `C:\Users\markd\src\jewelry-forge\out\band\test.stl`; STL; mm. Right-click the file
   input → Make Variable → `Output Path`.

## 2. Inputs and Output

- Drag the five variables into the **Inputs** section at the top of the notebook, in this
  order: `Outer Radius`, `Bore Radius`, `Width`, `Mesh Tolerance`, `Output Path`.
  (If your build offers right-click → *Make model input* instead, that does the same.)
- In the **Output** section type `Volume`. nTop allows one Output per notebook; the STL
  leaves through the Export Mesh block, not the Output.

| Input (exact name) | Type | Test value |
| --- | --- | --- |
| `Outer Radius` | Scalar, mm | 9.553 (US 6 bore + 1.3 mm) |
| `Bore Radius` | Scalar, mm | 8.253 (US 6 inner Ø 16.507 / 2) |
| `Width` | Scalar, mm | 4 |
| `Mesh Tolerance` | Scalar, mm | 0.01 |
| `Output Path` | Text | `...\out\band\test.stl` |

## 3. Save and verify

1. File → Save As `C:\Users\markd\src\jewelry-forge\ntop\notebooks\ring_band.ntop`.
2. PowerShell, repo root, venv active:

   ```powershell
   python -m ntopjewel templates ntop\notebooks\ring_band.ntop --catalog ring_band
   ```

   It prints the input template nTop generated and either `catalog matches the notebook`
   or the names that differ. Fix names in the GUI until it matches. (nTop spells a scalar
   `real` and a path `text` in its template; the runner copies that spelling, so those
   are not drift. A `point` where a scalar is expected is.)
3. First real run:

   ```powershell
   python -m ntopjewel band --size 6 --width 4 --thickness 1.3 --out out\band
   ```

   Expected: `ntopcl OK`, then a gate report with `PASS`, inner Ø 16.507 ± 0.05 mm,
   width 4.000, volume ≈ 290.95 mm³, sterling ≈ 3.0 g.
4. Send Claude `out\band\ring_band_US6.output.json` once: it confirms how nTop writes a
   scalar Output, which the parser currently tolerates in several shapes.

## 4. If something does not line up

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| input turns red when a variable is dropped in | variable has no unit | type the value with its unit (`9.553 mm`) into the variable, or recreate it from the input with Make Variable |
| `catalog drift: notebook declares input 'Outer radius'` | name differs by case/space | rename the variable in the GUI |
| `[E] ... Output Path` or no STL written | Export Mesh wants a Text input, or the folder does not exist | switch the variable type to Text; the runner creates the folder, but check the path |
| STL written but gate says width 50 | the bore cylinder became the band | `Outer` goes in the body input, `Bore` in the subtraction input |
| inner Ø off by exactly the thickness | radii swapped | `Outer Radius` is the larger one |
| volume differs from analytic by > 2 % | Mesh Tolerance too coarse | 0.01 mm; the gate compares against nTop's own volume as well |

## 5. What Phase 1 adds (not now)

A `Band from profile` custom block: Revolve Profile of a profile built from curves (flat,
D, court, half-round, knife-edge), centred on the origin, plus a comfort-fit bore made
by subtracting a torus of tube radius `(W²/4 + relief²) / (2·relief)` (see
`tables.torus_for_sagitta`) and a domed outer surface by intersecting with a torus the
same way. Engraving, milgrain and textures follow as separate blocks.
