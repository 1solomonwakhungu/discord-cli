"""Plugin commands: inspect third-party command extensions loaded via entry points."""

from __future__ import annotations

from typing import Any

import click

from discord_cli.errors import (
    DiscordCliError,
    classify_exception,
    resolve_process_exit_code,
    semantic_exit_codes_enabled,
)
from discord_cli.output import make_payload, print_output
from discord_cli.plugins import loaded_plugins, plugin_errors
from discord_cli.policy import enforce_group_allowlist, redact_secrets_in_text
from discord_cli.registry import build_output_options, registry


@registry.group("plugins")
def plugins_group() -> None:
    """Inspect third-party plugins discovered via the discord_cli.plugins entry-point group."""


@plugins_group.command("list")
@click.pass_context
def plugins_list(ctx: click.Context) -> None:
    try:
        enforce_group_allowlist("plugins list")
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
    root_ctx = ctx.find_root()
    root_cmd = root_ctx.command
    if hasattr(root_cmd, "ensure_plugins_loaded") and not (ctx.obj or {}).get("no_plugins"):
        root_cmd.ensure_plugins_loaded(root_ctx)
    human = (ctx.obj or {}).get("human", False)
    plugins = [
        {"name": plugin.name, "version": plugin.version, "module": plugin.module}
        for plugin in loaded_plugins()
    ]
    data: dict[str, Any] = {"plugins": plugins}
    errors = plugin_errors()
    if errors:
        data["errors"] = [
            {
                "name": err.name,
                "module": err.module,
                "error_type": err.error_type,
                "message": err.message,
            }
            for err in errors
        ]
    print_output(make_payload(data), human, options=build_output_options(ctx))
