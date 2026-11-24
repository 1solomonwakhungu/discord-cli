"""Shell completion script generator (`discord-cli completion generate`)."""

from __future__ import annotations

import click
from click.shell_completion import get_completion_class

from discord_cli.errors import CliError
from discord_cli.registry import registry

_SHELLS = ("bash", "zsh", "fish")


@registry.group("completion")
def completion_group() -> None:
    """Generate shell completion scripts for bash, zsh, or fish."""


@completion_group.command("generate")
@click.argument("shell", type=click.Choice(_SHELLS, case_sensitive=False))
@click.pass_context
def completion_generate(ctx: click.Context, shell: str) -> None:
    """Output a shell completion script for bash, zsh, or fish."""
    shell_name = shell.lower()
    comp_cls = get_completion_class(shell_name)
    if comp_cls is None:
        raise CliError(f"Unsupported shell: {shell}")
    root = ctx.find_root().command
    comp = comp_cls(root, {}, "discord-cli", "_DISCORD_CLI_COMPLETE")
    click.echo(comp.source(), nl=False)
