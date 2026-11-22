import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from simsup_core import FAILURES, SimSup, failure_catalogue, panel_wiring, parameter_choices  # noqa: E402

SCENARIOS = [{'name': 'Engine out', 'save': 'pad-save', 'failures': [{'failure': 'engine_one_out', 'trigger': {'met': 25}}]},
             {'name': 'False alarm', 'failures': [{'failure': 'false_alarm', 'parameters': {'alarm': 'cw_high_g'}}]}]


MODULES = [{'id': 'res', 'panels': [{'id': 'electrical', 'bus': 'sys', 'items': [
    {'id': 'solar', 'in': 'solar', 'led': {'out': 'led_solar'}}, {'id': 'ec', 'out': 'disp_ec'}]}]}]
WIRES = {'outputs': ['sys/disp_ec', 'sys/led_solar'], 'inputs': ['solar']}


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
    simsup = SimSup(panels=panel_wiring(MODULES))
    out = topics(simsup.handle('sim/simsup/cmd', {'action': 'inject', 'failure': 'panel_dark'}, 0))
    assert out['sim/failures/panel_dark'] == {'on': True, 'panel': 'electrical', **WIRES}
    assert out['sim/simsup/state']['active'] == [{'failure': 'panel_dark', 'parameters': {'panel': 'electrical'}}]
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


def test_an_unknown_panel_is_refused_and_a_revert_clears_the_active_failures():
    simsup = SimSup(panels=panel_wiring(MODULES))
    out = topics(simsup.handle('sim/simsup/cmd', {'action': 'inject', 'failure': 'panel_dark', 'parameters': {'panel': 'nope'}}, 0))
    assert 'sim/failures/panel_dark' not in out and not simsup.active
    simsup.handle('sim/simsup/cmd', {'action': 'inject', 'failure': 'rcs_fail'}, 1)
    out = topics(simsup.handle('cmd/game', {'revert': True}, 2))
    assert out['sim/failures/rcs_fail'] == {'on': False} and not simsup.active


def test_every_failure_parameter_offers_its_default_value():
    modules = [{'panels': [
        {'id': 'electrical', 'title': 'ELECTRICAL', 'bus': 'sys', 'items': [{'type': 'toggle', 'id': 'sas', 'label': 'SAS', 'in': 'sas'}]},
        {'id': 'ascent', 'title': 'ASCENT', 'bus': 'eng', 'items': [{'type': 'seg7', 'id': 'alt', 'label': 'ALT', 'out': 'disp_alt'},
            {'type': 'annunciator', 'cells': [{'out': 'cw_low_fuel', 'label': 'LOW FUEL'}]}]}]}]
    for failure in failure_catalogue(parameter_choices(modules)):
        for name, default in failure['parameters'].items():
            assert default in [each['value'] for each in failure['choices'][name]], (failure['id'], name)


def test_probe_mode_and_clearances_are_retained_and_logged():
    simsup = SimSup()
    out = topics(simsup.handle('sim/simsup/cmd', {'action': 'probe_mode', 'on': True}, 1))
    assert out['probe/mode'] == {'on': True}
    out = topics(simsup.handle('sim/simsup/cmd', {'action': 'clearance', 'groups': ['state', 'altitude']}, 2))
    assert out['probe/clearance'] == {'groups': ['altitude', 'state']}
    simsup.handle('sim/simsup/cmd', {'action': 'clearance', 'groups': ['altitude', 'apsides']}, 3)
    texts = [line['text'] for line in simsup.log]
    assert 'PROBE MODE ON' in texts and 'cleared: apsides' in texts and 'clearance withdrawn: state' in texts


def test_a_restarted_simsup_keeps_the_clearances_it_had_published():
    simsup = SimSup()
    simsup.handle('probe/clearance', {'groups': ['altitude']}, 0)       # its own retained message, read back
    simsup.handle('probe/mode', {'on': True}, 0)
    assert simsup.clearance == ['altitude'] and simsup.probe_mode
    simsup.handle('sim/simsup/cmd', {'action': 'clearance', 'groups': []}, 1)
    simsup.handle('probe/clearance', {'groups': []}, 1)
    assert simsup.clearance == []


def test_stations_are_opened_by_the_instructor_and_kept_across_a_restart():
    simsup = SimSup()
    out = topics(simsup.handle('sim/simsup/cmd', {'action': 'stations', 'open': ['mcc', 'console']}, 1))
    assert out['stations/open'] == {'open': ['console', 'mcc']}
    assert simsup.log[-1]['text'] == 'stations open: console, mcc'
    restarted = SimSup()
    restarted.handle('stations/open', {'open': ['wall']}, 0)
    assert restarted.stations == ['wall']
