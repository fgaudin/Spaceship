# rdv: RENDEZVOUS · DOCKING

Generated from `protocol/panels/rdv.json` by `firmware/tools/gen_module.py`. Chips: 1 MCP23017, 0 ADS1115, 11 MAX7219, 2 HT16K33.

| Panel | Control | Kind | Where |
|---|---|---|---|
| TARGET | TARGET | alphanumeric | HT16K33 0 (0x70) characters 0.. |
| TARGET | TGT | lamp | MCP 0 (0x20) GPA0 → ULN2803 if 12 V |
| TARGET | PORT | lamp | MCP 0 (0x20) GPA1 → ULN2803 if 12 V |
| TARGET | ◂ TGT | button | MCP 0 (0x20) GPA2 to GND |
| TARGET | TGT ▸ | button | MCP 0 (0x20) GPA3 to GND |
| TARGET | PORT ▸ | button | MCP 0 (0x20) GPA4 to GND |
| TARGET | CLEAR | button | MCP 0 (0x20) GPA5 to GND |
| TARGET | CTRL FROM PORT (LED) | lamp | MCP 0 (0x20) GPA6 → ULN2803 if 12 V |
| TARGET | CTRL FROM PORT | switch | MCP 0 (0x20) GPA7 to GND |
| ROTATION | YAW ° (+ RIGHT) | 7-segment | MAX7219 0 digits 0..4 |
| ROTATION | PITCH ° (+ UP) | 7-segment | MAX7219 1 digits 0..4 |
| ROTATION | ROLL ° (+ RIGHT) | 7-segment | MAX7219 2 digits 0..4 |
| ROTATION | RATE °/S | 7-segment | MAX7219 3 digits 0..3 |
| ROTATION | RATE °/S | 7-segment | MAX7219 3 digits 4..7 |
| ROTATION | RATE °/S | 7-segment | MAX7219 4 digits 0..3 |
| TRANSLATION | LATERAL M (+ RIGHT) | 7-segment | MAX7219 5 digits 0..4 |
| TRANSLATION | RATE M/S | 7-segment | MAX7219 4 digits 4..7 |
| TRANSLATION | VERTICAL M (+ UP) | 7-segment | MAX7219 6 digits 0..4 |
| TRANSLATION | RATE M/S | 7-segment | MAX7219 7 digits 0..3 |
| TRANSLATION | RANGE M | 7-segment | MAX7219 8 digits 0..4 |
| TRANSLATION | RATE M/S | 7-segment | MAX7219 7 digits 4..7 |
| DOCKING | RANGE M | 7-segment | MAX7219 9 digits 0..5 |
| DOCKING | KM | lamp | MCP 0 (0x20) GPB0 → ULN2803 if 12 V |
| DOCKING | CLOSING M/S | 7-segment | MAX7219 10 digits 0..4 |
| DOCKING | CAPTURE | lamp | MCP 0 (0x20) GPB1 → ULN2803 if 12 V |
| DOCKING | DOCKED | lamp | MCP 0 (0x20) GPB2 → ULN2803 if 12 V |
| DOCKING | UNDOCK ARM (LED) | lamp | MCP 0 (0x20) GPB3 → ULN2803 if 12 V |
| DOCKING | UNDOCK ARM | switch | MCP 0 (0x20) GPB4 to GND |
| DOCKING | UNDOCK | button | MCP 0 (0x20) GPB5 to GND |
| DOCKING | UNDOCK (lamp) | lamp | MCP 0 (0x20) GPB6 → ULN2803 if 12 V |
