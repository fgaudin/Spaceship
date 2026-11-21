# eng: PROPULSION · FLIGHT CONTROL

Generated from `protocol/panels/eng.json` by `firmware/tools/gen_module.py`. Chips: 3 MCP23017, 1 ADS1115, 3 MAX7219, 0 HT16K33, 9 addressable RGB LEDs.

| Panel | Control | Kind | Where |
|---|---|---|---|
| CAUTION & WARNING | MASTER ALARM | button | MCP 0 (0x20) GPA0 to GND |
| CAUTION & WARNING | MASTER ALARM (lamp) | lamp | MCP 0 (0x20) GPA1 → ULN2803 if 12 V |
| CAUTION & WARNING | MASTER CAUTION | button | MCP 0 (0x20) GPA2 to GND |
| CAUTION & WARNING | MASTER CAUTION (lamp) | lamp | MCP 0 (0x20) GPA3 → ULN2803 if 12 V |
| CAUTION & WARNING | LOW FUEL | lamp | MCP 0 (0x20) GPA4 → ULN2803 if 12 V |
| CAUTION & WARNING | HIGH G | lamp | MCP 0 (0x20) GPA5 → ULN2803 if 12 V |
| CAUTION & WARNING | LOW POWER | lamp | MCP 0 (0x20) GPA6 → ULN2803 if 12 V |
| CAUTION & WARNING | NO LINK | lamp | MCP 0 (0x20) GPA7 → ULN2803 if 12 V |
| CAUTION & WARNING | SAS DISAGREE | lamp | MCP 0 (0x20) GPB0 → ULN2803 if 12 V |
| CAUTION & WARNING | HIGH Q | lamp | MCP 0 (0x20) GPB1 → ULN2803 if 12 V |
| CAUTION & WARNING | FLAMEOUT | lamp | MCP 0 (0x20) GPB2 → ULN2803 if 12 V |
| CAUTION & WARNING | ENG FAIL | lamp | MCP 0 (0x20) GPB3 → ULN2803 if 12 V |
| CAUTION & WARNING | RCS LOW | lamp | MCP 0 (0x20) GPB4 → ULN2803 if 12 V |
| CAUTION & WARNING | SINK RATE | lamp | MCP 0 (0x20) GPB5 → ULN2803 if 12 V |
| CAUTION & WARNING | CLOSING | lamp | MCP 0 (0x20) GPB6 → ULN2803 if 12 V |
| CAUTION & WARNING | THROTTLE | lamp | MCP 0 (0x20) GPB7 → ULN2803 if 12 V |
| CAUTION & WARNING | OVERHEAT | lamp | MCP 1 (0x21) GPA0 → ULN2803 if 12 V |
| CAUTION & WARNING | GEAR UP | lamp | MCP 1 (0x21) GPA1 → ULN2803 if 12 V |
| CAUTION & WARNING | ATT ERR | lamp | MCP 1 (0x21) GPA2 → ULN2803 if 12 V |
| CAUTION & WARNING | ABLATOR LOW | lamp | MCP 1 (0x21) GPA3 → ULN2803 if 12 V |
| CAUTION & WARNING | CHUTE | lamp | MCP 1 (0x21) GPA4 → ULN2803 if 12 V |
| CAUTION & WARNING | COMM LOST | lamp | MCP 1 (0x21) GPA5 → ULN2803 if 12 V |
| CAUTION & WARNING | LS LOW | lamp | MCP 1 (0x21) GPA6 → ULN2803 if 12 V |
| CAUTION & WARNING | LS OUT | lamp | MCP 1 (0x21) GPA7 → ULN2803 if 12 V |
| CAUTION & WARNING | LAMP TEST | button | MCP 1 (0x21) GPB0 to GND |
| CAUTION & WARNING | TONE | buzzer | GPIO 4 → transistor → piezo |
| ENGINE | ENG ARM (LED) | lamp | MCP 1 (0x21) GPB1 → ULN2803 if 12 V |
| ENGINE | ENG ARM | switch | MCP 1 (0x21) GPB2 to GND |
| ENGINE | THRUST % | 7-segment | MAX7219 0 digits 0..2 |
| ENGINE | CUTOFF | button | MCP 1 (0x21) GPB3 to GND |
| ENGINE | CUTOFF (lamp) | lamp | MCP 1 (0x21) GPB4 → ULN2803 if 12 V |
| ENGINE | THRUST LIMIT | analog | ADS1115 0 (0x48) A0, ends to 3.3 V and GND |
| ENGINE | STAGE ΔV M/S | 7-segment | MAX7219 0 digits 3..7 |
| ENGINE | STAGE FUEL | bar | MAX7219 1 rows 0..1 |
| ENGINE | TWR | 7-segment | MAX7219 1 digits 2..5 |
| ENGINE | TWR MAX | 7-segment | MAX7219 2 digits 0..3 |
| ENGINE | GIMBAL LOCK (LED) | lamp | MCP 1 (0x21) GPB5 → ULN2803 if 12 V |
| ENGINE | GIMBAL LOCK | switch | MCP 1 (0x21) GPB6 to GND |
| STAGING · ABORT | ENGINES | lamp | MCP 1 (0x21) GPB7 → ULN2803 if 12 V |
| STAGING · ABORT | SOLIDS | lamp | MCP 2 (0x22) GPA0 → ULN2803 if 12 V |
| STAGING · ABORT | DECOUPLE | lamp | MCP 2 (0x22) GPA1 → ULN2803 if 12 V |
| STAGING · ABORT | CLAMPS | lamp | MCP 2 (0x22) GPA2 → ULN2803 if 12 V |
| STAGING · ABORT | CHUTES | lamp | MCP 2 (0x22) GPA3 → ULN2803 if 12 V |
| STAGING · ABORT | FAIRING | lamp | MCP 2 (0x22) GPA4 → ULN2803 if 12 V |
| STAGING · ABORT | STAGE | 7-segment | MAX7219 1 digits 6..7 |
| STAGING · ABORT | STAGE ARM | switch | MCP 2 (0x22) GPA5 to GND |
| STAGING · ABORT | STAGE | button | MCP 2 (0x22) GPA6 to GND |
| STAGING · ABORT | STAGE (lamp) | lamp | MCP 2 (0x22) GPA7 → ULN2803 if 12 V |
| STAGING · ABORT | ENGINES | RGB rosette | GPIO 33 data → LEDs 0..8 of the chain: centre, then the ring clockwise from the top |
| STAGING · ABORT | THRUST | bar | MAX7219 2 rows 4..5 |
| STAGING · ABORT | ABORT ARM | switch | MCP 2 (0x22) GPB0 to GND |
| STAGING · ABORT | ABORT | button | MCP 2 (0x22) GPB1 to GND |
| STAGING · ABORT | ABORT (lamp) | lamp | MCP 2 (0x22) GPB2 → ULN2803 if 12 V |
