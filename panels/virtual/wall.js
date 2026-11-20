/* Mission Control's wall display: the room's front screen, for everyone at once.

   GROUND TRACK  the flight so far (amber) and the next three orbits (cyan, then fainter) on a relief map of the body
                 sampled from the game by mcc-data, night shaded from where its sun is; the apsides, the next burn,
                 the impact point of a suborbital path, the target's track, the launch site
   ORBIT         seen from above the pole: the orbit, the moons with their spheres of influence, the target, the sun
   CHARTS        altitude and apsides, velocities, loads and heat over the mission clock, and the ascent profile
   EVENTS        lift-off, staging, max Q, engine on and off, AOS and LOS, alarms, from mcc-data's recorder

   Everything comes off the bus (mcc/bus.js); the history from mcc/history.js. F: full screen. */
import { store, orbit, flight, vessel, clock, linkUp, telemetryLive } from './mcc/bus.js';
import { bodyOf, moonsOf, planetOf, reading } from './mcc/bodies.js';
import { history, onHistory, recorderOnline } from './mcc/history.js';
import * as om from './mcc/orbitmath.js';
import { stripChart, AMBER, CYAN, GREEN, RED, MAGENTA, shortMet } from './mcc/charts.js';

const RAD = Math.PI / 180;
const HEAD_EVERY_MS = 250;
const MAP_EVERY_MS = 1000;
const ORBITS_AHEAD = 3;
const STEPS_PER_ORBIT = 480;
const SUBORBITAL_HORIZON_S = 3 * 3600;
const PHASES = { pre_launch: 'PRELAUNCH', flying: 'ATMOSPHERIC FLIGHT', sub_orbital: 'SUBORBITAL', orbiting: 'ORBIT',
  escaping: 'ESCAPE', landed: 'LANDED', splashed: 'SPLASHDOWN', docked: 'DOCKED' };
const COLORS = { amber: '#ffb000', cyan: '#4fc3f7', magenta: '#ff6ad5', red: '#ff3b2f', green: '#35e06f', ink: '#e8e6df', dim: '#9aa0a6' };
const $ = (id) => document.getElementById(id);
const PENDING_BURN = ['ready', 'armed', 'burn'];      // cmp/pad states with a burn to come (or under way)

/* ---------- helpers ---------- */
function formatMet(seconds, sign = 'T+') {
  if (seconds == null || !Number.isFinite(seconds)) return `${sign} ---:--:--`;
  const whole = Math.floor(Math.abs(seconds));
  const text = `${String(Math.floor(whole / 3600)).padStart(3, '0')}:${String(Math.floor(whole / 60) % 60).padStart(2, '0')}:${String(whole % 60).padStart(2, '0')}`;
  return `${seconds < 0 ? 'T−' : sign} ${text}`;
}
const km = (metres, decimals = 1) => (metres == null || !Number.isFinite(metres) ? '—' : (metres / 1000).toFixed(decimals));
const fixed = (value, decimals = 0) => (value == null || !Number.isFinite(value) ? '—' : value.toFixed(decimals));

/* A canvas drawn at the screen's resolution: returns its 2D context in CSS pixels, and its size. */
function sized(canvas) {
  const ratio = window.devicePixelRatio || 1;
  const { width, height } = canvas.getBoundingClientRect();
  if (canvas.width !== Math.round(width * ratio) || canvas.height !== Math.round(height * ratio)) {
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
  }
  const g = canvas.getContext('2d');
  g.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { g, width, height };
}

function currentBody() { return bodyOf(orbit().body) || bodyOf('Kerbin'); }

function elementsNow() {
  const o = orbit(), body = currentBody();
  return o.a != null && body ? om.elements(o, body.mu) : null;
}

/* ---------- the head ---------- */
function updateHead() {
  const v = vessel(), time = clock(), live = telemetryLive();
  $('vessel').textContent = v.name || '—';
  $('phase').textContent = PHASES[v.situation] || (v.situation || '—').toUpperCase();
  const body = orbit().body;
  $('soi').textContent = body ? body.toUpperCase() : '—';
  $('met').textContent = live ? formatMet(time.met) : 'NO TELEMETRY';
  $('met').parentElement.classList.toggle('stale', !live);
  const pad = store['cmp/pad'];
  const tigIn = pad?.tig != null && time.met != null ? pad.tig - time.met : null;
  $('tig-block').hidden = !(tigIn != null && PENDING_BURN.includes(pad.state));
  if (!$('tig-block').hidden) {
    const dv = Math.hypot(...(pad.dv || [0, 0, 0]));
    $('tig').textContent = `${formatMet(-tigIn, 'T+')} · ${dv.toFixed(1)} m/s`;
  }
  const lamp = (id, text, tone, blink = false) => {
    const node = $(id);
    node.textContent = text;
    node.className = `lamp ${tone}${blink ? ' blink' : ''}`;
  };
  const up = linkUp();
  lamp('lamp-link', up ? 'AOS' : 'LOS', up ? 'good' : 'red');
  const warp = time.warp || 1;
  lamp('lamp-warp', warp > 1 ? `WARP ${warp >= 10 ? Math.round(warp) : warp.toFixed(1)}×` : 'REAL TIME', warp > 1 ? 'amber' : '');
  const cw = store['cw/state'] || {};
  lamp('lamp-caution', 'CAUTION', cw.master_caution ? 'amber' : '');
  lamp('lamp-alarm', 'MASTER ALARM', cw.master_alarm ? 'red' : '', Boolean(cw.master_alarm));
  $('lamp-alarm').title = $('lamp-caution').title = (cw.active || []).join(' · ') || 'no alarm';
}

