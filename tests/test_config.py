"""Tests for discord_cli.config: token precedence and missing-token errors."""

from __future__ import annotations

import pytest

from discord_cli.config import Config, load_config
from discord_cli.errors import ConfigError


@pytest.fixture(autouse=True)
def isolated_cwd(tmp_path, monkeypatch):
    """Run every test from an empty directory with no DISCORD_BOT_TOKEN set.

    Prevents the developer's real environment or a real .env file from
    leaking into these tests via python-dotenv's upward directory search.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    return tmp_path


class TestTokenPrecedence:
    def test_flag_takes_precedence_over_everything(self, isolated_cwd, monkeypatch):
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "env-token")
        (isolated_cwd / ".env").write_text("DISCORD_BOT_TOKEN=dotenv-token\n")

        config = load_config(token_override="flag-token")

        assert config == Config(bot_token="flag-token")

    def test_flag_is_stripped(self):
        config = load_config(token_override="  flag-token  ")
        assert config.bot_token == "flag-token"

    def test_env_used_when_no_flag(self, monkeypatch):
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "env-token")

        config = load_config()

        assert config.bot_token == "env-token"

    def test_env_takes_precedence_over_dotenv(self, isolated_cwd, monkeypatch):
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "env-token")
        (isolated_cwd / ".env").write_text("DISCORD_BOT_TOKEN=dotenv-token\n")

        config = load_config()

        assert config.bot_token == "env-token"

    def test_dotenv_used_when_no_flag_or_env(self, isolated_cwd, monkeypatch):
        (isolated_cwd / ".env").write_text("DISCORD_BOT_TOKEN=dotenv-token\n")

        from dotenv import load_dotenv
        load_dotenv(str(isolated_cwd / ".env"), override=True)

        config = load_config()

        assert config.bot_token == "dotenv-token"


class TestMissingToken:
    def test_raises_config_error_when_nothing_is_set(self, isolated_cwd):
        with pytest.raises(ConfigError, match="DISCORD_BOT_TOKEN"):
            load_config()

    def test_empty_flag_falls_through_to_env_lookup(self, isolated_cwd):
        with pytest.raises(ConfigError):
            load_config(token_override="")
