"""
TTS com prioridade:
  1. Piper (offline, se instalado)
  2. Windows SAPI Francisca Natural (offline, se instalado o pacote PT-BR)
  3. edge-tts FranciscaNeural (online — fallback sempre disponível)

Interrupção: para de falar quando o usuário começa a falar.
"""

import asyncio
import os
import subprocess
import tempfile
import threading
import numpy as np
import sounddevice as sd
import pygame
import edge_tts
from pathlib import Path
from config import TTS_VOICE, TTS_RATE, TTS_PITCH, SAMPLE_RATE
from keilinks.log import get_logger

log = get_logger("voice")

# ─── Piper offline ────────────────────────────────────────────────────────────
PIPER_EXE   = Path("piper/piper.exe")
PIPER_MODEL = Path("piper/pt_BR-faber-medium.onnx")   # só tem masculino no Piper PT-BR
PIPER_OK    = PIPER_EXE.exists() and PIPER_MODEL.exists()

# ─── Windows SAPI (Francisca Natural offline) ─────────────────────────────────
# Requer: Configurações → Hora e idioma → Fala → vozes (instalar PT-BR + voz neural)
SAPI_VOICE_NAME = "Microsoft Francisca"   # nome exato na lista de vozes do Windows

# Threshold para detectar interrupção
INTERRUPT_THRESHOLD = 0.04
INTERRUPT_HOLD_SECS = 0.4

_BACKEND: str | None = None   # "piper" | "sapi" | "edge" — detectado no __init__


def _detect_backend() -> str:
    if PIPER_OK:
        return "piper"
    # Verifica se Francisca Natural está instalada no Windows
    try:
        import pyttsx3
        engine = pyttsx3.init()
        voices = engine.getProperty("voices")
        engine.stop()
        for v in voices:
            if SAPI_VOICE_NAME.lower() in v.name.lower():
                return "sapi"
    except Exception:
        pass
    return "edge"


