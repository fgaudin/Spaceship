/* FIDO, flight dynamics officer: where the vehicle is going. The orbit (figures and a drawing), the target, the
   ground position. */
import { create, box, figures, fixed, km, formatMet } from '../ui.js';
import { orbit, flight, store } from '../bus.js';
import { bodyOf } from '../bodies.js';

let setOrbit, setTarget, setGround, canvas;

export function mount(root) {
  const drawing = box(root, 'ORBIT', { at: [0, 0], size: [1, 2] });
  canvas = create('canvas', 'mcc-orbit');
  canvas.width = canvas.height = 420;
  canvas.setAttribute('role', 'img');
  canvas.setAttribute('aria-label', 'Orbit drawing');
  drawing.append(canvas);
  setOrbit = figures(box(root, 'ELEMENTS', { at: [1, 0], size: [1, 2] }), [['body', 'Body'], ['apo', 'Apoapsis'], ['peri', 'Periapsis'], ['e', 'Eccentricity'],
    ['i', 'Inclination'], ['period', 'Period'], ['t_apo', 'To apoapsis'], ['t_peri', 'To periapsis'], ['t_soi', 'To SOI change']]);
  setTarget = figures(box(root, 'TARGET', { at: [2, 0] }), [['name', 'Target'], ['range', 'Range'], ['closing', 'Closing'], ['los', 'LOS rate'], ['rel_v', 'Relative speed']]);
  setGround = figures(box(root, 'GROUND', { at: [2, 1] }), [['lat', 'Latitude'], ['lon', 'Longitude'], ['alt', 'Altitude'], ['radar', 'Above ground']]);
}

const seconds = (value) => (value == null ? '—' : formatMet(value));

export function update() {
  const o = orbit(), body = bodyOf(o.body), safe = body ? body.atmosphere || 5000 : 0;
  setOrbit('body', o.body || '—');
  setOrbit('apo', o.apo == null ? 'escape' : km(o.apo, 2));
  setOrbit('peri', km(o.peri, 2), o.peri != null && o.peri < safe ? 'bad' : '');
  setOrbit('e', fixed(o.e, 4));
  setOrbit('i', fixed(o.i, 2, '°'));
  setOrbit('period', seconds(o.period));
  setOrbit('t_apo', seconds(o.t_apo));
  setOrbit('t_peri', seconds(o.t_peri));
  setOrbit('t_soi', seconds(o.t_soi), o.t_soi != null && o.t_soi < 600 ? 'warn' : '');

  const target = store['tlm/target'] || {};
  setTarget('name', target.set ? target.name || '?' : 'none');
  setTarget('range', target.set ? (target.range > 100000 ? km(target.range) : fixed(target.range, 1, 'm')) : '—');
  setTarget('closing', target.set ? fixed(target.closing, 2, 'm/s') : '—');
  setTarget('los', target.set ? fixed(target.los_rate, 3, '°/min') : '—');
  setTarget('rel_v', target.set ? fixed(target.rel_v, 2, 'm/s') : '—');

  const f = flight();
  setGround('lat', fixed(f.lat, 3, '°'));
  setGround('lon', fixed(f.lon, 3, '°'));
  setGround('alt', km(f.alt, 2));
  setGround('radar', fixed(f.radar, 0, 'm'));
  drawOrbit(o, body);
}

/* Top-down: the body, its atmosphere, the orbit (a, e, argument of periapsis) and the vessel at its true anomaly. */
function drawOrbit(o, body) {
  const g = canvas.getContext('2d'), size = canvas.width, centre = size / 2;
  g.clearRect(0, 0, size, size);
  if (!body) return;
  const closed = o.a && o.e != null && o.e < 1;
  const farthest = closed ? o.a * (1 + o.e) : body.radius * 4;
  const scale = (size * 0.45) / Math.max(farthest, body.radius * 1.2);
  if (body.atmosphere) {
    g.fillStyle = 'rgba(76,150,255,.14)';
    g.beginPath(); g.arc(centre, centre, (body.radius + body.atmosphere) * scale, 0, 2 * Math.PI); g.fill();
  }
  g.fillStyle = body.color;
  g.beginPath(); g.arc(centre, centre, body.radius * scale, 0, 2 * Math.PI); g.fill();
  if (!o.a || o.e == null) return;
  const periapsisDirection = ((o.argp || 0) * Math.PI) / 180;
  const semiLatusRectum = o.a * (1 - o.e * o.e);
  const point = (anomaly) => {
    const radius = semiLatusRectum / (1 + o.e * Math.cos(anomaly));
    return [centre + radius * scale * Math.cos(anomaly + periapsisDirection), centre - radius * scale * Math.sin(anomaly + periapsisDirection)];
  };
  const limit = o.e < 1 ? Math.PI : Math.acos(-1 / o.e) - 0.05;
  g.strokeStyle = '#d9d6cd'; g.lineWidth = 2; g.beginPath();
  for (let step = 0; step <= 360; step++) {
    const [x, y] = point(-limit + (2 * limit * step) / 360);
    if (step === 0) g.moveTo(x, y); else g.lineTo(x, y);
  }
  g.stroke();
  const [x, y] = point(((o.nu || 0) * Math.PI) / 180);
  g.fillStyle = '#ffb000';
  g.beginPath(); g.arc(x, y, 6, 0, 2 * Math.PI); g.fill();
}
