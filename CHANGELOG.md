# Changelog

A full record of the changes to Find, grouped by type. Ulauncher installs the
extension straight from the repository, so each entry is dated by when the work
landed on the `main` branch, and the version tags mark the points published as
GitHub releases.

## 2026-06-01

A reliability pass on the search engine, with a full test suite behind it.

### Added

- Multi-word search. Two or more words narrow the results to paths where every
  word appears somewhere, in any order, so `ff budget wedding` finds a
  `honeymoon-budget.numbers` filed under a `Wedding` folder. A single word still
  matches the filename only, so a common word does not drag in every file under
  a folder that happens to share its name.
- Search time limit preference, default 5 seconds. A search that finds fewer
  results than the result limit keeps looking until this many seconds pass, then
  shows what it found. Lower is snappier; raise it to catch matches across large
  drives or separate partitions. A search that reaches the result limit still
  shows at once.
- A test suite covering the command builder, multi-word matching, relevance
  ranking, the streaming reader, the time limit, preference parsing, and the
  terminal action.

### Changed

- Exact results are ordered by relevance rather than the order `fd` happened to
  reach them. A file whose name matches more of the query words ranks above one
  that matches only through a parent folder, and the order is now identical from
  one repeat of a search to the next.
- The reader collects a larger pool of candidates and then ranks it, so the
  results shown are the best matches rather than whichever ones `fd` returned
  first.

### Fixed

- Searches no longer give up early and drop matches. The reader used to stop at
  the first lull in `fd`'s output; on a large or slow drive `fd` goes quiet for
  seconds while crossing an empty subtree, so a file that existed often never
  appeared and a different handful showed each run. It now reads until the
  result limit, `fd` finishing, or the time limit, with no early stop on a lull.
- A file whose name is not valid UTF-8, common on external or Windows-formatted
  drives, no longer aborts the search.
- A query beginning with a dash is searched for literally instead of being read
  as an `fd` option.
- "Open in terminal" works again. It was handing the launcher an argument in a
  shape it could not run, so nothing happened. A directory whose name contains
  shell characters is now passed safely. Added Ptyxis to the auto-detected
  terminals.
- A blank or non-numeric preference value (result limit, time limit) falls back
  to its default and reports a clear message, instead of silently breaking the
  next search.

### Internal

- Replaced the line-buffering subprocess wrapper, which had no effect on `fd`'s
  output, and read `fd`'s standard error through a temporary file so a flood of
  warnings cannot stall the search.
- Froze the preferences data class, renamed the `fd` binary resolver to a public
  name, and removed an unused preference loader.

### Documentation

- Rewrote the readme around the current behaviour, with example queries that
  match the screenshots, and replaced the single superseded screenshot with five
  current ones.

## 2026-05-23

### Internal

- Moved the private working-file ignore rules (editor notes, exports, scratch
  files) to a user-level global gitignore, so the repository's own `.gitignore`
  only carries rules that belong to the project.

## 2026-04-21

A large hardening and usability pass across search, preferences and results.

### Added

- Multiple base directories: search several comma-separated locations at once,
  walked together under one keyword.
- Terminal command supports a `{}` placeholder, so an unsupported terminal can
  still be used by giving its full command with the directory slot.

### Changed

- Results stream in as `fd` finds them rather than waiting for the whole walk to
  finish, so a narrow query with genuinely few matches no longer times out with
  "No results found". (This introduced an early-stop bug that was fixed on
  2026-06-01.)
- Multi-word queries matched against the full path, with a single word still
  matching the filename only. (Superseded on 2026-06-01 by all-words-in-any-order
  matching.)
- Exact matching is literal, so `.`, `?` and `*` behave as typed rather than as
  patterns.
- The system icon is resolved for each result rather than cached when the
  extension loads, so a change of icon theme is picked up without a restart.

### Fixed

- Real subprocess failures now surface as an error in the launcher instead of a
  silent empty result that read as "No results found".
- The `fd` process is cleaned up when `fzf` times out, so an abandoned fuzzy
  search leaves no orphaned processes behind.

### Internal

- Keyword lookups read the raw preferences from disk, flattening Ulauncher 6's
  separate triggers section, so the active keywords are always current.
- The icon lookup logs a failure at debug level instead of swallowing it
  silently, and the preferences read failure carries its traceback.

### Documentation

- Keyword display names in the preferences now show their default shortcut, for
  example "Find files only (ff)".
- Rewrote the readme for the `fd`/`fzf` backend, the keyword scheme and usage
  tips.

## 2026-04-01

### Internal

- Added Dependabot dependency updates and CodeQL security scanning to the CI
  workflows.

## 2026-03-29

A move off the system index to live search, with a redesigned result list.

### Added

- Fuzzy matching through `fzf`, on a new `fz` keyword.
- System file icons, resolved by type through GIO and Gtk, shown beside each
  result.
- Query highlighting, so the matched part of a result name stands out.

### Changed

- Replaced the `locate`/`plocate` backend with `fd` for instant search that
  needs no index to maintain and returns results in real time.
- New keyword scheme: `fz` (fuzzy), `f` (all), `ff` (files only), `fd`
  (directories only), replacing the earlier `fd`/`ff`/`fdir` set.
- Results show over two lines, the name and the containing path, and the
  consistent term throughout is "directory".
- Searches default to the home directory rather than the whole filesystem.
- The shortest query that triggers a search dropped from three characters to
  one.

### Fixed

- Capped the number of candidates fed to fuzzy matching so a broad `fz` query
  cannot crawl the whole filesystem before `fzf` filters it, and aligned the
  fallback base directory with the manifest default.

## 2026-03-28

### Fixed

- Saved preferences take effect on the next search instead of needing a
  Ulauncher restart, by reading them from disk on each query. This works around
  Ulauncher 6 beta not delivering preference-update events in its version 2
  compatibility mode.

## 2026-03-26

### Added

- Named actions for the Ulauncher 6 result menu, so it shows "Open" and the
  chosen Alt+Enter action rather than generic labels.

## 2026-03-24

### Added

- Initial release. Find files and directories by name with three keywords
  (`fd`, `ff`, `fdir`), case-insensitive matching through `locate`, a
  configurable result limit, and a choice of action on Alt+Enter (open the
  containing folder, open a terminal there, or copy the path). Options for
  hidden files, following symbolic links, a custom ignore file and a custom
  terminal command were present from the start.
