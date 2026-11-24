# syntax=docker/dockerfile:1.7
# Multi-stage Distroless OCI image for discord-cli (discordcli-agents).

FROM ghcr.io/astral-sh/uv:0.6.14 AS uv

FROM debian:bookworm-slim AS builder
COPY --from=uv /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_INSTALL_DIR=/python \
    UV_PYTHON_PREFERENCE=only-managed

RUN uv python install 3.12

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY docs/man/discord-cli.1 ./docs/man/discord-cli.1
COPY src ./src

RUN uv venv /app/.venv --python 3.12 && \
    uv pip install --python /app/.venv/bin/python --no-cache .

FROM gcr.io/distroless/cc-debian12:nonroot

COPY --from=builder --chown=nonroot:nonroot /python /python
COPY --from=builder --chown=nonroot:nonroot /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:/usr/local/bin:/usr/bin:/bin" \
    PYTHONUNBUFFERED=1 \
    DISCORD_CLI_NO_PLUGINS=1

LABEL org.opencontainers.image.source="https://github.com/1solomonwakhungu/discord-cli" \
      org.opencontainers.image.description="JSON-first Discord management CLI for AI agents and DevOps" \
      org.opencontainers.image.licenses="MIT"

ENTRYPOINT ["/app/.venv/bin/discord-cli"]
CMD ["--help"]
