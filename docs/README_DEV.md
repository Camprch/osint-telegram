# 👨‍💻 Guide Développeur — OSINT Telegram

Ce document explique **comment exécuter, tester et dépanner** le projet OSINT Telegram en local (Windows 11 + VS Code + Git Bash).

---

## 1️⃣ Prérequis

- Python 3.10 à 3.13  
- VS Code + extensions Python  
- Git Bash (terminal recommandé)  
- Un compte Telegram + `api_id` / `api_hash` (https://my.telegram.org)  
- Une clé OpenAI (`OPENAI_API_KEY`)

---

## 2️⃣ Installation locale

```bash
# Cloner
git clone https://github.com/Camprch/osint-telegram.git
cd osint-telegram

# Créer l'environnement virtuel
python -m venv .venv
source .venv/Scripts/activate   # (PowerShell: .venv\Scripts\Activate.ps1)

# Installer les dépendances
pip install --upgrade pip
pip install -r requirements.txt

# Vérification
python -c "import telethon, openai, dotenv; print('deps OK')"

3️⃣ Fichier .env (non commité)

Créer un fichier .env à la racine du projet :

TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

TELEGRAM_BOT_TOKEN=1234567890:AA...
TELEGRAM_TARGET_CHANNEL=-100xxxxxxxxxxxx
TELEGRAM_SOURCE_CHANNELS=@qgstrgsttg,@zefafa,@arfrfarf

OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_EMBEDDINGS_MODEL=text-embedding-3-small

FETCH_WINDOW_HOURS=48
SQLITE_DB_PATH=data/osint.sqlite3
TIMEZONE=Europe/Paris
LOG_LEVEL=INFO

TELEGRAM_MODE=user
# Optionnel : TELEGRAM_USER_SESSION=1A...

    .env est ignoré par Git ; ne jamais le commiter.

4️⃣ Générer la StringSession Telethon

mkdir -p .secrets
TELEGRAM_MODE=bot python -m src.login_user

    Entrer ton numéro Telegram (+33...)

    Copier le code reçu

    Un fichier .secrets/telegram_session est créé

    Option : copier son contenu dans TELEGRAM_USER_SESSION= du .env

5️⃣ Commandes utiles

# 1. Lecture des messages
python -m src.main --fetch-recent --per-channel 200

# 2. Traduction
python -m src.main --translate --limit 200

# 3. Embeddings + clustering
python -m src.main --embed --limit 400

# 4. Synthèse Markdown
python -m src.main --summarize --min-sim 0.85 --max-groups 5 --max-per-group 6

# 5. Publication (bot)
python -m src.main --publish

Rapports générés dans exports/YYYY-MM-DD_summary.md.
6️⃣ Astuces & conseils

    Handles valides : toujours commencer par @

    Canal cible : utiliser l’ID numérique (-100…)

    Bot admin obligatoire dans le canal cible

    Doublons : la synthèse fait déjà une dé-duplication sémantique

    Logs : sobres, compatibles CI (pas d’emojis)

7️⃣ Workflow GitHub Actions (rappel)

    Crée un .env temporaire à partir des secrets

    Lecture via StringSession (user)

    Publication via bot

    Envoi du résumé sur Telegram + artefact .md

    En cas d’échec : notification Telegram privée

8️⃣ Dépannage rapide
Erreur	Cause probable	Solution
ApiIdInvalidError	Mauvais api_id / api_hash	Vérifie sur my.telegram.org
BotMethodInvalidError	Lecture avec un bot	Passe en TELEGRAM_MODE=user
UsernameNotOccupiedError	Handle inexistant	Corrige les TELEGRAM_SOURCE_CHANNELS
CheckChatInviteRequest	Canal privé non résolu	Utilise l’ID numérique + bot admin
Invalid workflow file	Mauvais encodage	UTF-8 (LF), pas CRLF
Lenteur CI	Trop de messages	Baisse --limit ; normal ≈ 5–8 min
9️⃣ Sécurité

    .env, .secrets/, *.session → git-ignorés

    Secrets → uniquement dans .env (local) ou GitHub Secrets

    Aucun secret affiché dans les logs

🔟 Schéma textuel du pipeline

Telegram (user) -> fetcher -> SQLite -> translator (OpenAI)
                 -> embeddings -> summarizer -> Markdown
Telegram (bot) <- publisher

🧩 Checklist “premier run local”

.venv activé

.env complet

TELEGRAM_MODE=user

.secrets/telegram_session présent

--fetch-recent OK

--summarize produit un .md

    --publish envoie sur Telegram

📄 Licence

Ce projet est sous licence MIT.
© 2025 – Camille Paroche (@Camprch)
➡️ docs/LICENSE.md
