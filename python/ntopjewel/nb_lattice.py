"""The lattice band's notebook body, console-safe (no numpy): `ntop/recipes/ring_lattice.py` builds it in nTop,
`ntopjewel.lattice` runs and gates it on the laptop (2026-11-06).

    Band Body                      the profiled band (ring_band_profile's section, opened)
    Gyroid                         nTop's gyroid_implicit: the surface, Cell Size (cubic cells, the bar frame)
    Walled Gyroid                  thicken_implicit: the sheet, Wall thick about the surface
    Lattice Wrapped                Remap Cylindrical Body (Wrap Length = whole cells round the ring: X -> r, Y -> angle)
    Zone / Lattice Zone            hollow cylinders between the rims from the skin's top outwards; the lattice's
                                   reaches Lattice Inner Radius / Lattice Z Top .. Bottom - into the skin and the rims
                                   by the overlap, so the union overlaps instead of meeting on a face
    Lattice Trimmed                Band Body ∩ Lattice Zone ∩ Lattice Wrapped
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
LATTICE_SPECS = [("Cell Size", "mm"), ("Wall", "mm"), ("Wrap Length", "mm"), ("Lattice Round", "mm"), ("Lattice Round Inward", "mm"),
                 ("Lattice Inner Radius", "mm"), ("Lattice Z Top", "mm"), ("Lattice Z Bottom", "mm")] + nt.ZONE_SPECS
INPUT_ORDER = list(nj.BAND_INPUTS) + [n for n, _ in LATTICE_SPECS] + ["Output Path"]


def add_walled_gyroid(h, ids: dict) -> str:
    """nTop's gyroid surface, thickened and wrapped round the ring: returns the wrapped sheet's id."""
    gyroid = h.add("Gyroid", *GYROID, mask="gyroid_implicit", must=[["gyroid_implicit"]])
    h.wire(ids["Cell Size"], gyroid, [h.input_of_type(gyroid, "real")])
    h.comment(gyroid, "nTop's gyroid: the surface sin x cos y + sin y cos z + sin z cos x with cubic cells of Cell Size, in the bar "
                      "frame (X radial, Y along the ring, Z axial).")
    walled = h.add("Walled Gyroid", *THICKEN, mask="thicken_implicit", must=[["thicken_implicit"]])
    h.wire(gyroid, walled, [h.input_of_type(walled, "implicit")])
    h.wire(ids["Wall"], walled, [h.input_of_type(walled, "real_field")])
    h.comment(walled, "The surface thickened into a sheet Wall thick (Thicken Body; the thickness about the surface).")
    wrapped = h.remap_cylindrical("Lattice Wrapped", walled, ids["Wrap Length"])
    h.comment(wrapped, "The sheet wrapped round the ring axis: Wrap Length is a whole number of cells, so the pattern closes on itself.")
    return wrapped


def body(h, p, values, test_output):
    """The `_body(h, p, values, test_output)` of ring_lattice.ntop."""
    nj.add_band_inputs(h, values)
    ids = nj.add_typed_inputs(h, LATTICE_SPECS, values)
    out_var = nj.path_variable(h, "Output Path", test_output)
    with h.section("Band"):
        band = nj.add_profiled_band(h)
    with h.section("Lattice"):
        wrapped = add_walled_gyroid(h, ids)
    with h.section("Zone"):
        big = h.real_var("Zone Outer Radius", nt.ZONE_OUTER_RADIUS_MM, "mm")
        zone = nt.add_zone(h, ids, big_var=big, comment="The lattice's zone: between the rims, from the skin's top outwards; the band loses it.")
        lzone = nt.add_zone(h, ids, label="Lattice Zone", top="Lattice Z Top", bottom="Lattice Z Bottom", inner="Lattice Inner Radius",
                            big_var=big, comment="The same zone grown into the skin and the rims by the overlap: what the lattice fills, "
                                                 "so it is united overlapping, never meeting the skin on a face.")
    with h.section("Lattice In Zone"):
        trimmed = h.intersect("Lattice Trimmed", [band, lzone, wrapped],
                              comment="The wrapped sheet inside the band and the grown zone.")
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
