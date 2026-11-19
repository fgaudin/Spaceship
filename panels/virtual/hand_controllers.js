/* The hand controllers on the keyboard, until the USB joysticks exist: KSP's own keys. This page is then the hc node,
   publishing what the joystick service will: panel/hc/in/<axis> {"v": −1..1}, not retained (a stick let go is 0).

     rotation      W / S  pitch down / up   A / D  yaw left / right   Q / E  roll left / right
     translation   I / K  down / up         J / L  left / right       H / N  forward / back
     throttle      Left Shift up, Left Ctrl down, held: it moves the THROTTLE lever

   Signs are the pilot's, as in cockpit-logic's hand_controller.py: + pitch nose up, + yaw nose right, + roll right;
   + right, + up, + forward move the ship that way. A key gives the full throw (RCS FINE scales it in the cockpit).
   The keys come from the console's window, and from its glass screens, which pass them on (shell.js). */

import { connectBus } from './bus.js';

const AXIS_KEYS = {
  KeyW: ['rot_pitch', -1], KeyS: ['rot_pitch', 1], KeyA: ['rot_yaw', -1], KeyD: ['rot_yaw', 1],
  KeyQ: ['rot_roll', -1], KeyE: ['rot_roll', 1],
  KeyI: ['trans_up', -1], KeyK: ['trans_up', 1], KeyJ: ['trans_right', -1], KeyL: ['trans_right', 1],
  KeyH: ['trans_fwd', 1], KeyN: ['trans_fwd', -1],
};
export const HAND_CONTROLLER_KEYS = new Set([...Object.keys(AXIS_KEYS), 'ShiftLeft', 'ControlLeft']);
const AXES = ['rot_pitch', 'rot_yaw', 'rot_roll', 'trans_right', 'trans_up', 'trans_fwd'];
const THROTTLE_KEYS = { ShiftLeft: 1, ControlLeft: -1 };
const THROTTLE_PER_SECOND = 0.5;        // 0 to full in 2 s
const THROTTLE_STEP_EVERY_MS = 40;     // steps of 0.02: the lever moves in whole per cent
const STATUS_EVERY_MS = 5000;

const held = new Set();
const published = Object.fromEntries(AXES.map((axis) => [axis, 0]));
let client = null;
let throttleTimer = null;
let nudgeThrottle = () => {};

function axisValue(axis) {
  let value = 0;
  for (const code of held) if (AXIS_KEYS[code]?.[0] === axis) value += AXIS_KEYS[code][1];
  return Math.max(-1, Math.min(1, value));      // both keys of an axis: they cancel
}

function publishAxes() {
  for (const axis of AXES) {
    const value = axisValue(axis);
    if (value === published[axis]) continue;
    published[axis] = value;
    if (client?.connected) client.publish(`panel/hc/in/${axis}`, JSON.stringify({ v: value }), { qos: 1 });
  }
  draw();
}

function throttleDirection() {
  return Object.entries(THROTTLE_KEYS).reduce((sum, [code, sign]) => sum + (held.has(code) ? sign : 0), 0);
}

function driveThrottle() {
  const direction = throttleDirection();
  if (direction && !throttleTimer) {
    const step = () => nudgeThrottle(throttleDirection() * THROTTLE_PER_SECOND * THROTTLE_STEP_EVERY_MS / 1000);
    step();
    throttleTimer = setInterval(step, THROTTLE_STEP_EVERY_MS);
  } else if (!direction && throttleTimer) {
    clearInterval(throttleTimer);
    throttleTimer = null;
  }
}

/* A key went down or up; true when it is one of the hand controllers' (or the throttle's). */
export function handControllerKey(code, down) {
  if (!HAND_CONTROLLER_KEYS.has(code)) return false;
  if (down === held.has(code)) return true;    // key repeat
  if (down) held.add(code); else held.delete(code);
  if (code in THROTTLE_KEYS) driveThrottle(); else publishAxes();
  return true;
}

/* Everything let go: the window lost the keyboard, so the key-ups will never come. */
export function releaseHandControllers() {
  held.clear();
  driveThrottle();
  publishAxes();
}

/* ---------- the two sticks in the side column ---------- */
let pads = null;

function draw() {
  if (!pads) return;
  const place = (pad, x, y, twist) => {
    pad.dot.style.left = `${50 + x * 40}%`;
    pad.dot.style.top = `${50 - y * 40}%`;
    pad.bar.style.left = `${50 + Math.min(0, twist) * 50}%`;
    pad.bar.style.width = `${Math.abs(twist) * 50}%`;
    pad.box.classList.toggle('active', Boolean(x || y || twist));
  };
  place(pads.rotation, published.rot_yaw, published.rot_pitch, published.rot_roll);
  place(pads.translation, published.trans_right, published.trans_up, published.trans_fwd);
}

function buildPads(container) {
  const pad = (title, axes) => {
    const box = document.createElement('figure');
    box.className = 'hc-pad';
    box.innerHTML = `<div class="hc-square"><i class="hc-dot"></i></div><div class="hc-twist"><i class="hc-bar"></i></div>`
      + `<figcaption></figcaption>`;
    box.querySelector('figcaption').textContent = `${title} · ${axes}`;
    container.append(box);
    return { box, dot: box.querySelector('.hc-dot'), bar: box.querySelector('.hc-bar') };
  };
  pads = { rotation: pad('ROTATION', 'bar: roll'), translation: pad('TRANSLATION', 'bar: fwd') };
  draw();
}

/* `throttle`: the THROTTLE lever's nudge(amount), when the console has one. */
export function startHandControllers({ container, throttle }) {
  if (throttle) nudgeThrottle = throttle;
  if (container) buildPads(container);
  const publishStatus = () => client.publish('panel/hc/status', JSON.stringify({ online: true, fw: 'keyboard' }), { qos: 1, retain: true });
  client = connectBus({
    name: 'panel-hc',
    will: { topic: 'panel/hc/status', payload: { online: false } },
    onConnect() {
      publishStatus();
      for (const axis of AXES) client.publish(`panel/hc/in/${axis}`, JSON.stringify({ v: published[axis] }), { qos: 1 });
    },
  });
  setInterval(() => { if (client.connected) publishStatus(); }, STATUS_EVERY_MS);
  window.addEventListener('blur', releaseHandControllers);
}
