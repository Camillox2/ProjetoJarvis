"""
Detecção de wake word usando faster-whisper tiny (leve, roda em paralelo).
Escuta continuamente em janelas curtas e detecta quando chamam a Keilinks.
Também pode ativar por palmas sem passar pelo modelo.
Suporta unload/reload para liberar VRAM durante conversas.
"""

import time
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from config import (
    SAMPLE_RATE,
    CLAP_ENABLED,
    CLAP_COUNT_TO_WAKE,
    CLAP_SEQUENCE_WINDOW_SECS,
    CLAP_DEBOUNCE_SECS,
    CLAP_COOLDOWN_SECS,
    CLAP_PEAK_THRESHOLD,
    CLAP_STRONG_PEAK_THRESHOLD,
    CLAP_RMS_THRESHOLD,
    CLAP_CREST_MIN,
    CLAP_ACTIVE_RATIO_MAX,
    CLAP_ONSET_THRESHOLD,
)
from keilinks.log import get_logger

log = get_logger("wakeword")

# Variações de como o usuário pode chamar a Keilinks
WAKE_WORDS = [
    "keilinks",
    "oi keilinks",
    "ei keilinks",
    "hey keilinks",
    "ey keilinks",
    "olá keilinks",
    "ola keilinks",
    "eai keilinks",
    "e aí keilinks",
    "e ai keilinks",
    "kei",          # apelido curto
    "oi kei",
    "ei kei",
    "hey kei",
    # Variações fonéticas do Whisper tiny em PT-BR
    "que links",
    "que link",
    "oi que links",
    "oi que link",
    "ei que links",
    "ei que link",
    "hey que links",
    "k-link",
    "k-linx",
    "k link",
    "oi k-link",
    "oi k-linx",
    "oi k link",
    "e links",
    "ei links",
    "kélings",
    "cilinx",
    "kelings",
    # Ativação simples
    "oi",
    "hey",
    "ei",
    # Variações fonéticas do Whisper tiny para 'oi'
    "ui",
    "uí",
    " i",
]

# Janela de áudio para detectar wake word (segundos)
WAKE_WINDOW_SECS = 2.0
WAKE_STEP_SECS   = 0.05


