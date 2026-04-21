from __future__ import annotations

import logging
import select
import shutil
import subprocess
import time

from src.enums import MatchMode, SearchType
from src.preferences import FindPreferences

logger = logging.getLogger(__name__)

MIN_QUERY_LENGTH = 1

# Absolute ceiling. fd is killed at this point regardless of state.
HARD_TIMEOUT = 5.0

# Timing heuristics for when to stop reading fd output. The whole thing is a
# tradeoff: stop too early and you miss real matches that fd was about to
# emit; stop too late and every search feels sluggish.
#
# - Until the first match arrives, wait the full HARD_TIMEOUT so cold-cache
#   walks of /mnt/... aren't cut short.
# - After the first match, give fd a minimum settling window to emit any
#   siblings or descendants it's in the middle of walking. fd's parallel
#   threads often emit a parent, descend, then emit children a second or
#   two later - bailing at 500ms in that gap loses most of the results.
# - After the settling window, if fd goes this long without a new match,
#   assume it's scanning empty subtrees and return what we have.
MIN_WAIT_AFTER_FIRST = 2.0
IDLE_WAIT = 0.5


class SearchError(Exception):
    """Raised when the underlying search subprocess fails to start or errors out."""


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

    # Match against the full path only when the query contains a space. That
    # way "crap j" still finds things under ".../crap journalism/..." but a
    # single word like "crap" matches filenames, not every grandchild of some
    # unrelated folder whose parent path happens to contain "crap".
    if match_mode == MatchMode.EXACT and " " in query:
        cmd.append("--full-path")

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
        # Literal substring match so characters like . ? * behave as typed
        cmd += ["--fixed-strings", "--max-results", str(preferences.result_limit)]
        cmd.append(query)
    else:
        # Fuzzy mode: cap fd candidates so it doesn't crawl the entire filesystem
        cmd += ["--max-results", str(max(preferences.result_limit * 500, 5000))]
        cmd.append(".")

    # fd accepts multiple search roots as trailing positional args
    cmd += [str(d) for d in preferences.base_dir]

    return cmd


def _line_buffered(cmd: list[str]) -> list[str]:
    """Prepend stdbuf -oL so the subprocess flushes each line as it's emitted.

    Without this, fd block-buffers its output when stdout is a pipe, meaning
    we can't see matches until fd completes or fills a 4 KiB buffer.
    """
    if shutil.which("stdbuf"):
        return ["stdbuf", "-oL"] + cmd
    return cmd


def _kill_proc(proc: subprocess.Popen) -> None:
    if proc.stdout:
        try:
            proc.stdout.close()
        except Exception:
            pass
    if proc.poll() is None:
        proc.kill()
    proc.wait()


def _stream_with_idle_timeout(proc: subprocess.Popen, limit: int) -> list[str]:
    """Read lines from proc.stdout until we hit the limit, the hard timeout,
    or an idle period with no new output. Returns whatever was collected."""
    assert proc.stdout is not None
    results: list[str] = []
    start = time.monotonic()
    first_match = None
    last_match = None

    while len(results) < limit:
        now = time.monotonic()
        elapsed = now - start
        if elapsed >= HARD_TIMEOUT:
            break

        if last_match is None:
            wait = HARD_TIMEOUT - elapsed
        else:
            since_first = now - first_match
            if since_first < MIN_WAIT_AFTER_FIRST:
                # Settling window: keep reading regardless of idle gaps.
                wait = min(MIN_WAIT_AFTER_FIRST - since_first, HARD_TIMEOUT - elapsed)
            else:
                idle_budget = IDLE_WAIT - (now - last_match)
                if idle_budget <= 0:
                    break
                wait = min(idle_budget, HARD_TIMEOUT - elapsed)

        ready, _, _ = select.select([proc.stdout], [], [], wait)
        if not ready:
            break

        line = proc.stdout.readline()
        if not line:
            break  # EOF: fd finished on its own
        line = line.rstrip("\n")
        if line:
            results.append(line)
            last_match = time.monotonic()
            if first_match is None:
                first_match = last_match

    return results


def search(
    preferences: FindPreferences,
    query: str,
    search_type: SearchType,
    match_mode: MatchMode,
) -> list[str]:
    fd_cmd = _line_buffered(_build_fd_cmd(preferences, query, search_type, match_mode))

    logger.debug("Running: %s", fd_cmd)

    if match_mode == MatchMode.FUZZY:
        return _search_fuzzy(fd_cmd, query, preferences.result_limit)
    return _search_exact(fd_cmd, preferences.result_limit)


def _search_exact(fd_cmd: list[str], limit: int) -> list[str]:
    try:
        proc = subprocess.Popen(
            fd_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1
        )
    except OSError as exc:
        raise SearchError(f"Could not start fd: {exc}") from exc

    try:
        results = _stream_with_idle_timeout(proc, limit)
    finally:
        _kill_proc(proc)

    # Only surface an error if fd failed immediately with no output. A killed
    # process (returncode < 0) is expected here and not an error.
    if not results and proc.returncode not in (None, 0, 1) and proc.returncode > 1:
        stderr = (proc.stderr.read() if proc.stderr else "") or ""
        detail = stderr.strip().splitlines()[0:1] or [f"exit {proc.returncode}"]
        raise SearchError(f"Search failed: {detail[0]}")

    return results


def _search_fuzzy(fd_cmd: list[str], query: str, limit: int) -> list[str]:
    fzf_bin = shutil.which("fzf") or "fzf"
    fzf_cmd = [fzf_bin, "--filter", query]

    try:
        fd_proc = subprocess.Popen(
            fd_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
    except OSError as exc:
        raise SearchError(f"Could not start fd: {exc}") from exc

    try:
        try:
            fzf_proc = subprocess.Popen(
                fzf_cmd,
                stdin=fd_proc.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        except OSError as exc:
            raise SearchError(f"Could not start fzf: {exc}") from exc

        if fd_proc.stdout:
            fd_proc.stdout.close()  # fzf owns the read end now

        try:
            stdout, _ = fzf_proc.communicate(timeout=HARD_TIMEOUT)
        except subprocess.TimeoutExpired:
            # Kill fd first so fzf sees EOF on stdin and flushes its matches
            _kill_proc(fd_proc)
            try:
                stdout, _ = fzf_proc.communicate(timeout=1)
            except subprocess.TimeoutExpired:
                fzf_proc.kill()
                stdout, _ = fzf_proc.communicate()
    finally:
        _kill_proc(fd_proc)

    paths = [p for p in (stdout or "").strip().splitlines() if p]
    return paths[:limit]
