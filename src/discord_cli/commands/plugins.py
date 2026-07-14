"""Plugin commands: inspect third-party command extensions loaded via entry points."""

from __future__ import annotations

import click

from discord_cli.output import make_payload, print_output
from discord_cli.plugins import loaded_plugins
from discord_cli.registry import registry


@registry.group("plugins")
def plugins_group() -> None:
    """Inspect third-party plugins discovered via the discord_cli.plugins entry-point group."""


@plugins_group.command("list")
@click.pass_context
def plugins_list(ctx: click.Context) -> None:
    human = (ctx.obj or {}).get("human", False)
    plugins = [
        {"name": plugin.name, "version": plugin.version, "module": plugin.module}
        for plugin in loaded_plugins()
    ]
    print_output(make_payload({"plugins": plugins}), human)
