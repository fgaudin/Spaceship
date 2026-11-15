"""Rendezvous and docking in low Kerbin orbit, with the course's methods (planner/rdv.js).

    .venv/bin/python selftest/flight/rdv.py liftoff     # chaser on the pad: TM-11 liftoff time, then ascent.py
    .venv/bin/python selftest/flight/rdv.py transfer    # chaser in orbit: phase angle → Hohmann TIG, first burn
    .venv/bin/python selftest/flight/rdv.py terminal    # near arrival: braking gates (docking chapter) down to 100 m
    .venv/bin/python selftest/flight/rdv.py dock        # from 100 m: onto the target port's axis, close in, capture

The target is the vessel named 'Target' (renamed by `name-target`); the chaser is the active vessel.
KSP is used as the plant only: orbits, positions and velocities are measured; every burn comes from the planner or from
the guidance laws below. The closest approach after the transfer burn is checked with KSP's orbit propagation.
"""
import json, math, os, sys, time
from common import Kio, Log, planner, save, norm, dot, cross, DATA, warp_to
import burn

G0 = 9.80665


def sub(a, b): return [x - y for x, y in zip(a, b)]
def add(a, b): return [x + y for x, y in zip(a, b)]
def mul(a, k): return [x * k for x in a]
def mag(a): return math.sqrt(dot(a, a))
def clamp(x, lo, hi): return max(lo, min(hi, x))


def find_target(sc):
    name = os.environ.get('RDV_TARGET', 'Target')
    ts = [v for v in sc.vessels if v.name == name]
    if not ts:
        raise SystemExit(f"no vessel named {name!r} (run name-target with the target active, or set RDV_TARGET)")
    return ts[0]


def phase_angle(r_from, r_to, h):
    """Angle from r_from to r_to in the direction of motion (orbit normal h), in (−π, π]."""
    a, b = norm(r_from), norm(r_to)
    return math.atan2(dot(cross(a, b), norm(h)), dot(a, b))


def rel(ch, tg, f):
    """Target relative to the chaser: position (chaser → target) and the chaser's velocity relative to the target."""
    return sub(tg.position(f), ch.position(f)), sub(ch.velocity(f), tg.velocity(f))


def set_limit(v, frac):
    for e in v.parts.engines:
        if e.active:
            e.thrust_limit = frac


def closest_approach(ch, tg, f, t0, t1, step=5.0):
    best = (1e18, t0)
    t = t0
    while t <= t1:
        d = mag(sub(ch.orbit.position_at(t, f), tg.orbit.position_at(t, f)))
        if d < best[0]:
            best = (d, t)
        t += step
    # refine
    lo, hi = best[1] - step, best[1] + step
    for _ in range(40):
        m1, m2 = lo + (hi - lo) / 3, hi - (hi - lo) / 3
        d1 = mag(sub(ch.orbit.position_at(m1, f), tg.orbit.position_at(m1, f)))
        d2 = mag(sub(ch.orbit.position_at(m2, f), tg.orbit.position_at(m2, f)))
        if d1 < d2: hi = m2
        else: lo = m1
    t = (lo + hi) / 2
    return mag(sub(ch.orbit.position_at(t, f), tg.orbit.position_at(t, f))), t


# ---------------------------------------------------------------- name-target
def name_target():
    k = Kio('rdv-name')
    v = k.sc.active_vessel
    v.name = 'Target'
    v.control.sas = True
    v.control.rcs = False
    print('active vessel renamed Target, SAS on;', v.orbit.apoapsis_altitude, v.orbit.periapsis_altitude)
    k.close()


