"""Config loader. Reads env vars, fails LOUDLY if a required one is missing (rule 14).

Contract:
    what it does : centralizes all secrets/settings; validates required keys up front.
    how to use   : `from src.config import settings; settings.GEMINI_API_KEY`
                   or `from src.config import require; key = require("GEMINI_API_KEY")`.
    depends on   : os.environ; optionally a local .env (python-dotenv) for dev.

In production the values come from GitHub Actions secrets (already in os.environ).
Locally they come from a .env file (gitignored). Never commit real values (rule 5).
"""
from __future__ import annotations

import os

try:  # dev convenience only; absence is fine in CI where env is already populated
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


class ConfigError(RuntimeError):
    """Raised when a required setting is missing — hard stop (rule 14)."""


# Keys the Python pipeline needs. CLAUDE_CODE_OAUTH_TOKEN is intentionally NOT here:
# Claude ideation runs only in the Routine, never in this code (rule 4 / ToS).
REQUIRED = (
    "GEMINI_API_KEY",
    "GROQ_API_KEY",
    "SUPABASE_URL",
    "SUPABASE_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "PEXELS_API_KEY",
    "YOUTUBE_CLIENT_ID",
    "YOUTUBE_CLIENT_SECRET",
    "YOUTUBE_REFRESH_TOKEN",
)

# Settings with sensible defaults (see .env.example for meaning).
# Only keys something actually READS belong here. CHANNEL_NAME, CONTENT_STYLE and
# DIGEST_HOUR_UTC were carried for months after their last reader was removed — a default that
# nothing consults is a setting an operator can tune with no effect, which is worse than absent.
DEFAULTS = {
    "NICHE": "impact-news",
    # NICHE_LEAN ("soft-positive") removed 2026-07-27: it was read by nothing, and the operator's
    # policy is now truth-first rather than tone-first. What replaces it is a real gate —
    # factcheck.verify() re-checks every finished script (rule 6).
    "ENABLE_FALLBACK_IDEATION": "true",
    "AI_DISCLOSURE": "true",
    "MIN_SOURCES": "2",
    "PIXABAY_API_KEY": "",  # optional backup
}


def require(key: str) -> str:
    """Return a required env var or raise ConfigError. Use at the point of need."""
    val = os.environ.get(key)
    if not val:
        raise ConfigError(
            f"Missing required setting: {key}. "
            f"Set it in .env (local) or GitHub Actions secrets. See docs/03-setup-guide.md."
        )
    return val


def get(key: str, default: str | None = None) -> str | None:
    """Return an optional setting, falling back to DEFAULTS then `default`.

    An env var that is present but EMPTY counts as absent. This is not pedantry: GitHub Actions
    renders `FOO: ${{ vars.FOO }}` as `FOO=` when no repo variable exists, so a plain
    `os.environ.get(key, default)` hands the pipeline "" and the code default never applies.
    Locally the same var is simply unset, so the default DOES apply — which is how a green test
    suite coexisted with three broken subsystems in production (STATUS 2026-09-01): SFX_DIR=""
    crashed the SFX mixer, VOICE_STYLE_PROMPT="" stripped the narrator's delivery direction, and
    IMAGE_STYLE="" stripped "no text, no watermark" from every Flux prompt.

    `require` and `get_bool` already rejected empty values; only this accessor did not.
    """
    val = os.environ.get(key)
    if val is None or not val.strip():
        return DEFAULTS.get(key, default)
    return val


def get_bool(key: str, default: bool = True) -> bool:
    """Parse a boolean setting robustly (true/1/yes/on → True; false/0/no/off → False)."""
    val = os.environ.get(key, DEFAULTS.get(key))
    if val is None or str(val).strip() == "":
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "on", "y")


def validate(required: tuple[str, ...] = REQUIRED) -> None:
    """Validate all required settings at once. Call at pipeline start to fail loudly."""
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise ConfigError(
            "Missing required settings: "
            + ", ".join(missing)
            + ". See docs/03-setup-guide.md."
        )


if __name__ == "__main__":
    # Quick self-check: `python -m src.config`
    try:
        validate()
        print("config: all required settings present.")
    except ConfigError as e:
        print(f"config: {e}")
        raise
