# src/main.py
"""
Point d'entrée applicatif pour osint-telegram.

Commandes disponibles :
- --check-config
- --whoami
- --fetch-recent [--hours N --per-channel N]
- --translate    [--limit N --concurrency C --timeout S --max-chars K]
- --list-latest
- --export-md    [--hours N --out PATH]
- --embed        [--limit N]
- --cluster      [--min-sim FLOAT]
- --summarize    [--min-sim FLOAT --max-groups N --max-per-group N --out PATH]
- --publish      [--file PATH --dry-run]
"""

from __future__ import annotations
import argparse
import json
from datetime import datetime, timezone

from src.config import get_settings
from src.telegram_client import whoami, run_async
from src.db import (
    ensure_db,
    upsert_messages,
    fetch_untranslated,
    update_translation,
)
from src.fetcher import fetch_recent, list_latest
from src.translator import translate_batch_async, TranslateParams
from src.markdown_exporter import build_markdown, write_markdown
from src.embeddings import compute_embeddings, cluster_embeddings
from src.summarizer import build_summary_markdown, write_summary_markdown
from src.publisher import publish


# -----------------------
# Actions / Sous-commandes
# -----------------------

def cmd_check_config() -> int:
    settings = get_settings()
    print("✅ Configuration chargée avec succès.\n")
    print("Résumé (secrets masqués) :")
    print(json.dumps(settings.sanitized_view(), indent=2, ensure_ascii=False))
    print(f"\nMode Telegram actif : {settings.telegram_mode}")
    return 0


def cmd_whoami() -> int:
    print("🔐 Test d'authentification Telegram...")
    result = run_async(whoami())
    if hasattr(result, "result"):
        result = result.result()
    print("👤 Connecté :")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_fetch_recent(hours: int | None, per_channel: int) -> int:
    print("🗄️  Initialisation de la base SQLite…")
    ensure_db()
    print(f"📥 Collecte des messages récents… (hours={hours if hours is not None else 'env'}, per_channel={per_channel})")
    rows = run_async(fetch_recent(hours=hours, per_channel=per_channel))
    if hasattr(rows, "result"):
        rows = rows.result()
    print(f"🔎 Messages à insérer : {len(rows)}")
    inserted, skipped = upsert_messages(rows)
    print(f"✅ Insertion terminée. Nouveaux: {inserted}, doublons ignorés: {skipped}")
    return 0


def cmd_translate(limit: int, concurrency: int, timeout_s: int, max_chars: int) -> int:
    print("🗄️  Vérification de la base SQLite…")
    ensure_db()
    print(f"📝 Sélection des messages non traduits (limite {limit})…")
    rows = fetch_untranslated(limit=limit)
    if not rows:
        print("ℹ️  Aucun message à traduire.")
        return 0

    texts = [(r["channel_id"], r["message_id"], (r["text"] or "").strip()) for r in rows]
    params = TranslateParams(concurrency=concurrency, timeout_s=timeout_s, max_chars=max_chars)

    print(f"🧠 Traduction via OpenAI… ({len(texts)} messages, concurrency={concurrency}, timeout={timeout_s}s)")
    async def run():
        outputs = await translate_batch_async([t[2] for t in texts], params)
        done = 0
        for (chan_id, msg_id, _), fr in zip(texts, outputs):
            if fr is None:
                print(f"⚠️  Échec traduction msg {chan_id}/{msg_id}")
                continue
            try:
                update_translation(message_id=msg_id, channel_id=chan_id, text_fr=fr)
                done += 1
                if done % 5 == 0 or done == len(texts):
                    print(f"… progrès : {done}/{len(texts)}")
            except Exception as e:
                print(f"⚠️  Échec mise à jour DB pour {chan_id}/{msg_id} : {e}")
        return done

    done = run_async(run())
    if hasattr(done, "result"):
        done = done.result()

    print(f"✅ Traduction terminée. Messages mis à jour : {done}/{len(texts)}")
    return 0


def cmd_list_latest() -> int:
    print("🔎 Récupération des 3 derniers messages par canal…")
    preview = run_async(list_latest(per_channel=3))
    if hasattr(preview, "result"):
        preview = preview.result()
    for handle, items in preview:
        print(f"\n# {handle}")
        if not items:
            print("  (aucun résultat)")
            continue
        for msg_id, dt_iso, link in items:
            print(f"  - {dt_iso} – id={msg_id} – {link}")
    return 0


def cmd_export_md(hours: int | None, out_path: str | None) -> int:
    print("🧾 Génération du rapport Markdown dédupliqué…")
    h = hours if hours is not None else get_settings().fetch_window_hours
    content, kept, seen, per_channel = build_markdown(hours=h)
    path = write_markdown(content, out_path)
    print(f"✅ Export écrit : {path}")
    print(f"   Messages vus : {seen} | Après déduplication : {kept}")
    for ch, n in per_channel.items():
        print(f"   - {ch}: {n}")
    return 0


def cmd_embed(limit: int) -> int:
    done, total = compute_embeddings(limit)
    print(f"✅ Embeddings générés : {done}/{total}")
    return 0


