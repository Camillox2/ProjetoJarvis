"""
Sistema de plugins/skills dinâmicos.
Carrega .py de uma pasta skills/ e registra handlers de comandos.
Suporta hot-reload: se o arquivo mudar, recarrega automaticamente.

Cada skill é um .py com:
  TRIGGERS: list[str]  — frases que ativam o skill
  def handle(text: str, ctx: dict) -> str  — processa e retorna resposta
  NAME: str  (opcional) — nome exibido
  DESCRIPTION: str  (opcional) — descrição
"""

import importlib
import importlib.util
import os
import time
import threading
from pathlib import Path
from typing import Callable
from keilinks.log import get_logger

log = get_logger("skills")

SKILLS_DIR = Path("skills")


class Skill:
    def __init__(self, name: str, path: Path, triggers: list[str],
                 handler: Callable, description: str = ""):
        self.name        = name
        self.path        = path
        self.triggers    = triggers
        self.handler     = handler
        self.description = description
        self.mtime       = path.stat().st_mtime


class SkillLoader:
    def __init__(self, skills_dir: str = "skills"):
        self._dir = Path(skills_dir)
        self._dir.mkdir(exist_ok=True)
        self._skills: dict[str, Skill] = {}
        self._ctx: dict = {}  # contexto compartilhado com skills
        self._watcher_thread: threading.Thread | None = None
        self._running = False
        self._load_all()

    def set_context(self, ctx: dict):
        """Define o contexto que skills podem acessar (pc, media, brain, etc.)."""
        self._ctx = ctx

    def _load_all(self):
        """Carrega todos os .py da pasta de skills."""
        if not self._dir.exists():
            return
        for py in self._dir.glob("*.py"):
            if py.name.startswith("_"):
                continue
            self._load_skill(py)
        if self._skills:
            log.info("Skills carregados: %s", ", ".join(self._skills.keys()))

    def _load_skill(self, path: Path) -> bool:
        try:
            spec = importlib.util.spec_from_file_location(
                f"skills.{path.stem}", str(path)
            )
            if not spec or not spec.loader:
                return False
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            triggers = getattr(module, "TRIGGERS", None)
            handler  = getattr(module, "handle", None)
            if not triggers or not handler:
                log.warning("Skill %s ignorada: precisa ter TRIGGERS e handle().", path.name)
                return False

            name = getattr(module, "NAME", path.stem)
            desc = getattr(module, "DESCRIPTION", "")

            self._skills[path.stem] = Skill(
                name=name, path=path, triggers=triggers,
                handler=handler, description=desc,
            )
            log.debug("Skill '%s' carregado (%d triggers).", name, len(triggers))
            return True
        except Exception as e:
            log.error("Erro ao carregar skill %s: %s", path.name, e)
            return False

    def _reload_skill(self, name: str):
        """Recarrega um skill se o arquivo mudou."""
        skill = self._skills.get(name)
        if not skill or not skill.path.exists():
            return
        current_mtime = skill.path.stat().st_mtime
        if current_mtime > skill.mtime:
            log.info("Recarregando skill '%s'...", name)
            self._load_skill(skill.path)

    def try_handle(self, text: str) -> str | None:
        """Tenta processar o texto com algum skill. Retorna None se nenhum match."""
        t = text.lower()
        for name, skill in self._skills.items():
            # Checa se o arquivo mudou (hot-reload)
            self._reload_skill(name)
            for trigger in skill.triggers:
                if trigger in t:
                    try:
                        result = skill.handler(text, self._ctx)
                        if result:
                            return result
                    except Exception as e:
                        log.error("Erro no skill '%s': %s", skill.name, e)
                        return f"Erro no skill {skill.name}: {e}"
        return None

    def list_skills(self) -> str:
        if not self._skills:
            return "Nenhum skill instalado."
        lines = ["Skills instalados:"]
        for name, skill in self._skills.items():
            desc = f" — {skill.description}" if skill.description else ""
            triggers_str = ", ".join(skill.triggers[:3])
            lines.append(f"  • {skill.name}{desc} (triggers: {triggers_str})")
        return "\n".join(lines)

    def start_watcher(self):
        """Inicia thread de monitoramento para hot-reload."""
        if self._running:
            return
        self._running = True
        self._watcher_thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._watcher_thread.start()

    def _watch_loop(self):
        while self._running:
            time.sleep(5.0)
            if not self._dir.exists():
                continue
            # Detecta novos arquivos
            current_files = {p.stem for p in self._dir.glob("*.py") if not p.name.startswith("_")}
            known_files   = set(self._skills.keys())
            new_files = current_files - known_files
            for stem in new_files:
                path = self._dir / f"{stem}.py"
                if self._load_skill(path):
                    log.info("Novo skill detectado: '%s'.", stem)
