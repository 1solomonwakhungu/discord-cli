"""Authentication and profile management commands (`discord-cli auth`)."""

from __future__ import annotations

from typing import Any

import click

from discord_cli.config import (
    active_profile_name,
    delete_keyring_token,
    detect_token_source,
    get_config_path,
    keyring_available,
    load_merged_toml,
    load_user_toml,
    save_user_config,
    set_keyring_token,
    validate_profile_name,
)
from discord_cli.errors import (
    ConfigError,
    DiscordCliError,
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


def _emit_result(ctx: click.Context, data: Any) -> None:
    obj = ctx.obj or {}
    print_output(
        make_payload(data),
        bool(obj.get("human", False)),
        options=build_output_options(ctx),
    )


def _emit_error(ctx: click.Context, exc: Exception, *, command_path: str = "auth") -> None:
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


def _enforce_local_policy(ctx: click.Context, command_path: str, kwargs: dict[str, Any]) -> bool:
    """Check policy before mutating local auth state; returns True if dry-run handled."""
    obj = ctx.obj or {}
    policy_cfg = resolve_policy_config(
        cli_policy=obj.get("policy"),
        cli_max_mutations=obj.get("max_mutations"),
    )
    dry_run_plan = evaluate_policy(
        command_path,
        None,
        kwargs,
        policy_cfg,
        dry_run=bool(obj.get("dry_run", False)),
        yes=bool(obj.get("yes", False)),
        confirm_token=obj.get("confirm_token"),
    )
    if dry_run_plan is not None:
        write_audit_log(
            command=command_path,
            risk=effective_risk(command_path, kwargs),
            guild_id=None,
            policy=policy_cfg.policy,
            dry_run=True,
            ok=True,
            exit_code=0,
        )
        _emit_result(ctx, dry_run_plan)
        return True
    return False


@registry.group("auth")
def auth_group() -> None:
    """Manage bot authentication profiles and optional OS keyring credentials."""


@auth_group.command("login")
@click.option("--profile", "profile_name", default=None, help="Profile name (default: active).")
@click.option("--token", "bot_token", default=None, help="Bot token to store in OS keyring.")
@click.option("--guild", "default_guild", type=int, default=None, help="Default guild ID.")
@click.option(
    "--set-default", is_flag=True, default=False, help="Make this profile the default profile."
)
@click.pass_context
def auth_login(
    ctx: click.Context,
    profile_name: str | None,
    bot_token: str | None,
    default_guild: int | None,
    set_default: bool,
) -> None:
    """Configure a profile and optionally store its bot token in the OS keyring."""
    try:
        obj = ctx.obj or {}
        target_profile = validate_profile_name(
            profile_name or obj.get("profile") or active_profile_name()
        )
        if _enforce_local_policy(
            ctx,
            "auth login",
            {
                "profile": target_profile,
                "default_guild": default_guild,
                "set_default": set_default,
            },
        ):
            return

        token_to_store = bot_token or obj.get("token")
        stored_in_keyring = False
        if token_to_store:
            if not keyring_available():
                raise ConfigError(
                    "OS keyring backend is not installed. Install `discordcli-agents[keyring]` "
                    "or set DISCORD_BOT_TOKEN in your environment / .env file.",
                    recovery_hint="Run `pip install 'discordcli-agents[keyring]'` or export DISCORD_BOT_TOKEN.",
                )
            stored_in_keyring = set_keyring_token(target_profile, token_to_store)

        cfg_path = get_config_path()
        user_data = load_user_toml(cfg_path)
        profiles = dict(user_data.get("profiles") or {})
        prof = dict(profiles.get(target_profile) or {})
        if default_guild is not None:
            prof["default_guild"] = default_guild
        profiles[target_profile] = prof
        user_data["profiles"] = profiles
        if set_default or "default_profile" not in user_data:
            user_data["default_profile"] = target_profile
        saved = save_user_config(user_data, cfg_path)
        write_audit_log(
            command="auth login",
            risk="write",
            guild_id=default_guild,
            policy=str(obj.get("policy") or "allow-destructive"),
            dry_run=False,
            ok=True,
            exit_code=0,
        )
        _emit_result(
            ctx,
            {
                "profile": target_profile,
                "default_profile": user_data.get("default_profile"),
                "default_guild": prof.get("default_guild"),
                "stored_in_keyring": stored_in_keyring,
                "config_path": str(saved),
            },
        )
    except DiscordCliError as exc:
        _emit_error(ctx, exc, command_path="auth login")


@auth_group.command("status")
@click.option("--profile", "profile_name", default=None, help="Inspect a specific profile.")
@click.pass_context
def auth_status(ctx: click.Context, profile_name: str | None) -> None:
    """Show active authentication profile, token source, and keyring availability."""
    try:
        enforce_group_allowlist("auth status")
        obj = ctx.obj or {}
        merged = load_merged_toml()
        active = active_profile_name(profile_name or obj.get("profile"), merged)
        token_val, source = detect_token_source(obj.get("token"), profile=active)
        profiles = sorted((merged.get("profiles") or {}).keys())
        _emit_result(
            ctx,
            {
                "active_profile": active,
                "configured_profiles": profiles,
                "token_configured": bool(token_val),
                "token_source": source,
                "keyring_available": keyring_available(),
                "config_path": str(get_config_path()),
            },
        )
    except DiscordCliError as exc:
        _emit_error(ctx, exc, command_path="auth status")


@auth_group.command("switch")
@click.argument("profile_name")
@click.pass_context
def auth_switch(ctx: click.Context, profile_name: str) -> None:
    """Set the default active profile in config.toml."""
    try:
        target = validate_profile_name(profile_name)
        if _enforce_local_policy(ctx, "auth switch", {"profile": target}):
            return
        cfg_path = get_config_path()
        user_data = load_user_toml(cfg_path)
        profiles = dict(user_data.get("profiles") or {})
        profiles.setdefault(target, {})
        user_data["profiles"] = profiles
        user_data["default_profile"] = target
        saved = save_user_config(user_data, cfg_path)
        obj = ctx.obj or {}
        write_audit_log(
            command="auth switch",
            risk="write",
            guild_id=None,
            policy=str(obj.get("policy") or "allow-destructive"),
            dry_run=False,
            ok=True,
            exit_code=0,
        )
        _emit_result(
            ctx,
            {
                "active_profile": target,
                "config_path": str(saved),
            },
        )
    except DiscordCliError as exc:
        _emit_error(ctx, exc, command_path="auth switch")


@auth_group.command("logout")
@click.option("--profile", "profile_name", default=None, help="Profile to remove from keyring.")
@click.pass_context
def auth_logout(ctx: click.Context, profile_name: str | None) -> None:
    """Remove stored OS keyring credentials for a profile."""
    try:
        obj = ctx.obj or {}
        target = validate_profile_name(profile_name or obj.get("profile") or active_profile_name())
        if _enforce_local_policy(ctx, "auth logout", {"profile": target}):
            return
        removed = delete_keyring_token(target)
        write_audit_log(
            command="auth logout",
            risk="destructive",
            guild_id=None,
            policy=str(obj.get("policy") or "allow-destructive"),
            dry_run=False,
            ok=True,
            exit_code=0,
        )
        _emit_result(
            ctx,
            {
                "profile": target,
                "removed_from_keyring": removed,
                "keyring_available": keyring_available(),
            },
        )
    except DiscordCliError as exc:
        _emit_error(ctx, exc, command_path="auth logout")
