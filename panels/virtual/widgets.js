/* The widgets of a virtual panel: one builder per item type of a panel definition (protocol/panels/<id>.json).

   A builder returns the DOM nodes to show and registers what the bus needs to know:
     registry.outputs      output name → function(payload) that draws it
     registry.inputs       input name  → { read(), restore(value), retained, press?(down), nudge?(amount) }
     registry.keypadKeys   key         → function() that presses it
   Inputs are published through publishInput(name, value, retained). */

import { createSevenSegmentDisplay } from './seven_segment.js';

export function createElement(tag, className, properties = {}) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  Object.assign(element, properties);
  return element;
}

/* A lamp of any kind: lit, and blinking when asked. */
function showLamp(element, payload) {
  element.classList.toggle('lit', Boolean(payload.on));
  element.classList.toggle('blink', Boolean(payload.on) && Boolean(payload.blink));
}

export function createWidgetBuilders(registry, publishInput) {
  const { outputs, inputs, keypadKeys } = registry;

  /* The bat-handle switch shared by plain and guarded toggles. */
  function createToggleSwitch(item, onFlip) {
    const button = createElement('button', 'toggle', { type: 'button', title: item.label });
    button.innerHTML = '<span class="nut"></span><span class="bat"></span><span class="pos on">ON</span><span class="pos off">OFF</span>';
    let position = item.default ?? 0;
    const set = (value) => {
      position = value ? 1 : 0;
      button.setAttribute('aria-pressed', position ? 'true' : 'false');
    };
    set(position);
    button.addEventListener('click', () => {
      if (button.disabled) return;
      set(!position);
      onFlip(position);
    });
    return { node: button, read: () => position, set };
  }

  /* The indicator LED drawn above a switch: it shows the game's state and blinks when the switch disagrees. */
  function createIndicatorFor(item) {
    if (!item.led) return [];
    const led = createElement('div', `led ${item.led.color || 'green'}`, { title: `${item.label} indicator` });
    outputs.set(item.led.out, (payload) => showLamp(led, payload));
    return [led];
  }

  const builders = {
    toggle(item) {
      const toggle = createToggleSwitch(item, (position) => publishInput(item.in, position, true));
      inputs.set(item.in, { read: toggle.read, restore: toggle.set, retained: true });
      return [...createIndicatorFor(item), toggle.node];
    },

    /* A toggle under a red cover: the cover must be opened first, and closing it pushes the switch off. */
    guarded_toggle(item) {
      const wrapper = createElement('div', 'guarded');
      const toggle = createToggleSwitch(item, (position) => publishInput(item.in, position, true));
      const guard = createElement('button', 'guard', { type: 'button', title: `${item.label} guard` });
      let guardOpen = false;
      const setGuardOpen = (open) => {
        guardOpen = open;
        wrapper.classList.toggle('open', open);
        toggle.node.disabled = !open;
        if (!open && toggle.read()) {
          toggle.set(0);
          publishInput(item.in, 0, true);
        }
      };
      guard.addEventListener('click', () => setGuardOpen(!guardOpen));
      wrapper.append(toggle.node, guard);
      setGuardOpen(false);
      const restore = (position) => {
        if (position) setGuardOpen(true);
        toggle.set(position);
      };
      inputs.set(item.in, { read: toggle.read, restore, retained: true });
      return [...createIndicatorFor(item), wrapper];
    },

    button(item) {
      return builders.lamp_button({ ...item, plain: true });
    },

    /* A momentary push button, lit from behind when it has an output. It publishes 1 while held and 0 on release. */
    lamp_button(item) {
      const button = createElement('button', `btn ${item.plain ? 'plain' : item.color || 'amber'}`,
        { type: 'button', textContent: item.label });
      let held = false;
      const press = (down) => {
        if (down === held) return;
        held = down;
        button.classList.toggle('down', down);
        publishInput(item.in, down ? 1 : 0, false);
      };
      const isActivationKey = (event) => event.key === 'Enter' || event.key === ' ';
      button.addEventListener('pointerdown', (event) => { button.setPointerCapture(event.pointerId); press(true); });
      button.addEventListener('pointerup', () => press(false));
      button.addEventListener('pointercancel', () => press(false));
      button.addEventListener('keydown', (event) => { if (isActivationKey(event)) { event.preventDefault(); press(true); } });
      button.addEventListener('keyup', (event) => { if (isActivationKey(event)) press(false); });
      inputs.set(item.in, { read: () => (held ? 1 : 0), restore: () => {}, retained: false, press });
      if (item.out) outputs.set(item.out, (payload) => showLamp(button, payload));
      return [button];
    },

    led(item) {
      const led = createElement('div', `led ${item.color || 'green'}`);
      outputs.set(item.out, (payload) => showLamp(led, payload));
      return [led];
    },

    /* A grid of legend lamps (caution and warning, status lights). */
    annunciator(item) {
      const grid = createElement('div', 'annun');
      grid.style.gridTemplateColumns = `repeat(${item.cols || 3}, 1fr)`;
      for (const cellDefinition of item.cells) {
        const cell = createElement('div', `cell ${cellDefinition.color || 'amber'}`, { textContent: cellDefinition.label });
        outputs.set(cellDefinition.out, (payload) => showLamp(cell, payload));
        grid.appendChild(cell);
      }
      return [grid];
    },

    seg7(item) {
      const display = createSevenSegmentDisplay(item.digits, item.color);
      outputs.set(item.out, display.render);
      return [display.node];
    },

    /* An LED bar graph: payload {v: 0..1}. The top segments are amber then red. */
    bar(item) {
      const bar = createElement('div', 'bar');
      const segmentCount = item.segments || 10;
      const segments = [];
      for (let index = 0; index < segmentCount; index++) {
        const segment = createElement('i');
        if (index >= segmentCount * 0.7) segment.classList.add('hi');
        if (index === segmentCount - 1) segment.classList.add('top');
        bar.appendChild(segment);
        segments.push(segment);
      }
      outputs.set(item.out, (payload) => {
        const litCount = Math.round((payload.v || 0) * segmentCount);
        segments.forEach((segment, index) => segment.classList.toggle('on', index < litCount));
      });
      return [bar];
    },

    /* A rotary selector: click for the next position; shift-click, right-click or the wheel to go back. */
    rotary(item) {
      const wrapper = createElement('div', 'rotary-wrap');
      const knob = createElement('button', 'rotary',
        { type: 'button', title: `${item.label} (click: next, shift-click or wheel: back)` });
      const pointer = createElement('span', 'ptr');
      knob.appendChild(pointer);
      const positionCount = item.positions.length;
      const sweepDegrees = Math.min(270, 45 * (positionCount - 1));
      const angleOf = (index) => -sweepDegrees / 2 + (positionCount > 1 ? sweepDegrees * index / (positionCount - 1) : 0);
      const legends = item.positions.map((label, index) => {
        const radians = angleOf(index) * Math.PI / 180;
        const legend = createElement('span', 'tick', { textContent: label });
        legend.style.left = `${50 + 46 * Math.sin(radians)}%`;
        legend.style.top = `${56 - 46 * Math.cos(radians)}%`;
        wrapper.appendChild(legend);
        return legend;
      });
      let position = item.default ?? 0;
      const set = (value) => {
        position = ((value % positionCount) + positionCount) % positionCount;
        pointer.style.transform = `rotate(${angleOf(position)}deg)`;
        legends.forEach((legend, index) => legend.classList.toggle('sel', index === position));
      };
      const turn = (steps) => { set(position + steps); publishInput(item.in, position, true); };
      knob.addEventListener('click', (event) => turn(event.shiftKey ? -1 : 1));
      knob.addEventListener('contextmenu', (event) => { event.preventDefault(); turn(-1); });
      knob.addEventListener('wheel', (event) => { event.preventDefault(); turn(event.deltaY > 0 ? 1 : -1); }, { passive: false });
      knob.addEventListener('keydown', (event) => {
        if (event.key === 'ArrowRight') turn(1);
        if (event.key === 'ArrowLeft') turn(-1);
      });
      wrapper.appendChild(knob);
      set(position);
      inputs.set(item.in, { read: () => position, restore: set, retained: true });
      return [wrapper];
    },

    /* A lever or knob with a continuous value, 0 to 1 (throttle, thrust limiter). */
    pot(item) {
      const MIN_MS_BETWEEN_PUBLISHES = 50;      // while dragging
      const slider = createElement('input', 'pot',
        { type: 'range', min: 0, max: 1, step: 0.01, value: item.default ?? 0, title: item.label });
      const readout = createElement('div', 'pot-val');
      const showValue = () => { readout.textContent = `${Math.round(slider.value * 100)} %`; };
      const publish = () => publishInput(item.in, Number(slider.value), true);
      let lastPublished = 0;
      slider.addEventListener('input', () => {
        showValue();
        const now = performance.now();
        if (now - lastPublished > MIN_MS_BETWEEN_PUBLISHES) { lastPublished = now; publish(); }
      });
      slider.addEventListener('change', publish);       // the final position, always
      showValue();
      inputs.set(item.in, {
        read: () => Number(slider.value),
        restore: (value) => { slider.value = value; showValue(); },
        retained: true,
        nudge: (amount) => {
          slider.value = Math.max(0, Math.min(1, Number(slider.value) + amount));
          showValue();
          publish();
        },
      });
      return [slider, readout];
    },

    /* A keypad: every key press is published on the same input, with the key as value (not retained). The layout
       is a grid of rows with an optional column of tall keys on each side. */
    keypad(item) {
      const KEY_FLASH_MS = 120;
      const keypad = createElement('div', 'keypad');
      const createKey = (key, extraClass = '') => {
        const button = createElement('button', `key ${extraClass}`, { type: 'button', textContent: (item.labels || {})[key] || key });
        if (!key) {                             // an empty cell in the grid
          button.disabled = true;
          button.classList.add('blank');
          return button;
        }
        const press = () => {
          button.classList.add('down');
          publishInput(item.in, key, false);
          setTimeout(() => button.classList.remove('down'), KEY_FLASH_MS);
        };
        button.addEventListener('pointerdown', (event) => { event.preventDefault(); press(); });
        button.addEventListener('keydown', (event) => {
          if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); press(); }
        });
        keypadKeys.set(key, press);
        return button;
      };
      const createSideColumn = (keys, side) => {
        const column = createElement('div', `keycol ${side}`);
        keys.forEach((key) => column.appendChild(createKey(key, 'tall')));
        return column;
      };
      const grid = createElement('div', 'keygrid');
      const columnCount = item.rows[0].length;
      if (columnCount !== 5) grid.style.gridTemplateColumns = `repeat(${columnCount}, 3.3rem)`;   // the CSS default is 5
      for (const row of item.rows) for (const key of row) grid.appendChild(createKey(key));
      keypad.append(createSideColumn(item.left || [], 'left'), grid, createSideColumn(item.right || [], 'right'));
      return [keypad];
    },

    /* An LED matrix (engine status): payload {rows: ["..g..", …]}, one character per LED: g, a, r, w, or . for off. */
    matrix(item) {
      const COLOR_CLASSES = { g: 'green', a: 'amber', r: 'red', w: 'white' };
      const matrix = createElement('div', 'matrix');
      matrix.style.gridTemplateColumns = `repeat(${item.cols}, 1fr)`;
      const leds = [];
      for (let index = 0; index < item.rows * item.cols; index++) {
        const led = createElement('i');
        matrix.appendChild(led);
        leds.push(led);
      }
      outputs.set(item.out, (payload) => leds.forEach((led, index) => {
        const row = (payload.rows || [])[Math.floor(index / item.cols)] || '';
        led.className = COLOR_CLASSES[row[index % item.cols]] || '';
      }));
      return [matrix];
    },

    /* An alphanumeric LED display (a row of 14-segment or dot-matrix characters): payload {text, blank}. */
    alpha(item) {
      const CHARACTER_WIDTH_REM = 0.86, PADDING_REM = 1;
      const display = createElement('div', 'alpha');
      display.style.width = `${item.chars * CHARACTER_WIDTH_REM + PADDING_REM}rem`;
      outputs.set(item.out, (payload) => {
        display.textContent = payload.blank ? '' : String(payload.text ?? '').slice(0, item.chars);
      });
      return [display];
    },

    /* The warning tone: a warbling square wave, plus a visual cue because browsers block audio until a click. */
    buzzer(item) {
      const TONE_HZ = 760, WARBLE_HZ = 3, VOLUME = 0.04;
      const indicator = createElement('div', 'buzzer', { title: 'tone' });
      let audioContext = null, tone = null;
      const startTone = () => {
        audioContext = audioContext || new AudioContext();
        tone = audioContext.createOscillator();
        const volume = audioContext.createGain();
        tone.type = 'square';
        tone.frequency.value = TONE_HZ;
        volume.gain.value = VOLUME;
        const warble = audioContext.createOscillator(), warbleDepth = audioContext.createGain();
        warble.frequency.value = WARBLE_HZ;
        warbleDepth.gain.value = VOLUME;
        warble.connect(warbleDepth).connect(volume.gain);
        warble.start();
        tone.connect(volume).connect(audioContext.destination);
        tone.start();
      };
      outputs.set(item.out, (payload) => {
        indicator.classList.toggle('lit', Boolean(payload.on));
        try {
          if (payload.on && !tone) startTone();
          else if (!payload.on && tone) { tone.stop(); tone = null; }
        } catch (error) { /* no audio before a user gesture: the visual cue stays */ }
      });
      return [indicator];
    },
  };
  return builders;
}
