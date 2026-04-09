"""
Alarmes e temporizadores por voz.
"Acorda daqui a 20 minutos", "coloca um timer de 5 minutos",
"alarme às 7 da manhã" → toca som + fala.
"""

import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable
from keilinks.log import get_logger

log = get_logger("timer")

# Sons — usar pygame no callback
_ALARM_SOUND = Path("assets/alarm.wav")


TIMER_TRIGGERS = [
    "coloca um timer", "timer de", "temporizador de",
    "alarme daqui", "acorda daqui", "me acorda daqui",
    "alarme de", "me avisa em", "conta",
    "alarme às", "alarme as", "desperta às", "desperta as",
    "me acorda às", "me acorda as",
]


class TimerEntry:
    __slots__ = ("id", "label", "fire_at", "done", "_timer")

    def __init__(self, fire_at: datetime, label: str):
        self.id      = int(time.time() * 1000)
        self.fire_at = fire_at
        self.label   = label
        self.done    = False
        self._timer: threading.Timer | None = None


class TimerManager:
    def __init__(self, on_fire: Callable[[str], None]):
        """
        on_fire(mensagem): chamado quando o timer/alarme dispara.
        """
        self._on_fire = on_fire
        self._timers: list[TimerEntry] = []
        self._lock = threading.Lock()

    # ─── Parse natural ────────────────────────────────────────────────────────
    def parse(self, text: str) -> tuple[datetime | None, str]:
        """
        Extrai hora/duração do texto. Retorna (datetime_alvo, label).
        """
        now = datetime.now()
        t   = text.lower()

        # "daqui a N minutos/horas/segundos"
        m = re.search(
            r"(?:daqui\s+a?\s*|timer\s+de\s*|temporizador\s+de\s*|em\s+)"
            r"(\d+)\s*(segundo|minuto|hora|min|seg|hr)s?",
            t,
        )
        if m:
            n    = int(m.group(1))
            unit = m.group(2)
            if unit.startswith("seg"):
                delta = timedelta(seconds=n)
            elif unit.startswith("hr") or unit.startswith("hora"):
                delta = timedelta(hours=n)
            else:
                delta = timedelta(minutes=n)
            label = self._extract_label(text) or f"Timer de {n} {m.group(2)}(s)"
            return now + delta, label

        # "às HH:MM" ou "às Xh"
        m = re.search(r"(?:às|as)\s+(\d{1,2})(?::(\d{2}))?h?", t)
        if m:
            hour   = int(m.group(1))
            minute = int(m.group(2)) if m.group(2) else 0
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            label = self._extract_label(text) or f"Alarme às {hour}:{minute:02d}"
            return target, label

        # "N minutos" isolado (ex: "conta 5 minutos")
        m = re.search(r"(\d+)\s*(minuto|hora|segundo|min|seg|hr)s?", t)
        if m:
            n    = int(m.group(1))
            unit = m.group(2)
            if unit.startswith("seg"):
                delta = timedelta(seconds=n)
            elif unit.startswith("hr") or unit.startswith("hora"):
                delta = timedelta(hours=n)
            else:
                delta = timedelta(minutes=n)
            label = self._extract_label(text) or f"Timer de {n} {m.group(2)}(s)"
            return now + delta, label

        return None, ""

    @staticmethod
    def _extract_label(text: str) -> str:
        """Tenta extrair um label descritivo do texto."""
        for sep in [" pra ", " para ", " de "]:
            idx = text.lower().rfind(sep)
            if idx != -1:
                after = text[idx + len(sep):].strip()
                # Evita pegar unidades de tempo como label
                if after and not re.match(r"^\d+\s*(min|seg|hora|segundo|minuto)", after.lower()):
                    return after
        return ""

    # ─── Criar timer ──────────────────────────────────────────────────────────
    def add(self, fire_at: datetime, label: str) -> str:
        entry = TimerEntry(fire_at, label)
        delay = max(0.0, (fire_at - datetime.now()).total_seconds())

        def _fire():
            entry.done = True
            log.info("Timer disparou: %s", label)
            self._on_fire(f"⏰ {label}")

        entry._timer = threading.Timer(delay, _fire)
        entry._timer.daemon = True
        entry._timer.start()

        with self._lock:
            self._timers.append(entry)

        if delay < 60:
            return f"Timer de {int(delay)} segundos configurado."
        elif delay < 3600:
            return f"Timer de {int(delay / 60)} minutos configurado."
        else:
            return f"Alarme configurado para {fire_at.strftime('%H:%M')}."

    # ─── Cancelar ─────────────────────────────────────────────────────────────
    def cancel_last(self) -> str:
        with self._lock:
            pending = [t for t in self._timers if not t.done]
            if not pending:
                return "Nenhum timer ativo."
            last = pending[-1]
            if last._timer:
                last._timer.cancel()
            last.done = True
            return f"Timer cancelado: {last.label}"

    def cancel_all(self) -> str:
        with self._lock:
            count = 0
            for t in self._timers:
                if not t.done and t._timer:
                    t._timer.cancel()
                    t.done = True
                    count += 1
            return f"{count} timer(s) cancelado(s)." if count else "Nenhum timer ativo."

    # ─── Listar ───────────────────────────────────────────────────────────────
    def list_timers(self) -> str:
        with self._lock:
            pending = [t for t in self._timers if not t.done]
        if not pending:
            return "Nenhum timer ativo."
        lines = []
        for t in pending:
            remaining = (t.fire_at - datetime.now()).total_seconds()
            if remaining < 60:
                r = f"{int(remaining)}s"
            elif remaining < 3600:
                r = f"{int(remaining / 60)}min"
            else:
                r = f"{int(remaining / 3600)}h{int((remaining % 3600) / 60)}min"
            lines.append(f"- {t.label} (falta {r})")
        return "Timers ativos:\n" + "\n".join(lines)

    # ─── Handler para main ────────────────────────────────────────────────────
    def try_handle(self, text: str) -> str | None:
        t = text.lower()

        # Cancelar
        if "cancela" in t and ("timer" in t or "alarme" in t):
            if "todos" in t or "tudo" in t:
                return self.cancel_all()
            return self.cancel_last()

        # Listar
        if ("quais" in t or "lista" in t) and ("timer" in t or "alarme" in t):
            return self.list_timers()

        # Criar
        if any(tr in t for tr in TIMER_TRIGGERS):
            fire_at, label = self.parse(text)
            if fire_at:
                return self.add(fire_at, label)
            return "Não entendi o tempo. Fala algo como 'timer de 10 minutos'."

        return None
