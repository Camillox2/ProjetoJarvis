"""
Exporta conversas para Markdown.
Permite exportar o dia atual ou uma data específica.
"""

from datetime import datetime
from pathlib import Path
from keilinks.log import get_logger

log = get_logger("export")

EXPORT_DIR = Path("notas/conversas")

EXPORT_TRIGGERS = [
    "exporta a conversa", "exporta o histórico", "salva a conversa",
    "exporta a conversa de hoje", "exporta o chat",
]


class ConversationExporter:
    def __init__(self, history_db=None):
        self._history_db = history_db

    def export_today(self) -> str:
        return self.export_date(datetime.now().strftime("%Y-%m-%d"))

    def export_date(self, date_str: str) -> str:
        if not self._history_db:
            return "Histórico não disponível."
        msgs = self._history_db.search_by_date(date_str, limit=500)
        if not msgs:
            return f"Nenhuma conversa encontrada em {date_str}."
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        filename = EXPORT_DIR / f"conversa_{date_str}.md"

        lines = [f"# Conversa — {date_str}\n"]
        for m in msgs:
            ts = m.get("timestamp", "")
            hora = ts.split(" ")[1][:5] if " " in ts else ts[:5]
            role = "Você" if m["role"] == "user" else "Keilinks"
            lines.append(f"**[{hora}] {role}:** {m['content']}\n")

        filename.write_text("\n".join(lines), encoding="utf-8")
        log.info("Conversa exportada para %s", filename)
        return f"Conversa exportada para {filename}."

    def try_handle(self, text: str) -> str | None:
        t = text.lower()
        if not any(tr in t for tr in EXPORT_TRIGGERS):
            return None
        # Tenta extrair data
        import re
        m = re.search(r"(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{2,4}))?", text)
        if m:
            day, month = int(m.group(1)), int(m.group(2))
            year = int(m.group(3)) if m.group(3) else datetime.now().year
            if year < 100:
                year += 2000
            date_str = f"{year:04d}-{month:02d}-{day:02d}"
            return self.export_date(date_str)
        return self.export_today()
