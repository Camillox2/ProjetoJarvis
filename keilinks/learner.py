"""
Aprendizado passivo da Keilinks — extrai perfil do usuário em background.
Versão expandida: captura humor, nível de energia, horários de uso e padrões.
"""

import json
import threading
from datetime import datetime
from pathlib import Path
import httpx
from config import OLLAMA_HOST, LLM_FALLBACK
from keilinks.log import get_logger

log = get_logger("learner")

PROFILE_FILE = Path("memoria/perfil_usuario.json")

EXTRACTION_PROMPT = """Analise a mensagem abaixo e extraia informações sobre o usuário.
Responda APENAS com JSON válido neste formato (arrays vazios se não houver nada):
{{
  "personalidade": [],
  "gostos": [],
  "desgostos": [],
  "rotina": [],
  "objetivos": [],
  "contexto_profissional": [],
  "contexto_pessoal": [],
  "humor_detectado": "",
  "energia_detectada": "",
  "assuntos_frequentes": []
}}

Campos:
- humor_detectado: "animado", "cansado", "frustrado", "neutro", "feliz", "estressado" ou vazio
- energia_detectada: "alta", "baixa", "normal" ou vazio
- assuntos_frequentes: temas recorrentes que ele menciona

Seja conciso — máximo 1-2 itens por campo. Se não revelar nada, todos vazios.

Mensagem: "{text}"
"""


class Learner:
    def __init__(self):
        # Usa o modelo menor (4b) para não competir com o 8b durante conversa
        self.client  = httpx.Client(base_url=OLLAMA_HOST, timeout=30.0)
        self.profile = self._load_profile()
        self._usage_log: list[dict] = []   # log de horários de uso
        self._lock = threading.Lock()

    _DEFAULT_PROFILE = {
        "nome":                  None,
        "personalidade":         [],
        "gostos":                [],
        "desgostos":             [],
        "rotina":                [],
        "objetivos":             [],
        "contexto_profissional": [],
        "contexto_pessoal":      [],
        "assuntos_frequentes":   [],
        "padroes_humor":         {},
        "horarios_uso":          [],
        "ultima_atualizacao":    None,
    }

    def _load_profile(self) -> dict:
        PROFILE_FILE.parent.mkdir(exist_ok=True)
        # Sempre parte do default e mergeia o que existir em disco
        profile = dict(self._DEFAULT_PROFILE)
        for k, v in profile.items():
            if isinstance(v, (list, dict)):
                profile[k] = type(v)(v)  # cópia rasa
        if PROFILE_FILE.exists():
            try:
                saved = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
                if isinstance(saved, dict):
                    profile.update(saved)
            except Exception:
                pass
        return profile

    def _save_profile(self):
        with self._lock:
            self.profile["ultima_atualizacao"] = datetime.now().strftime("%d/%m/%Y %H:%M")
            PROFILE_FILE.write_text(
                json.dumps(self.profile, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def _extract_from_llm(self, text: str) -> dict | None:
        try:
            r = self.client.post("/api/chat", json={
                "model":    LLM_FALLBACK,   # 4b — rápido, não disputa VRAM com o 8b
                "messages": [{"role": "user", "content": EXTRACTION_PROMPT.format(text=text)}],
                "stream":   False,
                "options":  {"temperature": 0.1, "num_ctx": 1024},
            })
            r.raise_for_status()
            content = r.json()["message"]["content"].strip()
            start   = content.find("{")
            end     = content.rfind("}") + 1
            if start == -1 or end == 0:
                return None
            return json.loads(content[start:end])
        except Exception:
            return None

    def _merge(self, extracted: dict) -> bool:
        changed = False
        list_fields = ["personalidade", "gostos", "desgostos", "rotina",
                        "objetivos", "contexto_profissional", "contexto_pessoal",
                        "assuntos_frequentes"]

        for key in list_fields:
            for item in extracted.get(key, []):
                if item and item not in self.profile[key]:
                    self.profile[key].append(item)
                    changed = True
                    log.debug("%s: %s", key, item)

        # Humor por período do dia
        humor = extracted.get("humor_detectado", "").strip()
        if humor:
            hora    = datetime.now().hour
            periodo = "manhã" if hora < 12 else ("tarde" if hora < 18 else "noite")
            self.profile["padroes_humor"][periodo] = humor
            changed = True

        # Energia
        energia = extracted.get("energia_detectada", "").strip()
        if energia:
            log.debug("energia: %s", energia)

        return changed

    def _log_usage_time(self):
        """Registra o horário de uso para entender a rotina."""
        hora = datetime.now().strftime("%H:%M")
        if hora not in self.profile["horarios_uso"]:
            self.profile["horarios_uso"].append(hora)
            # Mantém só os últimos 50 registros únicos
            self.profile["horarios_uso"] = self.profile["horarios_uso"][-50:]

    def learn_async(self, text: str):
        self._log_usage_time()
        extracted = self._extract_from_llm(text)
        if extracted and self._merge(extracted):
            self._save_profile()

    def get_current_humor(self) -> str | None:
        hora    = datetime.now().hour
        periodo = "manhã" if hora < 12 else ("tarde" if hora < 18 else "noite")
        return self.profile.get("padroes_humor", {}).get(periodo)

    def get_profile_summary(self) -> str:
        lines = []
        fields = {
            "rotina":                "Rotina",
            "objetivos":             "Objetivos",
            "contexto_profissional": "Trabalho/Estudo",
            "contexto_pessoal":      "Vida pessoal",
        }
        for key, label in fields.items():
            items = self.profile.get(key, [])
            if items:
                lines.append(f"{label}: {', '.join(items[-3:])}")

        if not lines:
            return ""
        nome   = self.profile.get("nome")
        header = f"O nome dele é {nome}.\n" if nome else ""
        return header + "\n".join(lines)
