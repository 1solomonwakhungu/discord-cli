"""Channel commands: list, create, delete, edit, move, info."""

from __future__ import annotations

from typing import Any

import click
import discord

from discord_cli.errors import CliError
from discord_cli.models import channel_to_dict, get_category, get_channel, get_guild
from discord_cli.registry import TRI_STATE_BOOL, invoke, registry


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
@click.option("--category", type=int, default=None)
@click.option("--topic", default=None)
@click.option("--position", type=int, default=None)
@click.option("--nsfw", is_flag=True, default=False)
@click.option("--slowmode", type=int, default=None)
@click.pass_context
def channel_create(
    ctx: click.Context,
    name: str,
    channel_type: str,
    category: int | None,
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
@click.argument("channel_id", type=int)
@click.pass_context
def channel_delete(ctx: click.Context, channel_id: int) -> None:
    invoke(ctx, action_channel_delete, channel_id=channel_id)


@channel_group.command("edit")
@click.argument("channel_id", type=int)
@click.option("--name", default=None)
@click.option("--topic", default=None)
@click.option("--position", type=int, default=None)
@click.option("--slowmode", type=int, default=None)
@click.option("--nsfw", type=TRI_STATE_BOOL, default=None)
@click.pass_context
def channel_edit(
    ctx: click.Context,
    channel_id: int,
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
@click.argument("channel_id", type=int)
@click.option("--category", type=int, required=True)
@click.pass_context
def channel_move(ctx: click.Context, channel_id: int, category: int) -> None:
    invoke(ctx, action_channel_move, channel_id=channel_id, category=category)


@channel_group.command("info")
@click.argument("channel_id", type=int)
@click.pass_context
def channel_info(ctx: click.Context, channel_id: int) -> None:
    invoke(ctx, action_channel_info, channel_id=channel_id)


async def action_channel_list(client: discord.Client, guild_id: int | None, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    return {"guild_id": guild.id, "channels": [channel_to_dict(c) for c in guild.channels]}


async def action_channel_create(client: discord.Client, guild_id: int | None, **kwargs: Any) -> Any:
    guild = await get_guild(client, guild_id)
    category = get_category(guild, kwargs.get("category"))
    common = {
        "category": category,
        "position": kwargs.get("position"),
        "reason": "discord_cli channel create",
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
        channel = await guild.create_forum_channel(  # type: ignore[attr-defined]
            name,
            topic=kwargs.get("topic"),
            nsfw=kwargs.get("nsfw", False),
            slowmode_delay=kwargs.get("slowmode") or 0,
            **common,
        )
    else:
        raise CliError(f"Unsupported channel type: {ctype}")
    return {"created": channel_to_dict(channel, detailed=True)}


async def action_channel_delete(
    client: discord.Client, guild_id: int | None, channel_id: int, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    channel = get_channel(guild, channel_id)
    data = channel_to_dict(channel)
    await channel.delete(reason="discord_cli channel delete")
    return {"deleted": data}


async def action_channel_edit(
    client: discord.Client, guild_id: int | None, channel_id: int, **kwargs: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    channel = get_channel(guild, channel_id)
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
    edited = await channel.edit(**edits, reason="discord_cli channel edit")  # type: ignore[union-attr]
    return {"updated": channel_to_dict(edited or channel, detailed=True)}


async def action_channel_move(
    client: discord.Client, guild_id: int | None, channel_id: int, category: int, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    channel = get_channel(guild, channel_id)
    new_category = get_category(guild, category)
    await channel.edit(category=new_category, reason="discord_cli channel move")  # type: ignore[call-arg,union-attr]
    return {"updated": channel_to_dict(channel, detailed=True)}


async def action_channel_info(
    client: discord.Client, guild_id: int | None, channel_id: int, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    return channel_to_dict(get_channel(guild, channel_id), detailed=True)
