from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.enums import AltEnterAction
from src.preferences import (
    FindPreferences,
    _parse_base_dirs,
    get_preferences,
    load_raw_preferences,
    validate_preferences,
)


def _make_prefs(**overrides) -> FindPreferences:
    defaults = {
        "alt_enter_action": AltEnterAction.OPEN_FOLDER,
        "allow_hidden": False,
        "follow_symlinks": False,
        "result_limit": 15,
        "search_timeout": 5.0,
        "base_dir": [Path("/tmp")],
        "ignore_file": None,
        "terminal_cmd": None,
    }
    defaults.update(overrides)
    if "base_dir" in overrides and not isinstance(overrides["base_dir"], list):
        defaults["base_dir"] = [overrides["base_dir"]]
    return FindPreferences(**defaults)


def _raw(**overrides) -> dict[str, str]:
    base = {
        "alt_enter_action": "0",
        "allow_hidden": "0",
        "follow_symlinks": "0",
        "result_limit": "15",
        "search_timeout": "5",
        "base_dir": "~",
        "ignore_file": "",
        "terminal_cmd": "",
    }
    base.update(overrides)
    return base


class TestParseBaseDirs:
    def test_single(self):
        assert _parse_base_dirs("/tmp") == [Path("/tmp")]

    def test_tilde_expands(self):
        assert _parse_base_dirs("~") == [Path.home()]

    def test_comma_separated(self):
        assert _parse_base_dirs("/tmp,/var/tmp") == [Path("/tmp"), Path("/var/tmp")]

    def test_strips_whitespace(self):
        assert _parse_base_dirs(" /tmp , /var/tmp ") == [Path("/tmp"), Path("/var/tmp")]

    def test_empty_falls_back_to_home(self):
        assert _parse_base_dirs("") == [Path.home()]


class TestGetPreferences:
    def test_parses_types(self):
        prefs = get_preferences(_raw(alt_enter_action="2", allow_hidden="1", result_limit="20", search_timeout="3.5"))
        assert prefs.alt_enter_action == AltEnterAction.COPY_PATH
        assert prefs.allow_hidden is True
        assert prefs.result_limit == 20
        assert prefs.search_timeout == 3.5
        assert isinstance(prefs.search_timeout, float)

    def test_blank_numeric_uses_default(self):
        # A cleared field arrives as "" and should fall back, not crash.
        prefs = get_preferences(_raw(result_limit="", search_timeout=""))
        assert prefs.result_limit == 15
        assert prefs.search_timeout == 5.0

    def test_garbage_numeric_raises_valueerror(self):
        # main.py turns this into a visible message rather than a silent death.
        with pytest.raises(ValueError):
            get_preferences(_raw(result_limit="abc"))

    def test_blank_terminal_cmd_is_none(self):
        assert get_preferences(_raw(terminal_cmd="  ")).terminal_cmd is None


class TestValidatePreferences:
    def test_valid(self, tmp_path):
        assert validate_preferences(_make_prefs(base_dir=tmp_path)) == []

    def test_missing_base_dir(self):
        errors = validate_preferences(_make_prefs(base_dir=[Path("/no/such/dir/xyz")]))
        assert any("does not exist" in e for e in errors)

    def test_one_of_many_base_dirs_missing(self, tmp_path):
        errors = validate_preferences(_make_prefs(base_dir=[tmp_path, Path("/no/such/xyz")]))
        assert any("/no/such/xyz" in e for e in errors)

    def test_missing_ignore_file(self, tmp_path):
        errors = validate_preferences(_make_prefs(base_dir=tmp_path, ignore_file=tmp_path / "nope.txt"))
        assert any("Ignore file" in e for e in errors)

    def test_zero_result_limit(self, tmp_path):
        assert any("Result limit" in e for e in validate_preferences(_make_prefs(base_dir=tmp_path, result_limit=0)))

    def test_zero_search_timeout(self, tmp_path):
        assert any("Search time limit" in e for e in validate_preferences(_make_prefs(base_dir=tmp_path, search_timeout=0)))

    def test_negative_search_timeout(self, tmp_path):
        assert any("Search time limit" in e for e in validate_preferences(_make_prefs(base_dir=tmp_path, search_timeout=-1)))


class TestLoadRawPreferences:
    def test_reads_from_disk(self, tmp_path):
        f = tmp_path / "prefs.json"
        f.write_text(json.dumps({
            "preferences": {"result_limit": "20", "search_timeout": "8"},
            "triggers": {"kw_fz": {"keyword": "zz"}, "kw_files": {"keyword": "ii"}},
        }))
        with patch("src.preferences.PREFS_FILE", f):
            raw = load_raw_preferences()
        assert raw["result_limit"] == "20"
        assert raw["search_timeout"] == "8"
        assert raw["kw_fz"] == "zz"
        assert raw["kw_files"] == "ii"

    def test_defaults_when_file_missing(self, tmp_path):
        with patch("src.preferences.PREFS_FILE", tmp_path / "nope.json"):
            raw = load_raw_preferences()
        assert raw["result_limit"] == "15"
        assert raw["search_timeout"] == "5"
        assert raw["base_dir"] == "~"

    def test_defaults_on_invalid_json(self, tmp_path):
        f = tmp_path / "prefs.json"
        f.write_text("{ not valid json")
        with patch("src.preferences.PREFS_FILE", f):
            raw = load_raw_preferences()
        assert raw["search_timeout"] == "5"
