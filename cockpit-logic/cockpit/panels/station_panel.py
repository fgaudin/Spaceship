"""STATION panel: which capsule the console is, the command module (CM) or the lander (LM), and the move between them.

Turning the STATION selector starts the move: the gateway sends the crew across and hands the controls to the other
capsule (cmd/station), while the console goes dark for STATION_BLACKOUT_S (the crew climbing through the tunnel),
then powers up with a lamp test. The windows show that capsule's window cameras (cam/window/left and right).

The panel tells which capsule has the controls (CM, LM, from tlm/station), how many kerbals are in each, whether
the two are docked (TUNNEL: the crew can go across), and blinks TRANSFER through the move. TRANSFER stays lit while
the rest of the console is dark: it is on the panel's own supply."""
from .. import settings as S
from ..display_format import fit_number
from ..messages import PanelOutputs

STATIONS = ('cm', 'lm')                     # the selector's positions
SIDES = ('left', 'right')
LAMPS = ['lamp_stn_cm', 'lamp_stn_lm', 'lamp_tunnel']
DISPLAYS = ['disp_cm_crew', 'disp_lm_crew']


class StationMove:
    """The move under way, or none."""
    def __init__(self):
        self.to = None
        self.started = None

    def start(self, station, now):
        self.to, self.started = station, now

    def stop(self):
        self.to = self.started = None

    def phase(self, now):
        """'dark' (the blackout), 'lamp test' (the power-up), or None."""
        if self.to is None:
            return None
        elapsed = now - self.started
        if elapsed < S.STATION_BLACKOUT_S:
            return 'dark'
        if elapsed < S.STATION_BLACKOUT_S + S.STATION_LAMP_TEST_S:
            return 'lamp test'
        return None


def wanted_station(cockpit):
    return cockpit.selected('station', STATIONS)


def station_report(cockpit):
    """tlm/station, or {} without one (no window cameras, a plant that does not report it)."""
    return cockpit.telemetry.get('tlm/station', {})


def current_station(cockpit):
    """The capsule the crew is in, for the windows: the selector's, which the controls are kept on (a separation
    leaves the game flying the other side for a moment); the one the game flies when the selector's is empty."""
    report, wanted = station_report(cockpit), wanted_station(cockpit)
    if (report.get(wanted) or {}).get('crew') or not report.get('at'):
        return wanted
    return report['at']


def handle_input(cockpit, change):
    """Commands for a control of this panel, or None when the control belongs to another panel."""
    if change.control != 'station':
        return None
    if not change.moved:
        return []                           # the first report after a restart: where the selector already was
    return _start_move(cockpit)


def _start_move(cockpit):
    station = wanted_station(cockpit)
    cockpit.station_move.start(station, cockpit.now)
    return cockpit.command('cmd/station', {'to': station})


def tick(cockpit):
    """End the move once powered up again; if the selector was turned back during the blackout (the inputs are dead
    then), the crew goes back the other way. Outside a move, the selector wins (see _keep_the_controls)."""
    move = cockpit.station_move
    if move.to is None:
        return _keep_the_controls(cockpit)
    if move.phase(cockpit.now) is not None:
        return []
    went_to = move.to
    move.stop()
    if wanted_station(cockpit) != went_to and cockpit.powered():
        return _start_move(cockpit)
    return []


def _keep_the_controls(cockpit):
    """The craft is flown from the capsule the selector names: a separation leaves the game flying the side that kept
    the original root part, and "control from here" in the game moves the controls too. Then the controls only are
    sent back (no crew moves), switching vessels when the capsules are apart; never to an empty capsule."""
    report, wanted = station_report(cockpit), wanted_station(cockpit)
    if (not cockpit.powered() or not cockpit.telemetry_is_fresh() or report.get('at') in (None, wanted)
            or not (report.get(wanted) or {}).get('crew') or (cockpit.clock.get('warp') or 1) > 1
            or cockpit.seconds_since_command('cmd/station') < S.STATION_REASSERT_EVERY_S):
        return []
    return cockpit.command('cmd/station', {'to': wanted, 'controls_only': True})


def window_cameras(cockpit):
    """{'cam/window/left': {'id'}, ...}: the cameras named <station>_<side> on the camera list (cam/list); none
    through the blackout."""
    station = None if cockpit.station_move.phase(cockpit.now) == 'dark' else current_station(cockpit)
    wanted = {}
    for side in SIDES:
        name = f'{station}_{side}'
        camera = next((camera for camera in cockpit.cameras if station and _base_name(camera) == name), None)
        wanted[f'cam/window/{side}'] = {'id': camera.get('id') if camera else None}
    return wanted


def _base_name(camera):
    """The camera monitor numbers cameras that share a name ('cm_left 2'): the name without that number."""
    return str(camera.get('name') or '').split(' ')[0]


WINDOW_CAMERA_NAMES = {f'{station}_{side}' for station in STATIONS for side in SIDES}


def is_window_camera(camera):
    """A camera of the windows (cm_left, lm_right, ...): not one for the camera monitor."""
    return _base_name(camera) in WINDOW_CAMERA_NAMES


def render(cockpit, wanted):
    outputs = PanelOutputs(wanted, S.STATION_PANEL)
    phase = cockpit.station_move.phase(cockpit.now)
    if not cockpit.has_power():
        outputs.lamp('led_xfer', False)
        outputs.all_dark(LAMPS, DISPLAYS)
        return
    outputs.lamp('led_xfer', phase is not None, blink=phase == 'dark')
    if phase == 'dark':
        outputs.all_dark(LAMPS, DISPLAYS)
        return
    if cockpit.lamp_test():
        outputs.all_lit(LAMPS + ['led_xfer'])
        for name in DISPLAYS:
            outputs.text(name, '8.')
        return
    report = station_report(cockpit) if cockpit.telemetry_is_fresh() else {}
    outputs.lamp('lamp_stn_cm', report.get('at') == 'cm')
    outputs.lamp('lamp_stn_lm', report.get('at') == 'lm')
    outputs.lamp('lamp_tunnel', report.get('joined'))
    for station in STATIONS:
        capsule = report.get(station)
        outputs.text(f'disp_{station}_crew', fit_number(capsule['crew'], 0, 1) if capsule else '-')
