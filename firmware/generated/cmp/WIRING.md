# cmp: BURN COMPUTER

Generated from `protocol/panels/cmp.json` by `firmware/tools/gen_module.py`. Chips: 2 MCP23017, 0 ADS1115, 7 MAX7219, 0 HT16K33.

| Panel | Control | Kind | Where |
|---|---|---|---|
| PAD | TIG | button | MCP 0 (0x20) GPA0 to GND |
| PAD | TIG (lamp) | lamp | MCP 0 (0x20) GPA1 → ULN2803 if 12 V |
| PAD | disp_tig | 7-segment | MAX7219 0 digits 0..5 |
| PAD | PRO | button | MCP 0 (0x20) GPA2 to GND |
| PAD | PRO (lamp) | lamp | MCP 0 (0x20) GPA3 → ULN2803 if 12 V |
| PAD | disp_pro | 7-segment | MAX7219 1 digits 0..5 |
| PAD | NRM | button | MCP 0 (0x20) GPA4 to GND |
| PAD | NRM (lamp) | lamp | MCP 0 (0x20) GPA5 → ULN2803 if 12 V |
| PAD | disp_nrm | 7-segment | MAX7219 2 digits 0..5 |
| PAD | RAD | button | MCP 0 (0x20) GPA6 to GND |
| PAD | RAD (lamp) | lamp | MCP 0 (0x20) GPA7 → ULN2803 if 12 V |
| PAD | disp_rad | 7-segment | MAX7219 3 digits 0..5 |
| ENTRY | key | keypad | rows MCP 0 (0x20) GPB0 +3, columns MCP 0 (0x20) GPB4 +4 |
| ENTRY | UPLINK ACCEPT | button | MCP 1 (0x21) GPA1 to GND |
| ENTRY | UPLINK ACCEPT (lamp) | lamp | MCP 1 (0x21) GPA2 → ULN2803 if 12 V |
| ENTRY | PAD CLEAR | button | MCP 1 (0x21) GPA3 to GND |
| ENTRY | ENTRY ERR | lamp | MCP 1 (0x21) GPA4 → ULN2803 if 12 V |
| BURN | TIME TO TIG | 7-segment | MAX7219 4 digits 0..4 |
| BURN | ΔV TO GO | 7-segment | MAX7219 5 digits 0..4 |
| BURN | BURN TIME S | 7-segment | MAX7219 6 digits 0..3 |
| BURN | ATT ERR ° | 7-segment | MAX7219 6 digits 4..7 |
| BURN | BURN ARM (LED) | lamp | MCP 1 (0x21) GPA5 → ULN2803 if 12 V |
| BURN | BURN ARM | switch | MCP 1 (0x21) GPA6 to GND |
| BURN | TIG | lamp | MCP 1 (0x21) GPA7 → ULN2803 if 12 V |
| BURN | BURN | lamp | MCP 1 (0x21) GPB0 → ULN2803 if 12 V |
| BURN | CUTOFF | lamp | MCP 1 (0x21) GPB1 → ULN2803 if 12 V |
