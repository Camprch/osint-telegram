# src/publisher.py
"""
Publication sur Telegram (logs simplifiés, sans emojis, compatible CI).
"""

from __future__ import annotations
import os
import asyncio
from typing import List, Union
from telethon import TelegramClient
from telethon.errors import FloodWaitError, MessageTooLongError, AuthKeyDuplicatedError
from telethon.tl.types import PeerChannel
from src.config import get_settings

MAX_MSG_LEN = 4000


def _split_markdown(text: str, max_len: int = MAX_MSG_LEN) -> List[str]:
    parts = []
    buf = ""
    for line in text.splitlines(keepends=True):
        if len(line) > max_len:
            if buf.strip():
                parts.append(buf.strip())
                buf = ""
            start = 0
            while start < len(line):
                parts.append(line[start : start + max_len].rstrip())
                start += max_len
            continue
        if len(buf) + len(line) > max_len:
            parts.append(buf.strip())
            buf = line
        else:
            buf += line
    if buf.strip():
        parts.append(buf.strip())
    return parts


async def _resolve_target(client: TelegramClient, target: str) -> Union[int, object]:
    t = (target or "").strip()
    if not t:
        raise RuntimeError("TELEGRAM_TARGET_CHANNEL est vide.")

    try:
        n = int(t)
        if n < 0:
            return n
        else:
            return await client.get_input_entity(PeerChannel(n))
    except ValueError:
        pass

    candidates = [t] if t.startswith("http") else [t if t.startswith("@") else f"@{t}"]
    last_err = None
    for cand in candidates:
        try:
            return await client.get_input_entity(cand)
        except Exception as e:
            last_err = e
    raise RuntimeError(f"Impossible de résoudre la cible '{target}'. Détail: {last_err}")


async def _send_messages(file_path: str, dry_run: bool = False) -> None:
    cfg = get_settings()
    target = cfg.telegram_target_channel
    api_id = cfg.telegram_api_id
    api_hash = cfg.telegram_api_hash.get_secret_value()
    bot_token = cfg.telegram_bot_token.get_secret_value()

    if not os.path.exists(file_path):
        raise FileNotFoundError(file_path)

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read().strip()

    chunks = _split_markdown(content)
    print(f"[INFO] Fichier Markdown : {file_path}")
    print(f"[INFO] Segments à publier : {len(chunks)}")

    if dry_run:
        print("\n--- Prévisualisation (dry-run) ---")
        for i, ch in enumerate(chunks, 1):
            preview = ch[:600]
            print(f"\n--- Segment {i}/{len(chunks)} ---\n{preview}{'...' if len(ch) > 600 else ''}")
        print("\n(dry-run terminé, aucun envoi effectué)")
        return

    os.makedirs(".secrets", exist_ok=True)
    session_path = os.path.join(".secrets", "publisher_bot")

    print("[INFO] Connexion bot non interactive…")
    client = TelegramClient(session_path, api_id, api_hash)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            await client.sign_in(bot_token=bot_token)
    except AuthKeyDuplicatedError:
        print("[WARN] Session corrompue. Regénération…")
        await client.disconnect()
        for ext in (".session", ".session-journal", ""):
            p = session_path + ext
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
        client = TelegramClient(session_path, api_id, api_hash)
        await client.connect()
        await client.sign_in(bot_token=bot_token)

    try:
        entity = await _resolve_target(client, target)
    except RuntimeError as e:
        print(f"[ERROR] {e}")
        await client.disconnect()
        return

    print(f"[INFO] Publication sur Telegram → {target}")
    try:
        for i, chunk in enumerate(chunks, 1):
            try:
                await client.send_message(entity, chunk, parse_mode="md", link_preview=False)
                print(f"[OK] Segment {i}/{len(chunks)} envoyé.")
                await asyncio.sleep(1.5)
            except FloodWaitError as e:
                print(f"[WAIT] FloodWait {e.seconds}s, pause…")
                await asyncio.sleep(e.seconds + 2)
                await client.send_message(entity, chunk, parse_mode="md", link_preview=False)
                print(f"[OK] Segment {i} envoyé après attente.")
            except MessageTooLongError:
                print(f"[WARN] Segment {i} trop long, ignoré.")
            except Exception as e:
                print(f"[ERROR] Segment {i}: {e}")
                continue
    finally:
        await client.disconnect()

    print("[DONE] Publication terminée avec succès.")


def publish(file_path: str, dry_run: bool = False) -> None:
    asyncio.run(_send_messages(file_path, dry_run=dry_run))
