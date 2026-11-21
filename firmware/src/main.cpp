// Generic panel module firmware: an Olimex ESP32-POE2 on the cockpit's MQTT bus, the same node as a module of the
// virtual console (panels/virtual/panel.js). No logic: it publishes its controls' raw positions and draws what the
// cockpit logic tells it (protocol/topics.md, panel/<bus>/in|out/*). Which control is on which chip pin comes from
// generated/<module>/module_config.h (firmware/tools/gen_module.py), one build per module.
//
// DRAFT: written before any board exists. It compiles; it has not run. See firmware/README.md for what to check.

#include <Arduino.h>
#include <ETH.h>
#include <SPI.h>
#include <Wire.h>
#include <MQTT.h>
#include <ArduinoJson.h>
#include <Adafruit_MCP23X17.h>
#include <Adafruit_ADS1X15.h>
#include <Adafruit_LEDBackpack.h>

#include "module_config.h"

// ---------- the board (Olimex ESP32-POE / POE2: check against the board's schematic) ----------
#ifndef MQTT_HOST
#define MQTT_HOST "192.168.1.10"         // the cockpit machine; a build flag sets it
#endif
#ifndef MQTT_PORT
#define MQTT_PORT 1883
#endif
static const int I2C_SDA = 13, I2C_SCL = 16;                    // UEXT
static const int SPI_SCK = 14, SPI_MOSI = 2, SPI_MISO = 15, MAX7219_CS = 5;   // UEXT
static const uint32_t I2C_HZ = 400000;

// ---------- timing ----------
static const uint32_t SCAN_EVERY_MS = 5;           // switches and buttons
static const uint8_t DEBOUNCE_SAMPLES = 4;         // stable this many scans: 20 ms
static const uint32_t KEYPAD_EVERY_MS = 10;
static const uint32_t ANALOG_EVERY_MS = 10;        // one channel each time, round robin
static const uint32_t RENDER_EVERY_MS = 20;
static const uint32_t STATUS_EVERY_MS = 5000;
static const uint32_t LAMP_BLINK_HALF_MS = 250;    // as the console's lamps: 0.5 s
static const uint32_t DISPLAY_BLINK_HALF_MS = 500; // as its displays: 1 s
static const uint8_t MAX7219_INTENSITY = 8;        // 0..15
static const uint16_t BUZZER_HZ = 760, BUZZER_WARBLE_HZ = 600;

// ---------- hardware ----------
static WiFiClient net;
static MQTTClient mqtt(2048);                      // a matrix payload is the largest: 9 rows of 9 characters
static bool ethernetUp = false;
static Adafruit_MCP23X17 expanders[MCP_COUNT ? MCP_COUNT : 1];
static Adafruit_ADS1115 adcs[ADS_COUNT ? ADS_COUNT : 1];
static Adafruit_AlphaNum4 alphaChips[HT16K33_COUNT ? HT16K33_COUNT : 1];
static uint8_t maxFrame[MAX7219_COUNT ? MAX7219_COUNT : 1][8];   // row bytes, MAX7219 no-decode: DP A B C D E F G
static uint16_t outputLatch[MCP_COUNT ? MCP_COUNT : 1];          // lamps and keypad rows, per expander
static uint16_t outputMask[MCP_COUNT ? MCP_COUNT : 1];           // which pins are outputs

// ---------- input state ----------
struct Debounced { bool stable, last; uint8_t count; };
static Debounced pins[MCP_COUNT * 16 ? MCP_COUNT * 16 : 1];
static int8_t rotaryPosition[ROTARIES_COUNT ? ROTARIES_COUNT : 1];
static int32_t analogStep[ANALOGS_COUNT ? ANALOGS_COUNT : 1];
static char keypadDown[KEYPADS_COUNT ? KEYPADS_COUNT : 1][8];   // the key down, "" for none
static uint8_t analogNext = 0;

