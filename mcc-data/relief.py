"""Relief maps of the bodies, for the wall display's ground track: the terrain height sampled from the game on a
latitude-longitude grid (equirectangular, longitude −180° to 180° left to right, north up), shaded as if lit from
the north-west and coloured by height: seas, lowlands, highlands and snow on bodies with an ocean, the body's own
tint on the others. Where the game's biome says ice or desert (Kerbin's IceCaps, its Arid lands, Duna's polar caps),
the surface takes that colour instead, still shaded. Pure functions; the sampling is in service.py.
"""
import math
import struct
import zlib

WIDTH, HEIGHT = 1440, 720                   # a quarter of a degree a pixel
LIGHT_AZIMUTH_DEG, LIGHT_ELEVATION_DEG = 315.0, 40.0
TYPICAL_SLOPE = 0.22                        # the relief is exaggerated (or not) until the body's slopes average this
EXAGGERATION_RANGE = (1.0, 24.0)
# the tint of bodies without an ocean (r, g, b); others are grey
TINTS = {
    'Mun': (168, 168, 166), 'Minmus': (150, 205, 185), 'Duna': (196, 104, 70), 'Ike': (128, 122, 116),
    'Dres': (150, 140, 128), 'Moho': (140, 104, 80), 'Eeloo': (226, 226, 228), 'Gilly': (150, 116, 92),
    'Bop': (128, 104, 84), 'Pol': (208, 186, 126), 'Vall': (196, 214, 232), 'Tylo': (206, 196, 186),
    'Eve': (128, 70, 160), 'Jool': (110, 170, 60),
}
LAND = [(0.0, (58, 104, 56)), (0.12, (96, 132, 70)), (0.3, (150, 140, 88)), (0.5, (140, 110, 80)),
        (0.72, (150, 140, 132)), (0.9, (232, 232, 238)), (1.0, (250, 250, 252))]
SEA = [(0.0, (70, 128, 176)), (0.3, (38, 84, 140)), (1.0, (14, 34, 76))]
ARID = [(0.0, (214, 188, 132)), (0.2, (204, 164, 108)), (0.45, (176, 128, 86)), (0.72, (150, 132, 118)),
        (0.9, (232, 232, 238)), (1.0, (250, 250, 252))]
TUNDRA = [(0.0, (128, 136, 108)), (0.4, (140, 136, 116)), (0.72, (160, 156, 150)), (0.9, (232, 232, 238)),
          (1.0, (250, 250, 252))]
ICE_LAND, ICE_SEA = (240, 244, 250), (214, 228, 240)

# the surfaces read from the biome names (lower case, by word): the code of each in the surfaces grid
PLAIN, ICE, ARID_SURFACE, TUNDRA_SURFACE = 0, 1, 2, 3
SURFACE_WORDS = [(ICE, ('ice', 'snow', 'glacier', 'frozen')), (ARID_SURFACE, ('arid', 'desert', 'dune', 'badlands')),
                 (TUNDRA_SURFACE, ('tundra',))]


def surface_of(biome):
    """The surface code of a biome name: 'IceCaps' → ICE, 'AridLowlands' → ARID_SURFACE, 'Northern Ice Shelf' → ICE."""
    name = (biome or '').lower()
    for code, words in SURFACE_WORDS:
        if any(word in name for word in words):
            return code
    return PLAIN


def latitude_of_row(row, height=HEIGHT):
    return 90.0 - (row + 0.5) * 180.0 / height


def longitude_of_column(column, width=WIDTH):
    return -180.0 + (column + 0.5) * 360.0 / width


def blend(stops, fraction):
    fraction = min(1.0, max(0.0, fraction))
    for (start, low), (end, high) in zip(stops, stops[1:]):
        if fraction <= end:
            mix = (fraction - start) / (end - start) if end > start else 0.0
            return tuple(low[k] + (high[k] - low[k]) * mix for k in range(3))
    return stops[-1][1]


