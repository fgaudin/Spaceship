"""What the gateway watches part by part: engines, stage propellant, solar panels, reaction wheels, parachutes, ground contact, heat
and docking ports. Rebuilt after every staging, because parts leave and kRPC streams on them go stale."""
from .streams import FAST_HZ, SLOW_HZ, StreamGroup, read_or

TOTAL_RESOURCES = ('ElectricCharge', 'LiquidFuel', 'Oxidizer', 'MonoPropellant', 'XenonGas', 'Ablator',
                   'Food', 'Water', 'Oxygen')     # the last three: TAC Life Support
FUEL_CELL = 'fuel cell'          # in the name of the resource converter of the stock fuel cells
STAGE_PROPELLANTS = ('LiquidFuel', 'Oxidizer', 'SolidFuel', 'MonoPropellant', 'XenonGas')
PARACHUTE_OUT_STATES = {'semi_deployed', 'deployed'}
JETTISON_MODULE = 'ModuleJettison'   # a part that throws a cover off when staged (the SM-25's doors)


class WatchedEngine:
    def __init__(self, engine, streams, vessel_frame):
        self.engine = engine
        # Position across the vessel's axis (vessel frame: x right, y forward, z down): the cockpit lays the engine
        # status LEDs out from it.
        right, _, down = engine.part.position(vessel_frame)
        self.right, self.down = round(right, 2), round(down, 2)
        self.stage = engine.part.stage
        # What the engine gives at full throttle, also before it is lit (thrust and available_thrust are zero then):
        # the cockpit needs it for the TWR and the stage Δv on the pad. Specific impulse in vacuum and at sea level;
        # the cockpit takes the value for the outside pressure in between.
        self.rated_thrust = streams.attribute(engine, 'max_thrust', SLOW_HZ)
        self.vacuum_specific_impulse = round(engine.vacuum_specific_impulse, 1)
        self.sea_level_specific_impulse = round(engine.kerbin_sea_level_specific_impulse, 1)
        self.propellants = list(engine.propellant_names)    # what it burns: an ion engine leaves the rocket fuel alone
        self.active = streams.attribute(engine, 'active', SLOW_HZ)
        self.thrust = streams.attribute(engine, 'thrust', SLOW_HZ)
        self.available_thrust = streams.attribute(engine, 'available_thrust', SLOW_HZ)
        self.has_fuel = streams.attribute(engine, 'has_fuel', SLOW_HZ)

    def telemetry(self):
        return {'x': self.right, 'z': self.down, 'stage': self.stage, 'on': self.active(),
                'thrust': round(self.thrust(), 1), 'max': round(self.available_thrust(), 1), 'fuel': self.has_fuel(),
                'rated': round(self.rated_thrust(), 1), 'isp_vac': self.vacuum_specific_impulse,
                'isp_sl': self.sea_level_specific_impulse, 'propellants': self.propellants}


