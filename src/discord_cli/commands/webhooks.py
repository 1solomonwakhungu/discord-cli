"""Webhook commands: list, create, delete, info."""

from __future__ import annotations

from typing import Any

import click
import discord

from discord_cli.errors import CliError
from discord_cli.models import get_guild, resolve_channel, webhook_to_dict
from discord_cli.registry import invoke, registry


@registry.group("webhook")
def webhook_group() -> None:
    """Manage channel webhooks."""


@webhook_group.command("list")
@click.option("--channel", "channel_id", type=int, default=None)
@click.option(
    "--show-secrets",
    is_flag=True,
    default=False,
    help="Include unredacted webhook URL tokens in the output.",
)
@click.pass_context
def webhook_list(ctx: click.Context, channel_id: int | None, show_secrets: bool) -> None:
    invoke(ctx, action_webhook_list, channel_id=channel_id, show_secrets=show_secrets)


@webhook_group.command("create")
@click.option("--channel", "channel_id", type=int, required=True)
@click.option("--name", required=True)
@click.option(
    "--show-secrets",
    is_flag=True,
    default=False,
    help="Include unredacted webhook URL tokens in the output.",
)
@click.pass_context
def webhook_create(ctx: click.Context, channel_id: int, name: str, show_secrets: bool) -> None:
    invoke(ctx, action_webhook_create, channel_id=channel_id, name=name, show_secrets=show_secrets)


@webhook_group.command("delete")
@click.argument("webhook_id", type=int)
@click.pass_context
def webhook_delete(ctx: click.Context, webhook_id: int) -> None:
    invoke(ctx, action_webhook_delete, webhook_id=webhook_id)


@webhook_group.command("info")
@click.argument("webhook_id", type=int)
@click.option(
    "--show-secrets",
    is_flag=True,
    default=False,
    help="Include unredacted webhook URL tokens in the output.",
)
@click.pass_context
def webhook_info(ctx: click.Context, webhook_id: int, show_secrets: bool) -> None:
    invoke(ctx, action_webhook_info, webhook_id=webhook_id, show_secrets=show_secrets)


async def action_webhook_list(
    client: discord.Client,
    guild_id: int | None,
    channel_id: int | None,
    show_secrets: bool = False,
    **_: Any,
) -> Any:
    guild = await get_guild(client, guild_id)
    if channel_id is not None:
        channel = await resolve_channel(guild, channel_id, client=client)
        webhooks = await channel.webhooks()  # type: ignore[union-attr]
    else:
        webhooks = await guild.webhooks()
    return {"webhooks": [webhook_to_dict(w, show_secrets=show_secrets) for w in webhooks]}


async def action_webhook_create(
    client: discord.Client,
    guild_id: int | None,
    channel_id: int,
    name: str,
    show_secrets: bool = False,
    **_: Any,
) -> Any:
    guild = await get_guild(client, guild_id)
    channel = await resolve_channel(guild, channel_id, client=client)
    if not hasattr(channel, "create_webhook"):
        raise CliError("Channel does not support webhooks")
    webhook = await channel.create_webhook(name=name, reason="discord_cli webhook create")
    return {"created": webhook_to_dict(webhook, show_secrets=show_secrets)}


async def action_webhook_delete(
    client: discord.Client, guild_id: int | None, webhook_id: int, **_: Any
) -> Any:
    webhook = await client.fetch_webhook(webhook_id)
    data = webhook_to_dict(webhook, show_secrets=False)
    await webhook.delete(reason="discord_cli webhook delete")
    return {"deleted": data}


async def action_webhook_info(
    client: discord.Client,
    guild_id: int | None,
    webhook_id: int,
    show_secrets: bool = False,
    **_: Any,
) -> Any:
    return webhook_to_dict(await client.fetch_webhook(webhook_id), show_secrets=show_secrets)
