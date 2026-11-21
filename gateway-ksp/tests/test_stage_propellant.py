"""The stage's tanks are chosen again when the engines lit change (GAPS C22): chosen while no engine was lit yet,
they stayed empty and stage Δv read 0 through a whole ascent."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ksp.parts_watch import PartsWatch


class Engine:
    def __init__(self, lit):
        self.lit = lit

    def active(self):
        return self.lit


def watch(engine):
    parts = PartsWatch.__new__(PartsWatch)          # no kRPC: only the stage propellant bookkeeping
    parts.engines, parts.watched_stage, parts.watched_lit, parts.stage_tanks = [engine], None, None, []
    parts.stale, parts.generation, parts.rebuild = False, 0, None
    parts.refresh = lambda: None
    parts.chosen = []
    parts._watch_stage_tanks = lambda stage: (parts.chosen.append(engine.lit),
                                              setattr(parts, 'stage_tanks', [('LiquidFuel', 10.0, lambda: 4.0)] if engine.lit else []))
    return parts


def test_tanks_chosen_with_the_engine_off_are_chosen_again_when_it_lights():
    engine = Engine(lit=False)
    parts = watch(engine)
    assert parts.stage_propellant(0) == {}
    engine.lit = True
    assert parts.stage_propellant(0) == {'LiquidFuel': {'amount': 4.0, 'max': 10.0}}
    assert parts.chosen == [False, True]


def test_not_chosen_again_while_nothing_changes():
    engine = Engine(lit=True)
    parts = watch(engine)
    for _ in range(3):
        parts.stage_propellant(0)
    assert parts.chosen == [True]


# ---------- the rebuild after a staging, in the background (GAPS C4) ----------
from ksp.parts_watch import Rebuild


class Streams:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def bound_watch():
    engine = Engine(lit=True)
    parts = watch(engine)
    parts.stage_propellant(3)                       # bound: tanks chosen at once
    parts.streams, parts.stage_streams, parts.not_flown_engines = Streams(), Streams(), []
    parts.rebuild, parts.closed, parts.stale, parts.generation = None, False, False, 0
    started = []
    parts._start_rebuild = lambda stage: started.append((stage, parts.generation))
    return parts, started


def finished(stage, generation, marker):
    rebuild = Rebuild(stage, generation)
    fresh = PartsWatch.__new__(PartsWatch)
    fresh.__dict__.update({'watched_stage': stage, 'stage_tanks': [('LiquidFuel', 5.0, lambda: 1.0)],
                           'streams': Streams(), 'stage_streams': Streams(), 'marker': marker,
                           'not_flown_engines': [], 'rebuild': None, 'closed': False, 'stale': False, 'generation': 0})
    rebuild.result = fresh
    rebuild.done.set()
    return rebuild


def test_a_staging_keeps_the_old_streams_until_the_rebuilt_ones_are_ready():
    parts, started = bound_watch()
    old_streams = parts.streams
    parts.forget_stage()
    assert parts.stage_propellant(2) == {'LiquidFuel': {'amount': 4.0, 'max': 10.0}}     # the old ones meanwhile
    assert started == [(2, 1)]
    parts.rebuild = finished(2, 1, 'new')
    assert parts.stage_propellant(2) == {'LiquidFuel': {'amount': 1.0, 'max': 5.0}}      # swapped in
    assert parts.marker == 'new' and old_streams.closed and not parts.stale and parts.generation == 1


def test_a_rebuild_started_before_another_staging_is_dropped():
    parts, started = bound_watch()
    parts.forget_stage()
    parts.stage_propellant(2)
    parts.forget_stage()                            # staged again meanwhile
    parts.rebuild = finished(2, 1, 'stale')
    parts.stage_propellant(2)
    assert not hasattr(parts, 'marker') and started[-1] == (2, 2)
