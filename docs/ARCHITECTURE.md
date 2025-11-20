# 🧭 Architecture technique — OSINT Telegram

## 1) Objectif

Mettre en place une collecte et une analyse **automatiques** de messages de **canaux Telegram publics** :
- lecture (compte utilisateur),
- traduction FR,
- regroupement sémantique,
- synthèse Markdown,
- publication quotidienne sur un canal Telegram (bot),
- notification privée si échec (bot → DM).

Le pipeline est **autonome**, **sécurisé** (secrets), et **opérationnel en CI** (GitHub Actions).

---

## 2) Vue d’ensemble (schéma ASCII)

              +----------------------+
              |  GitHub Actions      |
              |  (cron 07:00 Paris)  |
              +----------+-----------+
                         |
                         v

+------------+ read +---------+ tx +-------------+ emb +--------------+
| Telegram |--------->| fetcher |------->| translator |-------> | embeddings |
| (user sess)| | .py | | .py | | .py |
+------------+ +---------+ +-------------+ +--------------+
| | |
| write | write | write
v v v
+-------- SQLite (data/osint.sqlite3) ------------------+
^ |
| |
| +-----------------------+
| | summarizer.py |
| | -> exports/YYYY-MM-DD |
| | _summary.md |
| +-----------+-----------+
| |
| post Markdown v
| +---------------------+
| | publisher.py (bot) |
| | -> Telegram channel |
| +---------------------+
|
+--> on failure -> notify DM (bot -> TELEGRAM_ALERT_CHAT_ID)


---

## 3) Modules & responsabilités

| Fichier | Rôle | Points clés |
|---|---|---|
| `src/config.py` | Charge/valide la config à partir de `.env` et de l’environnement (Pydantic). | Masque les secrets dans les résumés, valeurs par défaut sûres. |
| `src/telegram_client.py` | Crée les clients **Telethon** : `user` (lecture) et `bot` (publication). | Timeouts/réessais adaptés CI, gestion de la StringSession. |
| `src/fetcher.py` | Lit les messages récents des canaux (24h par défaut) et insère en DB. | Résilient : skip canal si handle invalide, logs `[WARN]` sans casser le run. |
| `src/translator.py` | Traduit en FR (OpenAI), garde passages sensibles en VO entre guillemets. | Batching, limites rate-limit, idempotent. |
| `src/embeddings.py` | Calcule les embeddings (OpenAI), stocke en DB, clusterise par similarité. | Cosine sim, seuil `min_sim`, clustering simple efficace. |
| `src/summarizer.py` | Produit le Markdown : TL;DR + sections thématiques, sources, stance. | Dé-dup sémantique intra-groupe, titres clairs, 3 bullets max. |
| `src/publisher.py` | Envoie le Markdown sur Telegram via **bot**. | Split message (< 4k chars), logs “clean” (compatibles CI). |
| `src/main.py` | CLI orchestration : `--fetch-recent`, `--translate`, `--embed`, `--summarize`, `--publish`. | Options `--limit`, `--min-sim`, `--max-groups`, `--dry-run`, etc. |

---

## 4) Modèle de données (SQLite)

Tables principales (simplifiées) :

messages(
channel_id INTEGER,
channel_username TEXT,
message_id INTEGER,
date_utc TEXT,
text_raw TEXT,
text_fr TEXT, -- après traduction
link TEXT, -- t.me/...
PRIMARY KEY(channel_id, message_id)
)

embeddings(
channel_id INTEGER,
message_id INTEGER,
vector BLOB, -- float32[]
model TEXT,
PRIMARY KEY(channel_id, message_id)
)

meta(
key TEXT PRIMARY KEY,
value TEXT
)


Caractéristiques :
- Idempotence : `INSERT OR IGNORE` pour éviter doublons.
- Traduction et embeddings séparés → reprise possible par étape.
- Index implicites via PK composites pour recherches rapides.

---

## 5) Configuration & secrets

### Variables essentielles (chargées via `.env` en local et via Secrets en CI)