// ---------- output state (what the cockpit logic last said) ----------
struct LampState { bool on, blink; };
struct TextState { char text[24]; bool blank, blink; };
static LampState lamps[LAMPS_COUNT ? LAMPS_COUNT : 1];
static TextState seg7Text[SEG7S_COUNT ? SEG7S_COUNT : 1];
static float barValue[BARS_COUNT ? BARS_COUNT : 1];
static char matrixLeds[MATRICES_COUNT ? MATRICES_COUNT : 1][128];
static TextState alphaText[ALPHAS_COUNT ? ALPHAS_COUNT : 1];
static bool buzzerOn[BUZZERS_COUNT ? BUZZERS_COUNT : 1];
static bool outputsDirty = true;

// =====================================================================================================================
// MAX7219 chain: the first chip on the wire is the last to receive; one register of every chip per CS pulse
// =====================================================================================================================
static void maxWriteAll(uint8_t reg, const uint8_t *perChip) {
  digitalWrite(MAX7219_CS, LOW);
  for (int chip = MAX7219_COUNT - 1; chip >= 0; chip--) {
    SPI.transfer(reg);
    SPI.transfer(perChip ? perChip[chip] : 0);
  }
  digitalWrite(MAX7219_CS, HIGH);
}

static void maxSetAll(uint8_t reg, uint8_t value) {
  uint8_t values[MAX7219_COUNT ? MAX7219_COUNT : 1];
  memset(values, value, sizeof(values));
  maxWriteAll(reg, values);
}

static void maxBegin() {
  if (!MAX7219_COUNT) return;
  pinMode(MAX7219_CS, OUTPUT);
  digitalWrite(MAX7219_CS, HIGH);
  SPI.begin(SPI_SCK, SPI_MISO, SPI_MOSI, MAX7219_CS);
  SPI.beginTransaction(SPISettings(4000000, MSBFIRST, SPI_MODE0));
  maxSetAll(0x0F, 0);                 // display test off
  maxSetAll(0x09, 0);                 // no decode: raw segments
  maxSetAll(0x0B, 7);                 // scan all 8 digits
  maxSetAll(0x0A, MAX7219_INTENSITY);
  maxSetAll(0x0C, 1);                 // out of shutdown
}

static void maxFlush() {
  if (!MAX7219_COUNT) return;
  for (uint8_t row = 0; row < 8; row++) {
    uint8_t values[MAX7219_COUNT];
    for (uint8_t chip = 0; chip < MAX7219_COUNT; chip++) values[chip] = maxFrame[chip][row];
    maxWriteAll(row + 1, values);
  }
}

// a glyph as MAX7219 segments (bit 7 DP, 6 A, 5 B, 4 C, 3 D, 2 E, 1 F, 0 G), the console's set (seven_segment.js)
static uint8_t glyph(char c) {
  switch (c) {
    case '0': return 0x7E; case '1': return 0x30; case '2': return 0x6D; case '3': return 0x79; case '4': return 0x33;
    case '5': return 0x5B; case '6': return 0x5F; case '7': return 0x70; case '8': return 0x7F; case '9': return 0x7B;
    case '-': return 0x01; case '+': return 0x01;    // no vertical bar on a plain digit: a minus sign
    case '_': return 0x08; case ' ': return 0x00;
    case 'A': return 0x77; case 'C': return 0x4E; case 'E': return 0x4F; case 'F': return 0x47; case 'H': return 0x37;
    case 'L': return 0x0E; case 'P': return 0x67; case 'S': return 0x5B;
    case 'b': return 0x1F; case 'd': return 0x3D; case 'n': return 0x15; case 'o': return 0x1D; case 'r': return 0x05;
    case 't': return 0x0F; case 'u': return 0x1C; case 'y': return 0x3B;
    default: return 0x01;                             // unknown: the middle bar, as the console
  }
}

