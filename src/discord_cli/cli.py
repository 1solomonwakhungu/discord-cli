"""Command-line entry point for discord-cli."""

from __future__ import annotations

import click

from discord_cli import __version__
from discord_cli.commands import (
    api,  # noqa: F401 - imports register command groups
    audit,  # noqa: F401 - imports register command groups
    categories,  # noqa: F401 - imports register command groups
    channels,  # noqa: F401 - imports register command groups
    doctor,  # noqa: F401 - imports register command groups
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
from discord_cli.output import MIN_MAX_CHARS
from discord_cli.plugins import load_plugins, plugins_disabled_by_env
from discord_cli.registry import OUTPUT_FORMATS, registry


class AliasedGroup(click.Group):
    """Click group that resolves shorthand aliases and loads plugins lazily on demand."""

    ALIASES: dict[str, str] = {
        "invite": "invites",
        "thread": "threads",
        "permission": "permissions",
        "plugin": "plugins",
    }

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._plugins_loaded = False

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        # Detect --no-plugins BEFORE Click runs eager --help / list_commands callbacks.
        if "--no-plugins" in args:
            ctx.ensure_object(dict)
            ctx.obj["no_plugins"] = True
        return super().parse_args(ctx, args)

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
@click.option(
    "--compact",
    is_flag=True,
    default=False,
    envvar="DISCORD_CLI_COMPACT",
    help="Emit minified single-line JSON without whitespace.",
)
@click.option(
    "--fields",
    default=None,
    help="Comma-separated dot-paths to project from output data (e.g. id,name,author.name).",
)
@click.option(
    "--max-chars",
    type=click.IntRange(min=MIN_MAX_CHARS),
    default=None,
    envvar="DISCORD_CLI_MAX_CHARS",
    help=f"Truncate JSON output cleanly within N characters (min {MIN_MAX_CHARS}) while staying valid JSON.",
)
@click.option(
    "--string-ids",
    is_flag=True,
    default=False,
    envvar="DISCORD_CLI_STRING_IDS",
    help="Serialize Discord 64-bit snowflake IDs as strings for JS/TS safety.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(OUTPUT_FORMATS, case_sensitive=False),
    default=None,
    help="Output format: json, jsonl, csv, table, markdown, or raw.",
)
@click.option(
    "--quiet",
    is_flag=True,
    default=False,
    help="Print only primary resource IDs (one per line).",
)
@click.option(
    "--output",
    "output_path",
    default=None,
    help="Write formatted output atomically to a file path.",
)
@click.pass_context
def main(
    ctx: click.Context,
    token: str | None,
    guild_id: int | None,
    human: bool,
    gateway: bool,
    no_plugins: bool,
    compact: bool,
    fields: str | None,
    max_chars: int | None,
    string_ids: bool,
    output_format: str | None,
    quiet: bool,
    output_path: str | None,
) -> None:
    """Command-line tool for managing Discord servers and automating Discord via AI agents."""
    ctx.ensure_object(dict)
    ctx.obj.update(
        {
            "token": token,
            "guild_id": guild_id,
            "human": human,
            "gateway": gateway,
            "no_plugins": no_plugins or bool(ctx.obj.get("no_plugins", False)),
            "compact": compact,
            "fields": fields,
            "max_chars": max_chars,
            "string_ids": string_ids,
            "format": output_format,
            "quiet": quiet,
            "output_path": output_path,
        }
    )


# Attach built-in command groups and lock their names + aliases against plugin shadowing.
registry.attach_all(main)
registry.lock_builtins(extra_protected=AliasedGroup.ALIASES.keys())


if __name__ == "__main__":
    main()
