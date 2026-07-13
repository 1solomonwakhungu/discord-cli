"""Command-line entry point for discord-cli."""

from __future__ import annotations

import click

from discord_cli import __version__


@click.group()
@click.version_option(version=__version__, prog_name="discord-cli")
def main() -> None:
    """Command-line tool for managing Discord servers and automating Discord via AI agents."""


if __name__ == "__main__":
    main()
