# 🛰️ OSINT Telegram — Daily Automated Intelligence Feed

## 🇫🇷 Résumé (FR)

Ce projet collecte automatiquement **tous les messages** des dernières 24h sur des **canaux telegram prédéfinis**, les **traduit en français**, **supprime les doublons**, les **regroupe par thèmes**, puis en produit une **synthèse** publiée chaque jour à 7h par un bot sur un **canal Telegram privé**.

Il fonctionne en mode totalement autonome grâce à **GitHub Actions** et un pipeline Python robuste.

### 🧩 Fonctionnalités principales
- Collecte automatique des 24 dernières heures de messages.
- Traduction contextuelle multilingue → français (via OpenAI).
- Regroupement thématique par similarité sémantique (embeddings).
- Synthèse quotidienne (TL;DR + sections + sources).
- Publication automatique sur un canal Telegram.
- Alerte Telegram privée en cas d’échec du workflow.

---

## 🇬🇧 Summary (EN)

This project automatically gathers **public Telegram channel messages**, **translates them into French**, **groups them by topics**, and generates a **Markdown daily summary** that is published to a **Telegram channel**.

It is fully autonomous thanks to **GitHub Actions** and a robust Python pipeline.

### 🧠 Key Features
- Collects last 24h of Telegram messages.
- Translates to French with contextual accuracy (OpenAI API).
- Groups related messages via semantic embeddings.
- Generates structured Markdown reports (TL;DR + sources).
- Publishes automatically via Telegram Bot.
- Sends alert on failure (Telegram private DM).

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


### Data flow (simplifié)

Telegram (user) → fetcher.py
↓
SQLite database
↓
translator.py (OpenAI)
↓
embeddings.py (OpenAI)
↓
summarizer.py
↓
Markdown report (.md)
↓
Telegram (bot) → publisher.py


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

## 🧱 CI/CD (GitHub Actions)

### 🔁 Exécution quotidienne
Le workflow `.github/workflows/daily.yml` :
1. installe l’environnement Python,  
2. prépare le `.env` à partir des secrets,  
3. exécute le pipeline complet,  
4. publie sur Telegram,  
5. upload le résumé `.md`,  
6. notifie en cas d’erreur.

### 💬 Commandes disponibles

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

## 🧾 Licence

Ce projet est sous licence MIT.  
© 2025 – Camille Paroche (@Camprch)
