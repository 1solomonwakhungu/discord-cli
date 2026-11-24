"""Tests for Wave 1b: output shaping, position-independent flags, zero-gateway webhooks, rich messages, audit, doctor, api."""

from __future__ import annotations

import datetime as dt
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from discord_cli.cli import main
from discord_cli.message_builder import load_embed, split_content
from discord_cli.output import OutputOptions, enforce_max_chars, project_fields, stringify_ids
from tests.conftest import (
    async_iter,
    make_client,
    make_guild,
    make_member,
    make_message,
    make_role,
    make_text_channel,
    make_user,
)


class TestOutputShapingAndPositionIndependentFlags:
    def test_position_independent_flags_work_after_subcommand(self, cli_runner, use_client):
        ch1 = make_text_channel(id=123456789012345678, name="announcements")
        ch2 = make_text_channel(id=223456789012345678, name="general")
        guild = make_guild(id=999999999999999999, name="HQ", channels=[ch1, ch2])
        use_client(make_client(guild))

        result = cli_runner.invoke(
            main,
            ["channel", "list", "--compact", "--fields", "id,name", "--string-ids"],
        )

        assert result.exit_code == 0
        assert "\n  " not in result.output
        payload = json.loads(result.output)
        assert payload["ok"] is True
        assert payload["data"]["guild_id"] == "999999999999999999"
        assert payload["data"]["channels"] == [
            {"id": "123456789012345678", "name": "announcements"},
            {"id": "223456789012345678", "name": "general"},
        ]

    def test_formats_jsonl_csv_markdown_raw_quiet_and_file_output(
        self, cli_runner, use_client, tmp_path
    ):
        ch1 = make_text_channel(id=300, name="general")
        ch2 = make_text_channel(id=301, name="alerts")
        guild = make_guild(id=1, name="HQ", channels=[ch1, ch2])
        use_client(make_client(guild))

        # jsonl
        r_jsonl = cli_runner.invoke(main, ["channel", "list", "--format", "jsonl", "--fields", "id,name"])
        assert r_jsonl.exit_code == 0
        lines = [json.loads(line) for line in r_jsonl.output.strip().splitlines()]
        assert lines == [{"id": 300, "name": "general"}, {"id": 301, "name": "alerts"}]

        # csv
        r_csv = cli_runner.invoke(main, ["channel", "list", "--format", "csv", "--fields", "id,name"])
        assert r_csv.exit_code == 0
        assert "id,name" in r_csv.output
        assert "300,general" in r_csv.output

        # markdown
        r_md = cli_runner.invoke(main, ["channel", "list", "--format", "markdown", "--fields", "id,name"])
        assert r_md.exit_code == 0
        assert "| id | name |" in r_md.output
        assert "| 300 | general |" in r_md.output

        # raw
        r_raw = cli_runner.invoke(main, ["channel", "list", "--format", "raw", "--fields", "id,name"])
        assert r_raw.exit_code == 0
        raw_data = json.loads(r_raw.output)
        assert "ok" not in raw_data
        assert raw_data["channels"][0] == {"id": 300, "name": "general"}

        # quiet
        r_q = cli_runner.invoke(main, ["channel", "list", "--quiet"])
        assert r_q.exit_code == 0
        assert r_q.output.strip().splitlines() == ["300", "301"]

        # atomic file output
        out_file = tmp_path / "channels.json"
        r_out = cli_runner.invoke(main, ["channel", "list", "--compact", "--output", str(out_file)])
        assert r_out.exit_code == 0
        assert r_out.output == ""
        saved = json.loads(out_file.read_text(encoding="utf-8"))
        assert saved["ok"] is True

    def test_max_chars_always_produces_valid_bounded_json(self):
        payload = {
            "ok": True,
            "data": {
                "messages": [
                    {"id": i, "content": f"message number {i} with extra words"} for i in range(50)
                ]
            },
        }
        truncated = enforce_max_chars(payload, max_chars=350, compact=True)
        serialized = json.dumps(truncated, separators=(",", ":"))
        assert len(serialized) <= 350
        parsed = json.loads(serialized)
        assert parsed["meta"]["truncated"] is True
        assert parsed["meta"]["omitted_items"] > 0

    def test_stringify_ids_preserves_64bit_snowflakes_and_bools(self):
        big = 1234567890123456789
        shaped = stringify_ids({"id": 123, "count": 5, "ok": True, "big_num": big})
        assert shaped == {"id": "123", "count": 5, "ok": True, "big_num": str(big)}

    def test_project_fields_supports_nested_dot_paths(self):
        data = {
            "channel_id": 10,
            "messages": [{"id": 1, "author": {"id": 2, "name": "alice"}, "content": "hi"}],
        }
        projected = project_fields(data, ("id", "author.name"))
        assert projected["messages"] == [{"id": 1, "author": {"name": "alice"}}]


