# stn: STATION

Generated from `protocol/panels/stn.json` by `firmware/tools/gen_module.py`. Chips: 1 MCP23017, 0 ADS1115, 1 MAX7219, 0 HT16K33.

| Panel | Control | Kind | Where |
|---|---|---|---|
| STATION | STATION CM | rotary position | MCP 0 (0x20) GPA0 to GND |
| STATION | STATION LM | rotary position | MCP 0 (0x20) GPA1 to GND |
| STATION | CM | lamp | MCP 0 (0x20) GPA2 → ULN2803 if 12 V |
| STATION | LM | lamp | MCP 0 (0x20) GPA3 → ULN2803 if 12 V |
| STATION | TRANSFER | lamp | MCP 0 (0x20) GPA4 → ULN2803 if 12 V |
| STATION | TUNNEL | lamp | MCP 0 (0x20) GPA5 → ULN2803 if 12 V |
| STATION | CM CREW | 7-segment | MAX7219 0 digits 0..0 |
| STATION | LM CREW | 7-segment | MAX7219 0 digits 1..1 |
