# src/utils/list_user_channels.py
"""
Liste les canaux/supergroupes accessibles avec TON COMPTE UTILISATEUR (StringSession).
Affiche : channel_id (positif), peer_id (-100...), titre, username s'il existe.
Usage :
  python -m src.utils.list_user_channels
"""

from __future__ import annotations
import os
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import Channel
from telethon.utils import get_peer_id
from src.config import get_settings

def _load_user_session() -> StringSession:
    path = os.path.join(".secrets", "telegram_session")
    if not os.path.exists(path):
        raise FileNotFoundError(
            ".secrets/telegram_session absent. Générez-le avec : TELEGRAM_MODE=bot python -m src.login_user"
        )
    with open(path, "r", encoding="utf-8") as f:
        return StringSession(f.read().strip())

async def _main():
    cfg = get_settings()
    session = _load_user_session()
    async with TelegramClient(session, cfg.telegram_api_id, cfg.telegram_api_hash.get_secret_value()) as client:
        print("👤 User connecté. Canaux/supergroupes visibles :\n")
        async for d in client.iter_dialogs():
            e = d.entity
            if isinstance(e, Channel):
                username = f"@{e.username}" if getattr(e, "username", None) else "-"
                channel_id = e.id  # positif (ID interne du channel)
                peer_id = get_peer_id(e)  # négatif, forme -100… utilisable partout
                print(f"[CHANNEL] channel_id={channel_id} | peer_id={peer_id} | title='{d.name}' | username={username}")
        print("\n✅ Fin de la liste. Utilise de préférence le peer_id (-100…).")

def main():
    asyncio.run(_main())

if __name__ == "__main__":
    main()
