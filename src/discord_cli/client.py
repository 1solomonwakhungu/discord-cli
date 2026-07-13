"""Discord bot lifecycle: connect, run a single action, print the result, exit."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from typing import Any, Callable

import discord

from discord_cli.config import load_config
from discord_cli.errors import DiscordCliError
from discord_cli.output import make_payload, print_output

Action = Callable[..., Awaitable[Any]]


class ManagementClient(discord.Client):
    """A discord.Client that runs a single action on_ready and then closes."""

    def __init__(self, action: Action, kwargs: dict[str, Any], intents: discord.Intents):
        super().__init__(intents=intents)
        self.action = action
        self.kwargs = kwargs
        self.result: Any = None
        self.error: dict[str, Any] | None = None

    async def on_ready(self) -> None:
        try:
            self.result = await self.action(self, **self.kwargs)
        except Exception as exc:  # noqa: BLE001 - user-facing CLI boundary
            self.error = {"type": exc.__class__.__name__, "message": str(exc)}
            if isinstance(exc, discord.HTTPException):
                self.error.update({"status": exc.status, "code": exc.code})
        finally:
            await self.close()


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


async def _run_async(
    action: Action, kwargs: dict[str, Any], token: str
) -> tuple[Any, dict[str, Any] | None]:
    last_error: dict[str, Any] | None = None
    for intents in (discord.Intents.all(), fallback_intents()):
        client = ManagementClient(action, kwargs, intents)
        try:
            async with bot_session(client, token) as session:
                result, error = session.result, session.error
        except discord.PrivilegedIntentsRequired as exc:
            last_error = {"type": exc.__class__.__name__, "message": str(exc)}
            continue
        except Exception as exc:  # noqa: BLE001 - user-facing CLI boundary
            return None, {"type": exc.__class__.__name__, "message": str(exc)}
        if last_error and error is None and isinstance(result, dict):
            result.setdefault(
                "warning",
                "Retried with non-privileged intents because privileged intents are not enabled for this bot.",
            )
        return result, error
    return None, last_error


def run_bot(
    action: Action, kwargs: dict[str, Any], token: str
) -> tuple[Any, dict[str, Any] | None]:
    """Run `action` against a freshly connected bot and return (result, error)."""
    return asyncio.run(_run_async(action, kwargs, token))


def run_action(
    action: Action, kwargs: dict[str, Any], human: bool, token: str | None = None
) -> None:
    """Load config, run the action against the bot, print the payload, and exit with its status."""
    try:
        bot_token = load_config(token).bot_token
    except DiscordCliError as exc:
        payload = make_payload(error={"type": exc.__class__.__name__, "message": str(exc)})
        print_output(payload, human)
        raise SystemExit(1) from None

    result, error = run_bot(action, kwargs, bot_token)
    payload = make_payload(result, error)
    print_output(payload, human)
    raise SystemExit(0 if payload["ok"] else 1)
