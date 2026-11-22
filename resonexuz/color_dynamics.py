"""Dinámica de color: tono (centroide), velocidad del beat y dos detectores de pico independientes."""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

import numpy as np

# Rangos de frecuencia (Hz) según la especificación.
SUB_RANGE = (30.0, 110.0)      # pico primario: bombo / drop
LOW_RANGE = (30.0, 250.0)      # flujo para onsets (velocidad del beat)
HIGH_RANGE = (1500.0, 8000.0)  # pico secundario: caja / transiente agudo
CENTROID_RANGE = (60.0, 4500.0)

BPM_SLOW, BPM_FAST = 65.0, 170.0
ONSET_WINDOW_S = 4.0
ONSET_REFRACTORY_S = 0.20
HUE_RED, HUE_VIOLET = 0.0, 0.78   # espectro de luz visible en HSV: rojo (grave) ... violeta (agudo)
N_ZONES = 8                        # zonas de frecuencia del historial de picos (8 bandas cada una)
TAU_PRIMARY, TAU_SECONDARY = 0.14, 0.10  # decaimiento de los picos en segundos (independiente de los FPS)


def lerp_angle(a: float, b: float, t: float) -> float:
    """Interpolación circular de matiz en [0, 1) por el camino más corto."""
    d = ((b - a + 0.5) % 1.0) - 0.5
    return (a + d * t) % 1.0


@dataclass(frozen=True)
class DynState:
    base_hue: float
    beat_speed: float
    bpm: float
    centroid_hz: float
    tonal_hue: float
    peak_pos: float     # posición media [0,1] (grave->agudo) de los picos de los últimos ~45 s
    peak_primary: float
    peak_secondary: float
    bass_env: float
    n_primary: int      # contadores acumulados de disparos (para telemetría)
    n_secondary: int


