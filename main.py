from __future__ import annotations

import logging
import shutil

from ulauncher.api.client.EventListener import EventListener
from ulauncher.api.client.Extension import Extension
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction
from ulauncher.api.shared.event import (
    KeywordQueryEvent,
    PreferencesEvent,
    PreferencesUpdateEvent,
)

from src.enums import MatchMode, SearchType
from src.preferences import (
    FindPreferences,
    get_preferences,
    load_raw_preferences,
    validate_preferences,
)
from src.results import generate_message, generate_result_items
from src.search import MIN_QUERY_LENGTH, SearchError, _resolve_fd_binary, search

logger = logging.getLogger(__name__)

KEYWORD_SEARCH_TYPE = {
    "kw_fz": SearchType.BOTH,
    "kw_all": SearchType.BOTH,
    "kw_files": SearchType.FILES,
    "kw_dirs": SearchType.DIRS,
}

KEYWORD_MATCH_MODE = {
    "kw_fz": MatchMode.FUZZY,
    "kw_all": MatchMode.EXACT,
    "kw_files": MatchMode.EXACT,
    "kw_dirs": MatchMode.EXACT,
}


class FindExtension(Extension):
    typed_preferences: FindPreferences

    def __init__(self) -> None:
        super().__init__()
        self.subscribe(PreferencesEvent, PreferencesEventListener())
        self.subscribe(PreferencesUpdateEvent, PreferencesUpdateEventListener())
        self.subscribe(KeywordQueryEvent, KeywordQueryEventListener())


class PreferencesEventListener(EventListener):
    def on_event(self, event: PreferencesEvent, extension: FindExtension) -> None:
        extension.typed_preferences = get_preferences(event.preferences)


class PreferencesUpdateEventListener(EventListener):
    def on_event(
        self, event: PreferencesUpdateEvent, extension: FindExtension
    ) -> None:
        preferences = extension.preferences
        preferences[event.id] = event.new_value
        extension.typed_preferences = get_preferences(preferences)


class KeywordQueryEventListener(EventListener):
    def on_event(
        self, event: KeywordQueryEvent, extension: FindExtension
    ) -> RenderResultListAction:
        if not _resolve_fd_binary():
            return generate_message("fd is not installed. Run: sudo dnf install fd-find", "error")

        raw_prefs = load_raw_preferences()
        prefs = get_preferences(raw_prefs)
        errors = validate_preferences(prefs)
        if errors:
            return generate_message(errors[0], "error")

        query = event.get_argument()
        if not query or len(query) < MIN_QUERY_LENGTH:
            noun = "character" if MIN_QUERY_LENGTH == 1 else "characters"
            return generate_message(f"Type at least {MIN_QUERY_LENGTH} {noun} to search.")

        keyword = event.get_keyword()
        search_type = SearchType.BOTH
        match_mode = MatchMode.EXACT
        for kw_id in KEYWORD_SEARCH_TYPE:
            if raw_prefs.get(kw_id) == keyword:
                search_type = KEYWORD_SEARCH_TYPE[kw_id]
                match_mode = KEYWORD_MATCH_MODE[kw_id]
                break

        if match_mode == MatchMode.FUZZY and not shutil.which("fzf"):
            return generate_message("fzf is not installed. Run: sudo dnf install fzf", "error")

        try:
            results = search(
                preferences=prefs,
                query=query,
                search_type=search_type,
                match_mode=match_mode,
            )
        except SearchError as exc:
            return generate_message(str(exc), "error")

        if not results:
            return generate_message("No results found.")

        items = generate_result_items(prefs, results)
        return RenderResultListAction(items)


if __name__ == "__main__":
    FindExtension().run()
