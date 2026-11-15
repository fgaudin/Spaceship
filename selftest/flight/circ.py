"""Circularise at the next apoapsis (or periapsis with --peri) around the current body: TM-9/10 PAD, flown by burn.py.

    .venv/bin/python selftest/flight/circ.py [--peri] [--save NAME]
"""
import math, sys
from common import Kio, Log, planner, save
import burn


def main():
    at_peri = '--peri' in sys.argv
    name = sys.argv[sys.argv.index('--save') + 1] if '--save' in sys.argv else 'selftest-circ'
    log = Log('circ')
    k = Kio('circ')
    sc = k.sc
    v = sc.active_vessel
    k.krpc.paused = True
    o = v.orbit
    body = o.body
    tig = sc.ut + (o.time_to_periapsis if at_peri else o.time_to_apoapsis)
    r = o.periapsis if at_peri else o.apoapsis
    F, isp = v.available_thrust, v.vacuum_specific_impulse
    pad, _ = planner('pad.js', {'cmd': 'circ', 'r': r, 'a': o.semi_major_axis, 'm': v.mass, 'F': F, 'isp': isp,
                                'mu': body.gravitational_parameter})
    log(f"{body.name} orbit {o.apoapsis_altitude:.0f} x {o.periapsis_altitude:.0f} m; circularise at "
        f"{'periapsis' if at_peri else 'apoapsis'}: v {pad['vNow']:.1f} → {pad['vc']:.1f}, Δv {pad['dv']:.2f} m/s, tb {pad['tb']:.1f} s")
    k.krpc.paused = False
    burn.execute(k, v, {'tig': tig, 'prograde': pad['dv'], 'normal': 0, 'radial': 0, 'tb': pad['tb']}, log, None, settle_s=30)
    v.auto_pilot.engaged = False
    v.control.sas = True
    o = v.orbit
    log(f'ORBIT {o.apoapsis_altitude:.0f} x {o.periapsis_altitude:.0f} m, i {math.degrees(o.inclination):.2f}°, mass {v.mass / 1e3:.3f} t')
    save(k, name, log)
    k.close()


if __name__ == '__main__':
    main()
