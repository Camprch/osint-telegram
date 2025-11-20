# src/translator.py
"""
Traduction FR via OpenAI, asynchrone et robuste.
- Async with AsyncOpenAI (SDK >=1.0)
- Concurrency contrôlée (Semaphore)
- Retry exponentiel (429/5xx)
- Timeout par requête
- Troncature naïve par caractères (evite prompts trop longs)
"""

from __future__ import annotations
import asyncio
import math
import random
from dataclasses import dataclass
from typing import Iterable, List, Tuple, Optional

from src.config import get_settings

SYSTEM_PROMPT = (
    "Tu es un traducteur FR pour des contenus OSINT.\n"
    "- Traduire fidèlement en français, sans inventer d'informations.\n"
    "- Conserver entre guillemets « \"...\" » les mentions sensibles (noms propres, slogans, hashtags, sigles) si la traduction serait ambiguë.\n"
    "- Laisser les URLs et handles Telegram intacts.\n"
    "- Ne pas ajouter de commentaires, ni d'emojis.\n"
    "- Sortie = texte seulement (une ou plusieurs phrases)."
)

@dataclass
class TranslateParams:
    concurrency: int = 3
    timeout_s: int = 30
    max_chars: int = 4000  # troncature simple si besoin
    max_retries: int = 4   # 0, 1, 2, 3 (backoff)


def _truncate(text: str, max_chars: int) -> str:
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    # coupe proprement sur une limite de mot si possible
    cut = t[:max_chars]
    last_space = cut.rfind(" ")
    if last_space > max_chars * 0.6:
        cut = cut[:last_space]
    return cut + " …"


async def _translate_one_async(client, model: str, text: str, params: TranslateParams) -> str:
    """
    Envoie une requête chat.completions avec timeout + retry exponentiel.
    """
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Texte source :\n{text}\n\nRéponse :"},
        ],
        "temperature": 0,
    }

    # retry avec backoff
    for attempt in range(params.max_retries + 1):
        try:
            # timeout par requête
            resp = await asyncio.wait_for(
                client.chat.completions.create(**payload),
                timeout=params.timeout_s,
            )
            return (resp.choices[0].message.content or "").strip()
        except asyncio.TimeoutError:
            if attempt >= params.max_retries:
                raise RuntimeError("Timeout OpenAI")
        except Exception as e:
            # erreurs transitoires : 429 / 5xx → retry, sinon raise
            msg = str(e).lower()
            transient = any(code in msg for code in ["429", "rate", "temporarily", "timeout", "5", "service unavailable"])
            if not transient or attempt >= params.max_retries:
                raise
        # backoff exponentiel avec jitter
        sleep_s = (2 ** attempt) + random.uniform(0, 0.5)
        await asyncio.sleep(sleep_s)
    # théoriquement jamais atteint
    raise RuntimeError("Échecs répétés OpenAI")


async def translate_batch_async(texts: List[str], params: TranslateParams) -> List[Optional[str]]:
    """
    Traduit une liste de textes. Retourne une liste de mêmes dimensions (chaînes ou None si échec).
    """
    cfg = get_settings()
    try:
        from openai import AsyncOpenAI  # SDK >=1.0
    except Exception as e:
        raise RuntimeError("Le SDK OpenAI doit être >= 1.0 pour la traduction async.") from e

    client = AsyncOpenAI(api_key=cfg.openai_api_key.get_secret_value())
    sem = asyncio.Semaphore(max(1, params.concurrency))

    async def worker(i: int, txt: str) -> Tuple[int, Optional[str]]:
        if not txt or not txt.strip():
            return i, ""
        t = _truncate(txt, params.max_chars)
        async with sem:
            try:
                fr = await _translate_one_async(client, cfg.openai_model, t, params)
                return i, fr
            except Exception as e:
                # on logge côté appelant; ici, on renvoie None
                return i, None

    tasks = [asyncio.create_task(worker(i, t)) for i, t in enumerate(texts)]
    results: List[Optional[str]] = [None] * len(texts)

    for fut in asyncio.as_completed(tasks):
        i, val = await fut
        results[i] = val
    await client.close()
    return results
