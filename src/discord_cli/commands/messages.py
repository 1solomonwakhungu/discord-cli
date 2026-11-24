"""Message commands: list, send, edit, delete, purge, fetch, pin, unpin, pins, publish, download, react, unreact."""

from __future__ import annotations

import inspect
import re
from pathlib import Path
from typing import Any

import click
import discord

from discord_cli.errors import CliError
from discord_cli.message_builder import (
    build_discord_files,
    load_embed,
    resolve_content,
    split_content,
)
from discord_cli.models import (
    get_guild,
    get_message,
    message_to_dict,
)
from discord_cli.registry import invoke, registry
from discord_cli.resolvers import (
    RESOURCE_ID,
    resolve_channel_selector,
    resolve_member_id,
    resolve_message_ref,
)

_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_STEM_BYTES = 180


def _safe_attachment_filename(attachment_id: int, filename: str) -> str:
    base = Path(filename.replace("\\", "/")).name
    stem, ext = Path(base).stem, Path(base).suffix
    clean_stem = _SAFE_FILENAME_RE.sub("_", stem).strip("._") or "attachment"
    clean_ext = _SAFE_FILENAME_RE.sub("", ext)[:16]
    if clean_ext and not clean_ext.startswith("."):
        clean_ext = f".{clean_ext}"
    clean_stem = clean_stem[:_MAX_STEM_BYTES]
    return f"{attachment_id}_{clean_stem}{clean_ext}"


async def _resolve_message_target(
    client: discord.Client,
    guild_id: int | None,
    message_id: int | str,
    channel_id: int | str | None,
) -> tuple[discord.Guild, discord.Message]:
    msg_id, ch_ref, resolved_guild_id = resolve_message_ref(message_id, channel_id, guild_id)
    if ch_ref is None:
        raise CliError(
            "--channel is required unless message_id is a Discord message URL "
            "(https://discord.com/channels/<guild>/<channel>/<message>)."
        )
    guild = await get_guild(client, resolved_guild_id)
    channel = await resolve_channel_selector(guild, ch_ref, client=client)
    message = await get_message(guild, channel.id, msg_id, client=client)
    return guild, message


@registry.group("message")
def message_group() -> None:
    """Send and manage messages."""


@message_group.command("list")
@click.argument("channel_id", type=RESOURCE_ID)
@click.option("--limit", type=int, default=20, help="Number of messages to fetch (default: 20)")
@click.option(
    "--before", "before_id", type=int, default=None, help="Fetch messages before this message ID"
)
@click.option(
    "--after", "after_id", type=int, default=None, help="Fetch messages after this message ID"
)
@click.pass_context
def message_list(
    ctx: click.Context,
    channel_id: int | str,
    limit: int,
    before_id: int | None,
    after_id: int | None,
) -> None:
    """List recent messages in a channel."""
    invoke(
        ctx,
        action_message_list,
        channel_id=channel_id,
        limit=limit,
        before_id=before_id,
        after_id=after_id,
    )


@message_group.command("send")
@click.argument("channel_id", type=RESOURCE_ID)
@click.option("--content", default=None, help="Message text, or '-' to read from stdin.")
@click.option("--embed-json", default=None, help="Embed JSON string or @filepath.")
@click.option("--embed-file", default=None, help="Path to a JSON file containing an embed.")
@click.option("--file", "files", multiple=True, help="Attachment file path (repeatable).")
@click.option("--reply-to", "reply_to", type=int, default=None, help="Message ID to reply to.")
@click.option("--silent", is_flag=True, default=False, help="Suppress push notifications.")
@click.option("--split", is_flag=True, default=False, help="Split content over 2000 chars.")
@click.pass_context
def message_send(
    ctx: click.Context,
    channel_id: int | str,
    content: str | None,
    embed_json: str | None,
    embed_file: str | None,
    files: tuple[str, ...],
    reply_to: int | None,
    silent: bool,
    split: bool,
) -> None:
    invoke(
        ctx,
        action_message_send,
        channel_id=channel_id,
        content=content,
        embed_json=embed_json,
        embed_file=embed_file,
        files=list(files),
        reply_to=reply_to,
        silent=silent,
        split=split,
    )


