"""Registry that lets each command module self-register a Click command group with the CLI."""

from __future__ import annotations

from typing import Any, Callable

import click

from discord_cli.client import Action, HttpAction, run_action, run_http_action
from discord_cli.errors import CliError, DiscordCliError
from discord_cli.models import bool_value
from discord_cli.output import OutputOptions, parse_fields

OUTPUT_FORMATS = ("json", "jsonl", "csv", "table", "markdown", "raw")

# Hidden leaf-level mirrors of global options so flags work BOTH before AND after subcommands
# (e.g. `discord-cli channel list --human` or `discord-cli channel list --compact --fields id,name`).
_SUBCOMMAND_GLOBAL_SPECS: tuple[tuple[tuple[str, ...], str, dict[str, Any]], ...] = (
    (("--token",), "_global_token", {"default": None}),
    (("--guild",), "_global_guild_id", {"type": int, "default": None}),
    (("--human",), "_global_human", {"is_flag": True, "default": False}),
    (("--gateway",), "_global_gateway", {"is_flag": True, "default": False}),
    (("--compact",), "_global_compact", {"is_flag": True, "default": False}),
    (("--fields",), "_global_fields", {"default": None}),
    (("--max-chars",), "_global_max_chars", {"type": int, "default": None}),
    (("--string-ids",), "_global_string_ids", {"is_flag": True, "default": False}),
    (
        ("--format", "-f"),
        "_global_format",
        {"type": click.Choice(OUTPUT_FORMATS, case_sensitive=False), "default": None},
    ),
    (("--quiet", "-q"), "_global_quiet", {"is_flag": True, "default": False}),
    (("--output", "-o"), "_global_output_path", {"default": None}),
)


class TriStateBoolParamType(click.ParamType):
    """A bool option that is None when omitted, distinguishing "not set" from "false"."""

    name = "bool"

    def convert(self, value: Any, param: Any, ctx: Any) -> bool | None:
        if value is None or isinstance(value, bool):
            return value
        try:
            return bool_value(value)
        except DiscordCliError as exc:
            self.fail(str(exc), param, ctx)


TRI_STATE_BOOL = TriStateBoolParamType()


def _attach_position_independent_options(cmd: click.Command) -> None:
    """Attach hidden global options to leaf commands so global flags work after subcommands."""
    if isinstance(cmd, click.Group):
        for sub in cmd.commands.values():
            _attach_position_independent_options(sub)
        return

    existing_opts = {
        flag
        for param in cmd.params
        if isinstance(param, click.Option)
        for flag in (*param.opts, *param.secondary_opts)
    }
    existing_names = {param.name for param in cmd.params}

    for flags, dest, kwargs in _SUBCOMMAND_GLOBAL_SPECS:
        if dest in existing_names:
            continue
        available_flags = [f for f in flags if f not in existing_opts]
        if not available_flags:
            continue
        cmd.params.append(
            click.Option(
                [*available_flags, dest],
                expose_value=False,
                hidden=True,
                callback=_make_override_callback(dest),
                **kwargs,
            )
        )


def _make_override_callback(dest: str) -> Callable[[click.Context, click.Parameter, Any], Any]:
    key = dest.removeprefix("_global_")

    def _cb(ctx: click.Context, param: click.Parameter, value: Any) -> Any:
        if value is None or value is False:
            return value
        ctx.ensure_object(dict)
        ctx.obj[key] = value
        return value

    return _cb


def build_output_options(ctx: click.Context) -> OutputOptions | None:
    """Build OutputOptions from ctx.obj, returning None when only default JSON/human applies."""
    obj = ctx.obj or {}
    output_format = obj.get("format")
    compact = bool(obj.get("compact", False))
    fields = parse_fields(obj.get("fields"))
    max_chars = obj.get("max_chars")
    string_ids = bool(obj.get("string_ids", False))
    quiet = bool(obj.get("quiet", False))
    output_path = obj.get("output_path")
    if not any(
        [output_format, compact, fields, max_chars is not None, string_ids, quiet, output_path]
    ):
        return None
    return OutputOptions(
        human=bool(obj.get("human", False)),
        output_format=output_format,
        compact=compact,
        fields=fields,
        max_chars=max_chars,
        string_ids=string_ids,
        quiet=quiet,
        output_path=output_path,
    )


class CommandRegistry:
    """Collects Click command groups defined by command modules for attachment to the root CLI."""

    def __init__(self) -> None:
        self._groups: dict[str, click.Group] = {}
        self._builtin_names: set[str] = set()

    def lock_builtins(self) -> None:
        """Mark all currently registered groups as protected built-in command groups."""
        self._builtin_names = set(self._groups.keys())

    @property
    def builtin_names(self) -> frozenset[str]:
        return frozenset(self._builtin_names)

    def group(self, name: str, **kwargs: Any) -> Callable[[Callable[..., Any]], click.Group]:
        """Decorator that defines a new top-level command group and registers it by name."""

        def decorator(func: Callable[..., Any]) -> click.Group:
            if name in self._builtin_names:
                raise CliError(f"Plugin cannot overwrite built-in command group {name!r}")
            command_group = click.group(name=name, **kwargs)(func)
            self._groups[name] = command_group
            return command_group

        return decorator

    def attach_all(self, root: click.Group) -> None:
        """Attach every registered group to the root CLI group."""
        for command_group in self._groups.values():
            _attach_position_independent_options(command_group)
            root.add_command(command_group)


registry = CommandRegistry()


def invoke(ctx: click.Context, action: Action, **kwargs: Any) -> None:
    """Merge the root options with command kwargs and run the Discord action."""
    obj = ctx.obj or {}
    merged = {"guild_id": obj.get("guild_id"), **kwargs}
    run_kwargs: dict[str, Any] = {
        "human": obj.get("human", False),
        "token": obj.get("token"),
    }
    if obj.get("gateway"):
        run_kwargs["use_gateway"] = True
    output_options = build_output_options(ctx)
    if output_options is not None:
        run_kwargs["output_options"] = output_options
    run_action(action, merged, **run_kwargs)


def invoke_http(ctx: click.Context, action: HttpAction, **kwargs: Any) -> None:
    """Run a zero-gateway HTTP action (e.g. webhook execution) using root output options."""
    obj = ctx.obj or {}
    run_kwargs: dict[str, Any] = {"human": obj.get("human", False)}
    output_options = build_output_options(ctx)
    if output_options is not None:
        run_kwargs["output_options"] = output_options
    run_http_action(action, kwargs, **run_kwargs)
