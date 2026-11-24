"""Shared Discord object lookups and JSON-serialization helpers used by command modules."""

from __future__ import annotations

import datetime as dt
import ipaddress
import json
import re
import socket
import urllib.parse
from typing import Any

import aiohttp
import discord

from discord_cli.errors import CliError

_WEBHOOK_URL_RE = re.compile(
    r"(https?://(?:(?:www|canary|ptb)\.)?discord(?:app)?\.com/api(?:/v\d+)?/webhooks/\d+/)([^/?#\s'\"<>]+)",
    re.IGNORECASE,
)
_DISCORD_WEBHOOK_HOSTS = frozenset(
    {
        "discord.com",
        "www.discord.com",
        "ptb.discord.com",
        "canary.discord.com",
        "discordapp.com",
        "www.discordapp.com",
        "ptb.discordapp.com",
        "canary.discordapp.com",
    }
)
_CGNAT_V4 = ipaddress.ip_network("100.64.0.0/10")
_6TO4_RELAY_V4 = ipaddress.ip_network("192.88.99.0/24")
_SITE_LOCAL_V6 = ipaddress.ip_network("fec0::/10")

_MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MiB safety cap for remote image downloads
_MAX_REDIRECTS = 5
_CHUNK_SIZE = 65536


def is_rest_mode(client: discord.Client | None) -> bool:
    """Return True when running via the REST-only transport (no Gateway cache)."""
    return getattr(client, "_discord_cli_transport", None) == "rest"


def _session_cache(client: discord.Client | None) -> dict[Any, Any] | None:
    if client is None:
        return None
    cache = getattr(client, "_discord_cli_cache", None)
    if isinstance(cache, dict):
        return cache
    return None


def invalidate_guild_cache(client: discord.Client | None, guild_id: int) -> None:
    """Drop cached guild entries after a guild-level mutation."""
    cache = _session_cache(client)
    if cache is None:
        return
    cache.pop(("guild", guild_id), None)
    cache.pop("default_guild", None)


def bool_value(value: str | bool | None) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    lowered = value.lower()
    if lowered in {"1", "true", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "no", "n", "off"}:
        return False
    raise CliError(f"Invalid boolean value: {value}. Use true or false.")


def parse_color(value: str | None) -> discord.Color | None:
    if not value:
        return None
    text = value.strip().lstrip("#")
    if len(text) != 6 or not re.fullmatch(r"[0-9a-fA-F]{6}", text):
        raise CliError(f"Invalid color: {value}. Use HEX like #ff00aa.")
    return discord.Color(int(text, 16))


def parse_permissions(value: str | int | None) -> discord.Permissions | None:
    if value in (None, ""):
        return None
    if isinstance(value, int) or str(value).isdigit():
        return discord.Permissions(int(value))
    perms = discord.Permissions.none()
    for name in re.split(r"[, ]+", str(value).strip()):
        if not name:
            continue
        if not hasattr(perms, name):
            raise CliError(f"Unknown permission: {name}")
        setattr(perms, name, True)
    return perms


def parse_duration(value: str) -> dt.timedelta:
    match = re.fullmatch(r"\s*(\d+)\s*([smhdw])\s*", value.lower())
    if not match:
        raise CliError("Duration must look like 30s, 5m, 1h, 2d, or 1w")
    amount = int(match.group(1))
    unit = match.group(2)
    return {
        "s": dt.timedelta(seconds=amount),
        "m": dt.timedelta(minutes=amount),
        "h": dt.timedelta(hours=amount),
        "d": dt.timedelta(days=amount),
        "w": dt.timedelta(weeks=amount),
    }[unit]


def iso(value: Any) -> Any:
    if isinstance(value, dt.datetime):
        return value.isoformat()
    return value


def redact_webhook_url(text: Any) -> Any:
    """Mask secret Discord webhook tokens anywhere inside a URL or arbitrary string."""
    if not text or not isinstance(text, str):
        return text
    return _WEBHOOK_URL_RE.sub(r"\1[REDACTED]", text)


def validate_webhook_url(url: str) -> str:
    """Validate that `url` is a Discord webhook URL without doing DNS SSRF checks."""
    cleaned = url.strip()
    parsed = urllib.parse.urlparse(cleaned)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise CliError("Invalid webhook URL: only http/https Discord webhook URLs are supported.")
    host = (parsed.hostname or "").lower()
    if host not in _DISCORD_WEBHOOK_HOSTS:
        raise CliError(f"Invalid webhook host: {host!r}. Must be a discord.com webhook URL.")
    if not _WEBHOOK_URL_RE.search(cleaned):
        raise CliError("Invalid Discord webhook URL format.")
    return cleaned


