"""SOLO panel: requests to the flight dynamics service (flight-dynamics/) for a pilot flying without Mission
Control. The service reads the buttons itself and reads the PAD up to the burn computer; this module only draws
what it answered (fd/status)."""
from .. import settings as S
from ..messages import PanelOutputs

LAMPS = ['lamp_fd_sent', 'lamp_fd_refused']


def render(cockpit, wanted):
    outputs = PanelOutputs(wanted, S.SOLO_PANEL)
    if not cockpit.powered():
        outputs.all_dark(LAMPS, ['txt_fd'])
        return
    if cockpit.lamp_test():
        outputs.all_lit(LAMPS)
        outputs.text('txt_fd', '*' * 16)
        return
    status = cockpit.telemetry.get('fd/status', {})
    outputs.text('txt_fd', status.get('text', '') or 'NO SERVICE')
    outputs.lamp('lamp_fd_sent', status.get('ok') and status.get('text') != 'READY')
    outputs.lamp('lamp_fd_refused', status.get('ok') is False and bool(status.get('text')))
