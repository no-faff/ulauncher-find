from __future__ import annotations

import logging
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

_icon_theme = Gtk.IconTheme.get_default()

FALLBACK_FILE_ICON = "text-x-generic"
FALLBACK_DIR_ICON = "folder"


def _get_system_icon(path: str) -> str | None:
    """Resolve the system icon for a file path. Returns the icon's filesystem path."""
    try:
        gio_file = Gio.File.new_for_path(path)
        info = gio_file.query_info("standard::icon", Gio.FileQueryInfoFlags.NONE, None)
        icon = info.get_icon()
        icon_info = _icon_theme.lookup_by_gicon(icon, 48, 0)
        if icon_info:
            return icon_info.get_filename()
    except Exception:
        pass

    # Fallback to generic system icon
    fallback_name = FALLBACK_DIR_ICON if Path(path).is_dir() else FALLBACK_FILE_ICON
    icon_info = _icon_theme.lookup_icon(fallback_name, 48, 0)
    return icon_info.get_filename() if icon_info else None

TERMINALS = ["konsole", "gnome-terminal", "xfce4-terminal", "tilix", "terminator", "kitty", "alacritty"]


def _detect_terminal() -> str | None:
    for term in TERMINALS:
        if shutil.which(term):
            return term
    return None


def _get_dirname(path_name: str) -> str:
    p = Path(path_name)
    return str(p) if p.is_dir() else str(p.parent)


def _get_terminal_action(terminal_cmd: str | None, path: str):
    dirname = _get_dirname(path)

    if terminal_cmd is None:
        terminal_cmd = _detect_terminal()

    if terminal_cmd is None:
        return DoNothingAction()

    if terminal_cmd in ("konsole", "gnome-terminal", "tilix", "terminator", "xfce4-terminal"):
        return RunScriptAction(terminal_cmd, ["--working-directory", dirname])
    elif terminal_cmd in ("kitty", "alacritty"):
        return RunScriptAction(terminal_cmd, ["--directory", dirname])
    else:
        return RunScriptAction(terminal_cmd, [dirname])


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
