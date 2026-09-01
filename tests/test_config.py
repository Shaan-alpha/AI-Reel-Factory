"""Tests for src.config — the one functional module so far.

Demonstrates the test pattern (rule 7: each module tested in isolation; rule 8: verify).
Run: `pytest` from the repo root.
"""
import os

import pytest

from src import config


def test_require_returns_value(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "abc123")
    assert config.require("GEMINI_API_KEY") == "abc123"


def test_require_raises_when_missing(monkeypatch):
    monkeypatch.delenv("DEFINITELY_MISSING_KEY", raising=False)
    with pytest.raises(config.ConfigError):
        config.require("DEFINITELY_MISSING_KEY")


def test_get_falls_back_to_default():
    # CHANNEL_NAME has a built-in default even if the env var is unset.
    assert config.get("CHANNEL_NAME") == os.environ.get("CHANNEL_NAME", "But It Matters")


def test_validate_reports_all_missing(monkeypatch):
    for key in config.REQUIRED:
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(config.ConfigError) as exc:
        config.validate()
    # Every missing key should be named in the error (fail loud, rule 14).
    for key in config.REQUIRED:
        assert key in str(exc.value)


def test_get_treats_a_present_but_empty_env_var_as_absent(monkeypatch):
    """`FOO: ${{ vars.FOO }}` with no repo variable exports FOO="" — an empty value must NOT
    shadow the code default.

    This is the 2026-09-01 root cause: os.environ.get(key, default) only falls back when the
    KEY IS ABSENT, so GitHub Actions handed the pipeline SFX_DIR="", VOICE_STYLE_PROMPT="" and
    IMAGE_STYLE="", silently disabling SFX, the narrator's delivery direction and the Flux
    style block — none of which reproduce locally, where the vars are simply unset.
    """
    monkeypatch.setenv("SFX_DIR", "")
    assert config.get("SFX_DIR", "assets/sfx") == "assets/sfx"


def test_get_treats_a_whitespace_only_env_var_as_absent(monkeypatch):
    monkeypatch.setenv("IMAGE_STYLE", "   ")
    assert config.get("IMAGE_STYLE", "cinematic") == "cinematic"


def test_get_prefers_DEFAULTS_over_the_caller_default_for_an_empty_env_var(monkeypatch):
    monkeypatch.setenv("CHANNEL_NAME", "")
    assert config.get("CHANNEL_NAME", "caller-default") == "But It Matters"


def test_get_still_returns_a_real_value(monkeypatch):
    monkeypatch.setenv("SFX_DIR", "/custom/sfx")
    assert config.get("SFX_DIR", "assets/sfx") == "/custom/sfx"
