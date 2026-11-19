"""The solo bus: the SOLO module, what a pilot flying without Mission Control has in its place.

- PAD REQUEST: requests to the flight dynamics service (flight-dynamics/). The service reads the buttons itself and
  reads the PAD up to the burn computer; this module only draws what it answered (fd/status).
- ORBIT: apoapsis, periapsis (km), the time to each, inclination.
- NAVIGATION: latitude, longitude and the body orbited; and the MODE switch, SOLO or MCC.

With MODE on MCC the three panels are dark, and the service ignores the requests.
"""
from .. import settings as S
from ..display_format import fit_number, format_time_to
from ..messages import PanelOutputs

LAMPS = ['lamp_fd_sent', 'lamp_fd_refused']
DISPLAYS = ['disp_lat', 'disp_lon', 'disp_apo', 'disp_peri', 'disp_t_apo', 'disp_t_peri', 'disp_incl']
TEXTS = {'txt_fd': 16, 'txt_body': S.BODY_NAME_CHARACTERS}


def render(cockpit, wanted):
    outputs = PanelOutputs(wanted, S.SOLO_PANEL)
    if not cockpit.powered() or (cockpit.mcc_mode() and not cockpit.lamp_test()):
        outputs.all_dark(LAMPS, [*DISPLAYS, *TEXTS])
        return
    if cockpit.lamp_test():
        outputs.all_lit(LAMPS, DISPLAYS)
        for name, characters in TEXTS.items():
            outputs.text(name, '*' * characters)
        return
    status = cockpit.telemetry.get('fd/status', {})
    outputs.text('txt_fd', status.get('text', '') or 'NO SERVICE')
    outputs.lamp('lamp_fd_sent', status.get('ok') and status.get('text') != 'READY')
    outputs.lamp('lamp_fd_refused', status.get('ok') is False and bool(status.get('text')))
    fresh = cockpit.telemetry_is_fresh()
    _render_navigation(cockpit, outputs, fresh)
    _render_orbit(cockpit, outputs, fresh)


def _render_navigation(cockpit, outputs, fresh):
    flight, orbit = (cockpit.flight, cockpit.orbit) if fresh else ({}, {})
    outputs.text('disp_lat', fit_number(flight.get('lat'), 2, 5, signed=True))
    outputs.text('disp_lon', fit_number(flight.get('lon'), 2, 6, signed=True))
    outputs.text('txt_body', (orbit.get('body') or '').upper()[:S.BODY_NAME_CHARACTERS])


def _render_orbit(cockpit, outputs, fresh):
    """Apoapsis and periapsis in km above the surface (negative: under it), the time to each, inclination in
    degrees."""
    orbit = cockpit.orbit if fresh else {}
    in_km = lambda metres: metres / 1000 if metres is not None else None
    outputs.text('disp_apo', fit_number(in_km(orbit.get('apo')), 2, 7))
    outputs.text('disp_peri', fit_number(in_km(orbit.get('peri')), 2, 7))
    outputs.text('disp_t_apo', format_time_to(orbit.get('t_apo')))
    outputs.text('disp_t_peri', format_time_to(orbit.get('t_peri')))
    outputs.text('disp_incl', fit_number(orbit.get('i'), 2, 5))
