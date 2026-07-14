"""Integration tests for member commands using the conftest.py fake client framework."""

from __future__ import annotations

import json

import pytest

from tests.conftest import make_client, make_guild, make_member, make_role


@pytest.fixture
def guild_with_members():
    r1 = make_role(id=1, name="@everyone")
    r2 = make_role(id=2, name="Member")
    m1 = make_member(id=200, name="alice", roles=[r1, r2])
    m2 = make_member(id=201, name="bob", roles=[r1])
    return make_guild(id=1, name="TestGuild", roles=[r1, r2], members=[m1, m2])


class TestMemberList:
    def test_lists_all_members(self, cli_runner, use_client, guild_with_members):
        client = make_client(guild_with_members)
        use_client(client)
        result = cli_runner.invoke(main, ["member", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert len(data["data"]) >= 2


class TestMemberInfo:
    def test_returns_member_details(self, cli_runner, use_client, guild_with_members):
        client = make_client(guild_with_members)
        use_client(client)
        result = cli_runner.invoke(main, ["member", "info", "200"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestMemberKick:
    def test_kicks_member(self, cli_runner, use_client, guild_with_members):
        client = make_client(guild_with_members)
        use_client(client)
        result = cli_runner.invoke(main, ["member", "kick", "200", "--reason", "Spam"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestMemberBan:
    def test_bans_member(self, cli_runner, use_client, guild_with_members):
        client = make_client(guild_with_members)
        use_client(client)
        result = cli_runner.invoke(main, ["member", "ban", "200", "--reason", "Violation"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestMemberUnban:
    def test_unbans_user(self, cli_runner, use_client, guild_with_members):
        client = make_client(guild_with_members)
        use_client(client)
        result = cli_runner.invoke(main, ["member", "unban", "200"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestMemberTimeout:
    def test_timeouts_member(self, cli_runner, use_client, guild_with_members):
        client = make_client(guild_with_members)
        use_client(client)
        result = cli_runner.invoke(main, ["member", "timeout", "200", "5m"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestMemberUntimeout:
    def test_untimeouts_member(self, cli_runner, use_client, guild_with_members):
        client = make_client(guild_with_members)
        use_client(client)
        result = cli_runner.invoke(main, ["member", "untimeout", "200"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestMemberNickname:
    def test_sets_nickname(self, cli_runner, use_client, guild_with_members):
        client = make_client(guild_with_members)
        use_client(client)
        result = cli_runner.invoke(main, ["member", "nickname", "200", "NewNick"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestMemberRoles:
    def test_lists_member_roles(self, cli_runner, use_client, guild_with_members):
        client = make_client(guild_with_members)
        use_client(client)
        result = cli_runner.invoke(main, ["member", "roles", "200"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


from discord_cli.cli import main  # noqa: E402
