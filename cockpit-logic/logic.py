"""Cockpit logic: the rules KSP does not model (PLAN.md §1). Pure: no I/O, time is passed in.

    c = Cockpit()
    out = c.handle(topic, payload_dict, now)   # → list of Msg to publish
    out = c.tick(now)                          # call every ~0.25 s: staleness, re-assert, displays

Outputs are rendered from the whole state and only changes are published (retained), so a panel that reconnects gets
the full picture from the broker.
"""
from dataclasses import dataclass, field
import math
from dsky import Dsky
from computer import Computer
from fmt import fit, fmt_evt, fmt_met, fit7  # noqa: F401 (re-exported)

PANEL = 'eng'
SYS = 'sys'
DSKY = 'dsky'
CMP = 'cmp'
RDV = 'rdv'
# for TWR and the stage Δv: (μ, R) of the bodies a Mun trip visits
BODIES = {'Kerbin': (3.5316e12, 600000.0), 'Mun': (6.5138398e10, 200000.0), 'Minmus': (1.7658e9, 60000.0)}
# lowest safe periapsis (m): top of the atmosphere, or just above the highest terrain
SAFE_PERI = {'Kerbin': 70000.0, 'Mun': 7100.0, 'Minmus': 5800.0}
EVT_SRC = ['MAN', 'TIG', 'APO', 'PERI', 'SOI']
CUTOFF_RESET = 0.05             # the throttle lever must come back under 5 % after a DSKY cutoff
STALE_S = 2.0
REASSERT_S = 1.0
DISAGREE_S = 2.0
G_LIMIT = 5.0
Q_LIMIT = 30000.0
LOW_FUEL = 0.10
LOW_POWER = 0.20

SAS_MODES = ['stability', 'prograde', 'retrograde', 'normal', 'antinormal', 'radial', 'antiradial', 'target', 'antitarget',
             'maneuver']
DISP_SEL = ['ALT', 'APO', 'PERI', 'VEL', 'V/S', 'MASS']
# C&W items: id → (legend, class) ; class 'W' = warning (master alarm, red), 'C' = caution (master caution, amber)
CW = {
    'cw_low_fuel': ('LOW FUEL', 'C'),
    'cw_high_g': ('HIGH G', 'W'),
    'cw_low_power': ('LOW POWER', 'C'),
    'cw_no_link': ('NO LINK', 'W'),
    'cw_sas_dis': ('SAS DISAGREE', 'C'),
    'cw_q': ('HIGH Q', 'C'),
    'cw_flameout': ('FLAMEOUT', 'C'),
    'cw_eng_fail': ('ENG FAIL', 'W'),
    'cw_rcs_low': ('RCS LOW', 'C'),
    'cw_sink': ('SINK RATE', 'W'),
    'cw_closing': ('CLOSING', 'C'),
    'cw_throttle': ('THROTTLE', 'C'),
    'cw_overheat': ('OVERHEAT', 'W'),
    'cw_gear': ('GEAR UP', 'W'),
    'cw_att': ('ATT ERR', 'C'),
    'cw_resid': ('DV RESID', 'C'),
    'cw_peri': ('PERI LOW', 'C'),
    'cw_soi': ('SOI CHANGE', 'C'),
    'cw_chute': ('CHUTE', 'C'),
    'cw_comm': ('COMM LOST', 'C'),
}
OVERHEAT = 0.80                 # hottest part, fraction of its temperature limit
ATT_ERR_DEG, ATT_ERR_FROM_S = 5.0, 30.0     # off the burn attitude by more than this, from 30 s before TIG
RESID_MIN, RESID_FRAC = 0.5, 0.02           # Δv residual after cutoff: 0.5 m/s or 2 % of the burn
SOI_SOON_S = 120.0
GEAR_ALT, CHUTE_ALT = 300.0, 15000.0
G_ENTRY = 0.05                  # the 0.05 G light (Mercury): drag is felt, the entry has begun
ALIGN_DEG = 2.0                 # docking: yaw and pitch error under this lights ALIGNED
RCS_LOW = 0.10
ENG_FAIL_S = 1.0                # an engine with fuel that gives under half its thrust for this long
# rendezvous and docking (the course's docking chapter): braking gate ρ / 400 s with a 0.05 m/s floor; capture envelope
GATE_S, GATE_FLOOR, GATE_MARGIN = 400.0, 0.05, 1.2
CAPTURE = {'v_min': 0.03, 'v_max': 0.3, 'lateral': 0.3, 'angle': 10.0, 'within': 10.0}
WARP_LEAD_S = 60.0              # WARP TO EVT stops this long before the event
GRID = 9                        # engine display: GRID × GRID LEDs
# What ABORT does in each position of the mode selector. Steps: cut = throttle to 0 (held until the lever is back at
# idle), group = KSP's abort action group (what the craft's builder wired: escape tower, decouplers), stage = next stage,
# sas / sas_radial = SAS on in stability / radial-out, rcs = RCS on. The forced SAS and RCS states hold until the pilot
# moves that switch.
ABORT_MODES = ['PAD', 'ASCENT', 'ORBIT', 'DESCENT']
ABORT_SEQ = {
    'PAD': ('cut', 'group'),                        # escape tower
    'ASCENT': ('cut', 'stage', 'sas', 'rcs'),       # tower gone: leave the launcher by staging
    'ORBIT': ('cut', 'sas', 'rcs'),                 # stop the burn, nothing is thrown away
    'DESCENT': ('group', 'sas_radial', 'rcs'),      # lander: abort group, nose up; the throttle stays with the pilot
}
LAMPS = ['master_alarm', 'master_caution', 'led_eng_arm', 'lamp_stage', 'led_sas', 'led_rcs', 'led_gear', 'led_lights',
         'lamp_abort', 'lamp_cutoff', 'led_gimbal', 'lamp_contact', 'lamp_05g', *CW]
