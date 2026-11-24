"""Registry that lets each command module self-register a Click command group with the CLI."""

from __future__ import annotations

import os
from collections.abc import Iterable
from typing import Any, Callable

import click

from discord_cli.client import Action, HttpAction, run_action, run_http_action
from discord_cli.config import resolve_guild_identifier
from discord_cli.errors import (
    CliError,
    DiscordCliError,
    classify_exception,
    resolve_process_exit_code,
    semantic_exit_codes_enabled,
)
from discord_cli.models import bool_value
from discord_cli.output import (
    MIN_MAX_CHARS,
    OutputOptions,
    make_payload,
    parse_fields,
    print_output,
)
from discord_cli.policy import (
    POLICY_LEVELS,
    effective_risk,
    evaluate_policy,
    redact_secrets_in_text,
    resolve_policy_config,
    stricter_max_mutations,
    stricter_policy,
    write_audit_log,
)
from discord_cli.resolvers import RESOURCE_ID

OUTPUT_FORMATS = ("json", "jsonl", "csv", "table", "markdown", "raw")


def _schema_callback(ctx: click.Context, param: click.Parameter, value: bool) -> None:
    """Eager `--schema` handler: emit JSON Schema for the current command without network calls."""
    if not value or ctx.resilient_parsing:
        return
    from discord_cli.schema import build_command_schema

    path = _extract_command_path(ctx)
    schema = build_command_schema(path, ctx.command)
    obj = ctx.obj or {}
    print_output(
        make_payload(schema),
        bool(obj.get("human", False)),
        options=build_output_options(ctx),
    )
    ctx.exit(0)


# Hidden mirrors of global options so flags work BOTH before AND after subcommands
# (e.g. `discord-cli channel list --human` or `discord-cli message send 123 --dry-run`).
_SUBCOMMAND_GLOBAL_SPECS: tuple[tuple[tuple[str, ...], str, dict[str, Any]], ...] = (
    (("--token",), "_global_token", {"default": None}),
    (("--guild",), "_global_guild_id", {"type": RESOURCE_ID, "default": None}),
    (("--profile",), "_global_profile", {"default": None}),
    (("--human",), "_global_human", {"is_flag": True, "default": False}),
    (("--gateway",), "_global_gateway", {"is_flag": True, "default": False}),
    (("--no-plugins",), "_global_no_plugins", {"is_flag": True, "default": False}),
    (("--compact",), "_global_compact", {"is_flag": True, "default": False}),
    (("--fields",), "_global_fields", {"default": None}),
    (
        ("--max-chars",),
        "_global_max_chars",
        {"type": click.IntRange(min=MIN_MAX_CHARS), "default": None},
    ),
    (("--string-ids",), "_global_string_ids", {"is_flag": True, "default": False}),
    (
        ("--format", "-f"),
        "_global_format",
        {"type": click.Choice(OUTPUT_FORMATS, case_sensitive=False), "default": None},
    ),
    (("--quiet", "-q"), "_global_quiet", {"is_flag": True, "default": False}),
    (("--output", "-o"), "_global_output_path", {"default": None}),
    (
        ("--policy",),
        "_global_policy",
        {"type": click.Choice(POLICY_LEVELS, case_sensitive=False), "default": None},
    ),
    (("--dry-run",), "_global_dry_run", {"is_flag": True, "default": False}),
    (("--yes",), "_global_yes", {"is_flag": True, "default": False}),
    (("--confirm-token",), "_global_confirm_token", {"default": None}),
    (
        ("--max-mutations",),
        "_global_max_mutations",
        {"type": click.IntRange(min=1), "default": None},
    ),
    (("--reason",), "_global_reason", {"default": None}),
    (("--untrusted-envelope",), "_global_untrusted_envelope", {"is_flag": True, "default": False}),
    (("--redact-pii",), "_global_redact_pii", {"is_flag": True, "default": False}),
    (
        ("--semantic-exit-codes",),
        "_global_semantic_exit_codes",
        {"is_flag": True, "default": False},
    ),
)


