# lnd: FLIGHT DATA · LANDING

Generated from `protocol/panels/lnd.json` by `firmware/tools/gen_module.py`. Chips: 1 MCP23017, 0 ADS1115, 9 MAX7219, 0 HT16K33.

| Panel | Control | Kind | Where |
|---|---|---|---|
| FLIGHT DATA · LANDING | ALT M | 7-segment | MAX7219 0 digits 0..7 |
| FLIGHT DATA · LANDING | V SPEED M/S | 7-segment | MAX7219 1 digits 0..4 |
| FLIGHT DATA · LANDING | H SPEED M/S | 7-segment | MAX7219 2 digits 0..4 |
| FLIGHT DATA · LANDING | ALT REF | switch | MCP 0 (0x20) GPA0 to GND |
| FLIGHT DATA · LANDING | TIME TO IMPACT S | 7-segment | MAX7219 3 digits 0..4 |
| FLIGHT DATA · LANDING | HOVER TIME S | 7-segment | MAX7219 4 digits 0..3 |
| FLIGHT DATA · LANDING | DRIFT M/S + R | 7-segment | MAX7219 5 digits 0..4 |
| FLIGHT DATA · LANDING | DRIFT M/S + UP | 7-segment | MAX7219 6 digits 0..4 |
| FLIGHT DATA · LANDING | CONTACT | lamp | MCP 0 (0x20) GPA1 → ULN2803 if 12 V |
| FLIGHT DATA · LANDING | SINK OK | lamp | MCP 0 (0x20) GPA2 → ULN2803 if 12 V |
| FLIGHT DATA · LANDING | DRIFT OK | lamp | MCP 0 (0x20) GPA3 → ULN2803 if 12 V |
| FLIGHT DATA · LANDING | UPRIGHT | lamp | MCP 0 (0x20) GPA4 → ULN2803 if 12 V |
| FLIGHT DATA · LANDING | GEAR DOWN | lamp | MCP 0 (0x20) GPA5 → ULN2803 if 12 V |
| FLIGHT DATA · LANDING | GEAR (LED) | lamp | MCP 0 (0x20) GPA6 → ULN2803 if 12 V |
| FLIGHT DATA · LANDING | GEAR | switch | MCP 0 (0x20) GPA7 to GND |
| FLIGHT DATA · LANDING | SPEED M/S | 7-segment | MAX7219 7 digits 0..4 |
| FLIGHT DATA · LANDING | G | 7-segment | MAX7219 4 digits 4..7 |
| FLIGHT DATA · LANDING | Q KPA | 7-segment | MAX7219 8 digits 0..3 |
