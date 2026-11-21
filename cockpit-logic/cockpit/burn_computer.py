"""Burn computer: holds one PAD and runs the burn. Pure logic, no I/O.

A PAD is what Mission Control reads up for a burn: TIG, the ignition time (mission elapsed time, seconds), and the
Δv to gain as prograde / normal / radial components (m/s).

    computer = BurnComputer()
    computer.select_field('tig'); computer.press_key('1'); ...; computer.press_key('ENTR')
    computer.receive_uplink({'tig_met': 5445, 'dv': [12.5, 0, -3]})   # shown blinking until accept_uplink()
    computer.arm(True)                    # BURN ARM: zero the Δv counter, count from now
    computer.count_delta_v(telemetry)     # on every tlm/vessel message
    computer.cutoff                       # True once the PAD's Δv has been counted: the cockpit cuts the throttle

Keys: 0-9, '.', '-' (sign), CLR, ENTR. TIG is keyed as hhmmss (13045 → 01:30:45), Δv in m/s with one decimal.
ENTR stores the field and moves to the next one; ENTR on an empty field keeps its value.
"""
import math

from .display_format import fit_number, format_event_time, format_mission_time
from .settings import STANDARD_GRAVITY

FIELDS = ['tig', 'pro', 'nrm', 'rad']           # in keying order; the last three are the Δv components
KEYS = set('0123456789.-') | {'CLR', 'ENTR'}
LAMPS = ['led_f_tig', 'led_f_pro', 'led_f_nrm', 'led_f_rad', 'lamp_uplink', 'led_burn_arm', 'lamp_tig', 'lamp_burn',
         'lamp_cutoff', 'lamp_err']
DISPLAYS = ['disp_tig', 'disp_pro', 'disp_nrm', 'disp_rad', 'disp_tfi', 'disp_vg', 'disp_tb', 'disp_att']

TIG_LAMP_FROM_S = 60.0              # the TIG lamp lights a minute before ignition (and stays a minute after) ...
TIG_LAMP_BLINKS_FROM_S = 10.0       # ... and blinks in the last 10 s
COMMAND_LATENCY_S = 0.05            # time for a throttle command to reach the engine
TIG_DIGITS, DELTA_V_WHOLE_DIGITS = 6, 4


def empty_pad():
    return {'tig': None, 'dv': [0.0, 0.0, 0.0]}


