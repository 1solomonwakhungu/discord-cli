"""Webhook commands: list, create, delete, info."""

from __future__ import annotations

from typing import Any

import click
import discord

from discord_cli.errors import CliError
from discord_cli.models import get_channel, get_guild, webhook_to_dict
from discord_cli.registry import invoke, registry


@registry.group("webhook")
def webhook_group() -> None:
    """Manage channel webhooks."""


@webhook_group.command("list")
@click.option("--channel", "channel_id", type=int, default=None)
@click.pass_context
def webhook_list(ctx: click.Context, channel_id: int | None) -> None:
    invoke(ctx, action_webhook_list, channel_id=channel_id)


@webhook_group.command("create")
@click.option("--channel", "channel_id", type=int, required=True)
@click.option("--name", required=True)
@click.pass_context
def webhook_create(ctx: click.Context, channel_id: int, name: str) -> None:
    invoke(ctx, action_webhook_create, channel_id=channel_id, name=name)


@webhook_group.command("delete")
@click.argument("webhook_id", type=int)
@click.pass_context
def webhook_delete(ctx: click.Context, webhook_id: int) -> None:
    invoke(ctx, action_webhook_delete, webhook_id=webhook_id)


@webhook_group.command("info")
@click.argument("webhook_id", type=int)
@click.pass_context
def webhook_info(ctx: click.Context, webhook_id: int) -> None:
    invoke(ctx, action_webhook_info, webhook_id=webhook_id)


async def action_webhook_list(client: discord.Client, guild_id: int | None, channel_id: int | None, **_: Any) -> Any:
    guild = await get_guild(client, guild_id)
    webhooks = await (get_channel(guild, channel_id).webhooks() if channel_id else guild.webhooks())
    return {"webhooks": [webhook_to_dict(w) for w in webhooks]}


async def action_webhook_create(
    client: discord.Client, guild_id: int | None, channel_id: int, name: str, **_: Any
) -> Any:
    guild = await get_guild(client, guild_id)
    channel = get_channel(guild, channel_id)
    if not hasattr(channel, "create_webhook"):
        raise CliError("Channel does not support webhooks")
    webhook = await channel.create_webhook(name=name, reason="discord_cli webhook create")
    return {"created": webhook_to_dict(webhook)}


async def action_webhook_delete(client: discord.Client, guild_id: int | None, webhook_id: int, **_: Any) -> Any:
    await get_guild(client, guild_id)
    webhook = await client.fetch_webhook(webhook_id)
    data = webhook_to_dict(webhook)
    await webhook.delete(reason="discord_cli webhook delete")
    return {"deleted": data}


async def action_webhook_info(client: discord.Client, guild_id: int | None, webhook_id: int, **_: Any) -> Any:
    await get_guild(client, guild_id)
    return webhook_to_dict(await client.fetch_webhook(webhook_id))