class TriStateBoolParamType(click.ParamType):
    """A bool option that is None when omitted, distinguishing "not set" from "false"."""

    name = "bool"

    def convert(self, value: Any, param: Any, ctx: Any) -> bool | None:
        if value is None or isinstance(value, bool):
            return value
        try:
            return bool_value(value)
        except DiscordCliError as exc:
            self.fail(str(exc), param, ctx)


TRI_STATE_BOOL = TriStateBoolParamType()


def _extract_command_path(ctx: Any) -> tuple[str, ...]:
    """Return canonical command path tokens (excluding root program name)."""
    tokens: list[str] = []
    cur: Any = ctx
    while cur is not None and getattr(cur, "parent", None) is not None:
        cmd = getattr(cur, "command", None)
        name = getattr(cmd, "name", None) or getattr(cur, "info_name", None)
        if name:
            tokens.append(str(name))
        cur = cur.parent
    tokens.reverse()
    return tuple(tokens)


def _attach_options_to_command(cmd: click.Command) -> None:
    existing_opts = {
        flag
        for param in cmd.params
        if isinstance(param, click.Option)
        for flag in (*param.opts, *param.secondary_opts)
    }
    existing_names = {param.name for param in cmd.params}

    if "--schema" not in existing_opts and "_global_schema" not in existing_names:
        cmd.params.append(
            click.Option(
                ["--schema", "_global_schema"],
                is_flag=True,
                is_eager=True,
                expose_value=False,
                hidden=True,
                callback=_schema_callback,
            )
        )

    for flags, dest, kwargs in _SUBCOMMAND_GLOBAL_SPECS:
        if dest in existing_names:
            continue
        available_flags = [f for f in flags if f not in existing_opts]
        if not available_flags:
            continue
        cmd.params.append(
            click.Option(
                [*available_flags, dest],
                expose_value=False,
                hidden=True,
                callback=_make_override_callback(dest),
                **kwargs,
            )
        )


def _attach_position_independent_options(cmd: click.Command) -> None:
    """Attach hidden global options to leaf commands and invoke-without-command groups."""
    if isinstance(cmd, click.Group):
        if cmd.invoke_without_command:
            _attach_options_to_command(cmd)
        for sub in cmd.commands.values():
            _attach_position_independent_options(sub)
        return
    _attach_options_to_command(cmd)


def _make_override_callback(dest: str) -> Callable[[click.Context, click.Parameter, Any], Any]:
    key = dest.removeprefix("_global_")

    def _cb(ctx: click.Context, param: click.Parameter, value: Any) -> Any:
        if value is None or value is False:
            return value
        ctx.ensure_object(dict)
        if key == "policy":
            ctx.obj[key] = stricter_policy(ctx.obj.get(key), str(value))
        elif key == "max_mutations":
            ctx.obj[key] = stricter_max_mutations(ctx.obj.get(key), int(value))
        else:
            ctx.obj[key] = value
        return value

    return _cb


def build_output_options(ctx: click.Context) -> OutputOptions | None:
    """Build OutputOptions from ctx.obj, returning None when only default JSON/human applies."""
    obj = ctx.obj or {}
    output_format = obj.get("format")
    compact = bool(obj.get("compact", False))
    fields = parse_fields(obj.get("fields"))
    max_chars = obj.get("max_chars")
    string_ids = bool(obj.get("string_ids", False))
    quiet = bool(obj.get("quiet", False))
    output_path = obj.get("output_path")
    untrusted_envelope = bool(obj.get("untrusted_envelope", False))
    redact_pii = bool(obj.get("redact_pii", False))
    if not any(
        [
            output_format,
            compact,
            fields,
            max_chars is not None,
            string_ids,
            quiet,
            output_path,
            untrusted_envelope,
            redact_pii,
        ]
    ):
        return None
    return OutputOptions(
        human=bool(obj.get("human", False)),
        output_format=output_format,
        compact=compact,
        fields=fields,
        max_chars=max_chars,
        string_ids=string_ids,
        quiet=quiet,
        output_path=output_path,
        untrusted_envelope=untrusted_envelope,
        redact_pii=redact_pii,
    )


