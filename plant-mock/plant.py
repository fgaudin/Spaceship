"""Mock plant: publishes the same tlm/* as the KSP gateway, from its own simple physics, and obeys the same cmd/*.

Planar Kerbin (μ, R, rotation, exponential atmosphere fitted in selftest/planner/profile.js), a three-stage vehicle with
fixed mass flow and pressure-dependent Isp (TM-7), drag, and a built-in gravity turn (no stick yet: the mock flies the
pitch itself). Electric charge drains (more with the lights on). Failures: sim/failures/<id> {"on": true}
(engine_out: every engine; engine_one_out: one of the lit engines; battery_short; telemetry_freeze; overheat; comm_lost).
A scripted target (cmd/target) stands in for rendezvous and docking: it closes from 2 km and stops at 30 m.
"""
import copy, json, math, os, threading, time
import paho.mqtt.client as mqtt

HOST = os.environ.get('MQTT_HOST', 'localhost')
PORT = int(os.environ.get('MQTT_PORT', '1883'))
MU, R, OMEGA, G0 = 3.5316e12, 600000.0, 2 * math.pi / 21549.425, 9.80665
RHO0, H_RHO, P0, H_P, ATM_TOP = 1.512, 5444.0, 101325.0, 5441.0, 70000.0
CDA = 4.0

STAGES = [   # name, propellant kg, dry kg, vacuum thrust N, Isp SL / vac s, resource
    {'name': 'S1', 'prop': 32000.0, 'dry': 6000.0, 'F': 1500e3, 'isp_sl': 285.0, 'isp_vac': 310.0, 'res': 'LiquidFuel'},
    {'name': 'S2', 'prop': 12000.0, 'dry': 2500.0, 'F': 250e3, 'isp_sl': 90.0, 'isp_vac': 350.0, 'res': 'LiquidFuel'},
    {'name': 'S3', 'prop': 1800.0, 'dry': 600.0, 'F': 60e3, 'isp_sl': 85.0, 'isp_vac': 345.0, 'res': 'LiquidFuel'},
]
PAYLOAD = 3900.0
EC_MAX = 400.0
ENGINES = [[(0.0, 0.0), (1.3, 0.0), (-1.3, 0.0), (0.0, 1.3), (0.0, -1.3)], [(0.0, 0.0)], [(0.0, 0.0)]]   # x, z per stage
TARGETS = ['Station', 'Tug']
WARP = [1, 2, 3, 4, 5, 10, 50, 100]          # the mock warps the whole simulation (rails or physics alike)


