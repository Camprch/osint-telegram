# src/utils/resolve_channel_id.py
"""
Résout l'ID numérique d'un canal (privé/public) avec le COMPTE UTILISATEUR (StringSession).
Usage:
    python -m src.utils.resolve_channel_id --target "<@handle|nom|lien t.me/...>"

Prérequis:
- .secrets/telegram_session (StringSession utilisateur) doit exister (créée via src/login_user.py)
- TELEGRAM_API_ID / TELEGRAM_API_HASH présents dans .env
"""

from __future__ import annotations
import os
import argparse
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import RPCError
from src.config import get_settings


def _load_user_session() -> StringSession:
    # on lit la session utilisateur depuis .secrets/telegram_session
    path = os.path.join(".secrets", "telegram_session")
    if not os.path.exists(path):
        raise FileNotFoundError(
            ".secrets/telegram_session absent. Générez-le avec: TELEGRAM_MODE=bot python -m src.login_user"
        )
    with open(path, "r", encoding="utf-8") as f:
        s = f.read().strip()
    return StringSession(s)


async def _main(target: str):
    cfg = get_settings()
    api_id = cfg.telegram_api_id
    api_hash = cfg.telegram_api_hash.get_secret_value()

    session = _load_user_session()
    async with TelegramClient(session, api_id, api_hash) as client:
        cand = target.strip()
        # autoriser nom brut, @handle, lien t.me
        try:
            entity = await client.get_entity(cand if cand.startswith("@") or cand.startswith("http") else f"@{cand}")
        except Exception:
            # dernier essai: tel quel
            entity = await client.get_entity(cand)

        # Pour les channels privés, Telethon expose l'id au format pair (-100…)
        print("✅ Résolution réussie.")
        print(f"Title     : {getattr(entity, 'title', getattr(entity, 'first_name', ''))}")
        print(f"Username  : @{getattr(entity, 'username', '-')}")
        print(f"ID (peer) : {entity.id}")  # <-- à copier dans TELEGRAM_TARGET_CHANNEL

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--target", required=True, help="Nom, @handle ou lien t.me du canal.")
    args = p.parse_args()
    asyncio.run(_main(args.target))

if __name__ == "__main__":
    main()
