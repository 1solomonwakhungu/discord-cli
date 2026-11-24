"""Third-party plugin discovery: load command extensions registered as entry points.

A plugin is any installed distribution that declares an entry point in the
``discord_cli.plugins`` group, pointing at a callable that accepts a
``CommandRegistry`` and registers one or more command groups on it, e.g.:

    [project.entry-points."discord_cli.plugins"]
    hello = "plugin_hello:register"

See docs/plugins.md for the full plugin API contract.
"""

from __future__ import annotations

import logging
import os
from importlib.metadata import EntryPoint, entry_points
from typing import NamedTuple

import click

from discord_cli.errors import CliError
from discord_cli.output import make_payload, print_output
from discord_cli.registry import CommandRegistry, _check_policy_and_dry_run, build_output_options

logger = logging.getLogger(__name__)


def _wrap_plugin_command_policy(cmd: click.Command) -> None:
    """Wrap a third-party plugin command so policy ceilings & allowlists apply before execution."""
    if isinstance(cmd, click.Group):
        for sub in cmd.commands.values():
            _wrap_plugin_command_policy(sub)
        if not cmd.invoke_without_command:
            return
    if getattr(cmd, "_discord_cli_policy_wrapped", False):
        return
    orig_invoke = cmd.invoke

    def _gated_invoke(ctx: click.Context) -> object:
        obj = ctx.obj or {}
        plan, _ = _check_policy_and_dry_run(ctx, obj.get("guild_id"), dict(ctx.params))
        if plan is not None:
            print_output(
                make_payload(plan),
                bool(obj.get("human", False)),
                options=build_output_options(ctx),
            )
            raise SystemExit(0)
        return orig_invoke(ctx)

    cmd.invoke = _gated_invoke  # type: ignore[method-assign]
    cmd._discord_cli_policy_wrapped = True


PLUGIN_GROUP = "discord_cli.plugins"


class PluginInfo(NamedTuple):
    """Metadata about a plugin that loaded and registered successfully."""

    name: str
    version: str
    module: str


class PluginError(NamedTuple):
    """Diagnostic record for a plugin that failed to load or register."""

    name: str
    module: str
    error_type: str
    message: str


_loaded: list[PluginInfo] = []
_errors: list[PluginError] = []


def loaded_plugins() -> list[PluginInfo]:
    """Return the plugins discovered by the most recent `load_plugins()` call."""
    return list(_loaded)


def plugin_errors() -> list[PluginError]:
    """Return errors recorded during the most recent `load_plugins()` call."""
    return list(_errors)


def plugins_disabled_by_env() -> bool:
    """Return True when DISCORD_CLI_NO_PLUGINS is set to a truthy value."""
    val = os.environ.get("DISCORD_CLI_NO_PLUGINS", "").strip().lower()
    return val in {"1", "true", "yes", "on"}


def _discover(group: str) -> list[EntryPoint]:
    try:
        return list(entry_points(group=group))
    except TypeError:
        # Python 3.9's entry_points() takes no arguments and returns a dict
        # keyed by group name instead of supporting selection by keyword.
        return list(entry_points().get(group, []))


def _entry_point_version(ep: EntryPoint) -> str:
    dist = getattr(ep, "dist", None)
    if dist is None:
        return "unknown"
    try:
        return dist.version
    except Exception:  # noqa: BLE001 - version metadata is best-effort
        return "unknown"


def load_plugins(registry: CommandRegistry, root: click.Group) -> list[PluginInfo]:
    """Discover, load, and register third-party plugins safely.

    A plugin that fails to import, resolve, or register — including raising
    SystemExit, attempting to shadow a built-in command group/alias, or mutating
    built-in subcommands — is skipped with a logged warning and recorded in
    `plugin_errors()`. It never crashes the CLI.
    """
    _loaded.clear()
    _errors.clear()
    for ep in _discover(PLUGIN_GROUP):
        before_groups = set(registry._groups.keys())
        try:
            register = ep.load()
            register(registry)
            violations = registry.check_builtin_integrity()
            if violations:
                raise CliError(
                    f"Plugin {ep.name!r} attempted to modify built-in subcommands: {', '.join(violations)}"
                )
        except KeyboardInterrupt:
            raise
        except BaseException as exc:  # noqa: BLE001 - even SystemExit in a plugin must not kill the CLI
            # Roll back any partially registered groups from the failed plugin.
            for added in set(registry._groups.keys()) - before_groups:
                registry._groups.pop(added, None)
            registry.check_builtin_integrity()
            logger.warning("Failed to load plugin %r from %r", ep.name, ep.value, exc_info=True)
            _errors.append(
                PluginError(
                    name=ep.name,
                    module=ep.value,
                    error_type=exc.__class__.__name__,
                    message=str(exc),
                )
            )
            continue
        for added_name in set(registry._groups.keys()) - before_groups:
            added_group = registry._groups.get(added_name)
            if added_group is not None:
                _wrap_plugin_command_policy(added_group)
        _loaded.append(PluginInfo(name=ep.name, version=_entry_point_version(ep), module=ep.value))

    registry.attach_all(root)
    return list(_loaded)