class CommandRegistry:
    """Collects Click command groups defined by command modules for attachment to the root CLI."""

    def __init__(self) -> None:
        self._groups: dict[str, click.Group] = {}
        self._builtin_names: set[str] = set()
        self._builtin_subcommands: dict[str, dict[str, click.Command]] = {}
        self._locked: bool = False

    def lock_builtins(self, extra_protected: Iterable[str] = ()) -> None:
        """Mark all currently registered groups, subcommands, and aliases as protected."""
        self._builtin_names = set(self._groups.keys()) | set(extra_protected)
        self._builtin_subcommands = {
            name: dict(group.commands) for name, group in self._groups.items()
        }
        self._locked = True

    @property
    def builtin_names(self) -> frozenset[str]:
        return frozenset(self._builtin_names)

    def check_builtin_integrity(self) -> list[str]:
        """Restore any built-in subcommands mutated by a plugin and return violation descriptions."""
        violations: list[str] = []
        for group_name, orig_commands in self._builtin_subcommands.items():
            group = self._groups.get(group_name)
            if group is None:
                continue
            for sub_name, orig_cmd in orig_commands.items():
                if group.commands.get(sub_name) is not orig_cmd:
                    violations.append(f"{group_name} {sub_name}")
                    group.commands[sub_name] = orig_cmd
            for sub_name in list(group.commands.keys()):
                if sub_name not in orig_commands:
                    violations.append(f"{group_name} {sub_name}")
                    del group.commands[sub_name]
        return violations

    def group(self, name: str, **kwargs: Any) -> Callable[[Callable[..., Any]], click.Group]:
        """Decorator that defines a new top-level command group and registers it by name."""

        def decorator(func: Callable[..., Any]) -> click.Group:
            if name in self._builtin_names:
                raise CliError(f"Plugin cannot overwrite built-in command group {name!r}")
            if self._locked and name in self._groups:
                raise CliError(f"Plugin group name {name!r} is already registered")
            command_group = click.group(name=name, **kwargs)(func)
            self._groups[name] = command_group
            return command_group

        return decorator

    def attach_all(self, root: click.Group) -> None:
        """Attach every registered group to the root CLI group."""
        for command_group in self._groups.values():
            _attach_position_independent_options(command_group)
            root.add_command(command_group)


registry = CommandRegistry()


