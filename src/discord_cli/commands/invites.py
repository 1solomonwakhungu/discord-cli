"""Invite management commands."""

from __future__ import annotations

from typing import Any

import click
import discord

from discord_cli.errors import CliError
from discord_cli.models import get_channel, get_guild
from discord_cli.registry import invoke, registry


@registry.group("invites")
def invites_group() -> None:
    """Manage server invites."""


@invites_group.command("list")
@click.pass_context
def invite_list(ctx: click.Context) -> None:
    """List all invites."""
    invoke(ctx, action_invite_list)


@invites_group.command("create")
@click.option("--channel-id", type=int, required=True, help="Channel to create invite for")
@click.option("--max-age", type=int, default=0, help="Max age in seconds (0=never)")
@click.option("--max-uses", type=int, default=0, help="Max uses (0=unlimited)")
@click.option("--temporary", is_flag=True, help="Temporary membership")
@click.pass_context
def invite_create(
    ctx: click.Context, channel_id: int, max_age: int, max_uses: int, temporary: bool
) -> None:
    """Create an invite."""
    invoke(
        ctx,
        action_invite_create,
        channel_id=channel_id,
        max_age=max_age,
        max_uses=max_uses,
        temporary=temporary,
    )


@invites_group.command("delete")
@click.argument("code")
@click.pass_context
def invite_delete(ctx: click.Context, code: str) -> None:
    """Delete an invite by code."""
    invoke(ctx, action_invite_delete, code=code)


async def action_invite_list(
    client: discord.Client, guild_id: int | None, **_: Any
) -> list[dict[str, Any]]:
    guild = await get_guild(client, guild_id)
    invites = await guild.invites()
    return [
        {
            "code": invite.code,
            "url": str(invite.url),
            "channel_id": invite.channel.id if invite.channel else None,
            "inviter_id": invite.inviter.id if invite.inviter else None,
            "max_uses": invite.max_uses,
            "uses": invite.uses,
            "max_age": invite.max_age,
            "temporary": invite.temporary,
            "created_at": invite.created_at.isoformat() if invite.created_at else None,
        }
        for invite in invites
    ]


async def action_invite_create(
    client: discord.Client,
    guild_id: int | None,
    channel_id: int,
    max_age: int,
    max_uses: int,
    temporary: bool,
    **_: Any,
) -> dict[str, str]:
    guild = await get_guild(client, guild_id)
    channel = get_channel(guild, channel_id)
    if not hasattr(channel, "create_invite"):
        raise CliError(f"Channel {channel_id} does not support invites")
    invite = await channel.create_invite(max_age=max_age, max_uses=max_uses, temporary=temporary)
    return {"code": invite.code, "url": str(invite.url)}


async def action_invite_delete(
    client: discord.Client, guild_id: int | None, code: str, **_: Any
) -> dict[str, str]:
    guild = await get_guild(client, guild_id)
    for invite in await guild.invites():
        if invite.code == code:
            await invite.delete(reason="discord_cli invite delete")
            return {"deleted": code}
    raise CliError(f"Invite {code} not found")
