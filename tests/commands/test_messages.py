"""Integration tests for message commands using the conftest.py fake client framework."""

from __future__ import annotations

import json

import pytest

from tests.conftest import make_client, make_guild, make_message, make_text_channel


@pytest.fixture
def guild_with_messages():
    ch = make_text_channel(id=300, name="general")
    msg = make_message(id=600, channel=ch, content="Hello world")
    ch.history = MagicMock(return_value=async_iter([msg]))
    ch.fetch_message = AsyncMock(return_value=msg)
    return make_guild(id=1, name="TestGuild", channels=[ch])


from unittest.mock import AsyncMock, MagicMock
from tests.conftest import async_iter


class TestMessageSend:
    def test_sends_message(self, cli_runner, use_client, guild_with_messages):
        client = make_client(guild_with_messages)
        use_client(client)
        result = cli_runner.invoke(main, ["message", "send", "300", "--content", "Test message"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestMessageFetch:
    def test_fetches_message(self, cli_runner, use_client, guild_with_messages):
        client = make_client(guild_with_messages)
        use_client(client)
        result = cli_runner.invoke(main, ["message", "fetch", "600", "--channel", "300"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestMessageDelete:
    def test_deletes_message(self, cli_runner, use_client, guild_with_messages):
        client = make_client(guild_with_messages)
        use_client(client)
        result = cli_runner.invoke(main, ["message", "delete", "600", "--channel", "300"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestMessagePin:
    def test_pins_message(self, cli_runner, use_client, guild_with_messages):
        client = make_client(guild_with_messages)
        use_client(client)
        result = cli_runner.invoke(main, ["message", "pin", "600", "--channel", "300"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestMessageUnpin:
    def test_unpins_message(self, cli_runner, use_client, guild_with_messages):
        client = make_client(guild_with_messages)
        use_client(client)
        result = cli_runner.invoke(main, ["message", "unpin", "600", "--channel", "300"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestMessageReact:
    def test_reacts_to_message(self, cli_runner, use_client, guild_with_messages):
        client = make_client(guild_with_messages)
        use_client(client)
        result = cli_runner.invoke(main, ["message", "react", "600", "--channel", "300", "--emoji", "👍"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


from discord_cli.cli import main  # noqa: E402
