"""Thread management commands."""

from __future__ import annotations

from typing import Any

import click
import discord

from discord_cli.errors import CliError
from discord_cli.models import fetch_guild_channels, get_guild, iso, resolve_channel
from discord_cli.registry import invoke, registry
from discord_cli.resolvers import RESOURCE_ID, resolve_channel_selector


@registry.group("threads")
def threads_group() -> None:
    """Manage server threads."""


@threads_group.command("list")
@click.option("--channel-id", type=RESOURCE_ID, help="Filter by channel ID or selector")
@click.pass_context
def thread_list(ctx: click.Context, channel_id: int | str | None) -> None:
    """List all threads."""
    invoke(ctx, action_thread_list, channel_id=channel_id)


@threads_group.command("create")
@click.argument("name")
@click.option(
    "--channel-id",
    type=RESOURCE_ID,
    required=True,
    help="Channel ID or selector to create thread in",
)
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


def _thread_to_summary(thread: discord.Thread) -> dict[str, Any]:
    return {
        "id": thread.id,
        "name": thread.name,
        "channel_id": thread.parent_id,
        "archived": thread.archived,
        "locked": thread.locked,
        "member_count": thread.member_count,
    }


async def action_thread_list(
    client: discord.Client, guild_id: int | None, channel_id: int | str | None, **_: Any
) -> list[dict[str, Any]]:
    guild = await get_guild(client, guild_id)
    resolved_channel_id: int | None = None
    if channel_id is not None:
        resolved_channel = await resolve_channel_selector(guild, channel_id, client=client)
        resolved_channel_id = resolved_channel.id
    threads: list[discord.Thread] = []

    active_fetcher = getattr(guild, "active_threads", None)
    if callable(active_fetcher):
        try:
            fetched = await active_fetcher()
            if isinstance(fetched, list):
                threads = fetched
        except (TypeError, discord.HTTPException):
            threads = []

    if not threads:
        # Fallback to channel cache (text + forum channels).
        channels = await fetch_guild_channels(guild, client=client)
        for channel in channels:
            for thread in getattr(channel, "threads", []):
                threads.append(thread)

    result: list[dict[str, Any]] = []
    seen: set[int] = set()
    for thread in threads:
        if thread.id in seen:
            continue
        if resolved_channel_id is not None and thread.parent_id != resolved_channel_id:
            continue
        seen.add(thread.id)
        result.append(_thread_to_summary(thread))
    return result


async def action_thread_create(
    client: discord.Client,
    guild_id: int | None,
    name: str,
    channel_id: int | str,
    thread_type: str,
    auto_archive: int,
    **_: Any,
) -> dict[str, Any]:
    guild = await get_guild(client, guild_id)
    channel = await resolve_channel_selector(guild, channel_id, client=client)
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


async def resolve_thread(
    client: discord.Client, guild: discord.Guild, thread_id: int
) -> discord.Thread:
    """Resolve an active or archived thread via cache first, then REST fetch."""
    thread = guild.get_thread(thread_id)
    if isinstance(thread, discord.Thread):
        return thread
    try:
        fetched = await resolve_channel(guild, thread_id, client=client)
    except CliError:
        raise CliError(f"Thread {thread_id} not found") from None
    if not isinstance(fetched, discord.Thread):
        raise CliError(f"Thread {thread_id} not found")
    return fetched


async def action_thread_delete(
    client: discord.Client,
    guild_id: int | None,
    thread_id: int,
    reason: str | None = None,
    **_: Any,
) -> dict[str, int]:
    guild = await get_guild(client, guild_id)
    thread = await resolve_thread(client, guild, thread_id)
    await thread.delete(reason=reason or "discord_cli thread delete")
    return {"deleted": thread_id}


async def action_thread_archive(
    client: discord.Client, guild_id: int | None, thread_id: int, **_: Any
) -> dict[str, int]:
    guild = await get_guild(client, guild_id)
    thread = await resolve_thread(client, guild, thread_id)
    await thread.edit(archived=True)
    return {"archived": thread_id}


async def action_thread_unarchive(
    client: discord.Client, guild_id: int | None, thread_id: int, **_: Any
) -> dict[str, int]:
    guild = await get_guild(client, guild_id)
    thread = await resolve_thread(client, guild, thread_id)
    await thread.edit(archived=False)
    return {"unarchived": thread_id}


async def action_thread_members(
    client: discord.Client, guild_id: int | None, thread_id: int, **_: Any
) -> list[dict[str, Any]]:
    guild = await get_guild(client, guild_id)
    thread = await resolve_thread(client, guild, thread_id)
    members = await thread.fetch_members()
    rows: list[dict[str, Any]] = []
    for member in members:
        name = getattr(member, "name", None)
        if name is None:
            cached = guild.get_member(member.id)
            if cached is not None:
                name = cached.name
        rows.append(
            {
                "id": member.id,
                "name": name,
                "joined_at": iso(getattr(member, "joined_at", None)),
            }
        )
    return rows
