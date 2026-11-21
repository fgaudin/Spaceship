# res: LIFE SUPPORT · ELECTRICAL · PROPELLANT

Generated from `protocol/panels/res.json` by `firmware/tools/gen_module.py`. Chips: 1 MCP23017, 0 ADS1115, 7 MAX7219, 0 HT16K33.

| Panel | Control | Kind | Where |
|---|---|---|---|
| LIFE SUPPORT | FOOD | bar | MAX7219 0 rows 0..1 |
| LIFE SUPPORT | WATER | bar | MAX7219 0 rows 2..3 |
| LIFE SUPPORT | O2 | bar | MAX7219 0 rows 4..5 |
| LIFE SUPPORT | FOOD H | 7-segment | MAX7219 1 digits 0..3 |
| LIFE SUPPORT | WATER H | 7-segment | MAX7219 1 digits 4..7 |
| LIFE SUPPORT | O2 H | 7-segment | MAX7219 2 digits 0..3 |
| LIFE SUPPORT | CREW | 7-segment | MAX7219 0 digits 6..7 |
| ELECTRICAL | CHARGE | bar | MAX7219 2 rows 4..5 |
| ELECTRICAL | EC | 7-segment | MAX7219 3 digits 0..4 |
| ELECTRICAL | EC/S | 7-segment | MAX7219 4 digits 0..4 |
| ELECTRICAL | SOLAR (LED) | lamp | MCP 0 (0x20) GPA0 → ULN2803 if 12 V |
| ELECTRICAL | SOLAR | switch | MCP 0 (0x20) GPA1 to GND |
| ELECTRICAL | FUEL CELL (LED) | lamp | MCP 0 (0x20) GPA2 → ULN2803 if 12 V |
| ELECTRICAL | FUEL CELL | switch | MCP 0 (0x20) GPA3 to GND |
| ELECTRICAL | WHEELS (LED) | lamp | MCP 0 (0x20) GPA4 → ULN2803 if 12 V |
| ELECTRICAL | WHEELS | switch | MCP 0 (0x20) GPA5 to GND |
| PROPELLANT | FUEL | bar | MAX7219 2 rows 6..7 |
| PROPELLANT | OXID | bar | MAX7219 3 rows 5..6 |
| PROPELLANT | MONO | bar | MAX7219 4 rows 5..6 |
| PROPELLANT | XENON | bar | MAX7219 5 rows 0..1 |
| PROPELLANT | BURN TIME S | 7-segment | MAX7219 5 digits 2..6 |
| PROPELLANT | RCS ΔV M/S | 7-segment | MAX7219 6 digits 0..3 |
