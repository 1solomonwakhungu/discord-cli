"""Integration tests for role commands using the conftest.py fake client framework."""

from __future__ import annotations

import json

import pytest

from tests.conftest import make_client, make_guild, make_role


@pytest.fixture
def guild_with_roles():
    r1 = make_role(id=1, name="@everyone")
    r2 = make_role(id=2, name="Admins")
    r3 = make_role(id=3, name="Moderators")
    return make_guild(id=1, name="TestGuild", roles=[r1, r2, r3])


class TestRoleList:
    def test_lists_all_roles(self, cli_runner, use_client, guild_with_roles):
        client = make_client(guild_with_roles)
        use_client(client)
        result = cli_runner.invoke(main, ["role", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert len(data["data"]) >= 2

    def test_empty_guild_returns_empty_roles(self, cli_runner, use_client):
        guild = make_guild(id=1, name="Empty")
        client = make_client(guild)
        use_client(client)
        result = cli_runner.invoke(main, ["role", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestRoleInfo:
    def test_returns_role_details(self, cli_runner, use_client, guild_with_roles):
        client = make_client(guild_with_roles)
        use_client(client)
        result = cli_runner.invoke(main, ["role", "info", "2"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["name"] == "Admins"


class TestRoleDelete:
    def test_deletes_role(self, cli_runner, use_client, guild_with_roles):
        client = make_client(guild_with_roles)
        use_client(client)
        result = cli_runner.invoke(main, ["role", "delete", "3"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestRoleCreate:
    def test_creates_role(self, cli_runner, use_client, guild_with_roles):
        client = make_client(guild_with_roles)
        use_client(client)
        result = cli_runner.invoke(main, ["role", "create", "NewRole"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestRoleAssign:
    def test_assigns_role_to_member(self, cli_runner, use_client, guild_with_roles):
        from tests.conftest import make_member
        m = make_member(id=200, name="TestUser", roles=[])
        guild = make_guild(id=1, name="TestGuild", roles=guild_with_roles.roles, members=[m])
        client = make_client(guild)
        use_client(client)
        result = cli_runner.invoke(main, ["role", "assign", "2", "200"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


from discord_cli.cli import main  # noqa: E402
