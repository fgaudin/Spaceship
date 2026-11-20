import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from orbits import Elements, hohmann, phase_angle  # noqa: E402
from planner import BODIES, Pad, Refusal, body_of, burn_time, change_plane, circularise, inject, moon_orbit, rendezvous  # noqa: E402

MU = BODIES['Kerbin']['mu']


def telemetry(a, e=0.0, i=0.0, lan=0.0, argp=0.0, nu=0.0, ut=1000.0, met=100.0, body='Kerbin', target=None):
    tlm = {'tlm/orbit': {'body': body, 'a': a, 'e': e, 'i': i, 'lan': lan, 'argp': argp, 'nu': nu, 'ut': ut},
           'tlm/time': {'ut': ut, 'met': met},
           'tlm/vessel': {'mass': 10000.0, 'thrust_avail': 200000.0, 'isp': 320.0}}
    if target:
        tlm['tlm/target'] = {'set': True, 'orbit': {'body': body, 'ut': ut, **target}}
    return tlm


def test_kepler_round_trip_and_the_mun_position_matches_ksp():
    orbit = Elements(a=700000, e=0.2, i=0.1, lan=1.0, argp=0.5, nu=0.3, ut=0, mu=MU)
    assert abs(orbit.at(orbit.period).nu - 0.3) < 1e-9
    # read from KSP at UT 90141.0: true anomaly −29.112°
    mun = moon_orbit('Mun', 90141.0)
    assert abs(math.degrees(mun.nu) - (360 - 29.112)) < 0.01


def test_circularise_at_apoapsis_from_a_suborbital_coast():
    # apoapsis 80 km, periapsis far below: circularise at apoapsis, prograde, about 1 000 m/s or more
    apoapsis, periapsis = 680000.0, 100000.0
    tlm = telemetry(a=(apoapsis + periapsis) / 2, e=(apoapsis - periapsis) / (apoapsis + periapsis), nu=120.0)
    pad = circularise(tlm)
    assert isinstance(pad, Pad) and pad.text.startswith('CIRC APO')
    speed_at_apoapsis = math.sqrt(MU * (2 / apoapsis - 2 / (apoapsis + periapsis)))
    assert abs(pad.dv[0] - (math.sqrt(MU / apoapsis) - speed_at_apoapsis)) < 0.05 and pad.dv[1:] == (0.0, 0.0)
    assert pad.tig_met > 100.0 + 60


def test_circularise_at_the_next_apsis_when_both_are_safe():
    # 100 × 90 km, just past apoapsis: the next apsis is the periapsis, so the burn is retrograde
    apoapsis, periapsis = 700000.0, 690000.0
    tlm = telemetry(a=(apoapsis + periapsis) / 2, e=(apoapsis - periapsis) / (apoapsis + periapsis), nu=190.0)
    pad = circularise(tlm)
    assert pad.text.startswith('CIRC PERI') and pad.dv[0] < 0


def test_plane_change_to_the_equator_is_a_normal_burn_at_a_node():
    pad = change_plane(telemetry(a=700000.0, i=5.0, lan=30.0, nu=10.0))
    speed = math.sqrt(MU / 700000.0)
    expected = 2 * speed * math.sin(math.radians(5) / 2)
    assert isinstance(pad, Pad) and pad.text.startswith('PLANE EQ 5.0')
    assert abs(math.hypot(*pad.dv) - expected) < 0.5 and abs(pad.dv[1]) > 10 * abs(pad.dv[0])
    assert isinstance(change_plane(telemetry(a=700000.0, i=0.0)), Refusal)


def test_plane_change_to_a_target_plane():
    pad = change_plane(telemetry(a=700000.0, i=1.0, lan=0.0, target={'a': 720000.0, 'e': 0.0, 'i': 3.0, 'lan': 0.0, 'argp': 0.0, 'nu': 0.0}))
    assert pad.text.startswith('PLANE TGT 2.0')


def test_rendezvous_waits_for_the_phase_angle():
    # target 50 km higher, 30° ahead: the burn must wait until the target is ahead by π − n2·T
    tlm = telemetry(a=700000.0, target={'a': 750000.0, 'e': 0.0, 'i': 0.0, 'lan': 0.0, 'argp': 0.0, 'nu': 30.0})
    pad = rendezvous(tlm)
    first_burn, transfer_time = hohmann(MU, 700000.0, 750000.0)
    assert isinstance(pad, Pad) and abs(pad.dv[0] - first_burn) < 0.05
    # At the middle of the burn (TIG + half the burn time) the target must be ahead by π − n2·T.
    middle = 1000.0 + (pad.tig_met - 100.0) + burn_time(tlm, first_burn) / 2
    own = Elements(a=700000.0, e=0, i=0, lan=0, argp=0, nu=0, ut=1000.0, mu=MU)
    target = Elements(a=750000.0, e=0, i=0, lan=0, argp=0, nu=math.radians(30), ut=1000.0, mu=MU)
    wanted = (math.pi - target.mean_motion * transfer_time) % (2 * math.pi)
    assert abs(phase_angle(own.at(middle), target.at(middle)) - wanted) < 1e-4      # TIG is rounded to 0.1 s


def test_rendezvous_refusals():
    assert rendezvous(telemetry(a=700000.0)).text == 'RDV: NO TARGET'
    tilted = {'a': 750000.0, 'e': 0.0, 'i': 3.0, 'lan': 0.0, 'argp': 0.0, 'nu': 0.0}
    assert rendezvous(telemetry(a=700000.0, target=tilted)).text == 'RDV: PLANE FIRST'
    assert rendezvous(telemetry(a=700000.0, e=0.2, target={**tilted, 'i': 0.0})).text == 'RDV: CIRC FIRST'


