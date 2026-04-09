"""
Sistema de notas por voz.
"Salva isso aqui", "cria uma nota sobre X" → salva em Markdown
compatível com Obsidian.

Exporta para pasta configurável (vault do Obsidian).
"""

import re
from datetime import datetime
from pathlib import Path
from keilinks.log import get_logger

log = get_logger("notes")


NOTE_TRIGGERS = [
    "salva isso", "cria uma nota", "anota isso", "nota sobre",
    "escreve isso", "guarda essa nota", "nova nota",
    "salva uma nota", "faz uma nota",
]

LIST_NOTE_TRIGGERS = [
    "minhas notas", "lista as notas", "quais notas", "mostra as notas",
]

SEARCH_NOTE_TRIGGERS = [
    "busca nas notas", "procura nas notas", "tem alguma nota sobre",
]


class NoteManager:
    def __init__(self, notes_dir: str = "notas", obsidian_vault: str = ""):
        """
        notes_dir: pasta local para salvar notas.
        obsidian_vault: caminho do vault Obsidian (se vazio, não exporta).
        """
        self._notes_dir = Path(notes_dir)
        self._notes_dir.mkdir(exist_ok=True)

        self._obsidian_vault = Path(obsidian_vault) if obsidian_vault else None
        if self._obsidian_vault:
            keilinks_folder = self._obsidian_vault / "Keilinks"
            keilinks_folder.mkdir(parents=True, exist_ok=True)
            log.info("Obsidian vault: %s", self._obsidian_vault)

    # ─── Criar nota ───────────────────────────────────────────────────────────
    def create_note(self, content: str, title: str = "") -> str:
        """
        Cria nota em Markdown. Se title vazio, gera automaticamente.
        """
        now = datetime.now()

        if not title:
            # Gera título a partir das primeiras palavras
            words = content.split()[:6]
            title = " ".join(words)
            if len(words) == 6:
                title += "..."

        # Sanitiza nome do arquivo
        safe_name = re.sub(r'[<>:"/\\|?*]', '', title)[:80].strip()
        if not safe_name:
            safe_name = now.strftime("Nota_%Y%m%d_%H%M%S")

        filename = f"{safe_name}.md"

        # Conteúdo em Markdown com frontmatter YAML
        md = f"""---
date: {now.strftime('%Y-%m-%d %H:%M')}
tags: [keilinks, voice-note]
---

# {title}

{content}

---
*Nota criada por voz via Keilinks em {now.strftime('%d/%m/%Y às %H:%M')}*
"""

        # Salva localmente
        local_path = self._notes_dir / filename
        local_path.write_text(md, encoding="utf-8")
        log.info("Nota salva: %s", local_path)

        # Exporta para Obsidian se configurado
        if self._obsidian_vault:
            obs_path = self._obsidian_vault / "Keilinks" / filename
            obs_path.write_text(md, encoding="utf-8")
            log.info("Exportada para Obsidian: %s", obs_path)
            return f"Nota salva e exportada pro Obsidian: {title}"

        return f"Nota salva: {title}"

    # ─── Listar notas ─────────────────────────────────────────────────────────
    def list_notes(self, limit: int = 10) -> str:
        notes = sorted(self._notes_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not notes:
            return "Nenhuma nota salva."

        lines = []
        for n in notes[:limit]:
            name = n.stem
            mtime = datetime.fromtimestamp(n.stat().st_mtime).strftime("%d/%m %H:%M")
            lines.append(f"- {name} ({mtime})")

        total = len(notes)
        header = f"{total} nota(s). Mais recentes:" if total > limit else f"{total} nota(s):"
        return header + "\n" + "\n".join(lines)

    # ─── Buscar nas notas ─────────────────────────────────────────────────────
    def search_notes(self, query: str, limit: int = 5) -> str:
        """Busca texto dentro das notas."""
        results = []
        query_lower = query.lower()

        for note_path in self._notes_dir.glob("*.md"):
            try:
                content = note_path.read_text(encoding="utf-8")
                if query_lower in content.lower():
                    # Pega um trecho relevante
                    idx = content.lower().find(query_lower)
                    start = max(0, idx - 50)
                    end   = min(len(content), idx + len(query) + 100)
                    snippet = content[start:end].replace("\n", " ").strip()
                    results.append(f"- **{note_path.stem}**: ...{snippet}...")
            except Exception:
                continue

        if not results:
            return f"Nenhuma nota encontrada com '{query}'."

        return f"Encontrei {len(results)} nota(s):\n" + "\n".join(results[:limit])

    # ─── Ler nota ─────────────────────────────────────────────────────────────
    def read_note(self, name: str) -> str:
        """Lê o conteúdo de uma nota pelo nome (parcial)."""
        for note_path in self._notes_dir.glob("*.md"):
            if name.lower() in note_path.stem.lower():
                content = note_path.read_text(encoding="utf-8")
                # Remove frontmatter
                if content.startswith("---"):
                    end = content.find("---", 3)
                    if end != -1:
                        content = content[end + 3:].strip()
                return content

        return f"Nota '{name}' não encontrada."

    # ─── Handler para main ────────────────────────────────────────────────────
    def try_handle(self, text: str) -> str | None:
        t = text.lower()

        # Buscar
        for tr in SEARCH_NOTE_TRIGGERS:
            if tr in t:
                query = t[t.index(tr) + len(tr):].strip()
                if query:
                    return self.search_notes(query)
                return "Sobre o que você quer buscar?"

        # Listar
        if any(tr in t for tr in LIST_NOTE_TRIGGERS):
            return self.list_notes()

        # Criar
        for tr in NOTE_TRIGGERS:
            if tr in t:
                content = text[t.index(tr) + len(tr):].strip()
                if content:
                    return self.create_note(content)
                return "Fala o conteúdo da nota."

        return None