def cmd_cluster(min_sim: float) -> int:
    clusters = cluster_embeddings(min_sim)
    print(f"🧩 {len(clusters)} groupes détectés (similarité ≥ {min_sim})\n")
    for idx, group in enumerate(clusters[:10], start=1):  # limite d'affichage
        print(f"### Groupe {idx} ({len(group)} messages)")
        for msg in group:
            ch = msg.get("channel") or "?"
            mid = msg.get("id")
            txt = (msg.get("text") or "")[:100].replace("\n", " ")
            print(f"- @{ch} #{mid} : {txt}…")
        print()
    return 0


def cmd_summarize(min_sim: float, max_groups: int, max_per_group: int, out_path: str | None) -> int:
    from src.summarizer import SummarizeParams
    params = SummarizeParams(
        min_sim=min_sim,
        max_groups=max_groups,
        max_per_group=max_per_group,
        temperature=0.2,
    )
    print(f"🧮 Construction de la synthèse (min_sim={min_sim}, groupes<= {max_groups}, msgs/groupe<= {max_per_group})…")
    md, stats = build_summary_markdown(params)
    path = write_summary_markdown(md, out_path)
    print(f"✅ Synthèse écrite : {path}")
    print(f"   Groupes : {stats['groups']} | Messages utilisés : {stats['msgs_used']}")
    return 0


def cmd_publish(file_path: str | None, dry_run: bool) -> int:
    if not file_path:
        today = datetime.now(timezone.utc).date().isoformat()
        file_path = f"exports/{today}_summary.md"
    print(f"📤 Publication du rapport : {file_path}")
    publish(file_path, dry_run=dry_run)
    return 0


# ---------------
# Entrée principale
# ---------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="osint-telegram")
    parser.add_argument("--check-config", action="store_true", help="Affiche la configuration (secrets masqués).")
    parser.add_argument("--whoami", action="store_true", help="Teste l'auth Telegram (bot/user).")
    parser.add_argument("--fetch-recent", action="store_true", help="Collecte les messages récents et les stocke en SQLite.")
    parser.add_argument("--translate", action="store_true", help="Traduit en français les messages non traduits.")
    parser.add_argument("--list-latest", action="store_true", help="Aperçu des derniers messages par canal (diagnostic).")
    parser.add_argument("--export-md", action="store_true", help="Exporte un Markdown dédupliqué des messages traduits.")
    parser.add_argument("--embed", action="store_true", help="Génère les embeddings OpenAI pour les messages traduits.")
    parser.add_argument("--cluster", action="store_true", help="Regroupe les messages similaires par embeddings.")
    parser.add_argument("--summarize", action="store_true", help="Produit une synthèse thématique Markdown à partir des clusters.")
    parser.add_argument("--publish", action="store_true", help="Publie un Markdown sur TELEGRAM_TARGET_CHANNEL (bot).")

    # Options partagées
    parser.add_argument("--limit", type=int, default=50, help="Limite pour --translate et --embed (par défaut 50).")
    parser.add_argument("--hours", type=int, default=None, help="Fenêtre (heures) pour --fetch-recent et --export-md.")
    parser.add_argument("--per-channel", type=int, default=200, help="Messages max par canal pour --fetch-recent.")
    parser.add_argument("--concurrency", type=int, default=3, help="Requêtes OpenAI en parallèle (translate).")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout par requête OpenAI (seconds) pour translate.")
    parser.add_argument("--max-chars", type=int, default=4000, help="Troncature naïve du texte source (translate).")
    parser.add_argument("--out", type=str, default=None, help="Chemin de sortie pour --export-md/--summarize (facultatif).")
    parser.add_argument("--min-sim", type=float, default=0.85, help="Seuil de similarité cosinus pour --cluster/--summarize.")
    parser.add_argument("--max-groups", type=int, default=6, help="Nombre max de groupes dans --summarize.")
    parser.add_argument("--max-per-group", type=int, default=8, help="Messages max par groupe dans --summarize.")
    parser.add_argument("--file", type=str, default=None, help="Chemin du fichier Markdown à publier (--publish).")
    parser.add_argument("--dry-run", action="store_true", help="Aperçu sans publication Telegram (--publish).")

    args = parser.parse_args(argv)

    if args.check_config:
        return cmd_check_config()
    if args.whoami:
        return cmd_whoami()
    if args.fetch_recent:
        return cmd_fetch_recent(hours=args.hours, per_channel=args.per_channel)
    if args.translate:
        return cmd_translate(limit=args.limit, concurrency=args.concurrency, timeout_s=args.timeout, max_chars=args.max_chars)
    if args.list_latest:
        return cmd_list_latest()
    if args.export_md:
        return cmd_export_md(hours=args.hours, out_path=args.out)
    if args.embed:
        return cmd_embed(limit=args.limit)
    if args.cluster:
        return cmd_cluster(min_sim=args.min_sim)
    if args.summarize:
        return cmd_summarize(min_sim=args.min_sim, max_groups=args.max_groups, max_per_group=args.max_per_group, out_path=args.out)
    if args.publish:
        return cmd_publish(file_path=args.file, dry_run=args.dry_run)

    print("osint-telegram : flags → "
          "--check-config, --whoami, "
          "--fetch-recent [--hours N --per-channel N], "
          "--translate [--limit N --concurrency C --timeout S --max-chars K], "
          "--list-latest, "
          "--export-md [--hours N --out PATH], "
          "--embed [--limit N], "
          "--cluster [--min-sim FLOAT], "
          "--summarize [--min-sim FLOAT --max-groups N --max-per-group N --out PATH], "
          "--publish [--file PATH --dry-run]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
