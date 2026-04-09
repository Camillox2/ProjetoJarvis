import re
import time
import threading
from typing import Generator
import httpx
from config import (
    OLLAMA_HOST, LLM_MODEL, LLM_FALLBACKS,
    LLM_TIMEOUT_SLOW, LLM_RECOVER_AFTER, MAX_HISTORY_TURNS, OLLAMA_KEEP_ALIVE,
)
from keilinks.log import get_logger
from keilinks.personality import SYSTEM_PROMPT
from keilinks.memory import Memory
from keilinks.learner import Learner
from keilinks.websearch import WebSearcher

log = get_logger("brain")

_OOM_SIGNALS = [
    "out of memory", "cuda error", "ggml_cuda", "failed to allocate",
    "cudamalloc failed", "not enough memory", "context too long",
]

# Pontuação que delimita o fim de uma sentença para TTS streaming
_SENTENCE_END = re.compile(r'(?<=[.!?])\s+|(?<=\n\n)')

# Remove emoji e artefatos que o LLM gera mas o TTS não deve falar
_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # símbolos e pictogramas
    "\U0001F680-\U0001F6FF"  # transporte e mapa
    "\U0001F1E0-\U0001F1FF"  # bandeiras
    "\U00002700-\U000027BF"  # dingbats
    "\U0001F900-\U0001F9FF"  # suplemento
    "\U00002600-\U000026FF"  # miscelânea
    "\uFE0F"                 # variation selector
    "]+", flags=re.UNICODE
)
_THINK_RE = re.compile(r'<think>.*?</think>', re.DOTALL | re.IGNORECASE)
_OPEN_THINK_RE = re.compile(r'<think>.*$', re.DOTALL | re.IGNORECASE)
_THINK_TAG_RE = re.compile(r'</?think>', re.IGNORECASE)
# Remove linhas que começam com PS:, Nota:, OBS:, (PS etc
_META_LINE_RE = re.compile(r'(?:^|\n)\s*(?:PS:|Nota:|OBS:|\(PS|\(Obs)[^\n]*', re.IGNORECASE)


