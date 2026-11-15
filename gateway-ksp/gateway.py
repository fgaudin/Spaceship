"""KSP gateway: the only process that talks to KSP (PLAN.md §1). kRPC streams → tlm/*; cmd/* → kRPC calls.

Same topics and payloads as the mock plant (protocol/topics.md). Handles: KSP not running (retries), scene changes and
vessel switches (streams rebuilt when the active vessel changes), stale streams after staging (the stage table and
resources are re-read after every staging event; see selftest/gaps.md G4).
"""
import json, math, os, queue, threading, time
import krpc
import paho.mqtt.client as mqtt

MQTT_HOST = os.environ.get('MQTT_HOST', 'localhost')
MQTT_PORT = int(os.environ.get('MQTT_PORT', '1883'))
KRPC_HOST = os.environ.get('KRPC_HOST', '127.0.0.1')
RATE_HZ = float(os.environ.get('RATE_HZ', '10'))
PROP = ('LiquidFuel', 'Oxidizer', 'SolidFuel', 'MonoPropellant')
SAS_MODES = ['stability', 'prograde', 'retrograde', 'normal', 'antinormal', 'radial', 'antiradial', 'target', 'antitarget',
             'maneuver']
RAILS = [1, 5, 10, 50, 100, 1000, 10000, 100000]      # KSP's rails warp rates
# protocol name ↔ kRPC SASMode member
TO_KRPC = {'stability': 'stability_assist', 'prograde': 'prograde', 'retrograde': 'retrograde', 'normal': 'normal',
           'antinormal': 'anti_normal', 'radial': 'radial', 'antiradial': 'anti_radial', 'target': 'target',
           'antitarget': 'anti_target', 'maneuver': 'maneuver'}
FROM_KRPC = {v: k for k, v in TO_KRPC.items()}