// right-aligned, a decimal point on the digit before it, the left end lost when too long (seven_segment.js)
static void renderSeg7(const Seg7Config &config, const TextState &state, bool visible) {
  uint8_t cells[24];
  uint8_t count = 0;
  if (!state.blank && visible) {
    for (const char *c = state.text; *c && count < sizeof(cells); c++) {
      if (*c == '.' && count && !(cells[count - 1] & 0x80)) cells[count - 1] |= 0x80;
      else if (*c == '.') cells[count++] = 0x80;
      else cells[count++] = glyph(*c);
    }
  }
  for (uint8_t digit = 0; digit < config.digits; digit++) {
    int source = (int)count - (int)config.digits + digit;
    maxFrame[config.chip][config.firstDigit + digit] = source >= 0 ? cells[source] : 0;
  }
}

// LED k of a bar or matrix: row firstRow + k / 8 (running onto the next chips), segment bit 7 - k % 8
static void setLed(uint8_t chip, uint8_t firstRow, uint16_t k, bool lit) {
  uint16_t row = firstRow + k / 8;
  uint8_t onChip = chip + row / 8, bit = 0x80 >> (k % 8);
  if (onChip >= MAX7219_COUNT) return;
  if (lit) maxFrame[onChip][row % 8] |= bit; else maxFrame[onChip][row % 8] &= ~bit;
}

// =====================================================================================================================
// Expanders
// =====================================================================================================================
static void expanderOutput(uint8_t pin, bool high) {
  uint16_t bit = 1u << (pin % 16);
  if (high) outputLatch[pin / 16] |= bit; else outputLatch[pin / 16] &= ~bit;
}

static void expandersBegin() {
  for (uint8_t chip = 0; chip < MCP_COUNT; chip++) {
    if (!expanders[chip].begin_I2C(0x20 + chip)) Serial.printf("MCP23017 0x%02X missing\n", 0x20 + chip);
    for (uint8_t bit = 0; bit < 16; bit++) expanders[chip].pinMode(bit, INPUT_PULLUP);   // inputs unless said below
  }
  auto output = [](uint8_t pin, bool level) {
    expanders[pin / 16].pinMode(pin % 16, OUTPUT);
    outputMask[pin / 16] |= 1u << (pin % 16);
    expanderOutput(pin, level);
  };
  for (uint8_t i = 0; i < LAMPS_COUNT; i++) output(LAMPS[i].pin, false);
  for (uint8_t k = 0; k < KEYPADS_COUNT; k++)
    for (uint8_t r = 0; r < KEYPADS[k].rows; r++) output(KEYPADS[k].firstRowPin + r, true);   // rows idle high
  for (uint8_t chip = 0; chip < MCP_COUNT; chip++) expanders[chip].writeGPIOAB(outputLatch[chip]);
}

static void expandersFlush() {
  for (uint8_t chip = 0; chip < MCP_COUNT; chip++) expanders[chip].writeGPIOAB(outputLatch[chip]);
}

// =====================================================================================================================
// Publishing
// =====================================================================================================================
static void publishValue(const char *topic, const char *json, bool retained) {
  if (mqtt.connected()) mqtt.publish(topic, json, retained, 1);
}

static void publishNumber(const char *topic, float value, bool retained) {
  char json[32];
  if (value == (int)value) snprintf(json, sizeof(json), "{\"v\":%d}", (int)value);
  else snprintf(json, sizeof(json), "{\"v\":%.3g}", value);
  publishValue(topic, json, retained);
}

static void publishStatus() {
  char json[128];
  snprintf(json, sizeof(json), "{\"online\":true,\"fw\":\"%s\",\"config\":\"%s\",\"uptime\":%lu}", FW_VERSION,
           CONFIG_HASH, (unsigned long)(millis() / 1000));
  publishValue(STATUS_TOPIC, json, true);
}

// every retained input as it stands: a physical switch is the truth, nothing to take back from the broker
static void publishAllPositions() {
  for (uint8_t i = 0; i < SWITCHES_COUNT; i++)
    if (!SWITCHES[i].momentary) publishNumber(SWITCHES[i].topic, pins[SWITCHES[i].pin].stable ? 1 : 0, true);
  for (uint8_t i = 0; i < ROTARIES_COUNT; i++)
    if (rotaryPosition[i] >= 0) publishNumber(ROTARIES[i].topic, rotaryPosition[i], true);
  for (uint8_t i = 0; i < ANALOGS_COUNT; i++)
    if (analogStep[i] >= 0) publishNumber(ANALOGS[i].topic, (float)analogStep[i] / ANALOGS[i].steps, true);
}

