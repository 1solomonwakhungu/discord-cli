"""Human-friendly resource selector parsing and fail-closed Discord entity resolution.

Supports raw numeric snowflakes alongside ergonomic selectors:
- Channels: `#general`, `cat:Engineering/#alerts`, `<#123...>`, or unambiguous name
- Categories: `cat:Engineering` or unambiguous name
- Roles: `role:Ops`, `@everyone`, `<@&123...>`, or unambiguous name
- Members: `@alice`, `user:alice`, `<@123...>`, `<@!123...>`
- Message URLs: `https://discord.com/channels/<guild_id>/<channel_id>/<message_id>`
- Guild aliases: resolved from config TOML `[guilds]` map
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import click
import discord

from discord_cli.errors import AmbiguousSelectorError, CliError, NotFoundError
from discord_cli.models import (
    fetch_guild_channels,
    fetch_guild_roles,
    get_member,
    is_rest_mode,
    resolve_category,
    resolve_channel,
    resolve_role,
)
from discord_cli.policy import (
    enforce_runtime_channel_allowlist,
    is_ascii_snowflake,
    parse_ascii_snowflake,
)

_CHANNEL_MENTION_RE = re.compile(r"^<#([0-9]+)>$")
_ROLE_MENTION_RE = re.compile(r"^<@&([0-9]+)>$")
_USER_MENTION_RE = re.compile(r"^<@!?([0-9]+)>$")
_MESSAGE_URL_RE = re.compile(
    r"^https?://(?:(?:ptb|canary)\.)?discord(?:app)?\.com/channels/([0-9]+)/([0-9]+)/([0-9]+)/?$"
)


class ResourceIdParamType(click.ParamType):
    """Click parameter type accepting either a valid ASCII snowflake ID or a human selector string."""

    name = "resource"

    def convert(self, value: Any, param: Any, ctx: Any) -> int | str:
        if isinstance(value, int) and not isinstance(value, bool):
            parsed = parse_ascii_snowflake(value)
            if parsed is None:
                self.fail(f"Discord snowflake ID out of range: {value}", param, ctx)
            return parsed
        if not isinstance(value, str):
            self.fail(f"Invalid resource identifier: {value!r}", param, ctx)
        stripped = value.strip()
        if not stripped:
            self.fail("Resource identifier cannot be empty.", param, ctx)
        if stripped.isascii() and stripped.isdigit():
            parsed = parse_ascii_snowflake(stripped)
            if parsed is None:
                self.fail(f"Discord snowflake ID out of range: {stripped}", param, ctx)
            return parsed
        return stripped


RESOURCE_ID = ResourceIdParamType()


@dataclass(frozen=True)
class MessageUrlParts:
    guild_id: int
    channel_id: int
    message_id: int


def parse_message_url(value: int | str) -> MessageUrlParts | None:
    """Parse a Discord message link (`https://discord.com/channels/<g>/<c>/<m>`)."""
    if not isinstance(value, str):
        return None
    match = _MESSAGE_URL_RE.match(value.strip())
    if not match:
        return None
    g_raw, c_raw, m_raw = match.group(1), match.group(2), match.group(3)
    if not (is_ascii_snowflake(g_raw) and is_ascii_snowflake(c_raw) and is_ascii_snowflake(m_raw)):
        return None
    return MessageUrlParts(
        guild_id=int(g_raw),
        channel_id=int(c_raw),
        message_id=int(m_raw),
    )


def parse_snowflake(value: int | str) -> int | None:
    """Return a validated integer snowflake in (0, 2^64) for int, ASCII digits, or Discord mention."""
    direct = parse_ascii_snowflake(value)
    if direct is not None:
        return direct
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    for pattern in (_CHANNEL_MENTION_RE, _ROLE_MENTION_RE, _USER_MENTION_RE):
        match = pattern.match(stripped)
        if match:
            return parse_ascii_snowflake(match.group(1))
    return None


def _disambiguate_matches(
    selector: str,
    kind: str,
    exact_matches: list[Any],
    ci_matches: list[Any],
    formatter: Any,
) -> Any:
    """Select an unambiguous match or raise AmbiguousSelectorError / NotFoundError."""
    chosen = exact_matches if exact_matches else ci_matches
    if len(chosen) == 1:
        return chosen[0]
    if len(chosen) > 1:
        candidates = [formatter(item) for item in chosen]
        raise AmbiguousSelectorError(
            f"Ambiguous {kind} selector {selector!r}: matched {len(candidates)} {kind}s.",
            candidates=candidates,
        )
    raise NotFoundError(f"{kind.capitalize()} not found for selector: {selector}")


async def resolve_channel_selector(
    guild: discord.Guild,
    selector: int | str,
    *,
    client: discord.Client | None = None,
) -> discord.abc.GuildChannel | discord.Thread:
    """Resolve a snowflake, `<#id>`, `#name`, `cat:Cat/#name`, or unambiguous channel name."""
    direct = parse_snowflake(selector)
    if direct is not None:
        channel = await resolve_channel(guild, direct, client=client)
        enforce_runtime_channel_allowlist(channel.id)
        return channel

    raw = str(selector).strip()
    cat_filter: str | None = None
    channel_name = raw

    if "/" in raw:
        left, right = raw.split("/", 1)
        left_clean = left.strip()
        if left_clean.lower().startswith("cat:"):
            left_clean = left_clean[4:].strip()
        cat_filter = left_clean
        channel_name = right.strip()

    if channel_name.startswith("#"):
        channel_name = channel_name[1:].strip()

    if not channel_name:
        raise CliError(f"Invalid channel selector: {selector!r}")

    channels = await fetch_guild_channels(guild, client=client)
    pool = [c for c in channels if not isinstance(c, discord.CategoryChannel)]

    if cat_filter is not None:
        cat_lower = cat_filter.lower()
        pool = [
            c
            for c in pool
            if getattr(c, "category", None) is not None
            and (
                c.category.name.lower() == cat_lower  # type: ignore[union-attr]
                or str(c.category.id) == cat_filter  # type: ignore[union-attr]
            )
        ]

    exact = [c for c in pool if c.name == channel_name]
    ci = [c for c in pool if c.name.lower() == channel_name.lower()]
    resolved = _disambiguate_matches(
        raw,
        "channel",
        exact,
        ci,
        lambda c: {
            "id": c.id,
            "name": c.name,
            "type": str(getattr(c, "type", "")),
            "category": getattr(getattr(c, "category", None), "name", None),
        },
    )
    enforce_runtime_channel_allowlist(resolved.id)
    return resolved


async def resolve_category_selector(
    guild: discord.Guild,
    selector: int | str | None,
    *,
    client: discord.Client | None = None,
) -> discord.CategoryChannel | None:
    """Resolve a snowflake or `cat:Name` / category name selector."""
    if selector is None:
        return None
    direct = parse_snowflake(selector)
    if direct is not None:
        cat = await resolve_category(guild, direct, client=client)
        if cat is not None:
            enforce_runtime_channel_allowlist(cat.id)
        return cat

    raw = str(selector).strip()
    cat_name = raw[4:].strip() if raw.lower().startswith("cat:") else raw
    if not cat_name:
        raise CliError(f"Invalid category selector: {selector!r}")

    categories = list(guild.categories)
    if not categories:
        all_channels = await fetch_guild_channels(guild, client=client)
        categories = [c for c in all_channels if isinstance(c, discord.CategoryChannel)]

    exact = [c for c in categories if c.name == cat_name]
    ci = [c for c in categories if c.name.lower() == cat_name.lower()]
    resolved = _disambiguate_matches(
        raw,
        "category",
        exact,
        ci,
        lambda c: {"id": c.id, "name": c.name},
    )
    enforce_runtime_channel_allowlist(resolved.id)
    return resolved


async def resolve_role_selector(
    guild: discord.Guild,
    selector: int | str,
    *,
    client: discord.Client | None = None,
) -> discord.Role:
    """Resolve a snowflake, `<@&id>`, `@everyone`, `role:Name`, or unambiguous role name."""
    direct = parse_snowflake(selector)
    if direct is not None:
        return await resolve_role(guild, direct, client=client)

    raw = str(selector).strip()
    roles = await fetch_guild_roles(guild, client=client)

    if raw.lower() in {"@everyone", "everyone"}:
        default_role = getattr(guild, "default_role", None)
        if default_role is not None:
            return default_role
        for role in roles:
            if role.id == guild.id or role.name == "@everyone":
                return role
        raise NotFoundError("Default @everyone role not found")

    role_name = raw[5:].strip() if raw.lower().startswith("role:") else raw
    if not role_name:
        raise CliError(f"Invalid role selector: {selector!r}")

    exact = [r for r in roles if r.name == role_name]
    ci = [r for r in roles if r.name.lower() == role_name.lower()]
    return _disambiguate_matches(
        raw,
        "role",
        exact,
        ci,
        lambda r: {"id": r.id, "name": r.name, "position": getattr(r, "position", 0)},
    )


async def resolve_member_selector(
    guild: discord.Guild,
    selector: int | str,
    *,
    client: discord.Client | None = None,
) -> discord.Member:
    """Resolve a snowflake, `<@id>`, `<@!id>`, `@name`, or `user:name` to a guild Member."""
    direct = parse_snowflake(selector)
    if direct is not None:
        return await get_member(guild, direct)

    raw = str(selector).strip()
    if raw.lower().startswith("user:"):
        query = raw[5:].strip()
    elif raw.startswith("@"):
        query = raw[1:].strip()
    else:
        query = raw
    if not query:
        raise CliError(f"Invalid member selector: {selector!r}")

    q_lower = query.lower()

    cached = list(getattr(guild, "members", []) or [])
    if cached:
        exact = [
            m
            for m in cached
            if m.name == query
            or getattr(m, "display_name", None) == query
            or getattr(m, "nick", None) == query
        ]
        ci = [
            m
            for m in cached
            if m.name.lower() == q_lower
            or str(getattr(m, "display_name", "")).lower() == q_lower
            or (getattr(m, "nick", None) or "").lower() == q_lower
        ]
        if exact or ci:
            return _disambiguate_matches(
                raw,
                "member",
                exact,
                ci,
                lambda m: {
                    "id": m.id,
                    "name": m.name,
                    "display_name": getattr(m, "display_name", m.name),
                },
            )

    if client is not None and (is_rest_mode(client) or not cached):
        route = discord.http.Route("GET", "/guilds/{guild_id}/members/search", guild_id=guild.id)
        raw_members = await client.http.request(route, params={"query": query, "limit": 25})
        matches: list[dict[str, Any]] = []
        exact_raw: list[dict[str, Any]] = []
        for entry in raw_members or []:
            user = entry.get("user") or {}
            uname = user.get("username", "")
            nick = entry.get("nick")
            gname = user.get("global_name")
            if query in (uname, nick, gname):
                exact_raw.append(entry)
            if q_lower in (
                uname.lower(),
                (nick or "").lower(),
                (gname or "").lower(),
            ):
                matches.append(entry)
        chosen = _disambiguate_matches(
            raw,
            "member",
            exact_raw,
            matches,
            lambda e: {
                "id": int((e.get("user") or {})["id"]),
                "name": (e.get("user") or {}).get("username", ""),
                "nick": e.get("nick"),
            },
        )
        uid = int(chosen["user"]["id"])
        return await get_member(guild, uid)

    raise NotFoundError(f"Member not found for selector: {selector}")


async def resolve_member_id(
    guild: discord.Guild,
    selector: int | str,
    *,
    client: discord.Client | None = None,
) -> int:
    """Resolve a member selector or snowflake to an integer user ID."""
    direct = parse_snowflake(selector)
    if direct is not None:
        return direct
    member = await resolve_member_selector(guild, selector, client=client)
    return member.id


def resolve_message_ref(
    message_ref: int | str,
    channel_ref: int | str | None = None,
    guild_id: int | None = None,
) -> tuple[int, int | str | None, int | None]:
    """Parse a message ID or Discord message URL into `(message_id, channel_ref, guild_id)`."""
    url_parts = parse_message_url(message_ref)
    if url_parts is not None:
        if guild_id is not None and guild_id != url_parts.guild_id:
            raise CliError(
                f"Message URL targets guild {url_parts.guild_id}, which conflicts with --guild {guild_id}."
            )
        return (
            url_parts.message_id,
            channel_ref if channel_ref is not None else url_parts.channel_id,
            guild_id if guild_id is not None else url_parts.guild_id,
        )
    direct = parse_snowflake(message_ref)
    if direct is not None:
        return direct, channel_ref, guild_id
    raise CliError(
        f"Invalid message identifier {message_ref!r}. Provide a numeric message ID or Discord message URL."
    )
