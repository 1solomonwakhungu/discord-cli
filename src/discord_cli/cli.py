"""Command-line entry point for discord-cli."""

from __future__ import annotations

import sys
from typing import Any

import click

from discord_cli import __version__
from discord_cli.commands import (
    api,  # noqa: F401 - imports register command groups
    audit,  # noqa: F401 - imports register command groups
    auth,  # noqa: F401 - imports register command groups
    categories,  # noqa: F401 - imports register command groups
    channels,  # noqa: F401 - imports register command groups
    completion,  # noqa: F401 - imports register command groups
    config_cmd,  # noqa: F401 - imports register command groups
    describe,  # noqa: F401 - imports register command groups
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
from discord_cli.errors import EXIT_USAGE
from discord_cli.output import MIN_MAX_CHARS, make_payload, print_json
from discord_cli.plugins import load_plugins, plugins_disabled_by_env
from discord_cli.policy import POLICY_LEVELS, redact_secrets_in_text
from discord_cli.registry import OUTPUT_FORMATS, registry
from discord_cli.resolvers import RESOURCE_ID


def _argv_before_dashdash(argv: list[str]) -> list[str]:
    try:
        return argv[: argv.index("--")]
    except ValueError:
        return argv


def _extract_token_args(argv: list[str]) -> list[str]:
    tokens: list[str] = []
    for idx, arg in enumerate(argv):
        if arg == "--token" and idx + 1 < len(argv):
            tokens.append(argv[idx + 1])
        elif arg.startswith("--token="):
            tokens.append(arg.split("=", 1)[1])
    return tokens


class AliasedGroup(click.Group):
    """Click group that resolves shorthand aliases, lazy plugins, and JSON UsageErrors."""

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

    def main(  # type: ignore[override]
        self,
        args: list[str] | None = None,
        prog_name: str | None = None,
        complete_var: str | None = None,
        standalone_mode: bool = True,
        **extra: Any,
    ) -> Any:
        import os

        argv = list(sys.argv[1:]) if args is None else list(args)
        flag_region = _argv_before_dashdash(argv)
        if not standalone_mode or "--human" in flag_region:
            return super().main(
                args=argv,
                prog_name=prog_name,
                complete_var=complete_var,
                standalone_mode=standalone_mode,
                **extra,
            )
        try:
            return super().main(
                args=argv,
                prog_name=prog_name,
                complete_var=complete_var,
                standalone_mode=False,
                **extra,
            )
        except click.ClickException as exc:
            if isinstance(exc, click.UsageError):
                cmd_hint = (
                    f"{exc.ctx.command_path} --help"
                    if exc.ctx is not None
                    else "discord-cli describe list --compact"
                )
                safe_msg = redact_secrets_in_text(
                    exc.format_message(),
                    extra_secrets=_extract_token_args(argv),
                )
                env_compact = os.environ.get("DISCORD_CLI_COMPACT", "").strip().lower() in {
                    "1",
                    "true",
                    "yes",
                    "on",
                }
                error = {
                    "type": exc.__class__.__name__,
                    "code": "USAGE_ERROR",
                    "category": "USAGE_ERROR",
                    "exit_code": EXIT_USAGE,
                    "retryable": False,
                    "message": safe_msg,
                    "recovery_hint": f"Inspect command usage with `{cmd_hint}`.",
                    "suggested_command": cmd_hint,
                }
                print_json(
                    make_payload(error=error),
                    compact=("--compact" in flag_region or env_compact),
                )
                sys.exit(EXIT_USAGE)
            exc.show()
            sys.exit(exc.exit_code)
        except click.Abort:
            click.echo("Aborted!", file=sys.stderr)
            sys.exit(1)


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
    type=RESOURCE_ID,
    default=None,
    envvar="DISCORD_GUILD_ID",
    help="Target guild ID or config alias. Required when the bot is in more than one guild.",
)
@click.option(
    "--profile",
    default=None,
    envvar="DISCORD_PROFILE",
    help="Configuration profile name from config.toml.",
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
@click.option(
    "--policy",
    type=click.Choice(POLICY_LEVELS, case_sensitive=False),
    default=None,
    help="Safety policy ceiling: read-only, allow-write, or allow-destructive.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Preview a mutating command and return a confirm_token without modifying Discord.",
)
@click.option(
    "--yes",
    is_flag=True,
    default=False,
    help="Confirm a destructive command when DISCORD_CLI_REQUIRE_CONFIRM=1 is active.",
)
@click.option(
    "--confirm-token",
    default=None,
    help="Confirmation token obtained from --dry-run for destructive commands.",
)
@click.option(
    "--max-mutations",
    type=click.IntRange(min=1),
    default=None,
    help="Maximum bulk mutations allowed (e.g. for message purge).",
)
@click.option(
    "--reason",
    default=None,
    envvar="DISCORD_CLI_REASON",
    help="Default Discord audit log reason for mutating commands.",
)
@click.option(
    "--untrusted-envelope",
    is_flag=True,
    default=False,
    envvar="DISCORD_CLI_UNTRUSTED_ENVELOPE",
    help="Wrap untrusted Discord text fields in a random-nonce XML boundary for prompt-injection defense.",
)
@click.option(
    "--redact-pii",
    is_flag=True,
    default=False,
    envvar="DISCORD_CLI_REDACT_PII",
    help="Redact emails, tokens, API keys, JWTs, and webhook secrets from output.",
)
@click.option(
    "--semantic-exit-codes",
    is_flag=True,
    default=False,
    envvar="DISCORD_CLI_SEMANTIC_EXIT_CODES",
    help="Return semantic exit codes (3=auth, 4=not found, 5=permission, 6=policy, 7=rate limit).",
)
@click.pass_context
def main(
    ctx: click.Context,
    token: str | None,
    guild_id: int | str | None,
    profile: str | None,
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
    policy: str | None,
    dry_run: bool,
    yes: bool,
    confirm_token: str | None,
    max_mutations: int | None,
    reason: str | None,
    untrusted_envelope: bool,
    redact_pii: bool,
    semantic_exit_codes: bool,
) -> None:
    """Command-line tool for managing Discord servers and automating Discord via AI agents."""
    ctx.ensure_object(dict)
    ctx.obj.update(
        {
            "token": token,
            "guild_id": guild_id,
            "profile": profile,
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
            "policy": policy,
            "dry_run": dry_run,
            "yes": yes,
            "confirm_token": confirm_token,
            "max_mutations": max_mutations,
            "reason": reason,
            "untrusted_envelope": untrusted_envelope,
            "redact_pii": redact_pii,
            "semantic_exit_codes": semantic_exit_codes,
        }
    )


# Attach built-in command groups and lock their names + aliases against plugin shadowing.
registry.attach_all(main)
registry.lock_builtins(extra_protected=AliasedGroup.ALIASES.keys())


if __name__ == "__main__":
    main()