/* ---------- the numbers under the orbit ---------- */
const NUMBERS = [['alt', 'ALTITUDE'], ['apo', 'APOAPSIS'], ['peri', 'PERIAPSIS'], ['inc', 'INCLINATION'],
  ['vorb', 'ORBITAL SPEED'], ['vs', 'VERTICAL SPEED'], ['tapo', 'TIME TO AP'], ['tperi', 'TIME TO PE'],
  ['period', 'PERIOD'], ['q', 'DYNAMIC PRESSURE'], ['twr', 'THRUST / WEIGHT'], ['mass', 'MASS']];
const numberCells = {};
function buildNumbers() {
  for (const [id, label] of NUMBERS) {
    const cell = document.createElement('div');
    const name = document.createElement('dt'), value = document.createElement('dd');
    name.textContent = label;
    value.textContent = '—';
    cell.append(name, value);
    $('numbers').append(cell);
    numberCells[id] = value;
  }
}
function setNumber(id, value, unit = '', tone = '') {
  const cell = numberCells[id];
  cell.innerHTML = '';
  cell.append(value);
  if (unit && value !== '—') { const small = document.createElement('small'); small.textContent = unit; cell.append(small); }
  cell.className = tone;
}
function updateNumbers() {
  const o = orbit(), f = flight(), v = vessel(), body = currentBody();
  const safe = body ? body.atmosphere || 0 : 0;
  setNumber('alt', km(f.alt), 'km');
  setNumber('apo', o.apo == null ? '—' : km(o.apo), 'km');
  setNumber('peri', km(o.peri), 'km', o.peri != null && o.peri < safe ? (o.peri < 0 ? 'bad' : 'warn') : '');
  setNumber('inc', fixed(o.i, 2), '°');
  setNumber('vorb', fixed(f.v_orb, 0), 'm/s');
  setNumber('vs', fixed(f.vs, 0), 'm/s');
  setNumber('tapo', o.t_apo == null ? '—' : shortMet(o.t_apo));
  setNumber('tperi', o.t_peri == null ? '—' : shortMet(o.t_peri));
  setNumber('period', o.period == null || o.e >= 1 ? '—' : shortMet(o.period));
  setNumber('q', f.q == null ? '—' : (f.q / 1000).toFixed(1), 'kPa');
  const gravity = body && f.alt != null ? body.mu / (body.radius + f.alt) ** 2 : null;
  const twr = gravity && v.mass ? (v.thrust || 0) / (v.mass * gravity) : null;
  setNumber('twr', fixed(twr, 2));
  setNumber('mass', v.mass == null ? '—' : (v.mass / 1000).toFixed(2), 't');
}

/* ---------- the ground track ---------- */
const mapImages = {};
function mapImageOf(body) {
  const info = store['mcc/maps']?.[body.name];
  if (!info || Math.round(info.radius) !== Math.round(body.radius)) return null;
  let image = mapImages[info.file];
  if (!image) {
    image = new Image();
    image.onload = () => drawMap();
    image.src = `maps/${info.file}`;
    mapImages[info.file] = image;
  }
  return image.complete && image.naturalWidth ? image : null;
}

/* the 2:1 rectangle of the map inside the frame */
function mapRect(width, height) {
  const w = Math.min(width, height * 2), h = w / 2;
  return { x: (width - w) / 2, y: (height - h) / 2, w, h };
}
const project = (rect, lat, lon) => [rect.x + ((lon + 180) / 360) * rect.w, rect.y + ((90 - lat) / 180) * rect.h];

/* a line through lat/lon points, broken where it crosses the edge of the map */
function trackPath(g, rect, points) {
  let previous = null;
  g.beginPath();
  for (const point of points) {
    const [x, y] = project(rect, point.lat, point.lon);
    if (!previous || Math.abs(point.lon - previous.lon) > 180) g.moveTo(x, y); else g.lineTo(x, y);
    previous = point;
  }
}

const nightCanvas = document.createElement('canvas');
nightCanvas.width = 360; nightCanvas.height = 180;
function nightShade(subsolar) {
  const g = nightCanvas.getContext('2d');
  const image = g.createImageData(360, 180);
  const sunLat = subsolar.lat * RAD, sunLon = subsolar.lon * RAD;
  for (let row = 0; row < 180; row++) {
    const lat = (89.5 - row) * RAD;
    for (let column = 0; column < 360; column++) {
      const lon = (column - 179.5) * RAD;
      const height = Math.asin(Math.sin(lat) * Math.sin(sunLat) + Math.cos(lat) * Math.cos(sunLat) * Math.cos(lon - sunLon)) / RAD;
      const darkness = Math.max(0, Math.min(1, (6 - height) / 18));
      const index = (row * 360 + column) * 4;
      image.data[index] = 2; image.data[index + 1] = 6; image.data[index + 2] = 18;
      image.data[index + 3] = Math.round(darkness * 200);
    }
  }
  g.putImageData(image, 0, 0);
  return nightCanvas;
}