@message_group.command("edit")
@click.argument("message_id", type=RESOURCE_ID)
@click.option(
    "--channel",
    "channel_id",
    type=RESOURCE_ID,
    default=None,
    help="Channel ID/selector (optional when message_id is a Discord message URL).",
)
@click.option("--content", required=True)
@click.pass_context
def message_edit(
    ctx: click.Context, message_id: int | str, channel_id: int | str | None, content: str
) -> None:
    invoke(ctx, action_message_edit, message_id=message_id, channel_id=channel_id, content=content)


@message_group.command("delete")
@click.argument("message_id", type=RESOURCE_ID)
@click.option(
    "--channel",
    "channel_id",
    type=RESOURCE_ID,
    default=None,
    help="Channel ID/selector (optional when message_id is a Discord message URL).",
)
@click.pass_context
def message_delete(ctx: click.Context, message_id: int | str, channel_id: int | str | None) -> None:
    invoke(ctx, action_message_delete, message_id=message_id, channel_id=channel_id)


@message_group.command("purge")
@click.argument("channel_id", type=RESOURCE_ID)
@click.option("--limit", type=int, required=True)
@click.option("--user", "user_id", type=RESOURCE_ID, default=None)
@click.option("--contains", default=None)
@click.pass_context
def message_purge(
    ctx: click.Context,
    channel_id: int | str,
    limit: int,
    user_id: int | str | None,
    contains: str | None,
) -> None:
    invoke(
        ctx,
        action_message_purge,
        channel_id=channel_id,
        limit=limit,
        user_id=user_id,
        contains=contains,
    )


@message_group.command("fetch")
@click.argument("message_id", type=RESOURCE_ID)
@click.option(
    "--channel",
    "channel_id",
    type=RESOURCE_ID,
    default=None,
    help="Channel ID/selector (optional when message_id is a Discord message URL).",
)
@click.pass_context
def message_fetch(ctx: click.Context, message_id: int | str, channel_id: int | str | None) -> None:
    invoke(ctx, action_message_fetch, message_id=message_id, channel_id=channel_id)


@message_group.command("pin")
@click.argument("message_id", type=RESOURCE_ID)
@click.option(
    "--channel",
    "channel_id",
    type=RESOURCE_ID,
    default=None,
    help="Channel ID/selector (optional when message_id is a Discord message URL).",
)
@click.pass_context
def message_pin(ctx: click.Context, message_id: int | str, channel_id: int | str | None) -> None:
    invoke(ctx, action_message_pin, message_id=message_id, channel_id=channel_id)


@message_group.command("unpin")
@click.argument("message_id", type=RESOURCE_ID)
@click.option(
    "--channel",
    "channel_id",
    type=RESOURCE_ID,
    default=None,
    help="Channel ID/selector (optional when message_id is a Discord message URL).",
)
@click.pass_context
def message_unpin(ctx: click.Context, message_id: int | str, channel_id: int | str | None) -> None:
    invoke(ctx, action_message_unpin, message_id=message_id, channel_id=channel_id)


@message_group.command("pins")
@click.argument("channel_id", type=RESOURCE_ID)
@click.option("--limit", type=int, default=50, help="Max pinned messages to return (default: 50)")
@click.pass_context
def message_pins(ctx: click.Context, channel_id: int | str, limit: int) -> None:
    """List pinned messages in a channel."""
    invoke(ctx, action_message_pins, channel_id=channel_id, limit=limit)


