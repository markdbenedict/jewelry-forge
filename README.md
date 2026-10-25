# jewelry-forge

Parametric jewelry for resin printing and investment casting, built with nTop (implicit
modeling, run headlessly through nTopCL), checked by a Python mesh gate, rendered and
sculpted in Blender, and operated through Claude Code skills.

```
.claude/skills/   skills Claude Code loads: ntop-automate, jewelry-design-rules, ring-band, ...
ntop/recipes/     GUI recipes for building custom blocks and runner notebooks
ntop/blocks/      the custom-block library (.ntop), nTop's "My Blocks" folder points here
ntop/notebooks/   Automate-ready runner notebooks, one per product family
ntop/packages/    manifest.json + README per block (nTop community-package layout)
catalog/          YAML schema of each runner notebook's inputs
python/ntopjewel/ runner, catalog validation, jewelry tables, mesh gate, CLI
python/tests/     pytest (offline by default; nTop runs are marked slow)
blender/          jewelry_kit.py, photo.py and the organic projects
out/              scratch output (git-ignored)
```

## Quick start (Windows)

```powershell
git clone https://github.com/markdbenedict/jewelry-forge.git C:\Users\markd\src\jewelry-forge
cd C:\Users\markd\src\jewelry-forge
.\scripts\bootstrap.ps1        # venv + pip install -e python/ + ntopcl check + tests
.\.venv\Scripts\Activate.ps1
python -m ntopjewel doctor
claude                         # approve the project-scoped nTop docs MCP server when asked
```

Phase 0 ("hello band"): build the runner notebook from `ntop/recipes/band-primitive.md`,
then

```powershell
python -m ntopjewel band --size 6 --width 4 --thickness 1.3 --out out\band
```

produces `out\band\ring_band_US6.stl`, runs the mesh gate, and prints the report.

See `CLAUDE.md` for conventions and the development plan for the roadmap.
