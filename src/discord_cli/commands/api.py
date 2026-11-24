"""Raw Discord REST API v10 escape hatch (`discord-cli api request`)."""

from __future__ import annotations

import urllib.parse
from typing import Any

import click
import discord

from discord_cli.errors import CliError
from discord_cli.message_builder import parse_json_payload
from discord_cli.registry import invoke, registry

_ALLOWED_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")


@registry.group("api")
def api_group() -> None:
    """Call any Discord REST API v10 endpoint directly with auth and rate-limit handling."""


@api_group.command("request")
@click.argument("method", type=click.Choice(_ALLOWED_METHODS, case_sensitive=False))
@click.argument("endpoint")
@click.option(
    "--json-body",
    default=None,
    help="JSON request body string or @path/to/body.json.",
)
@click.option(
    "--query",
    "query_params",
    multiple=True,
    help="Repeatable query parameter in key=value form.",
)
@click.option("--reason", default=None, help="Audit log reason header (X-Audit-Log-Reason).")
@click.pass_context
def api_request(
    ctx: click.Context,
    method: str,
    endpoint: str,
    json_body: str | None,
    query_params: tuple[str, ...],
    reason: str | None,
) -> None:
    """Execute a raw authenticated Discord REST API v10 request."""
    invoke(
        ctx,
        action_api_request,
        method=method.upper(),
        endpoint=endpoint,
        json_body=json_body,
        query_params=list(query_params),
        reason=reason,
    )


def _validate_endpoint(endpoint: str) -> str:
    if any(ord(ch) <= 0x20 or ord(ch) == 0x7F for ch in endpoint):
        raise CliError("Endpoint contains forbidden whitespace or control characters.")
    if not endpoint.startswith("/") or endpoint.startswith("//"):
        raise CliError(
            f"Invalid Discord API endpoint {endpoint!r}. Must be a relative path starting with '/'."
        )
    split = urllib.parse.urlsplit(endpoint)
    if split.scheme or split.netloc or "://" in split.path or "\\" in split.path:
        raise CliError(
            f"Invalid Discord API endpoint {endpoint!r}. Must be a relative path starting with '/'."
        )
    # Reject path traversal segments in both raw and percent-decoded forms.
    for candidate in (
        split.path,
        urllib.parse.unquote(split.path),
        urllib.parse.unquote(urllib.parse.unquote(split.path)),
    ):
        if "\\" in candidate:
            raise CliError(f"Invalid Discord API endpoint {endpoint!r}: backslashes not allowed.")
        segments = candidate.split("/")
        if ".." in segments or "." in segments:
            raise CliError(
                f"Invalid Discord API endpoint {endpoint!r}: path traversal segments are forbidden."
            )
    return endpoint


def _parse_query_params(pairs: list[str]) -> dict[str, str]:
    params: dict[str, str] = {}
    for item in pairs:
        if "=" not in item:
            raise CliError(f"Invalid --query parameter {item!r}. Expected key=value.")
        key, value = item.split("=", 1)
        params[key.strip()] = value
    return params


async def action_api_request(
    client: discord.Client,
    guild_id: int | None,
    method: str,
    endpoint: str,
    json_body: str | None = None,
    query_params: list[str] | None = None,
    reason: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    path = _validate_endpoint(endpoint)
    upper_method = method.upper()
    if upper_method not in _ALLOWED_METHODS:
        raise CliError(f"Unsupported HTTP method: {method}")

    route = discord.http.Route(upper_method, path)
    request_kwargs: dict[str, Any] = {}
    if json_body is not None:
        request_kwargs["json"] = parse_json_payload(json_body)
    if query_params:
        request_kwargs["params"] = _parse_query_params(query_params)
    if reason is not None:
        request_kwargs["reason"] = reason

    response = await client.http.request(route, **request_kwargs)
    return {"method": upper_method, "endpoint": path, "response": response}
