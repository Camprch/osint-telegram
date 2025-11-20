from telethon.sync import TelegramClient
from telethon.sessions import StringSession
import os

from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

# Si tu utilises python-dotenv, décommente :
# from dotenv import load_dotenv
# load_dotenv()

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]

BASE_DIR = Path(__file__).resolve().parent.parent
SECRETS_DIR = BASE_DIR / ".secrets"
SECRETS_DIR.mkdir(exist_ok=True)

SESSION_PATH = SECRETS_DIR / "telegram_session"

with TelegramClient(StringSession(), API_ID, API_HASH) as client:
    session_str = client.session.save()

    # Affiche la session pour que tu puisses la copier
    print("\n=== TELEGRAM_USER_SESSION (copie tout) ===\n")
    print(session_str)
    print("\n=== FIN ===\n")

    # Écrit aussi dans .secrets/telegram_session
    SESSION_PATH.write_text(session_str, encoding="utf-8")
    print(f"✅ Session écrite dans : {SESSION_PATH}")
