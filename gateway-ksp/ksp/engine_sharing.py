"""Docked, the CM and the LM are one vessel to KSP: staging, ENG ARM and the throttle reach every engine, and KSP may
put the two capsules' engines in one stage when it rebuilds the staging after docking (found by the Mun mission: the
CSM's Cheetah and the lander's Terrier, facing opposite ways, lit by one STAGE). The console is one capsule at a time
(STATION), so its engine controls drive that capsule's engines only: while docked, the other capsule's engines are
held shut down, and lit again when STATION flies that capsule or when the two are apart.

A capsule's side is found in the part tree: the docking joint between the capsules is a docked port whose parent part
is the other port; the parts under that port are one capsule's side, the rest the other's."""
import time

STATIONS = ('cm', 'lm')
CHAINS_KEPT_S = 10              # part chains are read again this often (docking, staging)


def other(station):
    return 'lm' if station == 'cm' else 'cm'


def sides(capsule_chains, engine_chains, joint_ports):
    """[station or None] for each engine. `capsule_chains`: {station: [the capsule part and its ancestors]};
    `engine_chains`: [[an engine part and its ancestors]]; `joint_ports`: docked ports whose parent is the port they
    are docked to. The joint that has exactly one capsule under it splits the vessel between the two."""
    for joint in joint_ports:
        under = [station for station, chain in capsule_chains.items() if joint in chain]
        if len(under) == 1:
            inside = under[0]
            return [inside if joint in chain else other(inside) for chain in engine_chains]
    return [None] * len(engine_chains)


def chain_of(part):
    """The part and its ancestors up to the root."""
    chain = []
    while part is not None:
        chain.append(part)
        part = part.parent
    return chain


class EngineSharing:
    def __init__(self):
        self.held = []                  # kRPC Engine objects shut down because their capsule is not the one flown
        self.chains_read_at = None
        self.chains = {}                # part → its chain to the root, kept CHAINS_KEPT_S

    def apply(self, link, failed=()):
        """Hold the engines of the capsule not flown, give back those of the capsule flown (or all, apart).
        `failed`: engines SimSup holds shut down; never relit here. Returns True when an engine changed. A part
        the game cannot read (gone in a staging or an undocking) is logged, never a lost link."""
        try:
            return self._apply(link, failed)
        except Exception as error:
            print('engine sharing:', str(error).splitlines()[0], flush=True)
            self.chains_read_at = None
            return False

    def _apply(self, link, failed):
        station, vessel = link.station, link.vessel
        if station is None or vessel is None:
            return False
        report = station.telemetry()
        flown, joined = report.get('at'), report.get('joined')
        changed = False
        engines = list(vessel.parts.engines)
        not_flown = []
        if joined and flown in STATIONS:
            capsules = station._capsules()
            engine_sides = sides({name: self._chain(capsules[name]) for name in STATIONS},
                                 [self._chain(engine.part) for engine in engines], self._joint_ports(vessel))
            not_flown = [engine for engine, side in zip(engines, engine_sides) if side is not None and side != flown]
            for engine in not_flown:
                if engine.active:
                    engine.active = False
                    self.held.append(engine)
                    changed = True
            for engine, side in zip(engines, engine_sides):
                if side == flown and engine in self.held:
                    changed |= self._give_back(engine, failed)
        else:
            for engine in engines:
                if engine in self.held:
                    changed |= self._give_back(engine, failed)
        if link.parts is not None and (changed or not_flown != link.parts.not_flown_engines):
            link.parts.not_flown_engines = not_flown        # NEXT STAGE leaves them out
            link.parts.read_next_stage()
        return changed

    def _give_back(self, engine, failed):
        self.held.remove(engine)
        if engine in failed:
            return False
        try:
            engine.active = True
        except Exception:               # gone (staged away, destroyed)
            return False
        return True

    def _chain(self, part):
        """The part's chain to the root, kept CHAINS_KEPT_S (a call to the game per ancestor)."""
        now = time.monotonic()
        if self.chains_read_at is None or now - self.chains_read_at > CHAINS_KEPT_S:
            self.chains, self.chains_read_at = {}, now
        if part not in self.chains:
            self.chains[part] = chain_of(part)
        return self.chains[part]

    @staticmethod
    def _joint_ports(vessel):
        joints = []
        for port in vessel.parts.docking_ports:
            if port.state.name != 'docked':
                continue
            parent = port.part.parent
            if parent is not None and parent.docking_port is not None:
                joints.append(port.part)
        return joints
