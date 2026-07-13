"""Export commands."""

from __future__ import annotations

import csv
import io
import json

import click

from ..client import run_bot
from ..output import output


@click.group()
def export() -> None:
    """Export channel data."""


@export.command("channel")
@click.argument("channel_id", type=int)
@click.option("--limit", type=int, default=100, help="Number of messages to export")
@click.option("--format", type=click.Choice(["json", "csv"]), default="json")
@click.pass_context
def export_channel(ctx: click.Context, channel_id: int, limit: int, fmt: str) -> None:
    """Export messages from a channel."""

    async def _action(client, **kwargs):
        guild = client.guilds[0]
        channel = guild.get_channel(channel_id)
        if not channel:
            raise ValueError(f"Channel {channel_id} not found")

        messages = []
        async for msg in channel.history(limit=limit):
            messages.append({
                "id": msg.id,
                "author_id": msg.author.id,
                "author_name": msg.author.name,
                "content": msg.content,
                "created_at": msg.created_at.isoformat(),
                "edited_at": msg.edited_at.isoformat() if msg.edited_at else None,
                "attachments": [
                    {"url": a.url, "filename": a.filename, "content_type": a.content_type}
                    for a in msg.attachments
                ],
                "embeds": len(msg.embeds),
                "pinned": msg.pinned,
            })

        if fmt == "csv":
            output_buf = io.StringIO()
            writer = csv.DictWriter(output_buf, fieldnames=["id", "author_id", "author_name", "content", "created_at", "pinned"])
            writer.writeheader()
            for m in messages:
                writer.writerow({k: m.get(k, "") for k in writer.fieldnames})
            return {"format": "csv", "count": len(messages), "data": output_buf.getvalue()}
        else:
            return {"format": "json", "count": len(messages), "messages": messages}

    result, error = run_bot(_action, ctx=ctx)
    output(result, error, ctx)
