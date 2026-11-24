"""Guild commands: info, edit, emojis, stickers, bans, regions, prune."""

from __future__ import annotations

from typing import Any

import click
import discord

from discord_cli.errors import CliError
from discord_cli.models import (
    bool_value,
    fetch_guild_channels,
    fetch_guild_roles,
    get_guild,
    invalidate_guild_cache,
    is_rest_mode,
    iso,
    member_to_dict,
    read_image_bytes_async,
)
from discord_cli.registry import invoke, registry


@registry.group("guild")
def guild_group() -> None:
    """Manage the guild itself: profile, emojis, stickers, bans, regions, pruning."""


@guild_group.command("info")
@click.pass_context
def guild_info(ctx: click.Context) -> None:
    invoke(ctx, action_guild_info)


@guild_group.command("edit")
@click.option("--name", default=None)
@click.option("--description", default=None)
@click.pass_context
def guild_edit(ctx: click.Context, name: str | None, description: str | None) -> None:
    invoke(ctx, action_guild_edit, name=name, description=description)


@guild_group.group("emojis")
def guild_emojis_group() -> None:
    """Manage custom emojis."""


@guild_emojis_group.command("list")
@click.pass_context
def guild_emojis_list(ctx: click.Context) -> None:
    invoke(ctx, action_guild_emojis_list)


@guild_emojis_group.command("create")
@click.argument("name")
@click.option("--image", required=True)
@click.pass_context
def guild_emojis_create(ctx: click.Context, name: str, image: str) -> None:
    invoke(ctx, action_guild_emojis_create, name=name, image=image)


@guild_emojis_group.command("delete")
@click.argument("emoji_id", type=int)
@click.pass_context
def guild_emojis_delete(ctx: click.Context, emoji_id: int) -> None:
    invoke(ctx, action_guild_emojis_delete, emoji_id=emoji_id)


@guild_group.group("stickers")
def guild_stickers_group() -> None:
    """Manage custom stickers."""


@guild_stickers_group.command("list")
@click.pass_context
def guild_stickers_list(ctx: click.Context) -> None:
    invoke(ctx, action_guild_stickers_list)


@guild_group.group("bans")
def guild_bans_group() -> None:
    """Inspect guild bans."""


@guild_bans_group.command("list")
@click.pass_context
def guild_bans_list(ctx: click.Context) -> None:
    invoke(ctx, action_guild_bans_list)


@guild_group.command("regions")
@click.pass_context
def guild_regions(ctx: click.Context) -> None:
    invoke(ctx, action_guild_regions)


@guild_group.command("prune")
@click.option("--days", type=int, required=True)
@click.option("--dry-run", default="true", help="true or false")
@click.pass_context
def guild_prune(ctx: click.Context, days: int, dry_run: str) -> None:
    invoke(ctx, action_guild_prune, days=days, dry_run=bool_value(dry_run))


async def _fetch_emojis(guild: discord.Guild) -> list[discord.Emoji]:
    if guild.emojis:
        return list(guild.emojis)
    if hasattr(guild, "fetch_emojis"):
        return list(await guild.fetch_emojis())
    return []


async def _fetch_stickers(guild: discord.Guild) -> list[discord.GuildSticker]:
    if guild.stickers:
        return list(guild.stickers)
    if hasattr(guild, "fetch_stickers"):
        return list(await guild.fetch_stickers())
    return []


async def action_guild_info(client: discord.Client, guild_id: int | None, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    rest = is_rest_mode(client)
    owner = guild.owner
    if owner is None and guild.owner_id:
        try:
            owner = await guild.fetch_member(guild.owner_id)
        except discord.HTTPException:
            owner = None
    channels = await fetch_guild_channels(guild, client=client)
    roles = await fetch_guild_roles(guild, client=client)
    emojis = await _fetch_emojis(guild)
    stickers = await _fetch_stickers(guild)
    member_count = guild.member_count
    if member_count is None:
        member_count = getattr(guild, "approximate_member_count", None)
    return {
        "id": guild.id,
        "name": guild.name,
        "description": guild.description,
        "owner": member_to_dict(owner, rest_mode=rest) if owner else {"id": guild.owner_id},
        "member_count": member_count,
        "channel_count": len(channels),
        "role_count": len(roles),
        "emoji_count": len(emojis),
        "sticker_count": len(stickers),
        "premium_tier": guild.premium_tier,
        "premium_subscription_count": guild.premium_subscription_count,
        "verification_level": str(guild.verification_level),
        "created_at": iso(guild.created_at),
        "features": list(guild.features),
        "icon_url": str(guild.icon.url) if guild.icon else None,
    }


async def action_guild_edit(client: discord.Client, guild_id: int | None, **kwargs: Any) -> Any:
    guild = await get_guild(client, guild_id)
    edits = {
        k: v
        for k, v in {"name": kwargs.get("name"), "description": kwargs.get("description")}.items()
        if v is not None
    }
    if not edits:
        raise CliError("No edits provided")
    await guild.edit(**edits, reason="discord_cli guild edit")
    invalidate_guild_cache(client, guild.id)
    return {"updated": await action_guild_info(client, guild.id)}


async def action_guild_emojis_list(client: discord.Client, guild_id: int | None, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    emojis = await _fetch_emojis(guild)
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
            for emoji in emojis
        ],
    }


async def action_guild_emojis_create(
    client: discord.Client, guild_id: int | None, name: str, image: str, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    image_bytes = await read_image_bytes_async(image)
    emoji = await guild.create_custom_emoji(
        name=name, image=image_bytes, reason="discord_cli emoji create"
    )
    return {
        "created": {
            "id": emoji.id,
            "name": emoji.name,
            "url": str(emoji.url),
            "animated": emoji.animated,
        }
    }


async def action_guild_emojis_delete(
    client: discord.Client, guild_id: int | None, emoji_id: int, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    emojis = await _fetch_emojis(guild)
    emoji = discord.utils.get(emojis, id=emoji_id)
    if emoji is None:
        raise CliError(f"Emoji not found: {emoji_id}")
    data = {"id": emoji.id, "name": emoji.name}
    await emoji.delete(reason="discord_cli emoji delete")
    return {"deleted": data}


async def action_guild_stickers_list(client: discord.Client, guild_id: int | None, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    stickers = await _fetch_stickers(guild)
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
            for sticker in stickers
        ],
    }


async def action_guild_bans_list(client: discord.Client, guild_id: int | None, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    bans = [entry async for entry in guild.bans(limit=None)]
    return {
        "guild_id": guild.id,
        "bans": [
            {
                "user": {"id": entry.user.id, "name": str(entry.user), "bot": entry.user.bot},
                "reason": entry.reason,
            }
            for entry in bans
        ],
    }


async def action_guild_regions(client: discord.Client, guild_id: int | None, **_: Any) -> Any:
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


async def action_guild_prune(
    client: discord.Client, guild_id: int | None, days: int, dry_run: bool, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    if dry_run:
        count = await guild.estimate_pruned_members(days=days)
        return {"dry_run": True, "days": days, "pruned_member_count": count}
    count = await guild.prune_members(days=days, reason="discord_cli guild prune")
    return {"dry_run": False, "days": days, "pruned_member_count": count}
