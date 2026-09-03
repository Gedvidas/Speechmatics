"""Resolve and validate Speechmatics API credentials."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .errors import CredentialsError

DEFAULT_WORKSPACE = Path(".local")
DEFAULT_CREDENTIALS_NAME = "speechmatics-api-key.json"


def resolve_workspace(value: str | None) -> Path:
    """Resolve an explicit, environment, or repository-local private workspace."""

    raw = value or os.environ.get("SPEECHMATICS_WORKSPACE")
    return Path(raw).expanduser() if raw else DEFAULT_WORKSPACE


def resolve_credentials(workspace: Path, value: str | None) -> Path:
    """Resolve an explicit credentials path or the default private key file."""

    return Path(value).expanduser() if value else workspace / "secrets" / DEFAULT_CREDENTIALS_NAME


def _key_from_json(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and isinstance(value.get("api_key"), str):
        return value["api_key"]
    raise CredentialsError("Credentials JSON must contain an `api_key` string.")


def _validate_api_key(value: str) -> str:
    key = value.strip()
    if len(key) < 16 or any(character.isspace() for character in key):
        raise CredentialsError("The Speechmatics API key has an invalid format.")
    if key.upper().startswith("YOUR_"):
        raise CredentialsError("Replace the placeholder with a real Speechmatics API key.")
    return key


def load_api_key(*, workspace: str | None = None, credentials: str | None = None) -> str:
    """Load an API key from an explicit file, the environment, or `.local`."""

    if credentials is None:
        environment_key = os.environ.get("SPEECHMATICS_API_KEY")
        if environment_key:
            return _validate_api_key(environment_key)

    path = resolve_credentials(resolve_workspace(workspace), credentials)
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise CredentialsError(f"Cannot read Speechmatics credentials file: {path}") from exc

    if not raw:
        raise CredentialsError(f"Speechmatics credentials file is empty: {path}")

    if raw.startswith(("{", '"')):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CredentialsError(f"Credentials file is not valid JSON: {path}") from exc
        return _validate_api_key(_key_from_json(value))
    return _validate_api_key(raw)