class BurnComputer:
    def __init__(self):
        self.pad = empty_pad()          # the loaded PAD: {'tig': seconds or None, 'dv': [prograde, normal, radial]}
        self.uplinked_pad = None        # a PAD from Mission Control, waiting for the crew to accept it
        self.selected_field = None      # the field being keyed, one of FIELDS
        self.typed = ''                 # what has been keyed into that field so far
        self.entry_error = False
        self.armed = False
        self.delta_v_counted = 0.0      # m/s gained since BURN ARM
        self.last_mission_time = None
        self.cutoff = False
        self.revision = 0               # goes up whenever the PAD changes

    # ---------- the PAD ----------
    def has_pad(self):
        return self.pad['tig'] is not None

    def delta_v_total(self):
        return math.sqrt(sum(component ** 2 for component in self.pad['dv']))

    def delta_v_to_go(self):
        """Negative after an overshoot: that is the residual."""
        return self.delta_v_total() - self.delta_v_counted

    def _pad_changed(self):
        self.revision += 1
        self.delta_v_counted, self.cutoff, self.last_mission_time = 0.0, False, None

    def load(self, ignition_time, delta_v):
        """A PAD from outside the keypad (a maneuver node made in the game)."""
        self.pad = {'tig': float(ignition_time), 'dv': [float(component) for component in delta_v]}
        self.selected_field, self.typed = None, ''
        self._pad_changed()

    def clear(self):
        self.pad, self.uplinked_pad = empty_pad(), None
        self.selected_field, self.typed, self.entry_error = None, '', False
        self._pad_changed()

    def receive_uplink(self, payload):
        try:
            delta_v = [float(component) for component in payload['dv']]
            if len(delta_v) != 3:
                raise ValueError('a PAD has three Δv components')
            self.uplinked_pad = {'tig': float(payload['tig_met']), 'dv': delta_v}
        except (KeyError, TypeError, ValueError):
            self.uplinked_pad, self.entry_error = None, True

    def accept_uplink(self):
        if self.uplinked_pad:
            self.pad, self.uplinked_pad = self.uplinked_pad, None
            self.selected_field, self.typed = None, ''
            self._pad_changed()

    # ---------- keying ----------
    def select_field(self, field):
        """A field button: start keying that field, also when it is selected already (ENTR moves on to the next field
        by itself, and a crew presses that field's button anyway: a toggle deselected it, and the keys then went into
        TIG). CLR leaves a field."""
        self.entry_error = False
        self.selected_field = field
        self.typed = ''

    def press_key(self, key):
        if key not in KEYS:
            return
        if key == 'CLR':
            self._clear_one_level()
            return
        if self.selected_field is None:
            if key == 'ENTR':
                self.accept_uplink()
                return
            self.selected_field, self.typed = 'tig', ''     # keying with no field selected starts at TIG
        if key == 'ENTR':
            self._store_field()
        elif self.selected_field == 'tig':
            self._type_time_digit(key)
        else:
            self._type_delta_v_character(key)

    def _clear_one_level(self):
        """CLR undoes one thing: what is typed, else the field selection, else a waiting uplink."""
        if self.typed:
            self.typed = ''
        elif self.selected_field:
            self.selected_field = None
        else:
            self.uplinked_pad = None
        self.entry_error = False

    def _type_time_digit(self, key):
        if key.isdigit() and len(self.typed) < TIG_DIGITS:
            self.typed += key
        else:
            self.entry_error = True

    def _type_delta_v_character(self, key):
        typed = self.typed
        if key == '-':                                      # the sign key toggles the sign at any time
            self.typed = typed[1:] if typed.startswith('-') else '-' + typed
        elif key == '.':
            if '.' in typed:
                self.entry_error = True
            else:
                self.typed = typed + ('0.' if typed in ('', '-') else '.')
        else:
            whole, _, decimals = typed.lstrip('-').partition('.')
            too_long = len(decimals) >= 1 if '.' in typed else len(whole) >= DELTA_V_WHOLE_DIGITS
            if too_long:
                self.entry_error = True
            else:
                self.typed = typed + key

    def _store_field(self):
        field, typed = self.selected_field, self.typed
        if typed not in ('', '-'):
            if field == 'tig':
                digits = typed.rjust(TIG_DIGITS, '0')
                hours, minutes, seconds = int(digits[:2]), int(digits[2:4]), int(digits[4:])
                if minutes >= 60 or seconds >= 60:
                    self.entry_error, self.typed = True, ''
                    return
                self.pad['tig'] = float(hours * 3600 + minutes * 60 + seconds)
            else:
                self.pad['dv'][FIELDS.index(field) - 1] = float(typed)
            self._pad_changed()
        self.entry_error = False
        next_index = FIELDS.index(field) + 1
        self.selected_field = FIELDS[next_index] if next_index < len(FIELDS) else None
        self.typed = ''

    # ---------- the burn ----------
    def arm(self, on):
        if on and not self.armed:
            self.delta_v_counted, self.cutoff, self.last_mission_time = 0.0, False, None
        self.armed = bool(on)

    def count_delta_v(self, telemetry):
        """The cutoff is on accumulated Δv (course TM-10): thrust / mass integrated over game time, so a paused or
        warped game counts correctly."""
        vessel = telemetry.get('tlm/vessel', {})
        mission_time = telemetry.get('tlm/time', {}).get('met')
        if mission_time is None:
            return
        counting = self.armed and self.has_pad() and self.last_mission_time is not None and vessel.get('mass')
        if counting and mission_time > self.last_mission_time:
            elapsed = mission_time - self.last_mission_time
            acceleration = (vessel.get('thrust') or 0.0) / vessel['mass']
            self.delta_v_counted += acceleration * elapsed
            # Cut early by what will still be gained: half a telemetry period (the mean age of the sample when the
            # limit is crossed) plus the time the command takes to reach the engine.
            still_to_come = acceleration * (elapsed / 2 + COMMAND_LATENCY_S)
            if not self.cutoff and 0 < self.delta_v_total() <= self.delta_v_counted + still_to_come:
                self.cutoff = True
        self.last_mission_time = mission_time

    def time_from_ignition(self, telemetry):
        """Seconds since TIG (negative before it), or None without a PAD or a clock."""
        mission_time = telemetry.get('tlm/time', {}).get('met')
        if mission_time is None or not self.has_pad():
            return None
        return mission_time - self.pad['tig']

    def burn_time(self, telemetry):
        """Seconds of burn for the Δv to go at full thrust (rocket equation, course TM-4); None with no thrust.
        Known as soon as a Δv is keyed, before the TIG: the crew needs it to centre the burn on its event."""
        vessel = telemetry.get('tlm/vessel', {})
        mass, thrust, specific_impulse = vessel.get('mass'), vessel.get('thrust_avail'), vessel.get('isp')
        if not (mass and thrust and specific_impulse) or self.delta_v_total() == 0:
            return None
        exhaust_velocity = specific_impulse * STANDARD_GRAVITY
        return mass * exhaust_velocity / thrust * (1 - math.exp(-max(0.0, self.delta_v_to_go()) / exhaust_velocity))

    def state(self, telemetry):
        """idle (no PAD), ready, armed, burn (armed and thrusting) or done (cut off)."""
        if not self.has_pad():
            return 'idle'
        if self.cutoff:
            return 'done'
        if self.armed:
            return 'burn' if (telemetry.get('tlm/vessel', {}).get('thrust') or 0) > 0 else 'armed'
        return 'ready'

    # ---------- the panel ----------
    def render(self, outputs, telemetry, powered, lamp_test, telemetry_fresh):
        """Draw the computer's panel into `outputs` (a PanelOutputs)."""
        if not powered:
            outputs.all_dark(LAMPS, DISPLAYS)
            return
        if lamp_test:
            outputs.all_lit(LAMPS, DISPLAYS)
            return
        self._render_pad_fields(outputs)
        time_from_ignition = self.time_from_ignition(telemetry)
        burn_time = self.burn_time(telemetry)
        state = self.state(telemetry)
        node = telemetry.get('tlm/node', {})
        attitude_error = node.get('att_err') if self.has_pad() and node.get('set') else None

        known = lambda value: value is not None and telemetry_fresh
        outputs.text('disp_tfi', format_event_time(time_from_ignition) if known(time_from_ignition) else '--.--')
        to_go = self.delta_v_to_go()
        outputs.text('disp_vg', fit_number(to_go, 1, 5, signed=to_go < 0) if self.has_pad() else '-----')
        outputs.text('disp_tb', fit_number(burn_time, 1, 4) if known(burn_time) else '----')
        outputs.text('disp_att', fit_number(attitude_error, 1, 4) if known(attitude_error) else '----')

        for field in FIELDS:
            outputs.lamp(f'led_f_{field}', self.selected_field == field)
        outputs.lamp('lamp_uplink', self.uplinked_pad is not None, blink=True)
        outputs.lamp('led_burn_arm', self.armed, blink=not self.has_pad())      # armed with nothing to burn
        near_ignition = (time_from_ignition is not None and state in ('ready', 'armed')
                         and -TIG_LAMP_FROM_S <= time_from_ignition < TIG_LAMP_FROM_S)
        outputs.lamp('lamp_tig', near_ignition, blink=near_ignition and time_from_ignition >= -TIG_LAMP_BLINKS_FROM_S)
        outputs.lamp('lamp_burn', state == 'burn')
        outputs.lamp('lamp_cutoff', state == 'done')
        outputs.lamp('lamp_err', self.entry_error)

    def _render_pad_fields(self, outputs):
        """The four PAD displays: a waiting uplink blinks; the field being keyed shows what is typed and a cursor.
        A field just selected keeps its stored value until the first key (its LED says it is selected)."""
        shown = self.uplinked_pad or self.pad
        uplink_waiting = self.uplinked_pad is not None
        values = {'tig': format_mission_time(shown['tig']) if shown['tig'] is not None else '--.--.--'}
        for index, field in enumerate(FIELDS[1:]):
            values[field] = fit_number(shown['dv'][index], 1, 5, signed=True)
        for field in FIELDS:
            if self.selected_field == field and self.typed and not uplink_waiting:
                outputs.text(f'disp_{field}', self.typed + '_')
            else:
                outputs.text(f'disp_{field}', values[field], blink=uplink_waiting)
