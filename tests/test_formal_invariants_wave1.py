"""Formal-verification regression suite for Wave 1 (derived from Opus 5.5 Z3/Hypothesis audit)."""

from __future__ import annotations

import ipaddress
import json
import socket
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import aiohttp
from aiohttp import web
import click
import discord
import pytest

from discord_cli.cli import AliasedGroup, main
from discord_cli.client import _format_exception
from discord_cli.commands.api import _validate_endpoint
from discord_cli.commands.audit import _resolve_audit_action
from discord_cli.commands.messages import _safe_attachment_filename
from discord_cli.errors import CliError
from discord_cli.message_builder import split_content
from discord_cli.models import (
    _is_forbidden_ip,
    get_guild,
    read_image_bytes_async,
    redact_webhook_url,
    validate_remote_url,
    validate_webhook_url,
)
from discord_cli.output import (
    OutputOptions,
    enforce_max_chars,
    print_output,
    sanitize_csv_cell,
    stringify_ids,
)
from discord_cli.plugins import load_plugins, plugin_errors
from discord_cli.registry import CommandRegistry
from tests.conftest import (
    async_iter,
    make_category,
    make_client,
    make_guild,
    make_message,
    make_role,
    make_text_channel,
)


class TestSSRFAndRebindingInvariants:
    @pytest.mark.parametrize(
        "ip_str",
        [
            "100.100.100.200",  # Alibaba Cloud metadata (CGNAT)
            "100.64.0.1",  # CGNAT / Tailscale
            "100.127.255.254",  # CGNAT upper edge
            "192.88.99.1",  # 6to4 relay
            "127.0.0.1",  # Loopback
            "169.254.169.254",  # AWS/GCP/Azure metadata
            "10.0.0.1",  # RFC1918
            "172.16.0.1",  # RFC1918
            "192.168.1.1",  # RFC1918
            "0.0.0.0",  # Unspecified
            "224.0.0.1",  # Multicast
            "::1",  # IPv6 loopback
            "fec0::1",  # Deprecated site-local IPv6
            "fe80::1",  # IPv6 link-local
            "fc00::1",  # IPv6 ULA
            "::ffff:100.64.0.1",
            "::ffff:100.100.100.200",
            "::ffff:127.0.0.1",
            "ff02::1",  # IPv6 multicast
        ],
    )
    def test_forbidden_non_global_ips_are_blocked(self, ip_str):
        addr = ipaddress.ip_address(ip_str)
        assert _is_forbidden_ip(addr) is True
        url = f"http://[{ip_str}]/x.png" if addr.version == 6 else f"http://{ip_str}/x.png"
        with pytest.raises(CliError):
            validate_remote_url(url)

    @pytest.mark.parametrize(
        "ip_str", ["1.1.1.1", "8.8.8.8", "162.159.135.232", "2606:4700:4700::1111"]
    )
    def test_public_global_ips_are_allowed(self, ip_str):
        addr = ipaddress.ip_address(ip_str)
        assert _is_forbidden_ip(addr) is False

    async def test_dns_rebinding_blocked_at_connect_time(self, monkeypatch):
        """Even if pre-validation saw a public IP, connect-time resolver blocks 127.0.0.1."""

        async def rebind_resolve(self, host, port=0, family=socket.AF_UNSPEC):
            return [
                {
                    "hostname": host,
                    "host": "127.0.0.1",
                    "port": port,
                    "family": socket.AF_INET,
                    "proto": 0,
                    "flags": 0,
                }
            ]

        monkeypatch.setattr(aiohttp.resolver.ThreadedResolver, "resolve", rebind_resolve)

        with pytest.raises(CliError, match="non-public IP"):
            await read_image_bytes_async("http://rebind.example.com/secret.png")

    async def test_read_image_bytes_async_reads_full_multi_chunk_body_and_enforces_cap(
        self, monkeypatch
    ):
        payload_3mb = b"A" * (3 * 1024 * 1024)

        async def handle_big(request):
            resp = web.StreamResponse(status=200)
            await resp.prepare(request)
            for i in range(0, len(payload_3mb), 64 * 1024):
                await resp.write(payload_3mb[i : i + 64 * 1024])
            await resp.write_eof()
            return resp

        async def handle_huge(request):
            resp = web.StreamResponse(status=200)
            await resp.prepare(request)
            chunk = b"B" * (256 * 1024)
            for _ in range(50):  # 12.5 MiB > 10 MiB cap
                await resp.write(chunk)
            await resp.write_eof()
            return resp

        app = web.Application()
        app.router.add_get("/big.png", handle_big)
        app.router.add_get("/huge.png", handle_huge)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]

        # Temporarily permit 127.0.0.1 ONLY to test the live aiohttp chunked reader.
        monkeypatch.setattr("discord_cli.models._is_forbidden_ip", lambda _addr: False)
        try:
            data = await read_image_bytes_async(f"http://127.0.0.1:{port}/big.png")
            assert len(data) == len(payload_3mb)
            assert data == payload_3mb

            with pytest.raises(CliError, match="maximum allowed size"):
                await read_image_bytes_async(f"http://127.0.0.1:{port}/huge.png")
        finally:
            await runner.cleanup()


