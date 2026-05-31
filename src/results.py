from __future__ import annotations

import logging
import shlex
import shutil
from pathlib import Path

import gi
gi.require_version('Gio', '2.0')
gi.require_version('Gtk', '3.0')
from gi.repository import Gio, Gtk

from ulauncher.api.shared.action.CopyToClipboardAction import CopyToClipboardAction
from ulauncher.api.shared.action.DoNothingAction import DoNothingAction
from ulauncher.api.shared.action.OpenAction import OpenAction
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction
from ulauncher.api.shared.action.RunScriptAction import RunScriptAction
from ulauncher.api.shared.item.ExtensionResultItem import ExtensionResultItem

from src.enums import AltEnterAction
from src.preferences import FindPreferences

logger = logging.getLogger(__name__)

FALLBACK_FILE_ICON = "text-x-generic"
FALLBACK_DIR_ICON = "folder"


def _get_system_icon(path: str) -> str | None:
    """Return the themed icon file for a path, or None if even the fallback is
    missing from the theme.

    Tries the file's own content-type icon via GIO first, then falls back to a
    generic file or folder icon by name, so a caller still gets something for a
    path that no longer exists. Gtk.IconTheme.get_default() is fetched each call
    rather than cached so a theme change is picked up without restarting.
    """
    icon_theme = Gtk.IconTheme.get_default()
    try:
        gio_file = Gio.File.new_for_path(path)
        info = gio_file.query_info("standard::icon", Gio.FileQueryInfoFlags.NONE, None)
        icon = info.get_icon()
        icon_info = icon_theme.lookup_by_gicon(icon, 48, 0)
        if icon_info:
            return icon_info.get_filename()
    except Exception:
        # GIO raises a wide, version-dependent set of GErrors for unreadable or
        # vanished paths; the generic fallback below covers all of them.
        logger.debug("Icon lookup failed for %s", path, exc_info=True)

    fallback_name = FALLBACK_DIR_ICON if Path(path).is_dir() else FALLBACK_FILE_ICON
    icon_info = icon_theme.lookup_icon(fallback_name, 48, 0)
    return icon_info.get_filename() if icon_info else None


# Auto-detect picks the first of these that is installed, so keep common desktop
# terminals near the top. The value is the flag set that opens the terminal in a
# given directory, with {} as the directory slot.
TERMINAL_ARGS: dict[str, list[str]] = {
    "konsole": ["--workdir", "{}"],
    "gnome-terminal": ["--working-directory", "{}"],
    # ptyxis treats --working-directory as a modifier, so it needs an explicit
    # action (--new-window) to actually open in that directory.
    "ptyxis": ["--new-window", "--working-directory", "{}"],
    "xfce4-terminal": ["--working-directory", "{}"],
    "tilix": ["--working-directory", "{}"],
    "terminator": ["--working-directory", "{}"],
    "kitty": ["--directory", "{}"],
    "alacritty": ["--working-directory", "{}"],
    "foot": ["--working-directory", "{}"],
    "wezterm": ["start", "--cwd", "{}"],
}


def _detect_terminal() -> str | None:
    for term in TERMINAL_ARGS:
        if shutil.which(term):
            return term
    return None


def _get_dirname(path_name: str) -> str:
    p = Path(path_name)
    return str(p) if p.is_dir() else str(p.parent)


def _terminal_argv(terminal_cmd: str, dirname: str) -> list[str]:
    """Resolve a terminal command into an argv list with the directory filled in.

    The {} slot is substituted after splitting, so a directory containing spaces
    stays a single argument.
    """
    if "{}" in terminal_cmd:
        return [part.replace("{}", dirname) for part in shlex.split(terminal_cmd)]
    if terminal_cmd in TERMINAL_ARGS:
        return [terminal_cmd] + [a.replace("{}", dirname) for a in TERMINAL_ARGS[terminal_cmd]]
    # Unknown terminal: best effort, pass the directory as the sole argument.
    return [terminal_cmd, dirname]


def _get_terminal_action(terminal_cmd: str | None, path: str):
    if terminal_cmd is None:
        terminal_cmd = _detect_terminal()
    if terminal_cmd is None:
        return DoNothingAction()

    argv = _terminal_argv(terminal_cmd, _get_dirname(path))
    if not argv:
        return DoNothingAction()

    # RunScriptAction runs its argument through a shell, so build one quoted
    # command string rather than handing it an argv list (which it silently
    # rejects). shlex.quote on every token keeps a directory named with shell
    # metacharacters an inert literal, not an injection.
    return RunScriptAction(" ".join(shlex.quote(part) for part in argv))


_ALT_ENTER_LABELS = {
    AltEnterAction.OPEN_FOLDER: "Open containing folder",
    AltEnterAction.OPEN_TERMINAL: "Open in terminal",
    AltEnterAction.COPY_PATH: "Copy path",
}


def _get_alt_enter_action(preferences: FindPreferences, path: str):
    if preferences.alt_enter_action == AltEnterAction.COPY_PATH:
        return CopyToClipboardAction(path)
    elif preferences.alt_enter_action == AltEnterAction.OPEN_TERMINAL:
        return _get_terminal_action(preferences.terminal_cmd, path)
    else:
        return OpenAction(_get_dirname(path))


def generate_result_items(
    preferences: FindPreferences, results: list[str]
) -> list[ExtensionResultItem]:
    alt_label = _ALT_ENTER_LABELS.get(preferences.alt_enter_action, "Secondary action")
    items = []
    for path in results:
        p = Path(path)
        icon = _get_system_icon(path) or "images/icon.png"
        items.append(
            ExtensionResultItem(
                icon=icon,
                name=p.name,
                description=str(p.parent),
                highlightable=True,
                on_enter=OpenAction(path),
                on_alt_enter=_get_alt_enter_action(preferences, path),
                # Naming the legacy actions gives the alt-enter chooser readable
                # labels instead of Ulauncher's generic defaults; the keys are
                # the ones Ulauncher maps back to on_enter/on_alt_enter.
                actions={
                    "__legacy_on_enter__": {"name": "Open"},
                    "__legacy_on_alt_enter__": {"name": alt_label},
                },
            )
        )
    return items


def generate_message(msg: str, icon: str = "icon") -> RenderResultListAction:
    return RenderResultListAction([
        ExtensionResultItem(
            icon=f"images/{icon}.png",
            name=msg,
            on_enter=DoNothingAction(),
        )
    ])
