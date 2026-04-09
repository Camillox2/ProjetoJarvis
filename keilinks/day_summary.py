"""
Resumo de dia — consolida informações do dia inteiro:
tempo de estudo, hábitos, lembretes, humor, assuntos discutidos.
"""

from datetime import datetime
from keilinks.log import get_logger

log = get_logger("summary")

DAY_SUMMARY_TRIGGERS = [
    "como foi meu dia", "resumo do dia", "resume meu dia",
    "o que fiz hoje", "como foi hoje",
]


class DaySummarizer:
    def __init__(self, history_db=None, study=None, habits=None,
                 reminders=None, mood_det=None, learner=None):
        self._history_db = history_db
        self._study      = study
        self._habits     = habits
        self._reminders  = reminders
        self._mood       = mood_det
        self._learner    = learner

    def build_summary_prompt(self) -> str:
        """Constrói um prompt para o LLM gerar um resumo natural do dia."""
        today = datetime.now().strftime("%Y-%m-%d")
        sections = []

        # Mensagens de hoje
        if self._history_db:
            msgs = self._history_db.search_by_date(today, limit=100)
            if msgs:
                user_msgs = [m for m in msgs if m["role"] == "user"]
                sections.append(f"Mensagens trocadas hoje: {len(msgs)} "
                                f"({len(user_msgs)} do usuário)")
                # Extrai assuntos (últimas 10 mensagens do usuário)
                recent_topics = [m["content"][:100] for m in user_msgs[-10:]]
                if recent_topics:
                    sections.append("Ultimos assuntos falados:\n" +
                                    "\n".join(f"- {t}" for t in recent_topics))

        # Estudo
        if self._study and self._study.is_active():
            sections.append(f"Modo estudo: {self._study.get_stats()}")
        elif self._study:
            stats = self._study.get_stats()
            if "Nenhuma" not in stats:
                sections.append(f"Estudo: {stats}")

        # Hábitos
        if self._habits:
            try:
                missed = self._habits.missed_today()
                if missed:
                    sections.append(f"Hábitos não feitos hoje: {missed}")
                completed = self._habits.completed_today()
                if completed:
                    sections.append(f"Hábitos completados: {completed}")
            except Exception:
                pass

        # Humor predominante
        if self._mood:
            trend = self._mood.get_trend(n=10)
            if trend and trend != "neutro":
                sections.append(f"Humor predominante: {trend}")

        # Perfil recente
        if self._learner:
            humor = self._learner.get_current_humor()
            if humor:
                sections.append(f"Humor do período: {humor}")

        if not sections:
            return ("O usuário perguntou como foi o dia dele. "
                    "Não tem muitos dados ainda. Faz um comentário breve e carinhoso.")

        context = "\n".join(sections)
        return (
            "O usuário quer um resumo do dia dele. Com base nos dados abaixo, "
            "faz um resumo conversacional, carinhoso e útil. "
            "Menciona pontos positivos e sugere melhorias se fizer sentido.\n\n"
            f"─── DADOS DO DIA ({today}) ──────\n{context}\n─────────────────────────────"
        )

    def try_handle(self, text: str) -> bool:
        """Retorna True se esse texto é uma trigger de resumo de dia."""
        t = text.lower()
        return any(tr in t for tr in DAY_SUMMARY_TRIGGERS)