// =====================================================================================================================
// Inputs
// =====================================================================================================================
static void scanSwitches() {
  for (uint8_t chip = 0; chip < MCP_COUNT; chip++) {
    uint16_t levels = expanders[chip].readGPIOAB();
    for (uint8_t bit = 0; bit < 16; bit++) {
      if (outputMask[chip] & (1u << bit)) continue;
      Debounced &pin = pins[chip * 16 + bit];
      bool closed = !(levels & (1u << bit));          // to GND when closed
      if (closed != pin.last) { pin.last = closed; pin.count = 0; }
      else if (pin.count < DEBOUNCE_SAMPLES) pin.count++;
    }
  }
  for (uint8_t i = 0; i < SWITCHES_COUNT; i++) {
    Debounced &pin = pins[SWITCHES[i].pin];
    if (pin.count >= DEBOUNCE_SAMPLES && pin.last != pin.stable) {
      pin.stable = pin.last;
      publishNumber(SWITCHES[i].topic, pin.stable ? 1 : 0, !SWITCHES[i].momentary);
    }
  }
  for (uint8_t i = 0; i < ROTARIES_COUNT; i++) {
    int8_t position = -1;
    for (uint8_t p = 0; p < ROTARIES[i].positions; p++) {
      Debounced &pin = pins[ROTARIES[i].firstPin + p];
      if (pin.count >= DEBOUNCE_SAMPLES && pin.last) { position = p; break; }
    }
    if (position >= 0 && position != rotaryPosition[i]) {      // between two positions: keep the last one
      rotaryPosition[i] = position;
      publishNumber(ROTARIES[i].topic, position, true);
    }
  }
}

static void scanKeypads() {
  for (uint8_t k = 0; k < KEYPADS_COUNT; k++) {
    const KeypadConfig &pad = KEYPADS[k];
    const char *down = nullptr;
    for (uint8_t r = 0; r < pad.rows && !down; r++) {
      expanderOutput(pad.firstRowPin + r, false);
      expandersFlush();
      for (uint8_t c = 0; c < pad.columns; c++) {
        uint8_t pin = pad.firstColumnPin + c;
        if (!(expanders[pin / 16].readGPIOAB() & (1u << (pin % 16)))) {
          const char *key = pad.keys[r * pad.columns + c];
          if (key[0]) { down = key; break; }
        }
      }
      expanderOutput(pad.firstRowPin + r, true);
    }
    expandersFlush();
    // a key is sent once, when it goes down (the console sends the key, not its release)
    if (down && strcmp(down, keypadDown[k]) != 0) {
      char json[24];
      snprintf(json, sizeof(json), "{\"v\":\"%s\"}", down);
      publishValue(pad.topic, json, false);
    }
    strncpy(keypadDown[k], down ? down : "", sizeof(keypadDown[k]) - 1);
  }
}

static void scanAnalog() {
  if (!ANALOGS_COUNT) return;
  const AnalogConfig &config = ANALOGS[analogNext];
  int16_t raw = adcs[config.chip].readADC_SingleEnded(config.channel);
  // GAIN_ONE: ±4.096 V full scale; the potentiometer spans 0..3.3 V
  float value = constrain(raw / (32767.0f * 3.3f / 4.096f), 0.0f, 1.0f);
  float scaled = value * config.steps;
  int32_t &step = analogStep[analogNext];
  // half a step of hysteresis: a wiper resting on a boundary does not flicker
  if (step < 0 || scaled > step + 0.75f || scaled < step - 0.75f) {
    int32_t next = lroundf(scaled);
    if (next != step) {
      step = next;
      publishNumber(config.topic, (float)step / config.steps, true);
    }
  }
  analogNext = (analogNext + 1) % ANALOGS_COUNT;
}