@message_group.command("publish")
@click.argument("message_id", type=RESOURCE_ID)
@click.option(
    "--channel",
    "channel_id",
    type=RESOURCE_ID,
    default=None,
    help="Channel ID/selector (optional when message_id is a Discord message URL).",
)
@click.pass_context
def message_publish(
    ctx: click.Context, message_id: int | str, channel_id: int | str | None
) -> None:
    """Crosspost (publish) an announcement channel message."""
    invoke(ctx, action_message_publish, message_id=message_id, channel_id=channel_id)


@message_group.command("download")
@click.argument("message_id", type=RESOURCE_ID)
@click.option(
    "--channel",
    "channel_id",
    type=RESOURCE_ID,
    default=None,
    help="Channel ID/selector (optional when message_id is a Discord message URL).",
)
@click.option("--out", "out_dir", required=True, help="Directory to save downloaded attachments.")
@click.pass_context
def message_download(
    ctx: click.Context, message_id: int | str, channel_id: int | str | None, out_dir: str
) -> None:
    """Download all attachments from a message into a local directory."""
    invoke(
        ctx,
        action_message_download,
        message_id=message_id,
        channel_id=channel_id,
        out_dir=out_dir,
    )


@message_group.command("react")
@click.argument("message_id", type=RESOURCE_ID)
@click.option(
    "--channel",
    "channel_id",
    type=RESOURCE_ID,
    default=None,
    help="Channel ID/selector (optional when message_id is a Discord message URL).",
)
@click.option("--emoji", required=True)
@click.pass_context
def message_react(
    ctx: click.Context, message_id: int | str, channel_id: int | str | None, emoji: str
) -> None:
    invoke(ctx, action_message_react, message_id=message_id, channel_id=channel_id, emoji=emoji)


@message_group.command("unreact")
@click.argument("message_id", type=RESOURCE_ID)
@click.option(
    "--channel",
    "channel_id",
    type=RESOURCE_ID,
    default=None,
    help="Channel ID/selector (optional when message_id is a Discord message URL).",
)
@click.option("--emoji", required=True)
@click.option(
    "--user",
    "user_id",
    type=RESOURCE_ID,
    default=None,
    help="Remove reaction from this user ID/selector (default: bot)",
)
@click.pass_context
def message_unreact(
    ctx: click.Context,
    message_id: int | str,
    channel_id: int | str | None,
    emoji: str,
    user_id: int | str | None,
) -> None:
    """Remove a reaction from a message."""
    invoke(
        ctx,
        action_message_unreact,
        message_id=message_id,
        channel_id=channel_id,
        emoji=emoji,
        user_id=user_id,
    )


async def action_message_list(
    client: discord.Client,
    guild_id: int | None,
    channel_id: int | str,
    limit: int,
    before_id: int | None = None,
    after_id: int | None = None,
    **_: Any,
) -> Any:
    guild = await get_guild(client, guild_id)
    channel = await resolve_channel_selector(guild, channel_id, client=client)
    if not hasattr(channel, "history"):
        raise CliError("Channel does not support reading messages")
    if limit <= 0:
        raise CliError("--limit must be a positive integer")
    history_kwargs: dict[str, Any] = {"limit": limit}
    if before_id is not None:
        history_kwargs["before"] = discord.Object(id=before_id)
    if after_id is not None:
        history_kwargs["after"] = discord.Object(id=after_id)
    messages = [message_to_dict(m) async for m in channel.history(**history_kwargs)]
    payload: dict[str, Any] = {
        "channel_id": channel.id,
        "count": len(messages),
        "messages": messages,
    }
    if messages:
        payload["pagination"] = {
            "has_more": len(messages) >= limit,
            "next_before": messages[-1]["id"],
            "next_after": messages[0]["id"],
        }
    return payload


