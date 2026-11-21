"""The PADs a flight dynamics officer works out, from the telemetry: circularise, change plane, rendezvous (or, from
the ground, the liftoff to meet the target), inject.

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

# KSP stock values (checked against the game), used only when the game's own are not there (the mock plant, or before
# mcc-data has read the bodies): μ (m³/s²), radius (m), lowest safe periapsis altitude (m).
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
# LIFTOFF (RDV TGT pressed on the ground): a direct rendezvous. The ascent burns low and almost level until the
# apoapsis reaches the target's height (a little under it), coasts up to it, and CIRC there matches the target, timed
# to be there when we are. Low orbits around a moon are all about the same height, so an insertion beside a parking
# orbit drifts towards the target over days: the phase must be right at the liftoff. The profile is the one flown from
# the panels in KSP (Mun, 2026-11-21: cutoff 1.6 km above the site climbing 2.5°, 34 s of burn, 135° and 950 s of coast).
APO_UNDER_TARGET_M = 1000.0         # the insertion's apoapsis under the target's orbit: no collision, a short close-in
CUTOFF_ABOVE_SITE_M = 1600.0        # the engine stops this high above the site ...
CUTOFF_CLIMB_DEG = 2.5              # ... climbing at this angle
ASCENT_LOSSES = 1.09                # Δv of the burn: the speed at cutoff and this share for gravity and steering
SITE_STATES = ('landed', 'splashed', 'pre_launch')
CLOSE_IN_RANGE_M = 25000.0          # RDV: a target this near is closed in on the RDV panel, not with a transfer
TERRAIN_MARGIN = 1.1                # an airless body's safe periapsis: its highest terrain and a tenth more
UNKNOWN_TERRAIN = 0.05              # ... or this fraction of its radius when nobody has measured the terrain


@dataclass
class Pad:
    tig_met: float
    dv: tuple           # prograde, normal, radial (m/s)
    text: str


@dataclass
class Refusal:
    text: str


# ---------- reading the telemetry ----------
def body_of(telemetry, name):
    """{'mu', 'radius', 'safe_altitude'} of a body as the game has it: the body flown from tlm/orbit (the gateway
    sends its μ, radius and atmosphere), the others from mcc/bodies (mcc-data reads them from KSP; JNSQ's Kerbin is
    2.7 times stock's). Stock's when neither has it; None for a body nobody knows."""
    orbit = telemetry.get('tlm/orbit', {})
    here = orbit if orbit.get('body') == name else {}
    live = ((telemetry.get('mcc/bodies') or {}).get('bodies') or {}).get(name) or {}
    stock = BODIES.get(name, {})
    mu = here.get('mu') or live.get('mu') or stock.get('mu')
    radius = here.get('radius') or live.get('radius') or stock.get('radius')
    if not (mu and radius):
        return None
    if 'atm' in here:
        atmosphere = here['atm'] or 0.0
    elif live:
        atmosphere = live.get('atmosphere') or 0.0
    else:
        return dict(stock)
    if atmosphere:
        safe = atmosphere
    elif live.get('highest'):
        safe = live['highest'] * TERRAIN_MARGIN
    elif stock:
        safe = stock['safe_altitude'] * radius / stock['radius']        # the terrain grows with the body
    else:
        safe = UNKNOWN_TERRAIN * radius
    return {'mu': mu, 'radius': radius, 'safe_altitude': safe}


def own_orbit(telemetry):
    orbit = telemetry.get('tlm/orbit', {})
    body = body_of(telemetry, orbit.get('body'))
    if body is None or orbit.get('a') is None or orbit.get('lan') is None:
        return None
    return elements_from(orbit, body['mu'])


def elements_from(orbit, mu):
    return Elements(a=orbit['a'], e=orbit['e'], i=math.radians(orbit['i']), lan=math.radians(orbit['lan']),
                    argp=math.radians(orbit['argp']), nu=math.radians(orbit['nu']), ut=orbit['ut'], mu=mu)


def moon_parent(telemetry, name):
    """The body `name` orbits: from mcc/bodies, else Kerbin for stock's moons. None for one nobody knows."""
    live = ((telemetry.get('mcc/bodies') or {}).get('bodies') or {}).get(name) or {}
    if live.get('orbit') and live.get('parent'):
        return live['parent']
    return 'Kerbin' if name in MOONS else None


def moon_orbit(name, ut, telemetry=None):
    """The moon's orbit at `ut`: the game's (mcc/bodies) when there, else stock's."""
    telemetry = telemetry or {}
    live = ((telemetry.get('mcc/bodies') or {}).get('bodies') or {}).get(name) or {}
    parent = moon_parent(telemetry, name)
    mu = (body_of(telemetry, parent) or {}).get('mu')
    if live.get('orbit') and mu:
        rails = live['orbit']
        a, e, i, lan, argp = rails['a'], rails['e'], rails['i'], rails['lan'], rails['argp']
        mean_at_epoch, epoch = rails['m0'], rails['epoch']
    else:
        (a, e, i, lan, argp, mean_at_epoch), epoch, mu = MOONS[name], 0.0, BODIES['Kerbin']['mu']
    at_periapsis = Elements(a=a, e=e, i=math.radians(i), lan=math.radians(lan), argp=math.radians(argp), nu=0.0,
                            ut=0.0, mu=mu)
    # true anomaly 0 is mean anomaly 0: the moon was at periapsis mean_at_epoch / n before the epoch
    return Elements(**{**at_periapsis.__dict__, 'ut': epoch - mean_at_epoch / at_periapsis.mean_motion}).at(ut)


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
    orbit, body = own_orbit(telemetry), body_of(telemetry, telemetry['tlm/orbit']['body'])
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
    in the same plane (else: CIRC or PLANE first). On the ground: the liftoff to meet the target."""
    if not usable(telemetry):
        return Refusal('NO ORBIT DATA')
    if telemetry.get('tlm/vessel', {}).get('situation') in SITE_STATES:
        return liftoff(telemetry)
    orbit = own_orbit(telemetry)
    target = _target_orbit(telemetry, orbit)
    if target is None:
        return Refusal('RDV: NO TARGET')
    # near and on about the same orbit, a transfer waits for the next lap: days around a moon (64 h after a liftoff)
    if (telemetry.get('tlm/target', {}).get('range') or math.inf) < CLOSE_IN_RANGE_M:
        return Refusal('RDV: CLOSE IN')
    return _transfer(telemetry, orbit, target, 'RDV')


def inject(telemetry, moon):
    """A Hohmann transfer from a parking orbit around the moon's planet to `moon`'s orbit, timed to meet the moon."""
    if not usable(telemetry):
        return Refusal('NO ORBIT DATA')
    parent = moon_parent(telemetry, moon)
    if parent is None:
        return Refusal(f'INJECT: NO {moon.upper()}')
    if telemetry['tlm/orbit']['body'] != parent:
        return Refusal(f'INJECT: NOT AT {parent.upper()}')
    orbit = own_orbit(telemetry)
    return _transfer(telemetry, orbit, moon_orbit(moon, orbit.ut, telemetry), f'INJ {moon.upper()}')


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


# ---------- liftoff to meet a target in orbit ----------
def liftoff(telemetry):
    """RDV TGT on the ground: a PAD whose TIG is the liftoff (the EVENT TIMER on TIG counts down to it), its Δv the
    ascent's and the CIRC's, and in the text the launch azimuth and the apoapsis to cut off on: `LIFT AZ088 AP 29`.
    Timed so that the target reaches the apoapsis when we do; the azimuth is along the target's plane at the site."""
    orbit = own_orbit(telemetry)
    body_name = telemetry['tlm/orbit']['body']
    body = body_of(telemetry, body_name)
    target = _target_orbit(telemetry, orbit)
    if target is None:
        return Refusal('RDV: NO TARGET')
    if telemetry['tlm/orbit'].get('atm'):
        return Refusal('LIFTOFF: AIRLESS ONLY')
    flight = telemetry.get('tlm/flight', {})
    site_altitude = max(0.0, (flight.get('alt') or 0.0) - (flight.get('radar') or 0.0))
    apoapsis_radius = target.a - APO_UNDER_TARGET_M
    if apoapsis_radius < body['radius'] + site_altitude + 2 * CUTOFF_ABOVE_SITE_M:
        return Refusal('LIFTOFF: TGT TOO LOW')
    rotation_period = (((telemetry.get('mcc/bodies') or {}).get('bodies') or {}).get(body_name) or {}).get('rotation_period')
    spin = TWO_PI / rotation_period if rotation_period else 0.0
    site_now = orbit.direction_at(orbit.nu)                 # a landed vessel's orbit holds where it stands
    delta_v, ascent_time, ascent_angle = ascent(telemetry, orbit.mu, body['radius'] + site_altitude, apoapsis_radius)
    # at the apoapsis the target must be where we are: it covers n·T during the ascent, we cover the ascent's angle
    wanted_lead = (ascent_angle - target.mean_motion * ascent_time) % TWO_PI
    normal = target.normal()
    closing_rate = target.mean_motion - spin * normal[2]    # the site turns with the body, the target goes round
    site_at = lambda dt: _turned(site_now, spin * dt)
    lead_at = lambda dt: _lead(site_at(dt), target.at(orbit.ut + dt), normal)
    wait = ((wanted_lead - lead_at(0.0)) % TWO_PI) / closing_rate
    for _ in range(3):
        if wait < LEAD_TIME_S:
            wait += TWO_PI / closing_rate
        for _ in range(20):
            step = (wanted_lead - lead_at(wait) + math.pi) % TWO_PI - math.pi
            wait += step / closing_rate
            if abs(step) < 1e-6:
                break
        if wait >= LEAD_TIME_S:
            break
    azimuth = _azimuth(site_at(wait), normal)
    clock = telemetry['tlm/time']
    tig_met = clock['met'] + (orbit.ut + wait - clock['ut'])
    apoapsis_km = (apoapsis_radius - body['radius']) / 1000
    return Pad(round(tig_met, 1), (round(delta_v, 1), 0.0, 0.0), f'LIFT AZ{azimuth:03.0f} AP{apoapsis_km:3.0f}')


def ascent(telemetry, mu, site_radius, apoapsis_radius):
    """(Δv, seconds from liftoff to the apoapsis, angle covered around the body) of the direct ascent: a burn to the
    cutoff, CUTOFF_ABOVE_SITE_M up and climbing CUTOFF_CLIMB_DEG, on an orbit whose apoapsis is `apoapsis_radius`; the
    coast up to it; CIRC there."""
    cutoff_radius = site_radius + CUTOFF_ABOVE_SITE_M
    climb = math.radians(CUTOFF_CLIMB_DEG)
    # vis-viva and angular momentum at the cutoff and the apoapsis: v_c r_c cos γ = v_a r_a, v² − 2μ/r the same
    ratio = (cutoff_radius * math.cos(climb) / apoapsis_radius) ** 2
    speed_cutoff = math.sqrt(2 * mu * (1 / cutoff_radius - 1 / apoapsis_radius) / (1 - ratio))
    a = 1 / (2 / cutoff_radius - speed_cutoff ** 2 / mu)
    e = apoapsis_radius / a - 1
    h = speed_cutoff * cutoff_radius * math.cos(climb)
    nu_cutoff = math.acos(max(-1.0, min(1.0, (h ** 2 / (mu * cutoff_radius) - 1) / e)))
    coast = Elements(a=a, e=e, i=0.0, lan=0.0, argp=0.0, nu=nu_cutoff, ut=0.0, mu=mu)
    burn_delta_v = speed_cutoff * ASCENT_LOSSES
    circularise_delta_v = math.sqrt(mu / apoapsis_radius) - h / apoapsis_radius
    burn = burn_time(telemetry, burn_delta_v) or burn_delta_v / (2 * STANDARD_GRAVITY)     # unknown engine: 2 g
    burn_angle = speed_cutoff / 2 * burn / site_radius      # downrange while burning: about half the final speed
    return (burn_delta_v + circularise_delta_v, burn + coast.time_to(math.pi),
            burn_angle + (math.pi - nu_cutoff))


def _turned(vector, angle):
    """Turned by `angle` about the body's axis (z), the way it spins."""
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    return (vector[0] * cos_a - vector[1] * sin_a, vector[0] * sin_a + vector[1] * cos_a, vector[2])


def _lead(site, target, normal):
    """How far the target is ahead of the site, in the target's plane, in its direction of motion (0 to 2π)."""
    in_plane = unit(tuple(x - dot(site, normal) * n for x, n in zip(site, normal)))
    there = target.direction_at(target.nu)
    return math.atan2(dot(cross(in_plane, there), normal), dot(in_plane, there)) % TWO_PI


def _azimuth(site, normal):
    """Degrees from north, towards east, of the target's direction of motion over the site."""
    along = unit(cross(normal, site))
    east = unit(cross((0.0, 0.0, 1.0), site))
    north = cross(site, east)
    return math.degrees(math.atan2(dot(along, east), dot(along, north))) % 360