def _clean_llm(text: str) -> str:
    """Remove emoji, metacomentários e pontuação órfã antes de falar."""
    text = _THINK_RE.sub(' ', text)
    text = _OPEN_THINK_RE.sub(' ', text)
    text = _THINK_TAG_RE.sub(' ', text)
    text = _META_LINE_RE.sub('', text)
    text = _EMOJI_RE.sub('', text)
    # Remove pontuação órfã que sobra após limpeza de emoji (ex: "😊)" → ")")
    text = re.sub(r'^[)\]}>]+\s*', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


class Brain:
    def __init__(self, on_model_change=None, history_db=None, on_search_start=None):
        self.memory   = Memory()
        self.learner  = Learner()
        self.searcher = WebSearcher()
        self._history_db = history_db
        self._on_search_start = on_search_start  # callback: chamado antes de buscar
        self.history: list[dict] = self._load_multi_session_history()

        self._primary    = LLM_MODEL
        self._fallbacks  = [model for model in LLM_FALLBACKS if model and model != LLM_MODEL]
        self._models     = [self._primary, *self._fallbacks]
        self._active_index = 0
        self._active     = self._models[self._active_index]
        self._using_fallback     = False
        self._fallback_successes = 0
        self._on_model_change    = on_model_change

        self._client = httpx.Client(base_url=OLLAMA_HOST, timeout=120.0)

        # Hints setados externamente pelo main antes de cada think_stream()
        self._build_system_prompt_extra: str = ""  # RAG context
        self._mood_hint: str = ""                  # Mood detection

        log.info("Modelo principal : %s", self._primary)
        log.info("Fallbacks        : %s", ", ".join(self._fallbacks) if self._fallbacks else "nenhum")

    def set_rag_context(self, context: str):
        """Define o contexto RAG para a próxima chamada ao LLM."""
        self._build_system_prompt_extra = context

    def set_mood_hint(self, hint: str):
        """Define a dica de humor do usuário para a próxima chamada."""
        self._mood_hint = hint

    def _load_multi_session_history(self) -> list[dict]:
        """Carrega histórico: JSON local + últimas mensagens do SQLite (multi-sessão)."""
        history = self.memory.history.copy()
        if self._history_db and not history:
            try:
                recent = self._history_db.get_recent_context(MAX_HISTORY_TURNS * 2)
                if recent:
                    log.info("Carregado contexto de sessões anteriores (%d chars).", len(recent))
                    # Parseia o texto de volta pra lista de dicts
                    for line in recent.split("\n"):
                        if "] Usuário: " in line:
                            content = line.split("] Usuário: ", 1)[1]
                            history.append({"role": "user", "content": content})
                        elif "] Keilinks: " in line:
                            content = line.split("] Keilinks: ", 1)[1]
                            history.append({"role": "assistant", "content": content})
            except Exception as e:
                log.warning("Falha ao carregar histórico multi-sessão: %s", e)
        return history

    # ─── Gestão de modelo ─────────────────────────────────────────────────────
    def _restore_primary(self, reason: str = "recuperado"):
        self._active_index       = 0
        self._active             = self._primary
        self._using_fallback     = False
        self._fallback_successes = 0
        log.info("Voltou para %s", self._primary)
        if self._on_model_change:
            self._on_model_change(self._primary, reason)

    def _switch_to_fallback(self, reason: str) -> bool:
        next_index = self._active_index + 1
        if next_index >= len(self._models):
            log.warning("Sem fallback adicional (%s). Permanecendo em %s.", reason, self._active)
            return False

        self._active_index       = next_index
        self._active             = self._models[self._active_index]
        self._using_fallback     = self._active_index > 0
        self._fallback_successes = 0
        log.warning("Fallback → %s (%s)", self._active, reason)
        if self._on_model_change:
            self._on_model_change(self._active, reason)
        return True

    def _try_recover(self):
        if not self._using_fallback:
            return
        self._fallback_successes += 1
        if self._fallback_successes >= LLM_RECOVER_AFTER:
            if self._ping(self._primary):
                self._restore_primary()
            else:
                self._fallback_successes = 0

    def _ping(self, model: str) -> bool:
        try:
            r = self._client.post("/api/chat", json={
                "model": model,
                "messages": [{"role": "user", "content": "ok"}],
                "stream": False,
                "think": False,
                "keep_alive": OLLAMA_KEEP_ALIVE,
                "options": {"num_ctx": 512, "num_predict": 5},
            }, timeout=20.0)
            return r.status_code == 200 and not any(s in r.text.lower() for s in _OOM_SIGNALS)
        except Exception:
            return False

    def warmup(self):
        """Pré-carrega o modelo em background para reduzir a latência da 1ª resposta."""
        t0 = time.monotonic()
        ok = self._ping(self._active)
        elapsed = time.monotonic() - t0
        if ok:
            log.info("Warmup do modelo %s em %.2fs", self._active, elapsed)
        else:
            log.warning("Warmup falhou para %s em %.2fs", self._active, elapsed)

    # ─── Prompt ───────────────────────────────────────────────────────────────
    def _build_system_prompt(self, extra: str = "") -> str:
        prompt = SYSTEM_PROMPT
        profile = self.learner.get_profile_summary()
        if profile:
            prompt += "\n\n─── O QUE VOCÊ JÁ APRENDEU SOBRE ELE ──────────────\n" + profile
        notes = self.memory.get_notes_as_text()
        if notes:
            prompt += "\n\n─── LEMBRETES QUE ELE PEDIU PRA GUARDAR ────────────\n" + notes
        if self._using_fallback:
            prompt += "\n\n[Sistema: modo econômico ativo — seja um pouco mais conciso.]"
        if self._mood_hint:
            prompt += f"\n\n[Humor do usuário detectado pela voz: {self._mood_hint}. Adapte seu tom.]"
            self._mood_hint = ""
        if self._build_system_prompt_extra:
            prompt += self._build_system_prompt_extra
            self._build_system_prompt_extra = ""
        if extra:
            prompt += extra
        return prompt

    def _trim_history(self):
        limit = MAX_HISTORY_TURNS if not self._using_fallback else MAX_HISTORY_TURNS // 2
        max_msgs = limit * 2
        if len(self.history) > max_msgs:
            self.history = self.history[-max_msgs:]

    def _base_options(self, has_image: bool = False) -> dict:
        num_ctx = 4096 if has_image else 2048
        if self._using_fallback:
            return {
                "temperature": 0.75,
                "top_p":       0.9,
                "num_ctx":     num_ctx,
                "num_predict": 128,
                "num_batch":   128,
                "num_keep":    64,
                "repeat_penalty": 1.1,
            }
        return {
            "temperature": 0.75,
            "top_p":       0.9,
            "num_ctx":     num_ctx,
            "num_predict": 160,    # limita geração pra não enrolar
            "num_batch":   256,
            "num_keep":    96,
            "repeat_penalty": 1.1,
        }

    # ─── Chamada normal (não-streaming) ───────────────────────────────────────
    def _call_llm(self, system: str, messages: list[dict], has_image: bool = False) -> str:
        for attempt in range(2):
            payload = {
                "model":    self._active,
                "messages": [{"role": "system", "content": system}, *messages],
                "stream":   False,
                "think":    False,
                "keep_alive": OLLAMA_KEEP_ALIVE,
                "options":  self._base_options(has_image=has_image),
            }
            t0 = time.monotonic()
            try:
                r = self._client.post("/api/chat", json=payload)
                elapsed = time.monotonic() - t0

                if any(s in r.text.lower() for s in _OOM_SIGNALS):
                    raise MemoryError("OOM na resposta")
                r.raise_for_status()
                message = r.json().get("message", {})
                reply = message.get("content", "").strip()
                thinking = message.get("thinking", "").strip()

                if not reply and thinking:
                    log.error("Modelo %s retornou apenas thinking (%d chars) em %.1fs.", self._active, len(thinking), elapsed)
                    return "Não consegui formular a resposta agora. Tenta de novo."

                if elapsed > LLM_TIMEOUT_SLOW:
                    self._switch_to_fallback(f"lento ({elapsed:.0f}s)")

                if self._using_fallback:
                    self._try_recover()
                return reply

            except httpx.TimeoutException:
                if attempt == 0 and self._switch_to_fallback("timeout"):
                    continue
                return "Demorou demais. Tenta de novo?"
            except MemoryError:
                if attempt == 0 and self._switch_to_fallback("erro de memória de vídeo"):
                    continue
                return "Memória cheia. Tenta em instantes."
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (500, 503) and attempt == 0 and self._switch_to_fallback(f"HTTP {e.response.status_code}"):
                    continue
                return f"Erro de servidor: {e}"
            except Exception as e:
                return f"Algo deu errado: {e}"
        return "Não consegui responder agora."

    # ─── Chamada com streaming (para TTS em tempo real) ───────────────────────
    def _stream_llm(
        self,
        system: str,
        messages: list[dict],
        store_reply: bool = True,
        has_image: bool = False,
        stop_event: threading.Event | None = None,
    ) -> Generator[str, None, None]:
        """
        Faz streaming do LLM e yield de sentenças completas conforme chegam.
        A Voice pode começar a falar a primeira frase enquanto o resto ainda gera.
        """
        opts = self._base_options(has_image=has_image)
        payload = {
            "model":    self._active,
            "messages": [{
                "role": "system", "content": system
            }, *messages],
            "stream":   True,
            "think":    False,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "options":  opts,
        }

        # Log de contexto para diagnóstico
        sys_len = len(system)
        hist_len = sum(len(m.get("content", "")) for m in messages)
        log.info("[TIMING] LLM stream: modelo=%s, system=%d chars, history=%d chars (%d msgs), num_ctx=%s, has_image=%s",
             self._active, sys_len, hist_len, len(messages), opts.get("num_ctx"), has_image)

        buffer      = ""
        full_reply  = ""
        oom_hit     = False
        cancelled   = False
        t0          = time.monotonic()
        t_first     = None   # tempo até primeiro token
        token_count = 0
        thinking_chars = 0
        final_stats: dict = {}

        try:
            with self._client.stream("POST", "/api/chat", json=payload, timeout=120.0) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if stop_event and stop_event.is_set():
                        cancelled = True
                        break
                    if not line:
                        continue
                    try:
                        import json as _json
                        data    = _json.loads(line)
                        message = data.get("message", {})
                        token   = message.get("content", "")
                        thinking = message.get("thinking", "")
                        done    = data.get("done", False)
                    except Exception:
                        continue

                    if any(s in line.lower() for s in _OOM_SIGNALS):
                        oom_hit = True
                        break

                    if thinking:
                        thinking_chars += len(thinking)

                    if token:
                        token_count += 1
                        if t_first is None:
                            t_first = time.monotonic() - t0
                            log.info("[TIMING] Primeiro token em %.1fs", t_first)

                    buffer     += token
                    full_reply += token

                    # Yield quando tem uma sentença completa
                    parts = _SENTENCE_END.split(buffer)
                    if len(parts) > 1:
                        for sentence in parts[:-1]:
                            s = _clean_llm(sentence)
                            if s:
                                yield s
                        buffer = parts[-1]

                    if done:
                        final_stats = data
                        break

        except httpx.TimeoutException:
            elapsed = time.monotonic() - t0
            log.error("[TIMING] Timeout após %.1fs (%d tokens)", elapsed, token_count)
            self._switch_to_fallback(f"timeout streaming ({elapsed:.0f}s)")
            yield "Demorei demais. Pode repetir?"
            return
        except Exception as e:
            log.error("[TIMING] Erro no stream: %s", e)
            yield f"Tive um problema aqui: {e}"
            return

        if cancelled:
            log.info("[TIMING] LLM stream cancelado: %.1fs, %d tokens", time.monotonic() - t0, token_count)
            return

        # Flush do buffer restante
        if buffer.strip():
            s = _clean_llm(buffer)
            if s:
                yield s

        elapsed = time.monotonic() - t0
        tps = token_count / elapsed if elapsed > 0 else 0
        log.info("[TIMING] LLM completo: %.1fs total, %d tokens, %.1f tok/s, first=%.1fs",
                 elapsed, token_count, tps, t_first or 0)
        if final_stats:
            load_s = final_stats.get("load_duration", 0) / 1_000_000_000
            prompt_s = final_stats.get("prompt_eval_duration", 0) / 1_000_000_000
            eval_s = final_stats.get("eval_duration", 0) / 1_000_000_000
            log.info(
                "[TIMING] Ollama: load=%.2fs prompt=%.2fs eval=%.2fs prompt_tokens=%s eval_tokens=%s thinking_chars=%d",
                load_s,
                prompt_s,
                eval_s,
                final_stats.get("prompt_eval_count", 0),
                final_stats.get("eval_count", token_count),
                thinking_chars,
            )

        if oom_hit:
            self._switch_to_fallback("OOM no streaming")
            yield "Fiquei sem memória no meio da resposta. Vou usar o modelo menor."
            return

        clean_reply = _clean_llm(full_reply)

        if not clean_reply:
            log.error(
                "Modelo %s retornou resposta vazia. thinking_chars=%d, prompt_tokens=%s, eval_tokens=%s",
                self._active,
                thinking_chars,
                final_stats.get("prompt_eval_count", 0),
                final_stats.get("eval_count", 0),
            )
            yield "Não consegui formular a resposta agora. Tenta de novo."
            return

        # Detecta resposta lenta
        elapsed = time.monotonic() - t0
        if elapsed > LLM_TIMEOUT_SLOW:
            self._switch_to_fallback(f"lento ({elapsed:.0f}s)")

        if self._using_fallback:
            self._try_recover()

        # Salva histórico com a resposta completa
        if store_reply and clean_reply:
            self.history.append({"role": "assistant", "content": clean_reply})
            self.memory.save_history(self.history)

    # ─── Interface pública ────────────────────────────────────────────────────
    def think_stream(self, user_text: str,
                     image_b64: str | None = None,
                     internal: bool = False,
                     stop_event: threading.Event | None = None) -> Generator[str, None, None]:
        """
        Versão streaming do think().
        Faz yield de sentenças conforme o LLM gera — use com voice.speak_stream().
        """
        t0_total = time.monotonic()

        call_history = self.history.copy()
        message: dict = {"role": "user", "content": user_text}
        if image_b64:
            message = {
                "role":    "user",
                "content": user_text or "O que você vê nessa imagem?",
                "images":  [image_b64],
            }

        if internal:
            call_history.append(message)
        else:
            self.history.append(message)
            self._trim_history()
            call_history = self.history

        search_context = ""
        if self.searcher.should_search_preemptive(user_text):
            t_search = time.monotonic()
            log.info("Buscando na web...")
            if self._on_search_start:
                self._on_search_start()
            query          = self.searcher.build_query(user_text)
            result         = self.searcher.search(query)
            search_context = self.searcher.format_for_prompt(result)
            log.info("[TIMING] Busca web: %.1fs (query='%s')", time.monotonic() - t_search, query)

        t_prompt = time.monotonic()
        system = self._build_system_prompt(search_context)
        log.info("[TIMING] Build prompt: %.3fs", time.monotonic() - t_prompt)

        generated_parts: list[str] = []
        for piece in self._stream_llm(
            system,
            call_history,
            store_reply=not internal,
            has_image=bool(image_b64),
            stop_event=stop_event,
        ):
            generated_parts.append(piece)
            yield piece

        log.info("[TIMING] think_stream total: %.1fs", time.monotonic() - t0_total)

        cancelled = bool(stop_event and stop_event.is_set())
        if cancelled:
            return

        if not internal:
            final_text = " ".join(p.strip() for p in generated_parts if p.strip()).strip()
            if final_text and (not self.history or self.history[-1].get("role") != "assistant"):
                self.history.append({"role": "assistant", "content": final_text})
                self.memory.save_history(self.history)

            threading.Thread(
                target=self.learner.learn_async, args=(user_text,), daemon=True
            ).start()

    def think(self, user_text: str, image_b64: str | None = None, internal: bool = False) -> str:
        """Versão não-streaming — para uso interno (resumos, OCR, etc.)."""
        call_history = self.history.copy()
        message: dict = {"role": "user", "content": user_text}
        if image_b64:
            message = {
                "role":    "user",
                "content": user_text or "O que você vê nessa imagem?",
                "images":  [image_b64],
            }

        if internal:
            call_history.append(message)
        else:
            self.history.append(message)
            self._trim_history()
            call_history = self.history

        search_context = ""
        if self.searcher.should_search_preemptive(user_text):
            query          = self.searcher.build_query(user_text)
            result         = self.searcher.search(query)
            search_context = self.searcher.format_for_prompt(result)

        reply = self._call_llm(self._build_system_prompt(search_context), call_history, has_image=bool(image_b64))

        if not search_context and self.searcher.should_search_reactive(reply):
            query  = self.searcher.build_query(user_text)
            result = self.searcher.search(query)
            sc     = self.searcher.format_for_prompt(result)
            follow = call_history + [
                {"role": "assistant", "content": reply},
                {"role": "user", "content": "Busquei na web:" + sc + "\nAgora me responde com isso."},
            ]
            reply = self._call_llm(self._build_system_prompt(), follow)

        if not internal:
            self.history.append({"role": "assistant", "content": reply})
            self.memory.save_history(self.history)

            threading.Thread(
                target=self.learner.learn_async, args=(user_text,), daemon=True
            ).start()

        return reply

    @property
    def active_model(self) -> str:
        return self._active

    @property
    def using_fallback(self) -> bool:
        return self._using_fallback

    def remember_note(self, note: str):
        self.memory.add_note(note)

    def clear_history(self):
        self.history = []
        self.memory.clear_history()

    def forget_everything(self):
        self.history = []
        self.memory.clear_history()
        self.memory.forget_notes()
