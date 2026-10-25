# Recipe: `ring_band.ntop` — flat band from two cylinders (Phase 0 "hello band")

**Goal.** One Automate-ready notebook that takes radii and a width, writes an STL, and
reports the volume. It proves the whole chain (JSON → nTopCL → STL → mesh gate) and gives
us the first printed sizing test. Profiles (D, court, comfort fit) come in Phase 1 as a
custom block; this notebook stays as the simplest possible runner.

**Time.** 20–30 minutes in the nTop GUI. Save as `ntop/notebooks/ring_band.ntop`.

**Conventions.** Units mm. Ring axis = Z, band centred on the origin (z from −Width/2 to
+Width/2). Input names must match `catalog/ring_band.yaml` exactly (case and spaces).

nTop lets you type a variable's name, or a short expression such as `Width / 2`, into
any scalar field. Where a step says *type an expression*, do that; if your build refuses
the expression, use a Math > Operations block (Divide, Add) to compute the same number.

## 1. Variables (these become the notebook inputs)

Add five variable blocks (type the value, then rename the block with F2 / double-click):

| Variable name (exact) | Type | Test value | Notes |
| --- | --- | --- | --- |
| `Outer Radius` | Scalar, mm | 9.553 | bore radius + thickness; US 6, 1.3 mm band |
| `Bore Radius` | Scalar, mm | 8.253 | US 6 inner diameter 16.507 / 2 |
| `Width` | Scalar, mm | 4.0 | |
| `Mesh Tolerance` | Scalar, mm | 0.01 | Mesh from Implicit Body tolerance |
| `Output Path` | File Path (or Text) | `C:\Users\markd\src\jewelry-forge\out\band\test.stl` | Python overwrites this per run |

Right-click each → **Make model input** (or drag it into the **Inputs** section). The
Inputs section should list exactly these five, in this order.

## 2. Geometry (Body section)

1. **Outer cylinder** — Create > Primitives > **Cylinder**.
   Radius = `Outer Radius`, Height = `Width`. Centre it on the origin along Z: if the
   block has a Frame/origin input, set the origin to `(0, 0, -Width / 2)` with the axis
   along +Z. Rename the block `Outer`.
   *Check:* select it; the Properties panel bounding box should read z −2.0 … +2.0 with
   the test values.
2. **Bore cylinder** — another Cylinder. Radius = `Bore Radius`, Height = `Width + 2`,
   origin `(0, 0, -Width / 2 - 1)`. Rename `Bore`. (1 mm past each face so the subtract
   cuts clean through.)
3. **Band** — Modeling > Booleans > **Boolean Subtract**. Body = `Outer`, Subtraction
   body (or Bodies list) = `Bore`. Blend type **Sharp**, Blend radius 0. Rename `Band`.
   *Check:* a flat ring, 19.11 mm across, 4 mm tall.
4. **Volume** — Modeling > Evaluation > **Mass Properties**. Body = `Band`, Density = 1
   (any unit; we read the volume). Rename the block `Mass Properties`. Open its
   properties and drag the **Volume** value out as a variable; name that variable
   `Volume`. *Check:* ≈ 290.95 mm³ for the test values (π·(9.553² − 8.253²)·4).
5. **Mesh** — Structures > Mesh > **Mesh from Implicit Body**. Body = `Band`,
   Tolerance = `Mesh Tolerance`, Min feature size 0.1 mm (default sharpen settings).
   Rename `Mesh`.
6. **Export** — Utilities > Exchange > **Export Mesh**. Mesh = `Mesh`, File = `Output Path`,
   format STL (binary), units mm. Rename `Export Mesh`.

## 3. Output

In the **Output** section type `Volume` (the variable from step 4). nTop allows one
Output per notebook; the STL leaves through the Export Mesh block, not the Output.

## 4. Save and verify

1. Save as `ntop/notebooks/ring_band.ntop` (File > Save As into the repo clone).
2. In PowerShell, from the repo root with the venv active:

   ```powershell
   python -m ntopjewel templates ntop\notebooks\ring_band.ntop --catalog ring_band
   ```

   It prints the input template nTop generated and either `catalog matches the notebook`
   or the names that differ. Fix names in the GUI until it matches.
3. First real run:

   ```powershell
   python -m ntopjewel band --size 6 --width 4 --thickness 1.3 --out out\band
   ```

   Expected: `ntopcl OK`, then a gate report with `PASS`, inner Ø 16.507 ± 0.05 mm,
   width 4.000, volume ≈ 290.95 mm³, sterling ≈ 3.0 g.
4. Send Claude `out\band\ring_band_US6.output.json` once: it confirms how nTop writes a
   scalar Output, which the parser currently tolerates in several shapes.

## 5. If something does not line up

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `catalog drift: notebook declares input 'Outer radius'` | name differs by case/space | rename the variable in the GUI |
| `[E] ... Output Path` or no STL written | Export Mesh wants a Text input, or the folder does not exist | switch the variable type to Text; the runner creates the folder, but check the path |
| STL written but gate says width 6.0 | the Bore cylinder height leaked into the band | check Bore is the *subtraction* body, not `Outer` |
| inner Ø off by exactly the thickness | radii swapped | `Outer` radius is the larger one |
| volume differs from analytic by > 2 % | Mesh Tolerance too coarse | 0.01 mm; the gate compares against nTop's own volume as well |

## 6. What Phase 1 adds (not now)

A `Band from profile` custom block: Revolve Profile of a profile built from curves (flat,
D, court, half-round, knife-edge), plus a comfort-fit bore made by subtracting a torus of
tube radius `(W²/4 + relief²) / (2·relief)` (see `tables.torus_for_sagitta`) and a domed
outer surface by intersecting with a torus the same way. Engraving, milgrain and
textures follow as separate blocks.