/* the track ahead of an orbit, with the inertial longitude pinned by `offset` at `offsetUt` */
function trackAhead(el, body, ut, offset, seconds, steps) {
  const points = [];
  let end = null;
  for (let step = 0; step <= steps; step++) {
    const t = ut + (seconds * step) / steps;
    const point = om.groundPoint(om.positionAtTime(el, t), t, offset, ut, body.rotation);
    if (point.r < body.radius) { end = { ...point, t, kind: 'impact' }; break; }
    if (body.soi && point.r > body.soi) { end = { ...point, t, kind: 'soi' }; break; }
    points.push({ t, lat: point.lat, lon: point.lon });
  }
  return { points, end };
}

let mapState = null;            // what the overlay needs: the rectangle and the vessel's place
function drawMap() {
  const { g, width, height } = sized($('map'));
  g.clearRect(0, 0, width, height);
  const body = currentBody();
  if (!body) return;
  const rect = mapRect(width, height);
  $('map-body').textContent = body.name.toUpperCase();
  // the ground
  const image = mapImageOf(body);
  if (image) {
    g.imageSmoothingQuality = 'high';
    g.drawImage(image, rect.x, rect.y, rect.w, rect.h);
    g.fillStyle = 'rgba(4,8,14,0.08)';
    g.fillRect(rect.x, rect.y, rect.w, rect.h);
  } else {
    const fill = g.createLinearGradient(0, rect.y, 0, rect.y + rect.h);
    fill.addColorStop(0, '#0c1520'); fill.addColorStop(0.5, body.color || '#1b2a3a'); fill.addColorStop(1, '#0c1520');
    g.fillStyle = fill;
    g.fillRect(rect.x, rect.y, rect.w, rect.h);
  }
  // night
  const ut = clock().ut;
  const subsolar = ut != null ? om.subsolarAt(body, planetOf(body.name), reading(), ut) : null;
  if (subsolar) {
    g.imageSmoothingEnabled = true;
    g.drawImage(nightShade(subsolar), rect.x, rect.y, rect.w, rect.h);
    const [sx, sy] = project(rect, subsolar.lat, subsolar.lon);
    g.fillStyle = 'rgba(255,214,90,0.9)';
    g.beginPath(); g.arc(sx, sy, 5, 0, 2 * Math.PI); g.fill();
    g.strokeStyle = 'rgba(255,214,90,0.35)'; g.lineWidth = 1;
    g.beginPath(); g.arc(sx, sy, 10, 0, 2 * Math.PI); g.stroke();
  }
  // graticule
  g.strokeStyle = 'rgba(255,255,255,0.10)'; g.lineWidth = 1;
  g.font = '10px ui-monospace, monospace'; g.fillStyle = 'rgba(255,255,255,0.45)';
  for (let lat = -60; lat <= 60; lat += 30) {
    const [, y] = project(rect, lat, 0);
    g.beginPath(); g.moveTo(rect.x, y); g.lineTo(rect.x + rect.w, y); g.stroke();
    g.fillText(`${Math.abs(lat)}°${lat > 0 ? 'N' : lat < 0 ? 'S' : ''}`, rect.x + 4, y - 3);
  }
  for (let lon = -150; lon <= 150; lon += 30) {
    const [x] = project(rect, 0, lon);
    g.beginPath(); g.moveTo(x, rect.y); g.lineTo(x, rect.y + rect.h); g.stroke();
    g.fillText(`${Math.abs(lon)}°${lon > 0 ? 'E' : lon < 0 ? 'W' : ''}`, x + 3, rect.y + 12);
  }
  g.strokeStyle = 'rgba(255,255,255,0.22)';
  g.strokeRect(rect.x + 0.5, rect.y + 0.5, rect.w - 1, rect.h - 1);

  const { columns, launch } = history();
  // flown: this body's part of the flight
  const flown = [];
  for (let index = 0; index < columns.t.length; index++) {
    if (columns.body[index] === body.name && columns.lat[index] != null) flown.push({ lat: columns.lat[index], lon: columns.lon[index] });
  }
  g.save();
  g.shadowColor = COLORS.amber; g.shadowBlur = 6;
  g.strokeStyle = COLORS.amber; g.lineWidth = 2.2; g.lineJoin = 'round';
  trackPath(g, rect, flown); g.stroke();
  g.restore();
  if (launch && launch.body === body.name) {
    const [x, y] = project(rect, launch.lat, launch.lon);
    g.fillStyle = COLORS.ink;
    g.beginPath(); g.moveTo(x, y - 7); g.lineTo(x + 6, y + 5); g.lineTo(x - 6, y + 5); g.closePath(); g.fill();
    label(g, 'LAUNCH', x + 9, y + 4, COLORS.ink);
  }

  // ahead: the next orbits
  const el = elementsNow(), f = flight();
  mapState = { rect, body };
  if (!el || ut == null || f.lon == null || !telemetryLive()) { drawReadout(); return; }
  const offset = om.groundOffset(el, ut, f.lon);
  const orbitTime = om.closed(el) ? om.period(el) : SUBORBITAL_HORIZON_S;
  const ahead = trackAhead(el, body, ut, offset, Math.min(orbitTime * ORBITS_AHEAD, 30 * 86400), STEPS_PER_ORBIT * ORBITS_AHEAD);
  const firstOrbitEnd = ut + orbitTime;
  const first = ahead.points.filter((point) => point.t <= firstOrbitEnd);
  const later = ahead.points.filter((point) => point.t >= firstOrbitEnd);
  g.save();
  g.strokeStyle = 'rgba(79,195,247,0.45)'; g.lineWidth = 1.4; g.setLineDash([5, 5]);
  trackPath(g, rect, later); g.stroke();
  g.setLineDash([]);
  g.shadowColor = COLORS.cyan; g.shadowBlur = 5;
  g.strokeStyle = COLORS.cyan; g.lineWidth = 2;
  trackPath(g, rect, first); g.stroke();
  g.restore();
  if (ahead.end) {
    const [x, y] = project(rect, ahead.end.lat, ahead.end.lon);
    if (ahead.end.kind === 'impact') {
      g.strokeStyle = COLORS.red; g.lineWidth = 2.5;
      g.beginPath(); g.moveTo(x - 6, y - 6); g.lineTo(x + 6, y + 6); g.moveTo(x + 6, y - 6); g.lineTo(x - 6, y + 6); g.stroke();
      label(g, `IMPACT ${formatMet((clock().met || 0) + ahead.end.t - ut)}`, x + 9, y + 4, COLORS.red);
    } else {
      label(g, 'LEAVES SOI', x + 6, y + 4, COLORS.cyan);
    }
  }
  // apsides and the next burn on the track
  const o = orbit();
  const marker = (seconds, text, color) => {
    if (seconds == null || seconds < 0 || (ahead.end && ut + seconds > ahead.end.t)) return;
    const t = ut + seconds;
    const point = om.groundPoint(om.positionAtTime(el, t), t, offset, ut, body.rotation);
    const [x, y] = project(rect, point.lat, point.lon);
    g.fillStyle = color;
    g.beginPath(); g.moveTo(x, y - 6); g.lineTo(x + 6, y); g.lineTo(x, y + 6); g.lineTo(x - 6, y); g.closePath(); g.fill();
    label(g, text, x + 9, y + 4, color);
  };
  if (o.apo != null && (o.e ?? 0) < 1) marker(o.t_apo, `AP ${km(o.apo)} km`, COLORS.ink);
  if (o.peri != null && o.peri > 0) marker(o.t_peri, `PE ${km(o.peri)} km`, COLORS.ink);
  const pad = store['cmp/pad'];
  if (pad?.tig != null && PENDING_BURN.includes(pad.state) && clock().met != null) marker(pad.tig - clock().met, 'TIG', COLORS.amber);
  // the target
  const target = store['tlm/target'];
  if (target?.set && target.orbit?.body === body.name) {
    const targetElements = om.elements(target.orbit, body.mu);
    if (targetElements) {
      const span = om.closed(targetElements) ? om.period(targetElements) : orbitTime;
      const track = trackAhead(targetElements, body, ut, offset, span, STEPS_PER_ORBIT);
      g.strokeStyle = 'rgba(255,106,213,0.8)'; g.lineWidth = 1.4;
      trackPath(g, rect, track.points); g.stroke();
      if (track.points.length) {
        const [x, y] = project(rect, track.points[0].lat, track.points[0].lon);
        g.fillStyle = COLORS.magenta;
        g.beginPath(); g.arc(x, y, 4.5, 0, 2 * Math.PI); g.fill();
        label(g, (target.name || 'TARGET').toUpperCase(), x + 8, y + 4, COLORS.magenta);
      }
    }
  }
  drawReadout();
}

