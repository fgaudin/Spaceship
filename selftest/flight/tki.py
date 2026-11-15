"""Trans-Kerbin injection from a Mun orbit.

Course: TM-17's minimum-energy return gives the Δv (planner/tki.js → homeward.phys.js handMinEnergy) and a first burn
position (asymptote opposite the Mun's velocity, burn θ∞ behind it along a counter-clockwise orbit). homeward.phys.js
places the burn for Apollo's clockwise orbit and in the plane; our orbit is counter-clockwise and inclined 12°, and the
hand placement missed by ~470 km of Kerbin periapsis (KSP node check). So the burn time is then solved with the course's
patched-conic model in 3D (TM-13/17): Mun-centred two-body motion to the SOI radius (Laplace, 2 430 km), plus the Mun's
velocity there, Kerbin conic → vacuum periapsis; bisection on the TIG for the target periapsis.
KSP's node prediction is read as a check (removed), then burn.py flies the PAD.

    .venv/bin/python selftest/flight/tki.py [--rp 30000]
"""
import json, math, os, sys, time
from common import Kio, Log, DATA, planner, save, norm, dot, cross
import burn


def wrap(x):
    return x % (2 * math.pi)


def wrap_pi(x):
    y = wrap(x)
    return y - 2 * math.pi if y > math.pi else y


def add(a, b, k=1.0):
    return [x + k * y for x, y in zip(a, b)]


def mag(a):
    return math.sqrt(dot(a, a))


def kerbin_rp(r0, v0, t0, mu_m, mu_k, R_soi, mun_state):
    """Patched conics: integrate Mun-centred two-body (RK4) to the SOI, then the Kerbin conic's periapsis radius."""
    f = lambda r: [-mu_m * x / mag(r) ** 3 for x in r]
    r, v, t = r0[:], v0[:], t0
    for _ in range(20000):
        if mag(r) >= R_soi:
            break
        dt = max(1.0, min(20.0, 0.002 * mag(r) / max(mag(v), 1.0) * 10))
        k1v = f(r); k1r = v
        k2v = f(add(r, k1r, dt / 2)); k2r = add(v, k1v, dt / 2)
        k3v = f(add(r, k2r, dt / 2)); k3r = add(v, k2v, dt / 2)
        k4v = f(add(r, k3r, dt)); k4r = add(v, k3v, dt)
        r = [r[i] + dt / 6 * (k1r[i] + 2 * k2r[i] + 2 * k3r[i] + k4r[i]) for i in range(3)]
        v = [v[i] + dt / 6 * (k1v[i] + 2 * k2v[i] + 2 * k3v[i] + k4v[i]) for i in range(3)]
        t += dt
    else:
        return None, None
    pm, vm = mun_state(t)
    R, V = add(r, pm), add(v, vm)
    h = mag(cross(R, V))
    eps = dot(V, V) / 2 - mu_k / mag(R)
    e = math.sqrt(max(0.0, 1 + 2 * eps * h * h / mu_k ** 2))
    return h * h / mu_k / (1 + e), t


