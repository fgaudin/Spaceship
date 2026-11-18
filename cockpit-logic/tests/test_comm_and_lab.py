"""COM panel and LAB panel."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cockpit import Cockpit  # noqa: E402
from test_logic import fed, topics  # noqa: E402

COM, LAB, ENG = 'panel/com/out/', 'panel/lab/out/', 'panel/eng/out/'
LAB_IN, ENG_IN = 'panel/lab/in/', 'panel/eng/in/'


# ---------- landing ----------
def test_orbit_panel_counts_down_to_the_apsides():
    c = Cockpit(); fed(c)
    c.handle('tlm/orbit', {'apo': 80000.0, 'peri': 70000.0, 't_apo': 3725.9, 't_peri': 442800.0}, 1)
    assert c.published[LAB + 'disp_t_apo']['text'] == '01.02.05'
    assert c.published[LAB + 'disp_t_peri']['text'] == '123.00.00'
    c.handle('tlm/orbit', {'apo': None, 'peri': 70000.0, 't_apo': None, 't_peri': -5.0}, 2)      # escaping, periapsis past
    assert c.published[LAB + 'disp_t_apo']['text'] == '-------'
    assert c.published[LAB + 'disp_t_peri']['text'] == '-------'


def test_landing_hover_time_gear_and_orbit():
    c = Cockpit()
    lander = {'situation': 'sub_orbital', 'mass': 4000.0, 'thrust_avail': 20000.0, 'isp': 300.0, 'gear': False}
    propellant = {'stage': {'LiquidFuel': {'amount': 90.0, 'max': 90.0}, 'Oxidizer': {'amount': 110.0, 'max': 110.0}},
                  'total': {}}

    def over_the_mun(t, **vessel):
        fed(c, t, flight={'radar': 5000.0, 'vs': -50.0, 'hs': 0.0, 'speed': 50.0, 'alt': 5600.0},
            vessel={**lander, **vessel}, resources=propellant)
        return c.handle('tlm/orbit', {'body': 'Mun', 'apo': 10000.0, 'peri': -50000.0, 'i': 12.345}, t)

    over_the_mun(0)
    # 1000 kg of propellant: Δv = 300·g0·ln(4000/3000) = 846 m/s; Mun gravity at 5.6 km is 1.541 m/s², and hovering
    # spends Δv at that rate: 549 s
    assert c.published[ENG + 'disp_hover']['text'] == '549'
    # ORBIT, on the lab bus: km above the surface, and the inclination
    assert c.published[LAB + 'disp_apo']['text'] == '10.00' and c.published[LAB + 'disp_peri']['text'] == '-50.00'
    assert c.published[LAB + 'disp_incl']['text'] == '12.35'
    # an engine that cannot lift the lander: no hover time
    over_the_mun(1, thrust_avail=5000.0)
    assert c.published[ENG + 'disp_hover']['text'] == '----'
    # GEAR is on ASCENT · DESCENT: the switch commands it, the LED blinks until the game agrees
    assert c.published[ENG + 'led_gear'] == {'on': False, 'blink': False}
    out = topics(c.handle(ENG_IN + 'gear', {'v': 1}, 2))
    assert out['cmd/gear'] == {'on': True} and out[ENG + 'led_gear'] == {'on': True, 'blink': True}
    over_the_mun(3, gear=True)
    assert c.published[ENG + 'led_gear'] == {'on': True, 'blink': False}


def test_navigation_figures():
    c = Cockpit()
    fed(c, flight={'lat': -1.243, 'lon': 92.141})
    c.handle('tlm/orbit', {'body': 'Minmus', 'apo': 1.0, 'peri': 1.0, 'i': 6.02}, 0)
    assert c.published[LAB + 'disp_lat']['text'] == '-1.24' and c.published[LAB + 'disp_lon']['text'] == '+92.14'
    assert c.published[LAB + 'disp_incl']['text'] == '6.02' and c.published[LAB + 'txt_body']['text'] == 'MINMUS'


# ---------- action groups ----------
def test_action_groups():
    c = Cockpit(); fed(c)
    assert topics(c.handle(LAB_IN + 'ag_10', {'v': 1}, 0))['cmd/action_group'] == {'n': 10}
    assert 'cmd/action_group' not in topics(c.handle(LAB_IN + 'ag_10', {'v': 0}, 0))
    c.handle('tlm/groups', {'on': [False, True] + [False] * 8}, 0)
    assert c.published[LAB + 'lamp_ag_2']['on'] and not c.published[LAB + 'lamp_ag_1']['on']


# ---------- cameras ----------
def test_camera_selection():
    c = Cockpit(); fed(c)
    assert c.published[LAB + 'txt_cam']['text'] == 'NO MONITOR' and c.published['cam/select'] == {'id': None}
    c.handle('cam/status', {'online': True, 'playing': False}, 0)
    assert c.published[LAB + 'txt_cam']['text'] == 'NO CAMERA'
    c.handle('cam/list', {'cameras': [{'id': 11, 'name': 'NavCam 1'}, {'id': 22, 'name': 'Dunvey Kerman'}]}, 0)
    assert c.published['cam/select'] == {'id': 11} and c.published[LAB + 'txt_cam']['text'] == 'NAVCAM 1'
    c.handle(LAB_IN + 'cam_next', {'v': 1}, 0)
    assert c.published['cam/select'] == {'id': 22} and c.published[LAB + 'disp_cam']['text'] == '2'
    c.handle(LAB_IN + 'cam_next', {'v': 0}, 0)
    c.handle(LAB_IN + 'cam_next', {'v': 1}, 0)                         # wraps around
    assert c.published['cam/select'] == {'id': 11}
    c.handle('cam/status', {'online': True, 'playing': True}, 0)
    assert c.published[LAB + 'led_cam_live']['on']
    c.handle('cam/list', {'cameras': [{'id': 22, 'name': 'Dunvey Kerman'}]}, 0)     # the selected camera is gone
    assert c.published['cam/select'] == {'id': 22}


# ---------- communications ----------
def comm(c, t, link, **more):
    c.handle('tlm/time', {'ut': 1000 + t, 'met': t, 'warp': 1}, t)
    return c.handle('tlm/comm', {'link': link, 'strength': 0.76 if link else 0.0, 'hops': 1 if link else 0,
                                 'via': 'Kerbin: Harvester Massif' if link else None, 'antenna': None, **more}, t)


def test_comm_panel_aos_and_los():
    c = Cockpit(); fed(c)
    comm(c, 0, True)
    assert c.published[COM + 'lamp_aos'] == {'on': True, 'blink': False} and not c.published[COM + 'lamp_los']['on']
    assert c.published[COM + 'txt_via']['text'] == 'HARVESTER MA' and c.published[COM + 'bar_signal'] == {'v': 0.76}
    assert c.published[COM + 'disp_hops']['text'] == '1'
    assert c.published[COM + 'disp_link_time']['text'] == '--.--'       # in this state since before we looked
    comm(c, 5, False)
    assert c.published[COM + 'lamp_los'] == {'on': True, 'blink': True} and not c.published[COM + 'lamp_aos']['on']
    assert c.published[COM + 'txt_via']['text'] == 'NO SIGNAL' and c.published[COM + 'bar_signal'] == {'v': 0.0}
    comm(c, 70, False)                                                  # steady after ten seconds
    assert c.published[COM + 'lamp_los'] == {'on': True, 'blink': False}
    assert c.published[COM + 'disp_link_time']['text'] == '01.05'
    comm(c, 71, True)
    assert c.published[COM + 'lamp_aos'] == {'on': True, 'blink': True}
    assert c.published[COM + 'disp_link_time']['text'] == '00.00'


def test_antenna_switch_acts_only_when_moved():
    c = Cockpit(); fed(c)
    assert 'cmd/antenna' not in topics(c.handle('panel/com/in/antenna', {'v': 0}, 0))
    assert topics(c.handle('panel/com/in/antenna', {'v': 1}, 1))['cmd/antenna'] == {'on': True}
    comm(c, 2, True, antenna=False)
    assert c.published[COM + 'led_antenna'] == {'on': True, 'blink': True}      # switch on, antennas not out yet
    comm(c, 3, True, antenna=True)
    assert c.published[COM + 'led_antenna'] == {'on': True, 'blink': False}


# ---------- solo panel ----------
def test_solo_panel_shows_the_flight_dynamics_answer():
    c = Cockpit(); fed(c)
    assert c.published['panel/solo/out/txt_fd']['text'] == 'NO SERVICE'
    c.handle('fd/status', {'text': 'CIRC APO 1004.2', 'ok': True}, 1)
    assert c.published['panel/solo/out/txt_fd']['text'] == 'CIRC APO 1004.2' and c.published['panel/solo/out/lamp_fd_sent']['on']
    c.handle('fd/status', {'text': 'RDV: NO TARGET', 'ok': False}, 2)
    assert c.published['panel/solo/out/lamp_fd_refused']['on'] and not c.published['panel/solo/out/lamp_fd_sent']['on']
