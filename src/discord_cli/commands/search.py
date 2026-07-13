"""Search commands."""

from __future__ import annotations

import click

from ..client import run_bot
from ..output import output


@click.group()
def search() -> None:
    """Search messages and members."""


@search.command("messages")
@click.option("--channel-id", type=int, help="Channel to search in")
@click.option("--query", required=True, help="Search query")
@click.option("--limit", type=int, default=25, help="Max results")
@click.pass_context
def search_messages(ctx: click.Context, channel_id: int | None, query: str, limit: int) -> None:
    """Search messages in a channel."""

    async def _action(client, **kwargs):
        guild = client.guilds[0]
        results = []
        channels = [guild.get_channel(channel_id)] if channel_id else guild.text_channels
        for channel in channels:
            if not channel:
                continue
            async for msg in channel.history(limit=limit):
                if query.lower() in msg.content.lower():
                    results.append({
                        "id": msg.id,
                        "channel_id": channel.id,
                        "author_id": msg.author.id,
                        "content": msg.content[:200],
                        "created_at": msg.created_at.isoformat(),
                    })
                    if len(results) >= limit:
                        return results
        return results

    result, error = run_bot(_action, ctx=ctx)
    output(result, error, ctx)


@search.command("members")
@click.option("--query", required=True, help="Member name to search for")
@click.pass_context
def search_members(ctx: click.Context, query: str) -> None:
    """Search for members by name."""

    async def _action(client, **kwargs):
        guild = client.guilds[0]
        query_lower = query.lower()
        members = [
            {
                "id": m.id,
                "name": m.name,
                "display_name": m.display_name,
                "nick": m.nick,
                "joined_at": m.joined_at.isoformat() if m.joined_at else None,
            }
            for m in guild.members
            if query_lower in m.name.lower() or (m.nick and query_lower in m.nick.lower())
        ]
        return members

    result, error = run_bot(_action, ctx=ctx)
    output(result, error, ctx)