class TestWebhookSecrecyAndRedaction:
    @pytest.mark.parametrize(
        "url",
        [
            "https://discord.com/api/webhooks/123/SECRET_TOKEN",
            "HTTPS://DISCORD.COM/api/v10/webhooks/123/SECRET_TOKEN",
            "Https://www.discord.com/api/webhooks/123/SECRET_TOKEN?wait=true",
            "https://ptb.discordapp.com/api/webhooks/123/SECRET_TOKEN/github",
            "Error calling https://canary.discord.com/api/webhooks/123/SECRET_TOKEN failed",
        ],
    )
    def test_redact_webhook_url_scrubs_all_variants_and_embedded_text(self, url):
        redacted = redact_webhook_url(url)
        assert "SECRET_TOKEN" not in redacted
        assert "[REDACTED]" in redacted

    def test_format_exception_never_leaks_webhook_token(self):
        exc = RuntimeError(
            "Connection failed for https://discord.com/api/webhooks/999/MY_LIVE_TOKEN?wait=true"
        )
        formatted = _format_exception(exc)
        assert "MY_LIVE_TOKEN" not in formatted["message"]
        assert "[REDACTED]" in formatted["message"]

    def test_webhook_validate_allows_discord_under_fake_ip_dns_and_blocks_evil_host(self):
        valid = validate_webhook_url("https://www.discord.com/api/webhooks/123/tok_abc")
        assert valid.endswith("tok_abc")
        with pytest.raises(CliError, match="Invalid webhook host"):
            validate_webhook_url("https://evil.example.com/api/webhooks/123/tok_abc")

    def test_webhook_split_with_thread_name_chains_created_thread_id(self, cli_runner, monkeypatch):
        created_thread_ch = make_text_channel(id=88888, name="forum-post")
        msg1 = make_message(id=701, channel=created_thread_ch, content="part1")
        msg2 = make_message(id=702, channel=created_thread_ch, content="part2")
        fake_wh = MagicMock()
        fake_wh.send = AsyncMock(side_effect=[msg1, msg2])
        monkeypatch.setattr("discord.Webhook.from_url", MagicMock(return_value=fake_wh))

        url = "https://discord.com/api/webhooks/123/secret-tok"
        long_text = ("A" * 1500) + "\n" + ("B" * 1000)
        result = cli_runner.invoke(
            main,
            [
                "webhook",
                "send",
                "--url",
                url,
                "--content",
                long_text,
                "--split",
                "--thread-name",
                "Release",
            ],
        )

        assert result.exit_code == 0
        assert fake_wh.send.await_count == 2
        assert fake_wh.send.await_args_list[0].kwargs["thread_name"] == "Release"
        assert fake_wh.send.await_args_list[1].kwargs["thread"].id == 88888


