"""Integration tests for the `plugins` command group."""

from __future__ import annotations

import json

from discord_cli.plugins import PluginInfo


class TestPluginsList:
    def test_lists_no_plugins_by_default(self, cli_runner, monkeypatch):
        monkeypatch.setattr("discord_cli.commands.plugins.loaded_plugins", lambda: [])

        result = cli_runner.invoke(main, ["plugins", "list"])

        assert result.exit_code == 0
        assert json.loads(result.output) == {"ok": True, "data": {"plugins": []}}

    def test_lists_loaded_plugins(self, cli_runner, monkeypatch):
        monkeypatch.setattr(
            "discord_cli.commands.plugins.loaded_plugins",
            lambda: [PluginInfo(name="hello", version="0.1.0", module="plugin_hello:register")],
        )

        result = cli_runner.invoke(main, ["plugins", "list"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["plugins"] == [
            {"name": "hello", "version": "0.1.0", "module": "plugin_hello:register"}
        ]


from discord_cli.cli import main  # noqa: E402
