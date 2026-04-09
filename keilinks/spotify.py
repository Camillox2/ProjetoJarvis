"""
Controle de mídia via teclas de mídia do Windows.
Funciona com Spotify, YouTube, qualquer player ativo — sem API key.
"""

import ctypes
from ctypes import wintypes

# Virtual key codes de mídia do Windows
VK_MEDIA_PLAY_PAUSE  = 0xB3
VK_MEDIA_NEXT_TRACK  = 0xB0
VK_MEDIA_PREV_TRACK  = 0xB1
VK_VOLUME_MUTE       = 0xAD
VK_VOLUME_UP         = 0xAF
VK_VOLUME_DOWN       = 0xAE

KEYEVENTF_KEYUP = 0x0002

user32 = ctypes.windll.user32


def _press_media_key(vk: int):
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


MEDIA_TRIGGERS = {
    "play":    ["play", "toca", "continua", "resume", "reproduz"],
    "pause":   ["pause", "pausa", "para a música", "para a musica"],
    "toggle":  ["play pause", "play/pause", "parar", "pausar"],
    "next":    ["próxima", "proxima", "next", "pula", "avança", "avanca"],
    "prev":    ["anterior", "volta", "previous", "prev", "música anterior", "musica anterior"],
    "mute_media": ["muta o spotify", "muta o player", "silencia o spotify"],
}


class SpotifyControl:

    def play_pause(self) -> str:
        _press_media_key(VK_MEDIA_PLAY_PAUSE)
        return "Play/pause."

    def next_track(self) -> str:
        _press_media_key(VK_MEDIA_NEXT_TRACK)
        return "Próxima faixa."

    def prev_track(self) -> str:
        _press_media_key(VK_MEDIA_PREV_TRACK)
        return "Faixa anterior."

    def try_handle(self, text: str) -> str | None:
        t = text.lower()

        # Ordem importa: verifica "play pause" antes de "play" isolado
        if any(p in t for p in MEDIA_TRIGGERS["toggle"]):
            return self.play_pause()
        if any(p in t for p in MEDIA_TRIGGERS["next"]):
            return self.next_track()
        if any(p in t for p in MEDIA_TRIGGERS["prev"]):
            return self.prev_track()
        if any(p in t for p in MEDIA_TRIGGERS["pause"]):
            return self.play_pause()
        if any(p in t for p in MEDIA_TRIGGERS["play"]):
            return self.play_pause()

        return None