function label(g, text, x, y, color) {
  g.font = '600 11px ui-monospace, "DejaVu Sans Mono", monospace';
  const width = g.measureText(text).width;
  g.fillStyle = 'rgba(0,0,0,0.6)';
  g.fillRect(x - 3, y - 11, width + 6, 15);
  g.fillStyle = color;
  g.fillText(text, x, y);
}

function drawReadout() {
  const f = flight();
  $('map-readout').textContent = f.lat == null ? '' :
    `${Math.abs(f.lat).toFixed(3)}°${f.lat >= 0 ? 'N' : 'S'}  ${Math.abs(f.lon).toFixed(3)}°${f.lon >= 0 ? 'E' : 'W'}  ·  ${km(f.alt)} km`;
  const mapping = store['mcc/data/status']?.mapping;
  $('map-status').hidden = !mapping;
  if (mapping) $('map-status').textContent = `MAPPING ${mapping.body.toUpperCase()} · ${Math.round(mapping.progress * 100)} %`;
}

/* the vessel, pulsing, on its own layer */
function drawMapOverlay(now) {
  const { g, width, height } = sized($('map-overlay'));
  g.clearRect(0, 0, width, height);
  const f = flight();
  if (!mapState || f.lat == null || !telemetryLive()) return;
  const [x, y] = project(mapState.rect, f.lat, f.lon);
  const pulse = (now / 1600) % 1;
  g.strokeStyle = `rgba(255,176,0,${1 - pulse})`; g.lineWidth = 2;
  g.beginPath(); g.arc(x, y, 6 + pulse * 22, 0, 2 * Math.PI); g.stroke();
  g.fillStyle = COLORS.amber;
  g.shadowColor = COLORS.amber; g.shadowBlur = 12;
  g.beginPath(); g.arc(x, y, 5.5, 0, 2 * Math.PI); g.fill();
  g.shadowBlur = 0;
  g.strokeStyle = '#000'; g.lineWidth = 1.5; g.stroke();
}

