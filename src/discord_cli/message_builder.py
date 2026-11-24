"""Shared message, embed, attachment, template, and chunking builders for messages & webhooks."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import discord

from discord_cli.errors import CliError
from discord_cli.models import embed_from_json, parse_color

DISCORD_MAX_CONTENT_LENGTH = 2000

TEMPLATES: dict[str, dict[str, Any]] = {
    "success": {"color": 0x2ECC71, "prefix": "✅ "},
    "error": {"color": 0xE74C3C, "prefix": "❌ "},
    "warning": {"color": 0xF39C12, "prefix": "⚠️ "},
    "info": {"color": 0x3498DB, "prefix": "ℹ️ "},
    "deploy": {"color": 0x5865F2, "prefix": "🚀 "},
    "alert": {"color": 0xE91E63, "prefix": "🚨 "},
}


def resolve_content(content: str | None) -> str | None:
    """Resolve message content, reading stdin when content is '-'."""
    if content == "-":
        return sys.stdin.read()
    return content


def load_embed(
    *,
    embed_json: str | None = None,
    embed_file: str | None = None,
    template: str | None = None,
    title: str | None = None,
    description: str | None = None,
    color: str | None = None,
    fields: tuple[str, ...] | list[str] = (),
) -> discord.Embed | None:
    """Construct a discord.Embed from JSON, file, template, or ergonomic builder flags."""
    if embed_json and embed_file:
        raise CliError("Specify at most one of --embed-json or --embed-file")

    embed: discord.Embed | None = None
    if embed_file:
        path = Path(embed_file)
        if not path.is_file():
            raise CliError(f"Embed file not found: {embed_file}")
        raw = path.read_text(encoding="utf-8")
        embed = embed_from_json(raw)
    elif embed_json:
        if embed_json.startswith("@"):
            path = Path(embed_json[1:])
            if not path.is_file():
                raise CliError(f"Embed file not found: {path}")
            embed = embed_from_json(path.read_text(encoding="utf-8"))
        else:
            embed = embed_from_json(embed_json)

    has_builder = any([template, title, description, color, fields])
    if not has_builder:
        return embed

    if embed is None:
        embed = discord.Embed()

    if template:
        spec = TEMPLATES.get(template.lower())
        if spec is None:
            raise CliError(f"Unknown template: {template}")
        if embed.colour is None and color is None:
            embed.colour = discord.Color(spec["color"])
        if title and not title.startswith(spec["prefix"]):
            title = f"{spec['prefix']}{title}"
        elif title is None and embed.title is None:
            title = f"{spec['prefix']}{template.capitalize()}"

    if title is not None:
        embed.title = title
    if description is not None:
        embed.description = description
    if color is not None:
        embed.colour = parse_color(color)

    for raw_field in fields:
        if "=" not in raw_field:
            raise CliError(
                f"Invalid --field {raw_field!r}. Expected 'Name=Value' or 'Name=Value:inline'."
            )
        name, rest = raw_field.split("=", 1)
        inline = False
        if rest.endswith(":inline"):
            rest = rest[: -len(":inline")]
            inline = True
        embed.add_field(name=name.strip(), value=rest.strip(), inline=inline)

    return embed


def build_discord_files(file_paths: tuple[str, ...] | list[str]) -> list[discord.File]:
    """Validate and wrap local file paths as discord.File objects."""
    files: list[discord.File] = []
    for raw_path in file_paths:
        path = Path(raw_path)
        if not path.is_file():
            raise CliError(f"Attachment file not found: {raw_path}")
        files.append(discord.File(str(path), filename=path.name))
    return files


def split_content(content: str, max_length: int = DISCORD_MAX_CONTENT_LENGTH) -> list[str]:
    """Split long content into Discord-safe chunks (<= max_length), preferring newline boundaries."""
    if len(content) <= max_length:
        return [content]

    chunks: list[str] = []
    remaining = content
    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break
        split_at = remaining.rfind("\n", 0, max_length)
        if split_at <= max_length // 2:
            split_at = remaining.rfind(" ", 0, max_length)
        if split_at <= 0:
            split_at = max_length
        chunk = remaining[:split_at].rstrip()
        if not chunk:
            chunk = remaining[:max_length]
            split_at = max_length
        chunks.append(chunk)
        remaining = remaining[split_at:].lstrip("\n")
    return chunks


def parse_json_payload(raw: str | None) -> Any:
    """Parse JSON string or @filepath into a Python object."""
    if raw is None:
        return None
    text = raw
    if raw.startswith("@"):
        path = Path(raw[1:])
        if not path.is_file():
            raise CliError(f"JSON file not found: {path}")
        text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise CliError(f"Invalid JSON payload: {exc}") from exc