class WakeWordDetector:
    def __init__(self):
        self.model = None
        self.chunk_samples = int(SAMPLE_RATE * WAKE_WINDOW_SECS)
        self.step_samples  = int(SAMPLE_RATE * WAKE_STEP_SECS)
        self._last_clap_ts = 0.0
        self._last_wake_ts = 0.0
        self._clap_times: list[float] = []
        self._noise_rms = 0.004
        self._load_model()

    def _load_model(self):
        """Carrega o modelo tiny na VRAM."""
        if self.model is not None:
            return
        log.info("Carregando detector de wake word (tiny)...")
        try:
            self.model = WhisperModel(
                "tiny",
                device="cuda",
                compute_type="float16",
            )
            log.info("Wake word pronta.")
        except Exception as e:
            log.error("Falha ao carregar wake word model: %s — tentando CPU", e)
            try:
                self.model = WhisperModel("tiny", device="cpu", compute_type="int8")
                log.info("Wake word rodando na CPU (fallback).")
            except Exception as e2:
                log.error("Wake word indisponível: %s", e2)
                self.model = None

    def unload(self):
        """Libera VRAM do modelo tiny (chamar durante conversas)."""
        if self.model is not None:
            del self.model
            self.model = None
            # Libera cache CUDA
            try:
                import torch
                torch.cuda.empty_cache()
            except Exception:
                pass
            log.debug("Wake word model descarregado da VRAM.")

    def reload(self):
        """Recarrega o modelo (chamar ao voltar pro idle)."""
        self._load_model()

    def _transcribe_chunk(self, audio_np: np.ndarray) -> str:
        if self.model is None:
            return ""
        segments, _ = self.model.transcribe(
            audio_np,
            language="pt",
            beam_size=1,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300},
        )
        return " ".join(seg.text for seg in segments).strip().lower()

    def _contains_wake_word(self, text: str) -> bool:
        # Remove pontuação e normaliza antes de checar
        import re
        clean = re.sub(r"[!?.,;:\-]", "", text).strip()
        return any(w in clean for w in WAKE_WORDS)

    def _detect_clap(self, audio_np: np.ndarray) -> tuple[bool, bool]:
        """
        Retorna (clap_detectada, clap_muito_forte).
        Usa um detector simples de impulso: pico alto, energia suficiente,
        crest factor alto e duração curta.
        """
        if not CLAP_ENABLED or len(audio_np) == 0:
            return False, False

        abs_audio = np.abs(audio_np)
        peak = float(abs_audio.max())
        rms = float(np.sqrt(np.mean(audio_np ** 2)))
        crest = peak / max(rms, 1e-6)
        onset = float(np.max(np.abs(np.diff(audio_np)))) if len(audio_np) > 1 else 0.0

        # Aprende o piso de ruído quando o sinal está baixo.
        if rms < max(CLAP_RMS_THRESHOLD * 1.5, self._noise_rms * 2.5):
            self._noise_rms = 0.97 * self._noise_rms + 0.03 * rms

        dynamic_peak_threshold = max(0.10, min(CLAP_PEAK_THRESHOLD, self._noise_rms * 18.0))
        dynamic_strong_threshold = max(0.20, min(CLAP_STRONG_PEAK_THRESHOLD, self._noise_rms * 28.0))
        dynamic_rms_threshold = max(0.006, min(CLAP_RMS_THRESHOLD, self._noise_rms * 5.0))
        active_ratio = float(np.mean(abs_audio > dynamic_peak_threshold * 0.35))

        is_candidate = (
            peak >= dynamic_peak_threshold and
            rms >= dynamic_rms_threshold and
            crest >= CLAP_CREST_MIN and
            onset >= CLAP_ONSET_THRESHOLD and
            active_ratio <= CLAP_ACTIVE_RATIO_MAX
        )
        is_strong = (
            peak >= dynamic_strong_threshold and
            rms >= dynamic_rms_threshold and
            onset >= CLAP_ONSET_THRESHOLD and
            active_ratio <= CLAP_ACTIVE_RATIO_MAX
        )

        if is_candidate:
            log.info(
                "Palma candidata: peak=%.2f rms=%.3f crest=%.1f onset=%.2f active=%.3f",
                peak, rms, crest, onset, active_ratio,
            )
        return is_candidate, is_strong

    def _handle_clap(self, audio_np: np.ndarray) -> bool:
        """Atualiza o estado das palmas e retorna True se deve ativar."""
        detected, strong = self._detect_clap(audio_np)
        if not detected:
            return False

        now = time.monotonic()
        if now - self._last_wake_ts < CLAP_COOLDOWN_SECS:
            return False
        if now - self._last_clap_ts < CLAP_DEBOUNCE_SECS:
            return False

        self._last_clap_ts = now

        if strong:
            self._last_wake_ts = now
            self._clap_times.clear()
            log.info("Palma forte detectada — ativando.")
            return True

        self._clap_times = [t for t in self._clap_times if now - t <= CLAP_SEQUENCE_WINDOW_SECS]
        self._clap_times.append(now)
        log.info("Palma detectada (%d/%d).", len(self._clap_times), CLAP_COUNT_TO_WAKE)

        if len(self._clap_times) >= CLAP_COUNT_TO_WAKE:
            self._last_wake_ts = now
            self._clap_times.clear()
            log.info("Sequência de palmas detectada — ativando.")
            return True
        return False

    def wait_for_wake_word(self) -> bool:
        """
        Fica em loop ouvindo janelas curtas de áudio.
        Retorna True quando o wake word for detectado.
        """
        # Garante que o modelo está carregado
        if self.model is None:
            self._load_model()
        if self.model is None:
            log.error("Wake word indisponível — aguardando Enter manual.")
            input("[Pressione Enter para simular wake word] ")
            return True

        if CLAP_ENABLED:
            log.info("Aguardando wake word ou palmas...")
        else:
            log.info("Aguardando wake word...")

        try:
            window_chunks: list[np.ndarray] = []
            window_samples = 0
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16") as stream:
                while True:
                    chunk, _ = stream.read(self.step_samples)
                    audio_np = chunk.flatten().astype(np.float32) / 32768.0

                    if self._handle_clap(audio_np):
                        return True

                    window_chunks.append(audio_np)
                    window_samples += len(audio_np)

                    if window_samples < self.chunk_samples:
                        continue

                    audio_window = np.concatenate(window_chunks, axis=0)[-self.chunk_samples:]
                    window_chunks.clear()
                    window_samples = 0

                    if np.abs(audio_window).mean() < 0.01:
                        continue

                    text = self._transcribe_chunk(audio_window)
                    if text:
                        log.info("Ouvi: '%s'", text)
                    if self._contains_wake_word(text):
                        log.info("Wake word detectada!")
                        return True
        except Exception as e:
            log.error("Erro no stream de áudio do wake word: %s", e)
            input("[Pressione Enter para simular wake word] ")
            return True
