"""
Keilinks — Assistente de IA local
Powered by: Ollama + faster-whisper + edge-tts/Piper + OpenCV
Hardware: NVIDIA RTX 50xx Blackwell (CUDA 12.4)
"""

import os
import re
import sys
import signal
import threading
import queue

from config import CONTINUOUS_LISTEN_TIMEOUT, CONTINUOUS_MAX_TURNS, SKILLS_DIR, CALENDAR_REMINDER_MINS, CALENDAR_CHECK_INTERVAL

from keilinks.log            import get_logger
from keilinks.brain          import Brain
from keilinks.ears           import Ears
from keilinks.voice          import Voice
from keilinks.eyes           import Eyes
from keilinks.wakeword       import WakeWordDetector
from keilinks.pc_control     import PCControl
from keilinks.spotify_api    import SpotifyControl
from keilinks.animator       import BrainAnimator
from keilinks.screen_monitor import ScreenMonitor, MonitorConfig
from keilinks.system_stats   import SystemStats
from keilinks.reminders      import ReminderManager
from keilinks.notifier       import notify
from keilinks.summarizer     import Summarizer
from keilinks.habits         import HabitTracker
from keilinks.briefing       import build_briefing_prompt
from keilinks.translator     import is_translate_trigger, extract_target_language, build_translate_prompt
from keilinks.timer          import TimerManager
from keilinks.history_db     import HistoryDB
from keilinks.mood           import MoodDetector
from keilinks.notes          import NoteManager
from keilinks.rag_memory     import RAGMemory
from keilinks.study_mode     import StudyMode
from keilinks.web_api        import WebInterface
from keilinks.presence       import PresenceMonitor, PresenceConfig
from keilinks.cinema_mode    import CinemaMode
from keilinks.skill_loader   import SkillLoader
from keilinks.calendar_sync  import CalendarSync
from keilinks.day_summary    import DaySummarizer
from keilinks.voice_profile  import VoiceProfile
from keilinks.export_conversation import ConversationExporter
from keilinks.weather            import WeatherService

log = get_logger("main")


# ─── Triggers ─────────────────────────────────────────────────────────────────
CAMERA_TRIGGERS = [
    "o que você vê", "o que ta vendo", "olha isso", "veja isso",
    "o que é isso", "olha aqui", "usa a câmera", "vê isso",
]
SCREEN_TRIGGERS = [
    "captura a tela", "analisa a tela", "o que tem na tela",
    "vê a tela", "olha a tela", "o que está na tela", "o que tá na tela",
]
OCR_TRIGGERS = [
    "lê o texto da tela", "lê a tela", "leia a tela",
    "o que está escrito na tela", "que texto tem na tela",
    "transcreve a tela", "copia o texto da tela",
]
SUMMARIZE_TRIGGERS = [
    "resume essa página", "resume esse artigo", "resume esse site",
    "resume esse vídeo", "resume isso", "me resume",
    "o que fala essa página", "o que diz esse artigo",
    "explica essa página", "lê essa página",
    "pontos principais", "pontos chave",
]
MONITOR_START_TRIGGERS = [
    "fica de olho na tela", "monitora a tela", "monitora minha tela",
    "observa a tela", "me avisa se mudar", "fica monitorando",
]
MONITOR_STOP_TRIGGERS = [
    "para de monitorar", "cancela o monitoramento", "deixa de olhar a tela",
]
REMEMBER_TRIGGERS = [
    "lembra que", "guarda que", "anota que", "não esquece que", "salva isso",
]
REMINDER_TRIGGERS = [
    "me lembra", "lembra de", "me avisa às", "coloca um lembrete",
]
STATS_TRIGGERS = [
    "como tá o pc", "como está o pc", "status do pc", "como tá o hardware",
    "uso de cpu", "uso da gpu", "quanto de ram", "temperatura", "métricas",
]
PRESENCE_ON_TRIGGERS  = ["fica me observando", "me monitora pela câmera", "fica de olho em mim",
                          "fica me vendo", "me vigia", "ativa presença"]
