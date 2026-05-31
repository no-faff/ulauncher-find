from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

from src.enums import AltEnterAction, MatchMode, SearchType
from src.preferences import FindPreferences
from src.search import (
    _build_fd_cmd,
    _exact_pattern_args,
    _rank_exact,
    _read_until_limit,
    resolve_fd_binary,
    search,
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


def _producer(script: str) -> subprocess.Popen:
    """A subprocess whose stdout we can feed to the reader under test."""
    return subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE, bufsize=0)


class TestResolveFdBinary:
    def test_finds_fd(self):
        with patch("shutil.which", side_effect=lambda x: "/usr/bin/fd" if x == "fd" else None):
            assert resolve_fd_binary() == "fd"

    def test_finds_fdfind_on_debian(self):
        with patch("shutil.which", side_effect=lambda x: "/usr/bin/fdfind" if x == "fdfind" else None):
            assert resolve_fd_binary() == "fdfind"

    def test_returns_none_if_neither(self):
        with patch("shutil.which", return_value=None):
            assert resolve_fd_binary() is None


class TestExactPatternArgs:
    def test_single_word_no_full_path(self):
        args = _exact_pattern_args("budget", 50)
        assert "--full-path" not in args
        assert "--fixed-strings" in args
        assert args[-2:] == ["--", "budget"]

    def test_max_results_passed_through(self):
        args = _exact_pattern_args("budget", 50)
        assert args[args.index("--max-results") + 1] == "50"

    def test_multi_word_uses_full_path_and_and(self):
        args = _exact_pattern_args("report march", 50)
        assert "--full-path" in args
        assert args[-2:] == ["--", "report"]
        assert args[args.index("--and") + 1] == "march"

    def test_and_comes_before_separator(self):
        args = _exact_pattern_args("report march", 50)
        assert args.index("--and") < args.index("--")

    def test_leading_dash_query_sits_after_separator(self):
        args = _exact_pattern_args("-foo", 50)
        assert args.index("--") < args.index("-foo")

    def test_whitespace_only_does_not_crash(self):
        args = _exact_pattern_args("   ", 50)
        assert args[-2] == "--"


class TestBuildFdCmd:
    def test_basic_exact_search(self):
        cmd = _build_fd_cmd(_make_prefs(), "budget", SearchType.BOTH, MatchMode.EXACT)
        assert cmd[0] in ("fd", "fdfind")
        assert cmd[1] == "-a"
        assert "--color" in cmd and "never" in cmd
        assert "budget" in cmd
        assert "/tmp" in cmd
        assert "--fixed-strings" in cmd
        assert "--max-results" in cmd
        assert "--" in cmd

    def test_separator_precedes_pattern_and_paths(self):
        cmd = _build_fd_cmd(_make_prefs(), "budget", SearchType.BOTH, MatchMode.EXACT)
        sep = cmd.index("--")
        assert cmd.index("budget") > sep
        assert cmd.index("/tmp") > sep

    def test_leading_dash_query_guarded(self):
        cmd = _build_fd_cmd(_make_prefs(), "-foo", SearchType.BOTH, MatchMode.EXACT)
        assert cmd.index("--") < cmd.index("-foo")

    def test_single_word_no_full_path(self):
        cmd = _build_fd_cmd(_make_prefs(), "budget", SearchType.BOTH, MatchMode.EXACT)
        assert "--full-path" not in cmd

    def test_multi_word_full_path_and_and(self):
        cmd = _build_fd_cmd(_make_prefs(), "report march", SearchType.BOTH, MatchMode.EXACT)
        assert "--full-path" in cmd
        assert "--and" in cmd
        assert "march" in cmd
        assert "report" in cmd

    def test_files_only(self):
        cmd = _build_fd_cmd(_make_prefs(), "x", SearchType.FILES, MatchMode.EXACT)
        assert cmd[cmd.index("--type") + 1] == "f"

    def test_dirs_only(self):
        cmd = _build_fd_cmd(_make_prefs(), "x", SearchType.DIRS, MatchMode.EXACT)
        assert cmd[cmd.index("--type") + 1] == "d"

    def test_hidden(self):
        assert "--hidden" in _build_fd_cmd(_make_prefs(allow_hidden=True), "x", SearchType.BOTH, MatchMode.EXACT)

    def test_no_hidden_by_default(self):
        assert "--hidden" not in _build_fd_cmd(_make_prefs(), "x", SearchType.BOTH, MatchMode.EXACT)

    def test_follow_symlinks(self):
        assert "--follow" in _build_fd_cmd(_make_prefs(follow_symlinks=True), "x", SearchType.BOTH, MatchMode.EXACT)

    def test_ignore_file(self):
        cmd = _build_fd_cmd(_make_prefs(ignore_file=Path("/tmp/.findignore")), "x", SearchType.BOTH, MatchMode.EXACT)
        assert "--ignore-file" in cmd
        assert str(Path("/tmp/.findignore")) in cmd

    def test_multiple_base_dirs_after_separator(self):
        cmd = _build_fd_cmd(_make_prefs(base_dir=[Path("/tmp"), Path("/var/tmp")]), "x", SearchType.BOTH, MatchMode.EXACT)
        sep = cmd.index("--")
        assert cmd.index("/tmp") > sep
        assert cmd.index("/var/tmp") > sep

    def test_fuzzy_uses_dot_and_no_fixed_strings(self):
        cmd = _build_fd_cmd(_make_prefs(), "budget", SearchType.BOTH, MatchMode.FUZZY)
        assert "." in cmd
        assert "budget" not in cmd
        assert "--fixed-strings" not in cmd

    def test_fuzzy_caps_candidates(self):
        cmd = _build_fd_cmd(_make_prefs(result_limit=15), "budget", SearchType.BOTH, MatchMode.FUZZY)
        assert int(cmd[cmd.index("--max-results") + 1]) >= 5000


