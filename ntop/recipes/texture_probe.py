"""What nTop's own texture blocks do to a ring band - the field textures rest on it (2026-11-06).

nTop 6.3.3 ships texture blocks in its toolkits that take any implicit body (discovery, 5 Nov):

    simplex_noise_deboss<implicit,integer,real_field,integer>                       (names unknown)
    cellular_noise_deboss<implicit,real,real_field,noise_distance_enum,noise_return_enum,integer>
        Body, Frequency, Depth factor, Distance, Return type, Random seed
    surface_roughness<implicit,integer,real_field,integer>                          (names unknown)
    voronoi_deboss / voronoi_emboss<implicit,real,integer,integer,real_field,blend_enum,real,real_field>[2.0.0]
                                                                                    (names unknown)
    triangle_wave_texture<implicit,vector,real_field,real_field>
        Body, Direction, Wave height, Wave spacing

None says what its numbers mean in millimetres (a "Depth factor", a "Frequency"), whether its enums have
defaults nTopCL accepts unset (the API can set no enum), or where on a band it acts - the outer face only, or
the bore and the rims too. So, as with points_probe and transform_probe, a probe: every block on its own copy
of the plain band (US 6 court 4 x 1.6, opened, Mesh Tolerance 0.05), each exported to its own STL by one
nTopCL run, and Python measures every STL against the designed section (`ntopjewel.texture_probe`: depth
range, how much of each face is touched, feature size, volume taken).

Input names are matched at build time by keywords (CASE_RULES below) and every match is logged in the
result, so a block whose names differ from the guess still builds and says what it got; an input no rule
matches is left at nTop's default (enums) or set to a logged neutral value. The probe numbers are notebook
inputs, so a second probe with other numbers is `texture-probe --set ...`, not a rebuild.

    python -m ntopjewel api build texture_probe      # nTop in the foreground, Python Console open
    python -m ntopjewel texture-probe                 # nTopCL + the measurements (out\\texture_probe)
"""
from __future__ import annotations

from pathlib import Path

from ntopjewel import nb_jewel as nj
from ntopjewel import nb_texture as nt

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
CASES, SPECS, PROBE_VALUES = nt.CASES, nt.SPECS, nt.PROBE_VALUES
OUTPUTS = nt.OUTPUTS
INPUT_ORDER = nt.input_order()

DEFAULTS = {
    "values": {},
    "input_order": INPUT_ORDER,
    "test_output": str(REPO / "out" / "api" / "texture_probe_band.stl"),
    "save_to": str(REPO / "ntop" / "notebooks" / "texture_probe.ntop"),
    "recipe_to": str(REPO / "ntop" / "recipes" / "texture_probe.recipe.json"),
    "pause": False,
    "lazy_ok": True,          # nTopCL is the test: the toolkit blocks' enums are set only by their defaults
    "fresh": True,
    "wait_s": 120,
    "volume_hint": "the plain US 6 court 4 x 1.6 band (the Output): about 306 mm³",
}


def prepare(params: dict, work_dir: Path) -> dict:
    """Laptop side: the band's numbers and the probe's."""
    from ntopjewel import texture_probe
    v = texture_probe.notebook_inputs(texture_probe.probe_band(), {k: "" for k in OUTPUTS})
    for k in OUTPUTS:
        v.pop(k)
    params["values"] = {**v, **(params.get("values") or {})}
    return params


def _texture(h, label: str, idents: list[str], mask: str, band: str, ids: dict) -> str:
    """One texture block on the band, every input matched by name (logged); returns the block id."""
    blk = h.add(label, *idents, mask=mask, must=[[mask]])
    got = []
    for inp in h.inputs(blk):
        name, typ = inp["name"], str(inp.get("type", ""))
        if "implicit" in typ:
            h.wire(band, blk, [name])
            got.append(f"{name} <- Band Body")
        elif "enum" in typ:
            got.append(f"{name} ({typ}) left at nTop's default")
        elif "vector" in typ:
            h.set(blk, [name], list(nt.WAVE_DIRECTION))
            got.append(f"{name} = {nt.WAVE_DIRECTION}")
        else:
            var = nt.match(name, typ)
            if var is not None:
                h.wire(ids[var], blk, [name])
                got.append(f"{name} ({typ}) <- {var}")
            else:
                base = next((k for k in nt.NEUTRAL if k in typ), None)
                if base is None or "field" in typ:     # a real_field cannot be set: wire a neutral variable
                    nv = h.real_var(f"{label} {name}", 1.0, "")
                    h.wire(nv, blk, [name])
                    got.append(f"{name} ({typ}) <- 1.0 (no rule: a neutral variable)")
                else:
                    h.set(blk, [name], nt.NEUTRAL[base])
                    got.append(f"{name} ({typ}) = {nt.NEUTRAL[base]} (no rule)")
    h.log.append(f"{label}: " + "; ".join(got))
    h.comment(blk, f"Probe: nTop's {mask} on the plain band. Inputs: " + "; ".join(got))
    return blk


def _body(h, p, values, test_output):
    nj.add_band_inputs(h, values)
    ids = nj.add_typed_inputs(h, [s for s in SPECS if s[0] not in nt.UNITLESS], values)
    for name in nt.UNITLESS:                     # unitless: variables inside the notebook, not inputs (nTopCL wants units)
        ids[name] = h.real_var(name, float(values.get(name, PROBE_VALUES[name])), "")
    outs = {label: nj.path_variable(h, f"Output {label}", str(Path(test_output).with_name(f"texture_probe_{nt.slug(label)}.stl")))
            for label in CASES}
    with h.section("Band"):
        band = nj.add_profiled_band(h)
    export = None
    for label, (idents, mask) in CASES.items():
        with h.section(label):
            blk = _texture(h, label, idents, mask, band, ids)
            mesh = h.mesh(f"{label} Mesh", blk, h.blocks["Mesh Tolerance"])
            exp = h.add(f"{label} Export", mask="export", must=nj.EXPORT)
            h.wire(mesh, exp, ["Mesh"])
            h.wire(outs[label], exp, nj.EXPORT_PATH_IN)
            export = export or exp
    with h.section("Result"):                    # the Output: the plain band's volume (cheap, and a check of the band)
        integ = h.add("Volume Integral", mask="volume_integral", must=nj.VOLUME_INTEGRAL)
        h.wire(band, integ, h.input_of_type(integ, "implicit"))
        one = h.real_var("One", 1.0, "")
        h.wire(one, integ, h.input_of_type(integ, "real_field"))
    return integ, export


def build(notebook, params: dict | None = None) -> dict:
    """Entry point for `api build texture_probe`."""
    return nj.standard_build(notebook, params, DEFAULTS, _body, "texture_probe")
