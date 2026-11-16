"""The mock's world: a planar Kerbin and a three-stage launcher. SI units."""
import math
from dataclasses import dataclass

# ---------- Kerbin ----------
GRAVITATIONAL_PARAMETER = 3.5316e12             # μ, m³/s²
RADIUS = 600000.0
ROTATION_RATE = 2 * math.pi / 21549.425         # rad/s
STANDARD_GRAVITY = 9.80665
# exponential atmosphere fitted to KSP's (same fit as the course's planner)
SEA_LEVEL_DENSITY, DENSITY_SCALE_HEIGHT = 1.512, 5444.0
SEA_LEVEL_PRESSURE, PRESSURE_SCALE_HEIGHT = 101325.0, 5441.0
ATMOSPHERE_TOP = 70000.0

# ---------- vehicle ----------
DRAG_AREA = 4.0                                 # Cd·A, m²
PARACHUTE_DRAG_AREA = 300.0
PARACHUTE_OPENS_BELOW = 8000.0
PAYLOAD_MASS = 3900.0
BATTERY_CAPACITY = 400.0                        # electric charge units
PROPELLANT_KG_PER_UNIT = 5.0


@dataclass(frozen=True)
class Stage:
    name: str
    propellant_mass: float
    dry_mass: float
    vacuum_thrust: float
    sea_level_isp: float
    vacuum_isp: float
    engine_positions: tuple                     # (x, z) of each engine across the vehicle's axis, m

    def mass_flow_at_full_throttle(self):
        return self.vacuum_thrust / (self.vacuum_isp * STANDARD_GRAVITY)

    def specific_impulse_at(self, pressure):
        """Isp falls linearly with ambient pressure, from the vacuum to the sea-level value (course TM-7)."""
        return self.vacuum_isp - (self.vacuum_isp - self.sea_level_isp) * pressure / SEA_LEVEL_PRESSURE


CLUSTER_OF_FIVE = ((0.0, 0.0), (1.3, 0.0), (-1.3, 0.0), (0.0, 1.3), (0.0, -1.3))
SINGLE_ENGINE = ((0.0, 0.0),)
STAGES = [      # in firing order
    Stage('S1', 32000.0, 6000.0, 1500e3, 285.0, 310.0, CLUSTER_OF_FIVE),
    Stage('S2', 12000.0, 2500.0, 250e3, 90.0, 350.0, SINGLE_ENGINE),
    Stage('S3', 1800.0, 600.0, 60e3, 85.0, 345.0, SINGLE_ENGINE),
]

# ---------- the scripted rendezvous target ----------
TARGET_NAMES = ['Station', 'Tug']
TARGET_PORT_COUNT = 2
TARGET_START_RANGE = 2000.0
TARGET_STOP_RANGE = 30.0

# The mock warps the whole simulation, rails or physics alike.
WARP_RATES = [1, 2, 3, 4, 5, 10, 50, 100]
