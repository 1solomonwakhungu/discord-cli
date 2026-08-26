"""Render a roff man page from the live Click command tree.

The man page is generated rather than hand-written so it can never drift from
the actual CLI: every command, argument, and option below is read off the same
Click objects that parse a real invocation. ``tests/test_manpage.py`` fails if
the committed ``docs/man/discord-cli.1`` no longer matches this renderer.
"""

from __future__ import annotations

import textwrap

import click

MANUAL_SECTION = "1"

#: roff refills adjacent text lines, so wrapping prose is purely cosmetic. It
#: keeps the committed page under mandoc's 80-byte style limit and makes diffs
#: between regenerations readable.
WRAP_WIDTH = 76
MANUAL_NAME = "discord-cli Manual"
SOURCE_NAME = "discord-cli"

# The generated page is committed to the repository, so the .TH date must be a
# stable value rather than "today" or every regeneration would report drift.
MANPAGE_DATE = "2026-08-26"

SHORT_DESCRIPTION = "manage Discord servers and automate Discord from the command line"

DESCRIPTION_PARAGRAPHS = [
    "discord-cli is a headless, scriptable command-line interface for Discord. "
    "It authenticates with a Discord bot token, connects to the Discord gateway, "
    "runs exactly one command, prints the result, and exits. There is no "
    "long-running daemon and no interactive prompt.",
    "Output is JSON by default so that results can be piped into jq, captured in "
    "CI logs, or consumed by an AI agent without additional parsing glue. Pass "
    "\\fB--human\\fR to render Rich-formatted tables for interactive use instead.",
    "Every command returns a payload with an \\fBok\\fR boolean. On success the "
    "payload carries a \\fBresult\\fR object; on failure it carries an \\fBerror\\fR "
    "object with a \\fBtype\\fR and \\fBmessage\\fR, and the process exits non-zero.",
]

ENVIRONMENT_VARIABLES = [
    (
        "DISCORD_BOT_TOKEN",
        "Discord bot token used to authenticate. Read from the process "
        "environment or from a .env file in the current directory. The "
        "\\fB--token\\fR option takes precedence over both.",
    ),
    (
        "DISCORD_GUILD_ID",
        "Default guild ID to operate on. The \\fB--guild\\fR option takes "
        "precedence. Required when the bot is a member of more than one guild.",
    ),
]

EXIT_STATUS = [
    ("0", "The command completed successfully and the payload reports ok: true."),
    (
        "1",
        "The command failed. Causes include a missing or invalid bot token, a "
        "missing guild, channel, role, or member, and any error returned by the "
        "Discord API. The payload reports ok: false with an error object.",
    ),
    ("2", "The command line could not be parsed, for example an unknown option."),
]

FILES = [
    (
        ".env",
        "Read from the current working directory at startup. Used to supply "
        "DISCORD_BOT_TOKEN without exporting it into the shell environment.",
    ),
]

EXAMPLES = [
    ("Show the current guild's profile as JSON:", "discord-cli guild info"),
    (
        "List channels as a human-readable table:",
        "discord-cli --human channel list",
    ),
    (
        "Create a text channel with a topic:",
        "discord-cli channel create announcements --type text \\\\\n"
        '    --topic "Server announcements"',
    ),
    (
        "Send a message to a channel:",
        'discord-cli message send 123456789012345678 --content "Deploy finished"',
    ),
    (
        "Target a specific guild when the bot is in several:",
        "discord-cli --guild 123456789012345678 role list",
    ),
    (
        "Export channel history and filter it with jq:",
        "discord-cli export channel 123456789012345678 --limit 500 | jq '.result'",
    ),
    (
        "Supply the token explicitly instead of via the environment:",
        'discord-cli --token "$MY_TOKEN" member list',
    ),
]

SEE_ALSO = [
    "Project homepage and full documentation: https://github.com/1solomonwakhungu/discord-cli",
    "Recipes for CI, cron, and agent workflows: docs/recipes.md in the source tree.",
    "jq(1) for filtering the JSON output.",
]


