"""Member commands: list, info, kick, ban, unban, timeout, untimeout, nickname, roles."""

from __future__ import annotations

from typing import Any

import click
import discord

from discord_cli.errors import CliError
from discord_cli.models import (
    fetch_guild_roles,
    get_guild,
    get_member,
    is_rest_mode,
    iso,
    member_to_dict,
    parse_duration,
    role_to_dict,
)
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
def member_ban(
    ctx: click.Context, member_id: int, reason: str | None, delete_message_days: int
) -> None:
    invoke(
        ctx,
        action_member_ban,
        member_id=member_id,
        reason=reason,
        delete_message_days=delete_message_days,
    )


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


def _raw_member_to_dict(
    raw: dict[str, Any], roles_by_id: dict[int, discord.Role]
) -> dict[str, Any]:
    user = raw.get("user") or {}
    user_id = int(user["id"])
    name = user.get("username", "")
    nick = raw.get("nick")
    global_name = user.get("global_name")
    display_name = nick or global_name or name
    role_ids = [int(rid) for rid in raw.get("roles", [])]
    resolved_roles = [
        {"id": rid, "name": roles_by_id[rid].name if rid in roles_by_id else str(rid)}
        for rid in role_ids
    ]
    top_role_obj = max(
        (roles_by_id[rid] for rid in role_ids if rid in roles_by_id),
        key=lambda r: r.position,
        default=None,
    )
    return {
        "id": user_id,
        "name": name,
        "display_name": display_name,
        "nick": nick,
        "bot": bool(user.get("bot", False)),
        "joined_at": raw.get("joined_at"),
        "created_at": iso(discord.utils.snowflake_time(user_id)),
        "roles": resolved_roles,
        "top_role": {"id": top_role_obj.id, "name": top_role_obj.name} if top_role_obj else None,
    }


async def _fetch_members_rest(client: discord.Client, guild: discord.Guild) -> list[dict[str, Any]]:
    roles = await fetch_guild_roles(guild, client=client)
    roles_by_id = {r.id: r for r in roles}
    all_members: list[dict[str, Any]] = []
    after: int | None = None
    while True:
        batch = await client.http.get_members(guild.id, limit=1000, after=after)
        if not batch:
            break
        for raw in batch:
            all_members.append(_raw_member_to_dict(raw, roles_by_id))
        if len(batch) < 1000:
            break
        after = int(batch[-1]["user"]["id"])
    return all_members


async def action_member_list(client: discord.Client, guild_id: int | None, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    rest = is_rest_mode(client)
    if rest:
        try:
            members_data = await _fetch_members_rest(client, guild)
            return {"guild_id": guild.id, "members": members_data}
        except discord.Forbidden:
            return {
                "guild_id": guild.id,
                "members": [],
                "partial": True,
                "warning": (
                    "Server Members Intent is not enabled for this bot in the Discord Developer "
                    "Portal; unable to list guild members."
                ),
            }
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


async def action_member_info(
    client: discord.Client, guild_id: int | None, member_id: int, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    return member_to_dict(
        await get_member(guild, member_id), detailed=True, rest_mode=is_rest_mode(client)
    )


async def action_member_kick(
    client: discord.Client, guild_id: int | None, member_id: int, reason: str | None, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    member = await get_member(guild, member_id)
    data = member_to_dict(member, rest_mode=is_rest_mode(client))
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
    ban_reason = reason or "discord_cli member ban"
    delete_seconds = min(max(0, delete_message_days) * 86400, 604800)
    try:
        member = await get_member(guild, member_id)
    except (discord.NotFound, CliError):
        # Hackban: user is not currently in the guild.
        await guild.ban(
            discord.Object(id=member_id),
            reason=ban_reason,
            delete_message_seconds=delete_seconds,
        )
        return {"banned": {"id": member_id, "hackban": True}}

    data = member_to_dict(member, rest_mode=is_rest_mode(client))
    await member.ban(reason=ban_reason, delete_message_seconds=delete_seconds)
    return {"banned": data}


async def action_member_unban(
    client: discord.Client, guild_id: int | None, user_id: int, **_: Any
) -> Any:
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
    return {
        "timed_out": member_to_dict(member, detailed=True, rest_mode=is_rest_mode(client)),
        "until": iso(until),
    }


async def action_member_untimeout(
    client: discord.Client, guild_id: int | None, member_id: int, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    member = await get_member(guild, member_id)
    await member.timeout(None, reason="discord_cli member untimeout")
    return {"untimeout": member_to_dict(member, detailed=True, rest_mode=is_rest_mode(client))}


async def action_member_nickname(
    client: discord.Client, guild_id: int | None, member_id: int, nickname: str, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    member = await get_member(guild, member_id)
    await member.edit(nick=nickname or None, reason="discord_cli member nickname")
    return {"updated": member_to_dict(member, detailed=True, rest_mode=is_rest_mode(client))}


async def action_member_roles(
    client: discord.Client, guild_id: int | None, member_id: int, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    member = await get_member(guild, member_id)
    rest = is_rest_mode(client)
    return {
        "member": member_to_dict(member, rest_mode=rest),
        "roles": [role_to_dict(r, rest_mode=rest) for r in member.roles],
    }
