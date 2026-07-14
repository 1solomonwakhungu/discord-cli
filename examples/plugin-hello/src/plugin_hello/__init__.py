"""Example discord-cli plugin: registers a `hello` command group with a `world` subcommand."""

from __future__ import annotations

import click

from discord_cli.output import make_payload, print_output
from discord_cli.registry import CommandRegistry

__version__ = "0.1.0"


def register(registry: CommandRegistry) -> None:
    """Entry point called by discord-cli's plugin loader; registers this plugin's commands."""

    @registry.group("hello")
    def hello_group() -> None:
        """Example plugin command group."""

    @hello_group.command("world")
    @click.pass_context
    def hello_world(ctx: click.Context) -> None:
        human = (ctx.obj or {}).get("human", False)
        print_output(make_payload({"message": "Hello from plugin!"}), human)
