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

from discord_cli.registry import CommandRegistry

logger = logging.getLogger(__name__)

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
    """Discover, load, and register third-party plugins.

    For each entry point in the `discord_cli.plugins` group, resolve the
    callable it points to and call it with `registry` so the plugin can
    register its own command groups. Newly registered groups are then
    attached to `root`. A plugin that fails to import, resolve, or register
    (including attempting to shadow a built-in command group) is skipped with
    a logged warning and recorded in `plugin_errors()`; it never crashes the CLI.
    """
    _loaded.clear()
    _errors.clear()
    for ep in _discover(PLUGIN_GROUP):
        try:
            register = ep.load()
            register(registry)
        except Exception as exc:  # noqa: BLE001 - a broken plugin must never crash the CLI
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
        _loaded.append(PluginInfo(name=ep.name, version=_entry_point_version(ep), module=ep.value))

    registry.attach_all(root)
    return list(_loaded)
