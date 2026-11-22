"""Captura de audio global estéreo multiplataforma (Linux parec / Windows WASAPI / macOS), FFT y AGC."""
from __future__ import annotations

import atexit
import math
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass

import numpy as np

from .color_dynamics import ColorDynamics, DynState

SAMPLE_RATE = 44100
CHUNK = 1024
N_BANDS = 64
F_MIN, F_MAX = 30.0, 14000.0
BLOCK_DT = CHUNK / SAMPLE_RATE
STALE_S = 0.5

PAREC_CMD = [
    "parec", "--format=float32le", f"--rate={SAMPLE_RATE}", "--channels=2",
    "--device=@DEFAULT_MONITOR@", "--latency-msec=12",
]


@dataclass(frozen=True)
class Frame:
    spectrum: np.ndarray     # promedio estéreo (64 bandas [0,1])
    spectrum_l: np.ndarray   # canal izquierdo (64 bandas [0,1])
    spectrum_r: np.ndarray   # canal derecho (64 bandas [0,1])
    idle: float              # 0 = hay audio, 1 = reposo
    dyn: DynState
    stereo_balance: float    # -1 (izq) .. +1 (der)


class AudioEngine:
    def __init__(self, cfg: dict) -> None:
        a = cfg["audio"]
        self.sensitivity = float(a["sensitivity"])
        self.gamma = float(a["gamma"])
        self.silence_rms = float(a["silence_rms"])
        self.silence_seconds = float(a["silence_seconds"])
        self.stereo_sep = float(np.clip(float(a.get("stereo_separation", 1.0)), 0.0, 1.0))

        freqs = np.fft.rfftfreq(CHUNK, 1.0 / SAMPLE_RATE)
        self.fft_freqs = freqs
        edges = np.geomspace(F_MIN, F_MAX, N_BANDS + 1)
        self.band_freqs = np.sqrt(edges[:-1] * edges[1:])
        self.bin_ranges: list[tuple[int, int] | None] = []
        for i in range(N_BANDS):
            idx = np.where((freqs >= edges[i]) & (freqs < edges[i + 1]))[0]
            self.bin_ranges.append((int(idx[0]), int(idx[-1]) + 1) if len(idx) >= 2 else None)
        self.window = np.hanning(CHUNK).astype(np.float32)
        self.win_norm = float(self.window.sum() / 2.0)
        self.tilt = np.linspace(0.85, 2.4, N_BANDS, dtype=np.float32)

        self.dynamics = ColorDynamics(self.band_freqs, BLOCK_DT, cfg)
        self._lock = threading.Lock()
        self._agc_max = 0.015
        self._target_l = np.zeros(N_BANDS, dtype=np.float32)
        self._target_r = np.zeros(N_BANDS, dtype=np.float32)
        self._spec_l = np.zeros(N_BANDS, dtype=np.float32)
        self._spec_r = np.zeros(N_BANDS, dtype=np.float32)
        self._bass_env = 0.0
        self._balance_target = 0.0
        self._balance = 0.0
        self._silent_blocks = 0
        self._last_block = 0.0
        self._idle = 1.0
        self._last_snap = time.monotonic()
        self.rms = 0.0
        self.agc = self._agc_max

        self._running = False
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        atexit.register(self.stop)

    def update_config(self, cfg: dict) -> None:
        a = cfg["audio"]
        with self._lock:
            self.sensitivity = float(a["sensitivity"])
            self.gamma = float(a["gamma"])
            self.silence_rms = float(a["silence_rms"])
            self.silence_seconds = float(a["silence_seconds"])
            self.stereo_sep = float(np.clip(float(a.get("stereo_separation", 1.0)), 0.0, 1.0))

    def _fft_bands(self, ch: np.ndarray) -> np.ndarray:
        mag = np.abs(np.fft.rfft(ch * self.window)) / self.win_norm
        bands = np.empty(N_BANDS, dtype=np.float32)
        for i, rng in enumerate(self.bin_ranges):
            bands[i] = mag[rng[0]:rng[1]].mean() if rng else np.interp(self.band_freqs[i], self.fft_freqs, mag)
        return bands * self.tilt

    def process_block(self, samples: np.ndarray) -> None:
        samples = samples.astype(np.float32, copy=False)
        if samples.ndim == 2 and samples.shape[1] >= 2:
            left, right = samples[:, 0], samples[:, 1]
        elif samples.ndim == 2 and samples.shape[1] == 1:
            left = right = samples[:, 0]
        elif samples.size == CHUNK * 2:
            left, right = samples[0::2], samples[1::2]
        else:
            left = right = samples[:CHUNK]

        mono = 0.5 * (left + right)
        rms_l = float(np.sqrt(np.mean(left * left)))
        rms_r = float(np.sqrt(np.mean(right * right)))
        rms = max(rms_l, rms_r, float(np.sqrt(np.mean(mono * mono))))

        bands_l = self._fft_bands(left)
        bands_r = self._fft_bands(right)
        frame_max = float(max(bands_l.max(), bands_r.max()))
        self._agc_max = max(frame_max, self._agc_max * 0.993, 0.015)

        norm_l = np.clip(bands_l * self.sensitivity / self._agc_max, 0.0, 1.0) ** self.gamma
        norm_r = np.clip(bands_r * self.sensitivity / self._agc_max, 0.0, 1.0) ** self.gamma
        norm_mono = 0.5 * (norm_l + norm_r)

        silent = rms < self.silence_rms
        if silent:
            norm_l = norm_l * 0.0
            norm_r = norm_r * 0.0
            norm_mono = norm_mono * 0.0
        active = not silent
        bal = (rms_r - rms_l) / (rms_l + rms_r + 1e-6) if active else 0.0

        with self._lock:
            self._silent_blocks = self._silent_blocks + 1 if silent else 0
            sep = self.stereo_sep
            self._target_l = norm_mono + (norm_l - norm_mono) * sep
            self._target_r = norm_mono + (norm_r - norm_mono) * sep
            self._balance_target = bal * sep
            self._last_block = time.monotonic()
            self.rms = rms
            self.agc = self._agc_max
            self.dynamics.update(norm_mono, active)

    @staticmethod
    def _smooth_angular(arr: np.ndarray) -> np.ndarray:
        sp = np.pad(arr, 1, mode="edge")
        return (0.25 * sp[:-2] + 0.5 * sp[1:-1] + 0.25 * sp[2:]).astype(np.float32)

    def get_frame(self) -> Frame:
        now = time.monotonic()
        dt = min(max(now - self._last_snap, 1e-4), 0.1)
        self._last_snap = now
        with self._lock:
            stale = (now - self._last_block) > STALE_S
            quiet = stale or (self._silent_blocks > 0 and self._silent_blocks * BLOCK_DT >= self.silence_seconds)
            tl = self._target_l if not stale else np.zeros(N_BANDS, dtype=np.float32)
            tr = self._target_r if not stale else np.zeros(N_BANDS, dtype=np.float32)
            rise = 1.0 - math.exp(-dt / 0.025)
            fall = 1.0 - math.exp(-dt / 0.09)
            kl = np.where(tl > self._spec_l, rise, fall).astype(np.float32)
            kr = np.where(tr > self._spec_r, rise, fall).astype(np.float32)
            self._spec_l = self._spec_l + (tl - self._spec_l) * kl
            self._spec_r = self._spec_r + (tr - self._spec_r) * kr
            be_t = self.dynamics.bass_target if not stale else 0.0
            self._bass_env += (be_t - self._bass_env) * (rise if be_t > self._bass_env else fall)
            self._balance += (self._balance_target - self._balance) * (1.0 - math.exp(-dt / 0.08))
            self._idle += ((1.0 if quiet else 0.0) - self._idle) * (1.0 - math.exp(-dt / (2.5 if quiet else 0.2)))
            self.dynamics.decay(dt)
            dyn = self.dynamics.snapshot(self._bass_env)
            spec_l = self._smooth_angular(self._spec_l)
            spec_r = self._smooth_angular(self._spec_r)
            spec = 0.5 * (spec_l + spec_r)
        return Frame(spec, spec_l, spec_r, float(self._idle), dyn, float(self._balance))

    def start(self, demo: bool = False) -> None:
        self._running = True
        target = self._demo_loop if demo else self._capture_loop
        self._thread = threading.Thread(target=target, name="audio", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        proc, self._proc = self._proc, None
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                proc.kill()

    def _capture_loop(self) -> None:
        if sys.platform.startswith("linux") and shutil.which("parec"):
            self._capture_parec()
            return
        if self._capture_soundcard():
            return
        print("[resonexuz] No se encontró captura de sistema disponible; iniciando audio sintético (--demo).", file=sys.stderr)
        self._demo_loop()

    def _capture_parec(self) -> None:
        need = CHUNK * 2 * 4
        while self._running:
            try:
                self._proc = subprocess.Popen(PAREC_CMD, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
            except OSError:
                break
            proc = self._proc
            buf = b""
            while self._running and proc.stdout is not None:
                chunk = proc.stdout.read(need - len(buf))
                if not chunk:
                    break
                buf += chunk
                if len(buf) >= need:
                    self.process_block(np.frombuffer(buf[:need], dtype="<f4"))
                    buf = b""
            if proc.poll() is None:
                proc.terminate()
            if self._running:
                time.sleep(1.0)

    def _capture_soundcard(self) -> bool:
        try:
            import soundcard as sc
        except ImportError:
            return False

        while self._running:
            try:
                mic = None
                spk = sc.default_speaker()
                if spk is not None:
                    try:
                        mic = sc.get_microphone(id=str(spk.name), include_loopback=True)
                    except Exception:
                        mic = None
                if mic is None:
                    mics = sc.all_microphones(include_loopback=True)
                    for m in mics:
                        if getattr(m, "isloopback", False) or "blackhole" in m.name.lower() or "monitor" in m.name.lower():
                            mic = m
                            break
                    if mic is None and mics:
                        mic = mics[0]
                if mic is None:
                    return False

                with mic.recorder(samplerate=SAMPLE_RATE, channels=2, blocksize=CHUNK) as rec:
                    while self._running:
                        data = rec.record(numframes=CHUNK)
                        if data is not None and len(data) >= CHUNK:
                            self.process_block(data[:CHUNK])
            except Exception as exc:
                print(f"[resonexuz] Error en captura soundcard ({exc}); reintentando…", file=sys.stderr)
                time.sleep(1.5)
        return True

    def _demo_loop(self) -> None:
        rng = np.random.default_rng(1)
        t0 = time.monotonic()
        n = 0
        while self._running:
            self.process_block(demo_block_stereo(n, rng))
            n += 1
            sleep = t0 + n * BLOCK_DT - time.monotonic()
            if sleep > 0:
                time.sleep(sleep)


def demo_block_stereo(n: int, rng: np.random.Generator, bpm: float = 126.0) -> np.ndarray:
    """Bloque estéreo intercalado de audio sintético para pruebas en cualquier OS."""
    t = (np.arange(CHUNK) + n * CHUNK) / SAMPLE_RATE
    beat = 60.0 / bpm
    ph = t % beat
    kick = np.sin(2 * np.pi * (48.0 * ph + 90.0 * (1 - np.exp(-ph * 25)) / 25.0)) * np.exp(-ph * 9.0) * 0.8
    ph8 = (t + beat / 2) % beat
    hat = rng.standard_normal(CHUNK).astype(np.float32) * np.exp(-ph8 * 60.0) * 0.14
    ph2 = (t + beat) % (2 * beat)
    snare = (rng.standard_normal(CHUNK) * 0.5 + np.sin(2 * np.pi * 190 * ph2)) * np.exp(-ph2 * 18.0) * 0.25
    sweep = 220.0 * 2 ** (1.5 * np.sin(2 * np.pi * t / 24.0))
    pad = np.sin(2 * np.pi * sweep * t) * 0.10
    pan = 0.5 + 0.45 * np.sin(2 * np.pi * t / 4.0)
    left = kick + (snare * (ph2 < 0.2) + hat + pad) * (1.0 - pan * 0.7)
    right = kick + (snare * (ph2 < 0.2) + hat + pad) * (0.3 + pan * 0.7)
    out = np.empty(CHUNK * 2, dtype=np.float32)
    out[0::2] = left
    out[1::2] = right
    return out
