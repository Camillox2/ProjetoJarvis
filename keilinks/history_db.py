"""
Histórico de conversas em SQLite com busca full-text (FTS5).
A Keilinks lembra de conversas de dias/semanas atrás.
Busca por palavra-chave ou data.
"""

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from keilinks.log import get_logger

log = get_logger("history")

DB_PATH = Path("memoria/historico.db")


class HistoryDB:
    def __init__(self):
        DB_PATH.parent.mkdir(exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()

    def _create_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
                ended_at    TEXT,
                summary     TEXT
            );

            CREATE TABLE IF NOT EXISTS messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  INTEGER NOT NULL REFERENCES sessions(id),
                role        TEXT    NOT NULL CHECK(role IN ('user','assistant','system')),
                content     TEXT    NOT NULL,
                timestamp   TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
                mood        TEXT,
                image_used  INTEGER NOT NULL DEFAULT 0
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                content,
                content='messages',
                content_rowid='id'
            );

            -- Trigger para manter o FTS em sincronia
            CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
                INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
            END;

            CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
                INSERT INTO messages_fts(messages_fts, rowid, content)
                    VALUES('delete', old.id, old.content);
            END;
        """)
        self._conn.commit()

    # ─── Sessões ──────────────────────────────────────────────────────────────
    def start_session(self) -> int:
        cur = self._conn.execute(
            "INSERT INTO sessions (started_at) VALUES (datetime('now','localtime'))"
        )
        self._conn.commit()
        sid = cur.lastrowid
        log.debug("Sessão %d iniciada.", sid)
        return sid

    def end_session(self, session_id: int, summary: str = ""):
        self._conn.execute(
            "UPDATE sessions SET ended_at = datetime('now','localtime'), summary = ? WHERE id = ?",
            (summary, session_id),
        )
        self._conn.commit()

    # ─── Mensagens ────────────────────────────────────────────────────────────
    def add_message(self, session_id: int, role: str, content: str,
                    mood: str = "", image_used: bool = False):
        self._conn.execute(
            "INSERT INTO messages (session_id, role, content, mood, image_used) VALUES (?,?,?,?,?)",
            (session_id, role, content, mood, 1 if image_used else 0),
        )
        self._conn.commit()

    # ─── Busca full-text ──────────────────────────────────────────────────────
    def search(self, query: str, limit: int = 20) -> list[dict]:
        """
        Busca por palavras-chave no histórico inteiro.
        Retorna lista de dicts com session_id, role, content, timestamp, snippet.
        """
        rows = self._conn.execute("""
            SELECT m.session_id, m.role, m.content, m.timestamp,
                   snippet(messages_fts, 0, '>>>', '<<<', '...', 40) AS snippet
            FROM messages_fts
            JOIN messages m ON m.id = messages_fts.rowid
            WHERE messages_fts MATCH ?
            ORDER BY m.timestamp DESC
            LIMIT ?
        """, (query, limit)).fetchall()

        return [
            {"session_id": r[0], "role": r[1], "content": r[2],
             "timestamp": r[3], "snippet": r[4]}
            for r in rows
        ]

    def search_by_date(self, date_str: str, limit: int = 50) -> list[dict]:
        """Busca mensagens de um dia específico (formato 'YYYY-MM-DD')."""
        rows = self._conn.execute("""
            SELECT session_id, role, content, timestamp
            FROM messages
            WHERE date(timestamp) = ?
            ORDER BY timestamp ASC
            LIMIT ?
        """, (date_str, limit)).fetchall()

        return [
            {"session_id": r[0], "role": r[1], "content": r[2], "timestamp": r[3]}
            for r in rows
        ]

    # ─── Contexto para o LLM ─────────────────────────────────────────────────
    def get_recent_context(self, n_messages: int = 10) -> str:
        """Retorna as últimas N mensagens como texto formatado para o prompt."""
        rows = self._conn.execute("""
            SELECT role, content, timestamp FROM messages
            ORDER BY id DESC LIMIT ?
        """, (n_messages,)).fetchall()

        if not rows:
            return ""

        lines = []
        for role, content, ts in reversed(rows):
            prefix = "Usuário" if role == "user" else "Keilinks"
            lines.append(f"[{ts}] {prefix}: {content}")
        return "\n".join(lines)

    def get_session_messages(self, session_id: int) -> list[dict]:
        rows = self._conn.execute("""
            SELECT role, content, timestamp, mood
            FROM messages WHERE session_id = ?
            ORDER BY id ASC
        """, (session_id,)).fetchall()

        return [
            {"role": r[0], "content": r[1], "timestamp": r[2], "mood": r[3]}
            for r in rows
        ]

    # ─── Estatísticas ─────────────────────────────────────────────────────────
    def stats(self) -> dict:
        """Estatísticas gerais do histórico."""
        total_msgs = self._conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        total_sess = self._conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        user_msgs  = self._conn.execute(
            "SELECT COUNT(*) FROM messages WHERE role='user'"
        ).fetchone()[0]

        first = self._conn.execute(
            "SELECT MIN(timestamp) FROM messages"
        ).fetchone()[0]

        return {
            "total_messages":   total_msgs,
            "total_sessions":   total_sess,
            "user_messages":    user_msgs,
            "assistant_msgs":   total_msgs - user_msgs,
            "first_message_at": first or "N/A",
        }

    # ─── Limpeza ──────────────────────────────────────────────────────────────
    def clear_all(self):
        self._conn.executescript("""
            DELETE FROM messages;
            DELETE FROM messages_fts;
            DELETE FROM sessions;
        """)
        self._conn.commit()
        log.info("Histórico limpo.")

    def close(self):
        self._conn.close()
