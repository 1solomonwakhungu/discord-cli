"""Integration tests for webhook commands."""

from __future__ import annotations

import json

import pytest

from tests.conftest import make_client, make_guild, make_text_channel, make_webhook


@pytest.fixture
def guild_with_webhooks():
    ch = make_text_channel(id=300, name="general")
    wh = make_webhook(id=700, name="TestWebhook", channel_id=300)
    guild = make_guild(id=1, name="TestGuild", channels=[ch])
    guild.webhooks = AsyncMock(return_value=[wh])
    return guild


from unittest.mock import AsyncMock


class TestWebhookList:
    def test_lists_webhooks(self, cli_runner, use_client, guild_with_webhooks):
        client = make_client(guild_with_webhooks)
        use_client(client)
        result = cli_runner.invoke(main, ["webhook", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestWebhookCreate:
    def test_creates_webhook(self, cli_runner, use_client, guild_with_webhooks):
        client = make_client(guild_with_webhooks)
        use_client(client)
        result = cli_runner.invoke(main, ["webhook", "create", "--channel", "300", "--name", "NewHook"])
        assert result.exit_code == 0


class TestWebhookInfo:
    def test_returns_webhook_details(self, cli_runner, use_client, guild_with_webhooks):
        client = make_client(guild_with_webhooks)
        use_client(client)
        result = cli_runner.invoke(main, ["webhook", "info", "700"])
        assert result.exit_code == 0


class TestWebhookDelete:
    def test_deletes_webhook(self, cli_runner, use_client, guild_with_webhooks):
        client = make_client(guild_with_webhooks)
        use_client(client)
        result = cli_runner.invoke(main, ["webhook", "delete", "700"])
        assert result.exit_code == 0


from discord_cli.cli import main  # noqa: E402
