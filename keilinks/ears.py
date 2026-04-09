"""
STT com faster-whisper + callback de volume para o animator.
Um único InputStream, sem conflito de dispositivo.
Suporta gravação com timeout configurável para conversa contínua.
"""

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from typing import Callable
from config import (
    WHISPER_MODEL, WHISPER_LANGUAGE,
    SAMPLE_RATE, SILENCE_THRESHOLD, SILENCE_DURATION, MAX_RECORD_SECS,
)
from keilinks.log import get_logger

log = get_logger("ears")


class Ears:
    def __init__(self):
        log.info("Carregando modelo de fala (%s)...", WHISPER_MODEL)
        self.last_audio: np.ndarray | None = None  # último áudio capturado (float32)
        self.model = None
        self._load_model()

    def _load_model(self):
        if self.model is not None:
            return
        # STT roda em CPU — mantém VRAM livre para o LLM (Ollama).
        # int8 em CPU é rápido o suficiente para PT-BR com o modelo small.
        self.model = WhisperModel(
            WHISPER_MODEL, device="cpu", compute_type="int8",
        )
        log.info("Pronta pra ouvir.")

    def unload(self):
        """Libera VRAM do modelo STT (chamar antes de LLM pesado)."""
        if self.model is not None:
            del self.model
            self.model = None
            try:
                import torch
                torch.cuda.empty_cache()
            except Exception:
                pass
            log.debug("Whisper STT descarregado da VRAM.")

    def reload(self):
        """Recarrega o modelo STT na VRAM."""
        if self.model is None:
            self._load_model()

    def listen(
        self,
        on_volume: Callable[[float], None] | None = None,
        timeout: float | None = None,
    ) -> str:
        """
        Grava até detectar silêncio e transcreve.
        on_volume(0.0–1.0): callback para o animator.
        timeout: se definido, retorna "" se nenhum som for detectado nesse tempo.
                 Usado para conversa contínua (espera o usuário falar algo).
        """
        log.debug("Ouvindo... (timeout=%s)", timeout)
        audio_chunks: list[np.ndarray] = []
        silent_time    = 0.0
        chunk_duration = 0.1
        chunk_samples  = int(SAMPLE_RATE * chunk_duration)
        total_recorded = 0.0
        has_speech     = False   # algum som acima do threshold foi detectado?
        max_secs       = timeout if timeout else MAX_RECORD_SECS

        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16") as stream:
                while total_recorded < max_secs:
                    chunk, _ = stream.read(chunk_samples)
                    audio_chunks.append(chunk.copy())
                    total_recorded += chunk_duration

                    amplitude = np.abs(chunk).mean()

                    if on_volume:
                        on_volume(min(1.0, float(amplitude) / 32768.0 * 8))

                    if amplitude < SILENCE_THRESHOLD:
                        silent_time += chunk_duration
                        # Se já teve fala e silenciou, para
                        if has_speech and silent_time >= SILENCE_DURATION and total_recorded > 1.0:
                            break
                        # Se está em timeout de conversa contínua e nunca falou, timeout
                        if timeout and not has_speech and silent_time >= timeout:
                            log.debug("Timeout de escuta sem fala detectada.")
                            return ""
                    else:
                        silent_time = 0.0
                        has_speech = True
        except Exception as e:
            log.error("Erro no stream de áudio: %s", e)
            return ""

        if not audio_chunks or not has_speech:
            return ""

        audio_np = np.concatenate(audio_chunks, axis=0).flatten().astype(np.float32) / 32768.0
        self.last_audio = audio_np  # disponível para análise de humor

        import time as _time
        t0_stt = _time.monotonic()
        try:
            segments, _ = self.model.transcribe(
                audio_np,
                language=WHISPER_LANGUAGE,
                beam_size=3,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500},
            )
            text = " ".join(seg.text for seg in segments).strip()
        except Exception as e:
            log.error("Erro na transcrição: %s", e)
            return ""

        stt_time = _time.monotonic() - t0_stt
        if text:
            log.info("[Você] %s (STT: %.1fs, áudio: %.1fs)", text, stt_time, total_recorded)
        return text
