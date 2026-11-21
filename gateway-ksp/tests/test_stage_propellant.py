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
