from __future__ import annotations

import shlex
from unittest.mock import patch

from src.results import _get_system_icon, _get_terminal_action


def _script(action) -> str:
    # RunScriptAction(script) -> {"type": ..., "data": [script, ""]}
    return action["data"][0]


def _effect_type(action) -> str:
    return action.get("type", "")


class TestGetSystemIcon:
    def test_real_file(self, tmp_path):
        f = tmp_path / "thing.txt"
        f.write_text("x")
        icon = _get_system_icon(str(f))
        assert isinstance(icon, str) and icon

    def test_directory(self, tmp_path):
        icon = _get_system_icon(str(tmp_path))
        assert isinstance(icon, str) and icon

    def test_nonexistent_path_falls_back(self):
        icon = _get_system_icon("/no/such/path/file.xyz")
        assert isinstance(icon, str) and icon


class TestGetTerminalAction:
    def test_none_detected_does_nothing(self, tmp_path):
        with patch("src.results._detect_terminal", return_value=None):
            action = _get_terminal_action(None, str(tmp_path))
        assert _effect_type(action) == "effect:do_nothing"

    def test_known_konsole(self, tmp_path):
        script = _script(_get_terminal_action("konsole", str(tmp_path)))
        assert "konsole" in script
        assert "--workdir" in script
        assert str(tmp_path) in script

    def test_known_kitty(self, tmp_path):
        script = _script(_get_terminal_action("kitty", str(tmp_path)))
        assert "kitty" in script and "--directory" in script

    def test_ptyxis_uses_new_window(self, tmp_path):
        script = _script(_get_terminal_action("ptyxis", str(tmp_path)))
        assert "ptyxis" in script
        assert "--new-window" in script
        assert "--working-directory" in script

    def test_custom_template(self, tmp_path):
        script = _script(_get_terminal_action("myterm --cd {} --title find", str(tmp_path)))
        assert "myterm" in script and "--cd" in script and "--title" in script and "find" in script
        assert str(tmp_path) in script

    def test_unknown_terminal_passes_dir(self, tmp_path):
        script = _script(_get_terminal_action("mystery-term", str(tmp_path)))
        assert "mystery-term" in script and str(tmp_path) in script

    def test_file_passes_parent_dir(self, tmp_path):
        f = tmp_path / "hello.txt"
        f.write_text("x")
        script = _script(_get_terminal_action("kitty", str(f)))
        assert str(tmp_path) in script
        assert str(f) not in script

    def test_hostile_dirname_is_quoted(self, tmp_path):
        evil = tmp_path / "a; touch pwned"
        evil.mkdir()
        script = _script(_get_terminal_action("kitty", str(evil)))
        # The directory must appear shell-quoted so its metacharacters stay inert.
        assert shlex.quote(str(evil)) in script
        assert "; touch pwned" not in script.replace(shlex.quote(str(evil)), "")
