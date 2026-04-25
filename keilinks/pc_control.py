"""
Controle completo do PC por voz.
Volume, brilho, apps, processos, teclado, clipboard, URLs, sistema,
Wi-Fi, Bluetooth, arquivos, terminal, mouse avançado, modo de energia,
dark mode, notificações, ejetar USB.
"""

import os
import re
import shutil
import subprocess
import webbrowser
import datetime
import urllib.parse

try:
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    _HAS_PYCAW = True
except ImportError:
    _HAS_PYCAW = False


# ─── Apps conhecidos ──────────────────────────────────────────────────────────
APP_MAP = {
    # Navegadores
    "spotify":                "spotify",
    "chrome":                 "chrome",
    "google chrome":          "chrome",
    "google":                 "chrome",
    "navegador":              "chrome",
    "firefox":                "firefox",
    "edge":                   "msedge",
    "microsoft edge":         "msedge",
    "brave":                  "brave",
    # Editores / código
    "notepad":                "notepad",
    "bloco de notas":         "notepad",
    "notepad++":              "notepad++",
    "vscode":                 "code",
    "visual studio code":     "code",
    "vs code":                "code",
    "visual studio":          "devenv",
    # Produtividade
    "calculadora":            "calc",
    "word":                   "winword",
    "excel":                  "excel",
    "powerpoint":             "powerpnt",
    "outlook":                "outlook",
    "onenote":                "onenote",
    "teams":                  "ms-teams",
    "microsoft teams":        "ms-teams",
    "zoom":                   "zoom",
    "slack":                  "slack",
    "notion":                 "notion",
    # Comunicação
    "discord":                "discord",
    "telegram":               "telegram",
    "whatsapp":               "whatsapp",
    # Games / mídia
    "steam":                  "steam",
    "vlc":                    "vlc",
    "media player":           "wmplayer",
    "obs":                    "obs64",
    "obs studio":             "obs64",
    "figma":                  "figma",
    # Sistema
    "explorador":             "explorer",
    "arquivos":               "explorer",
    "gerenciador de tarefas": "taskmgr",
    "task manager":           "taskmgr",
    "terminal":               "wt",
    "windows terminal":       "wt",
    "powershell":             "powershell",
    "cmd":                    "cmd",
    "prompt de comando":      "cmd",
    "paint":                  "mspaint",
    "registro":               "regedit",
    "editor de registro":     "regedit",
    "painel de controle":     "control",
    "camera":                       "microsoft.windows.camera:",
    "câmera":                       "microsoft.windows.camera:",
    "snipping tool":                "snippingtool",
    "recorte":                      "snippingtool",
    "ferramenta de recorte":        "snippingtool",
    # ── Windows 11 — configurações via ms-settings: ────────────────────────
    "configurações":                "ms-settings:",
    "settings":                     "ms-settings:",
    "configurações de som":         "ms-settings:sound",
    "configurações de áudio":       "ms-settings:sound",
    "configurações de rede":        "ms-settings:network-wifi",
    "configurações de wifi":        "ms-settings:network-wifi",
    "configurações de bluetooth":   "ms-settings:bluetooth",
    "configurações de display":     "ms-settings:display",
    "configurações de tela":        "ms-settings:display",
    "configurações de bateria":     "ms-settings:batterysaver",
    "economia de bateria":          "ms-settings:batterysaver",
    "configurações de energia":     "ms-settings:powersleep",
    "windows update":               "ms-settings:windowsupdate",
    "atualização do windows":       "ms-settings:windowsupdate",
    "apps instalados":              "ms-settings:appsfeatures",
    "configurações de aplicativos": "ms-settings:appsfeatures",
    "privacidade":                  "ms-settings:privacy",
    "configurações de privacidade": "ms-settings:privacy",
    "personalização":               "ms-settings:personalization",
    "papel de parede":              "ms-settings:personalization-background",
    "foco":                         "ms-settings:quiethours",
    "modo foco":                    "ms-settings:quiethours",
    "não perturbe":                 "ms-settings:quiethours",
    "acessibilidade":               "ms-settings:easeofaccess",
    "armazenamento":                "ms-settings:storagesense",
    "limpeza de armazenamento":     "ms-settings:storagesense",
    "conta microsoft":              "ms-settings:yourinfo",
    "dispositivos":                 "ms-settings:connecteddevices",
    "impressoras":                  "ms-settings:printers",
    "mouse settings":               "ms-settings:mousetouchpad",
    "configurações do mouse":       "ms-settings:mousetouchpad",
    "teclado settings":             "ms-settings:keyboard",
    "configurações de teclado":     "ms-settings:keyboard",
    "data e hora":                  "ms-settings:dateandtime",
    "região":                       "ms-settings:regionlanguage",
    "idioma":                       "ms-settings:regionlanguage",
}

# ─── Sites conhecidos ─────────────────────────────────────────────────────────
SITE_MAP = {
    "hbo":           "https://www.max.com",
    "max":           "https://www.max.com",
    "netflix":       "https://www.netflix.com",
    "prime video":   "https://www.primevideo.com",
    "prime":         "https://www.primevideo.com",
    "disney":        "https://www.disneyplus.com",
    "disney plus":   "https://www.disneyplus.com",
    "twitch":        "https://www.twitch.tv",
    "youtube":       "https://www.youtube.com",
    "github":        "https://www.github.com",
    "gmail":         "https://mail.google.com",
    "google drive":  "https://drive.google.com",
    "drive":         "https://drive.google.com",
    "chatgpt":       "https://chat.openai.com",
    "reddit":        "https://www.reddit.com",
    "twitter":       "https://www.twitter.com",
    "x":             "https://www.x.com",
    "instagram":     "https://www.instagram.com",
    "whatsapp web":  "https://web.whatsapp.com",
    "notion":        "https://www.notion.so",
    "figma":         "https://www.figma.com",
    "trello":        "https://www.trello.com",
    "spotify web":   "https://open.spotify.com",
    "claude":        "https://claude.ai",
    "perplexity":    "https://www.perplexity.ai",
    "gemini":        "https://gemini.google.com",
}

# ─── Pastas conhecidas ────────────────────────────────────────────────────────
import os as _os
FOLDER_MAP = {
    "downloads":        _os.path.join(_os.path.expanduser("~"), "Downloads"),
    "desktop":          _os.path.join(_os.path.expanduser("~"), "Desktop"),
    "área de trabalho": _os.path.join(_os.path.expanduser("~"), "Desktop"),
    "documentos":       _os.path.join(_os.path.expanduser("~"), "Documents"),
    "documents":        _os.path.join(_os.path.expanduser("~"), "Documents"),
    "imagens":          _os.path.join(_os.path.expanduser("~"), "Pictures"),
    "fotos":            _os.path.join(_os.path.expanduser("~"), "Pictures"),
    "músicas":          _os.path.join(_os.path.expanduser("~"), "Music"),
    "musicas":          _os.path.join(_os.path.expanduser("~"), "Music"),
    "vídeos":           _os.path.join(_os.path.expanduser("~"), "Videos"),
    "videos":           _os.path.join(_os.path.expanduser("~"), "Videos"),
    "appdata":          _os.path.join(_os.path.expanduser("~"), "AppData"),
}

# ─── Atalhos de teclado ───────────────────────────────────────────────────────
SHORTCUT_MAP = {
    "copiar":                  "ctrl+c",
    "colar":                   "ctrl+v",
    "recortar":                "ctrl+x",
    "desfazer":                "ctrl+z",
    "refazer":                 "ctrl+y",
    "salvar":                  "ctrl+s",
    "salvar como":             "ctrl+shift+s",
    "selecionar tudo":         "ctrl+a",
    "fechar aba":              "ctrl+w",
    "nova aba":                "ctrl+t",
    "reabrir aba":             "ctrl+shift+t",
    "nova janela":             "ctrl+n",
    "fechar janela":           "alt+f4",
    "print screen":            "printscreen",
    "alt f4":                  "alt+f4",
    "minimizar":               "win+down",
    "maximizar":               "win+up",
    "alterna janelas":         "alt+tab",
    "visão de tarefas":        "win+tab",
    "snap esquerda":           "win+left",
    "snap direita":            "win+right",
    "pesquisa windows":        "win+s",
    "central de notificações": "win+a",
    "task manager":            "ctrl+shift+esc",
    "tela cheia":              "f11",
    "recarregar":              "f5",
    "localizar":               "ctrl+f",
    "substituir":              "ctrl+h",
    "zoom mais":               "ctrl+=",
    "zoom menos":              "ctrl+-",
    "zoom original":           "ctrl+0",
    "enter":                   "enter",
    "escape":                  "esc",
    "esc":                     "esc",
    "tab":                     "tab",
    "backspace":               "backspace",
    "delete":                  "delete",
    "home":                    "home",
    "end":                     "end",
    "page up":                 "pageup",
    "page down":               "pagedown",
    # Windows 11 específicos
    "snap layouts":            "win+z",
    "widgets":                 "win+w",
    "área de trabalho":        "win+d",
    "nova área de trabalho":   "win+ctrl+d",
    "fecha área de trabalho":  "win+ctrl+f4",
    "próxima área de trabalho": "win+ctrl+right",
    "área anterior":           "win+ctrl+left",
    "emoji":                   "win+.",
    "copilot":                 "win+c",
    "acesso rápido":           "win+q",
    "rodar":                   "win+r",
}

# ─── Planos de energia ────────────────────────────────────────────────────────
POWER_PLANS = {
    "balanceado":      "381b4222-f694-41f0-9685-ff5bb260df2e",
    "equilibrado":     "381b4222-f694-41f0-9685-ff5bb260df2e",
    "alto desempenho": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
    "performance":     "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
    "economia":        "a1841308-3541-4fab-bc81-f71556f20b4a",
    "econômico":       "a1841308-3541-4fab-bc81-f71556f20b4a",
    "economizar":      "a1841308-3541-4fab-bc81-f71556f20b4a",
}

# Pastas onde buscar arquivos por padrão
_SEARCH_ROOTS = [
    _os.path.join(_os.path.expanduser("~"), "Desktop"),
    _os.path.join(_os.path.expanduser("~"), "Downloads"),
    _os.path.join(_os.path.expanduser("~"), "Documents"),
    _os.path.join(_os.path.expanduser("~"), "Pictures"),
    _os.path.join(_os.path.expanduser("~")),
]


