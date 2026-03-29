from __future__ import annotations

from pathlib import Path

from src.results import _get_system_icon


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
