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
    assert config.get("CHANNEL_NAME") == os.environ.get("CHANNEL_NAME", "Newsence")


def test_validate_reports_all_missing(monkeypatch):
    for key in config.REQUIRED:
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(config.ConfigError) as exc:
        config.validate()
    # Every missing key should be named in the error (fail loud, rule 14).
    for key in config.REQUIRED:
        assert key in str(exc.value)
