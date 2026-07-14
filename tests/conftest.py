"""Shared pytest fixtures: fake discord.py objects and an offline CLI harness.

Every command test drives the real Click CLI through ``CliRunner`` and the
real ``discord_cli.registry.invoke`` -> ``run_action`` call chain, but
``run_action`` itself is replaced (see ``patch_run_action`` below) with a
stand-in that runs the *real* action coroutine against a fake
``discord.Client`` instead of opening a network connection. This means
command option parsing, the action business logic, and JSON output
formatting are all exercised for real; only the Discord gateway connection
is faked.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from click.testing import CliRunner

from discord_cli.errors import DiscordCliError
from discord_cli.output import make_payload, print_output


# ---------------------------------------------------------------------------
# Fake discord.py object factories.
#
# MagicMock(spec=discord.X) is used (rather than plain objects) so that
# isinstance(fake, discord.X) succeeds -- several command modules and
# model helpers branch on isinstance checks against real discord.py types.
# ---------------------------------------------------------------------------


def make_role(
    *,
    id: int = 100,
    name: str = "TestRole",
    color: discord.Color | None = None,
    position: int = 1,
    managed: bool = False,
    mentionable: bool = False,
    hoist: bool = False,
    members: list[Any] | None = None,
    permissions: discord.Permissions | None = None,
) -> MagicMock:
    role = MagicMock(spec=discord.Role)
    role.id = id
    role.name = name
    role.color = color if color is not None else discord.Color.default()
    role.colour = role.color
    role.position = position
    role.managed = managed
    role.mentionable = mentionable
    role.hoist = hoist
    role.members = members or []
    role.permissions = permissions if permissions is not None else discord.Permissions.none()
    role.edit = AsyncMock(return_value=None)
    role.delete = AsyncMock(return_value=None)
    return role


def make_user(*, id: int = 900, name: str = "testuser", bot: bool = False) -> MagicMock:
    user = MagicMock(spec=discord.User)
    user.id = id
    user.name = name
    user.bot = bot
    user.__str__.return_value = f"{name}#0001"
    return user


def make_member(
    *,
    id: int = 200,
    name: str = "TestMember",
    display_name: str | None = None,
    nick: str | None = None,
    bot: bool = False,
    joined_at=None,
    created_at=None,
    roles: list[Any] | None = None,
    top_role: Any = None,
    guild_permissions: discord.Permissions | None = None,
    status: str = "online",
    premium_since=None,
    timed_out_until=None,
    display_avatar: Any = None,
) -> MagicMock:
    member = MagicMock(spec=discord.Member)
    member.id = id
    member.name = name
    member.display_name = display_name or name
    member.nick = nick
    member.bot = bot
    member.joined_at = joined_at
    member.created_at = created_at
    member.roles = roles or []
    member.top_role = top_role
    member.guild_permissions = (
        guild_permissions if guild_permissions is not None else discord.Permissions.none()
    )
    member.status = status
    member.premium_since = premium_since
    member.timed_out_until = timed_out_until
    member.display_avatar = display_avatar
    member.__str__.return_value = f"{name}#0001"
    member.add_roles = AsyncMock(return_value=None)
    member.remove_roles = AsyncMock(return_value=None)
    member.kick = AsyncMock(return_value=None)
    member.ban = AsyncMock(return_value=None)
    member.timeout = AsyncMock(return_value=None)
    member.edit = AsyncMock(return_value=None)
    return member


def make_text_channel(
    *,
    id: int = 300,
    name: str = "general",
    position: int = 0,
    category: Any = None,
    topic: str | None = None,
    nsfw: bool = False,
    slowmode_delay: int = 0,
    overwrites: dict[Any, discord.PermissionOverwrite] | None = None,
    threads: list[Any] | None = None,
) -> MagicMock:
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = id
    channel.name = name
    channel.type = discord.ChannelType.text
    channel.position = position
    channel.category = category
    channel.topic = topic
    channel.nsfw = nsfw
    channel.slowmode_delay = slowmode_delay
    channel.overwrites = overwrites or {}
    channel.threads = threads or []
    channel.guild = None
    channel.edit = AsyncMock(return_value=None)
    channel.delete = AsyncMock(return_value=None)
    channel.send = AsyncMock()
    channel.purge = AsyncMock(return_value=[])
    channel.set_permissions = AsyncMock(return_value=None)
    channel.create_webhook = AsyncMock()
    channel.create_invite = AsyncMock()
    channel.create_thread = AsyncMock()
    channel.webhooks = AsyncMock(return_value=[])
    channel.history = MagicMock(return_value=async_iter([]))
    channel.fetch_message = AsyncMock()
    return channel


def make_voice_channel(
    *, id: int = 310, name: str = "voice", position: int = 0, category: Any = None
) -> MagicMock:
    channel = MagicMock(spec=discord.VoiceChannel)
    channel.id = id
    channel.name = name
    channel.type = discord.ChannelType.voice
    channel.position = position
    channel.category = category
    channel.edit = AsyncMock(return_value=None)
    channel.delete = AsyncMock(return_value=None)
    return channel


def make_category(
    *, id: int = 400, name: str = "TestCategory", position: int = 0
) -> MagicMock:
    category = MagicMock(spec=discord.CategoryChannel)
    category.id = id
    category.name = name
    category.type = discord.ChannelType.category
    category.position = position
    category.category = None
    category.topic = None
    category.nsfw = False
    category.slowmode_delay = None
    category.edit = AsyncMock(return_value=None)
    category.delete = AsyncMock(return_value=None)
    return category


def make_thread(
    *,
    id: int = 500,
    name: str = "TestThread",
    parent_id: int = 300,
    archived: bool = False,
    locked: bool = False,
    member_count: int = 1,
    message_count: int = 0,
) -> MagicMock:
    thread = MagicMock(spec=discord.Thread)
    thread.id = id
    thread.name = name
    thread.type = discord.ChannelType.public_thread
    thread.position = None
    thread.category = None
    thread.topic = None
    thread.nsfw = False
    thread.slowmode_delay = 0
    thread.parent_id = parent_id
    thread.archived = archived
    thread.locked = locked
    thread.member_count = member_count
    thread.message_count = message_count
    thread.edit = AsyncMock(return_value=None)
    thread.delete = AsyncMock(return_value=None)
    thread.send = AsyncMock()
    thread.fetch_members = AsyncMock(return_value=[])
    return thread


def make_message(
    *,
    id: int = 600,
    channel: Any = None,
    guild: Any = None,
    author: Any = None,
    content: str = "hello world",
    created_at=None,
    edited_at=None,
    pinned: bool = False,
    attachments: list[Any] | None = None,
    embeds: list[Any] | None = None,
    reactions: list[Any] | None = None,
) -> MagicMock:
    message = MagicMock(spec=discord.Message)
    message.id = id
    message.channel = channel or make_text_channel()
    message.guild = guild
    message.author = author or make_member()
    message.content = content
    message.created_at = created_at
    message.edited_at = edited_at
    message.pinned = pinned
    message.attachments = attachments or []
    message.embeds = embeds or []
    message.reactions = reactions or []
    message.edit = AsyncMock(return_value=message)
    message.delete = AsyncMock(return_value=None)
    message.pin = AsyncMock(return_value=None)
    message.unpin = AsyncMock(return_value=None)
    message.add_reaction = AsyncMock(return_value=None)
    return message


def make_webhook(
    *,
    id: int = 700,
    name: str = "TestWebhook",
    channel_id: int = 300,
    guild_id: int = 1,
    user: Any = None,
    url: str = "https://discord.com/api/webhooks/700/fake-token-for-testing",
    created_at=None,
) -> MagicMock:
    webhook = MagicMock(spec=discord.Webhook)
    webhook.id = id
    webhook.name = name
    webhook.channel_id = channel_id
    webhook.guild_id = guild_id
    webhook.user = user
    webhook.url = url
    webhook.type = discord.WebhookType.incoming
    webhook.created_at = created_at
    webhook.delete = AsyncMock(return_value=None)
    return webhook


def make_invite(
    *,
    code: str = "abcdef",
    channel: Any = None,
    inviter: Any = None,
    uses: int = 0,
    max_uses: int = 0,
    max_age: int = 0,
    temporary: bool = False,
    created_at=None,
    expires_at=None,
) -> MagicMock:
    invite = MagicMock(spec=discord.Invite)
    invite.code = code
    invite.url = f"https://discord.gg/{code}"
    invite.channel = channel
    invite.inviter = inviter
    invite.uses = uses
    invite.max_uses = max_uses
    invite.max_age = max_age
    invite.temporary = temporary
    invite.created_at = created_at
    invite.expires_at = expires_at
    invite.delete = AsyncMock(return_value=None)
    return invite


async def async_iter(items: list[Any]):
    for item in items:
        yield item


def make_guild(
    *,
    id: int = 1,
    name: str = "TestGuild",
    description: str | None = None,
    owner: Any = None,
    owner_id: int = 200,
    member_count: int = 1,
    channels: list[Any] | None = None,
    categories: list[Any] | None = None,
    roles: list[Any] | None = None,
    members: list[Any] | None = None,
    emojis: list[Any] | None = None,
    stickers: list[Any] | None = None,
    threads: list[Any] | None = None,
    bans: list[Any] | None = None,
    invites: list[Any] | None = None,
    webhooks: list[Any] | None = None,
) -> MagicMock:
    guild = MagicMock(spec=discord.Guild)
    channels = channels or []
    categories = categories or []
    roles = roles or []
    members = members or []
    text_channels = [c for c in channels if getattr(c, "type", None) == discord.ChannelType.text]

    guild.id = id
    guild.name = name
    guild.description = description
    guild.owner = owner
    guild.owner_id = owner_id
    guild.member_count = member_count
    guild.channels = channels
    guild.categories = categories
    guild.text_channels = text_channels
    guild.roles = roles
    guild.members = members
    guild.emojis = emojis or []
    guild.stickers = stickers or []
    guild.premium_tier = 0
    guild.premium_subscription_count = 0
    guild.verification_level = discord.VerificationLevel.none
    guild.created_at = None
    guild.features = []
    guild.icon = None

    all_lookup: dict[int, Any] = {}
    for item in [*channels, *categories]:
        all_lookup[item.id] = item

    def _get_channel(channel_id: int) -> Any:
        item = all_lookup.get(channel_id)
        return item if item is not None and not isinstance(item, discord.Thread) else None

    thread_lookup = {t.id: t for t in (threads or [])}

    def _get_channel_or_thread(channel_id: int) -> Any:
        return all_lookup.get(channel_id) or thread_lookup.get(channel_id)

    def _get_role(role_id: int) -> Any:
        return next((r for r in roles if r.id == role_id), None)

    def _get_member(member_id: int) -> Any:
        return next((m for m in members if m.id == member_id), None)

    def _get_thread(thread_id: int) -> Any:
        return thread_lookup.get(thread_id)

    guild.get_channel = MagicMock(side_effect=_get_channel)
    guild.get_channel_or_thread = MagicMock(side_effect=_get_channel_or_thread)
    guild.get_role = MagicMock(side_effect=_get_role)
    guild.get_member = MagicMock(side_effect=_get_member)
    guild.get_thread = MagicMock(side_effect=_get_thread)

    guild.fetch_member = AsyncMock(side_effect=lambda mid: _get_member(mid))
    guild.fetch_members = MagicMock(side_effect=lambda **_: async_iter(members))
    guild.bans = MagicMock(side_effect=lambda **_: async_iter(bans or []))
    guild.invites = AsyncMock(return_value=invites or [])
    guild.webhooks = AsyncMock(return_value=webhooks or [])
    guild.unban = AsyncMock(return_value=None)
    guild.edit = AsyncMock(return_value=None)
    guild.create_category = AsyncMock()
    guild.create_text_channel = AsyncMock()
    guild.create_voice_channel = AsyncMock()
    guild.create_stage_channel = AsyncMock()
    guild.create_forum_channel = AsyncMock()
    guild.create_role = AsyncMock()
    guild.create_custom_emoji = AsyncMock()
    guild.estimate_pruned_members = AsyncMock(return_value=0)
    guild.prune_members = AsyncMock(return_value=0)

    return guild


def make_client(guild: Any) -> MagicMock:
    client = MagicMock(spec=discord.Client)
    client.guilds = [guild]
    client.get_guild = MagicMock(side_effect=lambda gid: guild if gid == guild.id else None)
    client.fetch_guild = AsyncMock(return_value=guild)
    client.fetch_user = AsyncMock(return_value=make_user())
    client.fetch_webhook = AsyncMock(return_value=make_webhook())
    client.http = MagicMock()
    client.http.request = AsyncMock(return_value=[])
    return client


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def guild_factory():
    return make_guild


@pytest.fixture
def role_factory():
    return make_role


@pytest.fixture
def member_factory():
    return make_member


@pytest.fixture
def user_factory():
    return make_user


@pytest.fixture
def channel_factory():
    return make_text_channel


@pytest.fixture
def voice_channel_factory():
    return make_voice_channel


@pytest.fixture
def category_factory():
    return make_category


@pytest.fixture
def thread_factory():
    return make_thread


@pytest.fixture
def message_factory():
    return make_message


@pytest.fixture
def webhook_factory():
    return make_webhook


@pytest.fixture
def invite_factory():
    return make_invite


@pytest.fixture
def client_factory():
    return make_client


@pytest.fixture
def fake_client_box() -> dict[str, Any]:
    """Mutable box that tests populate with the fake discord.Client to use."""
    return {}


@pytest.fixture(autouse=True)
def patch_run_action(monkeypatch, fake_client_box):
    """Replace discord_cli.registry.run_action with an offline equivalent.

    The real run_action connects to Discord's gateway. This stand-in runs
    the same action coroutine against whatever fake client the test placed
    in fake_client_box, then reuses the real make_payload/print_output so
    CLI output stays byte-for-byte what a real run would produce.
    """

    def _fake_run_action(action, kwargs, human=False, token=None):
        client = fake_client_box.get("client")
        try:
            result = asyncio.run(action(client, **kwargs))
            payload = make_payload(result=result)
        except DiscordCliError as exc:
            payload = make_payload(error={"type": exc.__class__.__name__, "message": str(exc)})
        print_output(payload, human)
        raise SystemExit(0 if payload["ok"] else 1)

    monkeypatch.setattr("discord_cli.registry.run_action", _fake_run_action)


@pytest.fixture
def use_client(fake_client_box):
    """Helper to register the fake client a test's CLI invocation should use."""

    def _use(client: Any) -> None:
        fake_client_box["client"] = client

    return _use
