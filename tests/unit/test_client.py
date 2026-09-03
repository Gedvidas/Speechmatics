from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
import requests

from speechmatics_tools.client import SpeechmaticsClient, validate_job_id
from speechmatics_tools.errors import ApiError, ValidationError


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        body: object | None = None,
        content: bytes | None = None,
    ) -> None:
        self.status_code = status_code
        self._body = body
        self.content = content if content is not None else json.dumps(body).encode()

    def json(self) -> object:
        if self._body is None:
            raise ValueError("not JSON")
        return self._body


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = iter(responses)
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def _call(self, method: str, url: str, kwargs: dict[str, Any]) -> FakeResponse:
        self.calls.append((method, url, kwargs))
        return next(self.responses)

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        return self._call("POST", url, kwargs)

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        return self._call("GET", url, kwargs)


def client_with(session: FakeSession, *, region: str = "eu1") -> SpeechmaticsClient:
    return SpeechmaticsClient("secret-key-value-123456", region=region, session=cast(requests.Session, session))


def test_create_job_uses_expected_multipart_request(tmp_path: Path) -> None:
    media = tmp_path / "sample.mp3"
    media.write_bytes(b"audio")
    session = FakeSession([FakeResponse(201, {"id": "abc123def4"})])
    config = {
        "type": "transcription",
        "transcription_config": {"language": "en"},
    }

    result = client_with(session).create_job(media, config)

    assert result == {"id": "abc123def4"}
    method, url, kwargs = session.calls[0]
    assert method == "POST"
    assert url == "https://eu1.asr.api.speechmatics.com/v2/jobs"
    assert kwargs["headers"]["Authorization"] == "Bearer secret-key-value-123456"
    assert json.loads(kwargs["data"]["config"]) == config
    assert kwargs["files"]["data_file"][0] == "sample.mp3"


def test_get_job_uses_same_selected_region_and_no_server_wait() -> None:
    session = FakeSession([FakeResponse(200, {"job": {"id": "abc123", "status": "running"}})])

    body = client_with(session, region="us1").get_job("abc123")

    assert body["job"]["status"] == "running"
    _, url, kwargs = session.calls[0]
    assert url == "https://us1.asr.api.speechmatics.com/v2/jobs/abc123"
    assert kwargs["params"] == {"wait": 0}


def test_iter_job_status_stops_when_done() -> None:
    session = FakeSession(
        [
            FakeResponse(200, {"job": {"id": "abc123", "status": "running"}}),
            FakeResponse(200, {"job": {"id": "abc123", "status": "done"}}),
        ]
    )
    sleeps: list[float] = []
    times: Iterator[float] = iter([0.0, 1.0])

    statuses = list(
        client_with(session).iter_job_status(
            "abc123",
            interval_seconds=2.5,
            timeout_seconds=30,
            clock=lambda: next(times),
            sleeper=sleeps.append,
        )
    )

    assert [body["job"]["status"] for body in statuses] == ["running", "done"]
    assert sleeps == [2.5]


@pytest.mark.parametrize(
    ("requested", "api_format", "content"),
    [
        ("json", "json-v2", b'{"format":"2.1"}'),
        ("srt", "srt", b"1\n00:00:00,000 --> 00:00:01,000\nHello\n"),
    ],
)
def test_download_transcript_selects_format(
    requested: str, api_format: str, content: bytes
) -> None:
    session = FakeSession([FakeResponse(200, content=content)])

    assert client_with(session).download_transcript("abc123", requested) == content
    _, _, kwargs = session.calls[0]
    assert kwargs["params"] == {"format": api_format, "wait": 0}


def test_api_error_does_not_expose_authorization_value() -> None:
    session = FakeSession([FakeResponse(401, {"message": "Unauthorized"})])

    with pytest.raises(ApiError) as captured:
        client_with(session).get_job("abc123")

    assert "secret-key-value" not in str(captured.value)
    assert "HTTP 401" in str(captured.value)


@pytest.mark.parametrize("job_id", ["../secret", "abc-123", "", "jobs/123"])
def test_rejects_unsafe_job_ids(job_id: str) -> None:
    with pytest.raises(ValidationError):
        validate_job_id(job_id)