class Plant:
    def __init__(self):
        self.reset()

    def reset(self):
        self.t, self.met0 = 0.0, None
        self.pitch = 90.0
        self.x, self.y, self.vx, self.vy = 0.0, R, OMEGA * R, 0.0    # inertial, launch site at +y, east +x
        self.stage_idx = -1                    # -1: on the pad, nothing lit
        self.props = [s['prop'] for s in STAGES]
        self.attached = len(STAGES)
        self.throttle, self.sas, self.rcs, self.gear, self.lights, self.brakes = 0.0, False, False, True, False, False
        self.sas_mode = 'stability'
        self.ec = EC_MAX
        self.situation = 'pre_launch'
        self.failures = set()
        self.g = 1.0
        self.q = 0.0
        self.thrust = 0.0
        self.solar, self.chute = False, 'stowed'
        self.warp = 0                          # index into WARP
        self.warp_to = None
        self.limit, self.gimbal_locked, self.paused = 1.0, False, False
        self.tgt, self.tgt_port, self.tgt_range, self.ctrl_port = None, None, 2000.0, False
        self.node = None

    # ---------- commands ----------
    def command(self, topic, p):
        if topic == 'cmd/throttle':
            self.throttle = max(0.0, min(1.0, float(p.get('v', 0))))
        elif topic == 'cmd/stage':
            self.stage()
        elif topic == 'cmd/abort':
            self.throttle = 0.0
            self.attached = min(self.attached, 0)    # capsule only
            self.stage_idx = len(STAGES)
        elif topic in ('cmd/sas', 'cmd/rcs', 'cmd/gear', 'cmd/lights', 'cmd/brakes'):
            setattr(self, topic.split('/')[1], bool(p.get('on')))
        elif topic == 'cmd/solar':
            self.solar = bool(p.get('on'))
        elif topic == 'cmd/chute':
            if self.chute == 'stowed':
                self.chute = 'deployed'
        elif topic == 'cmd/thrust_limit':
            self.limit = max(0.0, min(1.0, float(p.get('v', 1))))
        elif topic == 'cmd/gimbal':
            self.gimbal_locked = bool(p.get('locked'))
        elif topic == 'cmd/target':
            if p.get('clear'):
                self.tgt = self.tgt_port = None
            elif 'port' in p:
                if self.tgt is not None:
                    self.tgt_port = 0 if self.tgt_port is None else None if self.tgt_port >= 1 else self.tgt_port + 1
            else:
                step = 1 if int(p.get('step', 1)) >= 0 else -1
                self.tgt = (0 if step > 0 else len(TARGETS) - 1) if self.tgt is None else (self.tgt + step) % len(TARGETS)
                self.tgt_port, self.tgt_range = None, 2000.0
        elif topic == 'cmd/control_from':
            self.ctrl_port = bool(p.get('port'))
        elif topic == 'cmd/node':
            self.node = None if p.get('clear') else {'ut': p.get('ut'), 'dv': p.get('dv')}
        elif topic == 'cmd/pause':
            self.paused = bool(p.get('on'))
        elif topic == 'cmd/game':
            if p.get('quicksave'):
                self.saved = copy.deepcopy({k: v for k, v in self.__dict__.items() if k != 'saved'})
            elif p.get('quickload') and getattr(self, 'saved', None):
                self.__dict__.update(copy.deepcopy(self.saved))
        elif topic == 'cmd/warp' and 'to_ut' in p:
            self.warp_to = float(p['to_ut'])
        elif topic == 'cmd/warp':
            self.warp_to = None
            if p.get('stop'):
                self.warp = 0
            else:
                self.warp = max(0, min(len(WARP) - 1, self.warp + int(p.get('step', 0))))
        elif topic == 'cmd/sas_mode':
            self.sas_mode = p.get('mode', 'stability')
        elif topic == 'sim/reset':
            self.reset()
        elif topic.startswith('sim/failures/'):
            f = topic.split('/')[-1]
            (self.failures.add if p.get('on') else self.failures.discard)(f)

    def stage(self):
        if self.stage_idx < 0:
            self.stage_idx = 0
            self.situation = 'flying'
            self.met0 = self.t
        elif self.stage_idx < len(STAGES):
            # drop the current stage and light the next one
            self.attached = len(STAGES) - self.stage_idx - 1
            self.stage_idx += 1

    # ---------- physics ----------
    def mass(self):
        m = PAYLOAD
        for i in range(len(STAGES) - self.attached, len(STAGES)):
            m += STAGES[i]['dry'] + self.props[i]
        return m

    def burning(self):
        i = self.stage_idx
        return 0 <= i < len(STAGES) and i >= len(STAGES) - self.attached and self.props[i] > 0 and 'engine_out' not in self.failures

    def lit(self):
        """Fraction of the stage's engines giving thrust (failure engine_one_out: one of several is out)."""
        n = len(ENGINES[self.stage_idx]) if 0 <= self.stage_idx < len(STAGES) else 1
        return (n - 1) / n if 'engine_one_out' in self.failures and n > 1 else 1.0

    def step(self, dt):
        self.t += dt
        if self.tgt is not None:
            self.tgt_range = max(30.0, self.tgt_range - self.closing() * dt)
        if self.warp_to is not None:
            left = self.warp_to - self.t
            self.warp = max([i for i, r in enumerate(WARP) if r * 4 <= left] or [0])
            if left <= 4:
                self.warp, self.warp_to = 0, None
        r = math.hypot(self.x, self.y)
        h = r - R
        ur = (self.x / r, self.y / r)
        uh = (ur[1], -ur[0])
        va = (self.vx - OMEGA * self.y, self.vy + OMEGA * self.x)          # air-relative
        vam = math.hypot(*va)
        p = P0 * math.exp(-h / H_P) if h < ATM_TOP else 0.0
        rho = RHO0 * math.exp(-h / H_RHO) if h < ATM_TOP else 0.0
        m = self.mass()
        F = 0.0
        if self.burning():
            s = STAGES[self.stage_idx]
            mdot = s['F'] / (s['isp_vac'] * G0) * self.throttle * self.limit * self.lit()
            isp = s['isp_vac'] - (s['isp_vac'] - s['isp_sl']) * p / P0
            F = mdot * isp * G0
            burn = min(self.props[self.stage_idx], mdot * dt)
            self.props[self.stage_idx] -= burn
        g = MU / (r * r)
        if self.situation in ('pre_launch', 'landed', 'crashed') and F <= m * g:
            self.thrust = F                     # held on the ground until thrust exceeds weight
            self.q, self.g = 0.0, 1.0 if self.situation != 'crashed' else 0.0
            return
        if self.situation == 'crashed':
            return
        # pitch: vertical to 60 m/s, then along the air-relative velocity, kicked 5° east
        if vam < 60 or h < 500:
            u = (ur[0] * math.cos(math.radians(3)) + uh[0] * math.sin(math.radians(3)),
                 ur[1] * math.cos(math.radians(3)) + uh[1] * math.sin(math.radians(3)))
        else:
            u = (va[0] / vam, va[1] / vam)
            if h > ATM_TOP:                     # above the air: hold horizontal (circularise)
                u = uh
        self.pitch = math.degrees(math.atan2(u[0] * ur[0] + u[1] * ur[1], u[0] * uh[0] + u[1] * uh[1]))
        D = 0.5 * rho * vam * vam * (CDA + (300.0 if self.chute == 'deployed' and h < 8000 else 0.0))
        ax = F / m * u[0] - (D / m) * (va[0] / vam if vam else 0) - g * ur[0]
        ay = F / m * u[1] - (D / m) * (va[1] / vam if vam else 0) - g * ur[1]
        self.vx += ax * dt
        self.vy += ay * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.thrust = F
        self.q = 0.5 * rho * vam * vam
        self.g = math.hypot(ax + g * ur[0], ay + g * ur[1]) / G0
        if math.hypot(self.x, self.y) < R:
            if vam < 6:
                self.situation = 'landed'
            else:
                self.situation = 'crashed'
            self.x, self.y = ur[0] * R, ur[1] * R
            self.vx, self.vy = OMEGA * self.y, -OMEGA * self.x       # at rest on the turning ground
        elif h > ATM_TOP:
            self.situation = 'orbiting' if self.orbit()['peri'] > ATM_TOP else 'sub_orbital'
        else:
            self.situation = 'flying'
        drain = (0.5 + (3.0 if self.lights else 0) + (1.0 if self.sas else 0) - (2.5 if self.solar else 0)) * dt
        if 'battery_short' in self.failures:
            drain += 20 * dt
        self.ec = max(0.0, min(EC_MAX, self.ec - drain))

    def orbit(self):
        r = math.hypot(self.x, self.y)
        v2 = self.vx ** 2 + self.vy ** 2
        eps = v2 / 2 - MU / r
        h = self.x * self.vy - self.y * self.vx
        e = math.sqrt(max(0.0, 1 + 2 * eps * h * h / MU ** 2))
        a = -MU / (2 * eps) if abs(eps) > 1e-9 else float('inf')
        p = h * h / MU
        rp = p / (1 + e)
        ra = p / (1 - e) if e < 1 else float('inf')
        # true anomaly from r and the sign of the radial speed
        cosnu = max(-1.0, min(1.0, (p / r - 1) / e)) if e > 1e-6 else 1.0
        nu = math.degrees(math.acos(cosnu)) * (1 if self.x * self.vx + self.y * self.vy >= 0 else -1)
        return {'body': 'Kerbin', 'apo': ra - R if math.isfinite(ra) else None, 'peri': rp - R, 'a': a, 'e': e, 'i': 0.0, 'nu': round(nu, 3),
                'period': 2 * math.pi * math.sqrt(a ** 3 / MU) if e < 1 and a > 0 else None,
                't_soi': None, **self._times(a, e, nu)}

    @staticmethod
    def _times(a, e, nu_deg):
        """Time to apoapsis and periapsis (Kepler's equation), for an ellipse."""
        if not (0 <= e < 1) or a <= 0:
            return {'t_apo': None, 't_peri': None}
        nu = math.radians(nu_deg)
        E = 2 * math.atan2(math.sqrt(1 - e) * math.sin(nu / 2), math.sqrt(1 + e) * math.cos(nu / 2))
        M = (E - e * math.sin(E)) % (2 * math.pi)
        n = math.sqrt(MU / a ** 3)
        return {'t_peri': round(((2 * math.pi - M) % (2 * math.pi)) / n, 1), 't_apo': round(((math.pi - M) % (2 * math.pi)) / n, 1)}

    def closing(self):
        return 0.0 if self.tgt_range <= 30.0 else max(0.2, self.tgt_range / 300.0)    # a little over the ρ/400 s gate

    def target(self):
        if self.tgt is None:
            return {'set': False, 'ctrl_port': self.ctrl_port}
        c = self.closing()
        out = {'set': True, 'name': TARGETS[self.tgt], 'range': round(self.tgt_range, 2), 'closing': round(c, 3),
               'los_rate': 0.5, 'rel_v': round(c, 3), 'ctrl_port': self.ctrl_port}
        if self.tgt_port is not None:
            out['port'] = {'axial': round(self.tgt_range, 3), 'x': 0.1, 'z': -0.05, 'v_axial': -round(c, 4), 'vx': 0.0, 'vz': 0.0,
                           'angle': 2.0, 'from_port': self.ctrl_port, 'right': 0.1, 'up': 0.05, 'fwd': round(self.tgt_range, 3),
                           'v_right': -0.01, 'v_up': 0.0, 'yaw': 1.5, 'pitch': -0.5, 'roll': 4.0}
        return out

    def engines(self):
        i, out = self.stage_idx, []
        for k, pos in enumerate(ENGINES):
            here = k >= len(STAGES) - self.attached
            if not here:
                continue
            on = k == i
            n = len(pos)
            for j, (x, z) in enumerate(pos):
                fuel = self.props[k] > 0 and 'engine_out' not in self.failures
                dead = on and 'engine_one_out' in self.failures and n > 1 and j == 1
                each = STAGES[k]['F'] * self.limit / n
                out.append({'x': x, 'z': z, 'stage': len(STAGES) - k, 'on': on, 'fuel': fuel,
                            'max': round(each if fuel else 0.0, 1),
                            'thrust': round(self.thrust / (n * self.lit()), 1) if on and fuel and not dead else 0.0})
        return {'engines': out, 'limit': self.limit, 'gimbal_locked': self.gimbal_locked}

    # ---------- telemetry ----------
    def telemetry(self):
        r = math.hypot(self.x, self.y)
        ur = (self.x / r, self.y / r)
        uh = (ur[1], -ur[0])
        va = (self.vx - OMEGA * self.y, self.vy + OMEGA * self.x)
        vs = va[0] * ur[0] + va[1] * ur[1]
        hs = va[0] * uh[0] + va[1] * uh[1]
        h = r - R
        met = self.t - self.met0 if self.met0 is not None else 0.0
        i = self.stage_idx
        st = STAGES[i] if 0 <= i < len(STAGES) and i >= len(STAGES) - self.attached else None
        avail = st['F'] * self.limit * self.lit() if st and self.props[i] > 0 and 'engine_out' not in self.failures else 0.0
        stage_res = {st['res']: {'amount': round(self.props[i] / 5.0, 2), 'max': st['prop'] / 5.0}} if st else {}
        ksp_stage = len(STAGES) - max(i, 0) if i >= 0 else len(STAGES) + 1
        return {
            'tlm/time': {'ut': round(self.t, 2), 'met': round(met, 2), 'warp': WARP[self.warp], 'paused': self.paused},
            'tlm/flight': {'alt': round(h, 1), 'radar': round(h, 1), 'vs': round(vs, 2), 'hs': round(hs, 2),
                           'speed': round(math.hypot(*va), 2), 'q': round(self.q, 1), 'g': round(self.g, 3),
                           'vn': 0.0, 've': round(hs, 2),
                           'lat': 0.0, 'lon': round(math.degrees(math.atan2(self.x, self.y) - OMEGA * self.t), 4)},
            'tlm/vessel': {'name': 'Mock X', 'mass': round(self.mass(), 1), 'thrust': round(self.thrust, 1),
                           'thrust_avail': avail, 'isp': st['isp_vac'] if st else 0, 'situation': self.situation,
                           'stage': ksp_stage, 'throttle': self.throttle, 'sas': self.sas, 'rcs': self.rcs,
                           'gear': self.gear, 'lights': self.lights, 'brakes': self.brakes, 'sas_mode': self.sas_mode,
                           'solar': self.solar, 'chute': self.chute, 'comm': 'comm_lost' not in self.failures,
                           'has_gear': False, 'contact': self.situation in ('pre_launch', 'landed')},
            # nose attitude against the local horizon (deg); the mock flies due east with a slow roll program
            'tlm/attitude': {'pitch': round(getattr(self, 'pitch', 90.0), 2), 'heading': 90.0,
                             'roll': round(max(0.0, min(1.0, (met - 8) / 12)) * 90.0 - 90.0, 2) if self.met0 is not None else -90.0,
                             'prograde': {'pitch': round(math.degrees(math.atan2(vs, hs)), 2), 'heading': 90.0}
                             if math.hypot(vs, hs) > 1 else None},
            'tlm/orbit': self.orbit(),
            'tlm/target': self.target(),
            'tlm/engines': self.engines(),
            'tlm/thermal': {'max': 0.9 if 'overheat' in self.failures else 0.2},
            'tlm/node': {'set': True, 'ut': self.node['ut'], 'dv': self.node['dv'], 'att_err': 1.0} if self.node else {'set': False},
            'tlm/resources': {'stage': stage_res,
                              'total': {'ElectricCharge': {'amount': round(self.ec, 2), 'max': EC_MAX}}},
        }