def permissions_to_list(perms: discord.Permissions | discord.PermissionOverwrite) -> list[str]:
    return [name for name, allowed in perms if allowed is True]


def overwrite_to_dict(
    target: discord.Role | discord.Member | discord.Object,
    overwrite: discord.PermissionOverwrite,
) -> dict[str, Any]:
    allow, deny = overwrite.pair()
    if isinstance(target, discord.Role):
        target_type = "role"
    elif isinstance(target, discord.Member):
        target_type = "member"
    else:
        target_type = "object"
    return {
        "target_id": target.id,
        "target_name": getattr(target, "name", str(target)),
        "target_type": target_type,
        "allow": permissions_to_list(allow),
        "deny": permissions_to_list(deny),
        "allow_value": allow.value,
        "deny_value": deny.value,
    }


def role_to_dict(
    role: discord.Role,
    include_permissions: bool = True,
    *,
    rest_mode: bool = False,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": role.id,
        "name": role.name,
        "color": str(role.color),
        "color_value": role.color.value,
        "position": role.position,
        "managed": role.managed,
        "mentionable": role.mentionable,
        "hoist": role.hoist,
        "member_count": None if rest_mode else len(role.members),
    }
    if include_permissions:
        data["permissions"] = permissions_to_list(role.permissions)
        data["permissions_value"] = role.permissions.value
    return data


def member_to_dict(
    member: discord.Member,
    detailed: bool = False,
    *,
    rest_mode: bool = False,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": member.id,
        "name": member.name,
        "display_name": member.display_name,
        "nick": member.nick,
        "bot": member.bot,
        "joined_at": iso(member.joined_at),
        "created_at": iso(member.created_at),
        "roles": [
            {"id": role.id, "name": role.name} for role in member.roles if role.name != "@everyone"
        ],
        "top_role": {"id": member.top_role.id, "name": member.top_role.name}
        if member.top_role
        else None,
    }
    if detailed:
        data.update(
            {
                "status": None if rest_mode else str(member.status),
                "premium_since": iso(member.premium_since),
                "timed_out_until": iso(member.timed_out_until),
                "guild_permissions": permissions_to_list(member.guild_permissions),
                "guild_permissions_value": member.guild_permissions.value,
                "avatar_url": str(member.display_avatar.url) if member.display_avatar else None,
            }
        )
    return data


def channel_to_dict(
    channel: discord.abc.GuildChannel | discord.Thread, detailed: bool = False
) -> dict[str, Any]:
    category_obj = getattr(channel, "category", None)
    category_id = getattr(category_obj, "id", None)
    if category_id is None:
        category_id = getattr(channel, "category_id", None)
    data: dict[str, Any] = {
        "id": channel.id,
        "name": channel.name,
        "type": str(channel.type),
        "position": getattr(channel, "position", None),
        "category_id": category_id,
        "category": getattr(category_obj, "name", None),
        "topic": getattr(channel, "topic", None),
        "nsfw": getattr(channel, "nsfw", None),
        "slowmode_delay": getattr(channel, "slowmode_delay", None),
    }
    if isinstance(channel, discord.Thread):
        data.update(
            {
                "parent_id": channel.parent_id,
                "archived": channel.archived,
                "locked": channel.locked,
                "member_count": channel.member_count,
                "message_count": channel.message_count,
            }
        )
    if detailed and hasattr(channel, "overwrites"):
        data["overwrites"] = [
            overwrite_to_dict(target, overwrite)
            for target, overwrite in channel.overwrites.items()  # type: ignore[arg-type]
        ]
    return data


def message_to_dict(message: discord.Message) -> dict[str, Any]:
    return {
        "id": message.id,
        "channel_id": message.channel.id,
        "guild_id": message.guild.id if message.guild else None,
        "author": {
            "id": message.author.id,
            "name": str(message.author),
            "bot": getattr(message.author, "bot", None),
        },
        "content": message.content,
        "created_at": iso(message.created_at),
        "edited_at": iso(message.edited_at),
        "pinned": message.pinned,
        "attachments": [
            {"url": a.url, "filename": a.filename, "size": a.size} for a in message.attachments
        ],
        "embeds": [embed.to_dict() for embed in message.embeds],
        "reactions": [{"emoji": str(r.emoji), "count": r.count} for r in message.reactions],
    }


