# src/login_user.py
"""
Génère une StringSession (mode user) pour Telethon, sans prompts internes.
- Demande le numéro, envoie le code, gère la 2FA si besoin.
- Écrit la session dans .secrets/telegram_session (git-ignoré) et affiche un aperçu masqué.
"""

from __future__ import annotations
import os
from getpass import getpass

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneNumberInvalidError
from telethon.sessions import StringSession

from src.config import get_settings


def main() -> int:
    cfg = get_settings()
    os.makedirs(".secrets", exist_ok=True)

    print("⚠️  Opération sensible : ne partage jamais la StringSession.")
    phone = input("Numéro de téléphone (format international, ex: +33612345678) : ").strip()

    # Nettoyage simple : pas d'espaces
    phone = phone.replace(" ", "")

    try:
        client = TelegramClient(StringSession(), cfg.telegram_api_id, cfg.telegram_api_hash.get_secret_value())
        client.connect()

        if not client.is_user_authorized():
            try:
                client.send_code_request(phone)
            except PhoneNumberInvalidError:
                raise SystemExit("❌ Numéro invalide. Vérifie le format (+33…).")

            code = input("Code Telegram reçu (SMS/Telegram) : ").strip()
            try:
                client.sign_in(phone=phone, code=code)
            except PhoneCodeInvalidError:
                raise SystemExit("❌ Code invalide. Relance le script pour réessayer.")
            except SessionPasswordNeededError:
                pwd = getpass("Mot de passe 2FA (ne s'affiche pas) : ")
                client.sign_in(password=pwd)

        session_str = client.session.save()
        path = ".secrets/telegram_session"
        with open(path, "w", encoding="utf-8") as f:
            f.write(session_str)

        print("\n✅ Session générée et écrite dans:", path)
        print("👉 Copie-la dans ton .env sous TELEGRAM_USER_SESSION (une seule ligne).")
        print("Aperçu masqué :", "…" + session_str[-8:])
        client.disconnect()
        return 0

    except KeyboardInterrupt:
        print("\nInterrompu.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
