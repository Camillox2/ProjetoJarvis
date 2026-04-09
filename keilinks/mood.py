"""
Detecção de humor pela voz usando features de áudio.
Analisa tom (pitch), velocidade (speech rate), energia e variação
para inferir o estado emocional do usuário.

Não depende de modelo ML pesado — usa heurísticas sobre features acústicas.
"""

import numpy as np
from dataclasses import dataclass
from keilinks.log import get_logger

log = get_logger("mood")


@dataclass
class VoiceMood:
    mood:       str     # "neutro", "animado", "cansado", "frustrado", "calmo", "ansioso"
    energy:     float   # 0.0 ~ 1.0
    pitch_hz:   float   # frequência fundamental média
    speed:      float   # taxa relativa (1.0 = normal)
    confidence: float   # 0.0 ~ 1.0


# Thresholds calibrados para voz masculina PT-BR
# (podem precisar de ajuste fino)
_PITCH_LOW   = 100.0   # Hz — voz grave / cansada
_PITCH_HIGH  = 220.0   # Hz — voz aguda / animada
_ENERGY_LOW  = 0.01
_ENERGY_HIGH = 0.08


class MoodDetector:
    def __init__(self, sample_rate: int = 16000):
        self._sr = sample_rate
        self._history: list[VoiceMood] = []
        self._baseline_energy: float | None = None
        # Thresholds customizáveis via VoiceProfile
        self._pitch_low   = _PITCH_LOW
        self._pitch_high  = _PITCH_HIGH
        self._energy_low  = _ENERGY_LOW
        self._energy_high = _ENERGY_HIGH

    def apply_profile_thresholds(self, thresholds: dict):
        """Aplica thresholds personalizados do VoiceProfile."""
        self._energy_low  = thresholds.get("energy_low", _ENERGY_LOW)
        self._energy_high = thresholds.get("energy_high", _ENERGY_HIGH)
        self._pitch_low   = thresholds.get("pitch_low", _PITCH_LOW)
        self._pitch_high  = thresholds.get("pitch_high", _PITCH_HIGH)
        log.info("Thresholds atualizados pelo perfil de voz.")

    def analyze(self, audio_data: np.ndarray) -> VoiceMood:
        """
        Analisa um trecho de áudio (numpy float32/int16) e retorna o humor detectado.
        """
        # Normaliza para float32 [-1, 1]
        if audio_data.dtype == np.int16:
            audio = audio_data.astype(np.float32) / 32768.0
        else:
            audio = audio_data.astype(np.float32)

        if len(audio) < self._sr * 0.5:
            return VoiceMood("neutro", 0.5, 0.0, 1.0, 0.0)

        energy   = self._compute_energy(audio)
        pitch    = self._estimate_pitch(audio)
        speed    = self._estimate_speed(audio)
        variance = self._pitch_variance(audio)

        # Atualiza baseline de energia antes da classificação
        if self._baseline_energy is None:
            self._baseline_energy = energy
        else:
            self._baseline_energy = 0.9 * self._baseline_energy + 0.1 * energy

        mood, confidence = self._classify(energy, pitch, speed, variance)

        result = VoiceMood(
            mood=mood,
            energy=min(1.0, energy / max(_ENERGY_HIGH, 0.001)),
            pitch_hz=pitch,
            speed=speed,
            confidence=confidence,
        )

        self._history.append(result)
        if len(self._history) > 50:
            self._history = self._history[-50:]

        log.debug("Humor: %s (conf=%.2f, energy=%.4f, pitch=%.0fHz, speed=%.2f)",
                  mood, confidence, energy, pitch, speed)
        return result

    # ─── Features ─────────────────────────────────────────────────────────────
    @staticmethod
    def _compute_energy(audio: np.ndarray) -> float:
        """RMS energy do sinal."""
        return float(np.sqrt(np.mean(audio ** 2)))

    def _estimate_pitch(self, audio: np.ndarray) -> float:
        """
        Estimativa de pitch via autocorrelação.
        Retorna frequência fundamental em Hz (0 se não detectar).
        """
        # Janela no centro do áudio (evita silêncio nas bordas)
        center = len(audio) // 2
        window = audio[max(0, center - self._sr // 2): center + self._sr // 2]

        if len(window) < 1024:
            return 0.0

        # Autocorrelação
        corr = np.correlate(window, window, mode='full')
        corr = corr[len(corr) // 2:]

        # Limita à faixa de voz humana (80Hz ~ 300Hz)
        min_lag = self._sr // 300  # ~53 amostras para 300Hz
        max_lag = self._sr // 80   # ~200 amostras para 80Hz

        if max_lag >= len(corr):
            return 0.0

        segment = corr[min_lag:max_lag]
        if len(segment) == 0:
            return 0.0

        peak_idx = np.argmax(segment) + min_lag
        if peak_idx == 0:
            return 0.0

        return float(self._sr / peak_idx)

    def _estimate_speed(self, audio: np.ndarray) -> float:
        """
        Estimativa de velocidade da fala baseada em detecção de sílabas.
        Retorna taxa relativa (1.0 = ~4 sílabas/segundo).
        """
        # Envelope de energia em frames de 20ms
        frame_size = int(self._sr * 0.02)
        n_frames   = len(audio) // frame_size
        if n_frames < 5:
            return 1.0

        envelope = np.array([
            np.sqrt(np.mean(audio[i * frame_size:(i + 1) * frame_size] ** 2))
            for i in range(n_frames)
        ])

        # Normaliza
        if envelope.max() < 1e-6:
            return 1.0
        envelope = envelope / envelope.max()

        # Conta cruzamentos acima de 0.3 (proxy para sílabas)
        threshold = 0.3
        above     = envelope > threshold
        crossings = np.sum(np.diff(above.astype(int)) == 1)

        duration_secs = len(audio) / self._sr
        syllables_per_sec = crossings / max(duration_secs, 0.1)

        # Normaliza: 4 sílabas/s = velocidade 1.0
        return syllables_per_sec / 4.0

    def _pitch_variance(self, audio: np.ndarray) -> float:
        """Variação de pitch ao longo do áudio (indica expressividade)."""
        segments = np.array_split(audio, min(8, len(audio) // (self._sr // 4)))
        pitches  = [self._estimate_pitch(seg) for seg in segments if len(seg) > 1024]
        pitches  = [p for p in pitches if p > 50]
        if len(pitches) < 2:
            return 0.0
        return float(np.std(pitches))

    # ─── Classificação ────────────────────────────────────────────────────────
    def _classify(self, energy: float, pitch: float, speed: float,
                  variance: float) -> tuple[str, float]:
        """
        Classifica o humor com base nas features acústicas.
        Retorna (mood, confidence).
        """
        rel_energy = energy / max(self._baseline_energy or self._energy_high, 0.001)

        # Regras heurísticas (usa thresholds da instância)
        if energy < self._energy_low and speed < 0.7:
            return "cansado", 0.7

        if energy > self._energy_high and speed > 1.3 and pitch > self._pitch_high:
            return "animado", 0.8

        if energy > self._energy_high * 0.8 and speed > 1.2 and variance > 30:
            return "ansioso", 0.6

        if energy > self._energy_high and speed > 1.0 and pitch > self._pitch_high * 0.8:
            if variance > 25:
                return "frustrado", 0.6

        if energy < self._energy_high * 0.5 and speed < 0.9 and pitch < self._pitch_low * 1.3:
            return "calmo", 0.6

        if rel_energy > 1.5 and speed > 1.1:
            return "animado", 0.5

        if rel_energy < 0.6 and speed < 0.85:
            return "cansado", 0.5

        return "neutro", 0.4

    # ─── Trending ─────────────────────────────────────────────────────────────
    def get_trend(self, n: int = 5) -> str:
        """Retorna tendência das últimas N análises."""
        recent = self._history[-n:] if self._history else []
        if not recent:
            return "neutro"

        moods = [m.mood for m in recent]
        # Moda
        from collections import Counter
        most_common = Counter(moods).most_common(1)[0][0]
        return most_common

    def get_summary(self) -> str:
        """Resumo textual do humor para incluir no prompt do LLM."""
        if not self._history:
            return ""
        last = self._history[-1]
        trend = self.get_trend()

        parts = [f"Humor detectado: {last.mood}"]
        if last.energy > 0.7:
            parts.append("energia alta")
        elif last.energy < 0.3:
            parts.append("energia baixa")
        if last.speed > 1.2:
            parts.append("falando rápido")
        elif last.speed < 0.8:
            parts.append("falando devagar")
        if trend != last.mood:
            parts.append(f"tendência: {trend}")

        return " | ".join(parts)
