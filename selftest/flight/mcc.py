"""Midcourse correction toward the Mun (TM-14 with TM-13 patched conics, planner/mcc.js).

The game is paused while planning. The measured Kerbin orbit is reduced to (perigee radius, perigee speed, perigee angle
from the Mun), the course model solves an along-track Δv at the chosen time, KSP's node prediction is read as a check
(node removed), and burn.py flies it.

    .venv/bin/python selftest/flight/mcc.py [--target 30000] [--in 150]     (--in: seconds from now to the burn)
"""
import json, math, os, sys, time
from common import Kio, Log, Stager, DATA, planner, save
import burn


def arg(name, default):
    return float(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def perigee_fix(sc, v):
    o = v.orbit
    kb, mun = o.body, sc.bodies['Mun']
    nrf = kb.non_rotating_reference_frame
    ut = sc.ut
    tp = ut + o.time_to_periapsis - o.period if o.time_to_periapsis > o.period / 2 else ut + o.time_to_periapsis
    # refine: minimum radius near tp
    rad = lambda t: math.sqrt(sum(x * x for x in o.position_at(t, nrf)))
    lo, hi = tp - 300, tp + 300
    for _ in range(60):
        m1, m2 = lo + (hi - lo) / 3, hi - (hi - lo) / 3
        if rad(m1) < rad(m2):
            hi = m2
        else:
            lo = m1
    tp = (lo + hi) / 2
    rp = rad(tp)
    vp = math.sqrt(kb.gravitational_parameter * (2 / rp - 1 / o.semi_major_axis))
    p, vel = v.position(nrf), v.velocity(nrf)
    s = 1 if p[0] * vel[2] - p[2] * vel[0] > 0 else -1
    ang = lambda q: s * math.atan2(q[2], q[0])
    d = math.degrees(ang(o.position_at(tp, nrf)) - ang(mun.orbit.position_at(tp, nrf)))
    return {'ut': ut, 'tp': tp, 'rp': rp, 'vp': vp, 'angleDeg': (d + 180) % 360 - 180}


def main():
    target = arg('--target', 30000.0)
    lead = arg('--in', 150.0)
    log = Log('mcc')
    k = Kio('mcc')
    sc = k.sc
    v = sc.active_vessel
    k.krpc.paused = True
    fix = perigee_fix(sc, v)
    t_burn = fix['ut'] + lead
    q = dict(fix, tMcc=t_burn - fix['tp'], target=target, range=40)
    res, _ = planner('mcc.js', q)
    log(f"fix: perigee {fix['rp'] - 600000:.0f} m alt, v_p {fix['vp']:.2f} m/s, angle {fix['angleDeg']:.3f}°; course model "
        f"Mun periapsis now {res['nominal']['periAlt']}; MCC {res['mcc']} m/s at UT {t_burn:.1f} -> {res.get('after')}")
    if res['mcc'] is None:
        log('no solution'); k.krpc.paused = False; return
    dv = res['mcc']
    node = v.control.add_node(t_burn, prograde=dv)
    nxt = node.orbit.next_orbit
    ksp = nxt.periapsis_altitude if nxt is not None and nxt.body.name == 'Mun' else None
    log(f'KSP node check: Mun periapsis {ksp}')
    node.remove()
    F, isp = v.available_thrust or 250000.0, v.vacuum_specific_impulse or 350.0
    tb = v.mass * isp * 9.80665 / F * (1 - math.exp(-abs(dv) / (isp * 9.80665)))
    k.krpc.paused = False
    out = burn.execute(k, v, {'tig': t_burn, 'prograde': dv, 'normal': 0, 'radial': 0, 'tb': tb}, log, Stager(k, v, log),
                       settle_s=30)
    v.auto_pilot.engaged = False
    v.control.sas = True
    time.sleep(1)
    nxt = v.orbit.next_orbit
    meas = nxt.periapsis_altitude if nxt is not None and nxt.body.name == 'Mun' else None
    log(f"AFTER MCC: next {nxt.body.name if nxt else None}, Mun periapsis {meas}, "
        f"SOI in {v.orbit.time_to_soi_change:.0f} s, mass {v.mass / 1e3:.3f} t")
    save(k, 'selftest-mcc', log)
    with open(os.path.join(DATA, 'mcc-results.jsonl'), 'a') as f:
        f.write(json.dumps({'fix': fix, 'plan': res, 'ksp_node_peri': ksp, 'measured_peri': meas, 'burn': out}) + '\n')
    k.close()


if __name__ == '__main__':
    main()
