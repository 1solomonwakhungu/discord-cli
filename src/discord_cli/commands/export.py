"""Export commands."""

from __future__ import annotations

import csv
import io
from typing import Any

import click
import discord

from discord_cli.errors import CliError
from discord_cli.models import get_channel, get_guild
from discord_cli.registry import invoke, registry


@registry.group("export")
def export_group() -> None:
    """Export channel data."""


@export_group.command("channel")
@click.argument("channel_id", type=int)
@click.option("--limit", type=int, default=100, help="Number of messages to export")
@click.option("--format", "output_format", type=click.Choice(["json", "csv"]), default="json")
@click.pass_context
def export_channel(ctx: click.Context, channel_id: int, limit: int, output_format: str) -> None:
    """Export messages from a channel."""
    invoke(
        ctx,
        action_export_channel,
        channel_id=channel_id,
        limit=limit,
        output_format=output_format,
    )


async def action_export_channel(
    client: discord.Client,
    guild_id: int | None,
    channel_id: int,
    limit: int,
    output_format: str,
    **_: Any,
) -> dict[str, Any]:
    guild = await get_guild(client, guild_id)
    channel = get_channel(guild, channel_id)
    if not hasattr(channel, "history"):
        raise CliError(f"Channel {channel_id} does not support message history")

    messages: list[dict[str, Any]] = []
    async for message in channel.history(limit=limit):
        messages.append(
            {
                "id": message.id,
                "author_id": message.author.id,
                "author_name": message.author.name,
                "content": message.content,
                "created_at": message.created_at.isoformat(),
                "edited_at": message.edited_at.isoformat() if message.edited_at else None,
                "attachments": [
                    {
                        "url": attachment.url,
                        "filename": attachment.filename,
                        "content_type": attachment.content_type,
                    }
                    for attachment in message.attachments
                ],
                "embeds": len(message.embeds),
                "pinned": message.pinned,
            }
        )

    if output_format == "csv":
        output_buffer = io.StringIO()
        writer = csv.DictWriter(
            output_buffer,
            fieldnames=["id", "author_id", "author_name", "content", "created_at", "pinned"],
        )
        writer.writeheader()
        for message in messages:
            writer.writerow({key: message.get(key, "") for key in writer.fieldnames})
        return {"format": "csv", "count": len(messages), "data": output_buffer.getvalue()}
    return {"format": "json", "count": len(messages), "messages": messages}
