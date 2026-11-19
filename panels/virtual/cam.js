/* Camera monitor: shows one camera of the JRTI mod (Just Read The Instructions, a KSP mod that streams the craft's
   Hullcam cameras as MJPEG). A camera is listed once JRTI streams it: its "Auto-stream every camera" setting, or
   Stream pressed for that camera in its window.

   On the bus this page is the camera node:
     cam/list    (this page, retained)   {"cameras": [{"id", "name", "vessel"}]}: what can be shown
     cam/status  (this page, retained)   {"online", "playing"}
     cam/select  (cockpit logic)         {"id", "off"}: the camera to show, chosen on the CAMERA panel; "off" (its
                                         MONITOR switch): a black screen, no NO SIGNAL flag

   URL: cam.html?broker=ws://host:9001&jrti=/jrti
   JRTI's server (port 8080 on the KSP machine) is reached through the panel server's /jrti/ (panels/nginx.conf):
   JRTI sends no CORS header, so its camera list must come from this page's own origin.

   With ?window=left (or right) the page is one of the console's two windows instead: it shows the camera the
   cockpit logic puts on cam/window/left, fills the screen with it, writes no caption, and publishes nothing (the
   monitor is the camera node). A window also holds its camera at the window's field of view (WINDOW_FOV_DEG, or
   ?fov=), set through JRTI's camera settings and checked again on every camera list, since JRTI does not keep it
   across a reload and its viewer can change it.

   ?rotate=90 (or -90, 180) turns the picture by that many degrees, clockwise: for a window camera rolled on its part
   in the VAB, so that a portrait window gets the whole of JRTI's landscape picture, standing up. */

import { connectBus } from './bus.js';

const CAMERA_LIST_EVERY_MS = 3000;
const RETRY_AFTER_MS = 3000;
const WINDOW_FOV_DEG = 50;              // a capsule window seen from the seat
const FOV_TOLERANCE_DEG = 0.5;

const urlParameters = new URLSearchParams(location.search);
const jrtiUrl = urlParameters.get('jrti') || '/jrti';
const windowSide = urlParameters.get('window');           // 'left' or 'right': a window, not the monitor
const selectTopic = windowSide ? `cam/window/${windowSide}` : 'cam/select';
const windowFov = windowSide ? Number(urlParameters.get('fov')) || WINDOW_FOV_DEG : null;
if (windowSide) document.documentElement.classList.add('window-view');

const picture = document.getElementById('picture');
const screen = picture.parentElement;
const rotation = [90, -90, 180].includes(Number(urlParameters.get('rotate'))) ? Number(urlParameters.get('rotate')) : 0;
if (rotation) {
  picture.classList.add('rotated');
  picture.style.setProperty('--rotation', `${rotation}deg`);
  // a quarter turn: the picture is laid out with the screen's width and height swapped, then turned
  const quarterTurn = Math.abs(rotation) === 90;
  new ResizeObserver(() => {
    const { width, height } = screen.getBoundingClientRect();
    picture.style.width = `${quarterTurn ? height : width}px`;
    picture.style.height = `${quarterTurn ? width : height}px`;
  }).observe(screen);
}
const flag = document.getElementById('flag');
const caption = document.getElementById('caption');
const sourceText = document.getElementById('source');

let client = null;
let cameras = [];                       // as published on cam/list
let publishedList = '';
let wantedCameraId = null;              // from cam/select
let shownCameraId = null;               // the camera whose stream the picture is fed from
let playing = false;
let retryTimer = null;

function publish(topic, payload) {
  if (windowSide) return;               // a window only shows; the monitor speaks for the cameras
  if (client && client.connected) client.publish(topic, JSON.stringify(payload), { qos: 1, retain: true });
}

function setPlaying(isPlaying) {
  if (isPlaying === playing) return;
  playing = isPlaying;
  flag.hidden = isPlaying;
  publish('cam/status', { online: true, playing });
}

/* JRTI names a camera "<vessel>.<camera name>", the camera name being the one set in the part's menu (or the Hullcam
   part's own). Cameras with the same name (four docking ports) are numbered, so that the panel's display can tell
   them apart. */
