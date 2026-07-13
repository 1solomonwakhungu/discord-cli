"""Member commands: list, info, kick, ban, unban, timeout, untimeout, nickname, roles."""

from __future__ import annotations

from typing import Any

import click
import discord

from discord_cli.models import get_guild, get_member, iso, member_to_dict, parse_duration, role_to_dict
from discord_cli.registry import invoke, registry


@registry.group("member")
def member_group() -> None:
    """Manage guild members."""


@member_group.command("list")
@click.pass_context
def member_list(ctx: click.Context) -> None:
    invoke(ctx, action_member_list)


@member_group.command("info")
@click.argument("member_id", type=int)
@click.pass_context
def member_info(ctx: click.Context, member_id: int) -> None:
    invoke(ctx, action_member_info, member_id=member_id)


@member_group.command("kick")
@click.argument("member_id", type=int)
@click.option("--reason", default=None)
@click.pass_context
def member_kick(ctx: click.Context, member_id: int, reason: str | None) -> None:
    invoke(ctx, action_member_kick, member_id=member_id, reason=reason)


@member_group.command("ban")
@click.argument("member_id", type=int)
@click.option("--reason", default=None)
@click.option("--delete-message-days", type=int, default=0)
@click.pass_context
def member_ban(ctx: click.Context, member_id: int, reason: str | None, delete_message_days: int) -> None:
    invoke(ctx, action_member_ban, member_id=member_id, reason=reason, delete_message_days=delete_message_days)


@member_group.command("unban")
@click.argument("user_id", type=int)
@click.pass_context
def member_unban(ctx: click.Context, user_id: int) -> None:
    invoke(ctx, action_member_unban, user_id=user_id)


@member_group.command("timeout")
@click.argument("member_id", type=int)
@click.argument("duration")
@click.option("--reason", default=None)
@click.pass_context
def member_timeout(ctx: click.Context, member_id: int, duration: str, reason: str | None) -> None:
    invoke(ctx, action_member_timeout, member_id=member_id, duration=duration, reason=reason)


@member_group.command("untimeout")
@click.argument("member_id", type=int)
@click.pass_context
def member_untimeout(ctx: click.Context, member_id: int) -> None:
    invoke(ctx, action_member_untimeout, member_id=member_id)


@member_group.command("nickname")
@click.argument("member_id", type=int)
@click.argument("nickname")
@click.pass_context
def member_nickname(ctx: click.Context, member_id: int, nickname: str) -> None:
    invoke(ctx, action_member_nickname, member_id=member_id, nickname=nickname)


@member_group.command("roles")
@click.argument("member_id", type=int)
@click.pass_context
def member_roles(ctx: click.Context, member_id: int) -> None:
    invoke(ctx, action_member_roles, member_id=member_id)


async def action_member_list(client: discord.Client, guild_id: int | None, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    try:
        members = [member async for member in guild.fetch_members(limit=None)]
        return {"guild_id": guild.id, "members": [member_to_dict(m) for m in members]}
    except discord.ClientException as exc:
        if "Intents.members" not in str(exc):
            raise
        return {
            "guild_id": guild.id,
            "members": [member_to_dict(m) for m in guild.members],
            "partial": True,
            "warning": "Member intent is not enabled for this bot; returned cached visible members only.",
        }


async def action_member_info(client: discord.Client, guild_id: int | None, member_id: int, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    return member_to_dict(await get_member(guild, member_id), detailed=True)


async def action_member_kick(
    client: discord.Client, guild_id: int | None, member_id: int, reason: str | None, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    member = await get_member(guild, member_id)
    data = member_to_dict(member)
    await member.kick(reason=reason or "discord_cli member kick")
    return {"kicked": data}


async def action_member_ban(
    client: discord.Client,
    guild_id: int | None,
    member_id: int,
    reason: str | None,
    delete_message_days: int,
    **_: Any,
) -> Any:
    guild = await get_guild(client, guild_id)
    member = await get_member(guild, member_id)
    data = member_to_dict(member)
    await member.ban(
        reason=reason or "discord_cli member ban",
        delete_message_seconds=max(0, delete_message_days) * 86400,
    )
    return {"banned": data}


async def action_member_unban(client: discord.Client, guild_id: int | None, user_id: int, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    user = await client.fetch_user(user_id)
    await guild.unban(user, reason="discord_cli member unban")
    return {"unbanned": {"id": user.id, "name": str(user)}}


async def action_member_timeout(
    client: discord.Client,
    guild_id: int | None,
    member_id: int,
    duration: str,
    reason: str | None,
    **_: Any,
) -> Any:
    guild = await get_guild(client, guild_id)
    member = await get_member(guild, member_id)
    until = discord.utils.utcnow() + parse_duration(duration)
    await member.timeout(until, reason=reason or "discord_cli member timeout")
    return {"timed_out": member_to_dict(member, detailed=True), "until": iso(until)}


async def action_member_untimeout(client: discord.Client, guild_id: int | None, member_id: int, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    member = await get_member(guild, member_id)
    await member.timeout(None, reason="discord_cli member untimeout")
    return {"untimeout": member_to_dict(member, detailed=True)}


async def action_member_nickname(
    client: discord.Client, guild_id: int | None, member_id: int, nickname: str, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    member = await get_member(guild, member_id)
    await member.edit(nick=nickname or None, reason="discord_cli member nickname")
    return {"updated": member_to_dict(member, detailed=True)}


async def action_member_roles(client: discord.Client, guild_id: int | None, member_id: int, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    member = await get_member(guild, member_id)
    return {"member": member_to_dict(member), "roles": [role_to_dict(r) for r in member.roles]}