class TestRichMessagingAndPagination:
    def test_message_send_with_file_reply_silent_and_split(
        self, cli_runner, use_client, tmp_path
    ):
        ch = make_text_channel(id=300, name="general")
        sent1 = make_message(id=601, channel=ch, content="part1")
        sent2 = make_message(id=602, channel=ch, content="part2")
        ch.send = AsyncMock(side_effect=[sent1, sent2])
        guild = make_guild(id=1, name="HQ", channels=[ch])
        use_client(make_client(guild))

        artifact = tmp_path / "log.txt"
        artifact.write_text("deploy log", encoding="utf-8")
        long_text = ("A" * 1500) + "\n" + ("B" * 1000)

        result = cli_runner.invoke(
            main,
            [
                "message",
                "send",
                "300",
                "--content",
                long_text,
                "--file",
                str(artifact),
                "--reply-to",
                "555",
                "--silent",
                "--split",
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["ok"] is True
        assert payload["data"]["count"] == 2
        assert ch.send.await_count == 2
        first_kwargs = ch.send.await_args_list[0].kwargs
        assert first_kwargs["silent"] is True
        assert first_kwargs["reference"].message_id == 555
        assert len(first_kwargs["files"]) == 1

    def test_message_pins_publish_download_and_unreact(self, cli_runner, use_client, tmp_path):
        ch = make_text_channel(id=300, name="announcements")
        att = MagicMock()
        att.id = 42
        att.filename = "../../evil/report.txt"
        att.size = 10
        att.url = "https://cdn.discordapp.com/attachments/1/42/report.txt"
        att.save = AsyncMock()

        msg = make_message(id=600, channel=ch, content="Release!", attachments=[att])
        msg.publish = AsyncMock(return_value=msg)
        msg.remove_reaction = AsyncMock(return_value=None)
        ch.pins = MagicMock(return_value=async_iter([msg]))
        ch.fetch_message = AsyncMock(return_value=msg)

        guild = make_guild(id=1, name="HQ", channels=[ch])
        client = make_client(guild)
        client.user = make_user(id=999, name="OpsBot", bot=True)
        use_client(client)

        r_pins = cli_runner.invoke(main, ["message", "pins", "300"])
        assert r_pins.exit_code == 0
        assert json.loads(r_pins.output)["data"]["count"] == 1

        r_pub = cli_runner.invoke(main, ["message", "publish", "600", "--channel", "300"])
        assert r_pub.exit_code == 0
        msg.publish.assert_awaited_once()

        out_dir = tmp_path / "dl"
        r_dl = cli_runner.invoke(
            main, ["message", "download", "600", "--channel", "300", "--out", str(out_dir)]
        )
        assert r_dl.exit_code == 0
        dl_data = json.loads(r_dl.output)["data"]
        assert dl_data["count"] == 1
        assert dl_data["files"][0]["saved_path"].startswith(str(out_dir.resolve()))
        assert ".." not in dl_data["files"][0]["saved_path"]

        r_unreact = cli_runner.invoke(
            main, ["message", "unreact", "600", "--channel", "300", "--emoji", "👍"]
        )
        assert r_unreact.exit_code == 0
        msg.remove_reaction.assert_awaited_once()

    def test_member_list_pagination_limit_and_after(self, cli_runner, use_client):
        m1 = make_member(id=201, name="alice")
        m2 = make_member(id=202, name="bob")
        guild = make_guild(id=1, name="HQ", members=[m1, m2])
        use_client(make_client(guild))

        result = cli_runner.invoke(main, ["member", "list", "--limit", "2", "--after", "200"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["ok"] is True
        assert payload["data"]["pagination"] == {"has_more": True, "next_after": 202}


class TestZeroGatewayWebhookExecution:
    def test_webhook_send_edit_fetch_delete_without_bot_token(self, cli_runner, monkeypatch):
        msg = make_message(id=777, content="Deploy started")
        fake_wh = MagicMock()
        fake_wh.send = AsyncMock(return_value=msg)
        fake_wh.edit_message = AsyncMock(return_value=make_message(id=777, content="Deploy done"))
        fake_wh.fetch_message = AsyncMock(return_value=msg)
        fake_wh.delete_message = AsyncMock(return_value=None)

        monkeypatch.setattr("discord_cli.commands.webhooks.validate_remote_url", lambda u: u)
        monkeypatch.setattr("discord.Webhook.from_url", MagicMock(return_value=fake_wh))

        url = "https://discord.com/api/webhooks/123456/fake-token"
        r_send = cli_runner.invoke(
            main,
            [
                "webhook",
                "send",
                "--url",
                url,
                "--template",
                "deploy",
                "--title",
                "v1.7.0",
                "--field",
                "Env=prod:inline",
                "--thread-id",
                "999",
            ],
        )
        assert r_send.exit_code == 0
        assert json.loads(r_send.output)["data"]["sent"]["id"] == 777

        r_edit = cli_runner.invoke(
            main,
            ["webhook", "edit-message", "777", "--url", url, "--content", "Deploy done"],
        )
        assert r_edit.exit_code == 0
        assert json.loads(r_edit.output)["data"]["updated"]["content"] == "Deploy done"

        r_fetch = cli_runner.invoke(main, ["webhook", "fetch-message", "777", "--url", url])
        assert r_fetch.exit_code == 0
        assert json.loads(r_fetch.output)["data"]["id"] == 777

        r_del = cli_runner.invoke(main, ["webhook", "delete-message", "777", "--url", url])
        assert r_del.exit_code == 0
        assert json.loads(r_del.output)["data"]["deleted"]["message_id"] == 777


class TestAuditDoctorAndRawApi:
    def test_audit_list_and_user(self, cli_runner, use_client):
        actor = make_user(id=10, name="admin")
        target = make_user(id=20, name="spammer")
        entry = SimpleNamespace(
            id=9001,
            action=discord.AuditLogAction.ban,
            user=actor,
            target=target,
            reason="Spam raid",
            created_at=dt.datetime(2026, 3, 1, tzinfo=dt.timezone.utc),
        )
        guild = make_guild(id=1, name="HQ")
        guild.audit_logs = MagicMock(side_effect=lambda **_: async_iter([entry]))
        use_client(make_client(guild))

        r_list = cli_runner.invoke(main, ["audit", "list", "--action", "ban", "--limit", "10"])
        assert r_list.exit_code == 0
        data = json.loads(r_list.output)["data"]
        assert data["count"] == 1
        assert data["entries"][0]["action"] == "ban"

        r_user = cli_runner.invoke(main, ["audit", "user", "20"])
        assert r_user.exit_code == 0
        u_data = json.loads(r_user.output)["data"]
        assert u_data["entries"][0]["role_in_entry"] == "target"

    def test_doctor_check_reports_intents_and_permissions(self, cli_runner, use_client):
        bot_role = make_role(id=50, name="OpsBot", position=8)
        bot_member = make_member(
            id=999,
            name="OpsBot",
            bot=True,
            top_role=bot_role,
            guild_permissions=discord.Permissions(manage_channels=True, send_messages=True),
        )
        ch = make_text_channel(id=300, name="general")
        ch.permissions_for = MagicMock(return_value=discord.Permissions(view_channel=True, send_messages=True))
        guild = make_guild(id=1, name="HQ", roles=[bot_role], channels=[ch], members=[bot_member])
        client = make_client(guild)
        client.user = make_user(id=999, name="OpsBot", bot=True)
        # Members + Message Content enabled, Presence disabled
        flags = (1 << 14) | (1 << 18)
        client.http.request = AsyncMock(return_value={"id": "55555", "flags": flags})
        use_client(client)

        result = cli_runner.invoke(main, ["doctor", "check", "--channel", "300"])

        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        assert data["status"] == "warn"  # presence intent off
        assert data["intents"] == {
            "presence": False,
            "server_members": True,
            "message_content": True,
        }
        assert data["guild"]["bot_top_role_position"] == 8
        assert "send_messages" in data["channel"]["bot_permissions"]

    def test_api_request_validates_endpoint_and_forwards_params(self, cli_runner, use_client):
        guild = make_guild(id=1, name="HQ")
        client = make_client(guild)
        client.http.request = AsyncMock(return_value={"id": "1", "name": "HQ"})
        use_client(client)

        r_ok = cli_runner.invoke(
            main,
            ["api", "request", "GET", "/guilds/1", "--query", "with_counts=true"],
        )
        assert r_ok.exit_code == 0
        payload = json.loads(r_ok.output)
        assert payload["data"]["response"] == {"id": "1", "name": "HQ"}

        r_bad = cli_runner.invoke(main, ["api", "request", "GET", "https://evil.com/steal"])
        assert r_bad.exit_code == 1
        assert "Invalid Discord API endpoint" in r_bad.output


class TestMessageBuilderUnits:
    def test_split_content_respects_max_length(self):
        chunks = split_content("word " * 600, max_length=2000)
        assert len(chunks) >= 2
        assert all(len(c) <= 2000 for c in chunks)

    def test_load_embed_template_and_fields(self):
        embed = load_embed(template="success", title="Done", fields=["A=1:inline", "B=2"])
        assert embed is not None
        assert embed.title == "✅ Done"
        assert len(embed.fields) == 2
        assert embed.fields[0].inline is True
        assert embed.fields[1].inline is False
