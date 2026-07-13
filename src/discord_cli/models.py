"""Shared Discord object lookups and JSON-serialization helpers used by command modules."""

from __future__ import annotations

import datetime as dt
import json
import re
import urllib.request
from typing import Any

import discord

from discord_cli.errors import CliError


def bool_value(value: str | bool | None) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    lowered = value.lower()
    if lowered in {"1", "true", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "no", "n", "off"}:
        return False
    raise CliError(f"Invalid boolean value: {value}. Use true or false.")


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


def overwrite_to_dict(
    target: discord.Role | discord.Member, overwrite: discord.PermissionOverwrite
) -> dict[str, Any]:
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


def embed_from_json(embed_json: str) -> discord.Embed:
    try:
        payload = json.loads(embed_json)
    except json.JSONDecodeError as exc:
        raise CliError(f"Invalid embed JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise CliError("Embed JSON must be an object")
    return discord.Embed.from_dict(payload)


def read_image_bytes(source: str) -> bytes:
    if re.match(r"^https?://", source):
        with urllib.request.urlopen(source, timeout=30) as response:  # noqa: S310 - admin-provided source
            return response.read()
    with open(source, "rb") as image_file:
        return image_file.read()


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
