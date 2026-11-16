"""RDV panel: target selection, rendezvous figures against the braking gate, docking alignment, undocking.

The docking figures are in the pilot's own axes (tlm/target "port": right, up, yaw, pitch, roll), in the order the
manoeuvre is flown: turn to face the port, translate onto its axis, close.
"""
import math

from .. import settings as S
from ..alarms import braking_gate
from ..display_format import fit_number
from ..messages import PanelOutputs, switch_lamp

LAMPS = ['led_tgt', 'led_port', 'led_km', 'lamp_overspeed', 'lamp_capture', 'lamp_aligned', 'led_ctrl_port',
         'lamp_docked', 'led_undock_arm']
DISPLAYS = ['disp_range', 'disp_closing', 'disp_gate', 'disp_los', 'disp_roll', 'disp_yaw', 'disp_pitch',
            'disp_right', 'disp_up', 'disp_vright', 'disp_vup', 'disp_axial', 'disp_vaxial']
TARGET_NAME_CHARACTERS = 12

# Docking displays fed straight from a field of the port telemetry: display → (field, decimals, digits).
SIGNED_PORT_DISPLAYS = {
    'disp_yaw': ('yaw', 1, 5), 'disp_pitch': ('pitch', 1, 5), 'disp_roll': ('roll', 1, 5),
    'disp_right': ('right', 2, 5), 'disp_up': ('up', 2, 5),
    'disp_vright': ('v_right', 2, 4), 'disp_vup': ('v_up', 2, 4),
}


# ---------- inputs ----------
def handle_input(cockpit, change):
    """Commands for a control of this panel, or None when the control belongs to another panel."""
    control = change.control
    if control in ('tgt_next', 'tgt_prev'):
        return cockpit.command('cmd/target', {'step': 1 if control == 'tgt_next' else -1}) if change.pressed else []
    if control == 'tgt_clear':
        return cockpit.command('cmd/target', {'clear': True}) if change.pressed else []
    if control == 'port_next':
        return cockpit.command('cmd/target', {'port': 1}) if change.pressed else []
    if control == 'undock':
        return cockpit.command('cmd/undock', {}) if change.pressed and cockpit.is_on('undock_arm') else []
    if control == 'ctrl_port':
        return cockpit.command('cmd/control_from', {'port': change.on}) if change.moved else []
    return None


# ---------- outputs ----------
def render(cockpit, wanted):
    outputs = PanelOutputs(wanted, S.RENDEZVOUS_PANEL)
    if not cockpit.powered():
        outputs.all_dark(LAMPS, [*DISPLAYS, 'txt_tgt'])
        return
    if cockpit.is_on('lamp_test'):
        outputs.all_lit(LAMPS, DISPLAYS)
        outputs.text('txt_tgt', '*' * TARGET_NAME_CHARACTERS)
        return
    target = cockpit.target if cockpit.telemetry_is_fresh() else {}
    _render_target_and_rendezvous(cockpit, outputs, target)
    _render_docking(outputs, target.get('port'))
    outputs.lamp('lamp_docked', target.get('docked'))
    outputs.lamp('led_undock_arm', cockpit.is_on('undock_arm'))
    outputs.lamp('led_ctrl_port', *switch_lamp(target.get('ctrl_port'), cockpit.is_on('ctrl_port')))


def _render_target_and_rendezvous(cockpit, outputs, target):
    has_target = bool(target.get('set'))
    target_range = target.get('range') if has_target else None
    closing_speed = target.get('closing') if has_target else None
    line_of_sight_rate = target.get('los_rate') if has_target else None
    gate_speed = braking_gate(target_range) if target_range is not None else None
    range_in_km = target_range is not None and target_range >= S.RANGE_IN_KM_FROM_M

    name = (target.get('name') or '').upper()[:TARGET_NAME_CHARACTERS]
    outputs.text('txt_tgt', name if has_target else 'NO TARGET')
    outputs.lamp('led_tgt', has_target)
    outputs.lamp('led_port', target.get('port'))
    outputs.lamp('led_km', range_in_km)
    shown_range = None if target_range is None else target_range / 1000 if range_in_km else target_range
    outputs.text('disp_range', fit_number(shown_range, 1, 6))
    outputs.text('disp_closing', fit_number(closing_speed, 2, 5, signed=True))
    outputs.text('disp_gate', fit_number(gate_speed, 2, 5))
    outputs.text('disp_los', fit_number(line_of_sight_rate, 2, 4))
    over_the_gate = gate_speed is not None and closing_speed is not None and closing_speed > gate_speed
    outputs.lamp('lamp_overspeed', over_the_gate, blink=True)


def _render_docking(outputs, port):
    """`port`: the "port" block of tlm/target, present when a docking port is targeted."""
    own_axes = port if port and 'right' in port else None
    for display, (field, decimals, digits) in SIGNED_PORT_DISPLAYS.items():
        outputs.text(display, fit_number(own_axes[field] if own_axes else None, decimals, digits, signed=True))
    outputs.text('disp_axial', fit_number(port['axial'] if port else None, 2, 5))
    approach_speed = -port['v_axial'] if port else None         # v_axial is along the port's outward axis
    outputs.text('disp_vaxial', fit_number(approach_speed, 2, 4, signed=True))

    aligned = bool(own_axes) and max(abs(own_axes['yaw']), abs(own_axes['pitch'])) <= S.ALIGNED_WITHIN_DEG
    outputs.lamp('lamp_aligned', aligned)
    outputs.lamp('lamp_capture', bool(port) and _inside_capture_envelope(port, own_axes, approach_speed))


def _inside_capture_envelope(port, own_axes, approach_speed):
    """Close to the port, on its axis, slow enough and not too slow, and not too far off its direction."""
    if own_axes:
        lateral_offset = math.hypot(own_axes['right'], own_axes['up'])
    else:
        lateral_offset = math.hypot(port['x'], port['z'])       # older telemetry: the target port's axes
    angle = port.get('angle')
    return (0 < port['axial'] < S.CAPTURE_LAMP_WITHIN_M
            and lateral_offset <= S.CAPTURE_LATERAL_MAX_M
            and S.CAPTURE_SPEED_MIN_M_S <= approach_speed <= S.CAPTURE_SPEED_MAX_M_S
            and (angle is None or angle <= S.CAPTURE_ANGLE_MAX_DEG))
