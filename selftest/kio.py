"""kio: the only door to kRPC for the self-test.

Every property read, property write, method call and stream that goes through it is recorded, so
selftest/interface.md can be built from the log (SELFTEST.md, "Log 2").

    from kio import Kio
    k = Kio('ascent')              # connects; k.phase labels the calls that follow
    v = k.sc.active_vessel         # wrapped objects behave like the kRPC ones
    alt = k.stream(v.flight(), 'mean_altitude')      # a kRPC stream, logged as such
    k.phase = 'circularise'

The log is selftest/logs/interface.jsonl: one line per (service.class.member, kind, phase) the first
time it is seen, with the value type and the argument types (reference frames show up there), then a
counts summary in selftest/logs/interface-counts.json, rewritten by k.flush() and at exit.
"""
import atexit, json, os, threading, time
import krpc
from krpc.types import ClassBase

HERE = os.path.dirname(os.path.abspath(__file__))
LOGDIR = os.path.join(HERE, 'logs')


def _tname(x):
    if isinstance(x, ClassBase):
        return type(x).__name__
    if isinstance(x, (tuple, list)):
        inner = sorted({_tname(i) for i in x})
        return f'{type(x).__name__}[{len(x)}]<{",".join(inner)}>' if x else type(x).__name__
    if isinstance(x, dict):
        return 'dict'
    if hasattr(x, 'name') and hasattr(type(x), '__members__'):
        return f'{type(x).__name__}.{x.name}'          # an enum value
    return type(x).__name__


def _unwrap(x):
    if isinstance(x, Proxy):
        return object.__getattribute__(x, '_t')
    if isinstance(x, tuple):
        return tuple(_unwrap(i) for i in x)
    if isinstance(x, list):
        return [_unwrap(i) for i in x]
    if isinstance(x, dict):
        return {_unwrap(a): _unwrap(b) for a, b in x.items()}
    return x


class Recorder:
    def __init__(self, path, counts_path):
        self.path, self.counts_path = path, counts_path
        self.seen, self.counts, self.lock = set(), {}, threading.RLock()
        self.phase = 'setup'
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def log(self, member, kind, value=None, args=(), stream=False):
        # unwrap first: isinstance() on a Proxy reads __class__ through it, which logs again (deadlocked on a Part write)
        value, args = _unwrap(value), _unwrap(tuple(args))
        key = (member, kind, self.phase)
        with self.lock:
            ck = f'{member} {kind}' + (' stream' if stream else '')
            c = self.counts.setdefault(ck, {})
            c[self.phase] = c.get(self.phase, 0) + 1
            if key in self.seen:
                return
            self.seen.add(key)
            rec = {'t': time.strftime('%Y-%m-%dT%H:%M:%S'), 'phase': self.phase, 'member': member,
                   'kind': kind, 'stream': stream, 'args': [_tname(a) for a in args]}
            if value is not None:
                rec['type'] = _tname(value)
                if isinstance(value, (int, float, str, bool)) or (isinstance(value, tuple) and len(value) <= 4
                                                                   and all(isinstance(i, (int, float)) for i in value)):
                    rec['sample'] = value
            with open(self.path, 'a') as f:
                f.write(json.dumps(rec) + '\n')

    def flush(self):
        with self.lock:
            with open(self.counts_path, 'w') as f:
                json.dump(self.counts, f, indent=1, sort_keys=True)


class Proxy:
    """Wraps a kRPC service or object; reads, writes and calls are recorded by `rec`."""
    __slots__ = ('_t', '_svc', '_rec')

    def __init__(self, target, svc, rec):
        object.__setattr__(self, '_t', target)
        object.__setattr__(self, '_svc', svc)
        object.__setattr__(self, '_rec', rec)

    def _name(self, attr):
        t = object.__getattribute__(self, '_t')
        svc = object.__getattribute__(self, '_svc')
        cls = type(t).__name__
        return f'{svc}.{attr}' if cls == svc else f'{svc}.{cls}.{attr}'

    def _wrap(self, x):
        svc, rec = object.__getattribute__(self, '_svc'), object.__getattribute__(self, '_rec')
        if isinstance(x, ClassBase):
            return Proxy(x, svc, rec)
        if isinstance(x, tuple):
            return tuple(self._wrap(i) for i in x)
        if isinstance(x, list):
            return [self._wrap(i) for i in x]
        if isinstance(x, dict):
            return {self._wrap(a): self._wrap(b) for a, b in x.items()}
        return x

    def __getattr__(self, attr):
        t = object.__getattribute__(self, '_t')
        rec = object.__getattribute__(self, '_rec')
        desc = getattr(type(t), attr, None)
        if isinstance(desc, property):
            v = getattr(t, attr)
            rec.log(self._name(attr), 'read', v)
            return self._wrap(v)
        v = getattr(t, attr)
        if isinstance(v, type) or not callable(v):
            return v                                    # enum types, constants
        name = self._name(attr)

        def call(*a, **kw):
            r = v(*_unwrap(a), **{k: _unwrap(x) for k, x in kw.items()})
            rec.log(name, 'call', r, a + tuple(kw.values()))
            return self._wrap(r)
        return call

    def __setattr__(self, attr, value):
        t = object.__getattribute__(self, '_t')
        rec = object.__getattribute__(self, '_rec')
        rec.log(self._name(attr), 'write', value)
        setattr(t, attr, _unwrap(value))

    def __eq__(self, other):
        return object.__getattribute__(self, '_t') == _unwrap(other)

    def __hash__(self):
        return hash(object.__getattribute__(self, '_t'))

    def __repr__(self):
        return f'<kio {object.__getattribute__(self, "_t")!r}>'


class Kio:
    def __init__(self, phase='setup', name=None, address='127.0.0.1'):
        self.rec = Recorder(os.path.join(LOGDIR, 'interface.jsonl'), os.path.join(LOGDIR, 'interface-counts.json'))
        self.rec.phase = phase
        self.conn = krpc.connect(name=name or f'selftest-{phase}', address=address)
        self.sc = Proxy(self.conn.space_center, 'SpaceCenter', self.rec)
        self.krpc = Proxy(self.conn.krpc, 'KRPC', self.rec)
        atexit.register(self.flush)

    @property
    def phase(self):
        return self.rec.phase

    @phase.setter
    def phase(self, p):
        self.rec.phase = p

    def stream(self, obj, attr, *args):
        """Stream a property (stream(obj, 'prop')) or a method call (stream(obj, 'method', arg…))."""
        t = _unwrap(obj)
        name = obj._name(attr) if isinstance(obj, Proxy) else f'{type(t).__name__}.{attr}'
        if isinstance(getattr(type(t), attr, None), property):
            s = self.conn.add_stream(getattr, t, attr)
            try:
                self.rec.log(name, 'read', s(), stream=True)
            except Exception as e:                      # e.g. a singular frame at rest: the stream still works later
                self.rec.log(name, 'read', None, stream=True)
                self.rec.log(name, 'error:' + str(e).split('\n')[0][:120])
        else:
            s = self.conn.add_stream(getattr(t, attr), *_unwrap(args))
            self.rec.log(name, 'call', s(), args, stream=True)
        return s

    def flush(self):
        self.rec.flush()

    def close(self):
        self.flush()
        self.conn.close()