TOGGLE_CMDS = {'sas': 'cmd/sas', 'rcs': 'cmd/rcs', 'gear': 'cmd/gear', 'lights': 'cmd/lights', 'brakes': 'cmd/brakes',
               'solar': 'cmd/solar'}
SYS_LAMPS = ['led_solar', 'led_brakes', 'lamp_chute', 'led_chute_armed', 'led_warp', 'led_evt_run', 'led_pause']
RDV_LAMPS = ['led_tgt', 'led_port', 'led_km', 'lamp_overspeed', 'lamp_capture', 'lamp_aligned', 'led_ctrl_port']
RDV_DISPS = ['disp_range', 'disp_closing', 'disp_gate', 'disp_los', 'disp_roll', 'disp_yaw', 'disp_pitch', 'disp_right',
             'disp_up', 'disp_vright', 'disp_vup', 'disp_axial', 'disp_vaxial']
PANEL_WINS = {'sas', 'rcs', 'lights'}     # re-sent while the game disagrees; gear: game wins (lamp only)


@dataclass
class Msg:
    topic: str
    payload: dict
    retain: bool = False
    qos: int = 0


@dataclass
class Cockpit:
    inputs: dict = field(default_factory=lambda: {'cb_main': 1})
    tlm: dict = field(default_factory=dict)          # topic → payload
    tlm_t: float = -1e9                              # last telemetry time
    link_up: bool = False
    acked: set = field(default_factory=set)          # C&W items acknowledged while active
    disagree_since: dict = field(default_factory=dict)
    last_sent: dict = field(default_factory=dict)    # output topic → payload (dedupe)
    last_cmd: dict = field(default_factory=dict)     # cmd topic → (payload, time)
    abort_fired: bool = False
    now: float = 0.0
    dsky: Dsky = field(default_factory=Dsky)
    cutoff_latched: bool = False                     # DSKY Δv cutoff holds the throttle at 0 until the lever is idle
    evt: dict = field(default_factory=lambda: {'run': False, 't0': None, 'acc': 0.0, 'preset': 0.0})
    node_sent: dict | None = None                    # the node last commanded or taken from the game
    ec_rate: float = 0.0
    ec_prev: tuple | None = None                     # (met, amount)
    cmp: Computer = field(default_factory=Computer)
    node_rev: int = 0                                # computer PAD revision mirrored to KSP as a maneuver node
    forced: dict = field(default_factory=dict)       # sas / rcs states an abort imposed, until the switch is moved
    eng_known: tuple = (None, frozenset())           # (stage, engine positions seen burning): a missing one is lost

    # ---------- inputs ----------
    def handle(self, topic, payload, now):
        self.now = now
        out = []
        parts = topic.split('/')
        if len(parts) == 4 and parts[0] == 'panel' and parts[2] == 'in':
            ctl, val = parts[3], payload.get('v')
            if parts[1] == DSKY and ctl == 'key':
                if self.powered() and self.inputs.get('cb_dsky', 1):
                    self.dsky.key(str(val), now, self.tlm)
                return self._render()
            if parts[1] == CMP and ctl == 'key':
                if self.powered():
                    self.cmp.key(str(val))
                return self._sync_node() + self._render()
            prev = self.inputs.get(ctl)
            self.inputs[ctl] = val
            out += self._on_input(ctl, prev, val)
        elif topic in ('pad/uplink', 'dsky/uplink'):    # Mission Control reads up a PAD: both computers get it
            self.dsky.uplink(payload, now)
            self.cmp.uplink(payload)
        elif parts[0] == 'tlm':
            self.tlm[topic] = payload
            self.tlm_t = now
            if topic == 'tlm/vessel':
                was = self.dsky.cutoff
                self.dsky.step_time(now, self.tlm)
                was_c = self.cmp.cutoff
                self.cmp.step(self.tlm)
                if (self.dsky.cutoff and not was) or (self.cmp.cutoff and not was_c):
                    self.cutoff_latched = True
                    out += self._throttle()
                    if self.cmp.cutoff and not was_c:
                        out += self._cmd('cmd/node', {'clear': True}, force=True)
            elif topic == 'tlm/resources':
                self._ec_rate()
            elif topic == 'tlm/node':
                self._adopt_node(payload)
        elif topic == 'gateway/status':
            self.link_up = bool(payload.get('connected'))
        return out + self._render()

    def tick(self, now):
        self.now = now
        out = []
        # panel-wins controls: re-send while the game disagrees
        v = self.tlm.get('tlm/vessel', {})
        if self.powered() and self.fresh():
            out += self._sync_node()
            for ctl in PANEL_WINS:
                want = self.forced.get(ctl, bool(self.inputs.get(ctl, 0)))
                if ctl in v and bool(v[ctl]) != want:
                    out += self._cmd(TOGGLE_CMDS[ctl], {'on': want}, min_interval=REASSERT_S)
        return out + self._render()

    def reset(self):
        """sim/reset: a new flight. Switch positions, the link and telemetry are facts about the world and are kept;
        latched cockpit state (abort, acknowledgements, disagree timers, command history) is cleared."""
        self.abort_fired = False
        self.dsky = Dsky()
        self.cmp = Computer()
        self.cmp.arm(bool(self.inputs.get('burn_arm')))
        self.node_rev = 0
        self.forced.clear()
        self.eng_known = (None, frozenset())
        self.cutoff_latched = False
        self.evt = {'run': False, 't0': None, 'acc': 0.0, 'preset': 0.0}
        self.node_sent = None
        self.acked.clear()
        self.disagree_since.clear()
        self.last_cmd.clear()
        return self._render()

    def powered(self):
        return bool(self.inputs.get('cb_main', 1))

    def fresh(self):
        return self.now - self.tlm_t <= STALE_S

    def _cmd(self, topic, payload, min_interval=0.0, force=False):
        last = self.last_cmd.get(topic)
        if not force and last and last[0] == payload and self.now - last[1] < min_interval:
            return []
        self.last_cmd[topic] = (payload, self.now)
        return [Msg(topic, payload, False, 1 if topic != 'cmd/throttle' else 0)]

    def _on_input(self, ctl, prev, val):
        out = []
        pressed = bool(val) and not bool(prev)
        if ctl in ('master_alarm', 'master_caution') and pressed:
            cls = 'W' if ctl == 'master_alarm' else 'C'
            self.acked |= {i for i in self.active() if CW[i][1] == cls}
        if not self.powered():
            if ctl == 'cb_main':
                out += self._cmd('cmd/throttle', {'v': 0.0}, force=True)
            return out
        changed = prev is not None and val is not None and val != prev   # not the first report of a position
        if ctl in ('throttle', 'eng_arm', 'cb_main'):
            out += self._throttle()
        elif ctl == 'eng_cutoff' and pressed:
            self.cutoff_latched = True
            out += self._throttle()
        elif ctl == 'thrust_lim' and changed:
            # only when the knob moves: limiters set in the VAB are left alone until then (selftest gaps G8, G9)
            out += self._cmd('cmd/thrust_limit', {'v': round(float(val) * 20) / 20}, min_interval=1e9)
        elif ctl == 'gimbal_lock' and changed:
            out += self._cmd('cmd/gimbal', {'locked': bool(val)}, force=True)
        elif ctl in ('f_tig', 'f_pro', 'f_nrm', 'f_rad') and pressed:
            self.cmp.select(ctl[2:])
        elif ctl == 'pad_accept' and pressed:
            self.cmp.accept()
            out += self._sync_node()
        elif ctl == 'pad_clr' and pressed:
            self.cmp.clear()
            out += self._sync_node()
        elif ctl == 'burn_arm' and val is not None:
            self.cmp.arm(bool(val))
        elif ctl in ('tgt_next', 'tgt_prev') and pressed:
            out += self._cmd('cmd/target', {'step': 1 if ctl == 'tgt_next' else -1}, force=True)
        elif ctl == 'tgt_clear' and pressed:
            out += self._cmd('cmd/target', {'clear': True}, force=True)
        elif ctl == 'port_next' and pressed:
            out += self._cmd('cmd/target', {'port': 1}, force=True)
        elif ctl == 'ctrl_port' and changed:
            out += self._cmd('cmd/control_from', {'port': bool(val)}, force=True)
        elif ctl == 'warp_to' and pressed:
            t = self._event_time()
            tm = self.tlm.get('tlm/time', {})
            if t is not None and -t > WARP_LEAD_S and tm.get('ut') is not None:
                out += self._cmd('cmd/warp', {'to_ut': round(tm['ut'] - t - WARP_LEAD_S, 1)}, force=True)
        elif ctl == 'pause' and changed:
            out += self._cmd('cmd/pause', {'on': bool(val)}, force=True)
        elif ctl in ('quicksave', 'quickload') and pressed and self.inputs.get('save_arm'):
            out += self._cmd('cmd/game', {ctl: True}, force=True)
        elif ctl == 'chute_deploy' and pressed and self.inputs.get('chute_arm'):
            out += self._cmd('cmd/chute', {'deploy': True}, force=True)
        elif ctl in ('warp_up', 'warp_down') and pressed:
            out += self._cmd('cmd/warp', {'step': 1 if ctl == 'warp_up' else -1}, force=True)
        elif ctl == 'warp_stop' and pressed:
            out += self._cmd('cmd/warp', {'stop': True}, force=True)
        elif ctl in ('evt_start', 'evt_stop', 'evt_reset', 'evt_min', 'evt_sec') and pressed:
            met = self.tlm.get('tlm/time', {}).get('met') or 0.0
            e = self.evt
            if ctl == 'evt_start' and not e['run']:
                e['run'], e['t0'] = True, met
            elif ctl == 'evt_stop' and e['run']:
                e['run'], e['acc'] = False, e['acc'] + met - e['t0']
            elif ctl == 'evt_reset':
                e.update(run=False, t0=None, acc=0.0, preset=0.0)
            elif not e['run']:                                # MIN + / SEC +: the countdown's starting value
                m, sec = divmod(e['preset'], 60)
                e['preset'] = ((m + 1) % 100) * 60 + sec if ctl == 'evt_min' else m * 60 + (sec + 10) % 60
                e['acc'] = 0.0
        elif ctl == 'stage' and pressed and self.inputs.get('stage_arm'):
            out += self._cmd('cmd/stage', {}, force=True)
        elif ctl == 'abort' and pressed and self.inputs.get('abort_arm'):
            self.abort_fired = True
            out += self._abort()
        elif ctl in TOGGLE_CMDS and val is not None:
            self.forced.pop(ctl, None)
            out += self._cmd(TOGGLE_CMDS[ctl], {'on': bool(val)}, force=True)
        elif ctl == 'sas_mode' and val is not None:
            out += self._cmd('cmd/sas_mode', {'mode': SAS_MODES[int(val) % len(SAS_MODES)]}, force=True)
        return out

    def _abort(self):
        mode = ABORT_MODES[int(self.inputs.get('abort_mode') or 0) % len(ABORT_MODES)]
        out = []
        for step in ABORT_SEQ[mode]:
            if step == 'cut':
                self.cutoff_latched = True
                out += self._throttle()
            elif step == 'group':
                out += self._cmd('cmd/abort', {}, force=True)
            elif step == 'stage':
                out += self._cmd('cmd/stage', {}, force=True)
            elif step in ('sas', 'sas_radial'):
                self.forced['sas'] = True
                out += self._cmd('cmd/sas', {'on': True}, force=True)
                out += self._cmd('cmd/sas_mode', {'mode': 'radial' if step == 'sas_radial' else 'stability'}, force=True)
            elif step == 'rcs':
                self.forced['rcs'] = True
                out += self._cmd('cmd/rcs', {'on': True}, force=True)
        return out

    def _adopt_node(self, n):
        """A maneuver node made or moved in the game (map view) becomes the computer's PAD: TIG is the node's time less
        half the burn time. The node the cockpit itself made is recognised and left alone."""
        tm = self.tlm.get('tlm/time', {})
        last = self.last_cmd.get('cmd/node')
        if not n.get('set') or self.cmp.armed or tm.get('ut') is None or tm.get('met') is None:
            return
        if last and self.now - last[1] < 2.0:
            return                                            # our own command may not be in the telemetry yet
        s = self.node_sent
        if s and abs(s['ut'] - n['ut']) < 0.5 and all(abs(a - b) < 0.05 for a, b in zip(s['dv'], n['dv'])):
            return
        t_node = tm['met'] + n['ut'] - tm['ut']
        self.cmp.load(t_node, n['dv'])
        self.cmp.pad['tig'] = round(t_node - (self.cmp.burn_time(self.tlm) or 0.0) / 2, 1)
        self.node_rev, self.node_sent = self.cmp.rev, {'ut': n['ut'], 'dv': list(n['dv'])}

    def _sync_node(self):
        """Mirror the computer's PAD to KSP as a maneuver node at the burn point (TIG + half the burn time), so SAS can
        hold the burn attitude (SAS MODE MNVR). The cockpit still owns the PAD: KSP's node is only an attitude reference."""
        if self.cmp.rev == self.node_rev:
            return []
        tm = self.tlm.get('tlm/time', {})
        tfi = self.cmp.tfi(self.tlm)
        if not self.cmp.loaded() or self.cmp.dv_mag() == 0:
            self.node_rev, self.node_sent = self.cmp.rev, None
            return self._cmd('cmd/node', {'clear': True}, force=True)
        if tfi is None or tm.get('ut') is None or not self.fresh():
            return []                                             # no clock yet: try again on the next tick
        self.node_rev = self.cmp.rev
        if tfi >= 0:
            self.node_sent = None
            return self._cmd('cmd/node', {'clear': True}, force=True)
        tb = self.cmp.burn_time(self.tlm) or 0.0
        self.node_sent = {'ut': round(tm['ut'] - tfi + tb / 2, 2), 'dv': [round(x, 2) for x in self.cmp.pad['dv']]}
        return self._cmd('cmd/node', dict(self.node_sent), force=True)

    def _event_time(self):
        """Seconds from the event the event timer's source selects (negative before it), or None."""
        met = self.tlm.get('tlm/time', {}).get('met')
        orb = self.tlm.get('tlm/orbit', {})
        src = EVT_SRC[int(self.inputs.get('evt_src') or 0) % len(EVT_SRC)]
        if src == 'TIG' and met is not None:
            tig = self.cmp.pad['tig'] if self.cmp.loaded() else self.dsky.pad['tig']
            return None if tig is None else met - tig
        if src == 'APO' and orb.get('t_apo') is not None:
            return -orb['t_apo']
        if src == 'PERI' and orb.get('t_peri') is not None:
            return -orb['t_peri']
        if src == 'SOI' and orb.get('t_soi') is not None:
            return -orb['t_soi']
        return None

    def _throttle(self):
        lever = float(self.inputs.get('throttle') or 0.0)
        if self.cutoff_latched and lever < CUTOFF_RESET:
            self.cutoff_latched = False                       # the pilot has acknowledged the cutoff
        v = lever if self.inputs.get('eng_arm') and not self.cutoff_latched else 0.0
        v = round(max(0.0, min(1.0, v)), 3)
        last = self.last_cmd.get('cmd/throttle')
        if last and abs(last[0]['v'] - v) < 0.002:
            return []
        return self._cmd('cmd/throttle', {'v': v}, force=True)

    # ---------- caution & warning ----------
    def active(self):
        a = set()
        fl, ve = self.tlm.get('tlm/flight', {}), self.tlm.get('tlm/vessel', {})
        res = self.tlm.get('tlm/resources', {})
        if not self.fresh() or not self.link_up:
            a.add('cw_no_link')
            return a
        if fl.get('g', 0) > G_LIMIT:
            a.add('cw_high_g')
        if fl.get('q', 0) > Q_LIMIT:
            a.add('cw_q')
        frac = stage_fuel(res)
        if frac is not None and frac < LOW_FUEL and ve.get('thrust_avail', 0) > 0:
            a.add('cw_low_fuel')
        ec = res.get('total', {}).get('ElectricCharge')
        if ec and ec.get('max', 0) > 0 and ec['amount'] / ec['max'] < LOW_POWER:
            a.add('cw_low_power')
        mono = res.get('total', {}).get('MonoPropellant')
        if mono and mono.get('max', 0) > 0 and mono['amount'] / mono['max'] < RCS_LOW:
            a.add('cw_rcs_low')
        radar, vs = fl.get('radar'), fl.get('vs')
        if radar is not None and vs is not None and 0 < radar < 1000 and vs < -(8 + radar / 10) \
                and ve.get('situation') in ('flying', 'sub_orbital'):
            a.add('cw_sink')
        if float(self.inputs.get('throttle') or 0) > 0.02 and not self.inputs.get('eng_arm'):
            a.add('cw_throttle')                               # arming now would light the engine at once
        tg = self.tlm.get('tlm/target', {})
        if tg.get('set') and tg.get('range') is not None and (tg.get('closing') or 0) > GATE_MARGIN * gate(tg['range']):
            a.add('cw_closing')
        orb, sit = self.tlm.get('tlm/orbit', {}), ve.get('situation')
        if (self.tlm.get('tlm/thermal', {}).get('max') or 0) >= OVERHEAT:
            a.add('cw_overheat')
        falling = vs is not None and vs < 0 and sit in ('flying', 'sub_orbital')
        if falling and ve.get('has_gear') and ve.get('gear') is False and radar is not None and radar < GEAR_ALT:
            a.add('cw_gear')
        if falling and sit == 'flying' and ve.get('chute') == 'stowed' and not self.inputs.get('chute_arm') \
                and (fl.get('alt') or 1e9) < CHUTE_ALT:
            a.add('cw_chute')                                  # in the air, going down, parachute neither armed nor out
        if ve.get('comm') is False:
            a.add('cw_comm')
        safe = SAFE_PERI.get(orb.get('body'))
        if sit == 'orbiting' and safe is not None and orb.get('peri') is not None and orb['peri'] < safe:
            a.add('cw_peri')
        if orb.get('t_soi') is not None and 0 < orb['t_soi'] < SOI_SOON_S:
            a.add('cw_soi')
        st, tfi, nd = self.cmp.state(self.tlm), self.cmp.tfi(self.tlm), self.tlm.get('tlm/node', {})
        if st in ('ready', 'armed', 'burn') and tfi is not None and -ATT_ERR_FROM_S <= tfi and (st != 'ready' or tfi < ATT_ERR_FROM_S) \
                and nd.get('set') and (nd.get('att_err') or 0) > ATT_ERR_DEG:
            a.add('cw_att')
        if st == 'done' and abs(self.cmp.vg()) > max(RESID_MIN, RESID_FRAC * self.cmp.dv_mag()):
            a.add('cw_resid')
        cells, lost = self._engines()
        if any(c == 'r' for c in cells.values()) and not lost:
            a.add('cw_flameout')
        if lost or any(c == 'a' for c in cells.values()):
            t0 = self.disagree_since.setdefault('eng', self.now)
            if lost or self.now - t0 >= ENG_FAIL_S:
                a.add('cw_eng_fail')
        else:
            self.disagree_since.pop('eng', None)
        # SAS disagree: switch vs game for more than DISAGREE_S
        if 'sas' in ve and 'sas' in self.inputs and 'sas' not in self.forced:
            if bool(ve['sas']) != bool(self.inputs['sas']):
                t0 = self.disagree_since.setdefault('sas', self.now)
                if self.now - t0 >= DISAGREE_S:
                    a.add('cw_sas_dis')
            else:
                self.disagree_since.pop('sas', None)
        return a

    def _engines(self):
        """Engine display: ({(row, col): colour}, lost). One LED per engine, laid out as seen from behind the vessel.
        g = thrust, w = lit but idle (or next to ignite, before any engine is lit), a = has fuel but gives under half
        the thrust commanded, r = flamed out or gone (an engine that was burning in this stage and is no longer listed)."""
        en = self.tlm.get('tlm/engines', {}).get('engines') or []
        ve = self.tlm.get('tlm/vessel', {})
        stage, thr = ve.get('stage'), ve.get('throttle') or 0.0
        on = [e for e in en if e.get('on')]
        shown = on or [e for e in en if stage is not None and e.get('stage') == stage - 1]
        key = lambda e: (round(e['x'], 1), round(e['z'], 1))
        if self.eng_known[0] != (stage, ve.get('name')):
            self.eng_known = ((stage, ve.get('name')), frozenset())
        now_on = frozenset(key(e) for e in on)
        self.eng_known = (self.eng_known[0], self.eng_known[1] | now_on)
        lost = self.eng_known[1] - now_on if on else frozenset()
        pts = []
        for e in shown:
            if not e.get('on'):
                c = 'w'
            elif not e.get('fuel', True):
                c = 'r'
            elif thr > 0.02 and e.get('max', 0) > 0 and e.get('thrust', 0) < 0.5 * e['max'] * thr:
                c = 'a'
            else:
                c = 'g' if e.get('thrust', 0) > 0 else 'w'
            pts.append((key(e), c))
        pts += [(k, 'r') for k in lost]
        scale = max([max(abs(x), abs(z)) for (x, z), _ in pts] or [0.0])
        mid, cells = GRID // 2, {}
        for (x, z), c in sorted(pts, key=lambda p: (abs(p[0][0]) + abs(p[0][1]), p[0])):
            r0 = mid + (round(z / scale * mid) if scale > 0.05 else 0)
            c0 = mid + (round(x / scale * mid) if scale > 0.05 else 0)
            free = sorted(((r - r0) ** 2 + (q - c0) ** 2, r, q) for r in range(GRID) for q in range(GRID) if (r, q) not in cells)
            if free:
                cells[free[0][1:]] = c
        return cells, bool(lost)

    # ---------- outputs ----------
    def _render(self):
        want = {}
        o = lambda name, payload: want.__setitem__(f'panel/{PANEL}/out/{name}', payload)
        lamp_test = bool(self.inputs.get('lamp_test'))
        powered = self.powered()
        active = self.active()
        self.acked &= active                                  # an item that clears needs a new ack next time
        unacked = active - self.acked
        ve, fl = self.tlm.get('tlm/vessel', {}), self.tlm.get('tlm/flight', {})
        lamps = {name: (False, False) for name in LAMPS}
        if powered:
            for i in active:
                lamps[i] = (True, i in unacked)
            w_un = any(CW[i][1] == 'W' for i in unacked)
            c_un = any(CW[i][1] == 'C' for i in unacked)
            lamps['master_alarm'] = (w_un, w_un)
            lamps['master_caution'] = (c_un, False)
            lamps['led_eng_arm'] = (bool(self.inputs.get('eng_arm')), False)
            lamps['lamp_stage'] = (bool(self.inputs.get('stage_arm')), False)
            lamps['lamp_abort'] = (self.abort_fired or bool(self.inputs.get('abort_arm')), self.abort_fired)
            lamps['lamp_cutoff'] = (self.cutoff_latched, False)
            if self.fresh():
                lamps['lamp_contact'] = (bool(ve.get('contact')) and ve.get('situation') != 'pre_launch', False)
                lamps['lamp_05g'] = ((fl.get('g') or 0) >= G_ENTRY and not ve.get('thrust') and (fl.get('vs') or 0) < 0
                                     and ve.get('situation') in ('flying', 'sub_orbital'), False)
            gl = self.tlm.get('tlm/engines', {}).get('gimbal_locked')
            lamps['led_gimbal'] = (bool(gl), False)
            for ctl in ('sas', 'rcs', 'gear', 'lights'):
                game = ve.get(ctl)
                sw = self.forced.get(ctl, bool(self.inputs.get(ctl, 0)))
                if game is None:
                    lamps[f'led_{ctl}'] = (False, False)
                else:
                    lamps[f'led_{ctl}'] = (bool(game) or sw, bool(game) != sw)   # blink = disagree
        for name, (on, blink) in lamps.items():
            if lamp_test and powered:
                on, blink = True, False
            o(name, {'on': on, 'blink': blink})
        o('buzzer', {'on': powered and not lamp_test and any(CW[i][1] == 'W' for i in unacked)})
        # displays
        if not powered:
            for d in ('disp_a', 'disp_met', 'disp_stage', 'disp_eng_on'):
                o(d, {'text': '', 'blank': True})
            o('bar_fuel', {'v': 0.0}); o('bar_thrust', {'v': 0.0})
            o('mx_eng', {'rows': ['.' * GRID] * GRID})
        elif lamp_test:
            o('disp_a', {'text': '8.8.8.8.8.8.8.', 'blank': False}); o('disp_met', {'text': '8.8.8.8.8.8.8.', 'blank': False})
            o('disp_stage', {'text': '8.8.', 'blank': False}); o('bar_fuel', {'v': 1.0}); o('bar_thrust', {'v': 1.0})
            o('disp_eng_on', {'text': '8.8.', 'blank': False}); o('mx_eng', {'rows': ['w' * GRID] * GRID})
        else:
            o('disp_a', {'text': disp_a(self.inputs.get('disp_sel', 0), self.tlm) if self.fresh() else '-------', 'blank': False})
            met = self.tlm.get('tlm/time', {}).get('met')
            o('disp_met', {'text': fmt_met(met) if met is not None and self.fresh() else '--.--.--', 'blank': False})
            st = ve.get('stage')
            o('disp_stage', {'text': f'{st:2d}' if isinstance(st, int) and self.fresh() else '--', 'blank': False})
            frac = stage_fuel(self.tlm.get('tlm/resources', {}))
            o('bar_fuel', {'v': round(frac, 2) if frac is not None and self.fresh() else 0.0})
            ta = ve.get('thrust_avail') or 0
            o('bar_thrust', {'v': round(min(1.0, ve.get('thrust', 0) / ta), 2) if ta > 0 and self.fresh() else 0.0})
            cells = self._engines()[0] if self.fresh() else {}
            o('mx_eng', {'rows': [''.join(cells.get((r, q), '.') for q in range(GRID)) for r in range(GRID)]})
            n_on = sum(1 for c in cells.values() if c == 'g')
            o('disp_eng_on', {'text': f'{n_on:2d}' if self.fresh() and 'tlm/engines' in self.tlm else '--', 'blank': False})
        self._render_sys(want, powered, lamp_test)
        self._render_rdv(want, powered, lamp_test)
        for name, p in self.cmp.render(self.tlm, powered, lamp_test, self.fresh()).items():
            want[f'panel/{CMP}/out/{name}'] = p
        dsky_on = powered and bool(self.inputs.get('cb_dsky', 1))
        for name, p in self.dsky.render(self.now, self.tlm, dsky_on, self.fresh()).items():
            want[f'panel/{DSKY}/out/{name}'] = p
        out = []
        for t, p in want.items():
            if self.last_sent.get(t) != p:
                self.last_sent[t] = p
                out.append(Msg(t, p, True, 1))
        pad = {'tig': self.cmp.pad['tig'], 'dv': list(self.cmp.pad['dv']), 'armed': self.cmp.armed,
               'state': self.cmp.state(self.tlm)}
        if self.last_sent.get('cmp/pad') != pad:
            self.last_sent['cmp/pad'] = pad
            out.append(Msg('cmp/pad', pad, True, 1))
        cw = {'master_caution': lamps['master_caution'][0], 'master_alarm': lamps['master_alarm'][0],
              'active': sorted(CW[i][0] for i in active), 'unacked': sorted(CW[i][0] for i in unacked)}
        if self.last_sent.get('cw/state') != cw:
            self.last_sent['cw/state'] = cw
            out.append(Msg('cw/state', cw, True, 1))
        return out


    def _ec_rate(self):
        ec = self.tlm.get('tlm/resources', {}).get('total', {}).get('ElectricCharge')
        met = self.tlm.get('tlm/time', {}).get('met')
        if not ec or met is None:
            return
        if self.ec_prev and met > self.ec_prev[0]:
            r = (ec['amount'] - self.ec_prev[1]) / (met - self.ec_prev[0])
            self.ec_rate += (r - self.ec_rate) * 0.3
        self.ec_prev = (met, ec['amount'])

    def _render_sys(self, want, powered, lamp_test):
        o = lambda name, payload: want.__setitem__(f'panel/{SYS}/out/{name}', payload)
        ve, fl, orb = self.tlm.get('tlm/vessel', {}), self.tlm.get('tlm/flight', {}), self.tlm.get('tlm/orbit', {})
        res = self.tlm.get('tlm/resources', {})
        tot, st = res.get('total', {}), res.get('stage', {})
        fresh = self.fresh()
        disps = ('disp_ec', 'disp_ec_rate', 'disp_dv', 'disp_twr', 'disp_evt', 'disp_warp')
        bars = ('bar_ec', 'bar_lf', 'bar_ox', 'bar_mono')
        if not powered:
            for d in disps:
                o(d, {'text': '', 'blank': True})
            for b in bars:
                o(b, {'v': 0.0})
            for l in SYS_LAMPS:
                o(l, {'on': False, 'blink': False})
            return
        if lamp_test:
            for d in disps:
                o(d, {'text': '8.8.8.8.8.8.', 'blank': False})
            for b in bars:
                o(b, {'v': 1.0})
            for l in SYS_LAMPS:
                o(l, {'on': True, 'blink': False})
            return
        frac = lambda d, r: (d[r]['amount'] / d[r]['max']) if r in d and d[r].get('max') else None
        ec = tot.get('ElectricCharge')
        o('bar_ec', {'v': round(frac(tot, 'ElectricCharge') or 0.0, 2) if fresh else 0.0})
        o('disp_ec', {'text': fit(ec['amount'], 1, 5) if ec and fresh else '-----', 'blank': False})
        o('disp_ec_rate', {'text': fit(self.ec_rate, 2, 5, signed=True) if ec and fresh else '-----', 'blank': False})
        o('bar_lf', {'v': round(frac(st, 'LiquidFuel') or frac(st, 'SolidFuel') or 0.0, 2) if fresh else 0.0})
        o('bar_ox', {'v': round(frac(st, 'Oxidizer') or 0.0, 2) if fresh else 0.0})
        o('bar_mono', {'v': round(frac(tot, 'MonoPropellant') or 0.0, 2) if fresh else 0.0})
        # stage Δv (TM-4: rocket equation on this stage's propellant; LF, Ox and solid are 5 kg per unit, mono 4)
        dv = None
        prop = 5.0 * sum(st.get(r, {}).get('amount', 0.0) for r in ('LiquidFuel', 'Oxidizer', 'SolidFuel'))
        m, isp = ve.get('mass'), ve.get('isp')
        if m and isp and m > prop:
            dv = isp * 9.80665 * math.log(m / (m - prop))
        o('disp_dv', {'text': fit(dv, 0, 5) if dv is not None and fresh else '-----', 'blank': False})
        mu_r = BODIES.get(orb.get('body'))
        twr = None
        if mu_r and m and fl.get('alt') is not None:
            g = mu_r[0] / (mu_r[1] + fl['alt']) ** 2
            twr = (ve.get('thrust_avail') or 0.0) / (m * g)
        o('disp_twr', {'text': fit(twr, 2, 4) if twr is not None and fresh else '----', 'blank': False})
        # event timer
        met = self.tlm.get('tlm/time', {}).get('met')
        src = EVT_SRC[int(self.inputs.get('evt_src') or 0) % len(EVT_SRC)]
        t = None
        zero = False
        if src == 'MAN':
            e = self.evt
            t = e['acc'] + ((met - e['t0']) if e['run'] and met is not None else 0.0)
            if self.inputs.get('evt_down'):                   # count down from the preset; stop and blink at zero
                t = e['preset'] - t
                if t <= 0:
                    zero, t = e['preset'] > 0, 0.0
                    if e['run']:
                        e['run'], e['acc'] = False, e['preset']
        else:
            t = self._event_time()
        o('disp_evt', {'text': fmt_evt(t) if t is not None and fresh else '--.--', 'blank': False, 'blink': zero})
        warp = self.tlm.get('tlm/time', {}).get('warp') or 1
        o('disp_warp', {'text': f'{warp:g}' if fresh else '----', 'blank': False})
        lamps = {
            'led_warp': (warp > 1, False),
            'led_evt_run': (zero or src == 'MAN' and self.evt['run'] or src != 'MAN' and t is not None and -10 <= t < 0,
                            zero or src != 'MAN'),
            'led_chute_armed': (bool(self.inputs.get('chute_arm')), False),
            'lamp_chute': (ve.get('chute') == 'deployed', False),
            'led_pause': (bool(self.tlm.get('tlm/time', {}).get('paused')), False),
        }
        for ctl in ('solar', 'brakes'):
            game, sw = ve.get(ctl), bool(self.inputs.get(ctl, 0))
            lamps[f'led_{ctl}'] = (False, False) if game is None else (bool(game) or sw, bool(game) != sw)
        for l, (on, b) in lamps.items():
            o(l, {'on': on, 'blink': on and b})


    def _render_rdv(self, want, powered, lamp_test):
        o = lambda name, payload: want.__setitem__(f'panel/{RDV}/out/{name}', payload)
        if not powered or lamp_test:
            for d in RDV_DISPS:
                o(d, {'text': '8.8.8.8.8.8.' if powered else '', 'blank': not powered})
            o('txt_tgt', {'text': '*' * 12 if powered else '', 'blank': not powered})
            for l in RDV_LAMPS:
                o(l, {'on': powered, 'blink': False})
            return
        tg = self.tlm.get('tlm/target', {}) if self.fresh() else {}
        on, port = bool(tg.get('set')), tg.get('port')
        rng, closing = tg.get('range'), tg.get('closing')
        km = on and rng is not None and rng >= 100000
        g = gate(rng) if on and rng is not None else None
        o('txt_tgt', {'text': (tg.get('name') or '').upper()[:12] if on else 'NO TARGET', 'blank': False})
        o('disp_range', {'text': fit(rng / 1000 if km else rng, 1, 6) if on and rng is not None else '------', 'blank': False})
        o('disp_closing', {'text': fit(closing, 2, 5, signed=True) if on and closing is not None else '-----', 'blank': False})
        o('disp_gate', {'text': fit(g, 2, 5) if g is not None else '-----', 'blank': False})
        o('disp_los', {'text': fit(tg.get('los_rate'), 2, 4) if on and tg.get('los_rate') is not None else '----', 'blank': False})
        own = port if port and 'right' in port else None      # the pilot's own axes
        sg = lambda k, dec, w: {'text': fit(own[k], dec, w, signed=True) if own else '-' * w, 'blank': False}
        o('disp_roll', sg('roll', 1, 5)); o('disp_yaw', sg('yaw', 1, 5)); o('disp_pitch', sg('pitch', 1, 5))
        o('disp_right', sg('right', 2, 5)); o('disp_up', sg('up', 2, 5))
        o('disp_vright', sg('v_right', 2, 4)); o('disp_vup', sg('v_up', 2, 4))
        o('disp_axial', {'text': fit(port['axial'], 2, 5) if port else '-----', 'blank': False})
        o('disp_vaxial', {'text': fit(-port['v_axial'], 2, 4, signed=True) if port else '----', 'blank': False})
        lat = math.hypot(own['right'], own['up']) if own else math.hypot(port['x'], port['z']) if port else None
        ang = port.get('angle') if port else None
        over = g is not None and closing is not None and closing > g
        aligned = bool(own) and abs(own['yaw']) <= ALIGN_DEG and abs(own['pitch']) <= ALIGN_DEG
        cap = bool(port) and 0 < port['axial'] < CAPTURE['within'] and lat <= CAPTURE['lateral'] \
            and CAPTURE['v_min'] <= -port['v_axial'] <= CAPTURE['v_max'] and (ang is None or ang <= CAPTURE['angle'])
        cp, sw = tg.get('ctrl_port'), bool(self.inputs.get('ctrl_port', 0))
        lamps = {'led_tgt': (on, False), 'led_port': (bool(port), False), 'led_km': (km, False),
                 'lamp_overspeed': (over, True), 'lamp_capture': (cap, False), 'lamp_aligned': (aligned, False),
                 'led_ctrl_port': (False, False) if cp is None else (bool(cp) or sw, bool(cp) != sw)}
        for l, (lit, b) in lamps.items():
            o(l, {'on': lit, 'blink': lit and b})


def gate(rng):
    """Braking gate: the closing speed allowed at this range (docking chapter)."""
    return max(GATE_FLOOR, rng / GATE_S)


def stage_fuel(res):
    st = res.get('stage', {})
    amt = sum(st.get(r, {}).get('amount', 0) for r in ('LiquidFuel', 'SolidFuel'))
    mx = sum(st.get(r, {}).get('max', 0) for r in ('LiquidFuel', 'SolidFuel'))
    return amt / mx if mx > 0 else None


def disp_a(sel, tlm):
    fl, orb, ve = tlm.get('tlm/flight', {}), tlm.get('tlm/orbit', {}), tlm.get('tlm/vessel', {})
    key = DISP_SEL[int(sel or 0) % len(DISP_SEL)]
    val = {'ALT': fl.get('alt'), 'APO': orb.get('apo'), 'PERI': orb.get('peri'), 'VEL': fl.get('speed'),
           'V/S': fl.get('vs'), 'MASS': ve.get('mass')}[key]
    if val is None:
        return '-------'
    if key in ('ALT', 'APO', 'PERI'):
        return fit7(val / 1000.0, 2)          # km
    if key == 'MASS':
        return fit7(val / 1000.0, 3)          # t
    return fit7(val, 1)                       # m/s

