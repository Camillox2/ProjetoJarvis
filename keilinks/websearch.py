"""
Busca na web via Google (primário) ou DuckDuckGo (fallback), sem API key.
Detecta automaticamente quando a Keilinks precisa pesquisar
e injeta o resultado no contexto do LLM.
"""

import re
import httpx
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from googlesearch import search as _google_search
    _HAS_GOOGLE = True
except ImportError:
    _HAS_GOOGLE = False

try:
    from ddgs import DDGS
    _HAS_DDGS = True
except ImportError:
    try:
        from duckduckgo_search import DDGS  # fallback nome antigo
        _HAS_DDGS = True
    except ImportError:
        _HAS_DDGS = False

try:
    from bs4 import BeautifulSoup
    _HAS_BS4 = True
except ImportError:
    _HAS_BS4 = False

# ─── Palavras que forçam busca imediata ──────────────────────────────────────
# Triggers de frase exata (substring match) — sem risco de falso positivo
_PHRASE_TRIGGERS = [
    "o que aconteceu", "o que está acontecendo", "qual é o preço",
    "previsão do tempo", "essa semana", "esse mês",
]

# Triggers de palavra isolada — usam word boundary para evitar falso positivo
# (ex: "resultado" não deve disparar por "meu dia foi ótimo")
_WORD_TRIGGERS = [
    "notícia", "notícias", "recente", "recentes",
    "último", "última", "últimas", "últimos",
    "pesquisa", "pesquise", "busca", "busque", "procura", "procure",
    "cotação", "temperatura",
    "lançamento", "lançou", "novidade", "update", "atualização",
    "quem ganhou", "resultado", "placar",
]

# Regex compilado para word triggers (word boundary)
_WORD_TRIGGER_RE = re.compile(
    r'\b(?:' + '|'.join(re.escape(w) for w in _WORD_TRIGGERS) + r')\b',
    re.IGNORECASE
)

# ─── Frases que indicam que o LLM não sabe e precisou pesquisar ──────────────
UNCERTAINTY_PHRASES = [
    "não tenho informações atualizadas",
    "meu conhecimento vai até",
    "não sei ao certo",
    "não tenho certeza",
    "pode ter mudado",
    "recomendo verificar",
    "não posso confirmar",
    "dados recentes",
    "atualização recente",
]

MAX_RESULTS    = 3
MAX_BODY_CHARS = 600   # máximo de caracteres do corpo de cada página
_FETCH_TIMEOUT = 4.0   # timeout curto para fetch de corpo


class WebSearcher:
    def __init__(self):
        self.http = httpx.Client(timeout=_FETCH_TIMEOUT, follow_redirects=True)

    def should_search_preemptive(self, text: str) -> bool:
        """Retorna True se o texto do usuário claramente pede info da web."""
        t = text.lower()
        # Frases exatas (substring)
        if any(trigger in t for trigger in _PHRASE_TRIGGERS):
            return True
        # Palavras isoladas (word boundary — evita falsos positivos)
        return bool(_WORD_TRIGGER_RE.search(t))

    def should_search_reactive(self, llm_reply: str) -> bool:
        """Retorna True se a resposta do LLM indica que ele não sabe algo recente."""
        r = llm_reply.lower()
        return any(phrase in r for phrase in UNCERTAINTY_PHRASES)

    def build_query(self, user_text: str) -> str:
        """Monta a query de busca limpando o texto do usuário."""
        q = user_text.lower()
        # Remove saudações e palavras de comando
        for word in [
            "pesquisa", "pesquise", "busca", "busque", "procura", "procure",
            "keilinks", "pra mim", "sobre", "me fala", "me diz", "me conta",
            "oi", "olá", "ola", "ei", "hey", "e aí", "eai", "tudo bem",
            "tudo bom", "como vai", "bom dia", "boa tarde", "boa noite",
            "você sabe", "sabe me dizer", "queria saber", "quero saber",
        ]:
            q = q.replace(word, " ")
        # Remove pontuação no início/fim e espaços duplos
        q = re.sub(r"^[?!.,;\s]+", "", q)
        q = re.sub(r'\s+', ' ', q).strip()
        return q

    def _fetch_body(self, url: str) -> str:
        """Tenta pegar o texto principal de uma URL."""
        if not _HAS_BS4:
            return ""
        try:
            r = self.http.get(url, headers={"User-Agent": "Mozilla/5.0"})
            soup = BeautifulSoup(r.text, "html.parser")

            # Remove script/style
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()

            text = soup.get_text(separator=" ", strip=True)
            text = re.sub(r'\s+', ' ', text)
            return text[:MAX_BODY_CHARS]
        except Exception:
            return ""

    def _search_google(self, query: str) -> list[dict]:
        """Busca via Google e retorna lista no formato {title, body, href}."""
        urls = list(_google_search(query, num_results=MAX_RESULTS, lang="pt", region="br"))
        results = []
        for url in urls:
            results.append({"title": url, "body": "", "href": url})
        return results

    def _search_ddgs(self, query: str) -> list[dict]:
        """Busca via DuckDuckGo e retorna lista no formato {title, body, href}."""
        raw = list(DDGS().text(query, max_results=MAX_RESULTS, region="br-pt"))
        return [{"title": r.get("title", ""), "body": r.get("body", ""), "href": r.get("href", "")} for r in raw]

    def search(self, query: str) -> str:
        """
        Busca no Google (primário) ou DuckDuckGo (fallback) e retorna
        um bloco de contexto para injetar no prompt do LLM.
        """
        results: list[dict] = []

        # Tenta Google primeiro
        if _HAS_GOOGLE:
            try:
                results = self._search_google(query)
            except Exception:
                results = []

        # Fallback para DDGS se Google falhou ou indisponível
        if not results and _HAS_DDGS:
            try:
                results = self._search_ddgs(query)
            except Exception as e:
                return f"[Busca falhou: {e}]"

        if not results:
            return "[Nenhum resultado encontrado]"

        # Busca corpos das páginas em paralelo (quando snippet é curto)
        urls_to_fetch = {}
        for i, r in enumerate(results):
            body = r.get("body", "")
            url  = r.get("href", "")
            if len(body) < 200 and url:
                urls_to_fetch[i] = url

        fetched_bodies: dict[int, str] = {}
        if urls_to_fetch and _HAS_BS4:
            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = {
                    pool.submit(self._fetch_body, url): idx
                    for idx, url in urls_to_fetch.items()
                }
                for future in as_completed(futures, timeout=_FETCH_TIMEOUT + 1):
                    idx = futures[future]
                    try:
                        body = future.result()
                        if body:
                            fetched_bodies[idx] = body
                    except Exception:
                        pass

        lines = [f"Resultados da busca por: '{query}'\n"]
        for i, r in enumerate(results):
            title = r.get("title", "")
            body  = fetched_bodies.get(i, r.get("body", ""))
            url   = r.get("href", "")

            lines.append(f"[{i+1}] {title}")
            lines.append(f"    {body[:MAX_BODY_CHARS]}")
            lines.append(f"    Fonte: {url}\n")

        return "\n".join(lines)

    def format_for_prompt(self, search_result: str) -> str:
        """Formata o resultado para injetar no contexto do LLM."""
        return (
            "\n\n─── RESULTADO DE BUSCA WEB (use isso pra responder) ─────────────\n"
            + search_result
            + "\n──────────────────────────────────────────────────────────────────\n"
        )
