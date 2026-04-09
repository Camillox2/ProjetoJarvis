"""
Modo Cinema — detecta players de vídeo/streaming ativos.
Silencia notificações e presença automaticamente.
Ao detectar pausa, pergunta se o usuário quer algo.
"""

import time
import threading
import sys
from typing import Callable
from keilinks.log import get_logger

log = get_logger("cinema")

# Palavras no título da janela que indicam que o usuário tá assistindo algo
_PLAYER_KEYWORDS = [
    "netflix", "prime video", "disney+", "hbo max", "star+",
    "youtube", "twitch", "crunchyroll", "plex", "vlc",
    "mpv", "mpc-hc", "mpc-be", "potplayer", "windows media",
    "amazon prime", "globoplay", "paramount+", "apple tv",
    "jellyfin", "kodi", "stremio",
]

# Títulos que indicam pausa em players comuns
_PAUSE_INDICATORS = [
    "paused", "pausado", "❚❚", "▋▋",
]

CINEMA_START_TRIGGERS = [
    "modo cinema", "ativa modo cinema", "vou assistir",
    "vou ver um filme", "vou ver uma série", "tô assistindo",
]
CINEMA_STOP_TRIGGERS = [
    "para o modo cinema", "desativa modo cinema", "acabou o filme",
    "terminei de assistir", "sai do modo cinema",
]


class CinemaMode:
    def __init__(self, on_pause: Callable[[str], None] | None = None):
        """
        on_pause(msg): chamado quando detecta que o player pausou.
        """
        self._on_pause       = on_pause
        self._running        = False
        self._thread: threading.Thread | None = None
        self._paused_notified = False
        self._last_title      = ""
        self._cinema_auto     = False  # ativado por detecção automática
        self._check_interval  = 10.0   # segundos
        self._suppressing     = False  # se estamos suprimindo notificações

    @property
    def active(self) -> bool:
        return self._running

    @property
    def suppressing(self) -> bool:
        """Retorna True se devemos suprimir notificações/presença."""
        return self._running

    def start(self, auto: bool = False) -> str:
        if self._running:
            return "Modo cinema já está ativo."
        self._running = True
        self._cinema_auto = auto
        self._paused_notified = False
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("Modo cinema ativado%s.", " (automático)" if auto else "")
        return "Modo cinema ativado! Vou ficar quietinha até você terminar."

    def stop(self) -> str:
        if not self._running:
            return "Modo cinema não estava ativo."
        self._running = False
        log.info("Modo cinema desativado.")
        return "Modo cinema desativado. Voltei ao normal!"

    def detect_player(self) -> str | None:
        """Detecta se há um player de vídeo ativo. Retorna o título ou None."""
        title = self._get_active_window_title().lower()
        for kw in _PLAYER_KEYWORDS:
            if kw in title:
                return title
        return None

    def _get_active_window_title(self) -> str:
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

    def _is_paused(self, title: str) -> bool:
        t = title.lower()
        return any(ind in t for ind in _PAUSE_INDICATORS)

    def _loop(self):
        while self._running:
            time.sleep(self._check_interval)
            if not self._running:
                break

            title = self._get_active_window_title()
            is_player = any(kw in title.lower() for kw in _PLAYER_KEYWORDS)

            if not is_player and self._cinema_auto:
                # Player fechou — desativa automaticamente
                log.info("Player não detectado — desativando modo cinema auto.")
                self._running = False
                break

            if is_player and self._is_paused(title):
                if not self._paused_notified and self._on_pause:
                    self._paused_notified = True
                    self._on_pause("Vi que você pausou. Quer alguma coisa?")
            else:
                self._paused_notified = False

    def try_handle(self, text: str) -> str | None:
        t = text.lower()
        for trigger in CINEMA_START_TRIGGERS:
            if trigger in t:
                return self.start()
        for trigger in CINEMA_STOP_TRIGGERS:
            if trigger in t:
                return self.stop()
        return None
