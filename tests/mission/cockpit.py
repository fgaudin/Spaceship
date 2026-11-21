"""The pilot's side of the cockpit, for the full-mission test in KSP: panel inputs out, panel outputs in.

Everything the pilot does goes through `panel/<bus>/in/<control>` (and the hand controllers' `panel/hc/in/<axis>`);
everything it reads should be a panel output (`panel/<bus>/out/<name>`). Where it has to read something else (the
FDAI ball's markers, which are only on glass, or kRPC standing in for Mission Control's tools), it says so with
`stand_in()`, so the run's log lists every such place.

kRPC (`self.sc`) is used only by the test harness: launching, naming saves, ground truth for the checks, and the
planning that Mission Control's flight dynamics officer would do on the ground.
"""
import json, math, os, sys, time
import krpc
import paho.mqtt.client as mqtt

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG_DIR = os.path.join(ROOT, 'tmp', 'mission')
EVENT_SOURCE = {'MAN': 0, 'TIG': 1, 'APO': 2, 'PERI': 3, 'SOI': 4}
SPEED_REF = {'orbit': 0, 'surface': 1, 'target': 2}
SAS_BUTTON = {'stability': 'sas_stab', 'maneuver': 'sas_mnvr', 'prograde': 'sas_pro', 'retrograde': 'sas_retro',
              'normal': 'sas_nml', 'anti_normal': 'sas_anml', 'radial': 'sas_rad', 'anti_radial': 'sas_arad',
              'target': 'sas_tgt', 'anti_target': 'sas_atgt'}
NEXT_STAGE_CELLS = ('engines', 'solids', 'decouple', 'clamps', 'chutes', 'fairing')


class Abort(Exception):
    """The phase cannot go on safely: stop, leave the craft as it is."""


