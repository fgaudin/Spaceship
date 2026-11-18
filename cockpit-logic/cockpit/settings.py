"""Every threshold and table of the cockpit logic, in one place. Units are SI unless the name says otherwise."""

# ---------- panels (the <panel> part of panel/<panel>/in/... and .../out/...) ----------
ENGINE_PANEL = 'eng'
SYSTEMS_PANEL = 'sys'
COMPUTER_PANEL = 'cmp'
RENDEZVOUS_PANEL = 'rdv'
COMM_PANEL = 'com'
HAND_CONTROLLER_PANEL = 'hc'       # the hand controllers (USB joysticks), as a panel
SOLO_PANEL = 'solo'           # PAD requests to the flight dynamics service, flying solo
LAB_PANEL = 'lab'            # experimental panels

# ---------- link to the plant ----------
NO_CHARGE_BELOW = 0.01              # electric charge left under this: no power, the panels go dark
TELEMETRY_STALE_AFTER_S = 2.0       # older telemetry than this raises NO LINK and dashes the displays
REASSERT_EVERY_S = 1.0              # a "panel wins" switch is re-commanded this often while the game disagrees
SAS_MODE_RETRIES = 5                # a SAS mode the game does not take is sent again this many times
SAS_DISAGREE_AFTER_S = 2.0          # SAS switch against the game for this long: SAS DISAGREE

# Switches that simply mirror to a plant command: control name → command topic.
TOGGLE_COMMANDS = {'sas': 'cmd/sas', 'rcs': 'cmd/rcs', 'gear': 'cmd/gear', 'lights': 'cmd/lights',
                   'brakes': 'cmd/brakes', 'solar': 'cmd/solar', 'fuel_cell': 'cmd/fuel_cell'}
# Of those, the ones the panel wins: re-commanded while the game disagrees. For the others the game wins (lamp only).
PANEL_WINS = {'sas', 'rcs', 'lights'}

# ---------- rotary selectors (position index → meaning) ----------
SAS_MODES = ['stability', 'prograde', 'retrograde', 'normal', 'antinormal', 'radial', 'antiradial', 'target',
             'antitarget', 'maneuver']
EVENT_TIMER_SOURCES = ['MAN', 'TIG', 'APO', 'PERI', 'SOI']
SPEED_MODES = ['orbit', 'surface', 'target']    # the navball's speed reference: what PRO and RETRO follow
# FDAI controls (ATTITUDE panel): what the error needles point at, and their full scale
FDAI_NEEDLES = ['prograde', 'retrograde', 'off']
FDAI_ERROR_SCALES_DEG = [5, 50]

# ---------- engine and throttle ----------
HAND_CONTROLLER_DEADBAND = 0.05     # a stick axis under this is zero
FINE_CONTROL_SCALE = 0.3            # RCS FINE: the sticks command 30 % of their throw (KSP's precision mode is not in kRPC)
THROTTLE_IDLE_BELOW = 0.05          # the lever must come back under this to release a throttle cut
THROTTLE_DISAGREE_ABOVE = 0.005     # game throttle this far from the one commanded: command it again (a 0.02 trickle
                                    # left after a save load gave 1 kN for minutes, and KSP will not time-warp then)
THROTTLE_UP_ABOVE = 0.02            # lever position that counts as "throttle up"
THRUST_LIMIT_STEP = 0.05            # the limiter knob moves the engines in steps of 5 %
ENGINE_GRID_SIZE = 9                # engine status matrix: 9 × 9 LEDs
ENGINE_WEAK_BELOW = 0.5             # an engine giving under half the thrust commanded shows amber
ENGINE_FAIL_AFTER_S = 1.0           # ... and raises ENG FAIL when it lasts this long

