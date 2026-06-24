from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "macos-ci-artifact.yml"


def test_macos_ci_artifact_workflow_has_safe_triggers() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "name: macOS CI Artifact" in text
    assert "workflow_dispatch:" in text
    assert "branches:\n      - main\n      - office-plugin" in text
    assert "codex/macos-native-experience" not in text
    assert "tags-ignore:\n      - '**'" in text
    assert "release:" not in text
    assert "tags:\n" not in text
    assert "v*" not in text


def test_macos_ci_artifact_workflow_runs_macos_tests_before_building() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "full-tests:" in text
    assert "build-macos-artifact:" in text
    assert text.count("lfs: true") >= 2
    assert "needs: full-tests" in text
    assert "ubuntu-latest" not in text
    assert "macos-latest" not in text
    assert text.count("runs-on: macos-15") == 2
    assert "python-version: '3.11'" in text
    assert "python -m pytest --collect-only -q" in text
    assert "python -m pytest -q" in text
    assert "git diff --check" in text


def test_macos_ci_artifact_workflow_uploads_unsigned_ci_artifact_only() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "CI: \"1\"" in text
    assert "SKIP_CODESIGN: \"1\"" in text
    assert "SKIP_NOTARIZE: \"1\"" in text
    assert "CODESIGN_IDENTITY" not in text
    assert "APPLE_ID" not in text
    assert "APPLE_APP_PASSWORD" not in text
    assert "APPLE_TEAM_ID" not in text
    assert "gh release" not in text
    assert "softprops/action-gh-release" not in text
    assert "actions/checkout@v6" in text
    assert "actions/setup-python@v6" in text
    assert "actions/upload-artifact@v7" in text
    assert "LaTeXSnipper-macOS-app-ci-unsigned-${{ github.sha }}" in text
    assert "dist/LaTeXSnipper_*.app.zip" in text
    assert "dist/LaTeXSnipper*.dmg" in text
    assert "dist/**/*.app" not in text
    assert "build/**/*.app" not in text
    assert "build/**/*.zip" not in text
    assert "build/**/*.dmg" not in text
    assert "retention-days: 7" in text
