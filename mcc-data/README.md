# MCC data

Mission Control's data besides the live telemetry: the flight recorder, the bodies as the game has them, and relief
maps of their terrain. What uses it and how: [panels/virtual/mcc/README.md](../panels/virtual/mcc/README.md); the
topics: [protocol/topics.md](../protocol/topics.md) (`mcc/history`, `mcc/events`, `mcc/bodies`, `mcc/maps`,
`mcc/data/status`; it reads `mission/clock`).

| File | What it is |
|---|---|
| `recorder.py` | One sample a second and the flight's events; a new flight when the MET starts again from zero or when `mission/clock`'s launch moves (MET RESET, another craft), a quickload drops what came after. Pure. |
| `relief.py` | Shading and colouring a grid of heights into a PNG (no library). Pure. |
| `service.py` | The bus, the recorder's clock and disk copy (`STATE_FILE`), and a kRPC connection of its own for the bodies and the terrain (`MAPS_DIR`). |

A map is 1440 × 720 samples of the terrain height (and the sea, where there is one), about 1.5 minutes per body,
once: the body flown and its moons. Its file name carries the radius and a version (`Mun-400000-r2.png`), so a
JNSQ map never stands in for a stock one, and a new colouring makes new files; older ones can be deleted.

    .venv/bin/python -m pytest -q mcc-data/tests
