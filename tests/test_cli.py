"""Tests for the root CLI group and its global --token/--guild/--human options."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from discord_cli import __version__
from discord_cli.cli import main


@pytest.fixture
def captured_run_action(monkeypatch):
    """Capture the arguments the root options forward into run_action."""
    recorded = MagicMock(side_effect=SystemExit(0))
    monkeypatch.setattr("discord_cli.registry.run_action", recorded)
    return recorded


class TestRootGroup:
    def test_version_option_reports_package_version(self, cli_runner):
        result = cli_runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.output

    def test_help_documents_the_global_options(self, cli_runner):
        result = cli_runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        for option in ("--token", "--guild", "--human"):
            assert option in result.output

    def test_every_command_group_is_attached(self, cli_runner):
        result = cli_runner.invoke(main, ["--help"])
        for group in (
            "category",
            "channel",
            "export",
            "guild",
            "invites",
            "member",
            "message",
            "permissions",
            "plugins",
            "role",
            "search",
            "threads",
            "webhook",
        ):
            assert group in result.output


class TestGlobalOptions:
    def test_guild_and_token_reach_run_action(self, cli_runner, captured_run_action):
        cli_runner.invoke(
            main, ["--token", "tok", "--guild", "42", "channel", "list"], standalone_mode=False
        )
        _, kwargs = captured_run_action.call_args
        assert captured_run_action.call_args[0][1]["guild_id"] == 42
        assert kwargs["token"] == "tok"
        assert kwargs["human"] is False

    def test_human_flag_reaches_run_action(self, cli_runner, captured_run_action):
        cli_runner.invoke(main, ["--human", "channel", "list"], standalone_mode=False)
        assert captured_run_action.call_args[1]["human"] is True

    def test_defaults_when_no_global_options_are_given(self, cli_runner, captured_run_action):
        cli_runner.invoke(main, ["channel", "list"], standalone_mode=False)
        args, kwargs = captured_run_action.call_args
        assert args[1]["guild_id"] is None
        assert kwargs == {"human": False, "token": None}

    def test_token_falls_back_to_the_environment(self, cli_runner, captured_run_action):
        cli_runner.invoke(
            main,
            ["channel", "list"],
            env={"DISCORD_BOT_TOKEN": "env-token"},
            standalone_mode=False,
        )
        assert captured_run_action.call_args[1]["token"] == "env-token"

    def test_guild_falls_back_to_the_environment(self, cli_runner, captured_run_action):
        cli_runner.invoke(
            main,
            ["channel", "list"],
            env={"DISCORD_GUILD_ID": "77"},
            standalone_mode=False,
        )
        assert captured_run_action.call_args[0][1]["guild_id"] == 77

    def test_explicit_token_overrides_the_environment(self, cli_runner, captured_run_action):
        cli_runner.invoke(
            main,
            ["--token", "flag-token", "channel", "list"],
            env={"DISCORD_BOT_TOKEN": "env-token"},
            standalone_mode=False,
        )
        assert captured_run_action.call_args[1]["token"] == "flag-token"

    def test_non_integer_guild_is_rejected(self, cli_runner):
        result = cli_runner.invoke(main, ["--guild", "not-a-number", "channel", "list"])
        assert result.exit_code != 0
