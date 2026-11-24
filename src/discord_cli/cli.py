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
from discord_cli.plugins import load_plugins, plugins_disabled_by_env
from discord_cli.registry import registry


class AliasedGroup(click.Group):
    """Click group that resolves shorthand aliases and loads plugins lazily on execution."""

    ALIASES: dict[str, str] = {"invite": "invites"}

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._plugins_loaded = False

    def ensure_plugins_loaded(self, ctx: click.Context | None = None) -> None:
        if self._plugins_loaded:
            return
        if plugins_disabled_by_env():
            return
        if ctx is not None and (ctx.params.get("no_plugins") or (ctx.obj or {}).get("no_plugins")):
            return
        self._plugins_loaded = True
        load_plugins(registry, self)

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        resolved = self.ALIASES.get(cmd_name, cmd_name)
        cmd = super().get_command(ctx, resolved)
        if cmd is not None:
            return cmd
        self.ensure_plugins_loaded(ctx)
        return super().get_command(ctx, resolved)

    def list_commands(self, ctx: click.Context) -> list[str]:
        self.ensure_plugins_loaded(ctx)
        return super().list_commands(ctx)


@click.group(cls=AliasedGroup)
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
@click.option(
    "--gateway",
    is_flag=True,
    default=False,
    envvar="DISCORD_CLI_GATEWAY",
    help="Use a WebSocket Gateway connection instead of the faster REST-first default.",
)
@click.option(
    "--no-plugins",
    is_flag=True,
    default=False,
    envvar="DISCORD_CLI_NO_PLUGINS",
    help="Disable loading third-party discord_cli.plugins entry points.",
)
@click.pass_context
def main(
    ctx: click.Context,
    token: str | None,
    guild_id: int | None,
    human: bool,
    gateway: bool,
    no_plugins: bool,
) -> None:
    """Command-line tool for managing Discord servers and automating Discord via AI agents."""
    ctx.ensure_object(dict)
    ctx.obj.update(
        {
            "token": token,
            "guild_id": guild_id,
            "human": human,
            "gateway": gateway,
            "no_plugins": no_plugins,
        }
    )
    if not no_plugins and isinstance(ctx.command, AliasedGroup):
        ctx.command.ensure_plugins_loaded(ctx)


# Attach built-in command groups and lock their names against plugin shadowing.
registry.attach_all(main)
registry.lock_builtins()


if __name__ == "__main__":
    main()
