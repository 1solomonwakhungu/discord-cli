"""Command-line entry point for discord-cli."""

from __future__ import annotations

import click

from discord_cli import __version__

# Import all command modules to register them
from discord_cli.commands import (
    categories,
    channels,
    export,
    guilds,
    invites,
    members,
    messages,
    permissions,
    roles,
    search,
    threads,
    webhooks,
)


@click.group()
@click.version_option(version=__version__, prog_name="discord-cli")
def main() -> None:
    """Command-line tool for managing Discord servers and automating Discord via AI agents."""


# Register all command groups
main.add_command(channels.channel)
main.add_command(categories.category)
main.add_command(roles.role)
main.add_command(members.member)
main.add_command(messages.message)
main.add_command(guilds.guild)
main.add_command(permissions.permissions)
main.add_command(webhooks.webhook)
main.add_command(invites.invites)
main.add_command(threads.threads)
main.add_command(search.search)
main.add_command(export.export)


if __name__ == "__main__":
    main()