# ---------------------------------------------------------------- liftoff
def liftoff():
    log = Log('rdv-liftoff')
    k = Kio('rdv-liftoff')
    sc = k.sc
    ch = sc.active_vessel
    tg = find_target(sc)
    ch.name = 'Chaser'
    body = ch.orbit.body
    nrf = body.non_rotating_reference_frame
    plan = json.load(open(os.path.join(DATA, 'ascent-plan.json')))
    circ = plan['result']['circ']
    h_low = plan['prog']['targetAlt']
    t_coast = float(os.environ.get('RDV_COAST', '1200'))
    omega = 2 * math.pi / body.rotational_period
    rt, vt = tg.position(nrf), tg.velocity(nrf)
    h = cross(rt, vt)
    site = ch.position(nrf)
    # the site projected into the target's plane (TM-8: the planes are within a fraction of a degree here)
    hu = norm(h)
    site_p = sub(site, mul(hu, dot(site, hu)))
    phi_now = phase_angle(site_p, rt, h)
    di = math.degrees(math.asin(clamp(abs(dot(norm(site), hu)), 0, 1)))
    h_tgt = tg.orbit.semi_major_axis - body.equatorial_radius
    L, _ = planner('rdv.js', {'cmd': 'liftoff', 'hLow': h_low, 'hTgt': h_tgt, 'tAsc': circ['tApo'], 'thAsc': circ['thApo'],
                              'tCoast': t_coast, 'phiNow': phi_now, 'omega': omega})
    t_lift = sc.ut + L['delay']
    log(f"target {tg.orbit.apoapsis_altitude / 1e3:.1f} x {tg.orbit.periapsis_altitude / 1e3:.1f} km, i {math.degrees(tg.orbit.inclination):.3f}°; "
        f"site {di:.3f}° off the target plane")
    log(f"TM-11 liftoff: ascent {circ['tApo']:.0f} s over {math.degrees(circ['thApo']):.2f}°, coast {t_coast:.0f} s, Hohmann "
        f"{L['tH']:.0f} s → target must lead the site by {math.degrees(L['phiLift']):.2f}° at liftoff; now {math.degrees(phi_now):.2f}°; "
        f"liftoff in {L['delay']:.0f} s (UT {t_lift:.1f})")
    json.dump({'t_lift': t_lift, 'phi_lift': L['phiLift'], 'phi_now': phi_now, 't_coast': t_coast, 'plan_tAsc': circ['tApo'],
               'tH': L['tH']}, open(os.path.join(DATA, 'rdv-liftoff.json'), 'w'), indent=1)
    if '--dry' in sys.argv:
        return
    if t_lift - sc.ut > 20:
        warp_to(k, t_lift - 12, log)
    while sc.ut < t_lift - 2.2:       # ascent.py stages about 2 s after it starts
        time.sleep(0.05)
    log(f'starting ascent at UT {sc.ut:.1f}')
    k.close()
    import ascent
    sys.argv = [sys.argv[0]]
    ascent.main()


