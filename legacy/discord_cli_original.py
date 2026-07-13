#!/usr/bin/env python3
"""Headless Discord server management CLI."""

from __future__ import annotations

import argparse
import asyncio
import csv
import datetime as dt
import io
import json
import os
import re
import sys
import urllib.request
from typing import Any, Callable, Iterable

import discord


Action = Callable[..., Any]


class CliError(Exception):
    """Expected CLI/runtime error with a clean message."""


class ManagementClient(discord.Client):
    def __init__(self, action: Action, kwargs: dict[str, Any], intents: discord.Intents):
        super().__init__(intents=intents)
        self.action = action
        self.kwargs = kwargs
        self.result: Any = None
        self.error: dict[str, Any] | None = None

    async def on_ready(self) -> None:
        try:
            self.result = await self.action(self, **self.kwargs)
        except Exception as exc:  # noqa: BLE001 - user-facing CLI boundary
            self.error = {
                "type": exc.__class__.__name__,
                "message": str(exc),
            }
            if isinstance(exc, discord.HTTPException):
                self.error.update({"status": exc.status, "code": exc.code})
        finally:
            await self.close()


def load_token() -> str:
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if token:
        return token.strip()

    # Look for .env next to this script first, then cwd
    script_dir = os.path.dirname(os.path.abspath(__file__))
    for env_dir in (script_dir, os.getcwd()):
        env_path = os.path.join(env_dir, ".env")
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as env_file:
                for raw_line in env_file:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    if key.strip() == "DISCORD_BOT_TOKEN":
                        return value.strip().strip('"').strip("'")
    raise CliError("DISCORD_BOT_TOKEN not found in environment or .env")


def fallback_intents() -> discord.Intents:
    intents = discord.Intents.default()
    intents.guilds = True
    intents.reactions = True
    return intents


def run_bot(action: Action, kwargs: dict[str, Any]) -> tuple[Any, dict[str, Any] | None]:
    token = load_token()
    last_error: dict[str, Any] | None = None
    for intents in (discord.Intents.all(), fallback_intents()):
        client = ManagementClient(action, kwargs, intents)
        try:
            client.run(token, log_handler=None)
        except discord.PrivilegedIntentsRequired as exc:
            last_error = {"type": exc.__class__.__name__, "message": str(exc)}
            continue
        except Exception as exc:  # noqa: BLE001 - user-facing CLI boundary
            return None, {"type": exc.__class__.__name__, "message": str(exc)}
        if last_error and client.error is None and isinstance(client.result, dict):
            client.result.setdefault(
                "warning",
                "Retried with non-privileged intents because privileged intents are not enabled for this bot.",
            )
        return client.result, client.error
    return None, last_error


def snowflake(value: str | int | None, name: str = "id") -> int:
    if value is None:
        raise CliError(f"{name} is required")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise CliError(f"Invalid {name}: {value}") from exc


