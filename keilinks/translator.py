"""
Tradução de tela: OCR + LLM.
"traduz o que tá na tela" → captura, extrai texto, traduz.
Também suporta tradução de texto falado diretamente.
"""

import re


TRANSLATE_TRIGGERS = [
    "traduz o que tá na tela", "traduz a tela", "traduz isso",
    "traduz esse texto", "que língua é essa", "o que significa",
    "me traduz", "traduz pra", "tradução de",
]

# Idiomas detectáveis no comando
LANG_MAP = {
    "inglês":    "inglês",
    "english":   "inglês",
    "espanhol":  "espanhol",
    "francês":   "francês",
    "alemão":    "alemão",
    "japonês":   "japonês",
    "coreano":   "coreano",
    "português": "português",
    "italiano":  "italiano",
}


def extract_target_language(text: str) -> str:
    """Detecta o idioma destino no comando. Default: português."""
    t = text.lower()
    for lang_key, lang_name in LANG_MAP.items():
        if f"para {lang_key}" in t or f"pra {lang_key}" in t:
            return lang_name
    return "português"


def build_translate_prompt(source_text: str, target_lang: str = "português") -> str:
    return (
        f"Traduza o texto abaixo para {target_lang}. "
        f"Se o texto for muito longo, traduza os trechos mais importantes. "
        f"Seja natural e fluido, não literal demais.\n\n"
        f"Texto:\n{source_text}"
    )


def is_translate_trigger(text: str) -> bool:
    t = text.lower()
    return any(tr in t for tr in TRANSLATE_TRIGGERS)
