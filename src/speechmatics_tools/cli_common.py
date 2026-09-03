"""Shared command-line helpers."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .auth import load_api_key, resolve_workspace
from .client import REGION_ENDPOINTS, SpeechmaticsClient, endpoint_for_region
from .errors import SpeechmaticsToolsError, ValidationError
from .job_store import load_job_record


@dataclass(frozen=True)
class Connection:
    client: SpeechmaticsClient
    workspace: Path
    region: str


def add_connection_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the private workspace and regional endpoint arguments."""

    parser.add_argument("--credentials", help="Plain-text or JSON API-key file.")
    parser.add_argument(
        "--workspace",
        help="Private workspace (default: SPEECHMATICS_WORKSPACE or .local).",
    )
    parser.add_argument(
        "--region",
        choices=tuple(REGION_ENDPOINTS),
        default=None,
        help="Batch SaaS region (saved job region, SPEECHMATICS_REGION, or eu1).",
    )


def resolve_region(value: str | None) -> str:
    """Resolve and validate an explicit, environment, or default region."""

    region = (value or os.environ.get("SPEECHMATICS_REGION") or "eu1").lower()
    endpoint_for_region(region)
    return region


def connection_from_args(
    args: argparse.Namespace,
    *,
    job_id: str | None = None,
) -> Connection:
    """Resolve credentials, workspace, and the correct endpoint for a command."""

    workspace = resolve_workspace(args.workspace)
    explicit_region = args.region
    record = load_job_record(workspace, job_id) if job_id else None
    if record is not None:
        saved_region = record["region"]
        if explicit_region is not None and explicit_region != saved_region:
            raise ValidationError(
                f"Job `{job_id}` was created in `{saved_region}`, not `{explicit_region}`."
            )
        region = saved_region
    else:
        region = resolve_region(explicit_region)
    api_key = load_api_key(workspace=str(workspace), credentials=args.credentials)
    return Connection(
        client=SpeechmaticsClient(api_key, region=region),
        workspace=workspace,
        region=region,
    )


def print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def run_command(
    runner: Callable[[argparse.Namespace], int],
    parser: argparse.ArgumentParser,
    argv: Sequence[str] | None,
) -> int:
    """Translate expected failures and Ctrl+C into stable process exit codes."""

    try:
        return runner(parser.parse_args(argv))
    except (SpeechmaticsToolsError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted by user.", file=sys.stderr)
        return 130


def require_json_object(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValidationError(f"{context} must be a JSON object.")
    return value
