"""Tests for the man page renderer and the committed man page artifact."""

from __future__ import annotations

import re
from pathlib import Path

import click
import pytest

from discord_cli import __version__, manpage
from discord_cli.cli import main

MANPAGE_PATH = Path(__file__).resolve().parent.parent / "docs" / "man" / "discord-cli.1"


@pytest.fixture(scope="module")
def rendered() -> str:
    return manpage.build_manpage()


class TestCommittedArtifact:
    def test_manpage_file_exists(self):
        assert MANPAGE_PATH.is_file()

    def test_committed_manpage_matches_generator(self, rendered):
        """The committed page must be byte-identical to a fresh render.

        If this fails, regenerate it with:
            python -m discord_cli.manpage > docs/man/discord-cli.1
        """
        committed = MANPAGE_PATH.read_text(encoding="utf-8")
        assert committed == rendered, (
            "docs/man/discord-cli.1 is out of date. Regenerate it with: "
            "python -m discord_cli.manpage > docs/man/discord-cli.1"
        )

    def test_committed_manpage_reports_current_version(self):
        committed = MANPAGE_PATH.read_text(encoding="utf-8")
        assert f'"discord\\-cli {__version__}"' in committed


class TestStructure:
    @pytest.mark.parametrize(
        "section",
        [
            "NAME",
            "SYNOPSIS",
            "DESCRIPTION",
            "GLOBAL OPTIONS",
            "COMMANDS",
            "ENVIRONMENT",
            "FILES",
            "EXIT STATUS",
            "EXAMPLES",
            "SEE ALSO",
            "BUGS",
            "AUTHOR",
            "LICENSE",
        ],
    )
    def test_required_section_present(self, rendered, section):
        assert f".SH {section}\n" in rendered

    def test_title_header_is_first_directive(self, rendered):
        directives = [
            line for line in rendered.splitlines() if line.startswith(".") and line[1] != "\\"
        ]
        assert directives[0].startswith(".TH DISCORD\\-CLI 1 ")

    def test_ends_with_newline(self, rendered):
        assert rendered.endswith("\n")

    def test_nofill_blocks_are_balanced(self, rendered):
        depth = 0
        for line in rendered.splitlines():
            if line.startswith(".nf"):
                depth += 1
                assert depth == 1, "nested .nf block"
            elif line.startswith(".fi"):
                depth -= 1
                assert depth == 0, "unbalanced .fi"
        assert depth == 0

    def test_rs_blocks_are_balanced(self, rendered):
        opens = sum(1 for line in rendered.splitlines() if line.startswith(".RS"))
        closes = sum(1 for line in rendered.splitlines() if line.startswith(".RE"))
        assert opens == closes

    def test_no_line_exceeds_mandoc_style_limit(self, rendered):
        too_long = [
            line
            for line in rendered.splitlines()
            if len(line.encode("utf-8")) > 80 and not line.startswith(".")
        ]
        assert too_long == []


class TestCommandCoverage:
    def test_every_group_has_a_section(self, rendered):
        for name in main.commands:
            assert f".SH {name.upper()}\n" in rendered, f"missing section for {name}"

    def test_every_leaf_command_is_documented(self, rendered):
        missing = []
        for group_name, group in main.commands.items():
            for sub_name, sub in group.commands.items():
                if isinstance(sub, click.Group):
                    for leaf_name in sub.commands:
                        path = f"{group_name} {sub_name} {leaf_name}"
                        if f".SS discord\\-cli {path}" not in rendered:
                            missing.append(path)
                else:
                    path = f"{group_name} {sub_name}"
                    if f".SS discord\\-cli {path}" not in rendered:
                        missing.append(path)
        assert missing == []

    def test_global_options_are_documented(self, rendered):
        global_options = rendered.split(".SH GLOBAL OPTIONS")[1].split(".SH COMMANDS")[0]
        for flag in ("\\-\\-token", "\\-\\-guild", "\\-\\-human", "\\-\\-version"):
            assert flag in global_options

    def test_documents_a_known_command_option(self, rendered):
        # channel create --type is a Choice, so its values must be enumerated.
        assert "{text|voice|stage|forum}" in rendered


