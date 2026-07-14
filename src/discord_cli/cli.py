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
def main() -> None:
    """Command-line tool for managing Discord servers and automating Discord via AI agents."""


# Attach command groups registered by imported command modules.
registry.attach_all(main)

# Discover and attach third-party plugin command groups.
load_plugins(registry, main)


if __name__ == "__main__":
    main()
