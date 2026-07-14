"""Integration tests for guild commands using the conftest.py fake client framework."""

from __future__ import annotations

import json

import pytest

from tests.conftest import make_client, make_guild


@pytest.fixture
def guild():
    return make_guild(id=1, name="TestGuild", member_count=100)


class TestGuildInfo:
    def test_returns_guild_details(self, cli_runner, use_client, guild):
        client = make_client(guild)
        use_client(client)
        result = cli_runner.invoke(main, ["guild", "info"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["name"] == "TestGuild"


class TestGuildBansList:
    def test_lists_bans(self, cli_runner, use_client, guild):
        client = make_client(guild)
        use_client(client)
        result = cli_runner.invoke(main, ["guild", "bans", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestGuildEmojisList:
    def test_lists_emojis(self, cli_runner, use_client, guild):
        client = make_client(guild)
        use_client(client)
        result = cli_runner.invoke(main, ["guild", "emojis", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestGuildPrune:
    def test_prune_dry_run(self, cli_runner, use_client, guild):
        client = make_client(guild)
        use_client(client)
        result = cli_runner.invoke(main, ["guild", "prune", "--days", "7"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


from discord_cli.cli import main  # noqa: E402