class ColorDynamics:
    def __init__(self, band_freqs: np.ndarray, block_dt: float, cfg: dict) -> None:
        self.f = band_freqs.astype(np.float64)
        self.block_dt = block_dt
        self.sub_mask = (self.f >= SUB_RANGE[0]) & (self.f <= SUB_RANGE[1])
        self.low_mask = (self.f >= LOW_RANGE[0]) & (self.f <= LOW_RANGE[1])
        self.high_mask = (self.f >= HIGH_RANGE[0]) & (self.f <= HIGH_RANGE[1])
        self.log_f = np.log10(self.f)

        peaks, color = cfg["peaks"], cfg["color"]
        self.primary_ratio = float(peaks["primary_ratio"])
        self.secondary_ratio = float(peaks["secondary_ratio"])
        self.hue_smoothing = float(color["hue_smoothing"])
        self.history_s = max(5.0, float(color["history_seconds"]))
        # La memoria corta nunca puede ser más larga que la mitad de la larga: si no, la comparación "ahora vs. habitual" se invierte.
        self.short_s = max(1.0, min(float(color["short_seconds"]), self.history_s * 0.5))
        self.mode_weight = float(np.clip(color["mode_weight"], 0.0, 1.0))
        self.short_influence = float(color["short_influence"])
        self.tempo_influence = float(color["tempo_influence"])
        self.tone_influence = float(color["tone_influence"])

        self.base_hue = 0.45
        self.beat_speed = 0.35
        self.bpm = 0.0
        self.centroid_log = 0.5 * (math.log10(CENTROID_RANGE[0]) + math.log10(CENTROID_RANGE[1]))
        self.tonal_hue = 0.4
        self.peak_pos = 0.5
        self._tonal_norm = 0.5
        self._hist = np.zeros(N_ZONES)        # memoria larga de picos por zona (history_seconds)
        self._hist_fast = np.zeros(N_ZONES)   # memoria corta (short_seconds): qué se enfatiza ahora
        self.short_pos = 0.5
        self._zone_pos = (np.arange(N_ZONES) + 0.5) / N_ZONES
        self._hist_decay = math.exp(-block_dt / self.history_s)
        self._fast_decay = math.exp(-block_dt / self.short_s)
        self.peak_primary = 0.0
        self.peak_secondary = 0.0
        self.bass_target = 0.0
        self.n_primary = 0
        self.n_secondary = 0

        self._prev = np.zeros_like(self.f)
        self._ema_sub = 0.02
        self._prev_sub = 0.0
        self._ema_flux_low = 0.02
        self._prev_flux_low = 0.0
        self._ema_flux_high = 0.02
        self._onsets: deque[float] = deque()
        self._last_onset = -10.0
        self._media_t = 0.0

    # ---- análisis por bloque de audio (hilo de captura) ----
    def update(self, norm: np.ndarray, active: bool) -> None:
        """norm: 64 bandas normalizadas [0,1]. active=False en silencio: no hay picos ni onsets."""
        self._media_t += self.block_dt
        t = self._media_t
        diff = np.maximum(0.0, norm - self._prev)
        self._prev = norm.copy()

        sub = float(norm[self.sub_mask].mean()) if self.sub_mask.any() else 0.0
        self.bass_target = float(norm[self.low_mask].mean()) if self.low_mask.any() else 0.0
        flux_low = float(diff[self.low_mask].mean()) if self.low_mask.any() else 0.0
        flux_high = float(diff[self.high_mask].mean()) if self.high_mask.any() else 0.0

        if active:
            # Pico primario (bombo / drop): sub-grave sobre su media móvil y subiendo.
            if sub > max(self._ema_sub * self.primary_ratio, 0.08) and sub > self._prev_sub:
                strength = min((sub - self._ema_sub) * 3.8 + 0.25, 1.0)
                if strength > self.peak_primary * 0.6:   # evita contar el mismo golpe varias veces
                    self.n_primary += 1
                self.peak_primary = max(self.peak_primary, strength)
            # Pico secundario (caja / agudos): flujo medio-agudo sobre su media móvil.
            if flux_high > max(self._ema_flux_high * self.secondary_ratio, 0.015):
                ratio = flux_high / (self._ema_flux_high + 0.02)
                strength = min(max((ratio - self.secondary_ratio) / 2.0 + 0.45, 0.4), 1.0)
                if strength > self.peak_secondary * 0.6:
                    self.n_secondary += 1
                self.peak_secondary = max(self.peak_secondary, strength)
            # Onsets graves/medios -> velocidad del beat.
            if (flux_low > max(self._ema_flux_low * 1.6, 0.05) and flux_low > self._prev_flux_low
                    and t - self._last_onset > ONSET_REFRACTORY_S):
                self._onsets.append(t)
                self._last_onset = t

        self._ema_sub = 0.92 * self._ema_sub + 0.08 * sub
        self._ema_flux_low = 0.9 * self._ema_flux_low + 0.1 * flux_low
        self._ema_flux_high = 0.9 * self._ema_flux_high + 0.1 * flux_high
        self._prev_sub = sub
        self._prev_flux_low = flux_low

        while self._onsets and t - self._onsets[0] > ONSET_WINDOW_S:
            self._onsets.popleft()

        self._hist *= self._hist_decay
        self._hist_fast *= self._fast_decay
        if active:
            # Historial de picos: cuánta subida de energía hubo en cada zona de frecuencia en los últimos ~45 s.
            zones = diff.reshape(N_ZONES, -1).mean(axis=1)
            self._hist += zones
            self._hist_fast += zones
        self._update_beat_speed()
        if active:
            self._update_tone(norm)
            self._update_peak_pos()
        self._update_hue()

    def _update_beat_speed(self) -> None:
        target = 0.35
        self.bpm = 0.0
        if len(self._onsets) >= 4:
            iv = np.diff(np.asarray(self._onsets))
            iv = iv[iv > 0.05]
            if iv.size:
                bpm = 60.0 / float(np.median(iv))
                while bpm > 190.0:
                    bpm /= 2.0
                while bpm < 50.0:
                    bpm *= 2.0
                self.bpm = bpm
                target = float(np.clip((bpm - BPM_SLOW) / (BPM_FAST - BPM_SLOW), 0.0, 1.0))
        self.beat_speed += (target - self.beat_speed) * 0.05

    def _update_tone(self, norm: np.ndarray) -> None:
        energy = norm.astype(np.float64) ** 2
        total = float(energy.sum())
        if total < 1e-3:
            return
        c_log = float((energy * self.log_f).sum() / (total + 1e-9))   # centroide logarítmico ponderado
        self.centroid_log += (c_log - self.centroid_log) * 0.08
        lo, hi = math.log10(CENTROID_RANGE[0]), math.log10(CENTROID_RANGE[1])
        tonal_norm = float(np.clip((self.centroid_log - lo) / (hi - lo), 0.0, 1.0))
        self._tonal_norm = tonal_norm
        self.tonal_hue = HUE_RED + tonal_norm * (HUE_VIOLET - HUE_RED)

    def _soft_mode(self, weights: np.ndarray, power: float) -> float:
        """Moda suave: posición del máximo sin saltos entre zonas (media ponderada con pesos elevados a una potencia)."""
        w = np.power(np.maximum(weights, 0.0), power)
        total = float(w.sum())
        return float((w * self._zone_pos).sum() / total) if total > 1e-9 else 0.5

    def _update_peak_pos(self) -> None:
        """Posición del historial largo = mezcla de la media y la moda (la media sola tiende al centro = verde)."""
        total = float(self._hist.sum())
        if total > 1e-3:
            mean = float((self._hist * self._zone_pos).sum() / total)
            mode = self._soft_mode(self._hist / total, 4.0)
            pos = (1.0 - self.mode_weight) * mean + self.mode_weight * mode
            self.peak_pos += (pos - self.peak_pos) * 0.01
        # Énfasis reciente respecto a la norma de la memoria larga: qué frecuencias destacan ahora.
        fast_total = float(self._hist_fast.sum())
        if total > 1e-3 and fast_total > 1e-3:
            rel = (self._hist_fast / fast_total) / (self._hist / total + 0.02)
            self.short_pos += (self._soft_mode(rel, 3.0) - self.short_pos) * 0.02

    def _update_hue(self) -> None:
        """Matiz sobre el espectro visible: ancla de la memoria larga + énfasis reciente + tono actual + velocidad."""
        stretched = float(np.clip((self.peak_pos - 0.10) / 0.45, 0.0, 1.0))     # media/moda reales ocupan ~10-55 %
        anchor = HUE_RED + stretched * (HUE_VIOLET - HUE_RED)                   # picos graves = rojo, agudos = violeta
        recent = (self.short_pos - 0.5) * 2.0 * self.short_influence            # lo que destaca ahora frente a lo habitual
        tone = (self._tonal_norm - 0.5) * self.tone_influence                   # tono de este instante
        tempo = -(self.beat_speed - 0.5) * self.tempo_influence                 # rápido -> hacia el rojo, lento -> violeta
        target = float(np.clip(anchor + recent + tone + tempo, HUE_RED, HUE_VIOLET))
        self.base_hue += (target - self.base_hue) * self.hue_smoothing         # lineal: no salta de violeta a rojo

    # ---- lectura desde el hilo de render ----
    def decay(self, dt: float) -> None:
        self.peak_primary *= math.exp(-dt / TAU_PRIMARY)
        self.peak_secondary *= math.exp(-dt / TAU_SECONDARY)

    def snapshot(self, bass_env: float) -> DynState:
        return DynState(
            base_hue=self.base_hue,
            beat_speed=self.beat_speed,
            bpm=self.bpm,
            centroid_hz=10.0 ** self.centroid_log,
            tonal_hue=self.tonal_hue,
            peak_pos=self.peak_pos,
            peak_primary=self.peak_primary,
            peak_secondary=self.peak_secondary,
            bass_env=bass_env,
            n_primary=self.n_primary,
            n_secondary=self.n_secondary,
        )