# ---------------------------------------------------------------- Mun liftoff (lander from the surface, LOR)
def mun_liftoff():
    """TM-11 ascent timing on the Mun: the ascent profile comes from planner/mun_ascent.js (the same law as
    flight/mun_ascent.py), the wait from timing.phys.js liftoff / liftoffDelay with the Mun's rotation."""
    log = Log('rdv-mun-liftoff')
    k = Kio('rdv-mun-liftoff')
    sc = k.sc
    ch = sc.active_vessel
    tg = find_target(sc)
    body = ch.orbit.body
    nrf = body.non_rotating_reference_frame
    mu, R = body.gravitational_parameter, body.equatorial_radius
    target = float(os.environ.get('RDV_LOW', '20000'))
    t_coast = float(os.environ.get('RDV_COAST', '600'))
    omega = 2 * math.pi / body.rotational_period
    ch.control.throttle = 0.0
    F, isp = ch.available_thrust, ch.vacuum_specific_impulse
    if F <= 0:
        for e in ch.parts.engines:
            e.active = True
        F, isp = ch.available_thrust, ch.vacuum_specific_impulse
    A, _ = planner('mun_ascent.js', {'target': target, 'm0': ch.mass, 'F': F, 'isp': isp, 'mu': mu, 'R': R, 'omega': omega})
    rt, vt = tg.position(nrf), tg.velocity(nrf)
    h = cross(rt, vt)
    hu = norm(h)
    site = ch.position(nrf)
    site_p = sub(site, mul(hu, dot(site, hu)))
    phi_now = phase_angle(site_p, rt, h)
    off = math.degrees(math.asin(clamp(abs(dot(norm(site), hu)), 0, 1)))
    h_tgt = tg.orbit.semi_major_axis - R
    L, _ = planner('rdv.js', {'cmd': 'liftoff', 'hLow': target, 'hTgt': h_tgt, 'tAsc': A['tAsc'], 'thAsc': A['thAsc'],
                              'tCoast': t_coast, 'phiNow': phi_now, 'omega': omega, 'mu': mu, 'R': R})
    t_lift = sc.ut + L['delay']
    log(f"target {tg.orbit.apoapsis_altitude / 1e3:.1f} x {tg.orbit.periapsis_altitude / 1e3:.1f} km; site {off:.2f}° off its plane")
    log(f"ascent profile (planner/mun_ascent.js): to {target / 1e3:.0f} km in {A['tAsc']:.0f} s over {math.degrees(A['thAsc']):.2f}°, "
        f"Δv {A['dvAscent']:.0f} + circ {A['dvCirc']:.0f} m/s")
    log(f"TM-11 liftoff: target must lead the site by {math.degrees(L['phiLift']):.2f}° at liftoff; now {math.degrees(phi_now):.2f}°; "
        f"liftoff in {L['delay']:.0f} s (UT {t_lift:.1f}), then coast {t_coast:.0f} s and Hohmann {L['tH']:.0f} s")
    if '--dry' in sys.argv:
        return
    if t_lift - sc.ut > 20:
        warp_to(k, t_lift - 10, log)
    while sc.ut < t_lift - 0.5:
        time.sleep(0.05)
    log(f'liftoff at UT {sc.ut:.1f}')
    k.close()
    import mun_ascent
    sys.argv = [sys.argv[0], '--target', str(target)]
    mun_ascent.main()


# ---------------------------------------------------------------- plane change (TM-8)
def plane():
    """Rotate the chaser's orbit into the target's plane at the next relative node (planes.phys.js planeDv for the size;
    the Δv vector keeps the speed and turns the velocity into the target plane: v_new = |v_h| · (ĥ_t × r̂) + v_r)."""
    log = Log('rdv-plane')
    k = Kio('rdv-plane')
    sc = k.sc
    ch = sc.active_vessel
    tg = find_target(sc)
    nrf = ch.orbit.body.non_rotating_reference_frame
    ch.control.throttle = 0.0
    hc = norm(cross(ch.position(nrf), ch.velocity(nrf)))
    ht = norm(cross(tg.position(nrf), tg.velocity(nrf)))
    di = math.acos(clamp(dot(hc, ht), -1, 1))
    pl, _ = planner('rdv.js', {'cmd': 'plane', 'v': ch.orbit.speed, 'di': di})
    log(f'relative inclination {math.degrees(di):.3f}°, TM-8 plane change {pl["dv"]:.2f} m/s')
    if math.degrees(di) < 0.05:
        log('planes already matched')
        return
    # next node: where the chaser crosses the target plane (sign change of r · ĥ_t), at least 120 s ahead
    o = ch.orbit
    t0 = sc.ut + 120
    T = o.period
    f = lambda t: dot(o.position_at(t, nrf), ht)
    t, step = t0, 10.0
    prev = f(t)
    while t < t0 + T:
        t2 = t + step
        cur = f(t2)
        if prev * cur <= 0:
            lo, hi = t, t2
            for _ in range(50):
                mid = (lo + hi) / 2
                if f(lo) * f(mid) <= 0:
                    hi = mid
                else:
                    lo = mid
            t = (lo + hi) / 2
            break
        t, prev = t2, cur
    tig = t
    import burn
    pro, nrm, rad, r, vel = burn.frame_at(ch, tig, nrf)
    r_u = norm(r)
    v_r = dot(vel, r_u)
    v_h = sub(vel, mul(r_u, v_r))
    v_new = add(mul(norm(cross(ht, r_u)), mag(v_h)), mul(r_u, v_r))
    dv = sub(v_new, vel)
    pad = {'tig': tig, 'prograde': dot(dv, pro), 'normal': dot(dv, nrm), 'radial': dot(dv, rad)}
    F, isp = ch.available_thrust, ch.vacuum_specific_impulse
    pad['tb'] = planner('rdv.js', {'cmd': 'tb', 'dv': mag(dv), 'm': ch.mass, 'F': F, 'isp': isp})[0]['tb']
    log(f"node in {tig - sc.ut:.0f} s: Δv {mag(dv):.2f} m/s (TM-8 magnitude {pl['dv']:.2f}) = pro {pad['prograde']:.2f}, "
        f"nrm {pad['normal']:.2f}, rad {pad['radial']:.2f}")
    save(k, 'rdv-pre-plane', log)
    burn.execute(k, ch, pad, log, None, settle_s=40)
    ch.auto_pilot.engaged = False
    hc = norm(cross(ch.position(nrf), ch.velocity(nrf)))
    log(f'after: relative inclination {math.degrees(math.acos(clamp(dot(hc, ht), -1, 1))):.3f}°, '
        f'orbit {ch.orbit.apoapsis_altitude / 1e3:.2f} x {ch.orbit.periapsis_altitude / 1e3:.2f} km')
    save(k, 'rdv-plane', log)
    k.close()


