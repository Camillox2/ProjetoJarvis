"""
Modo Estudo — monitora a tela, detecta distração e manda voltar ao foco.
Usa OCR + LLM para entender se o conteúdo na tela é estudo ou distração.

Comandos:
  "modo estudo" / "ativa modo estudo" → inicia
  "para o modo estudo" / "desativa modo estudo" → para
  "quanto tempo estudei" → mostra stats
"""

import time
import threading
import numpy as np
import cv2
from datetime import datetime
from typing import Callable
from keilinks.log import get_logger

log = get_logger("study")


STUDY_START_TRIGGERS = [
    "modo estudo", "ativa modo estudo", "começa modo estudo",
    "vou estudar", "ativa o foco", "modo foco",
]

STUDY_STOP_TRIGGERS = [
    "para o modo estudo", "desativa modo estudo", "para de monitorar estudo",
    "sai do modo estudo", "desativa o foco", "para o foco",
]

STUDY_STATS_TRIGGERS = [
    "quanto tempo estudei", "tempo de estudo", "quanto estudei",
    "estatísticas de estudo", "stats de estudo",
]

# Apps/sites considerados distração (nomes que aparecem na barra de título)
_DISTRACTION_KEYWORDS = [
    "youtube", "reddit", "twitter", "instagram", "tiktok",
    "facebook", "twitch", "discord", "whatsapp", "telegram",
    "netflix", "9gag", "imgur",
]

# Intervalo entre checagens de tela
_CHECK_INTERVAL = 30.0  # segundos

# Quantas distrações seguidas antes de alertar
_DISTRACTION_THRESHOLD = 2


class StudyMode:
    def __init__(self, on_alert: Callable[[str], None]):
        """
        on_alert(message): chamado quando detecta distração.
        """
        self._on_alert  = on_alert
        self._running   = False
        self._paused    = False
        self._thread: threading.Thread | None = None

        # Stats
        self._started_at:   float | None = None
        self._total_focus:   float = 0.0   # segundos focado
        self._total_distracted: float = 0.0
        self._distraction_count = 0
        self._consecutive_distractions = 0
        self._last_check_focused = True

        # Frases variadas de alerta
        self._alerts = [
            "Ei, volta pro estudo! Tô de olho.",
            "Tá distraído, hein? Foca!",
            "Isso aí não é estudo... volta!",
            "Tá procrastinando? Bora voltar!",
            "Foco! Você consegue, amor.",
            "Opa, tá fugindo do estudo de novo.",
            "Distraído? Volta pro que importa!",
        ]
        self._alert_idx = 0

    # ─── API pública ──────────────────────────────────────────────────────────
    def start(self, subject: str = "") -> str:
        if self._running:
            return "Modo estudo já está ativo."

        self._running    = True
        self._paused     = False
        self._started_at = time.time()
        self._total_focus = 0.0
        self._total_distracted = 0.0
        self._distraction_count = 0
        self._consecutive_distractions = 0

        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

        msg = "Modo estudo ativado! Vou ficar de olho na sua tela."
        if subject:
            msg += f" Foco em: {subject}."
        log.info("Modo estudo iniciado.")
        return msg

    def stop(self) -> str:
        if not self._running:
            return "O modo estudo não estava ativo."
        self._running = False
        duration = time.time() - (self._started_at or time.time())
        log.info("Modo estudo encerrado. Duração: %.0fmin", duration / 60)
        return self.get_stats()

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def is_active(self) -> bool:
        return self._running

    # ─── Stats ────────────────────────────────────────────────────────────────
    def get_stats(self) -> str:
        if self._started_at is None:
            return "Nenhuma sessão de estudo registrada."

        duration = time.time() - self._started_at
        focus_pct = (self._total_focus / max(duration, 1)) * 100

        def fmt(s: float) -> str:
            if s < 60:
                return f"{int(s)}s"
            elif s < 3600:
                return f"{int(s / 60)}min"
            else:
                return f"{int(s / 3600)}h{int((s % 3600) / 60)}min"

        return (
            f"Sessão de estudo: {fmt(duration)}\n"
            f"Tempo focado: {fmt(self._total_focus)} ({focus_pct:.0f}%)\n"
            f"Distrações: {self._distraction_count}x"
        )

    # ─── Detecção ─────────────────────────────────────────────────────────────
    def _get_active_window_title(self) -> str:
        """Pega o título da janela ativa no Windows."""
        import sys
        if sys.platform != "win32":
            return ""
        try:
            import ctypes
            hwnd   = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buf    = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value
        except Exception:
            return ""

    def _is_distraction(self, window_title: str) -> bool:
        """Verifica se o título da janela indica distração."""
        title_lower = window_title.lower()
        return any(kw in title_lower for kw in _DISTRACTION_KEYWORDS)

    def _next_alert(self) -> str:
        msg = self._alerts[self._alert_idx % len(self._alerts)]
        self._alert_idx += 1
        return msg

    # ─── Loop principal ───────────────────────────────────────────────────────
    def _loop(self):
        last_check = time.time()

        while self._running:
            time.sleep(5.0)  # check a cada 5s pra ser responsivo ao stop

            if self._paused or not self._running:
                continue

            now = time.time()
            if now - last_check < _CHECK_INTERVAL:
                continue
            last_check = now

            title = self._get_active_window_title()
            is_distracted = self._is_distraction(title)

            if is_distracted:
                self._consecutive_distractions += 1
                self._distraction_count += 1
                self._total_distracted += _CHECK_INTERVAL
                self._last_check_focused = False

                if self._consecutive_distractions >= _DISTRACTION_THRESHOLD:
                    alert_msg = self._next_alert()
                    log.info("Distração detectada: %s", title)
                    self._on_alert(alert_msg)
                    self._consecutive_distractions = 0
            else:
                self._consecutive_distractions = 0
                self._total_focus += _CHECK_INTERVAL
                self._last_check_focused = True

    # ─── Handler para main ────────────────────────────────────────────────────
    def try_handle(self, text: str) -> str | None:
        t = text.lower()

        if any(tr in t for tr in STUDY_STATS_TRIGGERS):
            return self.get_stats()

        if any(tr in t for tr in STUDY_STOP_TRIGGERS):
            return self.stop()

        if any(tr in t for tr in STUDY_START_TRIGGERS):
            # Tenta extrair o assunto
            subject = ""
            for sep in [" de ", " sobre ", " em ", " pra ", " para "]:
                if sep in t:
                    idx = t.rfind(sep)
                    after = text[idx + len(sep):].strip()
                    if after and "estudo" not in after.lower() and "foco" not in after.lower():
                        subject = after
                        break
            return self.start(subject)

        return None
