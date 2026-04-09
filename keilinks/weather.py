"""
Clima em tempo real via wttr.in (gratuito, sem API key).
Detecta cidade no texto do usuário e retorna condições atuais.
"""

import re
import httpx
from keilinks.log import get_logger

log = get_logger("weather")

WEATHER_TRIGGERS = [
    "clima", "tempo", "temperatura", "previsão do tempo", "previsao do tempo",
    "vai chover", "vai fazer frio", "vai fazer calor", "tá chovendo",
    "como está o tempo", "como tá o tempo", "como está o clima", "como tá o clima",
]

# Cidades brasileiras comuns para detectar no texto
_CITY_PATTERN = re.compile(
    r"\bem\s+([A-ZÀ-Ú][a-zà-ú]+(?:\s+[A-ZÀ-Ú][a-zà-ú]+)*)",
    re.IGNORECASE,
)

_DEFAULT_CITY = "Curitiba"

_CONDITION_PT = {
    "Sunny": "ensolarado", "Clear": "céu limpo", "Partly cloudy": "parcialmente nublado",
    "Cloudy": "nublado", "Overcast": "encoberto", "Mist": "com neblina",
    "Fog": "com névoa", "Freezing fog": "com névoa congelante",
    "Patchy rain possible": "possibilidade de chuva", "Rain": "com chuva",
    "Light rain": "chuva fraca", "Heavy rain": "chuva forte",
    "Thundery outbreaks possible": "possibilidade de trovoada",
    "Blizzard": "tempestade de neve", "Snow": "nevando",
    "Sleet": "chuva com neve", "Drizzle": "garoa",
}


class WeatherService:
    def __init__(self, default_city: str = _DEFAULT_CITY):
        self._default_city = default_city
        self._client = httpx.Client(timeout=6.0)

    def _extract_city(self, text: str) -> str:
        m = _CITY_PATTERN.search(text)
        if m:
            return m.group(1).strip()
        return self._default_city

    def get_current(self, city: str) -> str | None:
        """Busca clima atual via wttr.in. Retorna texto formatado ou None."""
        try:
            url = f"https://wttr.in/{city.replace(' ', '+')}?format=j1&lang=pt"
            r = self._client.get(url)
            r.raise_for_status()
            data = r.json()

            current = data["current_condition"][0]
            temp_c  = current["temp_C"]
            feels   = current["FeelsLikeC"]
            humidity = current["humidity"]
            wind_kmh = current["windspeedKmph"]
            desc_en  = current.get("weatherDesc", [{}])[0].get("value", "")
            desc_pt  = _CONDITION_PT.get(desc_en, desc_en.lower())

            # Previsão de hoje (máx/mín)
            today = data["weather"][0]
            max_c = today["maxtempC"]
            min_c = today["mintempC"]

            # Chance de chuva
            hourly = today.get("hourly", [])
            rain_chance = max((int(h.get("chanceofrain", 0)) for h in hourly), default=0)

            result = (
                f"Em {city} agora: {temp_c}°C, sensação de {feels}°C, {desc_pt}. "
                f"Hoje: máxima {max_c}°C, mínima {min_c}°C, umidade {humidity}%"
            )
            if rain_chance > 30:
                result += f", {rain_chance}% de chance de chuva"
            if int(wind_kmh) > 20:
                result += f", vento a {wind_kmh}km/h"
            result += "."
            return result

        except httpx.TimeoutException:
            log.warning("wttr.in timeout para %s", city)
            return None
        except Exception as e:
            log.error("Erro ao buscar clima: %s", e)
            return None

    def try_handle(self, text: str) -> str | None:
        """Retorna resposta de clima se for trigger, None caso contrário."""
        t = text.lower()
        if not any(tr in t for tr in WEATHER_TRIGGERS):
            return None
        city = self._extract_city(text)
        log.info("Buscando clima em %s...", city)
        result = self.get_current(city)
        if result:
            return result
        return f"Não consegui buscar o clima de {city} agora. Tenta de novo em instantes."
