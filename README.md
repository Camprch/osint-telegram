#### 🛰️ OSINT Telegram — Daily Automated Intelligence Feed

### 🇫🇷 Résumé (FR)

Ce projet collecte automatiquement tous les messages des dernières 24h sur des canaux telegram prédéfinis, les traduit en français, supprime les doublons, les regroupe par thèmes, puis en produit une synthèse publiée chaque jour à 7h par un bot sur un canal Telegram privé.

Il fonctionne en mode totalement autonome grâce à **GitHub Actions** et un pipeline Python robuste.


### 🇬🇧 Summary (EN)

This project automatically gathers public Telegram channel messages, translates them into French, groups them by topics, and generates a Markdown daily summary that is published to a Telegram channel.

It is fully autonomous thanks to GitHub Actions and a robust Python pipeline.

---

## ⚙️ Architecture du projet

src/
├── config.py # Chargement et validation de la configuration (.env)
├── telegram_client.py # Connexion Telethon (user/bot)
├── fetcher.py # Lecture des messages Telegram
├── translator.py # Traduction des textes via OpenAI
├── embeddings.py # Génération et clustering thématique
├── summarizer.py # Synthèse Markdown quotidienne
├── publisher.py # Publication Telegram (bot)
└── main.py # CLI principale (fetch, translate, summarize, publish)

---

## 🔐 Sécurité & Secrets

Le projet s’appuie sur un fichier `.env` **non versionné** (et sur les **GitHub Secrets** en CI).

Secrets requis :
- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_USER_SESSION` *(StringSession utilisateur Telethon)*
- `TELEGRAM_TARGET_CHANNEL`
- `OPENAI_API_KEY`
- `TELEGRAM_ALERT_CHAT_ID`

---

## 💬 Commandes disponibles

python -m src.main --fetch-recent
python -m src.main --translate
python -m src.main --embed
python -m src.main --summarize
python -m src.main --publish

---

## 📁 Structure du dépôt

.github/workflows/daily.yml → Workflow GitHub Actions
data/ → Base SQLite
exports/ → Rapports Markdown quotidiens
src/ → Code source Python
docs/ → Documentation technique

---

## 📚 Documentation technique

➡️ Voir [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

---

## 📄 Licence

Ce projet est sous licence MIT.
© 2025 – Camille Paroche (@Camprch)
➡️ docs/LICENSE.md