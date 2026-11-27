"""CLI token UX tests: no live credentials or network calls."""
from __future__ import annotations

import builtins
import getpass

import pytest

from mako_intelligence.tools.yandex_direct_probe import prompt_for_token


def test_hidden_input_confirms_character_count_without_exposing_token(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    token = "TEST-NOT-A-REAL-TOKEN"
    monkeypatch.setattr(builtins, "input", lambda _prompt: "2")
    monkeypatch.setattr(getpass, "getpass", lambda _prompt: token)
    assert prompt_for_token() == token
    output = capsys.readouterr().out
    assert f"{len(token)} символов" in output
    assert token not in output


def test_visible_mode_available_only_by_explicit_choice(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    token = "VISIBLE-TEST-TOKEN-NOT-REAL"
    answers = iter(["1", token])
    monkeypatch.setattr(builtins, "input", lambda _prompt: next(answers))
    monkeypatch.setattr(getpass, "getpass", lambda _prompt: pytest.fail("hidden prompt used"))
    assert prompt_for_token() == token
    output = capsys.readouterr().out
    assert "ВНИМАНИЕ" in output
    assert f"{len(token)} символов" in output
    assert token not in output


def test_default_mode_is_hidden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(builtins, "input", lambda _prompt: "")
    monkeypatch.setattr(getpass, "getpass", lambda _prompt: "TEST-TOKEN")
    assert prompt_for_token() == "TEST-TOKEN"


@pytest.mark.parametrize("choice", ["3", "invalid"])
def test_unsupported_input_mode_rejected(
    monkeypatch: pytest.MonkeyPatch, choice: str
) -> None:
    monkeypatch.setattr(builtins, "input", lambda _prompt: choice)
    with pytest.raises(ValueError, match="режим ввода"):
        prompt_for_token()


def test_empty_token_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(builtins, "input", lambda _prompt: "1")
    with pytest.raises(ValueError, match="Токен пустой"):
        prompt_for_token()
