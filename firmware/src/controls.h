// The tables a module's generated configuration fills in (generated/<module>/module_config.h). Expander pins are
// numbered across the chain: pin 37 is the 6th pin of the 3rd MCP23017 (0x22, GPA5).
#pragma once
#include <stdint.h>

struct SwitchConfig {       // a toggle, guarded toggle, button or lit button's switch: to GND, pulled up
  const char *topic;
  uint8_t pin;
  bool momentary;           // buttons: 1 on press and 0 on release, not retained; switches: 0/1 retained
};

struct RotaryConfig {       // a selector: one pin per position, to GND on its position
  const char *topic;
  uint8_t firstPin;
  uint8_t positions;
};

struct AnalogConfig {       // a lever or knob: a potentiometer between 3.3 V and GND, its wiper on an ADS1115
  const char *topic;
  uint8_t chip;
  uint8_t channel;
  uint16_t steps;           // the value is sent in this many steps (100: 1 %)
};

struct KeypadConfig {       // a key matrix: rows driven low one at a time, columns pulled up
  const char *topic;
  uint8_t firstRowPin, rows, firstColumnPin, columns;
  const char *const *keys;  // rows × columns, "" where there is no key
};

struct LampConfig {         // a lamp, indicator LED or annunciator cell: an expander pin, through a ULN2803 above 5 V
  const char *topic;
  uint8_t pin;
};

struct Seg7Config {         // a 7-segment display on a MAX7219 of the chain, digits left to right
  const char *topic;
  uint8_t chip, firstDigit, digits;
};

struct BarConfig {          // a bar graph: segments on MAX7219 rows, 8 a row
  const char *topic;
  uint8_t chip, firstRow;
  uint8_t segments;
};

struct MatrixConfig {       // an LED matrix, its LEDs in reading order over MAX7219 rows (may run onto the next chip)
  const char *topic;
  uint8_t chip, firstRow, rows, columns;
};

struct AlphaConfig {        // an alphanumeric display: characters on HT16K33 chips, 8 a chip
  const char *topic;
  uint8_t firstChar, chars;
};

struct BuzzerConfig {
  const char *topic;
  uint8_t gpio;
};

struct RosetteConfig {      // the engine rosette: addressable RGB LEDs on the RGB chain, the centre first, then the ring
  const char *topic;
  uint8_t firstLed, leds;
};
