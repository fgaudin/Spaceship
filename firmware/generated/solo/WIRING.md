# solo: SOLO · FLIGHT DYNAMICS

Generated from `protocol/panels/solo.json` by `firmware/tools/gen_module.py`. Chips: 1 MCP23017, 0 ADS1115, 7 MAX7219, 3 HT16K33.

| Panel | Control | Kind | Where |
|---|---|---|---|
| PAD REQUEST | FLIGHT DYNAMICS | alphanumeric | HT16K33 0 (0x70) characters 0.. |
| PAD REQUEST | PAD SENT | lamp | MCP 0 (0x20) GPA0 → ULN2803 if 12 V |
| PAD REQUEST | REFUSED | lamp | MCP 0 (0x20) GPA1 → ULN2803 if 12 V |
| PAD REQUEST | CIRC | button | MCP 0 (0x20) GPA2 to GND |
| PAD REQUEST | PLANE | button | MCP 0 (0x20) GPA3 to GND |
| PAD REQUEST | RDV TGT | button | MCP 0 (0x20) GPA4 to GND |
| PAD REQUEST | INJECT | button | MCP 0 (0x20) GPA5 to GND |
| PAD REQUEST | INJECT TO MUN | rotary position | MCP 0 (0x20) GPA6 to GND |
| PAD REQUEST | INJECT TO MINMUS | rotary position | MCP 0 (0x20) GPA7 to GND |
| ORBIT | APOAPSIS KM | 7-segment | MAX7219 0 digits 0..6 |
| ORBIT | TIME TO APO | 7-segment | MAX7219 1 digits 0..6 |
| ORBIT | PERIAPSIS KM | 7-segment | MAX7219 2 digits 0..6 |
| ORBIT | TIME TO PERI | 7-segment | MAX7219 3 digits 0..6 |
| ORBIT | INCLINATION ° | 7-segment | MAX7219 4 digits 0..4 |
| NAVIGATION | BODY | alphanumeric | HT16K33 2 (0x72) characters 0.. |
| NAVIGATION | LAT ° (+ NORTH) | 7-segment | MAX7219 5 digits 0..4 |
| NAVIGATION | LON ° (+ EAST) | 7-segment | MAX7219 6 digits 0..5 |
| NAVIGATION | MODE | switch | MCP 0 (0x20) GPB0 to GND |
