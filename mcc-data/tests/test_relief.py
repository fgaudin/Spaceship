import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import relief  # noqa: E402


def test_biome_names_give_surfaces():
    assert relief.surface_of('IceCaps') == relief.ICE
    assert relief.surface_of('Northern Ice Shelf') == relief.ICE
    assert relief.surface_of('AridMountains') == relief.ARID_SURFACE
    assert relief.surface_of('Desert') == relief.ARID_SURFACE
    assert relief.surface_of('Tundra') == relief.TUNDRA_SURFACE
    assert relief.surface_of('Polar Lowlands') == relief.PLAIN          # the Mun's: not ice
    assert relief.surface_of('ArcticSea') == relief.PLAIN
    assert relief.surface_of(None) == relief.PLAIN


def test_ice_covers_the_sea_and_desert_is_sand():
    heights = [[-500.0, 200.0, 200.0, 200.0]] * 4
    ocean = [[True, False, False, False]] * 4
    plain = [[relief.PLAIN] * 4] * 4
    surfaces = [[relief.ICE, relief.ICE, relief.ARID_SURFACE, relief.PLAIN]] * 4
    before = relief.colour('Kerbin', heights, ocean, 600000.0, plain)
    after = relief.colour('Kerbin', heights, ocean, 600000.0, surfaces)
    pixel = lambda rows, column: tuple(rows[1][3 * column: 3 * column + 3])
    assert pixel(before, 0)[2] > pixel(before, 0)[0]                    # sea: blue
    assert min(pixel(after, 0)) > 200                                   # sea ice: white
    assert min(pixel(after, 1)) > 160                                   # ice cap: white
    red, green, blue = pixel(after, 2)
    assert red > green > blue                                           # desert: sand
    assert pixel(after, 3) == pixel(before, 3)                          # the rest unchanged
