"""COM panel, LAB panel and the cross-pointer."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cockpit import Cockpit  # noqa: E402
from cockpit.cross_pointer import cross_pointer  # noqa: E402
from test_logic import fed, topics  # noqa: E402

COM, LAB = 'panel/com/out/', 'panel/lab/out/'
LAB_IN = 'panel/lab/in/'


def dot(rows):
    """(row, column, colour) of the pointer's dot: the only LED that is not the white centre."""
    found = [(r, c, colour) for r, row in enumerate(rows) for c, colour in enumerate(row) if colour not in '.w']
    return found[0] if found else None


# ---------- cross-pointer ----------
def test_cross_pointer_scales_and_colours():
    scales = (4.0, 20.0, 90.0)
    pointer = cross_pointer(0.2, -0.3, scales)
    assert pointer.nulled and pointer.full_scale == 4.0 and dot(pointer.rows) == (4, 4, 'g')
    pointer = cross_pointer(2.0, 4.0, scales)                   # right and up: two columns right, top row
    assert dot(pointer.rows) == (0, 6, 'a') and pointer.rows[4][4] == 'w' and not pointer.nulled
    pointer = cross_pointer(-10.0, 1.0, scales)                 # the coarser scale takes over
    assert pointer.full_scale == 20.0 and dot(pointer.rows) == (4, 2, 'a')
    pointer = cross_pointer(170.0, 0.0, scales)                 # beyond every scale: held on the edge, red
    assert dot(pointer.rows) == (4, 8, 'r')
    assert cross_pointer(None, None, scales).rows == ['.' * 9] * 9


def test_cross_pointer_modes():
    c = Cockpit()
    fed(c, flight={'v_right': 3.0, 'v_fwd': -40.0, 'v_down': 1.0, 'speed': 40.1})
    c.handle('tlm/node', {'set': True, 'ut': 500, 'dv': [10, 0, 0], 'att_err': 3.2, 'yaw': 2.0, 'pitch': -2.0}, 0)
    assert dot(c.published[LAB + 'mx_xp']['rows']) == (6, 6, 'a')       # NODE: nose must go right and down
    assert c.published[LAB + 'disp_xp_right']['text'] == '+2.0' and c.published[LAB + 'disp_xp_scale']['text'] == '4.0'
    c.handle(LAB_IN + 'xp_mode', {'v': 1}, 0)                           # RETRO: flying backwards, nearly aligned
    assert c.published[LAB + 'disp_xp_scale']['text'] == '20.0'
    assert c.published[LAB + 'disp_xp_right']['text'] == '-4.3' and c.published[LAB + 'disp_xp_up']['text'] == '+1.4'
    c.handle(LAB_IN + 'xp_mode', {'v': 5}, 0)                           # DRIFT: 3 m/s right, 1 m/s down
    assert c.published[LAB + 'disp_xp_right']['text'] == '+3.0' and c.published[LAB + 'disp_xp_up']['text'] == '-1.0'
    assert dot(c.published[LAB + 'mx_xp']['rows']) == (4, 5, 'a')
    c.handle(LAB_IN + 'xp_mode', {'v': 4}, 0)                           # OFFSET: no port targeted
    assert c.published[LAB + 'disp_xp_right']['text'] == '-----' and dot(c.published[LAB + 'mx_xp']['rows']) is None
    port = {'right': 0.1, 'up': -0.05, 'fwd': 5, 'v_right': 0, 'v_up': 0, 'yaw': 0, 'pitch': 0, 'roll': 0,
            'axial': 5, 'x': 0, 'z': 0, 'v_axial': -0.1, 'angle': 0}
    c.handle('tlm/target', {'set': True, 'name': 'Target', 'range': 5, 'closing': 0.1, 'port': port}, 0)
    assert c.published[LAB + 'lamp_xp_null']['on']


# ---------- landing ----------
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
    assert c.published[LAB + 'disp_hover']['text'] == '549'
    assert c.published[LAB + 'disp_radar']['text'] == '5000'
    # ORBIT, on the lab bus: km above the surface, and the inclination
    assert c.published[LAB + 'disp_apo']['text'] == '10.00' and c.published[LAB + 'disp_peri']['text'] == '-50.00'
    assert c.published[LAB + 'disp_incl']['text'] == '12.35'
    # an engine that cannot lift the lander: no hover time
    over_the_mun(1, thrust_avail=5000.0)
    assert c.published[LAB + 'disp_hover']['text'] == '----'
    # GEAR is on the landing panel: the switch commands it, the LED blinks until the game agrees
    assert c.published[LAB + 'led_gear'] == {'on': False, 'blink': False}
    out = topics(c.handle(LAB_IN + 'gear', {'v': 1}, 2))
    assert out['cmd/gear'] == {'on': True} and out[LAB + 'led_gear'] == {'on': True, 'blink': True}
    over_the_mun(3, gear=True)
    assert c.published[LAB + 'led_gear'] == {'on': True, 'blink': False}


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
