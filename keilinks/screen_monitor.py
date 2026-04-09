"""
Monitoramento contínuo de tela.
A Keilinks fica de olho e fala proativamente quando detecta mudanças relevantes.

Modos:
  - watch_for_changes : detecta mudanças visuais grandes (pop-up, erro, notificação)
  - watch_content     : analisa o conteúdo a cada N segundos e comenta
  - watch_keyword     : avisa quando uma palavra aparece na tela (via OCR)
"""

import threading
import time
import numpy as np
import cv2
import base64
from dataclasses import dataclass
from typing import Callable
from keilinks.log import get_logger

log = get_logger("monitor")


@dataclass
class MonitorConfig:
    interval_secs: float = 5.0       # intervalo entre capturas
    change_threshold: float = 0.08   # % de pixels diferentes pra considerar mudança
    analyze_on_change: bool = True   # manda pra LLM quando detecta mudança
    keywords: list[str] = None       # palavras pra detectar via OCR (requer pytesseract)


class ScreenMonitor:
    def __init__(self, on_alert: Callable[[str, str | None], None]):
        """
        on_alert(mensagem, image_b64_opcional):
            callback chamado quando ela detecta algo — a main loop usa pra falar
        """
        self._on_alert   = on_alert
        self._running    = False
        self._thread: threading.Thread | None = None
        self._config     = MonitorConfig()
        self._prev_frame: np.ndarray | None = None
        self._lock       = threading.Lock()
        self._paused     = False

    # ─── API pública ──────────────────────────────────────────────────────────
    def start_watching(self, config: MonitorConfig | None = None):
        if self._running:
            return
        if config:
            self._config = config
        self._running = True
        self._paused  = False
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("Monitorando tela a cada %.1fs.", self._config.interval_secs)

    def stop_watching(self):
        self._running = False
        self._prev_frame = None
        log.info("Monitoramento de tela encerrado.")

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def is_watching(self) -> bool:
        return self._running

    # ─── Captura e comparação ─────────────────────────────────────────────────
    def _capture(self) -> np.ndarray | None:
        try:
            import mss
            with mss.mss() as sct:
                mon = sct.monitors[1]
                img = sct.grab(mon)
                frame = np.array(img)[:, :, :3]
                # Reduz pra comparação ser rápida
                return cv2.resize(frame, (640, 360))
        except Exception:
            return None

    def _frame_to_b64(self, frame: np.ndarray) -> str:
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return base64.b64encode(buf).decode("utf-8")

    def _change_ratio(self, a: np.ndarray, b: np.ndarray) -> float:
        """Retorna fração de pixels com diferença significativa entre os frames."""
        diff = cv2.absdiff(a, b)
        gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY)
        return float(mask.sum()) / (mask.shape[0] * mask.shape[1] * 255)

    def _ocr_check(self, frame: np.ndarray) -> list[str]:
        """Retorna keywords encontradas na tela via OCR."""
        if not self._config.keywords:
            return []
        try:
            import pytesseract
            text = pytesseract.image_to_string(frame, lang="por+eng").lower()
            return [kw for kw in self._config.keywords if kw.lower() in text]
        except Exception:
            return []

    # ─── Loop principal ───────────────────────────────────────────────────────
    def _loop(self):
        while self._running:
            time.sleep(self._config.interval_secs)

            if self._paused or not self._running:
                continue

            frame = self._capture()
            if frame is None:
                continue

            with self._lock:
                prev = self._prev_frame
                self._prev_frame = frame.copy()

            # ── Detecção de mudança visual ─────────────────────────────────────
            if prev is not None:
                ratio = self._change_ratio(prev, frame)

                if ratio > self._config.change_threshold:
                    log.info("Mudança detectada (%.1f%%)", ratio * 100)

                    if self._config.analyze_on_change:
                        b64 = self._frame_to_b64(frame)
                        self._on_alert(
                            "Detectei uma mudança na tela. Descreva brevemente o que aconteceu "
                            "e se é algo importante que o usuário deveria saber. "
                            "Se for trivial (cursor movendo, vídeo tocando), responda apenas: IGNORAR",
                            b64,
                        )

            # ── Detecção de keywords via OCR ──────────────────────────────────
            found = self._ocr_check(frame)
            if found:
                self._on_alert(
                    f"Detectei na tela as palavras: {', '.join(found)}. "
                    "Avisa o usuário de forma curta.",
                    None,
                )
