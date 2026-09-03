"""Persist non-secret metadata needed to resume Speechmatics jobs safely."""

from __future__ import annotations

import json
import os
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .client import REGION_ENDPOINTS, validate_job_id
from .errors import ValidationError

SCHEMA_VERSION = 1


def job_record_path(workspace: Path, job_id: str) -> Path:
    """Return a traversal-safe path for one local job record."""

    return workspace / "jobs" / f"{validate_job_id(job_id)}.json"


def save_job_record(
    workspace: Path,
    *,
    job_id: str,
    region: str,
    data_name: str,
    created_at: str | None = None,
) -> Path:
    """Atomically save the endpoint metadata required by later commands."""

    if region not in REGION_ENDPOINTS:
        raise ValidationError(f"Cannot save job record with unknown region `{region}`.")
    if not data_name:
        raise ValidationError("Cannot save a job record without a media file name.")
    destination = job_record_path(workspace, job_id)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "id": job_id,
        "region": region,
        "data_name": data_name,
        "created_at": created_at or datetime.now(UTC).isoformat(),
    }
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except OSError as exc:
        with suppress(OSError):
            temporary.unlink(missing_ok=True)
        raise ValidationError(f"Cannot save local job record: {destination}") from exc
    return destination


def load_job_record(workspace: Path, job_id: str) -> dict[str, Any] | None:
    """Load and validate a local job record, or return `None` when it is absent."""

    path = job_record_path(workspace, job_id)
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValidationError(f"Cannot read local job record: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Local job record is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"Local job record must be a JSON object: {path}")
    if value.get("schema_version") != SCHEMA_VERSION or value.get("id") != job_id:
        raise ValidationError(f"Local job record has invalid identity or schema: {path}")
    region = value.get("region")
    if not isinstance(region, str) or region not in REGION_ENDPOINTS:
        raise ValidationError(f"Local job record has an invalid region: {path}")
    return value