/* ---------- the orbit, from above the pole ---------- */
const stars = Array.from({ length: 160 }, () => [Math.random(), Math.random(), Math.random()]);
let orbitScale = null;
function drawOrbit() {
  const { g, width, height } = sized($('orbit'));
  g.clearRect(0, 0, width, height);
  for (const [sx, sy, bright] of stars) {
    g.fillStyle = `rgba(255,255,255,${0.12 + bright * 0.35})`;
    g.fillRect(sx * width, sy * height, bright > 0.85 ? 1.6 : 1, bright > 0.85 ? 1.6 : 1);
  }
  const body = currentBody();
  if (!body) return;
  $('orbit-body').textContent = body.name.toUpperCase();
  const cx = width / 2, cy = height / 2, room = Math.min(width, height) / 2 - 18;
  const el = elementsNow(), ut = clock().ut, f = flight();
  const moons = moonsOf(body.name).filter(Boolean).map((moon) => ({ moon, el: om.elements(moon.orbit, body.mu) })).filter((m) => m.el);
  // how far to show: the orbit, and the moons it reaches towards
  let reach = body.radius * 1.6;
  if (el) {
    const far = om.closed(el) ? el.a * (1 + el.e) : (body.soi || el.a * -4);
    reach = Math.max(reach, Math.min(far, body.soi || far) * 1.08);
    for (const { el: moonEl } of moons) if (far > 0.35 * moonEl.a) reach = Math.max(reach, moonEl.a * (1 + moonEl.e) * 1.08);
  }
  const wanted = room / reach;
  orbitScale = orbitScale ? orbitScale + (wanted - orbitScale) * 0.08 : wanted;
  const s = orbitScale;
  const at = ([x, y]) => [cx + x * s, cy - y * s];

  // the sun's direction: where it is overhead, turned into the orbit's frame by the vessel's longitude
  let sunAngle = null;
  if (el && ut != null && f.lon != null) {
    const subsolar = om.subsolarAt(body, planetOf(body.name), reading(), ut);
    if (subsolar) sunAngle = (subsolar.lon - om.groundOffset(el, ut, f.lon)) * RAD;
  }
  // the body: atmosphere, disc, day side
  const radius = Math.max(body.radius * s, 3);
  if (body.atmosphere) {
    g.fillStyle = 'rgba(79,150,255,0.13)';
    g.beginPath(); g.arc(cx, cy, (body.radius + body.atmosphere) * s, 0, 2 * Math.PI); g.fill();
  }
  const disc = sunAngle == null ? (body.color || '#2c4a6b')
    : (() => {
      const dx = Math.cos(sunAngle) * radius, dy = -Math.sin(sunAngle) * radius;
      const shade = g.createLinearGradient(cx - dx, cy - dy, cx + dx, cy + dy);
      shade.addColorStop(0, '#05080c'); shade.addColorStop(0.45, '#0b121b'); shade.addColorStop(0.55, body.color || '#2c4a6b');
      shade.addColorStop(1, lighten(body.color || '#2c4a6b'));
      return shade;
    })();
  g.fillStyle = disc;
  g.beginPath(); g.arc(cx, cy, radius, 0, 2 * Math.PI); g.fill();
  if (sunAngle != null) {
    const edge = room + 6;
    const [x, y] = [cx + Math.cos(sunAngle) * edge, cy - Math.sin(sunAngle) * edge];
    g.strokeStyle = 'rgba(255,214,90,0.5)'; g.setLineDash([2, 4]); g.lineWidth = 1;
    g.beginPath(); g.moveTo(cx + Math.cos(sunAngle) * (radius + 4), cy - Math.sin(sunAngle) * (radius + 4)); g.lineTo(x, y); g.stroke();
    g.setLineDash([]);
    g.fillStyle = '#ffd65a';
    g.beginPath(); g.arc(x, y, 4, 0, 2 * Math.PI); g.fill();
  }
  // the moons
  for (const { moon, el: moonEl } of moons) {
    path(g, moonEl, at, null);
    g.strokeStyle = 'rgba(200,200,200,0.28)'; g.setLineDash([3, 5]); g.lineWidth = 1; g.stroke(); g.setLineDash([]);
    if (ut == null) continue;
    const [mx, my] = at(om.positionAtTime(moonEl, ut));
    if (moon.soi) {
      g.strokeStyle = 'rgba(200,200,200,0.22)'; g.setLineDash([2, 3]);
      g.beginPath(); g.arc(mx, my, moon.soi * s, 0, 2 * Math.PI); g.stroke(); g.setLineDash([]);
    }
    g.fillStyle = moon.color || '#888';
    g.beginPath(); g.arc(mx, my, Math.max(moon.radius * s, 3.5), 0, 2 * Math.PI); g.fill();
    label(g, moon.name.toUpperCase(), mx + 8, my + 4, COLORS.dim);
  }
  // the target
  const target = store['tlm/target'];
  if (target?.set && target.orbit?.body === body.name) {
    const targetEl = om.elements(target.orbit, body.mu);
    if (targetEl) {
      strokeOrbit(g, targetEl, at, body.soi, body.radius, () => { g.strokeStyle = 'rgba(255,106,213,0.75)'; g.lineWidth = 1.3; },
        () => { g.strokeStyle = 'rgba(255,106,213,0.45)'; g.lineWidth = 1; g.setLineDash([3, 5]); });
      if (ut != null) {
        const position = om.positionAtTime(targetEl, ut);
        const [tx, ty] = at(position);
        g.globalAlpha = behind(position, body.radius) ? 0.4 : 1;
        g.fillStyle = COLORS.magenta; g.beginPath(); g.arc(tx, ty, 4, 0, 2 * Math.PI); g.fill();
        g.globalAlpha = 1;
      }
    }
  }
  // the vessel's orbit, its apsides, the vessel
  if (el) {
    // in front of the body solid and glowing; behind it (south of the equator, over the disc) thin and dashed
    strokeOrbit(g, el, at, body.soi, body.radius,
      () => { g.shadowColor = COLORS.cyan; g.shadowBlur = 6; g.strokeStyle = COLORS.cyan; g.lineWidth = 2; },
      () => { g.strokeStyle = 'rgba(190,232,255,0.85)'; g.lineWidth = 1.3; g.setLineDash([5, 5]); });
    const o = orbit();
    const apsis = (nu, text) => {
      const position = om.positionAt(el, nu);
      const [x, y] = at(position);
      g.globalAlpha = behind(position, body.radius) ? 0.45 : 1;
      g.fillStyle = COLORS.ink; g.beginPath(); g.arc(x, y, 3, 0, 2 * Math.PI); g.fill();
      label(g, text, x + 7, y - 6, COLORS.ink);
      g.globalAlpha = 1;
    };
    if (om.closed(el) && o.apo != null) apsis(Math.PI, `AP ${km(o.apo)} km`);
    if (o.peri != null) apsis(0, `PE ${km(o.peri)} km`);
    if (ut != null) {
      const position = om.positionAtTime(el, ut);
      const [x, y] = at(position);
      if (behind(position, body.radius)) {             // hidden by the body: a ring, not the bright dot
        g.strokeStyle = COLORS.amber; g.lineWidth = 1.5; g.globalAlpha = 0.8;
        g.beginPath(); g.arc(x, y, 4.5, 0, 2 * Math.PI); g.stroke(); g.globalAlpha = 1;
      } else {
        g.fillStyle = COLORS.amber; g.shadowColor = COLORS.amber; g.shadowBlur = 10;
        g.beginPath(); g.arc(x, y, 5, 0, 2 * Math.PI); g.fill(); g.shadowBlur = 0;
      }
    }
  }
  // the scale
  const bar = niceLength(reach / 3);
  g.strokeStyle = COLORS.dim; g.lineWidth = 1.5;
  g.beginPath(); g.moveTo(14, height - 14); g.lineTo(14 + bar * s, height - 14); g.stroke();
  g.fillStyle = COLORS.dim; g.font = '11px ui-monospace, monospace';
  g.fillText(bar >= 1e6 ? `${bar / 1e6} 000 km` : `${bar / 1000} km`, 14, height - 20);
  const o = orbit();
  if (o.e != null) g.fillText(`e ${o.e.toFixed(3)}   i ${fixed(o.i, 2)}°`, width - 130, height - 14);
}

