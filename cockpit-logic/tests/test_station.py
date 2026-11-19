"""STATION: moving the console between the command module and the lander."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cockpit import Cockpit, settings as S  # noqa: E402
from test_logic import fed, topics  # noqa: E402

SYS, SYS_IN, ENG, ENG_IN = 'panel/sys/out/', 'panel/sys/in/', 'panel/eng/out/', 'panel/eng/in/'
CM, LM = 0, 1           # the selector's positions
DOCKED_IN_CM = {'at': 'cm', 'joined': True, 'cm': {'crew': 3, 'seats': 3, 'here': True},
                'lm': {'crew': 0, 'seats': 2, 'here': True}}
WINDOW_CAMERAS = [{'id': 1, 'name': 'cm_left'}, {'id': 2, 'name': 'cm_right'}, {'id': 3, 'name': 'lm_left'},
                  {'id': 4, 'name': 'lm_right'}, {'id': 5, 'name': 'NavCam'}]
POWER_UP_AT = S.STATION_BLACKOUT_S
DONE_AT = S.STATION_BLACKOUT_S + S.STATION_LAMP_TEST_S


def docked_cockpit():
    c = Cockpit()
    fed(c)
    c.handle(SYS_IN + 'station', {'v': CM}, 0)          # the selector's first report: no move
    c.handle('tlm/station', DOCKED_IN_CM, 0)
    c.handle('cam/list', {'cameras': WINDOW_CAMERAS}, 0)
    return c


def test_the_panel_shows_the_capsules():
    c = docked_cockpit()
    assert c.station_move.to is None
    assert c.published[SYS + 'lamp_stn_cm']['on'] and not c.published[SYS + 'lamp_stn_lm']['on']
    assert c.published[SYS + 'lamp_tunnel']['on']
    assert c.published[SYS + 'disp_cm_crew']['text'] == '3' and c.published[SYS + 'disp_lm_crew']['text'] == '0'
    assert not c.published[SYS + 'led_xfer']['on']
    assert c.published['cam/window/left'] == {'id': 1} and c.published['cam/window/right'] == {'id': 2}


def test_moving_to_the_lander_goes_dark_then_powers_up():
    c = docked_cockpit()
    c.handle(ENG_IN + 'eng_arm', {'v': 1}, 0)
    out = topics(c.handle(SYS_IN + 'station', {'v': LM}, 1))
    assert out['cmd/station'] == {'to': 'lm'}
    assert out['cmd/throttle'] == {'v': 0.0}                        # the blackout stops the engine
    # dark, the windows too; only TRANSFER blinks
    assert c.published[SYS + 'led_xfer'] == {'on': True, 'blink': True}
    assert not c.published[SYS + 'lamp_stn_cm']['on'] and c.published[SYS + 'disp_cm_crew']['blank']
    assert c.published['cockpit/power'] == {'on': False}
    assert c.published['cam/window/left'] == {'id': None}
    assert topics(c.handle(ENG_IN + 'stage', {'v': 1}, 2)) == {}     # dead inputs
    # the game has moved the pilot across and flies from the lander
    fed(c, 10)
    c.handle('tlm/station', {**DOCKED_IN_CM, 'at': 'lm', 'cm': {'crew': 2, 'seats': 3, 'here': True},
                             'lm': {'crew': 1, 'seats': 2, 'here': True}}, 10)
    # power-up: lamp test
    fed(c, 1 + POWER_UP_AT)
    assert c.published['cockpit/power'] == {'on': True}
    assert c.published[SYS + 'led_xfer'] == {'on': True, 'blink': False}
    assert c.published[SYS + 'lamp_stn_cm']['on'] and c.published[SYS + 'disp_lm_crew']['text'] == '8.'
    assert c.published['cam/window/left'] == {'id': 3} and c.published['cam/window/right'] == {'id': 4}
    # and then the lander
    fed(c, 1 + DONE_AT)
    assert c.station_move.to is None and not c.published[SYS + 'led_xfer']['on']
    assert c.published[SYS + 'lamp_stn_lm']['on'] and not c.published[SYS + 'lamp_stn_cm']['on']
    assert c.published[SYS + 'disp_cm_crew']['text'] == '2' and c.published[SYS + 'disp_lm_crew']['text'] == '1'


def test_turned_back_during_the_blackout_goes_back():
    c = docked_cockpit()
    c.handle(SYS_IN + 'station', {'v': LM}, 1)
    assert topics(c.handle(SYS_IN + 'station', {'v': CM}, 5)) .get('cmd/station') is None   # dead input
    out = topics(fed(c, 1 + DONE_AT))
    assert out['cmd/station'] == {'to': 'cm'} and c.station_move.to == 'cm'


def test_no_window_cameras():
    c = docked_cockpit()
    c.handle('cam/list', {'cameras': [{'id': 5, 'name': 'NavCam'}, {'id': 6, 'name': 'cm_left 2'}]}, 1)
    assert c.published['cam/window/left'] == {'id': 6}              # numbered by the monitor: still found
    assert c.published['cam/window/right'] == {'id': None}


def test_without_power_the_panel_is_dark_and_the_selector_dead():
    c = docked_cockpit()
    c.handle('tlm/resources', {'stage': {}, 'total': {'ElectricCharge': {'amount': 0.0, 'max': 100}}}, 1)
    assert not c.published[SYS + 'led_xfer']['on'] and c.published[SYS + 'disp_cm_crew']['blank']
    assert 'cmd/station' not in topics(c.handle(SYS_IN + 'station', {'v': LM}, 2))


def test_after_a_separation_the_selector_keeps_the_controls():
    c = docked_cockpit()
    c.handle(SYS_IN + 'station', {'v': LM}, 1)
    fed(c, 1 + DONE_AT)
    in_lm = {'at': 'lm', 'joined': True, 'cm': {'crew': 1, 'seats': 3, 'here': True}, 'lm': {'crew': 1, 'seats': 2, 'here': True}}
    c.handle('tlm/station', in_lm, 1 + DONE_AT)
    assert 'cmd/station' not in topics(fed(c, 40))                  # the game agrees: nothing sent
    # separated: the game stays on the CM side (the original root)
    apart = {'at': 'cm', 'joined': False, 'cm': {'crew': 1, 'seats': 3, 'here': True}, 'lm': {'crew': 1, 'seats': 2, 'here': False}}
    c.handle('tlm/station', apart, 41)
    out = topics(fed(c, 41))
    assert out['cmd/station'] == {'to': 'lm', 'controls_only': True}
    assert c.published['cam/window/left'] == {'id': 3}             # the windows stay on the lander meanwhile
    assert 'cmd/station' not in topics(fed(c, 42))                  # not again at once
    assert topics(fed(c, 41 + S.STATION_REASSERT_EVERY_S))['cmd/station'] == {'to': 'lm', 'controls_only': True}


def test_the_controls_never_go_to_an_empty_capsule():
    c = Cockpit()
    fed(c)
    c.handle(SYS_IN + 'station', {'v': LM}, 0)          # a restart with the selector on LM
    c.handle('tlm/station', DOCKED_IN_CM, 0)            # the lander is empty
    assert 'cmd/station' not in topics(fed(c, 5))


def test_the_windows_follow_the_game_when_the_selected_capsule_is_empty():
    c = Cockpit()
    fed(c)
    c.handle(SYS_IN + 'station', {'v': LM}, 0)          # first report (a restart): no move; the lander is empty
    c.handle('tlm/station', DOCKED_IN_CM, 0)
    c.handle('cam/list', {'cameras': WINDOW_CAMERAS}, 0)
    assert c.station_move.to is None and c.published['cam/window/left'] == {'id': 1}
