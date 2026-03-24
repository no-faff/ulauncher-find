from __future__ import annotations

import logging
import shutil
from pathlib import Path

from ulauncher.api.shared.action.CopyToClipboardAction import CopyToClipboardAction
from ulauncher.api.shared.action.DoNothingAction import DoNothingAction
from ulauncher.api.shared.action.OpenAction import OpenAction
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction
from ulauncher.api.shared.action.RunScriptAction import RunScriptAction
from ulauncher.api.shared.item.ExtensionResultItem import ExtensionResultItem
from ulauncher.api.shared.item.ExtensionSmallResultItem import ExtensionSmallResultItem

from src.enums import AltEnterAction
from src.preferences import FindPreferences

logger = logging.getLogger(__name__)

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


def _get_alt_enter_action(preferences: FindPreferences, path: str):
    if preferences.alt_enter_action == AltEnterAction.COPY_PATH:
        return CopyToClipboardAction(path)
    elif preferences.alt_enter_action == AltEnterAction.OPEN_TERMINAL:
        return _get_terminal_action(preferences.terminal_cmd, path)
    else:
        return OpenAction(_get_dirname(path))


def generate_result_items(
    preferences: FindPreferences, results: list[str]
) -> list[ExtensionSmallResultItem]:
    items = []
    for path in results:
        items.append(
            ExtensionSmallResultItem(
                icon="images/sub-icon.png",
                name=path,
                on_enter=OpenAction(path),
                on_alt_enter=_get_alt_enter_action(preferences, path),
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
