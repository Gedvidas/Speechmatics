"""Shared command-line helpers."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Sequence

from .auth import load_api_key
from .client import REGION_ENDPOINTS, SpeechmaticsClient
from .errors import SpeechmaticsToolsError, ValidationError


def add_connection_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the private workspace and regional endpoint arguments."""

    parser.add_argument("--credentials", help="Plain-text or JSON API-key file.")
    parser.add_argument(
        "--workspace",
        help="Private workspace (default: SPEECHMATICS_WORKSPACE or .local).",
    )
    default_region = os.environ.get("SPEECHMATICS_REGION", "eu1").lower()
    if default_region not in REGION_ENDPOINTS:
        default_region = "eu1"
    parser.add_argument(
        "--region",
        choices=tuple(REGION_ENDPOINTS),
        default=default_region,
        help="Batch SaaS region; use the same region for every operation on a job.",
    )


def client_from_args(args: argparse.Namespace) -> SpeechmaticsClient:
    """Create an authenticated client from shared parsed arguments."""

    api_key = load_api_key(workspace=args.workspace, credentials=args.credentials)
    return SpeechmaticsClient(api_key, region=args.region)


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
