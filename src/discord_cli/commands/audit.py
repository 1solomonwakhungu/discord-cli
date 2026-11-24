"""Audit log inspection commands: list and user correlation."""

from __future__ import annotations

from typing import Any

import click
import discord

from discord_cli.errors import CliError
from discord_cli.models import get_guild, iso
from discord_cli.registry import invoke, registry


@registry.group("audit")
def audit_group() -> None:
    """Inspect guild audit logs for moderation and security triage."""


@audit_group.command("list")
@click.option("--limit", type=int, default=50, help="Max audit log entries to fetch (default: 50)")
@click.option("--action", "action_name", default=None, help="Filter by AuditLogAction name")
@click.option("--user", "user_id", type=int, default=None, help="Filter by actor user ID")
@click.option("--before", "before_id", type=int, default=None, help="Fetch entries before this ID")
@click.option("--after", "after_id", type=int, default=None, help="Fetch entries after this ID")
@click.pass_context
def audit_list(
    ctx: click.Context,
    limit: int,
    action_name: str | None,
    user_id: int | None,
    before_id: int | None,
    after_id: int | None,
) -> None:
    """List recent guild audit log entries."""
    invoke(
        ctx,
        action_audit_list,
        limit=limit,
        action_name=action_name,
        user_id=user_id,
        before_id=before_id,
        after_id=after_id,
    )


@audit_group.command("user")
@click.argument("user_id", type=int)
@click.option(
    "--limit", type=int, default=50, help="Max recent audit entries to scan (default: 50)"
)
@click.pass_context
def audit_user(ctx: click.Context, user_id: int, limit: int) -> None:
    """List audit log entries performed by or targeting a specific user ID."""
    invoke(ctx, action_audit_user, user_id=user_id, limit=limit)


def _audit_entry_to_dict(entry: Any) -> dict[str, Any]:
    actor = getattr(entry, "user", None)
    target = getattr(entry, "target", None)
    action = getattr(entry, "action", None)
    return {
        "id": entry.id,
        "action": getattr(action, "name", str(action)),
        "user": {"id": actor.id, "name": str(actor)} if actor is not None else None,
        "target": {
            "id": getattr(target, "id", None),
            "name": getattr(target, "name", str(target)) if target is not None else None,
            "type": target.__class__.__name__ if target is not None else None,
        }
        if target is not None
        else None,
        "reason": getattr(entry, "reason", None),
        "created_at": iso(getattr(entry, "created_at", None)),
    }


def _resolve_audit_action(action_name: str | None) -> Any:
    if not action_name:
        return None
    normalized = action_name.strip().lower()
    try:
        return discord.AuditLogAction[normalized]
    except KeyError:
        raise CliError(f"Unknown audit log action: {action_name}") from None


async def action_audit_list(
    client: discord.Client,
    guild_id: int | None,
    limit: int = 50,
    action_name: str | None = None,
    user_id: int | None = None,
    before_id: int | None = None,
    after_id: int | None = None,
    **_: Any,
) -> dict[str, Any]:
    if limit <= 0:
        raise CliError("--limit must be a positive integer")
    guild = await get_guild(client, guild_id)
    kwargs: dict[str, Any] = {"limit": limit}
    action_enum = _resolve_audit_action(action_name)
    if action_enum is not None:
        kwargs["action"] = action_enum
    if user_id is not None:
        kwargs["user"] = discord.Object(id=user_id)
    if before_id is not None:
        kwargs["before"] = discord.Object(id=before_id)
    if after_id is not None:
        kwargs["after"] = discord.Object(id=after_id)

    entries = [_audit_entry_to_dict(entry) async for entry in guild.audit_logs(**kwargs)]
    return {"guild_id": guild.id, "count": len(entries), "entries": entries}


async def action_audit_user(
    client: discord.Client,
    guild_id: int | None,
    user_id: int,
    limit: int = 50,
    **_: Any,
) -> dict[str, Any]:
    if limit <= 0:
        raise CliError("--limit must be a positive integer")
    guild = await get_guild(client, guild_id)
    matched: list[dict[str, Any]] = []
    async for entry in guild.audit_logs(limit=limit):
        actor_id = getattr(getattr(entry, "user", None), "id", None)
        target_id = getattr(getattr(entry, "target", None), "id", None)
        if actor_id == user_id or target_id == user_id:
            record = _audit_entry_to_dict(entry)
            record["role_in_entry"] = "actor" if actor_id == user_id else "target"
            matched.append(record)
    return {"guild_id": guild.id, "user_id": user_id, "count": len(matched), "entries": matched}
