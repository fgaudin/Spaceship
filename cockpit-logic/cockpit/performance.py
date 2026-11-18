"""The vehicle's figures shown on several panels: local gravity, stage Δv, TWR, hover time, speeds, time to impact."""
import math

from . import settings as S


def local_gravity(cockpit):
    """m/s² at the vessel's altitude, or None for a body the cockpit does not know."""
    body = S.BODIES.get(cockpit.orbit.get('body'))
    altitude = cockpit.flight.get('alt')
    if body is None or altitude is None:
        return None
    gravitational_parameter, radius = body
    return gravitational_parameter / (radius + altitude) ** 2


def _engines_that_push(cockpit):
    """The lit engines, or before ignition the ones the next staging lights (KSP numbers stages downwards)."""
    engines = cockpit.telemetry.get('tlm/engines', {}).get('engines') or []
    lit = [engine for engine in engines if engine.get('on')]
    if lit:
        return lit
    stage = cockpit.vessel.get('stage')
    return [engine for engine in engines if stage is not None and engine.get('stage') == stage - 1]


def stage_propellant_mass(cockpit):
    """kg in the stage's tanks of what its engines burn: an ion stage counts its xenon, not the rocket fuel it carries."""
    stage = cockpit.resources.get('stage', {})
    burnt = {name for engine in _engines_that_push(cockpit) for name in engine.get('propellants') or []}
    return sum(stage.get(name, {}).get('amount', 0.0) * S.RESOURCE_KG_PER_UNIT.get(name, 0.0)
               for name in burnt or S.ROCKET_PROPELLANTS)


def stage_delta_v(cockpit):
    """Δv left in the current stage, or before ignition in the next one: the rocket equation on its propellant
    (course TM-4). None when unknown."""
    propellant_mass = stage_propellant_mass(cockpit)
    mass, specific_impulse = cockpit.vessel.get('mass'), cockpit.propulsion()[1]
    if not (mass and specific_impulse) or mass <= propellant_mass:
        return None
    return specific_impulse * S.STANDARD_GRAVITY * math.log(mass / (mass - propellant_mass))


def thrust_to_weight(cockpit):
    """Available thrust over weight in the local gravity. None when the body or the altitude is unknown."""
    gravity, mass = local_gravity(cockpit), cockpit.vessel.get('mass')
    thrust = cockpit.propulsion()[0]
    if not (gravity and mass) or thrust is None:
        return None
    return thrust / (mass * gravity)


def current_thrust_to_weight(cockpit):
    """The thrust the engines give now over the weight in the local gravity: 0 with the engines off. None when the
    body, the altitude or the mass is unknown."""
    gravity, mass, thrust = local_gravity(cockpit), cockpit.vessel.get('mass'), cockpit.vessel.get('thrust')
    if not (gravity and mass) or thrust is None:
        return None
    return thrust / (mass * gravity)


def hover_time(cockpit):
    """Seconds the stage can hold the vessel still against gravity: hovering spends Δv at the rate of the local
    gravity, so it is the stage's Δv over g. None when unknown, or when the engines cannot lift the vessel."""
    delta_v, gravity, ratio = stage_delta_v(cockpit), local_gravity(cockpit), thrust_to_weight(cockpit)
    if delta_v is None or not gravity or ratio is None or ratio < 1:
        return None
    return delta_v / gravity


def speeds_in_reference(cockpit):
    """(horizontal, vertical, total) m/s against what the SPEED REF knob selects: the orbit, or the surface (also for
    TGT: a speed against a target says nothing of the ground below). Turning with the planet only adds sideways
    speed, so the vertical speed is the same in both. Each is None when unknown."""
    flight = cockpit.flight
    vertical = flight.get('vs')
    if cockpit.selected('speed_ref', S.SPEED_MODES) != 'orbit':
        return flight.get('hs'), vertical, flight.get('speed')
    total = flight.get('v_orb')
    if total is None or vertical is None:
        return None, vertical, total
    return math.sqrt(max(total ** 2 - vertical ** 2, 0.0)), vertical, total


def time_to_impact(cockpit):
    """Seconds to the ground at the present sink rate (gravity and braking ignored). None when not sinking, or on an
    orbit that stays above the surface."""
    radar, vertical, periapsis = cockpit.flight.get('radar'), cockpit.flight.get('vs'), cockpit.orbit.get('peri')
    if radar is None or vertical is None or vertical >= -S.SINKING_ABOVE_M_S or (periapsis or 0) > 0:
        return None
    return radar / -vertical


def burn_time(cockpit):
    """Seconds until the stage is dry at the present thrust, or at full thrust while the engines are not pushing.
    None when unknown."""
    full_thrust, specific_impulse = cockpit.propulsion()
    thrust = cockpit.vessel.get('thrust') or full_thrust
    if not (thrust and specific_impulse):
        return None
    return stage_propellant_mass(cockpit) * specific_impulse * S.STANDARD_GRAVITY / thrust


def rcs_delta_v(cockpit):
    """Δv the vessel's monopropellant can give through the RCS thrusters (an estimate: see the setting). None when
    unknown."""
    mass = cockpit.vessel.get('mass')
    units = cockpit.resources.get('total', {}).get('MonoPropellant', {}).get('amount')
    if not mass or units is None:
        return None
    propellant_mass = units * S.RESOURCE_KG_PER_UNIT['MonoPropellant']
    if mass <= propellant_mass:
        return None
    return S.RCS_SPECIFIC_IMPULSE_S * S.STANDARD_GRAVITY * math.log(mass / (mass - propellant_mass))


def life_support_hours(cockpit, resource):
    """Hours the crew can live on what is aboard, at TAC Life Support's rates and without recyclers. None without a
    crew, or when the vessel does not carry the resource."""
    crew, carried = cockpit.vessel.get('crew'), cockpit.resources.get('total', {}).get(resource)
    if not crew or not carried:
        return None
    return carried['amount'] / (S.LIFE_SUPPORT_USE_PER_KERBAL_S[resource] * crew) / 3600


def time_to_atmosphere(cockpit):
    """Seconds to the top of the atmosphere at the present sink rate. None when not coming down towards it: inside it
    already, climbing, on an orbit that stays above it, or around a body without one."""
    altitude, vertical = cockpit.flight.get('alt'), cockpit.flight.get('vs')
    top, periapsis = cockpit.orbit.get('atm'), cockpit.orbit.get('peri')
    if None in (altitude, vertical, top) or altitude <= top or vertical >= -S.SINKING_ABOVE_M_S:
        return None
    if periapsis is not None and periapsis >= top:
        return None
    return (altitude - top) / -vertical
