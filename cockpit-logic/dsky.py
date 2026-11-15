"""DSKY: Apollo-style verb/noun computer interface, as pure logic (no I/O, time passed in).

    d = Dsky()
    d.key('VERB', now, tlm); d.key('3', ...); ...     # one call per key press
    d.uplink({'tig_met': s, 'dv': [pro, nrm, rad]}, now)
    outs = d.render(now, tlm)                          # {output name: payload} for the panel
    d.cutoff                                           # True once P40 has counted the PAD's Δv (the cockpit cuts the throttle)

Keys: 0-9, +, -, VERB, NOUN, ENTR, CLR, PRO, KREL, RSET.
Verbs: 06 display once, 16 monitor, 21/22/23 load R1/R2/R3, 24 load R1-R2, 25 load R1-R3, 34 terminate,
       35 lamp test, 37 change program, 82 orbit (shows N44).
Nouns: 33 TIG (h, min, s), 36 MET (h, min, s), 40 TFI / VG / ΔV accumulated, 42 apo / peri / ΔV,
       43 lat / lon / alt, 44 apo / peri / time to apo, 60 hor. speed / vert. speed / radar alt, 62 speed / vert. speed / alt,
       81 ΔV prograde / normal / radial.
Programs: 00 idle, 30 external Δv (load TIG and Δv: flashing V06N33, V06N81, V06N42; PRO accepts each),
          40 burn (V16N40; flashing V99N40 at TIG−5 s asks for engine enable; Δv counter; cutoff at VG = 0).
Times are mission elapsed time (tlm/time met), distances km, speeds m/s, angles degrees.
"""
from dataclasses import dataclass, field
import math

G0 = 9.80665
KEYS = set('0123456789+-') | {'VERB', 'NOUN', 'ENTR', 'CLR', 'PRO', 'KREL', 'RSET'}
VERBS = {6, 16, 21, 22, 23, 24, 25, 34, 35, 37, 82, 99}
NOUNS = {33, 36, 40, 42, 43, 44, 60, 62, 81}
LOADABLE = {33, 81}
LAMPS = ['dsky_comp_acty', 'dsky_uplink', 'dsky_no_att', 'dsky_stby', 'dsky_key_rel', 'dsky_opr_err', 'dsky_prog',
         'dsky_temp', 'dsky_tracker', 'dsky_vel']


def reg(x, dec=1, width=5):
    """Register text: sign and `width` digits, with a decimal point (a digit carries it), right-aligned on 6 cells."""
    if x is None or not math.isfinite(x):
        return ''
    s = '+' if x >= 0 else '-'
    for d in range(dec, -1, -1):
        body = f'{abs(x):0{width + (1 if d else 0)}.{d}f}'
        if len(body.replace('.', '')) <= width:
            return s + body
    return s + '9' * width


