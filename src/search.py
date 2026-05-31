from __future__ import annotations

import logging
import os
import select
import shutil
import subprocess
import tempfile
import time

from src.enums import MatchMode, SearchType
from src.preferences import FindPreferences

logger = logging.getLogger(__name__)

MIN_QUERY_LENGTH = 1

# Fallback ceiling for callers that do not pass one (tests, direct use). The
# live extension always passes the user's search_timeout preference, which
# defaults to the same value.
DEFAULT_TIMEOUT = 5.0

# fd's walk order is non-deterministic, so --max-results returns an arbitrary
# subset, not the best one. Collecting a larger pool and ranking it means the
# shown results are the best of many candidates and stay stable between runs.
# The pool is capped because ranking past a few hundred adds nothing a user
# would notice.
_CANDIDATE_POOL_FACTOR = 20
_CANDIDATE_POOL_MAX = 500


class SearchError(Exception):
    """Raised when the underlying search subprocess fails to start or errors out."""


def resolve_fd_binary() -> str | None:
    return "fd" if shutil.which("fd") else ("fdfind" if shutil.which("fdfind") else None)


def _candidate_pool(result_limit: int) -> int:
    return min(result_limit * _CANDIDATE_POOL_FACTOR, _CANDIDATE_POOL_MAX)


def _decode_path(raw: bytes) -> str:
    """Decode one fd output line into a path.

    os.fsdecode (surrogateescape) lets a non-UTF8 filename round-trip instead of
    crashing the search. fd marks directories with a trailing slash, so drop it:
    a path should not depend on whether it is a directory, and the slash would
    otherwise pad a directory's length and skew the relevance ranking.
    """
    return os.fsdecode(raw).rstrip("/") or "/"


def _exact_pattern_args(query: str, max_results: int) -> list[str]:
    """Build the pattern arguments for an exact fd search.

    A single word matches filenames. Two or more whitespace-separated words must
    each appear somewhere in the full path, in any order, so "report march"
    finds a "quarterly-report.pdf" inside a "march" folder: one word hits the
    filename, the other a parent directory. Matching the full path is what makes
    that cross-component match possible; keeping a single word filename-only is
    deliberate, because full-path matching on one common word like "report"
    would drag in every file whose ancestor path happens to contain it.

    Each word is a literal (--fixed-strings) so . ? * match as typed. The first
    word is fd's positional pattern and the rest become --and patterns, fd's
    native "all of these must also match". A trailing -- ends the options so a
    query starting with a dash is treated as a pattern, never as an fd flag such
    as --exec.
    """
    words = query.split() or [query]
    args: list[str] = []
    if len(words) > 1:
        args.append("--full-path")
    args += ["--fixed-strings", "--max-results", str(max_results)]
    for word in words[1:]:
        args += ["--and", word]
    args += ["--", words[0]]
    return args


def _build_fd_cmd(
    preferences: FindPreferences,
    query: str,
    search_type: SearchType,
    match_mode: MatchMode,
) -> list[str]:
    fd_bin = resolve_fd_binary() or "fd"

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
        cmd += _exact_pattern_args(query, _candidate_pool(preferences.result_limit))
    else:
        # Fuzzy ranks in fzf, so fd just lists candidates. Cap them so a broad
        # search doesn't crawl the whole filesystem before fzf gets to filter.
        cap = max(preferences.result_limit * 500, 5000)
        cmd += ["--max-results", str(cap), "--", "."]

    # Search roots are positionals, so they sit after the -- alongside the
    # pattern; fd accepts several.
    cmd += [str(d) for d in preferences.base_dir]

    return cmd


def _kill_proc(proc: subprocess.Popen[bytes]) -> None:
    if proc.stdout:
        try:
            proc.stdout.close()
        except (OSError, ValueError):
            # Already closed (the fuzzy pipeline hands the read end to fzf) or
            # the pipe broke; neither is worth surfacing, but don't swallow it
            # blind.
            logger.debug("Closing subprocess stdout failed", exc_info=True)
    if proc.poll() is None:
        proc.kill()
    proc.wait()


def _read_until_limit(stdout: object, limit: int, timeout: float) -> list[str]:
    """Collect up to ``limit`` lines, stopping on EOF or the ``timeout`` ceiling.

    There is no idle-gap early stop on purpose. fd walks each root directory by
    directory and routinely falls silent for seconds while crossing a large
    match-free subtree, so a quiet gap means "still walking", not "finished";
    bailing on it silently dropped real matches. The only stop conditions are
    enough results, fd closing the pipe (EOF), or the ceiling.

    Reading raw bytes and splitting on newlines (rather than readline on a text
    stream) does two things: it keeps the ceiling a hard guarantee even if a
    line arrives in pieces, and it survives filenames that are not valid UTF-8
    (common on external drives) by round-tripping them through os.fsdecode.
    """
    fileno = stdout.fileno()  # type: ignore[attr-defined]
    results: list[str] = []
    buf = bytearray()
    start = time.monotonic()

    while len(results) < limit:
        remaining = timeout - (time.monotonic() - start)
        if remaining <= 0:
            break  # ceiling: return what we have rather than hang the launcher

        ready, _, _ = select.select([fileno], [], [], remaining)
        if not ready:
            break  # ceiling reached with no further output

        chunk = os.read(fileno, 65536)
        if not chunk:
            if buf and len(results) < limit:  # final line with no trailing newline
                tail = _decode_path(bytes(buf))
                if tail:
                    results.append(tail)
            break  # EOF: fd finished walking on its own

        buf += chunk
        while len(results) < limit:
            newline = buf.find(b"\n")
            if newline < 0:
                break
            line = bytes(buf[:newline])
            del buf[: newline + 1]
            if line:
                results.append(_decode_path(line))

    return results


