"""Multi-profile TOML configuration, guild aliases, and optional OS keyring support."""

from __future__ import annotations

import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from discord_cli.errors import ConfigError

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.9/3.10 path
    import tomli as tomllib  # type: ignore[no-redef]

KEYRING_SERVICE = "discord-cli"
_PROFILE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


@dataclass
class Config:
    bot_token: str
    profile: str = field(default="default", compare=False)
    default_guild: int | None = field(default=None, compare=False)
    guilds: dict[str, int] = field(default_factory=dict, compare=False)
    source: str = field(default="env", compare=False)


def get_config_path() -> Path:
    """Return the user config file path (`$XDG_CONFIG_HOME/discord-cli/config.toml`)."""
    override = os.environ.get("DISCORD_CLI_CONFIG")
    if override and override.strip():
        return Path(override.strip()).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and xdg.strip():
        return Path(xdg.strip()).expanduser() / "discord-cli" / "config.toml"
    return Path.home() / ".config" / "discord-cli" / "config.toml"


def get_project_config_path(cwd: Path | None = None) -> Path:
    """Return the optional project-local `.discord-cli.toml` path."""
    base = cwd if cwd is not None else Path.cwd()
    return base / ".discord-cli.toml"


def validate_profile_name(name: str) -> str:
    cleaned = name.strip()
    if not _PROFILE_NAME_RE.match(cleaned):
        raise ConfigError(
            f"Invalid profile name {name!r}. Use letters, digits, '.', '_', or '-' (max 64 chars)."
        )
    return cleaned


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        raise ConfigError(f"Failed to parse TOML config at {path}: {exc}") from exc


def _format_toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{escaped}"'
    raise ConfigError(f"Unsupported TOML value type: {type(value).__name__}")


def _dump_toml(data: dict[str, Any]) -> str:
    """Serialize our flat/profiled config dictionary cleanly to TOML (zero extra deps)."""
    lines: list[str] = []
    # Top-level scalars first.
    for key in sorted(data.keys()):
        val = data[key]
        if not isinstance(val, dict) and val is not None:
            lines.append(f"{key} = {_format_toml_value(val)}")

    # Top-level [guilds] table.
    guilds = data.get("guilds")
    if isinstance(guilds, dict) and guilds:
        if lines:
            lines.append("")
        lines.append("[guilds]")
        for alias in sorted(guilds.keys()):
            lines.append(f"{alias} = {_format_toml_value(guilds[alias])}")

    # [profiles.<name>] tables.
    profiles = data.get("profiles")
    if isinstance(profiles, dict):
        for pname in sorted(profiles.keys()):
            pdata = profiles[pname]
            if not isinstance(pdata, dict):
                continue
            if lines:
                lines.append("")
            lines.append(f"[profiles.{pname}]")
            for k in sorted(pdata.keys()):
                v = pdata[k]
                if not isinstance(v, dict) and v is not None:
                    lines.append(f"{k} = {_format_toml_value(v)}")
            pguilds = pdata.get("guilds")
            if isinstance(pguilds, dict) and pguilds:
                lines.append("")
                lines.append(f"[profiles.{pname}.guilds]")
                for alias in sorted(pguilds.keys()):
                    lines.append(f"{alias} = {_format_toml_value(pguilds[alias])}")

    return "\n".join(lines) + ("\n" if lines else "")


def save_user_config(data: dict[str, Any], path: Path | None = None) -> Path:
    """Atomically write user config TOML with owner-only permissions (0600 on POSIX)."""
    target = path if path is not None else get_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    rendered = _dump_toml(data)
    fd, tmp_name = tempfile.mkstemp(dir=str(target.parent), prefix=".config-", suffix=".tmp")
    try:
        try:
            os.chmod(tmp_name, 0o600)
        except OSError:
            pass
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(rendered)
        os.replace(tmp_name, target)
    except Exception:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise
    return target


def load_merged_toml(*, cwd: Path | None = None) -> dict[str, Any]:
    """Load global user config merged with optional project-local `.discord-cli.toml`."""
    user_data = _read_toml(get_config_path())
    project_data = _read_toml(get_project_config_path(cwd))

    merged: dict[str, Any] = dict(user_data)
    # Never allow project-local config to inject raw tokens.
    for key, val in project_data.items():
        if key in {"bot_token", "token"}:
            continue
        if key == "guilds" and isinstance(val, dict):
            combined = dict(merged.get("guilds") or {})
            combined.update(val)
            merged["guilds"] = combined
        elif key == "profiles" and isinstance(val, dict):
            profiles = dict(merged.get("profiles") or {})
            for pname, pval in val.items():
                if not isinstance(pval, dict):
                    continue
                clean_pval = {k: v for k, v in pval.items() if k not in {"bot_token", "token"}}
                existing = dict(profiles.get(pname) or {})
                existing.update(clean_pval)
                profiles[pname] = existing
            merged["profiles"] = profiles
        else:
            merged[key] = val
    return merged


def active_profile_name(
    profile_override: str | None = None, data: dict[str, Any] | None = None
) -> str:
    """Determine the active profile name: `--profile` > `DISCORD_PROFILE` > config default > `'default'`."""
    if profile_override and profile_override.strip():
        return validate_profile_name(profile_override)
    env_profile = os.environ.get("DISCORD_PROFILE", "").strip()
    if env_profile:
        return validate_profile_name(env_profile)
    cfg = data if data is not None else load_merged_toml()
    configured = cfg.get("default_profile")
    if isinstance(configured, str) and configured.strip():
        return validate_profile_name(configured)
    return "default"


def _import_keyring() -> Any:
    try:
        import keyring

        return keyring
    except ImportError:
        return None


