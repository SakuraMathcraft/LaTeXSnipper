from __future__ import annotations

import subprocess

import pytest
from latexsnipper_office import word_variables
from latexsnipper_office.word_variables import WordVariables, WordVariablesError

MARKER = "_LSLink0123456789abcdef"
NAME = "LS.E.0123456789abcdef0123456789abcdef.abcdef0123"


class FakeRun:
    def __init__(self, returncode=0, stderr=""):
        self.returncode = returncode
        self.stderr = stderr
        self.calls = []

    def __call__(self, command, **options):
        self.calls.append((command, options))
        return subprocess.CompletedProcess(command, self.returncode, "ok", self.stderr)


def test_writes_name_value_pairs_to_the_marked_document_as_utf8(monkeypatch):
    run = FakeRun()
    monkeypatch.setattr(word_variables.subprocess, "run", run)
    value = '{"latex":"\\\\frac{面积}{2}"}'
    assert WordVariables().write(
        MARKER, {"LaTeXSnipper.DocumentId": "a" * 32, NAME: value}
    ) == {"written": 2}
    ((command, options),) = run.calls
    assert command == [
        "/usr/bin/osascript",
        "-",
        MARKER,
        "LaTeXSnipper.DocumentId",
        "a" * 32,
        NAME,
        value,
    ]
    assert options["encoding"] == "utf-8" and options["input"] == word_variables._SCRIPT


@pytest.mark.parametrize(
    "marker, values",
    [
        ("_LSLinkXYZ", {NAME: "x"}),
        (MARKER, {}),
        (MARKER, {"Other": "x"}),
        (MARKER, {"LS.E.short.abcdef0123": "x"}),
        (MARKER, {NAME: ""}),
        (MARKER, {NAME: 3}),
        (MARKER, {NAME: "a\x00b"}),
        (MARKER, {f"LS.E.{i:032x}.abcdef0123": "x" for i in range(51)}),
    ],
)
def test_only_plugin_variables_with_valid_values_are_accepted(
    marker, values, monkeypatch
):
    monkeypatch.setattr(word_variables.subprocess, "run", FakeRun())
    with pytest.raises(WordVariablesError) as raised:
        WordVariables().write(marker, values)
    assert raised.value.status == 400


@pytest.mark.parametrize(
    "stderr, status, code",
    [
        (
            "execution error: Not authorized to send Apple events to Microsoft Word. (-1743)",
            403,
            "word_automation_denied",
        ),
        ("execution error: marker not found (1001)", 409, "word_document_unknown"),
        (
            "execution error: Microsoft Word got an error (-10000)",
            502,
            "word_variables_failed",
        ),
    ],
)
def test_script_failures_become_actionable_errors(stderr, status, code, monkeypatch):
    monkeypatch.setattr(word_variables.subprocess, "run", FakeRun(1, stderr))
    with pytest.raises(WordVariablesError) as raised:
        WordVariables().write(MARKER, {NAME: "x"})
    assert (raised.value.status, raised.value.code) == (status, code)


def test_timeout_is_reported(monkeypatch):
    def slow(command, **options):
        raise subprocess.TimeoutExpired(command, options["timeout"])

    monkeypatch.setattr(word_variables.subprocess, "run", slow)
    with pytest.raises(WordVariablesError, match="未及时响应"):
        WordVariables().write(MARKER, {NAME: "x"})
