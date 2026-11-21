# rnt: REENTRY · RECOVERY

Generated from `protocol/panels/rnt.json` by `firmware/tools/gen_module.py`. Chips: 1 MCP23017, 0 ADS1115, 3 MAX7219, 0 HT16K33.

| Panel | Control | Kind | Where |
|---|---|---|---|
| REENTRY · RECOVERY | ABLATOR | bar | MAX7219 0 rows 0..1 |
| REENTRY · RECOVERY | HOTTEST PART PCT | 7-segment | MAX7219 0 digits 2..5 |
| REENTRY · RECOVERY | TIME TO ATM S | 7-segment | MAX7219 1 digits 0..4 |
| REENTRY · RECOVERY | OUTSIDE °C | 7-segment | MAX7219 2 digits 0..3 |
| REENTRY · RECOVERY | PRESSURE KPA | 7-segment | MAX7219 2 digits 4..7 |
| REENTRY · RECOVERY | 0.05 G | lamp | MCP 0 (0x20) GPA0 → ULN2803 if 12 V |
| REENTRY · RECOVERY | CHUTE SAFE | lamp | MCP 0 (0x20) GPA1 → ULN2803 if 12 V |
| REENTRY · RECOVERY | CHUTE RISKY | lamp | MCP 0 (0x20) GPA2 → ULN2803 if 12 V |
| REENTRY · RECOVERY | CHUTE UNSAFE | lamp | MCP 0 (0x20) GPA3 → ULN2803 if 12 V |
| REENTRY · RECOVERY | CHUTE ARM (LED) | lamp | MCP 0 (0x20) GPA4 → ULN2803 if 12 V |
| REENTRY · RECOVERY | CHUTE ARM | switch | MCP 0 (0x20) GPA5 to GND |
| REENTRY · RECOVERY | CHUTE | button | MCP 0 (0x20) GPA6 to GND |
| REENTRY · RECOVERY | CHUTE (lamp) | lamp | MCP 0 (0x20) GPA7 → ULN2803 if 12 V |
| REENTRY · RECOVERY | BRAKES (LED) | lamp | MCP 0 (0x20) GPB0 → ULN2803 if 12 V |
| REENTRY · RECOVERY | BRAKES | switch | MCP 0 (0x20) GPB1 to GND |
