"""Thread management commands."""

from __future__ import annotations

import click

from ..client import run_bot
from ..output import output


@click.group()
def threads() -> None:
    """Manage server threads."""


@threads.command("list")
@click.option("--channel-id", type=int, help="Filter by channel ID")
@click.pass_context
def list_threads(ctx: click.Context, channel_id: int | None) -> None:
    """List all threads."""

    async def _action(client, **kwargs):
        guild = client.guilds[0]
        result = []
        for channel in guild.text_channels:
            if channel_id and channel.id != channel_id:
                continue
            for thread in channel.threads:
                result.append({
                    "id": thread.id,
                    "name": thread.name,
                    "channel_id": thread.parent_id,
                    "archived": thread.archived,
                    "locked": thread.locked,
                    "member_count": thread.member_count,
                })
        return result

    result, error = run_bot(_action, ctx=ctx)
    output(result, error, ctx)


@threads.command("create")
@click.argument("channel_id", type=int)
@click.option("--name", required=True, help="Thread name")
@click.option("--type", type=click.Choice(["public", "private"]), default="public")
@click.pass_context
def create_thread(ctx: click.Context, channel_id: int, name: str, thread_type: str) -> None:
    """Create a thread in a channel."""

    async def _action(client, **kwargs):
        guild = client.guilds[0]
        channel = guild.get_channel(channel_id)
        if not channel:
            raise ValueError(f"Channel {channel_id} not found")
        thread = await channel.create_thread(
            name=name, type=discord.ChannelType.private_thread if thread_type == "private" else discord.ChannelType.public_thread
        )
        return {"id": thread.id, "name": thread.name}

    result, error = run_bot(_action, ctx=ctx)
    output(result, error, ctx)


@threads.command("delete")
@click.argument("thread_id", type=int)
@click.pass_context
def delete_thread(ctx: click.Context, thread_id: int) -> None:
    """Delete a thread."""

    async def _action(client, **kwargs):
        guild = client.guilds[0]
        thread = guild.get_thread(thread_id)
        if not thread:
            raise ValueError(f"Thread {thread_id} not found")
        await thread.delete()
        return {"deleted": thread_id}

    result, error = run_bot(_action, ctx=ctx)
    output(result, error, ctx)


@threads.command("archive")
@click.argument("thread_id", type=int)
@click.pass_context
def archive_thread(ctx: click.Context, thread_id: int) -> None:
    """Archive a thread."""

    async def _action(client, **kwargs):
        guild = client.guilds[0]
        thread = guild.get_thread(thread_id)
        if not thread:
            raise ValueError(f"Thread {thread_id} not found")
        await thread.edit(archived=True)
        return {"archived": thread_id}

    result, error = run_bot(_action, ctx=ctx)
    output(result, error, ctx)


@threads.command("unarchive")
@click.argument("thread_id", type=int)
@click.pass_context
def unarchive_thread(ctx: click.Context, thread_id: int) -> None:
    """Unarchive a thread."""

    async def _action(client, **kwargs):
        guild = client.guilds[0]
        thread = guild.get_thread(thread_id)
        if not thread:
            raise ValueError(f"Thread {thread_id} not found")
        await thread.edit(archived=False)
        return {"unarchived": thread_id}

    result, error = run_bot(_action, ctx=ctx)
    output(result, error, ctx)


@threads.command("members")
@click.argument("thread_id", type=int)
@click.pass_context
def thread_members(ctx: click.Context, thread_id: int) -> None:
    """List members of a thread."""

    async def _action(client, **kwargs):
        guild = client.guilds[0]
        thread = guild.get_thread(thread_id)
        if not thread:
            raise ValueError(f"Thread {thread_id} not found")
        members = await thread.fetch_members()
        return [{"id": m.id, "name": m.name} for m in members]

    result, error = run_bot(_action, ctx=ctx)
    output(result, error, ctx)
