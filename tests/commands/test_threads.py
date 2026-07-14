"""Integration tests for thread commands."""

from __future__ import annotations

import json

import pytest

from tests.conftest import make_client, make_guild, make_text_channel, make_thread


@pytest.fixture
def guild_with_threads():
    ch = make_text_channel(id=300, name="general")
    t1 = make_thread(id=500, name="Thread1", parent_id=300)
    t2 = make_thread(id=501, name="Thread2", parent_id=300)
    guild = make_guild(id=1, name="TestGuild", channels=[ch], threads=[t1, t2])
    return guild


class TestThreadList:
    def test_lists_threads(self, cli_runner, use_client, guild_with_threads):
        client = make_client(guild_with_threads)
        use_client(client)
        result = cli_runner.invoke(main, ["threads", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestThreadCreate:
    def test_creates_thread(self, cli_runner, use_client, guild_with_threads):
        client = make_client(guild_with_threads)
        use_client(client)
        result = cli_runner.invoke(main, ["threads", "create", "NewThread", "--channel-id", "300"])
        assert result.exit_code == 0


class TestThreadDelete:
    def test_deletes_thread(self, cli_runner, use_client, guild_with_threads):
        client = make_client(guild_with_threads)
        use_client(client)
        result = cli_runner.invoke(main, ["threads", "delete", "500"])
        assert result.exit_code == 0


class TestThreadArchive:
    def test_archives_thread(self, cli_runner, use_client, guild_with_threads):
        client = make_client(guild_with_threads)
        use_client(client)
        result = cli_runner.invoke(main, ["threads", "archive", "500"])
        assert result.exit_code == 0


class TestThreadUnarchive:
    def test_unarchives_thread(self, cli_runner, use_client, guild_with_threads):
        client = make_client(guild_with_threads)
        use_client(client)
        result = cli_runner.invoke(main, ["threads", "unarchive", "500"])
        assert result.exit_code == 0


from discord_cli.cli import main  # noqa: E402
