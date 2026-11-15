"""Burn computer: holds one PAD and runs the burn. Pure logic (no I/O); times are mission elapsed time (tlm/time met).

A PAD is what Mission Control reads up: TIG (ignition time) and Δv as prograde / normal / radial components (m/s).

    c = Computer()
    c.select('tig'); c.key('0'); ...; c.key('ENTR')     # key a field: one display per field, the one being keyed blinks
    c.uplink({'tig_met': s, 'dv': [pro, nrm, rad]})     # from Mission Control: shown blinking until accept() (CLR rejects)
    c.arm(True)                                         # BURN ARM: zero the Δv counter and count thrust / mass from now
    c.step(tlm)                                         # on every tlm/vessel message
    c.cutoff                                            # True once the PAD's Δv has been counted (the cockpit cuts the throttle)

Keys: 0-9, '.', '-' (sign), CLR, ENTR. TIG is keyed as hhmmss (13045 → 01:30:45), Δv in m/s with one decimal.
ENTR stores the field and moves to the next one; ENTR on an empty field keeps its value.
"""
from dataclasses import dataclass, field
import math
from fmt import fit, fmt_evt, fmt_met

G0 = 9.80665
FIELDS = ['tig', 'pro', 'nrm', 'rad']
KEYS = set('0123456789.-') | {'CLR', 'ENTR'}
LAMPS = ['led_f_tig', 'led_f_pro', 'led_f_nrm', 'led_f_rad', 'lamp_uplink', 'led_burn_arm', 'lamp_tig', 'lamp_burn',
         'lamp_cutoff', 'lamp_err']
DISPS = ['disp_tig', 'disp_pro', 'disp_nrm', 'disp_rad', 'disp_tfi', 'disp_vg', 'disp_tb', 'disp_att']
TIG_WARN_S, TIG_BLINK_S = 60.0, 10.0
CMD_LATENCY_S = 0.05


