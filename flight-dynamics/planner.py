"""The PADs a flight dynamics officer works out, from the telemetry: circularise, change plane, rendezvous, inject.

Each request returns a `Pad` (TIG as mission time, Δv prograde / normal / radial, a short text for the panel) or a
`Refusal` (why not, in a few words). TIG is the ignition time, half the burn before the event, so that the burn is
centred on it, as the burn computer expects.
"""
import math
from dataclasses import dataclass

from orbits import TWO_PI, Elements, cross, dot, hohmann, phase_angle, unit

STANDARD_GRAVITY = 9.80665
LEAD_TIME_S = 60.0                  # a PAD's TIG is at least this far ahead: time to accept it and turn ...
URGENT_LEAD_S = 10.0                # ... unless the event will not come again (a suborbital apoapsis): then this
NEARLY_CIRCULAR = 0.05              # eccentricity under which rendezvous and injection use circular-orbit sums
SAME_PLANE_DEG = 0.05               # PLANE: nothing to do under this
COPLANAR_DEG = 0.5                  # RDV, INJECT: match planes first above this

# KSP stock values (checked against the game): μ (m³/s²), radius (m), lowest safe periapsis altitude (m).
BODIES = {
    'Kerbin': {'mu': 3.5316e12, 'radius': 600000.0, 'safe_altitude': 70000.0},
    'Mun': {'mu': 6.5138398e10, 'radius': 200000.0, 'safe_altitude': 7100.0},
    'Minmus': {'mu': 1.7658e9, 'radius': 60000.0, 'safe_altitude': 5800.0},
}
# The moons' orbits around Kerbin, on rails: a, e, i, lan, argp (degrees), mean anomaly at epoch 0 (radians).
MOONS = {
    'Mun': (12000000.0, 0.0, 0.0, 0.0, 0.0, 1.7),
    'Minmus': (47000000.0, 0.0, 6.0, 78.0, 38.0, 0.9),
}


@dataclass
class Pad:
    tig_met: float
    dv: tuple           # prograde, normal, radial (m/s)
    text: str


@dataclass
class Refusal:
    text: str


# ---------- reading the telemetry ----------
def own_orbit(telemetry):
    orbit = telemetry.get('tlm/orbit', {})
    body = BODIES.get(orbit.get('body'))
    if body is None or orbit.get('a') is None or orbit.get('lan') is None:
        return None
    return elements_from(orbit, body['mu'])


def elements_from(orbit, mu):
    return Elements(a=orbit['a'], e=orbit['e'], i=math.radians(orbit['i']), lan=math.radians(orbit['lan']),
                    argp=math.radians(orbit['argp']), nu=math.radians(orbit['nu']), ut=orbit['ut'], mu=mu)


def moon_orbit(name, ut):
    a, e, i, lan, argp, mean_at_epoch = MOONS[name]
    mu = BODIES['Kerbin']['mu']
    at_epoch = Elements(a=a, e=e, i=math.radians(i), lan=math.radians(lan), argp=math.radians(argp), nu=0.0, ut=0.0, mu=mu)
    # mean anomaly 0 at true anomaly 0: shift the epoch so that the mean anomaly at UT 0 is the stock one
    return Elements(**{**at_epoch.__dict__, 'ut': -mean_at_epoch / at_epoch.mean_motion}).at(ut)


def burn_time(telemetry, delta_v):
    """Seconds at full thrust (rocket equation); 0 when the vessel cannot say."""
    vessel = telemetry.get('tlm/vessel', {})
    mass, thrust, specific_impulse = vessel.get('mass'), vessel.get('thrust_avail'), vessel.get('isp')
    if not (mass and thrust and specific_impulse):
        return 0.0
    exhaust_velocity = specific_impulse * STANDARD_GRAVITY
    return mass * exhaust_velocity / thrust * (1 - math.exp(-abs(delta_v) / exhaust_velocity))


def pad_for(telemetry, orbit, event_ut, delta_v, label, repeats_every=None):
    """A Pad for a burn centred on `event_ut`. An event too close is moved to its next occurrence; one that will not
    come again (`repeats_every` None) is kept with a shorter lead, an urgent burn being better than none."""
    clock = telemetry.get('tlm/time', {})
    half_burn = burn_time(telemetry, math.sqrt(sum(component ** 2 for component in delta_v))) / 2
    tig_ut = event_ut - half_burn
    while repeats_every and tig_ut < orbit.ut + LEAD_TIME_S:
        tig_ut += repeats_every
    if tig_ut < orbit.ut + (LEAD_TIME_S if repeats_every else URGENT_LEAD_S):
        return Refusal(f'{label}: TOO LATE')
    tig_met = clock['met'] + (tig_ut - clock['ut'])
    total = math.sqrt(sum(component ** 2 for component in delta_v))
    return Pad(round(tig_met, 1), tuple(round(component, 2) for component in delta_v), f'{label} {total:.1f}')


def usable(telemetry):
    clock = telemetry.get('tlm/time', {})
    return clock.get('met') is not None and clock.get('ut') is not None and own_orbit(telemetry) is not None