function path(g, el, at, limit) {
  const [from, to] = om.anomalyRange(el, limit);
  g.beginPath();
  for (let step = 0; step <= 360; step++) {
    const [x, y] = at(om.positionAt(el, from + ((to - from) * step) / 360));
    if (step === 0) g.moveTo(x, y); else g.lineTo(x, y);
  }
}

/* Seen from above the north pole, a point is hidden when it is south of the equator and over the body's disc. */
const behind = ([x, y, z], radius) => z < 0 && x * x + y * y < radius * radius;

/* An orbit in runs: those in front stroked with `front()`'s style, those behind the body with `back()`'s. */
function strokeOrbit(g, el, at, limit, radius, front, back) {
  const [from, to] = om.anomalyRange(el, limit);
  const steps = 720;
  let run = [], hidden = null;
  const flush = () => {
    if (run.length < 2) return;
    g.save(); (hidden ? back : front)();
    g.beginPath(); run.forEach(([x, y], index) => (index ? g.lineTo(x, y) : g.moveTo(x, y))); g.stroke();
    g.restore();
  };
  for (let step = 0; step <= steps; step++) {
    const position = om.positionAt(el, from + ((to - from) * step) / steps);
    const point = at(position), isHidden = behind(position, radius);
    if (hidden !== null && isHidden !== hidden) { run.push(point); flush(); run = []; }
    hidden = isHidden;
    run.push(point);
  }
  flush();
}

function niceLength(length) {
  const power = 10 ** Math.floor(Math.log10(length));
  return [1, 2, 5, 10].map((m) => m * power).filter((value) => value <= length).pop() || power;
}

function lighten(hex) {
  const value = parseInt(hex.slice(1), 16);
  const channel = (shift) => Math.min(255, ((value >> shift) & 255) + 70);
  return `rgb(${channel(16)},${channel(8)},${channel(0)})`;
}

