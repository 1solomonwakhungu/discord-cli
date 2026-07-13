"""Registry that lets each command module self-register a Click command group with the CLI."""

from __future__ import annotations

from typing import Any, Callable

import click

from discord_cli.client import Action, run_action
from discord_cli.errors import DiscordCliError
from discord_cli.models import bool_value


class TriStateBoolParamType(click.ParamType):
    """A bool option that is None when omitted, distinguishing "not set" from "false"."""

    name = "bool"

    def convert(self, value: Any, param: Any, ctx: Any) -> bool | None:
        if value is None or isinstance(value, bool):
            return value
        try:
            return bool_value(value)
        except DiscordCliError as exc:
            self.fail(str(exc), param, ctx)


TRI_STATE_BOOL = TriStateBoolParamType()


class CommandRegistry:
    """Collects Click command groups defined by command modules for attachment to the root CLI."""

    def __init__(self) -> None:
        self._groups: dict[str, click.Group] = {}

    def group(self, name: str, **kwargs: Any) -> Callable[[Callable[..., Any]], click.Group]:
        """Decorator that defines a new top-level command group and registers it by name."""

        def decorator(func: Callable[..., Any]) -> click.Group:
            command_group = click.group(name=name, **kwargs)(func)
            self._groups[name] = command_group
            return command_group

        return decorator

    def attach_all(self, root: click.Group) -> None:
        """Attach every registered group to the root CLI group."""
        for command_group in self._groups.values():
            root.add_command(command_group)


registry = CommandRegistry()


def invoke(ctx: click.Context, action: Action, **kwargs: Any) -> None:
    """Merge the root --guild/--human/--token options with command kwargs and run the action."""
    obj = ctx.obj or {}
    merged = {"guild_id": obj.get("guild_id"), **kwargs}
    run_action(action, merged, human=obj.get("human", False), token=obj.get("token"))
