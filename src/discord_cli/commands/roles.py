"""Role commands: list, create, delete, edit, assign, remove, info."""

from __future__ import annotations

from typing import Any

import click
import discord

from discord_cli.errors import CliError
from discord_cli.models import (
    get_guild,
    get_member,
    get_role,
    member_to_dict,
    parse_color,
    parse_permissions,
    role_to_dict,
)
from discord_cli.registry import TRI_STATE_BOOL, invoke, registry


@registry.group("role")
def role_group() -> None:
    """Manage guild roles."""


@role_group.command("list")
@click.pass_context
def role_list(ctx: click.Context) -> None:
    invoke(ctx, action_role_list)


@role_group.command("create")
@click.argument("name")
@click.option("--color", default=None)
@click.option("--permissions", default=None)
@click.option("--mentionable", is_flag=True, default=False)
@click.option("--hoist", is_flag=True, default=False)
@click.pass_context
def role_create(
    ctx: click.Context,
    name: str,
    color: str | None,
    permissions: str | None,
    mentionable: bool,
    hoist: bool,
) -> None:
    invoke(
        ctx,
        action_role_create,
        name=name,
        color=color,
        permissions=permissions,
        mentionable=mentionable,
        hoist=hoist,
    )


@role_group.command("delete")
@click.argument("role_id", type=int)
@click.pass_context
def role_delete(ctx: click.Context, role_id: int) -> None:
    invoke(ctx, action_role_delete, role_id=role_id)


@role_group.command("edit")
@click.argument("role_id", type=int)
@click.option("--name", default=None)
@click.option("--color", default=None)
@click.option("--permissions", default=None)
@click.option("--mentionable", type=TRI_STATE_BOOL, default=None)
@click.option("--hoist", type=TRI_STATE_BOOL, default=None)
@click.pass_context
def role_edit(
    ctx: click.Context,
    role_id: int,
    name: str | None,
    color: str | None,
    permissions: str | None,
    mentionable: bool | None,
    hoist: bool | None,
) -> None:
    invoke(
        ctx,
        action_role_edit,
        role_id=role_id,
        name=name,
        color=color,
        permissions=permissions,
        mentionable=mentionable,
        hoist=hoist,
    )


@role_group.command("assign")
@click.argument("role_id", type=int)
@click.argument("user_id", type=int)
@click.pass_context
def role_assign(ctx: click.Context, role_id: int, user_id: int) -> None:
    invoke(ctx, action_role_assign, role_id=role_id, user_id=user_id)


@role_group.command("remove")
@click.argument("role_id", type=int)
@click.argument("user_id", type=int)
@click.pass_context
def role_remove(ctx: click.Context, role_id: int, user_id: int) -> None:
    invoke(ctx, action_role_remove, role_id=role_id, user_id=user_id)


@role_group.command("info")
@click.argument("role_id", type=int)
@click.pass_context
def role_info(ctx: click.Context, role_id: int) -> None:
    invoke(ctx, action_role_info, role_id=role_id)


async def action_role_list(client: discord.Client, guild_id: int | None, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    return {"guild_id": guild.id, "roles": [role_to_dict(r) for r in guild.roles]}


async def action_role_create(client: discord.Client, guild_id: int | None, **kwargs: Any) -> Any:
    guild = await get_guild(client, guild_id)
    role = await guild.create_role(
        name=kwargs["name"],
        colour=parse_color(kwargs.get("color")) or discord.Color.default(),
        permissions=parse_permissions(kwargs.get("permissions")) or discord.Permissions.none(),
        mentionable=kwargs.get("mentionable") or False,
        hoist=kwargs.get("hoist") or False,
        reason="discord_cli role create",
    )
    return {"created": role_to_dict(role)}


async def action_role_delete(
    client: discord.Client, guild_id: int | None, role_id: int, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    role = get_role(guild, role_id)
    data = role_to_dict(role)
    await role.delete(reason="discord_cli role delete")
    return {"deleted": data}


async def action_role_edit(
    client: discord.Client, guild_id: int | None, role_id: int, **kwargs: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    role = get_role(guild, role_id)
    edits: dict[str, Any] = {}
    if kwargs.get("name") is not None:
        edits["name"] = kwargs["name"]
    if kwargs.get("color") is not None:
        edits["colour"] = parse_color(kwargs["color"])
    if kwargs.get("permissions") is not None:
        edits["permissions"] = parse_permissions(kwargs["permissions"])
    if kwargs.get("mentionable") is not None:
        edits["mentionable"] = kwargs["mentionable"]
    if kwargs.get("hoist") is not None:
        edits["hoist"] = kwargs["hoist"]
    if not edits:
        raise CliError("No edits provided")
    await role.edit(**edits, reason="discord_cli role edit")
    return {"updated": role_to_dict(role)}


async def action_role_assign(
    client: discord.Client, guild_id: int | None, role_id: int, user_id: int, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    member = await get_member(guild, user_id)
    role = get_role(guild, role_id)
    await member.add_roles(role, reason="discord_cli role assign")
    return {"assigned": {"role": role_to_dict(role), "member": member_to_dict(member)}}


async def action_role_remove(
    client: discord.Client, guild_id: int | None, role_id: int, user_id: int, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    member = await get_member(guild, user_id)
    role = get_role(guild, role_id)
    await member.remove_roles(role, reason="discord_cli role remove")
    return {"removed": {"role": role_to_dict(role), "member": member_to_dict(member)}}


async def action_role_info(
    client: discord.Client, guild_id: int | None, role_id: int, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    return role_to_dict(get_role(guild, role_id))