class TestOutputShapingAndRichSafety:
    @pytest.mark.parametrize("compact", [True, False])
    @pytest.mark.parametrize("budget", [256, 400, 1000])
    def test_enforce_max_chars_respects_budget_for_success_and_error(self, compact, budget):
        success = {
            "ok": True,
            "data": {
                "features": [],
                "messages": [{"id": i, "content": f"hello world {i} " * 10} for i in range(50)],
            },
        }
        out = enforce_max_chars(success, max_chars=budget, compact=compact)
        serialized = (
            json.dumps(out, separators=(",", ":")) if compact else json.dumps(out, indent=2)
        )
        assert len(serialized) <= budget
        assert out["meta"]["truncated"] is True

        error = {
            "ok": False,
            "error": {"type": "HTTPException", "message": "X" * 1000, "extra": "Y" * 500},
        }
        err_out = enforce_max_chars(error, max_chars=budget, compact=compact)
        err_ser = (
            json.dumps(err_out, separators=(",", ":")) if compact else json.dumps(err_out, indent=2)
        )
        assert len(err_ser) <= budget
        assert err_out["ok"] is False

    def test_enforce_max_chars_trims_largest_list_not_empty_first_list(self):
        payload = {
            "ok": True,
            "data": {
                "features": [],
                "messages": [{"id": i, "content": f"msg {i}"} for i in range(100)],
            },
        }
        out = enforce_max_chars(payload, max_chars=1200, compact=True)
        assert out["data"] is not None
        assert len(out["data"]["messages"]) >= 1

    def test_enforce_max_chars_truncates_single_long_message_instead_of_dropping_it(self):
        payload = {"ok": True, "data": {"messages": [{"id": 1, "content": "Z" * 3000}]}}
        out = enforce_max_chars(payload, max_chars=800, compact=True)
        assert len(out["data"]["messages"]) == 1
        assert out["data"]["messages"][0]["content"].endswith("...")

    def test_stringify_ids_handles_tuples_and_preserves_bools(self):
        big = 1 << 60
        result = stringify_ids({"ids": (None, big), "ok": True, "bad": False})
        assert result == {"ids": [None, str(big)], "ok": True, "bad": False}

    def test_rich_markup_in_messages_and_errors_never_crashes(self, capsys):
        msg_payload = {
            "ok": True,
            "data": {
                "messages": [{"id": 1, "content": "lol [/b] [link=https://evil]click[/link]"}]
            },
        }
        print_output(msg_payload, human=True)
        assert "lol [/b]" in capsys.readouterr().out

        err_payload = {"ok": False, "error": {"type": "CliError", "message": "bad [/x] field"}}
        print_output(err_payload, options=OutputOptions(quiet=True))
        assert "bad [/x] field" in capsys.readouterr().err

    def test_csv_formula_neutralization(self):
        assert sanitize_csv_cell('=HYPERLINK("http://evil")').startswith("'=HYPERLINK")
        assert sanitize_csv_cell("+1+1") == "'+1+1"
        assert sanitize_csv_cell("-2+3") == "'-2+3"
        assert sanitize_csv_cell("@SUM(A1)") == "'@SUM(A1)"
        assert sanitize_csv_cell("normal text") == "normal text"


class TestSplitFilenameEndpointAuditAndStaleEdits:
    def test_split_content_invariants(self):
        with pytest.raises(ValueError):
            split_content("abc", max_length=0)
        assert split_content("   \n\t  ", max_length=10) == []
        chunks = split_content((" " * 3000) + "x", max_length=2000)
        assert all(1 <= len(c) <= 2000 and c.strip() for c in chunks)
        assert "".join(c.strip() for c in chunks) == "x"

    def test_safe_attachment_filename_preserves_ext_and_caps_length(self, tmp_path):
        jp = _safe_attachment_filename(1, "日本語.png")
        assert jp.endswith(".png")
        long_name = _safe_attachment_filename(1, ("a" * 400) + ".tar.gz")
        assert len(long_name.encode("utf-8")) <= 255
        assert long_name.endswith(".gz")
        for evil in ("../../etc/passwd", "..\\..\\evil.exe", "\x00.txt", "..", "."):
            safe = _safe_attachment_filename(9, evil)
            resolved = (tmp_path / safe).resolve()
            assert tmp_path.resolve() in resolved.parents

    @pytest.mark.parametrize(
        "bad_endpoint",
        [
            "/../admin",
            "/guilds/1/..",
            "/guilds/%2e%2e/users",
            "/guilds/%252e%252e/users",
            "/guilds/1\tfoo",
            "/guilds/1 foo",
            "/guilds/1\x1b[31m",
            "//evil.com/x",
            "https://evil.com/x",
            "/guilds/1\\..\\x",
        ],
    )
    def test_validate_endpoint_blocks_traversal_and_control_chars(self, bad_endpoint):
        with pytest.raises(CliError):
            _validate_endpoint(bad_endpoint)

    def test_validate_endpoint_allows_url_in_query_string(self):
        ep = "/guilds/1/audit-logs?ref=https://example.com"
        assert _validate_endpoint(ep) == ep

    def test_audit_action_rejects_non_enum_attributes(self):
        assert _resolve_audit_action("ban") == discord.AuditLogAction.ban
        with pytest.raises(CliError, match="Unknown audit log action"):
            _resolve_audit_action("category")

    def test_stale_edit_returns_post_edit_values(self, cli_runner, use_client):
        old_role = make_role(id=2, name="OldRole")
        new_role = make_role(id=2, name="NewRole")
        old_role.edit = AsyncMock(return_value=new_role)

        old_cat = make_category(id=400, name="OldCat")
        new_cat = make_category(id=400, name="NewCat")
        old_cat.edit = AsyncMock(return_value=new_cat)

        guild = make_guild(id=1, name="OldGuild", roles=[old_role], categories=[old_cat])
        use_client(make_client(guild))

        r_role = json.loads(
            cli_runner.invoke(main, ["role", "edit", "2", "--name", "NewRole"]).output
        )
        assert r_role["data"]["updated"]["name"] == "NewRole"

        r_cat = json.loads(
            cli_runner.invoke(main, ["category", "edit", "400", "--name", "NewCat"]).output
        )
        assert r_cat["data"]["updated"]["name"] == "NewCat"


