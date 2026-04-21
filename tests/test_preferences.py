from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from src.enums import AltEnterAction
from src.preferences import (
    FindPreferences,
    _parse_base_dirs,
    load_raw_preferences,
    validate_preferences,
)


def _make_prefs(**overrides) -> FindPreferences:
    defaults = {
        "alt_enter_action": AltEnterAction.OPEN_FOLDER,
        "allow_hidden": False,
        "follow_symlinks": False,
        "result_limit": 15,
        "base_dir": [Path("/tmp")],
        "ignore_file": None,
        "terminal_cmd": None,
    }
    defaults.update(overrides)
    if "base_dir" in overrides and not isinstance(overrides["base_dir"], list):
        defaults["base_dir"] = [overrides["base_dir"]]
    return FindPreferences(**defaults)


class TestParseBaseDirs:
    def test_single_path(self):
        dirs = _parse_base_dirs("/tmp")
        assert dirs == [Path("/tmp")]

    def test_expands_tilde(self):
        dirs = _parse_base_dirs("~")
        assert dirs == [Path.home()]

    def test_comma_separated(self):
        dirs = _parse_base_dirs("/tmp,/var/log")
        assert dirs == [Path("/tmp"), Path("/var/log")]

    def test_strips_whitespace(self):
        dirs = _parse_base_dirs(" /tmp , /var/log ")
        assert dirs == [Path("/tmp"), Path("/var/log")]

    def test_mixed_tilde_and_absolute(self):
        dirs = _parse_base_dirs("~,/tmp")
        assert dirs == [Path.home(), Path("/tmp")]

    def test_empty_falls_back_to_home(self):
        dirs = _parse_base_dirs("")
        assert dirs == [Path.home()]


class TestValidatePreferences:
    def test_valid(self):
        prefs = _make_prefs(base_dir=Path("/tmp"))
        assert validate_preferences(prefs) == []

    def test_missing_base_dir(self):
        prefs = _make_prefs(base_dir=[Path("/nonexistent/path/xyz")])
        errors = validate_preferences(prefs)
        assert len(errors) == 1
        assert "does not exist" in errors[0]

    def test_one_of_many_base_dirs_missing(self, tmp_path):
        prefs = _make_prefs(base_dir=[tmp_path, Path("/nonexistent/xyz")])
        errors = validate_preferences(prefs)
        assert len(errors) == 1
        assert "/nonexistent/xyz" in errors[0]

    def test_missing_ignore_file(self, tmp_path):
        prefs = _make_prefs(base_dir=tmp_path, ignore_file=tmp_path / "missing.txt")
        errors = validate_preferences(prefs)
        assert any("Ignore file" in e for e in errors)

    def test_zero_result_limit(self, tmp_path):
        prefs = _make_prefs(base_dir=tmp_path, result_limit=0)
        errors = validate_preferences(prefs)
        assert any("Result limit" in e for e in errors)

    def test_negative_result_limit(self, tmp_path):
        prefs = _make_prefs(base_dir=tmp_path, result_limit=-1)
        errors = validate_preferences(prefs)
        assert any("Result limit" in e for e in errors)


class TestLoadRawPreferences:
    def test_reads_from_disk(self, tmp_path):
        prefs_file = tmp_path / "prefs.json"
        prefs_file.write_text(json.dumps({
            "preferences": {
                "alt_enter_action": "1",
                "allow_hidden": "1",
                "follow_symlinks": "0",
                "result_limit": "20",
                "base_dir": "/tmp",
                "ignore_file": "",
                "terminal_cmd": "",
            },
            "triggers": {
                "kw_fz": {"keyword": "zz"},
                "kw_all": {"keyword": "aa"},
                "kw_files": {"keyword": "ii"},
                "kw_dirs": {"keyword": "dd"},
            },
        }))
        with patch("src.preferences.PREFS_FILE", prefs_file):
            raw = load_raw_preferences()
        assert raw["kw_fz"] == "zz"
        assert raw["kw_files"] == "ii"
        assert raw["result_limit"] == "20"

    def test_flattens_triggers_when_preferences_missing(self, tmp_path):
        prefs_file = tmp_path / "prefs.json"
        prefs_file.write_text(json.dumps({
            "triggers": {"kw_all": {"keyword": "f"}},
        }))
        with patch("src.preferences.PREFS_FILE", prefs_file):
            raw = load_raw_preferences()
        assert raw["kw_all"] == "f"
        assert raw["result_limit"] == "15"

    def test_falls_back_when_file_missing(self, tmp_path):
        with patch("src.preferences.PREFS_FILE", tmp_path / "does-not-exist.json"):
            raw = load_raw_preferences()
        assert raw["result_limit"] == "15"
        assert raw["base_dir"] == "~"

    def test_falls_back_on_invalid_json(self, tmp_path):
        prefs_file = tmp_path / "prefs.json"
        prefs_file.write_text("not valid json {{")
        with patch("src.preferences.PREFS_FILE", prefs_file):
            raw = load_raw_preferences()
        assert raw["result_limit"] == "15"

    def test_uses_defaults_when_preferences_key_missing(self, tmp_path):
        prefs_file = tmp_path / "prefs.json"
        prefs_file.write_text(json.dumps({"something_else": {}}))
        with patch("src.preferences.PREFS_FILE", prefs_file):
            raw = load_raw_preferences()
        assert raw["result_limit"] == "15"
