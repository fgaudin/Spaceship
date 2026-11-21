# aux: CAMERA · LINK

Generated from `protocol/panels/aux.json` by `firmware/tools/gen_module.py`. Chips: 1 MCP23017, 0 ADS1115, 2 MAX7219, 4 HT16K33.

| Panel | Control | Kind | Where |
|---|---|---|---|
| CAMERA | ON THE MONITOR | alphanumeric | HT16K33 0 (0x70) characters 0.. |
| CAMERA | CAMERA | 7-segment | MAX7219 0 digits 0..1 |
| CAMERA | LIVE | lamp | MCP 0 (0x20) GPA0 → ULN2803 if 12 V |
| CAMERA | ◂ CAM | button | MCP 0 (0x20) GPA1 to GND |
| CAMERA | CAM ▸ | button | MCP 0 (0x20) GPA2 to GND |
| CAMERA | MONITOR | switch | MCP 0 (0x20) GPA3 to GND |
| LINK · ANTENNA | AOS | lamp | MCP 0 (0x20) GPA4 → ULN2803 if 12 V |
| LINK · ANTENNA | LOS | lamp | MCP 0 (0x20) GPA5 → ULN2803 if 12 V |
| LINK · ANTENNA | SIGNAL | bar | MAX7219 0 rows 2..3 |
| LINK · ANTENNA | VIA | alphanumeric | HT16K33 2 (0x72) characters 0.. |
| LINK · ANTENNA | HOPS | 7-segment | MAX7219 0 digits 4..4 |
| LINK · ANTENNA | IN THIS STATE MIN.SEC | 7-segment | MAX7219 1 digits 0..4 |
| LINK · ANTENNA | ANTENNA DEPLOY (LED) | lamp | MCP 0 (0x20) GPA6 → ULN2803 if 12 V |
| LINK · ANTENNA | ANTENNA DEPLOY | switch | MCP 0 (0x20) GPA7 to GND |
