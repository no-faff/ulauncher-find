from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from src.enums import AltEnterAction

logger = logging.getLogger(__name__)

# Workaround for Ulauncher 6 beta: PreferencesUpdateEvent doesn't fire in
# API v2 compat mode, so saved preferences aren't picked up until restart.
# Reading from disk on each query fixes this. Can likely be removed once
# Ulauncher 6 is finalised.
PREFS_FILE = Path.home() / ".config" / "ulauncher" / "ext_preferences" / "com.github.no-faff.ulauncher-find.json"

_DEFAULT_RAW: dict[str, str] = {
    "alt_enter_action": "0",
    "allow_hidden": "0",
    "follow_symlinks": "0",
    "result_limit": "15",
    "base_dir": "~",
    "ignore_file": "",
    "terminal_cmd": "",
}


@dataclass
class FindPreferences:
    alt_enter_action: AltEnterAction
    allow_hidden: bool
    follow_symlinks: bool
    result_limit: int
    base_dir: list[Path]
    ignore_file: Path | None
    terminal_cmd: str | None


def _expand_path(path: str) -> Path | None:
    return Path(path).expanduser() if path else None


def _parse_base_dirs(raw: str) -> list[Path]:
    """Parse a comma-separated list of base directories."""
    dirs = [_expand_path(part.strip()) for part in raw.split(",")]
    return [d for d in dirs if d is not None] or [Path.home()]


def get_preferences(raw: dict[str, str]) -> FindPreferences:
    return FindPreferences(
        alt_enter_action=AltEnterAction(int(raw["alt_enter_action"])),
        allow_hidden=bool(int(raw["allow_hidden"])),
        follow_symlinks=bool(int(raw["follow_symlinks"])),
        result_limit=int(raw["result_limit"]),
        base_dir=_parse_base_dirs(raw["base_dir"]),
        ignore_file=_expand_path(raw.get("ignore_file", "")),
        terminal_cmd=raw.get("terminal_cmd", "").strip() or None,
    )


def load_raw_preferences() -> dict[str, str]:
    """Read the raw preferences dict from disk, falling back to defaults.

    Ulauncher 6 beta stores trigger keywords under a separate ``triggers``
    section, so we flatten them back into the returned dict for
    straightforward keyword lookups.
    """
    try:
        data = json.loads(PREFS_FILE.read_text())
        raw: dict[str, str] = dict(_DEFAULT_RAW)
        raw.update(data.get("preferences", {}))
        for kw_id, trigger in (data.get("triggers") or {}).items():
            if isinstance(trigger, dict) and "keyword" in trigger:
                raw[kw_id] = trigger["keyword"]
        return raw
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read preferences file, using defaults", exc_info=True)
        return dict(_DEFAULT_RAW)


def load_preferences() -> FindPreferences:
    """Read preferences directly from disk to ensure saved values are used."""
    return get_preferences(load_raw_preferences())


def validate_preferences(preferences: FindPreferences) -> list[str]:
    errors = []

    for d in preferences.base_dir:
        if not d.is_dir():
            errors.append(f"Base directory '{d}' does not exist.")

    if preferences.ignore_file and not preferences.ignore_file.is_file():
        errors.append(f"Ignore file '{preferences.ignore_file}' does not exist.")

    if preferences.result_limit <= 0:
        errors.append("Result limit must be greater than 0.")

    return errors
