"""DOI, powered descent and landing on the Mun (TM-15/16 structure; law in planner/landing.js, gap G5).

1. DOI (TM-15 `doi`): retrograde burn in the circular orbit, periapsis at hp, PDI half an orbit later.
2. Braking from periapsis at a fixed throttle: thrust split between a vertical channel that commands
   v_r = −(h − h_HG)/t_go (t_go = v_h / a_h) and the rest against the horizontal surface velocity.
3. Approach: vertical, sink rate 1 + h/k, horizontal residual nulled with ≤ 15° of tilt, throttle 0–100 %.
Heights are radar heights (above terrain, lowest point of the vessel). Frame: hybrid (Mun-fixed position, axes up/north/east).

    .venv/bin/python selftest/flight/descent.py [--hp 12000] [--throttle 0.3] [--hg 800] [--sink 10]
"""
import json, math, os, sys, time
from common import Kio, Log, DATA, planner, save, warp_to, norm, dot
from kio import _unwrap
import burn


def arg(name, default):
    return float(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def main():
    hp, thr, hHG, sinkK = arg('--hp', 12000.0), arg('--throttle', 0.3), arg('--hg', 800.0), arg('--sink', 10.0)
    log = Log('descent')
    k = Kio('descent')
    sc = k.sc
    v = sc.active_vessel
    mun = v.orbit.body
    assert mun.name == 'Mun', mun.name
    ctl, ap = v.control, v.auto_pilot
    o = v.orbit
    hc = o.semi_major_axis - mun.equatorial_radius
    mu = mun.gravitational_parameter
    k.krpc.paused = True
    # DOI with the course's formula; the landing simulated with our law
    plan, _ = planner('descent.js', {'hc': hc, 'hp': hp, 'm0': v.mass, 'prop': 1, 'F': v.available_thrust or 250000,
                                    'isp': v.vacuum_specific_impulse or 350, 'hHG': hHG, 'throttles': [thr]})
    doi = plan['doi']
    log(f"orbit {o.apoapsis_altitude:.0f} x {o.periapsis_altitude:.0f} m; DOI to {hp:.0f} m: Δv {doi['dv']:.2f} m/s "
        f"(v_c {doi['vc']:.1f} → v_a {doi['va']:.1f}), v at PDI {doi['vp']:.1f} m/s, coast {doi['coast']:.0f} s")
    F = v.available_thrust or 250000.0
    isp = v.vacuum_specific_impulse or 350.0
    tb = v.mass * isp * 9.80665 / F * (1 - math.exp(-doi['dv'] / (isp * 9.80665)))
    tig = sc.ut + 90
    node = v.control.add_node(tig, prograde=-doi['dv'])
    log(f"KSP node check: periapsis after DOI {node.orbit.periapsis_altitude:.0f} m")
    node.remove()
    k.krpc.paused = False
    save(k, 'selftest-pre-doi', log)
    burn.execute(k, v, {'tig': tig, 'prograde': -doi['dv'], 'normal': 0, 'radial': 0, 'tb': tb}, log, None, settle_s=30)
    o = v.orbit
    log(f'after DOI: {o.apoapsis_altitude:.0f} x {o.periapsis_altitude:.0f} m, periapsis in {o.time_to_periapsis:.0f} s')
    save(k, 'selftest-doi', log)

    # hybrid frame: position fixed to the Mun's surface, axes up/north/east at the vessel
    conn = k.conn
    hyb = conn.space_center.ReferenceFrame.create_hybrid(position=_unwrap(mun.reference_frame),
                                                         rotation=_unwrap(v.surface_reference_frame))
    k.rec.log('SpaceCenter.ReferenceFrame.create_hybrid', 'call', None, ('ReferenceFrame', 'ReferenceFrame'))
    flight = v.flight(mun.reference_frame)
    ut = k.stream(sc, 'ut')
    radar = k.stream(flight, 'surface_altitude')
    alt = k.stream(flight, 'mean_altitude')
    vel = conn.add_stream(_unwrap(v).velocity, hyb)
    k.rec.log('SpaceCenter.Vessel.velocity', 'call', vel(), ('ReferenceFrame(hybrid)',), stream=True)
    mass = k.stream(v, 'mass')
    sit = k.stream(v, 'situation')

    t_pdi = sc.ut + v.orbit.time_to_periapsis
    warp_to(k, t_pdi - 90, log)
    ap.reference_frame = hyb
    ap.target_roll = float('nan')
    vv = vel()
    ap.target_direction = tuple(norm([0.0, -vv[1], -vv[2]]))      # retrograde, horizontal
    ap.engaged = True
    ctl.sas = False
    while ut() < t_pdi:
        if radar() < 2500:
            log(f'terrain: radar {radar():.0f} m before PDI, starting early'); break
        time.sleep(0.05)
    bb = v.bounding_box(v.surface_reference_frame)
    low = min(bb[0][0], bb[1][0])
    log(f'PDI: h {alt():.0f} m (radar {radar():.0f} m), v {math.hypot(*vel()):.1f} m/s, mass {mass() / 1e3:.3f} t, '
        f'error {ap.error:.1f}°, lowest point {low:.2f} m')
    save(k, 'selftest-pdi', log)
    m_pdi = mass()
    m_dry = v.dry_mass
    phase, t0, last_row, gear = 'brake', ut(), 0, False
    dv_used = 0.0
    last = ut()
    while True:
        now = ut()
        dt = now - last; last = now
        vu, vn, ve = vel()
        vh = math.hypot(vn, ve)
        h = radar() + low
        r = mun.equatorial_radius + alt()
        g = mu / (r * r)
        Fav = v.available_thrust
        m = mass()
        if not gear and h < 3000:
            ctl.gear = True; gear = True
            time.sleep(0.1)
            bb = v.bounding_box(v.surface_reference_frame); low = min(bb[0][0], bb[1][0])
            log(f'gear down at {h:.0f} m, lowest point {low:.2f} m')
        hdir = [0.0, -vn / vh, -ve / vh] if vh > 1e-3 else [0.0, 0.0, 0.0]
        if phase == 'brake':
            aT = Fav * thr / m
            tgo = max(3.0, vh / (0.9 * aT))
            vr_cmd = -(h - hHG) / tgo
            av = g - vh * vh / r + 0.5 * (vr_cmd - vu)
            av = max(-0.9 * aT, min(0.9 * aT, av))
            ah = math.sqrt(max(0.0, aT * aT - av * av))
            d = [av + 0.0, ah * hdir[1], ah * hdir[2]]
            ap.target_direction = tuple(norm(d))
            # throttle only once pointing (the vertical channel still steers)
            ctl.throttle = thr if ap.error < 10 else 0.0
            dv_used += (thr * Fav / m if ap.error < 10 else 0) * dt
            if vh <= 1.0:
                phase = 'approach'
                log(f't {now - t0:.1f} s: HIGH GATE h {h:.0f} m, v_r {vu:.1f}, v_h {vh:.2f}, Δv so far {dv_used:.0f} m/s, '
                    f'mass {m / 1e3:.3f} t')
        else:
            cmd = -(1 + max(0.0, h) / sinkK)
            a_need = g + 0.8 * (cmd - vu)
            tan15 = math.tan(math.radians(15))
            a_h = min(tan15 * max(a_need, 0.1), 0.5 * vh)
            d = [max(a_need, 0.05), a_h * hdir[1], a_h * hdir[2]]
            ap.target_direction = tuple(norm(d))
            a_tot = math.sqrt(dot(d, d)) if a_need > 0 else 0.0
            th = max(0.0, min(1.0, a_tot * m / Fav)) if Fav > 0 else 0.0
            ctl.throttle = th
            dv_used += th * Fav / m * dt
        if now - last_row >= 0.25:
            last_row = now
            log.row(t=now - t0, h=h, alt=alt(), vr=vu, vh=vh, mass=m, thr=ctl.throttle, phase=phase, err=ap.error)
        s = sit()
        if s.name in ('landed', 'splashed') or (h < 0.3 and abs(vu) < 2.5):
            ctl.throttle = 0.0
            log(f'TOUCHDOWN t {now - t0:.1f} s: v_r {vu:.2f} m/s, v_h {vh:.2f} m/s, Δv {dv_used:.0f} m/s, '
                f'mass {m / 1e3:.3f} t (propellant used {(m_pdi - m):.0f} kg), situation {s.name}')
            break
        if m < m_dry + 30:                      # was a Kerbal X constant (7400 kg); now this vessel's dry mass + 30 kg
            log('propellant low: abort to orbit not implemented, cutting'); ctl.throttle = 0; break
        time.sleep(0.02)
    ap.engaged = False
    ctl.sas = True
    time.sleep(5)
    log(f'final situation {v.situation.name}, lat {flight.latitude:.4f}, lon {flight.longitude:.4f}, '
        f'biome {v.biome}, mass {v.mass / 1e3:.3f} t')
    save(k, 'selftest-landed', log)
    json.dump({'plan': plan, 'dv_descent': dv_used, 'mass': v.mass, 'lat': flight.latitude, 'lon': flight.longitude,
               'situation': v.situation.name}, open(os.path.join(DATA, 'descent-result.json'), 'w'), indent=1)
    k.close()


if __name__ == '__main__':
    main()
