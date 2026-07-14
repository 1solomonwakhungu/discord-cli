"""Category commands: list, create, delete, edit."""

from __future__ import annotations

from typing import Any

import click
import discord

from discord_cli.errors import CliError
from discord_cli.models import channel_to_dict, get_category, get_guild
from discord_cli.registry import invoke, registry


@registry.group("category")
def category_group() -> None:
    """Manage channel categories."""


@category_group.command("list")
@click.pass_context
def category_list(ctx: click.Context) -> None:
    invoke(ctx, action_category_list)


@category_group.command("create")
@click.argument("name")
@click.option("--position", type=int, default=None)
@click.pass_context
def category_create(ctx: click.Context, name: str, position: int | None) -> None:
    invoke(ctx, action_category_create, name=name, position=position)


@category_group.command("delete")
@click.argument("category_id", type=int)
@click.pass_context
def category_delete(ctx: click.Context, category_id: int) -> None:
    invoke(ctx, action_category_delete, category_id=category_id)


@category_group.command("edit")
@click.argument("category_id", type=int)
@click.option("--name", default=None)
@click.option("--position", type=int, default=None)
@click.pass_context
def category_edit(
    ctx: click.Context, category_id: int, name: str | None, position: int | None
) -> None:
    invoke(ctx, action_category_edit, category_id=category_id, name=name, position=position)


async def action_category_list(client: discord.Client, guild_id: int | None, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    return {
        "guild_id": guild.id,
        "categories": [channel_to_dict(c, detailed=True) for c in guild.categories],
    }


async def action_category_create(
    client: discord.Client, guild_id: int | None, name: str, position: int | None, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    category = await guild.create_category(
        name,
        position=position,
        reason="discord_cli category create",  # type: ignore[arg-type]
    )
    return {"created": channel_to_dict(category, detailed=True)}


async def action_category_delete(
    client: discord.Client, guild_id: int | None, category_id: int, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    category = get_category(guild, category_id)
    data = channel_to_dict(category)  # type: ignore[arg-type]
    await category.delete(reason="discord_cli category delete")  # type: ignore[union-attr]
    return {"deleted": data}


async def action_category_edit(
    client: discord.Client, guild_id: int | None, category_id: int, **kwargs: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    category = get_category(guild, category_id)
    edits = {
        k: v
        for k, v in {"name": kwargs.get("name"), "position": kwargs.get("position")}.items()
        if v is not None
    }
    if not edits:
        raise CliError("No edits provided")
    await category.edit(**edits, reason="discord_cli category edit")  # type: ignore[union-attr]
    return {"updated": channel_to_dict(category, detailed=True)}  # type: ignore[arg-type]
