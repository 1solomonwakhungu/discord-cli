"""Integration tests for permission commands."""

from __future__ import annotations

import json

import pytest

from tests.conftest import make_client, make_guild, make_role, make_text_channel


@pytest.fixture
def guild_with_perms():
    r = make_role(id=2, name="Member")
    ch = make_text_channel(id=300, name="general")
    return make_guild(id=1, name="TestGuild", roles=[r], channels=[ch])


class TestPermissionsList:
    def test_lists_permissions(self, cli_runner, use_client, guild_with_perms):
        client = make_client(guild_with_perms)
        use_client(client)
        result = cli_runner.invoke(main, ["permissions", "list", "--channel", "300"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestPermissionsSet:
    def test_sets_role_permission(self, cli_runner, use_client, guild_with_perms):
        client = make_client(guild_with_perms)
        use_client(client)
        result = cli_runner.invoke(main, [
            "permissions", "set",
            "--channel", "300",
            "--role", "2",
            "--allow", "send_messages",
        ])
        assert result.exit_code == 0


class TestPermissionsReset:
    def test_resets_role_permission(self, cli_runner, use_client, guild_with_perms):
        client = make_client(guild_with_perms)
        use_client(client)
        result = cli_runner.invoke(main, [
            "permissions", "reset",
            "--channel", "300",
            "--role", "2",
        ])
        assert result.exit_code == 0


from discord_cli.cli import main  # noqa: E402