// =====================================================================================================================
// Outputs: what the cockpit logic says, drawn locally (blinking included)
// =====================================================================================================================
static void copyText(TextState &state, JsonDocument &doc) {
  strncpy(state.text, doc["text"] | "", sizeof(state.text) - 1);
  state.text[sizeof(state.text) - 1] = 0;
  state.blank = doc["blank"] | false;
  state.blink = doc["blink"] | false;
}

static void onMessage(String &topic, String &payload) {
  JsonDocument doc;
  if (deserializeJson(doc, payload)) return;
  const char *t = topic.c_str();
  outputsDirty = true;
  for (uint8_t i = 0; i < LAMPS_COUNT; i++)
    if (!strcmp(t, LAMPS[i].topic)) { lamps[i] = {doc["on"] | false, doc["blink"] | false}; }
  for (uint8_t i = 0; i < SEG7S_COUNT; i++)
    if (!strcmp(t, SEG7S[i].topic)) copyText(seg7Text[i], doc);
  for (uint8_t i = 0; i < ALPHAS_COUNT; i++)
    if (!strcmp(t, ALPHAS[i].topic)) copyText(alphaText[i], doc);
  for (uint8_t i = 0; i < BARS_COUNT; i++)
    if (!strcmp(t, BARS[i].topic)) barValue[i] = doc["v"] | 0.0f;
  for (uint8_t i = 0; i < MATRICES_COUNT; i++) {
    if (strcmp(t, MATRICES[i].topic)) continue;
    // one character per LED: g, a, r, w lit (one colour on this draft), '.' off
    JsonArray rows = doc["rows"].as<JsonArray>();
    for (uint8_t r = 0; r < MATRICES[i].rows; r++) {
      const char *row = r < rows.size() ? (const char *)(rows[r] | "") : "";
      for (uint8_t c = 0; c < MATRICES[i].columns; c++) {
        uint16_t k = r * MATRICES[i].columns + c;
        if (k < sizeof(matrixLeds[i])) matrixLeds[i][k] = c < strlen(row) ? row[c] : '.';
      }
    }
  }
  for (uint8_t i = 0; i < BUZZERS_COUNT; i++)
    if (!strcmp(t, BUZZERS[i].topic)) buzzerOn[i] = doc["on"] | false;
}

static void render() {
  uint32_t now = millis();
  bool lampPhase = (now / LAMP_BLINK_HALF_MS) % 2 == 0;
  bool displayPhase = (now / DISPLAY_BLINK_HALF_MS) % 2 == 0;
  for (uint8_t i = 0; i < LAMPS_COUNT; i++)
    expanderOutput(LAMPS[i].pin, lamps[i].on && (!lamps[i].blink || lampPhase));
  for (uint8_t i = 0; i < SEG7S_COUNT; i++)
    renderSeg7(SEG7S[i], seg7Text[i], !seg7Text[i].blink || displayPhase);
  for (uint8_t i = 0; i < BARS_COUNT; i++) {
    uint8_t lit = lroundf(constrain(barValue[i], 0.0f, 1.0f) * BARS[i].segments);
    for (uint8_t s = 0; s < BARS[i].segments; s++) setLed(BARS[i].chip, BARS[i].firstRow, s, s < lit);
  }
  for (uint8_t i = 0; i < MATRICES_COUNT; i++)
    for (uint16_t k = 0; k < MATRICES[i].rows * MATRICES[i].columns; k++)
      setLed(MATRICES[i].chip, MATRICES[i].firstRow, k, matrixLeds[i][k] && matrixLeds[i][k] != '.');
  for (uint8_t i = 0; i < ALPHAS_COUNT; i++) {
    const AlphaConfig &config = ALPHAS[i];
    bool visible = !alphaText[i].blank && (!alphaText[i].blink || displayPhase);
    size_t length = visible ? strlen(alphaText[i].text) : 0;
    for (uint8_t c = 0; c < config.chars; c++) {
      uint8_t at = config.firstChar + c;
      alphaChips[at / 8].writeDigitAscii(at % 8, c < length ? alphaText[i].text[c] : ' ');   // left-aligned
    }
  }
  for (uint8_t chip = 0; chip < HT16K33_COUNT; chip++) alphaChips[chip].writeDisplay();
  for (uint8_t i = 0; i < BUZZERS_COUNT; i++) {
    if (buzzerOn[i]) ledcWriteTone(0, (now / 167) % 2 ? BUZZER_HZ : BUZZER_WARBLE_HZ);    // a 3 Hz warble
    else ledcWriteTone(0, 0);
  }
  expandersFlush();
  maxFlush();
  outputsDirty = false;
}

