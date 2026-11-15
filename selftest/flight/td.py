"""Transposition and docking after TMI (the docking chapter's "tde" scenario), then extraction of the lander.

    .venv/bin/python selftest/flight/td.py

1. Release the orbiter from the lander's top port (the port's "decouple node"): the orbiter becomes its own vessel.
   Name the two: 'Orbiter' and 'Lander' (the lander still carries the spent Poodle stage).
2. Orbiter: light its Terrier (throttle 0), back away along its nose with RCS to ~25 m, stop.
3. Turn round and dock its nose port to the lander's top port (rdv.dock: onto the port axis, close at 0.15 m/s).
4. Fire the TD-25 next to the Poodle tank: the spent translunar stage drifts off. Control from the Mk1-3 pod.
"""
import math, os, sys, time
from common import Kio, Log, save, dot
import rdv

BACKOFF_M = 25.0


def main():
    log = Log('td')
    k = Kio('td')
    sc = k.sc
    v = sc.active_vessel
    v.control.throttle = 0.0
    existing = {w.name: w for w in sc.vessels}
    if 'Orbiter' in existing and 'Lander' in existing:
        orbiter, lander = existing['Orbiter'], existing['Lander']
        log('resuming: orbiter already separated')
    else:
        # the lander's top port carries the orbiter: either directly (the port's "decouple node", current craft) or
        # through a TD-12 (first build: the TD-12 stays on the port, so the port then releases it as debris, G14)
        top = None
        for d in v.parts.docking_ports:
            if any(c.engine is not None or c.decoupler is not None for c in d.part.children):
                top = d
        if top is None:
            raise SystemExit('orbiter attachment not found')
        held = [c for c in top.part.children if c.engine is not None or c.decoupler is not None][0]
        if held.decoupler is not None:
            log(f'separating the orbiter: {held.title} on the lander port')
            new = held.decoupler.decouple()
            time.sleep(1.0)
            debris = top.undock()                  # the TD-12 left on the docking face
            log(f'released the TD-12 from the lander port ({debris.name})')
        else:
            log(f'separating the orbiter: lander port decouple node ({held.title} above it)')
            new = top.undock()
        time.sleep(1.0)
        lander = sc.active_vessel
        orbiter = new
        lander.name = 'Lander'
        orbiter.name = 'Orbiter'
        log(f"lander+S-IVB {lander.mass / 1e3:.2f} t, orbiter {orbiter.mass / 1e3:.2f} t; crew lander "
            f"{[c.name for c in lander.crew]}, orbiter {[c.name for c in orbiter.crew]}")
    sc.active_vessel = orbiter
    time.sleep(2.0)
    orb = sc.active_vessel
    orb.control.throttle = 0.0
    for e in orb.parts.engines:
        e.active = True
    orb.control.sas = False
    orb.control.rcs = True
    ap = orb.auto_pilot
    nrf = orb.orbit.body.non_rotating_reference_frame
    ap.reference_frame = nrf                           # (the autopilot refuses a frame that turns with the vessel)
    ap.target_direction = orb.direction(nrf)           # hold the current attitude while backing off
    ap.target_roll = float('nan')
    ap.engaged = True
    lf = lander.reference_frame
    log(f"lander ports now: {[d.state.name for d in lander.parts.docking_ports]}")
    # back off: 0.4 m/s along the orbiter's nose, then stop at BACKOFF_M
    t0 = sc.ut
    while sc.ut - t0 < 200:
        d = list(orb.position(lf))
        dist = math.sqrt(dot(d, d))
        vel = orb.velocity(lf)
        away = dot(vel, [x / dist for x in d]) if dist > 0 else 0
        if dist >= BACKOFF_M:
            break
        orb.control.forward = 1.0 if away < 0.4 else 0.0
        time.sleep(0.1)
    orb.control.forward = 0.0
    # stop
    t0 = sc.ut
    while sc.ut - t0 < 60:
        rv = [a - b for a, b in zip(orb.velocity(nrf), lander.velocity(nrf))]
        if math.sqrt(dot(rv, rv)) < 0.03:
            break
        dd = sc.transform_direction(tuple(-x for x in rv), nrf, orb.reference_frame)
        orb.control.right = max(-1, min(1, 4 * dd[0])); orb.control.forward = max(-1, min(1, 4 * dd[1]))
        orb.control.up = max(-1, min(1, -4 * dd[2]))
        time.sleep(0.1)
    orb.control.right = orb.control.forward = orb.control.up = 0.0
    d = orb.position(lf)
    log(f'backed off to {math.sqrt(dot(d, d)):.1f} m; turning round and docking')
    ap.engaged = False
    k.close()
    os.environ['RDV_TARGET'] = 'Lander'
    docked = rdv.dock(standoff=20.0, save_name='td-docked')
    if not docked:
        raise SystemExit('docking failed')
    # extraction: drop the spent translunar stage
    k = Kio('td')
    sc = k.sc
    v = sc.active_vessel
    v.name = 'LOR'
    drop = None
    for p in v.parts.all:
        if p.decoupler is not None and p.title.startswith('TD-25'):
            near = [q for q in [p.parent, *p.children] if q is not None]
            if any(q.title.startswith('Rockomax X200-16') for q in near):
                drop = p
    log(f'extraction: firing {drop.title if drop else "?"} next to the Poodle tank')
    if drop is not None:
        drop.decoupler.decouple()
        time.sleep(1.0)
    v = sc.active_vessel
    pod = [p for p in v.parts.all if p.title.startswith('Mk1-3')]
    if pod:
        v.parts.controlling = pod[0]
    v.auto_pilot.engaged = False
    v.control.rcs = False
    v.control.sas = True
    v.control.throttle = 0.0
    log(f"stack {v.name}: {len(v.parts.all)} parts, {v.mass / 1e3:.2f} t, crew {[c.name for c in v.crew]}, "
        f"engines {[e.part.title.split(' ')[0] + (' ON' if e.active else '') for e in v.parts.engines]}")
    save(k, 'td-extracted', log)
    k.close()


if __name__ == '__main__':
    main()
