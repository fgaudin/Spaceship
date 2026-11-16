"""What the gateway watches part by part: engines, stage propellant, solar panels, parachutes, ground contact, heat
and docking ports. Rebuilt after every staging, because parts leave and kRPC streams on them go stale."""
from .streams import FAST_HZ, SLOW_HZ, StreamGroup, read_or

STAGE_PROPELLANTS = ('LiquidFuel', 'Oxidizer', 'SolidFuel', 'MonoPropellant')
PARACHUTE_OUT_STATES = {'semi_deployed', 'deployed'}


class WatchedEngine:
    def __init__(self, engine, streams, vessel_frame):
        self.engine = engine
        # Position across the vessel's axis (vessel frame: x right, y forward, z down): the cockpit lays the engine
        # status LEDs out from it.
        right, _, down = engine.part.position(vessel_frame)
        self.right, self.down = round(right, 2), round(down, 2)
        self.stage = engine.part.stage
        self.active = streams.attribute(engine, 'active', SLOW_HZ)
        self.thrust = streams.attribute(engine, 'thrust', SLOW_HZ)
        self.available_thrust = streams.attribute(engine, 'available_thrust', SLOW_HZ)
        self.has_fuel = streams.attribute(engine, 'has_fuel', SLOW_HZ)

    def telemetry(self):
        return {'x': self.right, 'z': self.down, 'stage': self.stage, 'on': self.active(),
                'thrust': round(self.thrust(), 1), 'max': round(self.available_thrust(), 1), 'fuel': self.has_fuel()}


