"""Diagnostic command: verify auth, privileged intents, guild access, and bot permissions."""

from __future__ import annotations

from typing import Any

import click
import discord

from discord_cli.models import (
    fetch_guild_roles,
    get_guild,
    permissions_to_list,
    resolve_channel,
)
from discord_cli.registry import invoke, registry

# Discord ApplicationFlags bits for privileged gateway intents
_FLAG_GATEWAY_PRESENCE = 1 << 12
_FLAG_GATEWAY_PRESENCE_LIMITED = 1 << 13
_FLAG_GATEWAY_GUILD_MEMBERS = 1 << 14
_FLAG_GATEWAY_GUILD_MEMBERS_LIMITED = 1 << 15
_FLAG_GATEWAY_MESSAGE_CONTENT = 1 << 18
_FLAG_GATEWAY_MESSAGE_CONTENT_LIMITED = 1 << 19


@registry.group("doctor", invoke_without_command=True)
@click.pass_context
def doctor_group(ctx: click.Context) -> None:
    """Diagnose bot token, privileged intents, role hierarchy, and permissions."""
    if ctx.invoked_subcommand is None:
        invoke(ctx, action_doctor_check, channel_id=None)


@doctor_group.command("check")
@click.option(
    "--channel",
    "channel_id",
    type=int,
    default=None,
    help="Optional channel ID to inspect effective bot permissions in.",
)
@click.pass_context
def doctor_check(ctx: click.Context, channel_id: int | None) -> None:
    """Run connectivity, intent, hierarchy, and permission diagnostics."""
    invoke(ctx, action_doctor_check, channel_id=channel_id)


def _decode_intent_flags(flags: int) -> dict[str, bool]:
    return {
        "presence": bool(flags & (_FLAG_GATEWAY_PRESENCE | _FLAG_GATEWAY_PRESENCE_LIMITED)),
        "server_members": bool(
            flags & (_FLAG_GATEWAY_GUILD_MEMBERS | _FLAG_GATEWAY_GUILD_MEMBERS_LIMITED)
        ),
        "message_content": bool(
            flags & (_FLAG_GATEWAY_MESSAGE_CONTENT | _FLAG_GATEWAY_MESSAGE_CONTENT_LIMITED)
        ),
    }


async def action_doctor_check(
    client: discord.Client,
    guild_id: int | None,
    channel_id: int | None = None,
    **_: Any,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    bot_user = client.user
    bot_info = {"id": bot_user.id, "name": str(bot_user)} if bot_user is not None else None
    checks.append({"name": "auth", "status": "ok", "bot": bot_info})

    # Inspect application flags via REST /applications/@me (no Gateway connect needed).
    intents_status: dict[str, bool] | None = None
    app_id: int | None = None
    try:
        app_data = await client.http.request(discord.http.Route("GET", "/applications/@me"))
        if isinstance(app_data, dict):
            app_id = int(app_data["id"]) if app_data.get("id") else None
            flags = int(app_data.get("flags", 0))
            intents_status = _decode_intent_flags(flags)
            missing = [k for k, enabled in intents_status.items() if not enabled]
            checks.append(
                {
                    "name": "privileged_intents",
                    "status": "ok" if not missing else "warn",
                    "intents": intents_status,
                    "missing": missing,
                    "hint": (
                        f"Enable {', '.join(missing)} under Bot -> Privileged Gateway Intents "
                        f"in https://discord.com/developers/applications/{app_id or ''}/bot"
                        if missing
                        else None
                    ),
                }
            )
    except Exception as exc:  # noqa: BLE001 - diagnostic command should degrade gracefully
        checks.append({"name": "privileged_intents", "status": "warn", "detail": str(exc)})

    guild_report: dict[str, Any] | None = None
    channel_report: dict[str, Any] | None = None
    try:
        guild = await get_guild(client, guild_id)
        roles = await fetch_guild_roles(guild, client=client)
        bot_member = None
        if bot_user is not None:
            bot_member = guild.get_member(bot_user.id)
            if bot_member is None:
                try:
                    bot_member = await guild.fetch_member(bot_user.id)
                except Exception:  # noqa: BLE001
                    bot_member = None

        top_role_pos = bot_member.top_role.position if bot_member and bot_member.top_role else None
        max_role_pos = max((r.position for r in roles), default=0)
        guild_perms = (
            permissions_to_list(bot_member.guild_permissions) if bot_member is not None else []
        )
        guild_report = {
            "id": guild.id,
            "name": guild.name,
            "role_count": len(roles),
            "bot_top_role_position": top_role_pos,
            "max_role_position": max_role_pos,
            "bot_guild_permissions": guild_perms,
        }
        checks.append({"name": "guild", "status": "ok", "guild": guild_report})

        if channel_id is not None:
            channel = await resolve_channel(guild, channel_id, client=client)
            perms_list: list[str] = []
            if bot_member is not None and hasattr(channel, "permissions_for"):
                perms_list = permissions_to_list(channel.permissions_for(bot_member))  # type: ignore[arg-type]
            channel_report = {
                "id": channel.id,
                "name": channel.name,
                "type": str(channel.type),
                "bot_permissions": perms_list,
            }
            checks.append({"name": "channel", "status": "ok", "channel": channel_report})
    except Exception as exc:  # noqa: BLE001
        checks.append({"name": "guild", "status": "error", "detail": str(exc)})

    overall = "ok"
    if any(c["status"] == "error" for c in checks):
        overall = "error"
    elif any(c["status"] == "warn" for c in checks):
        overall = "warn"

    return {
        "status": overall,
        "bot": bot_info,
        "application_id": app_id,
        "intents": intents_status,
        "guild": guild_report,
        "channel": channel_report,
        "checks": checks,
    }
