"""
Integração com Google Calendar.
Lê eventos próximos e avisa proativamente.

Setup:
  1. Crie um projeto no Google Cloud Console
  2. Ative a Calendar API
  3. Crie credenciais OAuth 2.0 (Desktop app)
  4. Salve credentials.json na raiz do projeto
  5. Na primeira execução, abre o navegador pra autorizar
"""

import time
import threading
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable
from keilinks.log import get_logger

log = get_logger("calendar")

CREDENTIALS_FILE = Path("credentials.json")
TOKEN_FILE       = Path("memoria/calendar_token.json")
SCOPES           = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]

CALENDAR_TRIGGERS = [
    "minha agenda", "agenda de hoje", "meus compromissos",
    "o que tenho hoje", "o que tenho amanhã", "próximo compromisso",
    "próxima reunião", "eventos de hoje", "eventos de amanhã",
]

CALENDAR_CREATE_TRIGGERS = [
    "cria um evento", "cria uma reunião", "cria um compromisso",
    "adiciona à agenda", "adiciona na agenda", "marca uma reunião",
    "marca um evento", "agenda uma reunião", "agenda um compromisso",
    "coloca na agenda", "add na agenda",
]


class CalendarSync:
    def __init__(self, on_reminder: Callable[[str], None] | None = None):
        """
        on_reminder(msg): chamado N minutos antes de um evento.
        """
        self._on_reminder    = on_reminder
        self._service        = None
        self._ok             = False
        self._running        = False
        self._thread: threading.Thread | None = None
        self._notified_events: set[str] = set()
        self._reminder_mins  = 15  # avisa 15 min antes
        self._init_api()

    def _init_api(self):
        if not CREDENTIALS_FILE.exists():
            log.info("Google Calendar: credentials.json não encontrado. Desativado.")
            return
        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build

            creds = None
            if TOKEN_FILE.exists():
                creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        str(CREDENTIALS_FILE), SCOPES
                    )
                    creds = flow.run_local_server(port=0)
                TOKEN_FILE.parent.mkdir(exist_ok=True)
                TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

            self._service = build("calendar", "v3", credentials=creds)
            self._ok = True
            log.info("Google Calendar conectado.")

        except ImportError:
            log.info("google-api-python-client não instalado. Calendário desativado.")
        except Exception as e:
            log.warning("Erro ao conectar Google Calendar: %s", e)

    @property
    def available(self) -> bool:
        return self._ok

    def get_events_today(self) -> list[dict]:
        """Retorna eventos de hoje."""
        return self._get_events(datetime.now().replace(hour=0, minute=0, second=0),
                                datetime.now().replace(hour=23, minute=59, second=59))

    def get_events_tomorrow(self) -> list[dict]:
        """Retorna eventos de amanhã."""
        tomorrow = datetime.now() + timedelta(days=1)
        return self._get_events(tomorrow.replace(hour=0, minute=0, second=0),
                                tomorrow.replace(hour=23, minute=59, second=59))

    def get_upcoming(self, hours: int = 4) -> list[dict]:
        """Retorna eventos das próximas N horas."""
        now = datetime.now()
        return self._get_events(now, now + timedelta(hours=hours))

    def _get_events(self, start: datetime, end: datetime) -> list[dict]:
        if not self._ok:
            return []
        try:
            events_result = self._service.events().list(
                calendarId="primary",
                timeMin=start.isoformat() + "Z" if start.tzinfo is None
                    else start.isoformat(),
                timeMax=end.isoformat() + "Z" if end.tzinfo is None
                    else end.isoformat(),
                maxResults=20,
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            events = events_result.get("items", [])
            return [
                {
                    "id":      e["id"],
                    "summary": e.get("summary", "(sem título)"),
                    "start":   e["start"].get("dateTime", e["start"].get("date", "")),
                    "end":     e["end"].get("dateTime", e["end"].get("date", "")),
                    "location": e.get("location", ""),
                }
                for e in events
            ]
        except Exception as e:
            log.error("Erro ao buscar eventos: %s", e)
            return []

    def format_events(self, events: list[dict]) -> str:
        if not events:
            return "Nenhum evento encontrado."
        lines = []
        for ev in events:
            start = ev["start"]
            # Parse hora se for datetime
            if "T" in start:
                try:
                    dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                    hora = dt.strftime("%H:%M")
                except Exception:
                    hora = start
            else:
                hora = "dia inteiro"
            loc = f" — {ev['location']}" if ev.get("location") else ""
            lines.append(f"• {hora}: {ev['summary']}{loc}")
        return "\n".join(lines)

    # ─── Monitoramento proativo ───────────────────────────────────────────────
    def start_monitoring(self, check_interval: float = 120.0):
        """Checa eventos a cada N segundos e avisa antes de começar."""
        if not self._ok or self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop,
                                        args=(check_interval,), daemon=True)
        self._thread.start()
        log.info("Monitorando agenda a cada %.0fs.", check_interval)

    def stop_monitoring(self):
        self._running = False

    def _monitor_loop(self, interval: float):
        time.sleep(30.0)  # delay inicial
        while self._running:
            try:
                upcoming = self.get_upcoming(hours=1)
                now = datetime.now()
                for ev in upcoming:
                    if ev["id"] in self._notified_events:
                        continue
                    start_str = ev["start"]
                    if "T" not in start_str:
                        continue
                    try:
                        ev_start = datetime.fromisoformat(
                            start_str.replace("Z", "+00:00")
                        ).replace(tzinfo=None)
                    except Exception:
                        continue
                    mins_until = (ev_start - now).total_seconds() / 60
                    if 0 < mins_until <= self._reminder_mins:
                        self._notified_events.add(ev["id"])
                        msg = (
                            f"Ei, daqui {int(mins_until)} minutos "
                            f"tem: {ev['summary']}."
                        )
                        if ev.get("location"):
                            msg += f" Local: {ev['location']}."
                        if self._on_reminder:
                            self._on_reminder(msg)
            except Exception as e:
                log.error("Erro no monitor de agenda: %s", e)

            time.sleep(interval)

    def try_handle(self, text: str) -> str | None:
        t = text.lower()

        # ── Criar evento ──────────────────────────────────────────────────────
        if any(tr in t for tr in CALENDAR_CREATE_TRIGGERS):
            if not self._ok:
                return ("Calendário não configurado. Coloque o credentials.json "
                        "do Google Calendar na pasta do projeto.")
            return self.create_event(text)

        # ── Ler agenda ────────────────────────────────────────────────────────
        if not any(tr in t for tr in CALENDAR_TRIGGERS):
            return None
        if not self._ok:
            return ("Calendário não configurado. Coloque o credentials.json "
                    "do Google Calendar na pasta do projeto.")
        if "amanhã" in t:
            events = self.get_events_tomorrow()
            header = "Agenda de amanhã:"
        elif "próxim" in t:
            events = self.get_upcoming(hours=4)
            header = "Próximos eventos:"
        else:
            events = self.get_events_today()
            header = "Agenda de hoje:"
        formatted = self.format_events(events)
        return f"{header}\n{formatted}"

    def create_event(self, text: str) -> str:
        """
        Cria um evento no Google Calendar a partir de um texto natural.
        Ex: "cria uma reunião amanhã às 15h sobre deploy do projeto"
        """
        if not self._ok:
            return "Calendário não disponível."
        try:
            now = datetime.now()
            title = "Evento"
            event_start = None
            event_end   = None

            # Extrai hora (às Xh / às HH:MM)
            m = re.search(r"\b(?:às|as)\s+(\d{1,2})(?::(\d{2}))?h?", text, re.IGNORECASE)
            if m:
                hour   = int(m.group(1))
                minute = int(m.group(2)) if m.group(2) else 0
                base   = now + timedelta(days=1) if "amanhã" in text.lower() else now
                event_start = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
                event_end   = event_start + timedelta(hours=1)

            # Extrai "daqui a N minutos/horas"
            if not event_start:
                m2 = re.search(r"daqui\s+a?\s*(\d+)\s*(minuto|hora)s?", text, re.IGNORECASE)
                if m2:
                    n    = int(m2.group(1))
                    unit = m2.group(2).lower()
                    event_start = now + (timedelta(minutes=n) if "minuto" in unit else timedelta(hours=n))
                    event_end   = event_start + timedelta(hours=1)

            if not event_start:
                return "Não entendi o horário. Ex: 'cria uma reunião às 15h sobre projeto X'."

            # Extrai título (parte depois de "sobre", "de", "para")
            for sep in [" sobre ", " de ", " para ", " pra "]:
                if sep in text.lower():
                    idx   = text.lower().rfind(sep)
                    after = text[idx + len(sep):].strip()
                    # Filtra tokens de horário
                    if after and not re.match(r"^\d", after):
                        title = after.strip(".,!?")
                        break

            # Usa o timezone local
            import tzlocal  # type: ignore
            try:
                tz = tzlocal.get_localzone_name()
            except Exception:
                tz = "America/Sao_Paulo"

            body = {
                "summary": title,
                "start": {"dateTime": event_start.isoformat(), "timeZone": tz},
                "end":   {"dateTime": event_end.isoformat(),   "timeZone": tz},
            }
            self._service.events().insert(calendarId="primary", body=body).execute()
            hora_fmt = event_start.strftime("%d/%m às %H:%M")
            return f"Evento criado: '{title}' em {hora_fmt}."
        except ImportError:
            return "Instale tzlocal: pip install tzlocal"
        except Exception as e:
            log.error("Erro ao criar evento: %s", e)
            return f"Não consegui criar o evento: {e}"
