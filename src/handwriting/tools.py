from enum import Enum


class HandwritingTool(str, Enum):
    WRITE = "write"
    ERASE = "erase"
    SELECT_CORRECT = "select_correct"
