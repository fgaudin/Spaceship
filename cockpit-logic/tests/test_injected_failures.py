"""Failures SimSup injects into the cockpit: false alarm, dark panel, frozen display, stuck switch."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cockpit import Cockpit  # noqa: E402
from test_logic import O, P, fed, topics  # noqa: E402


def test_false_alarm_lights_a_caution_with_no_cause():
    c = Cockpit(); fed(c)
    c.handle('sim/failures/false_alarm', {'on': True, 'alarm': 'cw_low_fuel'}, 0)
    assert c.published[O + 'cw_low_fuel'] == {'on': True, 'blink': True} and c.published[O + 'master_caution']['on']
    c.handle('sim/failures/false_alarm', {'on': True, 'alarm': 'High Q'}, 1)          # by its legend
    assert c.published[O + 'cw_q']['on'] and not c.published[O + 'cw_low_fuel']['on']
    c.handle('sim/failures/false_alarm', {'on': False}, 2)
    assert not c.published[O + 'cw_q']['on']


def test_dark_panel_shows_nothing_and_ignores_its_inputs():
    c = Cockpit(); fed(c)
    c.handle('sim/failures/panel_dark', {'on': True, 'panel': 'sys'}, 0)
    assert c.published['panel/sys/out/disp_ec']['blank'] and c.published['panel/sys/out/bar_ec'] == {'v': 0.0}
    assert c.published['panel/sys/out/led_pause'] == {'on': False, 'blink': False}
    assert 'cmd/warp' not in topics(c.handle('panel/sys/in/warp_up', {'v': 1}, 1))
    assert 'cmd/stage' not in topics(c.handle(P + 'stage', {'v': 0}, 1))          # other panels unaffected
    c.handle('sim/failures/panel_dark', {'on': False}, 2)
    assert not c.published['panel/sys/out/disp_ec']['blank']


def test_frozen_display_keeps_its_value():
    c = Cockpit(); fed(c, flight={'alt': 12345.6})
    shown = c.published[O + 'disp_a']
    c.handle('sim/failures/display_frozen', {'on': True, 'output': 'eng/disp_a'}, 0)
    fed(c, 1, flight={'alt': 20000.0})
    assert c.published[O + 'disp_a'] == shown
    c.handle('sim/failures/display_frozen', {'on': False}, 2)
    fed(c, 3, flight={'alt': 20000.0})
    assert c.published[O + 'disp_a'] != shown


def test_stuck_switch_does_nothing():
    c = Cockpit(); fed(c)
    c.handle('sim/failures/switch_stuck', {'on': True, 'control': 'sas'}, 0)
    assert 'cmd/sas' not in topics(c.handle(P + 'sas', {'v': 1}, 1))
    c.handle('sim/failures/switch_stuck', {'on': False}, 2)
    assert topics(c.handle(P + 'sas', {'v': 1}, 3))['cmd/sas'] == {'on': True}