def bool_value(value: str | bool | None) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    lowered = value.lower()
    if lowered in {"1", "true", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def parse_color(value: str | None) -> discord.Color | None:
    if not value:
        return None
    text = value.strip().lstrip("#")
    if len(text) != 6 or not re.fullmatch(r"[0-9a-fA-F]{6}", text):
        raise CliError(f"Invalid color: {value}. Use HEX like #ff00aa.")
    return discord.Color(int(text, 16))


def parse_permissions(value: str | int | None) -> discord.Permissions | None:
    if value in (None, ""):
        return None
    if isinstance(value, int) or str(value).isdigit():
        return discord.Permissions(int(value))
    perms = discord.Permissions.none()
    for name in re.split(r"[, ]+", str(value).strip()):
        if not name:
            continue
        if not hasattr(perms, name):
            raise CliError(f"Unknown permission: {name}")
        setattr(perms, name, True)
    return perms


def parse_duration(value: str) -> dt.timedelta:
    match = re.fullmatch(r"\s*(\d+)\s*([smhdw])\s*", value.lower())
    if not match:
        raise CliError("Duration must look like 30s, 5m, 1h, 2d, or 1w")
    amount = int(match.group(1))
    unit = match.group(2)
    return {
        "s": dt.timedelta(seconds=amount),
        "m": dt.timedelta(minutes=amount),
        "h": dt.timedelta(hours=amount),
        "d": dt.timedelta(days=amount),
        "w": dt.timedelta(weeks=amount),
    }[unit]


def iso(value: Any) -> Any:
    if isinstance(value, dt.datetime):
        return value.isoformat()
    return value


def permissions_to_list(perms: discord.Permissions | discord.PermissionOverwrite) -> list[str]:
    return [name for name, allowed in perms if allowed is True]


def overwrite_to_dict(target: discord.Role | discord.Member, overwrite: discord.PermissionOverwrite) -> dict[str, Any]:
    allow, deny = overwrite.pair()
    return {
        "target_id": target.id,
        "target_name": getattr(target, "name", str(target)),
        "target_type": "role" if isinstance(target, discord.Role) else "member",
        "allow": permissions_to_list(allow),
        "deny": permissions_to_list(deny),
        "allow_value": allow.value,
        "deny_value": deny.value,
    }


def role_to_dict(role: discord.Role, include_permissions: bool = True) -> dict[str, Any]:
    data = {
        "id": role.id,
        "name": role.name,
        "color": str(role.color),
        "color_value": role.color.value,
        "position": role.position,
        "managed": role.managed,
        "mentionable": role.mentionable,
        "hoist": role.hoist,
        "member_count": len(role.members),
    }
    if include_permissions:
        data["permissions"] = permissions_to_list(role.permissions)
        data["permissions_value"] = role.permissions.value
    return data


def member_to_dict(member: discord.Member, detailed: bool = False) -> dict[str, Any]:
    data = {
        "id": member.id,
        "name": member.name,
        "display_name": member.display_name,
        "nick": member.nick,
        "bot": member.bot,
        "joined_at": iso(member.joined_at),
        "created_at": iso(member.created_at),
        "roles": [{"id": role.id, "name": role.name} for role in member.roles if role.name != "@everyone"],
        "top_role": {"id": member.top_role.id, "name": member.top_role.name} if member.top_role else None,
    }
    if detailed:
        data.update(
            {
                "status": str(member.status),
                "premium_since": iso(member.premium_since),
                "timed_out_until": iso(member.timed_out_until),
                "guild_permissions": permissions_to_list(member.guild_permissions),
                "guild_permissions_value": member.guild_permissions.value,
                "avatar_url": str(member.display_avatar.url) if member.display_avatar else None,
            }
        )
    return data


def channel_to_dict(channel: discord.abc.GuildChannel | discord.Thread, detailed: bool = False) -> dict[str, Any]:
    data = {
        "id": channel.id,
        "name": channel.name,
        "type": str(channel.type),
        "position": getattr(channel, "position", None),
        "category_id": getattr(getattr(channel, "category", None), "id", None),
        "category": getattr(getattr(channel, "category", None), "name", None),
        "topic": getattr(channel, "topic", None),
        "nsfw": getattr(channel, "nsfw", None),
        "slowmode_delay": getattr(channel, "slowmode_delay", None),
    }
    if isinstance(channel, discord.Thread):
        data.update(
            {
                "parent_id": channel.parent_id,
                "archived": channel.archived,
                "locked": channel.locked,
                "member_count": channel.member_count,
                "message_count": channel.message_count,
            }
        )
    if detailed and hasattr(channel, "overwrites"):
        data["overwrites"] = [
            overwrite_to_dict(target, overwrite) for target, overwrite in channel.overwrites.items()
        ]
    return data


def message_to_dict(message: discord.Message) -> dict[str, Any]:
    return {
        "id": message.id,
        "channel_id": message.channel.id,
        "guild_id": message.guild.id if message.guild else None,
        "author": {
            "id": message.author.id,
            "name": str(message.author),
            "bot": getattr(message.author, "bot", None),
        },
        "content": message.content,
        "created_at": iso(message.created_at),
        "edited_at": iso(message.edited_at),
        "pinned": message.pinned,
        "attachments": [{"url": a.url, "filename": a.filename, "size": a.size} for a in message.attachments],
        "embeds": [embed.to_dict() for embed in message.embeds],
        "reactions": [{"emoji": str(r.emoji), "count": r.count} for r in message.reactions],
    }


async def get_guild(client: discord.Client, guild_id: int | None) -> discord.Guild:
    if guild_id:
        guild = client.get_guild(guild_id)
        if guild is None:
            guild = await client.fetch_guild(guild_id)
        if guild is None:
            raise CliError(f"Guild not found: {guild_id}")
        return guild
    if not client.guilds:
        raise CliError("Bot is not in any guilds")
    return client.guilds[0]


def get_channel(guild: discord.Guild, channel_id: int) -> discord.abc.GuildChannel | discord.Thread:
    channel = guild.get_channel_or_thread(channel_id)
    if channel is None:
        raise CliError(f"Channel not found: {channel_id}")
    return channel


def get_category(guild: discord.Guild, category_id: int | None) -> discord.CategoryChannel | None:
    if category_id is None:
        return None
    category = guild.get_channel(category_id)
    if not isinstance(category, discord.CategoryChannel):
        raise CliError(f"Category not found: {category_id}")
    return category


async def get_member(guild: discord.Guild, member_id: int) -> discord.Member:
    member = guild.get_member(member_id)
    if member is None:
        member = await guild.fetch_member(member_id)
    return member


def get_role(guild: discord.Guild, role_id: int) -> discord.Role:
    role = guild.get_role(role_id)
    if role is None:
        raise CliError(f"Role not found: {role_id}")
    return role


async def get_message(guild: discord.Guild, channel_id: int, message_id: int) -> discord.Message:
    channel = get_channel(guild, channel_id)
    if not isinstance(channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel, discord.StageChannel)):
        raise CliError("Channel does not support messages")
    return await channel.fetch_message(message_id)


