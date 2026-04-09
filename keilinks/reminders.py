"""
Sistema de lembretes com alarme real.
"Me lembra às 18h de ligar pra mãe" → dispara na hora certa.
"""

import json
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

REMINDERS_FILE = Path("memoria/lembretes.json")


class ReminderManager:
    def __init__(self, on_reminder: Callable[[str], None]):
        """on_reminder(mensagem): chamado quando o lembrete dispara."""
        self._on_reminder = on_reminder
        self._reminders: list[dict] = self._load()
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._tick, daemon=True)
        self._thread.start()

    # ─── Parse de tempo natural ───────────────────────────────────────────────
    def parse_reminder(self, text: str) -> tuple[datetime | None, str]:
        """
        Extrai horário e mensagem do texto.
        Exemplos:
          "me lembra às 18h de ligar pra mãe"
          "lembra daqui a 30 minutos de tomar água"
          "me lembra amanhã às 9h da reunião"
        """
        now = datetime.now()
        when = None
        msg  = text

        # daqui a N minutos/horas
        m = re.search(r"daqui\s+a?\s*(\d+)\s*(minuto|hora)s?", text, re.IGNORECASE)
        if m:
            n    = int(m.group(1))
            unit = m.group(2).lower()
            when = now + (timedelta(minutes=n) if "minuto" in unit else timedelta(hours=n))

        # às HH:MM ou às Xh
        if not when:
            m = re.search(r"\b(?:às|as|ao?s?)\s+(\d{1,2})(?::(\d{2}))?h?", text, re.IGNORECASE)
            if m:
                hour = int(m.group(1))
                minute = int(m.group(2)) if m.group(2) else 0
                when = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if when < now:
                    when += timedelta(days=1)  # assume amanhã se já passou

        # amanhã às X
        if not when:
            m = re.search(r"amanhã\s+(?:às|as)?\s*(\d{1,2})(?::(\d{2}))?h?", text, re.IGNORECASE)
            if m:
                hour   = int(m.group(1))
                minute = int(m.group(2)) if m.group(2) else 0
                when   = (now + timedelta(days=1)).replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )

        # Extrai a mensagem (parte depois de "de" ou "para")
        for sep in [" de ", " para ", " pra "]:
            if sep in text.lower():
                msg = text[text.lower().rfind(sep) + len(sep):].strip()
                break

        return when, msg

    # ─── CRUD ─────────────────────────────────────────────────────────────────
    def add(self, when: datetime, message: str) -> str:
        entry = {
            "id":      int(time.time() * 1000),
            "when":    when.isoformat(),
            "message": message,
            "done":    False,
        }
        with self._lock:
            self._reminders.append(entry)
            self._save()

        delta = when - datetime.now()
        mins  = int(delta.total_seconds() / 60)
        if mins < 60:
            return f"Anotado! Vou te lembrar em {mins} minutos: {message}"
        hours = mins // 60
        return f"Anotado! Vou te lembrar às {when.strftime('%H:%M')}: {message}"

    def list_reminders(self) -> str:
        with self._lock:
            pending = [r for r in self._reminders if not r["done"]]
        if not pending:
            return "Sem lembretes pendentes."
        lines = []
        for r in pending:
            dt  = datetime.fromisoformat(r["when"])
            lines.append(f"• {dt.strftime('%d/%m %H:%M')} — {r['message']}")
        return "\n".join(lines)

    def clear_done(self):
        with self._lock:
            self._reminders = [r for r in self._reminders if not r["done"]]
            self._save()

    # ─── Persistência ─────────────────────────────────────────────────────────
    def _load(self) -> list[dict]:
        REMINDERS_FILE.parent.mkdir(exist_ok=True)
        if REMINDERS_FILE.exists():
            try:
                return json.loads(REMINDERS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def _save(self):
        REMINDERS_FILE.write_text(
            json.dumps(self._reminders, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ─── Loop de verificação ──────────────────────────────────────────────────
    def _tick(self):
        while True:
            time.sleep(10)
            now = datetime.now()
            with self._lock:
                for r in self._reminders:
                    if r["done"]:
                        continue
                    if datetime.fromisoformat(r["when"]) <= now:
                        r["done"] = True
                        threading.Thread(
                            target=self._on_reminder,
                            args=(f"Lembrete: {r['message']}",),
                            daemon=True,
                        ).start()
                self._save()
