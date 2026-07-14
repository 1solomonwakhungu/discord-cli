"""Thread management commands."""

from __future__ import annotations

from typing import Any

import click
import discord

from discord_cli.errors import CliError
from discord_cli.models import get_channel, get_guild
from discord_cli.registry import invoke, registry


@registry.group("threads")
def threads_group() -> None:
    """Manage server threads."""


@threads_group.command("list")
@click.option("--channel-id", type=int, help="Filter by channel ID")
@click.pass_context
def thread_list(ctx: click.Context, channel_id: int | None) -> None:
    """List all threads."""
    invoke(ctx, action_thread_list, channel_id=channel_id)


@threads_group.command("create")
@click.argument("name")
@click.option("--channel-id", type=int, required=True, help="Channel to create the thread in")
@click.option("--type", "thread_type", type=click.Choice(["public", "private"]), default="public")
@click.option(
    "--auto-archive",
    type=click.Choice(["60", "1440", "4320", "10080"]),
    default="1440",
    help="Minutes before auto-archiving",
)
@click.pass_context
def thread_create(
    ctx: click.Context, name: str, channel_id: int, thread_type: str, auto_archive: str
) -> None:
    """Create a thread in a channel."""
    invoke(
        ctx,
        action_thread_create,
        name=name,
        channel_id=channel_id,
        thread_type=thread_type,
        auto_archive=int(auto_archive),
    )


@threads_group.command("delete")
@click.argument("thread_id", type=int)
@click.pass_context
def thread_delete(ctx: click.Context, thread_id: int) -> None:
    """Delete a thread."""
    invoke(ctx, action_thread_delete, thread_id=thread_id)


@threads_group.command("archive")
@click.argument("thread_id", type=int)
@click.pass_context
def thread_archive(ctx: click.Context, thread_id: int) -> None:
    """Archive a thread."""
    invoke(ctx, action_thread_archive, thread_id=thread_id)


@threads_group.command("unarchive")
@click.argument("thread_id", type=int)
@click.pass_context
def thread_unarchive(ctx: click.Context, thread_id: int) -> None:
    """Unarchive a thread."""
    invoke(ctx, action_thread_unarchive, thread_id=thread_id)


@threads_group.command("members")
@click.argument("thread_id", type=int)
@click.pass_context
def thread_members(ctx: click.Context, thread_id: int) -> None:
    """List members of a thread."""
    invoke(ctx, action_thread_members, thread_id=thread_id)


async def action_thread_list(
    client: discord.Client, guild_id: int | None, channel_id: int | None, **_: Any
) -> list[dict[str, Any]]:
    guild = await get_guild(client, guild_id)
    result: list[dict[str, Any]] = []
    for channel in guild.text_channels:
        if channel_id is not None and channel.id != channel_id:
            continue
        for thread in channel.threads:
            result.append(
                {
                    "id": thread.id,
                    "name": thread.name,
                    "channel_id": thread.parent_id,
                    "archived": thread.archived,
                    "locked": thread.locked,
                    "member_count": thread.member_count,
                }
            )
    return result


async def action_thread_create(
    client: discord.Client,
    guild_id: int | None,
    name: str,
    channel_id: int,
    thread_type: str,
    auto_archive: int,
    **_: Any,
) -> dict[str, Any]:
    guild = await get_guild(client, guild_id)
    channel = get_channel(guild, channel_id)
    if not isinstance(channel, discord.TextChannel):
        raise CliError("Threads can only be created in text channels")
    thread = await channel.create_thread(
        name=name,
        type=(
            discord.ChannelType.private_thread
            if thread_type == "private"
            else discord.ChannelType.public_thread
        ),
        auto_archive_duration=auto_archive,  # type: ignore[arg-type]
    )
    return {"id": thread.id, "name": thread.name}


def get_thread(guild: discord.Guild, thread_id: int) -> discord.Thread:
    thread = guild.get_thread(thread_id)
    if thread is None:
        raise CliError(f"Thread {thread_id} not found")
    return thread


async def action_thread_delete(
    client: discord.Client, guild_id: int | None, thread_id: int, **_: Any
) -> dict[str, int]:
    thread = get_thread(await get_guild(client, guild_id), thread_id)
    await thread.delete(reason="discord_cli thread delete")
    return {"deleted": thread_id}


async def action_thread_archive(
    client: discord.Client, guild_id: int | None, thread_id: int, **_: Any
) -> dict[str, int]:
    thread = get_thread(await get_guild(client, guild_id), thread_id)
    await thread.edit(archived=True)
    return {"archived": thread_id}


async def action_thread_unarchive(
    client: discord.Client, guild_id: int | None, thread_id: int, **_: Any
) -> dict[str, int]:
    thread = get_thread(await get_guild(client, guild_id), thread_id)
    await thread.edit(archived=False)
    return {"unarchived": thread_id}


async def action_thread_members(
    client: discord.Client, guild_id: int | None, thread_id: int, **_: Any
) -> list[dict[str, Any]]:
    thread = get_thread(await get_guild(client, guild_id), thread_id)
    members = await thread.fetch_members()
    return [{"id": member.id, "name": member.name} for member in members]  # type: ignore[attr-defined]