/* ---------- charts ---------- */
let charts = [];
function buildCharts() {
  charts = [
    stripChart($('chart-altitude'), {
      series: [
        { label: 'ALTITUDE', color: AMBER, unit: 'km', value: (c, i) => c.alt[i] / 1000 },
        { label: 'APOAPSIS', color: CYAN, unit: 'km', value: (c, i) => c.apo[i] / 1000 },
        { label: 'PERIAPSIS', color: GREEN, unit: 'km', value: (c, i) => c.peri[i] / 1000 },
      ],
      scales: { y: { range: (u, min, max) => [Math.max(min, -100), Math.max(max, 1)] } },
    }),
    stripChart($('chart-velocity'), {
      series: [
        { label: 'SURFACE', color: AMBER, unit: 'm/s', decimals: 0, value: (c, i) => c.spd[i] },
        { label: 'ORBITAL', color: CYAN, unit: 'm/s', decimals: 0, value: (c, i) => c.vorb[i] },
        { label: 'VERTICAL', color: GREEN, unit: 'm/s', decimals: 0, value: (c, i) => c.vs[i] },
      ],
    }),
    stripChart($('chart-loads'), {
      series: [
        { label: 'Q', color: AMBER, unit: 'kPa', value: (c, i) => (c.q[i] == null ? null : c.q[i] / 1000) },
        { label: 'G', color: CYAN, scale: 'g', unit: 'g', decimals: 2, value: (c, i) => c.g[i] },
        { label: 'HEAT', color: RED, scale: 'pct', unit: '%', decimals: 0, value: (c, i) => (c.heat[i] == null ? null : c.heat[i] * 100) },
      ],
      scales: { y: { range: (u, min, max) => [0, Math.max(max, 1)] }, g: { range: (u, min, max) => [0, Math.max(max, 1)] },
        pct: { range: [0, 100], hidden: true } },
    }),
  ];
}

/* altitude against the distance from the launch site, along the ground, from lift-off to the top of the climb */
function drawProfile() {
  const { g, width, height } = sized($('profile'));
  g.clearRect(0, 0, width, height);
  const { columns, launch, events } = history();
  const body = launch ? bodyOf(launch.body) : null;
  const pad = { left: 44, right: 10, top: 8, bottom: 24 };
  const w = width - pad.left - pad.right, h = height - pad.top - pad.bottom;
  g.font = '11px ui-monospace, monospace';
  if (!launch || !body) {
    const text = columns.t.length && columns.alt[columns.alt.length - 1] > 1000 ? 'LIFT-OFF NOT RECORDED' : 'WAITING FOR LIFT-OFF';
    g.fillStyle = COLORS.dim;
    g.fillText(text, pad.left + w / 2 - g.measureText(text).width / 2, pad.top + h / 2);
    return;
  }
  const points = [];
  const lat0 = launch.lat * RAD, lon0 = launch.lon * RAD;
  let farthest = 0;
  for (let index = 0; index < columns.t.length; index++) {
    if (columns.t[index] < launch.t - 1 || columns.body[index] !== launch.body || columns.lat[index] == null) continue;
    const lat = columns.lat[index] * RAD, lon = columns.lon[index] * RAD;
    const angle = Math.acos(Math.min(1, Math.sin(lat0) * Math.sin(lat) + Math.cos(lat0) * Math.cos(lat) * Math.cos(lon - lon0)));
    const downrange = angle * body.radius / 1000;
    if (downrange < farthest * 0.98 && farthest > 50) break;          // round the world: the ascent is over
    farthest = Math.max(farthest, downrange);
    points.push({ t: columns.t[index], x: downrange, y: (columns.alt[index] || 0) / 1000 });
  }
  const top = Math.max(...points.map((point) => point.y), (body.atmosphere || 0) / 1000 * 1.1, 1);
  const right = Math.max(farthest, 1);
  const X = (value) => pad.left + (value / right) * w, Y = (value) => pad.top + h - (value / top) * h;
  // axes and grid
  g.strokeStyle = 'rgba(255,255,255,0.07)'; g.fillStyle = COLORS.dim; g.lineWidth = 1;
  for (const value of ticks(top)) { g.beginPath(); g.moveTo(pad.left, Y(value)); g.lineTo(pad.left + w, Y(value)); g.stroke(); g.fillText(String(value), 4, Y(value) + 4); }
  for (const value of ticks(right)) { g.fillText(String(value), X(value) - 8, height - 6); }
  const taken = [];                   // the rectangles of the labels already placed: none may overlap
  if (body.atmosphere) {
    const y = Y(body.atmosphere / 1000);
    g.strokeStyle = 'rgba(79,150,255,0.6)'; g.setLineDash([6, 4]);
    g.beginPath(); g.moveTo(pad.left, y); g.lineTo(pad.left + w, y); g.stroke(); g.setLineDash([]);
    const text = `ATMOSPHERE ${(body.atmosphere / 1000).toFixed(0)} km`;
    const textWidth = g.measureText(text).width;
    const x = pad.left + w - textWidth - 4;           // on the right: the climb crosses it on the left
    g.fillStyle = 'rgba(79,150,255,0.9)'; g.fillText(text, x, y - 5);
    taken.push({ x: x - 2, y: y - 16, w: textWidth + 4, h: 14 });
  }
  // the climb
  g.save(); g.shadowColor = COLORS.amber; g.shadowBlur = 6; g.strokeStyle = COLORS.amber; g.lineWidth = 2.2;
  g.beginPath();
  points.forEach((point, index) => (index ? g.lineTo(X(point.x), Y(point.y)) : g.moveTo(X(point.x), Y(point.y))));
  g.stroke(); g.restore();
  // the events along it: those at the same place share a label; each label goes where it covers no other
  const marks = [];
  for (const event of events) {
    if (!['stage', 'milestone', 'engine'].includes(event.kind) || event.text === 'LIFTOFF') continue;
    const point = points.find((candidate) => candidate.t >= event.t);
    if (!point) continue;
    const x = X(point.x), y = Y(point.y);
    const near = marks.find((mark) => Math.hypot(mark.x - x, mark.y - y) < PROFILE_MERGE_PX);
    if (near) {
      if (!near.texts.includes(event.text)) near.texts.push(event.text);
      near.milestone ||= event.kind === 'milestone';
    } else marks.push({ x, y, texts: [event.text], milestone: event.kind === 'milestone' });
  }
  const area = { left: pad.left, right: width - 2, top: 2, bottom: pad.top + h };
  for (const mark of marks) {
    g.fillStyle = mark.milestone ? COLORS.cyan : COLORS.ink;
    g.beginPath(); g.arc(mark.x, mark.y, 3.2, 0, 2 * Math.PI); g.fill();
  }
  for (const mark of marks) {
    const text = mark.texts.join(' · ');
    const box = placeLabel(g, text, mark, taken, area);
    if (!box) continue;
    g.fillStyle = 'rgba(10,13,18,0.82)'; g.fillRect(box.x, box.y, box.w, box.h);
    g.fillStyle = mark.milestone ? COLORS.cyan : COLORS.ink;
    g.fillText(text, box.x + 2, box.y + box.h - 3);
    taken.push(box);
  }
  const last = points[points.length - 1];
  if (last) { g.fillStyle = COLORS.amber; g.beginPath(); g.arc(X(last.x), Y(last.y), 4.5, 0, 2 * Math.PI); g.fill(); }
}

