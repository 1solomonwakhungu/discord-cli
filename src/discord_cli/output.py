"""Output formatting helpers (JSON by default, Rich tables for --human)."""

from __future__ import annotations

import json
from typing import Any


def make_payload(result: Any = None, error: dict[str, Any] | None = None) -> dict[str, Any]:
    if error:
        return {"ok": False, "error": error}
    return {"ok": True, "data": result}


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, default=str))


def print_human(payload: dict[str, Any]) -> None:
    try:
        from rich.console import Console
        from rich.table import Table
    except ImportError:
        print_json(payload)
        return

    console = Console()
    if not payload.get("ok"):
        console.print(f"[red]Error:[/red] {payload['error'].get('message')}")
        return

    data = payload.get("data")
    if isinstance(data, dict):
        list_key = next((key for key, value in data.items() if isinstance(value, list)), None)
        if list_key and data[list_key] and isinstance(data[list_key][0], dict):
            table = Table(title=list_key)
            rows = data[list_key]
            keys = list(rows[0].keys())[:8]
            for key in keys:
                table.add_column(str(key))
            for row in rows:
                table.add_row(
                    *[
                        json.dumps(row.get(key), default=str) if isinstance(row.get(key), (dict, list)) else str(row.get(key))
                        for key in keys
                    ]
                )
            console.print(table)
            return
    console.print_json(json.dumps(data, default=str))


def print_output(payload: dict[str, Any], human: bool) -> None:
    """Print `payload` as JSON, or as a human-readable Rich table/summary when `human` is set."""
    print_human(payload) if human else print_json(payload)
