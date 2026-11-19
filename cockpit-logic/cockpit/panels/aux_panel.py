"""The aux bus: the AUX module in MAIN.

- ACTION GROUPS: the ten custom groups of the craft, with their state.
- CAMERA: picks the camera shown on the monitor page (cam.html, fed by the JRTI mod), among the cameras that are
  not the windows'; its MONITOR switch turns the monitor off (cam/select {"id": null, "off": true}: a black screen).
"""
from .. import settings as S
from .station_panel import is_window_camera
from ..display_format import fit_number
from ..messages import PanelOutputs

ACTION_GROUP_NUMBERS = range(1, S.ACTION_GROUP_COUNT + 1)
LAMPS = ['led_cam_live', *[f'lamp_ag_{number}' for number in ACTION_GROUP_NUMBERS]]


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
def monitor_cameras(cockpit):
    """The cameras the monitor can be put on: the camera list without the windows' own."""
    return [camera for camera in cockpit.cameras if not is_window_camera(camera)]


def monitor_switched_on(cockpit):
    return bool(cockpit.inputs.get('cam_power', 1))     # on until the switch reports


def selected_camera_index(cockpit):
    """Index in monitor_cameras of the selected camera; the first one when the selected camera is gone."""
    cameras = monitor_cameras(cockpit)
    for index, camera in enumerate(cameras):
        if camera.get('id') == cockpit.selected_camera_id:
            return index
    return 0 if cameras else None


def step_camera(cockpit, step):
    cameras, index = monitor_cameras(cockpit), selected_camera_index(cockpit)
    if index is not None:
        cockpit.selected_camera_id = cameras[(index + step) % len(cameras)].get('id')


def camera_selection(cockpit):
    """cam/select: the camera the monitor must show, none with its switch off."""
    if not monitor_switched_on(cockpit):
        return {'id': None, 'off': True}
    index = selected_camera_index(cockpit)
    return {'id': monitor_cameras(cockpit)[index].get('id') if index is not None else None}


# ---------- outputs ----------
def render(cockpit, wanted):
    outputs = PanelOutputs(wanted, S.AUX_PANEL)
    if not cockpit.powered():
        outputs.all_dark(LAMPS, ['disp_cam', 'txt_cam'])
        return
    if cockpit.lamp_test():
        outputs.all_lit(LAMPS, ['disp_cam'])
        outputs.text('txt_cam', '*' * S.CAMERA_NAME_CHARACTERS)
        return
    groups = cockpit.telemetry.get('tlm/groups', {}).get('on') or [] if cockpit.telemetry_is_fresh() else []
    for number in ACTION_GROUP_NUMBERS:
        outputs.lamp(f'lamp_ag_{number}', number <= len(groups) and groups[number - 1])
    _render_camera(cockpit, outputs)


def _render_camera(cockpit, outputs):
    index = selected_camera_index(cockpit)
    monitor_on = bool(cockpit.camera_monitor.get('online'))
    if not monitor_switched_on(cockpit):
        outputs.text('txt_cam', 'MONITOR OFF')
        outputs.blank('disp_cam')
    elif index is None or not monitor_on:      # the list of a monitor that has gone stays on the bus
        outputs.text('txt_cam', 'NO CAMERA' if monitor_on else 'NO MONITOR')
        outputs.text('disp_cam', '--')
    else:
        name = monitor_cameras(cockpit)[index].get('name') or ''
        outputs.text('txt_cam', str(name).upper()[:S.CAMERA_NAME_CHARACTERS])
        outputs.text('disp_cam', fit_number(index + 1, 0, 2))
    outputs.lamp('led_cam_live', monitor_on and cockpit.camera_monitor.get('playing'), blink=False)