def keyring_available() -> bool:
    return _import_keyring() is not None


def get_keyring_token(profile: str) -> str | None:
    kr = _import_keyring()
    if kr is None:
        return None
    try:
        val = kr.get_password(KEYRING_SERVICE, profile)
        return val.strip() if isinstance(val, str) and val.strip() else None
    except Exception:
        return None


def set_keyring_token(profile: str, token: str) -> bool:
    kr = _import_keyring()
    if kr is None:
        return False
    try:
        kr.set_password(KEYRING_SERVICE, profile, token.strip())
        return True
    except Exception as exc:
        raise ConfigError(f"Failed to save token to OS keyring: {exc}") from exc


def delete_keyring_token(profile: str) -> bool:
    kr = _import_keyring()
    if kr is None:
        return False
    try:
        kr.delete_password(KEYRING_SERVICE, profile)
        return True
    except Exception:
        return False


def get_guild_aliases(profile: str | None = None, *, cwd: Path | None = None) -> dict[str, int]:
    """Return guild alias -> snowflake ID mapping for the active profile."""
    data = load_merged_toml(cwd=cwd)
    pname = active_profile_name(profile, data)
    aliases: dict[str, int] = {}
    top_guilds = data.get("guilds")
    if isinstance(top_guilds, dict):
        for k, v in top_guilds.items():
            if isinstance(v, int) or (isinstance(v, str) and v.isdigit()):
                aliases[str(k).lower()] = int(v)
    profiles = data.get("profiles")
    if isinstance(profiles, dict) and isinstance(profiles.get(pname), dict):
        pguilds = profiles[pname].get("guilds")
        if isinstance(pguilds, dict):
            for k, v in pguilds.items():
                if isinstance(v, int) or (isinstance(v, str) and v.isdigit()):
                    aliases[str(k).lower()] = int(v)
    return aliases


def resolve_guild_identifier(
    raw_guild: int | str | None,
    *,
    profile: str | None = None,
    cwd: Path | None = None,
) -> int | None:
    """Resolve `--guild` (int, digit string, or config alias) or profile default_guild."""
    if raw_guild is not None:
        if isinstance(raw_guild, int) and not isinstance(raw_guild, bool):
            return raw_guild
        text = str(raw_guild).strip()
        if text.isdigit():
            return int(text)
        aliases = get_guild_aliases(profile, cwd=cwd)
        if text.lower() in aliases:
            return aliases[text.lower()]
        raise ConfigError(
            f"Unknown guild alias {text!r}. Provide a numeric guild ID or define `[guilds].{text}` in config.toml.",
            recovery_hint="Run `discord-cli config set guilds.<alias> <guild_id>` or pass a numeric --guild ID.",
        )

    # Fallback to profile default_guild in config.toml if configured.
    data = load_merged_toml(cwd=cwd)
    pname = active_profile_name(profile, data)
    profiles = data.get("profiles")
    if isinstance(profiles, dict) and isinstance(profiles.get(pname), dict):
        dg = profiles[pname].get("default_guild")
        if isinstance(dg, int) or (isinstance(dg, str) and dg.isdigit()):
            return int(dg)
    top_dg = data.get("default_guild")
    if isinstance(top_dg, int) or (isinstance(top_dg, str) and top_dg.isdigit()):
        return int(top_dg)
    return None


def load_config(
    token_override: str | None = None,
    *,
    profile: str | None = None,
) -> Config:
    """Load configuration with precedence: --token > DISCORD_BOT_TOKEN > .env > OS keyring profile."""
    merged = load_merged_toml()
    pname = active_profile_name(profile, merged)
    aliases = get_guild_aliases(pname)
    default_guild = resolve_guild_identifier(None, profile=pname)

    if token_override:
        return Config(
            bot_token=token_override.strip(),
            profile=pname,
            default_guild=default_guild,
            guilds=aliases,
            source="flag",
        )

    # Check explicit environment first, then .env.
    env_token = os.environ.get("DISCORD_BOT_TOKEN")
    if env_token and env_token.strip():
        return Config(
            bot_token=env_token.strip(),
            profile=pname,
            default_guild=default_guild,
            guilds=aliases,
            source="env",
        )

    load_dotenv()

    env_token = os.environ.get("DISCORD_BOT_TOKEN")
    if env_token and env_token.strip():
        return Config(
            bot_token=env_token.strip(),
            profile=pname,
            default_guild=default_guild,
            guilds=aliases,
            source="dotenv",
        )

    # Check profile-specific env var if configured in config.toml (`token_env = "MY_TOKEN"`).
    profiles = merged.get("profiles")
    if isinstance(profiles, dict) and isinstance(profiles.get(pname), dict):
        token_env = profiles[pname].get("token_env")
        if isinstance(token_env, str) and token_env.strip():
            val = os.environ.get(token_env.strip())
            if val and val.strip():
                return Config(
                    bot_token=val.strip(),
                    profile=pname,
                    default_guild=default_guild,
                    guilds=aliases,
                    source=f"env:{token_env.strip()}",
                )

    # Optional OS keyring lookup for the active profile.
    kr_token = get_keyring_token(pname)
    if kr_token:
        return Config(
            bot_token=kr_token,
            profile=pname,
            default_guild=default_guild,
            guilds=aliases,
            source=f"keyring:{pname}",
        )

    raise ConfigError(
        "DISCORD_BOT_TOKEN not found in environment, .env, OS keyring, or --token",
        recovery_hint=(
            "Export DISCORD_BOT_TOKEN, pass --token, or install `discordcli-agents[keyring]` "
            "and run `discord-cli auth login`."
        ),
        suggested_command="discord-cli auth status",
    )
