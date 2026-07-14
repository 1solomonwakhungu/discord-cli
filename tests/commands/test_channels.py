"""Integration tests for channel commands using the conftest.py fake client framework."""

from __future__ import annotations

import json

import pytest

from tests.conftest import (
    make_category,
    make_client,
    make_guild,
    make_text_channel,
    make_voice_channel,
)


@pytest.fixture
def guild_with_channels():
    cat = make_category(id=400, name="General")
    ch1 = make_text_channel(id=300, name="general", category=cat, topic="General chat")
    ch2 = make_text_channel(id=301, name="random", category=cat)
    vc = make_voice_channel(id=310, name="Voice")
    return make_guild(id=1, name="TestGuild", channels=[ch1, ch2, vc], categories=[cat])


class TestChannelList:
    def test_lists_all_channels(self, cli_runner, use_client, guild_with_channels):
        client = make_client(guild_with_channels)
        use_client(client)
        result = cli_runner.invoke(main, ["channel", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert len(data["data"]) >= 2


class TestChannelInfo:
    def test_returns_channel_details(self, cli_runner, use_client, guild_with_channels):
        client = make_client(guild_with_channels)
        use_client(client)
        result = cli_runner.invoke(main, ["channel", "info", "300"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["name"] == "general"

    def test_info_nonexistent_channel(self, cli_runner, use_client, guild_with_channels):
        client = make_client(guild_with_channels)
        use_client(client)
        result = cli_runner.invoke(main, ["channel", "info", "999999"])
        assert result.exit_code == 1


class TestChannelDelete:
    def test_deletes_channel(self, cli_runner, use_client, guild_with_channels):
        client = make_client(guild_with_channels)
        use_client(client)
        result = cli_runner.invoke(main, ["channel", "delete", "300"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestChannelMove:
    def test_moves_channel_to_category(self, cli_runner, use_client, guild_with_channels):
        client = make_client(guild_with_channels)
        use_client(client)
        result = cli_runner.invoke(main, ["channel", "move", "301", "--category", "400"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestChannelEdit:
    def test_edits_channel_name(self, cli_runner, use_client, guild_with_channels):
        client = make_client(guild_with_channels)
        use_client(client)
        result = cli_runner.invoke(main, ["channel", "edit", "300", "--name", "renamed"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


# Import here to avoid circular import issues
from discord_cli.cli import main  # noqa: E402
