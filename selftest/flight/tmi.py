"""Trans-Mun injection: plan with planner/tmi.js (course: TM-2, TM-11, TM-13, TM-10), find the TIG from the phase angle,
check the encounter with a KSP maneuver node (check only, removed before the burn), fly the PAD with burn.py.

    .venv/bin/python selftest/flight/tmi.py [--peri 30000]
"""
import json, math, os, sys, time
from common import Kio, Log, Stager, DATA, planner, save
import burn

PROP = ('LiquidFuel', 'Oxidizer')
DENS = 5.0     # kg per unit, LF and Ox


def ang(p, s):
    return s * math.atan2(p[2], p[0])


def wrap(x):
    return x % (2 * math.pi)


def wrap_pi(x):
    y = wrap(x)
    return y - 2 * math.pi if y > math.pi else y


def island(part):
    """The parts an engine can draw from: its connected parts, not crossing a decoupler or a docking port (a stack
    with a payload that has engines of its own, like Mun LOR, puts several fuel islands in one decouple group)."""
    seen, todo = set(), [part]
    out = []
    while todo:
        p = todo.pop()
        if p._object_id in seen:
            continue
        seen.add(p._object_id)
        out.append(p)
        for q in [p.parent, *p.children]:
            if q is None or q._object_id in seen:
                continue
            if q.decoupler is not None or q.docking_port is not None:
                seen.add(q._object_id)
                out.append(q)            # the separation part goes with the stage below it; do not cross it
                continue
            todo.append(q)
    return out


def stage_list(v):
    """Remaining burn stages in order: [{prop, dry, F, isp, group}]. Stages with active engines first (the stage that
    is lit), then the others by decouple group. Propellant and dry mass come from the engines' fuel islands."""
    out = []
    engines = list(v.parts.engines)
    active = [e for e in engines if e.active]
    groups = sorted({e.part.decouple_stage for e in active}, reverse=True)
    if not groups:
        groups = sorted({e.part.decouple_stage for e in engines}, reverse=True)
    for g in groups:
        engs = [e for e in (active or engines) if e.part.decouple_stage == g]
        ids, parts = set(), []
        for e in engs:
            for p in island(e.part):
                if p._object_id not in ids:
                    ids.add(p._object_id)
                    parts.append(p)
        prop = sum(p.resources.amount(r) for p in parts for r in PROP) * DENS
        dry = sum(p.dry_mass for p in parts)
        F = sum(e.max_vacuum_thrust for e in engs)
        isp = F / sum(e.max_vacuum_thrust / e.vacuum_specific_impulse for e in engs)
        out.append({'group': g, 'prop': prop, 'dry': dry, 'F': F, 'isp': isp})
    return out


def main():
    peri_target = float(sys.argv[sys.argv.index('--peri') + 1]) if '--peri' in sys.argv else 30000.0
    log = Log('tmi')
    k = Kio('tmi')
    sc = k.sc
    v = sc.active_vessel
    kerbin = v.orbit.body
    mun = sc.bodies['Mun']
    nrf = kerbin.non_rotating_reference_frame
    o = v.orbit
    park = o.semi_major_axis - kerbin.equatorial_radius
    stages = stage_list(v)
    log(f'parking orbit a-R {park:.0f} m (apo {o.apoapsis_altitude:.0f}, peri {o.periapsis_altitude:.0f}), mass {v.mass / 1e3:.3f} t')
    for s in stages:
        log(f"  stage group {s['group']}: prop {s['prop'] / 1e3:.3f} t, dry {s['dry'] / 1e3:.3f} t, F {s['F'] / 1e3:.0f} kN, Isp {s['isp']:.0f} s")
    t0 = time.time()
    res, _ = planner('tmi.js', {'parkAlt': park, 'periAlt': peri_target, 'm': v.mass, 'stages': stages})
    log(f'planner ({time.time() - t0:.0f} s): hand Hohmann Δv {res["hand"]["dv"]:.1f} m/s, Mun lead {res["hand"]["munLeadDeg"]:.2f}°, '
        f'tof {res["hand"]["tof"] / 3600:.2f} h')
    b = res['best']
    log(f"patched conics: Δv {b['dv']:.2f} m/s, burn angle {b['burnAngle']:.2f}° (Mun lead {-b['burnAngle']:.2f}°), "
        f"SOI at +{b['tSOI'] / 3600:.2f} h, Mun periapsis {b['periAlt']:.0f} m, v∞ {b['vinf']:.1f} m/s; "
        f"sensitivity {b['dPeri_dDv'] / 1e3:.1f} km per m/s, {b['dPeri_dDeg'] / 1e3:.1f} km per degree; burn {res['burn']}")

    # angle convention: the vessel's angle increases with time
    p, vel = v.position(nrf), v.velocity(nrf)
    s = 1.0 if (p[0] * vel[2] - p[2] * vel[0]) > 0 else -1.0
    phi_req = math.radians(b['burnAngle'])
    n_v = 2 * math.pi / o.period
    n_m = 2 * math.pi / mun.orbit.period
    ut = sc.ut
    phi_now = wrap_pi(ang(p, s) - ang(mun.position(nrf), s))
    wait = wrap(phi_req - phi_now) / (n_v - n_m)
    if wait < 240:
        wait += 2 * math.pi / (n_v - n_m)
    tig = ut + wait
    # refine on the predicted positions (Newton on the phase error)
    for _ in range(6):
        err = wrap_pi(ang(o.position_at(tig, nrf), s) - ang(mun.orbit.position_at(tig, nrf), s) - phi_req)
        tig -= err / (n_v - n_m)
    log(f'phase now {math.degrees(phi_now):.2f}°, TIG in {tig - ut:.0f} s (UT {tig:.1f}); residual {math.degrees(err):.4f}°')

    # check with KSP's own prediction (a maneuver node), then remove it
    node = v.control.add_node(tig, prograde=b['dv'])
    nxt = node.orbit.next_orbit
    ksp_peri = nxt.periapsis_altitude if nxt is not None and nxt.body.name == 'Mun' else None
    log(f"KSP node check: next orbit {nxt.body.name if nxt else None}, Mun periapsis {ksp_peri}")
    node.remove()

    bt = res['burn']['tb']
    save(k, 'selftest-pre-tmi', log)
    stager = Stager(k, v, log)
    out = burn.execute(k, v, {'tig': tig, 'prograde': b['dv'], 'normal': 0, 'radial': 0, 'tb': bt}, log, stager)
    v.auto_pilot.engaged = False
    v.control.sas = True
    nxt = v.orbit.next_orbit
    meas = nxt.periapsis_altitude if nxt is not None and nxt.body.name == 'Mun' else None
    log(f"AFTER TMI: Kerbin orbit apo {v.orbit.apoapsis_altitude / 1e3:.0f} km, next {nxt.body.name if nxt else None}, "
        f"Mun periapsis {meas}, SOI change at UT {v.orbit.time_to_soi_change + sc.ut if nxt else None}, mass {v.mass / 1e3:.3f} t")
    save(k, 'selftest-tmi', log)
    json.dump({'plan': res, 'tig': tig, 'ksp_node_peri': ksp_peri, 'measured_peri': meas, 'burn': out, 'mass': v.mass,
               'stage': v.control.current_stage}, open(os.path.join(DATA, 'tmi-result.json'), 'w'), indent=1)
    k.close()


if __name__ == '__main__':
    main()
