"""Frame-rate sampler for the window cameras: the game's frame rate and JRTI's per-camera render cost, once a second.

Read only: it asks JRTI's debug page (http://localhost:8080/debug/stats), nvidia-smi if there is one, and on Linux the
KSP process's CPU use. Standard library only, so it runs the same on Linux and on Windows (python tests/framerate.py).

    python tests/framerate.py [seconds] [label]        # default 15 s

How to read the results and what was measured so far: PERFORMANCE.md.
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

JRTI_STATS = os.environ.get('JRTI_STATS', 'http://localhost:8080/debug/stats')


def jrti_stats():
    try:
        with urllib.request.urlopen(JRTI_STATS, timeout=1) as response:
            return json.load(response)
    except Exception:
        return {}


def gpu():
    """(utilisation %, memory MB) from nvidia-smi, or ('', '') without one."""
    if not shutil.which('nvidia-smi'):
        return '', ''
    try:
        out = subprocess.run(['nvidia-smi', '--query-gpu=utilization.gpu,memory.used', '--format=csv,noheader,nounits'],
                             capture_output=True, text=True, timeout=2).stdout.strip().splitlines()[0]
        load, memory = (part.strip() for part in out.split(','))
        return load, memory
    except Exception:
        return '', ''


class KspCpu:
    """The KSP process's CPU use in % of one core, on Linux (from /proc); '' elsewhere."""
    def __init__(self):
        self.pid = None
        if os.path.isdir('/proc'):
            for pid in filter(str.isdigit, os.listdir('/proc')):
                try:
                    with open(f'/proc/{pid}/cmdline', 'rb') as f:
                        if b'KSP.x86_64' in f.read():
                            self.pid = pid
                            break
                except OSError:
                    continue
        self.last = self._ticks()

    def _ticks(self):
        if not self.pid:
            return None
        try:
            with open(f'/proc/{self.pid}/stat') as f:
                fields = f.read().rsplit(')', 1)[1].split()
            return int(fields[11]) + int(fields[12]), time.monotonic()
        except OSError:
            return None

    def sample(self):
        now = self._ticks()
        if not now or not self.last:
            return ''
        (t1, w1), (t0, w0) = now, self.last
        self.last = now
        return round(100 * (t1 - t0) / os.sysconf('SC_CLK_TCK') / max(w1 - w0, 1e-6))


def main():
    seconds = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    label = sys.argv[2] if len(sys.argv) > 2 else 'sample'
    cpu = KspCpu()
    print(f'== {label}  ({seconds} s)')
    print(f'{"t":>3} {"fps":>6} {"frame_ms":>8} {"max_ms":>7} {"jrti_ms":>7} {"gpu%":>5} {"gpu_mb":>6} {"ksp_cpu":>7} {"viewers":>7}')
    for second in range(1, seconds + 1):
        time.sleep(1)
        s = jrti_stats()
        load, memory = gpu()
        print(f'{second:>3} {round(s.get("fps", 0), 1):>6} {round(s.get("frame_ms_avg", 0), 1):>8} '
              f'{round(s.get("frame_ms_max", 0), 1):>7} {round(s.get("jrti_ms_avg", 0), 1):>7} {load:>5} {memory:>6} '
              f'{cpu.sample():>7} {s.get("stream_clients", "-"):>7}')
    s = jrti_stats()
    if not s:
        print('JRTI not answering: is the game in flight, with its web server on?')
        return
    print(f'max_fps {s.get("max_fps")}  spread {s.get("spread")}')
    for camera in s.get('cameras', []):
        print(f'  {camera["camera"]:<28} renders/s {round(camera["renders_per_s"], 1):>5}  '
              f'render_ms {round(camera["render_ms_avg"], 1):>5}  capture_ms {round(camera["capture_ms_avg"], 1):>5}  '
              f'viewers {camera["stream_clients"]}')


if __name__ == '__main__':
    main()