class TestRankExact:
    def test_name_hit_beats_path_only_hit(self):
        paths = ["/data/report/notes.txt", "/data/march/report.pdf"]
        assert _rank_exact(paths, "report")[0] == "/data/march/report.pdf"

    def test_more_name_hits_rank_first(self):
        paths = ["/data/march/report.txt", "/data/x/march-report.txt"]
        assert _rank_exact(paths, "report march")[0] == "/data/x/march-report.txt"

    def test_order_is_stable_regardless_of_input_order(self):
        paths = ["/a/budget.txt", "/b/budget-2024.txt", "/c/old/budget.txt"]
        assert _rank_exact(list(paths), "budget") == _rank_exact(list(reversed(paths)), "budget")

    def test_shorter_path_breaks_ties(self):
        paths = ["/a/b/c/report.txt", "/a/report.txt"]
        assert _rank_exact(paths, "report")[0] == "/a/report.txt"

    def test_empty_query_returns_unchanged(self):
        paths = ["/z.txt", "/a.txt"]
        assert _rank_exact(paths, "   ") == paths


class TestReadUntilLimit:
    def test_stops_at_limit(self):
        proc = _producer("import sys\nfor i in range(100): sys.stdout.buffer.write(b'line%d\\n' % i)\nsys.stdout.flush()")
        try:
            out = _read_until_limit(proc.stdout, 3, 5.0)
        finally:
            proc.kill(); proc.wait(); proc.stdout.close()
        assert out == ["line0", "line1", "line2"]

    def test_stops_at_eof(self):
        proc = _producer("import sys; sys.stdout.buffer.write(b'alpha\\nbeta\\n'); sys.stdout.flush()")
        try:
            out = _read_until_limit(proc.stdout, 10, 5.0)
        finally:
            proc.kill(); proc.wait(); proc.stdout.close()
        assert out == ["alpha", "beta"]

    def test_does_not_stop_on_idle_gap(self):
        # Regression: the old reader bailed on a short silence and dropped
        # everything fd emitted afterwards. A gap is not EOF.
        proc = _producer(
            "import sys, time\n"
            "w = sys.stdout.buffer\n"
            "w.write(b'first\\n'); w.flush()\n"
            "time.sleep(1.0)\n"
            "w.write(b'second\\nthird\\n'); w.flush()\n"
        )
        start = time.monotonic()
        try:
            out = _read_until_limit(proc.stdout, 10, 5.0)
        finally:
            proc.kill(); proc.wait(); proc.stdout.close()
        elapsed = time.monotonic() - start
        assert out == ["first", "second", "third"]
        assert elapsed >= 0.9

    def test_honours_time_ceiling(self):
        proc = _producer("import time; time.sleep(10)")
        start = time.monotonic()
        try:
            out = _read_until_limit(proc.stdout, 10, 0.4)
        finally:
            proc.kill(); proc.wait(); proc.stdout.close()
        elapsed = time.monotonic() - start
        assert out == []
        assert 0.3 <= elapsed < 1.5

    def test_survives_non_utf8_output(self):
        proc = _producer("import sys; sys.stdout.buffer.write(b'\\xff\\xfe\\n'); sys.stdout.flush()")
        try:
            out = _read_until_limit(proc.stdout, 10, 5.0)
        finally:
            proc.kill(); proc.wait(); proc.stdout.close()
        assert out == [os.fsdecode(b"\xff\xfe")]


class TestSearch:
    def test_returns_string_paths(self, tmp_path):
        (tmp_path / "budget.txt").write_text("x")
        results = search(_make_prefs(base_dir=tmp_path), "budget", SearchType.BOTH, MatchMode.EXACT)
        assert results and all(isinstance(r, str) for r in results)

    def test_respects_result_limit(self, tmp_path):
        for i in range(10):
            (tmp_path / f"report-{i}.txt").write_text("x")
        results = search(_make_prefs(base_dir=tmp_path, result_limit=3), "report", SearchType.FILES, MatchMode.EXACT)
        assert len(results) == 3

    def test_multi_word_matches_across_path(self, tmp_path):
        (tmp_path / "march").mkdir()
        (tmp_path / "march" / "quarterly-report.pdf").write_text("x")
        (tmp_path / "other").mkdir()
        (tmp_path / "other" / "notes.txt").write_text("x")
        results = search(_make_prefs(base_dir=tmp_path), "report march", SearchType.FILES, MatchMode.EXACT)
        assert any("quarterly-report.pdf" in r for r in results)
        assert all("notes.txt" not in r for r in results)

    def test_dirs_only(self, tmp_path):
        (tmp_path / "budget").mkdir()
        (tmp_path / "budget.txt").write_text("x")
        results = search(_make_prefs(base_dir=tmp_path), "budget", SearchType.DIRS, MatchMode.EXACT)
        assert any(r.endswith("/budget") for r in results)
        assert all(not r.endswith("budget.txt") for r in results)

    def test_fuzzy_returns_list(self, tmp_path):
        (tmp_path / "budget.txt").write_text("x")
        results = search(_make_prefs(base_dir=tmp_path), "budget", SearchType.BOTH, MatchMode.FUZZY)
        assert isinstance(results, list)