def _wrap_lines(lines: list) -> list:
    """Wrap prose lines, leaving control lines and no-fill blocks untouched.

    roff refills filled text itself, so this only affects the bytes on disk: it
    keeps the committed page within mandoc's style limit and keeps regeneration
    diffs line-oriented instead of one enormous line per paragraph.
    """
    wrapped: list = []
    in_nofill = False

    for line in lines:
        if line.startswith(".nf"):
            in_nofill = True
        elif line.startswith(".fi"):
            in_nofill = False

        if in_nofill or line.startswith(".") or len(line) <= WRAP_WIDTH:
            wrapped.append(line)
            continue

        pieces = textwrap.wrap(
            line,
            width=WRAP_WIDTH,
            break_long_words=False,
            break_on_hyphens=False,
        )
        for index, piece in enumerate(pieces):
            # A continuation that happens to start with . or ' would be read as
            # a roff control line.
            if index and (piece.startswith(".") or piece.startswith("'")):
                piece = "\\&" + piece
            wrapped.append(piece)

    return wrapped


def escape(text: str) -> str:
    """Escape a plain string for safe inclusion in roff output."""
    if not text:
        return ""
    escaped = text.replace("\\", "\\e").replace("-", "\\-")
    # A line starting with . or ' is a roff control line; neutralize it.
    if escaped.startswith(".") or escaped.startswith("'"):
        escaped = "\\&" + escaped
    return escaped


def _escape_preformatted(text: str) -> str:
    """Escape text destined for a .nf/.fi block, preserving intentional markup."""
    return text.replace("-", "\\-")


def _clean(text: str | None) -> str:
    """Collapse a docstring or help string into a single line."""
    if not text:
        return ""
    return " ".join(text.split())


def _first_sentence(text: str) -> str:
    """Return the first sentence of a help string, for summary listings."""
    cleaned = _clean(text)
    if not cleaned:
        return ""
    head, separator, _ = cleaned.partition(". ")
    return head + "." if separator else cleaned


def argument_placeholder(param: click.Argument) -> str:
    """Render a positional argument the way the synopsis should show it."""
    name = param.metavar or param.name.upper()
    if param.nargs == -1:
        return f"[{name}]..."
    if not param.required:
        return f"[{name}]"
    return name


def option_names(param: click.Option) -> str:
    """Render an option's flags plus its value placeholder."""
    flags = ", ".join(sorted(param.opts, key=len))
    if param.is_flag:
        return flags
    metavar = param.metavar or _type_metavar(param)
    return f"{flags} {metavar}" if metavar else flags


def _type_metavar(param: click.Option) -> str:
    param_type = param.type
    if isinstance(param_type, click.Choice):
        return "{" + "|".join(str(choice) for choice in param_type.choices) + "}"
    name = getattr(param_type, "name", "") or ""
    if name in ("text", "string"):
        return "TEXT"
    if name in ("integer", "int"):
        return "INTEGER"
    if name == "bool":
        return "BOOL"
    return name.upper() or "VALUE"


def _has_default(param: click.Option) -> bool:
    """Report whether an option has a real default worth documenting.

    Click >= 8.2 represents "no default" with an ``UNSET`` sentinel rather than
    ``None``, and the sentinel's repr would otherwise be printed verbatim.
    """
    default = param.default
    if default is None or type(default).__name__ == "Sentinel":
        return False
    return default != () and default != []


def option_description(param: click.Option) -> str:
    """Build a description for an option, appending choices and defaults."""
    parts = []
    help_text = _clean(param.help)
    if help_text:
        parts.append(help_text)

    if isinstance(param.type, click.Choice):
        choices = ", ".join(str(choice) for choice in param.type.choices)
        parts.append(f"One of: {choices}.")

    if _has_default(param) and not param.is_flag:
        parts.append(f"Defaults to {param.default}.")

    if param.required:
        parts.append("Required.")

    if not parts:
        parts.append(f"Set the {param.name.replace('_', ' ')} value.")

    return " ".join(parts)