class WatchedExperiment:
    def __init__(self, experiment, streams):
        self.experiment = experiment
        self.title = experiment.title
        self.rerunnable = experiment.rerunnable
        self.available = streams.attribute(experiment, 'available', SLOW_HZ)
        self.has_data = streams.attribute(experiment, 'has_data', SLOW_HZ)
        self.inoperable = streams.attribute(experiment, 'inoperable', SLOW_HZ)
        self.values = None              # (science, science if transmitted) of the data held, read once per result

    def telemetry(self):
        has_data = self.has_data()
        if not has_data:
            self.values = None
        elif self.values is None:
            data = self.experiment.data
            self.values = (round(sum(item.science_value for item in data), 2),
                           round(sum(item.transmit_value for item in data), 2))
        return {'title': self.title, 'available': self.available(), 'data': has_data,
                'inoperable': self.inoperable(), 'rerunnable': self.rerunnable,
                'value': self.values and self.values[0], 'transmit': self.values and self.values[1]}


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
        self.antennas = [antenna for antenna in parts.antennas if antenna.deployable]
        self.antennas_deployed = [streams.attribute(antenna, 'deployed', SLOW_HZ) for antenna in self.antennas]
        self._watch_fuel_cells(parts)
        self.reaction_wheels = list(parts.reaction_wheels)
        self.wheels_active = [streams.attribute(wheel, 'active', SLOW_HZ) for wheel in self.reaction_wheels]
        self.parachutes = list(parts.parachutes)
        self.parachute_states = [streams.attribute(parachute, 'state', SLOW_HZ) for parachute in self.parachutes]
        self.parachute_safety = [streams.attribute(parachute, 'safe_state', SLOW_HZ) for parachute in self.parachutes]
        self.experiments = [WatchedExperiment(experiment, streams) for experiment in parts.experiments]
        self.engines = [WatchedEngine(engine, streams, vessel.reference_frame) for engine in parts.engines]
        self.read_engine_settings()
        self.ground_contacts = ([streams.attribute(leg, 'is_grounded', FAST_HZ) for leg in parts.legs]
                                + [streams.attribute(wheel, 'grounded', FAST_HZ) for wheel in parts.wheels])
        self._watch_heat(parts)
        self.docking_ports = list(parts.docking_ports)
        self.not_flown_engines = getattr(self, 'not_flown_engines', [])   # engine_sharing.py: the other capsule's
        self.next_stage = self._next_stage_contents(parts)
        self.docking_port_states = [streams.attribute(port, 'state', SLOW_HZ) for port in self.docking_ports]
        self.docking_states_seen, self.is_docked = None, False
        self._watch_total_resources()

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
        # `stage`: the stage this list was read in (the cockpit must not pair it with a newer stage number)
        return {'engines': engines, 'stage': self.watched_stage, 'limit': self.thrust_limit,
                'gimbal_locked': self.gimbal_locked}

    # ---------- resources of the whole vessel ----------
    def _watch_total_resources(self):
        """resource → (amount stream, capacity). Read again with the parts, because staging takes capacity away.
        These are the dearest streams of all: KSP walks every part for each."""
        self.total_resource_watch = {}
        for resource in TOTAL_RESOURCES:
            capacity = self.vessel.resources.max(resource)
            if capacity > 0:
                amount = self.streams.call(SLOW_HZ, self.vessel.resources.amount, resource)
                self.total_resource_watch[resource] = (amount, capacity)

    def total_resources(self):
        """{'<resource>': {'amount', 'max'}} for the whole vessel."""
        if not self.total_resource_watch:
            # Just after a save loads KSP reports no capacity at all for a moment: look again.
            self._watch_total_resources()
        return {resource: {'amount': round(read_or(0.0, amount), 3), 'max': round(capacity, 3)}
                for resource, (amount, capacity) in self.total_resource_watch.items()}

    # ---------- propellant of the current stage ----------
    def stage_propellant(self, stage_number):
        """{'<resource>': {'amount', 'max'}} for the tanks that leave with the burning engines. kRPC 0.7 has no call
        for this, so there is one stream per tank and resource, rebuilt when the stage number changes."""
        if stage_number != self.watched_stage:
            self.watched_stage = stage_number
            self.refresh()
            self._watch_stage_tanks(stage_number)
        totals = {}
        for resource, capacity, amount in self.stage_tanks:
            total = totals.setdefault(resource, {'amount': 0.0, 'max': 0.0})
            total['amount'] += amount()
            total['max'] += capacity
        return {resource: {'amount': round(total['amount'], 3), 'max': round(total['max'], 3)}
                for resource, total in totals.items()}

    def _watch_stage_tanks(self, stage_number):
        """The tanks that leave with the burning engines; before ignition, with the engines that the next staging
        lights (KSP numbers stages downwards: they are in stage_number − 1)."""
        self.stage_streams.close()
        self.stage_tanks = []           # (resource, capacity, amount stream)
        engines = self.vessel.parts.engines
        burning_groups = {engine.part.decouple_stage for engine in engines if engine.active}
        if not burning_groups:
            burning_groups = {engine.part.decouple_stage for engine in engines if engine.part.stage == stage_number - 1}
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

    def antenna_deployed_state(self):
        """True / False, or None when the vessel has no deployable antenna."""
        if not self.antennas_deployed:
            return None
        return any(read_or(False, deployed) for deployed in self.antennas_deployed)

    def parachute_safety_state(self):
        """Whether opening the parachutes now is 'safe', 'risky' or 'unsafe' (the worst of them); None when KSP gives
        no verdict, or without parachutes."""
        states = {read_or(None, safety) for safety in self.parachute_safety}
        names = {state.name for state in states if state is not None}
        return next((name for name in ('unsafe', 'risky', 'safe') if name in names), None)

    def science_telemetry(self):
        experiments = []
        for watched in self.experiments:
            try:
                experiments.append(watched.telemetry())
            except Exception:           # the part is gone: left out until the parts are read again
                continue
        return experiments

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

    # ---------- the next staging ----------
    def read_next_stage(self):
        self.next_stage = self._next_stage_contents(self.vessel.parts)

    def _next_stage_contents(self, parts):
        """What pressing STAGE does: how many liquid engines and solid motors it lights, and whether it decouples,
        releases launch clamps, opens parachutes or jettisons a fairing. None when no stage is left. Read when the
        part list is rebuilt, which every staging does (KSP numbers stages downwards: the next is current − 1)."""
        try:
            stage = self.vessel.control.current_stage - 1
            if stage < 0:
                return None
            in_stage = lambda items: any(item.part.stage == stage for item in items)
            lit = [watched for watched in self.engines
                   if watched.stage == stage and watched.engine not in self.not_flown_engines]
            solids = sum('SolidFuel' in engine.propellants for engine in lit)
            # A docking port separates too, by its decouple node (a launch escape tower on the CM's nose port, an
            # undocking), and covers come off parts that are not fairings (the SM-25's doors, ModuleJettison): both
            # left NEXT STAGE dark or short in the Mun mission. Engines carry ModuleJettison for their shrouds, which
            # do not come off when the engine is staged: left out.
            ports = any(port.part.stage == stage for port in parts.docking_ports)
            covers = any(module.part.stage == stage and module.part.engine is None
                         for module in parts.modules_with_name(JETTISON_MODULE))
            return {'stage': stage, 'engines': len(lit) - solids, 'solids': solids,
                    'decouple': in_stage(parts.decouplers) or ports, 'clamps': in_stage(parts.launch_clamps),
                    'chutes': in_stage(self.parachutes), 'fairing': in_stage(parts.fairings) or covers}
        except Exception as error:      # a part kRPC cannot read: no preview rather than no telemetry
            print('next stage unreadable:', str(error).splitlines()[0], flush=True)
            return None

    # ---------- fuel cells ----------
    def _watch_fuel_cells(self, parts):
        """The resource converters that are fuel cells, as (converter, index), and whether each is running."""
        try:
            self.fuel_cells = [(converter, index) for converter in parts.resource_converters
                               for index in range(converter.count) if FUEL_CELL in converter.name(index).lower()]
        except Exception:           # a modded converter kRPC cannot read: no fuel cells rather than no telemetry
            self.fuel_cells = []
        self.fuel_cells_running = [self.streams.call(SLOW_HZ, converter.active, index) for converter, index in self.fuel_cells]

    def fuel_cell_state(self):
        """True when a fuel cell runs, False, or None when the vessel has none."""
        return any(read_or(False, running) for running in self.fuel_cells_running) if self.fuel_cells_running else None

    def wheels_state(self):
        """True when a reaction wheel is on, False, or None when the vessel has none."""
        return any(read_or(False, active) for active in self.wheels_active) if self.wheels_active else None

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
