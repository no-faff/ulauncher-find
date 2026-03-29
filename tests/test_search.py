from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.enums import AltEnterAction, MatchMode, SearchType
from src.preferences import FindPreferences
from src.search import _build_fd_cmd, _resolve_fd_binary, search


def _make_prefs(**overrides) -> FindPreferences:
    defaults = {
        "alt_enter_action": AltEnterAction.OPEN_FOLDER,
        "allow_hidden": False,
        "follow_symlinks": False,
        "result_limit": 15,
        "base_dir": Path("/home/test"),
        "ignore_file": None,
        "terminal_cmd": None,
    }
    defaults.update(overrides)
    return FindPreferences(**defaults)


class TestResolveFdBinary:
    def test_finds_fd(self):
        with patch("shutil.which", side_effect=lambda x: "/usr/bin/fd" if x == "fd" else None):
            assert _resolve_fd_binary() == "fd"

    def test_finds_fdfind_on_debian(self):
        with patch("shutil.which", side_effect=lambda x: "/usr/bin/fdfind" if x == "fdfind" else None):
            assert _resolve_fd_binary() == "fdfind"

    def test_returns_none_if_neither(self):
        with patch("shutil.which", return_value=None):
            assert _resolve_fd_binary() is None


class TestBuildFdCmd:
    def test_basic_exact_search(self):
        prefs = _make_prefs()
        cmd = _build_fd_cmd(prefs, "budget", SearchType.BOTH, MatchMode.EXACT)
        assert cmd[1] == "-a"
        assert "--color" in cmd and "never" in cmd
        assert "budget" in cmd
        assert str(Path("/home/test")) in cmd
        assert "--max-results" in cmd

    def test_files_only(self):
        prefs = _make_prefs()
        cmd = _build_fd_cmd(prefs, "test", SearchType.FILES, MatchMode.EXACT)
        type_idx = cmd.index("--type")
        assert cmd[type_idx + 1] == "f"

    def test_dirs_only(self):
        prefs = _make_prefs()
        cmd = _build_fd_cmd(prefs, "test", SearchType.DIRS, MatchMode.EXACT)
        type_idx = cmd.index("--type")
        assert cmd[type_idx + 1] == "d"

    def test_hidden_files(self):
        prefs = _make_prefs(allow_hidden=True)
        cmd = _build_fd_cmd(prefs, "test", SearchType.BOTH, MatchMode.EXACT)
        assert "--hidden" in cmd

    def test_no_hidden_by_default(self):
        prefs = _make_prefs()
        cmd = _build_fd_cmd(prefs, "test", SearchType.BOTH, MatchMode.EXACT)
        assert "--hidden" not in cmd

    def test_follow_symlinks(self):
        prefs = _make_prefs(follow_symlinks=True)
        cmd = _build_fd_cmd(prefs, "test", SearchType.BOTH, MatchMode.EXACT)
        assert "--follow" in cmd

    def test_ignore_file(self):
        prefs = _make_prefs(ignore_file=Path("/home/test/.findignore"))
        cmd = _build_fd_cmd(prefs, "test", SearchType.BOTH, MatchMode.EXACT)
        assert "--ignore-file" in cmd
        assert str(Path("/home/test/.findignore")) in cmd

    def test_fuzzy_mode_uses_dot_pattern(self):
        prefs = _make_prefs()
        cmd = _build_fd_cmd(prefs, "budget", SearchType.BOTH, MatchMode.FUZZY)
        assert "." in cmd
        assert "budget" not in cmd

    def test_fuzzy_mode_no_max_results(self):
        prefs = _make_prefs()
        cmd = _build_fd_cmd(prefs, "budget", SearchType.BOTH, MatchMode.FUZZY)
        assert "--max-results" not in cmd


class TestSearch:
    def test_returns_paths(self):
        prefs = _make_prefs(base_dir=Path.home())
        results = search(prefs, "python", SearchType.BOTH, MatchMode.EXACT)
        assert isinstance(results, list)
        if results:
            assert isinstance(results[0], str)

    def test_respects_result_limit(self):
        prefs = _make_prefs(base_dir=Path.home(), result_limit=3)
        results = search(prefs, "a", SearchType.BOTH, MatchMode.EXACT)
        assert len(results) <= 3

    def test_fuzzy_search_returns_results(self):
        prefs = _make_prefs(base_dir=Path.home())
        results = search(prefs, "python", SearchType.BOTH, MatchMode.FUZZY)
        assert isinstance(results, list)