def search(
    preferences: FindPreferences,
    query: str,
    search_type: SearchType,
    match_mode: MatchMode,
) -> list[str]:
    fd_cmd = _build_fd_cmd(preferences, query, search_type, match_mode)

    logger.debug("Running: %s", fd_cmd)

    if match_mode == MatchMode.FUZZY:
        # fzf already orders by match score, so leave its order untouched.
        return _search_fuzzy(fd_cmd, query, preferences.result_limit, preferences.search_timeout)

    pool = _candidate_pool(preferences.result_limit)
    raw = _search_exact(fd_cmd, pool, preferences.search_timeout)
    return _rank_exact(raw, query)[: preferences.result_limit]


def _rank_exact(paths: list[str], query: str) -> list[str]:
    """Order exact results by relevance instead of fd's walk order.

    A file whose name contains more of the query words ranks above one that
    matches only through a parent folder, so for "report march" a file named
    "march-report.pdf" beats a stray file sitting under some other "report"
    folder. Ties break on full-path word count, then shorter path, then
    alphabetically, all deterministic so repeat searches don't reshuffle.
    """
    words = [w for w in query.lower().split() if w]
    if not words:
        return paths

    def key(path: str) -> tuple[int, int, int, str]:
        name = os.path.basename(path).lower()
        full = path.lower()
        name_hits = sum(1 for w in words if w in name)
        path_hits = sum(1 for w in words if w in full)
        return (-name_hits, -path_hits, len(path), full)

    return sorted(paths, key=key)


def _search_exact(fd_cmd: list[str], limit: int, timeout: float = DEFAULT_TIMEOUT) -> list[str]:
    # stderr goes to a real file, not a pipe: fd is near-silent by default, but
    # if it ever warns in volume an undrained pipe would fill and block fd's
    # writes, stalling stdout until the ceiling. A file never fills.
    with tempfile.TemporaryFile() as stderr_file:
        try:
            proc = subprocess.Popen(
                fd_cmd, stdout=subprocess.PIPE, stderr=stderr_file, bufsize=0
            )
        except OSError as exc:
            raise SearchError(f"Could not start fd: {exc}") from exc

        assert proc.stdout is not None
        try:
            results = _read_until_limit(proc.stdout, limit, timeout)
        finally:
            _kill_proc(proc)

        # fd exits 0 even when nothing matched, and negative when we killed it at
        # the ceiling; only a code above 1 is a genuine fd error worth surfacing.
        if not results and proc.returncode is not None and proc.returncode > 1:
            stderr_file.seek(0)
            lines = stderr_file.read().decode("utf-8", "replace").strip().splitlines()
            detail = lines[0] if lines else f"exit {proc.returncode}"
            raise SearchError(f"Search failed: {detail}")

        return results


def _search_fuzzy(
    fd_cmd: list[str], query: str, limit: int, timeout: float = DEFAULT_TIMEOUT
) -> list[str]:
    fzf_bin = shutil.which("fzf") or "fzf"
    # Joined --filter= so a query starting with a dash is the filter value, not
    # an unknown fzf option.
    fzf_cmd = [fzf_bin, f"--filter={query}"]

    try:
        fd_proc = subprocess.Popen(fd_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except OSError as exc:
        raise SearchError(f"Could not start fd: {exc}") from exc

    try:
        try:
            fzf_proc = subprocess.Popen(
                fzf_cmd, stdin=fd_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
            )
        except OSError as exc:
            raise SearchError(f"Could not start fzf: {exc}") from exc

        if fd_proc.stdout:
            fd_proc.stdout.close()  # fzf owns the read end; lets fd see SIGPIPE if fzf exits first

        try:
            stdout, _ = fzf_proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Kill fd first so fzf sees EOF on stdin and flushes the matches it has.
            _kill_proc(fd_proc)
            try:
                stdout, _ = fzf_proc.communicate(timeout=1)
            except subprocess.TimeoutExpired:
                fzf_proc.kill()
                stdout, _ = fzf_proc.communicate()
    finally:
        _kill_proc(fd_proc)

    paths = [_decode_path(line) for line in (stdout or b"").split(b"\n") if line]
    return paths[:limit]
