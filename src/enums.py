from enum import Enum


class AltEnterAction(Enum):
    OPEN_FOLDER = 0
    OPEN_TERMINAL = 1
    COPY_PATH = 2


class SearchType(Enum):
    BOTH = 0
    FILES = 1
    DIRS = 2
