"""Runtime schema & capability discovery commands (`discord-cli describe`)."""

from __future__ import annotations

import click

from discord_cli.errors import (
    DiscordCliError,
    NotFoundError,
    classify_exception,
    resolve_process_exit_code,
    semantic_exit_codes_enabled,
)
from discord_cli.output import make_payload, print_output
from discord_cli.policy import RISK_LEVELS, enforce_group_allowlist, redact_secrets_in_text
from discord_cli.registry import build_output_options, registry
from discord_cli.schema import (
    build_command_schema,
    build_commands_json,
    list_command_summaries,
    resolve_command_by_path,
)


def _check_group(ctx: click.Context, path: str) -> None:
    try:
        enforce_group_allowlist(path)
    except DiscordCliError as exc:
        obj = ctx.obj or {}
        err = classify_exception(exc, message_sanitizer=redact_secrets_in_text)
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
        ) from None


def _emit_local(ctx: click.Context, data: object) -> None:
    obj = ctx.obj or {}
    print_output(
        make_payload(data),
        bool(obj.get("human", False)),
        options=build_output_options(ctx),
    )


def _root_group(ctx: click.Context) -> click.Group:
    root = ctx.find_root().command
    assert isinstance(root, click.Group)
    return root


@registry.group("describe", invoke_without_command=True)
@click.pass_context
def describe_group(ctx: click.Context) -> None:
    """Introspect CLI commands, JSON Schemas, risk levels, and required permissions."""
    _check_group(ctx, "describe")
    if ctx.invoked_subcommand is None:
        root = _root_group(ctx)
        rows = list_command_summaries(root, compact=True)
        _emit_local(ctx, {"count": len(rows), "commands": rows})


@describe_group.command("list")
@click.option("--compact", "compact_list", is_flag=True, default=False, help="Compact summaries.")
@click.option("--group", "group_filter", default=None, help="Filter by top-level command group.")
@click.option(
    "--risk",
    "risk_filter",
    type=click.Choice(RISK_LEVELS, case_sensitive=False),
    default=None,
    help="Filter by risk level (read, write, or destructive).",
)
@click.pass_context
def describe_list(
    ctx: click.Context,
    compact_list: bool,
    group_filter: str | None,
    risk_filter: str | None,
) -> None:
    """List available commands with risk levels and capability metadata."""
    root = _root_group(ctx)
    rows = list_command_summaries(
        root,
        compact=compact_list,
        group_filter=group_filter,
        risk_filter=risk_filter.lower() if risk_filter else None,
    )
    _emit_local(ctx, {"count": len(rows), "commands": rows})


@describe_group.command("command")
@click.argument("path", nargs=-1, required=True)
@click.pass_context
def describe_command(ctx: click.Context, path: tuple[str, ...]) -> None:
    """Return full JSON Schema and safety metadata for a specific command path."""
    root = _root_group(ctx)
    resolved = resolve_command_by_path(root, path)
    if resolved is None:
        err = NotFoundError(
            f"Unknown command path: {' '.join(path)}",
            recovery_hint="Run `discord-cli describe list --compact` to see all valid commands.",
            suggested_command="discord-cli describe list --compact",
        )
        obj = ctx.obj or {}
        from discord_cli.errors import (
            classify_exception,
            resolve_process_exit_code,
            semantic_exit_codes_enabled,
        )

        err_dict = classify_exception(err)
        print_output(
            make_payload(error=err_dict),
            bool(obj.get("human", False)),
            options=build_output_options(ctx),
        )
        raise SystemExit(
            resolve_process_exit_code(
                err_dict,
                semantic=semantic_exit_codes_enabled(bool(obj.get("semantic_exit_codes", False))),
            )
        )
    resolved_path, cmd = resolved
    if isinstance(cmd, click.Group):
        rows = list_command_summaries(root, group_filter=resolved_path[0])
        _emit_local(ctx, {"group": " ".join(resolved_path), "commands": rows})
        return
    _emit_local(ctx, build_command_schema(resolved_path, cmd))


@describe_group.command("commands-json")
@click.pass_context
def describe_commands_json(ctx: click.Context) -> None:
    """Emit the full commands.json manifest generated from the live Click command tree."""
    root = _root_group(ctx)
    _emit_local(ctx, build_commands_json(root))
