"""Custom exceptions, semantic exit codes, and self-healing error classification."""

from __future__ import annotations

import os
from typing import Any

import discord

# Semantic exit codes (opt-in via --semantic-exit-codes / DISCORD_CLI_SEMANTIC_EXIT_CODES=1,
# except EXIT_USAGE=2 for Click usage errors and EXIT_POLICY=6 for explicit policy denials).
EXIT_OK = 0
EXIT_RUNTIME = 1
EXIT_USAGE = 2
EXIT_AUTH_CONFIG = 3
EXIT_NOT_FOUND = 4
EXIT_PERMISSION = 5
EXIT_POLICY = 6
EXIT_RATE_LIMIT = 7


class DiscordCliError(Exception):
    """Base class for expected CLI/runtime errors with structured recovery metadata."""

    default_code: str = "RUNTIME_ERROR"
    default_exit_code: int = EXIT_RUNTIME
    default_retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        exit_code: int | None = None,
        retryable: bool | None = None,
        retry_after_seconds: float | None = None,
        recovery_hint: str | None = None,
        suggested_command: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code or self.default_code
        self.exit_code = self.default_exit_code if exit_code is None else exit_code
        self.retryable = self.default_retryable if retryable is None else retryable
        self.retry_after_seconds = retry_after_seconds
        self.recovery_hint = recovery_hint
        self.suggested_command = suggested_command
        self.details = details


class ConfigError(DiscordCliError):
    """Raised when configuration (e.g. bot token or profile) cannot be loaded."""

    default_code = "AUTH_OR_CONFIG"
    default_exit_code = EXIT_AUTH_CONFIG


class ApiError(DiscordCliError):
    """Raised when a Discord API call fails."""

    default_code = "RUNTIME_ERROR"
    default_exit_code = EXIT_RUNTIME


class CliError(DiscordCliError):
    """Raised inside a command action when the request cannot be completed."""

    default_code = "RUNTIME_ERROR"
    default_exit_code = EXIT_RUNTIME


class NotFoundError(CliError):
    """Raised when a requested guild, channel, role, member, or message is not found."""

    default_code = "NOT_FOUND"
    default_exit_code = EXIT_NOT_FOUND


class AmbiguousSelectorError(NotFoundError):
    """Raised when a human resource selector matches multiple Discord resources."""

    default_code = "AMBIGUOUS_SELECTOR"
    default_exit_code = EXIT_NOT_FOUND

    def __init__(
        self,
        message: str,
        *,
        candidates: list[dict[str, Any]],
        recovery_hint: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code="AMBIGUOUS_SELECTOR",
            exit_code=EXIT_NOT_FOUND,
            recovery_hint=recovery_hint
            or "Re-run using an explicit numeric snowflake ID from error.details.candidates.",
            details={"candidates": candidates},
        )
        self.candidates = candidates


class PermissionDeniedError(CliError):
    """Raised when the bot lacks Discord permissions or privileged intents."""

    default_code = "PERMISSION_DENIED"
    default_exit_code = EXIT_PERMISSION


class PolicyDeniedError(CliError):
    """Raised when a local safety policy blocks a command before any Discord API call."""

    default_code = "POLICY_DENIED"
    default_exit_code = EXIT_POLICY


class RateLimitError(ApiError):
    """Raised when Discord rate limits a request (HTTP 429)."""

    default_code = "RATE_LIMITED"
    default_exit_code = EXIT_RATE_LIMIT
    default_retryable = True


def semantic_exit_codes_enabled(cli_flag: bool = False) -> bool:
    """Return True when semantic exit codes (3-7) should be returned directly by process exit."""
    if cli_flag:
        return True
    env_val = os.environ.get("DISCORD_CLI_SEMANTIC_EXIT_CODES", "").strip().lower()
    return env_val in {"1", "true", "yes", "on"}


def resolve_process_exit_code(error: dict[str, Any] | None, *, semantic: bool = False) -> int:
    """Compute the process exit code from a formatted error payload.

    Preserves v1.x exit code 1 by default except for:
    - Click usage errors (2)
    - Explicit local policy denials (6)
    - Any error when `--semantic-exit-codes` / `DISCORD_CLI_SEMANTIC_EXIT_CODES=1` is active.
    """
    if not error:
        return EXIT_OK
    category = error.get("category")
    raw_code = error.get("exit_code")
    if category == "POLICY_DENIED":
        return EXIT_POLICY
    if category == "USAGE_ERROR":
        return EXIT_USAGE
    if semantic and isinstance(raw_code, int) and 1 <= raw_code <= 7:
        return raw_code
    return EXIT_RUNTIME