# ---------------------------------------------------------------- transfer
def transfer():
    log = Log('rdv-transfer')
    k = Kio('rdv-transfer')
    sc = k.sc
    ch = sc.active_vessel
    tg = find_target(sc)
    body = ch.orbit.body
    nrf = body.non_rotating_reference_frame
    mu = body.gravitational_parameter
    oc, ot = ch.orbit, tg.orbit
    hc = cross(ch.position(nrf), ch.velocity(nrf))
    ht = cross(tg.position(nrf), tg.velocity(nrf))
    di = math.acos(clamp(dot(norm(hc), norm(ht)), -1, 1))
    pl, _ = planner('rdv.js', {'cmd': 'plane', 'v': ot.speed, 'di': di})
    log(f"chaser {oc.apoapsis_altitude / 1e3:.2f} x {oc.periapsis_altitude / 1e3:.2f} km, target {ot.apoapsis_altitude / 1e3:.2f} x "
        f"{ot.periapsis_altitude / 1e3:.2f} km; relative inclination {math.degrees(di):.3f}° (plane change {pl['dv']:.2f} m/s, "
        f"left to the terminal phase)")
    phi0 = phase_angle(ch.position(nrf), tg.position(nrf), hc)
    ut0 = sc.ut
    P, _ = planner('rdv.js', {'cmd': 'phase', 'r1': oc.semi_major_axis, 'r2': ot.semi_major_axis, 'phi0': phi0, 't0': ut0, 'mu': mu})
    log(f"TM-11: phase now {math.degrees(phi0):.2f}°, required {math.degrees(P['phiReq']):.2f}°, wait {P['wait']:.0f} s "
        f"(synodic {P['syn'] / 3600:.1f} h), TOF {P['tof']:.0f} s; Hohmann Δv {P['dv1']:.2f} + {P['dv2']:.2f} m/s")
    tig = P['tig']
    while tig - sc.ut < 90:
        tig += P['syn']
    set_limit(ch, 0.25)
    F, isp, m = ch.available_thrust, ch.vacuum_specific_impulse, ch.mass
    tb = planner('rdv.js', {'cmd': 'tb', 'dv': P['dv1'], 'm': m, 'F': F, 'isp': isp})[0]['tb']
    save(k, 'rdv-pre-transfer', log)
    res = burn.execute(k, ch, {'tig': tig, 'prograde': P['dv1'], 'normal': 0, 'radial': 0, 'tb': tb}, log, None, settle_s=40)
    ch.auto_pilot.engaged = False
    miss, tca = closest_approach(ch, tg, nrf, sc.ut, sc.ut + P['tof'] * 1.5)
    log(f"check (KSP propagation): closest approach {miss:.0f} m at UT {tca:.0f} (planned arrival UT {tig + P['tof']:.0f}, "
        f"{tca - tig - P['tof']:+.0f} s)")
    json.dump({'tig': tig, 'tof': P['tof'], 'tca': tca, 'miss': miss, 'dv1': P['dv1'], 'dv2': P['dv2'], 'burn': res},
              open(os.path.join(DATA, 'rdv-transfer.json'), 'w'), indent=1)
    save(k, 'rdv-transfer-coast', log)
    k.close()


