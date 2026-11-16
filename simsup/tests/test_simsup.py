import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from simsup_core import FAILURES, SimSup  # noqa: E402

SCENARIOS = [{'name': 'Engine out', 'save': 'pad-save', 'failures': [{'failure': 'engine_one_out', 'trigger': {'met': 25}}]},
             {'name': 'False alarm', 'failures': [{'failure': 'false_alarm', 'parameters': {'alarm': 'cw_high_g'}}]}]


def topics(messages):
    return {message.topic: message.payload for message in messages}


def flying(simsup, t, met, alt=1000.0, stage=8):
    out = simsup.handle('tlm/time', {'met': met, 'ut': 1000 + met}, t)
    out += simsup.handle('tlm/vessel', {'situation': 'flying', 'stage': stage}, t)
    return out + simsup.handle('tlm/flight', {'alt': alt}, t)


def test_startup_clears_every_failure_and_publishes_the_scenarios():
    out = topics(SimSup(scenarios=SCENARIOS).startup())
    assert all(out[f'sim/failures/{failure}'] == {'on': False} for failure in FAILURES)
    assert out['sim/simsup/scenarios']['scenarios'] == SCENARIOS and out['sim/freeze'] == {'on': False}


def test_inject_and_clear_with_default_parameters():
    simsup = SimSup()
    out = topics(simsup.handle('sim/simsup/cmd', {'action': 'inject', 'failure': 'panel_dark'}, 0))
    assert out['sim/failures/panel_dark'] == {'on': True, 'panel': 'sys'}
    assert out['sim/simsup/state']['active'] == [{'failure': 'panel_dark', 'parameters': {'panel': 'sys'}}]
    out = topics(simsup.handle('sim/simsup/cmd', {'action': 'clear', 'failure': 'panel_dark'}, 1))
    assert out['sim/failures/panel_dark'] == {'on': False} and out['sim/simsup/state']['active'] == []


def test_armed_failures_fire_on_their_trigger():
    simsup = SimSup()
    simsup.handle('sim/simsup/cmd', {'action': 'arm', 'failure': 'engine_out', 'trigger': {'met': 30}}, 0)
    simsup.handle('sim/simsup/cmd', {'action': 'arm', 'failure': 'comm_lost', 'trigger': {'alt_above': 20000}}, 0)
    simsup.handle('sim/simsup/cmd', {'action': 'arm', 'failure': 'gimbal_stuck', 'trigger': {'stage': 7}}, 0)
    # on the pad MET is zero: nothing fires
    assert 'sim/failures/engine_out' not in topics(simsup.handle('tlm/vessel', {'situation': 'pre_launch', 'stage': 9}, 0))
    assert 'sim/failures/engine_out' not in topics(flying(simsup, 1, met=29))
    out = topics(flying(simsup, 2, met=31))
    assert out['sim/failures/engine_out'] == {'on': True} and len(simsup.armed) == 2
    assert topics(flying(simsup, 3, met=40, alt=25000))['sim/failures/comm_lost'] == {'on': True}
    assert topics(flying(simsup, 4, met=50, alt=26000, stage=7))['sim/failures/gimbal_stuck'] == {'on': True}
    assert simsup.armed == []


def test_disarm():
    simsup = SimSup()
    simsup.handle('sim/simsup/cmd', {'action': 'arm', 'failure': 'engine_out', 'trigger': {'met': 30}}, 0)
    number = simsup.armed[0].number
    simsup.handle('sim/simsup/cmd', {'action': 'disarm', 'number': number}, 1)
    assert 'sim/failures/engine_out' not in topics(flying(simsup, 2, met=40))


def test_scenario_loads_the_save_clears_old_failures_and_arms_its_own():
    simsup = SimSup(scenarios=SCENARIOS)
    simsup.handle('sim/simsup/cmd', {'action': 'inject', 'failure': 'rcs_fail'}, 0)
    out = topics(simsup.handle('sim/simsup/cmd', {'action': 'scenario', 'name': 'Engine out'}, 1))
    assert out['sim/load'] == {'save': 'pad-save'} and out['sim/failures/rcs_fail'] == {'on': False}
    assert [armed.failure for armed in simsup.armed] == ['engine_one_out'] and simsup.scenario == 'Engine out'
    out = topics(simsup.handle('sim/simsup/cmd', {'action': 'scenario', 'name': 'False alarm'}, 2))
    assert out['sim/failures/false_alarm'] == {'on': True, 'alarm': 'cw_high_g'} and simsup.armed == []


def test_new_session_clears_the_log_and_the_debrief():
    simsup = SimSup()
    simsup.handle('sim/simsup/cmd', {'action': 'inject', 'failure': 'engine_out'}, 0)
    out = simsup.handle('sim/simsup/cmd', {'action': 'new_session'}, 1)
    state = {message.topic: message.payload for message in out}
    assert state['sim/simsup/state']['debrief'] == [] and len(state['sim/simsup/log']['log']) == 1


def test_freeze():
    simsup = SimSup()
    assert topics(simsup.handle('sim/simsup/cmd', {'action': 'freeze', 'on': True}, 0))['sim/freeze'] == {'on': True}


def test_log_and_debrief_response_times():
    simsup = SimSup()
    flying(simsup, 0, met=100)
    simsup.handle('sim/simsup/cmd', {'action': 'inject', 'failure': 'engine_out'}, 0)
    simsup.handle('cw/state', {'active': ['ENG FAIL']}, 1)
    flying(simsup, 2, met=103)
    simsup.handle('panel/eng/in/master_alarm', {'v': 1}, 2)
    flying(simsup, 3, met=107)
    out = topics(simsup.handle('panel/eng/in/stage', {'v': 1}, 3))
    entry = out['sim/simsup/state']['debrief'][0]
    assert entry['ack_after'] == 3.0 and entry['action_after'] == 7.0
    kinds = [line['kind'] for line in out['sim/simsup/log']['log']]
    assert kinds == ['failure', 'alarm', 'crew', 'crew']


def test_noisy_inputs_are_logged_once_a_second():
    simsup = SimSup()
    for step in range(10):
        simsup.handle('panel/eng/in/throttle', {'v': step / 10}, step * 0.1)
    assert len(simsup.log) == 1
    simsup.tick(1.1)                                    # the last value held back is logged, not lost
    assert simsup.log[-1]['text'] == 'eng/throttle = 0.9' and len(simsup.log) == 2
