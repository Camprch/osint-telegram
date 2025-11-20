# src/summarizer.py
"""
Synthèse OSINT — rendu Telegram compact (date claire, pas de pavé).
- 3 bullets max par thème
- Pas de séparateurs '---'
- Sources en mode bref (1-2 liens max par section)
- Fallback fuseau horaire (Windows OK, pas de tzdata)
"""

from __future__ import annotations
import os
import json
import sqlite3
import numpy as np
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Tuple
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import get_settings
from src.embeddings import cluster_embeddings


@dataclass
class SummarizeParams:
    min_sim: float = 0.85
    max_groups: int = 6
    max_per_group: int = 8
    temperature: float = 0.2
    model: str = ""
    dedupe_sim: float = 0.88


SYSTEM_GROUP = (
    "Tu es un analyste OSINT. Écris une synthèse courte et claire en français, sans spéculation.\n"
    "- Ton journalistique sobre et informatif.\n"
    "- Résume en 3 points maximum, concis et non redondants.\n"
    "- Le 'title' doit donner le contexte (lieu/acteur/sujet principal).\n"
    "- Réponds STRICTEMENT en JSON: {\"title\": str, \"bullets\": [str, ...]}."
)

SYSTEM_TLDR = (
    "Tu es un analyste OSINT. À partir des résumés fournis, produis un TL;DR (max 3 points).\n"
    "Réponds STRICTEMENT en JSON: {\"tldr\": [str, ...]}."
)

# ---------- Mise en forme compacte ----------

def _date_fr_compact(d_utc: datetime) -> str:
    """Retourne une date très lisible '06/11/2025' (Europe/Paris si possible, sinon fuseau local)."""
    try:
        from zoneinfo import ZoneInfo
        dt = d_utc.astimezone(ZoneInfo("Europe/Paris"))
    except Exception:
        dt = d_utc.astimezone()
    return dt.strftime("%d/%m/%Y")


# ---------- DB / OpenAI utils ----------

def _open_db():
    cfg = get_settings()
    conn = sqlite3.connect(cfg.sqlite_db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _get_client():
    from openai import OpenAI
    cfg = get_settings()
    return OpenAI(api_key=cfg.openai_api_key.get_secret_value()), cfg.openai_model


@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def _chat_json(system_prompt: str, user_prompt: str, temperature: float) -> dict:
    client, model = _get_client()
    resp = client.chat.completions.create(
        model=model or "gpt-4o-mini",
        temperature=temperature,
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user", "content": user_prompt}],
    )
    content = (resp.choices[0].message.content or "").strip()
    if content.startswith("```"):
        content = content.strip("` \n").split("\n", 1)[-1]
    return json.loads(content)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denom) if denom else 0.0


def _fetch_vectors_for(pairs: List[Tuple[str, int]]) -> Dict[Tuple[str, int], np.ndarray]:
    vectors: Dict[Tuple[str, int], np.ndarray] = {}
    if not pairs:
        return vectors
    with _open_db() as conn:
        for chunk in [pairs[i:i+300] for i in range(0, len(pairs), 300)]:
            where = " OR ".join("(m.channel_username=? AND m.message_id=?)" for _ in chunk)
            params = [x for pair in chunk for x in pair]
            rows = conn.execute(f"""
                SELECT m.channel_username, m.message_id, e.vector
                FROM embeddings e
                JOIN messages m ON m.message_id=e.message_id AND m.channel_id=e.channel_id
                WHERE {where}
            """, params).fetchall()
            for r in rows:
                vectors[(r["channel_username"], r["message_id"])] = np.frombuffer(r["vector"], dtype=np.float32)
    return vectors


def _dedupe(items: List[dict], vectors: Dict[Tuple[str, int], np.ndarray], thr: float) -> List[dict]:
    kept, used = [], set()
    for i, a in enumerate(items):
        if i in used:
            continue
        va = vectors.get((a.get("channel"), a.get("id")))
        group = [i]
        for j, b in enumerate(items):
            if j <= i or j in used:
                continue
            vb = vectors.get((b.get("channel"), b.get("id")))
            if va is not None and vb is not None and _cosine(va, vb) > thr:
                group.append(j)
        rep = max(group, key=lambda k: len(items[k].get("text", "")))
        kept.append(items[rep])
        used.update(group)
    return kept


def _summarize_group(texts: List[str], temperature: float) -> Tuple[str, List[str]]:
    joined = "\n---\n".join(texts)
    data = _chat_json(SYSTEM_GROUP, f"Voici plusieurs messages :\n{joined}", temperature)
    title = data.get("title", "Thème général").strip()
    bullets = [b.strip() for b in data.get("bullets", [])][:3]
    return title, bullets


def _build_tldr(summaries: List[str], temperature: float) -> List[str]:
    if not summaries:
        return []
    joined = "\n".join(summaries)
    data = _chat_json(SYSTEM_TLDR, f"Voici plusieurs résumés :\n{joined}", temperature)
    return [b.strip() for b in data.get("tldr", [])][:3]


# ---------- Assembly ----------

def build_summary_markdown(params: SummarizeParams) -> Tuple[str, Dict[str, int]]:
    clusters = cluster_embeddings(min_sim=params.min_sim)
    if not clusters:
        d = _date_fr_compact(datetime.now(timezone.utc))
        return (f"🛰️ **OSINT – {d}**\n\n*(Aucun contenu)*", {"groups": 0})

    clusters = clusters[:params.max_groups]
    all_pairs = [(m["channel"], m["id"]) for g in clusters for m in g[:params.max_per_group]]
    vectors = _fetch_vectors_for(all_pairs)

    sections, short_summaries = [], []
    msgs_used = 0

    for g in clusters:
        items = _dedupe(g[:params.max_per_group], vectors, params.dedupe_sim)
        texts = [m["text"] for m in items if m.get("text")]
        if not texts:
            continue
        title, bullets = _summarize_group(texts, params.temperature)
        msgs_used += len(texts)

        # Sources brèves: on affiche 1 à 2 liens max
        src_lines = []
        with _open_db() as conn:
            shown = 0
            for m in items:
                ch = m["channel"]; mid = m["id"]
                row = conn.execute(
                    "SELECT link, date_utc FROM messages WHERE channel_username=? AND message_id=?",
                    (ch, mid)
                ).fetchone()
                if shown < 2:
                    link = row["link"] if row else ""
                    src_lines.append(f"[{ch} #{mid}]({link})")
                    shown += 1
        sources_md = " • ".join(src_lines)

        bullets_md = "\n".join(f"• {b}" for b in bullets)

        sections.append(
            f"🔹 {title}\n"
            f"{bullets_md}\n"
            f"📎 {sources_md}\n"
        )
        short_summaries.append(f"{title}: " + "; ".join(bullets))

    tldr = _build_tldr(short_summaries, params.temperature)
    d = _date_fr_compact(datetime.now(timezone.utc))
    meta = f"{int(os.getenv('FETCH_WINDOW_HOURS', get_settings().fetch_window_hours))}h • {len(sections)} thèmes • {msgs_used} msgs"

    header = [
        f"🛰️ **OSINT – {d}**",
        meta,
        "",
        "📌 Essentiel",
    ] + [f"• {x}" for x in tldr] + [""]

    md = "\n".join(header + sections)
    stats = {"groups": len(sections), "msgs_used": msgs_used}
    return md, stats


def write_summary_markdown(content: str, out_path: str | None = None) -> str:
    os.makedirs("exports", exist_ok=True)
    if not out_path:
        today = datetime.now(timezone.utc).date().isoformat()
        out_path = f"exports/{today}_summary.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content.strip() + "\n")
    return out_path
