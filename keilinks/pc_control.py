"""
Controle completo do PC por voz.
Volume, brilho, apps, processos, teclado, clipboard, URLs, sistema.
"""

import os
import re
import shutil
import subprocess
import webbrowser

try:
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    _HAS_PYCAW = True
except ImportError:
    _HAS_PYCAW = False


# ─── Apps conhecidos ──────────────────────────────────────────────────────────
APP_MAP = {
    "spotify":               "spotify",
    "chrome":                "chrome",
    "google":                "chrome",
    "navegador":             "chrome",
    "firefox":               "firefox",
    "notepad":               "notepad",
    "bloco de notas":        "notepad",
    "calculadora":           "calc",
    "discord":               "discord",
    "vscode":                "code",
    "visual studio code":    "code",
    "vs code":               "code",
    "steam":                 "steam",
    "explorador":            "explorer",
    "arquivos":              "explorer",
    "gerenciador de tarefas": "taskmgr",
    "task manager":          "taskmgr",
    "word":                  "winword",
    "excel":                 "excel",
    "obs":                   "obs64",
    "terminal":              "wt",
    "powershell":            "powershell",
    "cmd":                   "cmd",
    "paint":                 "mspaint",
    "whatsapp":              "whatsapp",
}

# ─── Atalhos de teclado conhecidos ────────────────────────────────────────────
SHORTCUT_MAP = {
    "copiar":          "ctrl+c",
    "colar":           "ctrl+v",
    "recortar":        "ctrl+x",
    "desfazer":        "ctrl+z",
    "refazer":         "ctrl+y",
    "salvar":          "ctrl+s",
    "selecionar tudo": "ctrl+a",
    "fechar aba":      "ctrl+w",
    "nova aba":        "ctrl+t",
    "print screen":    "printscreen",
    "alt f4":          "alt+f4",
    "minimizar":       "win+down",
    "maximizar":       "win+up",
    "área de trabalho": "win+d",
}


class PCControl:
    def __init__(self):
        self._vol = None
        self._init_volume()

    def _init_volume(self):
        if not _HAS_PYCAW:
            self._vol = None
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

    # ─── Apps ─────────────────────────────────────────────────────────────────
    def open_app(self, raw_name: str) -> str:
        name = raw_name.lower().strip()
        # Tenta match exato primeiro, depois parcial
        cmd = APP_MAP.get(name)
        if not cmd:
            for key, val in APP_MAP.items():
                if key in name or name in key:
                    cmd = val
                    break
        if not cmd:
            return f"Não conheço o app '{raw_name}'. Adiciona ele no meu APP_MAP."

        # Resolve o executável sem shell=True (previne injeção de comando)
        exe = shutil.which(cmd)
        if not exe:
            exe = cmd  # tenta o nome direto (Windows resolve alguns como 'calc')

        try:
            subprocess.Popen([exe])
            return f"{raw_name.capitalize()} aberto."
        except Exception as e:
            return f"Não consegui abrir {raw_name}: {e}"

    def close_app(self, name: str) -> str:
        try:
            import psutil
            name_lower = name.lower().strip()
            killed = []
            for proc in psutil.process_iter(["name", "pid"]):
                if name_lower in proc.info["name"].lower():
                    proc.kill()
                    killed.append(proc.info["name"])
            if killed:
                return f"Fechei: {', '.join(set(killed))}."
            return f"Não encontrei nenhum processo com '{name}' rodando."
        except ImportError:
            return "Instala psutil para fechar processos por nome."
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

    # ─── Clipboard ────────────────────────────────────────────────────────────
    def get_clipboard(self) -> str:
        try:
            import pyperclip
            text = pyperclip.paste()
            return f"Clipboard: {text[:200]}" if text else "Clipboard vazio."
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

    # ─── Parser de intenção ───────────────────────────────────────────────────
    def try_handle(self, text: str) -> str | None:
        t = text.lower()

        # ── Volume ────────────────────────────────────────────────────────────
        m = re.search(r"volume\s*(?:para|em|a|pro|em)?\s*(\d+)", t)
        if m:
            return self.set_volume(int(m.group(1)))
        if any(p in t for p in ["aumenta o volume", "sobe o volume", "volume mais alto"]):
            return self.set_volume(min(100, self.get_volume() + 10))
        if any(p in t for p in ["diminui o volume", "baixa o volume", "abaixa o volume", "volume mais baixo"]):
            return self.set_volume(max(0, self.get_volume() - 10))
        if any(p in t for p in ["muta", "sem som", "silencia o pc"]):
            return self.mute()
        if any(p in t for p in ["desmuta", "tira o mudo", "coloca o som de volta"]):
            return self.unmute()

        # ── Brilho ────────────────────────────────────────────────────────────
        m = re.search(r"brilho\s*(?:para|em|a|pro)?\s*(\d+)", t)
        if m:
            return self.set_brightness(int(m.group(1)))
        if any(p in t for p in ["aumenta o brilho", "mais brilho"]):
            return self.set_brightness(80)
        if any(p in t for p in ["diminui o brilho", "menos brilho"]):
            return self.set_brightness(30)

        # ── Fechar processo ───────────────────────────────────────────────────
        for kw in ["fecha o", "fecha a", "fecha", "mata o processo", "kill"]:
            if kw in t:
                app = t.split(kw, 1)[-1].strip()
                if app:
                    return self.close_app(app)

        # ── Abrir app ─────────────────────────────────────────────────────────
        for kw in ["abre o", "abre a", "abre", "abrir o", "abrir a", "abrir", "lança"]:
            if kw in t:
                remainder = t.split(kw, 1)[-1].strip()
                # Tenta match multi-palavra contra APP_MAP
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
        m = re.search(r"digita\s+(.+)", t)
        if m:
            return self.type_text(m.group(1))

        # ── Clipboard ─────────────────────────────────────────────────────────
        if "o que tem no clipboard" in t or "lê o clipboard" in t:
            return self.get_clipboard()

        # ── URLs ──────────────────────────────────────────────────────────────
        m = re.search(r"abre\s+(?:o site|a página|o link)?\s*([\w./-]+\.\w{2,})", t)
        if m:
            return self.open_url(m.group(1))

        # ── Sistema ───────────────────────────────────────────────────────────
        if any(p in t for p in ["dorme o pc", "modo sleep", "suspende o pc"]):
            return self.sleep_pc()
        if any(p in t for p in ["bloqueia o pc", "trava o pc", "lock"]):
            return self.lock_pc()
        if "reinicia o pc" in t or "restart" in t:
            return self.restart()
        if "desliga o pc" in t or "shutdown" in t:
            return self.shutdown()
        if "cancela o desligamento" in t:
            return self.cancel_shutdown()

        # ── Print / screenshot ────────────────────────────────────────────────
        if any(p in t for p in ["tira um print", "screenshot", "print da tela"]):
            # Salva em disco (sem analisar)
            return "Use 'captura a tela' pra eu analisar, ou 'tira um print' só pra salvar."

        return None
