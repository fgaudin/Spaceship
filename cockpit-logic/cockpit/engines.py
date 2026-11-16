"""Engine status matrix: one LED per engine, placed as the engines sit across the vessel, so any number and layout of
engines fits without a screen.

Colours: g = giving thrust, w = lit but idle (or next to ignite, before any engine is lit), a = has fuel but gives
well under the thrust commanded, r = flamed out, or gone (it was burning in this stage and is no longer listed).
"""
from dataclasses import dataclass, field

from .settings import ENGINE_GRID_SIZE, ENGINE_WEAK_BELOW, THROTTLE_UP_ABOVE

THRUSTING, IDLE, WEAK, DEAD, OFF = 'g', 'w', 'a', 'r', '.'
SAME_PLACE_M = 0.05         # a layout narrower than this is a single engine on the axis


@dataclass
class EngineSurvey:
    cells: dict = field(default_factory=dict)       # (row, column) → colour
    engine_lost: bool = False

    def count(self, colour):
        return sum(1 for cell_colour in self.cells.values() if cell_colour == colour)

    def rows(self):
        """The matrix as the protocol wants it: one string per row, one character per LED."""
        size = ENGINE_GRID_SIZE
        return [''.join(self.cells.get((row, column), OFF) for column in range(size)) for row in range(size)]


class EngineMonitor:
    """Remembers which engines have burned in the current stage, to notice one that disappears."""

    def __init__(self):
        self.flight_and_stage = None                # (vessel name, stage number) the memory belongs to
        self.positions_seen_burning = frozenset()

    def survey(self, engines, vessel):
        """`engines`: the list of tlm/engines; `vessel`: tlm/vessel."""
        stage, throttle = vessel.get('stage'), vessel.get('throttle') or 0.0
        lit = [engine for engine in engines if engine.get('on')]
        # Before ignition nothing is lit: show the engines of the next stage instead.
        shown = lit or [engine for engine in engines if stage is not None and engine.get('stage') == stage - 1]

        if self.flight_and_stage != (vessel.get('name'), stage):
            self.flight_and_stage, self.positions_seen_burning = (vessel.get('name'), stage), frozenset()
        lit_positions = frozenset(position_of(engine) for engine in lit)
        self.positions_seen_burning |= lit_positions
        lost_positions = self.positions_seen_burning - lit_positions if lit else frozenset()

        points = [(position_of(engine), colour_of(engine, throttle)) for engine in shown]
        points += [(position, DEAD) for position in lost_positions]
        return EngineSurvey(lay_out(points), bool(lost_positions))


def position_of(engine):
    """Where the engine sits across the vessel's axis, rounded so that telemetry noise does not move it."""
    return round(engine['x'], 1), round(engine['z'], 1)


def colour_of(engine, throttle):
    if not engine.get('on'):
        return IDLE
    if not engine.get('fuel', True):
        return DEAD
    thrust, full_thrust = engine.get('thrust', 0), engine.get('max', 0)
    if throttle > THROTTLE_UP_ABOVE and full_thrust > 0 and thrust < ENGINE_WEAK_BELOW * full_thrust * throttle:
        return WEAK
    return THRUSTING if thrust > 0 else IDLE


def lay_out(points):
    """Place each ((x, z), colour) on the grid, scaled so the outermost engine is on the edge. Engines that would
    share a cell take the nearest free one; inner engines are placed first."""
    size, centre = ENGINE_GRID_SIZE, ENGINE_GRID_SIZE // 2
    widest = max([max(abs(x), abs(z)) for (x, z), _ in points] or [0.0])
    cells = {}
    inner_first = sorted(points, key=lambda point: (abs(point[0][0]) + abs(point[0][1]), point[0]))
    for (x, z), colour in inner_first:
        row = centre + (round(z / widest * centre) if widest > SAME_PLACE_M else 0)
        column = centre + (round(x / widest * centre) if widest > SAME_PLACE_M else 0)
        free_cells = [(r, c) for r in range(size) for c in range(size) if (r, c) not in cells]
        if free_cells:
            nearest = min(free_cells, key=lambda cell: ((cell[0] - row) ** 2 + (cell[1] - column) ** 2, cell))
            cells[nearest] = colour
    return cells
