"""Hand controllers: rotation (pitch, yaw, roll) and translation (right, up, forward), each axis −1 to 1.

The real ones will be USB joysticks read by a small service that publishes panel/hc/in/<axis>, like any panel; tests
publish the same topics. The cockpit applies a deadband and passes the axes on as cmd/rotate and cmd/translate.
Signs are the pilot's: + pitch is nose up, + yaw nose right, + roll right wing down; + right, + up, + forward move the
ship that way.

With SAS on, the cockpit switches SAS off while the rotation stick is off centre and back on, in the panel's mode,
when it is centred: KSP does this itself for keyboard steering, but not for inputs that come through kRPC, and SAS
would otherwise fight the stick.
"""
from .. import settings as S

ROTATION_AXES = {'rot_pitch': 'pitch', 'rot_yaw': 'yaw', 'rot_roll': 'roll'}
TRANSLATION_AXES = {'trans_right': 'right', 'trans_up': 'up', 'trans_fwd': 'forward'}


def axis_value(cockpit, control):
    """The axis as commanded: clamped to −1..1, zero inside the deadband (a released stick never rests at exactly 0),
    scaled down with RCS FINE for small, precise corrections (docking)."""
    value = max(-1.0, min(1.0, float(cockpit.inputs.get(control) or 0.0)))
    if abs(value) < S.HAND_CONTROLLER_DEADBAND:
        return 0.0
    scale = S.FINE_CONTROL_SCALE if cockpit.is_on('rcs_fine') else 1.0
    return round(value * scale, 3)


def rotation(cockpit):
    return {axis: axis_value(cockpit, control) for control, axis in ROTATION_AXES.items()}


def translation(cockpit):
    return {axis: axis_value(cockpit, control) for control, axis in TRANSLATION_AXES.items()}


def steering(cockpit):
    """The rotation stick is off centre."""
    return any(rotation(cockpit).values())


def handle_input(cockpit, change):
    """Commands for a control of this panel, or None when the control belongs to another panel."""
    if change.control in ROTATION_AXES:
        was_steering = any(cockpit.last_commands.get('cmd/rotate', ({},))[0].values())
        commands = cockpit.command_once('cmd/rotate', rotation(cockpit))
        if steering(cockpit) != was_steering and cockpit.is_on('sas'):
            # release SAS for the stick, or take it back (the gateway puts the panel's SAS mode back)
            commands += cockpit.command('cmd/sas', {'on': not steering(cockpit)})
        return commands
    if change.control in TRANSLATION_AXES:
        return cockpit.command_once('cmd/translate', translation(cockpit))
    if change.control == 'rcs_fine':
        # KSP's precision mode for the keyboard (it does not scale inputs through kRPC); a stick held while
        # switching changes its command at once
        return (cockpit.command(S.TOGGLE_COMMANDS['rcs_fine'], {'on': change.on})
                + cockpit.command_once('cmd/rotate', rotation(cockpit)) + cockpit.command_once('cmd/translate', translation(cockpit)))
    return None


def release(cockpit):
    """Main bus off: the sticks are dead, so nothing may stay applied."""
    return (cockpit.command_once('cmd/rotate', {axis: 0.0 for axis in ROTATION_AXES.values()})
            + cockpit.command_once('cmd/translate', {axis: 0.0 for axis in TRANSLATION_AXES.values()}))