# ---------- caution and warning thresholds ----------
G_FORCE_LIMIT = 5.0
DYNAMIC_PRESSURE_LIMIT_PA = 30000.0
LOW_FUEL_FRACTION = 0.10
LOW_POWER_FRACTION = 0.20
LOW_MONOPROPELLANT_FRACTION = 0.10
OVERHEAT_FRACTION = 0.80            # hottest part, as a fraction of its temperature limit
SINK_RATE_BELOW_ALTITUDE_M = 1000.0
SINK_RATE_BASE_M_S, SINK_RATE_PER_ALTITUDE = 8.0, 0.1   # allowed descent rate: 8 m/s + 10 % of the radar altitude
GEAR_UP_BELOW_ALTITUDE_M = 300.0
CHUTE_BELOW_ALTITUDE_M = 15000.0
ATTITUDE_ERROR_LIMIT_DEG = 5.0      # off the burn attitude by more than this ...
ATTITUDE_ERROR_WINDOW_S = 30.0      # ... from this long before TIG
RESIDUAL_MIN_M_S, RESIDUAL_FRACTION = 0.5, 0.02     # Δv residual after cutoff: 0.5 m/s or 2 % of the burn
ENTRY_G_FORCE = 0.05                # the 0.05 G light (as on Mercury): drag is felt, the entry has begun

# Gravitational parameter μ (m³/s²) and radius (m) of the bodies a Mun trip visits, for the TWR display.
BODIES = {'Kerbin': (3.5316e12, 600000.0), 'Mun': (6.5138398e10, 200000.0), 'Minmus': (1.7658e9, 60000.0)}
STANDARD_GRAVITY = 9.80665
STANDARD_PRESSURE_PA = 101325.0
PROPELLANT_KG_PER_UNIT = 5.0        # liquid fuel, oxidizer and solid fuel in KSP

# ---------- rendezvous and docking (the course's docking chapter) ----------
BRAKING_GATE_TIME_S = 400.0         # allowed closing speed = range / 400 s ...
BRAKING_GATE_FLOOR_M_S = 0.05       # ... but never under 0.05 m/s
CLOSING_CAUTION_MARGIN = 1.2        # CLOSING caution at 20 % over the gate
RANGE_IN_KM_FROM_M = 100000.0       # the range display switches to km from 100 km
ATTITUDE_RATE_SMOOTHING = 0.25      # weight of the newest sample in the ATTITUDE panel's rates
DOCKING_RATE_SMOOTHING = 0.4       # weight of the newest sample in the yaw, pitch and roll rates
# Capture envelope: closing speed, lateral offset and angle at contact; the lamp only works within 10 m.
CAPTURE_SPEED_MIN_M_S, CAPTURE_SPEED_MAX_M_S = 0.03, 0.3
CAPTURE_LATERAL_MAX_M = 0.3
CAPTURE_ANGLE_MAX_DEG = 10.0
CAPTURE_LAMP_WITHIN_M = 10.0

# ---------- radio link ----------
STATION_NAME_CHARACTERS = 12        # the display of the first station or relay on the way

# ---------- experimental panels ----------
CROSS_POINTER_SIZE = 9              # LEDs on a side
CROSS_POINTER_MODES = ['NODE', 'RETRO', 'PRO', 'PORT', 'OFFSET', 'DRIFT']
# Full scales, finest first: the value at the edge of the matrix (four LEDs from the centre).
CROSS_POINTER_ANGLE_SCALES_DEG = (4.0, 20.0, 90.0)
CROSS_POINTER_OFFSET_SCALES_M = (1.0, 4.0, 20.0, 100.0)
CROSS_POINTER_DRIFT_SCALES_M_S = (2.0, 10.0, 50.0, 250.0)
CROSS_POINTER_MOVING_ABOVE_M_S = 1.0    # under this speed prograde and retrograde mean nothing
ACTION_GROUP_COUNT = 10
BODY_NAME_CHARACTERS = 8
CAMERA_NAME_CHARACTERS = 16

# ---------- time warp ----------
WARP_TO_EVENT_LEAD_S = 60.0         # WARP TO EVT stops this long before the event
EVENT_IMMINENT_S = 10.0             # the timer's RUN lamp blinks in the last 10 s before the event

# ---------- maneuver node mirror ----------
NODE_ECHO_DELAY_S = 2.0             # after commanding a node, ignore the game's node for this long (stale telemetry)
NODE_SAME_TIME_S, NODE_SAME_DELTA_V = 0.5, 0.05     # tolerances to recognise the node the cockpit itself made
