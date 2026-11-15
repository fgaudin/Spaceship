"""Ascent from the Mun to a low circular orbit (TM-7 shape in vacuum; TM-9/10 circularisation PAD).

Vertical rise to clear the ground, then the elevation falls linearly with the horizontal speed,
e = 90° (1 − v_h / (0.85 v_c)), floored at 5° (and at 30° while the radar height is below 1.5 km and still climbing slowly),
cutoff when the apoapsis reaches the target, coast, circularise at apoapsis with burn.py.

    .venv/bin/python selftest/flight/mun_ascent.py [--target 20000]
"""
import json, math, os, sys, time
from common import Kio, Log, DATA, planner, save
import burn


def main():
    target = float(sys.argv[sys.argv.index('--target') + 1]) if '--target' in sys.argv else 20000.0
    log = Log('mun-ascent')
    k = Kio('mun-ascent')
    sc = k.sc
    v = sc.active_vessel
    mun = v.orbit.body
    ctl, ap = v.control, v.auto_pilot
    mu, R = mun.gravitational_parameter, mun.equatorial_radius
    vc = math.sqrt(mu / (R + target))
    fl = v.flight(mun.reference_frame)
    radar, vs, hs, alt = (k.stream(fl, a) for a in ('surface_altitude', 'vertical_speed', 'horizontal_speed', 'mean_altitude'))
    apo = k.stream(v.orbit, 'apoapsis_altitude')
    m0 = v.mass
    save(k, 'selftest-mun-surface', log)
    ap.reference_frame = v.surface_reference_frame
    ap.target_pitch_and_heading(90, 90)
    ap.target_roll = float('nan')
    ap.engaged = True
    ctl.sas = False
    ctl.throttle = 1.0
    t0 = sc.ut
    log(f'LIFTOFF from the Mun, mass {m0 / 1e3:.3f} t, target apoapsis {target:.0f} m (v_c {vc:.1f} m/s)')
    gear_up = False
    while True:
        h, vh, vv = radar(), hs(), vs()
        if not gear_up and h > 100:
            ctl.gear = False; gear_up = True
        if h < 150:
            e = 90.0
        else:
            e = max(5.0, 90.0 * (1 - vh / (0.85 * vc)))
            if h < 1500 and vv < 40:
                e = max(e, 30.0)
        ap.target_pitch_and_heading(e, 90)
        if apo() >= target:
            ctl.throttle = 0.0
            log(f't {sc.ut - t0:.1f} s: CUTOFF apoapsis {apo():.0f} m, alt {alt():.0f} m (radar {h:.0f}), v_h {vh:.1f}, v_v {vv:.1f}')
            break
        time.sleep(0.02)
    o = v.orbit
    tig = sc.ut + o.time_to_apoapsis
    F, isp = v.available_thrust, v.vacuum_specific_impulse
    pad, _ = planner('pad.js', {'cmd': 'circ', 'r': o.apoapsis, 'a': o.semi_major_axis, 'm': v.mass, 'F': F, 'isp': isp, 'mu': mu})
    log(f"circularisation PAD: v_apo {pad['vNow']:.1f}, v_c {pad['vc']:.1f}, Δv {pad['dv']:.1f} m/s, tb {pad['tb']:.1f} s")
    burn.execute(k, v, {'tig': tig, 'prograde': pad['dv'], 'normal': 0, 'radial': 0, 'tb': pad['tb']}, log, None, settle_s=20)
    ap.engaged = False
    ctl.sas = True
    o = v.orbit
    log(f'MUN ORBIT: {o.apoapsis_altitude:.0f} x {o.periapsis_altitude:.0f} m, i {math.degrees(o.inclination):.2f}°, '
        f'mass {v.mass / 1e3:.3f} t, ascent Δv {350 * 9.80665 * math.log(m0 / v.mass):.0f} m/s (from mass, Isp 350)')
    save(k, 'selftest-mun-orbit2', log)
    json.dump({'apo': o.apoapsis_altitude, 'peri': o.periapsis_altitude, 'mass': v.mass, 'm0': m0},
              open(os.path.join(DATA, 'mun-ascent-result.json'), 'w'), indent=1)
    k.close()


if __name__ == '__main__':
    main()