def edit_kwargs(args: argparse.Namespace, names: Iterable[str]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    for name in names:
        if hasattr(args, name):
            value = getattr(args, name)
            if value is not None:
                kwargs[name] = value
    return kwargs


async def action_channel_list(client: discord.Client, guild_id: int | None, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    return {"guild_id": guild.id, "channels": [channel_to_dict(c) for c in guild.channels]}


async def action_channel_create(client: discord.Client, guild_id: int | None, **kwargs: Any) -> Any:
    guild = await get_guild(client, guild_id)
    category = get_category(guild, kwargs.get("category"))
    common = {
        "category": category,
        "position": kwargs.get("position"),
        "reason": "discord_cli channel create",
    }
    common = {k: v for k, v in common.items() if v is not None}
    ctype = kwargs.get("type") or "text"
    name = kwargs["name"]
    if ctype == "text":
        channel = await guild.create_text_channel(
            name,
            topic=kwargs.get("topic"),
            nsfw=kwargs.get("nsfw", False),
            slowmode_delay=kwargs.get("slowmode") or 0,
            **common,
        )
    elif ctype == "voice":
        channel = await guild.create_voice_channel(name, **common)
    elif ctype == "stage":
        channel = await guild.create_stage_channel(name, **common)
    elif ctype == "forum":
        channel = await guild.create_forum_channel(
            name,
            topic=kwargs.get("topic"),
            nsfw=kwargs.get("nsfw", False),
            slowmode_delay=kwargs.get("slowmode") or 0,
            **common,
        )
    else:
        raise CliError(f"Unsupported channel type: {ctype}")
    return {"created": channel_to_dict(channel, detailed=True)}


async def action_channel_delete(client: discord.Client, guild_id: int | None, channel_id: int, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    channel = get_channel(guild, channel_id)
    data = channel_to_dict(channel)
    await channel.delete(reason="discord_cli channel delete")
    return {"deleted": data}


async def action_channel_edit(client: discord.Client, guild_id: int | None, channel_id: int, **kwargs: Any) -> Any:
    guild = await get_guild(client, guild_id)
    channel = get_channel(guild, channel_id)
    edits: dict[str, Any] = {}
    if kwargs.get("name") is not None:
        edits["name"] = kwargs["name"]
    if kwargs.get("topic") is not None and hasattr(channel, "topic"):
        edits["topic"] = kwargs["topic"]
    if kwargs.get("position") is not None:
        edits["position"] = kwargs["position"]
    if kwargs.get("slowmode") is not None and hasattr(channel, "slowmode_delay"):
        edits["slowmode_delay"] = kwargs["slowmode"]
    if kwargs.get("nsfw") is not None and hasattr(channel, "nsfw"):
        edits["nsfw"] = kwargs["nsfw"]
    if not edits:
        raise CliError("No edits provided")
    edited = await channel.edit(**edits, reason="discord_cli channel edit")
    return {"updated": channel_to_dict(edited or channel, detailed=True)}


async def action_channel_move(client: discord.Client, guild_id: int | None, channel_id: int, category: int, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    channel = get_channel(guild, channel_id)
    new_category = get_category(guild, category)
    await channel.edit(category=new_category, reason="discord_cli channel move")
    return {"updated": channel_to_dict(channel, detailed=True)}


async def action_channel_info(client: discord.Client, guild_id: int | None, channel_id: int, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    return channel_to_dict(get_channel(guild, channel_id), detailed=True)


async def action_category_list(client: discord.Client, guild_id: int | None, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    return {"guild_id": guild.id, "categories": [channel_to_dict(c, detailed=True) for c in guild.categories]}


async def action_category_create(client: discord.Client, guild_id: int | None, name: str, position: int | None, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    category = await guild.create_category(name, position=position, reason="discord_cli category create")
    return {"created": channel_to_dict(category, detailed=True)}


async def action_category_delete(client: discord.Client, guild_id: int | None, category_id: int, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    category = get_category(guild, category_id)
    data = channel_to_dict(category)
    await category.delete(reason="discord_cli category delete")
    return {"deleted": data}


async def action_category_edit(client: discord.Client, guild_id: int | None, category_id: int, **kwargs: Any) -> Any:
    guild = await get_guild(client, guild_id)
    category = get_category(guild, category_id)
    edits = {k: v for k, v in {"name": kwargs.get("name"), "position": kwargs.get("position")}.items() if v is not None}
    if not edits:
        raise CliError("No edits provided")
    await category.edit(**edits, reason="discord_cli category edit")
    return {"updated": channel_to_dict(category, detailed=True)}


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


async def action_role_delete(client: discord.Client, guild_id: int | None, role_id: int, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    role = get_role(guild, role_id)
    data = role_to_dict(role)
    await role.delete(reason="discord_cli role delete")
    return {"deleted": data}


async def action_role_edit(client: discord.Client, guild_id: int | None, role_id: int, **kwargs: Any) -> Any:
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


async def action_role_assign(client: discord.Client, guild_id: int | None, role_id: int, user_id: int, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    member = await get_member(guild, user_id)
    role = get_role(guild, role_id)
    await member.add_roles(role, reason="discord_cli role assign")
    return {"assigned": {"role": role_to_dict(role), "member": member_to_dict(member)}}


async def action_role_remove(client: discord.Client, guild_id: int | None, role_id: int, user_id: int, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    member = await get_member(guild, user_id)
    role = get_role(guild, role_id)
    await member.remove_roles(role, reason="discord_cli role remove")
    return {"removed": {"role": role_to_dict(role), "member": member_to_dict(member)}}


async def action_role_info(client: discord.Client, guild_id: int | None, role_id: int, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    return role_to_dict(get_role(guild, role_id))


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


async def action_member_kick(client: discord.Client, guild_id: int | None, member_id: int, reason: str | None, **_: Any) -> Any:
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


def embed_from_json(embed_json: str) -> discord.Embed:
    try:
        payload = json.loads(embed_json)
    except json.JSONDecodeError as exc:
        raise CliError(f"Invalid embed JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise CliError("Embed JSON must be an object")
    return discord.Embed.from_dict(payload)


async def action_message_send(
    client: discord.Client,
    guild_id: int | None,
    channel_id: int,
    content: str | None,
    embed_json: str | None,
    **_: Any,
) -> Any:
    guild = await get_guild(client, guild_id)
    channel = get_channel(guild, channel_id)
    if not hasattr(channel, "send"):
        raise CliError("Channel does not support sending messages")
    embed = embed_from_json(embed_json) if embed_json else None
    if content is None and embed is None:
        raise CliError("--content or --embed-json is required")
    message = await channel.send(content=content, embed=embed)
    return {"sent": message_to_dict(message)}


async def action_message_edit(
    client: discord.Client, guild_id: int | None, message_id: int, channel_id: int, content: str, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    message = await get_message(guild, channel_id, message_id)
    edited = await message.edit(content=content)
    return {"updated": message_to_dict(edited)}


async def action_message_delete(
    client: discord.Client, guild_id: int | None, message_id: int, channel_id: int, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    message = await get_message(guild, channel_id, message_id)
    data = message_to_dict(message)
    await message.delete()
    return {"deleted": data}


async def action_message_purge(
    client: discord.Client,
    guild_id: int | None,
    channel_id: int,
    limit: int,
    user_id: int | None,
    contains: str | None,
    **_: Any,
) -> Any:
    guild = await get_guild(client, guild_id)
    channel = get_channel(guild, channel_id)
    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
        raise CliError("Channel does not support purge")

    def check(message: discord.Message) -> bool:
        if user_id is not None and message.author.id != user_id:
            return False
        if contains is not None and contains not in message.content:
            return False
        return True

    deleted = await channel.purge(limit=limit, check=check, reason="discord_cli message purge")
    return {"deleted_count": len(deleted), "deleted": [message_to_dict(m) for m in deleted]}


async def action_message_fetch(
    client: discord.Client, guild_id: int | None, message_id: int, channel_id: int, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    return message_to_dict(await get_message(guild, channel_id, message_id))


async def action_message_pin(
    client: discord.Client, guild_id: int | None, message_id: int, channel_id: int, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    message = await get_message(guild, channel_id, message_id)
    await message.pin(reason="discord_cli message pin")
    return {"pinned": message_to_dict(message)}


async def action_message_unpin(
    client: discord.Client, guild_id: int | None, message_id: int, channel_id: int, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    message = await get_message(guild, channel_id, message_id)
    await message.unpin(reason="discord_cli message unpin")
    return {"unpinned": message_to_dict(message)}


async def action_message_react(
    client: discord.Client, guild_id: int | None, message_id: int, channel_id: int, emoji: str, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    message = await get_message(guild, channel_id, message_id)
    await message.add_reaction(emoji)
    return {"reacted": {"message_id": message.id, "emoji": emoji}}


async def action_guild_info(client: discord.Client, guild_id: int | None, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    owner = guild.owner or (await guild.fetch_member(guild.owner_id) if guild.owner_id else None)
    return {
        "id": guild.id,
        "name": guild.name,
        "description": guild.description,
        "owner": member_to_dict(owner) if owner else {"id": guild.owner_id},
        "member_count": guild.member_count,
        "channel_count": len(guild.channels),
        "role_count": len(guild.roles),
        "emoji_count": len(guild.emojis),
        "sticker_count": len(guild.stickers),
        "premium_tier": guild.premium_tier,
        "premium_subscription_count": guild.premium_subscription_count,
        "verification_level": str(guild.verification_level),
        "created_at": iso(guild.created_at),
        "features": list(guild.features),
        "icon_url": str(guild.icon.url) if guild.icon else None,
    }


async def action_guild_edit(client: discord.Client, guild_id: int | None, **kwargs: Any) -> Any:
    guild = await get_guild(client, guild_id)
    edits = {k: v for k, v in {"name": kwargs.get("name"), "description": kwargs.get("description")}.items() if v is not None}
    if not edits:
        raise CliError("No edits provided")
    await guild.edit(**edits, reason="discord_cli guild edit")
    return {"updated": await action_guild_info(client, guild.id)}


async def action_guild_emojis_list(client: discord.Client, guild_id: int | None, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    return {
        "guild_id": guild.id,
        "emojis": [
            {
                "id": emoji.id,
                "name": emoji.name,
                "animated": emoji.animated,
                "managed": emoji.managed,
                "available": emoji.available,
                "url": str(emoji.url),
                "roles": [{"id": r.id, "name": r.name} for r in emoji.roles],
            }
            for emoji in guild.emojis
        ],
    }


def read_image_bytes(source: str) -> bytes:
    if re.match(r"^https?://", source):
        with urllib.request.urlopen(source, timeout=30) as response:  # noqa: S310 - admin-provided source
            return response.read()
    with open(source, "rb") as image_file:
        return image_file.read()


async def action_guild_emojis_create(
    client: discord.Client, guild_id: int | None, name: str, image: str, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    emoji = await guild.create_custom_emoji(name=name, image=read_image_bytes(image), reason="discord_cli emoji create")
    return {"created": {"id": emoji.id, "name": emoji.name, "url": str(emoji.url), "animated": emoji.animated}}


async def action_guild_emojis_delete(client: discord.Client, guild_id: int | None, emoji_id: int, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    emoji = discord.utils.get(guild.emojis, id=emoji_id)
    if emoji is None:
        raise CliError(f"Emoji not found: {emoji_id}")
    data = {"id": emoji.id, "name": emoji.name}
    await emoji.delete(reason="discord_cli emoji delete")
    return {"deleted": data}


async def action_guild_stickers_list(client: discord.Client, guild_id: int | None, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    return {
        "guild_id": guild.id,
        "stickers": [
            {
                "id": sticker.id,
                "name": sticker.name,
                "description": sticker.description,
                "emoji": sticker.emoji,
                "format": str(sticker.format),
                "url": sticker.url,
            }
            for sticker in guild.stickers
        ],
    }


async def action_guild_bans_list(client: discord.Client, guild_id: int | None, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    bans = [entry async for entry in guild.bans(limit=None)]
    return {
        "guild_id": guild.id,
        "bans": [
            {"user": {"id": entry.user.id, "name": str(entry.user), "bot": entry.user.bot}, "reason": entry.reason}
            for entry in bans
        ],
    }


async def action_guild_regions(client: discord.Client, guild_id: int | None, **_: Any) -> Any:
    await get_guild(client, guild_id)
    route = discord.http.Route("GET", "/voice/regions")
    regions = await client.http.request(route)
    return {
        "regions": [
            {
                "id": r.get("id"),
                "name": r.get("name"),
                "vip": r.get("vip"),
                "optimal": r.get("optimal"),
                "deprecated": r.get("deprecated"),
                "custom": r.get("custom"),
            }
            for r in regions
        ]
    }


async def action_guild_prune(client: discord.Client, guild_id: int | None, days: int, dry_run: bool, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    if dry_run:
        count = await guild.estimate_pruned_members(days=days)
        return {"dry_run": True, "days": days, "pruned_member_count": count}
    count = await guild.prune_members(days=days, reason="discord_cli guild prune")
    return {"dry_run": False, "days": days, "pruned_member_count": count}


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


async def action_webhook_list(client: discord.Client, guild_id: int | None, channel_id: int | None, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    webhooks = await (get_channel(guild, channel_id).webhooks() if channel_id else guild.webhooks())
    return {"webhooks": [webhook_to_dict(w) for w in webhooks]}


def webhook_to_dict(webhook: discord.Webhook) -> dict[str, Any]:
    return {
        "id": webhook.id,
        "name": webhook.name,
        "channel_id": webhook.channel_id,
        "guild_id": webhook.guild_id,
        "user": {"id": webhook.user.id, "name": str(webhook.user)} if webhook.user else None,
        "url": webhook.url,
        "type": str(webhook.type),
        "created_at": iso(webhook.created_at),
    }


async def action_webhook_create(
    client: discord.Client, guild_id: int | None, channel_id: int, name: str, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    channel = get_channel(guild, channel_id)
    if not hasattr(channel, "create_webhook"):
        raise CliError("Channel does not support webhooks")
    webhook = await channel.create_webhook(name=name, reason="discord_cli webhook create")
    return {"created": webhook_to_dict(webhook)}


async def action_webhook_delete(client: discord.Client, guild_id: int | None, webhook_id: int, **_: Any) -> Any:
    await get_guild(client, guild_id)
    webhook = await client.fetch_webhook(webhook_id)
    data = webhook_to_dict(webhook)
    await webhook.delete(reason="discord_cli webhook delete")
    return {"deleted": data}


async def action_webhook_info(client: discord.Client, guild_id: int | None, webhook_id: int, **_: Any) -> Any:
    await get_guild(client, guild_id)
    return webhook_to_dict(await client.fetch_webhook(webhook_id))


async def action_invite_list(client: discord.Client, guild_id: int | None, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    invites = await guild.invites()
    return {"guild_id": guild.id, "invites": [invite_to_dict(i) for i in invites]}


def invite_to_dict(invite: discord.Invite) -> dict[str, Any]:
    return {
        "code": invite.code,
        "url": invite.url,
        "channel_id": invite.channel.id if invite.channel else None,
        "channel_name": invite.channel.name if invite.channel else None,
        "inviter": {"id": invite.inviter.id, "name": str(invite.inviter)} if invite.inviter else None,
        "uses": invite.uses,
        "max_uses": invite.max_uses,
        "max_age": invite.max_age,
        "temporary": invite.temporary,
        "created_at": iso(invite.created_at),
        "expires_at": iso(invite.expires_at),
    }


async def action_invite_create(
    client: discord.Client,
    guild_id: int | None,
    channel_id: int,
    max_age: int,
    max_uses: int,
    temporary: bool,
    **_: Any,
) -> Any:
    guild = await get_guild(client, guild_id)
    channel = get_channel(guild, channel_id)
    if not hasattr(channel, "create_invite"):
        raise CliError("Channel does not support invites")
    invite = await channel.create_invite(
        max_age=max_age,
        max_uses=max_uses,
        temporary=temporary,
        reason="discord_cli invite create",
    )
    return {"created": invite_to_dict(invite)}


async def action_invite_delete(client: discord.Client, guild_id: int | None, code: str, **_: Any) -> Any:
    await get_guild(client, guild_id)
    invite = await client.fetch_invite(code)
    data = invite_to_dict(invite)
    await invite.delete(reason="discord_cli invite delete")
    return {"deleted": data}


async def action_thread_list(client: discord.Client, guild_id: int | None, channel_id: int | None, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    threads = await guild.active_threads()
    if channel_id is not None:
        threads = [thread for thread in threads if thread.parent_id == channel_id or thread.id == channel_id]
    return {"threads": [channel_to_dict(t, detailed=True) for t in threads]}


async def action_thread_create(
    client: discord.Client,
    guild_id: int | None,
    channel_id: int,
    name: str,
    thread_type: str,
    **_: Any,
) -> Any:
    guild = await get_guild(client, guild_id)
    channel = get_channel(guild, channel_id)
    if not isinstance(channel, discord.TextChannel):
        raise CliError("Thread creation requires a text channel")
    ctype = discord.ChannelType.private_thread if thread_type == "private" else discord.ChannelType.public_thread
    thread = await channel.create_thread(name=name, type=ctype, reason="discord_cli thread create")
    return {"created": channel_to_dict(thread, detailed=True)}


async def action_thread_delete(client: discord.Client, guild_id: int | None, thread_id: int, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    thread = get_channel(guild, thread_id)
    if not isinstance(thread, discord.Thread):
        raise CliError(f"Thread not found: {thread_id}")
    data = channel_to_dict(thread)
    await thread.delete()
    return {"deleted": data}


async def action_thread_archive(client: discord.Client, guild_id: int | None, thread_id: int, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    thread = get_channel(guild, thread_id)
    if not isinstance(thread, discord.Thread):
        raise CliError(f"Thread not found: {thread_id}")
    await thread.edit(archived=True)
    return {"archived": channel_to_dict(thread, detailed=True)}


async def action_thread_unarchive(client: discord.Client, guild_id: int | None, thread_id: int, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    thread = get_channel(guild, thread_id)
    if not isinstance(thread, discord.Thread):
        raise CliError(f"Thread not found: {thread_id}")
    await thread.edit(archived=False)
    return {"unarchived": channel_to_dict(thread, detailed=True)}


async def action_thread_members(client: discord.Client, guild_id: int | None, thread_id: int, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    thread = get_channel(guild, thread_id)
    if not isinstance(thread, discord.Thread):
        raise CliError(f"Thread not found: {thread_id}")
    members = await thread.fetch_members()
    return {
        "thread": channel_to_dict(thread),
        "members": [
            {
                "id": member.id,
                "joined_at": iso(member.joined_at),
                "flags": member.flags.value,
            }
            for member in members
        ],
    }


async def action_search_messages(
    client: discord.Client, guild_id: int | None, channel_id: int, query: str, limit: int, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    channel = get_channel(guild, channel_id)
    if not hasattr(channel, "history"):
        raise CliError("Channel does not support history")
    matches = []
    async for message in channel.history(limit=limit):
        if query.lower() in message.content.lower():
            matches.append(message_to_dict(message))
    return {"query": query, "matches": matches}


async def action_search_members(client: discord.Client, guild_id: int | None, query: str, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    lowered = query.lower()
    results = []
    try:
        async for member in guild.fetch_members(limit=None):
            haystack = " ".join(filter(None, [member.name, member.display_name, member.nick])).lower()
            if lowered in haystack:
                results.append(member_to_dict(member))
        return {"query": query, "members": results}
    except discord.ClientException as exc:
        if "Intents.members" not in str(exc):
            raise
        for member in guild.members:
            haystack = " ".join(filter(None, [member.name, member.display_name, member.nick])).lower()
            if lowered in haystack:
                results.append(member_to_dict(member))
        return {
            "query": query,
            "members": results,
            "partial": True,
            "warning": "Member intent is not enabled for this bot; searched cached visible members only.",
        }


async def action_export_channel(
    client: discord.Client, guild_id: int | None, channel_id: int, limit: int, export_format: str, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    channel = get_channel(guild, channel_id)
    if not hasattr(channel, "history"):
        raise CliError("Channel does not support history")
    messages = [message_to_dict(m) async for m in channel.history(limit=limit, oldest_first=True)]
    if export_format == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=["id", "channel_id", "author_id", "author_name", "content", "created_at"])
        writer.writeheader()
        for message in messages:
            writer.writerow(
                {
                    "id": message["id"],
                    "channel_id": message["channel_id"],
                    "author_id": message["author"]["id"],
                    "author_name": message["author"]["name"],
                    "content": message["content"],
                    "created_at": message["created_at"],
                }
            )
        return {"format": "csv", "channel_id": channel_id, "content": output.getvalue()}
    return {"format": "json", "channel_id": channel_id, "messages": messages}


def add_common_id_arg(parser: argparse.ArgumentParser, dest: str) -> None:
    parser.add_argument(dest, type=lambda v: snowflake(v, dest))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Discord management CLI")
    parser.add_argument("--guild", dest="guild_id", type=lambda v: snowflake(v, "guild"), help="Guild/server ID")
    parser.add_argument("--human", action="store_true", help="Print a human-readable summary instead of JSON")
    subparsers = parser.add_subparsers(dest="resource", required=True)

    channel = subparsers.add_parser("channel")
    channel_sub = channel.add_subparsers(dest="command", required=True)
    channel_sub.add_parser("list").set_defaults(action=action_channel_list)
    p = channel_sub.add_parser("create")
    p.add_argument("name")
    p.add_argument("--type", choices=["text", "voice", "stage", "forum"], default="text")
    p.add_argument("--category", type=lambda v: snowflake(v, "category"))
    p.add_argument("--topic")
    p.add_argument("--position", type=int)
    p.add_argument("--nsfw", action="store_true")
    p.add_argument("--slowmode", type=int)
    p.set_defaults(action=action_channel_create)
    p = channel_sub.add_parser("delete")
    add_common_id_arg(p, "channel_id")
    p.set_defaults(action=action_channel_delete)
    p = channel_sub.add_parser("edit")
    add_common_id_arg(p, "channel_id")
    p.add_argument("--name")
    p.add_argument("--topic")
    p.add_argument("--position", type=int)
    p.add_argument("--slowmode", type=int)
    p.add_argument("--nsfw", type=bool_value)
    p.set_defaults(action=action_channel_edit)
    p = channel_sub.add_parser("move")
    add_common_id_arg(p, "channel_id")
    p.add_argument("--category", type=lambda v: snowflake(v, "category"), required=True)
    p.set_defaults(action=action_channel_move)
    p = channel_sub.add_parser("info")
    add_common_id_arg(p, "channel_id")
    p.set_defaults(action=action_channel_info)

    category = subparsers.add_parser("category")
    category_sub = category.add_subparsers(dest="command", required=True)
    category_sub.add_parser("list").set_defaults(action=action_category_list)
    p = category_sub.add_parser("create")
    p.add_argument("name")
    p.add_argument("--position", type=int)
    p.set_defaults(action=action_category_create)
    p = category_sub.add_parser("delete")
    add_common_id_arg(p, "category_id")
    p.set_defaults(action=action_category_delete)
    p = category_sub.add_parser("edit")
    add_common_id_arg(p, "category_id")
    p.add_argument("--name")
    p.add_argument("--position", type=int)
    p.set_defaults(action=action_category_edit)

    role = subparsers.add_parser("role")
    role_sub = role.add_subparsers(dest="command", required=True)
    role_sub.add_parser("list").set_defaults(action=action_role_list)
    p = role_sub.add_parser("create")
    p.add_argument("name")
    p.add_argument("--color")
    p.add_argument("--permissions")
    p.add_argument("--mentionable", action="store_true")
    p.add_argument("--hoist", action="store_true")
    p.set_defaults(action=action_role_create)
    p = role_sub.add_parser("delete")
    add_common_id_arg(p, "role_id")
    p.set_defaults(action=action_role_delete)
    p = role_sub.add_parser("edit")
    add_common_id_arg(p, "role_id")
    p.add_argument("--name")
    p.add_argument("--color")
    p.add_argument("--permissions")
    p.add_argument("--mentionable", type=bool_value)
    p.add_argument("--hoist", type=bool_value)
    p.set_defaults(action=action_role_edit)
    p = role_sub.add_parser("assign")
    p.add_argument("role_id", type=lambda v: snowflake(v, "role_id"))
    p.add_argument("user_id", type=lambda v: snowflake(v, "user_id"))
    p.set_defaults(action=action_role_assign)
    p = role_sub.add_parser("remove")
    p.add_argument("role_id", type=lambda v: snowflake(v, "role_id"))
    p.add_argument("user_id", type=lambda v: snowflake(v, "user_id"))
    p.set_defaults(action=action_role_remove)
    p = role_sub.add_parser("info")
    add_common_id_arg(p, "role_id")
    p.set_defaults(action=action_role_info)

    member = subparsers.add_parser("member")
    member_sub = member.add_subparsers(dest="command", required=True)
    member_sub.add_parser("list").set_defaults(action=action_member_list)
    p = member_sub.add_parser("info")
    add_common_id_arg(p, "member_id")
    p.set_defaults(action=action_member_info)
    p = member_sub.add_parser("kick")
    add_common_id_arg(p, "member_id")
    p.add_argument("--reason")
    p.set_defaults(action=action_member_kick)
    p = member_sub.add_parser("ban")
    add_common_id_arg(p, "member_id")
    p.add_argument("--reason")
    p.add_argument("--delete-message-days", type=int, default=0)
    p.set_defaults(action=action_member_ban)
    p = member_sub.add_parser("unban")
    p.add_argument("user_id", type=lambda v: snowflake(v, "user_id"))
    p.set_defaults(action=action_member_unban)
    p = member_sub.add_parser("timeout")
    add_common_id_arg(p, "member_id")
    p.add_argument("duration")
    p.add_argument("--reason")
    p.set_defaults(action=action_member_timeout)
    p = member_sub.add_parser("untimeout")
    add_common_id_arg(p, "member_id")
    p.set_defaults(action=action_member_untimeout)
    p = member_sub.add_parser("nickname")
    add_common_id_arg(p, "member_id")
    p.add_argument("nickname")
    p.set_defaults(action=action_member_nickname)
    p = member_sub.add_parser("roles")
    add_common_id_arg(p, "member_id")
    p.set_defaults(action=action_member_roles)

    message = subparsers.add_parser("message")
    message_sub = message.add_subparsers(dest="command", required=True)
    p = message_sub.add_parser("send")
    p.add_argument("channel_id", type=lambda v: snowflake(v, "channel_id"))
    p.add_argument("--content")
    p.add_argument("--embed-json")
    p.set_defaults(action=action_message_send)
    p = message_sub.add_parser("edit")
    p.add_argument("message_id", type=lambda v: snowflake(v, "message_id"))
    p.add_argument("--channel", dest="channel_id", type=lambda v: snowflake(v, "channel"), required=True)
    p.add_argument("--content", required=True)
    p.set_defaults(action=action_message_edit)
    p = message_sub.add_parser("delete")
    p.add_argument("message_id", type=lambda v: snowflake(v, "message_id"))
    p.add_argument("--channel", dest="channel_id", type=lambda v: snowflake(v, "channel"), required=True)
    p.set_defaults(action=action_message_delete)
    p = message_sub.add_parser("purge")
    p.add_argument("channel_id", type=lambda v: snowflake(v, "channel_id"))
    p.add_argument("--limit", type=int, required=True)
    p.add_argument("--user", dest="user_id", type=lambda v: snowflake(v, "user"))
    p.add_argument("--contains")
    p.set_defaults(action=action_message_purge)
    p = message_sub.add_parser("fetch")
    p.add_argument("message_id", type=lambda v: snowflake(v, "message_id"))
    p.add_argument("--channel", dest="channel_id", type=lambda v: snowflake(v, "channel"), required=True)
    p.set_defaults(action=action_message_fetch)
    p = message_sub.add_parser("pin")
    p.add_argument("message_id", type=lambda v: snowflake(v, "message_id"))
    p.add_argument("--channel", dest="channel_id", type=lambda v: snowflake(v, "channel"), required=True)
    p.set_defaults(action=action_message_pin)
    p = message_sub.add_parser("unpin")
    p.add_argument("message_id", type=lambda v: snowflake(v, "message_id"))
    p.add_argument("--channel", dest="channel_id", type=lambda v: snowflake(v, "channel"), required=True)
    p.set_defaults(action=action_message_unpin)
    p = message_sub.add_parser("react")
    p.add_argument("message_id", type=lambda v: snowflake(v, "message_id"))
    p.add_argument("--channel", dest="channel_id", type=lambda v: snowflake(v, "channel"), required=True)
    p.add_argument("--emoji", required=True)
    p.set_defaults(action=action_message_react)

    guild = subparsers.add_parser("guild")
    guild_sub = guild.add_subparsers(dest="command", required=True)
    guild_sub.add_parser("info").set_defaults(action=action_guild_info)
    p = guild_sub.add_parser("edit")
    p.add_argument("--name")
    p.add_argument("--description")
    p.set_defaults(action=action_guild_edit)
    emojis = guild_sub.add_parser("emojis")
    emojis_sub = emojis.add_subparsers(dest="emoji_command", required=True)
    emojis_sub.add_parser("list").set_defaults(action=action_guild_emojis_list)
    p = emojis_sub.add_parser("create")
    p.add_argument("name")
    p.add_argument("--image", required=True)
    p.set_defaults(action=action_guild_emojis_create)
    p = emojis_sub.add_parser("delete")
    p.add_argument("emoji_id", type=lambda v: snowflake(v, "emoji_id"))
    p.set_defaults(action=action_guild_emojis_delete)
    stickers = guild_sub.add_parser("stickers")
    stickers_sub = stickers.add_subparsers(dest="sticker_command", required=True)
    stickers_sub.add_parser("list").set_defaults(action=action_guild_stickers_list)
    bans = guild_sub.add_parser("bans")
    bans_sub = bans.add_subparsers(dest="ban_command", required=True)
    bans_sub.add_parser("list").set_defaults(action=action_guild_bans_list)
    guild_sub.add_parser("regions").set_defaults(action=action_guild_regions)
    p = guild_sub.add_parser("prune")
    p.add_argument("--days", type=int, required=True)
    p.add_argument("--dry-run", type=bool_value, default=True)
    p.set_defaults(action=action_guild_prune)

    permissions = subparsers.add_parser("permissions")
    permissions_sub = permissions.add_subparsers(dest="command", required=True)
    p = permissions_sub.add_parser("list")
    p.add_argument("--channel", dest="channel_id", type=lambda v: snowflake(v, "channel"), required=True)
    p.set_defaults(action=action_permissions_list)
    p = permissions_sub.add_parser("set")
    p.add_argument("--channel", dest="channel_id", type=lambda v: snowflake(v, "channel"), required=True)
    p.add_argument("--role", dest="role_id", type=lambda v: snowflake(v, "role"))
    p.add_argument("--user", dest="user_id", type=lambda v: snowflake(v, "user"))
    p.add_argument("--allow")
    p.add_argument("--deny")
    p.set_defaults(action=action_permissions_set)
    p = permissions_sub.add_parser("reset")
    p.add_argument("--channel", dest="channel_id", type=lambda v: snowflake(v, "channel"), required=True)
    p.add_argument("--role", dest="role_id", type=lambda v: snowflake(v, "role"))
    p.add_argument("--user", dest="user_id", type=lambda v: snowflake(v, "user"))
    p.set_defaults(action=action_permissions_reset)

    webhook = subparsers.add_parser("webhook")
    webhook_sub = webhook.add_subparsers(dest="command", required=True)
    p = webhook_sub.add_parser("list")
    p.add_argument("--channel", dest="channel_id", type=lambda v: snowflake(v, "channel"))
    p.set_defaults(action=action_webhook_list)
    p = webhook_sub.add_parser("create")
    p.add_argument("--channel", dest="channel_id", type=lambda v: snowflake(v, "channel"), required=True)
    p.add_argument("--name", required=True)
    p.set_defaults(action=action_webhook_create)
    p = webhook_sub.add_parser("delete")
    p.add_argument("webhook_id", type=lambda v: snowflake(v, "webhook_id"))
    p.set_defaults(action=action_webhook_delete)
    p = webhook_sub.add_parser("info")
    p.add_argument("webhook_id", type=lambda v: snowflake(v, "webhook_id"))
    p.set_defaults(action=action_webhook_info)

    invite = subparsers.add_parser("invite")
    invite_sub = invite.add_subparsers(dest="command", required=True)
    invite_sub.add_parser("list").set_defaults(action=action_invite_list)
    p = invite_sub.add_parser("create")
    p.add_argument("--channel", dest="channel_id", type=lambda v: snowflake(v, "channel"), required=True)
    p.add_argument("--max-age", type=int, default=0)
    p.add_argument("--max-uses", type=int, default=0)
    p.add_argument("--temporary", action="store_true")
    p.set_defaults(action=action_invite_create)
    p = invite_sub.add_parser("delete")
    p.add_argument("code")
    p.set_defaults(action=action_invite_delete)

    thread = subparsers.add_parser("thread")
    thread_sub = thread.add_subparsers(dest="command", required=True)
    p = thread_sub.add_parser("list")
    p.add_argument("--channel", dest="channel_id", type=lambda v: snowflake(v, "channel"))
    p.set_defaults(action=action_thread_list)
    p = thread_sub.add_parser("create")
    p.add_argument("channel_id", type=lambda v: snowflake(v, "channel_id"))
    p.add_argument("--name", required=True)
    p.add_argument("--type", dest="thread_type", choices=["public", "private"], default="public")
    p.set_defaults(action=action_thread_create)
    p = thread_sub.add_parser("delete")
    p.add_argument("thread_id", type=lambda v: snowflake(v, "thread_id"))
    p.set_defaults(action=action_thread_delete)
    p = thread_sub.add_parser("archive")
    p.add_argument("thread_id", type=lambda v: snowflake(v, "thread_id"))
    p.set_defaults(action=action_thread_archive)
    p = thread_sub.add_parser("unarchive")
    p.add_argument("thread_id", type=lambda v: snowflake(v, "thread_id"))
    p.set_defaults(action=action_thread_unarchive)
    p = thread_sub.add_parser("members")
    p.add_argument("thread_id", type=lambda v: snowflake(v, "thread_id"))
    p.set_defaults(action=action_thread_members)

    search = subparsers.add_parser("search")
    search_sub = search.add_subparsers(dest="command", required=True)
    p = search_sub.add_parser("messages")
    p.add_argument("--channel", dest="channel_id", type=lambda v: snowflake(v, "channel"), required=True)
    p.add_argument("--query", required=True)
    p.add_argument("--limit", type=int, required=True)
    p.set_defaults(action=action_search_messages)
    p = search_sub.add_parser("members")
    p.add_argument("--query", required=True)
    p.set_defaults(action=action_search_members)

    export = subparsers.add_parser("export")
    export_sub = export.add_subparsers(dest="command", required=True)
    p = export_sub.add_parser("channel")
    p.add_argument("channel_id", type=lambda v: snowflake(v, "channel_id"))
    p.add_argument("--limit", type=int, required=True)
    p.add_argument("--format", dest="export_format", choices=["json", "csv"], default="json")
    p.set_defaults(action=action_export_channel)

    return parser


def make_payload(result: Any = None, error: dict[str, Any] | None = None) -> dict[str, Any]:
    if error:
        return {"ok": False, "error": error}
    return {"ok": True, "data": result}


def print_human(payload: dict[str, Any]) -> None:
    try:
        from rich.console import Console
        from rich.table import Table
    except Exception:  # noqa: BLE001 - optional dependency fallback
        print(json.dumps(payload, indent=2, default=str))
        return

    console = Console()
    if not payload.get("ok"):
        console.print(f"[red]Error:[/red] {payload['error'].get('message')}")
        return
    data = payload.get("data")
    if isinstance(data, dict):
        list_key = next((k for k, v in data.items() if isinstance(v, list)), None)
        if list_key and data[list_key] and isinstance(data[list_key][0], dict):
            table = Table(title=list_key)
            rows = data[list_key]
            keys = list(rows[0].keys())[:8]
            for key in keys:
                table.add_column(str(key))
            for row in rows:
                table.add_row(*[json.dumps(row.get(key), default=str) if isinstance(row.get(key), (dict, list)) else str(row.get(key)) for key in keys])
            console.print(table)
            return
    console.print_json(json.dumps(data, default=str))


def namespace_to_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    excluded = {"human", "resource", "command", "emoji_command", "sticker_command", "ban_command", "action"}
    return {key: value for key, value in vars(args).items() if key not in excluded}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    kwargs = namespace_to_kwargs(args)
    result, error = run_bot(args.action, kwargs)
    payload = make_payload(result, error)
    if args.human:
        print_human(payload)
    else:
        print(json.dumps(payload, indent=2, default=str))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
