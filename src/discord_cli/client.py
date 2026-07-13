"""Discord client used to run one-off management actions."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

import discord

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
