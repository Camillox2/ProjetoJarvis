"""
Controle do Spotify via Web API (spotipy).
Substitui teclas de mídia por controle real: busca, toca playlist,
mostra o que tá tocando, controla volume do Spotify, etc.

Fallback: se o Spotify não estiver autenticado, usa teclas de mídia.

Setup:
  1. Cria app em https://developer.spotify.com/dashboard
  2. Seta SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET, SPOTIPY_REDIRECT_URI no .env
  3. Primeira execução abre browser pra autorizar
"""

import os
import ctypes
from typing import Optional
from keilinks.log import get_logger

log = get_logger("spotify")

# ─── Teclas de mídia (fallback) ───────────────────────────────────────────────
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
KEYEVENTF_KEYUP     = 0x0002
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
    "now":     ["o que tá tocando", "que música é essa", "qual música", "que tá tocando",
                "que musica é essa", "o que está tocando"],
    "search":  ["toca a música", "toca a musica", "coloca a música", "coloca a musica",
                "bota pra tocar", "toca no spotify"],
    "playlist": ["coloca uma playlist", "coloca playlist", "toca playlist",
                 "coloca uma playlist de", "playlist de"],
    "vol_up":  ["aumenta o spotify", "volume do spotify pra cima"],
    "vol_down": ["diminui o spotify", "volume do spotify pra baixo", "abaixa o spotify"],
    "shuffle": ["aleatório", "aleatorio", "shuffle"],
    "repeat":  ["repete essa", "repetir", "repeat"],
}


