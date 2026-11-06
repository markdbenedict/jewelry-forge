"""The texture probe's cases and rules, console-safe (no numpy): `ntop/recipes/texture_probe.py` builds them in nTop,
`ntopjewel.texture_probe` runs and measures them on the laptop (2026-11-06)."""
from __future__ import annotations

from . import nb_jewel as nj

TK = "ntoptoolkits.architected_materials."

# label -> (identifier candidates, highest version first; mask for the search)
CASES = {
    "Simplex": ([TK + "simplex_noise_deboss<implicit,integer,real_field,integer>"], "simplex_noise_deboss"),
    "Cellular": ([TK + "cellular_noise_deboss<implicit,real,real_field,noise_distance_enum,noise_return_enum,integer>"],
                 "cellular_noise_deboss"),
    "Roughness": ([TK + "surface_roughness<implicit,integer,real_field,integer>"], "surface_roughness"),
    "Voronoi Deboss": ([TK + "voronoi_deboss<implicit,real,integer,integer,real_field,blend_enum,real,real_field>[2.0.0]",
                        TK + "voronoi_deboss<implicit,real,integer,integer,real_field,blend_enum,real>"], "voronoi_deboss"),
    "Voronoi Emboss": ([TK + "voronoi_emboss<implicit,real,integer,integer,real_field,blend_enum,real,real_field>[2.0.0]",
                        TK + "voronoi_emboss<implicit,real,integer,integer,real_field,blend_enum,real>"], "voronoi_emboss"),
    "Triangle Wave": ([TK + "triangle_wave_texture<implicit,vector,real_field,real_field>"], "triangle_wave_texture"),
}

# the probe's numbers (notebook inputs): what each texture input gets when its name says what it is.
# The input names, measured by the first build (2026-11-06, texture_probe 0.1.0):
#   simplex_noise_deboss    Frequency (integer), Depth factor (real_field, a LENGTH), Random seed
#   cellular_noise_deboss   Frequency (real), Depth factor (real_field, a LENGTH), Distance, Return type (enums), Random seed
#   surface_roughness       Roughness frequency (integer), Roughess [sic] amplitude (real_field), Seed value
#   voronoi_deboss / _emboss  Feature size (real), Voronoi cell count, Relaxation iterations (integers), Thickness
#                           (real_field), Blend type (enum), Blend radius (real), Spatial weighting (real_field, a LENGTH)
#   triangle_wave_texture   Direction (vector), Wave height, Wave spacing (real_fields)
# "Depth factor" given a unitless number failed ("Operand A (no units) and Operand B (units of length) do not
# match"), as did Spatial weighting ("requires units of length"): both take millimetres.
SPECS = [("Seed", "int"), ("Count", "int"), ("Cells", "int"), ("Iterations", "int"), ("Frequency Count", "int"),
         ("Depth", "mm"), ("Frequency", ""), ("Cell Size", "mm"), ("Wave Spacing", "mm"), ("Wall", "mm"),
         ("Weighting", "mm"), ("Blend", "mm")]
UNITLESS = ("Frequency",)                   # unitless reals: nTopCL inputs need units, so these stay variables inside the
                                            # notebook (their PROBE_VALUES baked in at build), not notebook inputs
# Round one (6 Nov, Frequency 1.0 / Frequency Count 10): the noises' features were 9-10 mm and cellular noise at
# frequency 1 took a uniform 0.158 mm off the whole ring - the frequencies read as per METRE (nTop's SI inside), so
# round two asks 500 per metre: cells and waves about 2 mm.
PROBE_VALUES = {"Seed": 1, "Count": 3, "Cells": 200, "Iterations": 3, "Frequency Count": 500, "Depth": 0.1,
                "Frequency": 500.0, "Cell Size": 1.0, "Wave Spacing": 0.5, "Wall": 0.15, "Weighting": 1.0, "Blend": 0.0}
WAVE_DIRECTION = [0.0, 0.0, 1.0]         # along the ring axis: the waves run round the band as grooves

