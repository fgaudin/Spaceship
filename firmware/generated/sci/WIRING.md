# sci: SCIENCE · ACTION GROUPS

Generated from `protocol/panels/sci.json` by `firmware/tools/gen_module.py`. Chips: 2 MCP23017, 0 ADS1115, 2 MAX7219, 4 HT16K33.

| Panel | Control | Kind | Where |
|---|---|---|---|
| SCIENCE | EXPERIMENT | alphanumeric | HT16K33 0 (0x70) characters 0.. |
| SCIENCE | NO | 7-segment | MAX7219 0 digits 0..1 |
| SCIENCE | BIOME | alphanumeric | HT16K33 2 (0x72) characters 0.. |
| SCIENCE | ◂ EXP | button | MCP 0 (0x20) GPA0 to GND |
| SCIENCE | EXP ▸ | button | MCP 0 (0x20) GPA1 to GND |
| SCIENCE | READY | lamp | MCP 0 (0x20) GPA2 → ULN2803 if 12 V |
| SCIENCE | DATA | lamp | MCP 0 (0x20) GPA3 → ULN2803 if 12 V |
| SCIENCE | SPENT | lamp | MCP 0 (0x20) GPA4 → ULN2803 if 12 V |
| SCIENCE | SCIENCE | 7-segment | MAX7219 0 digits 2..6 |
| SCIENCE | IF SENT | 7-segment | MAX7219 1 digits 0..4 |
| SCIENCE | RUN | button | MCP 0 (0x20) GPA5 to GND |
| SCIENCE | SEND | button | MCP 0 (0x20) GPA6 to GND |
| SCIENCE | DUMP | button | MCP 0 (0x20) GPA7 to GND |
| SCIENCE | RESET | button | MCP 0 (0x20) GPB0 to GND |
| SCIENCE | RUN ALL | button | MCP 0 (0x20) GPB1 to GND |
| ACTION GROUPS | AG 1 | button | MCP 0 (0x20) GPB2 to GND |
| ACTION GROUPS | AG 1 (lamp) | lamp | MCP 0 (0x20) GPB3 → ULN2803 if 12 V |
| ACTION GROUPS | AG 2 | button | MCP 0 (0x20) GPB4 to GND |
| ACTION GROUPS | AG 2 (lamp) | lamp | MCP 0 (0x20) GPB5 → ULN2803 if 12 V |
| ACTION GROUPS | AG 3 | button | MCP 0 (0x20) GPB6 to GND |
| ACTION GROUPS | AG 3 (lamp) | lamp | MCP 0 (0x20) GPB7 → ULN2803 if 12 V |
| ACTION GROUPS | AG 4 | button | MCP 1 (0x21) GPA0 to GND |
| ACTION GROUPS | AG 4 (lamp) | lamp | MCP 1 (0x21) GPA1 → ULN2803 if 12 V |
| ACTION GROUPS | AG 5 | button | MCP 1 (0x21) GPA2 to GND |
| ACTION GROUPS | AG 5 (lamp) | lamp | MCP 1 (0x21) GPA3 → ULN2803 if 12 V |
| ACTION GROUPS | AG 6 | button | MCP 1 (0x21) GPA4 to GND |
| ACTION GROUPS | AG 6 (lamp) | lamp | MCP 1 (0x21) GPA5 → ULN2803 if 12 V |
| ACTION GROUPS | AG 7 | button | MCP 1 (0x21) GPA6 to GND |
| ACTION GROUPS | AG 7 (lamp) | lamp | MCP 1 (0x21) GPA7 → ULN2803 if 12 V |
| ACTION GROUPS | AG 8 | button | MCP 1 (0x21) GPB0 to GND |
| ACTION GROUPS | AG 8 (lamp) | lamp | MCP 1 (0x21) GPB1 → ULN2803 if 12 V |
| ACTION GROUPS | AG 9 | button | MCP 1 (0x21) GPB2 to GND |
| ACTION GROUPS | AG 9 (lamp) | lamp | MCP 1 (0x21) GPB3 → ULN2803 if 12 V |
| ACTION GROUPS | AG 10 | button | MCP 1 (0x21) GPB4 to GND |
| ACTION GROUPS | AG 10 (lamp) | lamp | MCP 1 (0x21) GPB5 → ULN2803 if 12 V |