class Link:
    """One kRPC connection and the streams for the active vessel."""
    def __init__(self):
        self.conn = krpc.connect(name='capsule-gateway', address=KRPC_HOST)
        self.sc = self.conn.space_center
        self.vessel = None
        self.streams = {}
        self.stage_parts = []
        self.stage_seen = None
        self.throttle_cmd = 0.0                    # last throttle the cockpit commanded
        self.warp_to = None                        # UT to warp to (cmd/warp to_ut), stepped by the main loop
        self.nodes = []                            # maneuver nodes this gateway created (cmd/node)
        self.has_target = False

    def bind(self):
        """(Re)build every stream when the active vessel changes. Returns True on a new binding, None with no vessel."""
        v = self.sc.active_vessel
        if v is None:
            self.vessel = None
            return None
        if self.vessel is not None and v == self.vessel:
            return False
        self.drop_streams()
        self.vessel = v
        # KSP sets the throttle to 50 % when a save loads (selftest/gaps.md G11): the panel is the authority
        v.control.throttle = self.throttle_cmd
        body = v.orbit.body
        fl = v.flight(body.reference_frame)
        fs = v.flight()                            # surface frame: pitch, heading, roll against the local horizon
        self.body_frame = body.reference_frame
        ctl, o, res = v.control, v.orbit, v.resources
        add = self.conn.add_stream
        # one stream per value: a plain read costs a round trip (~3 ms) and the loop made >100 of them (NO LINK flicker)
        self.streams = {
            'ut': add(getattr, self.sc, 'ut'), 'warp': add(getattr, self.sc, 'warp_rate'),
            'paused': add(getattr, self.conn.krpc, 'paused'),
            'alt': add(getattr, fl, 'mean_altitude'), 'radar': add(getattr, fl, 'surface_altitude'),
            'vs': add(getattr, fl, 'vertical_speed'), 'hs': add(getattr, fl, 'horizontal_speed'),
            'speed': add(getattr, fl, 'speed'), 'q': add(getattr, fl, 'dynamic_pressure'), 'g': add(getattr, fl, 'g_force'),
            'lat': add(getattr, fl, 'latitude'), 'lon': add(getattr, fl, 'longitude'),
            'mass': add(getattr, v, 'mass'), 'thrust': add(getattr, v, 'thrust'),
            'thrust_avail': add(getattr, v, 'available_thrust'), 'isp': add(getattr, v, 'specific_impulse'),
            'situation': add(getattr, v, 'situation'), 'met': add(getattr, v, 'met'),
            'pitch': add(getattr, fs, 'pitch'), 'heading': add(getattr, fs, 'heading'), 'roll': add(getattr, fs, 'roll'),
            'vel': add(v.velocity, body.reference_frame),
            'stage': add(getattr, ctl, 'current_stage'), 'throttle': add(getattr, ctl, 'throttle'),
            'sas': add(getattr, ctl, 'sas'), 'rcs': add(getattr, ctl, 'rcs'), 'gear': add(getattr, ctl, 'gear'),
            'lights': add(getattr, ctl, 'lights'), 'brakes': add(getattr, ctl, 'brakes'), 'sas_mode': add(getattr, ctl, 'sas_mode'),
            'o_body': add(getattr, o, 'body'), 'o_apo': add(getattr, o, 'apoapsis_altitude'),
            'o_peri': add(getattr, o, 'periapsis_altitude'), 'o_a': add(getattr, o, 'semi_major_axis'),
            'o_e': add(getattr, o, 'eccentricity'), 'o_i': add(getattr, o, 'inclination'), 'o_T': add(getattr, o, 'period'),
            'o_tapo': add(getattr, o, 'time_to_apoapsis'), 'o_tperi': add(getattr, o, 'time_to_periapsis'),
            'o_nu': add(getattr, o, 'true_anomaly'), 'o_argp': add(getattr, o, 'argument_of_periapsis'),
            'o_tsoi': add(getattr, o, 'time_to_soi_change'), 'comm': add(getattr, v.comms, 'can_communicate'),
        }
        self.totals = {}
        for r in ('ElectricCharge', 'LiquidFuel', 'Oxidizer', 'MonoPropellant'):
            mx = res.max(r)
            if mx > 0:
                self.totals[r] = (add(res.amount, r), mx)
        self.body_names = {}
        self.stage_seen = None
        self.nodes, self.warp_to = [], None
        cp = v.parts.controlling
        self.ctrl_default = cp if cp.docking_port is None else v.parts.root    # where CTRL FROM PORT off goes back to
        self.refresh_parts()
        return True

    def drop_streams(self):
        for s in [*self.streams.values(), *[a for a, _ in getattr(self, 'totals', {}).values()],
                  *[a for _, _, a in getattr(self, 'stage_res', [])], *getattr(self, 'part_streams', [])]:
            try:
                s.remove()
            except Exception:
                pass
        self.streams, self.totals, self.stage_res, self.part_streams = {}, {}, [], []

    def refresh_parts(self):
        """Solar panels and parachutes, as streams (re-read after every staging)."""
        for st in getattr(self, 'part_streams', []):
            try:
                st.remove()
            except Exception:
                pass
        v, add = self.vessel, self.conn.add_stream
        self.solar = [add(getattr, p, 'deployed') for p in v.parts.solar_panels if p.deployable]
        self.chutes = [add(getattr, c, 'state') for c in v.parts.parachutes]
        self.solar_parts = list(v.parts.solar_panels)
        self.chute_parts = list(v.parts.parachutes)
        self.part_streams = [*self.solar, *self.chutes]
        # engines: position across the vessel's axis (vessel frame: x right, y forward, z down), state as streams
        self.engines = []
        rf = v.reference_frame
        for e in v.parts.engines:
            x, _, z = e.part.position(rf)
            st = [add(getattr, e, 'active'), add(getattr, e, 'thrust'), add(getattr, e, 'available_thrust'), add(getattr, e, 'has_fuel')]
            self.engines.append({'e': e, 'x': round(x, 2), 'z': round(z, 2), 'stage': e.part.stage, 'st': st})
            self.part_streams += st
        self.read_engine_settings()
        # ground contact: landing legs and wheels
        self.ground = [add(getattr, l, 'is_grounded') for l in v.parts.legs] + [add(getattr, w, 'grounded') for w in v.parts.wheels]
        # heat: skin temperature of every part and core temperature of the engines, each against its limit
        eng_parts = {d['e'].part._object_id for d in self.engines}
        self.heat = []
        for p in v.parts.all:
            self.heat.append((add(getattr, p, 'skin_temperature'), p.max_skin_temperature))
            if p._object_id in eng_parts:
                self.heat.append((add(getattr, p, 'temperature'), p.max_temperature))
        self.dock_ports = list(v.parts.docking_ports)
        self.dock_states = [add(getattr, d, 'state') for d in self.dock_ports]
        self.part_streams += [*self.ground, *[h for h, _ in self.heat], *self.dock_states]

    def real_docks(self):
        """Ports docked to another docking port. A port with an ordinary part stacked on it in the VAB also reports
        'docked'; that is not a docking."""
        return [d for d in self.dock_ports if d.state.name == 'docked' and d.docked_part is not None
                and d.docked_part.docking_port is not None]

    def docked(self):
        try:
            states = tuple(f().name for f in self.dock_states)
            if states != getattr(self, 'dock_seen', None):          # look at the partners only when a port changes state
                self.dock_seen, self.dock_real = states, bool(self.real_docks())
            return self.dock_real
        except Exception:
            return False

    def undock(self):
        """Undock: the port the vessel is controlled from if it is docked, else the first docked port."""
        v = self.vessel
        ds = self.real_docks()
        if not ds:
            return
        cp = v.parts.controlling
        pick = [d for d in ds if d.part == cp] or ds
        pick[0].undock()
        time.sleep(0.2)
        self.vessel = None                          # the vessel has split: rebuild every stream

    def grounded(self):
        try:
            return any(f() for f in self.ground)
        except Exception:
            return False

    def thermal(self):
        """Hottest part as a fraction of its temperature limit."""
        worst = 0.0
        for h, mx in self.heat:
            try:
                worst = max(worst, h() / mx if mx > 0 else 0.0)
            except Exception:                      # the part is gone
                pass
        return {'max': round(worst, 3)}

    def node(self):
        """The first maneuver node in the game (made by the cockpit or by the player in map view), with the angle between
        the vessel's axis and the burn direction."""
        ns = self.vessel.control.nodes
        if not ns:
            return {'set': False}
        n = ns[0]
        d = n.direction(self.vessel.reference_frame)
        return {'set': True, 'ut': round(n.ut, 2), 'dv': [round(n.prograde, 3), round(n.normal, 3), round(n.radial, 3)],
                'att_err': round(math.degrees(math.acos(max(-1.0, min(1.0, d[1])))), 2)}

    def read_engine_settings(self):
        act = [d['e'] for d in self.engines if d['st'][0]()]
        lim = [e.thrust_limit for e in act if not e.throttle_locked]
        gim = [e.gimbal_locked for e in (act or [d['e'] for d in self.engines]) if e.gimballed]
        self.eng_limit = round(sum(lim) / len(lim), 3) if lim else None
        self.gimbal_locked = any(gim) if gim else None

    def engine_table(self):
        out = []
        for d in self.engines:
            try:
                on, th, mx, fuel = (f() for f in d['st'])
            except Exception:                      # the engine is gone (destroyed): the cockpit shows it as lost
                continue
            out.append({'x': d['x'], 'z': d['z'], 'stage': d['stage'], 'on': on, 'thrust': round(th, 1), 'max': round(mx, 1),
                        'fuel': fuel})
        return {'engines': out, 'limit': self.eng_limit, 'gimbal_locked': self.gimbal_locked}

    def stage_table(self):
        """Propellant in the decouple group of the burning engines (kRPC 0.7 has no per-stage resource call): one
        amount stream per tank and resource, rebuilt when the stage changes."""
        v = self.vessel
        st = self.streams['stage']()
        if st != self.stage_seen:
            self.stage_seen = st
            for _, _, a in self.stage_res:
                try:
                    a.remove()
                except Exception:
                    pass
            self.refresh_parts()
            engines = [e for e in v.parts.engines if e.active]
            groups = {e.part.decouple_stage for e in engines}
            g = max(groups) if groups else None
            self.stage_res = []
            for p in v.parts.all:
                if g is None or p.decouple_stage != g:
                    continue
                for r in set(p.resources.names) & set(PROP):
                    mx = p.resources.max(r)
                    if mx > 0:
                        self.stage_res.append((r, mx, self.conn.add_stream(p.resources.amount, r)))
        out = {}
        for r, mx, a in self.stage_res:
            d = out.setdefault(r, {'amount': 0.0, 'max': 0.0})
            d['amount'] += a()
            d['max'] += mx
        return {r: {'amount': round(d['amount'], 3), 'max': round(d['max'], 3)} for r, d in out.items()}

    def snapshot(self, slow=True, tgt=False):
        """Fast topics every call (time, flight, attitude, vessel); orbit, resources, engines and target only when `slow`
        (the target also when `tgt`: it is published faster while one is set)."""
        v, s = self.vessel, {k: f() for k, f in self.streams.items()}
        solar = any(f() for f in self.solar) if self.solar else None
        chute = None
        if self.chutes:
            states = {f().name for f in self.chutes}
            chute = 'deployed' if states & {'semi_deployed', 'deployed'} else 'armed' if 'armed' in states else \
                'cut' if states == {'cut'} else 'stowed'
        vn = ve = None
        # surface prograde as pitch and heading (surface frame: x up, y north, z east)
        pro = None
        if s['speed'] > 1:
            up, north, east = self.sc.transform_direction(s['vel'], self.body_frame, v.surface_reference_frame)
            vn, ve = north, east
            pro = {'pitch': round(math.degrees(math.atan2(up, math.hypot(north, east))), 2),
                   'heading': round(math.degrees(math.atan2(east, north)) % 360, 2)}
        out = {
            'tlm/attitude': {'pitch': round(s['pitch'], 2), 'heading': round(s['heading'], 2), 'roll': round(s['roll'], 2),
                             'prograde': pro},
            'tlm/time': {'ut': round(s['ut'], 2), 'met': round(s['met'], 2), 'warp': s['warp'], 'paused': s['paused']},
            'tlm/flight': {**{k: round(s[k], 3) for k in ('alt', 'radar', 'vs', 'hs', 'speed', 'q', 'g', 'lat', 'lon')},
                           'vn': None if vn is None else round(vn, 2), 've': None if ve is None else round(ve, 2)},
            'tlm/vessel': {'name': v.name if slow or not hasattr(self, 'vname') else self.vname,
                           'mass': round(s['mass'], 1), 'thrust': round(s['thrust'], 1),
                           'thrust_avail': round(s['thrust_avail'], 1), 'isp': round(s['isp'], 1),
                           'situation': s['situation'].name, 'stage': s['stage'], 'throttle': round(s['throttle'], 3),
                           'sas': s['sas'], 'rcs': s['rcs'], 'gear': s['gear'], 'lights': s['lights'], 'brakes': s['brakes'],
                           'sas_mode': FROM_KRPC.get(s['sas_mode'].name, s['sas_mode'].name) if s['sas'] else None,
                           'solar': solar, 'chute': chute, 'comm': s['comm'], 'has_gear': bool(self.ground),
                           'contact': s['situation'].name in ('landed', 'splashed', 'pre_launch') or self.grounded()},
        }
        self.vname = out['tlm/vessel']['name']
        if slow:
            b = s['o_body']
            if b._object_id not in self.body_names:
                self.body_names[b._object_id] = b.name
            apo, e = s['o_apo'], s['o_e']
            out['tlm/orbit'] = {'body': self.body_names[b._object_id], 'apo': apo if math.isfinite(apo) else None,
                                'peri': s['o_peri'], 'a': s['o_a'], 'e': e, 'i': math.degrees(s['o_i']),
                                'period': s['o_T'] if e < 1 else None, 't_apo': s['o_tapo'] if e < 1 else None,
                                't_peri': s['o_tperi'], 'nu': math.degrees(s['o_nu']), 'argp': math.degrees(s['o_argp']),
                                't_soi': s['o_tsoi'] if math.isfinite(s['o_tsoi']) else None}
            out['tlm/resources'] = {'stage': self.stage_table(),
                                    'total': {r: {'amount': round(a(), 3), 'max': round(mx, 3)} for r, (a, mx) in self.totals.items()}}
            out['tlm/engines'] = self.engine_table()
            out['tlm/thermal'] = self.thermal()
            out['tlm/node'] = self.node()
        if slow or (tgt and self.has_target):
            out['tlm/target'] = self.target()
        return out

    def target(self):
        """Relative state to the target vessel (and docking port, if one is targeted), or {'set': False}."""
        tv = self.sc.target_vessel
        tp = self.sc.target_docking_port
        if tv is None and tp is not None:
            tv = tp.part.vessel
        v = self.vessel
        cp = v.parts.controlling
        own = cp.docking_port                                           # None unless the vessel is controlled from a port
        self.has_target = tv is not None
        if tv is None:
            return {'set': False, 'ctrl_port': own is not None, 'docked': self.docked()}
        nrf = v.orbit.body.non_rotating_reference_frame
        rp, rv = tv.position(nrf), v.position(nrf)
        d = [a - b for a, b in zip(rp, rv)]                         # chaser → target
        rng = math.sqrt(sum(x * x for x in d))
        dv = [a - b for a, b in zip(v.velocity(nrf), tv.velocity(nrf))]   # chaser relative to the target
        u = [x / rng for x in d] if rng > 0 else [0, 0, 0]
        closing = sum(a * b for a, b in zip(dv, u))
        side = [a - closing * b for a, b in zip(dv, u)]
        out = {'set': True, 'name': tv.name, 'range': round(rng, 2), 'closing': round(closing, 3),
               'los_rate': round(math.degrees(math.sqrt(sum(x * x for x in side)) / rng) * 60, 4) if rng > 1 else None,
               'rel_v': round(math.sqrt(sum(x * x for x in dv)), 3), 'ctrl_port': own is not None, 'docked': self.docked()}
        if tp is not None:
            F = tp.reference_frame                                      # y out of the target port
            here = own.position(F) if own else v.position(F)
            vel = v.velocity(F)
            ax = (own.direction(F) if own else v.direction(F))[1]       # −1 when facing straight into the target port
            out['port'] = {'axial': round(here[1], 3), 'x': round(here[0], 3), 'z': round(here[2], 3),
                           'v_axial': round(vel[1], 4), 'vx': round(vel[0], 4), 'vz': round(vel[2], 4),
                           'angle': round(math.degrees(math.acos(max(-1.0, min(1.0, -ax)))), 2), 'from_port': own is not None}
            # the same in the pilot's own axes (vessel frame: x right, y forward, z down), so that no roll is needed
            # to read them: where the target port is, how that changes, and how to turn to face it squarely
            vrf, tr = v.reference_frame, self.sc.transform_direction
            tpos, opos = tp.position(vrf), (own.position(vrf) if own else (0.0, 0.0, 0.0))
            p = [a - b for a, b in zip(tpos, opos)]
            d = tr((0.0, -1.0, 0.0), F, vrf)                            # the way to point: into the target port
            u = tr((0.0, 0.0, -1.0), F, vrf)                            # the target port's own "up"
            w = tr(vel, F, vrf)                                         # our velocity relative to the target
            deg = lambda a, b: round(math.degrees(math.atan2(a, b)), 2)
            out['port'].update({'right': round(p[0], 3), 'up': round(-p[2], 3), 'fwd': round(p[1], 3),
                                'v_right': round(-w[0], 4), 'v_up': round(w[2], 4),
                                'yaw': deg(d[0], d[1]), 'pitch': deg(-d[2], d[1]), 'roll': deg(u[0], -u[2])})
        return out

    def command(self, topic, p):
        v, ctl = self.vessel, self.vessel.control
        if topic == 'cmd/throttle':
            self.throttle_cmd = max(0.0, min(1.0, float(p.get('v', 0))))
            ctl.throttle = self.throttle_cmd
        elif topic == 'cmd/stage':
            ctl.activate_next_stage()
            time.sleep(0.1)                        # let the part list settle before the next read (G4)
            self.stage_seen = None
        elif topic == 'cmd/abort':
            ctl.abort = True
        elif topic in ('cmd/sas', 'cmd/rcs', 'cmd/gear', 'cmd/lights', 'cmd/brakes'):
            setattr(ctl, topic.split('/')[1], bool(p.get('on')))
        elif topic == 'cmd/solar':
            for sp in self.solar_parts:
                if sp.deployable:
                    sp.deployed = bool(p.get('on'))
        elif topic == 'cmd/chute':
            for c in self.chute_parts:
                if c.state.name in ('stowed', 'armed'):
                    c.deploy()
        elif topic == 'cmd/thrust_limit':
            lim = max(0.0, min(1.0, float(p.get('v', 1))))
            for d in self.engines:                  # the engines that are lit; solid boosters cannot be limited in flight
                e = d['e']
                if e.active and not e.throttle_locked:
                    e.thrust_limit = lim
            self.read_engine_settings()
        elif topic == 'cmd/gimbal':
            for d in self.engines:
                if d['e'].gimballed:
                    d['e'].gimbal_locked = bool(p.get('locked'))
            self.read_engine_settings()
        elif topic == 'cmd/target':
            self.set_target(p)
        elif topic == 'cmd/undock':
            self.undock()
        elif topic == 'cmd/control_from':
            if p.get('port'):
                ports = [d for d in v.parts.docking_ports if d.state.name == 'ready']
                if ports:
                    v.parts.controlling = ports[0].part
            else:
                v.parts.controlling = self.ctrl_default
        elif topic == 'cmd/node':
            ctl.remove_nodes()                      # the PAD is the one maneuver: a node made in map view goes too
            self.nodes = []
            if not p.get('clear') and p.get('ut', 0) > self.streams['ut']():
                pro, nrm, rad = (float(x) for x in p['dv'])
                self.nodes = [ctl.add_node(float(p['ut']), prograde=pro, normal=nrm, radial=rad)]
        elif topic == 'cmd/pause':
            self.conn.krpc.paused = bool(p.get('on'))
        elif topic == 'cmd/game':
            if p.get('quicksave'):
                self.sc.quicksave()
            elif p.get('quickload'):
                self.sc.quickload()                 # the vessel object changes: the main loop rebinds
        elif topic == 'cmd/warp' and 'to_ut' in p:
            self.warp_to = float(p['to_ut'])
        elif topic == 'cmd/warp':
            sc = self.sc
            self.warp_to = None
            if p.get('stop'):
                sc.rails_warp_factor = 0
                sc.physics_warp_factor = 0
            else:
                step = int(p.get('step', 0))
                if sc.warp_mode.name == 'physics' or (sc.rails_warp_factor == 0 and v.orbit.body.has_atmosphere and
                                                      v.flight().mean_altitude < v.orbit.body.atmosphere_depth):
                    sc.physics_warp_factor = max(0, min(3, sc.physics_warp_factor + step))
                else:
                    sc.rails_warp_factor = max(0, min(7, sc.rails_warp_factor + step))
        elif topic == 'cmd/sas_mode':
            mode = p.get('mode', 'stability')
            if mode in SAS_MODES:
                try:
                    ctl.sas_mode = getattr(self.sc.SASMode, TO_KRPC[mode])
                except Exception as e:          # e.g. a mode not available at this pilot/probe level
                    print('sas_mode refused:', mode, e, flush=True)


    def set_target(self, p):
        """cmd/target: {'step': ±1} next / previous vessel around the same body (nearest first), {'port': 1} next free
        docking port of the target (then back to the vessel itself), {'clear': true}."""
        sc, v = self.sc, self.vessel
        if p.get('clear'):
            sc.clear_target()
            return
        tp = sc.target_docking_port
        tv = sc.target_vessel or (tp.part.vessel if tp is not None else None)
        if 'port' in p:
            if tv is None:
                return
            try:
                ports = [d for d in tv.parts.docking_ports if d.state.name == 'ready']
            except Exception:
                ports = []                          # not loaded yet (beyond physics range)
            i = ports.index(tp) + 1 if tp in ports else 0
            if i < len(ports):
                sc.target_docking_port = ports[i]
            else:
                sc.target_vessel = tv
            return
        nrf = v.orbit.body.non_rotating_reference_frame
        here = v.position(nrf)
        cands = [w for w in sc.vessels if w != v and w.orbit.body == v.orbit.body and w.type.name not in ('debris', 'flag')]
        if not cands:
            return
        cands.sort(key=lambda w: math.dist(here, w.position(nrf)))
        step = 1 if int(p.get('step', 1)) >= 0 else -1
        i = (cands.index(tv) + step) % len(cands) if tv in cands else (0 if step > 0 else -1)
        sc.target_vessel = cands[i]

    def warp_step(self):
        """WARP TO: pick the rails warp rate from the time left (kRPC's warp_to blocks, so it is done here, per loop)."""
        if self.warp_to is None:
            return
        sc = self.sc
        left = self.warp_to - self.streams['ut']()
        want = max([i for i, r in enumerate(RAILS) if r * 4 <= left] or [0])
        if want == 0:                               # under 20 s left: done (no point crawling there in real time)
            self.warp_to = None
        want = min(want, sc.maximum_rails_warp_factor)
        if sc.rails_warp_factor != want:
            sc.rails_warp_factor = want