async def action_message_send(
    client: discord.Client,
    guild_id: int | None,
    channel_id: int | str,
    content: str | None,
    embed_json: str | None,
    embed_file: str | None = None,
    files: list[str] | None = None,
    reply_to: int | None = None,
    silent: bool = False,
    split: bool = False,
    **_: Any,
) -> Any:
    guild = await get_guild(client, guild_id)
    channel = await resolve_channel_selector(guild, channel_id, client=client)
    if not hasattr(channel, "send"):
        raise CliError("Channel does not support sending messages")
    resolved_content = resolve_content(content)
    embed = load_embed(embed_json=embed_json, embed_file=embed_file)
    file_paths = files or []
    if resolved_content is None and embed is None and not file_paths:
        raise CliError("--content, --embed-json/--embed-file, or --file is required")

    chunks = (
        split_content(resolved_content)
        if resolved_content is not None and split
        else ([resolved_content] if resolved_content is not None else [None])
    )
    reference = (
        discord.MessageReference(message_id=reply_to, channel_id=channel.id)
        if reply_to is not None
        else None
    )

    sent_messages: list[dict[str, Any]] = []
    for idx, chunk in enumerate(chunks):
        send_kwargs: dict[str, Any] = {
            "content": chunk,
            "embed": embed if idx == 0 else None,
        }
        if idx == 0 and file_paths:
            send_kwargs["files"] = build_discord_files(file_paths)
        if idx == 0 and reference is not None:
            send_kwargs["reference"] = reference
        if silent:
            send_kwargs["silent"] = True
        message = await channel.send(**send_kwargs)  # type: ignore[arg-type]
        sent_messages.append(message_to_dict(message))

    if len(sent_messages) == 1:
        return {"sent": sent_messages[0]}
    return {"sent": sent_messages, "count": len(sent_messages)}


async def action_message_edit(
    client: discord.Client,
    guild_id: int | None,
    message_id: int | str,
    channel_id: int | str | None,
    content: str,
    **_: Any,
) -> Any:
    _, message = await _resolve_message_target(client, guild_id, message_id, channel_id)
    edited = await message.edit(content=content)
    return {"updated": message_to_dict(edited)}


async def action_message_delete(
    client: discord.Client,
    guild_id: int | None,
    message_id: int | str,
    channel_id: int | str | None,
    **_: Any,
) -> Any:
    _, message = await _resolve_message_target(client, guild_id, message_id, channel_id)
    data = message_to_dict(message)
    await message.delete()
    return {"deleted": data}


async def action_message_purge(
    client: discord.Client,
    guild_id: int | None,
    channel_id: int | str,
    limit: int,
    user_id: int | str | None,
    contains: str | None,
    reason: str | None = None,
    **_: Any,
) -> Any:
    guild = await get_guild(client, guild_id)
    channel = await resolve_channel_selector(guild, channel_id, client=client)
    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
        raise CliError("Channel does not support purge")
    resolved_user_id = (
        await resolve_member_id(guild, user_id, client=client) if user_id is not None else None
    )

    def check(message: discord.Message) -> bool:
        if resolved_user_id is not None and message.author.id != resolved_user_id:
            return False
        if contains is not None and contains not in message.content:
            return False
        return True

    deleted = await channel.purge(
        limit=limit, check=check, reason=reason or "discord_cli message purge"
    )
    return {"deleted_count": len(deleted), "deleted": [message_to_dict(m) for m in deleted]}


async def action_message_fetch(
    client: discord.Client,
    guild_id: int | None,
    message_id: int | str,
    channel_id: int | str | None,
    **_: Any,
) -> Any:
    _, message = await _resolve_message_target(client, guild_id, message_id, channel_id)
    return message_to_dict(message)


async def action_message_pin(
    client: discord.Client,
    guild_id: int | None,
    message_id: int | str,
    channel_id: int | str | None,
    reason: str | None = None,
    **_: Any,
) -> Any:
    _, message = await _resolve_message_target(client, guild_id, message_id, channel_id)
    await message.pin(reason=reason or "discord_cli message pin")
    return {"pinned": message_to_dict(message)}


