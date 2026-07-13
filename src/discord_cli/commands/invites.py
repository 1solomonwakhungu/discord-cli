"""Invite management commands."""

from __future__ import annotations

import click

from ..client import run_bot
from ..output import output


@click.group()
def invites() -> None:
    """Manage server invites."""


@invites.command("list")
@click.pass_context
def list_invites(ctx: click.Context) -> None:
    """List all invites."""

    async def _action(client, **kwargs):
        guild = client.guilds[0]
        invites = await guild.invites()
        return [
            {
                "code": inv.code,
                "url": str(inv.url),
                "channel_id": inv.channel.id if inv.channel else None,
                "inviter_id": inv.inviter.id if inv.inviter else None,
                "max_uses": inv.max_uses,
                "uses": inv.uses,
                "max_age": inv.max_age,
                "temporary": inv.temporary,
                "created_at": inv.created_at.isoformat() if inv.created_at else None,
            }
            for inv in invites
        ]

    result, error = run_bot(_action, ctx=ctx)
    output(result, error, ctx)


@invites.command("create")
@click.option("--channel-id", required=True, help="Channel to create invite for")
@click.option("--max-age", type=int, default=0, help="Max age in seconds (0=never)")
@click.option("--max-uses", type=int, default=0, help="Max uses (0=unlimited)")
@click.option("--temporary", is_flag=True, help="Temporary membership")
@click.pass_context
def create_invite(ctx: click.Context, channel_id: int, max_age: int, max_uses: int, temporary: bool) -> None:
    """Create an invite."""

    async def _action(client, **kwargs):
        guild = client.guilds[0]
        channel = guild.get_channel(channel_id)
        if not channel:
            raise ValueError(f"Channel {channel_id} not found")
        invite = await channel.create_invite(
            max_age=max_age, max_uses=max_uses, temporary=temporary
        )
        return {"code": invite.code, "url": str(invite.url)}

    result, error = run_bot(_action, ctx=ctx)
    output(result, error, ctx)


@invites.command("delete")
@click.argument("code")
@click.pass_context
def delete_invite(ctx: click.Context, code: str) -> None:
    """Delete an invite by code."""

    async def _action(client, **kwargs):
        guild = client.guilds[0]
        invites = await guild.invites()
        for inv in invites:
            if inv.code == code:
                await inv.delete()
                return {"deleted": code}
        raise ValueError(f"Invite {code} not found")

    result, error = run_bot(_action, ctx=ctx)
    output(result, error, ctx)
