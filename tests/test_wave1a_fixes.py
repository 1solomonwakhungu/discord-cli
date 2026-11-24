"""Tests for Wave 1a: bug fixes, REST-first behavior, SSRF/redaction security, and plugin isolation."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import click
import discord
import pytest

from discord_cli.cli import main
from discord_cli.errors import CliError
from discord_cli.models import (
    redact_webhook_url,
    validate_remote_url,
    webhook_to_dict,
)
from discord_cli.plugins import PluginError, load_plugins, plugin_errors
from discord_cli.registry import CommandRegistry
from tests.conftest import (
    async_iter,
    make_client,
    make_guild,
    make_message,
    make_role,
    make_text_channel,
    make_thread,
    make_webhook,
)


class TestMultiGuildFailClosed:
    def test_refuses_when_bot_in_multiple_cached_guilds_without_flag(self, cli_runner, use_client):
        g1 = make_guild(id=1, name="Prod")
        g2 = make_guild(id=2, name="Staging")
        client = make_client(g1)
        client.guilds = [g1, g2]
        use_client(client)

        result = cli_runner.invoke(main, ["guild", "info"])

        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["ok"] is False
        assert "multiple" in payload["error"]["message"].lower() or "2 guilds" in payload["error"]["message"]
        assert "--guild" in payload["error"]["message"]

    def test_refuses_when_rest_fetch_guilds_returns_multiple(self, cli_runner, use_client):
        g1 = make_guild(id=1, name="Prod")
        g2 = make_guild(id=2, name="Staging")
        client = make_client(g1)
        client.guilds = []
        client.fetch_guilds = MagicMock(return_value=async_iter([g1, g2]))
        use_client(client)

        result = cli_runner.invoke(main, ["channel", "list"])

        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["ok"] is False
        assert "--guild" in payload["error"]["message"]

    def test_rest_single_guild_discovery_succeeds(self, cli_runner, use_client):
        ch = make_text_channel(id=300, name="general")
        guild = make_guild(id=42, name="SoloGuild", channels=[])
        guild.fetch_channels = AsyncMock(return_value=[ch])
        client = make_client(guild)
        client._discord_cli_transport = "rest"
        client._discord_cli_cache = {}
        client.guilds = []
        client.get_guild = MagicMock(return_value=None)
        client.fetch_guilds = MagicMock(return_value=async_iter([guild]))
        client.fetch_guild = AsyncMock(return_value=guild)
        use_client(client)

        result = cli_runner.invoke(main, ["channel", "list"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["ok"] is True
        assert payload["data"]["guild_id"] == 42
        assert payload["data"]["channels"][0]["name"] == "general"


class TestForumCreateFix:
    def test_channel_create_forum_calls_create_forum(self, cli_runner, use_client):
        created_forum = MagicMock(spec=discord.ForumChannel)
        created_forum.id = 999
        created_forum.name = "help-forum"
        created_forum.type = discord.ChannelType.forum
        created_forum.position = 1
        created_forum.category = None
        created_forum.category_id = None
        created_forum.topic = "Ask here"
        created_forum.nsfw = False
        created_forum.slowmode_delay = 0
        created_forum.overwrites = {}

        guild = make_guild(id=1, name="TestGuild")
        guild.create_forum = AsyncMock(return_value=created_forum)
        use_client(make_client(guild))

        result = cli_runner.invoke(
            main, ["channel", "create", "help-forum", "--type", "forum", "--topic", "Ask here"]
        )

        assert result.exit_code == 0
        guild.create_forum.assert_awaited_once()
        payload = json.loads(result.output)
        assert payload["ok"] is True
        assert payload["data"]["created"]["id"] == 999


class TestSearchFixes:
    def test_search_messages_separates_scan_limit_from_result_limit(self, cli_runner, use_client):
        ch = make_text_channel(id=300, name="general")
        now = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
        msgs = [
            make_message(id=100 + i, channel=ch, content="noise", created_at=now) for i in range(30)
        ] + [make_message(id=200, channel=ch, content="needle match!", created_at=now)]
        ch.history = MagicMock(return_value=async_iter(msgs))
        guild = make_guild(id=1, name="TestGuild", channels=[ch])
        use_client(make_client(guild))

        result = cli_runner.invoke(
            main, ["search", "messages", "needle", "--limit", "5", "--scan-limit", "100"]
        )

        assert result.exit_code == 0
        ch.history.assert_called_once_with(limit=100)
        payload = json.loads(result.output)
        assert payload["ok"] is True
        assert len(payload["data"]) == 1
        assert payload["data"][0]["id"] == 200

    def test_search_messages_skips_forbidden_channels(self, cli_runner, use_client):
        now = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
        forbidden_ch = make_text_channel(id=301, name="staff-only")

        async def forbidden_iter():
            response = SimpleNamespace(status=403, reason="Forbidden")
            raise discord.Forbidden(response, {"code": 50001, "message": "Missing Access"})
            yield  # pragma: no cover

        forbidden_ch.history = MagicMock(return_value=forbidden_iter())
        open_ch = make_text_channel(id=302, name="public")
        open_ch.history = MagicMock(
            return_value=async_iter([make_message(id=777, channel=open_ch, content="deploy ok", created_at=now)])
        )
        guild = make_guild(id=1, name="TestGuild", channels=[forbidden_ch, open_ch])
        use_client(make_client(guild))

        result = cli_runner.invoke(main, ["search", "messages", "deploy"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["ok"] is True
        assert [m["id"] for m in payload["data"]] == [777]

    def test_search_members_uses_rest_endpoint_in_rest_mode(self, cli_runner, use_client):
        guild = make_guild(id=1, name="TestGuild", members=[])
        client = make_client(guild)
        client._discord_cli_transport = "rest"
        client.http.request = AsyncMock(
            return_value=[
                {
                    "user": {"id": "555", "username": "alice", "global_name": "Alice"},
                    "nick": "Ally",
                    "joined_at": "2026-01-01T00:00:00+00:00",
                }
            ]
        )
        use_client(client)

        result = cli_runner.invoke(main, ["search", "members", "ali"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["ok"] is True
        assert payload["data"][0]["id"] == 555
        assert payload["data"][0]["display_name"] == "Ally"


class TestThreadFixes:
    def test_unarchive_fetches_uncached_archived_thread(self, cli_runner, use_client):
        archived = make_thread(id=555, name="OldThread", archived=True)
        guild = make_guild(id=1, name="TestGuild", threads=[])
        guild.get_thread = MagicMock(return_value=None)
        guild.fetch_channel = AsyncMock(return_value=archived)
        use_client(make_client(guild))

        result = cli_runner.invoke(main, ["threads", "unarchive", "555"])

        assert result.exit_code == 0
        archived.edit.assert_awaited_once_with(archived=False)

    def test_thread_members_handles_threadmember_without_name(self, cli_runner, use_client):
        tm = SimpleNamespace(id=999, joined_at=dt.datetime(2026, 2, 1, tzinfo=dt.timezone.utc))
        thread = make_thread(id=500, name="Thread1")
        thread.fetch_members = AsyncMock(return_value=[tm])
        guild = make_guild(id=1, name="TestGuild", threads=[thread])
        use_client(make_client(guild))

        result = cli_runner.invoke(main, ["threads", "members", "500"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["ok"] is True
        assert payload["data"][0]["id"] == 999
        assert payload["data"][0]["name"] is None
        assert payload["data"][0]["joined_at"] is not None


class TestMemberFixes:
    def test_member_ban_hackbans_user_not_in_guild(self, cli_runner, use_client):
        guild = make_guild(id=1, name="TestGuild", members=[])
        guild.get_member = MagicMock(return_value=None)
        response = SimpleNamespace(status=404, reason="Not Found")
        guild.fetch_member = AsyncMock(
            side_effect=discord.NotFound(response, {"code": 10007, "message": "Unknown Member"})
        )
        use_client(make_client(guild))

        result = cli_runner.invoke(
            main, ["member", "ban", "888888", "--reason", "Raider left", "--delete-message-days", "1"]
        )

        assert result.exit_code == 0
        guild.ban.assert_awaited_once()
        payload = json.loads(result.output)
        assert payload["ok"] is True
        assert payload["data"]["banned"] == {"id": 888888, "hackban": True}

    def test_member_list_rest_mode_paginates_via_http(self, cli_runner, use_client):
        role = make_role(id=10, name="Ops", position=2)
        guild = make_guild(id=1, name="TestGuild", roles=[role])
        client = make_client(guild)
        client._discord_cli_transport = "rest"
        client.http.get_members = AsyncMock(
            return_value=[
                {
                    "user": {"id": "123456789012345678", "username": "bob", "bot": False},
                    "nick": None,
                    "roles": ["10"],
                    "joined_at": "2026-01-01T00:00:00+00:00",
                }
            ]
        )
        use_client(client)

        result = cli_runner.invoke(main, ["member", "list"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["ok"] is True
        assert payload["data"]["members"][0]["name"] == "bob"
        assert payload["data"]["members"][0]["top_role"] == {"id": 10, "name": "Ops"}


class TestWebhookRedactionAndSSRF:
    def test_webhook_url_is_redacted_by_default(self):
        wh = make_webhook(id=700, url="https://discord.com/api/webhooks/700/super-secret-token")
        data = webhook_to_dict(wh)
        assert "super-secret-token" not in data["url"]
        assert data["url"].endswith("/700/[REDACTED]")
        assert data["url_redacted"] is True

    def test_webhook_url_revealed_with_show_secrets(self):
        wh = make_webhook(id=700, url="https://discord.com/api/webhooks/700/super-secret-token")
        data = webhook_to_dict(wh, show_secrets=True)
        assert data["url"] == "https://discord.com/api/webhooks/700/super-secret-token"
        assert "url_redacted" not in data

    def test_webhook_info_cli_respects_show_secrets(self, cli_runner, use_client):
        guild = make_guild(id=1, name="TestGuild")
        client = make_client(guild)
        client.fetch_webhook = AsyncMock(
            return_value=make_webhook(id=700, url="https://discord.com/api/webhooks/700/secret123")
        )
        use_client(client)

        redacted = json.loads(cli_runner.invoke(main, ["webhook", "info", "700"]).output)
        assert "secret123" not in redacted["data"]["url"]

        revealed = json.loads(
            cli_runner.invoke(main, ["webhook", "info", "700", "--show-secrets"]).output
        )
        assert "secret123" in revealed["data"]["url"]

    def test_redact_webhook_url_handles_none_and_non_webhook(self):
        assert redact_webhook_url(None) is None
        assert redact_webhook_url("https://example.com/other") == "https://example.com/other"

    @pytest.mark.parametrize(
        "bad_url",
        [
            "file:///etc/passwd",
            "ftp://example.com/a.png",
            "http://127.0.0.1/secret",
            "http://169.254.169.254/latest/meta-data/",
            "http://10.0.0.1/internal.png",
            "http://192.168.1.1/router.png",
            "http://[::1]/local",
            "http://localhost/admin",
        ],
    )
    def test_validate_remote_url_blocks_ssrf_targets(self, bad_url):
        with pytest.raises(CliError):
            validate_remote_url(bad_url)


class TestPluginHardening:
    def test_plugin_cannot_shadow_builtin_group(self, monkeypatch):
        reg = CommandRegistry()

        @reg.group("channel")
        def builtin_channel():
            pass

        reg.lock_builtins()

        def evil_register(r: CommandRegistry):
            @r.group("channel")
            def hijacked():
                pass

        ep = MagicMock()
        ep.name = "evil-plugin"
        ep.value = "evil:register"
        ep.dist = MagicMock(version="1.0.0")
        ep.load.return_value = evil_register
        monkeypatch.setattr("discord_cli.plugins.entry_points", lambda **_: [ep])

        @click.group()
        def root():
            pass

        reg.attach_all(root)
        loaded = load_plugins(reg, root)

        assert loaded == []
        errs = plugin_errors()
        assert len(errs) == 1
        assert errs[0].name == "evil-plugin"
        assert "built-in" in errs[0].message

    def test_plugins_list_includes_errors_when_present(self, cli_runner, monkeypatch):
        monkeypatch.setattr("discord_cli.commands.plugins.loaded_plugins", lambda: [])
        monkeypatch.setattr(
            "discord_cli.commands.plugins.plugin_errors",
            lambda: [PluginError("broken", "broken:reg", "ImportError", "no module")],
        )

        result = cli_runner.invoke(main, ["plugins", "list"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["data"]["plugins"] == []
        assert payload["data"]["errors"][0]["name"] == "broken"


class TestNpmPackagingHardening:
    def test_npm_install_uses_isolated_venv_and_pins_version(self):
        repo_root = Path(__file__).resolve().parent.parent
        install_js = (repo_root / "packaging" / "npm" / "install.js").read_text(encoding="utf-8")
        index_js = (repo_root / "packaging" / "npm" / "index.js").read_text(encoding="utf-8")
        assert ".venv" in install_js
        assert "${pkg.name}==${pkg.version}" in install_js
        assert "--upgrade" not in install_js
        assert ".venv" in index_js
