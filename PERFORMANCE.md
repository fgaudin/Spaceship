# Frame rate with the window cameras

The console's two windows are JRTI cameras (`cm_left`, `cm_right`, or `lm_left`, `lm_right`), and each one is drawn
by the game a second time. In JNSQ this halves the frame rate or worse. This page holds what was measured, the
settings that came out of it, and how to run the same test again, on another machine or system.

## The test

The sampler is [tests/framerate.py](tests/framerate.py) (standard library only, Linux or Windows). It reads JRTI's
debug page (`http://localhost:8080/debug/stats`) once a second, with `nvidia-smi` for the GPU and, on Linux, KSP's CPU
use. It changes nothing in the game.

```
python tests/framerate.py 15 baseline        # 15 s, labelled "baseline"
```

The columns: the game's frame rate and frame time (average and slowest), `jrti_ms` (JRTI's time per game frame,
averaged), the GPU's load and memory, KSP's CPU (in % of one core), the number of viewers. Then, per camera:
renders per second, time per render (`render_ms`, most of it `capture_ms`), viewers.

1. Hold the flight still: on the launch pad (the windows see the sky) is the most repeatable. Conditions that move
   (altitude, view, engines) change the numbers by 3–8 ms, more than most settings.
2. Open the two windows: the console's (`cam.html?window=left`, `?window=right`), or, without the cockpit stack, two
   JRTI viewers (`http://localhost:8080/viewer.html?id=<id>`, the ids from `http://localhost:8080/cameras`). JRTI's
   cost is per camera that has at least one viewer, whichever page it is.
3. Sample: windows open, then windows closed (the game alone), then each setting changed one at a time.

## What was measured (2026-11-23, Linux)

Ubuntu, X11, native Linux KSP (`KSP.x86_64`, OpenGL), RTX 4070 (driver 580), 20 threads, 62 GB. JNSQ with Scatterer,
EVE, Deferred, TUFX, Firefly, Waterfall, TexturesUnlimited, ReStock. AcapelloCam, 156–162 parts. JRTI 3.3.0 at
960 × 540, JPEG quality 85.

| Case | Game fps | Frame ms | JRTI ms/frame | First camera | Second camera |
|---|---|---|---|---|---|
| No viewers (the game alone) | 55 | 18 | 0 | – | – |
| Two windows, Max FPS 24 (never reached) | 20 | 50 | 23 | 16 | 7 |
| Max FPS 20 | 19 | 54 | 26 | 18 | 8 |
| Max FPS 15, spreading off | 21 | 47 | 16–21 | 15–20 | 6–8 |
| Max FPS 10, spreading on | 24–27 | 37–42 | 14 | 17–18 | 16–18 |
| Max FPS 10, spreading off | 30 | 33 | 10 | 18 | 8 |
| Max FPS 15, Scatterer and EVE removed from GameData | 36 | 28 | 10 | 11–14 | 11–14 |

What it says:

- **Cameras nobody watches cost nothing**: JRTI renders a camera only while it has a viewer. The LM's cameras while
  flying the CM, the docking-port NavCams: 0 renders. Nothing to build for that.
- **The GPU is never the limit**: 30–55 % in every case. The cost is on the processor's side.
- **The first camera of each game frame pays about 10 ms more than the next one**, whatever it sees: the extra moved
  with the rendering order, not with the camera (after a relaunch the other camera became the expensive one), and not
  with the view (lit side or dark, sky or ground). Most likely it waits for the GPU to finish the game's own view
  before it can draw (and read back) its picture.
- **A camera renders at most once per game frame, and at most Max FPS times a second.** The game slows down to make
  room, so a cap above the game's frame rate does nothing (24 and 20 changed nothing at about 20 fps); 15 barely
  helps; 10 does.
- **Spreading the captures (JRTI's Spread Captures) works against two windows**: each camera then has a frame to
  itself and pays the first camera's extra. Off, the two share a frame: about 25 ms in one frame, ten times a second,
  so a frame in three or so is slow (65–85 ms) and the motion less even.
- **No difference**: resolution, anti-aliasing (0 or 2: about 1 ms), what the camera looks at (lit side of the tower or
  dark: none; the ground instead of the sky: about +3 ms on the second camera), the plumes (Waterfall), the parts
  (156 or 120: about 1 ms).
- **JRTI's integration switches do not change the cost**: Deferred, Scatterer, EVE off in JRTI's settings, even after a
  revert or a relaunch from the VAB: the same camera cost, and the clouds still in the windows. Scatterer and EVE draw
  on every camera through their own hooks; JRTI's switches cover only what JRTI adds.
- **Scatterer and EVE themselves cost the game's own view 10–20 ms a frame** (removed from GameData: 36 fps instead of
  21 at Max FPS 15, KSP's CPU 154 % instead of 194 %). The cameras cost the same with or without them.

Settings for JNSQ on Linux: **Spread Captures off, Max FPS 10** (about 30 fps in the game, the windows at 10); 15 if
the windows matter more than the game. Anti-aliasing and resolution as wanted: they cost next to nothing.

Not tested: Deferred removed from GameData (its JRTI switch did nothing, like the others).

## Next: the same test on Windows

The open question is whether DirectX 11 (KSP on Windows, or the Windows build through Proton and DXVK) waits less, and
prepares each camera's frame faster, than OpenGL on Linux, since the processor's side is what limits. To compare:

- The same JNSQ mod set, installed by CKAN on Windows (mods with shaders per system, Scatterer, EVE, Deferred, TUFX,
  JRTI's HullcamShaders, need their Windows files; do not copy GameData from Linux).
- The same JRTI settings: 960 × 540, anti-aliasing 2, JPEG 85, Spread Captures off, then Max FPS 15 and 10. JRTI writes
  its settings file (`GameData/JustReadTheInstructions/PluginData/settings.cfg`) only when the game quits.
- The same craft (AcapelloCam) on the pad, two viewers, the rows of the table above: no viewers, Max FPS 15, Max FPS
  10; then with Scatterer and EVE removed if the gain is not enough.
- Python 3 on Windows runs the sampler as it is (`py tests\framerate.py 15 baseline`). KSP's CPU column stays empty
  there; Task Manager shows it.

The JRTI viewers are enough for the test; the cockpit stack is not needed. Running the stack on Windows (Docker Desktop
on WSL2) needs one change still to make: `gateway-ksp` and `mcc-data` use `network_mode: host` to reach kRPC on
127.0.0.1, which does not work from Docker Desktop's VM. The plan: kRPC's server address set to Any (allowed through
the Windows firewall on private networks only, since kRPC has no password), the two services pointed at
`host.docker.internal`, and the broker by name like the other services. Clone the repo inside WSL, not on a Windows
drive (bash scripts, line endings, bind-mount speed).
