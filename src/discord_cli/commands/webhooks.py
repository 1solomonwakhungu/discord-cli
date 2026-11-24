"""Webhook commands: CRUD (bot token) + zero-gateway execution (send/edit/delete/fetch)."""

from __future__ import annotations

import os
from typing import Any

import aiohttp
import click
import discord

from discord_cli.errors import CliError
from discord_cli.message_builder import (
    TEMPLATES,
    build_discord_files,
    load_embed,
    resolve_content,
    split_content,
)
from discord_cli.models import (
    get_guild,
    message_to_dict,
    resolve_channel,
    validate_webhook_url,
    webhook_to_dict,
)
from discord_cli.registry import invoke, invoke_http, registry


def _resolve_webhook_url(url: str | None) -> str:
    resolved = url or os.environ.get("DISCORD_WEBHOOK_URL")
    if not resolved:
        raise CliError("Webhook URL required via --url or DISCORD_WEBHOOK_URL")
    return validate_webhook_url(resolved)


@registry.group("webhook")
def webhook_group() -> None:
    """Manage and execute channel webhooks."""


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


@webhook_group.command("edit")
@click.argument("webhook_id", type=int)
@click.option("--name", default=None)
@click.option("--channel", "channel_id", type=int, default=None)
@click.option(
    "--show-secrets",
    is_flag=True,
    default=False,
    help="Include unredacted webhook URL tokens in the output.",
)
@click.pass_context
def webhook_edit(
    ctx: click.Context,
    webhook_id: int,
    name: str | None,
    channel_id: int | None,
    show_secrets: bool,
) -> None:
    """Edit webhook name or channel."""
    invoke(
        ctx,
        action_webhook_edit,
        webhook_id=webhook_id,
        name=name,
        channel_id=channel_id,
        show_secrets=show_secrets,
    )


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


@webhook_group.command("send")
@click.option("--url", default=None, help="Webhook URL (or DISCORD_WEBHOOK_URL env var).")
@click.option("--content", default=None, help="Message text, or '-' to read from stdin.")
@click.option("--embed-json", default=None, help="Embed JSON string or @filepath.")
@click.option("--embed-file", default=None, help="Path to a JSON file containing an embed.")
@click.option("--file", "files", multiple=True, help="Attachment file path (repeatable).")
@click.option("--username", default=None, help="Override webhook display username.")
@click.option("--avatar-url", default=None, help="Override webhook avatar URL.")
@click.option("--thread-id", type=int, default=None, help="Post into an existing thread ID.")
@click.option("--thread-name", default=None, help="Create a new forum/media thread with this name.")
@click.option(
    "--template",
    type=click.Choice(sorted(TEMPLATES.keys()), case_sensitive=False),
    default=None,
    help="Built-in embed preset.",
)
@click.option("--title", default=None, help="Embed title.")
@click.option("--description", default=None, help="Embed description.")
@click.option("--color", default=None, help="Embed HEX color (e.g. #5865F2).")
@click.option("--field", "fields", multiple=True, help="Embed field 'Name=Value[:inline]'.")
@click.option("--split", is_flag=True, default=False, help="Split content over 2000 chars.")
@click.option("--silent", is_flag=True, default=False, help="Suppress push notifications.")
@click.option(
    "--no-wait", is_flag=True, default=False, help="Fire-and-forget without returning message."
)
@click.pass_context
def webhook_send(
    ctx: click.Context,
    url: str | None,
    content: str | None,
    embed_json: str | None,
    embed_file: str | None,
    files: tuple[str, ...],
    username: str | None,
    avatar_url: str | None,
    thread_id: int | None,
    thread_name: str | None,
    template: str | None,
    title: str | None,
    description: str | None,
    color: str | None,
    fields: tuple[str, ...],
    split: bool,
    silent: bool,
    no_wait: bool,
) -> None:
    """Send a message via a Discord webhook URL (zero Gateway, no bot token required)."""
    invoke_http(
        ctx,
        action_webhook_send,
        url=url,
        content=content,
        embed_json=embed_json,
        embed_file=embed_file,
        files=list(files),
        username=username,
        avatar_url=avatar_url,
        thread_id=thread_id,
        thread_name=thread_name,
        template=template,
        title=title,
        description=description,
        color=color,
        fields=list(fields),
        split=split,
        silent=silent,
        wait=not no_wait,
    )


