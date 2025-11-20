# src/fetcher.py
"""
Collecte des messages récents depuis des canaux publics Telegram.
- Fenêtre temporelle en heures (paramétrable) + limite de messages par canal.
- Diagnostic: fonctions utilitaires pour lister les derniers messages.
"""

from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple

from telethon.tl.types import Channel, User, Chat
from telethon.errors import RPCError

from src.config import get_settings
from src.telegram_client import open_client

UTC = timezone.utc


def _build_link(entity: Channel | Chat | User, msg_id: int) -> str | None:
    username = getattr(entity, "username", None)
    if username:
        return f"https://t.me/{username}/{msg_id}"
    return None


async def fetch_recent(hours: Optional[int] = None, per_channel: int = 200, channels: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Récupère jusqu'à `per_channel` messages par canal, puis filtre par fenêtre temporelle `hours`.
    - hours=None => utilise cfg.fetch_window_hours
    - channels=None => utilise cfg.telegram_source_channels
    """
    cfg = get_settings()
    window_h = hours if hours is not None else cfg.fetch_window_hours
    cutoff = datetime.now(tz=UTC) - timedelta(hours=window_h)
    handles = channels if channels is not None else cfg.telegram_source_channels

    all_rows: List[Dict[str, Any]] = []

    async with open_client() as client:
        for handle in handles:
            handle = (handle or "").strip()
            if not handle:
                continue

            try:
                entity = await client.get_entity(handle)
            except RPCError as e:
                print(f"⚠️  Résolution échouée pour {handle}: {e}")
                continue

            # Récupère les N derniers messages (plus simple et fiable)
            async for msg in client.iter_messages(entity, limit=per_channel):
                if not msg:
                    continue
                # date -> UTC
                msg_dt = msg.date
                if msg_dt and msg_dt.tzinfo is None:
                    msg_dt = msg_dt.replace(tzinfo=UTC)

                # Filtre temporel
                if msg_dt and msg_dt < cutoff:
                    continue

                text = (msg.message or getattr(msg, "text", "") or "").strip()
                if not text:
                    continue

                row = {
                    "channel_id": getattr(entity, "id", None),
                    "channel_username": getattr(entity, "username", None),
                    "message_id": msg.id,
                    "date_utc": (msg_dt.isoformat() if msg_dt else datetime.now(tz=UTC).isoformat()),
                    "text": text,
                    "link": _build_link(entity, msg.id),
                }
                all_rows.append(row)

    return all_rows


async def list_latest(per_channel: int = 3) -> List[Tuple[str, List[Tuple[int, str, str]]]]:
    """
    Retourne, pour chaque canal, un petit aperçu des derniers messages:
    [(handle, [(msg_id, date_iso, link), ...]), ...]
    """
    cfg = get_settings()
    preview: List[Tuple[str, List[Tuple[int, str, str]]]] = []
    async with open_client() as client:
        for handle in cfg.telegram_source_channels:
            handle = (handle or "").strip()
            if not handle:
                continue
            try:
                entity = await client.get_entity(handle)
            except RPCError as e:
                preview.append((handle, []))
                continue

            entries: List[Tuple[int, str, str]] = []
            async for msg in client.iter_messages(entity, limit=per_channel):
                dt = msg.date
                if dt and dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                entries.append(
                    (msg.id, (dt.isoformat() if dt else ""), _build_link(entity, msg.id) or "")
                )
            preview.append((handle, entries))
    return preview