# ---------------------------------------------------------------- guidance helpers
class Ctl:
    """Main engine (throttled down) and RCS translation, both driven by a Δv error vector in a given frame."""
    def __init__(self, k, ch, log):
        self.k, self.sc, self.ch, self.log = k, k.sc, ch, log
        self.ap = ch.auto_pilot
        self.c = ch.control

    def rcs(self, err, frame, gain=3.0):
        d = self.sc.transform_direction(tuple(err), frame, self.ch.reference_frame)
        self.c.right = clamp(gain * d[0], -1, 1)
        self.c.forward = clamp(gain * d[1], -1, 1)
        self.c.up = clamp(-gain * d[2], -1, 1)

    def rcs_off(self):
        self.c.right = self.c.forward = self.c.up = 0.0

    def engine(self, err_fn, frame, tol, timeout=120):
        """Point along the Δv error and burn until it is below tol (closed loop on the measured relative velocity)."""
        self.rcs_off()
        ap = self.ap
        ap.reference_frame = frame
        t0 = self.sc.ut
        e = err_fn()
        ap.target_direction = tuple(norm(e))
        ap.engaged = True
        while self.sc.ut - t0 < timeout:
            e = err_fn()
            if mag(e) < tol:
                break
            ap.target_direction = tuple(norm(e))
            if ap.error < 3:
                acc = max(self.ch.available_thrust, 1) / self.ch.mass
                self.c.throttle = clamp(mag(e) / acc, 0.05, 1.0)
            else:
                self.c.throttle = 0.0
            time.sleep(0.05)
        self.c.throttle = 0.0
        return mag(err_fn())