@webhook_group.command("edit-message")
@click.argument("message_id", type=int)
@click.option("--url", default=None, help="Webhook URL (or DISCORD_WEBHOOK_URL env var).")
@click.option("--thread-id", type=int, default=None, help="Thread ID if message is in a thread.")
@click.option("--content", default=None, help="Updated message text, or '-' to read from stdin.")
@click.option("--embed-json", default=None, help="Updated embed JSON string or @filepath.")
@click.option("--embed-file", default=None, help="Path to a JSON file containing an embed.")
@click.option(
    "--template",
    type=click.Choice(sorted(TEMPLATES.keys()), case_sensitive=False),
    default=None,
    help="Built-in embed preset.",
)
@click.option("--title", default=None, help="Embed title.")
@click.option("--description", default=None, help="Embed description.")
@click.option("--color", default=None, help="Embed HEX color.")
@click.option("--field", "fields", multiple=True, help="Embed field 'Name=Value[:inline]'.")
@click.pass_context
def webhook_edit_message(
    ctx: click.Context,
    message_id: int,
    url: str | None,
    thread_id: int | None,
    content: str | None,
    embed_json: str | None,
    embed_file: str | None,
    template: str | None,
    title: str | None,
    description: str | None,
    color: str | None,
    fields: tuple[str, ...],
) -> None:
    """Edit a message previously sent by a webhook (zero Gateway, no bot token required)."""
    invoke_http(
        ctx,
        action_webhook_edit_message,
        message_id=message_id,
        url=url,
        thread_id=thread_id,
        content=content,
        embed_json=embed_json,
        embed_file=embed_file,
        template=template,
        title=title,
        description=description,
        color=color,
        fields=list(fields),
    )


@webhook_group.command("delete-message")
@click.argument("message_id", type=int)
@click.option("--url", default=None, help="Webhook URL (or DISCORD_WEBHOOK_URL env var).")
@click.option("--thread-id", type=int, default=None, help="Thread ID if message is in a thread.")
@click.pass_context
def webhook_delete_message(
    ctx: click.Context, message_id: int, url: str | None, thread_id: int | None
) -> None:
    """Delete a message sent by a webhook (zero Gateway, no bot token required)."""
    invoke_http(
        ctx,
        action_webhook_delete_message,
        message_id=message_id,
        url=url,
        thread_id=thread_id,
    )


@webhook_group.command("fetch-message")
@click.argument("message_id", type=int)
@click.option("--url", default=None, help="Webhook URL (or DISCORD_WEBHOOK_URL env var).")
@click.option("--thread-id", type=int, default=None, help="Thread ID if message is in a thread.")
@click.pass_context
def webhook_fetch_message(
    ctx: click.Context, message_id: int, url: str | None, thread_id: int | None
) -> None:
    """Fetch a message sent by a webhook (zero Gateway, no bot token required)."""
    invoke_http(
        ctx,
        action_webhook_fetch_message,
        message_id=message_id,
        url=url,
        thread_id=thread_id,
    )


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


async def action_webhook_edit(
    client: discord.Client,
    guild_id: int | None,
    webhook_id: int,
    name: str | None = None,
    channel_id: int | None = None,
    show_secrets: bool = False,
    **_: Any,
) -> Any:
    webhook = await client.fetch_webhook(webhook_id)
    edits: dict[str, Any] = {}
    if name is not None:
        edits["name"] = name
    if channel_id is not None:
        guild = await get_guild(client, guild_id)
        edits["channel"] = await resolve_channel(guild, channel_id, client=client)
    if not edits:
        raise CliError("No edits provided")
    edited = await webhook.edit(**edits, reason="discord_cli webhook edit")
    return {"updated": webhook_to_dict(edited or webhook, show_secrets=show_secrets)}


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


