"""Fly a PAD as a finite burn, the way Moonshot's executeBurns does (TM-10):
attitude held fixed in inertial space along the planned Δv at TIG, constant thrust, burn centred on TIG,
cut off when the accumulated Δv (∫ F/m dt) reaches the planned |Δv|. The last half second is throttled down
so the cutoff lands within a few cm/s (an execution detail; the course assumes an instant cutoff).

pad = { 'tig': UT of the impulse, 'prograde': m/s, 'normal': m/s, 'radial': m/s, 'tb': s (planned burn time) }
Frame at TIG: prograde along v, normal along r × v (orbit normal), radial completes the triad (outward).
"""
import math, time
from common import norm, cross, dot, warp_to


def frame_at(v, ut, frame):
    o = v.orbit
    p0 = o.position_at(ut - 0.5, frame)
    p1 = o.position_at(ut + 0.5, frame)
    r = list(o.position_at(ut, frame))
    vel = [b - a for a, b in zip(p0, p1)]
    if math.sqrt(dot(vel, vel)) < 50:
        # near standstill (top of a vertical climb, G6): prograde undefined; use the local horizontal along the
        # horizontal part of the motion, or east-ish (perpendicular to r and the frame's y axis = rotation axis)
        up = norm(r)
        hor = [x - dot(vel, up) * u for x, u in zip(vel, up)]
        if math.sqrt(dot(hor, hor)) < 1:
            hor = cross([0.0, 1.0, 0.0], up)
        vel = norm(hor)
    pro = norm(vel)
    nrm = norm(cross(r, vel))
    rad = norm(cross(pro, nrm))
    if dot(rad, r) < 0:
        rad = [-x for x in rad]
    return pro, nrm, rad, r, vel


def execute(k, v, pad, log, stager=None, settle_s=40, max_err_deg=1.0):
    sc = k.sc
    body = v.orbit.body
    nrf = body.non_rotating_reference_frame
    pro, nrm, rad, r, vel = frame_at(v, pad['tig'], nrf)
    dvv = [pad['prograde'] * a + pad['normal'] * b + pad['radial'] * c for a, b, c in zip(pro, nrm, rad)]
    dvmag = math.sqrt(dot(dvv, dvv))
    u = norm(dvv)
    tb = pad['tb']
    t_start = pad['tig'] - tb / 2
    log(f"PAD: TIG UT {pad['tig']:.1f}, Δv {dvmag:.2f} m/s (pro {pad['prograde']:.2f}, nrm {pad['normal']:.2f}, "
        f"rad {pad['radial']:.2f}), burn {tb:.1f} s, start UT {t_start:.1f}")
    ap = v.auto_pilot
    ap.reference_frame = nrf
    ap.target_direction = tuple(u)
    ap.target_roll = float('nan')
    ap.engaged = True
    if t_start - sc.ut > settle_s + 5:
        warp_to(k, t_start - settle_s, log)
    # settle the attitude
    while sc.ut < t_start - 1:
        time.sleep(0.2)
    err = ap.error
    log(f'attitude error at ignition {err:.2f}°')
    while sc.ut < t_start:
        time.sleep(0.02)
    ctl = v.control
    done, last = 0.0, sc.ut
    ctl.throttle = 1.0
    t0 = sc.ut
    mass = k.stream(v, 'mass')
    thrust = k.stream(v, 'thrust')
    ut = k.stream(sc, 'ut')
    thr_prev = 1.0
    while done < dvmag - 0.02:
        now = ut()
        dt = now - last
        last = now
        # Streams can be stale for a few frames after staging (the dropped engine's thrust on the new, lighter mass:
        # +19 m/s counted but not flown on TMI). Read thrust and available thrust directly and cap one by the other.
        avail = v.available_thrust
        F = min(v.thrust, avail * thr_prev * 1.02 + 1.0)
        m = v.mass
        acc = F / m
        done += acc * dt
        rem = dvmag - done
        full = avail / m
        if full > 0:
            thr_prev = max(0.02, min(1.0, rem / (full * 0.5))) if rem < full * 0.5 else 1.0
            ctl.throttle = thr_prev
        if stager is not None:
            stager.check(now)
        if now - t0 > 3 * tb + 30:
            log('burn timeout')
            break
        time.sleep(0.01)
    ctl.throttle = 0.0
    mass.remove(); thrust.remove(); ut.remove()
    o = v.orbit
    log(f'cutoff: Δv done {done:.2f} m/s in {sc.ut - t0:.1f} s (planned {tb:.1f} s); '
        f'orbit apo {o.apoapsis_altitude / 1e3:.2f} km peri {o.periapsis_altitude / 1e3:.2f} km e {o.eccentricity:.5f}')
    return {'dv_done': done, 'burn_s': sc.ut - t0, 'att_err': err}