# ---------------------------------------------------------------- terminal phase
def terminal():
    log = Log('rdv-terminal')
    k = Kio('rdv-terminal')
    sc = k.sc
    ch = sc.active_vessel
    tg = find_target(sc)
    body = ch.orbit.body
    nrf = body.non_rotating_reference_frame
    ctl = Ctl(k, ch, log)
    gate = lambda rho: planner('rdv.js', {'cmd': 'gate', 'rho': rho})[0]
    G = gate(1000)
    TAU, VMIN, HAND = G['TAU_G'], G['V_MIN'], G['HANDOVER']
    gs = lambda rho: max(rho / TAU, VMIN)
    set_limit(ch, 0.10)
    ch.control.sas = False
    ch.control.rcs = True
    # arrive: warp until about 6 km or the closest approach
    tr = json.load(open(os.path.join(DATA, 'rdv-transfer.json')))
    miss, tca = closest_approach(ch, tg, nrf, sc.ut, sc.ut + 3000)
    log(f'closest approach {miss:.0f} m at UT {tca:.0f} ({tca - sc.ut:.0f} s from now)')
    # time when the range falls under 6 km, else the closest approach
    t_start = tca
    t = sc.ut
    while t < tca:
        if mag(sub(ch.orbit.position_at(t, nrf), tg.orbit.position_at(t, nrf))) < 6000:
            t_start = t
            break
        t += 5
    if t_start - sc.ut > 60:
        warp_to(k, t_start - 30, log)
    p, vr = rel(ch, tg, nrf)
    rho = mag(p)
    vc = dot(vr, norm(p))                # closing speed (positive when closing)
    vs = mag(sub(vr, mul(norm(p), dot(vr, norm(p)))))
    log(f'TERMINAL start: range {rho:.0f} m, closing {vc:.2f} m/s, sideways {vs:.2f} m/s (Δv to null {mag(vr):.2f} m/s)')
    ap = ch.auto_pilot
    ap.reference_frame = nrf
    ap.target_roll = float('nan')
    mono0 = ch.resources.amount('MonoPropellant')
    lf0 = ch.resources.amount('LiquidFuel')
    firing = False
    last_log = 0
    n_eng = 0
    t0 = sc.ut
    while True:
        p, vr = rel(ch, tg, nrf)
        rho = mag(p)
        u = norm(p)
        v_des = mul(u, gs(rho))
        err = sub(v_des, vr)
        e = mag(err)
        if rho < HAND:
            break
        if e > max(1.5, 0.5 * gs(rho)):
            n_eng += 1
            sc.physics_warp_factor = 0
            log(f'  range {rho:.0f} m: engine trim, error {e:.2f} m/s (gate {gs(rho):.2f})')
            left = ctl.engine(lambda: sub(mul(norm(rel(ch, tg, nrf)[0]), gs(mag(rel(ch, tg, nrf)[0]))), rel(ch, tg, nrf)[1]),
                              nrf, tol=0.3)
            log(f'    done, error {left:.2f} m/s')
            continue
        # keep the nose on the target (the COAS line of sight); RCS trims the rest
        ap.target_direction = tuple(u)
        ap.engaged = True
        on = max(0.15 * gs(rho), 0.04)
        if e > on or (firing and e > 0.3 * on):
            firing = True
            sc.physics_warp_factor = 0
            ctl.rcs(err, nrf)
        else:
            firing = False
            ctl.rcs_off()
            sc.physics_warp_factor = 0          # physics warp + autopilot burns RCS against itself (gaps.md G12)
        if sc.ut - last_log > 30:
            last_log = sc.ut
            los = mag(cross(u, vr)) / rho
            log(f'  t {sc.ut - t0:6.0f} s range {rho:7.1f} m closing {dot(vr, u):5.2f} (gate {gs(rho):.2f}) error {e:.2f} '
                f'LOS rate {math.degrees(los) * 60:.3f}°/min mono {ch.resources.amount("MonoPropellant"):.1f}')
        if sc.ut - t0 > 7200:
            log('terminal timeout')
            break
        time.sleep(0.1)
    sc.physics_warp_factor = 0
    ctl.rcs_off()
    # stop at the handover point
    ctl_err = lambda: mul(rel(ch, tg, nrf)[1], -1)
    while mag(ctl_err()) > 0.03:
        ctl.rcs(ctl_err(), nrf)
        time.sleep(0.1)
    ctl.rcs_off()
    p, vr = rel(ch, tg, nrf)
    log(f'HANDOVER at {mag(p):.1f} m, relative speed {mag(vr):.3f} m/s; {n_eng} engine trims, '
        f'mono used {mono0 - ch.resources.amount("MonoPropellant"):.1f}, fuel used {lf0 - ch.resources.amount("LiquidFuel"):.1f} '
        f'in {sc.ut - t0:.0f} s')
    save(k, 'rdv-handover', log)
    k.close()


