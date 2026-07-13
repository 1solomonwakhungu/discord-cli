"""Search commands."""

from __future__ import annotations

from typing import Any

import click
import discord

from discord_cli.models import get_channel, get_guild
from discord_cli.registry import invoke, registry


@registry.group("search")
def search_group() -> None:
    """Search messages and members."""


@search_group.command("messages")
@click.argument("query")
@click.option("--channel-id", type=int, help="Channel to search in")
@click.option("--limit", type=int, default=25, help="Max results")
@click.pass_context
def search_messages(ctx: click.Context, query: str, channel_id: int | None, limit: int) -> None:
    """Search messages in a channel."""
    invoke(ctx, action_search_messages, query=query, channel_id=channel_id, limit=limit)


@search_group.command("members")
@click.argument("query")
@click.option("--limit", type=int, default=25, help="Max results")
@click.pass_context
def search_members(ctx: click.Context, query: str, limit: int) -> None:
    """Search for members by name or nickname."""
    invoke(ctx, action_search_members, query=query, limit=limit)


async def action_search_messages(
    client: discord.Client,
    guild_id: int | None,
    query: str,
    channel_id: int | None,
    limit: int,
    **_: Any,
) -> list[dict[str, Any]]:
    guild = await get_guild(client, guild_id)
    channels = [get_channel(guild, channel_id)] if channel_id is not None else guild.text_channels
    results: list[dict[str, Any]] = []
    for channel in channels:
        if not hasattr(channel, "history"):
            continue
        async for message in channel.history(limit=limit):
            if query.lower() in message.content.lower():
                results.append(
                    {
                        "id": message.id,
                        "channel_id": channel.id,
                        "author_id": message.author.id,
                        "content": message.content[:200],
                        "created_at": message.created_at.isoformat(),
                    }
                )
                if len(results) >= limit:
                    return results
    return results


async def action_search_members(
    client: discord.Client, guild_id: int | None, query: str, limit: int, **_: Any
) -> list[dict[str, Any]]:
    guild = await get_guild(client, guild_id)
    query_lower = query.lower()
    members = [
        {
            "id": member.id,
            "name": member.name,
            "display_name": member.display_name,
            "nick": member.nick,
            "joined_at": member.joined_at.isoformat() if member.joined_at else None,
        }
        for member in guild.members
        if query_lower in member.name.lower()
        or (member.nick is not None and query_lower in member.nick.lower())
    ]
    return members[:limit]
