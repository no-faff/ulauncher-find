# Find

A [Ulauncher](https://ulauncher.io/) extension for finding files and directories by name. Uses `locate` for instant results across your entire filesystem.

![Find extension screenshot](screenshot.png)

## Features

- Three keywords: `fd` (files and directories), `ff` (files only), `fdir` (directories only)
- Instant results using a pre-built index
- Case insensitive matching on filenames
- Configurable base directory, result limit, Alt+Enter action and more

## Requirements

- Ulauncher 6 (Extension API v2)
- plocate

Install plocate if you don't have it:

```bash
# Fedora
sudo dnf install plocate

# Ubuntu/Debian
sudo apt install plocate
```

The locate database updates automatically via a systemd timer. To update it manually after adding new files:

```bash
sudo updatedb
```

## Install

Open Ulauncher preferences, go to Extensions, click "Add extension" and paste:

```
https://github.com/no-faff/ulauncher-find
```

## Settings

| Setting | Description | Default |
|---|---|---|
| fd / ff / fdir keywords | Trigger keywords for each search mode | `fd`, `ff`, `fdir` |
| Alt+Enter action | Open containing folder, open in terminal, or copy path | Open containing folder |
| Base directory | Where to search. Use `/` for everywhere | `/` |
| Result limit | Maximum results shown | 15 |
| Terminal command | Terminal for "open in terminal" action. Blank to auto-detect | (blank) |

## Usage

| Action | What it does |
|---|---|
| Enter | Opens the file or directory |
| Alt+Enter | Configurable: open folder, open terminal, or copy path |

## Licence

MIT
