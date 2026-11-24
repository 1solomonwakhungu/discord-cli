"""Runtime JSON Schema introspection and commands.json generator from the live Click tree."""

from __future__ import annotations

from typing import Any

import click

from discord_cli import __version__
from discord_cli.policy import get_command_meta


def _param_json_schema(param: click.Parameter) -> dict[str, Any]:
    """Convert a Click Argument or Option into a JSON Schema property dict."""
    schema: dict[str, Any] = {}
    ptype = param.type

    if isinstance(param, click.Option) and param.is_flag:
        schema["type"] = "boolean"
    elif isinstance(ptype, click.Choice):
        schema["type"] = "string"
        schema["enum"] = list(ptype.choices)
    elif isinstance(ptype, click.IntRange):
        schema["type"] = "integer"
        if ptype.min is not None:
            schema["minimum"] = ptype.min
        if ptype.max is not None:
            schema["maximum"] = ptype.max
    elif ptype is click.INT or getattr(ptype, "name", "") == "integer":
        schema["type"] = "integer"
    elif ptype is click.FLOAT or getattr(ptype, "name", "") == "float":
        schema["type"] = "number"
    elif getattr(ptype, "name", "") == "bool":
        schema["type"] = "boolean"
    elif getattr(ptype, "name", "") == "resource":
        schema["type"] = ["integer", "string"]
        schema["description_type"] = "snowflake_or_selector"
    else:
        schema["type"] = "string"

    if getattr(param, "multiple", False):
        schema = {"type": "array", "items": schema}

    if isinstance(param, click.Option) and param.help:
        schema["description"] = param.help
    if isinstance(param.default, (str, int, float, bool)) and not (
        isinstance(param, click.Option) and param.multiple
    ):
        schema["default"] = param.default
    return schema


def _param_commands_json_type(param: click.Parameter) -> str | None:
    if isinstance(param, click.Option) and param.is_flag:
        return "flag"
    ptype = param.type
    if ptype is click.INT or isinstance(ptype, click.IntRange):
        return "int"
    if getattr(ptype, "name", "") == "bool":
        return "tri_state_bool"
    if getattr(ptype, "name", "") == "resource":
        return "resource"
    return None


def iter_leaf_commands(
    group: click.Group, prefix: tuple[str, ...] = ()
) -> list[tuple[tuple[str, ...], click.Command]]:
    """Return every non-hidden leaf command under `group` in declaration order."""
    leaves: list[tuple[tuple[str, ...], click.Command]] = []
    for name, cmd in group.commands.items():
        if cmd.hidden:
            continue
        path = (*prefix, name)
        if isinstance(cmd, click.Group):
            leaves.extend(iter_leaf_commands(cmd, path))
        else:
            leaves.append((path, cmd))
    return leaves


def resolve_command_by_path(
    root: click.Group, path_tokens: tuple[str, ...] | list[str]
) -> tuple[tuple[str, ...], click.Command] | None:
    """Resolve a command path (handling root aliases) from the live Click tree."""
    aliases = getattr(root, "ALIASES", {})
    current: click.Command = root
    resolved: list[str] = []
    for idx, token in enumerate(path_tokens):
        if not isinstance(current, click.Group):
            return None
        lookup = aliases.get(token, token) if idx == 0 else token
        nxt = current.commands.get(lookup)
        if nxt is None or nxt.hidden:
            return None
        resolved.append(lookup)
        current = nxt
    if not resolved:
        return None
    return tuple(resolved), current


def build_command_schema(path: tuple[str, ...], cmd: click.Command) -> dict[str, Any]:
    """Build a complete machine-readable JSON Schema descriptor for one leaf command."""
    label = " ".join(path)
    meta = get_command_meta(label)

    properties: dict[str, Any] = {}
    required: list[str] = []
    args_list: list[dict[str, Any]] = []
    options_list: list[dict[str, Any]] = []

    for param in cmd.params:
        if isinstance(param, click.Option) and param.hidden:
            continue
        pname = param.name or ""
        prop = _param_json_schema(param)
        if isinstance(param, click.Argument):
            properties[pname] = prop
            if param.required:
                required.append(pname)
            args_list.append(
                {
                    "name": pname,
                    "required": bool(param.required),
                    "schema": prop,
                }
            )
        elif isinstance(param, click.Option):
            long_flag = next((o for o in param.opts if o.startswith("--")), param.opts[0])
            properties[long_flag] = prop
            if param.required:
                required.append(long_flag)
            options_list.append(
                {
                    "name": long_flag,
                    "flags": list(param.opts),
                    "required": bool(param.required),
                    "schema": prop,
                }
            )

    return {
        "command": label,
        "path": list(path),
        "description": (cmd.help or cmd.short_help or "").strip(),
        "risk": meta.risk,
        "risk_dynamic": meta.risk_dynamic,
        "untrusted_output": meta.untrusted_output,
        "supports_dry_run": meta.supports_dry_run,
        "guild_scoped": meta.guild_scoped,
        "required_bot_permissions": list(meta.required_bot_permissions),
        "args": args_list,
        "options": options_list,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }


