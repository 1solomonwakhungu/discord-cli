"""Configuration loading for discord-cli."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from discord_cli.errors import ConfigError


@dataclass
class Config:
    bot_token: str


def load_config() -> Config:
    """Load configuration from environment variables and a local .env file."""
    load_dotenv()

    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        raise ConfigError("DISCORD_BOT_TOKEN not found in environment or .env")

    return Config(bot_token=token.strip())
