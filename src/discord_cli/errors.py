"""Custom exceptions for discord-cli."""


class DiscordCliError(Exception):
    """Base class for expected CLI/runtime errors with a clean message."""


class ConfigError(DiscordCliError):
    """Raised when configuration (e.g. bot token) cannot be loaded."""


class ApiError(DiscordCliError):
    """Raised when a Discord API call fails."""


class CliError(DiscordCliError):
    """Raised inside a command action when the request cannot be completed."""
