import os

# ─── Modelos ───────────────────────────────────────────────────────────────────
OLLAMA_HOST  = "http://localhost:11434"
# qwen3-vl:4b no Ollama 0.20.4 está consumindo a saída inteira em thinking.
# gemma3:4b é o modelo local mais estável e rápido aqui, com suporte a visão.
LLM_MODEL    = "gemma3:4b"
LLM_FALLBACK = "gemma3:4b"
OLLAMA_KEEP_ALIVE = "30m"

# Tempo máximo de resposta antes de considerar "lento demais" (segundos)
LLM_TIMEOUT_SLOW  = 45.0

# Requisições bem-sucedidas no fallback antes de tentar voltar ao principal
LLM_RECOVER_AFTER = 5

# ─── STT (fala → texto) ────────────────────────────────────────────────────────
WHISPER_MODEL        = "medium"
WHISPER_LANGUAGE     = "pt"
WHISPER_COMPUTE_TYPE = "int8_float16"  # economiza ~600MB vs float16, mesma qualidade

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
CLAP_PEAK_THRESHOLD         = 0.18   # pico mínimo normalizado (0-1)
CLAP_STRONG_PEAK_THRESHOLD  = 0.35   # uma palma muito forte ativa sozinha
CLAP_RMS_THRESHOLD          = 0.012  # energia mínima
CLAP_CREST_MIN              = 4.0    # pico / rms -> ajuda a distinguir de voz
CLAP_ACTIVE_RATIO_MAX       = 0.22   # palma é impulso curto, não som sustentado
CLAP_ONSET_THRESHOLD        = 0.09   # subida brusca — ajuda a separar de voz

# ─── Memória de conversa ──────────────────────────────────────────────────────
MAX_HISTORY_TURNS = 8

# ─── Conversa contínua ────────────────────────────────────────────────────────
# Após responder, Keilinks fica ouvindo por este tempo antes de voltar ao idle.
# Se o usuário falar nesse intervalo, continua a conversa sem precisar do wake word.
CONTINUOUS_LISTEN_TIMEOUT = 8.0    # segundos de silêncio antes de voltar pro idle
CONTINUOUS_MAX_TURNS      = 20     # máximo de turnos antes de forçar idle

# ─── Logging ──────────────────────────────────────────────────────────────────
LOG_LEVEL = "INFO"       # DEBUG | INFO | WARNING | ERROR
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