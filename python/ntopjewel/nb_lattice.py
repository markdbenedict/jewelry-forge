"""The lattice band's notebook body, console-safe (no numpy): `ntop/recipes/ring_lattice.py` builds it in nTop,
`ntopjewel.lattice` runs and gates it on the laptop (2026-11-06).

    Band Body                      the profiled band (ring_band_profile's section, opened)
    Gyroid                         nTop's gyroid_implicit: the surface, Cell Size (cubic cells, the bar frame). Its field is
                                   the gyroid function scaled by cell / 2π, NOT a distance (measured 2026-11-06, api_facts
                                   gyroid_field_gradient 1.6): a thickness or an offset in it is that many times smaller
    Seed Sheet                     thicken_implicit: a thin seed, Seed Thickness in field units (two voxels or 0.2 mm true)
    Seed Wrapped                   Remap Cylindrical Body (Wrap Length = whole cells round the ring: X -> r, Y -> angle)
    Zone / Lattice Zone            hollow cylinders between the rims from the skin's top outwards; the lattice's
                                   reaches Lattice Inner Radius / Lattice Z Top .. Bottom - into the skin and the rims
                                   by the overlap (past the growth and the round), so the union overlaps instead of
                                   meeting on a face
    Seed Trimmed                   Band Body ∩ Lattice Zone ∩ Seed Wrapped (bounded: the mesh round trip needs it)
    Seed Re-distanced              Mesh from Implicit Body -> Implicit Body from Mesh: a true distance field of the seed
    Sheet Grown                    Offset Body by Sheet Growth, (wall − seed) / 2: exact on a distance field, the sheet
                                   uniform to the seed's share of the wall
    Lattice Trimmed                Band Body ∩ Lattice Zone ∩ Sheet Grown (the growth crossed the dome)
    Lattice Opened                 the opening by Lattice Round (offset in, re-distance, offset out): a feather edge where
                                   a sheet meets the dome nearly tangent goes, the sheet ends come back rounded
    Skin And Rims                  Band Body − Zone
    Lattice Band                   Skin And Rims ∪ Lattice Opened (sharp)
    -> Volume Integral (the Output) / Mesh from Implicit Body -> Export Mesh (Output Path)

Every number is a notebook input (ntopjewel.lattice.GyroidSpec.notebook_inputs). The gyroid block's one real input
and the thicken block's are wired by type: their names are not in the discovery dump (the first build logs them)."""
from __future__ import annotations

from . import nb_jewel as nj
from . import nb_texture as nt

GYROID = ["gyroid_implicit<real>[1.1.0]", "gyroid_implicit<real>"]
THICKEN = ["thicken_implicit<implicit,real_field>"]
LATTICE_SPECS = [("Cell Size", "mm"), ("Seed Thickness", "mm"), ("Sheet Growth", "mm"), ("Wrap Length", "mm"), ("Lattice Round", "mm"),
                 ("Lattice Round Inward", "mm"), ("Lattice Inner Radius", "mm"), ("Lattice Z Top", "mm"), ("Lattice Z Bottom", "mm")] + nt.ZONE_SPECS
INPUT_ORDER = list(nj.BAND_INPUTS) + [n for n, _ in LATTICE_SPECS] + ["Output Path"]


def add_seed_gyroid(h, ids: dict) -> str:
    """nTop's gyroid surface, thickened into the thin seed sheet and wrapped round the ring: returns the wrapped seed's id."""
    gyroid = h.add("Gyroid", *GYROID, mask="gyroid_implicit", must=[["gyroid_implicit"]])
    h.wire(ids["Cell Size"], gyroid, [h.input_of_type(gyroid, "real")])
    h.comment(gyroid, "nTop's gyroid: the surface sin x cos y + sin y cos z + sin z cos x with cubic cells of Cell Size, in the bar "
                      "frame (X radial, Y along the ring, Z axial). Its field is the function scaled by cell / 2π, not a distance "
                      "(measured 2026-11-06): a thickness in it comes out about 1.6 x smaller - hence the seed and the re-distance.")
    seed = h.add("Seed Sheet", *THICKEN, mask="thicken_implicit", must=[["thicken_implicit"]])
    h.wire(gyroid, seed, [h.input_of_type(seed, "implicit")])
    h.wire(ids["Seed Thickness"], seed, [h.input_of_type(seed, "real_field")])
    h.comment(seed, "The surface thickened into a thin seed (Thicken Body, symmetric about the surface): Seed Thickness is in the "
                    "field's units, about 1.6 x the millimetres it comes out at.")
    wrapped = h.remap_cylindrical("Seed Wrapped", seed, ids["Wrap Length"])
    h.comment(wrapped, "The seed wrapped round the ring axis: Wrap Length is a whole number of cells, so the pattern closes on itself.")
    return wrapped


