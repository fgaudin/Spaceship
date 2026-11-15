"""Ascent to a circular parking orbit, flying the program in selftest/data/ascent-plan.json (planner/ascent.js).

TM-6/7 guidance: vertical rise, pitch kick ramped over 4 s, gravity turn along the air-relative velocity, cutoff when the
apoapsis reaches the target; while still in the atmosphere the apoapsis is topped up (drag lowers it). Then TM-9/10:
circularisation PAD at apoapsis (vis-viva Δv, burn time from the rocket equation, centred), flown by burn.py.

    .venv/bin/python selftest/flight/ascent.py [--no-launch]
"""
import json, math, os, sys, time
from common import Kio, Log, Stager, DATA, planner, save
import burn

ATM_TOP = 70000


def main():
    plan = json.load(open(os.path.join(DATA, 'ascent-plan.json')))
    prog = plan['prog']
    target = prog['targetAlt']
    log = Log('ascent')
    k = Kio('ascent')
    sc = k.sc
    v = sc.active_vessel
    body = v.orbit.body
    log(f"program: kick at {prog['kickT']} s by {prog['kickA']}°, cutoff at apoapsis {target / 1e3:.0f} km; "
        f"planned Δv left {plan['result']['dvLeft']:.0f} m/s")
    surf = v.flight(body.reference_frame)
    alt = k.stream(surf, 'mean_altitude')
    vs = k.stream(surf, 'vertical_speed')
    hs = k.stream(surf, 'horizontal_speed')
    q = k.stream(surf, 'dynamic_pressure')
    spd = k.stream(surf, 'speed')
    ut = k.stream(sc, 'ut')
    apo = k.stream(v.orbit, 'apoapsis_altitude')
    peri = k.stream(v.orbit, 'periapsis_altitude')
    mass = k.stream(v, 'mass')
    thrust = k.stream(v, 'thrust')
    drag = k.stream(surf, 'drag')       # body frame: the surface-velocity frame is singular at rest
    ap = v.auto_pilot
    ctl = v.control
    stager = Stager(k, v, log)

    save(k, 'selftest-pad', log)
    ap.reference_frame = v.surface_reference_frame
    ap.target_pitch_and_heading(90, 90)
    ap.target_roll = float('nan')
    ap.engaged = True
    ctl.sas = False
    ctl.throttle = 1.0
    time.sleep(1.0)
    t_launch = ut()
    stager.stage(t_launch, 'ignition + clamps')
    log('LIFTOFF')
    mode = 'vertical'
    kick = prog['kickA']
    last_row = 0
    max_q = (0, 0, 0)
    cut_ut = None
    while True:
        now = ut()
        t = now - t_launch
        h = alt()
        gam = math.degrees(math.atan2(vs(), max(hs(), 1e-3)))     # air-relative flight-path angle
        if mode == 'vertical' and t >= prog['kickT']:
            mode = 'kick'
            log(f't {t:.1f} s: pitch kick, h {h:.0f} m, v {spd():.1f} m/s')
        if mode == 'vertical':
            pitch = 90.0
        elif mode == 'kick':
            pitch = 90 - kick * min(1, (t - prog['kickT']) / 4)
            if t >= prog['kickT'] + 4 and gam <= 90 - kick:
                mode = 'turn'
                log(f't {t:.1f} s: gravity turn, h {h:.0f} m, γ {gam:.1f}°')
        else:
            pitch = min(90 - kick, gam)
        if mode != 'coast':
            ap.target_pitch_and_heading(pitch, 90)
        qq = q()
        if qq > max_q[0]:
            max_q = (qq, t, h)
        stager.check(now)
        if mode in ('kick', 'turn') and apo() >= target:
            ctl.throttle = 0.0
            cut_ut = now
            mode = 'coast'
            log(f't {t:.1f} s: CUTOFF apoapsis {apo():.0f} m, h {h:.0f} m, v {spd():.1f} m/s, mass {mass() / 1e3:.2f} t')
        if mode == 'coast':
            # hold surface prograde through the rest of the atmosphere; top up the apoapsis against drag
            ap.target_pitch_and_heading(gam, 90)
            a = apo()
            ctl.throttle = 0.0 if a >= target else min(1.0, max(0.05, (target - a) / 2000))
            if h > ATM_TOP:
                ctl.throttle = 0.0
                log(f't {t:.1f} s: out of the atmosphere, apoapsis {apo():.0f} m, periapsis {peri():.0f} m')
                break
        if now - last_row >= 0.5:
            last_row = now
            d = drag()
            log.row(t=t, h=h, v=spd(), vs=vs(), hs=hs(), gamma=gam, pitch=pitch if mode != 'coast' else gam,
                    q=qq, drag=math.sqrt(sum(x * x for x in d)), mass=mass(), thrust=thrust(), apo=apo(), peri=peri(),
                    stage=ctl.current_stage, mode=mode)
        if h < 50 and t > 10 and vs() < -5:
            log('FALLING: abort script'); ctl.throttle = 0; return
        time.sleep(0.02)
    log(f'max Q {max_q[0] / 1e3:.1f} kPa at t {max_q[1]:.1f} s, h {max_q[2]:.0f} m')
    save(k, 'selftest-coast', log)

    # circularisation PAD at apoapsis (TM-9/10)
    o = v.orbit
    tig = sc.ut + o.time_to_apoapsis
    r_apo = o.apoapsis
    isp = v.vacuum_specific_impulse
    F = v.available_thrust
    pad, _ = planner('pad.js', {'cmd': 'circ', 'r': r_apo, 'a': o.semi_major_axis, 'm': v.mass, 'F': F, 'isp': isp})
    log(f"circularisation PAD: v_apo {pad['vNow']:.1f}, v_c {pad['vc']:.1f}, Δv {pad['dv']:.1f} m/s, tb {pad['tb']:.1f} s "
        f"(m {v.mass / 1e3:.2f} t, F {F / 1e3:.0f} kN, Isp {isp:.0f} s)")
    res = burn.execute(k, v, {'tig': tig, 'prograde': pad['dv'], 'normal': 0, 'radial': 0, 'tb': pad['tb']}, log, stager)
    o = v.orbit
    log(f'PARKING ORBIT: apo {o.apoapsis_altitude:.0f} m, peri {o.periapsis_altitude:.0f} m, e {o.eccentricity:.5f}, '
        f'i {math.degrees(o.inclination):.3f}°, mass {v.mass / 1e3:.3f} t, stage {ctl.current_stage}')
    ap.engaged = False
    ctl.sas = True
    save(k, 'selftest-lko', log)
    json.dump({'pad': pad, 'burn': res, 'apo': o.apoapsis_altitude, 'peri': o.periapsis_altitude, 'mass': v.mass,
               'max_q': max_q, 'cut_ut': cut_ut, 't_launch': t_launch},
              open(os.path.join(DATA, 'ascent-result.json'), 'w'), indent=1)
    k.close()


if __name__ == '__main__':
    main()
