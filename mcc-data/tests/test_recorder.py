"""The flight recorder: samples, flights, events."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from recorder import MAX_POINTS, Recorder  # noqa: E402
import relief  # noqa: E402


def feed(r, met, situation='flying', stage=3, thrust=0.0, alt=1000.0, q=0.0, body='Kerbin', **flight):
    r.on_message('tlm/time', {'met': met, 'ut': 1000 + met})
    r.on_message('tlm/flight', {'alt': alt, 'q': q, 'lat': 1.0, 'lon': 2.0, 'speed': 100.0, **flight})
    r.on_message('tlm/orbit', {'body': body, 'apo': 5000.0, 'peri': -500000.0, 'atm': 70000.0})
    r.on_message('tlm/vessel', {'situation': situation, 'stage': stage, 'thrust': thrust, 'thrust_avail': 1000.0})
    return [e.text for e in r.sample()]


def test_a_launch_makes_its_events():
    r = Recorder()
    feed(r, 0, situation='pre_launch', thrust=0)
    assert feed(r, 1, situation='pre_launch', thrust=900) == []
    assert feed(r, 2, thrust=900) == ['LIFTOFF']
    assert feed(r, 4, thrust=900) == ['ENGINE ON']                 # on for 2 s: an event, at the moment it started
    assert r.events[-1].t == 1 and r.launch['lat'] == 1.0
    feed(r, 10, thrust=900, q=20000.0)
    feed(r, 11, thrust=900, q=25000.0)
    assert feed(r, 12, thrust=900, q=20000.0) == ['MAX Q 25.0 kPa']
    assert feed(r, 13, stage=2, thrust=900) == ['STAGE 2']
    assert feed(r, 20, thrust=0, alt=71000.0) == ['LEFT THE ATMOSPHERE']
    assert feed(r, 22, thrust=0, alt=72000.0, situation='sub_orbital') == ['SUBORBITAL', 'ENGINE CUTOFF']


def test_the_comm_link_and_alarms_make_events_at_once():
    r = Recorder()
    feed(r, 5)
    r.on_message('tlm/comm', {'link': True})
    assert [e.text for e in r.on_message('tlm/comm', {'link': False})] == ['LOS']
    r.on_message('cw/state', {'active': []})
    assert [e.text for e in r.on_message('cw/state', {'active': ['LOW FUEL']})] == ['C&W LOW FUEL']


def test_a_new_flight_and_a_quickload():
    r = Recorder()
    for met in range(0, 50):
        feed(r, met)
    first = r.flight_number
    feed(r, 20)                                                      # quickloaded at 20 s: what came after goes
    assert r.points[-1]['t'] == 20 and r.flight_number == first
    feed(r, 0.2)                                                     # a revert to the launch: a new flight
    assert r.flight_number == first + 1 and len(r.points) == 1


def test_a_long_flight_keeps_its_length_at_half_the_resolution():
    r = Recorder()
    for met in range(MAX_POINTS + 2):
        feed(r, met)
    assert len(r.points) <= MAX_POINTS and r.points[0]['t'] == 0 and r.points[-1]['t'] == MAX_POINTS + 1
    history = r.history()
    assert len(history['columns']['t']) == len(history['columns']['alt'])


def test_a_relief_map_is_a_png_of_the_right_size():
    heights = [[(column - 4) * 100.0 for column in range(8)] for _ in range(4)]
    rows = relief.colour('Kerbin', heights, [[h < 0 for h in row] for row in heights], 600000)
    data = relief.png(rows, 8, 4)
    assert data[:8] == b'\x89PNG\r\n\x1a\n' and len(rows) == 4 and len(rows[0]) == 8 * 3


def test_the_flight_survives_a_restart():
    r = Recorder()
    feed(r, 0, situation='pre_launch')
    feed(r, 1)
    r.on_message('cw/state', {'active': ['LOW FUEL']})
    restarted = Recorder()
    restarted.restore(__import__('json').loads(__import__('json').dumps(r.state())))
    assert restarted.points == r.points and [e.text for e in restarted.events] == [e.text for e in r.events]
    assert restarted.on_message('cw/state', {'active': ['LOW FUEL']}) == []        # not a new alarm


def test_a_revert_does_not_launch_from_the_body_flown_before():
    r = Recorder()
    for met in range(100, 110):
        feed(r, met, situation='orbiting', body='Mun')               # at the Mun, then reverted to the launch
    # the clock is back at 0 while the orbit heard last still names the Mun
    r.on_message('tlm/time', {'met': 0.0, 'ut': 2000.0})
    r.sample()
    feed(r, 0.4, situation='pre_launch')
    events = feed(r, 1.0)
    assert 'LIFTOFF' in events and not any(text.startswith('SOI') for text in events)
    assert r.launch['body'] == 'Kerbin' and r.launch['lat'] == 1.0


def test_a_launch_saved_on_the_wrong_body_is_found_again_on_restore():
    r = Recorder()
    r.restore({'points': [{'t': 0.0, 'body': 'Mun', 'lat': 0.0, 'lon': 0.0},
                          {'t': 0.36, 'body': 'Kerbin', 'lat': 1.0, 'lon': 2.0},
                          {'t': 1.0, 'body': 'Kerbin', 'lat': 1.1, 'lon': 2.0}],
               'events': [{'t': 0.4, 'text': 'LIFTOFF', 'kind': 'milestone'}],
               'launch': {'lat': 0.0, 'lon': 0.0, 'body': 'Mun', 't': 0.36}})
    assert r.launch == {'lat': 1.0, 'lon': 2.0, 'body': 'Kerbin', 't': 0.4}


def test_a_mission_clock_set_again_starts_a_new_flight():
    import recorder
    r = recorder.Recorder()
    r.on_message('mission/clock', {'launch_ut': 1000.0})
    r.points = [{'t': 30.0}, {'t': 500.0}]
    r.on_message('mission/clock', {'launch_ut': 1000.4})          # the same clock (rounding): nothing
    assert len(r.points) == 2
    r.on_message('mission/clock', {'launch_ut': 9000.0})          # MET RESET: a new flight
    assert r.points == []
