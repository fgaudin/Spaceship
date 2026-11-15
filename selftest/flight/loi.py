"""Mun orbit insertion (TM-13 LOI; TM-2 vis-viva, TM-10 burn time): warp into the Mun's SOI, then circularise at
periapsis with a retrograde PAD (Δv = v_c − v_p < 0), flown by burn.py. No staging allowed (Poodle only).

    .venv/bin/python selftest/flight/loi.py
"""
import json, math, os, time
from common import Kio, Log, DATA, planner, save, warp_to
import burn


def main():
    log = Log('loi')
    k = Kio('loi')
    sc = k.sc
    v = sc.active_vessel
    if v.orbit.body.name != 'Mun':
        t_soi = sc.ut + v.orbit.time_to_soi_change
        warp_to(k, t_soi + 60, log)
        time.sleep(2)
    o = v.orbit
    mun = o.body
    log(f'in {mun.name} SOI: periapsis {o.periapsis_altitude:.0f} m in {o.time_to_periapsis:.0f} s, e {o.eccentricity:.4f}, '
        f'i {math.degrees(o.inclination):.2f}°, v∞ {math.sqrt(max(0, -mun.gravitational_parameter / o.semi_major_axis)):.1f} m/s')
    save(k, 'selftest-mun-soi', log)
    k.krpc.paused = True
    tig = sc.ut + o.time_to_periapsis
    F, isp = v.available_thrust, v.vacuum_specific_impulse
    pad, _ = planner('pad.js', {'cmd': 'circ', 'r': o.periapsis, 'a': o.semi_major_axis, 'm': v.mass, 'F': F, 'isp': isp,
                                'mu': mun.gravitational_parameter})
    log(f"LOI PAD: v_p {pad['vNow']:.1f}, v_c {pad['vc']:.1f}, Δv {pad['dv']:.1f} m/s, tb {pad['tb']:.1f} s "
        f"(m {v.mass / 1e3:.3f} t, F {F / 1e3:.0f} kN, Isp {isp:.0f} s)")
    node = v.control.add_node(tig, prograde=pad['dv'])
    log(f'KSP node check: orbit after {node.orbit.apoapsis_altitude:.0f} x {node.orbit.periapsis_altitude:.0f} m')
    node.remove()
    k.krpc.paused = False
    res = burn.execute(k, v, {'tig': tig, 'prograde': pad['dv'], 'normal': 0, 'radial': 0, 'tb': pad['tb']}, log, None)
    v.auto_pilot.engaged = False
    v.control.sas = True
    o = v.orbit
    log(f'MUN ORBIT: apo {o.apoapsis_altitude:.0f} m, peri {o.periapsis_altitude:.0f} m, e {o.eccentricity:.5f}, '
        f'i {math.degrees(o.inclination):.2f}°, period {o.period:.0f} s, mass {v.mass / 1e3:.3f} t')
    save(k, 'selftest-loi', log)
    json.dump({'pad': pad, 'burn': res, 'apo': o.apoapsis_altitude, 'peri': o.periapsis_altitude, 'mass': v.mass,
               'inclination': o.inclination}, open(os.path.join(DATA, 'loi-result.json'), 'w'), indent=1)
    k.close()


if __name__ == '__main__':
    main()
