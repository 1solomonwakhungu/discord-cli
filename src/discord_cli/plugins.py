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


_loaded: list[PluginInfo] = []


def loaded_plugins() -> list[PluginInfo]:
    """Return the plugins discovered by the most recent `load_plugins()` call."""
    return list(_loaded)


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
    is skipped with a logged warning; it never crashes the CLI.
    """
    _loaded.clear()
    for ep in _discover(PLUGIN_GROUP):
        try:
            register = ep.load()
            register(registry)
        except Exception:  # noqa: BLE001 - a broken plugin must never crash the CLI
            logger.warning("Failed to load plugin %r from %r", ep.name, ep.value, exc_info=True)
            continue
        _loaded.append(PluginInfo(name=ep.name, version=_entry_point_version(ep), module=ep.value))

    registry.attach_all(root)
    return list(_loaded)
