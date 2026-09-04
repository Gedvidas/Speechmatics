"""HTTP client for the Speechmatics Batch Jobs API."""

from __future__ import annotations

import json
import mimetypes
import random
import re
import time
from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import requests

from .errors import ApiError, ValidationError

REGION_ENDPOINTS: Mapping[str, str] = {
    "eu1": "https://eu1.asr.api.speechmatics.com/v2",
    "eu2": "https://eu2.asr.api.speechmatics.com/v2",
    "us1": "https://us1.asr.api.speechmatics.com/v2",
    "us2": "https://us2.asr.api.speechmatics.com/v2",
    "au1": "https://au1.asr.api.speechmatics.com/v2",
}
SUPPORTED_MEDIA_SUFFIXES = {
    ".wav",
    ".mp3",
    ".aac",
    ".ogg",
    ".mpeg",
    ".amr",
    ".m4a",
    ".mp4",
    ".flac",
}
TERMINAL_STATUSES = {"done", "rejected"}
RETRYABLE_GET_STATUSES = {429, 500, 502, 503, 504}
_JOB_ID = re.compile(r"^[A-Za-z0-9]+$")


def endpoint_for_region(region: str) -> str:
    """Return the official Batch SaaS endpoint for a supported region."""

    try:
        return REGION_ENDPOINTS[region.lower()]
    except KeyError as exc:
        choices = ", ".join(REGION_ENDPOINTS)
        raise ValidationError(f"Unknown Speechmatics region `{region}`; choose: {choices}.") from exc


def validate_job_id(job_id: str) -> str:
    """Validate an opaque SaaS job ID before putting it in a URL path."""

    if not _JOB_ID.fullmatch(job_id):
        raise ValidationError("Job ID must contain ASCII letters and digits only.")
    return job_id


def validate_job_config(config: Mapping[str, Any]) -> None:
    """Check the minimal fields required by the Batch API."""

    if config.get("type") != "transcription":
        raise ValidationError("Job config `type` must be `transcription`.")
    transcription = config.get("transcription_config")
    if not isinstance(transcription, dict):
        raise ValidationError("Job config requires a `transcription_config` object.")
    language = transcription.get("language")
    if not isinstance(language, str) or not language.strip():
        raise ValidationError("Job config requires a non-empty transcription language.")


def validate_media_file(path: Path) -> Path:
    """Validate a local file against Speechmatics' documented Batch formats."""

    if not path.is_file():
        raise ValidationError(f"Media file does not exist: {path}")
    if path.suffix.lower() not in SUPPORTED_MEDIA_SUFFIXES:
        choices = ", ".join(sorted(SUPPORTED_MEDIA_SUFFIXES))
        raise ValidationError(f"Unsupported media extension `{path.suffix}`; choose: {choices}.")
    return path


