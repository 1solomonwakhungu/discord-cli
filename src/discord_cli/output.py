"""Output formatting helpers (JSON and human-readable)."""

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
    except ImportError:
        print_json(payload)
        return

    console = Console()
    if not payload.get("ok"):
        console.print(f"[red]Error:[/red] {payload['error'].get('message')}")
        return
    console.print_json(json.dumps(payload.get("data"), default=str))