def list_command_summaries(
    root: click.Group,
    *,
    compact: bool = False,
    group_filter: str | None = None,
    risk_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Return a filterable list of command descriptors from the live Click tree."""
    rows: list[dict[str, Any]] = []
    for path, cmd in iter_leaf_commands(root):
        if group_filter and path[0] != group_filter:
            continue
        label = " ".join(path)
        meta = get_command_meta(label)
        if risk_filter and meta.risk != risk_filter:
            continue
        if compact:
            rows.append(
                {
                    "command": label,
                    "risk": meta.risk,
                    "description": (cmd.help or cmd.short_help or "").strip().splitlines()[0]
                    if (cmd.help or cmd.short_help)
                    else "",
                }
            )
        else:
            rows.append(
                {
                    "command": label,
                    "group": path[0],
                    "risk": meta.risk,
                    "untrusted_output": meta.untrusted_output,
                    "supports_dry_run": meta.supports_dry_run,
                    "required_bot_permissions": list(meta.required_bot_permissions),
                    "description": (cmd.help or cmd.short_help or "").strip(),
                }
            )
    return rows


def _serialize_leaf_for_commands_json(name: str, cmd: click.Command) -> dict[str, Any]:
    args: list[dict[str, Any]] = []
    options: list[dict[str, Any]] = []
    for param in cmd.params:
        if isinstance(param, click.Option) and param.hidden:
            continue
        if isinstance(param, click.Argument):
            entry: dict[str, Any] = {"name": param.name}
            t = _param_commands_json_type(param)
            if t:
                entry["type"] = t
            if param.required:
                entry["required"] = True
            args.append(entry)
        elif isinstance(param, click.Option):
            for flag in param.opts:
                opt_entry: dict[str, Any] = {"name": flag}
                t = _param_commands_json_type(param)
                if t:
                    opt_entry["type"] = t
                if param.required:
                    opt_entry["required"] = True
                if isinstance(param.type, click.Choice):
                    opt_entry["choices"] = list(param.type.choices)
                if (
                    isinstance(param.default, (str, int, float, bool))
                    and not param.is_flag
                    and not param.multiple
                ):
                    opt_entry["default"] = param.default
                options.append(opt_entry)
    return {
        "name": name,
        "description": (cmd.help or cmd.short_help or f"Run {name}").strip(),
        "args": args,
        "options": options,
    }


def _serialize_group_commands(group: click.Group) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for name, sub in group.commands.items():
        if sub.hidden:
            continue
        if isinstance(sub, click.Group):
            items.append(
                {
                    "name": name,
                    "description": (sub.help or sub.short_help or "").strip(),
                    "subcommands": _serialize_group_commands(sub),
                }
            )
        else:
            items.append(_serialize_leaf_for_commands_json(name, sub))
    return items


def build_commands_json(root: click.Group) -> dict[str, Any]:
    """Generate the canonical `commands.json` manifest directly from the live Click tree."""
    global_options: list[dict[str, Any]] = []
    for param in root.params:
        if not isinstance(param, click.Option) or param.hidden:
            continue
        for flag in param.opts:
            if flag in {"--version", "--help"}:
                continue
            entry: dict[str, Any] = {"name": flag}
            t = _param_commands_json_type(param)
            entry["type"] = t or "string"
            if isinstance(param.type, click.Choice):
                entry["choices"] = list(param.type.choices)
            if param.help:
                entry["description"] = param.help
            global_options.append(entry)

    groups: list[dict[str, Any]] = []
    for gname, gcmd in root.commands.items():
        if gcmd.hidden or not isinstance(gcmd, click.Group):
            continue
        groups.append(
            {
                "name": gname,
                "description": (gcmd.help or gcmd.short_help or "").strip(),
                "commands": _serialize_group_commands(gcmd),
            }
        )

    return {
        "name": "discord-cli",
        "version": __version__,
        "description": "Command-line tool for managing Discord servers via AI agents",
        "output_format": "json",
        "global_options": global_options,
        "command_groups": groups,
    }
