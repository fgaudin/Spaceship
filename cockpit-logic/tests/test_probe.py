"""Probe mode: the sequencer flies the uplinked program; the panels command nothing."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cockpit import Cockpit  # noqa: E402
from cockpit.probe_sequencer import ProgramError, burnout_engines, parse_program  # noqa: E402
import pytest  # noqa: E402


def commands(messages):
    return [(m.topic, m.payload) for m in messages if m.topic.startswith('cmd/')]


class Flight:
    """A cockpit in probe mode, fed with telemetry at game time `ut` (MET = ut − 1000)."""

    def __init__(self, link=True):
        self.c = Cockpit()
        self.t = 0.0
        self.ut = 1000.0
        self.thrust = 0.0
        self.c.handle('gateway/status', {'connected': True, 'plant': 'mock'}, 0)
        self.c.handle('tlm/comm', {'link': link}, 0)
        self.feed()
        self.mode = commands(self.c.handle('probe/mode', {'on': True}, 0))

    def feed(self):
        out = self.c.handle('tlm/time', {'ut': self.ut, 'met': self.ut - 1000, 'warp': 1}, self.t)
        out += self.c.handle('tlm/vessel', {'mass': 1000.0, 'thrust': self.thrust, 'thrust_avail': 20000.0,
                                            'isp': 300.0, 'sas': False, 'throttle': 0.0}, self.t)
        return out

    def run(self, seconds, step=0.25):
        """Game and wall time go on together; every command sent meanwhile."""
        sent = []
        for _ in range(int(round(seconds / step))):
            self.t += step
            self.ut += step
            sent += commands(self.feed() + self.c.tick(self.t))
        return sent

    def send(self, topic, payload):
        return commands(self.c.handle(topic, payload, self.t))

    @property
    def state(self):
        return self.c.probe_sequencer.summary()


def test_probe_mode_closes_the_throttle_and_ignores_the_panels():
    f = Flight()
    assert f.mode == [('cmd/throttle', {'v': 0.0})]
    assert f.send('panel/eng/in/stage', {'v': 1}) == []
    assert f.send('panel/eng/in/sas', {'v': 1}) == []
    assert f.run(2) == []                       # the SAS switch is on, nothing re-commands it


def test_a_launch_program_runs_its_steps_in_time():
    f = Flight()
    f.send('probe/program', {'name': 'hop', 'steps': [
        {'t': 0, 'do': 'throttle', 'v': 1}, {'t': 1, 'do': 'stage'},
        {'t': 5, 'do': 'kick', 'pitch': 0, 'yaw': 0.4, 's': 2}, {'t': 8, 'do': 'sas_mode', 'mode': 'prograde'}]})
    assert f.state['state'] == 'loaded'
    sent = f.send('probe/exec', {'do': 'go'})
    assert sent == [('cmd/throttle', {'v': 1.0})]
    sent = f.run(1)
    assert ('cmd/stage', {}) in sent
    sent = f.run(4)
    assert ('cmd/sas', {'on': False}) in sent and ('cmd/rotate', {'pitch': 0.0, 'yaw': 0.4, 'roll': 0.0}) in sent
    sent = f.run(2)
    assert ('cmd/rotate', {'pitch': 0.0, 'yaw': 0.0, 'roll': 0.0}) in sent and ('cmd/sas', {'on': True}) in sent
    sent = f.run(1)
    assert ('cmd/sas_mode', {'mode': 'prograde'}) in sent
    assert f.state['state'] == 'done' and all(step['status'] == 'done' for step in f.state['steps'])


def test_a_burn_loads_its_pad_early_and_ends_at_the_cutoff():
    f = Flight()
    f.send('probe/program', {'steps': [{'t': 0, 'do': 'sas_mode', 'mode': 'maneuver'},
                                       {'met': 10, 'do': 'burn', 'dv': [50, 0, 0]}]})
    f.send('probe/exec', {'do': 'go'})
    assert f.c.burn_computer.pad == {'tig': 10.0, 'dv': [50.0, 0.0, 0.0]}     # the node exists for SAS MANEUVER
    assert any(topic == 'cmd/node' and 'ut' in payload for topic, payload in f.run(0.5))
    sent = f.run(9.5)
    assert ('cmd/throttle', {'v': 1.0}) in sent and f.c.burn_computer.armed
    f.thrust = 20000.0                          # 20 m/s² on 1 t: 50 m/s in 2.5 s
    sent = f.run(3)
    assert ('cmd/throttle', {'v': 0.0}) in sent
    assert f.state['state'] == 'done' and 'cutoff' in f.state['log'][-2]['text']
    assert not f.c.burn_computer.has_pad()


def test_a_burn_with_no_thrust_is_given_up():
    f = Flight()
    f.send('probe/program', {'steps': [{'met': 1, 'do': 'burn', 'dv': [5, 0, 0]}, {'met': 2, 'do': 'stage'}]})
    f.send('probe/exec', {'do': 'go'})
    sent = f.run(12)
    assert f.state['steps'][0]['status'] == 'failed' and ('cmd/stage', {}) in sent


def test_stop_closes_the_throttle_and_centres_the_inputs():
    f = Flight()
    f.send('probe/program', {'steps': [{'t': 0, 'do': 'throttle', 'v': 1}, {'t': 0, 'do': 'kick', 'pitch': 1, 's': 30}]})
    f.send('probe/exec', {'do': 'go'})
    f.run(1)
    sent = f.send('probe/exec', {'do': 'stop'})
    assert ('cmd/throttle', {'v': 0.0}) in sent and ('cmd/rotate', {'pitch': 0.0, 'yaw': 0.0, 'roll': 0.0}) in sent
    assert f.state['state'] == 'stopped' and f.state['steps'][1]['status'] == 'failed'


def test_no_link_no_uplink():
    f = Flight(link=False)
    f.send('probe/program', {'steps': [{'t': 0, 'do': 'stage'}]})
    assert f.state['state'] == 'empty' and f.state['message'] == 'NO LINK: UPLINK REFUSED'


def test_a_running_program_carries_on_without_the_link():
    f = Flight()
    f.send('probe/program', {'steps': [{'t': 3, 'do': 'stage'}]})
    f.send('probe/exec', {'do': 'go'})
    f.c.handle('tlm/comm', {'link': False}, f.t)
    assert ('cmd/stage', {}) in f.run(4)


def test_not_in_probe_mode_the_room_commands_nothing():
    c = Cockpit()
    c.handle('tlm/comm', {'link': True}, 0)
    c.handle('probe/program', {'steps': [{'t': 0, 'do': 'stage'}]}, 0)
    assert c.probe_sequencer.state == 'empty'


def test_leaving_probe_mode_stops_the_program():
    f = Flight()
    f.send('probe/program', {'steps': [{'t': 60, 'do': 'stage'}]})
    f.send('probe/exec', {'do': 'go'})
    assert ('cmd/throttle', {'v': 0.0}) in f.send('probe/mode', {'on': False})
    assert f.state['state'] == 'stopped'


@pytest.mark.parametrize('steps, error', [
    ([], 'no steps'),
    ([{'t': 0, 'do': 'warp'}], "step 1: unknown action 'warp'"),
    ([{'do': 'stage'}], 'step 1: give one of t, met or burnout'),
    ([{'t': 0, 'burnout': 1, 'do': 'stage'}], 'step 1: give one of t, met or burnout'),
    ([{'t': 0, 'do': 'stage'}, {'t': 1, 'do': 'throttle', 'v': 2}], 'step 2: v out of range (0 to 1)'),
    ([{'t': 0, 'do': 'burn', 'dv': [1, 0, 0]}], 'step 1: a burn needs its TIG as met'),
    ([{'t': 0, 'do': 'kick', 'pitch': 0.5}], 'step 1: s missing'),
    ([{'t': 0, 'do': 'sas_mode', 'mode': 'up'}], "step 1: unknown SAS mode 'up'"),
])
def test_bad_programs_are_rejected_with_the_step(steps, error):
    with pytest.raises(ProgramError, match=error.replace('(', r'\(').replace(')', r'\)')):
        parse_program({'steps': steps})


def test_stop_after_the_last_step_still_cuts_the_engine():
    """Found in KSP: the ascent program ended with the throttle open; STOP at the wanted apoapsis did nothing."""
    f = Flight()
    f.send('probe/program', {'steps': [{'t': 0, 'do': 'throttle', 'v': 1}, {'t': 0, 'do': 'stage'}]})
    f.send('probe/exec', {'do': 'go'})
    f.run(1)
    assert f.state['state'] == 'done'
    assert ('cmd/throttle', {'v': 0.0}) in f.send('probe/exec', {'do': 'stop'})


def engine(stage, drop, fuel, on=True):
    return {'x': 0.0, 'z': 0.0, 'stage': stage, 'drop': drop, 'on': on, 'fuel': fuel}


def test_burnout_watches_what_the_next_staging_drops():
    core, boosters = engine(3, 0, True), [engine(3, 2, False), engine(3, 2, False)]
    assert burnout_engines([core, *boosters], 3) == boosters          # the core burns on: the boosters are watched
    assert burnout_engines([core], 2) == [core]                       # nothing dropped next: every lit engine
    unlit_upper = engine(0, -1, True, on=False)
    assert burnout_engines([core, unlit_upper], 1) == [core]          # an engine not lit yet is not watched


def burnout_flight(engines, stage=3, engines_stage=None, delay=1):
    f = Flight()
    f.c.handle('tlm/engines', {'engines': engines, 'stage': stage if engines_stage is None else engines_stage}, 0)
    f.c.telemetry['tlm/vessel'] = {**f.c.vessel, 'stage': stage}
    original = f.feed
    def feed():
        out = original()
        f.c.telemetry['tlm/vessel']['stage'] = stage
        return out
    f.feed = feed
    f.send('probe/program', {'steps': [{'burnout': delay, 'do': 'stage'}]})
    f.send('probe/exec', {'do': 'go'})
    return f


def test_boosters_empty_core_burning_stages_after_the_delay():
    f = burnout_flight([engine(3, 0, True), engine(3, 2, False), engine(3, 2, False)], delay=1)
    assert ('cmd/stage', {}) not in f.run(0.75)
    assert ('cmd/stage', {}) in f.run(0.5)
    assert [line['text'] for line in f.state['log']][-3:] == ['burnout', 'stage', 'program complete']


def test_short_burners_lit_with_the_boosters_do_not_fire_it():
    """The VAB-reset Ariane: Sepratrons (2.5 s) lit with the Kickbacks, both dropped by the next staging."""
    sepratrons_out_kickbacks_burning = [engine(5, 4, False), engine(5, 4, False), engine(5, 4, True), engine(5, 4, True)]
    f = burnout_flight(sepratrons_out_kickbacks_burning, stage=5)
    assert ('cmd/stage', {}) not in f.run(5)


def test_no_burnout_from_an_engine_list_older_than_the_last_staging():
    f = burnout_flight([engine(3, 2, False)], stage=2, engines_stage=3)
    assert ('cmd/stage', {}) not in f.run(3)


def test_a_burn_that_flames_out_ends_short_and_lets_the_program_go_on():
    """Found in KSP: the core ran dry 1 100 m/s into a 1 611 m/s burn; the step waited forever, throttle open, and the
    staging to the next engine never came."""
    f = Flight()
    f.send('probe/program', {'steps': [{'met': 1, 'do': 'burn', 'dv': [100, 0, 0]}, {'met': 2, 'do': 'stage'}]})
    f.send('probe/exec', {'do': 'go'})
    f.run(1)
    f.thrust = 20000.0                          # 20 m/s² for 2 s: 40 of the 100 m/s
    f.run(2)
    f.thrust = 0.0
    sent = f.run(4)
    assert ('cmd/throttle', {'v': 0.0}) in sent and ('cmd/stage', {}) in sent
    assert f.state['steps'][0]['status'] == 'failed'
    assert any(line['text'].startswith('flameout: burn 6') for line in f.state['log'])
