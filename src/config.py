# src/config.py
"""
Charge et valide la configuration de l'application.
Double mode Telegram :
- bot : via TELEGRAM_BOT_TOKEN (limité pour lire des canaux publics)
- user: via TELEGRAM_USER_SESSION (StringSession MTProto) pour lecture publique
"""

from __future__ import annotations
import os
import re
from functools import lru_cache
from typing import List, Optional, Dict, Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field, SecretStr, ValidationError, field_validator


def _split_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _mask(value: Optional[str], show: int = 4) -> str:
    if not value:
        return "∅"
    if len(value) <= show:
        return "•" * len(value)
    return "•" * (len(value) - show) + value[-show:]


class Settings(BaseModel):
    # --- Telegram ---
    telegram_api_id: int = Field(..., description="Telegram API ID (my.telegram.org)")
    telegram_api_hash: SecretStr = Field(..., description="Telegram API Hash (my.telegram.org)")
    telegram_mode: str = Field(default="bot", description="bot | user")
    telegram_bot_token: Optional[SecretStr] = Field(default=None, description="Token @BotFather (mode bot)")
    telegram_user_session: Optional[SecretStr] = Field(default=None, description="StringSession (mode user)")
    telegram_target_channel: str = Field(..., description="Handle ou ID du canal de sortie")
    telegram_source_channels: List[str] = Field(default_factory=list, description="Canaux publics sources")

    # --- OpenAI ---
    openai_api_key: SecretStr = Field(..., description="Clé API OpenAI")
    openai_model: str = Field(default="gpt-4o-mini", description="Modèle de génération/synthèse")
    openai_embeddings_model: str = Field(default="text-embedding-3-small", description="Modèle d'embeddings")

    # --- Exécution & stockage ---
    fetch_window_hours: int = Field(default=48, ge=1, le=168, description="Fenêtre de collecte (heures)")
    sqlite_db_path: str = Field(default="data/osint.sqlite3", description="Chemin du fichier SQLite")
    timezone: str = Field(default="Europe/Paris", description="Timezone applicative")
    log_level: str = Field(default="INFO", description="Niveau de log: DEBUG/INFO/WARNING/ERROR")

    # --- Validateurs ---
    @field_validator("telegram_api_id")
    @classmethod
    def _api_id_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("TELEGRAM_API_ID doit être un entier > 0 (depuis my.telegram.org/apps).")
        return v

    @field_validator("telegram_api_hash")
    @classmethod
    def _api_hash_format(cls, v: SecretStr) -> SecretStr:
        val = v.get_secret_value()
        if not re.fullmatch(r"[0-9a-fA-F]{32}", val or ""):
            raise ValueError("TELEGRAM_API_HASH doit être une chaîne hexadécimale de 32 caractères.")
        return v

    @field_validator("telegram_mode")
    @classmethod
    def _mode_valid(cls, v: str) -> str:
        v2 = v.strip().lower()
        if v2 not in {"bot", "user"}:
            raise ValueError("TELEGRAM_MODE doit être 'bot' ou 'user'.")
        return v2

    def sanitized_view(self) -> Dict[str, Any]:
        return {
            "telegram_api_id": self.telegram_api_id,
            "telegram_api_hash": _mask(self.telegram_api_hash.get_secret_value() if self.telegram_api_hash else None),
            "telegram_mode": self.telegram_mode,
            "telegram_bot_token": _mask(self.telegram_bot_token.get_secret_value() if self.telegram_bot_token else None),
            "telegram_user_session": _mask(self.telegram_user_session.get_secret_value() if self.telegram_user_session else None),
            "telegram_target_channel": self.telegram_target_channel,
            "telegram_source_channels": self.telegram_source_channels,
            "openai_api_key": _mask(self.openai_api_key.get_secret_value() if self.openai_api_key else None),
            "openai_model": self.openai_model,
            "openai_embeddings_model": self.openai_embeddings_model,
            "fetch_window_hours": self.fetch_window_hours,
            "sqlite_db_path": self.sqlite_db_path,
            "timezone": self.timezone,
            "log_level": self.log_level,
        }


def _build_from_env() -> Settings:
    load_dotenv(override=False)

    env = os.environ
    missing = []

    def req(name: str) -> str:
        val = env.get(name)
        if not val:
            missing.append(name)
            return ""
        return val

    def opt(name: str, default: Optional[str] = None) -> str:
        return env.get(name, default) if env.get(name, default) is not None else ""

    data: Dict[str, Any] = {
        # Telegram
        "telegram_api_id": int(req("TELEGRAM_API_ID") or 0),
        "telegram_api_hash": SecretStr(req("TELEGRAM_API_HASH")),
        "telegram_mode": opt("TELEGRAM_MODE", "bot"),
        "telegram_bot_token": SecretStr(opt("TELEGRAM_BOT_TOKEN") or "") if opt("TELEGRAM_BOT_TOKEN") else None,
        "telegram_user_session": SecretStr(opt("TELEGRAM_USER_SESSION") or "") if opt("TELEGRAM_USER_SESSION") else None,
        "telegram_target_channel": req("TELEGRAM_TARGET_CHANNEL"),
        "telegram_source_channels": _split_csv(opt("TELEGRAM_SOURCE_CHANNELS", "")),

        # OpenAI
        "openai_api_key": SecretStr(req("OPENAI_API_KEY")),
        "openai_model": opt("OPENAI_MODEL", "gpt-4o-mini"),
        "openai_embeddings_model": opt("OPENAI_EMBEDDINGS_MODEL", "text-embedding-3-small"),

        # Exécution & stockage
        "fetch_window_hours": int(opt("FETCH_WINDOW_HOURS", "48")),
        "sqlite_db_path": opt("SQLITE_DB_PATH", "data/osint.sqlite3"),
        "timezone": opt("TIMEZONE", "Europe/Paris"),
        "log_level": opt("LOG_LEVEL", "INFO"),
    }

    try:
        settings = Settings(**data)
    except ValidationError as ve:
        raise RuntimeError(
            "Configuration incomplète ou invalide. Vérifie ton .env: "
            + ", ".join(missing) if missing else str(ve)
        ) from ve

    # Cohérence mode
    if settings.telegram_mode == "bot" and not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_MODE=bot mais TELEGRAM_BOT_TOKEN est absent.")
    if settings.telegram_mode == "user" and not settings.telegram_user_session:
        raise RuntimeError("TELEGRAM_MODE=user mais TELEGRAM_USER_SESSION est absent (StringSession requise).")

    return settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return _build_from_env()
