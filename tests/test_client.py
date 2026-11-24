"""Tests for discord_cli.client: REST-first default and opt-in Gateway lifecycle."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

from discord_cli import client as client_mod
from discord_cli.errors import ConfigError


async def ok_action(client, **kwargs):
    return {"msg": "hi"}


async def list_action(client, **kwargs):
    return [{"id": 1}]


async def failing_action(client, **kwargs):
    raise ValueError("kaboom")


class TestFallbackIntents:
    def test_returns_reduced_intents(self):
        intents = client_mod.fallback_intents()
        assert intents.guilds is True
        assert intents.reactions is True
        assert intents != discord.Intents.all()


class TestRestClient:
    async def test_rest_default_uses_login_and_closes(self, monkeypatch):
        login_calls = []

        async def fake_login(self, token):
            login_calls.append(token)

        monkeypatch.setattr(client_mod.RestClient, "login", fake_login)

        result, error = await client_mod._run_async(ok_action, {}, "fake-token")

        assert login_calls == ["fake-token"]
        assert result == {"msg": "hi"}
        assert error is None

    async def test_rest_action_http_exception_formatted(self, monkeypatch):
        monkeypatch.setattr(client_mod.RestClient, "login", AsyncMock(return_value=None))
        response = SimpleNamespace(status=403, reason="Forbidden")
        http_exc = discord.HTTPException(response, {"code": 50013, "message": "Missing Permissions"})

        async def http_failing_action(client, **kwargs):
            raise http_exc

        result, error = await client_mod._run_async(http_failing_action, {}, "fake-token")

        assert result is None
        assert error["type"] == "HTTPException"
        assert error["status"] == 403
        assert error["code"] == 50013

    async def test_rest_login_failure_returned_as_error(self, monkeypatch):
        monkeypatch.setattr(
            client_mod.RestClient, "login", AsyncMock(side_effect=RuntimeError("bad token"))
        )

        result, error = await client_mod._run_async(ok_action, {}, "fake-token")

        assert result is None
        assert error["type"] == "RuntimeError"
        assert error["message"] == "bad token"
        assert error["category"] == "RUNTIME_ERROR"
        assert error["exit_code"] == 1
        assert error["retryable"] is False

    async def test_rest_session_closes_on_error(self):
        c = client_mod.RestClient()
        c.login = AsyncMock(side_effect=RuntimeError("boom"))

        with pytest.raises(RuntimeError):
            async with client_mod.rest_session(c, "fake-token"):
                pass

        assert c.is_closed()


class TestManagementClientOnReady:
    async def test_success_sets_result_and_closes(self):
        c = client_mod.ManagementClient(ok_action, {}, discord.Intents.default())
        await c.on_ready()
        assert c.result == {"msg": "hi"}
        assert c.error is None
        assert c.is_closed()

    async def test_failure_sets_error_and_closes(self):
        c = client_mod.ManagementClient(failing_action, {}, discord.Intents.default())
        await c.on_ready()
        assert c.result is None
        assert c.error["type"] == "ValueError"
        assert c.error["message"] == "kaboom"
        assert c.error["category"] == "RUNTIME_ERROR"
        assert c.is_closed()

    async def test_http_exception_includes_status_and_code(self):
        response = SimpleNamespace(status=403, reason="Forbidden")
        http_exc = discord.HTTPException(response, {"code": 50013, "message": "Missing Permissions"})

        async def http_failing_action(client, **kwargs):
            raise http_exc

        c = client_mod.ManagementClient(http_failing_action, {}, discord.Intents.default())
        await c.on_ready()

        assert c.error["type"] == "HTTPException"
        assert c.error["status"] == 403
        assert c.error["code"] == 50013


class TestRunAsyncGateway:
    async def test_success_returns_result_with_no_error(self, monkeypatch):
        async def fake_start(self, token):
            await self.on_ready()

        monkeypatch.setattr(client_mod.ManagementClient, "start", fake_start)

        result, error = await client_mod._run_async(
            ok_action, {}, "fake-token-for-testing", use_gateway=True
        )

        assert result == {"msg": "hi"}
        assert error is None

    async def test_action_error_is_propagated_without_warning(self, monkeypatch):
        async def fake_start(self, token):
            await self.on_ready()

        monkeypatch.setattr(client_mod.ManagementClient, "start", fake_start)

        result, error = await client_mod._run_async(
            failing_action, {}, "fake-token-for-testing", use_gateway=True
        )

        assert result is None
        assert error["type"] == "ValueError"
        assert error["message"] == "kaboom"
        assert error["category"] == "RUNTIME_ERROR"

    async def test_retries_with_fallback_intents_on_privileged_intents_required(self, monkeypatch):
        async def fake_start(self, token):
            if self.intents == discord.Intents.all():
                raise discord.PrivilegedIntentsRequired(shard_id=None)
            await self.on_ready()

        monkeypatch.setattr(client_mod.ManagementClient, "start", fake_start)

        result, error = await client_mod._run_async(
            ok_action, {}, "fake-token-for-testing", use_gateway=True
        )

        assert error is None
        assert result["msg"] == "hi"
        assert "non-privileged intents" in result["warning"]

    async def test_fallback_warning_emitted_to_stderr_for_list_results(self, monkeypatch, capsys):
        async def fake_start(self, token):
            if self.intents == discord.Intents.all():
                raise discord.PrivilegedIntentsRequired(shard_id=None)
            await self.on_ready()

        monkeypatch.setattr(client_mod.ManagementClient, "start", fake_start)

        result, error = await client_mod._run_async(
            list_action, {}, "fake-token-for-testing", use_gateway=True
        )

        assert error is None
        assert result == [{"id": 1}]
        assert "non-privileged intents" in capsys.readouterr().err

    async def test_returns_last_privileged_intents_error_if_both_attempts_fail(self, monkeypatch):
        async def fake_start(self, token):
            raise discord.PrivilegedIntentsRequired(shard_id=None)

        monkeypatch.setattr(client_mod.ManagementClient, "start", fake_start)

        result, error = await client_mod._run_async(
            ok_action, {}, "fake-token-for-testing", use_gateway=True
        )

        assert result is None
        assert error["type"] == "PrivilegedIntentsRequired"

    async def test_generic_exception_from_start_is_returned_as_error(self, monkeypatch):
        async def fake_start(self, token):
            raise RuntimeError("network unreachable")

        monkeypatch.setattr(client_mod.ManagementClient, "start", fake_start)

        result, error = await client_mod._run_async(
            ok_action, {}, "fake-token-for-testing", use_gateway=True
        )

        assert result is None
        assert error["type"] == "RuntimeError"
        assert error["message"] == "network unreachable"
        assert error["category"] == "RUNTIME_ERROR"

    async def test_env_var_enables_gateway_transport(self, monkeypatch):
        monkeypatch.setenv("DISCORD_CLI_TRANSPORT", "gateway")

        async def fake_start(self, token):
            await self.on_ready()

        monkeypatch.setattr(client_mod.ManagementClient, "start", fake_start)

        result, error = await client_mod._run_async(ok_action, {}, "fake-token")
        assert result == {"msg": "hi"}
        assert error is None


class TestRunBot:
    def test_runs_async_via_asyncio_run_rest_default(self, monkeypatch):
        monkeypatch.setattr(client_mod.RestClient, "login", AsyncMock(return_value=None))

        result, error = client_mod.run_bot(ok_action, {}, "fake-token-for-testing")

        assert result == {"msg": "hi"}
        assert error is None

    def test_runs_async_via_gateway_when_requested(self, monkeypatch):
        async def fake_start(self, token):
            await self.on_ready()

        monkeypatch.setattr(client_mod.ManagementClient, "start", fake_start)

        result, error = client_mod.run_bot(
            ok_action, {}, "fake-token-for-testing", use_gateway=True
        )

        assert result == {"msg": "hi"}
        assert error is None


class TestRunAction:
    def test_config_error_prints_error_payload_and_exits_1(self, monkeypatch, capsys):
        def raise_config_error(token_override=None):
            raise ConfigError("DISCORD_BOT_TOKEN not found in environment, .env, or --token")

        monkeypatch.setattr(client_mod, "load_config", raise_config_error)

        with pytest.raises(SystemExit) as exc_info:
            client_mod.run_action(ok_action, {}, human=False)

        assert exc_info.value.code == 1
        assert "DISCORD_BOT_TOKEN" in capsys.readouterr().out

    def test_success_prints_ok_payload_and_exits_0(self, monkeypatch, capsys):
        monkeypatch.setattr(
            client_mod, "load_config", lambda token_override=None: SimpleNamespace(bot_token="tok")
        )
        monkeypatch.setattr(client_mod, "run_bot", lambda action, kwargs, token: ({"id": 1}, None))

        with pytest.raises(SystemExit) as exc_info:
            client_mod.run_action(ok_action, {}, human=False)

        assert exc_info.value.code == 0
        out = capsys.readouterr().out
        assert '"ok": true' in out

    def test_bot_error_prints_error_payload_and_exits_1(self, monkeypatch, capsys):
        monkeypatch.setattr(
            client_mod, "load_config", lambda token_override=None: SimpleNamespace(bot_token="tok")
        )
        monkeypatch.setattr(
            client_mod,
            "run_bot",
            lambda action, kwargs, token: (None, {"type": "CliError", "message": "nope"}),
        )

        with pytest.raises(SystemExit) as exc_info:
            client_mod.run_action(ok_action, {}, human=False)

        assert exc_info.value.code == 1
        out = capsys.readouterr().out
        assert "nope" in out


class TestBotSession:
    async def test_closes_client_even_when_start_raises(self):
        c = client_mod.ManagementClient(ok_action, {}, discord.Intents.default())
        c.start = AsyncMock(side_effect=RuntimeError("boom"))

        with pytest.raises(RuntimeError):
            async with client_mod.bot_session(c, "fake-token-for-testing"):
                pass

        assert c.is_closed()

    async def test_yields_the_client_on_success(self):
        c = client_mod.ManagementClient(ok_action, {}, discord.Intents.default())

        async def fake_start(token):
            await c.on_ready()

        c.start = fake_start

        async with client_mod.bot_session(c, "fake-token-for-testing") as session:
            assert session is c
            assert session.result == {"msg": "hi"}
