"""Permission overwrite commands: list, set, reset."""

from __future__ import annotations

from typing import Any

import click
import discord

from discord_cli.errors import CliError
from discord_cli.models import (
    channel_to_dict,
    get_guild,
    overwrite_to_dict,
    parse_permissions,
)
from discord_cli.registry import invoke, registry
from discord_cli.resolvers import (
    RESOURCE_ID,
    resolve_channel_selector,
    resolve_member_selector,
    resolve_role_selector,
)


@registry.group("permissions")
def permissions_group() -> None:
    """Manage per-channel permission overwrites."""


@permissions_group.command("list")
@click.option("--channel", "channel_id", type=RESOURCE_ID, required=True)
@click.pass_context
def permissions_list(ctx: click.Context, channel_id: int | str) -> None:
    invoke(ctx, action_permissions_list, channel_id=channel_id)


@permissions_group.command("set")
@click.option("--channel", "channel_id", type=RESOURCE_ID, required=True)
@click.option("--role", "role_id", type=RESOURCE_ID, default=None)
@click.option("--user", "user_id", type=RESOURCE_ID, default=None)
@click.option("--allow", default=None)
@click.option("--deny", default=None)
@click.pass_context
def permissions_set(
    ctx: click.Context,
    channel_id: int | str,
    role_id: int | str | None,
    user_id: int | str | None,
    allow: str | None,
    deny: str | None,
) -> None:
    invoke(
        ctx,
        action_permissions_set,
        channel_id=channel_id,
        role_id=role_id,
        user_id=user_id,
        allow=allow,
        deny=deny,
    )


@permissions_group.command("reset")
@click.option("--channel", "channel_id", type=RESOURCE_ID, required=True)
@click.option("--role", "role_id", type=RESOURCE_ID, default=None)
@click.option("--user", "user_id", type=RESOURCE_ID, default=None)
@click.pass_context
def permissions_reset(
    ctx: click.Context,
    channel_id: int | str,
    role_id: int | str | None,
    user_id: int | str | None,
) -> None:
    invoke(ctx, action_permissions_reset, channel_id=channel_id, role_id=role_id, user_id=user_id)


async def action_permissions_list(
    client: discord.Client, guild_id: int | None, channel_id: int | str, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    channel = await resolve_channel_selector(guild, channel_id, client=client)
    if not hasattr(channel, "overwrites"):
        raise CliError("Channel does not support permission overwrites")
    return {
        "channel": channel_to_dict(channel),
        "overwrites": [overwrite_to_dict(t, o) for t, o in channel.overwrites.items()],  # type: ignore[arg-type]
    }


async def action_permissions_set(
    client: discord.Client,
    guild_id: int | None,
    channel_id: int | str,
    role_id: int | str | None,
    user_id: int | str | None,
    allow: str | None,
    deny: str | None,
    reason: str | None = None,
    **_: Any,
) -> Any:
    guild = await get_guild(client, guild_id)
    channel = await resolve_channel_selector(guild, channel_id, client=client)
    if (role_id is None) == (user_id is None):
        raise CliError("Specify exactly one of --role or --user")
    target = (
        await resolve_role_selector(guild, role_id, client=client)
        if role_id is not None
        else await resolve_member_selector(guild, user_id, client=client)  # type: ignore[arg-type]
    )
    allow_perms = parse_permissions(allow) or discord.Permissions.none()
    deny_perms = parse_permissions(deny) or discord.Permissions.none()
    overwrite = discord.PermissionOverwrite.from_pair(allow_perms, deny_perms)
    await channel.set_permissions(
        target, overwrite=overwrite, reason=reason or "discord_cli permissions set"
    )  # type: ignore[union-attr]
    return {"set": overwrite_to_dict(target, overwrite)}


async def action_permissions_reset(
    client: discord.Client,
    guild_id: int | None,
    channel_id: int | str,
    role_id: int | str | None,
    user_id: int | str | None,
    reason: str | None = None,
    **_: Any,
) -> Any:
    guild = await get_guild(client, guild_id)
    channel = await resolve_channel_selector(guild, channel_id, client=client)
    if (role_id is None) == (user_id is None):
        raise CliError("Specify exactly one of --role or --user")
    target = (
        await resolve_role_selector(guild, role_id, client=client)
        if role_id is not None
        else await resolve_member_selector(guild, user_id, client=client)  # type: ignore[arg-type]
    )
    await channel.set_permissions(
        target, overwrite=None, reason=reason or "discord_cli permissions reset"
    )  # type: ignore[union-attr]
    return {"reset": {"target_id": target.id, "target_name": getattr(target, "name", str(target))}}