def main():
    plant = Plant()
    lock = threading.Lock()
    cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='plant-mock')
    cli.will_set('gateway/status', json.dumps({'connected': False, 'plant': 'mock'}), qos=1, retain=True)

    status = lambda c: c.publish('gateway/status', json.dumps({'connected': True, 'plant': 'mock', 'scene': 'flight',
                                                                'vessel': 'Mock X', 'paused': False}), qos=1, retain=True)

    def on_connect(c, u, f, rc, props=None):
        c.subscribe('cmd/#', qos=1); c.subscribe('sim/#', qos=1)
        status(c)
        print('mock plant connected', flush=True)

    def on_message(c, u, m):
        try:
            p = json.loads(m.payload or b'{}')
        except ValueError:
            return
        with lock:
            plant.command(m.topic, p)

    cli.on_connect, cli.on_message = on_connect, on_message
    while True:
        try:
            cli.connect(HOST, PORT, keepalive=10); break
        except OSError as e:
            print('broker not ready:', e, flush=True); time.sleep(1)
    cli.loop_start()
    dt, pub_every, n = 0.02, 5, 0
    last = time.monotonic()
    while True:
        now = time.monotonic()
        steps = max(1, int((now - last) / dt))
        last += steps * dt
        with lock:
            for _ in range(0 if plant.paused else min(steps * WARP[plant.warp], 5000)):
                plant.step(dt)
            n += 1
            tlm = plant.telemetry() if n % pub_every == 0 and 'telemetry_freeze' not in plant.failures else None
        if n % 250 == 0:                     # every 5 s (protocol: on change + 5 s)
            status(cli)
        if tlm:
            for t, p in tlm.items():
                cli.publish(t, json.dumps(p), qos=0, retain=(t == 'tlm/orbit'))
        time.sleep(max(0.0, last + dt - time.monotonic()))


if __name__ == '__main__':
    main()
