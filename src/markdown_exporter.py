# src/markdown_exporter.py
"""
Export Markdown brut des messages traduits (FR), avec déduplication de contenu.
- Regroupe par canal.
- Déduplique sur la fenêtre spécifiée : mêmes contenus (normalisés) => 1 seule entrée.
- Produit un fichier dans exports/YYYY-MM-DD_raw.md (par défaut).
"""

from __future__ import annotations
import os
import re
import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from src.config import get_settings
from src.db import ensure_db, fetch_translated_since


_whitespace_re = re.compile(r"\s+")
_soft_punct_re = re.compile(r"[·•\u2026]+")

def _normalize_text(s: str) -> str:
    """
    Normalisation pour déduplication :
    - trim
    - lowercase
    - compresse espaces
    - supprime quelques ponctuations faibles ('•', '…', puces)
    """
    if not s:
        return ""
    s2 = s.strip().lower()
    s2 = _soft_punct_re.sub(" ", s2)
    s2 = _whitespace_re.sub(" ", s2)
    return s2.strip()

def _hash_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def build_markdown(hours: int) -> Tuple[str, int, int, Dict[str, int]]:
    """
    Construit le contenu Markdown (string) pour la fenêtre `hours`.
    Retourne: (markdown, total_items_after_dedupe, total_seen, per_channel_counts)
    """
    cfg = get_settings()
    ensure_db()
    rows = fetch_translated_since(hours=hours)

    seen_hashes: set[str] = set()
    grouped: Dict[str, List[Tuple[str, str, str]]] = {}  # by channel -> list of (dt_iso, link, text_fr)
    total_seen = 0
    total_kept = 0

    for r in rows:
        total_seen += 1
        text_fr = (r["text_fr"] or "").strip()
        if not text_fr:
            continue
        norm = _normalize_text(text_fr)
        if not norm:
            continue
        h = _hash_text(norm)
        if h in seen_hashes:
            continue
        seen_hashes.add(h)
        ch = r["channel_username"] or f"id_{r['channel_id']}"
        dt_iso = r["date_utc"] or ""
        link = r["link"] or ""
        grouped.setdefault(ch, []).append((dt_iso, link, text_fr))
        total_kept += 1

    # Tri par canal (alpha), puis par date desc (déjà OK)
    parts: List[str] = []
    today = datetime.now(timezone.utc).date().isoformat()
    header = (
        f"# OSINT – Rapport brut du {today}\n\n"
        f"**Fenêtre :** {hours}h • **Sources :** {', '.join(sorted(grouped.keys())) if grouped else 'Aucune'}  \n"
        f"**Messages traduits (après déduplication) :** {total_kept}\n\n"
        f"---\n"
    )
    parts.append(header)

    per_channel_counts: Dict[str, int] = {}
    for channel in sorted(grouped.keys(), key=lambda x: x.lower()):
        parts.append(f"## {channel}\n")
        count = 0
        for dt_iso, link, text_fr in grouped[channel]:
            safe_link = f"[Lien]({link}) — " if link else ""
            date_str = f"*{dt_iso}*" if dt_iso else ""
            # Chaque entrée en puce avec citation du texte
            parts.append(f"- {safe_link}{date_str}\n  > {text_fr}\n")
            count += 1
        parts.append("\n---\n")
        per_channel_counts[channel] = count

    return ("\n".join(parts).strip() + "\n"), total_kept, total_seen, per_channel_counts

def write_markdown(content: str, out_path: str | None = None) -> str:
    """Écrit le contenu dans exports/YYYY-MM-DD_raw.md par défaut, retourne le chemin écrit."""
    os.makedirs("exports", exist_ok=True)
    if not out_path:
        today = datetime.now(timezone.utc).date().isoformat()
        out_path = os.path.join("exports", f"{today}_raw.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    return out_path
