# src/embeddings.py
"""
Gestion des embeddings OpenAI (text-embedding-3-small) pour les messages traduits.
- Génère des vecteurs (numpy arrays) pour text_fr non encore vectorisés.
- Stocke dans SQLite (table embeddings).
- Fournit un regroupement basique par similarité cosinus.
"""

from __future__ import annotations
import os
import io
import sqlite3
import numpy as np
from typing import List, Tuple, Dict
from tqdm import tqdm

from src.config import get_settings
from src.db import ensure_db

# --- Table et schéma ---
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    vector BLOB NOT NULL,
    UNIQUE (message_id, channel_id)
);
CREATE INDEX IF NOT EXISTS idx_embeddings_message ON embeddings(message_id);
"""

def _connect() -> sqlite3.Connection:
    cfg = get_settings()
    os.makedirs(os.path.dirname(cfg.sqlite_db_path), exist_ok=True)
    conn = sqlite3.connect(cfg.sqlite_db_path)
    conn.row_factory = sqlite3.Row
    return conn

def ensure_embeddings_table() -> None:
    """Crée la table embeddings si nécessaire."""
    with _connect() as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()

# --- Accès messages traduits sans embeddings ---
def fetch_unembedded(limit: int = 100) -> List[sqlite3.Row]:
    """Retourne les messages traduits sans vecteur associé."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT m.channel_id, m.message_id, m.text_fr
            FROM messages m
            LEFT JOIN embeddings e ON e.message_id = m.message_id AND e.channel_id = m.channel_id
            WHERE m.text_fr IS NOT NULL AND TRIM(m.text_fr) <> '' AND e.id IS NULL
            ORDER BY m.date_utc DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return rows

def insert_embedding(channel_id: int, message_id: int, vector: np.ndarray) -> None:
    """Stocke un embedding dans la base."""
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO embeddings (channel_id, message_id, vector) VALUES (?, ?, ?)",
            (channel_id, message_id, vector.astype(np.float32).tobytes()),
        )
        conn.commit()

# --- OpenAI embeddings ---
def _get_openai_client():
    from openai import OpenAI
    cfg = get_settings()
    return OpenAI(api_key=cfg.openai_api_key.get_secret_value()), cfg

def compute_embeddings(limit: int = 100) -> Tuple[int, int]:
    """
    Calcule les embeddings pour les messages non vectorisés.
    Retourne (traités, total).
    """
    ensure_db()
    ensure_embeddings_table()
    rows = fetch_unembedded(limit)
    if not rows:
        print("ℹ️  Aucun message à vectoriser.")
        return 0, 0

    client, cfg = _get_openai_client()
    texts = [r["text_fr"] for r in rows]
    ids = [(r["channel_id"], r["message_id"]) for r in rows]

    print(f"🧠 Calcul des embeddings pour {len(texts)} messages…")
    batch_size = 50
    total = len(texts)
    done = 0
    for i in tqdm(range(0, total, batch_size)):
        batch = texts[i : i + batch_size]
        resp = client.embeddings.create(model=cfg.openai_embeddings_model, input=batch)
        for j, data in enumerate(resp.data):
            vec = np.array(data.embedding, dtype=np.float32)
            ch, mid = ids[i + j]
            insert_embedding(ch, mid, vec)
            done += 1
    return done, total

# --- Similarité / regroupement ---
def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)

def cluster_embeddings(min_sim: float = 0.85) -> List[List[Dict]]:
    """Regroupe les messages par similarité cosinus."""
    ensure_embeddings_table()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT m.channel_username, m.message_id, m.text_fr, e.vector
            FROM embeddings e
            JOIN messages m ON m.message_id = e.message_id AND m.channel_id = e.channel_id
            WHERE m.text_fr IS NOT NULL
            """
        ).fetchall()

    if not rows:
        print("ℹ️  Aucun embedding trouvé.")
        return []

    # Vecteurs + infos
    vecs = [np.frombuffer(r["vector"], dtype=np.float32) for r in rows]
    texts = [r["text_fr"] for r in rows]
    infos = [{"channel": r["channel_username"], "id": r["message_id"], "text": r["text_fr"]} for r in rows]

    clusters: List[List[Dict]] = []
    used = set()
    for i in range(len(vecs)):
        if i in used:
            continue
        group = [infos[i]]
        used.add(i)
        for j in range(i + 1, len(vecs)):
            if j in used:
                continue
            sim = cosine_similarity(vecs[i], vecs[j])
            if sim >= min_sim:
                group.append(infos[j])
                used.add(j)
        clusters.append(group)
    return clusters
