"""Engine status matrix: one LED per engine, placed as the engines sit across the vessel, so any number and layout of
engines fits without a screen.

Colours: g = giving thrust, w = lit but idle (or next to ignite, before any engine is lit), a = has fuel but gives
well under the thrust commanded, r = flamed out, or gone (it was burning in this stage and is no longer listed).
"""
from dataclasses import dataclass, field

from .settings import ENGINE_GRID_SIZE, ENGINE_WEAK_BELOW, STANDARD_PRESSURE_PA, THROTTLE_UP_ABOVE

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

    def survey(self, engine_telemetry, vessel):
        """`engine_telemetry`: tlm/engines; `vessel`: tlm/vessel."""
        engines = engine_telemetry.get('engines') or []
        # The stage the engine list was read in. tlm/vessel has the stage number sooner than tlm/engines has the new
        # list: just after staging, the vessel's number with the old list would make the dropped engines look lost.
        stage = engine_telemetry.get('stage', vessel.get('stage'))
        throttle = vessel.get('throttle') or 0.0
        switched_on = [engine for engine in engines if engine.get('on')]
        lit = still_in_use(switched_on)
        # Before ignition nothing is lit: show the engines of the next stage instead.
        shown = lit or [engine for engine in engines if stage is not None and engine.get('stage') == stage - 1]

        if self.flight_and_stage != (vessel.get('name'), stage):
            self.flight_and_stage, self.positions_seen_burning = (vessel.get('name'), stage), frozenset()
        lit_positions = frozenset(position_of(engine) for engine in lit)
        spent_positions = frozenset(position_of(engine) for engine in switched_on) - lit_positions
        self.positions_seen_burning = (self.positions_seen_burning | lit_positions) - spent_positions
        lost_positions = self.positions_seen_burning - lit_positions if lit else frozenset()

        points = [(position_of(engine), colour_of(engine, throttle)) for engine in shown]
        points += [(position, DEAD) for position in lost_positions]
        return EngineSurvey(lay_out(points), bool(lost_positions))


def still_in_use(lit_engines):
    """The lit engines, less the spent ones: an engine out of fuel that is still attached while engines ignited in
    a later stage burn (KSP numbers stages downwards). It did its job; it is not a failure to stage away."""
    burning_stages = [engine.get('stage', 0) for engine in lit_engines if engine.get('fuel', True)]
    if not burning_stages:
        return lit_engines                          # everything is out of fuel: flameout, the cue to stage
    latest_stage = min(burning_stages)
    return [engine for engine in lit_engines
            if engine.get('fuel', True) or engine.get('stage', 0) <= latest_stage]


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


def propulsion(engine_telemetry, vessel, flight):
    """(thrust at full throttle, specific impulse) of what pushes the vessel: the lit engines as KSP reports them, or,
    before any engine is lit, the engines the next staging lights (KSP numbers stages downwards: stage − 1).
    None for either when unknown."""
    thrust, specific_impulse = vessel.get('thrust_avail') or 0.0, vessel.get('isp') or 0.0
    if thrust > 0 and specific_impulse > 0:
        return thrust, specific_impulse
    stage = vessel.get('stage')
    engines = engine_telemetry.get('engines') or []
    if any(engine.get('on') for engine in engines) or stage is None:
        return None, None                           # lit but giving nothing: flamed out, not "before ignition"
    next_engines = [engine for engine in engines if engine.get('stage') == stage - 1 and engine.get('rated')]
    if not next_engines:
        return None, None
    # Specific impulse falls about linearly with the outside pressure between vacuum and one atmosphere.
    atmospheres = min(1.0, (flight.get('p') or 0.0) / STANDARD_PRESSURE_PA)
    total_thrust = sum(engine['rated'] for engine in next_engines)
    # Engines burning together: their propellant flows add up, so the specific impulse is thrust-weighted harmonic.
    propellant_flow = sum(engine['rated'] / (engine['isp_vac'] + (engine['isp_sl'] - engine['isp_vac']) * atmospheres)
                          for engine in next_engines)
    return total_thrust, total_thrust / propellant_flow if propellant_flow > 0 else None