class Cockpit:
    def __init__(self, phase):
        os.makedirs(LOG_DIR, exist_ok=True)
        self.phase = phase
        self.logfile = open(os.path.join(LOG_DIR, f'{phase}.log'), 'a')
        self.findings = open(os.path.join(LOG_DIR, 'findings.jsonl'), 'a')
        self.seen = {}
        self.alarms_seen = {}
        self.start = time.time()
        self.cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f'mission-{phase}-{os.getpid()}')
        self.cli.on_message = self._on_message
        self.cli.connect('localhost', 1883)
        self.cli.subscribe('#')
        self.cli.loop_start()
        self.conn = krpc.connect(name=f'mission-{phase}')
        self.sc = self.conn.space_center
        self.log(f'===== phase {phase} =====')

    # ---------- the bus ----------
    def _on_message(self, client, userdata, message):
        try:
            payload = json.loads(message.payload or b'{}')
        except ValueError:
            return
        self.seen[message.topic] = payload
        if message.topic == 'cw/state':
            for legend in payload.get('active', []) or []:
                if legend not in self.alarms_seen:
                    self.alarms_seen[legend] = self.met()
                    self.log(f'C&W: {legend} on')
            for legend in list(self.alarms_seen):
                if legend not in (payload.get('active') or []):
                    del self.alarms_seen[legend]

    def pin(self, bus, control, value, retain=True, settle=0.25):
        self.cli.publish(f'panel/{bus}/in/{control}', json.dumps({'v': value}), qos=1, retain=retain)
        time.sleep(settle)

    def press(self, bus, control):
        self.pin(bus, control, 1, retain=False)
        self.pin(bus, control, 0, retain=False)

    def stick(self, axis, value):
        self.cli.publish(f'panel/hc/in/{axis}', json.dumps({'v': round(value, 3)}), qos=1)

    def sticks_centred(self):
        for axis in ('rot_pitch', 'rot_yaw', 'rot_roll', 'trans_right', 'trans_up', 'trans_fwd'):
            self.stick(axis, 0.0)
        time.sleep(0.3)

    def out(self, bus, name):
        return self.seen.get(f'panel/{bus}/out/{name}') or {}

    def text(self, bus, name):
        return self.out(bus, name).get('text')

    def num(self, bus, name):
        """A display's figure, or None for dashes or a blank display."""
        shown = self.out(bus, name)
        if shown.get('blank'):
            return None
        try:
            return float(shown.get('text'))
        except (TypeError, ValueError):
            return None

    def lit(self, bus, name):
        return bool(self.out(bus, name).get('on'))

    def tlm(self, name):
        return self.seen.get(f'tlm/{name}') or {}

    def met(self):
        return self.tlm('time').get('met')

    # ---------- the log ----------
    def log(self, text):
        line = f'{time.strftime("%H:%M:%S")} [{self.phase}] MET {self._met_text()}  {text}'
        print(line, flush=True)
        self.logfile.write(line + '\n'); self.logfile.flush()

    def _met_text(self):
        met = self.seen.get('tlm/time', {}).get('met')
        if met is None:
            return '--'
        return f'{int(met // 3600):02d}:{int(met // 60 % 60):02d}:{int(met % 60):02d}'

    def _finding(self, kind, text):
        key = (kind, text)
        if key in getattr(self, '_noted', set()):
            return
        self._noted = getattr(self, '_noted', set()) | {key}
        self.log(f'{kind}: {text}')
        self.findings.write(json.dumps({'phase': self.phase, 'kind': kind, 'text': text, 'met': self.met(),
                                        'at': time.strftime('%Y-%m-%d %H:%M:%S')}) + '\n')
        self.findings.flush()

    def gap(self, text):
        """Something the cockpit does not give the pilot."""
        self._finding('GAP', text)

    def stand_in(self, text):
        """The pilot read something that is not a panel output (glass, or Mission Control's tools)."""
        self._finding('STAND-IN', text)

    def problem(self, text):
        """The cockpit did something wrong."""
        self._finding('PROBLEM', text)

    def check(self, what, ok, info=''):
        self.log(('PASS ' if ok else 'FAIL ') + what + ('' if ok else f'   [{info}]'))
        if not ok:
            self._finding('FAIL', f'{what} [{info}]')
        return ok

    # ---------- waiting ----------
    def wait(self, predicate, timeout=10, step=0.1):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if predicate():
                    return True
            except (KeyError, TypeError, ValueError, ZeroDivisionError):
                pass
            time.sleep(step)
        return False

    # ---------- saves (the harness) ----------
    def save(self, name):
        self.sc.save(f'full-{name}')
        self.log(f'saved full-{name}')

    def load(self, name):
        self.zero_inputs(keep_switches=True)     # before the load too: retained arms and throttle reach the new vessel
        self.sc.load(f'full-{name}')
        time.sleep(8)
        self.zero_inputs(keep_switches=True)
        self.wait(lambda: self.tlm('vessel').get('name') == self.sc.active_vessel.name, 15)
        time.sleep(2)
        self.log(f'loaded full-{name}: {self.sc.active_vessel.name}')

    def zero_inputs(self, keep_switches=False):
        """Throttle to idle, sticks centred, burn and engine arms off. Without keep_switches, every switch to a
        known state: the retained inputs of an earlier session would otherwise stay in force."""
        self.pin('eng', 'throttle', 0.0)
        self.sticks_centred()
        for bus, control, value in (('cmp', 'burn_arm', 0), ('eng', 'eng_arm', 0), ('eng', 'stage_arm', 0),
                                    ('eng', 'abort_arm', 0), ('rdv', 'undock_arm', 0), ('sys', 'chute_arm', 0),
                                    ('sys', 'revert_arm', 0), ('eng', 'hold', 0), ('sys', 'evt_src', 0),
                                    ('sys', 'evt_down', 0), ('eng', 'thrust_lim', 1.0), ('sys', 'pause', 0),
                                    ('eng', 'rcs', 0)):     # RCS off unless a phase needs it: it fires for rotation too
            self.pin(bus, control, value)
        if keep_switches:
            return
        for bus, control, value in (('eng', 'cb_main', 1), ('eng', 'rcs_fine', 0), ('eng', 'gimbal_lock', 0),
                                    ('eng', 'alt_ref', 0), ('eng', 'fdai_markers', 1), ('rdv', 'ctrl_port', 0),
                                    ('sys', 'brakes', 0), ('sys', 'cabin_light', 1), ('sys', 'backlight', 1),
                                    ('solo', 'mcc_mode', 0), ('solo', 'fd_body', 0), ('com', 'antenna', 1),
                                    ('aux', 'cam_power', 1)):
            self.pin(bus, control, value)

    # ---------- procedures ----------
    def next_stage(self):
        return [cell.upper() for cell in NEXT_STAGE_CELLS if self.lit('eng', f'lamp_ns_{cell}')]

    def stage(self, expect=None, why=''):
        """STAGE ARM, read NEXT STAGE, press STAGE. `expect`: the NEXT STAGE cells that must be lit (a list)."""
        self.pin('eng', 'stage_arm', 1)
        preview = self.next_stage()
        number = self.text('eng', 'disp_stage')
        if expect is not None and sorted(preview) != sorted(expect):
            time.sleep(2.0)                     # the preview follows a staging a moment later
            preview = self.next_stage()
        if expect is not None and sorted(preview) != sorted(expect):
            self.pin('eng', 'stage_arm', 0)
            raise Abort(f'NEXT STAGE shows {preview or "nothing"} at stage {number}, expected {expect} ({why}): not staged')
        self.press('eng', 'stage')
        self.log(f'STAGE {number} ({why}): NEXT STAGE was {preview or "dark"}')
        time.sleep(1.5)
        return preview

    def sas_mode(self, mode, timeout=30):
        """Press a SAS MODE button; True once its lamp is steady."""
        if not self.lit('eng', 'led_sas'):
            self.pin('eng', 'sas', 1)
        button = SAS_BUTTON[mode]
        self.press('eng', button)
        ok = self.wait(lambda: self.out('eng', f'lamp_{button}') == {'on': True, 'blink': False}, timeout)
        if not ok:
            self.log(f'SAS MODE {mode}: lamp {self.out("eng", "lamp_" + button)}, game {self.tlm("vessel").get("sas_mode")}')
        return ok

    def hold(self, pitch, heading):
        """ATTITUDE HOLD knobs (whole degrees)."""
        self.pin('eng', 'hold_pitch', round((pitch + 90) / 180, 5), settle=0.05)
        self.pin('eng', 'hold_hdg', round((heading % 360) / 360, 5), settle=0.05)

    def key_pad(self, tig_met, prograde, normal=0.0, radial=0.0):
        """Key a PAD into the burn computer: TIG as hhmmss of MET, Δv in m/s."""
        hours = int(tig_met // 3600)
        tig = f'{hours:02d}{int(tig_met // 60 % 60):02d}{int(tig_met % 60):02d}'
        wanted = [round(prograde, 1), round(normal, 1), round(radial, 1)]
        for attempt in range(3):
            # TIG's button once; ENTR then moves on to PRO, NRM and RAD by itself (pressing the next field's
            # button after ENTR sends the keys back into TIG: a finding)
            self.press('cmp', 'f_tig')
            time.sleep(0.2)
            for field, value in (('f_tig', tig), ('f_pro', f'{prograde:.1f}'), ('f_nrm', f'{normal:.1f}'),
                                 ('f_rad', f'{radial:.1f}')):
                for character in value:
                    self.pin('cmp', 'key', character, retain=False, settle=0.3)
                self.pin('cmp', 'key', 'ENTR', retain=False, settle=0.4)
            time.sleep(0.8)
            pad = self.seen.get('cmp/pad', {})
            if pad.get('tig') is not None and abs(pad['tig'] - int(tig_met)) < 1.5 and \
                    all(abs(a - b) < 0.06 for a, b in zip(pad.get('dv', []), wanted)):
                break
            self.problem(f'keyed PAD not stored as keyed (attempt {attempt + 1}): {pad}, wanted TIG {int(tig_met)} Δv {wanted}')
        pad = self.seen.get('cmp/pad', {})
        self.log(f'PAD keyed: TIG {self.text("cmp", "disp_tig")}, Δv {self.text("cmp", "disp_pro")} / '
                 f'{self.text("cmp", "disp_nrm")} / {self.text("cmp", "disp_rad")}, burn {self.text("cmp", "disp_tb")} s '
                 f'(cmp/pad {pad.get("tig")}, {pad.get("dv")}); ERR lamp {self.lit("cmp", "lamp_err")}')
        return pad

    def request_pad(self, button, body=None):
        """A SOLO PAD REQUEST; returns fd/status. The PAD then blinks on the burn computer."""
        if body is not None:
            self.pin('solo', 'fd_body', body)
        self.seen.pop('fd/status', None)
        self.press('solo', button)
        self.wait(lambda: 'fd/status' in self.seen, 8)
        status = self.seen.get('fd/status', {})
        self.log(f'SOLO {button}: {self.text("solo", "txt_fd")!r} {status}')
        if status.get('ok'):
            self.wait(lambda: self.lit('cmp', 'lamp_uplink'), 5)
        return status

    def warp_to_event(self, source, until_s, timeout=3600):
        """Timer on `source`, WARP TO EVT, until the event is `until_s` away (the timer counts up to it: −mm.ss)."""
        self.pin('sys', 'evt_src', EVENT_SOURCE[source])
        time.sleep(1.0)
        deadline = time.time() + timeout
        while time.time() < deadline:
            left = self.event_in()
            if left is None or left <= until_s:
                break
            if self.tlm('time').get('warp', 1) <= 1 and left > until_s + 30:
                self.press('sys', 'warp_to')
                time.sleep(3)
            time.sleep(1)
        if self.tlm('time').get('warp', 1) > 1:
            self.press('sys', 'warp_stop')
            self.wait(lambda: self.tlm('time').get('warp', 1) <= 1, 20)
        self.log(f'warp over: event {source} in {self.event_in()} s')

    def event_in(self):
        """Seconds to the event timer's event, from its display (counting up to the event: '-mm.ss')."""
        shown = self.text('sys', 'disp_evt')
        if not shown or '-' not in shown[:1]:
            return None if not shown or shown.strip('-. ') == '' else 0.0
        return clock_seconds(shown[1:])

    def fly_pad(self, accept=True, min_burn_s=10.0, max_att_err=3.5, attitude_timeout=240, on_flameout=None):
        """ACCEPT (an uplinked PAD), BURN ARM, SAS MNVR, warp to TIG, throttle up, the burn computer cuts off.
        Returns the Δv left to go (display) and the measured Δv."""
        if accept:
            self.press('cmp', 'pad_accept')
            if not self.wait(lambda: not self.lit('cmp', 'lamp_uplink'), 5):
                self.problem('UPLINK ACCEPT: the uplink lamp stayed on')
        time.sleep(0.6)
        pad = dict(self.seen['cmp/pad'])
        dv = math.sqrt(sum(component ** 2 for component in pad['dv']))
        craft = self.tlm('vessel')
        thrust = craft.get('thrust_avail') or 0.0
        if thrust <= 0:
            # engines not lit yet: BURN TIME on the CMP panel works from the next staging's engines
            pass
        burn_s = self.num('cmp', 'disp_tb')
        self.log(f'PAD to fly: TIG {self.text("cmp", "disp_tig")}, Δv {dv:.1f} m/s, burn {burn_s} s at full thrust')
        if burn_s is not None and burn_s < min_burn_s:
            limit = max(0.05, math.floor(burn_s / min_burn_s / 0.05) * 0.05)
            self.pin('eng', 'thrust_lim', limit)
            self.log(f'short burn: THRUST LIMIT {limit * 100:.0f} %')
        self.pin('cmp', 'burn_arm', 1)
        self.wait(lambda: self.seen['cmp/pad']['state'] == 'armed', 5)
        if not self.sas_mode('maneuver', 30):
            self.problem(f'SAS MNVR not taken: {self.tlm("vessel").get("sas_mode")}')
        self.wait(lambda: self.num('cmp', 'disp_att') is not None and self.num('cmp', 'disp_att') < max_att_err,
                  attitude_timeout)
        self.log(f'burn attitude: ATT ERR {self.text("cmp", "disp_att")}°; TIG in {pad["tig"] - self.met():.0f} s')
        if pad['tig'] - self.met() > 120:
            self.warp_to_event('TIG', 90, timeout=7200)
        if not self.wait(lambda: self.num('cmp', 'disp_att') is not None and self.num('cmp', 'disp_att') < max_att_err, 80):
            self.problem(f'not on the burn attitude at TIG−{pad["tig"] - self.met():.0f} s: ATT ERR {self.text("cmp", "disp_att")}')
        if self.met() > pad['tig'] + 5:
            self.problem(f'TIG passed while getting on the burn attitude ({self.met() - pad["tig"]:.0f} s late): no burn')
            self.pin('cmp', 'burn_arm', 0)
            raise Abort('TIG passed')
        while self.met() < pad['tig']:
            time.sleep(0.05)
        error = self.num('cmp', 'disp_att')
        if error is None or error > 10:
            self.problem(f'burn refused at TIG: ATT ERR {self.text("cmp", "disp_att")} (over 10°)')
            self.pin('cmp', 'burn_arm', 0)
            raise Abort('not on the burn attitude at TIG')
        mass_before = self.tlm('vessel')['mass']
        self.pin('eng', 'eng_arm', 1)
        self.pin('eng', 'throttle', 1.0, settle=0.0)
        self.log(f'TIG: throttle up (TIG lamp {self.out("cmp", "lamp_tig")})')
        deadline, next_note, lit_seen = time.time() + 1800, time.time() + 5, False
        while time.time() < deadline and not self.lit('cmp', 'lamp_cutoff'):
            if (self.tlm('vessel').get('thrust') or 0) > 0:
                lit_seen = True
            if self.lit('eng', 'cw_flameout') or (time.time() > next_note - 3 and not lit_seen and
                                                  (self.num('eng', 'disp_eng_on') or 0) == 0):
                if on_flameout is not None:
                    if on_flameout() == 'stop':
                        break
                else:
                    self.stage(why='flameout during the burn')
                lit_seen = False
                next_note = time.time() + 5
            if time.time() > next_note:
                self.log(f'  burning: Δv to go {self.text("cmp", "disp_vg")}, ATT ERR {self.text("cmp", "disp_att")}, '
                         f'TWR {self.text("eng", "disp_twr")}, state {self.seen["cmp/pad"]["state"]}')
                next_note = time.time() + 10
            time.sleep(0.05)
        self.pin('eng', 'throttle', 0.0)
        cut = self.lit('cmp', 'lamp_cutoff')
        time.sleep(1.5)
        left = self.num('cmp', 'disp_vg')
        self.log(f'cutoff {"by the computer" if cut else "NOT by the computer"}: Δv to go {self.text("cmp", "disp_vg")}')
        self.pin('cmp', 'burn_arm', 0); self.pin('eng', 'eng_arm', 0); self.pin('eng', 'stage_arm', 0)
        self.pin('eng', 'thrust_lim', 1.0)
        self.pin('sys', 'evt_src', EVENT_SOURCE['MAN'])
        return left, pad

    def orbit_text(self):
        return (f'APO {self.text("solo", "disp_apo")} km PERI {self.text("solo", "disp_peri")} km '
                f'INCL {self.text("solo", "disp_incl")}° around {self.text("solo", "txt_body")}')

    def report_alarms(self):
        if self.alarms_seen:
            self.log(f'C&W lit now: {sorted(self.alarms_seen)}')


def clock_seconds(text):
    """'hh.mm.ss', 'mm.ss', or the event timer's 'hHmm' past 99 minutes → seconds."""
    text = text.strip().lstrip('-')
    if 'H' in text:
        hours, minutes = text.split('H')
        return int(hours) * 3600 + int(minutes) * 60
    seconds = 0
    for part in text.strip().lstrip('-').split('.'):
        seconds = seconds * 60 + int(part)
    return seconds


def run(phases, argv):
    """`python mission.py <phase> [<phase> …]`: run phases in order."""
    names = argv[1:] or sys.exit('phases: ' + ' '.join(phases))
    for name in names:
        phases[name]()