- `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`
- `TELEGRAM_USER_SESSION` *(StringSession Telethon — lecture)*
- `TELEGRAM_BOT_TOKEN` *(publication)*
- `TELEGRAM_TARGET_CHANNEL` *(ID numérique recommandé, ex. `-100…`)*
- `TELEGRAM_SOURCE_CHANNELS` *(ex: `@rgrqerzbvb,@regregez,@hazhehrfoiaher`)*
- `OPENAI_API_KEY`
- `FETCH_WINDOW_HOURS` *(48 par défaut)*
- `SQLITE_DB_PATH` *(ex: `data/osint.sqlite3`)*
- `TIMEZONE` *(ex: `Europe/Paris`)*
- `LOG_LEVEL` *(INFO/DEBUG)*

Bonnes pratiques :
- `.env` **git-ignoré** (jamais commité).
- En CI : secrets uniquement via **GitHub Secrets**.
- Le bot **publie uniquement** ; la **lecture** utilise la **StringSession user**.

---

## 6) Orchestration (séquence d’exécution)

### Séquence journalière (CI)

    fetcher (user) → lit N messages / canal (48h)

    translator(OpenAI) → traduit FR (lots)

    embeddings(OpenAI) → calcule vecteurs, clusterise

    summarizer → génère exports/YYYY-MM-DD_summary.md

    publisher (bot) → publie sur Telegram

    notify(on failure) → DM Telegram privé

    upload artifact → dépose le .md dans le run Actions


### Modes d’échec tolérés
- Handle invalide → `[WARN]` + canal ignoré, pipeline continue.
- Rate-limit Telethon → retries + `FloodWait` gérés.
- OpenAI 429/5xx → retries exponentiels (Tenacity).
- Publication segment > 4k → segment ignoré (log `[WARN]`), suite continue.

---

## 7) Paramétrage de la synthèse

- `--min-sim` (clustering inter-messages) : défaut `0.85`.
- `--max-groups` : limite de sections (ex: `5`).
- `--max-per-group` : msgs considérés par groupe (ex: `6`).
- Dé-dup **intra-groupe** (cosine) : seuil ~`0.88–0.93`.
- 3 bullets max par thème ; TL;DR compact (≤ 3 bullets).
- Stance de sources lue via `src/channel_meta.py` (optionnel).

---

## 8) Sécurité

- **Jamais** de secrets en clair dans le code, logs sobres.
- Les valeurs de secrets sont **masquées** automatiquement dans GitHub Actions.
- Le `.env` CI est généré **éphémère** sur runner.
- Le bot doit être **admin** du canal cible.
- Pour canaux privés : utiliser l’**ID numérique** (résolution plus fiable).

---

## 9) CI/CD (GitHub Actions)

Fichier : `.github/workflows/daily.yml`

- Triggers : `schedule` (07:00 Europe/Paris) + `workflow_dispatch`.
- Étapes : checkout → setup Python → install deps → **prepare .env** → run pipeline (user) → publish (bot) → upload artifact → notify on failure.
- Logs “clean” (sans emojis) pour compatibilité terminal/CI.

---

## 10) Runbook (opérations courantes)

- **Changer les sources** : éditer `TELEGRAM_SOURCE_CHANNELS` (local `.env` / CI Secrets ou YAML).
- **Raccourcir le rapport** : baisser `--max-groups`, `--max-per-group`, renforcer dé-dup.
- **Problème de lecture** : vérifier `TELEGRAM_MODE=user` + `TELEGRAM_USER_SESSION`.
- **Problème de publication** : vérifier `TELEGRAM_TARGET_CHANNEL` (ID `-100…`) + bot admin.
- **Timeout/429** : réduire `--limit` en CI (translate/embed), relancer.

---

## 11) Évolutions possibles

- **Classifier idéologique** (pro-X / neutre) automatique par embeddings.
- **Dashboard** (Streamlit) pour stats temporelles, stance agrégée, tendances.
- **Archivage long terme** des `.md` (branche `reports/` ou dépôt privé d’archive).
- **Glossaire automatique** : détection des termes techniques récurrents.

---

## 12) Licence & auteur

- Licence : MIT
- Auteur : **@Camprch** — Projet OSINT automatisé