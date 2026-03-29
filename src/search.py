from __future__ import annotations

import logging
import shutil
import subprocess

from src.enums import MatchMode, SearchType
from src.preferences import FindPreferences

logger = logging.getLogger(__name__)

MIN_QUERY_LENGTH = 1
TIMEOUT_SECONDS = 5


def _resolve_fd_binary() -> str | None:
    return "fd" if shutil.which("fd") else ("fdfind" if shutil.which("fdfind") else None)


def _build_fd_cmd(
    preferences: FindPreferences,
    query: str,
    search_type: SearchType,
    match_mode: MatchMode,
) -> list[str]:
    fd_bin = _resolve_fd_binary() or "fd"

    cmd: list[str] = [fd_bin, "-a", "--color", "never"]

    if search_type == SearchType.FILES:
        cmd += ["--type", "f"]
    elif search_type == SearchType.DIRS:
        cmd += ["--type", "d"]

    if preferences.allow_hidden:
        cmd.append("--hidden")

    if preferences.follow_symlinks:
        cmd.append("--follow")

    if preferences.ignore_file:
        cmd += ["--ignore-file", str(preferences.ignore_file)]

    if match_mode == MatchMode.EXACT:
        cmd += ["--max-results", str(preferences.result_limit)]
        cmd.append(query)
    else:
        # Fuzzy mode: cap fd candidates so it doesn't crawl the entire filesystem
        cmd += ["--max-results", str(max(preferences.result_limit * 500, 5000))]
        cmd.append(".")

    cmd.append(str(preferences.base_dir))

    return cmd


def search(
    preferences: FindPreferences,
    query: str,
    search_type: SearchType,
    match_mode: MatchMode,
) -> list[str]:
    fd_cmd = _build_fd_cmd(preferences, query, search_type, match_mode)

    logger.debug("Running: %s", fd_cmd)

    try:
        if match_mode == MatchMode.FUZZY:
            # Pipe fd output into fzf for fuzzy matching
            fd_proc = subprocess.Popen(
                fd_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
            )
            fzf_bin = shutil.which("fzf") or "fzf"
            fzf_cmd = [fzf_bin, "--filter", query]
            result = subprocess.run(
                fzf_cmd,
                stdin=fd_proc.stdout,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
            )
            fd_proc.stdout.close()
            fd_proc.wait()
        else:
            result = subprocess.run(
                fd_cmd,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
            )
    except subprocess.TimeoutExpired:
        logger.warning("Search timed out after %ss", TIMEOUT_SECONDS)
        return []

    # fd returns 1 when no results, fzf returns 1 when no match
    if result.returncode not in (0, 1):
        logger.error("Search failed: %s", result.stderr)
        return []

    paths = result.stdout.strip().splitlines()
    paths = [p for p in paths if p]

    return paths[:preferences.result_limit]
