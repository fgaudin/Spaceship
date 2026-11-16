"""Cross-pointer: one dot on a square LED matrix shows a pair of values (right / up) around a centre.

One matrix and one selector stand in for a screen: the same LEDs show how far the nose is from the burn direction,
where the docking port is, or which way the lander drifts. The scale adapts: the dot uses the finest full scale
that contains it, and a display beside the matrix says which.

Colours: w = the centre, for reference; a = the dot; g = the dot on the centre at the finest scale (nulled);
r = the dot held on the edge because the value is beyond the coarsest scale.
"""
from dataclasses import dataclass

from .settings import CROSS_POINTER_SIZE

CENTRE, DOT, NULLED, OFF_SCALE, OFF = 'w', 'a', 'g', 'r', '.'


@dataclass
class CrossPointer:
    rows: list              # the matrix as the protocol wants it: one string per row, one character per LED
    full_scale: float       # value at the edge of the matrix; None without a value
    nulled: bool            # the dot is on the centre at the finest scale


def blank_matrix(colour=OFF):
    return [colour * CROSS_POINTER_SIZE for _ in range(CROSS_POINTER_SIZE)]


def cross_pointer(right, up, full_scales):
    """`right`, `up`: the two values (None when there is nothing to show); `full_scales`: the scales, finest first."""
    if right is None or up is None:
        return CrossPointer(blank_matrix(), None, False)
    centre = CROSS_POINTER_SIZE // 2
    largest = max(abs(right), abs(up))
    full_scale = next((scale for scale in full_scales if largest <= scale), full_scales[-1])
    off_scale = largest > full_scale

    def cells_from_centre(value):
        return max(-centre, min(centre, round(value / full_scale * centre)))

    row, column = centre - cells_from_centre(up), centre + cells_from_centre(right)
    on_centre = (row, column) == (centre, centre)
    nulled = on_centre and full_scale == full_scales[0]
    grid = [[OFF] * CROSS_POINTER_SIZE for _ in range(CROSS_POINTER_SIZE)]
    grid[centre][centre] = CENTRE
    grid[row][column] = OFF_SCALE if off_scale else NULLED if nulled else DOT
    return CrossPointer([''.join(cells) for cells in grid], full_scale, nulled)