// =====================================================================================================================
// Network
// =====================================================================================================================
static void onNetworkEvent(arduino_event_id_t event) {
  if (event == ARDUINO_EVENT_ETH_GOT_IP) { ethernetUp = true; Serial.printf("ethernet: %s\n", ETH.localIP().toString().c_str()); }
  if (event == ARDUINO_EVENT_ETH_DISCONNECTED) ethernetUp = false;
}

static void connectBus() {
  static uint32_t lastTry = 0;
  if (mqtt.connected() || !ethernetUp || millis() - lastTry < 2000) return;
  lastTry = millis();
  mqtt.setWill(STATUS_TOPIC, "{\"online\":false}", true, 1);
  if (!mqtt.connect("panel-" MODULE_ID)) { Serial.println("mqtt: not connected"); return; }
  for (const char *bus : BUSES) {
    String topic = String("panel/") + bus + "/out/#";
    mqtt.subscribe(topic, 1);                      // retained: the displays come back as the cockpit left them
  }
  publishStatus();
  publishAllPositions();
  Serial.println("mqtt: connected");
}

// =====================================================================================================================
void setup() {
  Serial.begin(115200);
  Serial.printf("module %s, %s, config %s\n", MODULE_ID, FW_VERSION, CONFIG_HASH);
  memset(rotaryPosition, -1, sizeof(rotaryPosition));
  for (auto &step : analogStep) step = -1;
  Wire.begin(I2C_SDA, I2C_SCL, I2C_HZ);
  expandersBegin();
  for (uint8_t chip = 0; chip < ADS_COUNT; chip++) {
    adcs[chip].begin(0x48 + chip);
    adcs[chip].setGain(GAIN_ONE);
    adcs[chip].setDataRate(RATE_ADS1115_860SPS);
  }
  for (uint8_t chip = 0; chip < HT16K33_COUNT; chip++) alphaChips[chip].begin(0x70 + chip);
  maxBegin();
  for (uint8_t i = 0; i < BUZZERS_COUNT; i++) { ledcSetup(0, BUZZER_HZ, 8); ledcAttachPin(BUZZERS[i].gpio, 0); }
  for (uint8_t i = 0; i < 8; i++) { scanSwitches(); delay(SCAN_EVERY_MS); }      // positions known before the bus
  WiFi.onEvent(onNetworkEvent);
  ETH.begin();
  mqtt.begin(MQTT_HOST, MQTT_PORT, net);
  mqtt.onMessage(onMessage);
}

void loop() {
  static uint32_t lastScan = 0, lastKeypad = 0, lastAnalog = 0, lastRender = 0, lastStatus = 0;
  uint32_t now = millis();
  connectBus();
  mqtt.loop();
  if (now - lastScan >= SCAN_EVERY_MS) { lastScan = now; scanSwitches(); }
  if (KEYPADS_COUNT && now - lastKeypad >= KEYPAD_EVERY_MS) { lastKeypad = now; scanKeypads(); }
  if (ANALOGS_COUNT && now - lastAnalog >= ANALOG_EVERY_MS) { lastAnalog = now; scanAnalog(); }
  if (now - lastRender >= RENDER_EVERY_MS) { lastRender = now; render(); }
  if (now - lastStatus >= STATUS_EVERY_MS) { lastStatus = now; publishStatus(); }
}