class TestPluginAndGuildStateMachines:
    def test_plugin_isolation_blocks_aliases_subcommand_hijack_and_system_exit(self, monkeypatch):
        reg = CommandRegistry()

        @reg.group("message")
        def msg_grp():
            pass

        @msg_grp.command("send")
        def msg_send():
            pass

        reg.lock_builtins(extra_protected=AliasedGroup.ALIASES.keys())

        def alias_plugin(r: CommandRegistry):
            @r.group("invite")
            def hijacked_alias():
                pass

        def subcmd_plugin(r: CommandRegistry):
            @r._groups["message"].command("send")
            def evil_send():
                pass

        def exit_plugin(r: CommandRegistry):
            raise SystemExit(3)

        eps = []
        for name, fn in [
            ("alias-p", alias_plugin),
            ("sub-p", subcmd_plugin),
            ("exit-p", exit_plugin),
        ]:
            ep = MagicMock()
            ep.name = name
            ep.value = f"{name}:reg"
            ep.dist = MagicMock(version="1.0")
            ep.load.return_value = fn
            eps.append(ep)

        monkeypatch.setattr("discord_cli.plugins.entry_points", lambda **_: eps)

        @click.group()
        def root():
            pass

        reg.attach_all(root)
        loaded = load_plugins(reg, root)

        assert loaded == []
        assert len(plugin_errors()) == 3
        assert reg._groups["message"].commands["send"] is msg_send

    def test_no_plugins_with_help_does_not_load_plugins(self, cli_runner, monkeypatch):
        called = []
        monkeypatch.setattr("discord_cli.cli.load_plugins", lambda *a, **k: called.append(True))
        saved = main._plugins_loaded
        main._plugins_loaded = False
        try:
            res = cli_runner.invoke(main, ["--no-plugins", "--help"])
            assert res.exit_code == 0
            assert called == []
        finally:
            main._plugins_loaded = saved

    async def test_get_guild_exhaustive_fail_closed_states(self):
        g1 = make_guild(id=1, name="G1")
        g2 = make_guild(id=2, name="G2")

        # 0 cached, 0 fetched -> error
        c0 = make_client(g1)
        c0.guilds = []
        c0.fetch_guilds = MagicMock(return_value=async_iter([]))
        with pytest.raises(CliError, match="not in any guilds"):
            await get_guild(c0, None)

        # 2 cached, no explicit ID -> fail closed
        c2 = make_client(g1)
        c2.guilds = [g1, g2]
        with pytest.raises(CliError, match="--guild"):
            await get_guild(c2, None)

        # 2 cached, explicit ID -> honors explicit ID
        c2.get_guild = MagicMock(side_effect=lambda gid: g2 if gid == 2 else g1)
        assert (await get_guild(c2, 2)) is g2
