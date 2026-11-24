"""Channel commands: list, create, delete, edit, move, info."""

from __future__ import annotations

from typing import Any

import click
import discord

from discord_cli.errors import CliError
from discord_cli.models import (
    channel_to_dict,
    fetch_guild_channels,
    get_guild,
)
from discord_cli.registry import TRI_STATE_BOOL, invoke, registry
from discord_cli.resolvers import (
    RESOURCE_ID,
    resolve_category_selector,
    resolve_channel_selector,
)


@registry.group("channel")
def channel_group() -> None:
    """Manage guild channels."""


@channel_group.command("list")
@click.pass_context
def channel_list(ctx: click.Context) -> None:
    invoke(ctx, action_channel_list)


@channel_group.command("create")
@click.argument("name")
@click.option(
    "--type", "channel_type", type=click.Choice(["text", "voice", "stage", "forum"]), default="text"
)
@click.option("--category", type=RESOURCE_ID, default=None)
@click.option("--topic", default=None)
@click.option("--position", type=int, default=None)
@click.option("--nsfw", is_flag=True, default=False)
@click.option("--slowmode", type=int, default=None)
@click.pass_context
def channel_create(
    ctx: click.Context,
    name: str,
    channel_type: str,
    category: int | str | None,
    topic: str | None,
    position: int | None,
    nsfw: bool,
    slowmode: int | None,
) -> None:
    invoke(
        ctx,
        action_channel_create,
        name=name,
        type=channel_type,
        category=category,
        topic=topic,
        position=position,
        nsfw=nsfw,
        slowmode=slowmode,
    )


@channel_group.command("delete")
@click.argument("channel_id", type=RESOURCE_ID)
@click.pass_context
def channel_delete(ctx: click.Context, channel_id: int | str) -> None:
    invoke(ctx, action_channel_delete, channel_id=channel_id)


@channel_group.command("edit")
@click.argument("channel_id", type=RESOURCE_ID)
@click.option("--name", default=None)
@click.option("--topic", default=None)
@click.option("--position", type=int, default=None)
@click.option("--slowmode", type=int, default=None)
@click.option("--nsfw", type=TRI_STATE_BOOL, default=None)
@click.pass_context
def channel_edit(
    ctx: click.Context,
    channel_id: int | str,
    name: str | None,
    topic: str | None,
    position: int | None,
    slowmode: int | None,
    nsfw: bool | None,
) -> None:
    invoke(
        ctx,
        action_channel_edit,
        channel_id=channel_id,
        name=name,
        topic=topic,
        position=position,
        slowmode=slowmode,
        nsfw=nsfw,
    )


@channel_group.command("move")
@click.argument("channel_id", type=RESOURCE_ID)
@click.option("--category", type=RESOURCE_ID, required=True)
@click.pass_context
def channel_move(ctx: click.Context, channel_id: int | str, category: int | str) -> None:
    invoke(ctx, action_channel_move, channel_id=channel_id, category=category)


@channel_group.command("info")
@click.argument("channel_id", type=RESOURCE_ID)
@click.pass_context
def channel_info(ctx: click.Context, channel_id: int | str) -> None:
    invoke(ctx, action_channel_info, channel_id=channel_id)


async def action_channel_list(client: discord.Client, guild_id: int | None, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    channels = await fetch_guild_channels(guild, client=client)
    return {"guild_id": guild.id, "channels": [channel_to_dict(c) for c in channels]}


async def action_channel_create(client: discord.Client, guild_id: int | None, **kwargs: Any) -> Any:
    guild = await get_guild(client, guild_id)
    category = await resolve_category_selector(guild, kwargs.get("category"), client=client)
    reason = kwargs.get("reason") or "discord_cli channel create"
    common = {
        "category": category,
        "position": kwargs.get("position"),
        "reason": reason,
    }
    common = {k: v for k, v in common.items() if v is not None}
    ctype = kwargs.get("type") or "text"
    name = kwargs["name"]
    if ctype == "text":
        channel = await guild.create_text_channel(
            name,
            topic=kwargs.get("topic"),  # type: ignore[arg-type]
            nsfw=kwargs.get("nsfw", False),
            slowmode_delay=kwargs.get("slowmode") or 0,
            **common,  # type: ignore[arg-type]
        )
    elif ctype == "voice":
        channel = await guild.create_voice_channel(name, **common)  # type: ignore[arg-type,assignment]
    elif ctype == "stage":
        channel = await guild.create_stage_channel(name, **common)  # type: ignore[arg-type,assignment]
    elif ctype == "forum":
        channel = await guild.create_forum(  # type: ignore[assignment]
            name,
            topic=kwargs.get("topic"),
            nsfw=kwargs.get("nsfw", False),
            slowmode_delay=kwargs.get("slowmode") or 0,
            **common,  # type: ignore[arg-type]
        )
    else:
        raise CliError(f"Unsupported channel type: {ctype}")
    return {"created": channel_to_dict(channel, detailed=True)}


async def action_channel_delete(
    client: discord.Client,
    guild_id: int | None,
    channel_id: int | str,
    reason: str | None = None,
    **_: Any,
) -> Any:
    guild = await get_guild(client, guild_id)
    channel = await resolve_channel_selector(guild, channel_id, client=client)
    data = channel_to_dict(channel)
    await channel.delete(reason=reason or "discord_cli channel delete")
    return {"deleted": data}


async def action_channel_edit(
    client: discord.Client, guild_id: int | None, channel_id: int | str, **kwargs: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    channel = await resolve_channel_selector(guild, channel_id, client=client)
    edits: dict[str, Any] = {}
    if kwargs.get("name") is not None:
        edits["name"] = kwargs["name"]
    if kwargs.get("topic") is not None and hasattr(channel, "topic"):
        edits["topic"] = kwargs["topic"]
    if kwargs.get("position") is not None:
        edits["position"] = kwargs["position"]
    if kwargs.get("slowmode") is not None and hasattr(channel, "slowmode_delay"):
        edits["slowmode_delay"] = kwargs["slowmode"]
    if kwargs.get("nsfw") is not None and hasattr(channel, "nsfw"):
        edits["nsfw"] = kwargs["nsfw"]
    if not edits:
        raise CliError("No edits provided")
    reason = kwargs.get("reason") or "discord_cli channel edit"
    edited = await channel.edit(**edits, reason=reason)  # type: ignore[union-attr]
    return {"updated": channel_to_dict(edited or channel, detailed=True)}


async def action_channel_move(
    client: discord.Client,
    guild_id: int | None,
    channel_id: int | str,
    category: int | str,
    reason: str | None = None,
    **_: Any,
) -> Any:
    guild = await get_guild(client, guild_id)
    channel = await resolve_channel_selector(guild, channel_id, client=client)
    new_category = await resolve_category_selector(guild, category, client=client)
    await channel.edit(category=new_category, reason=reason or "discord_cli channel move")  # type: ignore[call-arg,union-attr]
    return {"updated": channel_to_dict(channel, detailed=True)}


async def action_channel_info(
    client: discord.Client, guild_id: int | None, channel_id: int | str, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    return channel_to_dict(
        await resolve_channel_selector(guild, channel_id, client=client), detailed=True
    )
