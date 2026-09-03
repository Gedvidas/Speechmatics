from __future__ import annotations

import json
from pathlib import Path

import pytest

from speechmatics_tools import auth
from speechmatics_tools.auth import load_api_key, resolve_workspace
from speechmatics_tools.errors import CredentialsError


def test_loads_json_key_from_default_workspace(tmp_path: Path) -> None:
    secret = tmp_path / "secrets" / "speechmatics-api-key.json"
    secret.parent.mkdir()
    secret.write_text(json.dumps({"api_key": "a" * 32}), encoding="utf-8")

    assert load_api_key(workspace=str(tmp_path)) == "a" * 32


def test_loads_api_key_from_json(tmp_path: Path) -> None:
    secret = tmp_path / "key.json"
    secret.write_text(json.dumps({"api_key": "b" * 32}), encoding="utf-8")

    assert load_api_key(credentials=str(secret)) == "b" * 32


def test_loads_plain_text_key_from_explicit_file(tmp_path: Path) -> None:
    secret = tmp_path / "key.txt"
    secret.write_text("f" * 32 + "\n", encoding="utf-8")

    assert load_api_key(credentials=str(secret)) == "f" * 32


def test_explicit_file_takes_precedence_over_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = tmp_path / "key.txt"
    secret.write_text("c" * 32, encoding="utf-8")
    monkeypatch.setenv("SPEECHMATICS_API_KEY", "d" * 32)

    assert load_api_key(credentials=str(secret)) == "c" * 32


def test_environment_key_is_supported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPEECHMATICS_API_KEY", "e" * 32)

    assert load_api_key() == "e" * 32


@pytest.mark.parametrize("value", ["", "short", "contains whitespace", "YOUR_API_KEY"])
def test_rejects_invalid_or_placeholder_keys(tmp_path: Path, value: str) -> None:
    secret = tmp_path / "key.txt"
    secret.write_text(value, encoding="utf-8")

    with pytest.raises(CredentialsError):
        load_api_key(credentials=str(secret))


def test_source_checkout_default_workspace_is_absolute_and_cwd_independent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SPEECHMATICS_WORKSPACE", raising=False)
    expected = Path(auth.__file__).resolve().parents[2] / ".local"

    monkeypatch.chdir(tmp_path)

    assert resolve_workspace(None) == expected.resolve()
    assert resolve_workspace(None).is_absolute()


def test_explicit_relative_workspace_is_normalized_to_absolute_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert resolve_workspace("private-data") == (tmp_path / "private-data").resolve()
