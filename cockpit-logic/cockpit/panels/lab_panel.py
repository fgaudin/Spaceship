"""LAB panel: experimental panels, tried here before they earn a place in the cockpit.

- CROSS-POINTER: a 9 × 9 LED matrix with a selector, in place of a screen for the precise phases of flight.
- LANDING: radar altitude, speeds, time to the ground and the height needed to brake.
- NAVIGATION: latitude, longitude, inclination and the body orbited.
- ACTION GROUPS: the ten custom groups of the craft, with their state.
- CAMERA: picks the camera shown on the monitor page (cam.html, fed by the Kerbcast mod).
"""
import math

from .. import settings as S
from ..cross_pointer import blank_matrix, cross_pointer
from ..display_format import fit_number
from ..messages import PanelOutputs

ACTION_GROUP_NUMBERS = range(1, S.ACTION_GROUP_COUNT + 1)
LAMPS = ['lamp_xp_null', 'lamp_brake', 'led_cam_live', *[f'lamp_ag_{number}' for number in ACTION_GROUP_NUMBERS]]
DISPLAYS = ['disp_xp_right', 'disp_xp_up', 'disp_xp_scale', 'disp_radar', 'disp_ld_vs', 'disp_ld_hs',
            'disp_impact', 'disp_brake_alt', 'disp_lat', 'disp_lon', 'disp_incl', 'disp_cam']
TEXTS = {'txt_body': S.BODY_NAME_CHARACTERS, 'txt_cam': S.CAMERA_NAME_CHARACTERS}
FALLING_SITUATIONS = ('flying', 'sub_orbital')


# ---------- inputs ----------
def handle_input(cockpit, change):
    """Commands for a control of this panel, or None when the control belongs to another panel."""
    control = change.control
    if control.startswith('ag_'):
        return cockpit.command('cmd/action_group', {'n': int(control[3:])}) if change.pressed else []
    if control in ('cam_next', 'cam_prev'):
        if change.pressed:
            step_camera(cockpit, 1 if control == 'cam_next' else -1)
        return []
    return None


# ---------- cameras ----------
def selected_camera_index(cockpit):
    """Index in cockpit.cameras of the selected camera; the first one when the selected camera is gone."""
    for index, camera in enumerate(cockpit.cameras):
        if camera.get('id') == cockpit.selected_camera_id:
            return index
    return 0 if cockpit.cameras else None


def step_camera(cockpit, step):
    index = selected_camera_index(cockpit)
    if index is not None:
        cockpit.selected_camera_id = cockpit.cameras[(index + step) % len(cockpit.cameras)].get('id')


def camera_selection(cockpit):
    """cam/select: the camera the monitor must show."""
    index = selected_camera_index(cockpit)
    return {'id': cockpit.cameras[index].get('id') if index is not None else None}


# ---------- cross-pointer ----------
def cross_pointer_values(cockpit, mode):
    """(right, up, full scales, decimals) for a mode of the selector; right and up are None without data.

    Angles are "fly to the dot": the dot is where the nose must go. OFFSET shows where the target port is, and
    DRIFT which way the vessel moves over the ground, both across the vessel's own axis."""
    flight, node = cockpit.flight, cockpit.telemetry.get('tlm/node', {})
    port = cockpit.target.get('port') or {}
    right = forward = down = None
    if (flight.get('speed') or 0.0) > S.CROSS_POINTER_MOVING_ABOVE_M_S and 'v_right' in flight:
        right, forward, down = flight['v_right'], flight['v_fwd'], flight['v_down']
    angle = lambda sideways, ahead: math.degrees(math.atan2(sideways, ahead))
    if mode == 'NODE':
        values = (node.get('yaw'), node.get('pitch')) if node.get('set') else (None, None)
        return (*values, S.CROSS_POINTER_ANGLE_SCALES_DEG, 1)
    if mode == 'PRO':
        values = (angle(right, forward), angle(-down, forward)) if right is not None else (None, None)
        return (*values, S.CROSS_POINTER_ANGLE_SCALES_DEG, 1)
    if mode == 'RETRO':
        values = (angle(-right, -forward), angle(down, -forward)) if right is not None else (None, None)
        return (*values, S.CROSS_POINTER_ANGLE_SCALES_DEG, 1)
    if mode == 'PORT':
        return (port.get('yaw'), port.get('pitch'), S.CROSS_POINTER_ANGLE_SCALES_DEG, 1)
    if mode == 'OFFSET':
        return (port.get('right'), port.get('up'), S.CROSS_POINTER_OFFSET_SCALES_M, 2)
    # DRIFT: also shown at rest, where it must read zero
    if 'v_right' in flight:
        return (flight['v_right'], -flight['v_down'], S.CROSS_POINTER_DRIFT_SCALES_M_S, 1)
    return (None, None, S.CROSS_POINTER_DRIFT_SCALES_M_S, 1)


# ---------- landing ----------
def local_gravity(cockpit):
    """m/s² at the vessel's altitude, or None for a body the cockpit does not know."""
    body = S.BODIES.get(cockpit.orbit.get('body'))
    altitude = cockpit.flight.get('alt')
    if body is None or altitude is None:
        return None
    gravitational_parameter, radius = body
    return gravitational_parameter / (radius + altitude) ** 2


