"""Configuration loading for discord-cli."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from discord_cli.errors import ConfigError


@dataclass
class Config:
    bot_token: str


def load_config(token_override: str | None = None) -> Config:
    """Load configuration, preferring --token, then the environment, then a local .env file."""
    if token_override:
        return Config(bot_token=token_override.strip())

    load_dotenv()

    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        raise ConfigError("DISCORD_BOT_TOKEN not found in environment, .env, or --token")

    return Config(bot_token=token.strip())