def webhook_to_dict(webhook: discord.Webhook, *, show_secrets: bool = False) -> dict[str, Any]:
    raw_url = webhook.url
    url = raw_url if show_secrets else redact_webhook_url(raw_url)
    data: dict[str, Any] = {
        "id": webhook.id,
        "name": webhook.name,
        "channel_id": webhook.channel_id,
        "guild_id": webhook.guild_id,
        "user": {"id": webhook.user.id, "name": str(webhook.user)} if webhook.user else None,
        "url": url,
        "type": str(webhook.type),
        "created_at": iso(webhook.created_at),
    }
    if not show_secrets and url != raw_url:
        data["url_redacted"] = True
    return data


def invite_to_dict(invite: discord.Invite) -> dict[str, Any]:
    return {
        "code": invite.code,
        "url": invite.url,
        "channel_id": invite.channel.id if invite.channel else None,
        "channel_name": invite.channel.name if invite.channel else None,  # type: ignore[union-attr]
        "inviter": {"id": invite.inviter.id, "name": str(invite.inviter)}
        if invite.inviter
        else None,
        "uses": invite.uses,
        "max_uses": invite.max_uses,
        "max_age": invite.max_age,
        "temporary": invite.temporary,
        "created_at": iso(invite.created_at),
        "expires_at": iso(invite.expires_at),
    }