def test_injection_to_the_mun_is_a_hohmann_transfer_timed_on_the_mun():
    pad = inject(telemetry(a=680000.0, ut=90141.0), 'Mun')
    first_burn, _ = hohmann(MU, 680000.0, 12000000.0)
    assert isinstance(pad, Pad) and pad.text.startswith('INJ MUN') and abs(pad.dv[0] - first_burn) < 0.05
    assert 800 < pad.dv[0] < 900                                  # the textbook ~860 m/s from LKO
    minmus = inject(telemetry(a=680000.0, ut=90141.0), 'Minmus')
    assert 'PL 6DEG' in minmus.text
    assert inject(telemetry(a=250000.0, body='Mun'), 'Mun').text == 'INJECT: NOT AT KERBIN'


def test_a_suborbital_apoapsis_close_ahead_is_kept_not_moved_an_orbit_later():
    # 40 s before apoapsis on a suborbital coast: the next "orbit" goes through Kerbin, so the burn stays now
    apoapsis, periapsis = 680000.0, 100000.0
    a, e = (apoapsis + periapsis) / 2, (apoapsis - periapsis) / (apoapsis + periapsis)
    orbit = Elements(a=a, e=e, i=0, lan=0, argp=0, nu=math.pi, ut=1000.0, mu=MU).at(1000.0 - 40.0)
    tlm = telemetry(a=a, e=e, nu=math.degrees(orbit.nu))
    tlm['tlm/vessel']['thrust_avail'] = 1500000.0        # a short burn: half of it is about 10 s
    pad = circularise(tlm)
    assert isinstance(pad, Pad) and 100.0 + 10 < pad.tig_met < 100.0 + 40


def test_the_service_ignores_requests_in_mcc_mode():
    import importlib.util          # by its path: mcc-data has a service.py too, and pytest may run both
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'service.py')
    spec = importlib.util.spec_from_file_location('flight_dynamics_service', path)
    service = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(service)
    answer = service.answer
    tlm = telemetry(700000.0, e=0.01)
    assert answer('fd_circ', tlm, {'mcc_mode': 1}) == (None, {'text': '', 'ok': False})
    assert answer('fd_circ', tlm, {'mcc_mode': 0})[1]['text'] != ''


# JNSQ, as the game gives it (mcc/bodies read from KSP, and tlm/orbit's figures): not stock's
JNSQ_MU, JNSQ_RADIUS = 2.5105024e13, 1600000.0
JNSQ_BODIES = {'ut': 0.0, 'bodies': {
    'Kerbin': {'radius': JNSQ_RADIUS, 'mu': JNSQ_MU, 'atmosphere': 80000.0, 'parent': 'Sun', 'orbit': {}},
    'Mun': {'radius': 400000.0, 'mu': 2.2751428e11, 'atmosphere': 0.0, 'parent': 'Kerbin', 'highest': 12000.0,
            'orbit': {'a': 90960000.0, 'e': 0.0, 'i': 0.0, 'lan': 0.0, 'argp': 0.0, 'm0': 1.7, 'epoch': 0.0}},
}}


def jnsq(a, ut=1000.0, **orbit):
    tlm = telemetry(a, ut=ut, **orbit)
    tlm['tlm/orbit'].update(mu=JNSQ_MU, radius=JNSQ_RADIUS, atm=80000.0)
    tlm['mcc/bodies'] = JNSQ_BODIES
    return tlm


def test_the_game_s_bodies_replace_stock_s():
    tlm = jnsq(1700000.0)
    assert body_of(tlm, 'Kerbin') == {'mu': JNSQ_MU, 'radius': JNSQ_RADIUS, 'safe_altitude': 80000.0}
    assert body_of(tlm, 'Mun')['safe_altitude'] == 12000.0 * 1.1          # an airless body: its highest terrain
    assert body_of({}, 'Kerbin') == BODIES['Kerbin']                      # the mock plant: stock's


def test_circularise_in_jnsq_uses_its_kerbin():
    # 100 km × 30 km around JNSQ's Kerbin: the periapsis is in its 80 km atmosphere, so at apoapsis
    apoapsis, periapsis = JNSQ_RADIUS + 100000.0, JNSQ_RADIUS + 30000.0
    pad = circularise(jnsq((apoapsis + periapsis) / 2, e=(apoapsis - periapsis) / (apoapsis + periapsis), nu=120.0))
    speed_at_apoapsis = math.sqrt(JNSQ_MU * (2 / apoapsis - 2 / (apoapsis + periapsis)))
    assert pad.text.startswith('CIRC APO')
    assert abs(pad.dv[0] - (math.sqrt(JNSQ_MU / apoapsis) - speed_at_apoapsis)) < 0.05


def test_injection_in_jnsq_aims_at_its_mun():
    pad = inject(jnsq(JNSQ_RADIUS + 100000.0), 'Mun')
    first_burn, _ = hohmann(JNSQ_MU, JNSQ_RADIUS + 100000.0, 90960000.0)
    assert isinstance(pad, Pad) and abs(pad.dv[0] - first_burn) < 0.05
    assert moon_orbit('Mun', 0.0, jnsq(1700000.0)).a == 90960000.0