PRESENCE_OFF_TRIGGERS = ["para de me observar", "para de me monitorar",
                          "desativa presença", "para de me vigiar"]
GOOD_MORNING_TRIGGERS = ["bom dia", "boa tarde", "boa noite"]
CLEAR_HISTORY  = ["limpa a memória", "esquece a conversa", "zera a conversa"]
FORGET_ALL     = ["esquece tudo", "apaga tudo que você sabe"]
EXIT_TRIGGERS  = ["tchau keilinks", "até logo keilinks", "encerra o programa", "fecha o programa"]
HISTORY_SEARCH_TRIGGERS = [
    "busca no histórico", "procura no histórico", "o que falamos sobre",
    "lembra quando", "quando a gente falou",
]
SILENT_MODE_ON  = ["fica quieta", "modo silencioso", "não fala", "fica muda", "silêncio"]
SILENT_MODE_OFF = ["pode falar", "volta a falar", "desativa silêncio", "fala de novo"]
SKILL_LIST_TRIGGERS    = ["lista os skills", "quais skills", "plugins instalados"]
RECALIBRATE_TRIGGERS   = ["recalibra minha voz", "recalibra o perfil de voz", "recalibrar voz"]


def match(text: str, triggers: list[str]) -> bool:
    t = text.lower()
    return any(tr in t for tr in triggers)

def extract_note(text: str) -> str | None:
    t = text.lower()
    for trigger in REMEMBER_TRIGGERS:
        if trigger in t:
            return text[text.lower().index(trigger) + len(trigger):].strip()
    return None


def handle_smalltalk(text: str) -> str | None:
    t = text.lower().strip()
    t_simple = t.strip(" !?.,;:")
    if any(p in t for p in [
        "como você está", "como voce está", "como você tá", "como voce tá",
        "como é que você tá", "como é que voce tá", "como e que você tá", "como e que voce tá",
        "como é que você está", "como é que voce está", "como e que você está", "como e que voce está",
        "como que você está", "como que voce está", "como que você tá", "como que voce tá",
        "você está bem", "voce está bem", "você tá bem", "voce tá bem",
        "tudo bem", "tudo bom",
    ]):
        return "Tô bem. E você?"
    if any(p in t for p in ["o que você tá fazendo", "o que voce tá fazendo", "o que você está fazendo", "o que voce está fazendo"]):
        return "Tô aqui, pronta pra te ajudar."
    if any(p in t for p in ["quem é você", "quem é voce"]):
        return "Sou a Keilinks. Tô aqui pra te ajudar e conversar com você."
    if any(p == t_simple or t_simple.startswith(p + " ") for p in ["fui", "tchau", "falou", "até mais", "ate mais"]):
        return "Até já."
    return None


# ─── Fila de alertas proativos ────────────────────────────────────────────────
_alert_queue: queue.Queue = queue.Queue()


