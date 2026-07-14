"""Tests for discord_cli.plugins: entry-point discovery, loading, and failure isolation."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import click
import pytest

from discord_cli.plugins import PluginInfo, load_plugins, loaded_plugins
from discord_cli.registry import CommandRegistry


def make_entry_point(name, version="1.2.3", register=None, raise_on_load=False):
    ep = MagicMock()
    ep.name = name
    ep.value = f"{name}_module:register"
    ep.dist = MagicMock()
    ep.dist.version = version
    if raise_on_load:
        ep.load.side_effect = RuntimeError("boom")
    else:
        ep.load.return_value = register or (lambda registry: None)
    return ep


@pytest.fixture
def root():
    @click.group()
    def root():
        pass

    return root


class TestLoadPlugins:
    def test_no_plugins_installed_returns_empty(self, monkeypatch, root):
        monkeypatch.setattr("discord_cli.plugins.entry_points", lambda **_: [])
        registry = CommandRegistry()

        result = load_plugins(registry, root)

        assert result == []
        assert loaded_plugins() == []

    def test_loads_and_registers_a_plugin(self, monkeypatch, root):
        def register(registry):
            @registry.group("widget")
            def widget_group():
                pass

        ep = make_entry_point("widget-plugin", version="0.2.0", register=register)
        monkeypatch.setattr("discord_cli.plugins.entry_points", lambda **_: [ep])

        registry = CommandRegistry()
        result = load_plugins(registry, root)

        assert result == [PluginInfo(name="widget-plugin", version="0.2.0", module=ep.value)]
        assert "widget" in root.commands

    def test_broken_plugin_is_skipped_with_a_warning(self, monkeypatch, root, caplog):
        good = make_entry_point(
            "good", register=lambda registry: registry.group("ok")(lambda: None)
        )
        bad = make_entry_point("bad", raise_on_load=True)
        monkeypatch.setattr("discord_cli.plugins.entry_points", lambda **_: [bad, good])

        registry = CommandRegistry()
        with caplog.at_level(logging.WARNING):
            result = load_plugins(registry, root)

        assert [p.name for p in result] == ["good"]
        assert any("bad" in record.message for record in caplog.records)
        assert "ok" in root.commands

    def test_plugin_whose_register_raises_is_skipped(self, monkeypatch, root):
        def register(registry):
            raise ValueError("bad plugin")

        ep = make_entry_point("exploder", register=register)
        monkeypatch.setattr("discord_cli.plugins.entry_points", lambda **_: [ep])

        registry = CommandRegistry()
        result = load_plugins(registry, root)

        assert result == []

    def test_missing_dist_version_falls_back_to_unknown(self, monkeypatch, root):
        ep = make_entry_point("no-dist")
        ep.dist = None
        monkeypatch.setattr("discord_cli.plugins.entry_points", lambda **_: [ep])

        registry = CommandRegistry()
        result = load_plugins(registry, root)

        assert result[0].version == "unknown"

    def test_entry_points_group_kwarg_unsupported_falls_back_to_dict(self, monkeypatch, root):
        ep = make_entry_point("legacy")

        def fake_entry_points(**kwargs):
            if kwargs:
                raise TypeError("entry_points() takes no keyword arguments")
            return {"discord_cli.plugins": [ep]}

        monkeypatch.setattr("discord_cli.plugins.entry_points", fake_entry_points)

        registry = CommandRegistry()
        result = load_plugins(registry, root)

        assert [p.name for p in result] == ["legacy"]

    def test_second_call_replaces_previously_loaded_plugins(self, monkeypatch, root):
        first = make_entry_point("first")
        monkeypatch.setattr("discord_cli.plugins.entry_points", lambda **_: [first])
        registry = CommandRegistry()
        load_plugins(registry, root)
        assert [p.name for p in loaded_plugins()] == ["first"]

        monkeypatch.setattr("discord_cli.plugins.entry_points", lambda **_: [])
        load_plugins(registry, root)

        assert loaded_plugins() == []