async def action_webhook_send(
    *,
    url: str | None = None,
    content: str | None = None,
    embed_json: str | None = None,
    embed_file: str | None = None,
    files: list[str] | None = None,
    username: str | None = None,
    avatar_url: str | None = None,
    thread_id: int | None = None,
    thread_name: str | None = None,
    template: str | None = None,
    title: str | None = None,
    description: str | None = None,
    color: str | None = None,
    fields: list[str] | None = None,
    split: bool = False,
    silent: bool = False,
    wait: bool = True,
    **_: Any,
) -> dict[str, Any]:
    webhook_url = _resolve_webhook_url(url)
    resolved_content = resolve_content(content)
    embed = load_embed(
        embed_json=embed_json,
        embed_file=embed_file,
        template=template,
        title=title,
        description=description,
        color=color,
        fields=fields or [],
    )
    file_paths = files or []
    if resolved_content is None and embed is None and not file_paths:
        raise CliError(
            "At least one of --content, --embed-json/--embed-file/--template, or --file is required"
        )

    chunks = (
        split_content(resolved_content)
        if resolved_content is not None and split
        else ([resolved_content] if resolved_content is not None else [None])
    )
    if not chunks:
        if embed is None and not file_paths:
            raise CliError("Message content cannot be empty or whitespace-only")
        chunks = [None]
    if len(chunks) > 1 and thread_name is not None and not wait:
        raise CliError(
            "--split with --thread-name requires waiting for the created thread (omit --no-wait)"
        )

    active_thread_id = thread_id
    async with aiohttp.ClientSession() as session:
        webhook = discord.Webhook.from_url(webhook_url, session=session)
        sent_messages: list[dict[str, Any]] = []
        for idx, chunk in enumerate(chunks):
            send_kwargs: dict[str, Any] = {"wait": wait, "silent": silent}
            if chunk is not None:
                send_kwargs["content"] = chunk
            if idx == 0 and embed is not None:
                send_kwargs["embed"] = embed
            if idx == 0 and file_paths:
                send_kwargs["files"] = build_discord_files(file_paths)
            if username is not None:
                send_kwargs["username"] = username
            if avatar_url is not None:
                send_kwargs["avatar_url"] = avatar_url
            if active_thread_id is not None:
                send_kwargs["thread"] = discord.Object(id=active_thread_id)
            elif idx == 0 and thread_name is not None:
                send_kwargs["thread_name"] = thread_name

            try:
                msg = await webhook.send(**send_kwargs)
            except Exception as exc:
                if sent_messages:
                    sent_ids = [m["id"] for m in sent_messages]
                    raise CliError(
                        f"Failed sending chunk {idx + 1}/{len(chunks)} "
                        f"(already sent message IDs: {sent_ids}): {exc}"
                    ) from exc
                raise
            if msg is not None:
                sent_messages.append(message_to_dict(msg))
                if idx == 0 and thread_name is not None and active_thread_id is None:
                    active_thread_id = msg.channel.id

    if not wait:
        return {"sent": True, "chunks": len(chunks)}
    if len(sent_messages) == 1:
        return {"sent": sent_messages[0]}
    return {"sent": sent_messages, "count": len(sent_messages)}


async def action_webhook_edit_message(
    *,
    message_id: int,
    url: str | None = None,
    thread_id: int | None = None,
    content: str | None = None,
    embed_json: str | None = None,
    embed_file: str | None = None,
    template: str | None = None,
    title: str | None = None,
    description: str | None = None,
    color: str | None = None,
    fields: list[str] | None = None,
    **_: Any,
) -> dict[str, Any]:
    webhook_url = _resolve_webhook_url(url)
    resolved_content = resolve_content(content)
    embed = load_embed(
        embed_json=embed_json,
        embed_file=embed_file,
        template=template,
        title=title,
        description=description,
        color=color,
        fields=fields or [],
    )
    edit_kwargs: dict[str, Any] = {}
    if resolved_content is not None:
        edit_kwargs["content"] = resolved_content
    if embed is not None:
        edit_kwargs["embed"] = embed
    if not edit_kwargs:
        raise CliError("No edits provided")
    if thread_id is not None:
        edit_kwargs["thread"] = discord.Object(id=thread_id)

    async with aiohttp.ClientSession() as session:
        webhook = discord.Webhook.from_url(webhook_url, session=session)
        edited = await webhook.edit_message(message_id, **edit_kwargs)
    return {"updated": message_to_dict(edited)}


async def action_webhook_delete_message(
    *,
    message_id: int,
    url: str | None = None,
    thread_id: int | None = None,
    **_: Any,
) -> dict[str, Any]:
    webhook_url = _resolve_webhook_url(url)
    kwargs: dict[str, Any] = {}
    if thread_id is not None:
        kwargs["thread"] = discord.Object(id=thread_id)
    async with aiohttp.ClientSession() as session:
        webhook = discord.Webhook.from_url(webhook_url, session=session)
        await webhook.delete_message(message_id, **kwargs)
    return {"deleted": {"message_id": message_id, "thread_id": thread_id}}


async def action_webhook_fetch_message(
    *,
    message_id: int,
    url: str | None = None,
    thread_id: int | None = None,
    **_: Any,
) -> dict[str, Any]:
    webhook_url = _resolve_webhook_url(url)
    kwargs: dict[str, Any] = {}
    if thread_id is not None:
        kwargs["thread"] = discord.Object(id=thread_id)
    async with aiohttp.ClientSession() as session:
        webhook = discord.Webhook.from_url(webhook_url, session=session)
        msg = await webhook.fetch_message(message_id, **kwargs)
    return message_to_dict(msg)
