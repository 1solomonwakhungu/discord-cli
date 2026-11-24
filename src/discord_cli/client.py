"""Discord bot lifecycle: REST-first by default, zero-gateway HTTP, and opt-in Gateway."""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from typing import Any, Callable

import discord

from discord_cli.config import load_config
from discord_cli.errors import DiscordCliError
from discord_cli.output import OutputOptions, make_payload, print_output

Action = Callable[..., Awaitable[Any]]
HttpAction = Callable[..., Awaitable[Any]]


def _format_exception(exc: Exception) -> dict[str, Any]:
    error: dict[str, Any] = {"type": exc.__class__.__name__, "message": str(exc)}
    if isinstance(exc, discord.HTTPException):
        error.update({"status": exc.status, "code": exc.code})
    return error


class RestClient(discord.Client):
    """A lightweight discord.Client that authenticates over REST only (zero Gateway IDENTIFY)."""

    def __init__(self) -> None:
        super().__init__(intents=discord.Intents.none())
        self._discord_cli_transport = "rest"
        self._discord_cli_cache: dict[Any, Any] = {}


class ManagementClient(discord.Client):
    """A discord.Client that runs a single action on_ready over the Gateway and then closes."""

    def __init__(self, action: Action, kwargs: dict[str, Any], intents: discord.Intents):
        super().__init__(intents=intents)
        self._discord_cli_transport = "gateway"
        self._discord_cli_cache: dict[Any, Any] = {}
        self.action = action
        self.kwargs = kwargs
        self.result: Any = None
        self.error: dict[str, Any] | None = None

    async def on_ready(self) -> None:
        try:
            self.result = await self.action(self, **self.kwargs)
        except Exception as exc:  # noqa: BLE001 - user-facing CLI boundary
            self.error = _format_exception(exc)
        finally:
            await self.close()


@asynccontextmanager
async def rest_session(client: RestClient, token: str) -> AsyncIterator[RestClient]:
    """Authenticate `client` for REST calls and guarantee its HTTP session closes."""
    try:
        await client.login(token)
        yield client
    finally:
        if not client.is_closed():
            await client.close()


@asynccontextmanager
async def bot_session(client: ManagementClient, token: str) -> AsyncIterator[ManagementClient]:
    """Connect the client, let it run its action to completion, and guarantee it closes."""
    try:
        await client.start(token)
        yield client
    finally:
        if not client.is_closed():
            await client.close()


def fallback_intents() -> discord.Intents:
    intents = discord.Intents.default()
    intents.guilds = True
    intents.reactions = True
    return intents


def _should_use_gateway(use_gateway: bool | None) -> bool:
    if use_gateway is not None:
        return use_gateway
    env_transport = os.environ.get("DISCORD_CLI_TRANSPORT", "").strip().lower()
    if env_transport == "gateway":
        return True
    env_flag = os.environ.get("DISCORD_CLI_GATEWAY", "").strip().lower()
    return env_flag in {"1", "true", "yes", "on"}


async def _run_rest_async(
    action: Action, kwargs: dict[str, Any], token: str
) -> tuple[Any, dict[str, Any] | None]:
    client = RestClient()
    try:
        async with rest_session(client, token) as session:
            try:
                result = await action(session, **kwargs)
                return result, None
            except Exception as exc:  # noqa: BLE001 - user-facing CLI boundary
                return None, _format_exception(exc)
    except Exception as exc:  # noqa: BLE001 - user-facing CLI boundary
        return None, _format_exception(exc)


async def _run_gateway_async(
    action: Action, kwargs: dict[str, Any], token: str
) -> tuple[Any, dict[str, Any] | None]:
    last_error: dict[str, Any] | None = None
    for intents in (discord.Intents.all(), fallback_intents()):
        client = ManagementClient(action, kwargs, intents)
        try:
            async with bot_session(client, token) as session:
                result, error = session.result, session.error
        except discord.PrivilegedIntentsRequired as exc:
            last_error = _format_exception(exc)
            continue
        except Exception as exc:  # noqa: BLE001 - user-facing CLI boundary
            return None, _format_exception(exc)
        if last_error and error is None:
            warning_msg = (
                "Retried with non-privileged intents because privileged intents are not enabled "
                "for this bot."
            )
            if isinstance(result, dict):
                result.setdefault("warning", warning_msg)
            else:
                print(f"Warning: {warning_msg}", file=sys.stderr)
        return result, error
    return None, last_error


async def _run_async(
    action: Action,
    kwargs: dict[str, Any],
    token: str,
    *,
    use_gateway: bool | None = None,
) -> tuple[Any, dict[str, Any] | None]:
    if _should_use_gateway(use_gateway):
        return await _run_gateway_async(action, kwargs, token)
    return await _run_rest_async(action, kwargs, token)


def run_bot(
    action: Action,
    kwargs: dict[str, Any],
    token: str,
    *,
    use_gateway: bool | None = None,
) -> tuple[Any, dict[str, Any] | None]:
    """Run `action` against Discord (REST-first by default) and return (result, error)."""
    return asyncio.run(_run_async(action, kwargs, token, use_gateway=use_gateway))


def _emit_and_exit(
    result: Any,
    error: dict[str, Any] | None,
    human: bool,
    output_options: OutputOptions | None = None,
) -> None:
    payload = make_payload(result, error)
    print_output(payload, human, options=output_options)
    raise SystemExit(0 if payload["ok"] else 1)


def run_action(
    action: Action,
    kwargs: dict[str, Any],
    human: bool,
    token: str | None = None,
    *,
    use_gateway: bool | None = None,
    output_options: OutputOptions | None = None,
) -> None:
    """Load config, run the action against Discord, print the payload, and exit with its status."""
    try:
        bot_token = load_config(token).bot_token
    except DiscordCliError as exc:
        _emit_and_exit(
            None,
            {"type": exc.__class__.__name__, "message": str(exc)},
            human,
            output_options=output_options,
        )

    if use_gateway is None:
        result, error = run_bot(action, kwargs, bot_token)
    else:
        result, error = run_bot(action, kwargs, bot_token, use_gateway=use_gateway)
    _emit_and_exit(result, error, human, output_options=output_options)


def run_http_action(
    action: HttpAction,
    kwargs: dict[str, Any],
    human: bool = False,
    *,
    output_options: OutputOptions | None = None,
) -> None:
    """Run a zero-gateway, bot-token-free HTTP action (e.g. webhook execution) and exit."""

    async def _runner() -> tuple[Any, dict[str, Any] | None]:
        try:
            return await action(**kwargs), None
        except Exception as exc:  # noqa: BLE001 - user-facing CLI boundary
            return None, _format_exception(exc)

    result, error = asyncio.run(_runner())
    _emit_and_exit(result, error, human, output_options=output_options)