class TestEscaping:
    def test_hyphens_are_escaped_outside_control_lines(self, rendered):
        offenders = [
            line
            for line in rendered.splitlines()
            if not line.startswith(".") and re.search(r"(?<!\\)-", line)
        ]
        assert offenders == []

    def test_escape_neutralizes_leading_control_characters(self):
        assert manpage.escape(".env").startswith("\\&")
        assert manpage.escape("'quoted").startswith("\\&")

    def test_escape_handles_empty_string(self):
        assert manpage.escape("") == ""

    def test_escape_escapes_backslashes(self):
        assert manpage.escape("a\\b") == "a\\eb"


class TestRendererUnits:
    def test_argument_placeholder_variants(self):
        required = click.Argument(["channel_id"], required=True)
        optional = click.Argument(["channel_id"], required=False)
        variadic = click.Argument(["ids"], nargs=-1)
        assert manpage.argument_placeholder(required) == "CHANNEL_ID"
        assert manpage.argument_placeholder(optional) == "[CHANNEL_ID]"
        assert manpage.argument_placeholder(variadic) == "[IDS]..."

    def test_option_names_render_flags_and_metavar(self):
        flag = click.Option(["--human"], is_flag=True)
        valued = click.Option(["--guild", "-g"], type=int)
        assert manpage.option_names(flag) == "--human"
        assert manpage.option_names(valued) == "-g, --guild INTEGER"

    def test_option_description_includes_choices_and_default(self):
        option = click.Option(
            ["--type"], type=click.Choice(["text", "voice"]), default="text", help="Channel type."
        )
        description = manpage.option_description(option)
        assert "Channel type." in description
        assert "One of: text, voice." in description
        assert "Defaults to text." in description

    def test_option_description_marks_required(self):
        option = click.Option(["--name"], required=True, help="A name.")
        assert "Required." in manpage.option_description(option)

    def test_option_description_falls_back_when_no_help(self):
        option = click.Option(["--max_age"])
        assert manpage.option_description(option) == "Set the max age value."

    def test_render_manpage_accepts_a_custom_program(self):
        @click.group(help="A tiny tool.")
        def tiny():
            pass

        @tiny.command(help="Do a thing.")
        @click.argument("target")
        @click.option("--loud", is_flag=True, help="Be loud.")
        def act(target, loud):
            pass

        rendered = manpage.render_manpage(tiny, prog_name="tiny", version="9.9.9")
        assert ".TH TINY 1 " in rendered
        assert '"tiny 9.9.9"' not in rendered  # source name is discord-cli
        assert ".SS tiny act" in rendered
        assert "TARGET" in rendered
        assert "\\-\\-loud" in rendered

    def test_hidden_commands_are_not_documented(self):
        @click.group(help="Group.")
        def parent():
            pass

        @parent.command(hidden=True, help="Secret.")
        def secret():
            pass

        @parent.command(help="Public.")
        def public():
            pass

        rendered = manpage.render_manpage(parent, prog_name="parent")
        assert "secret" not in rendered
        assert ".SS parent public" in rendered

    def test_hidden_options_are_not_documented(self):
        @click.group(help="Group.")
        def parent():
            pass

        @parent.command(help="Cmd.")
        @click.option("--internal", hidden=True)
        @click.option("--shown", help="Shown option.")
        def cmd(internal, shown):
            pass

        rendered = manpage.render_manpage(parent, prog_name="parent")
        assert "internal" not in rendered
        assert "\\-\\-shown" in rendered


class TestEntryPoint:
    def test_module_main_writes_the_page(self, capsys):
        manpage.main()
        captured = capsys.readouterr().out
        assert captured.startswith(".\\\"")
        assert ".SH NAME" in captured