def main():
    cmds = queue.Queue()
    cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='gateway-ksp')
    cli.will_set('gateway/status', json.dumps({'connected': False, 'plant': 'ksp'}), qos=1, retain=True)
    cli.on_connect = lambda c, u, f, rc, props=None: c.subscribe('cmd/#', qos=1)
    cli.on_message = lambda c, u, m: cmds.put((m.topic, json.loads(m.payload or b'{}')))
    while True:
        try:
            cli.connect(MQTT_HOST, MQTT_PORT, keepalive=10); break
        except OSError as e:
            print('broker not ready:', e, flush=True); time.sleep(1)
    cli.loop_start()
    status = lambda **kw: cli.publish('gateway/status', json.dumps({'plant': 'ksp', **kw}), qos=1, retain=True)
    while True:
        try:
            link = Link()
        except Exception as e:
            status(connected=False, error=str(e)[:200])
            print('kRPC not reachable:', e, flush=True)
            time.sleep(3)
            continue
        print('connected to kRPC', link.conn.krpc.get_status().version, flush=True)
        last_status = 0
        tick = 0
        try:
            while True:
                bound = link.bind()
                if bound is None:                    # VAB, Space Center, tracking station: no active vessel
                    if time.monotonic() - last_status > 2:
                        last_status = time.monotonic()
                        status(connected=False, scene='no vessel')
                    time.sleep(0.5)
                    continue
                if bound:
                    print('active vessel:', link.vessel.name, flush=True)
                    status(connected=True, scene='flight', vessel=link.vessel.name, paused=link.conn.krpc.paused)
                while not cmds.empty():
                    t, p = cmds.get()
                    link.command(t, p)
                link.warp_step()
                tick += 1
                for t, p in link.snapshot(slow=tick % 5 == 1, tgt=tick % 2 == 0).items():
                    cli.publish(t, json.dumps(p), qos=0, retain=(t == 'tlm/orbit'))
                if time.monotonic() - last_status > 5:
                    last_status = time.monotonic()
                    status(connected=True, scene='flight', vessel=link.vessel.name, paused=link.conn.krpc.paused)
                # wait for the next period on the command queue: a command (the computer's cutoff) acts at once
                deadline = time.monotonic() + 1 / RATE_HZ
                while True:
                    try:
                        t, p = cmds.get(timeout=max(0.0, deadline - time.monotonic()))
                    except queue.Empty:
                        break
                    link.command(t, p)
        except Exception as e:                       # scene change, KSP quit, vessel destroyed
            print('link lost:', repr(e)[:300], flush=True)
            status(connected=False, error=repr(e)[:200])
            try:
                link.conn.close()
            except Exception:
                pass
            time.sleep(2)


if __name__ == '__main__':
    main()
