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
from discord_cli.policy import is_ascii_snowflake

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.9/3.10 path
    import tomli as tomllib  # type: ignore[no-redef]

KEYRING_SERVICE = "discord-cli"
_PROFILE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_TOML_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_PROJECT_FORBIDDEN_KEYS = frozenset({"bot_token", "token", "token_env", "default_profile"})
_DISPLAY_SECRET_KEYS = frozenset({"bot_token", "token"})


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


def validate_toml_key_segment(segment: str) -> str:
    """Validate a single TOML bare-key segment (prevents TOML injection and invalid syntax)."""
    if not _TOML_KEY_RE.match(segment):
        raise ConfigError(
            f"Invalid configuration key segment {segment!r}. "
            "Use only ASCII letters, digits, '_' or '-' (1-64 chars)."
        )
    return segment


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        raise ConfigError(f"Failed to parse TOML config at {path}: {exc}") from exc


def load_user_toml(path: Path | None = None) -> dict[str, Any]:
    """Read ONLY the user-scoped config.toml (never merges project-local .discord-cli.toml)."""
    return _read_toml(path if path is not None else get_config_path())


def _escape_toml_string(value: str) -> str:
    out: list[str] = ['"']
    for ch in value:
        code = ord(ch)
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\b":
            out.append("\\b")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\f":
            out.append("\\f")
        elif ch == "\r":
            out.append("\\r")
        elif code < 0x20 or code == 0x7F:
            out.append(f"\\u{code:04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _format_toml_key(key: str) -> str:
    if _TOML_KEY_RE.match(key):
        return key
    return _escape_toml_string(key)


def _format_toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return _escape_toml_string(value)
    if isinstance(value, list):
        return "[" + ", ".join(_format_toml_value(item) for item in value) + "]"
    raise ConfigError(f"Unsupported TOML value type: {type(value).__name__}")


def _dump_toml_table(data: dict[str, Any], prefix: tuple[str, ...], lines: list[str]) -> None:
    scalars = [(k, v) for k, v in sorted(data.items()) if not isinstance(v, dict) and v is not None]
    tables = [(k, v) for k, v in sorted(data.items()) if isinstance(v, dict)]

    if prefix and (scalars or not tables):
        if lines:
            lines.append("")
        header = ".".join(_format_toml_key(seg) for seg in prefix)
        lines.append(f"[{header}]")

    for k, v in scalars:
        lines.append(f"{_format_toml_key(str(k))} = {_format_toml_value(v)}")

    for k, sub in tables:
        _dump_toml_table(sub, (*prefix, str(k)), lines)


def _dump_toml(data: dict[str, Any]) -> str:
    """Losslessly serialize a nested config dict to valid TOML and verify round-trip."""
    lines: list[str] = []
    _dump_toml_table(data, (), lines)
    rendered = "\n".join(lines) + ("\n" if lines else "")
    # Verify round-trip parse before ever touching disk.
    try:
        tomllib.loads(rendered)
    except Exception as exc:
        raise ConfigError(f"Refusing to write invalid TOML config: {exc}") from exc
    return rendered


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


def sanitize_config_for_display(data: dict[str, Any]) -> dict[str, Any]:
    """Strip any secret token keys before displaying configuration."""
    clean: dict[str, Any] = {}
    for k, v in data.items():
        if str(k).lower() in _DISPLAY_SECRET_KEYS:
            continue
        if isinstance(v, dict):
            clean[k] = sanitize_config_for_display(v)
        else:
            clean[k] = v
    return clean


def load_merged_toml(*, cwd: Path | None = None) -> dict[str, Any]:
    """Load global user config merged with optional project-local `.discord-cli.toml`.

    Security boundary: project-local `.discord-cli.toml` can NEVER inject `bot_token`,
    `token`, `token_env`, or `default_profile`.
    """
    user_data = load_user_toml()
    project_data = _read_toml(get_project_config_path(cwd))

    merged: dict[str, Any] = dict(user_data)
    for key, val in project_data.items():
        if key in _PROJECT_FORBIDDEN_KEYS:
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
                clean_pval = {k: v for k, v in pval.items() if k not in _PROJECT_FORBIDDEN_KEYS}
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


def _coerce_snowflake(val: Any) -> int | None:
    if isinstance(val, bool):
        return None
    if isinstance(val, int) and val > 0:
        return val if is_ascii_snowflake(str(val)) else None
    if isinstance(val, str) and is_ascii_snowflake(val.strip()):
        return int(val.strip())
    return None


def get_guild_aliases(profile: str | None = None, *, cwd: Path | None = None) -> dict[str, int]:
    """Return guild alias -> snowflake ID mapping for the active profile."""
    data = load_merged_toml(cwd=cwd)
    pname = active_profile_name(profile, data)
    aliases: dict[str, int] = {}
    top_guilds = data.get("guilds")
    if isinstance(top_guilds, dict):
        for k, v in top_guilds.items():
            gid = _coerce_snowflake(v)
            if gid is not None:
                aliases[str(k).lower()] = gid
    profiles = data.get("profiles")
    if isinstance(profiles, dict) and isinstance(profiles.get(pname), dict):
        pguilds = profiles[pname].get("guilds")
        if isinstance(pguilds, dict):
            for k, v in pguilds.items():
                gid = _coerce_snowflake(v)
                if gid is not None:
                    aliases[str(k).lower()] = gid
    return aliases


def resolve_guild_identifier(
    raw_guild: int | str | None,
    *,
    profile: str | None = None,
    cwd: Path | None = None,
) -> int | None:
    """Resolve `--guild` (ASCII snowflake or config alias) or profile default_guild."""
    if raw_guild is not None:
        direct = _coerce_snowflake(raw_guild)
        if direct is not None:
            return direct
        text = str(raw_guild).strip()
        aliases = get_guild_aliases(profile, cwd=cwd)
        if text.lower() in aliases:
            return aliases[text.lower()]
        raise ConfigError(
            f"Unknown guild alias or invalid guild ID {text!r}. "
            f"Provide a numeric ASCII guild ID or define `[guilds].{text}` in config.toml.",
            recovery_hint="Run `discord-cli config set guilds.<alias> <guild_id>` or pass a numeric --guild ID.",
        )

    data = load_merged_toml(cwd=cwd)
    pname = active_profile_name(profile, data)
    profiles = data.get("profiles")
    if isinstance(profiles, dict) and isinstance(profiles.get(pname), dict):
        dg = _coerce_snowflake(profiles[pname].get("default_guild"))
        if dg is not None:
            return dg
    return _coerce_snowflake(data.get("default_guild"))


def detect_token_source(
    token_override: str | None = None,
    *,
    profile: str | None = None,
) -> tuple[str | None, str]:
    """Return `(token_or_none, source_label)` across flag, env, .env, token_env, and keyring."""
    if token_override and token_override.strip():
        return token_override.strip(), "flag"

    env_token = os.environ.get("DISCORD_BOT_TOKEN")
    if env_token and env_token.strip():
        return env_token.strip(), "env"

    load_dotenv()

    env_token = os.environ.get("DISCORD_BOT_TOKEN")
    if env_token and env_token.strip():
        return env_token.strip(), "dotenv"

    user_data = load_user_toml()
    pname = active_profile_name(profile, user_data)
    profiles = user_data.get("profiles")
    if isinstance(profiles, dict) and isinstance(profiles.get(pname), dict):
        token_env = profiles[pname].get("token_env")
        if isinstance(token_env, str) and token_env.strip():
            val = os.environ.get(token_env.strip())
            if val and val.strip():
                return val.strip(), f"env:{token_env.strip()}"

    kr_token = get_keyring_token(pname)
    if kr_token:
        return kr_token, f"keyring:{pname}"

    return None, "none"


def load_config(
    token_override: str | None = None,
    *,
    profile: str | None = None,
) -> Config:
    """Load configuration with precedence: --token > DISCORD_BOT_TOKEN > .env > token_env > OS keyring."""
    merged = load_merged_toml()
    pname = active_profile_name(profile, merged)
    aliases = get_guild_aliases(pname)
    default_guild = resolve_guild_identifier(None, profile=pname)

    token, source = detect_token_source(token_override, profile=pname)
    if token:
        return Config(
            bot_token=token,
            profile=pname,
            default_guild=default_guild,
            guilds=aliases,
            source=source,
        )

    raise ConfigError(
        "DISCORD_BOT_TOKEN not found in environment, .env, OS keyring, or --token",
        recovery_hint=(
            "Export DISCORD_BOT_TOKEN, pass --token, or install `discordcli-agents[keyring]` "
            "and run `discord-cli auth login`."
        ),
        suggested_command="discord-cli auth status",
    )