# ---------- the four requests ----------
def circularise(telemetry):
    """At apoapsis if the periapsis is below the safe altitude (or open orbit: at periapsis), else at the next apsis."""
    if not usable(telemetry):
        return Refusal('NO ORBIT DATA')
    orbit, body = own_orbit(telemetry), BODIES[telemetry['tlm/orbit']['body']]
    if not orbit.closed:
        at, nu = 'PERI', 0.0
    elif orbit.periapsis_radius - body['radius'] < body['safe_altitude']:
        at, nu = 'APO', math.pi
    else:
        at, nu = min((('APO', math.pi), ('PERI', 0.0)), key=lambda apsis: orbit.time_to(apsis[1]))
    radius = orbit.radius_at(nu)
    delta_v = math.sqrt(orbit.mu / radius) - orbit.speed_at_radius(radius)
    event_ut = orbit.ut + orbit.time_to(nu) if orbit.closed else orbit.ut + _time_to_periapsis_open(orbit)
    # The apsis comes round again only if the orbit stays clear of the atmosphere and the ground.
    repeats = orbit.closed and orbit.periapsis_radius - body['radius'] >= body['safe_altitude']
    return pad_for(telemetry, orbit, event_ut, (delta_v, 0.0, 0.0), f'CIRC {at}', orbit.period if repeats else None)


def _time_to_periapsis_open(orbit):
    """Hyperbolic: seconds to periapsis (0 if past it)."""
    e, nu = orbit.e, orbit.nu if orbit.nu < math.pi else orbit.nu - TWO_PI
    hyperbolic = 2 * math.atanh(math.sqrt((e - 1) / (e + 1)) * math.tan(nu / 2))
    mean = e * math.sinh(hyperbolic) - hyperbolic
    return max(0.0, -mean / orbit.mean_motion)


def change_plane(telemetry):
    """Into the target's plane (same body), or the equator's without a target, at the node where it is cheaper."""
    if not usable(telemetry):
        return Refusal('NO ORBIT DATA')
    orbit = own_orbit(telemetry)
    if not orbit.closed:
        return Refusal('PLANE: NOT IN ORBIT')
    target = _target_orbit(telemetry, orbit)
    wanted_normal, label = (target.normal(), 'PLANE TGT') if target else ((0.0, 0.0, 1.0), 'PLANE EQ')
    own_normal = orbit.normal()
    angle = math.degrees(math.acos(max(-1.0, min(1.0, dot(own_normal, wanted_normal)))))
    if angle < SAME_PLANE_DEG:
        return Refusal(f'{label}: IN PLANE')
    node = unit(cross(own_normal, wanted_normal))
    options = []
    for direction in (node, tuple(-x for x in node)):
        nu = orbit.true_anomaly_of(direction)
        speed = orbit.speed_at_radius(orbit.radius_at(nu))
        position = orbit.direction_at(nu)
        along_now = unit(cross(own_normal, position))           # horizontal direction of motion (circular-orbit sum)
        along_after = unit(cross(wanted_normal, position))
        change = tuple(speed * (after - now) for after, now in zip(along_after, along_now))
        options.append((math.sqrt(dot(change, change)), nu, (dot(change, along_now), dot(change, own_normal), 0.0)))
    _, nu, delta_v = min(options)
    return pad_for(telemetry, orbit, orbit.ut + orbit.time_to(nu), delta_v, f'{label} {angle:.1f}DEG', orbit.period)


def _target_orbit(telemetry, orbit):
    target = telemetry.get('tlm/target', {})
    target_orbit = target.get('orbit') if target.get('set') else None
    if not target_orbit or target_orbit.get('body') != telemetry['tlm/orbit']['body']:
        return None
    return elements_from(target_orbit, orbit.mu).at(orbit.ut)


def rendezvous(telemetry):
    """A Hohmann transfer to the target's orbit, timed so that both arrive together. Both orbits nearly circular and
    in the same plane (else: CIRC or PLANE first)."""
    if not usable(telemetry):
        return Refusal('NO ORBIT DATA')
    orbit = own_orbit(telemetry)
    target = _target_orbit(telemetry, orbit)
    if target is None:
        return Refusal('RDV: NO TARGET')
    return _transfer(telemetry, orbit, target, 'RDV')


def inject(telemetry, moon):
    """A Hohmann transfer from a parking orbit around Kerbin to `moon`'s orbit, timed to meet the moon."""
    if not usable(telemetry):
        return Refusal('NO ORBIT DATA')
    if telemetry['tlm/orbit']['body'] != 'Kerbin':
        return Refusal('INJECT: NOT AT KERBIN')
    orbit = own_orbit(telemetry)
    return _transfer(telemetry, orbit, moon_orbit(moon, orbit.ut), f'INJ {moon.upper()}')


def _transfer(telemetry, orbit, target, label):
    if orbit.e > NEARLY_CIRCULAR or target.e > NEARLY_CIRCULAR:
        return Refusal(f'{label}: CIRC FIRST')
    tilt = math.degrees(math.acos(max(-1.0, min(1.0, dot(orbit.normal(), target.normal())))))
    if tilt > COPLANAR_DEG and label == 'RDV':
        return Refusal('RDV: PLANE FIRST')
    first_burn, transfer_time = hohmann(orbit.mu, orbit.a, target.a)
    # When the burn starts, the target must be ahead by π − (the angle it covers during the transfer).
    wanted_phase = (math.pi - target.mean_motion * transfer_time) % TWO_PI
    phase_now = phase_angle(orbit, target)
    closing_rate = target.mean_motion - orbit.mean_motion
    synodic_period = TWO_PI / abs(closing_rate)
    wait = ((wanted_phase - phase_now) / closing_rate) % synodic_period
    pad = pad_for(telemetry, orbit, orbit.ut + wait, (first_burn, 0.0, 0.0), label, synodic_period)
    if isinstance(pad, Pad) and tilt > COPLANAR_DEG:
        pad.text = f'{label} PL {tilt:.0f}DEG'            # a moon off the plane (Minmus): fix it on the way
    return pad
