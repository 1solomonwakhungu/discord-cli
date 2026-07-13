"""Message commands: send, edit, delete, purge, fetch, pin, unpin, react."""

from __future__ import annotations

from typing import Any

import click
import discord

from discord_cli.errors import CliError
from discord_cli.models import embed_from_json, get_channel, get_guild, get_message, message_to_dict
from discord_cli.registry import invoke, registry


@registry.group("message")
def message_group() -> None:
    """Send and manage messages."""


@message_group.command("send")
@click.argument("channel_id", type=int)
@click.option("--content", default=None)
@click.option("--embed-json", default=None)
@click.pass_context
def message_send(ctx: click.Context, channel_id: int, content: str | None, embed_json: str | None) -> None:
    invoke(ctx, action_message_send, channel_id=channel_id, content=content, embed_json=embed_json)


@message_group.command("edit")
@click.argument("message_id", type=int)
@click.option("--channel", "channel_id", type=int, required=True)
@click.option("--content", required=True)
@click.pass_context
def message_edit(ctx: click.Context, message_id: int, channel_id: int, content: str) -> None:
    invoke(ctx, action_message_edit, message_id=message_id, channel_id=channel_id, content=content)


@message_group.command("delete")
@click.argument("message_id", type=int)
@click.option("--channel", "channel_id", type=int, required=True)
@click.pass_context
def message_delete(ctx: click.Context, message_id: int, channel_id: int) -> None:
    invoke(ctx, action_message_delete, message_id=message_id, channel_id=channel_id)


@message_group.command("purge")
@click.argument("channel_id", type=int)
@click.option("--limit", type=int, required=True)
@click.option("--user", "user_id", type=int, default=None)
@click.option("--contains", default=None)
@click.pass_context
def message_purge(
    ctx: click.Context, channel_id: int, limit: int, user_id: int | None, contains: str | None
) -> None:
    invoke(ctx, action_message_purge, channel_id=channel_id, limit=limit, user_id=user_id, contains=contains)


@message_group.command("fetch")
@click.argument("message_id", type=int)
@click.option("--channel", "channel_id", type=int, required=True)
@click.pass_context
def message_fetch(ctx: click.Context, message_id: int, channel_id: int) -> None:
    invoke(ctx, action_message_fetch, message_id=message_id, channel_id=channel_id)


@message_group.command("pin")
@click.argument("message_id", type=int)
@click.option("--channel", "channel_id", type=int, required=True)
@click.pass_context
def message_pin(ctx: click.Context, message_id: int, channel_id: int) -> None:
    invoke(ctx, action_message_pin, message_id=message_id, channel_id=channel_id)


@message_group.command("unpin")
@click.argument("message_id", type=int)
@click.option("--channel", "channel_id", type=int, required=True)
@click.pass_context
def message_unpin(ctx: click.Context, message_id: int, channel_id: int) -> None:
    invoke(ctx, action_message_unpin, message_id=message_id, channel_id=channel_id)


@message_group.command("react")
@click.argument("message_id", type=int)
@click.option("--channel", "channel_id", type=int, required=True)
@click.option("--emoji", required=True)
@click.pass_context
def message_react(ctx: click.Context, message_id: int, channel_id: int, emoji: str) -> None:
    invoke(ctx, action_message_react, message_id=message_id, channel_id=channel_id, emoji=emoji)


async def action_message_send(
    client: discord.Client,
    guild_id: int | None,
    channel_id: int,
    content: str | None,
    embed_json: str | None,
    **_: Any,
) -> Any:
    guild = await get_guild(client, guild_id)
    channel = get_channel(guild, channel_id)
    if not hasattr(channel, "send"):
        raise CliError("Channel does not support sending messages")
    embed = embed_from_json(embed_json) if embed_json else None
    if content is None and embed is None:
        raise CliError("--content or --embed-json is required")
    message = await channel.send(content=content, embed=embed)
    return {"sent": message_to_dict(message)}


async def action_message_edit(
    client: discord.Client, guild_id: int | None, message_id: int, channel_id: int, content: str, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    message = await get_message(guild, channel_id, message_id)
    edited = await message.edit(content=content)
    return {"updated": message_to_dict(edited)}


async def action_message_delete(
    client: discord.Client, guild_id: int | None, message_id: int, channel_id: int, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    message = await get_message(guild, channel_id, message_id)
    data = message_to_dict(message)
    await message.delete()
    return {"deleted": data}


async def action_message_purge(
    client: discord.Client,
    guild_id: int | None,
    channel_id: int,
    limit: int,
    user_id: int | None,
    contains: str | None,
    **_: Any,
) -> Any:
    guild = await get_guild(client, guild_id)
    channel = get_channel(guild, channel_id)
    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
        raise CliError("Channel does not support purge")

    def check(message: discord.Message) -> bool:
        if user_id is not None and message.author.id != user_id:
            return False
        if contains is not None and contains not in message.content:
            return False
        return True

    deleted = await channel.purge(limit=limit, check=check, reason="discord_cli message purge")
    return {"deleted_count": len(deleted), "deleted": [message_to_dict(m) for m in deleted]}


async def action_message_fetch(
    client: discord.Client, guild_id: int | None, message_id: int, channel_id: int, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    return message_to_dict(await get_message(guild, channel_id, message_id))


async def action_message_pin(
    client: discord.Client, guild_id: int | None, message_id: int, channel_id: int, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    message = await get_message(guild, channel_id, message_id)
    await message.pin(reason="discord_cli message pin")
    return {"pinned": message_to_dict(message)}


async def action_message_unpin(
    client: discord.Client, guild_id: int | None, message_id: int, channel_id: int, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    message = await get_message(guild, channel_id, message_id)
    await message.unpin(reason="discord_cli message unpin")
    return {"unpinned": message_to_dict(message)}


async def action_message_react(
    client: discord.Client, guild_id: int | None, message_id: int, channel_id: int, emoji: str, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    message = await get_message(guild, channel_id, message_id)
    await message.add_reaction(emoji)
    return {"reacted": {"message_id": message.id, "emoji": emoji}}
