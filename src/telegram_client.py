# src/telegram_client.py
"""
Client Telegram (bot ou user) basé sur Telethon.
- mode bot  : start(bot_token=...)
- mode user : start() avec StringSession (lecture canaux publics)
"""

from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Any

from telethon import TelegramClient
from telethon.errors import RPCError
from telethon.sessions import StringSession

from src.config import get_settings


@asynccontextmanager
async def open_client() -> AsyncIterator[TelegramClient]:
    cfg = get_settings()
    if cfg.telegram_mode == "bot":
        session = StringSession()  # éphémère
        client = TelegramClient(
            session=session,
            api_id=cfg.telegram_api_id,
            api_hash=cfg.telegram_api_hash.get_secret_value(),
        )
        try:
            await client.start(bot_token=cfg.telegram_bot_token.get_secret_value())
            yield client
        finally:
            await client.disconnect()
    else:
        # mode user
        session = StringSession(cfg.telegram_user_session.get_secret_value())
        client = TelegramClient(
            session=session,
            api_id=cfg.telegram_api_id,
            api_hash=cfg.telegram_api_hash.get_secret_value(),
        )
        try:
            await client.start()  # pas de bot_token
            yield client
        finally:
            await client.disconnect()


async def whoami() -> Dict[str, Any]:
    """Retourne des infos non sensibles sur l'entité connectée (bot ou user)."""
    async with open_client() as client:
        try:
            me = await client.get_me()
        except RPCError as e:
            raise RuntimeError(f"Échec de récupération du profil : {e}") from e

        return {
            "id": me.id,
            "is_bot": bool(getattr(me, "bot", False)),
            "username": getattr(me, "username", None),
            "first_name": getattr(me, "first_name", None),
            "last_name": getattr(me, "last_name", None),
        }


def run_async(coro):
    """Exécute une coroutine avec une boucle asyncio sûre (compatible Windows/VS Code)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return asyncio.ensure_future(coro)
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)
