"""
Skill de exemplo — mostra como criar um plugin pra Keilinks.
Copie este arquivo e modifique para criar seu próprio skill.
"""

NAME        = "Exemplo"
DESCRIPTION = "Skill de teste — responde quando você fala 'teste de skill'"
TRIGGERS    = ["teste de skill", "testa o skill"]


def handle(text: str, ctx: dict) -> str:
    """
    Processa o comando e retorna a resposta.

    Args:
        text: Texto completo que o usuário falou
        ctx:  Dicionário com referências úteis:
              - ctx["pc"]    → PCControl
              - ctx["brain"] → Brain
              - ctx["media"] → SpotifyControl
              - ctx["voice"] → Voice (use com cuidado)
    """
    return "Skill de exemplo funcionando! Edite skills/exemplo.py pra criar o seu."