def shading(heights, radius):
    """Lambert shading of the terrain, 0..1 per pixel, from the heights (m) and the body's radius (m)."""
    rows, columns = len(heights), len(heights[0])
    azimuth, elevation = math.radians(LIGHT_AZIMUTH_DEG), math.radians(LIGHT_ELEVATION_DEG)
    light = (math.sin(azimuth) * math.cos(elevation), math.cos(azimuth) * math.cos(elevation), math.sin(elevation))
    dy = math.pi * radius / rows
    slopes = []
    for row in range(rows):
        dx = max(2 * math.pi * radius * math.cos(math.radians(latitude_of_row(row, rows))) / columns, dy * 0.05)
        up, down = heights[max(0, row - 1)], heights[min(rows - 1, row + 1)]
        line = heights[row]
        slopes.append([((line[(column + 1) % columns] - line[column - 1]) / (2 * dx), (up[column] - down[column]) / (2 * dy))
                       for column in range(columns)])
    middle = slopes[rows // 4: rows - rows // 4]                         # away from the poles' stretched pixels
    mean = sum(abs(east) + abs(north) for line in middle for east, north in line) / max(1, sum(len(line) for line in middle))
    exaggeration = min(EXAGGERATION_RANGE[1], max(EXAGGERATION_RANGE[0], TYPICAL_SLOPE / mean if mean else 1.0))
    shade = []
    for row in range(rows):
        out = []
        for slope_east, slope_north in slopes[row]:
            normal = (-slope_east * exaggeration, -slope_north * exaggeration, 1.0)
            length = math.sqrt(normal[0] ** 2 + normal[1] ** 2 + 1.0)
            out.append(max(0.0, sum(n * l for n, l in zip(normal, light)) / length))
        shade.append(out)
    return shade


def colour(name, heights, ocean, radius, surfaces=None):
    """RGB rows. `ocean`: a grid of booleans (under the sea), or None for a body without one. `surfaces`: a grid of
    surface codes (surface_of), or None: ice covers land and sea alike, desert and tundra recolour the land."""
    shade = shading(heights, radius)
    flat_shade = math.sin(math.radians(LIGHT_ELEVATION_DEG))
    land = [h for row, wet in zip(heights, ocean or [[False] * len(heights[0])] * len(heights)) for h, w in zip(row, wet) if not w]
    low, high = (min(land), max(land)) if land else (0.0, 1.0)
    deepest = min(min(row) for row in heights)
    tint = TINTS.get(name, (160, 160, 160))
    rows = []
    for row_index, row in enumerate(heights):
        line = bytearray()
        for column, height in enumerate(row):
            light = 0.6 + 0.4 * shade[row_index][column] / flat_shade
            surface = surfaces[row_index][column] if surfaces else PLAIN
            wet = bool(ocean and ocean[row_index][column])
            land_level = (height - max(low, 0.0)) / max(high - max(low, 0.0), 1.0)
            if surface == ICE:
                base = ICE_SEA if wet else ICE_LAND
                light = 1.0 if wet else 0.72 + 0.28 * shade[row_index][column] / flat_shade
            elif wet:
                base = blend(SEA, height / deepest if deepest < 0 else 0.0)
                light = 1.0
            elif surface == ARID_SURFACE:
                level = land_level if ocean else (height - low) / max(high - low, 1.0)
                base = blend(ARID, level)
            elif surface == TUNDRA_SURFACE:
                level = land_level if ocean else (height - low) / max(high - low, 1.0)
                base = blend(TUNDRA, level)
            elif ocean:
                base = blend(LAND, land_level)
            else:
                level = (height - low) / max(high - low, 1.0)
                base = tuple(channel * (0.42 + 0.58 * level ** 0.8) for channel in tint)
            line += bytes(min(255, max(0, round(channel * light))) for channel in base)
        rows.append(bytes(line))
    return rows


def png(rows, width, height):
    """An 8-bit RGB PNG of `rows` (bytes of width × 3 each)."""
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    raw = b''.join(b'\x00' + row for row in rows)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))