class PartsWatch:
    def __init__(self, connection, vessel):
        self.connection, self.vessel = connection, vessel
        self.streams = StreamGroup(connection)
        self.stage_streams = StreamGroup(connection)
        self.watched_stage = None       # stage number the stage propellant streams belong to
        self.refresh()

    def refresh(self):
        """Read the part list again and rebuild every part stream."""
        self.streams.close()
        vessel, streams = self.vessel, self.streams
        parts = vessel.parts
        self.solar_panels = [panel for panel in parts.solar_panels if panel.deployable]
        self.solar_deployed = [streams.attribute(panel, 'deployed', SLOW_HZ) for panel in self.solar_panels]
        self.parachutes = list(parts.parachutes)
        self.parachute_states = [streams.attribute(parachute, 'state', SLOW_HZ) for parachute in self.parachutes]
        self.engines = [WatchedEngine(engine, streams, vessel.reference_frame) for engine in parts.engines]
        self.read_engine_settings()
        self.ground_contacts = ([streams.attribute(leg, 'is_grounded', FAST_HZ) for leg in parts.legs]
                                + [streams.attribute(wheel, 'grounded', FAST_HZ) for wheel in parts.wheels])
        self._watch_heat(parts)
        self.docking_ports = list(parts.docking_ports)
        self.docking_port_states = [streams.attribute(port, 'state', SLOW_HZ) for port in self.docking_ports]
        self.docking_states_seen, self.is_docked = None, False

    def close(self):
        self.streams.close()
        self.stage_streams.close()

    # ---------- engines ----------
    def read_engine_settings(self):
        """Thrust limiter and gimbal lock change only on command, so they are read then, not streamed."""
        lit = [watched.engine for watched in self.engines if watched.active()]
        limiters = [engine.thrust_limit for engine in lit if not engine.throttle_locked]
        gimbals = [engine.gimbal_locked for engine in (lit or self.all_engines()) if engine.gimballed]
        self.thrust_limit = round(sum(limiters) / len(limiters), 3) if limiters else None
        self.gimbal_locked = any(gimbals) if gimbals else None

    def all_engines(self):
        return [watched.engine for watched in self.engines]

    def engine_telemetry(self):
        engines = []
        for watched in self.engines:
            try:
                engines.append(watched.telemetry())
            except Exception:           # destroyed: left out, and the cockpit shows it as lost
                continue
        return {'engines': engines, 'limit': self.thrust_limit, 'gimbal_locked': self.gimbal_locked}

    # ---------- propellant of the current stage ----------
    def stage_propellant(self, stage_number):
        """{'<resource>': {'amount', 'max'}} for the tanks that leave with the burning engines. kRPC 0.7 has no call
        for this, so there is one stream per tank and resource, rebuilt when the stage number changes."""
        if stage_number != self.watched_stage:
            self.watched_stage = stage_number
            self.refresh()
            self._watch_stage_tanks()
        totals = {}
        for resource, capacity, amount in self.stage_tanks:
            total = totals.setdefault(resource, {'amount': 0.0, 'max': 0.0})
            total['amount'] += amount()
            total['max'] += capacity
        return {resource: {'amount': round(total['amount'], 3), 'max': round(total['max'], 3)}
                for resource, total in totals.items()}

    def _watch_stage_tanks(self):
        self.stage_streams.close()
        self.stage_tanks = []           # (resource, capacity, amount stream)
        burning_groups = {engine.part.decouple_stage for engine in self.vessel.parts.engines if engine.active}
        if not burning_groups:
            return
        burning_group = max(burning_groups)
        for part in self.vessel.parts.all:
            if part.decouple_stage != burning_group:
                continue
            for resource in set(part.resources.names) & set(STAGE_PROPELLANTS):
                capacity = part.resources.max(resource)
                if capacity > 0:
                    amount = self.stage_streams.call(SLOW_HZ, part.resources.amount, resource)
                    self.stage_tanks.append((resource, capacity, amount))

    def forget_stage(self):
        """After a staging command: rebuild on the next read."""
        self.watched_stage = None

    # ---------- solar panels, parachutes, ground ----------
    def solar_deployed_state(self):
        """True / False, or None when the vessel has no deployable panel."""
        return any(deployed() for deployed in self.solar_deployed) if self.solar_deployed else None

    def parachute_state(self):
        """'deployed', 'armed', 'cut' or 'stowed'; None without parachutes."""
        if not self.parachute_states:
            return None
        states = {state().name for state in self.parachute_states}
        if states & PARACHUTE_OUT_STATES:
            return 'deployed'
        if 'armed' in states:
            return 'armed'
        return 'cut' if states == {'cut'} else 'stowed'

    def has_landing_gear(self):
        return bool(self.ground_contacts)

    def touches_ground(self):
        return any(read_or(False, contact) for contact in self.ground_contacts)

    # ---------- heat ----------
    def _watch_heat(self, parts):
        """Skin temperature of every part and core temperature of the engines, each with its limit."""
        engine_part_ids = {watched.engine.part._object_id for watched in self.engines}
        self.temperatures = []          # (temperature stream, limit)
        for part in parts.all:
            skin_temperature = self.streams.attribute(part, 'skin_temperature', SLOW_HZ)
            self.temperatures.append((skin_temperature, part.max_skin_temperature))
            if part._object_id in engine_part_ids:
                core_temperature = self.streams.attribute(part, 'temperature', SLOW_HZ)
                self.temperatures.append((core_temperature, part.max_temperature))

    def thermal_telemetry(self):
        """The hottest part, as a fraction of its temperature limit."""
        fractions = [read_or(0.0, temperature) / limit for temperature, limit in self.temperatures if limit > 0]
        return {'max': round(max(fractions, default=0.0), 3)}

    # ---------- docking ----------
    def ports_docked_to_a_port(self):
        """A port with an ordinary part stacked on it in the VAB also reports 'docked'; that is not a docking."""
        return [port for port in self.docking_ports
                if port.state.name == 'docked' and port.docked_part is not None
                and port.docked_part.docking_port is not None]

    def docked(self):
        """Whether the vessel is docked to another. The partners are only looked at when a port changes state."""
        try:
            states = tuple(state().name for state in self.docking_port_states)
            if states != self.docking_states_seen:
                self.docking_states_seen, self.is_docked = states, bool(self.ports_docked_to_a_port())
            return self.is_docked
        except Exception:
            return False