def _emit_local_error(
    ctx: click.Context,
    exc: Exception,
    *,
    audit_meta: dict[str, Any] | None = None,
) -> None:
    obj = ctx.obj or {}
    err = classify_exception(exc, message_sanitizer=redact_secrets_in_text)
    exit_code = resolve_process_exit_code(
        err,
        semantic=semantic_exit_codes_enabled(bool(obj.get("semantic_exit_codes", False))),
    )
    if audit_meta is not None:
        write_audit_log(
            command=str(audit_meta.get("command", "")),
            risk=str(audit_meta.get("risk", "read")),
            guild_id=audit_meta.get("guild_id"),
            policy=str(audit_meta.get("policy", "allow-destructive")),
            dry_run=bool(audit_meta.get("dry_run", False)),
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


def _check_policy_and_dry_run(
    ctx: click.Context,
    guild_id: int | None,
    kwargs: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Run policy evaluation before any network call.

    Returns `(dry_run_plan_or_none, audit_meta_or_none)`.
    """
    obj = ctx.obj or {}
    cmd_path = " ".join(_extract_command_path(ctx))
    risk = effective_risk(cmd_path, kwargs)

    try:
        policy_cfg = resolve_policy_config(
            cli_policy=obj.get("policy"),
            cli_max_mutations=obj.get("max_mutations"),
        )
    except DiscordCliError as exc:
        _emit_local_error(
            ctx,
            exc,
            audit_meta={
                "command": cmd_path,
                "risk": risk,
                "guild_id": guild_id,
                "policy": "invalid",
                "dry_run": bool(obj.get("dry_run", False)),
            },
        )
        raise  # pragma: no cover

    audit_enabled = bool(os.environ.get("DISCORD_CLI_AUDIT_LOG", "").strip())
    audit_meta = (
        {
            "command": cmd_path,
            "risk": risk,
            "guild_id": guild_id,
            "policy": policy_cfg.policy,
            "dry_run": bool(obj.get("dry_run", False)),
        }
        if audit_enabled
        else None
    )

    try:
        plan = evaluate_policy(
            cmd_path,
            guild_id,
            kwargs,
            policy_cfg,
            dry_run=bool(obj.get("dry_run", False)),
            yes=bool(obj.get("yes", False)),
            confirm_token=obj.get("confirm_token"),
        )
    except DiscordCliError as exc:
        _emit_local_error(ctx, exc, audit_meta=audit_meta)
        raise  # pragma: no cover

    return plan, audit_meta


def invoke(ctx: click.Context, action: Action, **kwargs: Any) -> None:
    """Merge root options, enforce local safety policies, and run the Discord action."""
    obj = ctx.obj or {}
    profile = obj.get("profile")

    try:
        resolved_guild = resolve_guild_identifier(obj.get("guild_id"), profile=profile)
    except DiscordCliError as exc:
        _emit_local_error(ctx, exc)
        return  # pragma: no cover

    merged: dict[str, Any] = {"guild_id": resolved_guild, **kwargs}
    global_reason = obj.get("reason") or os.environ.get("DISCORD_CLI_REASON")
    if global_reason and not merged.get("reason"):
        merged["reason"] = global_reason

    plan, audit_meta = _check_policy_and_dry_run(ctx, resolved_guild, merged)
    if plan is not None:
        if audit_meta is not None:
            write_audit_log(
                command=str(audit_meta["command"]),
                risk=str(audit_meta["risk"]),
                guild_id=resolved_guild,
                policy=str(audit_meta["policy"]),
                dry_run=True,
                ok=True,
                exit_code=0,
            )
        print_output(
            make_payload(plan),
            bool(obj.get("human", False)),
            options=build_output_options(ctx),
        )
        raise SystemExit(0)

    run_kwargs: dict[str, Any] = {
        "human": obj.get("human", False),
        "token": obj.get("token"),
    }
    if obj.get("gateway"):
        run_kwargs["use_gateway"] = True
    output_options = build_output_options(ctx)
    if output_options is not None:
        run_kwargs["output_options"] = output_options
    if profile:
        run_kwargs["profile"] = profile
    if obj.get("semantic_exit_codes"):
        run_kwargs["semantic_exit"] = True
    if audit_meta is not None:
        run_kwargs["audit_meta"] = audit_meta
    run_action(action, merged, **run_kwargs)


def invoke_http(ctx: click.Context, action: HttpAction, **kwargs: Any) -> None:
    """Enforce local safety policies and run a zero-gateway HTTP action."""
    obj = ctx.obj or {}
    merged = dict(kwargs)
    global_reason = obj.get("reason") or os.environ.get("DISCORD_CLI_REASON")
    if global_reason and not merged.get("reason"):
        merged["reason"] = global_reason

    plan, audit_meta = _check_policy_and_dry_run(ctx, None, merged)
    if plan is not None:
        if audit_meta is not None:
            write_audit_log(
                command=str(audit_meta["command"]),
                risk=str(audit_meta["risk"]),
                guild_id=None,
                policy=str(audit_meta["policy"]),
                dry_run=True,
                ok=True,
                exit_code=0,
            )
        print_output(
            make_payload(plan),
            bool(obj.get("human", False)),
            options=build_output_options(ctx),
        )
        raise SystemExit(0)

    run_kwargs: dict[str, Any] = {"human": obj.get("human", False)}
    output_options = build_output_options(ctx)
    if output_options is not None:
        run_kwargs["output_options"] = output_options
    if obj.get("semantic_exit_codes"):
        run_kwargs["semantic_exit"] = True
    if audit_meta is not None:
        run_kwargs["audit_meta"] = audit_meta
    run_http_action(action, merged, **run_kwargs)