def main():
    rp_alt = float(sys.argv[sys.argv.index('--rp') + 1]) if '--rp' in sys.argv else 30000.0
    log = Log('tki')
    k = Kio('tki')
    sc = k.sc
    v = sc.active_vessel
    o = v.orbit
    mun = o.body
    kerbin = mun.orbit.body
    k.krpc.paused = True
    alt = o.semi_major_axis - mun.equatorial_radius
    hand, _ = planner('tki.js', {'alt': alt, 'rpAlt': rp_alt})
    log(f"hand (TM-17 min energy): v_a {hand['va']:.1f}, v_Mun {hand['vM']:.1f}, v∞ {hand['vinf']:.1f}, v_c {hand['vc']:.1f}, "
        f"v_hyp {hand['vhyp']:.1f}, Δv {hand['dv']:.1f} m/s, e {hand['e']:.4f}, θ∞ {hand['thInfDeg']:.2f}°, tof {hand['tof'] / 3600:.2f} h")
    mnrf, knrf = mun.non_rotating_reference_frame, kerbin.non_rotating_reference_frame
    p, vel = v.position(mnrf), v.velocity(mnrf)
    s = 1.0 if (p[0] * vel[2] - p[2] * vel[0]) > 0 else -1.0
    ang = lambda q: s * math.atan2(q[2], q[0])

    def mun_vel(t):
        a, b = mun.orbit.position_at(t - 1, knrf), mun.orbit.position_at(t + 1, knrf)
        return [(y - x) / 2 for x, y in zip(a, b)]

    # the Mun's circular orbit, analytically from one sample (fast; e = 0, i = 0 in KSP)
    t_ref = sc.ut
    p_ref, v_ref = list(mun.orbit.position_at(t_ref, knrf)), mun_vel(t_ref)
    Rm, Vm = mag(p_ref), mag(v_ref)
    e1, e2 = [x / Rm for x in p_ref], [x / Vm for x in v_ref]
    Wm = Vm / Rm

    def mun_state(t):
        th = Wm * (t - t_ref)
        c, sn = math.cos(th), math.sin(th)
        return [Rm * (c * a + sn * b) for a, b in zip(e1, e2)], [Vm * (-sn * a + c * b) for a, b in zip(e1, e2)]

    # the hand calculation's v∞ is the speed "at infinity"; the patch is at the SOI radius, where the speed must be v∞_hand:
    # v_SOI² = v∞² + 2μ/R_SOI (vis-viva), so the hyperbola's true v∞ is smaller (gap G7)
    R_soi0 = mun.sphere_of_influence
    vinf2 = hand['vinf'] ** 2 - 2 * mun.gravitational_parameter / R_soi0
    r_orb = o.semi_major_axis
    vhyp = math.sqrt(vinf2 + 2 * mun.gravitational_parameter / r_orb)
    dv_soi = vhyp - math.sqrt(mun.gravitational_parameter / r_orb)
    e_soi = 1 + r_orb * vinf2 / mun.gravitational_parameter
    log(f"SOI-corrected: v∞ {math.sqrt(vinf2):.1f} m/s (speed {hand['vinf']:.1f} at the SOI), Δv {dv_soi:.1f} m/s, "
        f"θ∞ {math.degrees(math.acos(-1 / e_soi)):.2f}°")
    hand['dv_hand'] = hand['dv']
    hand['dv'] = dv_soi
    hand['thInfDeg'] = math.degrees(math.acos(-1 / e_soi))
    th_inf = math.radians(hand['thInfDeg'])
    n = 2 * math.pi / o.period
    W = 2 * math.pi / mun.orbit.period
    burn_angle = lambda t: ang([-x for x in mun_vel(t)]) - th_inf
    ut = sc.ut
    t = ut + wrap(burn_angle(ut) - ang(p)) / (n - W)
    if t - ut < 400:
        t += 2 * math.pi / (n - W)
    for _ in range(8):
        err = wrap_pi(ang(o.position_at(t, mnrf)) - burn_angle(t))
        t -= err / (n - W)
    t_hand = t
    mu_m, mu_k = mun.gravitational_parameter, kerbin.gravitational_parameter
    R_soi = mun.sphere_of_influence
    Rk = kerbin.equatorial_radius

    def rp_for(tig):
        r0 = list(o.position_at(tig, mnrf))
        a, b = o.position_at(tig - 0.5, mnrf), o.position_at(tig + 0.5, mnrf)
        v0 = [y - x for x, y in zip(a, b)]
        v1 = add(v0, norm(v0), hand['dv'])
        rp, _ = kerbin_rp(r0, v1, tig, mu_m, mu_k, R_soi, mun_state)
        return None if rp is None else rp - Rk

    g0 = rp_for(t_hand)
    log(f'hand TIG UT {t_hand:.1f}: patched-conic Kerbin periapsis {g0 / 1e3 if g0 is not None else None:.1f} km')
    # scan ±25° of burn position for the target periapsis (the root nearest the hand TIG), then bisect
    step = math.radians(1.0) / n
    best = None
    prev = (t_hand, g0)
    for sgn in (1, -1):
        prev = (t_hand, g0)
        for i in range(1, 61):
            tt = t_hand + sgn * i * step
            gg = rp_for(tt)
            if gg is not None and prev[1] is not None and (gg - rp_alt) * (prev[1] - rp_alt) < 0:
                lo, hi = sorted([prev[0], tt])
                glo = rp_for(lo)
                for _ in range(40):
                    mid = (lo + hi) / 2
                    gm = rp_for(mid)
                    if (gm - rp_alt) * (glo - rp_alt) > 0:
                        lo, glo = mid, gm
                    else:
                        hi = mid
                cand = (lo + hi) / 2
                if best is None or abs(cand - t_hand) < abs(best - t_hand):
                    best = cand
                break
            prev = (tt, gg)
    if best is None:
        log('no TIG found for the target periapsis'); k.krpc.paused = False; return
    t = best
    log(f'solved TIG UT {t:.1f} ({(t - t_hand) * n * 180 / math.pi:+.2f}° of burn position from the hand value), '
        f'periapsis {rp_for(t) / 1e3:.2f} km')
    node = v.control.add_node(t, prograde=hand['dv'])
    nxt = node.orbit.next_orbit
    ksp_rp = nxt.periapsis_altitude if nxt is not None and nxt.body.name == 'Kerbin' else None
    log(f"KSP node check: next {nxt.body.name if nxt else None}, Kerbin periapsis {ksp_rp}")
    node.remove()
    F, isp = v.available_thrust, v.vacuum_specific_impulse
    tb = v.mass * isp * 9.80665 / F * (1 - math.exp(-hand['dv'] / (isp * 9.80665)))
    k.krpc.paused = False
    save(k, 'selftest-pre-tki', log)
    out = burn.execute(k, v, {'tig': t, 'prograde': hand['dv'], 'normal': 0, 'radial': 0, 'tb': tb}, log, None, settle_s=30)
    v.auto_pilot.engaged = False
    v.control.sas = True
    time.sleep(1)
    nxt = v.orbit.next_orbit
    meas = nxt.periapsis_altitude if nxt is not None and nxt.body.name == 'Kerbin' else None
    log(f"AFTER TKI: next {nxt.body.name if nxt else None}, Kerbin periapsis {meas}, mass {v.mass / 1e3:.3f} t, "
        f"SOI exit in {v.orbit.time_to_soi_change:.0f} s")
    save(k, 'selftest-tki', log)
    json.dump({'hand': hand, 'tig_hand': t_hand, 'tig': t, 'ksp_node_rp': ksp_rp, 'measured_rp': meas, 'burn': out,
               'mass': v.mass}, open(os.path.join(DATA, 'tki-result.json'), 'w'), indent=1)
    k.close()


if __name__ == '__main__':
    main()