class PCControl:
    def __init__(self):
        self._vol = None
        self._init_volume()

    def _init_volume(self):
        if not _HAS_PYCAW:
            return
        try:
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            self._vol = cast(interface, POINTER(IAudioEndpointVolume))
        except Exception:
            self._vol = None

    # ─── Volume ───────────────────────────────────────────────────────────────
    def set_volume(self, percent: int) -> str:
        if not self._vol:
            return "Controle de volume indisponível."
        percent = max(0, min(100, percent))
        self._vol.SetMasterVolumeLevelScalar(percent / 100.0, None)
        return f"Volume em {percent}%."

    def get_volume(self) -> int:
        if not self._vol:
            return 50
        return int(self._vol.GetMasterVolumeLevelScalar() * 100)

    def mute(self) -> str:
        if self._vol:
            self._vol.SetMute(1, None)
        return "Mutado."

    def unmute(self) -> str:
        if self._vol:
            self._vol.SetMute(0, None)
        return "Som de volta."

    # ─── Brilho ───────────────────────────────────────────────────────────────
    def set_brightness(self, percent: int) -> str:
        try:
            import screen_brightness_control as sbc
            sbc.set_brightness(max(0, min(100, percent)))
            return f"Brilho em {percent}%."
        except ImportError:
            return "Instala screen-brightness-control para controlar brilho."
        except Exception as e:
            return f"Não consegui ajustar o brilho: {e}"

    # ─── Microfone ────────────────────────────────────────────────────────────
    def mute_microphone(self) -> str:
        """Muta o microfone padrão via pycaw."""
        try:
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            from comtypes import CLSCTX_ALL
            from ctypes import cast, POINTER
            import pythoncom
            pythoncom.CoInitialize()
            devices = AudioUtilities.GetMicrophone()
            if devices is None:
                return "Microfone não encontrado."
            iface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            vol = cast(iface, POINTER(IAudioEndpointVolume))
            vol.SetMute(1, None)
            return "Microfone mutado."
        except Exception as e:
            # Fallback: atalho Win+Alt+K (Teams/Windows 11 mute)
            self.send_shortcut("ctrl+shift+m")
            return "Microfone mutado (atalho)."

    def unmute_microphone(self) -> str:
        """Desmuta o microfone padrão."""
        try:
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            from comtypes import CLSCTX_ALL
            from ctypes import cast, POINTER
            import pythoncom
            pythoncom.CoInitialize()
            devices = AudioUtilities.GetMicrophone()
            if devices is None:
                return "Microfone não encontrado."
            iface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            vol = cast(iface, POINTER(IAudioEndpointVolume))
            vol.SetMute(0, None)
            return "Microfone ativado."
        except Exception as e:
            self.send_shortcut("ctrl+shift+m")
            return "Microfone ativado (atalho)."

    # ─── Night Light ──────────────────────────────────────────────────────────
    def night_light_on(self) -> str:
        """Ativa o Night Light do Windows 11."""
        try:
            subprocess.run([
                "reg", "add",
                r"HKCU\Software\Microsoft\Windows\CurrentVersion\CloudStore\Store\DefaultAccount\Current\default$windows.data.bluelightreduction.bluelightreductionstate\windows.data.bluelightreduction.bluelightreductionstate",
                "/v", "Data", "/t", "REG_BINARY",
                "/d", "43420100",
                "/f"
            ], capture_output=True)
        except Exception:
            pass
        # Também abre as config para o user ativar se o registro não funcionar
        os.startfile("ms-settings:nightlight")
        return "Abrindo configurações de Night Light."

    def night_light_off(self) -> str:
        """Desativa o Night Light via configurações."""
        os.startfile("ms-settings:nightlight")
        return "Abrindo configurações de Night Light para desativar."

    # ─── Clipboard em voz ─────────────────────────────────────────────────────
    def read_clipboard_aloud(self) -> str:
        """Retorna o texto do clipboard para ser lido em voz pela IA."""
        try:
            import pyperclip
            text = pyperclip.paste()
            if not text or not text.strip():
                return "O clipboard está vazio."
            text = text.strip()
            if len(text) > 500:
                return f"Clipboard (primeiros 500 chars): {text[:500]}…"
            return f"No clipboard está escrito: {text}"
        except ImportError:
            return "Instala pyperclip para ler o clipboard."

    def open_clipboard_history(self) -> str:
        """Abre o histórico de clipboard do Windows 11 (Win+V)."""
        self.send_shortcut("win+v")
        return "Histórico de clipboard aberto."

    # ─── Modo Ditado ─────────────────────────────────────────────────────────
    def start_dictation(self) -> str:
        """Ativa o modo de ditado do Windows 11 (Win+H)."""
        self.send_shortcut("win+h")
        return "Modo ditado ativado. Fale para digitar."

    # ─── Always on Top ───────────────────────────────────────────────────────
    def set_window_always_on_top(self, window_title: str = None) -> str:
        """Coloca a janela ativa (ou pelo título) sempre no topo."""
        try:
            import ctypes
            HWND_TOPMOST = -1
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            if window_title:
                hwnd = ctypes.windll.user32.FindWindowW(None, window_title)
            else:
                hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                return "Janela não encontrada."
            ctypes.windll.user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
            return "Janela fixada no topo."
        except Exception as e:
            return f"Erro ao fixar janela: {e}"

    def unset_window_always_on_top(self) -> str:
        """Remove o 'sempre no topo' da janela ativa."""
        try:
            import ctypes
            HWND_NOTOPMOST = -2
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            ctypes.windll.user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
            return "Janela removida do topo."
        except Exception as e:
            return f"Erro: {e}"

    # ─── Apps ─────────────────────────────────────────────────────────────────
    @staticmethod
    def _clean_app_name(raw: str) -> str:
        """Remove artigos, possessivos, pontuação do STT e ruído antes do nome do app."""
        name = raw.lower().strip()
        # Remove pontuação final que o STT adiciona ("Spotify." → "spotify")
        name = name.rstrip(".,!?;\")'​")
        # Possessivos e determinantes que o usuário fala naturalmente
        for prefix in ["o meu ", "a minha ", "o seu ", "a sua ", "meu ", "minha ",
                       "seu ", "sua ", "um ", "uma ", "o ", "a ", "os ", "as "]:
            if name.startswith(prefix):
                name = name[len(prefix):]
                break
        # Remove sufixos comuns
        for suffix in [" pra mim", " para mim", " agora", " por favor", " pra gente"]:
            if name.endswith(suffix):
                name = name[: -len(suffix)].strip()
        # Remove pontuação residual após remoção de sufixo
        return name.strip().rstrip(".,!?;")

    def open_app(self, raw_name: str) -> str:
        name = self._clean_app_name(raw_name)
        cmd = APP_MAP.get(name)
        if not cmd:
            for key, val in APP_MAP.items():
                if key in name or name in key:
                    cmd = val
                    break
        if not cmd:
            cmd = name  # tenta como executável direto

        # URIs do Windows (ms-settings:, microsoft.windows.camera:, etc.)
        # Precisam de os.startfile(), não subprocess.Popen()
        if cmd.endswith(":") or "ms-settings" in cmd or "microsoft.windows" in cmd:
            try:
                os.startfile(cmd)
                return f"{raw_name.capitalize()} aberto."
            except Exception as e:
                return f"Não consegui abrir '{raw_name}': {e}"

        exe = shutil.which(cmd)

        # Fallback: procura em caminhos conhecidos do Windows quando não está no PATH
        if not exe:
            _loca = os.environ.get("LOCALAPPDATA", "")
            _app  = os.environ.get("APPDATA", "")
            _app_paths = {
                # Navegadores
                "chrome":        [
                    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                    os.path.join(_loca, "Google", "Chrome", "Application", "chrome.exe"),
                ],
                "firefox":       [
                    r"C:\Program Files\Mozilla Firefox\firefox.exe",
                    r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
                ],
                "msedge":        [
                    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                ],
                "brave":         [
                    os.path.join(_app, "Local", "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
                    os.path.join(_loca, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
                ],
                # Música/entretenimento
                "spotify":       [
                    os.path.join(_app, "Spotify", "Spotify.exe"),
                    os.path.join(_loca, "Microsoft", "WindowsApps", "Spotify.exe"),
                ],
                # Comunicação
                "discord":       [
                    os.path.join(_loca, "Discord", "Update.exe"),
                ],
                "telegram":      [
                    os.path.join(_app, "Telegram Desktop", "Telegram.exe"),
                    os.path.join(_loca, "Telegram Desktop", "Telegram.exe"),
                ],
                "whatsapp":      [
                    os.path.join(_loca, "WhatsApp", "WhatsApp.exe"),
                ],
                "slack":         [
                    os.path.join(_loca, "slack", "slack.exe"),
                ],
                "zoom":          [
                    os.path.join(_loca, "Zoom", "bin", "Zoom.exe"),
                ],
                # Editores
                "notepad++":     [
                    r"C:\Program Files\Notepad++\notepad++.exe",
                    r"C:\Program Files (x86)\Notepad++\notepad++.exe",
                ],
                "code":          [
                    os.path.join(_loca, "Programs", "Microsoft VS Code", "Code.exe"),
                    r"C:\Program Files\Microsoft VS Code\Code.exe",
                ],
                # Criativo / streaming
                "obs":           [
                    r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
                    r"C:\Program Files (x86)\obs-studio\bin\32bit\obs32.exe",
                ],
                "obs studio":    [r"C:\Program Files\obs-studio\bin\64bit\obs64.exe"],
                "vlc":           [
                    r"C:\Program Files\VideoLAN\VLC\vlc.exe",
                    r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
                ],
                # Jogos
                "steam":         [
                    r"C:\Program Files (x86)\Steam\steam.exe",
                    r"C:\Program Files\Steam\steam.exe",
                ],
            }
            # chrome/msedge mapeados pelo APP_MAP como 'chrome'/'msedge' — busca pelo cmd
            for candidate_paths in _app_paths.get(cmd, _app_paths.get(name, [])):
                candidate = os.path.normpath(candidate_paths)
                if os.path.isfile(candidate):
                    exe = candidate
                    break

        # Último fallback: tenta como executável direto
        if not exe:
            exe = cmd

        # Discord precisa de --processStart no Update.exe
        if "Discord" in (exe or "") and "Update.exe" in (exe or ""):
            try:
                subprocess.Popen([exe, "--processStart", "Discord.exe"])
                return "Discord aberto."
            except Exception as e:
                return f"Não consegui abrir o Discord: {e}"

        try:
            subprocess.Popen([exe])
            return f"{name.capitalize()} aberto."
        except Exception as e:
            return f"Não consegui abrir '{name}': {e}"

    def close_app(self, name: str) -> str:
        try:
            import psutil
            name_lower = name.lower().strip()
            # Verifica se o nome do app tem equivalente no APP_MAP
            exe_name = APP_MAP.get(name_lower, name_lower)
            killed = []
            for proc in psutil.process_iter(["name", "pid"]):
                pname = proc.info["name"].lower()
                if name_lower in pname or exe_name.lower() in pname:
                    proc.kill()
                    killed.append(proc.info["name"])
            if killed:
                return f"Fechei: {', '.join(set(killed))}."
            return f"Não encontrei '{name}' rodando."
        except ImportError:
            return "Instala psutil para fechar processos."
        except Exception as e:
            return f"Erro ao fechar {name}: {e}"

    # ─── Teclado ──────────────────────────────────────────────────────────────
    def send_shortcut(self, shortcut: str) -> str:
        try:
            import keyboard
            keyboard.send(shortcut)
            return f"Atalho '{shortcut}' enviado."
        except ImportError:
            return "Instala keyboard para enviar atalhos."
        except Exception as e:
            return f"Erro ao enviar atalho: {e}"

    def type_text(self, text: str) -> str:
        try:
            import keyboard
            keyboard.write(text, delay=0.02)
            return f"Digitei: {text}"
        except ImportError:
            return "Instala keyboard para digitar texto."
        except Exception as e:
            return f"Erro ao digitar: {e}"

    def press_key(self, key: str) -> str:
        try:
            import keyboard
            keyboard.press_and_release(key)
            return f"Tecla '{key}' pressionada."
        except ImportError:
            return "Instala keyboard para pressionar teclas."

    # ─── Clipboard ────────────────────────────────────────────────────────────
    def get_clipboard(self) -> str:
        try:
            import pyperclip
            text = pyperclip.paste()
            return f"Clipboard: {text[:300]}" if text else "Clipboard vazio."
        except ImportError:
            return "Instala pyperclip para acessar o clipboard."

    def set_clipboard(self, text: str) -> str:
        try:
            import pyperclip
            pyperclip.copy(text)
            return "Copiado para o clipboard."
        except ImportError:
            return "Instala pyperclip para usar o clipboard."

    # ─── URLs ─────────────────────────────────────────────────────────────────
    def open_url(self, url: str) -> str:
        if not url.startswith("http"):
            url = "https://" + url
        webbrowser.open(url)
        return f"Abrindo {url}."

    def search_google(self, query: str) -> str:
        url = "https://www.google.com/search?q=" + urllib.parse.quote(query)
        webbrowser.open(url)
        return f"Pesquisando '{query}' no Google."

    def search_youtube(self, query: str) -> str:
        url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)
        webbrowser.open(url)
        return f"Pesquisando '{query}' no YouTube."

    # ─── Pastas ───────────────────────────────────────────────────────────────
    def open_folder(self, name: str) -> str:
        name_lower = name.lower().strip()
        path = FOLDER_MAP.get(name_lower)
        if not path:
            for k, v in FOLDER_MAP.items():
                if k in name_lower or name_lower in k:
                    path = v
                    break
        if path and os.path.exists(path):
            subprocess.Popen(["explorer", path])
            return f"Abrindo pasta {name}."
        return f"Não conheço a pasta '{name}'."

    # ─── Screenshot ───────────────────────────────────────────────────────────
    def take_screenshot(self) -> str:
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        os.makedirs(desktop, exist_ok=True)
        ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(desktop, f"screenshot_{ts}.png")
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            img.save(path)
            return f"Screenshot salvo no Desktop: screenshot_{ts}.png"
        except ImportError:
            pass
        try:
            ps_script = (
                "Add-Type -AssemblyName System.Windows.Forms,System.Drawing; "
                "$s=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds; "
                "$bmp=New-Object System.Drawing.Bitmap($s.Width,$s.Height); "
                "$g=[System.Drawing.Graphics]::FromImage($bmp); "
                "$g.CopyFromScreen(0,0,0,0,$bmp.Size); "
                f'$bmp.Save("{path.replace(chr(92), "/")}"); '
                "$g.Dispose(); $bmp.Dispose()"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                capture_output=True, timeout=10,
            )
            if os.path.exists(path):
                return f"Screenshot salvo no Desktop: screenshot_{ts}.png"
        except Exception as e:
            return f"Erro ao tirar screenshot: {e}"
        return "Não consegui salvar o screenshot."

    # ─── Sistema ──────────────────────────────────────────────────────────────
    def sleep_pc(self) -> str:
        subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
        return "Colocando o PC pra dormir."

    def lock_pc(self) -> str:
        subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"])
        return "PC bloqueado."

    def shutdown(self) -> str:
        subprocess.run(["shutdown", "/s", "/t", "10"])
        return "Desligando em 10 segundos. Fala 'cancela' se mudar de ideia."

    def cancel_shutdown(self) -> str:
        subprocess.run(["shutdown", "/a"])
        return "Desligamento cancelado."

    def restart(self) -> str:
        subprocess.run(["shutdown", "/r", "/t", "10"])
        return "Reiniciando em 10 segundos."

    # ─── Window management ────────────────────────────────────────────────────
    def focus_window(self, name: str) -> str:
        try:
            import pygetwindow as gw
            wins = gw.getWindowsWithTitle(name)
            if not wins:
                all_titles = gw.getAllTitles()
                matches = [w for w in all_titles if name.lower() in w.lower()]
                if matches:
                    wins = gw.getWindowsWithTitle(matches[0])
            if wins:
                w = wins[0]
                if w.isMinimized:
                    w.restore()
                w.activate()
                return f"Janela '{w.title}' em foco."
            return f"Nenhuma janela com '{name}' aberta."
        except ImportError:
            return "Instala pygetwindow para gerenciar janelas."
        except Exception as e:
            return f"Erro ao focar janela: {e}"

    def list_windows(self) -> str:
        try:
            import pygetwindow as gw
            titles = [t for t in gw.getAllTitles() if t.strip()]
            if not titles:
                return "Nenhuma janela aberta."
            return "Janelas abertas:\n" + "\n".join(f"- {t}" for t in titles[:20])
        except ImportError:
            return "Instala pygetwindow para listar janelas."

    def minimize_window(self, name: str = "") -> str:
        try:
            import pygetwindow as gw
            wins = gw.getWindowsWithTitle(name) if name else [gw.getActiveWindow()]
            if wins and wins[0]:
                wins[0].minimize()
                return "Janela minimizada."
            return "Nenhuma janela encontrada."
        except ImportError:
            return "Instala pygetwindow para gerenciar janelas."

    def maximize_window(self, name: str = "") -> str:
        try:
            import pygetwindow as gw
            wins = gw.getWindowsWithTitle(name) if name else [gw.getActiveWindow()]
            if wins and wins[0]:
                wins[0].maximize()
                return "Janela maximizada."
            return "Nenhuma janela encontrada."
        except ImportError:
            return "Instala pygetwindow para gerenciar janelas."

    # ─── Processos ────────────────────────────────────────────────────────────
    def list_processes(self) -> str:
        try:
            import psutil
            _SYSTEM_PROCS = {
                "system", "idle", "registry", "smss.exe", "csrss.exe",
                "wininit.exe", "services.exe", "lsass.exe", "winlogon.exe",
                "fontdrvhost.exe", "dwm.exe", "svchost.exe",
            }
            procs = sorted({
                p.info["name"]
                for p in psutil.process_iter(["name"])
                if p.info["name"] and p.info["name"].lower() not in _SYSTEM_PROCS
            })
            return "Processos em execução:\n" + "\n".join(f"- {p}" for p in procs[:35])
        except ImportError:
            return "Instala psutil para listar processos."

    def system_info(self) -> str:
        try:
            import psutil
            cpu   = psutil.cpu_percent(interval=0.5)
            mem   = psutil.virtual_memory()
            disk  = psutil.disk_usage(os.path.expanduser("~").split(os.sep)[0] + os.sep)
            freq  = psutil.cpu_freq()
            freq_str = f" @ {freq.current:.0f}MHz" if freq else ""
            return (
                f"CPU: {cpu:.0f}%{freq_str} | "
                f"RAM: {mem.percent:.0f}% ({mem.used // 1024**2}MB / {mem.total // 1024**2}MB) | "
                f"Disco: {disk.percent:.0f}% usado, {disk.free // 1024**3}GB livres"
            )
        except ImportError:
            return "Instala psutil para info do sistema."
        except Exception as e:
            return f"Erro ao consultar sistema: {e}"

    # ─── Mouse ────────────────────────────────────────────────────────────────
    def mouse_move(self, x: int, y: int) -> str:
        try:
            import pyautogui
            pyautogui.moveTo(x, y, duration=0.3)
            return f"Mouse em ({x}, {y})."
        except ImportError:
            return "Instala pyautogui para controlar o mouse."

    def mouse_click(self, x: int = None, y: int = None, button: str = "left") -> str:
        try:
            import pyautogui
            if x is not None and y is not None:
                pyautogui.click(x, y, button=button)
            else:
                pyautogui.click(button=button)
            return "Clique executado."
        except ImportError:
            return "Instala pyautogui para controlar o mouse."

    def double_click(self, x: int = None, y: int = None) -> str:
        try:
            import pyautogui
            if x is not None and y is not None:
                pyautogui.doubleClick(x, y)
            else:
                pyautogui.doubleClick()
            return "Double-click executado."
        except ImportError:
            return "Instala pyautogui para controlar o mouse."

    def right_click(self, x: int = None, y: int = None) -> str:
        try:
            import pyautogui
            if x is not None and y is not None:
                pyautogui.rightClick(x, y)
            else:
                pyautogui.rightClick()
            return "Right-click executado."
        except ImportError:
            return "Instala pyautogui para controlar o mouse."

    def scroll(self, direction: str, amount: int = 3) -> str:
        try:
            import pyautogui
            clicks = amount if direction == "up" else -amount
            pyautogui.scroll(clicks)
            return f"Rolou {'para cima' if direction == 'up' else 'para baixo'}."
        except ImportError:
            return "Instala pyautogui para rolar a tela."

    def drag(self, x1: int, y1: int, x2: int, y2: int) -> str:
        try:
            import pyautogui
            pyautogui.moveTo(x1, y1, duration=0.2)
            pyautogui.dragTo(x2, y2, duration=0.5, button="left")
            return f"Arrastei ({x1},{y1}) → ({x2},{y2})."
        except ImportError:
            return "Instala pyautogui para arrastar."

    def get_mouse_pos(self) -> str:
        try:
            import pyautogui
            x, y = pyautogui.position()
            return f"Mouse em ({x}, {y})."
        except ImportError:
            return "Instala pyautogui para verificar posição do mouse."

    # ─── Wi-Fi ────────────────────────────────────────────────────────────────
    def wifi_on(self) -> str:
        result = subprocess.run(
            ["netsh", "interface", "set", "interface", "Wi-Fi", "enabled"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return "Wi-Fi ligado."
        # Tenta encontrar o nome correto da interface
        return self._wifi_toggle("enabled")

    def wifi_off(self) -> str:
        result = subprocess.run(
            ["netsh", "interface", "set", "interface", "Wi-Fi", "disabled"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return "Wi-Fi desligado."
        return self._wifi_toggle("disabled")

    def _wifi_toggle(self, state: str) -> str:
        """Tenta encontrar a interface Wi-Fi pelo nome real."""
        result = subprocess.run(
            ["netsh", "interface", "show", "interface"],
            capture_output=True, text=True, encoding="cp850",
        )
        for line in result.stdout.splitlines():
            if "wi-fi" in line.lower() or "wireless" in line.lower() or "wifi" in line.lower():
                parts = line.split()
                if parts:
                    iface = parts[-1]
                    subprocess.run(
                        ["netsh", "interface", "set", "interface", iface, state],
                        capture_output=True,
                    )
                    label = "ligado" if state == "enabled" else "desligado"
                    return f"Wi-Fi {label} (interface: {iface})."
        return f"Não encontrei interface Wi-Fi. Verifique nas configurações de rede."

    def list_wifi(self) -> str:
        result = subprocess.run(
            ["netsh", "wlan", "show", "networks"],
            capture_output=True, text=True, encoding="cp850",
        )
        if result.returncode != 0:
            return "Wi-Fi desligado ou sem adaptador."
        lines = result.stdout.splitlines()
        networks = [l.split(":", 1)[-1].strip() for l in lines if "SSID" in l and "BSSID" not in l]
        if networks:
            return "Redes Wi-Fi disponíveis:\n" + "\n".join(f"- {n}" for n in networks[:15])
        return "Nenhuma rede encontrada (ou Wi-Fi desligado)."

    def connect_wifi(self, ssid: str) -> str:
        result = subprocess.run(
            ["netsh", "wlan", "connect", f"name={ssid}"],
            capture_output=True, text=True, encoding="cp850",
        )
        if "concluída" in result.stdout.lower() or "successfully" in result.stdout.lower():
            return f"Conectado à rede '{ssid}'."
        return f"Tentei conectar em '{ssid}'. Verifique se o nome está certo e se já está salvo."

    def wifi_status(self) -> str:
        result = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True, text=True, encoding="cp850",
        )
        if result.returncode != 0 or not result.stdout.strip():
            return "Wi-Fi desligado ou sem adaptador."
        for line in result.stdout.splitlines():
            if "SSID" in line and "BSSID" not in line:
                ssid = line.split(":", 1)[-1].strip()
                return f"Conectado em: {ssid}"
        return "Wi-Fi ligado mas não conectado."

    # ─── Bluetooth ────────────────────────────────────────────────────────────
    def _bluetooth_set_state(self, state_on: bool) -> str:
        state_str  = "On" if state_on else "Off"
        label      = "ligado" if state_on else "desligado"
        script = (
            "Add-Type -AssemblyName System.Runtime.WindowsRuntime | Out-Null; "
            "[void][Windows.Devices.Radios.Radio,Windows.System.Devices,ContentType=WindowsRuntime]; "
            "$ra = [Windows.Devices.Radios.Radio]::GetRadiosAsync().GetAwaiter().GetResult(); "
            "$bt = $ra | Where-Object { $_.Kind -eq 'Bluetooth' }; "
            f"if ($bt) {{ $bt.SetStateAsync('{state_str}').GetAwaiter().GetResult() | Out-Null; Write-Output 'OK' }} "
            "else { Write-Output 'NOT_FOUND' }"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True, text=True, timeout=10,
            )
            if "OK" in result.stdout:
                return f"Bluetooth {label}."
            if "NOT_FOUND" in result.stdout:
                return "Adaptador Bluetooth não encontrado."
        except Exception as e:
            pass
        return f"Não consegui {'ligar' if state_on else 'desligar'} o Bluetooth."

    def bluetooth_on(self)  -> str: return self._bluetooth_set_state(True)
    def bluetooth_off(self) -> str: return self._bluetooth_set_state(False)

    def list_bluetooth_devices(self) -> str:
        script = (
            "Add-Type -AssemblyName System.Runtime.WindowsRuntime | Out-Null; "
            "[void][Windows.Devices.Enumeration.DeviceInformation,Windows.System.Devices,ContentType=WindowsRuntime]; "
            "$selector = [Windows.Devices.Bluetooth.BluetoothDevice]::GetDeviceSelectorFromPairingState($true); "
            "$devices = [Windows.Devices.Enumeration.DeviceInformation]::FindAllAsync($selector).GetAwaiter().GetResult(); "
            "foreach ($d in $devices) { Write-Output $d.Name }"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True, text=True, timeout=10,
            )
            devs = [l.strip() for l in result.stdout.splitlines() if l.strip()]
            if devs:
                return "Dispositivos Bluetooth pareados:\n" + "\n".join(f"- {d}" for d in devs)
            return "Nenhum dispositivo Bluetooth pareado encontrado."
        except Exception as e:
            return f"Erro ao listar Bluetooth: {e}"

    # ─── Gerenciamento de arquivos ────────────────────────────────────────────
    def find_file(self, name: str) -> str:
        found = []
        name_lower = name.lower()
        for root in _SEARCH_ROOTS:
            if not os.path.exists(root):
                continue
            try:
                for dirpath, _, files in os.walk(root):
                    for fname in files:
                        if name_lower in fname.lower():
                            found.append(os.path.join(dirpath, fname))
                            if len(found) >= 8:
                                break
                    if len(found) >= 8:
                        break
            except PermissionError:
                continue
        if found:
            return "Encontrei:\n" + "\n".join(f"- {p}" for p in found)
        return f"Não encontrei '{name}' nas pastas principais."

    def open_file(self, name_or_path: str) -> str:
        # Caminho direto
        if os.path.exists(name_or_path):
            os.startfile(name_or_path)
            return f"Abrindo {os.path.basename(name_or_path)}."
        # Busca pelo nome
        found = []
        name_lower = name_or_path.lower()
        for root in _SEARCH_ROOTS:
            if not os.path.exists(root):
                continue
            try:
                for dirpath, _, files in os.walk(root):
                    for fname in files:
                        if name_lower in fname.lower():
                            found.append(os.path.join(dirpath, fname))
                    if found:
                        break
            except PermissionError:
                continue
        if len(found) == 1:
            os.startfile(found[0])
            return f"Abrindo {os.path.basename(found[0])}."
        if len(found) > 1:
            return (
                f"Encontrei {len(found)} arquivos com esse nome. Qual você quer?\n"
                + "\n".join(f"- {p}" for p in found[:5])
            )
        return f"Não encontrei '{name_or_path}'."

    def create_file(self, path: str) -> str:
        # Se não tem barra, cria no Desktop
        if not os.sep in path and "/" not in path:
            path = os.path.join(os.path.expanduser("~"), "Desktop", path)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a"):
                pass
            return f"Arquivo criado: {path}"
        except Exception as e:
            return f"Não consegui criar '{path}': {e}"

    def create_folder(self, path: str) -> str:
        if not os.sep in path and "/" not in path:
            path = os.path.join(os.path.expanduser("~"), "Desktop", path)
        try:
            os.makedirs(path, exist_ok=True)
            return f"Pasta criada: {path}"
        except Exception as e:
            return f"Não consegui criar a pasta: {e}"

    def delete_file(self, name_or_path: str) -> str:
        """Deleta apenas se encontrar exatamente 1 arquivo com esse nome."""
        if os.path.isfile(name_or_path):
            os.remove(name_or_path)
            return f"Arquivo '{name_or_path}' deletado."
        if os.path.isdir(name_or_path):
            return "Isso é uma pasta, não um arquivo. Use 'deleta a pasta'."
        # Busca
        found = []
        name_lower = name_or_path.lower()
        for root in _SEARCH_ROOTS[:3]:  # Segurança: só Desktop/Downloads/Documents
            if not os.path.exists(root):
                continue
            try:
                for dirpath, _, files in os.walk(root):
                    for fname in files:
                        if name_lower == fname.lower():
                            found.append(os.path.join(dirpath, fname))
            except PermissionError:
                continue
        if len(found) == 1:
            os.remove(found[0])
            return f"Deletei: {found[0]}"
        if len(found) > 1:
            return f"Encontrei {len(found)} arquivos com esse nome. Seja mais específico:\n" + "\n".join(f"- {p}" for p in found)
        return f"Não encontrei '{name_or_path}'."

    def delete_folder(self, name_or_path: str) -> str:
        if os.path.isdir(name_or_path):
            shutil.rmtree(name_or_path)
            return f"Pasta '{name_or_path}' deletada."
        return f"Não encontrei a pasta '{name_or_path}'."

    def copy_file(self, src: str, dst: str) -> str:
        try:
            shutil.copy2(src, dst)
            return f"Copiado para {dst}."
        except Exception as e:
            return f"Erro ao copiar: {e}"

    def move_file(self, src: str, dst: str) -> str:
        try:
            shutil.move(src, dst)
            return f"Movido para {dst}."
        except Exception as e:
            return f"Erro ao mover: {e}"

    def rename_file(self, old: str, new: str) -> str:
        try:
            os.rename(old, new)
            return f"Renomeado para '{new}'."
        except Exception as e:
            return f"Erro ao renomear: {e}"

    def list_folder_contents(self, path: str = "") -> str:
        if not path:
            path = os.path.expanduser("~")
        try:
            items = os.listdir(path)
            dirs  = [f"📁 {i}" for i in sorted(items) if os.path.isdir(os.path.join(path, i))]
            files = [f"📄 {i}" for i in sorted(items) if os.path.isfile(os.path.join(path, i))]
            all_items = dirs + files
            if not all_items:
                return f"Pasta '{path}' está vazia."
            return f"Conteúdo de '{os.path.basename(path)}':\n" + "\n".join(all_items[:30])
        except Exception as e:
            return f"Erro ao listar pasta: {e}"

    # ─── Terminal / Shell ─────────────────────────────────────────────────────
    def run_command(self, cmd: str) -> str:
        """Abre terminal e executa o comando. Não espera resultado (não-bloqueante)."""
        try:
            # Tenta Windows Terminal primeiro, senão PowerShell
            subprocess.Popen(["wt", "powershell", "-NoExit", "-Command", cmd])
            return f"Rodando no terminal: {cmd}"
        except FileNotFoundError:
            try:
                subprocess.Popen(["powershell", "-NoExit", "-Command", cmd])
                return f"Rodando no PowerShell: {cmd}"
            except Exception as e:
                return f"Erro ao executar: {e}"

    def run_command_silent(self, cmd: str) -> str:
        """Executa comando e retorna a saída (bloqueante, sem abrir janela)."""
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", cmd],
                capture_output=True, text=True, timeout=15, encoding="utf-8",
            )
            out = (result.stdout or result.stderr or "").strip()
            return out[:400] if out else "Comando executado (sem saída)."
        except subprocess.TimeoutExpired:
            return "Comando demorou demais. Tente no terminal."
        except Exception as e:
            return f"Erro: {e}"

    # ─── Modo de energia ──────────────────────────────────────────────────────
    def set_power_mode(self, mode: str) -> str:
        mode_lower = mode.lower().strip()
        guid = POWER_PLANS.get(mode_lower)
        if not guid:
            return f"Modo '{mode}' não reconhecido. Use: balanceado, alto desempenho, economia."
        result = subprocess.run(["powercfg", "/s", guid], capture_output=True)
        if result.returncode == 0:
            return f"Modo de energia: {mode}."
        return f"Não consegui mudar o modo de energia (tente como administrador)."

    def get_power_mode(self) -> str:
        result = subprocess.run(
            ["powercfg", "/getactivescheme"],
            capture_output=True, text=True, encoding="cp850",
        )
        out = result.stdout.lower()
        if "balanced" in out or "balanceado" in out or "381b4222" in out:
            return "Modo atual: Balanceado."
        if "high" in out or "alto" in out or "8c5e7fda" in out:
            return "Modo atual: Alto Desempenho."
        if "power saver" in out or "economia" in out or "a1841308" in out:
            return "Modo atual: Economia."
        return f"Modo de energia: {result.stdout.strip()}"

    # ─── Dark mode / Night light ──────────────────────────────────────────────
    def toggle_dark_mode(self, force_dark: bool = None) -> str:
        import winreg
        key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
            current, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            if force_dark is None:
                new_val = 0 if current == 1 else 1
            else:
                new_val = 0 if force_dark else 1
            winreg.SetValueEx(key, "AppsUseLightTheme",   0, winreg.REG_DWORD, new_val)
            winreg.SetValueEx(key, "SystemUsesLightTheme", 0, winreg.REG_DWORD, new_val)
            winreg.CloseKey(key)
            return "Modo escuro ativado." if new_val == 0 else "Modo claro ativado."
        except Exception as e:
            return f"Erro ao mudar tema: {e}"

    def toggle_night_light(self) -> str:
        """Abre as configurações de Night Light do Windows 11."""
        os.startfile("ms-settings:nightlight")
        return "Configurações de Night Light abertas."

    # ─── Notificações ─────────────────────────────────────────────────────────
    def show_notification(self, title: str, message: str, duration: int = 5) -> str:
        # win11toast — melhor no Windows 11 (não bloqueia thread)
        try:
            from win11toast import notify as _notify11
            _notify11(title, message)
            return f"Notificação enviada: {title}"
        except ImportError:
            pass
        except Exception:
            pass
        # Fallback: win10toast
        try:
            from win10toast import ToastNotifier
            ToastNotifier().show_toast(title, message, duration=duration, threaded=True)
            return f"Notificação enviada: {title}"
        except ImportError:
            pass
        except Exception:
            pass
        # Fallback final: PowerShell
        t = title.replace("'", "''")
        m = message.replace("'", "''")
        script = (
            "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null; "
            "$tmpl = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(2); "
            "$nodes = $tmpl.GetElementsByTagName('text'); "
            f"$nodes.Item(0).AppendChild($tmpl.CreateTextNode('{t}')) | Out-Null; "
            f"$nodes.Item(1).AppendChild($tmpl.CreateTextNode('{m}')) | Out-Null; "
            "$toast = [Windows.UI.Notifications.ToastNotification]::new($tmpl); "
            "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Keilinks').Show($toast)"
        )
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command", script],
                           capture_output=True, timeout=5)
            return f"Notificação: {title}"
        except Exception as e:
            return f"Erro ao enviar notificação: {e}"

    # ─── Ejetar USB / drive ───────────────────────────────────────────────────
    def eject_usb(self, drive: str = None) -> str:
        if not drive:
            # Lista drives removíveis
            script = (
                "Get-WmiObject Win32_Volume | "
                "Where-Object { $_.DriveType -eq 2 } | "
                "Select-Object -ExpandProperty DriveLetter"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True, text=True, timeout=5,
            )
            drives = [l.strip() for l in result.stdout.splitlines() if l.strip()]
            if not drives:
                return "Nenhum dispositivo removível encontrado."
            if len(drives) == 1:
                return self.eject_usb(drives[0])
            return "Qual drive ejeto? " + ", ".join(drives)

        drive_letter = drive.upper().strip().rstrip(":\\") + ":"
        script = (
            f"$shell = New-Object -ComObject Shell.Application; "
            f"$item = $shell.Namespace(17).ParseName('{drive_letter}'); "
            f"if ($item) {{ $item.InvokeVerb('Eject'); Write-Output 'OK' }} "
            f"else {{ Write-Output 'NOT_FOUND' }}"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=5,
        )
        if "OK" in result.stdout:
            return f"Drive {drive_letter} ejetado com segurança."
        return f"Não encontrei o drive {drive_letter}."

    # ─── OCR — Windows nativo (winrt) + Tesseract fallback ───────────────────
    def _ocr_screenshot(self, monitor: int = 1) -> list[tuple[str, int, int, int, int]]:
        """
        Tira screenshot e retorna lista de (texto, x, y, largura, altura).
        Tenta Windows OCR nativo primeiro (sem deps extras),
        depois Tesseract como fallback.
        """
        import mss
        import numpy as np
        import cv2
        import tempfile, os

        with mss.mss() as sct:
            img   = sct.grab(sct.monitors[monitor])
            frame = np.array(img)[:, :, :3]

        # ── Windows OCR (WinRT — já instalado) ────────────────────────────────
        tmp = tempfile.mktemp(suffix=".png")
        try:
            cv2.imwrite(tmp, frame)
            words = self._winrt_ocr(tmp)
            if words:
                return words
        finally:
            try: os.remove(tmp)
            except: pass

        # ── Tesseract fallback ────────────────────────────────────────────────
        return self._tesseract_ocr(frame)

    def _winrt_ocr(self, png_path: str) -> list[tuple[str, int, int, int, int]]:
        """Windows OCR via WinRT — nativo, sem Tesseract."""
        try:
            import asyncio
            import winrt.windows.storage as ws
            import winrt.windows.graphics.imaging as wgi
            import winrt.windows.media.ocr as wo

            abs_path = os.path.abspath(png_path)

            async def _run():
                file    = await ws.StorageFile.get_file_from_path_async(abs_path)
                stream  = await file.open_read_async()
                decoder = await wgi.BitmapDecoder.create_async(stream)
                bitmap  = await decoder.get_software_bitmap_async()

                engine = wo.OcrEngine.try_create_from_user_profile_languages()
                if engine is None:
                    return []
                result = await engine.recognize_async(bitmap)
                out = []
                for line in result.lines:
                    for word in line.words:
                        b = word.bounding_rect
                        out.append((word.text, int(b.x), int(b.y), int(b.width), int(b.height)))
                return out

            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(_run())
            finally:
                loop.close()
        except Exception:
            return []

    def _tesseract_ocr(self, frame) -> list[tuple[str, int, int, int, int]]:
        """Tesseract OCR — precisa do binário instalado."""
        try:
            import pytesseract
            # Garante que o binário seja encontrado mesmo sem reiniciar o terminal
            import os as _os
            _tess = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            if _os.path.isfile(_tess):
                pytesseract.pytesseract.tesseract_cmd = _tess
            data = pytesseract.image_to_data(
                frame, lang="por+eng",
                output_type=pytesseract.Output.DICT,
                config="--psm 11",
            )
            words = []
            for i, word in enumerate(data["text"]):
                if not word.strip() or int(data["conf"][i]) < 30:
                    continue
                words.append((word, data["left"][i], data["top"][i],
                               data["width"][i], data["height"][i]))
            return words
        except Exception:
            return []

    # ─── Automação de tela (OCR + click) ─────────────────────────────────────
    def click_on_text(self, text: str, monitor: int = 1) -> str:
        """Tira screenshot, acha o texto via OCR (Windows nativo ou Tesseract) e clica."""
        try:
            import pyautogui
        except ImportError:
            return "Instala pyautogui para clicar na tela."

        words = self._ocr_screenshot(monitor)
        if not words:
            return "OCR indisponível. Verifique se os pacotes winrt estão instalados."

        text_lower = text.lower()
        best_x, best_y, best_score = None, None, 0.0

        for word_text, x, y, w, h in words:
            if text_lower in word_text.lower():
                score = len(text) / max(len(word_text), 1)
                if score > best_score:
                    best_x, best_y = x + w // 2, y + h // 2
                    best_score = score

        if best_x is not None:
            pyautogui.click(best_x, best_y)
            return f"Cliquei em '{text}' ({best_x},{best_y})."
        return f"Não encontrei '{text}' na tela."

    def click_button(self, label: str) -> str:
        return self.click_on_text(label)

    def type_in_field(self, field_label: str, text: str) -> str:
        """Clica no campo pelo label e digita."""
        result = self.click_on_text(field_label)
        if "Cliquei" not in result:
            return result
        import time as _t
        _t.sleep(0.3)
        return self.type_text(text)

    def search_on_screen(self, query: str) -> str:
        """Ctrl+F e digita a busca na janela ativa."""
        self.send_shortcut("ctrl+f")
        import time as _t
        _t.sleep(0.5)
        return self.type_text(query)

    # ─── Controle do navegador ────────────────────────────────────────────────
    def browser_go_to(self, url: str) -> str:
        """Foca a barra de endereços do browser ativo e navega para a URL."""
        import time as _t
        if not url.startswith("http"):
            url = "https://" + url
        self.send_shortcut("ctrl+l")   # foca a barra de endereços
        _t.sleep(0.3)
        self.type_text(url)
        _t.sleep(0.1)
        self.press_key("enter")
        return f"Navegando para {url}."

    def browser_search(self, query: str) -> str:
        """Abre nova aba e pesquisa no Google."""
        import time as _t
        self.send_shortcut("ctrl+t")   # nova aba
        _t.sleep(0.4)
        url = "https://www.google.com/search?q=" + urllib.parse.quote(query)
        self.type_text(url)
        _t.sleep(0.1)
        self.press_key("enter")
        return f"Pesquisando '{query}' no navegador."

    def browser_new_tab(self, url: str = "") -> str:
        import time as _t
        self.send_shortcut("ctrl+t")
        if url:
            _t.sleep(0.4)
            return self.browser_go_to(url)
        return "Nova aba aberta."

    def browser_close_tab(self) -> str:
        self.send_shortcut("ctrl+w")
        return "Aba fechada."

    def browser_back(self) -> str:
        self.send_shortcut("alt+left")
        return "Voltei."

    def browser_forward(self) -> str:
        self.send_shortcut("alt+right")
        return "Avancei."

    def browser_refresh(self) -> str:
        self.send_shortcut("f5")
        return "Página recarregada."

    # ─── Busca em streaming ───────────────────────────────────────────────────
    _STREAMING_SEARCH = {
        "netflix":     "https://www.netflix.com/search?q={}",
        "max":         "https://play.max.com/search?q={}",
        "hbo":         "https://play.max.com/search?q={}",
        "disney":      "https://www.disneyplus.com/search?q={}",
        "disney plus": "https://www.disneyplus.com/search?q={}",
        "prime":       "https://www.primevideo.com/search/ref=atv_nb_sr?phrase={}",
        "prime video": "https://www.primevideo.com/search/ref=atv_nb_sr?phrase={}",
        "youtube":     "https://www.youtube.com/results?search_query={}",
        "twitch":      "https://www.twitch.tv/search?term={}",
        "crunchyroll":  "https://www.crunchyroll.com/pt-br/search?q={}",
    }

    def search_streaming(self, service: str, query: str) -> str:
        svc = service.lower().strip()
        template = None
        for key, url in self._STREAMING_SEARCH.items():
            if key in svc:
                template = url
                break
        if not template:
            return f"Serviço '{service}' não reconhecido. Use: Netflix, Max, Disney, Prime, YouTube."
        url = template.format(urllib.parse.quote(query))
        webbrowser.open(url)
        return f"Pesquisando '{query}' no {service.title()}."

    # ─── Informações da tela ──────────────────────────────────────────────────
    def screen_info(self) -> str:
        try:
            import pyautogui
            w, h = pyautogui.size()
            return f"Resolução: {w}x{h}."
        except ImportError:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-CimInstance Win32_VideoController).CurrentHorizontalResolution,"
                 "(Get-CimInstance Win32_VideoController).CurrentVerticalResolution"],
                capture_output=True, text=True, timeout=5,
            )
            return f"Resolução: {result.stdout.strip()}"

    # ─── Múltiplos monitores ──────────────────────────────────────────────────
    def list_monitors(self) -> str:
        try:
            import ctypes
            from ctypes import wintypes
            monitors = []

            MonitorEnumProc = ctypes.WINFUNCTYPE(
                ctypes.c_bool,
                ctypes.c_ulong, ctypes.c_ulong,
                ctypes.POINTER(wintypes.RECT), ctypes.c_longlong,
            )

            def _cb(hMon, hdc, lpRect, lParam):
                r = lpRect.contents
                monitors.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
                return True

            ctypes.windll.user32.EnumDisplayMonitors(None, None, MonitorEnumProc(_cb), 0)
            if not monitors:
                return "Nenhum monitor encontrado."
            lines = [f"Monitor {i}: {w}x{h} em ({x},{y})" for i, (x, y, w, h) in enumerate(monitors, 1)]
            return "\n".join(lines)
        except Exception as e:
            return f"Erro ao listar monitores: {e}"

    def _get_monitor_origins(self) -> list[tuple[int, int]]:
        import ctypes
        from ctypes import wintypes
        origins: list[tuple[int, int]] = []
        MonitorEnumProc = ctypes.WINFUNCTYPE(
            ctypes.c_bool, ctypes.c_ulong, ctypes.c_ulong,
            ctypes.POINTER(wintypes.RECT), ctypes.c_longlong,
        )
        def _cb(hMon, hdc, lpRect, lParam):
            r = lpRect.contents
            origins.append((r.left, r.top))
            return True
        ctypes.windll.user32.EnumDisplayMonitors(None, None, MonitorEnumProc(_cb), 0)
        return origins

    def move_window_to_monitor(self, window_name: str, monitor_num: int) -> str:
        try:
            import pygetwindow as gw
            origins = self._get_monitor_origins()
            if monitor_num < 1 or monitor_num > len(origins):
                return f"Monitor {monitor_num} não encontrado. Você tem {len(origins)} monitor(es)."
            mx, my = origins[monitor_num - 1]
            wins = gw.getWindowsWithTitle(window_name)
            if not wins:
                titles = [t for t in gw.getAllTitles() if window_name.lower() in t.lower()]
                if titles:
                    wins = gw.getWindowsWithTitle(titles[0])
            if not wins:
                return f"Janela '{window_name}' não encontrada."
            w = wins[0]
            if w.isMinimized:
                w.restore()
            w.moveTo(mx + 40, my + 40)
            return f"'{w.title}' movida para Monitor {monitor_num}."
        except ImportError:
            return "Instala pygetwindow para mover janelas entre monitores."
        except Exception as e:
            return f"Erro ao mover janela: {e}"

    def set_display_mode(self, mode: str) -> str:
        """Controla como os monitores são usados (estender, duplicar, etc.)."""
        modes = {
            "estender":        "/extend",
            "duplicar":        "/clone",
            "só segundo":      "/external",
            "só primeiro":     "/internal",
            "segundo monitor": "/external",
            "primeiro monitor": "/internal",
            "clone":           "/clone",
            "extend":          "/extend",
        }
        flag = None
        for key, val in modes.items():
            if key in mode.lower():
                flag = val
                break
        if not flag:
            flag = "/extend"
        try:
            subprocess.Popen(["DisplaySwitch.exe", flag])
            return f"Modo de exibição: {mode}."
        except Exception as e:
            return f"Erro ao mudar modo de exibição: {e}"

    def change_resolution(self, width: int, height: int) -> str:
        """Muda resolução via ChangeDisplaySettings (ctypes, sem deps extras)."""
        try:
            import ctypes
            DM_PELSWIDTH  = 0x00080000
            DM_PELSHEIGHT = 0x00100000
            ENUM_CURRENT_SETTINGS = -1

            class DEVMODE(ctypes.Structure):
                _fields_ = [
                    ("dmDeviceName",        ctypes.c_wchar * 32),
                    ("dmSpecVersion",        ctypes.c_ushort),
                    ("dmDriverVersion",      ctypes.c_ushort),
                    ("dmSize",               ctypes.c_ushort),
                    ("dmDriverExtra",        ctypes.c_ushort),
                    ("dmFields",             ctypes.c_ulong),
                    ("dmPositionX",          ctypes.c_long),
                    ("dmPositionY",          ctypes.c_long),
                    ("dmDisplayOrientation", ctypes.c_ulong),
                    ("dmDisplayFixedOutput", ctypes.c_ulong),
                    ("dmColor",              ctypes.c_short),
                    ("dmDuplex",             ctypes.c_short),
                    ("dmYResolution",        ctypes.c_short),
                    ("dmTTOption",           ctypes.c_short),
                    ("dmCollate",            ctypes.c_short),
                    ("dmFormName",           ctypes.c_wchar * 32),
                    ("dmLogPixels",          ctypes.c_ushort),
                    ("dmBitsPerPel",         ctypes.c_ulong),
                    ("dmPelsWidth",          ctypes.c_ulong),
                    ("dmPelsHeight",         ctypes.c_ulong),
                    ("dmDisplayFlags",       ctypes.c_ulong),
                    ("dmDisplayFrequency",   ctypes.c_ulong),
                ]

            dm = DEVMODE()
            dm.dmSize = ctypes.sizeof(DEVMODE)
            ctypes.windll.user32.EnumDisplaySettingsW(None, ENUM_CURRENT_SETTINGS, ctypes.byref(dm))
            dm.dmPelsWidth  = width
            dm.dmPelsHeight = height
            dm.dmFields     = DM_PELSWIDTH | DM_PELSHEIGHT
            result = ctypes.windll.user32.ChangeDisplaySettingsW(ctypes.byref(dm), 0)
            if result == 0:
                return f"Resolução alterada para {width}x{height}."
            return f"Resolução {width}x{height} não suportada pelo monitor (código {result})."
        except Exception as e:
            return f"Erro ao mudar resolução: {e}"

    # ─── Limpeza ──────────────────────────────────────────────────────────────
    def empty_recycle_bin(self) -> str:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Clear-RecycleBin -Force -ErrorAction SilentlyContinue; Write-Output 'OK'"],
            capture_output=True, text=True, timeout=15,
        )
        if "OK" in result.stdout:
            return "Lixeira esvaziada."
        return "Não consegui esvaziar a lixeira."

    def clean_temp(self) -> str:
        script = r"""
        $paths = @($env:TEMP, $env:TMP, "C:\Windows\Temp")
        $count = 0
        foreach ($p in $paths) {
            if (Test-Path $p) {
                $files = Get-ChildItem $p -Recurse -Force -ErrorAction SilentlyContinue
                foreach ($f in $files) {
                    try { Remove-Item $f.FullName -Force -Recurse -ErrorAction Stop; $count++ }
                    catch {}
                }
            }
        }
        Write-Output "$count"
        """
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=30,
        )
        n = result.stdout.strip()
        return f"Limpeza de temp concluída. {n} arquivo(s) removido(s)." if n.isdigit() else "Limpeza de temp concluída."

    def get_disk_usage(self) -> str:
        script = (
            "Get-PSDrive -PSProvider FileSystem | "
            "Select-Object Name, @{N='Used(GB)';E={[math]::Round($_.Used/1GB,1)}}, "
            "@{N='Free(GB)';E={[math]::Round($_.Free/1GB,1)}} | "
            "Format-Table -AutoSize | Out-String"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() or "Não foi possível obter informações de disco."

    # ─── Serviços Windows ─────────────────────────────────────────────────────
    def manage_service(self, name: str, action: str) -> str:
        """action: start | stop | restart | status"""
        action = action.lower().strip()
        if action in ("start", "iniciar", "ligar"):
            cmd = f"Start-Service -Name '{name}' -ErrorAction Stop"
            ok_msg = f"Serviço '{name}' iniciado."
        elif action in ("stop", "parar", "desligar"):
            cmd = f"Stop-Service -Name '{name}' -Force -ErrorAction Stop"
            ok_msg = f"Serviço '{name}' parado."
        elif action in ("restart", "reiniciar"):
            cmd = f"Restart-Service -Name '{name}' -Force -ErrorAction Stop"
            ok_msg = f"Serviço '{name}' reiniciado."
        else:
            cmd = f"Get-Service -Name '*{name}*' | Select-Object Name, Status, DisplayName | Format-Table -AutoSize | Out-String"
            ok_msg = None

        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=15,
        )
        if ok_msg and result.returncode == 0:
            return ok_msg
        if ok_msg:
            return f"Erro ao {action} '{name}': {(result.stderr or result.stdout).strip()[:200]}"
        return result.stdout.strip() or f"Serviço '{name}' não encontrado."

    def list_services(self, filter_running: bool = True) -> str:
        where = "Where-Object { $_.Status -eq 'Running' }" if filter_running else "Where-Object { $_ }"
        script = (
            f"Get-Service | {where} | "
            "Select-Object Name, DisplayName, Status | "
            "Sort-Object DisplayName | "
            "Format-Table -AutoSize | Out-String"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=10,
        )
        out = result.stdout.strip()
        return out[:800] if out else "Não foi possível listar os serviços."

    # ─── Tarefas agendadas ────────────────────────────────────────────────────
    def create_scheduled_task(self, name: str, time_str: str, command: str) -> str:
        """Cria tarefa agendada. time_str no formato HH:MM."""
        safe_name    = re.sub(r"[^\w\-]", "_", name)
        safe_command = command.replace("'", "''")
        script = (
            f"$action  = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-Command \"{safe_command}\"'; "
            f"$trigger = New-ScheduledTaskTrigger -Daily -At '{time_str}'; "
            f"Register-ScheduledTask -TaskName '{safe_name}' -Action $action -Trigger $trigger -Force | Out-Null; "
            f"Write-Output 'OK'"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=15,
        )
        if "OK" in result.stdout:
            return f"Tarefa '{name}' agendada para {time_str}."
        return f"Erro ao criar tarefa: {(result.stderr or '').strip()[:200]}"

    def list_scheduled_tasks(self) -> str:
        script = (
            "Get-ScheduledTask | Where-Object { $_.TaskPath -eq '\\' } | "
            "Select-Object TaskName, State | Format-Table -AutoSize | Out-String"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip()[:600] or "Nenhuma tarefa agendada personalizada."

    def delete_scheduled_task(self, name: str) -> str:
        safe = re.sub(r"[^\w\-]", "_", name)
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Unregister-ScheduledTask -TaskName '{safe}' -Confirm:$false; Write-Output 'OK'"],
            capture_output=True, text=True, timeout=10,
        )
        if "OK" in result.stdout:
            return f"Tarefa '{name}' removida."
        return f"Não encontrei a tarefa '{name}'."

    # ─── Bateria ──────────────────────────────────────────────────────────────
    def battery_status(self) -> str:
        try:
            import psutil
            batt = psutil.sensors_battery()
            if not batt:
                return "Sem bateria (PC de mesa ou não suportado)."
            charging = "carregando" if batt.power_plugged else "na bateria"
            return f"Bateria: {batt.percent:.0f}% ({charging})."
        except Exception as e:
            return f"Erro ao verificar bateria: {e}"

    # ─── Comando composto ─────────────────────────────────────────────────────
    def _exec_action(self, action_text: str) -> str:
        """Executa a segunda parte de um comando composto após abrir um app."""
        import time as _t
        _t.sleep(2.5)
        a = action_text.strip()

        m = re.match(r"(?:digita|escreve|escreva|digite|cola|coloca)\s+(.+)", a)
        if m:
            typed = m.group(1).strip()
            for ctx in [" dentro", " lá", " ali", " nisso", " aí", " nele", " nela"]:
                if typed.endswith(ctx):
                    typed = typed[: -len(ctx)].strip()
            return self.type_text(typed)

        m = re.match(r"(?:pesquisa|busca|procura)\s+(.+)", a)
        if m:
            return self.search_google(m.group(1).strip())

        m = re.match(r"(?:vai\s+para?|acessa|abre|navega\s+para?)\s+(.+)", a)
        if m:
            dest = m.group(1).strip()
            for name, url in sorted(SITE_MAP.items(), key=lambda x: len(x[0]), reverse=True):
                if name in dest:
                    return self.open_url(url)
            if "." in dest:
                return self.open_url(dest)

        return ""

    # ─── Parser de intenção ───────────────────────────────────────────────────
    def try_handle(self, text: str) -> str | None:
        t = text.lower()

        # ── Comando composto: "abre X e AÇÃO Y" ──────────────────────────────
        m = re.search(
            r"(?:abr[ae](?:i|ir)?|abre)(?:\s+[oa]s?)?\s+([\w\s\+]+?)\s+e\s+"
            r"((?:digita|escreve|escreva|digite|cola|pesquisa|busca|vai\s+para?|acessa|navega)\s+.+?)$",
            t,
        )
        if m:
            app_part    = m.group(1).strip()
            action_part = m.group(2).strip()
            for filler in [" pra mim", " para mim", " pra você", " agora"]:
                if app_part.endswith(filler):
                    app_part = app_part[: -len(filler)].strip()
            r1 = self.open_app(app_part)
            r2 = self._exec_action(action_part)
            return f"{r1} {r2}".strip()

        # ── Wi-Fi ─────────────────────────────────────────────────────────────
        if any(p in t for p in ["liga o wifi", "liga o wi-fi", "ativa o wifi", "ligar o wifi", "ativa wifi"]):
            return self.wifi_on()
        if any(p in t for p in ["desliga o wifi", "desliga o wi-fi", "desativa o wifi", "desligar wifi"]):
            return self.wifi_off()
        if any(p in t for p in ["lista as redes", "redes wifi", "redes wi-fi", "redes disponíveis",
                                  "quais redes", "mostrar redes"]):
            return self.list_wifi()
        if any(p in t for p in ["status do wifi", "status do wi-fi", "wifi está conectado",
                                  "qual rede estou", "rede que estou"]):
            return self.wifi_status()
        m = re.search(r"(?:conecta|conectar|liga)\s+(?:no|na|ao|a)\s+(?:wifi|wi-fi)\s+(.+)", t)
        if m:
            return self.connect_wifi(m.group(1).strip())

        # ── Bluetooth ─────────────────────────────────────────────────────────
        if any(p in t for p in ["liga o bluetooth", "ativa o bluetooth", "ligar bluetooth",
                                  "ativa bluetooth", "liga bluetooth"]):
            return self.bluetooth_on()
        if any(p in t for p in ["desliga o bluetooth", "desativa o bluetooth", "desligar bluetooth"]):
            return self.bluetooth_off()
        if any(p in t for p in ["dispositivos bluetooth", "lista bluetooth", "quais bluetooth"]):
            return self.list_bluetooth_devices()

        # ── Info do sistema ───────────────────────────────────────────────────
        if any(p in t for p in ["como tá o pc", "como está o pc", "status do pc", "info do sistema",
                                  "uso do sistema", "quanto de cpu", "quanto de ram",
                                  "uso de memória", "uso de cpu", "desempenho do pc",
                                  "memória ram", "uso de disco"]):
            return self.system_info()
        if any(p in t for p in ["bateria", "carga do notebook", "quanto de bateria"]):
            return self.battery_status()
        if any(p in t for p in ["resolução da tela", "tamanho da tela", "resolução do monitor"]):
            return self.screen_info()

        # ── Modo de energia ───────────────────────────────────────────────────
        if any(p in t for p in ["modo de alta performance", "alto desempenho", "modo performance",
                                  "modo gaming", "máximo desempenho", "modo turbo"]):
            return self.set_power_mode("alto desempenho")
        if any(p in t for p in ["modo balanceado", "modo normal", "modo equilibrado", "balanço de energia"]):
            return self.set_power_mode("balanceado")
        if any(p in t for p in ["modo de economia", "economiza energia", "modo econômico",
                                  "economizar bateria", "modo sleep de energia"]):
            return self.set_power_mode("economia")
        if any(p in t for p in ["qual modo de energia", "modo de energia atual", "plano de energia"]):
            return self.get_power_mode()

        # ── Dark mode / Night light ───────────────────────────────────────────
        if any(p in t for p in ["modo escuro", "dark mode", "ativa o dark mode", "tema escuro",
                                  "ativa o tema escuro", "coloca o tema escuro"]):
            return self.toggle_dark_mode(force_dark=True)
        if any(p in t for p in ["modo claro", "light mode", "tema claro", "desativa o dark mode",
                                  "ativa o tema claro", "coloca o tema claro"]):
            return self.toggle_dark_mode(force_dark=False)
        if any(p in t for p in ["alterna o tema", "troca o tema", "inverte o tema"]):
            return self.toggle_dark_mode()
        if any(p in t for p in ["night light", "luz noturna", "filtro de cor azul",
                                  "proteção ocular", "filtro noturno"]):
            return self.toggle_night_light()

        # ── Janelas ───────────────────────────────────────────────────────────
        if any(p in t for p in ["quais janelas", "janelas abertas", "lista as janelas", "o que tá aberto"]):
            return self.list_windows()
        if any(p in t for p in ["quais programas", "lista os processos", "o que está rodando",
                                  "programas abertos", "apps abertos", "processos rodando"]):
            return self.list_processes()
        for kw in ["foca no", "foca na", "traz o", "traz a", "vai para a janela do"]:
            if kw in t:
                name = t.split(kw, 1)[-1].strip().rstrip("., ")
                if name:
                    return self.focus_window(name)
        if any(p in t for p in ["minimiza a janela", "minimiza tudo", "minimizar janela", "minimiza ela"]):
            return self.minimize_window()
        if any(p in t for p in ["maximiza a janela", "maximiza tudo", "maximizar janela", "maximiza ela"]):
            return self.maximize_window()

        # ── Mouse ─────────────────────────────────────────────────────────────
        if any(p in t for p in ["rola pra baixo", "rola para baixo", "desce a página", "scroll down"]):
            return self.scroll("down")
        if any(p in t for p in ["rola pra cima", "rola para cima", "sobe a página", "scroll up"]):
            return self.scroll("up")
        m = re.search(r"(?:double\s+click|duplo\s+clique|clica\s+duas\s+vezes)\s+(?:em\s+)?(\d+)\s*[,x]\s*(\d+)", t)
        if m:
            return self.double_click(int(m.group(1)), int(m.group(2)))
        if any(p in t for p in ["double click", "duplo clique", "clica duas vezes"]):
            return self.double_click()
        if any(p in t for p in ["botão direito", "right click", "clique direito", "clica com o direito"]):
            m2 = re.search(r"(\d+)\s*[,x]\s*(\d+)", t)
            if m2:
                return self.right_click(int(m2.group(1)), int(m2.group(2)))
            return self.right_click()
        m = re.search(r"(?:clica|click)\s+(?:em\s+)?(\d+)\s*[,x]\s*(\d+)", t)
        if m:
            return self.mouse_click(int(m.group(1)), int(m.group(2)))
        if any(p in t for p in ["clica aqui", "clique aqui", "dá um clique"]):
            return self.mouse_click()
        m = re.search(r"arrasta\s+(?:de\s+)?(\d+)\s*[,x]\s*(\d+)\s+(?:para?|até)\s+(\d+)\s*[,x]\s*(\d+)", t)
        if m:
            return self.drag(int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)))
        if any(p in t for p in ["onde está o mouse", "posição do mouse", "onde tá o cursor"]):
            return self.get_mouse_pos()

        # ── Volume ────────────────────────────────────────────────────────────
        m = re.search(r"volume\s*(?:para|em|a|pro)?\s*(\d+)", t)
        if m:
            return self.set_volume(int(m.group(1)))
        if any(p in t for p in ["aumenta o volume", "sobe o volume", "volume mais alto", "mais volume"]):
            return self.set_volume(min(100, self.get_volume() + 10))
        if any(p in t for p in ["diminui o volume", "baixa o volume", "abaixa o volume", "menos volume"]):
            return self.set_volume(max(0, self.get_volume() - 10))
        if any(p in t for p in ["muta", "sem som", "silencia o pc", "tira o som"]):
            return self.mute()
        if any(p in t for p in ["desmuta", "tira o mudo", "coloca o som de volta", "tira o mute"]):
            return self.unmute()

        # ── Brilho ────────────────────────────────────────────────────────────
        m = re.search(r"brilho\s*(?:para|em|a|pro)?\s*(\d+)", t)
        if m:
            return self.set_brightness(int(m.group(1)))
        if any(p in t for p in ["aumenta o brilho", "mais brilho", "brilho mais alto"]):
            return self.set_brightness(80)
        if any(p in t for p in ["diminui o brilho", "menos brilho", "brilho mais baixo"]):
            return self.set_brightness(30)

        # ── Fechar processo ───────────────────────────────────────────────────
        for kw in ["fecha o", "fecha a", "fecha", "mata o processo", "kill", "fechar o", "fechar a"]:
            if kw in t:
                app = t.split(kw, 1)[-1].strip().rstrip("., ")
                if app and len(app) > 1:
                    return self.close_app(app)

        # ── Automação de tela ────────────────────────────────────────────────────
        for kw in ["clica no botão", "clica em", "clique no", "clique em", "aperta o botão",
                   "aperta o", "clica no texto"]:
            if kw in t:
                target = t.split(kw, 1)[-1].strip().rstrip(".,! ")
                if target:
                    return self.click_on_text(target)
        for kw in ["digita no campo", "escreve no campo", "preenche o campo"]:
            if kw in t:
                parts = t.split(kw, 1)[-1].strip()
                # "campo X com Y" ou "campo X: Y"
                m2 = re.search(r"(.+?)\s+(?:com|:)\s+(.+)", parts)
                if m2:
                    return self.type_in_field(m2.group(1).strip(), m2.group(2).strip())
        if any(p in t for p in ["pesquisa na página", "ctrl f", "busca na página",
                                  "acha na página", "localiza na página"]):
            m2 = re.search(r"(?:pesquisa|busca|acha|localiza)\s+(?:na\s+página\s+)?(.+)", t)
            if m2:
                return self.search_on_screen(m2.group(1).strip())

        # ── Streaming search ─────────────────────────────────────────────────
        m = re.search(
            r"(?:busca|pesquisa|procura|coloca|abre|toca)\s+"
            r"(.+?)\s+(?:no|na|em)\s+(netflix|max|hbo|disney|prime|youtube|twitch|crunchyroll)",
            t,
        )
        if m:
            return self.search_streaming(m.group(2), m.group(1).strip())
        m = re.search(
            r"(?:no|na)\s+(netflix|max|hbo|disney|prime\s+video|youtube|twitch|crunchyroll)"
            r"\s+(?:busca|pesquisa|procura|coloca|abre)\s+(.+)",
            t,
        )
        if m:
            return self.search_streaming(m.group(1), m.group(2).strip())

        # ── Monitores ─────────────────────────────────────────────────────────
        if any(p in t for p in ["quais monitores", "lista os monitores", "monitores conectados",
                                  "quantos monitores"]):
            return self.list_monitors()
        m = re.search(r"(?:move|mover|leva|manda)\s+(?:a\s+janela\s+)?(.+?)\s+(?:pro|para\s+o)\s+monitor\s+(\d+)", t)
        if m:
            return self.move_window_to_monitor(m.group(1).strip(), int(m.group(2)))
        if any(p in t for p in ["estender monitores", "estende os monitores", "modo estender"]):
            return self.set_display_mode("estender")
        if any(p in t for p in ["duplicar monitores", "duplica os monitores", "modo duplicar"]):
            return self.set_display_mode("duplicar")
        if any(p in t for p in ["só o segundo monitor", "apenas segundo monitor", "só segundo"]):
            return self.set_display_mode("só segundo")
        if any(p in t for p in ["só o primeiro monitor", "apenas primeiro monitor", "só primeiro"]):
            return self.set_display_mode("só primeiro")
        m = re.search(r"resolução\s+(?:para\s+)?(\d{3,4})\s*[xX×]\s*(\d{3,4})", t)
        if m:
            return self.change_resolution(int(m.group(1)), int(m.group(2)))

        # ── Limpeza ───────────────────────────────────────────────────────────
        if any(p in t for p in ["esvazia a lixeira", "limpa a lixeira", "esvaziar lixeira",
                                  "limpar lixeira", "vazia a lixeira"]):
            return self.empty_recycle_bin()
        if any(p in t for p in ["limpa os temporários", "limpar temp", "apaga os temporários",
                                  "limpa o temp", "limpar arquivos temporários"]):
            return self.clean_temp()
        if any(p in t for p in ["espaço em disco", "uso do disco", "quanto tem no disco",
                                  "tamanho dos drives"]):
            return self.get_disk_usage()

        # ── Serviços Windows ──────────────────────────────────────────────────
        if any(p in t for p in ["serviços rodando", "lista os serviços", "quais serviços estão rodando"]):
            return self.list_services()
        for kw in ["status do serviço", "informação do serviço", "info do serviço"]:
            if kw in t:
                name = t.split(kw, 1)[-1].strip().rstrip(".,! ")
                if name:
                    return self.manage_service(name, "status")
        m = re.search(r"(inicia|para|reinicia|start|stop|restart)\s+o\s+servi[çc]o\s+(.+)", t)
        if m:
            action_kw, svc = m.group(1), m.group(2).strip().rstrip(".,! ")
            action = "start" if action_kw in ("inicia","start") else ("stop" if action_kw in ("para","stop") else "restart")
            return self.manage_service(svc, action)

        # ── Tarefas agendadas ─────────────────────────────────────────────────
        if any(p in t for p in ["lista as tarefas", "tarefas agendadas", "quais tarefas agendadas"]):
            return self.list_scheduled_tasks()
        m = re.search(r"(?:cria|agenda)\s+(?:uma\s+)?tarefa\s+(.+?)\s+às\s+(\d{1,2}:\d{2})\s+(?:para\s+|pra\s+)?(.+)", t)
        if m:
            return self.create_scheduled_task(m.group(1).strip(), m.group(2), m.group(3).strip())
        for kw in ["remove a tarefa", "deleta a tarefa", "cancela a tarefa agendada"]:
            if kw in t:
                name = t.split(kw, 1)[-1].strip().rstrip(".,! ")
                if name:
                    return self.delete_scheduled_task(name)

        # ── Ejetar USB ────────────────────────────────────────────────────────
        if any(p in t for p in ["ejeta", "ejetar", "remover com segurança"]):
            m = re.search(r"([a-zA-Z]):", t)
            drive = m.group(0) if m else None
            return self.eject_usb(drive)

        # ── Terminal ──────────────────────────────────────────────────────────
        for kw in ["roda o comando", "executa o comando", "roda no terminal", "executa no terminal",
                   "abre o terminal e roda", "abre o terminal e executa"]:
            if kw in t:
                cmd = t.split(kw, 1)[-1].strip()
                if cmd:
                    return self.run_command(cmd)
        m = re.search(r"(?:executa|roda)\s+(?:o\s+script\s+|o\s+arquivo\s+)?(.+\.(?:py|ps1|bat|sh|exe))", t)
        if m:
            return self.run_command(m.group(1).strip())

        # ── Arquivos ──────────────────────────────────────────────────────────
        for kw in ["busca o arquivo", "procura o arquivo", "encontra o arquivo",
                   "onde está o arquivo", "onde fica o arquivo", "acha o arquivo"]:
            if kw in t:
                name = t.split(kw, 1)[-1].strip().rstrip("., ")
                if name:
                    return self.find_file(name)
        m = re.search(r"abre\s+o\s+arquivo\s+(.+)", t)
        if m:
            return self.open_file(m.group(1).strip())
        for kw in ["cria o arquivo", "cria um arquivo", "cria arquivo", "novo arquivo chamado"]:
            if kw in t:
                name = t.split(kw, 1)[-1].strip().rstrip("., ")
                if name:
                    return self.create_file(name)
        for kw in ["cria a pasta", "cria uma pasta", "cria pasta", "nova pasta chamada"]:
            if kw in t:
                name = t.split(kw, 1)[-1].strip().rstrip("., ")
                if name:
                    return self.create_folder(name)
        for kw in ["deleta o arquivo", "apaga o arquivo", "remove o arquivo", "deleta arquivo"]:
            if kw in t:
                name = t.split(kw, 1)[-1].strip().rstrip("., ")
                if name:
                    return self.delete_file(name)
        for kw in ["lista o conteúdo da pasta", "lista a pasta", "o que tem na pasta",
                   "conteúdo da pasta", "o que tem em"]:
            if kw in t:
                folder = t.split(kw, 1)[-1].strip().rstrip("., ")
                if folder:
                    path = FOLDER_MAP.get(folder.lower(), folder)
                    return self.list_folder_contents(path)

        # ── Pesquisa Google ───────────────────────────────────────────────────
        for kw in ["pesquisa no google", "busca no google", "procura no google",
                   "pesquisa google", "pesquisa sobre", "busca sobre"]:
            if kw in t:
                query = t.split(kw, 1)[-1].strip().strip("?.,!")
                if query:
                    return self.search_google(query)

        # ── Pesquisa YouTube ──────────────────────────────────────────────────
        for kw in ["pesquisa no youtube", "busca no youtube", "procura no youtube",
                   "pesquisa youtube", "busca youtube"]:
            if kw in t:
                query = t.split(kw, 1)[-1].strip().strip("?.,!")
                if query:
                    return self.search_youtube(query)

        # ── Abrir pasta ───────────────────────────────────────────────────────
        for kw in ["abre a pasta", "abra a pasta", "vai para a pasta", "mostra a pasta",
                   "vai pra pasta", "abre os"]:
            if kw in t:
                remainder = t.split(kw, 1)[-1].strip()
                for key in sorted(FOLDER_MAP.keys(), key=len, reverse=True):
                    if key in remainder or remainder.startswith(key):
                        return self.open_folder(key)
                folder_result = self.open_folder(remainder)
                if "Não conheço" not in folder_result:
                    return folder_result

        # ── Abrir site pelo nome ──────────────────────────────────────────────
        for site_kw in ["coloca no", "vai pro", "vai para o", "vai para a",
                         "abre o", "abre a", "coloca o", "coloca a", "acessa o", "acessa a"]:
            if site_kw in t:
                remainder = t.split(site_kw, 1)[-1].strip().rstrip("., ")
                for site_name, url in sorted(SITE_MAP.items(), key=lambda x: len(x[0]), reverse=True):
                    if site_name in remainder:
                        return self.open_url(url)

        # ── Abrir app ─────────────────────────────────────────────────────────
        for kw in ["abra o", "abra a", "abra", "abre o", "abre a", "abre",
                   "abrir o", "abrir a", "abrir", "lança", "abre uma aba no",
                   "abra uma aba no"]:
            if kw in t:
                remainder = t.split(kw, 1)[-1].strip()
                for strip_suffix in [" e coloca", " e coloque", " e vai", " e acessa",
                                      " e digita", " e escreve", " e pesquisa",
                                      " pra mim", " para mim"]:
                    if strip_suffix in remainder:
                        remainder = remainder.split(strip_suffix, 1)[0].strip()
                app_name = remainder
                for key in sorted(APP_MAP.keys(), key=len, reverse=True):
                    if remainder.startswith(key):
                        app_name = key
                        break
                return self.open_app(app_name)

        # ── Atalhos de teclado ────────────────────────────────────────────────
        for name, shortcut in SHORTCUT_MAP.items():
            if name in t:
                return self.send_shortcut(shortcut)

        # ── Digitar texto ─────────────────────────────────────────────────────
        m = re.search(r"(?:digita|escreve)\s+(.+)", t)
        if m:
            return self.type_text(m.group(1))

        # ── Clipboard ─────────────────────────────────────────────────────────
        if any(p in t for p in ["o que tem no clipboard", "lê o clipboard", "o que está no clipboard",
                                  "me mostra o clipboard", "conteúdo do clipboard"]):
            return self.get_clipboard()
        if any(p in t for p in ["lê o que tem no clipboard", "fala o clipboard", "lê o clipboard em voz",
                                  "lê o que está no clipboard", "fala o que tem no clipboard"]):
            return self.read_clipboard_aloud()
        if any(p in t for p in ["histórico do clipboard", "histórico de clipboard",
                                  "clipboard history", "win+v", "abre o clipboard history"]):
            return self.open_clipboard_history()
        m = re.search(r"copia\s+(?:isso|o texto)?\s*[:\-]?\s*(.+)", t)
        if m:
            return self.set_clipboard(m.group(1).strip())

        # ── URLs diretas ──────────────────────────────────────────────────────
        for kw in ["abre o site", "abre a página", "abre o link", "acessa o site"]:
            if kw in t:
                remainder = t.split(kw, 1)[-1].strip()
                if "." in remainder:
                    return self.open_url(remainder)
        m = re.search(r"abre\s+(?:o\s+site\s+|a\s+página\s+|o\s+link\s+)?([\w./-]+\.\w{2,})", t)
        if m:
            return self.open_url(m.group(1))

        # ── Sistema ───────────────────────────────────────────────────────────
        if any(p in t for p in ["dorme o pc", "modo sleep", "suspende o pc",
                                  "coloca o pc pra dormir", "pc pra dormir"]):
            return self.sleep_pc()
        if any(p in t for p in ["bloqueia o pc", "trava o pc", "bloqueia a tela", "trava a tela"]):
            return self.lock_pc()
        if any(p in t for p in ["reinicia o pc", "restart", "reiniciar o pc", "reinicia o computador"]):
            return self.restart()
        if any(p in t for p in ["desliga o pc", "shutdown", "desligar o pc", "desliga o computador"]):
            return self.shutdown()
        if any(p in t for p in ["cancela o desligamento", "cancela o shutdown", "não desliga"]):
            return self.cancel_shutdown()

        # ── Configurações Win 11 ──────────────────────────────────────────────
        for kw in ["abre as configurações de", "vai para as configurações de",
                   "abre configurações de", "configurações de"]:
            if kw in t:
                setting = t.split(kw, 1)[-1].strip().rstrip(".,! ")
                # Busca no APP_MAP por "configurações de X"
                for key, val in APP_MAP.items():
                    if setting in key and "ms-settings" in val:
                        return self.open_app(key)
                # Abre configurações genéricas
                return self.open_app("configurações")

        # ── Screenshot ────────────────────────────────────────────────────────
        if any(p in t for p in ["tira um print", "screenshot", "print da tela",
                                  "tira uma foto da tela", "salva a tela", "captura e salva"]):
            return self.take_screenshot()

        # ── Microfone ─────────────────────────────────────────────────────────
        if any(p in t for p in ["muta o microfone", "desativa o microfone", "silencia o mic",
                                  "muta o mic", "desliga o microfone"]):
            return self.mute_microphone()
        if any(p in t for p in ["ativa o microfone", "desmuta o microfone", "liga o microfone",
                                  "desmuta o mic", "ativa o mic"]):
            return self.unmute_microphone()

        # ── Night Light ───────────────────────────────────────────────────────
        if any(p in t for p in ["ativa o night light", "liga o night light", "modo noturno",
                                  "ativa luz noturna", "liga luz noturna", "protect eyes",
                                  "modo escuro de tela", "ativa proteção de olhos"]):
            return self.night_light_on()
        if any(p in t for p in ["desativa o night light", "desliga o night light",
                                  "desativa luz noturna", "desliga luz noturna"]):
            return self.night_light_off()

        # ── Ditado ────────────────────────────────────────────────────────────
        if any(p in t for p in ["modo ditado", "ativa ditado", "começa a ditar",
                                  "ditado por voz", "win+h", "digita o que eu falar"]):
            return self.start_dictation()

        # ── Always on top ─────────────────────────────────────────────────────
        if any(p in t for p in ["fixa a janela no topo", "sempre no topo", "pin no topo",
                                  "mantém a janela no topo", "coloca sempre no topo"]):
            return self.set_window_always_on_top()
        if any(p in t for p in ["tira do topo", "remove do topo", "desfaz o topo",
                                  "não fica mais no topo"]):
            return self.unset_window_always_on_top()

        # ── Notificação ───────────────────────────────────────────────────────
        m = re.search(r"manda uma notificação\s+(?:dizendo\s+)?[:\-]?\s*(.+)", t)
        if m:
            return self.show_notification("Keilinks", m.group(1).strip())

        return None
