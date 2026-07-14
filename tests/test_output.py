"""Tests for discord_cli.output: make_payload, print_json, print_human."""

from __future__ import annotations

import json
import sys

import pytest

from discord_cli.output import make_payload, print_human, print_json, print_output


class TestMakePayload:
    def test_success_wraps_result(self):
        payload = make_payload(result={"id": 1})
        assert payload == {"ok": True, "data": {"id": 1}}

    def test_success_with_no_result(self):
        payload = make_payload()
        assert payload == {"ok": True, "data": None}

    def test_error_wraps_error_and_ignores_result(self):
        error = {"type": "CliError", "message": "boom"}
        payload = make_payload(result={"id": 1}, error=error)
        assert payload == {"ok": False, "error": error}


class TestPrintJson:
    def test_prints_indented_json(self, capsys):
        print_json({"ok": True, "data": {"id": 1}})
        captured = capsys.readouterr()
        assert json.loads(captured.out) == {"ok": True, "data": {"id": 1}}
        assert "\n  " in captured.out  # indent=2

    def test_uses_str_fallback_for_non_serializable(self, capsys):
        class Weird:
            def __str__(self):
                return "weird-value"

        print_json({"ok": True, "data": {"thing": Weird()}})
        captured = capsys.readouterr()
        assert json.loads(captured.out) == {"ok": True, "data": {"thing": "weird-value"}}


class TestPrintHuman:
    def test_error_payload_prints_message(self, capsys):
        print_human({"ok": False, "error": {"type": "CliError", "message": "no permission"}})
        captured = capsys.readouterr()
        assert "no permission" in captured.out

    def test_list_of_dicts_renders_table(self, capsys):
        payload = {
            "ok": True,
            "data": {"roles": [{"id": 1, "name": "Admin"}, {"id": 2, "name": "Member"}]},
        }
        print_human(payload)
        captured = capsys.readouterr()
        assert "roles" in captured.out
        assert "Admin" in captured.out
        assert "Member" in captured.out

    def test_non_list_data_prints_json(self, capsys):
        payload = {"ok": True, "data": {"id": 1, "name": "solo"}}
        print_human(payload)
        captured = capsys.readouterr()
        assert "solo" in captured.out

    def test_empty_list_falls_back_to_json(self, capsys):
        payload = {"ok": True, "data": {"roles": []}}
        print_human(payload)
        captured = capsys.readouterr()
        assert "roles" in captured.out

    def test_table_row_with_nested_value_is_json_encoded(self, capsys):
        payload = {
            "ok": True,
            "data": {
                "members": [
                    {"id": 1, "name": "solo", "roles": [{"id": 9, "name": "Admin"}]},
                ]
            },
        }
        print_human(payload)
        captured = capsys.readouterr()
        assert "Admin" in captured.out

    def test_falls_back_to_json_when_rich_unavailable(self, monkeypatch, capsys):
        monkeypatch.setitem(sys.modules, "rich.console", None)
        monkeypatch.setitem(sys.modules, "rich.table", None)
        payload = {"ok": True, "data": {"id": 1}}
        print_human(payload)
        captured = capsys.readouterr()
        assert json.loads(captured.out) == payload


class TestPrintOutput:
    def test_human_true_calls_print_human(self, capsys):
        print_output({"ok": True, "data": {"id": 1}}, human=True)
        captured = capsys.readouterr()
        assert "1" in captured.out

    def test_human_false_calls_print_json(self, capsys):
        print_output({"ok": True, "data": {"id": 1}}, human=False)
        captured = capsys.readouterr()
        assert json.loads(captured.out) == {"ok": True, "data": {"id": 1}}
