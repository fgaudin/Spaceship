# SimSup: the instructor station

In Apollo, the simulation supervisor (SimSup) and their team ran the training simulations. They set up the scenario,
injected failures without warning the crew, watched how the crew coped, then debriefed. This is that station: a
service that owns the simulation, and a web page to drive it.

Page: **http://localhost:8650/simsup.html** (SIMSUP in the top bar of every panel page).

## How it fits in

```
                                    ┌──────────────────────┐
  simsup.html (instructor) ───────▶ │  simsup service      │  sim/simsup/cmd   requests from the page
        ▲                           │  (simsup/)           │
        │ sim/simsup/state, log,    │  · failures on/off   │
        │ scenarios (retained)      │  · armed triggers    │──▶ sim/failures/<id>  {"on", parameters}  (retained)
        └───────────────────────────│  · scenarios         │──▶ sim/freeze         {"on"}              (retained)
                                    │  · event log         │──▶ sim/load           {"save"}
                                    │  · debrief           │
                                    └──────────┬───────────┘
                                               │ listens to the whole flight: tlm/*, panel/+/in/#, cmd/#, cw/state
               ┌───────────────────────────────┼───────────────────────────────┐
               ▼                               ▼                               ▼
   gateway-ksp (or the mock)           cockpit-logic                     (nothing else
   failures of the vehicle:            failures of the instruments:       reads sim/*)
   engines, gimbals, RCS, wheels,      false alarm, dark panel,
   chutes, comms, telemetry;           frozen display, stuck switch
   freeze = KSP paused; load a save
```

One writer per topic, as everywhere on the bus: only SimSup writes `sim/failures/*`, `sim/freeze` and `sim/load`.
The crew's panels never see a failure as such; they see its consequences, through the cockpit and KSP.

## The parts

| File | What it is |
|---|---|
| `simsup_core.py` | The logic, pure (no I/O, time passed in): the failure catalogue (`FAILURES`), armed failures and their triggers, scenarios, the log and the debrief. Unit-tested in `tests/`. |
| `service.py` | The MQTT shell: feeds bus messages to the core, publishes what it returns, ticks once a second. |
| `scenarios.json` | The scenarios: a save to load, a briefing, and failures with their triggers. Edit it to add your own. |
| `../panels/virtual/simsup.html`, `simsup.js`, `simsup.css` | The page. It only displays what the service publishes and sends requests; the service keeps all the state, so closing or reloading the page loses nothing. |
| `../gateway-ksp/ksp/failures.py` | How the gateway applies vehicle failures in KSP. |
| `../cockpit-logic/cockpit/injected_failures.py` | How the cockpit applies instrument failures. |

## Failures

| Id | What happens | Applied by | How |
|---|---|---|---|
| `engine_out` | Every lit engine shuts down | gateway (and mock) | kRPC `engine.active = False`, checked again twice a second so the engines stay off. Staging to a new engine works: that is the recovery. When cleared, the engines are repaired but not relit. |
| `engine_one_out` | One engine of the cluster shuts down | gateway (and mock) | The lit engine farthest from the axis, so the engine matrix shows which. |
| `gimbal_stuck` | Gimbals locked | gateway (and mock) | Gimbals locked; `cmd/gimbal` from the crew is ignored. |
| `rcs_fail` | RCS dead | gateway | Every RCS part disabled. |
| `wheels_fail` | Reaction wheels dead | gateway | Every reaction wheel off: SAS weak or useless. |
| `chute_fail` | Parachutes do not deploy | gateway (and mock) | `cmd/chute` ignored. |
| `comm_lost` | Radio link lost | gateway (and mock) | Telemetry reports no link: COM panel LOS, COMM LOST caution. KSP itself still has its link. |
| `telemetry_freeze` | All telemetry stops | gateway (and mock) | Nothing published: NO LINK, dashed displays. |
| `battery_short`, `overheat` | — | mock only | KSP has no way through kRPC to drain a battery or heat a part. |
| `false_alarm` | A caution or warning with no cause | cockpit | Parameter `alarm`: its id (`cw_low_fuel`) or its legend (`LOW FUEL`). |
| `panel_dark` | A panel loses power | cockpit | Parameter `panel` (`sys`, `cmp`…): every output dark, every input ignored. |
| `display_frozen` | A display freezes | cockpit | Parameter `output` (`eng/disp_alt`): keeps the value shown at that moment. |
| `switch_stuck` | A switch or button does nothing | cockpit | Parameter `control` (`sas`, `stage`…): its input is ignored. |

## Triggers

A failure can be injected now, or armed to fire later:

| Trigger | Fires when |
|---|---|
| `{"met": 25}` | mission time reaches 25 s (MET counts from liftoff, so nothing fires on the pad) |
| `{"alt_below": 4000}`, `{"alt_above": 30000}` | altitude crosses the value, in metres |
| `{"stage": 8}` | the vessel reaches stage 8 (KSP numbers stages downwards) |

## A scenario, start to finish

1. The instructor presses START on "Ascent: engine out". SimSup clears every failure, empties the log, publishes
   `sim/load {"save": "lor3-selftest-pad"}` (the gateway loads the save), and arms `engine_one_out` at MET 25 s.
2. The crew launches. SimSup watches `tlm/time`; at MET 25 s it publishes `sim/failures/engine_one_out {"on": true}`.
3. The gateway shuts the outermost lit engine. The cockpit's engine matrix shows it red, ENG FAIL lights, MASTER
   ALARM blinks and the tone sounds.
4. SimSup logs everything: the failure, the alarms coming on, each crew input and each command. The debrief shows
   how long until the crew acknowledged (MASTER ALARM pressed) and until their first action.
5. The instructor can FREEZE (KSP paused, whatever the crew's PAUSE switch says), CLEAR the failure, add notes, and
   EXPORT the log and the debrief as a JSON file. NEW SESSION empties both.

## The bus messages

| Topic | Writer | Payload |
|---|---|---|
| `sim/simsup/cmd` | the page | `{"action": "inject", "failure", "parameters"}`, `"clear"`, `"clear_all"`, `{"action": "arm", "failure", "parameters", "trigger"}`, `{"action": "disarm", "number"}`, `{"action": "freeze", "on"}`, `{"action": "scenario", "name"}`, `{"action": "load", "save"}`, `{"action": "note", "text"}`, `"new_session"` |
| `sim/failures/<id>` | SimSup | `{"on": bool, …parameters}`, retained. All set off when the service starts. |
| `sim/freeze` | SimSup | `{"on": bool}`, retained |
| `sim/load` | SimSup | `{"save": "<KSP save name>"}` |
| `sim/simsup/scenarios` | SimSup | `{"scenarios": [...], "failures": [catalogue]}`, retained |
| `sim/simsup/state` | SimSup | `{"scenario", "frozen", "active", "armed", "debrief"}`, retained |
| `sim/simsup/log` | SimSup | `{"log": [{"t", "met", "kind", "text"}]}` (last 2 000 lines), retained |

## Running and testing

```sh
docker compose up -d --build simsup                       # with the rest of the stack
.venv/bin/python -m pytest -q simsup/tests                # the logic
.venv/bin/python tests/e2e_ksp_simsup.py --save lor3-selftest-pad   # every failure, freeze and load, in KSP
```

## Not done yet

- Failures with a degree (an engine at 50 % thrust, a slow leak) rather than on/off.
- A voice loop to the crew, and Mission Control's side (PADs are uplinked from the burn computer's own page).
- Battery and heat failures in KSP: kRPC cannot drain a resource or heat a part.