function nameCameras(jrtiCameras) {
  const streaming = jrtiCameras.filter((camera) => camera.streaming).map((camera) => {
    const fullName = String(camera.name || '');
    const dot = fullName.lastIndexOf('.');
    return { id: camera.id, name: dot >= 0 ? fullName.slice(dot + 1) : fullName, vessel: dot >= 0 ? fullName.slice(0, dot) : '' };
  });
  const countByName = new Map();
  for (const camera of streaming) countByName.set(camera.name, (countByName.get(camera.name) || 0) + 1);
  const numberByName = new Map();
  return streaming.map((camera) => {
    if (countByName.get(camera.name) < 2) return camera;
    numberByName.set(camera.name, (numberByName.get(camera.name) || 0) + 1);
    return { ...camera, name: `${camera.name} ${numberByName.get(camera.name)}` };
  });
}

async function refreshCameraList() {
  try {
    const response = await fetch(`${jrtiUrl}/cameras`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`JRTI: ${response.status}`);
    cameras = nameCameras(await response.json());
    sourceText.textContent = `jrti: ✓ ${cameras.length} cameras`;
  } catch {
    cameras = [];
    sourceText.textContent = 'jrti: ✗';
  }
  const list = JSON.stringify({ cameras });
  if (list !== publishedList) {
    publishedList = list;
    publish('cam/list', { cameras });
  }
  showWantedCamera();
  holdWindowFov();
}

/* A window's camera at the window's field of view: JRTI's /camera/<id>/settings takes the keys it is given. */
async function holdWindowFov() {
  if (windowFov === null || shownCameraId === null) return;
  const cameraId = shownCameraId;
  try {
    const settings = await (await fetch(`${jrtiUrl}/camera/${cameraId}/settings`, { cache: 'no-store' })).json();
    if (settings.fov == null || Math.abs(settings.fov - windowFov) <= FOV_TOLERANCE_DEG) return;
    await fetch(`${jrtiUrl}/camera/${cameraId}/settings`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ fov: windowFov }),
    });
  } catch { /* JRTI away (not in flight): the next camera list tries again */ }
}

function stopPicture() {
  clearTimeout(retryTimer);
  shownCameraId = null;
  picture.removeAttribute('src');
  setPlaying(false);
}

/* Feed the picture from the wanted camera's stream unless it already is. */
function showWantedCamera() {
  const camera = cameras.find((candidate) => candidate.id === wantedCameraId);
  caption.textContent = camera && !windowSide ? `${camera.name} · ${camera.vessel}` : '';
  if (!camera) {
    if (shownCameraId !== null) stopPicture();
    return;
  }
  if (shownCameraId === camera.id) return;
  stopPicture();
  shownCameraId = camera.id;
  picture.src = `${jrtiUrl}/camera/${camera.id}/stream`;
  holdWindowFov();
}

/* An MJPEG stream in an <img>: the first frame is a load, a broken or ended stream an error. */
picture.addEventListener('load', () => setPlaying(Boolean(picture.getAttribute('src'))));
picture.addEventListener('error', () => {
  if (!picture.getAttribute('src')) return;
  const cameraId = shownCameraId;
  stopPicture();
  retryTimer = setTimeout(() => { if (wantedCameraId === cameraId) showWantedCamera(); }, RETRY_AFTER_MS);
});

function connectToBus() {
  client = connectBus({
    name: windowSide ? `window-${windowSide}` : 'camera-monitor',
    will: windowSide ? undefined : { topic: 'cam/status', payload: { online: false, playing: false } },
    onConnect: (connection) => {
      connection.subscribe(selectTopic, { qos: 1 });
      publish('cam/status', { online: true, playing });
      publishedList = '';               // publish the list again on the next refresh
      refreshCameraList();
    },
    onMessage: (topic, text) => {
      if (topic !== selectTopic) return;
      try {
        const selection = JSON.parse(text);
        wantedCameraId = selection.id ?? null;
        document.documentElement.classList.toggle('switched-off', Boolean(selection.off));
      } catch { return; }
      showWantedCamera();
    },
  });
}

connectToBus();
setInterval(refreshCameraList, CAMERA_LIST_EVERY_MS);
