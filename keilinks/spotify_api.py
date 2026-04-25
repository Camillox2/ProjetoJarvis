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
    "play":    ["play", "dá play", "da play", "toca", "continua", "resume", "reproduz"],
    "pause":   ["pause", "pausa", "para a música", "para a musica"],
    "toggle":  ["play pause", "play/pause", "parar", "pausar"],
    "next":    ["próxima", "proxima", "next", "pula", "avança", "avanca",
                "passa a música", "passa a musica", "passe a música", "passe a musica",
                "próxima música", "proxima musica"],
    "prev":    ["anterior", "volta", "previous", "prev", "música anterior", "musica anterior",
                "volta a música", "volta a musica"],
    "now":     ["o que tá tocando", "que música é essa", "qual música", "que tá tocando",
                "que musica é essa", "o que está tocando", "que som é esse", "que artista",
                "nome da música", "qual é a música", "qual é essa música"],
    "like":    ["curte essa música", "curte essa musica", "salva essa música", "salva essa musica",
                "gostei dessa música", "gostei dessa musica", "adiciona nas favoritas",
                "salva nos favoritos", "like nessa música"],
    "dislike": ["não gostei dessa música", "nao gostei dessa musica",
                "remove dos favoritos", "descurte"],
    "search":  ["toca a música", "toca a musica", "coloca a música", "coloca a musica",
                "bota pra tocar", "toca no spotify", "coloca o", "toca o",
                "quero ouvir", "bota o", "coloca a", "toca a"],
    "play_generic": [
        "tem uma música", "tem uma musica", "tem alguma música", "tem alguma musica",
        "bota uma música", "bota uma musica", "bota alguma coisa", "bota algum som",
        "coloca uma música", "coloca uma musica", "coloca alguma coisa", "coloca um som",
        "toca alguma coisa", "toca alguma música", "toca alguma musica",
        "liga o spotify", "bota o spotify", "coloca o spotify",
        "uma música pra mim", "uma musica pra mim",
        "bota um som pra mim", "coloca um som pra mim",
        "quero ouvir alguma coisa", "quero uma música",
        "coloca uma musica pra mim", "bota musica", "bota música",
        "rola uma música", "rola uma musica", "rola algo",
    ],
    "playlist": ["coloca uma playlist", "coloca playlist", "toca playlist",
                 "coloca uma playlist de", "playlist de"],
    "vol_up":  ["aumenta o spotify", "volume do spotify pra cima", "aumenta o volume da música",
                "aumenta o som", "mais alto"],
    "vol_down": ["diminui o spotify", "volume do spotify pra baixo", "abaixa o spotify",
                 "diminui o volume da música", "abaixa o som", "mais baixo"],
    "shuffle": ["aleatório", "aleatorio", "shuffle", "modo aleatório", "embaralha"],
    "repeat":  ["repete essa", "repetir", "repeat", "repete a música", "loop"],
    "queue":   ["adiciona na fila", "coloca na fila", "add na fila", "bota na fila",
                "próxima faixa coloca", "na fila coloca", "adiciona à fila"],
    "lyrics":  ["letra dessa música", "letra da música", "o que diz essa música",
                "me fala a letra", "qual a letra", "mostra a letra", "diz a letra",
                "canta essa música", "como é a letra"],
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
                "user-library-modify "
                "user-library-read "
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

    def like_current(self) -> str:
        if not self._api_ok:
            return "API não conectada."
        try:
            pb = self._sp.current_playback()
            if not pb or not pb.get("item"):
                return "Nenhuma música tocando."
            track_id = pb["item"]["id"]
            name     = pb["item"]["name"]
            self._sp.current_user_saved_tracks_add([track_id])
            return f"Curti e salvei '{name}' nos favoritos."
        except Exception as e:
            return f"Erro: {e}"

    def dislike_current(self) -> str:
        if not self._api_ok:
            return "API não conectada."
        try:
            pb = self._sp.current_playback()
            if not pb or not pb.get("item"):
                return "Nenhuma música tocando."
            track_id = pb["item"]["id"]
            name     = pb["item"]["name"]
            self._sp.current_user_saved_tracks_delete([track_id])
            return f"Removi '{name}' dos favoritos."
        except Exception as e:
            return f"Erro: {e}"

    def add_to_queue(self, query: str) -> str:
        """Adiciona uma música à fila do Spotify."""
        if not self._api_ok:
            return "Spotify API não conectada."
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
            self._sp.add_to_queue(uri, device_id=device)
            return f"Adicionei '{name}' de {artist} à fila."
        except Exception as e:
            return f"Erro ao adicionar na fila: {e}"

    def get_lyrics(self) -> str:
        """Busca a letra da música atual via Lyrics.ovh (API gratuita, sem key)."""
        if not self._api_ok:
            return "Spotify API não conectada."
        try:
            import httpx
            pb = self._sp.current_playback()
            if not pb or not pb.get("item"):
                return "Nenhuma música tocando."
            track  = pb["item"]
            name   = track.get("name", "")
            artist = track["artists"][0]["name"] if track.get("artists") else ""
            if not name or not artist:
                return "Não consegui identificar a música atual."
            # API pública gratuita — sem chave
            url = f"https://api.lyrics.ovh/v1/{httpx.URL(artist).path}/{httpx.URL(name).path}"
            # Simplifica: usa httpx direto
            resp = httpx.get(
                f"https://api.lyrics.ovh/v1/{artist}/{name}",
                timeout=8.0,
                follow_redirects=True,
            )
            if resp.status_code == 200:
                data = resp.json()
                lyrics = data.get("lyrics", "")
                if lyrics:
                    # Retorna no máximo 600 chars pra não ficar enorme no TTS
                    lyrics_clean = lyrics.replace("\r", "").strip()
                    if len(lyrics_clean) > 600:
                        lyrics_clean = lyrics_clean[:600] + "…"
                    return f"Letra de {name} - {artist}:\n{lyrics_clean}"
            return f"Não encontrei a letra de '{name}' por {artist}."
        except Exception as e:
            return f"Erro ao buscar letra: {e}"

    # ─── Handler para main ────────────────────────────────────────────────────
    def try_handle(self, text: str) -> str | None:
        import re
        t = text.lower()

        # Se o usuário pediu explicitamente para abrir o Spotify, deixa o PCControl
        # resolver a abertura do app. O main trata o caso composto "abre + dá play".
        if "spotify" in t and any(v in t for v in ("abre ", "abrir ", "open ")):
            return None

        # Ordem importa — mais específico primeiro
        if any(p in t for p in MEDIA_TRIGGERS["now"]):
            return self.now_playing()

        if any(p in t for p in MEDIA_TRIGGERS["like"]):
            return self.like_current()

        if any(p in t for p in MEDIA_TRIGGERS["dislike"]):
            return self.dislike_current()

        if any(p in t for p in MEDIA_TRIGGERS["shuffle"]):
            return self.toggle_shuffle()

        if any(p in t for p in MEDIA_TRIGGERS["repeat"]):
            return self.toggle_repeat()

        if any(p in t for p in MEDIA_TRIGGERS["lyrics"]):
            return self.get_lyrics()

        if any(p in t for p in MEDIA_TRIGGERS["queue"]):
            for tr in MEDIA_TRIGGERS["queue"]:
                if tr in t:
                    query = t[t.index(tr) + len(tr):].strip()
                    if query and len(query) > 2:
                        return self.add_to_queue(query)
            return "Qual música você quer adicionar na fila?"

        # Volume do Spotify com valor exato
        m = re.search(r"volume\s+(?:do\s+)?spotify\s+(?:para|em|a|pro)?\s*(\d+)", t)
        if m:
            return self.set_volume(int(m.group(1)))

        if any(p in t for p in MEDIA_TRIGGERS["vol_up"]):
            return self.set_volume(80)

        if any(p in t for p in MEDIA_TRIGGERS["vol_down"]):
            return self.set_volume(30)

        if any(p in t for p in MEDIA_TRIGGERS["playlist"]):
            for tr in MEDIA_TRIGGERS["playlist"]:
                if tr in t:
                    query = t[t.index(tr) + len(tr):].strip()
                    if query:
                        return self.play_playlist(query)
            return self.play_playlist("Top Brasil")

        # Play genérico (sem música específica) — antes do search pra não conflitar
        if any(p in t for p in MEDIA_TRIGGERS["play_generic"]):
            return self.play_pause()

        if any(p in t for p in MEDIA_TRIGGERS["search"]):
            for tr in sorted(MEDIA_TRIGGERS["search"], key=len, reverse=True):  # maior trigger primeiro
                if tr in t:
                    query = t[t.index(tr) + len(tr):].strip()
                    if query and len(query) > 2:
                        return self.search_and_play(query)
            # Trigger encontrado mas sem query — play genérico
            return self.play_pause()

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
