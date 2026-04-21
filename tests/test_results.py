from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from src.results import _get_system_icon, _get_terminal_action


def _action_type(action: dict) -> str:
    return action.get("type", "")


def _run_script_parts(action: dict) -> tuple[str, list[str]]:
    # RunScriptAction returns {"type": ..., "data": [cmd, [args]]}
    cmd, args = action["data"]
    return cmd, list(args)


class TestGetSystemIcon:
    def test_returns_string_path_for_real_file(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello")
        icon_path = _get_system_icon(str(test_file))
        assert icon_path is not None
        assert isinstance(icon_path, str)

    def test_returns_string_path_for_directory(self, tmp_path):
        icon_path = _get_system_icon(str(tmp_path))
        assert icon_path is not None
        assert isinstance(icon_path, str)

    def test_returns_fallback_for_nonexistent_path(self):
        icon_path = _get_system_icon("/nonexistent/path/file.xyz")
        assert icon_path is not None
        assert isinstance(icon_path, str)


class TestGetTerminalAction:
    def test_no_terminal_and_none_detected(self, tmp_path):
        with patch("src.results._detect_terminal", return_value=None):
            action = _get_terminal_action(None, str(tmp_path))
        assert _action_type(action) == "effect:do_nothing"

    def test_known_terminal_kitty(self, tmp_path):
        action = _get_terminal_action("kitty", str(tmp_path))
        cmd, args = _run_script_parts(action)
        assert cmd == "kitty"
        assert "--directory" in args
        assert str(tmp_path) in args

    def test_known_terminal_konsole_uses_workdir(self, tmp_path):
        action = _get_terminal_action("konsole", str(tmp_path))
        cmd, args = _run_script_parts(action)
        assert cmd == "konsole"
        assert "--workdir" in args
        assert str(tmp_path) in args

    def test_custom_template_with_placeholder(self, tmp_path):
        action = _get_terminal_action("myterm --cd {} --title find", str(tmp_path))
        cmd, args = _run_script_parts(action)
        assert cmd == "myterm"
        assert "--cd" in args
        assert str(tmp_path) in args
        assert "--title" in args

    def test_unknown_terminal_without_placeholder_passes_dir(self, tmp_path):
        action = _get_terminal_action("mystery-term", str(tmp_path))
        cmd, args = _run_script_parts(action)
        assert cmd == "mystery-term"
        assert args == [str(tmp_path)]

    def test_passes_parent_dir_for_file(self, tmp_path):
        test_file = tmp_path / "hello.txt"
        test_file.write_text("x")
        action = _get_terminal_action("kitty", str(test_file))
        _, args = _run_script_parts(action)
        assert str(tmp_path) in args
        assert str(test_file) not in args
