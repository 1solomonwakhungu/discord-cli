"""Permission overwrite commands: list, set, reset."""

from __future__ import annotations

from typing import Any

import click
import discord

from discord_cli.errors import CliError
from discord_cli.models import channel_to_dict, get_channel, get_guild, get_member, get_role, overwrite_to_dict, parse_permissions
from discord_cli.registry import invoke, registry


@registry.group("permissions")
def permissions_group() -> None:
    """Manage per-channel permission overwrites."""


@permissions_group.command("list")
@click.option("--channel", "channel_id", type=int, required=True)
@click.pass_context
def permissions_list(ctx: click.Context, channel_id: int) -> None:
    invoke(ctx, action_permissions_list, channel_id=channel_id)


@permissions_group.command("set")
@click.option("--channel", "channel_id", type=int, required=True)
@click.option("--role", "role_id", type=int, default=None)
@click.option("--user", "user_id", type=int, default=None)
@click.option("--allow", default=None)
@click.option("--deny", default=None)
@click.pass_context
def permissions_set(
    ctx: click.Context,
    channel_id: int,
    role_id: int | None,
    user_id: int | None,
    allow: str | None,
    deny: str | None,
) -> None:
    invoke(ctx, action_permissions_set, channel_id=channel_id, role_id=role_id, user_id=user_id, allow=allow, deny=deny)


@permissions_group.command("reset")
@click.option("--channel", "channel_id", type=int, required=True)
@click.option("--role", "role_id", type=int, default=None)
@click.option("--user", "user_id", type=int, default=None)
@click.pass_context
def permissions_reset(ctx: click.Context, channel_id: int, role_id: int | None, user_id: int | None) -> None:
    invoke(ctx, action_permissions_reset, channel_id=channel_id, role_id=role_id, user_id=user_id)


async def action_permissions_list(client: discord.Client, guild_id: int | None, channel_id: int, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    channel = get_channel(guild, channel_id)
    if not hasattr(channel, "overwrites"):
        raise CliError("Channel does not support permission overwrites")
    return {"channel": channel_to_dict(channel), "overwrites": [overwrite_to_dict(t, o) for t, o in channel.overwrites.items()]}


async def action_permissions_set(
    client: discord.Client,
    guild_id: int | None,
    channel_id: int,
    role_id: int | None,
    user_id: int | None,
    allow: str | None,
    deny: str | None,
    **_: Any,
) -> Any:
    guild = await get_guild(client, guild_id)
    channel = get_channel(guild, channel_id)
    if (role_id is None) == (user_id is None):
        raise CliError("Specify exactly one of --role or --user")
    target = get_role(guild, role_id) if role_id is not None else await get_member(guild, user_id)
    allow_perms = parse_permissions(allow) or discord.Permissions.none()
    deny_perms = parse_permissions(deny) or discord.Permissions.none()
    overwrite = discord.PermissionOverwrite.from_pair(allow_perms, deny_perms)
    await channel.set_permissions(target, overwrite=overwrite, reason="discord_cli permissions set")
    return {"set": overwrite_to_dict(target, overwrite)}


async def action_permissions_reset(
    client: discord.Client,
    guild_id: int | None,
    channel_id: int,
    role_id: int | None,
    user_id: int | None,
    **_: Any,
) -> Any:
    guild = await get_guild(client, guild_id)
    channel = get_channel(guild, channel_id)
    if (role_id is None) == (user_id is None):
        raise CliError("Specify exactly one of --role or --user")
    target = get_role(guild, role_id) if role_id is not None else await get_member(guild, user_id)
    await channel.set_permissions(target, overwrite=None, reason="discord_cli permissions reset")
    return {"reset": {"target_id": target.id, "target_name": getattr(target, "name", str(target))}}