const PROFILE_MERGE_PX = 12;           // events closer than this on the profile share one label
const LABEL_HEIGHT = 14;

/* Where `text` can go next to `mark` (a point) without covering a rectangle in `taken`, inside `area`: beside it
   first, then further up or down. Null when nowhere (the label is left out; its dot stays). */
function placeLabel(g, text, mark, taken, area) {
  const width = g.measureText(text).width + 4;
  const overlaps = (box) => taken.some((other) => box.x < other.x + other.w && other.x < box.x + box.w
    && box.y < other.y + other.h && other.y < box.y + box.h);
  for (const shift of [0, 1, -1, 2, -2, 3, -3, 4, -4]) {
    for (const side of ['right', 'left']) {
      const x = side === 'right' ? mark.x + 7 : mark.x - 7 - width;
      const y = mark.y + 4 - LABEL_HEIGHT / 2 + shift * (LABEL_HEIGHT + 1);
      const box = { x: Math.max(area.left, Math.min(x, area.right - width)), y, w: width, h: LABEL_HEIGHT };
      if (box.y < area.top || box.y + box.h > area.bottom) continue;
      if (Math.abs(box.x - x) > width / 2) continue;                   // pushed too far from its dot
      if (!overlaps(box)) return box;
    }
  }
  return null;
}

function ticks(max) {
  const step = niceLength(max / 3);
  const values = [];
  for (let value = step; value <= max; value += step) values.push(Math.round(value));
  return values;
}

/* ---------- events ---------- */
let shownEvents = '';
function updateEvents() {
  const { events } = history();
  $('recorder').textContent = recorderOnline() ? '' : 'recorder offline';
  const key = events.map((event) => event.t + event.text).join('|');
  if (key === shownEvents) return;
  const fresh = new Set(events.filter((event) => !shownEvents.includes(event.t + event.text)).map((event) => event.t + event.text));
  const first = !shownEvents;
  shownEvents = key;
  const list = $('events');
  list.innerHTML = '';
  if (!events.length) {
    const empty = document.createElement('li');
    empty.className = 'empty';
    empty.textContent = 'No event yet: lift-off, staging, max Q, AOS and LOS, alarms appear here.';
    list.append(empty);
    return;
  }
  for (const event of [...events].reverse().slice(0, 80)) {
    const item = document.createElement('li');
    item.className = `${event.kind}${!first && fresh.has(event.t + event.text) ? ' new' : ''}`;
    const time = document.createElement('time'), text = document.createElement('span');
    time.textContent = formatMet(event.t);
    text.textContent = event.text;
    item.append(time, text);
    list.append(item);
  }
}

/* ---------- full screen ---------- */
function toggleFullScreen() {
  if (document.fullscreenElement) document.exitFullscreen();
  else document.documentElement.requestFullscreen?.().catch(() => {});
}
document.addEventListener('fullscreenchange', () => document.body.classList.toggle('tv', Boolean(document.fullscreenElement)));
document.addEventListener('keydown', (event) => { if (event.key === 'f' || event.key === 'F') toggleFullScreen(); });
$('fullscreen').addEventListener('click', toggleFullScreen);

/* ---------- start ---------- */
buildNumbers();
buildCharts();
onHistory(() => {
  const { columns } = history();
  for (const chart of charts) chart.update(columns);
  drawProfile();
  updateEvents();
});
setInterval(() => { updateHead(); updateNumbers(); }, HEAD_EVERY_MS);
setInterval(drawMap, MAP_EVERY_MS);
new ResizeObserver(() => { drawMap(); drawProfile(); }).observe(document.querySelector('.wall'));
let lastOrbitFrame = 0;
function frame(now) {
  drawMapOverlay(now);
  if (now - lastOrbitFrame > 33) { drawOrbit(); lastOrbitFrame = now; }
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
updateEvents();
