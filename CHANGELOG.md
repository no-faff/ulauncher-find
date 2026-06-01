# Changelog

Notable changes to Find. There are no formal releases: Ulauncher installs the
extension straight from the repository, so each entry is dated by when the
change landed on the `main` branch.

## 2026-06-01

A reliability pass on the search engine, with a full test suite behind it.

### Added

- Multi-word search. Two or more words narrow the results to paths where every
  word appears somewhere, in any order, so `ff report march` finds a
  `quarterly-report.pdf` filed under a `march` folder. A single word still
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

## 2026-04-21

### Added

- Multiple base directories: search several comma-separated locations at once.

### Changed

- Results stream in as `fd` finds them rather than waiting for the whole walk to
  finish. (This introduced an early-stop bug that was fixed on 2026-06-01.)
- Multi-word queries matched against the full path. (Superseded on 2026-06-01 by
  all-words-in-any-order matching.)

## 2026-04-01

### Added

- Dependabot and CodeQL security scanning in CI.

## 2026-03-29

A move off the system index to live search, with a redesigned result list.

### Changed

- Replaced the `locate`/`plocate` backend with `fd` for instant search that
  needs no index to maintain, plus optional fuzzy matching through `fzf`.
- New keyword scheme: `fz` (fuzzy), `f` (all), `ff` (files only), `fd`
  (directories only).
- Results show the system file icon over two lines, the name and the containing
  path, with the matched part of the name highlighted.
- Exact matching is literal, so `.`, `?` and `*` are searched as themselves
  rather than as wildcards.
- Searches default to the home directory.

### Fixed

- Capped the number of candidates fed to fuzzy matching so a broad `fz` query
  cannot crawl the whole filesystem.

## 2026-03-28

### Fixed

- Saved preferences take effect on the next search instead of needing a
  Ulauncher restart.

## 2026-03-26

### Added

- Action labels for the Ulauncher 6 result menu, so Enter and Alt+Enter read
  clearly.

## 2026-03-24

### Added

- Initial release: find files and directories by name, via `locate`.
