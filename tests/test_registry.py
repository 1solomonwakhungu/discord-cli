"""Tests for discord_cli.registry: TriStateBoolParamType, CommandRegistry, invoke()."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import click
import pytest
from click.testing import CliRunner

from discord_cli.registry import TRI_STATE_BOOL, CommandRegistry, invoke


class TestTriStateBoolParamType:
    @pytest.fixture
    def cmd(self):
        @click.command()
        @click.option("--flag", type=TRI_STATE_BOOL, default=None)
        def cmd(flag):
            click.echo(repr(flag))

        return cmd

    def test_omitted_is_none(self, cmd):
        result = CliRunner().invoke(cmd, [])
        assert result.exit_code == 0
        assert result.output.strip() == "None"

    @pytest.mark.parametrize("value", ["true", "1", "yes", "y", "on"])
    def test_truthy_strings(self, cmd, value):
        result = CliRunner().invoke(cmd, ["--flag", value])
        assert result.exit_code == 0
        assert result.output.strip() == "True"

    @pytest.mark.parametrize("value", ["false", "0", "no", "n", "off"])
    def test_falsy_strings(self, cmd, value):
        result = CliRunner().invoke(cmd, ["--flag", value])
        assert result.exit_code == 0
        assert result.output.strip() == "False"

    def test_invalid_value_fails_the_command(self, cmd):
        result = CliRunner().invoke(cmd, ["--flag", "bogus"])
        assert result.exit_code != 0
        assert "Invalid boolean value" in result.output

    def test_convert_passes_through_actual_bools(self):
        assert TRI_STATE_BOOL.convert(True, None, None) is True
        assert TRI_STATE_BOOL.convert(False, None, None) is False
        assert TRI_STATE_BOOL.convert(None, None, None) is None


class TestCommandRegistry:
    def test_group_decorator_registers_and_returns_a_click_group(self):
        registry = CommandRegistry()

        @registry.group("widget")
        def widget_group():
            """Manage widgets."""

        assert "widget" in registry._groups
        assert isinstance(registry._groups["widget"], click.Group)
        assert registry._groups["widget"].name == "widget"

    def test_attach_all_adds_every_registered_group_to_root(self):
        registry = CommandRegistry()

        @registry.group("widget")
        def widget_group():
            pass

        @registry.group("gadget")
        def gadget_group():
            pass

        @click.group()
        def root():
            pass

        registry.attach_all(root)

        assert set(root.commands.keys()) == {"widget", "gadget"}


class TestInvoke:
    def test_merges_root_options_with_command_kwargs(self, monkeypatch):
        fake_run_action = MagicMock()
        monkeypatch.setattr("discord_cli.registry.run_action", fake_run_action)

        ctx = SimpleNamespace(obj={"guild_id": 42, "human": True, "token": "tok"})
        action = MagicMock()

        invoke(ctx, action, channel_id=1)

        fake_run_action.assert_called_once_with(
            action, {"guild_id": 42, "channel_id": 1}, human=True, token="tok"
        )

    def test_defaults_when_ctx_obj_is_none(self, monkeypatch):
        fake_run_action = MagicMock()
        monkeypatch.setattr("discord_cli.registry.run_action", fake_run_action)

        ctx = SimpleNamespace(obj=None)
        action = MagicMock()

        invoke(ctx, action)

        fake_run_action.assert_called_once_with(action, {"guild_id": None}, human=False, token=None)
