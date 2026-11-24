"""Configuration file inspection and editing commands (`discord-cli config`)."""

from __future__ import annotations

from typing import Any

import click

from discord_cli.config import (
    get_config_path,
    get_project_config_path,
    load_merged_toml,
    save_user_config,
)
from discord_cli.errors import (
    CliError,
    DiscordCliError,
    NotFoundError,
    classify_exception,
    resolve_process_exit_code,
    semantic_exit_codes_enabled,
)
from discord_cli.output import make_payload, print_output
from discord_cli.policy import evaluate_policy, resolve_policy_config
from discord_cli.registry import build_output_options, registry

_FORBIDDEN_CONFIG_KEYS = frozenset({"token", "bot_token"})


def _emit(ctx: click.Context, data: Any) -> None:
    obj = ctx.obj or {}
    print_output(
        make_payload(data),
        bool(obj.get("human", False)),
        options=build_output_options(ctx),
    )


def _emit_error(ctx: click.Context, exc: Exception) -> None:
    obj = ctx.obj or {}
    err = classify_exception(exc)
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
    )


def _coerce_value(raw: str) -> Any:
    lowered = raw.strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if raw.strip().isdigit():
        return int(raw.strip())
    return raw


@registry.group("config")
def config_group() -> None:
    """Inspect and manage discord-cli TOML configuration and guild aliases."""


@config_group.command("path")
@click.pass_context
def config_path(ctx: click.Context) -> None:
    """Print user and project-local configuration file paths."""
    user_path = get_config_path()
    proj_path = get_project_config_path()
    _emit(
        ctx,
        {
            "user_config": str(user_path),
            "user_config_exists": user_path.exists(),
            "project_config": str(proj_path),
            "project_config_exists": proj_path.exists(),
        },
    )


@config_group.command("list")
@click.pass_context
def config_list(ctx: click.Context) -> None:
    """Display the merged non-secret configuration."""
    try:
        _emit(ctx, load_merged_toml())
    except DiscordCliError as exc:
        _emit_error(ctx, exc)


@config_group.command("get")
@click.argument("key")
@click.pass_context
def config_get(ctx: click.Context, key: str) -> None:
    """Read a dot-separated key from the merged configuration."""
    try:
        data: Any = load_merged_toml()
        for part in key.split("."):
            if isinstance(data, dict) and part in data:
                data = data[part]
            else:
                raise NotFoundError(f"Configuration key not found: {key}")
        _emit(ctx, {"key": key, "value": data})
    except DiscordCliError as exc:
        _emit_error(ctx, exc)


@config_group.command("set")
@click.argument("key")
@click.argument("value")
@click.pass_context
def config_set(ctx: click.Context, key: str, value: str) -> None:
    """Set a dot-separated non-secret key in user config.toml (e.g. guilds.prod 123456)."""
    try:
        obj = ctx.obj or {}
        parts = [p.strip() for p in key.split(".") if p.strip()]
        if not parts:
            raise CliError("Configuration key cannot be empty.")
        if any(p.lower() in _FORBIDDEN_CONFIG_KEYS for p in parts):
            raise CliError(
                "Do not store bot tokens in config.toml. Use DISCORD_BOT_TOKEN or `discord-cli auth login`."
            )

        policy_cfg = resolve_policy_config(
            cli_policy=obj.get("policy"),
            cli_max_mutations=obj.get("max_mutations"),
        )
        dry_run_plan = evaluate_policy(
            "config set",
            None,
            {"key": key, "value": value},
            policy_cfg,
            dry_run=bool(obj.get("dry_run", False)),
            yes=bool(obj.get("yes", False)),
            confirm_token=obj.get("confirm_token"),
        )
        if dry_run_plan is not None:
            _emit(ctx, dry_run_plan)
            return

        cfg_path = get_config_path()
        user_data = load_merged_toml() if cfg_path.exists() else {}
        cursor: dict[str, Any] = user_data
        for segment in parts[:-1]:
            if segment not in cursor or not isinstance(cursor[segment], dict):
                cursor[segment] = {}
            cursor = cursor[segment]
        parsed_val = _coerce_value(value)
        cursor[parts[-1]] = parsed_val
        saved = save_user_config(user_data, cfg_path)
        _emit(ctx, {"key": key, "value": parsed_val, "config_path": str(saved)})
    except DiscordCliError as exc:
        _emit_error(ctx, exc)
