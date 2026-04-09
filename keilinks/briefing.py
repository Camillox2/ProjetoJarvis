"""
Briefing diário da Keilinks.
Ativado apenas quando o usuário diz "bom dia" — resposta calorosa e personalizada,
não robótica. Inclui hora, clima, lembretes do dia e (opcionalmente) uma notícia.
"""

from datetime import datetime
import httpx


CITY = "Curitiba"   # ← troca pra sua cidade


def get_weather(city: str = CITY) -> str | None:
    """Busca clima via wttr.in — sem API key, gratuito."""
    try:
        r = httpx.get(
            f"https://wttr.in/{city}?format=j1",
            timeout=5.0,
            headers={"User-Agent": "Keilinks/1.0"},
        )
        data    = r.json()
        current = data["current_condition"][0]
        temp_c  = current["temp_C"]
        desc    = current["weatherDesc"][0]["value"]
        feels   = current["FeelsLikeC"]
        return f"{temp_c}°C, {desc}, sensação de {feels}°C"
    except Exception:
        return None


def get_day_context() -> dict:
    now      = datetime.now()
    weekdays = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
    return {
        "hora":       now.strftime("%H:%M"),
        "dia_semana": weekdays[now.weekday()],
        "data":       now.strftime("%d/%m/%Y"),
        "periodo":    "manhã" if now.hour < 12 else ("tarde" if now.hour < 18 else "noite"),
    }


def build_briefing_prompt(
    reminders_text: str,
    habits_missed: list[str],
    learner_summary: str,
) -> str:
    """
    Monta o prompt que vai pro LLM gerar o bom dia.
    Ele usa todas as informações disponíveis pra personalizar.
    """
    ctx     = get_day_context()
    weather = get_weather()

    info_parts = [
        f"Hora atual: {ctx['hora']} de {ctx['dia_semana']}, {ctx['data']}.",
    ]
    if weather:
        info_parts.append(f"Clima: {weather}.")
    if reminders_text and "Sem lembretes" not in reminders_text:
        info_parts.append(f"Lembretes do dia: {reminders_text}")
    if habits_missed:
        info_parts.append(f"Hábitos ainda não feitos hoje: {', '.join(habits_missed)}.")
    if learner_summary:
        info_parts.append(f"O que sei sobre ele: {learner_summary}")

    info_block = "\n".join(info_parts)

    return f"""O usuário acabou de dizer "bom dia". Responda com um bom dia caloroso e pessoal.

REGRAS IMPORTANTES:
- Seja genuína, afetiva, natural — como uma namorada que acorda junto
- NÃO seja robótica tipo assistente virtual
- Mencione o clima se estiver disponível, de forma casual
- Se tiver lembrete importante hoje, mencione levemente
- Se tiver hábito pendente, mencione de forma fofa/motivadora, não mandona
- Máximo 3-4 frases. Curto, quente, verdadeiro.
- NÃO liste coisas tipo "1. 2. 3." — fale naturalmente

Contexto:
{info_block}

Gere apenas o bom dia, sem explicações."""