# ---------------------------------------------------------------- docking
def dock(standoff=30.0, save_name=None):
    log = Log('rdv-dock')
    k = Kio('rdv-dock')
    sc = k.sc
    ch = sc.active_vessel
    tg = find_target(sc)
    nrf = ch.orbit.body.non_rotating_reference_frame
    ready = lambda v: [d for d in v.parts.docking_ports if d.state == sc.DockingPortState.ready]
    # target port: the free one facing the chaser most
    tps = ready(tg)
    tp = max(tps, key=lambda d: dot(d.direction(nrf), norm(sub(ch.position(nrf), d.position(nrf)))))
    # chaser port: the free one facing forward
    cps = ready(ch)
    cp = max(cps, key=lambda d: d.direction(ch.reference_frame)[1])
    log(f'target ports {len(tps)}, chosen on {tp.part.title} ({tp.part.parent.title if tp.part.parent else "-"}); chaser port on '
        f'{cp.part.parent.title if cp.part.parent else "-"}')
    ch.parts.controlling = cp.part
    sc.target_docking_port = tp            # display aid only (navball target markers)
    F = tp.reference_frame                  # y: out of the target port
    ctl = Ctl(k, ch, log)
    ap = ch.auto_pilot
    ap.reference_frame = F
    ap.target_direction = (0.0, -1.0, 0.0)
    ap.target_roll = float('nan')
    ap.engaged = True
    ch.control.rcs = True
    ch.control.sas = False
    env = planner('rdv.js', {'cmd': 'gate', 'rho': 10})[0]['env']
    pos = lambda: list(cp.position(F))
    vel = lambda: list(ch.velocity(F))
    p = pos()
    log(f'chaser port in target-port frame: axial {p[1]:.1f} m, lateral {math.hypot(p[0], p[2]):.1f} m')
    # waypoints: around to the front of the port if needed, then 30 m out on the axis
    wps = []
    lat = [p[0], 0.0, p[2]]
    if mag(lat) < 1:
        lat = [1.0, 0.0, 0.0]
    lat = norm(lat)
    if p[1] < 20:
        wps += [[lat[0] * 40, p[1], lat[2] * 40], [lat[0] * 40, max(40.0, standoff), lat[2] * 40]]
    wps.append([0.0, standoff, 0.0])

    def go_to(w, tol=1.0, vmax=0.8):
        t0 = sc.ut
        while sc.ut - t0 < 1800:
            p, v = pos(), vel()
            d = sub(w, p)
            dist = mag(d)
            if dist < tol and mag(v) < 0.05:
                break
            v_des = mul(norm(d), clamp(dist / 60, 0.0, vmax)) if dist > 0.05 else [0, 0, 0]
            err = sub(v_des, v)
            ctl.rcs(err, F, gain=4.0) if mag(err) > 0.02 else ctl.rcs_off()
            time.sleep(0.1)
        ctl.rcs_off()

    for w in wps:
        log(f'  waypoint {w[0]:.0f}, {w[1]:.0f}, {w[2]:.0f} (port frame)')
        go_to(w)
        p = pos()
        log(f'    at axial {p[1]:.1f} m, lateral {math.hypot(p[0], p[2]):.2f} m, attitude error {ap.error:.1f}°')
    # final approach: close at well inside the capture envelope, null the lateral offset as we go
    v_close = 0.15
    log(f"FINAL approach at {v_close} m/s (capture envelope {env['vmin']}–{env['vmax']} m/s, lateral ≤ {env['lat']} m, "
        f"angle ≤ {env['ang']}°)")
    t0 = sc.ut
    last = 0
    docked = False
    while sc.ut - t0 < 900:
        try:
            if cp.state in (sc.DockingPortState.docked, sc.DockingPortState.docking):
                docked = True
                break
            p, v = pos(), vel()
        except Exception as e:                   # the vessels merged
            log(f'  (vessel changed: {e!r:.80})')
            docked = True
            break
        ax = p[1]
        lat_err = [-p[0] / 15, 0, -p[2] / 15]
        lat_err = [clamp(x, -0.1, 0.1) for x in lat_err]
        vy = -v_close if ax > 3 else -0.1
        if ap.error > 5:
            vy = 0.0                             # hold the range until the alignment is back
        v_des = [lat_err[0], vy, lat_err[2]]
        err = sub(v_des, v)
        ctl.rcs(err, F, gain=5.0) if mag(err) > 0.01 else ctl.rcs_off()
        if sc.ut - last > 5:
            last = sc.ut
            log(f'  axial {ax:6.2f} m lateral {math.hypot(p[0], p[2]):.2f} m closing {-v[1]:.3f} m/s att err {ap.error:.1f}°')
        time.sleep(0.1)
    try:
        ctl.rcs_off()
    except Exception:
        pass
    time.sleep(3)
    v = sc.active_vessel
    log(f"{'DOCKED' if docked else 'NOT DOCKED'}: active vessel {v.name}, {len(v.parts.all)} parts, "
        f"mass {v.mass / 1e3:.2f} t, ports {[d.state.name for d in v.parts.docking_ports]}")
    try:
        v.auto_pilot.engaged = False
        v.control.rcs = False
        v.control.sas = True
    except Exception:
        pass
    save(k, save_name or ('rdv-docked' if docked else 'rdv-dock-fail'), log)
    k.close()
    return docked


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    {'name-target': name_target, 'liftoff': liftoff, 'mun-liftoff': mun_liftoff, 'plane': plane, 'transfer': transfer,
     'terminal': terminal,
     'dock': dock}.get(
        cmd, lambda: sys.exit(__doc__))()
