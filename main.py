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

from src.enums import SearchType
from src.preferences import FindPreferences, get_preferences, load_preferences, validate_preferences
from src.results import generate_message, generate_result_items
from src.search import MIN_QUERY_LENGTH, search

logger = logging.getLogger(__name__)

KEYWORD_SEARCH_TYPE = {
    "kw_all": SearchType.BOTH,
    "kw_files": SearchType.FILES,
    "kw_dirs": SearchType.DIRS,
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
        if not shutil.which("locate"):
            return generate_message("plocate is not installed. Run: sudo dnf install plocate", "error")

        prefs = load_preferences()
        errors = validate_preferences(prefs)
        if errors:
            return generate_message(errors[0], "error")

        query = event.get_argument()
        if not query or len(query) < MIN_QUERY_LENGTH:
            return generate_message(f"Type at least {MIN_QUERY_LENGTH} characters to search.")

        # Work out which keyword was used to determine search type
        keyword = event.get_keyword()
        search_type = SearchType.BOTH
        for kw_id, kw_type in KEYWORD_SEARCH_TYPE.items():
            if extension.preferences.get(kw_id) == keyword:
                search_type = kw_type
                break

        results = search(
            preferences=prefs,
            query=query,
            search_type=search_type,
        )

        if not results:
            return generate_message("No results found.")

        items = generate_result_items(prefs, results)
        return RenderResultListAction(items)


if __name__ == "__main__":
    FindExtension().run()
