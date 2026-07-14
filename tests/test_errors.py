"""Tests for discord_cli.errors: custom exception hierarchy."""

from __future__ import annotations

import pytest

from discord_cli.errors import ApiError, CliError, ConfigError, DiscordCliError


class TestExceptionHierarchy:
    @pytest.mark.parametrize("exc_cls", [ConfigError, ApiError, CliError])
    def test_all_are_discord_cli_errors(self, exc_cls):
        assert issubclass(exc_cls, DiscordCliError)

    def test_discord_cli_error_is_an_exception(self):
        assert issubclass(DiscordCliError, Exception)

    def test_message_is_preserved(self):
        exc = CliError("something went wrong")
        assert str(exc) == "something went wrong"

    def test_can_be_caught_as_base_class(self):
        with pytest.raises(DiscordCliError):
            raise ConfigError("missing token")

        with pytest.raises(DiscordCliError):
            raise ApiError("api failed")

        with pytest.raises(DiscordCliError):
            raise CliError("bad input")