def add_grown_sheet(h, band_var: str, lzone_var: str, wrapped: str, ids: dict) -> str:
    """The seed trimmed to the band inside the grown zone, re-distanced (the mesh round trip: a true distance field) and
    grown to the wall by an Offset (exact on a distance field), then trimmed again (the growth crossed the dome).
    Returns the trimmed sheet's id."""
    seed_trimmed = h.intersect("Seed Trimmed", [band_var, lzone_var, wrapped],
                               comment="The wrapped seed inside the band and the grown zone: bounded, so it can be meshed.")
    exact = nj.add_redistance(h, "Seed", seed_trimmed, h.blocks["Mesh Tolerance"])
    h.comment(exact, "The seed with a true distance field (Mesh from Implicit Body at the Mesh Tolerance -> Implicit Body from Mesh): "
                     "an Offset of it moves its faces by exactly the offset.")
    grown = h.offset("Sheet Grown", exact, ids["Sheet Growth"])
    h.comment(grown, "The seed grown to the wall: Sheet Growth = (wall − seed) / 2 each side, uniform to the seed's share of the wall.")
    return h.intersect("Lattice Trimmed", [band_var, lzone_var, grown],
                       comment="Trimmed again: the growth crossed the dome, and reached further into the skin and the rims (inside them).")


def body(h, p, values, test_output):
    """The `_body(h, p, values, test_output)` of ring_lattice.ntop."""
    nj.add_band_inputs(h, values)
    ids = nj.add_typed_inputs(h, LATTICE_SPECS, values)
    out_var = nj.path_variable(h, "Output Path", test_output)
    with h.section("Band"):
        band = nj.add_profiled_band(h)
    with h.section("Lattice"):
        wrapped = add_seed_gyroid(h, ids)
    with h.section("Zone"):
        big = h.real_var("Zone Outer Radius", nt.ZONE_OUTER_RADIUS_MM, "mm")
        zone = nt.add_zone(h, ids, big_var=big, comment="The lattice's zone: between the rims, from the skin's top outwards; the band loses it.")
        lzone = h.wrap_var("Lattice Zone Body",
                           nt.add_zone(h, ids, label="Lattice Zone", top="Lattice Z Top", bottom="Lattice Z Bottom", inner="Lattice Inner Radius",
                                       big_var=big, comment="The same zone grown into the skin and the rims by the overlap: what the lattice "
                                                            "fills, so it is united overlapping, never meeting the skin on a face."))
    with h.section("Lattice In Zone"):
        trimmed = add_grown_sheet(h, band, lzone, wrapped, ids)
        opened = nj.add_opening(h, trimmed, ids["Lattice Round Inward"], ids["Lattice Round"], h.blocks["Mesh Tolerance"],
                                name="Lattice Opened", base="Lattice")
        h.comment(opened, "The lattice opened by Lattice Round: a feather edge where a sheet meets the dome nearly tangent "
                          "(thinner than twice the round) goes, and the sheet ends come back rounded - castable. " + nj.OPENING_NOTE)
        skin = h.subtract("Skin And Rims", band, [zone], comment="The band less the zone: the bore skin and the rims, as designed.")
        joined = h.union("Lattice Band", [skin, opened], comment="The skin and rims with the opened lattice (sharp union; the lattice "
                                                                 "reaches into both by the overlap).")
        body_var = h.wrap_var("Lattice Band Body", joined)
    with h.section("Export"):
        integ, _mesh, export = nj.add_measure_mesh_export(h, body_var, out_var, h.blocks["Mesh Tolerance"])
    return integ, export