def classify_exception(exc: Exception, *, message_sanitizer: Any = None) -> dict[str, Any]:
    """Convert any exception into a structured, agent-friendly error dictionary."""
    raw_message = str(exc)
    message = str(message_sanitizer(raw_message)) if callable(message_sanitizer) else raw_message

    error: dict[str, Any] = {
        "type": exc.__class__.__name__,
        "message": message,
        "category": "RUNTIME_ERROR",
        "exit_code": EXIT_RUNTIME,
        "retryable": False,
    }

    if isinstance(exc, DiscordCliError):
        error["category"] = exc.code
        error["code"] = exc.code
        error["exit_code"] = exc.exit_code
        error["retryable"] = exc.retryable
        if exc.retry_after_seconds is not None:
            error["retry_after_seconds"] = exc.retry_after_seconds
        if exc.recovery_hint:
            error["recovery_hint"] = exc.recovery_hint
        elif isinstance(exc, ConfigError):
            error["recovery_hint"] = (
                "Set DISCORD_BOT_TOKEN, pass --token, or run `discord-cli auth login`."
            )
            error["suggested_command"] = "discord-cli doctor"
        if exc.suggested_command:
            error["suggested_command"] = exc.suggested_command
        if exc.details:
            error["details"] = exc.details
        # Infer NOT_FOUND / AUTH_OR_CONFIG for legacy CliError messages when not explicitly typed
        if type(exc) is CliError:
            lowered = raw_message.lower()
            if "not found" in lowered:
                error["category"] = "NOT_FOUND"
                error["exit_code"] = EXIT_NOT_FOUND
            elif "multiple guilds" in lowered or "not in any guilds" in lowered:
                error["category"] = "AUTH_OR_CONFIG"
                error["exit_code"] = EXIT_AUTH_CONFIG
                error.setdefault(
                    "recovery_hint",
                    "Specify --guild <id> or set DISCORD_GUILD_ID (or configure a default guild in config.toml).",
                )
        return error

    if isinstance(exc, discord.PrivilegedIntentsRequired):
        error.update(
            {
                "category": "PERMISSION_DENIED",
                "exit_code": EXIT_PERMISSION,
                "recovery_hint": (
                    "Enable the required Privileged Gateway Intents in the Discord Developer Portal "
                    "or run without --gateway (REST-first mode)."
                ),
                "suggested_command": "discord-cli doctor",
            }
        )
        return error

    if isinstance(exc, discord.LoginFailure):
        error.update(
            {
                "category": "AUTH_OR_CONFIG",
                "exit_code": EXIT_AUTH_CONFIG,
                "recovery_hint": "Verify DISCORD_BOT_TOKEN is valid and not revoked.",
                "suggested_command": "discord-cli doctor",
            }
        )
        return error

    if isinstance(exc, discord.HTTPException):
        status = getattr(exc, "status", None)
        discord_code = getattr(exc, "code", None)
        error.update({"status": status, "code": discord_code})
        if status == 401:
            error.update(
                {
                    "category": "AUTH_OR_CONFIG",
                    "exit_code": EXIT_AUTH_CONFIG,
                    "recovery_hint": "Verify your Discord bot token is valid.",
                    "suggested_command": "discord-cli doctor",
                }
            )
        elif status == 403 or isinstance(exc, discord.Forbidden):
            error.update(
                {
                    "category": "PERMISSION_DENIED",
                    "exit_code": EXIT_PERMISSION,
                    "recovery_hint": (
                        "Check bot role hierarchy and channel permission overwrites."
                    ),
                    "suggested_command": "discord-cli doctor",
                }
            )
        elif status == 404 or isinstance(exc, discord.NotFound):
            error.update(
                {
                    "category": "NOT_FOUND",
                    "exit_code": EXIT_NOT_FOUND,
                    "recovery_hint": (
                        "Verify the target resource ID exists in the selected guild."
                    ),
                }
            )
        elif status == 429:
            retry_after = getattr(exc, "retry_after", None)
            error.update(
                {
                    "category": "RATE_LIMITED",
                    "exit_code": EXIT_RATE_LIMIT,
                    "retryable": True,
                    "recovery_hint": "Back off and retry after Discord's rate-limit window.",
                }
            )
            if isinstance(retry_after, (int, float)):
                error["retry_after_seconds"] = float(retry_after)
        elif isinstance(status, int) and status >= 500:
            error.update(
                {
                    "category": "RATE_LIMITED",
                    "exit_code": EXIT_RATE_LIMIT,
                    "retryable": True,
                    "recovery_hint": "Discord returned a transient 5xx error; retry with exponential backoff.",
                }
            )
        return error

    return error