class Voice:
    def __init__(self):
        global _BACKEND
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)

        _BACKEND = _detect_backend()
        self._backend = _BACKEND

        self._stop_monitor = False
        self._interrupted  = False
        self._sapi_voice_id: str | None = None
        self._mood: str = "neutro"      # humor atual para TTS emocional
        self._silent_mode: bool = False  # modo silencioso (sem TTS)

        if self._backend == "piper":
            log.info("TTS: Piper offline (PT-BR)")
        elif self._backend == "sapi":
            self._sapi_voice_id = self._get_sapi_voice_id()
            log.info("TTS: Windows SAPI — %s (offline)", SAPI_VOICE_NAME)
        else:
            log.info("TTS: edge-tts online — %s", TTS_VOICE)

    def set_mood(self, mood: str):
        """Adapta o TTS ao humor detectado."""
        self._mood = mood

    @property
    def silent_mode(self) -> bool:
        return self._silent_mode

    @silent_mode.setter
    def silent_mode(self, value: bool):
        self._silent_mode = value
        log.info("Modo silencioso: %s", "ON" if value else "OFF")

    def _get_emotion_params(self) -> tuple[str, str]:
        """Retorna (rate, pitch) ajustados ao humor. Só para edge-tts."""
        mood_map = {
            "animado":   ("+15%", "+5Hz"),
            "feliz":     ("+10%", "+3Hz"),
            "cansado":   ("-15%", "-3Hz"),
            "calmo":     ("-5%",  "-1Hz"),
            "frustrado": ("+5%",  "+2Hz"),
            "ansioso":   ("+10%", "+4Hz"),
            "neutro":    (TTS_RATE, TTS_PITCH),
        }
        return mood_map.get(self._mood, (TTS_RATE, TTS_PITCH))

    # ─── API pública ──────────────────────────────────────────────────────────
    def speak(self, text: str, interruptible: bool = True) -> bool:
        """Fala o texto. Retorna True se completou, False se foi interrompido."""
        if not text.strip():
            return True

        # Modo silencioso: só loga, não fala
        if self._silent_mode:
            log.info("[silencioso] %s", text)
            return True

        # Remove markdown que soa estranho na fala
        clean = self._clean_for_speech(text)

        # Após limpeza o texto pode ficar vazio — não envia pro TTS
        if not clean or len(clean) < 2:
            return True

        log.info("%s", text)

        suffix = ".wav" if self._backend in ("piper", "sapi") else ".mp3"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            tmp_path = f.name

        try:
            import time as _time
            t0_synth = _time.monotonic()
            if self._backend == "piper":
                self._synth_piper(clean, tmp_path)
            elif self._backend == "sapi":
                self._synth_sapi(clean, tmp_path)
            else:
                asyncio.run(self._synth_edge(clean, tmp_path))
            log.debug("[TIMING] TTS synth: %.2fs (%d chars)", _time.monotonic() - t0_synth, len(clean))

            self._interrupted  = False
            self._stop_monitor = False

            if interruptible:
                t = threading.Thread(target=self._interrupt_monitor, daemon=True)
                t.start()

            return self._play(tmp_path)
        except Exception as e:
            log.error("TTS erro: %s (texto='%s')", e, clean[:50])
            return True
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def speak_stream(self, sentence_gen, interruptible: bool = True) -> bool:
        """
        Recebe um gerador de sentenças (do brain.think_stream) e fala cada uma
        conforme chega — começa a falar antes de terminar de gerar.
        Retorna False se foi interrompida pelo usuário.
        """
        for sentence in sentence_gen:
            if not sentence.strip():
                continue
            completed = self.speak(sentence, interruptible=interruptible)
            if not completed:
                return False   # interrompida
        return True

    def stop(self):
        pygame.mixer.music.stop()

    # ─── Síntese ──────────────────────────────────────────────────────────────
    def _synth_piper(self, text: str, out: str):
        result = subprocess.run(
            [str(PIPER_EXE), "--model", str(PIPER_MODEL), "--output_file", out],
            input=text.encode("utf-8"),
            capture_output=True, timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode())

    def _get_sapi_voice_id(self) -> str | None:
        try:
            import pyttsx3
            engine = pyttsx3.init()
            voices = engine.getProperty("voices")
            engine.stop()
            for v in voices:
                if SAPI_VOICE_NAME.lower() in v.name.lower():
                    return v.id
        except Exception:
            pass
        return None

    def _synth_sapi(self, text: str, out: str):
        import pyttsx3
        engine = pyttsx3.init()
        if self._sapi_voice_id:
            engine.setProperty("voice", self._sapi_voice_id)
        # Adapta velocidade ao humor
        rate_map = {"animado": 195, "cansado": 155, "calmo": 160, "ansioso": 190}
        engine.setProperty("rate", rate_map.get(self._mood, 175))
        engine.setProperty("volume", 1.0)
        engine.save_to_file(text, out)
        engine.runAndWait()
        engine.stop()

    async def _synth_edge(self, text: str, out: str):
        rate, pitch = self._get_emotion_params()
        communicate = edge_tts.Communicate(text, TTS_VOICE, rate=rate, pitch=pitch)
        await communicate.save(out)

    # ─── Reprodução ───────────────────────────────────────────────────────────
    def _play(self, path: str) -> bool:
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            if self._interrupted:
                pygame.mixer.music.stop()
                log.info("Interrompida.")
                return False
            pygame.time.wait(50)
        return True

    # ─── Monitor de interrupção ───────────────────────────────────────────────
    def _interrupt_monitor(self):
        chunk_size  = int(SAMPLE_RATE * 0.05)
        hold_chunks = int(INTERRUPT_HOLD_SECS / 0.05)
        loud_count  = 0
        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16") as stream:
                while not self._stop_monitor and not self._interrupted:
                    chunk, _ = stream.read(chunk_size)
                    amp = np.abs(chunk.flatten().astype(np.float32)).mean() / 32768.0
                    if amp > INTERRUPT_THRESHOLD:
                        loud_count += 1
                        if loud_count >= hold_chunks:
                            self._interrupted = True
                    else:
                        loud_count = max(0, loud_count - 1)
        except Exception:
            pass

    # ─── Limpeza de texto para fala ───────────────────────────────────────────
    @staticmethod
    def _clean_for_speech(text: str) -> str:
        import re
        text = re.sub(r'\*{1,2}(.+?)\*{1,2}', r'\1', text)   # remove **negrito**
        text = re.sub(r'`{1,3}[^`]*`{1,3}', '', text)         # remove `código`
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)  # links → texto
        text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE) # remove # headers
        text = re.sub(r'─+', '', text)                         # remove separadores
        text = re.sub(r'\n{2,}', '. ', text)                   # dupla quebra → pausa
        text = re.sub(r'\s+', ' ', text).strip()
        return text
