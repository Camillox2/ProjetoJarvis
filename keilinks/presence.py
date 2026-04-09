"""
Monitoramento de presença via câmera — CPU-only.
Usa Haar Cascade (OpenCV built-in) para detecção de face.
Sem VLM: zero gasto de VRAM no loop de presença.
"""

import cv2
import time
import threading
import random
from dataclasses import dataclass
from typing import Callable

from keilinks.log import get_logger

log = get_logger("presence")


# ─── Detector de face (CPU, built-in do OpenCV) ───────────────────────────────
_FACE_CASCADE = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)

# Frases de abertura por hora do dia — sem VLM, sem VRAM
_OPENERS_DAY = [
    "Ei, tô por aqui se quiser conversar.",
    "Oi. Tô vendo que você tá de boa. Alguma coisa?",
    "Tô aqui se precisar de alguma coisa.",
    "Alguma coisa que você queira falar?",
    "Ei, parece que você tá livre. Quer bater um papo?",
]
_OPENERS_NIGHT = [
    "Ei, ainda acordado? Tô por aqui.",
    "Tá tarde. Tô aqui se quiser conversar.",
    "Oi. Posso te ajudar com alguma coisa?",
]


def _pick_opener() -> str:
    hour = time.localtime().tm_hour
    pool = _OPENERS_NIGHT if hour >= 22 or hour < 6 else _OPENERS_DAY
    return random.choice(pool)


# ─── Configuração ─────────────────────────────────────────────────────────────
@dataclass
class PresenceConfig:
    check_interval_secs: float = 25.0   # checa a cada N segundos
    min_gap_secs:        float = 300.0  # mínimo entre engajamentos (5 min)
    engage_when_focused: bool  = False  # reservado — mantido por compatibilidade
    sensitivity:         str   = "normal"  # "low" | "normal" | "high"


class PresenceMonitor:
    def __init__(self, on_engage: Callable[[str], None], eyes=None):
        """
        on_engage(abertura): chamado quando a Keilinks decide iniciar conversa.
        eyes: instância de Eyes — compartilha a câmera.
        """
        self._on_engage          = on_engage
        self._eyes               = eyes
        self._config             = PresenceConfig()
        self._running            = False
        self._paused             = False
        self._thread: threading.Thread | None = None
        self._last_engage        = 0.0
        self._consecutive_present = 0   # checks seguidos com face detectada
        self._consecutive_absent  = 0   # checks seguidos sem face

    # ─── API pública ──────────────────────────────────────────────────────────
    def start(self, config: PresenceConfig | None = None):
        if self._running:
            return
        if config:
            self._config = config
        if not self._eyes or not self._eyes.is_available():
            log.warning("Câmera não disponível — monitoramento desativado.")
            return
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("Monitorando você a cada %.0fs.", self._config.check_interval_secs)

    def stop(self):
        self._running = False

    def pause(self):
        """Pausa durante conversa ativa."""
        self._paused = True

    def resume(self):
        self._paused = False

    def is_running(self) -> bool:
        return self._running

    # ─── Detecção de face (CPU, Haar Cascade) ────────────────────────────────
    def _detect_face(self) -> bool:
        """Retorna True se detectou pelo menos uma face. CPU-only, zero VRAM."""
        frame = self._eyes.capture_frame()
        if frame is None:
            return False
        gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = _FACE_CASCADE.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60)
        )
        return len(faces) > 0

    # ─── Decisão de engajamento ───────────────────────────────────────────────
    def _should_engage(self) -> bool:
        elapsed = time.time() - self._last_engage
        if elapsed < self._config.min_gap_secs:
            return False
        # "low": só engaja após 3 checks presentes; "normal": 2; "high": 1
        min_checks = {"low": 3, "normal": 2, "high": 1}.get(self._config.sensitivity, 2)
        return self._consecutive_present >= min_checks

    # ─── Loop principal ───────────────────────────────────────────────────────
    def _loop(self):
        time.sleep(30.0)  # delay inicial para não engajar logo ao abrir

        while self._running:
            time.sleep(self._config.check_interval_secs)

            if self._paused or not self._running:
                continue

            present = self._detect_face()
            log.debug("Presença: face=%s consecutive_present=%d", present, self._consecutive_present)

            if present:
                self._consecutive_present += 1
                self._consecutive_absent   = 0
            else:
                self._consecutive_absent  += 1
                self._consecutive_present  = 0

            if present and self._should_engage():
                self._last_engage         = time.time()
                self._consecutive_present = 0
                self._on_engage(_pick_opener())
