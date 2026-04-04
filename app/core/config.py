from __future__ import annotations

import os
from dataclasses import dataclass

def _get_env(name: str, default: str | None = None) -> str:
    val = os.getenv(name, default)
    if val is None:
        raise RuntimeError(f"Missing required env var: {name}")
    return val

@dataclass(frozen=True)
class Settings:
    REDIS_URL: str = _get_env("REDIS_URL", "redis://localhost:6379/0")
    VERIFY_TOKEN: str = _get_env("VERIFY_TOKEN", "empressa_verify_2026")
    WHATSAPP_TOKEN: str = _get_env("WHATSAPP_TOKEN", "")
    PHONE_NUMBER_ID: str = _get_env("PHONE_NUMBER_ID", "")
    GRAPH_API_VERSION: str = _get_env("GRAPH_API_VERSION", "v19.0")

    PUBLIC_BASE_URL: str = _get_env("PUBLIC_BASE_URL", "http://localhost:8000")

    # session controls
    SESSION_TIMEOUT_SECONDS: int = int(_get_env("SESSION_TIMEOUT_SECONDS", "1800"))
    CHECKER_INTERVAL_SECONDS: int = int(_get_env("CHECKER_INTERVAL_SECONDS", "5"))

    # gemini
    GEMINI_API_KEY: str = _get_env("GEMINI_API_KEY", "")
    GEMINI_API_KEYS: str = _get_env("GEMINI_API_KEYS", "")
    GEMINI_TEXT_MODEL: str = _get_env("GEMINI_TEXT_MODEL", "gemini-2.0-flash")
    GEMINI_IMAGE_MODEL: str = _get_env("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image-preview")

settings = Settings()
