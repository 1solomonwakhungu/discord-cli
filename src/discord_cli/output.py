"""Output formatting helpers (JSON by default, Rich tables for --human)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rich.table import Table

_MAX_TABLE_COLUMNS = 8


def make_payload(result: Any = None, error: dict[str, Any] | None = None) -> dict[str, Any]:
    if error:
        return {"ok": False, "error": error}
    return {"ok": True, "data": result}


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, default=str))


def _format_cell(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    return str(value)


def _extract_table_rows(data: Any) -> tuple[list[dict[str, Any]] | None, str | None]:
    if isinstance(data, dict):
        list_key = next((key for key, value in data.items() if isinstance(value, list)), None)
        if list_key and data[list_key] and all(isinstance(row, dict) for row in data[list_key]):
            return data[list_key], str(list_key)
    elif isinstance(data, list) and data and all(isinstance(row, dict) for row in data):
        return data, None
    return None, None


def _build_table(
    table_cls: type[Table],
    rows: list[dict[str, Any]],
    title: str | None = None,
) -> Table:
    table = table_cls(title=title)
    keys = list(rows[0].keys())[:_MAX_TABLE_COLUMNS]
    for key in keys:
        table.add_column(str(key))
    for row in rows:
        table.add_row(*[_format_cell(row.get(key)) for key in keys])
    return table


def print_human(payload: dict[str, Any]) -> None:
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
        console.print(_build_table(Table, rows, title=title))
        return
    console.print_json(json.dumps(data, default=str))


def print_output(payload: dict[str, Any], human: bool) -> None:
    """Print `payload` as JSON, or as a human-readable Rich table/summary when `human` is set."""
    print_human(payload) if human else print_json(payload)