def _visible_options(command: click.Command) -> list:
    return [
        param for param in command.params if isinstance(param, click.Option) and not param.hidden
    ]


def _arguments(command: click.Command) -> list:
    return [param for param in command.params if isinstance(param, click.Argument)]


def _subcommands(group: click.Group) -> list:
    """Return a group's non-hidden subcommands, sorted by name."""
    result = []
    for name in sorted(group.commands):
        command = group.commands[name]
        if not command.hidden:
            result.append((name, command))
    return result


def command_synopsis(prog_name: str, path: str, command: click.Command) -> str:
    """Build a one-line synopsis for a leaf command."""
    pieces = [prog_name, path]
    if _visible_options(command):
        pieces.append("[OPTIONS]")
    pieces.extend(argument_placeholder(arg) for arg in _arguments(command))
    return " ".join(piece for piece in pieces if piece)


def _render_leaf_command(lines: list, prog_name: str, path: str, command: click.Command) -> None:
    lines.append(f".SS {escape(f'{prog_name} {path}')}")
    lines.append(".nf")
    lines.append(_escape_preformatted(command_synopsis(prog_name, path, command)))
    lines.append(".fi")

    description = _clean(command.help) or _clean(command.short_help)
    if description:
        lines.append(".PP")
        lines.append(escape(description))

    arguments = _arguments(command)
    if arguments:
        lines.append(".PP")
        lines.append("Arguments:")
        for argument in arguments:
            lines.append(".RS 4")
            lines.append(".TP")
            lines.append(f"\\fB{escape(argument_placeholder(argument))}\\fR")
            required = "Required." if argument.required else "Optional."
            lines.append(escape(f"{argument.name.replace('_', ' ').capitalize()}. {required}"))
            lines.append(".RE")

    options = _visible_options(command)
    if options:
        lines.append(".PP")
        lines.append("Options:")
        for option in options:
            lines.append(".RS 4")
            lines.append(".TP")
            lines.append(f"\\fB{_escape_preformatted(option_names(option))}\\fR")
            lines.append(escape(option_description(option)))
            lines.append(".RE")


def _render_group(lines: list, prog_name: str, name: str, group: click.Group) -> None:
    lines.append(f".SH {escape(name.upper())}")
    description = _clean(group.help) or _clean(group.short_help)
    if description:
        lines.append(escape(description))

    for subname, subcommand in _subcommands(group):
        path = f"{name} {subname}"
        if isinstance(subcommand, click.Group):
            for leafname, leaf in _subcommands(subcommand):
                _render_leaf_command(lines, prog_name, f"{path} {leafname}", leaf)
        else:
            _render_leaf_command(lines, prog_name, path, subcommand)