def main():
    print("=" * 55)
    print("  Keilinks — Iniciando...")
    print("=" * 55)

    anim = BrainAnimator()
    anim.start()
    anim.set_state("idle")

    def _on_model_change(novo_modelo: str, motivo: str):
        if "4b" in novo_modelo:
            msg = "Tô usando o modelo menor, tava pesado. Volto pro normal quando estabilizar."
        else:
            msg = "Voltei ao modelo completo. Tudo certo."
        _alert_queue.put(("system", msg, None))
        notify("Keilinks — Modelo", msg)

    history_db = HistoryDB()
    brain      = Brain(on_model_change=_on_model_change, history_db=history_db,
                       on_search_start=lambda: voice.speak("Deixa eu pesquisar...", interruptible=False))
    ears       = Ears()
    voice      = Voice()
    eyes       = Eyes()
    wake       = WakeWordDetector()
    pc         = PCControl()
    media      = SpotifyControl()
    stats      = SystemStats(on_alert=lambda msg: _alert_queue.put(("system", msg, None)))
    summarizer = Summarizer()
    habits     = HabitTracker()
    mood_det   = MoodDetector()
    note_mgr   = NoteManager(
        notes_dir     = "notas",
        obsidian_vault = os.environ.get("OBSIDIAN_VAULT", ""),
    )
    rag        = RAGMemory()
    voice_prof = VoiceProfile()

    def speak_brain_stream(
        prompt_text: str,
        *,
        image_b64: str | None = None,
        internal: bool = False,
        interruptible: bool = True,
    ) -> bool:
        return voice.speak_stream(
            lambda stop_event: brain.think_stream(
                prompt_text,
                image_b64=image_b64,
                internal=internal,
                stop_event=stop_event,
            ),
            interruptible=interruptible,
        )

    # Aplica perfil de voz calibrado (se existir)
    if voice_prof.calibrated:
        thresholds = voice_prof.get_thresholds()
        if thresholds:
            mood_det.apply_profile_thresholds(thresholds)

    def _on_timer_fire(msg: str):
        _alert_queue.put(("timer", msg, None))
        notify("Keilinks — Timer", msg)

    timer_mgr  = TimerManager(on_fire=_on_timer_fire)

    def _on_study_alert(msg: str):
        _alert_queue.put(("study", msg, None))

    study      = StudyMode(on_alert=_on_study_alert)

    def _on_reminder(msg: str):
        _alert_queue.put(("reminder", msg, None))
        notify("Keilinks — Lembrete", msg)

    reminders  = ReminderManager(on_reminder=_on_reminder)

    # ── Cinema Mode ───────────────────────────────────────────────────────────
    def _on_cinema_pause(msg: str):
        _alert_queue.put(("cinema", msg, None))

    cinema = CinemaMode(on_pause=_on_cinema_pause)

    # ── Plugins/Skills ────────────────────────────────────────────────────────
    skills = SkillLoader(skills_dir=SKILLS_DIR)
    skills.set_context({
        "pc": pc, "brain": brain, "media": media,
        "voice": voice, "ears": ears, "eyes": eyes,
    })
    skills.start_watcher()

    # ── Google Calendar ───────────────────────────────────────────────────────
    def _on_calendar_reminder(msg: str):
        _alert_queue.put(("calendar", msg, None))
        notify("Keilinks — Agenda", msg)

    calendar = CalendarSync(on_reminder=_on_calendar_reminder)
    calendar._reminder_mins = CALENDAR_REMINDER_MINS
    if calendar.available:
        calendar.start_monitoring(check_interval=CALENDAR_CHECK_INTERVAL)

    # ── Resumo do dia / Exportar conversa ─────────────────────────────────────
    day_summary = DaySummarizer(
        history_db=history_db, study=study, habits=habits,
        reminders=reminders, mood_det=mood_det, learner=brain.learner,
    )
    exporter = ConversationExporter(history_db=history_db)

    # ── Clima (wttr.in — sem API key) ─────────────────────────────────────────
    from keilinks.learner import Learner as _L  # só pra pegar cidade do perfil
    _city = brain.learner.profile.get("cidade", "Curitiba") if hasattr(brain.learner, "profile") else "Curitiba"
    weather = WeatherService(default_city=_city)

    def _on_screen_alert(prompt: str, image_b64: str | None):
        _alert_queue.put(("screen", prompt, image_b64))

    screen_mon = ScreenMonitor(on_alert=_on_screen_alert)
    stats.start_monitoring(interval=30.0)

    # Presença — ela te observa pela câmera e inicia conversa quando faz sentido
    def _on_presence_engage(abertura: str):
        """Keilinks detectou que você tá entediado/relaxado e quer conversar."""
        _alert_queue.put(("presence", abertura, None))

    presence = PresenceMonitor(on_engage=_on_presence_engage, eyes=eyes)
    # Começa automaticamente se a câmera estiver disponível
    if eyes.is_available():
        presence.start(PresenceConfig(
            check_interval_secs = 25.0,   # checa a cada 25s
            min_gap_secs        = 300.0,  # no mínimo 5 min entre abordagens
            engage_when_focused = False,  # respeita quando você tá focado
            sensitivity         = "normal",
        ))

    # Auto-detecção de cinema: se player estiver aberto ao iniciar
    if cinema.detect_player():
        cinema.start(auto=True)
        log.info("Player de vídeo detectado ao iniciar. Modo cinema automático.")

    # ── Interface Web ─────────────────────────────────────────────────────────
    web = WebInterface(
        history_db = history_db,
        rag_memory = rag,
        notes      = note_mgr,
        stats      = stats,
        brain      = brain,
        habits     = habits,
        study      = study,
    )
    web.start()

    # Sessão do histórico
    session_id = history_db.start_session()

    def handle_exit(sig=None, frame=None):
        print("\n[Keilinks] Encerrando...")
        history_db.end_session(session_id)
        history_db.close()
        anim.stop()
        screen_mon.stop_watching()
        stats.stop_monitoring()
        presence.stop()
        cinema.stop()
        calendar.stop_monitoring()
        study.stop() if study.is_active() else None
        eyes.release()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_exit)

    # ── Apresentação ──────────────────────────────────────────────────────────
    intro = (
        "Oi, amor. Câmera ligada. Me chama ou bate palmas quando precisar."
        if eyes.is_available()
        else "Oi, amor. Tô aqui. Me chama ou bate palmas quando precisar."
    )
    anim.set_state("speaking")
    voice.speak(intro)
    anim.set_state("idle")

    # Pré-aquece o LLM enquanto fica idle para reduzir a latência da 1ª resposta.
    threading.Thread(target=brain.warmup, daemon=True).start()

    # ─── Thread de alertas proativos ──────────────────────────────────────────
    def alert_worker():
        while True:
            try:
                kind, prompt, image_b64 = _alert_queue.get(timeout=1)
            except queue.Empty:
                continue

            anim.set_state("thinking")

            if kind == "screen":
                reply = brain.think(prompt, image_b64=image_b64, internal=True)
                if reply.strip().upper() == "IGNORAR":
                    anim.set_state("idle")
                    continue

            elif kind == "presence":
                # Abertura já vem pronta do LLM de presença
                # Continua a conversa depois de falar — sem precisar de wake word
                anim.set_state("speaking")
                presence.pause()
                screen_mon.pause()
                completed = voice.speak(prompt, interruptible=True)

                if completed:
                    # Fica ouvindo a resposta dele por até 8s
                    anim.set_state("listening")
                    user_reply = ears.listen(on_volume=anim.set_volume)
                    if user_reply:
                        anim.set_state("thinking")
                        anim.set_state("speaking")
                        speak_brain_stream(user_reply)

                presence.resume()
                screen_mon.resume()
                anim.set_state("idle")
                continue

            elif kind == "timer":
                # Timer/alarme disparou — fala imediatamente
                anim.set_state("speaking")
                voice.speak(prompt, interruptible=False)
                anim.set_state("idle")
                continue

            elif kind == "study":
                # Modo estudo: alerta de distração
                anim.set_state("speaking")
                voice.speak(prompt, interruptible=False)
                anim.set_state("idle")
                continue

            elif kind in ("calendar", "cinema"):
                # Alertas de agenda ou cinema (pausa detectada)
                if not cinema.suppressing or kind == "cinema":
                    anim.set_state("speaking")
                    voice.speak(prompt, interruptible=False)
                anim.set_state("idle")
                continue

            else:
                reply = prompt

            anim.set_state("speaking")
            voice.speak(reply, interruptible=False)
            anim.set_state("idle")

    threading.Thread(target=alert_worker, daemon=True).start()

    # ─── Loop principal ───────────────────────────────────────────────────────
    while True:
        anim.set_state("idle")
        wake.wait_for_wake_word()
        screen_mon.pause()
        presence.pause()

        # Descarrega wake word da VRAM durante a conversa
        wake.unload()

        anim.set_state("speaking")
        voice.speak("Oi!", interruptible=False)

        # ── Conversa contínua: fica ouvindo até dar timeout ───────────────────
        turns = 0
        while turns < CONTINUOUS_MAX_TURNS:
            anim.set_state("listening")

            # Primeira escuta: sem timeout (espera o usuário falar)
            # Próximas escutas: usa timeout para detectar fim da conversa
            timeout = None if turns == 0 else CONTINUOUS_LISTEN_TIMEOUT
            user_text = ears.listen(on_volume=anim.set_volume, timeout=timeout)

            if not user_text:
                if turns == 0:
                    # Primeira escuta sem resultado — pede pra repetir e tenta mais 1x
                    anim.set_state("speaking")
                    voice.speak("Não entendi. Pode repetir?")
                    turns += 1
                    continue
                else:
                    # Timeout na conversa contínua — encerra conversa normalmente
                    log.info("Conversa encerrada por silêncio (timeout).")
                    break

            turns += 1

            # ── Salva no histórico SQLite + RAG ───────────────────────────────
            history_db.add_message(session_id, "user", user_text)
            rag.add(user_text, role="user")

            # ── Saída ─────────────────────────────────────────────────────────
            if match(user_text, EXIT_TRIGGERS):
                anim.set_state("speaking")
                voice.speak("Tá bom, amor. Até mais.")
                handle_exit()

            # ── Modo silencioso ────────────────────────────────────────────────
            if match(user_text, SILENT_MODE_ON):
                voice.silent_mode = True
                # Fala antes de silenciar
                anim.set_state("speaking")
                voice.silent_mode = False
                voice.speak("Ok, fico muda. Me avisa quando quiser que eu volte.")
                voice.silent_mode = True
                continue

            if match(user_text, SILENT_MODE_OFF):
                voice.silent_mode = False
                anim.set_state("speaking")
                voice.speak("Voltei! Pode falar.")
                continue

            # ── Cinema mode ────────────────────────────────────────────────────
            cinema_resp = cinema.try_handle(user_text)
            if cinema_resp:
                anim.set_state("speaking")
                voice.speak(cinema_resp)
                continue

            # ── Recalibrar perfil de voz ───────────────────────────────────────
            if match(user_text, RECALIBRATE_TRIGGERS):
                anim.set_state("speaking")
                voice.speak(voice_prof.recalibrate())
                continue

            # ── Listar skills ──────────────────────────────────────────────────
            if match(user_text, SKILL_LIST_TRIGGERS):
                anim.set_state("speaking")
                voice.speak(skills.list_skills())
                continue

            # ── Exportar conversa ──────────────────────────────────────────────
            export_resp = exporter.try_handle(user_text)
            if export_resp:
                anim.set_state("speaking")
                voice.speak(export_resp)
                continue

            # ── Resumo do dia ──────────────────────────────────────────────────
            if day_summary.try_handle(user_text):
                anim.set_state("thinking")
                prompt = day_summary.build_summary_prompt()
                anim.set_state("speaking")
                speak_brain_stream(prompt, internal=True)
                continue

            # ── Google Calendar ────────────────────────────────────────────────
            cal_resp = calendar.try_handle(user_text)
            if cal_resp:
                anim.set_state("speaking")
                voice.speak(cal_resp)
                continue

            # ── Clima (wttr.in direto — mais rápido que busca web) ─────────────
            weather_resp = weather.try_handle(user_text)
            if weather_resp:
                anim.set_state("speaking")
                if any(p in user_text.lower() for p in ["e o seu", "e você", "e voce", "como você está", "como voce está", "como você tá", "como voce tá"]):
                    weather_resp += " E eu tô bem por aqui."
                voice.speak(weather_resp)
                continue

            smalltalk_resp = handle_smalltalk(user_text)
            if smalltalk_resp:
                anim.set_state("speaking")
                voice.speak(smalltalk_resp)
                continue

            # ── Plugins/Skills dinâmicos ───────────────────────────────────────
            skill_resp = skills.try_handle(user_text)
            if skill_resp:
                anim.set_state("speaking")
                voice.speak(skill_resp)
                continue

            # ── Presença (liga/desliga) ────────────────────────────────────────
            if match(user_text, PRESENCE_ON_TRIGGERS):
                if eyes.is_available():
                    presence.start(PresenceConfig(check_interval_secs=25.0, min_gap_secs=300.0))
                    anim.set_state("speaking")
                    voice.speak("Tá bom, vou ficar de olho em você.")
                else:
                    voice.speak("Câmera não disponível.")
                continue

            if match(user_text, PRESENCE_OFF_TRIGGERS):
                presence.stop()
                anim.set_state("speaking")
                voice.speak("Ok, parei de te observar.")
                continue

            # ── Bom dia / boa tarde / boa noite ───────────────────────────────
            if match(user_text, GOOD_MORNING_TRIGGERS):
                anim.set_state("thinking")
                prompt = build_briefing_prompt(
                    reminders_text   = reminders.list_reminders(),
                    habits_missed    = habits.missed_today(),
                    learner_summary  = brain.learner.get_profile_summary(),
                )
                anim.set_state("speaking")
                speak_brain_stream(prompt, internal=True)
                continue

            # ── Memória ───────────────────────────────────────────────────────
            if match(user_text, CLEAR_HISTORY):
                brain.clear_history()
                anim.set_state("speaking")
                voice.speak("Conversa limpa.")
                continue

            if match(user_text, FORGET_ALL):
                brain.forget_everything()
                anim.set_state("speaking")
                voice.speak("Apaguei tudo.")
                continue

            note = extract_note(user_text)
            if note:
                brain.remember_note(note)
                anim.set_state("speaking")
                voice.speak("Anotei.")
                continue

            # ── Hábitos ───────────────────────────────────────────────────────
            habit_resp = habits.try_handle(user_text)
            if habit_resp:
                anim.set_state("speaking")
                voice.speak(habit_resp)
                continue
            # ── Timer / Alarme ────────────────────────────────────────────────
            timer_resp = timer_mgr.try_handle(user_text)
            if timer_resp:
                anim.set_state("speaking")
                voice.speak(timer_resp)
                continue

            # ── Notas (Obsidian-compatible) ───────────────────────────────────
            note_resp = note_mgr.try_handle(user_text)
            if note_resp:
                anim.set_state("speaking")
                voice.speak(note_resp)
                continue

            # ── Modo Estudo ───────────────────────────────────────────────────
            study_resp = study.try_handle(user_text)
            if study_resp:
                anim.set_state("speaking")
                voice.speak(study_resp)
                continue

            # ── Busca no histórico ────────────────────────────────────────────
            if match(user_text, HISTORY_SEARCH_TRIGGERS):
                anim.set_state("thinking")
                # Extrai o que buscar
                query = user_text
                for tr in HISTORY_SEARCH_TRIGGERS:
                    if tr in user_text.lower():
                        query = user_text[user_text.lower().index(tr) + len(tr):].strip()
                        break
                if query:
                    results = history_db.search(query, limit=5)
                    if results:
                        context = "\n".join(
                            f"[{r['timestamp']}] {'Você' if r['role']=='user' else 'Keilinks'}: {r['content']}"
                            for r in results
                        )
                        prompt = (
                            f"O usuário quer lembrar de uma conversa sobre: {query}\n"
                            f"Aqui está o que encontrei no histórico:\n{context}\n\n"
                            "Resume o que encontrou de forma conversacional."
                        )
                        anim.set_state("speaking")
                        speak_brain_stream(prompt, internal=True)
                    else:
                        anim.set_state("speaking")
                        voice.speak(f"Não encontrei nada sobre '{query}' no histórico.")
                else:
                    anim.set_state("speaking")
                    voice.speak("Sobre o que você quer buscar?")
                continue
            # ── Lembretes ─────────────────────────────────────────────────────
            if match(user_text, REMINDER_TRIGGERS):
                when, msg = reminders.parse_reminder(user_text)
                reply = reminders.add(when, msg) if when else reminders.list_reminders()
                anim.set_state("speaking")
                voice.speak(reply)
                continue

            if "lista os lembretes" in user_text.lower() or "quais lembretes" in user_text.lower():
                anim.set_state("speaking")
                voice.speak(reminders.list_reminders())
                continue

            # ── Stats do PC ───────────────────────────────────────────────────
            if match(user_text, STATS_TRIGGERS):
                anim.set_state("speaking")
                voice.speak(stats.summary_text())
                continue

            # ── Monitor de tela ───────────────────────────────────────────────
            if match(user_text, MONITOR_START_TRIGGERS):
                interval = 5.0
                m = re.search(r"a cada\s+(\d+)\s*(segundo|minuto)s?", user_text.lower())
                if m:
                    n = int(m.group(1))
                    interval = n if "segundo" in m.group(2) else n * 60
                screen_mon.start_watching(MonitorConfig(
                    interval_secs=interval, change_threshold=0.08, analyze_on_change=True,
                ))
                anim.set_state("speaking")
                voice.speak("Tô de olho. Te aviso se mudar algo relevante.")
                continue

            if match(user_text, MONITOR_STOP_TRIGGERS):
                screen_mon.stop_watching()
                anim.set_state("speaking")
                voice.speak("Parei de monitorar.")
                continue

            # ── Mídia ─────────────────────────────────────────────────────────
            media_resp = media.try_handle(user_text)
            if media_resp:
                anim.set_state("speaking")
                voice.speak(media_resp)
                continue

            # ── PC control ────────────────────────────────────────────────────
            pc_resp = pc.try_handle(user_text)
            if pc_resp:
                anim.set_state("speaking")
                voice.speak(pc_resp)
                continue

            # ── Tradução de tela ──────────────────────────────────────────────
            if is_translate_trigger(user_text):
                anim.set_state("thinking")
                screen_text = eyes.read_screen_text()
                if not screen_text:
                    anim.set_state("speaking")
                    voice.speak("Não consegui ler o texto da tela.")
                    continue
                target_lang = extract_target_language(user_text)
                prompt      = build_translate_prompt(screen_text, target_lang)
                anim.set_state("speaking")
                speak_brain_stream(prompt, internal=True)
                continue

            # ── Resumo de página ──────────────────────────────────────────────
            if match(user_text, SUMMARIZE_TRIGGERS):
                anim.set_state("thinking")
                url = summarizer.extract_url(user_text)
                if not url:
                    anim.set_state("speaking")
                    voice.speak("Não encontrei URL. Cola no clipboard ou fala a URL.")
                    continue
                mode = "pontos" if any(p in user_text.lower() for p in ["pontos", "chave", "tópico"]) else "resumo"
                voice.speak("Deixa eu acessar...", interruptible=False)
                prompt = summarizer.summarize_url(url, mode=mode)
                anim.set_state("speaking")
                speak_brain_stream(prompt, internal=True)
                continue

            # ── OCR ───────────────────────────────────────────────────────────
            if match(user_text, OCR_TRIGGERS):
                anim.set_state("thinking")
                text_on_screen = eyes.read_screen_text()
                anim.set_state("speaking")
                if text_on_screen is None:
                    voice.speak("Pytesseract não está instalado.")
                elif not text_on_screen.strip():
                    voice.speak("Não encontrei texto legível na tela.")
                else:
                    prompt = (
                        "O usuário pediu pra você ler o texto que está na tela. "
                        "Leia de forma natural, resumindo se for muito longo:\n\n" + text_on_screen
                    )
                    speak_brain_stream(prompt, internal=True)
                continue

            # ── Visão ─────────────────────────────────────────────────────────
            image_b64 = None
            if match(user_text, SCREEN_TRIGGERS):
                log.info("Capturando tela...")
                image_b64 = eyes.capture_screen_b64()
                if not image_b64:
                    anim.set_state("speaking")
                    voice.speak("Não consegui capturar a tela.")
                    continue
            elif match(user_text, CAMERA_TRIGGERS) and eyes.is_available():
                log.info("Capturando câmera...")
                image_b64 = eyes.capture_frame_b64()

            # ── LLM com streaming + RAG context ──────────────────────────────
            import time as _time
            t0_pipeline = _time.monotonic()
            anim.set_state("thinking")

            # Suprime alertas de hardware enquanto o LLM processa (GPU sempre ~97%)
            stats.set_suppress(True)

            try:
                import torch
                _vram_before = torch.cuda.memory_allocated() / 1024**2
            except Exception:
                _vram_before = None

            # Injeta contexto RAG de conversas anteriores
            t0_rag = _time.monotonic()
            rag_context = rag.query_for_prompt(user_text)
            if rag_context:
                brain.set_rag_context(rag_context)
                log.info("[TIMING] RAG query: %.2fs", _time.monotonic() - t0_rag)

            # Humor: detecta pelo áudio capturado e adapta voz
            if ears.last_audio is not None and len(ears.last_audio) > 1600:
                t0_mood = _time.monotonic()
                mood_result = mood_det.analyze(ears.last_audio)
                voice.set_mood(mood_result.mood)
                log.debug("[TIMING] Mood detect: %.2fs", _time.monotonic() - t0_mood)
                # Alimenta calibração do perfil de voz
                if not voice_prof.calibrated:
                    voice_prof.add_sample(mood_result.energy, mood_result.pitch_hz, mood_result.speed)
                    if voice_prof.calibrated:
                        thresholds = voice_prof.get_thresholds()
                        if thresholds:
                            mood_det.apply_profile_thresholds(thresholds)
                            log.info("Perfil de voz calibrado — thresholds aplicados.")

            mood_summary = mood_det.get_summary()
            if mood_summary:
                brain.set_mood_hint(mood_summary)

            anim.set_state("speaking")
            completed = speak_brain_stream(user_text, image_b64=image_b64)
            stats.set_suppress(False)  # reativa alertas após resposta

            try:
                import torch
                _vram_after = torch.cuda.memory_allocated() / 1024**2
                if _vram_before is not None:
                    log.debug("[VRAM] Antes LLM: %.0fMB  Depois: %.0fMB  Δ=%.0fMB  Pipeline: %.1fs",
                              _vram_before, _vram_after, _vram_after - _vram_before,
                              _time.monotonic() - t0_pipeline)
            except Exception:
                pass

            # Salva resposta do assistant no histórico + RAG
            if brain.history and brain.history[-1].get("role") == "assistant":
                assistant_text = brain.history[-1]["content"]
                history_db.add_message(session_id, "assistant", assistant_text)
                rag.add(assistant_text, role="assistant")

            # Se interrompida, ouve imediatamente (sem timeout, como ação direta)
            if not completed:
                anim.set_state("listening")
                user_text2 = ears.listen(on_volume=anim.set_volume)
                if user_text2:
                    history_db.add_message(session_id, "user", user_text2)
                    rag.add(user_text2, role="user")
                    anim.set_state("thinking")
                    anim.set_state("speaking")
                    speak_brain_stream(user_text2)
                    if brain.history and brain.history[-1].get("role") == "assistant":
                        assistant_text2 = brain.history[-1]["content"]
                        history_db.add_message(session_id, "assistant", assistant_text2)
                        rag.add(assistant_text2, role="assistant")

            # Continua o loop da conversa contínua — volta pro listening com timeout

        # ── Saiu da conversa contínua — volta ao idle ─────────────────────────
        log.info("Voltando ao modo idle.")
        screen_mon.resume()
        presence.resume()
        wake.reload()   # recarrega o modelo tiny na VRAM


if __name__ == "__main__":
    main()