def hms(t):
    t = max(0.0, t or 0.0)
    return int(t // 3600), int(t // 60 % 60), t % 60


@dataclass
class Dsky:
    prog: int = 0
    verb: int | None = None
    noun: int | None = None
    flash: bool = False                 # verb/noun flashing: the computer waits for the crew
    mode: str = 'idle'                  # idle, verb, noun, load, prog
    buf: str = ''                       # digits being keyed (verb, noun, register or program)
    load_regs: list = field(default_factory=list)   # registers still to load (V21–V25)
    loaded: dict = field(default_factory=dict)      # register values keyed so far
    frozen: tuple | None = None         # V06 snapshot
    opr_err: bool = False
    prog_alarm: bool = False
    key_rel: bool = False
    lamp_test_until: float = -1.0
    uplink_until: float = -1.0
    activity_until: float = -1.0
    pad: dict = field(default_factory=lambda: {'tig': None, 'dv': [0.0, 0.0, 0.0]})
    step: int = 0                       # step inside P30/P40
    dv_acc: float = 0.0
    last_t: float | None = None
    enabled: bool = False               # P40: crew answered V99 (engine enable)
    cutoff: bool = False
    saved: tuple | None = None          # program display, kept while the crew keys something else (KEY REL)

    # ---------- keys ----------
    def key(self, k, now, tlm):
        if k not in KEYS:
            return
        self.activity_until = now + 0.3
        if k == 'RSET':
            self.opr_err = self.prog_alarm = False
            return
        if k == 'KREL':
            if self.saved:
                self.verb, self.noun, self.flash = self.saved
                self.saved, self.key_rel, self.mode, self.buf = None, False, 'idle', ''
            return
        if k == 'CLR':
            self.buf = ''
            return
        if k == 'VERB':
            self._take_keyboard()
            self.mode, self.buf = 'verb', ''
            return
        if k == 'NOUN':
            if self.mode in ('verb', 'noun', 'idle'):
                if self.mode == 'verb' and self.buf:
                    self._commit_verb()
                self.mode, self.buf = 'noun', ''
            return
        if k == 'PRO':
            self._proceed(now, tlm)
            return
        if k == 'ENTR':
            self._enter(now, tlm)
            return
        # digits and signs
        if self.mode in ('verb', 'noun', 'prog'):
            if k.isdigit() and len(self.buf) < 2:
                self.buf += k
            elif not k.isdigit():
                self.opr_err = True
        elif self.mode == 'load':
            if k in '+-':
                self.buf = k if not self.buf else self.buf
                if self.buf != k:
                    self.opr_err = True
            elif k.isdigit():
                if not self.buf and self.noun != 33:
                    self.opr_err = True            # signed data must start with + or −
                elif len(self.buf.lstrip('+-')) < 5:
                    self.buf += k
        else:
            self.opr_err = True

    def _take_keyboard(self):
        if self.flash and not self.saved:
            self.saved = (self.verb, self.noun, self.flash)
            self.key_rel = True

    def _commit_verb(self):
        self.verb = int(self.buf)

    def _enter(self, now, tlm):
        if self.mode == 'verb':
            if self.buf:
                self._commit_verb()
            self.mode, self.buf = 'idle', ''
            if self.verb == 37:
                self.mode = 'prog'
                return
            if self.verb == 35:
                self.lamp_test_until = now + 5
                return
            if self.verb == 34:
                self._start_prog(0, now)
                return
            if self.verb == 82:
                self.verb, self.noun, self.flash = 16, 44, False
                return
            if self.verb not in VERBS:
                self.opr_err = True
                return
            if self.verb in (21, 22, 23, 24, 25) and self.noun in LOADABLE:
                # V25 ENTR with no noun keyed: load the noun on display (P30's flashing V06N33 / V06N81)
                self.saved, self.key_rel = None, False
                self._begin_load()
            return
        if self.mode == 'noun':
            if not self.buf:
                self.opr_err = True
                return
            self.noun = int(self.buf)
            self.mode, self.buf = 'idle', ''
            if self.verb not in VERBS or self.noun not in NOUNS:
                self.opr_err = True
                return
            if self.verb in (21, 22, 23, 24, 25):
                if self.noun not in LOADABLE:
                    self.opr_err = True
                    return
                self._begin_load()
                return
            if self.verb == 6:
                self.frozen = self.values(self.noun, now, tlm)
            return
        if self.mode == 'prog':
            if len(self.buf) != 2 or int(self.buf) not in (0, 30, 40):
                self.opr_err = True
                self.mode, self.buf = 'idle', ''
                return
            p = int(self.buf)
            self.mode, self.buf = 'idle', ''
            self._start_prog(p, now)
            return
        if self.mode == 'load':
            if not self.buf.lstrip('+-'):
                self.opr_err = True
                return
            r = self.load_regs.pop(0)
            sign = -1 if self.buf.startswith('-') else 1
            self.loaded[r] = sign * int(self.buf.lstrip('+-'))
            self.buf = ''
            if not self.load_regs:
                self._store(now, tlm)
                self.mode = 'idle'
            return
        # ENTR with nothing keyed: in a flashing V06 display it is the same as PRO
        if self.flash:
            self._proceed(now, tlm)

    def _begin_load(self):
        self.load_regs = {21: [1], 22: [2], 23: [3], 24: [1, 2], 25: [1, 2, 3]}[self.verb]
        self.loaded, self.mode, self.buf = {}, 'load', ''

    def _store(self, now, tlm):
        L = self.loaded
        if self.noun == 33:
            h, m, s = self.values(33, now, tlm)[1]
            h = L.get(1, h)
            m = L.get(2, m)
            s = L.get(3, s * 100) / 100 if 3 in L else s
            if m >= 60 or s >= 60:
                self.opr_err = True
                return
            self.pad['tig'] = h * 3600 + m * 60 + s
        elif self.noun == 81:
            dv = list(self.pad['dv'])
            for i in (1, 2, 3):
                if i in L:
                    dv[i - 1] = L[i] / 10.0            # entered in 0.1 m/s
            self.pad['dv'] = dv
        # back to the program's display (still waiting for PRO)
        if self.prog == 30:
            self.verb, self.flash = 6, True
        self.dv_acc = 0.0

    def _start_prog(self, p, now):
        self.prog, self.step, self.saved, self.key_rel = p, 0, None, False
        self.enabled, self.cutoff, self.dv_acc, self.last_t = False, False, 0.0, None
        if p == 0:
            self.verb = self.noun = None
            self.flash = False
        elif p == 30:
            self.verb, self.noun, self.flash = 6, 33, True
        elif p == 40:
            if self.pad['tig'] is None:
                self.prog_alarm = True
                self.prog = 0
                self.verb = self.noun = None
                return
            self.verb, self.noun, self.flash = 16, 40, False

    def _proceed(self, now, tlm):
        if self.prog == 30 and self.flash:
            if self.noun == 33:
                self.noun = 81
            elif self.noun == 81:
                self.noun = 42
            elif self.noun == 42:
                self._start_prog(0, now)
            return
        if self.prog == 40 and self.verb == 99:
            self.enabled = True
            self.verb, self.flash = 16, False
            return
        if self.flash:
            self.flash = False

    def uplink(self, p, now):
        try:
            self.pad = {'tig': float(p['tig_met']), 'dv': [float(x) for x in p['dv']]}
        except (KeyError, TypeError, ValueError):
            self.opr_err = True
            return
        self.uplink_until = now + 3.0

    # ---------- the computer ----------
    def step_time(self, now, tlm):
        """Δv counter and P40 sequencing; call on every telemetry message."""
        ve = tlm.get('tlm/vessel', {})
        met = tlm.get('tlm/time', {}).get('met')
        t = now
        if self.prog == 40 and met is not None and self.pad['tig'] is not None:
            tfi = self.pad['tig'] - met
            if tfi <= 5 and not self.enabled and self.verb != 99:
                self.saved = None
                self.verb, self.noun, self.flash = 99, 40, True
            # count thrust/mass once the engine is enabled (TM-10: the cutoff is on accumulated Δv)
            if self.enabled and self.last_t is not None and ve.get('mass'):
                self.dv_acc += (ve.get('thrust', 0.0) / ve['mass']) * (t - self.last_t)
            if self.enabled and self.dv_acc >= self.dv_mag() > 0:
                self.cutoff = True
        self.last_t = t

    def dv_mag(self):
        return math.sqrt(sum(x * x for x in self.pad['dv']))

    def values(self, noun, now, tlm):
        """(kind, data) for a noun: kind 'num' → three numbers; kind 'hms' → (h, m, s)."""
        fl, orb = tlm.get('tlm/flight', {}), tlm.get('tlm/orbit', {})
        met = tlm.get('tlm/time', {}).get('met')
        km = lambda x: None if x is None else x / 1000.0
        if noun == 33:
            return ('hms', hms(self.pad['tig']) if self.pad['tig'] is not None else (0, 0, 0.0))
        if noun == 36:
            return ('hms', hms(met))
        if noun == 40:
            tfi = (met - self.pad['tig']) if (met is not None and self.pad['tig'] is not None) else None
            vg = max(0.0, self.dv_mag() - self.dv_acc)
            return ('n40', (tfi, vg, self.dv_acc))
        if noun == 42:
            return ('num', ((km(orb.get('apo')), 1), (km(orb.get('peri')), 1), (self.dv_mag(), 1)))
        if noun == 43:
            return ('num', ((fl.get('lat'), 2), (fl.get('lon'), 2), (km(fl.get('alt')), 1)))
        if noun == 44:
            t = orb.get('t_apo')
            return ('mmss', ((km(orb.get('apo')), 1), (km(orb.get('peri')), 1), t))
        if noun == 60:
            return ('num', ((fl.get('hs'), 1), (fl.get('vs'), 1), (fl.get('radar'), 0)))
        if noun == 62:
            return ('num', ((fl.get('speed'), 0), (fl.get('vs'), 1), (km(fl.get('alt')), 1)))
        if noun == 81:
            return ('num', tuple((x, 1) for x in self.pad['dv']))
        return ('num', ((None, 0),) * 3)

    # ---------- display ----------
    def render(self, now, tlm, powered=True, fresh=True):
        out = {}
        o = lambda k, v: out.__setitem__(k, v)
        if not powered:
            for r in ('dsky_prog', 'dsky_verb', 'dsky_noun', 'dsky_r1', 'dsky_r2', 'dsky_r3'):
                o(f'{r}_disp', {'text': '', 'blank': True})
            for l in LAMPS:
                o(l, {'on': False, 'blink': False})
            return out
        if now < self.lamp_test_until:
            for r, n in (('dsky_prog', 2), ('dsky_verb', 2), ('dsky_noun', 2)):
                o(f'{r}_disp', {'text': '88', 'blank': False})
            for r in ('dsky_r1', 'dsky_r2', 'dsky_r3'):
                o(f'{r}_disp', {'text': '+88888', 'blank': False})
            for l in LAMPS:
                o(l, {'on': True, 'blink': l in ('dsky_opr_err', 'dsky_key_rel')})
            o('dsky_verb_disp', {'text': '88', 'blank': False, 'blink': True})
            o('dsky_noun_disp', {'text': '88', 'blank': False, 'blink': True})
            return out
        two = lambda x: '' if x is None else f'{x:02d}'
        o('dsky_prog_disp', {'text': two(self.prog), 'blank': False})
        verb_text = self.buf if self.mode == 'verb' else two(self.verb)
        noun_text = self.buf if self.mode == 'noun' else two(self.noun)
        if self.mode == 'prog':
            o('dsky_prog_disp', {'text': self.buf, 'blank': False, 'blink': False})
        blink = self.flash and self.mode == 'idle'
        o('dsky_verb_disp', {'text': verb_text, 'blank': False, 'blink': blink})
        o('dsky_noun_disp', {'text': noun_text, 'blank': False, 'blink': blink})
        regs = ['', '', '']
        if self.noun in NOUNS and self.verb is not None and fresh:
            kind, data = self.frozen if (self.verb == 6 and self.frozen and not self.flash) else self.values(self.noun, now, tlm)
            if kind == 'hms':
                h, m, s = data
                regs = [f'+{h:05d}', f'+{m:05d}', '+' + f'{s:06.2f}'.rjust(6, '0')]
            elif kind == 'n40':
                tfi, vg, acc = data
                if tfi is None:
                    regs[0] = ''
                else:
                    a = abs(tfi)
                    mm, ss = min(99, int(a // 60)), int(a % 60)
                    regs[0] = ('-' if tfi < 0 else '+') + f'{mm:02d} {ss:02d}'
                regs[1], regs[2] = reg(vg, 1), reg(acc, 1)
            elif kind == 'mmss':
                (a, da), (b, db), t = data
                regs[0], regs[1] = reg(a, da), reg(b, db)
                if t is not None:
                    mm, ss = min(999, int(t // 60)), int(t % 60)
                    regs[2] = f'+{mm:03d}{ss:02d}' if mm >= 100 else f'+{mm:02d} {ss:02d}'
            else:
                regs = [reg(v, d) for v, d in data]
        if self.mode == 'load':
            # registers being loaded show what is keyed, the others are blank until entered
            r = self.load_regs[0] if self.load_regs else None
            for i in (1, 2, 3):
                if i == r:
                    regs[i - 1] = self.buf
                elif i in self.loaded:
                    regs[i - 1] = f"{'+' if self.loaded[i] >= 0 else '-'}{abs(self.loaded[i]):05d}"
                elif i in self.load_regs:
                    regs[i - 1] = ''
            o('dsky_verb_disp', {'text': two(self.verb), 'blank': False, 'blink': True})
            o('dsky_noun_disp', {'text': two(self.noun), 'blank': False, 'blink': True})
        for i, t in enumerate(regs, 1):
            o(f'dsky_r{i}_disp', {'text': t, 'blank': False})
        lamps = {l: (False, False) for l in LAMPS}
        lamps['dsky_comp_acty'] = (now < self.activity_until or (self.prog == 40 and self.enabled and not self.cutoff), False)
        lamps['dsky_uplink'] = (now < self.uplink_until, False)
        lamps['dsky_no_att'] = ('tlm/attitude' not in tlm or not fresh, False)
        lamps['dsky_key_rel'] = (self.key_rel, True)
        lamps['dsky_opr_err'] = (self.opr_err, True)
        lamps['dsky_prog'] = (self.prog_alarm, False)
        lamps['dsky_vel'] = (self.cutoff, False)
        for l, (on, b) in lamps.items():
            o(l, {'on': on, 'blink': on and b})
        return out
