"""Configuration file inspection and editing commands (`discord-cli config`)."""

from __future__ import annotations

from typing import Any

import click

from discord_cli.config import (
    get_config_path,
    get_project_config_path,
    load_merged_toml,
    load_user_toml,
    sanitize_config_for_display,
    save_user_config,
    validate_profile_name,
    validate_toml_key_segment,
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
from discord_cli.policy import (
    effective_risk,
    enforce_group_allowlist,
    evaluate_policy,
    redact_secrets_in_text,
    resolve_policy_config,
    write_audit_log,
)
from discord_cli.registry import build_output_options, registry

_FORBIDDEN_CONFIG_KEYS = frozenset({"token", "bot_token"})


def _emit(ctx: click.Context, data: Any) -> None:
    obj = ctx.obj or {}
    print_output(
        make_payload(data),
        bool(obj.get("human", False)),
        options=build_output_options(ctx),
    )


def _emit_error(ctx: click.Context, exc: Exception, *, command_path: str = "config") -> None:
    obj = ctx.obj or {}
    err = classify_exception(exc, message_sanitizer=redact_secrets_in_text)
    exit_code = resolve_process_exit_code(
        err,
        semantic=semantic_exit_codes_enabled(bool(obj.get("semantic_exit_codes", False))),
    )
    write_audit_log(
        command=command_path,
        risk=effective_risk(command_path, {}),
        guild_id=None,
        policy=str(obj.get("policy") or "allow-destructive"),
        dry_run=bool(obj.get("dry_run", False)),
        ok=False,
        exit_code=exit_code,
        error_code=err.get("category"),
    )
    print_output(
        make_payload(error=err),
        bool(obj.get("human", False)),
        options=build_output_options(ctx),
    )
    raise SystemExit(exit_code)


def _coerce_value(raw: str) -> Any:
    stripped = raw.strip()
    lowered = stripped.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if stripped.isascii() and stripped.isdigit():
        return int(stripped)
    return raw


@registry.group("config")
def config_group() -> None:
    """Inspect and manage discord-cli TOML configuration and guild aliases."""


@config_group.command("path")
@click.pass_context
def config_path(ctx: click.Context) -> None:
    """Print user and project-local configuration file paths."""
    try:
        enforce_group_allowlist("config path")
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
    except DiscordCliError as exc:
        _emit_error(ctx, exc, command_path="config path")


@config_group.command("list")
@click.pass_context
def config_list(ctx: click.Context) -> None:
    """Display the merged non-secret configuration."""
    try:
        enforce_group_allowlist("config list")
        _emit(ctx, sanitize_config_for_display(load_merged_toml()))
    except DiscordCliError as exc:
        _emit_error(ctx, exc, command_path="config list")


@config_group.command("get")
@click.argument("key")
@click.pass_context
def config_get(ctx: click.Context, key: str) -> None:
    """Read a dot-separated key from the merged configuration."""
    try:
        enforce_group_allowlist("config get")
        parts = key.split(".")
        if any(p.lower() in _FORBIDDEN_CONFIG_KEYS for p in parts):
            raise NotFoundError(f"Configuration key not found: {key}")
        data: Any = sanitize_config_for_display(load_merged_toml())
        for part in parts:
            if isinstance(data, dict) and part in data:
                data = data[part]
            else:
                raise NotFoundError(f"Configuration key not found: {key}")
        _emit(ctx, {"key": key, "value": data})
    except DiscordCliError as exc:
        _emit_error(ctx, exc, command_path="config get")


@config_group.command("set")
@click.argument("key")
@click.argument("value")
@click.pass_context
def config_set(ctx: click.Context, key: str, value: str) -> None:
    """Set a dot-separated non-secret key in user config.toml (e.g. guilds.prod 123456)."""
    try:
        obj = ctx.obj or {}
        if not key or not key.strip():
            raise CliError("Configuration key cannot be empty.")
        raw_parts = key.split(".")
        parts = [validate_toml_key_segment(p) for p in raw_parts]
        if any(p.lower() in _FORBIDDEN_CONFIG_KEYS for p in parts):
            raise CliError(
                "Do not store bot tokens in config.toml. Use DISCORD_BOT_TOKEN or `discord-cli auth login`."
            )
        if parts == ["default_profile"]:
            validate_profile_name(value)

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
            write_audit_log(
                command="config set",
                risk="write",
                guild_id=None,
                policy=policy_cfg.policy,
                dry_run=True,
                ok=True,
                exit_code=0,
            )
            _emit(ctx, dry_run_plan)
            return

        cfg_path = get_config_path()
        user_data = load_user_toml(cfg_path)
        cursor: dict[str, Any] = user_data
        for segment in parts[:-1]:
            if segment not in cursor or not isinstance(cursor[segment], dict):
                cursor[segment] = {}
            cursor = cursor[segment]
        parsed_val = _coerce_value(value)
        cursor[parts[-1]] = parsed_val
        saved = save_user_config(user_data, cfg_path)
        write_audit_log(
            command="config set",
            risk="write",
            guild_id=None,
            policy=policy_cfg.policy,
            dry_run=False,
            ok=True,
            exit_code=0,
        )
        _emit(ctx, {"key": key, "value": parsed_val, "config_path": str(saved)})
    except DiscordCliError as exc:
        _emit_error(ctx, exc, command_path="config set")
