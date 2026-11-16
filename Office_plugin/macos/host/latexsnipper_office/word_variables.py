"""Write Word document variables for the add-in pages.

The Windows add-in keeps formula metadata in Word document variables
(``LaTeXSnipper.DocumentId`` and ``LS.E.<equationId>.<revision>``). Office.js
can read them (they are part of ``body.getOoxml()``) but cannot write them,
while Word's AppleScript dictionary can. The page marks its document with a
hidden bookmark first, so the script writes to exactly that document even when
several are open.
"""

from __future__ import annotations

import logging
import re
import subprocess

logger = logging.getLogger(f"latexsnipper.{__name__}")

MAX_VARIABLES = 50
MAX_VALUE_LENGTH = 60000
TIMEOUT_SECONDS = 30
_MARKER = re.compile(r"\A_LSLink[0-9a-f]{16,32}\Z")
_NAME = re.compile(
    r"\A(?:LaTeXSnipper\.DocumentId|LS\.E\.[0-9a-f]{32}\.[0-9a-f]{10})\Z"
)

# Arguments: marker, then name/value pairs. Errors 1001 and -1743 are mapped below.
_SCRIPT = """
on run argv
  set marker to item 1 of argv
  tell application id "com.microsoft.Word"
    repeat with documentIndex from 1 to (count of documents)
      set wordDocument to document documentIndex
      if (exists bookmark marker of wordDocument) then
        repeat with pairIndex from 2 to (count of argv) by 2
          set variableName to item pairIndex of argv
          set variableValue to item (pairIndex + 1) of argv
          if (exists variable variableName of wordDocument) then
            set variable value of variable variableName of wordDocument to variableValue
          else
            make new variable at wordDocument with properties {name:variableName, variable value:variableValue}
          end if
        end repeat
        return "ok"
      end if
    end repeat
  end tell
  error "marker not found" number 1001
end run
"""


class WordVariablesError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def validate(marker: object, values: object) -> list[tuple[str, str]]:
    if not isinstance(marker, str) or not _MARKER.match(marker):
        raise WordVariablesError(400, "invalid_request", "文档标记无效。")
    if not isinstance(values, dict) or not 1 <= len(values) <= MAX_VARIABLES:
        raise WordVariablesError(400, "invalid_request", "文档变量无效。")
    pairs = []
    for name, value in values.items():
        if not _NAME.match(name) or not isinstance(value, str):
            raise WordVariablesError(400, "invalid_request", "文档变量无效。")
        if not value or len(value) > MAX_VALUE_LENGTH or "\x00" in value:
            raise WordVariablesError(400, "invalid_request", "文档变量内容无效。")
        pairs.append((name, value))
    return pairs


class WordVariables:
    def write(self, marker: object, values: object) -> dict[str, int]:
        pairs = validate(marker, values)
        arguments = [str(marker)] + [part for pair in pairs for part in pair]
        try:
            result = subprocess.run(
                ["/usr/bin/osascript", "-", *arguments],
                input=_SCRIPT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise WordVariablesError(
                504, "word_timeout", "Word 未及时响应，公式数据未写入。"
            ) from None
        if result.returncode != 0:
            raise _error(result.stderr)
        logger.info("wrote %d Word document variables", len(pairs))
        return {"written": len(pairs)}


def _error(stderr: str) -> WordVariablesError:
    if "-1743" in stderr:
        return WordVariablesError(
            403,
            "word_automation_denied",
            "macOS 未允许 LaTeXSnipper Office 控制 Microsoft Word。请在“系统设置 › 隐私与安全性 › 自动化”中允许后重试。",
        )
    if "1001" in stderr:
        return WordVariablesError(
            409, "word_document_unknown", "无法定位当前 Word 文档，请重试。"
        )
    logger.warning("osascript failed: %s", stderr.strip())
    return WordVariablesError(502, "word_variables_failed", "Word 未能保存公式数据。")


__all__ = ["WordVariables", "WordVariablesError", "validate"]