def _response_message(response: requests.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    if not isinstance(body, dict):
        return ""
    message = body.get("message")
    if isinstance(message, str):
        return message[:500]
    error = body.get("error")
    if isinstance(error, str):
        return error[:500]
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        return error["message"][:500]
    return ""


class SpeechmaticsClient:
    """Authenticated operations for one Speechmatics Batch SaaS region."""

    def __init__(
        self,
        api_key: str,
        *,
        region: str = "eu1",
        session: requests.Session | None = None,
        max_retries: int = 4,
        retry_sleeper: Callable[[float], None] = time.sleep,
        retry_random: Callable[[], float] = random.random,
    ) -> None:
        if max_retries < 0:
            raise ValidationError("Retry count cannot be negative.")
        self._endpoint = endpoint_for_region(region)
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._session = session or requests.Session()
        self._max_retries = max_retries
        self._retry_sleeper = retry_sleeper
        self._retry_random = retry_random

    def _retry_delay(self, attempt: int, response: requests.Response | None = None) -> float:
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    return max(0.0, float(retry_after))
                except ValueError:
                    try:
                        retry_at = parsedate_to_datetime(retry_after)
                        if retry_at.tzinfo is None:
                            retry_at = retry_at.replace(tzinfo=UTC)
                        return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())
                    except (TypeError, ValueError, OverflowError):
                        pass
        base = min(2**attempt, 30)
        return base * (0.5 + self._retry_random())

    def _get_with_retry(
        self,
        url: str,
        *,
        params: Mapping[str, str | int],
        failure_message: str,
        timeout: tuple[int, int],
    ) -> requests.Response:
        """Retry idempotent GET operations after transient failures."""

        for attempt in range(self._max_retries + 1):
            try:
                response = self._session.get(
                    url,
                    headers=self._headers,
                    params=params,
                    timeout=timeout,
                )
            except requests.RequestException as exc:
                if attempt >= self._max_retries:
                    raise ApiError(failure_message) from exc
                self._retry_sleeper(self._retry_delay(attempt))
                continue
            if response.status_code not in RETRYABLE_GET_STATUSES or attempt >= self._max_retries:
                return response
            self._retry_sleeper(self._retry_delay(attempt, response))
        raise AssertionError("Retry loop terminated unexpectedly.")

    def _check_response(
        self,
        response: requests.Response,
        *,
        expected_status: int,
    ) -> requests.Response:
        if response.status_code == expected_status:
            return response
        detail = _response_message(response)
        suffix = f": {detail}" if detail else "."
        raise ApiError(f"Speechmatics API returned HTTP {response.status_code}{suffix}")

    def _json_object(self, response: requests.Response, *, context: str) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError as exc:
            raise ApiError(f"Speechmatics returned invalid JSON for {context}.") from exc
        if not isinstance(body, dict):
            raise ApiError(f"Speechmatics returned a non-object JSON value for {context}.")
        return body

    def create_job(self, media_path: Path, config: Mapping[str, Any]) -> dict[str, Any]:
        """Upload a local media file and create an asynchronous transcription job."""

        path = validate_media_file(media_path)
        validate_job_config(config)
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        try:
            handle = path.open("rb")
        except OSError as exc:
            raise ValidationError(f"Cannot open media file: {path}") from exc
        with handle:
            for attempt in range(self._max_retries + 1):
                if attempt:
                    handle.seek(0)
                try:
                    response = self._session.post(
                        f"{self._endpoint}/jobs",
                        headers=self._headers,
                        data={"config": json.dumps(config, ensure_ascii=False)},
                        files={"data_file": (path.name, handle, content_type)},
                        # urllib3 keeps the connect timeout on the socket while
                        # sending the multipart request body. Large WAV uploads
                        # can therefore time out during a temporary 10-second
                        # upload stall even though the connection is healthy.
                        timeout=(120, 600),
                    )
                except requests.RequestException as exc:
                    raise ApiError(
                        "The job submission outcome is unknown after a network failure. "
                        "Do not resubmit until recent Speechmatics jobs have been checked."
                    ) from exc
                if response.status_code != 429 or attempt >= self._max_retries:
                    break
                self._retry_sleeper(self._retry_delay(attempt, response))
        checked = self._check_response(response, expected_status=201)
        body = self._json_object(checked, context="job creation")
        if not isinstance(body.get("id"), str) or not body["id"]:
            raise ApiError("Speechmatics job creation response does not contain an `id`.")
        return body

    def get_job(self, job_id: str) -> dict[str, Any]:
        """Fetch one job immediately without the endpoint's default wait."""

        safe_id = validate_job_id(job_id)
        response = self._get_with_retry(
            f"{self._endpoint}/jobs/{safe_id}",
            params={"wait": 0},
            failure_message="Could not retrieve the Speechmatics job status after retries.",
            timeout=(10, 60),
        )
        checked = self._check_response(response, expected_status=200)
        body = self._json_object(checked, context="job status")
        job = body.get("job")
        if not isinstance(job, dict) or not isinstance(job.get("status"), str):
            raise ApiError("Speechmatics job response does not contain a valid `job.status`.")
        return body

    def iter_job_status(
        self,
        job_id: str,
        *,
        interval_seconds: float,
        timeout_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> Iterator[dict[str, Any]]:
        """Yield status responses until a terminal state or local timeout."""

        if interval_seconds <= 0:
            raise ValidationError("Polling interval must be greater than zero.")
        if timeout_seconds <= 0:
            raise ValidationError("Polling timeout must be greater than zero.")
        deadline = clock() + timeout_seconds
        while True:
            body = self.get_job(job_id)
            yield body
            status = body["job"]["status"]
            if status in TERMINAL_STATUSES or clock() >= deadline:
                return
            sleeper(interval_seconds)

    def download_transcript(self, job_id: str, transcript_format: str) -> bytes:
        """Download a completed transcript as validated JSON-v2 or SRT bytes."""

        safe_id = validate_job_id(job_id)
        formats = {"json": "json-v2", "srt": "srt"}
        try:
            api_format = formats[transcript_format]
        except KeyError as exc:
            raise ValidationError("Transcript format must be `json` or `srt`.") from exc
        params: dict[str, str | int] = {"format": api_format, "wait": 0}
        response = self._get_with_retry(
            f"{self._endpoint}/jobs/{safe_id}/transcript",
            params=params,
            failure_message="Could not download the Speechmatics transcript after retries.",
            timeout=(10, 120),
        )
        checked = self._check_response(response, expected_status=200)
        content = checked.content
        if not content:
            raise ApiError("Speechmatics returned an empty transcript.")
        if transcript_format == "json":
            try:
                parsed = json.loads(content)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ApiError("Speechmatics returned an invalid JSON transcript.") from exc
            if not isinstance(parsed, dict):
                raise ApiError("Speechmatics returned a non-object JSON transcript.")
        return content
