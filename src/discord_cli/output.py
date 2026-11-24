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
    if isinstance(obj, list):
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


def project_fields(data: Any, fields: tuple[str, ...]) -> Any:
    """Project comma-separated dot-paths onto a dict or list of dicts inside `data`."""
    if not fields:
        return data
    if isinstance(data, list):
        return [_project_dict(item, fields) if isinstance(item, dict) else item for item in data]
    if isinstance(data, dict):
        # If dict wraps a primary list of dicts (e.g. {"guild_id": 1, "channels": [...]}),
        # project the list items while preserving scalar wrapper keys.
        list_key = next(
            (
                k
                for k, v in data.items()
                if isinstance(v, list) and all(isinstance(row, dict) for row in v)
            ),
            None,
        )
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


def _truncate_strings(obj: Any, max_str_len: int) -> Any:
    if isinstance(obj, str) and len(obj) > max_str_len:
        return obj[: max(0, max_str_len - 3)] + "..."
    if isinstance(obj, list):
        return [_truncate_strings(item, max_str_len) for item in obj]
    if isinstance(obj, dict):
        return {k: _truncate_strings(v, max_str_len) for k, v in obj.items()}
    return obj


def enforce_max_chars(
    payload: dict[str, Any], max_chars: int, *, compact: bool = False
) -> dict[str, Any]:
    """Ensure serialized JSON stays <= max_chars while ALWAYS remaining valid JSON."""
    if max_chars <= 0:
        return payload
    serialized = _serialize_json(payload, compact=compact)
    if len(serialized) <= max_chars:
        return payload

    # Deep copy via JSON round-trip so we never mutate caller's dicts.
    working: dict[str, Any] = json.loads(json.dumps(payload, default=str))
    meta: dict[str, Any] = dict(working.get("meta") or {})
    meta["truncated"] = True
    meta["max_chars"] = max_chars
    meta["truncation_hint"] = (
        f"Output exceeded --max-chars {max_chars}. Re-run with narrower --fields or smaller --limit."
    )

    data = working.get("data")
    omitted = 0

    # Strategy 1: Trim trailing items from the primary list in data.
    target_list: list[Any] | None = None
    if isinstance(data, list):
        target_list = data
    elif isinstance(data, dict):
        list_key = next((k for k, v in data.items() if isinstance(v, list)), None)
        if list_key is not None:
            target_list = data[list_key]

    if target_list is not None and len(target_list) > 0:
        # Binary search for the largest prefix that fits within max_chars.
        full_items = list(target_list)
        lo, hi = 0, len(full_items)
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
        target_list[:] = full_items[:best]
        omitted = len(full_items) - best
        meta["omitted_items"] = omitted
        working["meta"] = meta
        if len(_serialize_json(working, compact=compact)) <= max_chars:
            return working

    # Strategy 2: Progressively truncate long string values inside data.
    for str_cap in (200, 80, 32, 12):
        working["data"] = _truncate_strings(working.get("data"), str_cap)
        working["meta"] = meta
        if len(_serialize_json(working, compact=compact)) <= max_chars:
            return working

    # Strategy 3: Hard fallback keeping valid minimal envelope.
    minimal: dict[str, Any] = {
        "ok": working.get("ok", True),
        "data": None,
        "meta": {"truncated": True, "omitted_items": omitted, "max_chars": max_chars},
    }
    if not working.get("ok", True) and "error" in working:
        minimal = {
            "ok": False,
            "error": _truncate_strings(working["error"], 80),
            "meta": {"truncated": True},
        }
    return minimal


def shape_payload(payload: dict[str, Any], options: OutputOptions) -> dict[str, Any]:
    """Apply --fields, --string-ids, and --max-chars shaping to a payload."""
    shaped = dict(payload)
    meta = dict(shaped.get("meta") or {})

    if shaped.get("ok") and options.fields:
        shaped["data"] = project_fields(shaped.get("data"), options.fields)
        meta["fields"] = list(options.fields)

    if options.string_ids:
        shaped["data"] = stringify_ids(shaped.get("data"))

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


def _extract_table_rows(data: Any) -> tuple[list[dict[str, Any]] | None, str | None]:
    if isinstance(data, dict):
        list_key = next((key for key, value in data.items() if isinstance(value, list)), None)
        if list_key and data[list_key] and all(isinstance(row, dict) for row in data[list_key]):
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
        writer.writerow({k: _format_cell(row.get(k)) for k in fieldnames})
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
    table = table_cls(title=title)
    keys = list(rows[0].keys())
    if max_columns is not None:
        keys = keys[:max_columns]
    for key in keys:
        table.add_column(str(key))
    for row in rows:
        table.add_row(*[_format_cell(row.get(key)) for key in keys])
    return table


def print_human(payload: dict[str, Any], *, all_columns: bool = False) -> None:
    try:
        from rich.console import Console
        from rich.table import Table
    except ImportError:
        print_json(payload)
        return

    if not payload.get("ok"):
        Console(stderr=True).print(f"[red]Error:[/red] {payload['error'].get('message')}")
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
