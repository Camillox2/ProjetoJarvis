"""
Rastreador de hábitos da Keilinks.
"fiz exercício hoje", "bebi água", "li 30 minutos" → ela registra, acompanha e cobra.
"""

import json
import re
from datetime import datetime, date
from pathlib import Path
from typing import Callable

HABITS_FILE = Path("memoria/habitos.json")


class HabitTracker:
    def __init__(self, on_nudge: Callable[[str], None] | None = None):
        """on_nudge: callback quando ela quer te cobrar um hábito."""
        self._on_nudge = on_nudge
        self.data      = self._load()

    # ─── CRUD de hábitos ──────────────────────────────────────────────────────
    def add_habit(self, name: str, frequency: str = "daily") -> str:
        """Registra um novo hábito pra rastrear."""
        slug = name.lower().strip()
        if slug not in self.data["habits"]:
            self.data["habits"][slug] = {
                "name":      name,
                "frequency": frequency,
                "streak":    0,
                "best":      0,
                "log":       [],
            }
            self._save()
            return f"Certo, vou acompanhar '{name}' pra você."
        return f"Já tô de olho em '{name}'."

    def log_habit(self, raw_text: str) -> str:
        """
        Tenta identificar qual hábito foi completado pelo texto e registra.
        Retorna mensagem de resposta.
        """
        today = str(date.today())
        matched = []

        for slug, h in self.data["habits"].items():
            if slug in raw_text.lower() or any(w in raw_text.lower() for w in slug.split()):
                log = h["log"]
                if today not in log:
                    log.append(today)
                    h["log"] = log[-90:]   # guarda últimos 90 dias

                    # Calcula streak
                    streak = self._calc_streak(log)
                    h["streak"] = streak
                    h["best"]   = max(h["best"], streak)
                    matched.append((h["name"], streak, h["best"]))

        if not matched:
            return None   # não era um log de hábito

        self._save()
        responses = []
        for name, streak, best in matched:
            if streak == 1:
                responses.append(f"'{name}' marcado hoje.")
            elif streak == best:
                responses.append(f"'{name}' — {streak} dias seguidos! Recorde seu.")
            else:
                responses.append(f"'{name}' — {streak} dias seguidos. Continua assim.")

        return " ".join(responses)

    def status(self) -> str:
        """Resumo de todos os hábitos."""
        if not self.data["habits"]:
            return "Nenhum hábito cadastrado ainda. Me fala o que quer acompanhar."

        today   = str(date.today())
        lines   = []
        pending = []

        for slug, h in self.data["habits"].items():
            done = today in h["log"]
            icon = "✓" if done else "○"
            lines.append(f"{icon} {h['name']} — {h['streak']} dias seguidos")
            if not done:
                pending.append(h["name"])

        summary = "\n".join(lines)
        if pending:
            summary += f"\n\nAinda falta: {', '.join(pending)}."
        return summary

    def missed_today(self) -> list[str]:
        """Retorna hábitos não registrados hoje."""
        today = str(date.today())
        return [
            h["name"]
            for h in self.data["habits"].values()
            if today not in h["log"]
        ]

    # ─── Detecção no texto livre ──────────────────────────────────────────────
    LOG_TRIGGERS = [
        "fiz", "fiz o", "completei", "terminei", "acabei de", "fiz meu",
        "bebi", "comi", "li", "estudei", "treinei", "meditei",
        "exercício", "academia", "corri", "caminhei",
    ]
    ADD_TRIGGERS  = [
        "quero acompanhar", "rastreia", "monitora", "me cobra",
        "adiciona o hábito", "novo hábito",
    ]
    STATUS_TRIGGERS = [
        "hábitos", "meus hábitos", "como tô nos hábitos",
        "status dos hábitos", "como estão meus hábitos",
    ]

    def try_handle(self, text: str) -> str | None:
        t = text.lower()

        if any(tr in t for tr in self.STATUS_TRIGGERS):
            return self.status()

        for tr in self.ADD_TRIGGERS:
            if tr in t:
                name = t.split(tr, 1)[-1].strip().split("\n")[0][:40]
                return self.add_habit(name)

        if any(tr in t for tr in self.LOG_TRIGGERS):
            result = self.log_habit(text)
            if result:
                return result

        return None

    # ─── Utilidades ───────────────────────────────────────────────────────────
    def _calc_streak(self, log: list[str]) -> int:
        if not log:
            return 0
        sorted_log = sorted(log, reverse=True)
        streak     = 0
        check      = date.today()
        for entry in sorted_log:
            if str(check) == entry:
                streak += 1
                from datetime import timedelta
                check -= timedelta(days=1)
            else:
                break
        return streak

    def _load(self) -> dict:
        HABITS_FILE.parent.mkdir(exist_ok=True)
        if HABITS_FILE.exists():
            try:
                return json.loads(HABITS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"habits": {}}

    def _save(self):
        HABITS_FILE.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
