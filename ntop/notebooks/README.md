# Runner notebooks

Automate-ready notebooks, one per product family. Each declares its inputs (names exactly
as in `catalog/<name>.yaml`), one Output (the volume from Mass Properties), and writes
files through Export blocks fed by `file_path` inputs. Run them only through
`python -m ntopjewel ...`, which validates inputs, calls `ntopcl` and runs the gate.

| Notebook | Catalog | Recipe |
| --- | --- | --- |
| `ring_band.ntop` | `catalog/ring_band.yaml` | `ntop/recipes/band-primitive.md` |
