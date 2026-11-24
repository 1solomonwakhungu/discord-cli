"""Output formatting & agent context-window shaping helpers.

Supports JSON (default), compact JSON, NDJSON (jsonl), CSV, Markdown tables,
Rich tables (--human / --format table), unwrapped raw output, quiet ID mode,
dot-path field projection (--fields), 64-bit string IDs (--string-ids),
token-aware valid-JSON truncation (--max-chars), and atomic file output (-o).
"""

from __future__ import annotations

import csv
import io
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rich.table import Table

_MAX_TABLE_COLUMNS = 8
_JS_MAX_SAFE_INTEGER = (1 << 53) - 1
MIN_MAX_CHARS = 256
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


@dataclass(frozen=True)
class OutputOptions:
    """Formatting and shaping options applied when rendering a CLI payload."""

    human: bool = False
    output_format: str | None = None
    compact: bool = False
    fields: tuple[str, ...] = ()
    max_chars: int | None = None
    string_ids: bool = False
    quiet: bool = False
    output_path: str | None = None
    untrusted_envelope: bool = False
    redact_pii: bool = False

    @property
    def effective_format(self) -> str:
        if self.output_format:
            return self.output_format.lower()
        return "table" if self.human else "json"


def parse_fields(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def make_payload(
    result: Any = None,
    error: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if error:
        payload: dict[str, Any] = {"ok": False, "error": error}
    else:
        payload = {"ok": True, "data": result}
    if meta:
        payload["meta"] = meta
    return payload


def _is_id_key(key: str) -> bool:
    return key == "id" or key.endswith("_id") or key.endswith("_ids")


def stringify_ids(obj: Any, *, key_hint: str | None = None) -> Any:
    """Convert Discord snowflake IDs (or ints > JS MAX_SAFE_INTEGER) to strings recursively."""
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, int):
        if (key_hint is not None and _is_id_key(key_hint)) or abs(obj) > _JS_MAX_SAFE_INTEGER:
            return str(obj)
        return obj
    if isinstance(obj, (list, tuple)):
        return [stringify_ids(item, key_hint=key_hint) for item in obj]
    if isinstance(obj, dict):
        return {k: stringify_ids(v, key_hint=str(k)) for k, v in obj.items()}
    return obj


def _extract_dot_path(row: dict[str, Any], path: str) -> tuple[bool, Any]:
    current: Any = row
    for segment in path.split("."):
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        else:
            return False, None
    return True, current


def _project_dict(row: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    projected: dict[str, Any] = {}
    for path in fields:
        found, value = _extract_dot_path(row, path)
        if not found:
            continue
        parts = path.split(".")
        cursor = projected
        for part in parts[:-1]:
            if part not in cursor or not isinstance(cursor[part], dict):
                cursor[part] = {}
            cursor = cursor[part]
        cursor[parts[-1]] = value
    return projected


def _find_primary_list_key(data: dict[str, Any], *, require_dicts: bool = False) -> str | None:
    """Pick the largest non-empty list key in `data` (falling back to any matching list)."""
    candidates: list[tuple[int, str]] = []
    for key, value in data.items():
        if not isinstance(value, list):
            continue
        if require_dicts and not all(isinstance(row, dict) for row in value):
            continue
        candidates.append((len(value), key))
    if not candidates:
        return None
    # Prefer non-empty lists, choosing the largest one.
    non_empty = [c for c in candidates if c[0] > 0]
    if non_empty:
        return max(non_empty, key=lambda item: item[0])[1]
    return candidates[0][1]


def project_fields(data: Any, fields: tuple[str, ...]) -> Any:
    """Project comma-separated dot-paths onto a dict or list of dicts inside `data`."""
    if not fields:
        return data
    if isinstance(data, list):
        return [_project_dict(item, fields) if isinstance(item, dict) else item for item in data]
    if isinstance(data, dict):
        list_key = _find_primary_list_key(data, require_dicts=True)
        if list_key is not None and not any(f in data for f in fields):
            copied = dict(data)
            copied[list_key] = [_project_dict(row, fields) for row in data[list_key]]
            return copied
        return _project_dict(data, fields)
    return data


def _serialize_json(payload: dict[str, Any], *, compact: bool = False) -> str:
    if compact:
        return json.dumps(payload, separators=(",", ":"), default=str)
    return json.dumps(payload, indent=2, default=str)


def _truncate_strings(obj: Any, max_str_len: int, *, envelope_tag: str | None = None) -> Any:
    if isinstance(obj, str):
        if envelope_tag:
            prefix = f"<{envelope_tag}>"
            suffix = f"</{envelope_tag}>"
            if obj.startswith(prefix) and obj.endswith(suffix):
                inner = obj[len(prefix) : -len(suffix)]
                if len(inner) > max_str_len:
                    inner = inner[: max(0, max_str_len - 3)] + "..."
                return f"{prefix}{inner}{suffix}"
        if len(obj) > max_str_len:
            return obj[: max(0, max_str_len - 3)] + "..."
        return obj
    if isinstance(obj, list):
        return [_truncate_strings(item, max_str_len, envelope_tag=envelope_tag) for item in obj]
    if isinstance(obj, dict):
        return {
            k: _truncate_strings(v, max_str_len, envelope_tag=envelope_tag) for k, v in obj.items()
        }
    return obj


def enforce_max_chars(
    payload: dict[str, Any], max_chars: int, *, compact: bool = False
) -> dict[str, Any]:
    """Ensure serialized JSON stays <= max_chars (for max_chars >= 256) while remaining valid JSON.

    When an untrusted envelope (`payload["security"]`) is present, preserves BOTH the
    `security` block and every `<tag>...</tag>` boundary intact.
    """
    if max_chars <= 0:
        return payload
    serialized = _serialize_json(payload, compact=compact)
    if len(serialized) <= max_chars:
        return payload

    working: dict[str, Any] = json.loads(json.dumps(payload, default=str))
    security_block: dict[str, Any] | None = (
        working.get("security") if isinstance(working.get("security"), dict) else None
    )
    envelope_tag: str | None = (
        str(security_block["boundary_tag"])
        if security_block and isinstance(security_block.get("boundary_tag"), str)
        else None
    )
    compact_security: dict[str, Any] | None = (
        {
            "provenance": security_block.get("provenance", "untrusted_discord_user_content"),
            "boundary_tag": envelope_tag,
            "boundary_nonce": security_block.get("boundary_nonce", ""),
        }
        if security_block and envelope_tag
        else None
    )

    meta: dict[str, Any] = dict(working.get("meta") or {})
    meta["truncated"] = True
    meta["max_chars"] = max_chars
    meta["truncation_hint"] = (
        f"Output exceeded --max-chars {max_chars}. Re-run with narrower --fields or smaller --limit."
    )

    def _with_security(candidate: dict[str, Any], *, short_sec: bool = False) -> dict[str, Any]:
        if security_block is not None:
            candidate["security"] = compact_security if short_sec else security_block
        return candidate

    if not working.get("ok", True):
        err = working.get("error")
        err_type = err.get("type", "Error") if isinstance(err, dict) else "Error"
        err_msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        for short_sec in (False, True):
            for cap in (200, 80, 40, 20, 8):
                candidate_err: dict[str, Any] = {
                    "type": str(err_type)[:40],
                    "message": _truncate_strings(str(err_msg), cap, envelope_tag=envelope_tag),
                }
                candidate = _with_security(
                    {"ok": False, "error": candidate_err, "meta": {"truncated": True}},
                    short_sec=short_sec,
                )
                if len(_serialize_json(candidate, compact=compact)) <= max_chars:
                    return candidate
        return _with_security(
            {
                "ok": False,
                "error": {
                    "type": "Error",
                    "message": f"<{envelope_tag}>...</{envelope_tag}>" if envelope_tag else "...",
                },
                "meta": {"truncated": True},
            },
            short_sec=True,
        )

    data = working.get("data")
    omitted = 0

    # Strategy 1: Trim trailing items from the largest non-empty list in data.
    target_list: list[Any] | None = None
    if isinstance(data, list) and data:
        target_list = data
    elif isinstance(data, dict):
        list_key = _find_primary_list_key(data)
        if list_key is not None and data[list_key]:
            target_list = data[list_key]

    if target_list is not None and len(target_list) > 0:
        full_items = list(target_list)
        lo, hi = 1, len(full_items)
        best = 0
        while lo <= hi:
            mid = (lo + hi) // 2
            target_list[:] = full_items[:mid]
            meta["omitted_items"] = len(full_items) - mid
            working["meta"] = meta
            if len(_serialize_json(working, compact=compact)) <= max_chars:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        if best > 0:
            target_list[:] = full_items[:best]
            meta["omitted_items"] = len(full_items) - best
            working["meta"] = meta
            return working
        # Even 1 full item didn't fit — try keeping the first item with truncated inner strings!
        for str_cap in (400, 200, 80, 32):
            target_list[:] = [_truncate_strings(full_items[0], str_cap, envelope_tag=envelope_tag)]
            omitted = len(full_items) - 1
            meta["omitted_items"] = omitted
            working["meta"] = meta
            if len(_serialize_json(working, compact=compact)) <= max_chars:
                return working
        target_list[:] = []
        omitted = len(full_items)
        meta["omitted_items"] = omitted
        working["meta"] = meta
        if len(_serialize_json(working, compact=compact)) <= max_chars:
            return working

    # Strategy 2: Progressively truncate long inner string values inside data (never breaking tags).
    for short_sec in (False, True):
        if security_block is not None:
            working["security"] = compact_security if short_sec else security_block
        for str_cap in (200, 80, 32, 12):
            working["data"] = _truncate_strings(
                working.get("data"), str_cap, envelope_tag=envelope_tag
            )
            working["meta"] = meta
            if len(_serialize_json(working, compact=compact)) <= max_chars:
                return working

    # Strategy 3: Minimal valid JSON envelope (preserving security metadata when active).
    for short_sec in (False, True):
        minimal = _with_security(
            {
                "ok": True,
                "data": None,
                "meta": {"truncated": True, "omitted_items": omitted, "max_chars": max_chars},
            },
            short_sec=short_sec,
        )
        if len(_serialize_json(minimal, compact=compact)) <= max_chars:
            return minimal
    return _with_security(
        {"ok": True, "data": None, "meta": {"truncated": True}},
        short_sec=True,
    )


def shape_payload(payload: dict[str, Any], options: OutputOptions) -> dict[str, Any]:
    """Apply --fields, --string-ids, --redact-pii, --untrusted-envelope, and --max-chars shaping."""
    shaped = dict(payload)
    meta = dict(shaped.get("meta") or {})

    if shaped.get("ok") and options.fields:
        shaped["data"] = project_fields(shaped.get("data"), options.fields)
        meta["fields"] = list(options.fields)

    if options.string_ids:
        shaped["data"] = stringify_ids(shaped.get("data"))

    if options.redact_pii:
        from discord_cli.policy import redact_pii

        if shaped.get("ok") and "data" in shaped:
            shaped["data"] = redact_pii(shaped["data"])
        elif "error" in shaped:
            shaped["error"] = redact_pii(shaped["error"])
        meta["pii_redacted"] = True

    if options.untrusted_envelope:
        from discord_cli.policy import apply_untrusted_envelope

        shaped = apply_untrusted_envelope(shaped)

    if meta:
        shaped["meta"] = meta

    if options.max_chars is not None and options.effective_format in {"json", "raw"}:
        shaped = enforce_max_chars(shaped, options.max_chars, compact=options.compact)

    return shaped


def print_json(payload: dict[str, Any], *, compact: bool = False) -> None:
    print(_serialize_json(payload, compact=compact))


def _format_cell(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    if value is None:
        return ""
    return str(value)


def sanitize_csv_cell(value: Any) -> str:
    """Neutralize spreadsheet formula injection (=, +, -, @, tab, CR) in CSV cells."""
    text = _format_cell(value)
    if text and text[0] in _CSV_FORMULA_PREFIXES:
        return "'" + text
    return text


def _extract_table_rows(data: Any) -> tuple[list[dict[str, Any]] | None, str | None]:
    if isinstance(data, dict):
        list_key = _find_primary_list_key(data, require_dicts=True)
        if list_key and data[list_key]:
            return data[list_key], str(list_key)
    elif isinstance(data, list) and data and all(isinstance(row, dict) for row in data):
        return data, None
    return None, None


def _extract_ids(data: Any) -> list[str]:
    rows, _ = _extract_table_rows(data)
    if rows is not None:
        ids = [str(row["id"]) for row in rows if "id" in row]
        if ids:
            return ids
        codes = [str(row["code"]) for row in rows if "code" in row]
        if codes:
            return codes
    if isinstance(data, dict):
        if "id" in data:
            return [str(data["id"])]
        for key in (
            "created",
            "updated",
            "deleted",
            "sent",
            "pinned",
            "unpinned",
            "banned",
            "kicked",
        ):
            nested = data.get(key)
            if isinstance(nested, dict) and "id" in nested:
                return [str(nested["id"])]
    return []


def _format_csv(data: Any) -> str:
    rows, _ = _extract_table_rows(data)
    if rows is None:
        if isinstance(data, dict):
            rows = [data]
        else:
            return ""
    if not rows:
        return ""
    fieldnames = list(rows[0].keys())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: sanitize_csv_cell(row.get(k)) for k in fieldnames})
    return buf.getvalue()


def _format_markdown(data: Any) -> str:
    rows, _ = _extract_table_rows(data)
    if rows is None:
        if isinstance(data, dict):
            rows = [data]
        else:
            return f"```json\n{json.dumps(data, indent=2, default=str)}\n```"
    if not rows:
        return "_No results._"
    keys = list(rows[0].keys())
    header = "| " + " | ".join(str(k) for k in keys) + " |"
    sep = "| " + " | ".join("---" for _ in keys) + " |"
    body = [
        "| "
        + " | ".join(_format_cell(row.get(k)).replace("|", "\\|").replace("\n", " ") for k in keys)
        + " |"
        for row in rows
    ]
    return "\n".join([header, sep, *body])


def _format_jsonl(data: Any) -> str:
    rows, _ = _extract_table_rows(data)
    items = rows if rows is not None else (data if isinstance(data, list) else [data])
    return "\n".join(json.dumps(item, separators=(",", ":"), default=str) for item in items)


def _write_atomic(path_str: str, content: str) -> None:
    target = Path(path_str)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(target.parent), prefix=".discord-cli-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            if content and not content.endswith("\n"):
                handle.write("\n")
        os.replace(tmp_name, target)
    except Exception:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


def _build_table(
    table_cls: type[Table],
    rows: list[dict[str, Any]],
    title: str | None = None,
    *,
    max_columns: int | None = _MAX_TABLE_COLUMNS,
) -> Table:
    from rich.text import Text

    table = table_cls(title=Text(title) if title is not None else None)
    keys = list(rows[0].keys())
    if max_columns is not None:
        keys = keys[:max_columns]
    for key in keys:
        table.add_column(Text(str(key)))
    for row in rows:
        table.add_row(*[Text(_format_cell(row.get(key))) for key in keys])
    return table


def print_human(payload: dict[str, Any], *, all_columns: bool = False) -> None:
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.text import Text
    except ImportError:
        print_json(payload)
        return

    if not payload.get("ok"):
        err_msg = str((payload.get("error") or {}).get("message", ""))
        text = Text("Error: ", style="red")
        text.append(err_msg)
        Console(stderr=True).print(text)
        return

    console = Console()
    data = payload.get("data")
    rows, title = _extract_table_rows(data)
    if rows is not None:
        max_cols = None if all_columns else _MAX_TABLE_COLUMNS
        console.print(_build_table(Table, rows, title=title, max_columns=max_cols))
        return
    console.print_json(json.dumps(data, default=str))


def print_output(
    payload: dict[str, Any],
    human: bool = False,
    *,
    options: OutputOptions | None = None,
) -> None:
    """Render `payload` according to OutputOptions (backward-compatible with `human` bool)."""
    opts = options if options is not None else OutputOptions(human=human)
    shaped = shape_payload(payload, opts)
    fmt = opts.effective_format

    if opts.quiet:
        if not shaped.get("ok"):
            print_human(shaped)
            return
        text = "\n".join(_extract_ids(shaped.get("data")))
        if opts.output_path:
            _write_atomic(opts.output_path, text)
        elif text:
            print(text)
        return

    if fmt == "table":
        if opts.output_path:
            rendered = (
                _format_markdown(shaped.get("data"))
                if shaped.get("ok")
                else _serialize_json(shaped)
            )
            _write_atomic(opts.output_path, rendered)
        else:
            print_human(shaped, all_columns=bool(opts.fields))
        return

    if fmt == "json":
        text = _serialize_json(shaped, compact=opts.compact)
    elif fmt == "raw":
        target = shaped.get("data") if shaped.get("ok") else shaped
        text = (
            _serialize_json(target, compact=opts.compact)
            if isinstance(target, dict)
            else json.dumps(target, default=str)
        )
    elif fmt == "jsonl":
        if not shaped.get("ok"):
            text = _serialize_json(shaped, compact=True)
        else:
            text = _format_jsonl(shaped.get("data"))
    elif fmt == "csv":
        if not shaped.get("ok"):
            text = _serialize_json(shaped, compact=opts.compact)
        else:
            text = _format_csv(shaped.get("data"))
    elif fmt == "markdown":
        if not shaped.get("ok"):
            text = _serialize_json(shaped, compact=opts.compact)
        else:
            text = _format_markdown(shaped.get("data"))
    else:
        text = _serialize_json(shaped, compact=opts.compact)

    if opts.output_path:
        _write_atomic(opts.output_path, text)
    else:
        print(text, end="" if fmt == "csv" and text.endswith("\n") else "\n")