# (keywords in the lower-cased input name, accepted type substrings, variable) - first match wins
CASE_RULES = [
    (("seed",), ("integer",), "Seed"),
    (("freq",), ("integer",), "Frequency Count"),
    (("freq",), ("real",), "Frequency"),
    (("factor", "depth", "height", "amplitude"), ("real",), "Depth"),
    (("spacing", "period", "wavelength"), ("real",), "Wave Spacing"),
    (("thickness", "wall"), ("real",), "Wall"),
    (("weight",), ("real",), "Weighting"),
    (("size", "scale", "distance between"), ("real",), "Cell Size"),
    (("blend", "radius", "fillet", "round"), ("real",), "Blend"),
    (("cell count", "number of", "points"), ("integer",), "Cells"),
    (("iteration", "relax"), ("integer",), "Iterations"),
    (("count", "octave", "level", "detail"), ("integer",), "Count"),
]
NEUTRAL = {"real": 1.0, "integer": 1, "bool": False}

OUTPUTS = [f"Output {label}" for label in CASES]



def input_order() -> list[str]:
    return list(nj.BAND_INPUTS) + [n for n, _ in SPECS if n not in UNITLESS] + OUTPUTS


def slug(label: str) -> str:
    return label.lower().replace(" ", "_")


def match(name: str, typ: str) -> str | None:
    """The probe variable an input of this name and type takes, or None."""
    low = name.lower()
    for words, types, var in CASE_RULES:
        if any(w in low for w in words) and any(t in typ for t in types):
            return var
    return None


# ---- the products: nTop's blocks on a band, masked to the outer face -------------------------------------------
VORONOI_SPECS = [("Cell Size", "mm"), ("Cells", "int"), ("Iterations", "int"), ("Groove", "mm"), ("Weighting", "mm"),
                 ("Blend", "mm"), ("Zone Z Top", "mm"), ("Zone Z Bottom", "mm"), ("Zone Inner Radius", "mm")]
ZONE_OUTER_RADIUS_MM = 40.0            # the mask zone's outside: past any band (catalog max outer radius 25)


def add_voronoi_deboss(h, body: str, ids: dict, label: str = "Grooved") -> str:
    """nTop's voronoi deboss on `body`: half-round grooves (width = Thickness) along the walls of a 3-D voronoi
    tessellation, on EVERY face (input names measured 2026-11-06; Blend type stays at nTop's default)."""
    blk = h.add(label, *CASES["Voronoi Deboss"][0], mask="voronoi_deboss", must=[["voronoi_deboss"]])
    h.wire(body, blk, ["Body"])
    h.wire(ids["Cell Size"], blk, ["Feature size"])
    h.wire(ids["Cells"], blk, ["Voronoi cell count"])
    h.wire(ids["Iterations"], blk, ["Relaxation iterations"])
    h.wire(ids["Groove"], blk, ["Thickness"])               # a real_field: a mm variable wired in
    h.wire(ids["Blend"], blk, ["Blend radius"])
    h.wire(ids["Weighting"], blk, ["Spatial weighting"])    # a real_field, a length (measured: unitless was refused)
    h.comment(blk, "nTop's Voronoi Deboss: the cell walls carved as half-round grooves, Thickness wide and half as deep, "
                   "over the whole surface - the mask below keeps the outer face's.")
    return blk


def add_outer_face_mask(h, band_var: str, textured: str, ids: dict, label: str = "Textured") -> str:
    """Keep a texture to the outer face: the dents (band − textured) inside a zone - a hollow cylinder between the
    rims (Zone Z Bottom .. Zone Z Top, as the band's own Z Top / Z Bottom), from Zone Inner Radius (just under the
    dome) outwards - cut from the band. Returns the "Textured Band" variable. The texture is a deboss here (it only
    removes metal); an emboss would add its growth inside the zone instead."""
    import ntopjewel.nb_jewel as nj
    dents = h.subtract("Dents", band_var, [textured], comment="What the texture took off, on every face.")
    top = nj.point_block(h, "Zone Top", z_var=ids["Zone Z Top"])
    bottom = nj.point_block(h, "Zone Bottom", z_var=ids["Zone Z Bottom"])
    big = h.real_var("Zone Outer Radius", ZONE_OUTER_RADIUS_MM, "mm")
    outer = h.cylinder("Zone Outside", bottom, top, big)
    inner = h.cylinder("Zone Inside", None, None, ids["Zone Inner Radius"], z_span=(-10.0, 10.0))   # longer: the points feed one block each
    zone = h.subtract("Zone", outer, [inner], comment="The outer face's zone: between the rims, from under the dome outwards.")
    kept = h.intersect("Dents In Zone", [dents, zone])
    textured = h.subtract(label, band_var, [kept], comment="The band less the dents inside the zone: the bore, the sides and the "
                                                            "rims stay as designed; the grooves stop at the rims in a clean line.")
    return h.wrap_var("Textured Band", textured)
