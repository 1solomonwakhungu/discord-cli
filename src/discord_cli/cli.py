"""Command-line entry point for discord-cli."""

from __future__ import annotations

import click

from discord_cli import __version__
from discord_cli.commands import (
    categories,  # noqa: F401 - imports register command groups
    channels,  # noqa: F401 - imports register command groups
    export,  # noqa: F401 - imports register command groups
    guilds,  # noqa: F401 - imports register command groups
    invites,  # noqa: F401 - imports register command groups
    members,  # noqa: F401 - imports register command groups
    messages,  # noqa: F401 - imports register command groups
    permissions,  # noqa: F401 - imports register command groups
    plugins,  # noqa: F401 - imports register command groups
    roles,  # noqa: F401 - imports register command groups
    search,  # noqa: F401 - imports register command groups
    threads,  # noqa: F401 - imports register command groups
    webhooks,  # noqa: F401 - imports register command groups
)
from discord_cli.plugins import load_plugins
from discord_cli.registry import registry


@click.group()
@click.version_option(version=__version__, prog_name="discord-cli")
@click.option(
    "--token",
    default=None,
    envvar="DISCORD_BOT_TOKEN",
    help="Discord bot token. Overrides DISCORD_BOT_TOKEN and .env.",
)
@click.option(
    "--guild",
    "guild_id",
    type=int,
    default=None,
    envvar="DISCORD_GUILD_ID",
    help="Target guild ID. Required when the bot is in more than one guild.",
)
@click.option(
    "--human",
    is_flag=True,
    default=False,
    help="Render human-readable tables instead of the default JSON output.",
)
@click.pass_context
def main(ctx: click.Context, token: str | None, guild_id: int | None, human: bool) -> None:
    """Command-line tool for managing Discord servers and automating Discord via AI agents."""
    ctx.ensure_object(dict)
    ctx.obj.update({"token": token, "guild_id": guild_id, "human": human})


# Attach command groups registered by imported command modules.
registry.attach_all(main)

# Discover and attach third-party plugin command groups.
load_plugins(registry, main)


if __name__ == "__main__":
    main()
