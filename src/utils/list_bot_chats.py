# src/utils/list_bot_chats.py
"""
Liste les chats accessibles au BOT (non interactif) pour récupérer l'ID d'un canal privé.
Usage :
    python -m src.utils.list_bot_chats
"""

from __future__ import annotations
import os
import asyncio

from telethon import TelegramClient
from telethon.tl.types import Channel, Chat, User
from src.config import get_settings


async def _main():
    cfg = get_settings()
    api_id = cfg.telegram_api_id
    api_hash = cfg.telegram_api_hash.get_secret_value()
    bot_token = cfg.telegram_bot_token.get_secret_value()

    os.makedirs(".secrets", exist_ok=True)
    session_path = os.path.join(".secrets", "list_bot_chats")

    client = TelegramClient(session_path, api_id, api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        await client.sign_in(bot_token=bot_token)

    print("🤖 Bot connecté. Récupération des chats…\n")
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        title = dialog.name or ""
        username = getattr(entity, "username", None)
        # id affiché au format -100XXXXXXXXXX pour les channels (megagroup/channel)
        if isinstance(entity, Channel):
            # Telethon stocke l'id interne (channel_id) ; pour le format "peer id", c'est -100* + channel_id
            peer_id = -1000000000000 - 1  # dummy init
            try:
                # Telethon fournit "entity.id" déjà au bon format (-100...)
                peer_id = entity.id
            except Exception:
                pass
            print(f"[CHANNEL]  id={peer_id} | title='{title}' | username=@{username if username else '-'}")
        elif isinstance(entity, Chat):
            print(f"[CHAT]     id={entity.id} | title='{title}' | username=-")
        elif isinstance(entity, User):
            uname = f"@{entity.username}" if entity.username else "-"
            print(f"[USER]     id={entity.id} | name='{title}' | username={uname}")

    await client.disconnect()
    print("\n✅ Fin de la liste. Choisis l'ID du canal cible (format -100XXXXXXXXXX) puis mets-le dans .env.")


def main():
    asyncio.run(_main())


if __name__ == "__main__":
    main()