class SpotifyControl:
    def __init__(self):
        self._sp = None       # spotipy.Spotify instance
        self._api_ok = False  # True se autenticação funcionou
        self._init_api()

    def _init_api(self):
        """Tenta inicializar a Spotify Web API."""
        try:
            import spotipy
            from spotipy.oauth2 import SpotifyOAuth

            client_id     = os.environ.get("SPOTIPY_CLIENT_ID", "")
            client_secret = os.environ.get("SPOTIPY_CLIENT_SECRET", "")
            redirect_uri  = os.environ.get("SPOTIPY_REDIRECT_URI", "http://localhost:8888/callback")

            if not client_id or not client_secret:
                log.info("Spotify Web API: sem credenciais. Usando teclas de mídia.")
                return

            scope = (
                "user-read-playback-state "
                "user-modify-playback-state "
                "user-read-currently-playing "
                "playlist-read-private "
                "playlist-read-collaborative"
            )

            auth_manager = SpotifyOAuth(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                scope=scope,
                cache_path="memoria/.spotify_cache",
                open_browser=True,
            )

            self._sp = spotipy.Spotify(auth_manager=auth_manager)
            # Testa
            self._sp.current_user()
            self._api_ok = True
            log.info("Spotify Web API conectada.")

        except ImportError:
            log.info("spotipy não instalado. Usando teclas de mídia.")
        except Exception as e:
            log.warning("Spotify Web API falhou: %s. Usando teclas de mídia.", e)

    # ─── API methods ──────────────────────────────────────────────────────────
    def _get_active_device(self) -> Optional[str]:
        if not self._api_ok:
            return None
        try:
            devices = self._sp.devices()
            for d in devices.get("devices", []):
                if d.get("is_active"):
                    return d["id"]
            # Se nenhum ativo, pega o primeiro
            devs = devices.get("devices", [])
            return devs[0]["id"] if devs else None
        except Exception:
            return None

    def play_pause(self) -> str:
        if self._api_ok:
            try:
                pb = self._sp.current_playback()
                if pb and pb.get("is_playing"):
                    self._sp.pause_playback()
                    return "Pausei o Spotify."
                else:
                    self._sp.start_playback()
                    return "Dando play."
            except Exception:
                pass
        _press_media_key(VK_MEDIA_PLAY_PAUSE)
        return "Play/pause."

    def next_track(self) -> str:
        if self._api_ok:
            try:
                self._sp.next_track()
                return "Próxima faixa."
            except Exception:
                pass
        _press_media_key(VK_MEDIA_NEXT_TRACK)
        return "Próxima faixa."

    def prev_track(self) -> str:
        if self._api_ok:
            try:
                self._sp.previous_track()
                return "Faixa anterior."
            except Exception:
                pass
        _press_media_key(VK_MEDIA_PREV_TRACK)
        return "Faixa anterior."

    def now_playing(self) -> str:
        if not self._api_ok:
            return "Spotify API não conectada. Não consigo ver o que tá tocando."
        try:
            current = self._sp.current_playback()
            if not current or not current.get("item"):
                return "Nada tocando no momento."
            track  = current["item"]
            name   = track.get("name", "?")
            artist = ", ".join(a["name"] for a in track.get("artists", []))
            album  = track.get("album", {}).get("name", "")
            return f"Tocando: {name} de {artist}" + (f" — álbum {album}" if album else "")
        except Exception as e:
            return f"Erro ao consultar Spotify: {e}"

    def search_and_play(self, query: str) -> str:
        if not self._api_ok:
            return "Spotify API não conectada. Configure as credenciais."
        try:
            results = self._sp.search(q=query, type="track", limit=1, market="BR")
            tracks  = results.get("tracks", {}).get("items", [])
            if not tracks:
                return f"Não encontrei '{query}' no Spotify."
            track  = tracks[0]
            name   = track["name"]
            artist = track["artists"][0]["name"]
            uri    = track["uri"]
            device = self._get_active_device()
            self._sp.start_playback(device_id=device, uris=[uri])
            return f"Tocando: {name} de {artist}."
        except Exception as e:
            return f"Erro ao buscar no Spotify: {e}"

    def play_playlist(self, query: str) -> str:
        if not self._api_ok:
            return "Spotify API não conectada."
        try:
            results = self._sp.search(q=query, type="playlist", limit=1, market="BR")
            playlists = results.get("playlists", {}).get("items", [])
            if not playlists:
                return f"Nenhuma playlist '{query}' encontrada."
            pl     = playlists[0]
            name   = pl["name"]
            uri    = pl["uri"]
            device = self._get_active_device()
            self._sp.start_playback(device_id=device, context_uri=uri)
            self._sp.shuffle(True, device_id=device)
            return f"Tocando playlist: {name}."
        except Exception as e:
            return f"Erro ao tocar playlist: {e}"

    def set_volume(self, pct: int) -> str:
        if not self._api_ok:
            return "Spotify API não conectada."
        try:
            pct = max(0, min(100, pct))
            self._sp.volume(pct)
            return f"Volume do Spotify em {pct}%."
        except Exception as e:
            return f"Erro: {e}"

    def toggle_shuffle(self) -> str:
        if not self._api_ok:
            return "API não conectada."
        try:
            pb = self._sp.current_playback()
            state = not pb.get("shuffle_state", False)
            self._sp.shuffle(state)
            return "Aleatório ligado." if state else "Aleatório desligado."
        except Exception as e:
            return f"Erro: {e}"

    def toggle_repeat(self) -> str:
        if not self._api_ok:
            return "API não conectada."
        try:
            pb = self._sp.current_playback()
            mode = pb.get("repeat_state", "off")
            new_mode = "track" if mode == "off" else "off"
            self._sp.repeat(new_mode)
            return "Repetindo essa faixa." if new_mode == "track" else "Repetição desligada."
        except Exception as e:
            return f"Erro: {e}"

    # ─── Handler para main ────────────────────────────────────────────────────
    def try_handle(self, text: str) -> str | None:
        t = text.lower()

        # Ordem importa
        if any(p in t for p in MEDIA_TRIGGERS["now"]):
            return self.now_playing()

        if any(p in t for p in MEDIA_TRIGGERS["shuffle"]):
            return self.toggle_shuffle()

        if any(p in t for p in MEDIA_TRIGGERS["repeat"]):
            return self.toggle_repeat()

        if any(p in t for p in MEDIA_TRIGGERS["vol_up"]):
            return self.set_volume(80)  # TODO: extrair valor do texto

        if any(p in t for p in MEDIA_TRIGGERS["vol_down"]):
            return self.set_volume(30)

        if any(p in t for p in MEDIA_TRIGGERS["playlist"]):
            # Extrai nome da playlist depois do trigger
            for tr in MEDIA_TRIGGERS["playlist"]:
                if tr in t:
                    query = t[t.index(tr) + len(tr):].strip()
                    if query:
                        return self.play_playlist(query)
            return self.play_playlist("Top Brasil")

        if any(p in t for p in MEDIA_TRIGGERS["search"]):
            # Extrai nome da música depois do trigger
            for tr in MEDIA_TRIGGERS["search"]:
                if tr in t:
                    query = t[t.index(tr) + len(tr):].strip()
                    if query:
                        return self.search_and_play(query)
            return "Que música você quer ouvir?"

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