async def action_message_unpin(
    client: discord.Client,
    guild_id: int | None,
    message_id: int | str,
    channel_id: int | str | None,
    reason: str | None = None,
    **_: Any,
) -> Any:
    _, message = await _resolve_message_target(client, guild_id, message_id, channel_id)
    await message.unpin(reason=reason or "discord_cli message unpin")
    return {"unpinned": message_to_dict(message)}


async def action_message_pins(
    client: discord.Client,
    guild_id: int | None,
    channel_id: int | str,
    limit: int = 50,
    **_: Any,
) -> dict[str, Any]:
    if limit <= 0:
        raise CliError("--limit must be a positive integer")
    guild = await get_guild(client, guild_id)
    channel = await resolve_channel_selector(guild, channel_id, client=client)
    if not hasattr(channel, "pins"):
        raise CliError("Channel does not support pinned messages")
    pins_result = (
        channel.pins(limit=limit)
        if "limit" in str(inspect.signature(channel.pins))
        else channel.pins()
    )  # type: ignore[union-attr]
    if hasattr(pins_result, "__aiter__"):
        pinned = [message_to_dict(m) async for m in pins_result][:limit]
    else:
        pinned = [message_to_dict(m) for m in (await pins_result)][:limit]
    return {"channel_id": channel.id, "count": len(pinned), "messages": pinned}


async def action_message_publish(
    client: discord.Client,
    guild_id: int | None,
    message_id: int | str,
    channel_id: int | str | None,
    **_: Any,
) -> dict[str, Any]:
    _, message = await _resolve_message_target(client, guild_id, message_id, channel_id)
    published = await message.publish()
    return {"published": message_to_dict(published or message)}


async def action_message_download(
    client: discord.Client,
    guild_id: int | None,
    message_id: int | str,
    channel_id: int | str | None,
    out_dir: str,
    **_: Any,
) -> dict[str, Any]:
    _, message = await _resolve_message_target(client, guild_id, message_id, channel_id)
    dest = Path(out_dir)
    dest.mkdir(parents=True, exist_ok=True)
    saved: list[dict[str, Any]] = []
    for idx, attachment in enumerate(message.attachments):
        att_id = getattr(attachment, "id", idx)
        safe_name = _safe_attachment_filename(att_id, attachment.filename)
        target_path = (dest / safe_name).resolve()
        if dest.resolve() not in target_path.parents:
            raise CliError(f"Unsafe attachment path rejected: {attachment.filename}")
        await attachment.save(target_path)
        saved.append(
            {
                "id": att_id,
                "filename": attachment.filename,
                "saved_path": str(target_path),
                "size": attachment.size,
            }
        )
    return {"message_id": message.id, "count": len(saved), "files": saved}


async def action_message_react(
    client: discord.Client,
    guild_id: int | None,
    message_id: int | str,
    channel_id: int | str | None,
    emoji: str,
    **_: Any,
) -> Any:
    _, message = await _resolve_message_target(client, guild_id, message_id, channel_id)
    await message.add_reaction(emoji)
    return {"reacted": {"message_id": message.id, "emoji": emoji}}


async def action_message_unreact(
    client: discord.Client,
    guild_id: int | None,
    message_id: int | str,
    channel_id: int | str | None,
    emoji: str,
    user_id: int | str | None = None,
    **_: Any,
) -> dict[str, Any]:
    guild, message = await _resolve_message_target(client, guild_id, message_id, channel_id)
    resolved_user_id = (
        await resolve_member_id(guild, user_id, client=client) if user_id is not None else None
    )
    target = discord.Object(id=resolved_user_id) if resolved_user_id is not None else client.user
    if target is None:
        raise CliError("Could not determine target user for unreact; pass --user <id>")
    await message.remove_reaction(emoji, target)
    return {
        "unreacted": {
            "message_id": message.id,
            "emoji": emoji,
            "user_id": getattr(target, "id", resolved_user_id),
        }
    }