def landing_figures(cockpit):
    """(seconds to the ground in free fall, height needed to stop at full thrust); None for what cannot be said."""
    flight, vessel = cockpit.flight, cockpit.vessel
    gravity, height, vertical_speed = local_gravity(cockpit), flight.get('radar'), flight.get('vs')
    if vessel.get('situation') not in FALLING_SITUATIONS or None in (gravity, height, vertical_speed) or height <= 0:
        return None, None
    # height + vertical_speed·t − ½·gravity·t² = 0
    seconds_to_ground = (vertical_speed + math.sqrt(vertical_speed ** 2 + 2 * gravity * height)) / gravity
    mass, full_thrust = vessel.get('mass') or 0.0, vessel.get('thrust_avail') or 0.0
    braking = full_thrust / mass - gravity if mass > 0 else 0.0     # deceleration left once gravity is held
    speed = flight.get('speed') or abs(vertical_speed)
    braking_height = speed ** 2 / (2 * braking) if braking > 0 else None
    return seconds_to_ground, braking_height


# ---------- outputs ----------
def render(cockpit, wanted):
    outputs = PanelOutputs(wanted, S.LAB_PANEL)
    if not cockpit.powered():
        outputs.all_dark(LAMPS, [*DISPLAYS, *TEXTS])
        outputs.raw('mx_xp', {'rows': blank_matrix()})
        return
    if cockpit.is_on('lamp_test'):
        outputs.all_lit(LAMPS, DISPLAYS)
        for name, characters in TEXTS.items():
            outputs.text(name, '*' * characters)
        outputs.raw('mx_xp', {'rows': blank_matrix('w')})
        return
    fresh = cockpit.telemetry_is_fresh()
    _render_cross_pointer(cockpit, outputs, fresh)
    _render_landing(cockpit, outputs, fresh)
    _render_navigation(cockpit, outputs, fresh)
    groups = cockpit.telemetry.get('tlm/groups', {}).get('on') or [] if fresh else []
    for number in ACTION_GROUP_NUMBERS:
        outputs.lamp(f'lamp_ag_{number}', number <= len(groups) and groups[number - 1])
    _render_camera(cockpit, outputs)


def _render_cross_pointer(cockpit, outputs, fresh):
    mode = cockpit.selected('xp_mode', S.CROSS_POINTER_MODES)
    right, up, full_scales, decimals = cross_pointer_values(cockpit, mode)
    if not fresh:
        right = up = None
    pointer = cross_pointer(right, up, full_scales)
    outputs.raw('mx_xp', {'rows': pointer.rows})
    outputs.text('disp_xp_right', fit_number(right, decimals, 5, signed=True))
    outputs.text('disp_xp_up', fit_number(up, decimals, 5, signed=True))
    outputs.text('disp_xp_scale', fit_number(pointer.full_scale, 1, 3))
    outputs.lamp('lamp_xp_null', pointer.nulled)


def _render_landing(cockpit, outputs, fresh):
    flight = cockpit.flight if fresh else {}
    seconds_to_ground, braking_height = landing_figures(cockpit) if fresh else (None, None)
    height, vertical_speed = flight.get('radar'), flight.get('vs')
    outputs.text('disp_radar', fit_number(height, 0, 6))
    outputs.text('disp_ld_vs', fit_number(vertical_speed, 1, 5, signed=True))
    outputs.text('disp_ld_hs', fit_number(flight.get('hs'), 1, 5))
    outputs.text('disp_impact', fit_number(seconds_to_ground, 0, 4))
    outputs.text('disp_brake_alt', fit_number(braking_height, 0, 6))
    descending = vertical_speed is not None and vertical_speed < -S.BRAKE_ONLY_BELOW_VERTICAL_SPEED_M_S
    brake_soon = descending and braking_height is not None and height <= S.BRAKE_SOON_MARGIN * braking_height
    brake_now = brake_soon and height <= S.BRAKE_NOW_MARGIN * braking_height
    outputs.lamp('lamp_brake', brake_soon, blink=brake_now)


def _render_navigation(cockpit, outputs, fresh):
    flight, orbit = (cockpit.flight, cockpit.orbit) if fresh else ({}, {})
    outputs.text('disp_lat', fit_number(flight.get('lat'), 2, 5, signed=True))
    outputs.text('disp_lon', fit_number(flight.get('lon'), 2, 6, signed=True))
    outputs.text('disp_incl', fit_number(orbit.get('i'), 2, 5))
    outputs.text('txt_body', (orbit.get('body') or '').upper()[:S.BODY_NAME_CHARACTERS])


def _render_camera(cockpit, outputs):
    index = selected_camera_index(cockpit)
    monitor_on = bool(cockpit.camera_monitor.get('online'))
    if index is None or not monitor_on:      # the list of a monitor that has gone stays on the bus
        outputs.text('txt_cam', 'NO CAMERA' if monitor_on else 'NO MONITOR')
        outputs.text('disp_cam', '--')
    else:
        outputs.text('txt_cam', str(cockpit.cameras[index].get('name') or '').upper()[:S.CAMERA_NAME_CHARACTERS])
        outputs.text('disp_cam', fit_number(index + 1, 0, 2))
    outputs.lamp('led_cam_live', monitor_on and cockpit.camera_monitor.get('playing'), blink=False)