def embed_from_json(embed_json: str) -> discord.Embed:
    try:
        payload = json.loads(embed_json)
    except json.JSONDecodeError as exc:
        raise CliError(f"Invalid embed JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise CliError("Embed JSON must be an object")
    return discord.Embed.from_dict(payload)


def _is_forbidden_ip(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True for any non-globally-routable or multicast IP (including CGNAT/site-local)."""
    if isinstance(addr, ipaddress.IPv6Address):
        if addr.ipv4_mapped is not None:
            addr = addr.ipv4_mapped
        elif addr in _SITE_LOCAL_V6:
            return True
    if isinstance(addr, ipaddress.IPv4Address):
        if addr in _CGNAT_V4 or addr in _6TO4_RELAY_V4:
            return True
    return (not addr.is_global) or addr.is_multicast


def _check_url_syntax_and_literal(url: str) -> tuple[urllib.parse.ParseResult, str]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise CliError(f"Unsupported URL scheme: {parsed.scheme!r}. Only http/https allowed.")
    host = parsed.hostname
    if not host:
        raise CliError("Invalid URL (missing hostname)")
    lowered = host.rstrip(".").lower()
    if lowered in {"localhost", "localhost.localdomain"} or lowered.endswith(".local"):
        raise CliError(f"Refusing to fetch from local hostname: {host}")

    try:
        ip_literal = ipaddress.ip_address(host)
    except ValueError:
        ip_literal = None
    if ip_literal is not None and _is_forbidden_ip(ip_literal):
        raise CliError(f"Refusing to fetch from non-public IP address: {host}")
    return parsed, host


def validate_remote_url(url: str) -> str:
    """Validate an http(s) URL and block non-global/CGNAT/site-local/multicast SSRF targets."""
    parsed, host = _check_url_syntax_and_literal(url)
    try:
        ipaddress.ip_address(host)
        return url
    except ValueError:
        pass

    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise CliError(f"Could not resolve hostname {host!r}: {exc}") from exc

    if not infos:
        raise CliError(f"Could not resolve hostname {host!r}")

    for info in infos:
        sockaddr = info[4]
        resolved_ip = ipaddress.ip_address(sockaddr[0])
        if _is_forbidden_ip(resolved_ip):
            raise CliError(
                f"Refusing to fetch from {host!r}: resolved to non-public IP {resolved_ip}"
            )
    return url


class _SafeResolver(aiohttp.resolver.ThreadedResolver):
    """aiohttp DNS resolver that validates every resolved IP at connect time (prevents DNS rebinding)."""

    async def resolve(
        self,
        host: str,
        port: int = 0,
        family: socket.AddressFamily = socket.AF_UNSPEC,
    ) -> list[dict[str, Any]]:
        results = await super().resolve(host, port, family)
        for entry in results:
            ip = ipaddress.ip_address(entry["host"])
            if _is_forbidden_ip(ip):
                raise CliError(f"Refusing to connect to {host!r}: resolved to non-public IP {ip}")
        return results


async def read_image_bytes_async(source: str) -> bytes:
    """Read image bytes asynchronously via aiohttp (rebinding-safe + chunked full read) or local file."""
    if re.match(r"^https?://", source, re.IGNORECASE):
        current_url = source
        _check_url_syntax_and_literal(current_url)
        timeout = aiohttp.ClientTimeout(total=30)
        connector = aiohttp.TCPConnector(resolver=_SafeResolver())
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            for _ in range(_MAX_REDIRECTS + 1):
                _check_url_syntax_and_literal(current_url)
                async with session.get(current_url, allow_redirects=False) as resp:
                    if resp.status in {301, 302, 303, 307, 308}:
                        location = resp.headers.get("Location")
                        if not location:
                            raise CliError("Redirect response missing Location header")
                        current_url = urllib.parse.urljoin(current_url, location)
                        continue
                    resp.raise_for_status()
                    buf = bytearray()
                    async for chunk in resp.content.iter_chunked(_CHUNK_SIZE):
                        buf.extend(chunk)
                        if len(buf) > _MAX_IMAGE_BYTES:
                            raise CliError(
                                f"Remote image exceeds maximum allowed size ({_MAX_IMAGE_BYTES} bytes)"
                            )
                    return bytes(buf)
            raise CliError("Too many redirects while fetching remote image")
    with open(source, "rb") as image_file:
        return image_file.read()


async def _fetch_guild_by_id(client: discord.Client, guild_id: int) -> discord.Guild:
    cache = _session_cache(client)
    cache_key = ("guild", guild_id)
    if cache is not None and cache_key in cache:
        return cache[cache_key]
    try:
        guild = await client.fetch_guild(guild_id, with_counts=True)
    except TypeError:
        guild = await client.fetch_guild(guild_id)
    if guild is None:
        raise CliError(f"Guild not found: {guild_id}")
    if cache is not None:
        cache[cache_key] = guild
    return guild


async def get_guild(client: discord.Client, guild_id: int | None) -> discord.Guild:
    """Resolve the target guild via cache or REST, failing closed on multi-guild ambiguity."""
    from discord_cli.policy import enforce_runtime_guild_allowlist

    if guild_id is not None:
        enforce_runtime_guild_allowlist(guild_id)
        guild = client.get_guild(guild_id)
        if guild is not None:
            return guild
        return await _fetch_guild_by_id(client, guild_id)

    cached_guilds = list(client.guilds)
    if len(cached_guilds) > 1:
        listing = ", ".join(f"{g.name} ({g.id})" for g in cached_guilds[:10])
        raise CliError(
            f"Bot is in {len(cached_guilds)} guilds ({listing}). "
            "Specify --guild <id> or set DISCORD_GUILD_ID."
        )
    if len(cached_guilds) == 1:
        enforce_runtime_guild_allowlist(cached_guilds[0].id)
        return cached_guilds[0]

    # REST-only mode: client.guilds is empty, so discover guilds over REST.
    cache = _session_cache(client)
    if cache is not None and "default_guild" in cache:
        cached = cache["default_guild"]
        enforce_runtime_guild_allowlist(cached.id)
        return cached

    if not hasattr(client, "fetch_guilds"):
        raise CliError("Bot is not in any guilds")

    discovered = [g async for g in client.fetch_guilds(limit=10)]
    if not discovered:
        raise CliError("Bot is not in any guilds")
    if len(discovered) > 1:
        listing = ", ".join(f"{g.name} ({g.id})" for g in discovered)
        raise CliError(
            f"Bot is in multiple guilds ({listing}). Specify --guild <id> or set DISCORD_GUILD_ID."
        )
    enforce_runtime_guild_allowlist(discovered[0].id)
    guild = await _fetch_guild_by_id(client, discovered[0].id)
    if cache is not None:
        cache["default_guild"] = guild
    return guild


async def fetch_guild_channels(
    guild: discord.Guild, client: discord.Client | None = None
) -> list[discord.abc.GuildChannel]:
    """Return guild channels, using cache if populated or fetching via REST (memoized)."""
    if guild.channels:
        return list(guild.channels)
    cache = _session_cache(client)
    cache_key = ("channels", guild.id)
    if cache is not None and cache_key in cache:
        return list(cache[cache_key])
    if hasattr(guild, "fetch_channels"):
        fetched = list(await guild.fetch_channels())
        if cache is not None:
            cache[cache_key] = fetched
        return fetched
    return []


async def fetch_guild_roles(
    guild: discord.Guild, client: discord.Client | None = None
) -> list[discord.Role]:
    """Return guild roles, using cache if populated or fetching via REST (memoized)."""
    if guild.roles:
        return list(guild.roles)
    cache = _session_cache(client)
    cache_key = ("roles", guild.id)
    if cache is not None and cache_key in cache:
        return list(cache[cache_key])
    if hasattr(guild, "fetch_roles"):
        fetched = list(await guild.fetch_roles())
        if cache is not None:
            cache[cache_key] = fetched
        return fetched
    return []


def get_channel(guild: discord.Guild, channel_id: int) -> discord.abc.GuildChannel | discord.Thread:
    channel = guild.get_channel_or_thread(channel_id)
    if channel is None:
        raise CliError(f"Channel not found: {channel_id}")
    return channel


async def resolve_channel(
    guild: discord.Guild, channel_id: int, client: discord.Client | None = None
) -> discord.abc.GuildChannel | discord.Thread:
    """Look up a channel or thread belonging to `guild` via cache first, then REST fetch."""
    from discord_cli.policy import enforce_runtime_channel_allowlist

    enforce_runtime_channel_allowlist(channel_id)
    channel = guild.get_channel_or_thread(channel_id)
    if channel is not None:
        return channel
    cache = _session_cache(client)
    cache_key = ("channel", guild.id, channel_id)
    if cache is not None and cache_key in cache:
        return cache[cache_key]
    for fetcher in (getattr(guild, "fetch_channel", None), getattr(client, "fetch_channel", None)):
        if fetcher is None:
            continue
        try:
            fetched = await fetcher(channel_id)
        except discord.NotFound:
            continue
        if fetched is not None and isinstance(fetched, (discord.abc.GuildChannel, discord.Thread)):
            fetched_guild = getattr(fetched, "guild", None)
            fetched_guild_id = (
                getattr(fetched_guild, "id", None)
                if fetched_guild is not None
                else getattr(fetched, "guild_id", None)
            )
            if isinstance(fetched_guild_id, int) and fetched_guild_id != guild.id:
                continue
            if cache is not None:
                cache[cache_key] = fetched
            return fetched
    raise CliError(f"Channel not found: {channel_id}")


def get_category(guild: discord.Guild, category_id: int | None) -> discord.CategoryChannel | None:
    if category_id is None:
        return None
    category = guild.get_channel(category_id)
    if not isinstance(category, discord.CategoryChannel):
        raise CliError(f"Category not found: {category_id}")
    return category


async def resolve_category(
    guild: discord.Guild, category_id: int | None, client: discord.Client | None = None
) -> discord.CategoryChannel | None:
    """Look up a category channel via cache first, then REST fetch."""
    if category_id is None:
        return None
    category = guild.get_channel(category_id)
    if isinstance(category, discord.CategoryChannel):
        return category
    try:
        fetched = await resolve_channel(guild, category_id, client=client)
    except CliError:
        raise CliError(f"Category not found: {category_id}") from None
    if not isinstance(fetched, discord.CategoryChannel):
        raise CliError(f"Category not found: {category_id}")
    return fetched


async def get_member(guild: discord.Guild, member_id: int) -> discord.Member:
    member = guild.get_member(member_id)
    if member is None:
        member = await guild.fetch_member(member_id)
    if member is None:
        raise CliError(f"Member not found: {member_id}")
    return member


def get_role(guild: discord.Guild, role_id: int) -> discord.Role:
    role = guild.get_role(role_id)
    if role is None:
        raise CliError(f"Role not found: {role_id}")
    return role


async def resolve_role(
    guild: discord.Guild, role_id: int, client: discord.Client | None = None
) -> discord.Role:
    """Look up a role via cache first, then memoized guild.fetch_roles()."""
    role = guild.get_role(role_id)
    if role is not None:
        return role
    for candidate in await fetch_guild_roles(guild, client=client):
        if candidate.id == role_id:
            return candidate
    raise CliError(f"Role not found: {role_id}")


async def get_message(
    guild: discord.Guild,
    channel_id: int,
    message_id: int,
    client: discord.Client | None = None,
) -> discord.Message:
    channel = await resolve_channel(guild, channel_id, client=client)
    if not isinstance(
        channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel, discord.StageChannel)
    ):
        raise CliError("Channel does not support messages")
    return await channel.fetch_message(message_id)
