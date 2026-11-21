# sys: SYSTEMS

Generated from `protocol/panels/sys.json` by `firmware/tools/gen_module.py`. Chips: 2 MCP23017, 0 ADS1115, 2 MAX7219, 0 HT16K33.

| Panel | Control | Kind | Where |
|---|---|---|---|
| TIME WARP | RATE × | 7-segment | MAX7219 0 digits 0..5 |
| TIME WARP | WARP | lamp | MCP 0 (0x20) GPA0 → ULN2803 if 12 V |
| TIME WARP | ◂ SLOWER | button | MCP 0 (0x20) GPA1 to GND |
| TIME WARP | FASTER ▸ | button | MCP 0 (0x20) GPA2 to GND |
| TIME WARP | WARP TO EVT | button | MCP 0 (0x20) GPA3 to GND |
| TIME WARP | STOP WARP | button | MCP 0 (0x20) GPA4 to GND |
| TIME WARP | PAUSE (LED) | lamp | MCP 0 (0x20) GPA5 → ULN2803 if 12 V |
| TIME WARP | PAUSE | switch | MCP 0 (0x20) GPA6 to GND |
| LIGHTS · FAN | FAN | switch | MCP 0 (0x20) GPA7 to GND |
| LIGHTS · FAN | CABIN | switch | MCP 0 (0x20) GPB0 to GND |
| LIGHTS · FAN | BACKLIGHT | switch | MCP 0 (0x20) GPB1 to GND |
| LIGHTS · FAN | EXTERNAL (LED) | lamp | MCP 0 (0x20) GPB2 → ULN2803 if 12 V |
| LIGHTS · FAN | EXTERNAL | switch | MCP 0 (0x20) GPB3 to GND |
| EVENT TIMER | MIN.SEC | 7-segment | MAX7219 1 digits 0..4 |
| EVENT TIMER | SOURCE MAN | rotary position | MCP 0 (0x20) GPB4 to GND |
| EVENT TIMER | SOURCE TIG | rotary position | MCP 0 (0x20) GPB5 to GND |
| EVENT TIMER | SOURCE APO | rotary position | MCP 0 (0x20) GPB6 to GND |
| EVENT TIMER | SOURCE PERI | rotary position | MCP 0 (0x20) GPB7 to GND |
| EVENT TIMER | SOURCE SOI | rotary position | MCP 1 (0x21) GPA0 to GND |
| EVENT TIMER | RUN | lamp | MCP 1 (0x21) GPA1 → ULN2803 if 12 V |
| EVENT TIMER | START | button | MCP 1 (0x21) GPA2 to GND |
| EVENT TIMER | STOP | button | MCP 1 (0x21) GPA3 to GND |
| EVENT TIMER | RESET | button | MCP 1 (0x21) GPA4 to GND |
| EVENT TIMER | COUNT DOWN | switch | MCP 1 (0x21) GPA5 to GND |
| EVENT TIMER | MIN + | button | MCP 1 (0x21) GPA6 to GND |
| EVENT TIMER | SEC +10 | button | MCP 1 (0x21) GPA7 to GND |
| SAVE | QUICK SAVE | button | MCP 1 (0x21) GPB0 to GND |
| SAVE | QUICK LOAD | button | MCP 1 (0x21) GPB1 to GND |
| SAVE | REVERT ARM | switch | MCP 1 (0x21) GPB2 to GND |
| SAVE | REVERT TO LAUNCH | button | MCP 1 (0x21) GPB3 to GND |
| SAVE | REVERT TO LAUNCH (lamp) | lamp | MCP 1 (0x21) GPB4 → ULN2803 if 12 V |
