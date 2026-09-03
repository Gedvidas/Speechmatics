from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest

from speechmatics_tools.cli_common import connection_from_args
from speechmatics_tools.errors import ValidationError
from speechmatics_tools.job_store import load_job_record, save_job_record


def connection_args(workspace: Path, *, region: str | None = None) -> Namespace:
    secret = workspace / "secrets" / "speechmatics-api-key.json"
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text(json.dumps({"api_key": "a" * 32}), encoding="utf-8")
    return Namespace(workspace=str(workspace), credentials=None, region=region)


def test_job_record_round_trip_contains_only_safe_resume_metadata(tmp_path: Path) -> None:
    path = save_job_record(
        tmp_path,
        job_id="abc123def4",
        region="us1",
        data_name="interview.wav",
        created_at="2026-09-03T20:00:00+00:00",
    )

    assert path == tmp_path / "jobs" / "abc123def4.json"
    assert load_job_record(tmp_path, "abc123def4") == {
        "schema_version": 1,
        "id": "abc123def4",
        "region": "us1",
        "data_name": "interview.wav",
        "created_at": "2026-09-03T20:00:00+00:00",
    }
    assert "api_key" not in path.read_text(encoding="utf-8")


def test_saved_region_wins_over_environment_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args = connection_args(tmp_path)
    save_job_record(
        tmp_path,
        job_id="abc123def4",
        region="us1",
        data_name="interview.wav",
    )
    monkeypatch.setenv("SPEECHMATICS_REGION", "eu1")

    connection = connection_from_args(args, job_id="abc123def4")

    assert connection.region == "us1"


def test_explicit_region_cannot_conflict_with_saved_job(tmp_path: Path) -> None:
    args = connection_args(tmp_path, region="eu1")
    save_job_record(
        tmp_path,
        job_id="abc123def4",
        region="us1",
        data_name="interview.wav",
    )

    with pytest.raises(ValidationError, match="was created in `us1`"):
        connection_from_args(args, job_id="abc123def4")


def test_missing_record_uses_explicit_region(tmp_path: Path) -> None:
    connection = connection_from_args(connection_args(tmp_path, region="au1"), job_id="abc123def4")

    assert connection.region == "au1"


def test_corrupt_record_is_not_silently_ignored(tmp_path: Path) -> None:
    path = tmp_path / "jobs" / "abc123def4.json"
    path.parent.mkdir()
    path.write_text("not-json", encoding="utf-8")

    with pytest.raises(ValidationError, match="not valid JSON"):
        load_job_record(tmp_path, "abc123def4")
