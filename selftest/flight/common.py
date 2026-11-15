"""Shared helpers for the flight scripts: connection, logging, staging, warp, saves, the planner bridge."""
import json, math, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                       # selftest/
sys.path.insert(0, ROOT)
from kio import Kio                                 # noqa: E402

LOGS = os.path.join(ROOT, 'logs')
DATA = os.path.join(ROOT, 'data')
os.makedirs(LOGS, exist_ok=True)


class Log:
    """Text log + CSV telemetry for one phase."""
    def __init__(self, phase):
        stamp = time.strftime('%Y%m%d-%H%M%S')
        self.txt = open(os.path.join(LOGS, f'{phase}-{stamp}.log'), 'a', buffering=1)
        self.csv_path = os.path.join(LOGS, f'{phase}-{stamp}.csv')
        self.csv, self.cols = None, None

    def __call__(self, *a):
        line = time.strftime('%H:%M:%S ') + ' '.join(str(x) for x in a)
        print(line, flush=True)
        self.txt.write(line + '\n')

    def row(self, **kw):
        if self.csv is None:
            self.cols = list(kw)
            self.csv = open(self.csv_path, 'a', buffering=1)
            self.csv.write(','.join(self.cols) + '\n')
        self.csv.write(','.join(f'{kw.get(c, "")}' if not isinstance(kw.get(c), float) else f'{kw[c]:.6g}' for c in self.cols) + '\n')


def planner(script, payload=None, args=()):
    """Run a Node planner script; JSON in on stdin, JSON out on the last stdout line."""
    p = subprocess.run(['node', os.path.join(ROOT, 'planner', script), *args], input=json.dumps(payload or {}),
                       capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        raise RuntimeError(f'planner {script} failed: {p.stderr[-2000:]}')
    lines = [l for l in p.stdout.strip().splitlines() if l.strip()]
    return json.loads(lines[-1]), '\n'.join(lines[:-1])


def vec(a):
    return list(a)


def norm(a):
    n = math.sqrt(sum(x * x for x in a))
    return [x / n for x in a]


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def state(k, v, frame=None):
    """Position and velocity of vessel v in the body's non-rotating frame (KSP frames are left-handed, y = north)."""
    body = v.orbit.body
    f = frame or body.non_rotating_reference_frame
    return vec(v.position(f)), vec(v.velocity(f))


class Stager:
    """Stage when an active engine runs dry; a stage that leaves no engine burning is followed by the next one."""
    def __init__(self, k, v, log):
        self.k, self.v, self.log = k, v, log
        self.last = 0

    def engines_burning(self):
        return [e for e in self.v.parts.engines if e.active and e.has_fuel]

    def flameout(self):
        # has_fuel stayed True on the Mun LOR core after it ran dry (propellant still reachable through the docking
        # ports' crossfeed?): an active engine that can give no thrust is out as well
        return any(e.active and (not e.has_fuel or e.available_thrust <= 0) for e in self.v.parts.engines)

    def check(self, ut, allow_upper=True):
        if ut - self.last < 0.6:
            return False
        if self.flameout():
            self.stage(ut, 'flameout')
            if not self.engines_burning() and allow_upper:
                time.sleep(0.5)
                self.stage(ut, 'no engine burning')
            return True
        return False

    def stage(self, ut, why):
        self.v.control.activate_next_stage()
        self.last = ut
        self.log(f'STAGE ({why}) -> current stage {self.v.control.current_stage}')


def warp_to(k, ut, log=None):
    sc = k.sc
    if log:
        log(f'warp to UT {ut:.1f} ({ut - sc.ut:.0f} s)')
    sc.warp_to(ut)


def save(k, name, log=None):
    name = os.environ.get('SAVE_PREFIX', '') + name      # e.g. SAVE_PREFIX=rdv- keeps earlier flights' saves
    k.sc.save(name)
    if log:
        log(f'saved game "{name}"')
