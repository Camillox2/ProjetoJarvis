"""
Monitoramento de presença via câmera.
A Keilinks observa o usuário periodicamente e inicia conversa
quando percebe tédio, relaxamento ou algo interessante acontecendo.

Usa qwen3-vl:8b pra analisar o frame e decidir se e como engajar.
"""

import base64
import json
import time
import threading
import random
import httpx
from dataclasses import dataclass
from typing import Callable

from config import OLLAMA_HOST, LLM_MODEL, OLLAMA_KEEP_ALIVE
from keilinks.log import get_logger

log = get_logger("presence")


# ─── Configuração ─────────────────────────────────────────────────────────────
@dataclass
class PresenceConfig:
    check_interval_secs: float = 25.0   # checa a cada N segundos
    min_gap_secs:        float = 300.0  # mínimo entre engajamentos (5 min)
    engage_when_focused: bool  = False  # respeita foco: não interrompe se focado
    sensitivity:         str   = "normal"  # "low" | "normal" | "high"


# Prompt de análise — neutro e objetivo
_ANALYSIS_PROMPT = """Analise o frame da câmera e responda APENAS com JSON válido, sem texto extra:
{
  "presente": true/false,
  "estado": "focado|entediado|relaxado|fazendo_algo|ausente",
  "atividade": "descrição objetiva do que a pessoa está fazendo",
  "expressao": "neutro|sério|cansado|animado|frustrado|sorrindo",
  "engajar": true/false,
  "abertura": "primeira frase natural para iniciar conversa"
}

Regras de estado (seja preciso, não force positivo):
- focado: olhando para tela, digitando ou lendo ativamente
- entediado: parado, olhar vago, sem fazer nada
- relaxado: numa posição confortável, descansando
- fazendo_algo: atividade visível (comendo, desenhando, olhando celular, etc.)
- ausente: ninguém no frame

Regras para engajar:
- engajar=true: entediado, relaxado sem foco, fazendo_algo interessante
- engajar=false: focado no computador, ausente

A "abertura" deve ser curta, natural e direta. Exemplos:
- Bom: "Tô vendo que você parou. Tá bem?"
- Bom: "O que você tá fazendo aí?"  
- Ruim: "Olá! Detectei que você está entediado."
- Ruim: "Que sorriso lindo!" (não invente o que não está no frame)"""


class PresenceMonitor:
    def __init__(self, on_engage: Callable[[str], None], eyes=None):
        """
        on_engage(abertura): chamado quando a Keilinks decide iniciar conversa.
        A string é a primeira frase dela — já pronta pra falar.
        eyes: instância de Eyes — compartilha a câmera (evita conflito).
        """
        self._on_engage      = on_engage
        self._eyes           = eyes
        self._config         = PresenceConfig()
        self._running        = False
        self._paused         = False
        self._thread: threading.Thread | None = None
        self._last_engage    = 0.0          # timestamp do último engajamento
        self._client         = httpx.Client(base_url=OLLAMA_HOST, timeout=30.0)
        self._consecutive_bored = 0         # detecta tédio persistente

    # ─── API pública ──────────────────────────────────────────────────────────
    def start(self, config: PresenceConfig | None = None):
        if self._running:
            return
        if config:
            self._config = config
        if not self._eyes or not self._eyes.is_available():
            log.warning("Câmera não disponível — monitoramento desativado.")
            return
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("Monitorando você a cada %.0fs.", self._config.check_interval_secs)

    def stop(self):
        self._running = False

    def pause(self):
        """Pausa durante conversa ativa — evita ela te interromper no meio."""
        self._paused = True

    def resume(self):
        self._paused = False

    def is_running(self) -> bool:
        return self._running

    # ─── Câmera (usa Eyes compartilhado) ─────────────────────────────────────
    def _capture_b64(self) -> str | None:
        if not self._eyes or not self._eyes.is_available():
            return None
        return self._eyes.capture_frame_b64()

    # ─── Análise via LLM ──────────────────────────────────────────────────────
    def _analyze(self, image_b64: str) -> dict | None:
        try:
            t0 = time.time()
            r = self._client.post("/api/chat", json={
                "model":   LLM_MODEL,
                "messages": [{
                    "role":    "user",
                    "content": _ANALYSIS_PROMPT,
                    "images":  [image_b64],
                }],
                "stream":  False,
                "think":   False,
                "keep_alive": OLLAMA_KEEP_ALIVE,
                "options": {"temperature": 0.2, "num_ctx": 1024, "num_predict": 200},
            })
            r.raise_for_status()
            elapsed = time.time() - t0
            message = r.json().get("message", {})
            content = message.get("content", "").strip()
            thinking = message.get("thinking", "").strip()
            if not content and thinking:
                log.debug("[TIMING] Presença: %.1fs — modelo retornou só thinking (%d chars)", elapsed, len(thinking))
                return None
            start   = content.find("{")
            end     = content.rfind("}") + 1
            if start == -1 or end == 0:
                log.debug("[TIMING] Presença: %.1fs — JSON inválido", elapsed)
                return None
            data = json.loads(content[start:end])
            # Valida campos obrigatórios
            if not isinstance(data, dict) or "presente" not in data:
                return None
            log.debug("[TIMING] Presença: %.1fs — estado=%s", elapsed, data.get("estado"))
            return data
        except Exception as e:
            log.error("Erro na análise: %s", e)
            return None

    # ─── Decisão de engajamento ───────────────────────────────────────────────
    def _should_engage(self, analysis: dict) -> bool:
        if not analysis.get("presente", False):
            self._consecutive_bored = 0
            return False

        estado = analysis.get("estado", "")
        engajar = analysis.get("engajar", False)

        # Respeita foco se configurado
        if estado == "focado" and not self._config.engage_when_focused:
            self._consecutive_bored = 0
            return False

        # Cooldown mínimo
        elapsed = time.time() - self._last_engage
        if elapsed < self._config.min_gap_secs:
            # Exceção: tédio persistente reduz o cooldown pela metade
            if estado == "entediado":
                self._consecutive_bored += 1
            if self._consecutive_bored < 3 or elapsed < self._config.min_gap_secs / 2:
                return False

        # Sensibilidade
        if self._config.sensitivity == "low" and not engajar:
            return False
        if self._config.sensitivity == "normal" and estado not in ("entediado", "relaxado", "fazendo_algo"):
            return False

        return engajar

    # ─── Loop principal ───────────────────────────────────────────────────────
    def _loop(self):
        # Pequeno delay inicial pra não engajar logo que abre
        time.sleep(30.0)

        while self._running:
            time.sleep(self._config.check_interval_secs)

            if self._paused or not self._running:
                continue

            b64 = self._capture_b64()
            if not b64:
                continue

            analysis = self._analyze(b64)
            if not analysis:
                continue

            estado  = analysis.get("estado", "")
            abertura = analysis.get("abertura", "").strip()

            log.debug("estado=%s | engajar=%s | %s", estado, analysis.get('engajar'), analysis.get('motivo_engajar',''))

            if self._should_engage(analysis) and abertura:
                self._last_engage    = time.time()
                self._consecutive_bored = 0
                self._on_engage(abertura)
