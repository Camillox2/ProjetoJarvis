import os

# ─── Modelos ───────────────────────────────────────────────────────────────────
OLLAMA_HOST  = "http://localhost:11434"
# Qwen 3.5 unifica texto e visão e evita swap constante entre modelos.
LLM_MODEL     = "qwen3.5:397b-cloud"
LLM_FALLBACKS = ["qwen3.5:9b", "qwen3.5:4b", "qwen3.5:2b", "qwen3.5:0.8b"]
# Compatibilidade com componentes antigos que ainda usam um único fallback.
LLM_FALLBACK  = LLM_FALLBACKS[0]
OLLAMA_KEEP_ALIVE = "30m"

# Tempo máximo de resposta antes de considerar "lento demais" (segundos)
LLM_TIMEOUT_SLOW  = 45.0

# Requisições bem-sucedidas no fallback antes de tentar voltar ao principal
LLM_RECOVER_AFTER = 5

# ─── STT (fala → texto) ────────────────────────────────────────────────────────
WHISPER_MODEL        = "medium"   # boot estável; na GPU já melhora tempo e precisão prática
WHISPER_LANGUAGE     = "pt"
WHISPER_COMPUTE_TYPE = "float16"

# ─── TTS (texto → fala) ────────────────────────────────────────────────────────
TTS_VOICE = "pt-BR-FranciscaNeural"
TTS_RATE  = "+5%"
TTS_PITCH = "+0Hz"

# ─── Câmera ───────────────────────────────────────────────────────────────────
CAMERA_INDEX   = 0
CAMERA_ENABLED = True

# ─── Áudio ────────────────────────────────────────────────────────────────────
SAMPLE_RATE       = 16000
SILENCE_THRESHOLD = 300    # reduzido: mic USB tem ganho menor
SILENCE_DURATION  = 1.2    # detecta fim de fala mais rápido
MAX_RECORD_SECS   = 30

# ─── Ativação por palmas ──────────────────────────────────────────────────────
CLAP_ENABLED                = True
CLAP_COUNT_TO_WAKE          = 2      # duas palmas rápidas ativam com menos falso positivo
CLAP_SEQUENCE_WINDOW_SECS   = 1.5    # janela máxima entre as palmas
CLAP_DEBOUNCE_SECS          = 0.12   # evita contar a mesma palma duas vezes
CLAP_COOLDOWN_SECS          = 1.5    # evita reativar logo depois
CLAP_PEAK_THRESHOLD         = 0.14   # pico mínimo normalizado — foi 0.18 mas cortava palmas reais
CLAP_STRONG_PEAK_THRESHOLD  = 0.30   # uma palma muito forte ativa sozinha
CLAP_RMS_THRESHOLD          = 0.010  # energia mínima
CLAP_CREST_MIN              = 3.5    # pico / rms — palmas têm crest 4-8, voz tem 2-4
CLAP_ACTIVE_RATIO_MAX       = 0.28   # palma é impulso curto — was 0.22, mas cortava palmas legítimas
CLAP_ONSET_THRESHOLD        = 0.09   # subida brusca — ajuda a separar de voz

# ─── Memória de conversa ──────────────────────────────────────────────────────
MAX_HISTORY_TURNS = 8

# ─── Conversa contínua ────────────────────────────────────────────────────────
# Após responder, Keilinks fica ouvindo por este tempo antes de voltar ao idle.
# Se o usuário falar nesse intervalo, continua a conversa sem precisar do wake word.
CONTINUOUS_LISTEN_TIMEOUT = 8.0    # segundos de silêncio antes de voltar pro idle
CONTINUOUS_MAX_TURNS      = 20     # máximo de turnos antes de forçar idle

# ─── Logging ──────────────────────────────────────────────────────────────────
LOG_LEVEL = "DEBUG"      # DEBUG | INFO | WARNING | ERROR
LOG_FILE  = "logs/keilinks.log"

# ─── Notas / Obsidian ────────────────────────────────────────────────────────
# Se OBSIDIAN_VAULT estiver definida como variável de ambiente, exporta notas pra lá.
# Exemplo: set OBSIDIAN_VAULT=C:\Users\vitor\ObsidianVault
NOTES_DIR = "notas"

# ─── Interface Web ────────────────────────────────────────────────────────────
WEB_PORT = 7865
# ─── Plugins/Skills ───────────────────────────────────────────────────────
SKILLS_DIR = "skills"

# ─── Calendário Google ────────────────────────────────────────────────────
CALENDAR_REMINDER_MINS = 15       # avisa N minutos antes do evento
CALENDAR_CHECK_INTERVAL = 120.0   # checa a cada N segundos