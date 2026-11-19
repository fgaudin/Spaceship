/* Camera monitor: shows one camera of the Kerbcast mod (a KSP mod that streams the craft's cameras over WebRTC).

   On the bus this page is the camera node:
     cam/list    (this page, retained)   {"cameras": [{"id", "name", "vessel", "kind"}]}: what can be shown
     cam/status  (this page, retained)   {"online", "playing"}
     cam/select  (cockpit logic)         {"id"}: the camera to show, chosen on the CAMERA panel

   URL: cam.html?broker=ws://host:9001&kerbcast=http://host:8088
   Kerbcast listens on this machine only unless its BindAddress setting is changed. */

import { connectBus } from './bus.js';

const CAMERA_LIST_EVERY_MS = 3000;
const RETRY_AFTER_MS = 3000;
const ICE_GATHERING_TIMEOUT_MS = 2000;
const STALLED_AFTER_MS = 4000;          // no new picture for this long: NO SIGNAL

const urlParameters = new URLSearchParams(location.search);
const host = location.hostname || 'localhost';
const kerbcastUrl = urlParameters.get('kerbcast') || `http://${host}:8088`;

const video = document.getElementById('video');
const flag = document.getElementById('flag');
const caption = document.getElementById('caption');
const sourceText = document.getElementById('source');

let client = null;
let cameras = [];                       // as published on cam/list
let publishedList = '';
let wantedCameraId = null;              // from cam/select
let shownCameraId = null;               // the camera the current connection carries
let connection = null;                  // RTCPeerConnection to Kerbcast
let connectionNumber = 0;               // to drop the results of a connection that has been replaced
let playing = false;
let lastPictureAt = 0;
let retryTimer = null;

function publish(topic, payload) {
  if (client && client.connected) client.publish(topic, JSON.stringify(payload), { qos: 1, retain: true });
}

function setPlaying(isPlaying) {
  if (isPlaying === playing) return;
  playing = isPlaying;
  flag.hidden = isPlaying;
  publish('cam/status', { online: true, playing });
}

/* Cameras with the same name (four docking ports) are numbered, so that the panel's display can tell them apart. */
function nameCameras(kerbcastCameras) {
  const active = kerbcastCameras.filter((camera) => camera.lifecycle === 'active');
  const countByName = new Map();
  for (const camera of active) countByName.set(camera.cameraName, (countByName.get(camera.cameraName) || 0) + 1);
  const numberByName = new Map();
  return active.map((camera) => {
    let name = camera.cameraName;
    if (countByName.get(name) > 1) {
      numberByName.set(name, (numberByName.get(name) || 0) + 1);
      name = `${name} ${numberByName.get(name)}`;
    }
    return { id: camera.flightId, name, vessel: camera.vesselName, kind: camera.kind };
  });
}

async function refreshCameraList() {
  try {
    const response = await fetch(`${kerbcastUrl}/cameras`, { cache: 'no-store' });
    cameras = nameCameras((await response.json()).cameras || []);
    sourceText.textContent = `kerbcast: ✓ ${cameras.length} cameras`;
  } catch {
    cameras = [];
    sourceText.textContent = 'kerbcast: ✗';
  }
  const list = JSON.stringify({ cameras });
  if (list !== publishedList) {
    publishedList = list;
    publish('cam/list', { cameras });
  }
  showWantedCamera();
}

function closeConnection() {
  connectionNumber++;
  if (connection) connection.close();
  connection = null;
  shownCameraId = null;
  video.srcObject = null;
  setPlaying(false);
}

function retryLater() {
  clearTimeout(retryTimer);
  retryTimer = setTimeout(showWantedCamera, RETRY_AFTER_MS);
}

/* Connect to the wanted camera unless it is already the one shown. */
function showWantedCamera() {
  const camera = cameras.find((candidate) => candidate.id === wantedCameraId);
  caption.textContent = camera ? `${camera.name} · ${camera.vessel}` : '';
  if (!camera) {
    if (connection) closeConnection();
    return;
  }
  if (shownCameraId === camera.id && connection) return;
  closeConnection();
  connect(camera.id).catch(() => { closeConnection(); retryLater(); });
}

function iceGatheringDone(peer) {
  if (peer.iceGatheringState === 'complete') return Promise.resolve();
  return new Promise((resolve) => {
    peer.addEventListener('icegatheringstatechange', () => { if (peer.iceGatheringState === 'complete') resolve(); });
    setTimeout(resolve, ICE_GATHERING_TIMEOUT_MS);
  });
}

/* Kerbcast's protocol: one receive-only video track per camera asked for, a control data channel, and the SDP offer
   posted with the camera ids; the answer comes back in the reply. */
async function connect(cameraId) {
  const peer = new RTCPeerConnection();
  const myNumber = ++connectionNumber;
  connection = peer;
  shownCameraId = cameraId;
  peer.addTransceiver('video', { direction: 'recvonly' });
  peer.addEventListener('track', (event) => {
    if (myNumber !== connectionNumber) return;
    video.srcObject = new MediaStream([event.track]);
    video.play().catch(() => {});
  });
  peer.addEventListener('connectionstatechange', () => {
    if (myNumber === connectionNumber && ['failed', 'closed', 'disconnected'].includes(peer.connectionState)) {
      closeConnection();
      retryLater();
    }
  });
  const control = peer.createDataChannel('kerbcast-control');
  const send = (message) => { if (control.readyState === 'open') control.send(JSON.stringify(message)); };
  control.addEventListener('open', () => {
    send({ type: 'hello' });
    // Kerbcast renders a camera at the size it is displayed
    send({ type: 'report-display-size', content: { flightId: cameraId, width: video.clientWidth, height: video.clientHeight } });
  });
  control.addEventListener('message', (event) => {
    try { if (JSON.parse(event.data).type === 'ping') send({ type: 'pong' }); } catch { /* not for us */ }
  });

  await peer.setLocalDescription(await peer.createOffer());
  await iceGatheringDone(peer);
  const response = await fetch(`${kerbcastUrl}/offer`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sdp: peer.localDescription.sdp, cameras: [cameraId] }),
  });
  if (!response.ok) throw new Error(`Kerbcast refused the offer: ${response.status}`);
  const answer = await response.json();
  if (myNumber !== connectionNumber) return;
  await peer.setRemoteDescription({ type: 'answer', sdp: answer.sdp });
}

/* "Playing" means pictures keep coming, not just that a connection exists. */
function watchPictures() {
  let lastTime = -1;
  setInterval(() => {
    if (video.srcObject && video.currentTime !== lastTime) {
      lastTime = video.currentTime;
      lastPictureAt = performance.now();
    }
    setPlaying(Boolean(video.srcObject) && performance.now() - lastPictureAt < STALLED_AFTER_MS);
  }, 500);
}

function connectToBus() {
  client = connectBus({
    name: 'camera-monitor',
    will: { topic: 'cam/status', payload: { online: false, playing: false } },
    onConnect: (connection) => {
      connection.subscribe('cam/select', { qos: 1 });
      publish('cam/status', { online: true, playing });
      publishedList = '';               // publish the list again on the next refresh
      refreshCameraList();
    },
    onMessage: (topic, text) => {
      if (topic !== 'cam/select') return;
      try { wantedCameraId = JSON.parse(text).id ?? null; } catch { return; }
      showWantedCamera();
    },
  });
}

connectToBus();
watchPictures();
setInterval(refreshCameraList, CAMERA_LIST_EVERY_MS);
