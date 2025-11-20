# src/db.py
"""
Stockage SQLite pour les messages Telegram.
- Table messages : id, channel_id, channel_username, message_id, date_utc, text, text_fr, link, collected_at_utc
- Contrainte UNIQUE (channel_id, message_id)
- Migrations légères (ajout de text_fr si absent)
"""

from __future__ import annotations
import os
import sqlite3
from typing import Iterable, Dict, Any, Tuple, Optional, List

from src.config import get_settings


SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL,
    channel_username TEXT,
    message_id INTEGER NOT NULL,
    date_utc TEXT NOT NULL,          -- ISO 8601 (UTC)
    text TEXT,                       -- texte brut
    text_fr TEXT,                    -- traduction FR (nullable)
    link TEXT,                       -- permalien t.me si dispo
    collected_at_utc TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (channel_id, message_id)
);
CREATE INDEX IF NOT EXISTS idx_messages_channel_date ON messages(channel_id, date_utc);
"""


def _connect() -> sqlite3.Connection:
    cfg = get_settings()
    db_path = cfg.sqlite_db_path
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)


def ensure_db() -> None:
    """Crée le schéma et applique les migrations légères si nécessaire."""
    with _connect() as conn:
        conn.executescript(SCHEMA_SQL)
        # Migration : ajouter text_fr si absent (ancien schéma)
        if not _column_exists(conn, "messages", "text_fr"):
            conn.execute("ALTER TABLE messages ADD COLUMN text_fr TEXT")
        conn.commit()


def upsert_messages(rows: Iterable[Dict[str, Any]]) -> Tuple[int, int]:
    """
    Insère une liste de messages.
    Retourne (insert_count, skipped_count) où skipped_count ~ doublons selon la contrainte UNIQUE.
    """
    insert_count = 0
    skipped = 0
    with _connect() as conn:
        cur = conn.cursor()
        for r in rows:
            cur.execute(
                """
                INSERT OR IGNORE INTO messages
                (channel_id, channel_username, message_id, date_utc, text, link)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    r["channel_id"],
                    r.get("channel_username"),
                    r["message_id"],
                    r["date_utc"],
                    r.get("text"),
                    r.get("link"),
                ),
            )
            if cur.rowcount == 1:
                insert_count += 1
            else:
                skipped += 1
        conn.commit()
    return insert_count, skipped


def fetch_untranslated(limit: int = 50) -> List[sqlite3.Row]:
    """Récupère des messages avec text non vide et text_fr NULL, par date descendante."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, channel_id, channel_username, message_id, date_utc, text, link
            FROM messages
            WHERE text IS NOT NULL
              AND TRIM(text) <> ''
              AND (text_fr IS NULL OR TRIM(text_fr) = '')
            ORDER BY date_utc DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return rows


def update_translation(message_id: int, channel_id: int, text_fr: str) -> None:
    """Met à jour la traduction pour un message spécifique."""
    with _connect() as conn:
        conn.execute(
            """
            UPDATE messages
            SET text_fr = ?
            WHERE message_id = ? AND channel_id = ?
            """,
            (text_fr, message_id, channel_id),
        )
        conn.commit()
# --- Export helpers ---

from datetime import datetime, timedelta, timezone
from typing import List

def fetch_translated_since(hours: int) -> List[sqlite3.Row]:
    """Retourne les messages avec text_fr non vide, plus récents que now-`hours` (UTC)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT channel_id, channel_username, message_id, date_utc, text_fr, link
            FROM messages
            WHERE text_fr IS NOT NULL AND TRIM(text_fr) <> ''
              AND date_utc >= ?
            ORDER BY channel_username NULLS LAST, date_utc DESC
            """,
            (cutoff,),
        ).fetchall()
    return rows
