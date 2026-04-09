"""
Perfil de voz do usuário — calibra o MoodDetector com amostras reais.
Coleta os primeiros N áudios para estabelecer baseline personalizado.
"""

import json
import numpy as np
from pathlib import Path
from keilinks.log import get_logger

log = get_logger("vprofile")

PROFILE_FILE = Path("memoria/voice_profile.json")
CALIBRATION_SAMPLES = 10  # amostras necessárias para calibrar


class VoiceProfile:
    def __init__(self, sample_rate: int = 16000):
        self._sr = sample_rate
        self._calibrated = False
        self._samples_collected = 0
        self._energy_samples: list[float] = []
        self._pitch_samples: list[float]  = []
        self._speed_samples: list[float]  = []
        self._profile: dict = self._load()
        if self._profile.get("calibrated"):
            self._calibrated = True
            log.info("Perfil de voz carregado (baseline personalizado).")

    def _load(self) -> dict:
        if PROFILE_FILE.exists():
            try:
                return json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save(self):
        PROFILE_FILE.parent.mkdir(exist_ok=True)
        PROFILE_FILE.write_text(
            json.dumps(self._profile, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    @property
    def calibrated(self) -> bool:
        return self._calibrated

    @property
    def samples_needed(self) -> int:
        return max(0, CALIBRATION_SAMPLES - self._samples_collected)

    def add_sample(self, energy: float, pitch: float, speed: float):
        """Adiciona uma amostra de áudio para calibração."""
        if self._calibrated:
            return

        if energy > 0.001:  # ignora silêncio
            self._energy_samples.append(energy)
        if pitch > 50:  # ignora pitch inválido
            self._pitch_samples.append(pitch)
        if 0.1 < speed < 5.0:  # ignora velocidades absurdas
            self._speed_samples.append(speed)
        self._samples_collected += 1

        if self._samples_collected >= CALIBRATION_SAMPLES:
            self._calibrate()

    def _calibrate(self):
        """Calcula baseline personalizado a partir das amostras."""
        self._profile = {
            "calibrated": True,
            "samples":    self._samples_collected,
            "energy_mean": float(np.mean(self._energy_samples)) if self._energy_samples else 0.04,
            "energy_std":  float(np.std(self._energy_samples)) if self._energy_samples else 0.02,
            "pitch_mean":  float(np.mean(self._pitch_samples)) if self._pitch_samples else 150.0,
            "pitch_std":   float(np.std(self._pitch_samples)) if self._pitch_samples else 30.0,
            "speed_mean":  float(np.mean(self._speed_samples)) if self._speed_samples else 1.0,
            "speed_std":   float(np.std(self._speed_samples)) if self._speed_samples else 0.2,
        }
        self._save()
        self._calibrated = True
        log.info("Perfil de voz calibrado! (%d amostras). "
                 "Energy=%.4f±%.4f, Pitch=%.0f±%.0f, Speed=%.2f±%.2f",
                 self._samples_collected,
                 self._profile["energy_mean"], self._profile["energy_std"],
                 self._profile["pitch_mean"], self._profile["pitch_std"],
                 self._profile["speed_mean"], self._profile["speed_std"])

    def get_thresholds(self) -> dict | None:
        """Retorna thresholds personalizados para o MoodDetector."""
        if not self._calibrated:
            return None
        p = self._profile
        return {
            "energy_low":  p["energy_mean"] - p["energy_std"],
            "energy_high": p["energy_mean"] + p["energy_std"],
            "pitch_low":   p["pitch_mean"] - p["pitch_std"],
            "pitch_high":  p["pitch_mean"] + p["pitch_std"],
            "speed_normal": p["speed_mean"],
        }

    def recalibrate(self) -> str:
        """Reseta a calibração para recalibrar."""
        self._calibrated = False
        self._samples_collected = 0
        self._energy_samples = []
        self._pitch_samples  = []
        self._speed_samples  = []
        self._profile = {}
        if PROFILE_FILE.exists():
            PROFILE_FILE.unlink()
        return (f"Calibração resetada. Vou recalibrar com as próximas "
                f"{CALIBRATION_SAMPLES} falas suas.")