@dataclass
class Computer:
    pad: dict = field(default_factory=lambda: {'tig': None, 'dv': [0.0, 0.0, 0.0]})
    pending: dict | None = None         # uplinked PAD, waiting for the crew to accept it
    field: str | None = None            # field being keyed
    buf: str = ''
    err: bool = False
    armed: bool = False
    dv_acc: float = 0.0
    last_met: float | None = None
    cutoff: bool = False
    rev: int = 0                        # bumps whenever the PAD changes

    # ---------- PAD ----------
    def loaded(self):
        return self.pad['tig'] is not None

    def dv_mag(self):
        return math.sqrt(sum(x * x for x in self.pad['dv']))

    def _changed(self):
        self.rev += 1
        self.dv_acc, self.cutoff, self.last_met = 0.0, False, None

    def select(self, f):
        """A field button: start keying that field (pressing it again leaves the field unchanged)."""
        self.err = False
        self.field, self.buf = (None if self.field == f else f), ''

    def uplink(self, p):
        try:
            self.pending = {'tig': float(p['tig_met']), 'dv': [float(x) for x in p['dv']][:3]}
            if len(self.pending['dv']) != 3:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            self.pending, self.err = None, True

    def accept(self):
        if self.pending:
            self.pad, self.pending, self.field, self.buf = self.pending, None, None, ''
            self._changed()

    def load(self, tig, dv):
        """A PAD from outside the keypad (a maneuver node made in the game)."""
        self.pad = {'tig': float(tig), 'dv': [float(x) for x in dv]}
        self.field, self.buf = None, ''
        self._changed()

    def clear(self):
        self.pad = {'tig': None, 'dv': [0.0, 0.0, 0.0]}
        self.pending, self.field, self.buf, self.err = None, None, '', False
        self._changed()

    def key(self, k):
        if k not in KEYS:
            return
        if k == 'CLR':
            if self.buf:
                self.buf = ''
            elif self.field:
                self.field = None
            else:
                self.pending = None             # reject an uplink
            self.err = False
            return
        if self.field is None:
            if k == 'ENTR':
                if self.pending:
                    self.accept()
                return
            self.field, self.buf = 'tig', ''    # keying with no field selected starts at TIG
        if k == 'ENTR':
            self._store()
            return
        b = self.buf
        if self.field == 'tig':
            if k.isdigit() and len(b) < 6:
                self.buf = b + k
            else:
                self.err = True
            return
        if k == '-':
            self.buf = b[1:] if b.startswith('-') else '-' + b
        elif k == '.':
            if '.' in b:
                self.err = True
            else:
                self.buf = b + ('0.' if b in ('', '-') else '.')
        else:
            whole, _, frac = b.lstrip('-').partition('.')
            if ('.' in b and len(frac) >= 1) or ('.' not in b and len(whole) >= 4):
                self.err = True
            else:
                self.buf = b + k

    def _store(self):
        f, b = self.field, self.buf
        if b not in ('', '-'):
            if f == 'tig':
                d = b.rjust(6, '0')
                h, m, s = int(d[:2]), int(d[2:4]), int(d[4:])
                if m >= 60 or s >= 60:
                    self.err, self.buf = True, ''
                    return
                self.pad['tig'] = float(h * 3600 + m * 60 + s)
            else:
                self.pad['dv'][FIELDS.index(f) - 1] = float(b)
            self._changed()
        self.err = False
        i = FIELDS.index(f) + 1
        self.field, self.buf = (FIELDS[i] if i < len(FIELDS) else None), ''

    # ---------- burn ----------
    def arm(self, on):
        if on and not self.armed:
            self.dv_acc, self.cutoff, self.last_met = 0.0, False, None
        self.armed = bool(on)

    def step(self, tlm):
        """Δv counter (TM-10: the cutoff is on accumulated Δv, thrust / mass integrated over game time)."""
        ve = tlm.get('tlm/vessel', {})
        met = tlm.get('tlm/time', {}).get('met')
        if met is None:
            return
        if self.armed and self.loaded() and self.last_met is not None and met > self.last_met and ve.get('mass'):
            dt = met - self.last_met
            a = (ve.get('thrust') or 0.0) / ve['mass']
            self.dv_acc += a * dt
            # cut early by what will still be gained: half a telemetry period (the sample's mean age when the limit
            # is crossed) plus the time the command takes to reach the engine
            if not self.cutoff and self.dv_mag() > 0 and self.dv_acc + a * (dt / 2 + CMD_LATENCY_S) >= self.dv_mag():
                self.cutoff = True
        self.last_met = met

    def vg(self):
        """Δv still to gain; negative after an overshoot (the residual)."""
        return self.dv_mag() - self.dv_acc

    def tfi(self, tlm):
        met = tlm.get('tlm/time', {}).get('met')
        return None if met is None or not self.loaded() else met - self.pad['tig']

    def burn_time(self, tlm):
        """Seconds of burn for the Δv to go at full thrust (rocket equation, TM-4), or None with no thrust available."""
        ve = tlm.get('tlm/vessel', {})
        m, F, isp = ve.get('mass'), ve.get('thrust_avail'), ve.get('isp')
        if not (m and F and isp) or not self.loaded():
            return None
        c = isp * G0
        return m * c / F * (1 - math.exp(-max(0.0, self.vg()) / c))

    def state(self, tlm):
        if not self.loaded():
            return 'idle'
        if self.cutoff:
            return 'done'
        if self.armed:
            return 'burn' if (tlm.get('tlm/vessel', {}).get('thrust') or 0) > 0 else 'armed'
        return 'ready'

    # ---------- display ----------
    def render(self, tlm, powered=True, lamp_test=False, fresh=True):
        out = {}
        if not powered or lamp_test:
            for d in DISPS:
                out[d] = {'text': '8.8.8.8.8.8.' if powered else '', 'blank': not powered}
            for l in LAMPS:
                out[l] = {'on': powered, 'blink': False}
            return out
        show = self.pending or self.pad
        pend = self.pending is not None

        def disp(name, f, text):
            if self.field == f and not pend:
                out[name] = {'text': self.buf + '_', 'blank': False, 'blink': False}     # steady, with a cursor
            else:
                out[name] = {'text': text, 'blank': False, 'blink': pend}
        disp('disp_tig', 'tig', fmt_met(show['tig']) if show['tig'] is not None else '--.--.--')
        for i, f in enumerate(FIELDS[1:]):
            disp(f'disp_{f}', f, fit(show['dv'][i], 1, 5, signed=True))
        tfi, tb, st = self.tfi(tlm), self.burn_time(tlm), self.state(tlm)
        out['disp_tfi'] = {'text': fmt_evt(tfi) if tfi is not None and fresh else '--.--', 'blank': False}
        out['disp_vg'] = {'text': fit(self.vg(), 1, 5, signed=self.vg() < 0) if self.loaded() else '-----', 'blank': False}
        out['disp_tb'] = {'text': fit(tb, 1, 4) if tb is not None and fresh else '----', 'blank': False}
        att = tlm.get('tlm/node', {}).get('att_err') if self.loaded() and tlm.get('tlm/node', {}).get('set') else None
        out['disp_att'] = {'text': fit(att, 1, 4) if att is not None and fresh else '----', 'blank': False}
        lamps = {l: (False, False) for l in LAMPS}
        for f in FIELDS:
            lamps[f'led_f_{f}'] = (self.field == f, False)
        lamps['lamp_uplink'] = (pend, True)
        lamps['led_burn_arm'] = (self.armed, not self.loaded())
        if tfi is not None and st in ("ready", "armed") and -TIG_WARN_S <= tfi < TIG_WARN_S:
            lamps['lamp_tig'] = (True, tfi >= -TIG_BLINK_S)
        lamps['lamp_burn'] = (st == 'burn', False)
        lamps['lamp_cutoff'] = (st == 'done', False)
        lamps['lamp_err'] = (self.err, False)
        for l, (on, b) in lamps.items():
            out[l] = {'on': on, 'blink': on and b}
        return out
