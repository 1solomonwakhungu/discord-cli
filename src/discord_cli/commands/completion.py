"""Shell completion script generator (`discord-cli completion generate`)."""

from __future__ import annotations

import click
from click.shell_completion import get_completion_class

from discord_cli.errors import (
    CliError,
    DiscordCliError,
    classify_exception,
    resolve_process_exit_code,
    semantic_exit_codes_enabled,
)
from discord_cli.output import make_payload, print_output
from discord_cli.policy import enforce_group_allowlist, redact_secrets_in_text
from discord_cli.registry import build_output_options, registry

_SHELLS = ("bash", "zsh", "fish")


@registry.group("completion")
def completion_group() -> None:
    """Generate shell completion scripts for bash, zsh, or fish."""


@completion_group.command("generate")
@click.argument("shell", type=click.Choice(_SHELLS, case_sensitive=False))
@click.pass_context
def completion_generate(ctx: click.Context, shell: str) -> None:
    """Output a shell completion script for bash, zsh, or fish."""
    try:
        enforce_group_allowlist("completion generate")
    except DiscordCliError as exc:
        obj = ctx.obj or {}
        err = classify_exception(exc, message_sanitizer=redact_secrets_in_text)
        print_output(
            make_payload(error=err),
            bool(obj.get("human", False)),
            options=build_output_options(ctx),
        )
        raise SystemExit(
            resolve_process_exit_code(
                err,
                semantic=semantic_exit_codes_enabled(bool(obj.get("semantic_exit_codes", False))),
            )
        ) from None
    shell_name = shell.lower()
    comp_cls = get_completion_class(shell_name)
    if comp_cls is None:
        raise CliError(f"Unsupported shell: {shell}")
    root = ctx.find_root().command
    comp = comp_cls(root, {}, "discord-cli", "_DISCORD_CLI_COMPLETE")
    click.echo(comp.source(), nl=False)
