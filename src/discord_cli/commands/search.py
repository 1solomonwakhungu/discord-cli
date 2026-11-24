"""Search commands."""

from __future__ import annotations

import asyncio
from typing import Any

import click
import discord

from discord_cli.errors import CliError
from discord_cli.models import fetch_guild_channels, get_guild, is_rest_mode
from discord_cli.registry import invoke, registry
from discord_cli.resolvers import RESOURCE_ID, resolve_channel_selector

_SEARCH_CONCURRENCY = 4


@registry.group("search")
def search_group() -> None:
    """Search messages and members."""


@search_group.command("messages")
@click.argument("query")
@click.option("--channel-id", type=RESOURCE_ID, help="Channel ID or selector to search in")
@click.option("--limit", type=int, default=25, help="Max matched results to return")
@click.option(
    "--scan-limit",
    type=int,
    default=500,
    help="Max messages to scan per channel (0 for unlimited)",
)
@click.pass_context
def search_messages(
    ctx: click.Context, query: str, channel_id: int | str | None, limit: int, scan_limit: int
) -> None:
    """Search messages in a channel or across the guild."""
    invoke(
        ctx,
        action_search_messages,
        query=query,
        channel_id=channel_id,
        limit=limit,
        scan_limit=scan_limit,
    )


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
    channel_id: int | str | None,
    limit: int,
    scan_limit: int = 500,
    **_: Any,
) -> list[dict[str, Any]]:
    if limit <= 0:
        raise CliError("--limit must be a positive integer")
    if scan_limit < 0:
        raise CliError("--scan-limit must be >= 0")

    guild = await get_guild(client, guild_id)
    if channel_id is not None:
        channels: list[Any] = [await resolve_channel_selector(guild, channel_id, client=client)]
    else:
        from discord_cli.policy import get_allowed_channels

        all_channels = await fetch_guild_channels(guild, client=client)
        allow_channels = get_allowed_channels()
        channels = [
            c
            for c in all_channels
            if (
                isinstance(c, discord.TextChannel)
                or getattr(c, "type", None) == discord.ChannelType.text
            )
            and (allow_channels is None or c.id in allow_channels)
        ]

    query_lower = query.lower()
    history_limit: int | None = None if scan_limit == 0 else scan_limit
    semaphore = asyncio.Semaphore(_SEARCH_CONCURRENCY)

    async def _scan_channel(channel: Any) -> list[dict[str, Any]]:
        if not hasattr(channel, "history"):
            return []
        matches: list[dict[str, Any]] = []
        async with semaphore:
            try:
                async for message in channel.history(limit=history_limit):
                    if query_lower in (message.content or "").lower():
                        matches.append(
                            {
                                "id": message.id,
                                "channel_id": channel.id,
                                "author_id": message.author.id,
                                "content": message.content[:200],
                                "created_at": message.created_at.isoformat(),
                            }
                        )
                        if len(matches) >= limit:
                            break
            except (discord.Forbidden, discord.NotFound):
                return []
        return matches

    per_channel = await asyncio.gather(*(_scan_channel(ch) for ch in channels))
    results: list[dict[str, Any]] = []
    for channel_matches in per_channel:
        for item in channel_matches:
            results.append(item)
            if len(results) >= limit:
                return results
    return results


async def action_search_members(
    client: discord.Client, guild_id: int | None, query: str, limit: int, **_: Any
) -> list[dict[str, Any]]:
    if limit <= 0:
        raise CliError("--limit must be a positive integer")
    guild = await get_guild(client, guild_id)
    if is_rest_mode(client) or not guild.members:
        route = discord.http.Route("GET", "/guilds/{guild_id}/members/search", guild_id=guild.id)
        raw_members = await client.http.request(
            route, params={"query": query, "limit": min(limit, 1000)}
        )
        results: list[dict[str, Any]] = []
        for raw in raw_members or []:
            user = raw.get("user") or {}
            name = user.get("username", "")
            nick = raw.get("nick")
            global_name = user.get("global_name")
            results.append(
                {
                    "id": int(user["id"]),
                    "name": name,
                    "display_name": nick or global_name or name,
                    "nick": nick,
                    "joined_at": raw.get("joined_at"),
                }
            )
        return results[:limit]

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
