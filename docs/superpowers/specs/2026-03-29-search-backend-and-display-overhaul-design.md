# Search backend and display overhaul

## Summary

Replace the plocate search backend with fd + fzf, add system icons via
GIO/Gtk, and switch to a two-line result display (filename + directory).

## Motivation

- plocate depends on a daily updatedb cron job. Files created or downloaded
  since the last run don't appear. This is a dealbreaker for a file finder.
- fd walks the filesystem live, so results are always current.
- fzf adds fuzzy matching: typing "budg24" finds "Budget_2024.xlsx".
- System icons make results visually distinct. A PDF looks different from
  a spreadsheet, which looks different from a video file.
- Two-line display (filename bold, directory underneath) is easier to scan
  than a single line showing the full path.

## Changes

### 1. Search backend (search.py)

Replace the `locate` subprocess call with an `fd | fzf` pipeline.

**How it works:**
- `fd` lists all files from the base directory
- Its stdout is piped into `fzf --filter <query>` which does fuzzy matching
  and scoring
- Results are truncated to the configured limit

**fd flags built from preferences:**
- `--type f` (files only), `--type d` (dirs only), or neither (both)
- `--hidden` when allow_hidden is enabled
- `--follow` when follow_symlinks is enabled
- `--ignore-file <path>` when ignore_file is set (this preference currently
  does nothing with plocate, so this is a free win)
- `--color never` to avoid ANSI codes in output
- `-a` for absolute paths

**fzf flags:**
- `--filter <query>` for non-interactive fuzzy matching

**Error handling:**
- Check for `fd` and `fzf` binaries via `shutil.which` before searching
- Keep the existing 5-second timeout on the subprocess pipeline
- Handle the case where fd or fzf returns non-zero (empty results, not a crash)

**What's removed:**
- The `locate` command and all its flags
- The `_is_dir()` helper that stat-checks each result (fd handles type
  filtering natively via `--type`)
- Post-search filtering by base_dir (fd searches from base_dir directly)
- Post-search filtering by search type (fd's `--type` flag handles this)

The search function becomes simpler because fd handles filtering that
plocate couldn't.

### 2. System icons (results.py)

Add a function that resolves the system icon for a given file path using
GIO and Gtk.

**How it works:**
- Create a `Gio.File` for the path
- Query its `standard::icon` attribute
- Look up the icon in the current Gtk icon theme at 48px
- Return the icon's filesystem path (which Ulauncher can use directly)
- If the lookup fails for any reason, the system theme's generic icons
  (`text-x-generic` for files, `folder` for directories) are always
  available as a natural fallback from GIO itself

**Imports needed:**
```python
import gi
gi.require_version('Gio', '2.0')
gi.require_version('Gtk', '3.0')
from gi.repository import Gio, Gtk
```

These are already available in the Ulauncher runtime (Ulauncher itself
uses Gtk).

**Performance:** Measured at 0.13ms per icon on this system. At 100
results that's 13ms total.

### 3. Result display (results.py)

Switch from `ExtensionSmallResultItem` (single line, full path) to
`ExtensionResultItem` (two lines).

- **name**: filename only (e.g. "Budget_2024.xlsx")
- **description**: parent directory path (e.g. "/home/fred/Documents")
- **icon**: system icon path from the GIO lookup

### 4. Dependency check (main.py)

Change the startup check from `shutil.which("locate")` to check for
both `fd` and `fzf`. Show a clear error message naming whichever
binary is missing.

### 5. Manifest changes (manifest.json)

- Change `base_dir` default from `/` to `~`
- Update the extension description to reflect the new capabilities

## What stays the same

- All preferences and their IDs (no breaking changes for existing users)
- The three keywords (fd, ff, fdir)
- Alt+enter actions (open folder, open terminal, copy path)
- Terminal detection and command logic
- Preference validation and the typed dataclass
- The preferences-from-disk workaround for Ulauncher 6
- Query debounce (already set to 0.5s)
- MIN_QUERY_LENGTH = 3

## Dependencies

**New runtime requirements:**
- `fd` (sharkdp/fd, packaged as `fd-find` on most distros)
- `fzf` (junegunn/fzf)

**Removed runtime requirement:**
- `plocate`

Both fd and fzf are widely packaged. On Fedora: `sudo dnf install fd-find fzf`.
On Ubuntu/Debian: `sudo apt install fd-find fzf` (binary may be called
`fdfind` on Debian/Ubuntu).

**Debian/Ubuntu note:** The fd binary is called `fdfind` on Debian-based
systems due to a naming conflict. The code must check for both `fd` and
`fdfind` and use whichever is available.

## Files touched

| File | Change |
|---|---|
| `src/search.py` | Rewrite: fd + fzf pipeline replaces locate |
| `src/results.py` | Add GIO icon lookup, switch to ExtensionResultItem with name/description |
| `main.py` | Update dependency check from locate to fd + fzf |
| `manifest.json` | Change base_dir default to ~, update description |

No new files created.

## Risks and mitigations

**fd speed from /**: Benchmarked on this system. With `--max-results`,
fd bails out early. Worst case (hidden + no-ignore) was 176ms from /.
Normal searches under 20ms. Acceptable.

**Debian fd/fdfind naming**: Must check for both binary names. Use
`shutil.which("fd") or shutil.which("fdfind")`.

**GIO icon lookup on non-existent files**: fd only returns files that
exist at search time, so this shouldn't happen. But if a file is deleted
between search and display, the GIO lookup will fail gracefully (returns
a generic icon).

**Gtk version**: The code uses Gtk 3.0. Ulauncher 6 currently uses Gtk 3.
If Ulauncher moves to Gtk 4, the icon lookup imports would need updating,
but that's a future concern and would affect Ulauncher's own API too.
