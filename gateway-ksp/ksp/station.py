"""The two capsules the console can be: the command module (CM) and the lander (LM). Which crewed part each one is,
how many kerbals are in each, which one the craft is flown from (tlm/station), and the move from one to the other
(cmd/station): the crew goes across while there are seats, then the controls follow.

A capsule is found by its window cameras, the Hullcam cameras named cm_left, cm_right, lm_left and lm_right in the
part menu of the JRTI mod (Just Read The Instructions), which streams them under that name: the part a station's
camera is attached to, or the first crewed part above it. When the capsules are undocked, the other one is a separate
vessel nearby."""
import time

STATIONS = ('cm', 'lm')
WINDOW_CAMERAS = {station: (f'{station}_left', f'{station}_right') for station in STATIONS}
JRTI_MODULE, JRTI_NAME_FIELD = 'JRTICameraConfigModule', 'jrtiName'     # the camera name set in the part menu
NEARBY_M = 2500             # beyond this KSP has not loaded the other vessel: it cannot be flown from here
FIND_AGAIN_EVERY_S = 10     # the capsules are looked for again this often (docking, undocking, staging)
CREW_ORDER = ('Pilot', 'Engineer', 'Scientist')     # who goes across first when not everyone fits
SWITCH_SETTLE_S = 0.5       # after switching vessels, before controlling it
TRANSFER_SETTLE_S = 0.5     # between two kerbals going across (back to back, the second transfer failed)


def other(station):
    return 'lm' if station == 'cm' else 'cm'


def capsule_of(camera):
    """The crewed part a window camera is attached to, or the first one above it."""
    part = camera
    while part is not None:
        if part.crew_capacity > 0:
            return part
        part = part.parent
    return None


def find_capsules(space_center, vessel):
    """{station: part}: the capsules in the vessel, then in vessels close enough to be loaded."""
    capsules = {}
    for candidate in [vessel] + nearby_vessels(space_center, vessel):
        named = named_cameras(candidate)
        for station in STATIONS:
            if station in capsules:
                continue
            cameras = [part for name, part in named if name in WINDOW_CAMERAS[station]]
            capsule = next((found for found in map(capsule_of, cameras) if found is not None), None)
            if capsule is not None:
                capsules[station] = capsule
        if len(capsules) == len(STATIONS):
            break
    return capsules


def named_cameras(vessel):
    """[(name, part)]: the cameras of the vessel given a name in JRTI's part menu."""
    named = []
    for module in vessel.parts.modules_with_name(JRTI_MODULE):
        name = next((field.value for field in module.field_list if field.name == JRTI_NAME_FIELD), '')
        if name and name.strip():
            named.append((name.strip(), module.part))
    return named


def nearby_vessels(space_center, vessel):
    frame = vessel.reference_frame
    near = []
    for candidate in space_center.vessels:
        if candidate == vessel:
            continue
        try:
            if sum(component ** 2 for component in candidate.position(frame)) ** 0.5 < NEARBY_M:
                near.append(candidate)
        except RuntimeError:
            continue            # a vessel that went away while looking
    return near


class StationWatch:
    """Bound to one active vessel, like PartsWatch."""
    def __init__(self, space_center, vessel):
        self.space_center, self.vessel = space_center, vessel
        self.capsules = {}
        self.found_at = None

    def _capsules(self, refresh=False):
        if refresh or self.found_at is None or time.monotonic() - self.found_at > FIND_AGAIN_EVERY_S:
            self.capsules = find_capsules(self.space_center, self.vessel)
            self.found_at = time.monotonic()
        return self.capsules

    def telemetry(self):
        """tlm/station: per capsule its crew and seats, and whether it is in this vessel; which one has the
        controls; whether the crew can go across (both capsules in the same vessel: docked)."""
        capsules, payload = self._capsules(), {'at': None}
        try:
            controlling = self.vessel.parts.controlling
            for station in STATIONS:
                capsule = capsules.get(station)
                if capsule is None:
                    payload[station] = None
                    continue
                payload[station] = {'crew': len(capsule.crew), 'seats': capsule.crew_capacity,
                                    'here': capsule.vessel == self.vessel}
                if capsule == controlling:
                    payload['at'] = station
        except RuntimeError:            # a capsule that left (undocked and unloaded, destroyed): look again
            self.found_at = None
            return {'at': None, 'cm': None, 'lm': None, 'joined': False}
        payload['joined'] = all(payload[station] and payload[station]['here'] for station in STATIONS)
        return payload

    def go_to(self, station, link, move_crew=True):
        """cmd/station: the crew goes across into `station`'s capsule while it has seats (only when the two are
        docked, and `move_crew`), then the craft is flown from it, switching to its vessel when the two are apart.
        Returns False when that capsule is nowhere to be found."""
        capsules = self._capsules(refresh=True)
        target, source = capsules.get(station), capsules.get(other(station))
        if target is None:
            return False
        if move_crew and source is not None and source.vessel == target.vessel:
            self._move_crew(source, target)
        if target.vessel == self.vessel:
            self.vessel.parts.controlling = target
            link.default_control_part = target          # where CTRL FROM PORT off comes back to
            link.target_facts = None                    # the control point is one of them
        else:
            self.space_center.active_vessel = target.vessel
            time.sleep(SWITCH_SETTLE_S)
            target.vessel.parts.controlling = target
            link.unbind()                               # a new active vessel: the main loop binds it
        return True

    def _move_crew(self, source, target):
        """As many as fit, pilots first. Never into a full part: kRPC then drops the kerbal out of the vessel."""
        order = lambda kerbal: CREW_ORDER.index(kerbal.trait) if kerbal.trait in CREW_ORDER else len(CREW_ORDER)
        for _ in range(target.crew_capacity):
            # the source's crew read again each time: after a transfer, the crew objects read before it are stale and
            # kRPC fails on them (NullReferenceException), which used to stop the move after the first kerbal
            remaining = sorted(source.crew, key=order)
            if not remaining or target.available_seats <= 0:
                break
            try:
                self.space_center.transfer_crew(remaining[0], target)
            except Exception as error:      # KSP not ready for the next transfer yet: once more, a moment later
                print(f'crew transfer of {remaining[0].name} failed ({error}); trying again', flush=True)
                time.sleep(TRANSFER_SETTLE_S)
                self.space_center.transfer_crew(sorted(source.crew, key=order)[0], target)
            time.sleep(TRANSFER_SETTLE_S)
