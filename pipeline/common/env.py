"""Environment and secrets.

- Loads `.env` from the repo root (never overrides variables already set in the shell).
- `require(name, why=...)` returns a key or raises `MissingKeyError` naming the stage that needs
  it and where to get it, so a stranger with no keys gets a useful message, not a stack trace.
- `redact(text)` removes any secret value from text before it is logged or printed.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]

# Canonical name -> accepted aliases (first match wins). The aliases exist because providers
# name their credentials differently over time (e.g. Cloudflare "API key" vs "API token").
ALIASES: dict[str, tuple[str, ...]] = {
    "GEMINI_API_KEY": ("GOOGLE_API_KEY",),
    "CLOUDFLARE_ACCOUNT_ID": (),
    "CLOUDFLARE_API_TOKEN": ("CLOUDFLARE_API_KEY",),
    "KAGGLE_API_TOKEN": (),
}

WHERE: dict[str, str] = {
    "GEMINI_API_KEY": "Google AI Studio -> Get API key (https://aistudio.google.com/apikey)",
    "CLOUDFLARE_ACCOUNT_ID": "Cloudflare dashboard -> Workers AI -> 'Use REST API' (the account id)",
    "CLOUDFLARE_API_TOKEN": (
        "Cloudflare dashboard -> Workers AI -> 'Use REST API' -> Create a Workers AI API token"
    ),
    "KAGGLE_API_TOKEN": "kaggle.com -> Settings -> API -> Generate New Token (needs phone verification for GPU)",
}

SECRET_NAMES = (
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "CLOUDFLARE_API_TOKEN",
    "CLOUDFLARE_API_KEY",
    "KAGGLE_API_TOKEN",
    "KAGGLE_KEY",
)

_loaded = False


class MissingKeyError(RuntimeError):
    """A credential needed by a stage is not configured."""


def load_env() -> None:
    global _loaded
    if not _loaded:
        load_dotenv(ROOT / ".env", override=False, encoding="utf-8")
        _loaded = True


def get(name: str) -> str | None:
    load_env()
    for candidate in (name, *ALIASES.get(name, ())):
        value = os.environ.get(candidate, "").strip()
        if value:
            return value
    return None


def require(name: str, *, why: str) -> str:
    value = get(name)
    if value:
        return value
    where = WHERE.get(name, "see .env.example")
    raise MissingKeyError(
        f"{name} is not set, and the {why} needs it.\n"
        f"  Get it from: {where}\n"
        f"  Then add it to .env (see .env.example)."
    )


def kaggle_auth_available() -> bool:
    """True if the Kaggle CLI can authenticate (env token, legacy key pair or a token file)."""
    load_env()
    home = Path.home() / ".kaggle"
    return bool(
        get("KAGGLE_API_TOKEN")
        or (os.environ.get("KAGGLE_USERNAME") and os.environ.get("KAGGLE_KEY"))
        or (home / "kaggle.json").exists()
        or (home / "access_token").exists()
    )


def redact(text: str) -> str:
    """Replace any configured secret value in `text` with ***."""
    load_env()
    if not text:
        return text
    for name in SECRET_NAMES:
        value = os.environ.get(name, "").strip()
        if len(value) >= 8:
            text = text.replace(value, "***")
    return text
