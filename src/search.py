from __future__ import annotations

import logging
import subprocess

from src.enums import SearchType
from src.preferences import FindPreferences

logger = logging.getLogger(__name__)

MIN_QUERY_LENGTH = 3
TIMEOUT_SECONDS = 5


def search(
    preferences: FindPreferences, query: str, search_type: SearchType
) -> list[str]:
    cmd: list[str] = [
        "locate",
        "--ignore-case",
        "--basename",
        "--limit", str(preferences.result_limit),
        query,
    ]

    logger.debug("Running: %s", cmd)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        logger.warning("locate timed out after %ss", TIMEOUT_SECONDS)
        return []

    if result.returncode not in (0, 1):
        logger.error("locate failed: %s", result.stderr)
        return []

    paths = result.stdout.strip().splitlines()
    paths = [p for p in paths if p]

    # Filter by search type
    if search_type == SearchType.FILES:
        paths = [p for p in paths if not _is_dir(p)]
    elif search_type == SearchType.DIRS:
        paths = [p for p in paths if _is_dir(p)]

    # Filter by base directory if set
    base = str(preferences.base_dir)
    if base and base != "/":
        paths = [p for p in paths if p.startswith(base)]

    return paths[:preferences.result_limit]


def _is_dir(path: str) -> bool:
    from pathlib import Path
    try:
        return Path(path).is_dir()
    except (OSError, ValueError):
        return False
