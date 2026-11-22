"""Drift guards ensuring docs, commands.json, SKILL.md, and manpage stay aligned with Click."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import click

from discord_cli.cli import main

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMANDS_JSON_PATH = REPO_ROOT / "commands.json"
SKILL_MD_PATH = REPO_ROOT / "skills" / "discord-cli-server-management" / "SKILL.md"
AI_AGENTS_MD_PATH = REPO_ROOT / "docs" / "ai-agents.md"
MANPAGE_PATH = REPO_ROOT / "docs" / "man" / "discord-cli.1"


def _live_leaf_commands(
    group: click.Group, prefix: tuple[str, ...] = ()
) -> dict[tuple[str, ...], click.Command]:
    leaves: dict[tuple[str, ...], click.Command] = {}
    for name, cmd in group.commands.items():
        if cmd.hidden:
            continue
        path = (*prefix, name)
        if isinstance(cmd, click.Group):
            leaves.update(_live_leaf_commands(cmd, path))
        else:
            leaves[path] = cmd
    return leaves


def _json_leaf_commands(data: dict[str, Any]) -> dict[tuple[str, ...], dict[str, Any]]:
    leaves: dict[tuple[str, ...], dict[str, Any]] = {}
    for group in data["command_groups"]:
        gname = group["name"]
        for cmd in group["commands"]:
            cname = cmd["name"]
            if "subcommands" in cmd:
                for sub in cmd["subcommands"]:
                    assert isinstance(sub, dict), (
                        f"Expected structured subcommand dict under {gname} {cname}, got {sub!r}"
                    )
                    leaves[(gname, cname, sub["name"])] = sub
            else:
                leaves[(gname, cname)] = cmd
    return leaves


def _click_option_flags(cmd: click.Command) -> set[str]:
    return {
        opt
        for param in cmd.params
        if isinstance(param, click.Option) and not param.hidden
        for opt in param.opts
    }


def _click_arg_names(cmd: click.Command) -> list[str]:
    return [param.name for param in cmd.params if isinstance(param, click.Argument) and param.name]


class TestCommandsJsonDrift:
    def test_global_options_match_click(self):
        data = json.loads(COMMANDS_JSON_PATH.read_text(encoding="utf-8"))
        documented = {opt["name"] for opt in data["global_options"]}
        live = _click_option_flags(main) - {"--version", "--help"}
        assert documented == live

    def test_top_level_groups_match_click(self):
        data = json.loads(COMMANDS_JSON_PATH.read_text(encoding="utf-8"))
        group_names = [group["name"] for group in data["command_groups"]]
        assert len(group_names) == len(set(group_names)), "Duplicate groups in commands.json"
        assert set(group_names) == set(main.commands.keys())

    def test_leaf_commands_args_and_options_match_click(self):
        data = json.loads(COMMANDS_JSON_PATH.read_text(encoding="utf-8"))
        live_leaves = _live_leaf_commands(main)
        json_leaves = _json_leaf_commands(data)

        assert set(json_leaves.keys()) == set(live_leaves.keys())

        for path, live_cmd in sorted(live_leaves.items()):
            spec = json_leaves[path]
            label = " ".join(path)

            doc_args = [arg["name"] for arg in spec.get("args", [])]
            assert doc_args == _click_arg_names(live_cmd), f"Args mismatch for `{label}`"

            doc_opts = {opt["name"] for opt in spec.get("options", [])}
            assert doc_opts == _click_option_flags(live_cmd), f"Options mismatch for `{label}`"

            live_opt_by_flag = {
                flag: param
                for param in live_cmd.params
                if isinstance(param, click.Option) and not param.hidden
                for flag in param.opts
            }
            for opt_spec in spec.get("options", []):
                flag = opt_spec["name"]
                live_param = live_opt_by_flag[flag]
                assert bool(opt_spec.get("required", False)) == bool(live_param.required), (
                    f"Required mismatch for `{label} {flag}`"
                )
                if isinstance(live_param.type, click.Choice):
                    assert opt_spec.get("choices") == list(live_param.type.choices), (
                        f"Choices mismatch for `{label} {flag}`"
                    )


class TestSkillMdDrift:
    @staticmethod
    def _extract_catalog_section(content: str) -> str:
        match = re.search(
            r"^## Command Catalog\s*\n(.*?)(?=^## |\Z)", content, flags=re.MULTILINE | re.DOTALL
        )
        assert match is not None, "SKILL.md is missing `## Command Catalog` section"
        return match.group(1)

    def test_command_catalog_groups_match_click(self):
        catalog = self._extract_catalog_section(SKILL_MD_PATH.read_text(encoding="utf-8"))
        headings = re.findall(r"^###\s+(\S+)\s*$", catalog, flags=re.MULTILINE)
        assert len(headings) == len(set(headings)), "Duplicate group headings in SKILL.md"
        assert set(headings) == set(main.commands.keys())

    def test_command_catalog_leaves_and_flags_match_click(self):
        catalog = self._extract_catalog_section(SKILL_MD_PATH.read_text(encoding="utf-8"))
        live_leaves = _live_leaf_commands(main)

        documented_paths: set[tuple[str, ...]] = set()
        current_group: str | None = None

        for line in catalog.splitlines():
            heading = re.match(r"^###\s+(\S+)\s*$", line)
            if heading:
                current_group = heading.group(1)
                continue

            bullet = re.match(r"^-\s+`([^`]+)`", line)
            if not bullet:
                continue

            invocation = bullet.group(1).strip()
            tokens = invocation.split()
            assert tokens, f"Empty command bullet in SKILL.md: {line}"
            assert current_group is not None
            assert tokens[0] == current_group, (
                f"Bullet `{invocation}` under `### {current_group}` must start with `{current_group}`"
            )

            # Walk the Click tree greedily to find the leaf command path.
            cmd: click.Command = main
            path: list[str] = []
            idx = 0
            while isinstance(cmd, click.Group) and idx < len(tokens):
                token = tokens[idx]
                if token in cmd.commands:
                    cmd = cmd.commands[token]
                    path.append(token)
                    idx += 1
                else:
                    break

            path_tuple = tuple(path)
            assert path_tuple in live_leaves, (
                f"Documented command `{invocation}` does not resolve to a live Click leaf command"
            )
            documented_paths.add(path_tuple)

            # Every --flag shown on the catalog line must exist on that Click command.
            shown_flags = set(re.findall(r"--[a-z0-9][a-z0-9-]*", invocation))
            valid_flags = _click_option_flags(live_leaves[path_tuple])
            unknown_flags = shown_flags - valid_flags
            assert not unknown_flags, (
                f"Unknown flag(s) {sorted(unknown_flags)} on `{invocation}`; "
                f"valid flags are {sorted(valid_flags)}"
            )

        assert documented_paths == set(live_leaves.keys())


class TestDocsAndManpageDrift:
    def test_ai_agents_has_no_phantom_mcp_server(self):
        content = AI_AGENTS_MD_PATH.read_text(encoding="utf-8")
        assert "mcp serve" not in content
        assert "mcpServers" not in content

    def test_ai_agents_and_skill_do_not_use_query_flag_for_search(self):
        pattern = re.compile(r"search\s+(?:messages|members)\b[^\n]*--query")
        for doc_path in (AI_AGENTS_MD_PATH, SKILL_MD_PATH):
            content = doc_path.read_text(encoding="utf-8")
            assert not pattern.search(content), f"Found invalid --query on search in {doc_path}"

    def test_manpage_does_not_reference_dot_result(self):
        content = MANPAGE_PATH.read_text(encoding="utf-8")
        assert ".result" not in content
        assert "\\fBresult\\fR" not in content
