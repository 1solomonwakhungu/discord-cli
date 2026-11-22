"""Integration tests for message commands using the conftest.py fake client framework."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from discord_cli.cli import main
from discord_cli.models import message_to_dict
from tests.conftest import async_iter, make_client, make_guild, make_message, make_text_channel


@pytest.fixture
def guild_with_messages():
    ch = make_text_channel(id=300, name="general")
    msg = make_message(id=600, channel=ch, content="Hello world")
    ch.history = MagicMock(return_value=async_iter([msg]))
    ch.fetch_message = AsyncMock(return_value=msg)
    return make_guild(id=1, name="TestGuild", channels=[ch])


class TestMessageList:
    def test_lists_messages_with_default_limit(self, cli_runner, use_client):
        ch = make_text_channel(id=300, name="general")
        msg1 = make_message(id=601, channel=ch, content="Latest message")
        msg2 = make_message(id=600, channel=ch, content="Older message")
        ch.history = MagicMock(return_value=async_iter([msg1, msg2]))
        guild = make_guild(id=1, name="TestGuild", channels=[ch])
        use_client(make_client(guild))

        result = cli_runner.invoke(main, ["message", "list", "300"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["ok"] is True
        assert payload["data"]["channel_id"] == 300
        assert payload["data"]["count"] == 2
        assert payload["data"]["messages"] == [message_to_dict(msg1), message_to_dict(msg2)]
        ch.history.assert_called_once_with(limit=20)

    def test_forwards_limit_before_and_after_options(self, cli_runner, use_client):
        ch = make_text_channel(id=300, name="general")
        msg = make_message(id=600, channel=ch, content="Between cursors")
        ch.history = MagicMock(return_value=async_iter([msg]))
        guild = make_guild(id=1, name="TestGuild", channels=[ch])
        use_client(make_client(guild))

        result = cli_runner.invoke(
            main,
            ["message", "list", "300", "--limit", "5", "--before", "700", "--after", "500"],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["ok"] is True
        assert payload["data"]["count"] == 1
        ch.history.assert_called_once()
        _, kwargs = ch.history.call_args
        assert kwargs["limit"] == 5
        assert isinstance(kwargs["before"], discord.Object)
        assert kwargs["before"].id == 700
        assert isinstance(kwargs["after"], discord.Object)
        assert kwargs["after"].id == 500

    def test_forwards_only_provided_cursor(self, cli_runner, use_client):
        ch = make_text_channel(id=300, name="general")
        ch.history = MagicMock(return_value=async_iter([]))
        guild = make_guild(id=1, name="TestGuild", channels=[ch])
        use_client(make_client(guild))

        result = cli_runner.invoke(main, ["message", "list", "300", "--before", "700"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["ok"] is True
        assert payload["data"] == {"channel_id": 300, "count": 0, "messages": []}
        _, kwargs = ch.history.call_args
        assert kwargs["limit"] == 20
        assert isinstance(kwargs["before"], discord.Object)
        assert kwargs["before"].id == 700
        assert "after" not in kwargs

    @pytest.mark.parametrize("bad_limit", ["0", "-1", "-20"])
    def test_rejects_non_positive_limit(self, cli_runner, use_client, bad_limit):
        ch = make_text_channel(id=300, name="general")
        ch.history = MagicMock(return_value=async_iter([]))
        guild = make_guild(id=1, name="TestGuild", channels=[ch])
        use_client(make_client(guild))

        result = cli_runner.invoke(main, ["message", "list", "300", "--limit", bad_limit])

        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["ok"] is False
        assert payload["error"]["type"] == "CliError"
        assert "positive integer" in payload["error"]["message"]
        ch.history.assert_not_called()

    def test_rejects_channel_without_history(self, cli_runner, use_client, category_factory):
        category = category_factory(id=400, name="General")
        guild = make_guild(id=1, name="TestGuild", categories=[category])
        use_client(make_client(guild))

        result = cli_runner.invoke(main, ["message", "list", "400"])

        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["ok"] is False
        assert payload["error"]["type"] == "CliError"
        assert "does not support reading messages" in payload["error"]["message"]

    def test_human_output_renders_table(self, cli_runner, use_client, guild_with_messages):
        use_client(make_client(guild_with_messages))

        result = cli_runner.invoke(main, ["--human", "message", "list", "300"])

        assert result.exit_code == 0
        assert "messages" in result.output
        assert "600" in result.output
        assert "Hello" in result.output


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
        result = cli_runner.invoke(
            main, ["message", "react", "600", "--channel", "300", "--emoji", "👍"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
