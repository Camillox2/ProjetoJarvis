"""
Resumo de páginas web.
Detecta a URL do navegador ativo ou pega do clipboard,
faz scraping, limpa o conteúdo e manda pro LLM resumir.

Suporta:
  - URL falada/detectada no comando
  - URL copiada no clipboard
  - URL da aba ativa do Chrome/Firefox/Edge (via acessibilidade do Windows)
  - YouTube: extrai transcrição automática se disponível
"""

import re
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlparse
import httpx
from keilinks.log import get_logger

try:
    from bs4 import BeautifulSoup
    _HAS_BS4 = True
except ImportError:
    _HAS_BS4 = False

log = get_logger("summarizer")

# Cache simples em disco — mesma URL não busca de novo por 30 minutos
CACHE_FILE = Path("memoria/cache_resumos.json")
CACHE_TTL  = 60 * 30   # 30 minutos

MAX_CHARS_TO_LLM = 6000   # máximo de caracteres enviados ao LLM


class Summarizer:
    def __init__(self):
        self._cache: dict = self._load_cache()
        self._http = httpx.Client(
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"},
        )

    # ─── Entrada principal ────────────────────────────────────────────────────
    def extract_url(self, user_text: str) -> str | None:
        """
        Tenta encontrar a URL:
        1. No texto falado
        2. No clipboard
        3. Na barra de endereço do navegador ativo (Windows)
        """
        # 1. URL no texto falado
        url = self._find_url_in_text(user_text)
        if url:
            return url

        # 2. Clipboard
        url = self._url_from_clipboard()
        if url:
            log.debug("URL do clipboard: %s", url)
            return url

        # 3. Barra de endereço do navegador ativo
        url = self._url_from_browser()
        if url:
            log.debug("URL do navegador: %s", url)
            return url

        return None

    def summarize_url(self, url: str, mode: str = "resumo") -> str:
        """
        mode: "resumo" | "pontos" | "completo"
        Retorna o texto preparado para o LLM.
        """
        # Cache hit
        cache_key = hashlib.md5(url.encode()).hexdigest()
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if time.time() - entry["ts"] < CACHE_TTL:
                log.debug("Usando cache.")
                content = entry["content"]
                title   = entry["title"]
            else:
                del self._cache[cache_key]
                content, title = self._fetch(url)
        else:
            content, title = self._fetch(url)
            if content:
                self._cache[cache_key] = {
                    "ts": time.time(), "content": content, "title": title
                }
                self._save_cache()

        if not content:
            return f"Não consegui acessar a página: {url}"

        return self._build_llm_prompt(url, title, content, mode)

    # ─── Fetch e extração de conteúdo ─────────────────────────────────────────
    def _fetch(self, url: str) -> tuple[str, str]:
        """Retorna (conteúdo_limpo, título)."""
        if not _HAS_BS4:
            return "", "bs4 não instalado"

        # YouTube: tenta transcrição primeiro
        if "youtube.com/watch" in url or "youtu.be/" in url:
            transcript = self._youtube_transcript(url)
            if transcript:
                return transcript, "YouTube"

        try:
            r = self._http.get(url)
            r.raise_for_status()
        except Exception as e:
            return "", f"Erro: {e}"

        soup = BeautifulSoup(r.text, "html.parser")
        title = soup.title.string.strip() if soup.title else url

        # Remove ruído
        for tag in soup(["script", "style", "nav", "footer", "header",
                          "aside", "form", "button", "iframe", "noscript",
                          "figure", "figcaption", "menu"]):
            tag.decompose()

        # Tenta extrair o bloco de conteúdo principal
        main = (
            soup.find("article") or
            soup.find("main") or
            soup.find(id=re.compile(r"content|article|post|body", re.I)) or
            soup.find(class_=re.compile(r"content|article|post|entry|text", re.I)) or
            soup.body
        )

        raw = (main or soup).get_text(separator="\n", strip=True)
        clean = self._clean_text(raw)
        return clean[:MAX_CHARS_TO_LLM], title

    def _clean_text(self, text: str) -> str:
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'[ \t]{2,}', ' ', text)
        # Remove linhas muito curtas (menu items, breadcrumbs, etc.)
        lines = [l for l in text.splitlines() if len(l.strip()) > 20]
        return "\n".join(lines)

    def _youtube_transcript(self, url: str) -> str | None:
        """Tenta baixar a transcrição automática do YouTube."""
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            vid_id = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", url)
            if not vid_id:
                return None
            transcript = YouTubeTranscriptApi.get_transcript(
                vid_id.group(1), languages=["pt", "pt-BR", "en"]
            )
            return " ".join(t["text"] for t in transcript)[:MAX_CHARS_TO_LLM]
        except Exception:
            return None

    # ─── Detecção de URL ──────────────────────────────────────────────────────
    def _find_url_in_text(self, text: str) -> str | None:
        match = re.search(
            r'https?://[^\s<>"\']+|www\.[^\s<>"\']+\.[a-z]{2,}[^\s<>"\']*',
            text, re.IGNORECASE
        )
        if match:
            url = match.group(0)
            if not url.startswith("http"):
                url = "https://" + url
            return url
        return None

    def _url_from_clipboard(self) -> str | None:
        try:
            import pyperclip
            text = pyperclip.paste().strip()
            if text and re.match(r'https?://', text):
                return text
        except Exception:
            pass
        return None

    def _url_from_browser(self) -> str | None:
        """
        Pega a URL da barra de endereço do Chrome/Edge/Firefox ativo
        via UI Automation (Windows acessibilidade — sem extensão).
        """
        try:
            import subprocess
            # PowerShell: pega o título da janela ativa e tenta extrair URL
            script = """
            Add-Type -AssemblyName UIAutomationClient
            Add-Type -AssemblyName UIAutomationTypes
            $ae = [System.Windows.Automation.AutomationElement]::FocusedElement
            $root = [System.Windows.Automation.TreeWalker]::RawViewWalker
            $win = $ae
            while ($win -and $win.Current.ControlType -ne [System.Windows.Automation.ControlType]::Window) {
                $win = $root.GetParent($win)
            }
            if ($win) {
                $bars = $win.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                    (New-Object System.Windows.Automation.PropertyCondition(
                        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
                        [System.Windows.Automation.ControlType]::Edit)))
                foreach ($bar in $bars) {
                    $val = ($bar.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern) -as
                            [System.Windows.Automation.ValuePattern]).Current.Value
                    if ($val -match '^https?://') { Write-Output $val; break }
                }
            }
            """
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True, text=True, timeout=5
            )
            url = result.stdout.strip()
            if url and url.startswith("http"):
                return url
        except Exception:
            pass
        return None

    # ─── Prompt para o LLM ────────────────────────────────────────────────────
    def _build_llm_prompt(self, url: str, title: str, content: str, mode: str) -> str:
        instructions = {
            "resumo":   "Faça um resumo claro e direto do conteúdo abaixo em português. "
                        "Destaque os pontos principais. Seja conciso mas completo.",
            "pontos":   "Liste os pontos principais do conteúdo abaixo em tópicos curtos, "
                        "em português. Máximo 7 tópicos.",
            "completo": "Explique o conteúdo abaixo em detalhes, em português. "
                        "Organize as informações de forma clara.",
        }

        return (
            f"{instructions.get(mode, instructions['resumo'])}\n\n"
            f"Título: {title}\n"
            f"URL: {url}\n\n"
            f"Conteúdo:\n{content}"
        )

    # ─── Cache ────────────────────────────────────────────────────────────────
    def _load_cache(self) -> dict:
        CACHE_FILE.parent.mkdir(exist_ok=True)
        if CACHE_FILE.exists():
            try:
                return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_cache(self):
        CACHE_FILE.write_text(
            json.dumps(self._cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