def render_manpage(
    cli: click.Group,
    prog_name: str = "discord-cli",
    version: str = "",
    date: str = MANPAGE_DATE,
) -> str:
    """Render the complete man page for ``cli`` as a roff document."""
    lines: list = []

    lines.append('.\\" Generated by discord_cli.manpage -- do not edit this file by hand.')
    lines.append('.\\" Regenerate with: python -m discord_cli.manpage')
    lines.append(
        f'.TH {escape(prog_name.upper())} {MANUAL_SECTION} "{date}" '
        f'"{escape(SOURCE_NAME)} {version}" "{escape(MANUAL_NAME)}"'
    )

    # NAME
    lines.append(".SH NAME")
    lines.append(f"{escape(prog_name)} \\- {escape(SHORT_DESCRIPTION)}")

    # SYNOPSIS
    lines.append(".SH SYNOPSIS")
    lines.append(".nf")
    lines.append(_escape_preformatted(f"{prog_name} [GLOBAL OPTIONS] COMMAND [ARGS]..."))
    lines.append(_escape_preformatted(f"{prog_name} --version"))
    lines.append(_escape_preformatted(f"{prog_name} --help"))
    lines.append(".fi")

    # DESCRIPTION
    lines.append(".SH DESCRIPTION")
    for index, paragraph in enumerate(DESCRIPTION_PARAGRAPHS):
        if index:
            lines.append(".PP")
        lines.append(paragraph.replace("-", "\\-"))

    # GLOBAL OPTIONS
    lines.append(".SH GLOBAL OPTIONS")
    lines.append(
        escape(
            "These options are accepted by the top-level command and apply to "
            "every subcommand. They must appear before the command name."
        )
    )
    for option in _visible_options(cli):
        lines.append(".TP")
        lines.append(f"\\fB{_escape_preformatted(option_names(option))}\\fR")
        lines.append(escape(option_description(option)))

    # COMMAND SUMMARY
    lines.append(".SH COMMANDS")
    lines.append(
        escape(
            "Commands are grouped by the Discord resource they operate on. "
            "Each group is documented in its own section below."
        )
    )
    for name, group in _subcommands(cli):
        lines.append(".TP")
        lines.append(f"\\fB{escape(name)}\\fR")
        summary = _first_sentence(group.help or group.short_help or "")
        lines.append(escape(summary))

    # Per-group detail sections.
    for name, group in _subcommands(cli):
        if isinstance(group, click.Group):
            _render_group(lines, prog_name, name, group)
        else:
            lines.append(f".SH {escape(name.upper())}")
            _render_leaf_command(lines, prog_name, name, group)

    # ENVIRONMENT
    lines.append(".SH ENVIRONMENT")
    for variable, description in ENVIRONMENT_VARIABLES:
        lines.append(".TP")
        lines.append(f"\\fB{escape(variable)}\\fR")
        lines.append(description.replace("-", "\\-"))

    # FILES
    lines.append(".SH FILES")
    for path, description in FILES:
        lines.append(".TP")
        lines.append(f"\\fB{escape(path)}\\fR")
        lines.append(escape(description))

    # EXIT STATUS
    lines.append(".SH EXIT STATUS")
    for code, description in EXIT_STATUS:
        lines.append(".TP")
        lines.append(f"\\fB{escape(code)}\\fR")
        lines.append(escape(description))

    # EXAMPLES
    lines.append(".SH EXAMPLES")
    for index, (caption, command) in enumerate(EXAMPLES):
        if index:
            lines.append(".PP")
        lines.append(escape(caption))
        lines.append(".RS 4")
        lines.append(".nf")
        lines.append(_escape_preformatted(command))
        lines.append(".fi")
        lines.append(".RE")

    # SEE ALSO
    lines.append(".SH SEE ALSO")
    for index, entry in enumerate(SEE_ALSO):
        if index:
            lines.append(".br")
        lines.append(escape(entry))

    # BUGS
    lines.append(".SH BUGS")
    lines.append(escape("Report bugs at https://github.com/1solomonwakhungu/discord-cli/issues"))

    # AUTHOR / LICENSE
    lines.append(".SH AUTHOR")
    lines.append(escape("Solomon Wakhungu <1solomonwakhungu@gmail.com>"))
    lines.append(".SH LICENSE")
    lines.append(
        escape(
            "MIT License. This is free software: you are free to change and "
            "redistribute it. There is NO WARRANTY, to the extent permitted by law."
        )
    )

    return "\n".join(_wrap_lines(lines)) + "\n"


def build_manpage() -> str:
    """Render the man page for the project's own CLI at its current version."""
    from discord_cli import __version__
    from discord_cli.cli import main

    return render_manpage(main, prog_name="discord-cli", version=__version__)


def main() -> None:
    """Write the generated man page to stdout."""
    click.echo(build_manpage(), nl=False)


if __name__ == "__main__":  # pragma: no cover
    main()
