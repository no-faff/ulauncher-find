from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from src.enums import AltEnterAction

logger = logging.getLogger(__name__)

# Ulauncher 6 beta does not deliver PreferencesUpdateEvent in v2 compatibility
# mode, so a saved preference is not seen until the launcher restarts. Reading
# the file on each query sidesteps that. Revisit once Ulauncher 6 is stable and
# the event fires reliably.
PREFS_FILE = Path.home() / ".config" / "ulauncher" / "ext_preferences" / "com.github.no-faff.ulauncher-find.json"

# Every preference is stored as a string, so this also documents the expected
# keys and gives load_raw_preferences a base to merge onto: a partial or absent
# file then cannot raise KeyError downstream, only a wrong value can.
_DEFAULT_RAW: dict[str, str] = {
    "alt_enter_action": "0",
    "allow_hidden": "0",
    "follow_symlinks": "0",
    "result_limit": "15",
    "search_timeout": "5",
    "base_dir": "~",
    "ignore_file": "",
    "terminal_cmd": "",
}


@dataclass(frozen=True)
class FindPreferences:
    alt_enter_action: AltEnterAction
    allow_hidden: bool
    follow_symlinks: bool
    result_limit: int
    search_timeout: float
    base_dir: list[Path]
    ignore_file: Path | None
    terminal_cmd: str | None


def _raw_value(raw: dict[str, str], key: str) -> str:
    """Return a preference string, treating a blank field as unset.

    Ulauncher hands back an empty string for a cleared input, which should mean
    "use the default", not crash int()/float(). A non-empty but unparseable
    value is left to raise so the caller can tell the user (see main.py).
    """
    value = raw.get(key, _DEFAULT_RAW[key]).strip()
    return value or _DEFAULT_RAW[key]


def _expand_path(path: str) -> Path | None:
    return Path(path).expanduser() if path else None


def _parse_base_dirs(raw: str) -> list[Path]:
    dirs = [_expand_path(part.strip()) for part in raw.split(",")]
    return [d for d in dirs if d is not None] or [Path.home()]


def get_preferences(raw: dict[str, str]) -> FindPreferences:
    """Parse the raw string preferences into typed values.

    Every value arrives as text (booleans as "0"/"1", the alt-enter enum as a
    stringified int). A genuinely malformed number raises ValueError here on
    purpose; main.py converts that into a visible message rather than letting it
    kill the query thread silently.
    """
    return FindPreferences(
        alt_enter_action=AltEnterAction(int(_raw_value(raw, "alt_enter_action"))),
        allow_hidden=bool(int(_raw_value(raw, "allow_hidden"))),
        follow_symlinks=bool(int(_raw_value(raw, "follow_symlinks"))),
        result_limit=int(_raw_value(raw, "result_limit")),
        search_timeout=float(_raw_value(raw, "search_timeout")),
        base_dir=_parse_base_dirs(raw.get("base_dir", "") or _DEFAULT_RAW["base_dir"]),
        ignore_file=_expand_path(raw.get("ignore_file", "")),
        terminal_cmd=raw.get("terminal_cmd", "").strip() or None,
    )


def load_raw_preferences() -> dict[str, str]:
    """Read the raw preferences dict from disk, falling back to defaults.

    Ulauncher 6 beta keeps the trigger keywords under a separate ``triggers``
    section, so they are flattened back in alongside the plain preferences to
    keep the keyword lookup in main.py a single dict access.
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


def validate_preferences(preferences: FindPreferences) -> list[str]:
    errors = []

    for d in preferences.base_dir:
        if not d.is_dir():
            errors.append(f"Base directory '{d}' does not exist.")

    if preferences.ignore_file and not preferences.ignore_file.is_file():
        errors.append(f"Ignore file '{preferences.ignore_file}' does not exist.")

    if preferences.result_limit <= 0:
        errors.append("Result limit must be greater than 0.")

    if preferences.search_timeout <= 0:
        errors.append("Search time limit must be greater than 0.")

    return errors
