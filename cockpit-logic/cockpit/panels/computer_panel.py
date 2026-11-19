"""CMP panel: the controls of the burn computer. The computer itself is in burn_computer.py."""
from .. import settings as S
from ..messages import PanelOutputs

# Field button → the PAD field it selects.
FIELD_BUTTONS = {'f_tig': 'tig', 'f_pro': 'pro', 'f_nrm': 'nrm', 'f_rad': 'rad'}


def press_key(cockpit, key):
    """A key of the numeric keypad. A stored field changes the PAD, so the game's node may have to follow."""
    if cockpit.powered():
        cockpit.burn_computer.press_key(key)
    return cockpit.node_mirror.pad_to_node(cockpit)


def handle_input(cockpit, change):
    """Commands for a control of this panel, or None when the control belongs to another panel."""
    control, computer = change.control, cockpit.burn_computer
    if control in FIELD_BUTTONS:
        if change.pressed:
            computer.select_field(FIELD_BUTTONS[control])
        return []
    if control == 'pad_accept':
        if change.pressed:
            computer.accept_uplink()
        return cockpit.node_mirror.pad_to_node(cockpit)
    if control == 'pad_clr':
        if change.pressed:
            computer.clear()
        return cockpit.node_mirror.pad_to_node(cockpit)
    if control == 'burn_arm':
        if change.value is not None:
            computer.arm(change.on)
        return []
    return None


def render(cockpit, wanted):
    outputs = PanelOutputs(wanted, S.COMPUTER_PANEL)
    cockpit.burn_computer.render(outputs, cockpit.telemetry, cockpit.powered(), cockpit.lamp_test(),
                                 cockpit.telemetry_is_fresh())
