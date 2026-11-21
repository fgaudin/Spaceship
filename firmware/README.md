# Panel module firmware (draft)

One generic firmware for every I/O module: an Olimex ESP32-POE2 on the cockpit's MQTT bus, doing exactly what a
module of the virtual console does (`panels/virtual/panel.js`). It holds no logic: it publishes its controls' raw
positions and draws what the cockpit logic sends (protocol/topics.md). What is wired where comes from the module's
definition, `protocol/panels/<module>.json`, through a generated header: one build per module.

**A draft, written before any board exists.** It compiles for every module; it has not run on hardware.

```
  protocol/panels/eng.json ── tools/gen_module.py ──▶ generated/eng/module_config.h   (the tables the firmware uses)
                                                  └─▶ generated/eng/WIRING.md         (where each control is wired)
                                                  └─▶ modules.ini                     (a PlatformIO environment per module)
  src/main.cpp + generated/eng/module_config.h ── pio run -e eng ──▶ the eng module's firmware
```

## Building

```
python tools/gen_module.py --all        # after any change to protocol/panels/*.json
pio run -e eng                          # build (the PlatformIO install in ~/.platformio has it all)
pio run -e eng -t upload                # flash over USB; pio device monitor for the log
```

The broker's address is `MQTT_HOST` in `platformio.ini`. Glass modules (Raspberry Pi: the camera monitor, the FDAI,
the windows) and the throttle stand-in are not ESP32 boards and are skipped.

## How it works

| | On the board | On the bus |
|---|---|---|
| Toggle, guarded toggle | MCP23017 pin to GND, pulled up, debounced 20 ms | `panel/<bus>/in/<id>` `{"v": 0/1}`, retained |
| Button, lit button | the same | `{"v": 1}` on press, `{"v": 0}` on release, not retained |
| Rotary selector | one pin per position | `{"v": index}`, retained; between two positions the last one stays |
| Lever, knob | potentiometer 0..3.3 V on an ADS1115 channel, 100 steps, half a step of hysteresis | `{"v": 0..1}`, retained |
| Keypad | rows driven low one at a time, columns pulled up | `{"v": "<key>"}` when a key goes down, not retained |
| Lamp, LED, annunciator cell | MCP23017 output (through a ULN2803 for 12 V lamps); blink drawn locally, 0.5 s | `panel/<bus>/out/<id>` `{"on", "blink"}` |
| 7-segment display | MAX7219 digits (raw segments, the console's glyphs, right-aligned, the point on the digit before); blink 1 s | `{"text", "blank", "blink"}` |
| Bar | MAX7219 rows, 8 segments a row | `{"v": 0..1}` |
| LED matrix | MAX7219 rows, LEDs in reading order (one colour in this draft) | `{"rows": [...]}` |
| Alphanumeric | HT16K33, 8 characters a chip, left-aligned | `{"text", "blank", "blink"}` |
| Buzzer | GPIO 4, a 760 / 600 Hz warble through a transistor | `{"on"}` |

On connecting it publishes every switch, selector and lever position as it stands (a physical switch is the truth),
then `panel/<module>/status` every 5 s: `{"online", "fw", "config", "uptime"}`, with a last will `{"online": false}`.
`config` is the virtual console's fingerprint of the definition (FNV-1a), so a board running an old configuration
shows up against the console (checked: `eng` and `rdv` give the same hash as the console).

## The code

| File | What it is |
|---|---|
| `src/main.cpp` | Ethernet, MQTT, the scan of inputs, the rendering of outputs, the MAX7219 chain driver. |
| `src/controls.h` | The table types the generated header fills. |
| `tools/gen_module.py` | Gives each control a place on the module's chips, writes the header, the wiring table and `modules.ini`. |
| `generated/<module>/` | Its output: `module_config.h`, `WIRING.md`. |

## To check when the first board arrives

- The pins: Ethernet uses the `esp32-poe` board's variant; I2C on UEXT SDA 13 / SCL 16; SPI on UEXT SCK 14, MOSI 2,
  MISO 15, CS 5; the buzzer on GPIO 4. Check them against the ESP32-POE2's schematic (its module is a WROVER).
- Inputs QoS 1, retained, as the console's; whether the 5 ms scan of up to 8 expanders on I2C keeps up.
- Several modules (lnd, rdv) need 9 to 11 MAX7219 on one chain: fine for the SPI, worth checking for the 5 V rail
  (the console's budget, Left Alt).
- The engine matrix is one colour here; the console's has green, amber, red and white (two planes of LEDs, or RGB).
- The ADS1115's reference: a potentiometer on 3.3 V read against GAIN_ONE (4.096 V full scale).
- No over-the-air update yet: flashing is over USB.
