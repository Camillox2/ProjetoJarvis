"""
Memória persistente: salva o histórico de conversas em disco.
A Keilinks lembra o que você falou mesmo depois de fechar o programa.
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path

MEMORY_DIR  = Path("memoria")
HISTORY_FILE = MEMORY_DIR / "historico.json"
NOTES_FILE   = MEMORY_DIR / "notas.json"   # coisas que o usuário pediu pra lembrar

_INTERNAL_USER_PATTERNS = (
    "o usuário quer ",
    "o usuário perguntou ",
    "o usuário pediu ",
    "busquei na web:",
)
_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002700-\U000027BF"
    "\U0001F900-\U0001F9FF"
    "\U00002600-\U000026FF"
    "\uFE0F"
    "]+",
    flags=re.UNICODE,
)


class Memory:
    def __init__(self):
        MEMORY_DIR.mkdir(exist_ok=True)
        self.history: list[dict] = self._load_history()
        self.notes: list[str]    = self._load_notes()

    # ─── Histórico de conversa ────────────────────────────────────────────────
    def _load_history(self) -> list[dict]:
        if HISTORY_FILE.exists():
            try:
                raw = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
                clean = self._sanitize_history(raw)
                if clean != raw:
                    self.save_history(clean)
                return clean
            except Exception:
                return []
        return []

    def save_history(self, history: list[dict]):
        history = self._sanitize_history(history)
        HISTORY_FILE.write_text(
            json.dumps(history, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _sanitize_history(self, history: list[dict]) -> list[dict]:
        if not isinstance(history, list):
            return []

        clean: list[dict] = []
        skip_next_assistant = False

        for msg in history:
            if not isinstance(msg, dict):
                continue

            role = msg.get("role")
            content = str(msg.get("content", "")).strip()
            if role not in ("user", "assistant") or not content:
                continue

            lower = content.lower()
            if role == "user" and any(lower.startswith(p) for p in _INTERNAL_USER_PATTERNS):
                skip_next_assistant = True
                continue

            if role == "assistant":
                if skip_next_assistant:
                    skip_next_assistant = False
                    continue
                if _EMOJI_RE.search(content) or "(PS:" in content or "abraço virtual" in lower:
                    continue

            clean.append({"role": role, "content": content})

        return clean[-12:]

    def clear_history(self):
        self.history = []
        if HISTORY_FILE.exists():
            HISTORY_FILE.unlink()

    # ─── Notas / lembranças ───────────────────────────────────────────────────
    def _load_notes(self) -> list[str]:
        if NOTES_FILE.exists():
            try:
                return json.loads(NOTES_FILE.read_text(encoding="utf-8"))
            except Exception:
                return []
        return []

    def add_note(self, note: str):
        entry = f"[{datetime.now().strftime('%d/%m/%Y')}] {note}"
        self.notes.append(entry)
        NOTES_FILE.write_text(
            json.dumps(self.notes, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_notes_as_text(self) -> str:
        if not self.notes:
            return ""
        return "Coisas que você me pediu pra lembrar:\n" + "\n".join(f"- {n}" for n in self.notes)

    def forget_notes(self):
        self.notes = []
        if NOTES_FILE.exists():
            NOTES_FILE.unlink()
